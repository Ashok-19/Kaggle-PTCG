from __future__ import annotations

import struct
import subprocess
import tempfile
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

_MAGIC = b"GCRULE01"
_HEADER = struct.Struct("<8s12I")


@dataclass(frozen=True)
class RuleTableBlob:
    cards: bytes
    skills: bytes
    attacks: bytes
    effects: bytes
    triggers: bytes
    substring_masks: bytes
    card_count: int
    skill_count: int
    attack_count: int
    effect_count: int
    trigger_count: int
    substring_mask_count: int
    substring_mask_words: int
    card_stride: int
    skill_stride: int
    attack_stride: int
    effect_stride: int
    trigger_stride: int

    @property
    def total_bytes(self) -> int:
        return sum(
            len(part)
            for part in (
                self.cards,
                self.skills,
                self.attacks,
                self.effects,
                self.triggers,
                self.substring_masks,
            )
        )


@lru_cache(maxsize=4)
def extract_rule_tables(official_dir: Path, repo_root: Path) -> RuleTableBlob:
    official_dir = official_dir.resolve()
    repo_root = repo_root.resolve()
    source = repo_root / "scripts/gpu_cabt_rule_extract.cpp"
    with tempfile.TemporaryDirectory(prefix="gpu-cabt-rules-") as tmp:
        exe = Path(tmp) / "extract"
        subprocess.run(
            [
                "g++",
                "-std=c++23",
                "-O2",
                "-I",
                str(official_dir),
                str(source),
                "-o",
                str(exe),
            ],
            check=True,
        )
        raw = subprocess.check_output([str(exe)])
    if len(raw) < _HEADER.size:
        raise RuntimeError("rule extractor returned a truncated header")
    unpacked = _HEADER.unpack_from(raw)
    if unpacked[0] != _MAGIC:
        raise RuntimeError(f"unexpected rule extractor magic {unpacked[0]!r}")
    (
        card_count,
        skill_count,
        attack_count,
        effect_count,
        trigger_count,
        substring_mask_count,
        substring_mask_words,
        card_stride,
        skill_stride,
        attack_stride,
        effect_stride,
        trigger_stride,
    ) = unpacked[1:]
    cursor = _HEADER.size

    def take(count: int, stride: int) -> bytes:
        nonlocal cursor
        size = count * stride
        result = raw[cursor : cursor + size]
        if len(result) != size:
            raise RuntimeError("rule extractor returned truncated table data")
        cursor += size
        return result

    cards = take(card_count, card_stride)
    skills = take(skill_count, skill_stride)
    attacks = take(attack_count, attack_stride)
    effects = take(effect_count, effect_stride)
    triggers = take(trigger_count, trigger_stride)
    substring_masks = take(substring_mask_count, substring_mask_words * 4)
    if cursor != len(raw):
        raise RuntimeError(f"rule extractor has {len(raw) - cursor} trailing bytes")
    return RuleTableBlob(
        cards=cards,
        skills=skills,
        attacks=attacks,
        effects=effects,
        triggers=triggers,
        substring_masks=substring_masks,
        card_count=card_count,
        skill_count=skill_count,
        attack_count=attack_count,
        effect_count=effect_count,
        trigger_count=trigger_count,
        substring_mask_count=substring_mask_count,
        substring_mask_words=substring_mask_words,
        card_stride=card_stride,
        skill_stride=skill_stride,
        attack_stride=attack_stride,
        effect_stride=effect_stride,
        trigger_stride=trigger_stride,
    )

# Native enum values are loaded separately by the CUDA source builder.
