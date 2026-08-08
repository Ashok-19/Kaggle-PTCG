from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Iterable, Mapping

from .memory import PublicGameMemory


@dataclass(frozen=True)
class DeckTemplate:
    """One legal 60-card hypothesis; it is not a claim about hidden truth."""

    name: str
    cards: tuple[int, ...]
    signature_ids: frozenset[int] = frozenset()
    source: str = ""

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("deck template name must be non-empty")
        if len(self.cards) != 60:
            raise ValueError(f"deck template {self.name!r} must contain exactly 60 cards")
        if any(isinstance(card, bool) or not isinstance(card, int) or card <= 0 for card in self.cards):
            raise ValueError(f"deck template {self.name!r} contains an invalid card ID")
        if not self.signature_ids.issubset(set(self.cards)):
            raise ValueError("signature IDs must be present in the template")

    @property
    def counts(self) -> Counter[int]:
        return Counter(self.cards)


@dataclass(frozen=True)
class TemplateSupport:
    name: str
    compatible: bool
    support_score: float
    normalized_weight: float
    distinct_observed: int
    matched_copies: int
    signature_hits: int
    contradictions: tuple[tuple[int, int, int], ...] = ()


class ArchetypeRegistry:
    """Rank deck hypotheses from public evidence while preserving uncertainty."""

    def __init__(self, templates: Iterable[DeckTemplate]) -> None:
        values = tuple(templates)
        if not values:
            raise ValueError("at least one deck template is required")
        names = [template.name for template in values]
        if len(names) != len(set(names)):
            raise ValueError("deck template names must be unique")
        self.templates = values

    def rank(self, memory: PublicGameMemory | Mapping[int, int]) -> tuple[TemplateSupport, ...]:
        observed = (
            memory.opponent_observed_card_counts()
            if isinstance(memory, PublicGameMemory)
            else Counter(
                {int(card): int(count) for card, count in memory.items() if int(count) > 0}
            )
        )
        raw = []
        for template in self.templates:
            counts = template.counts
            contradictions = tuple(
                sorted(
                    (card_id, count, counts.get(card_id, 0))
                    for card_id, count in observed.items()
                    if count > counts.get(card_id, 0)
                )
            )
            compatible = not contradictions
            matched_copies = sum(
                min(count, counts.get(card_id, 0)) for card_id, count in observed.items()
            )
            distinct = sum(1 for card_id in observed if counts.get(card_id, 0) > 0)
            signature_hits = sum(
                1 for card_id in template.signature_ids if observed.get(card_id, 0) > 0
            )
            # Deterministic support only; this is deliberately not a calibrated posterior.
            score = (
                float(signature_hits * 4 + distinct + 0.25 * matched_copies)
                if compatible
                else 0.0
            )
            raw.append(
                (
                    template,
                    compatible,
                    score,
                    distinct,
                    matched_copies,
                    signature_hits,
                    contradictions,
                )
            )

        compatible_rows = [row for row in raw if row[1]]
        all_zero = bool(compatible_rows) and all(row[2] == 0.0 for row in compatible_rows)
        total = (
            float(len(compatible_rows))
            if all_zero
            else sum(row[2] for row in compatible_rows)
        )
        results = []
        for template, compatible, score, distinct, copies, signature_hits, contradictions in raw:
            if not compatible or total == 0.0:
                weight = 0.0
            elif all_zero:
                weight = 1.0 / len(compatible_rows)
            else:
                weight = score / total
            results.append(
                TemplateSupport(
                    name=template.name,
                    compatible=compatible,
                    support_score=score,
                    normalized_weight=weight,
                    distinct_observed=distinct,
                    matched_copies=copies,
                    signature_hits=signature_hits,
                    contradictions=contradictions,
                )
            )
        return tuple(
            sorted(
                results,
                key=lambda item: (
                    item.compatible,
                    item.normalized_weight,
                    item.signature_hits,
                    item.distinct_observed,
                    item.name,
                ),
                reverse=True,
            )
        )

    def weighted_templates(
        self,
        memory: PublicGameMemory | Mapping[int, int],
        *,
        max_templates: int = 4,
        cumulative_weight: float = 0.95,
        min_weight: float = 0.01,
    ) -> tuple[tuple[DeckTemplate, float], ...]:
        """Return a renormalized plausible set for information-set search.

        Sparse evidence deliberately leaves several templates alive. The caller
        must aggregate a single root decision across these worlds rather than
        choosing a template-specific action (strategy fusion).
        """

        if max_templates <= 0:
            raise ValueError("max_templates must be positive")
        if not 0.0 < cumulative_weight <= 1.0:
            raise ValueError("cumulative_weight must be in (0, 1]")
        if not 0.0 <= min_weight <= 1.0:
            raise ValueError("min_weight must be in [0, 1]")

        ranked = [row for row in self.rank(memory) if row.compatible]
        if not ranked:
            return ()
        by_name = {template.name: template for template in self.templates}
        selected: list[tuple[DeckTemplate, float]] = []
        cumulative = 0.0
        for row in ranked:
            if selected and row.normalized_weight < min_weight:
                continue
            selected.append((by_name[row.name], row.normalized_weight))
            cumulative += row.normalized_weight
            if len(selected) >= max_templates or cumulative >= cumulative_weight:
                break

        total = sum(weight for _, weight in selected)
        if total <= 0.0:
            # This can only happen when every compatible row has zero support;
            # rank() normally assigns a uniform prior, but stay defensive.
            uniform = 1.0 / len(selected)
            return tuple((template, uniform) for template, _ in selected)
        return tuple((template, weight / total) for template, weight in selected)

    def qualified_template(
        self,
        memory: PublicGameMemory | Mapping[int, int],
        *,
        min_distinct_observed: int = 2,
        min_signature_hits: int = 1,
        min_weight: float = 0.70,
        min_margin: float = 0.25,
    ) -> DeckTemplate | None:
        ranked = self.rank(memory)
        compatible = [row for row in ranked if row.compatible]
        if not compatible:
            return None
        best = compatible[0]
        second_weight = compatible[1].normalized_weight if len(compatible) > 1 else 0.0
        if best.distinct_observed < min_distinct_observed:
            return None
        if best.signature_hits < min_signature_hits:
            return None
        if best.normalized_weight < min_weight:
            return None
        if best.normalized_weight - second_weight < min_margin:
            return None
        return next(template for template in self.templates if template.name == best.name)
