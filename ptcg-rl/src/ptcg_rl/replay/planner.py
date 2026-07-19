from __future__ import annotations

import csv
import hashlib
import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

INDEX_COLUMNS = (
    "date",
    "daily_dataset_slug",
    "daily_dataset_url",
    "episode_count",
    "total_bytes",
    "top_avg_score",
    "median_avg_score",
)
DAILY_COLUMNS = (
    "episode_id",
    "create_time",
    "avg_score",
    "min_score",
    "sum_score",
    "agent_count",
    "size_bytes",
)
STRATUM_ORDER = ("elite_dual", "elite_avg", "broad_time")


class ReplayPlanError(ValueError):
    pass


@dataclass(frozen=True)
class DatasetRef:
    owner: str
    slug: str
    version: int


@dataclass(frozen=True)
class PlanCaps:
    max_files: int
    max_total_bytes: int
    max_file_bytes: int


@dataclass(frozen=True)
class PlannerConfig:
    schema_version: int
    planner_version: str
    seed: int
    source_date: str
    index_dataset: DatasetRef
    daily_dataset: DatasetRef
    caps: PlanCaps
    quotas: Mapping[str, int]
    time_blocks: int
    avg_score_quantile: float
    min_score_quantile: float

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> PlannerConfig:
        _reject_unknown(
            value,
            {
                "schema_version",
                "planner_version",
                "seed",
                "source_date",
                "index_dataset",
                "daily_dataset",
                "caps",
                "quotas",
                "time_blocks",
                "quantiles",
            },
            "config",
        )
        _require(value, {"schema_version", "planner_version", "seed", "source_date"}, "config")
        index = _dataset_ref(value.get("index_dataset"), "index_dataset")
        daily = _dataset_ref(value.get("daily_dataset"), "daily_dataset")
        caps_value = _mapping(value.get("caps"), "caps")
        _reject_unknown(caps_value, {"max_files", "max_total_bytes", "max_file_bytes"}, "caps")
        _require(caps_value, {"max_files", "max_total_bytes", "max_file_bytes"}, "caps")
        caps = PlanCaps(
            max_files=_positive_int(caps_value["max_files"], "caps.max_files"),
            max_total_bytes=_positive_int(
                caps_value["max_total_bytes"], "caps.max_total_bytes"
            ),
            max_file_bytes=_positive_int(caps_value["max_file_bytes"], "caps.max_file_bytes"),
        )
        quotas_value = _mapping(value.get("quotas"), "quotas")
        _reject_unknown(quotas_value, set(STRATUM_ORDER), "quotas")
        _require(quotas_value, set(STRATUM_ORDER), "quotas")
        quotas = {name: _nonnegative_int(quotas_value[name], f"quotas.{name}") for name in STRATUM_ORDER}
        if sum(quotas.values()) != caps.max_files:
            raise ReplayPlanError("sum(quotas) must equal caps.max_files")
        quantiles = _mapping(value.get("quantiles"), "quantiles")
        _reject_unknown(quantiles, {"avg_score", "min_score"}, "quantiles")
        _require(quantiles, {"avg_score", "min_score"}, "quantiles")
        avg_quantile = _quantile_value(quantiles["avg_score"], "quantiles.avg_score")
        min_quantile = _quantile_value(quantiles["min_score"], "quantiles.min_score")
        config = cls(
            schema_version=_positive_int(value["schema_version"], "schema_version"),
            planner_version=_nonempty(value["planner_version"], "planner_version"),
            seed=_nonnegative_int(value["seed"], "seed"),
            source_date=_nonempty(value["source_date"], "source_date"),
            index_dataset=index,
            daily_dataset=daily,
            caps=caps,
            quotas=quotas,
            time_blocks=_positive_int(value.get("time_blocks"), "time_blocks"),
            avg_score_quantile=avg_quantile,
            min_score_quantile=min_quantile,
        )
        if config.daily_dataset.slug != f"pokemon-tcg-ai-battle-episodes-{config.source_date}":
            raise ReplayPlanError("daily dataset slug does not match source_date")
        return config


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ReplayPlanError(f"{name} must be an object")
    return value


def _reject_unknown(value: Mapping[str, Any], allowed: set[str], name: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ReplayPlanError(f"{name} contains unknown keys: {', '.join(unknown)}")


def _require(value: Mapping[str, Any], required: set[str], name: str) -> None:
    missing = sorted(required - set(value))
    if missing:
        raise ReplayPlanError(f"{name} is missing keys: {', '.join(missing)}")


def _dataset_ref(value: Any, name: str) -> DatasetRef:
    item = _mapping(value, name)
    _reject_unknown(item, {"owner", "slug", "version"}, name)
    _require(item, {"owner", "slug", "version"}, name)
    return DatasetRef(
        owner=_nonempty(item["owner"], f"{name}.owner"),
        slug=_nonempty(item["slug"], f"{name}.slug"),
        version=_positive_int(item["version"], f"{name}.version"),
    )


def _nonempty(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReplayPlanError(f"{name} must be a nonempty string")
    return value.strip()


def _positive_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ReplayPlanError(f"{name} must be a positive integer")
    return value


def _nonnegative_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ReplayPlanError(f"{name} must be a nonnegative integer")
    return value


def _quantile_value(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ReplayPlanError(f"{name} must be numeric")
    result = float(value)
    if not 0 < result < 1:
        raise ReplayPlanError(f"{name} must be between zero and one")
    return result


def load_config(path: Path) -> PlannerConfig:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ReplayPlanError(f"cannot load config {path}: {error}") from error
    return PlannerConfig.from_mapping(_mapping(value, "config"))


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
        "utf-8"
    )


def _read_csv(path: Path, expected_columns: tuple[str, ...]) -> tuple[bytes, list[dict[str, str]]]:
    try:
        raw = path.read_bytes()
        text = raw.decode("utf-8")
    except (OSError, UnicodeError) as error:
        raise ReplayPlanError(f"cannot read manifest {path}: {error}") from error
    reader = csv.DictReader(text.splitlines())
    if tuple(reader.fieldnames or ()) != expected_columns:
        raise ReplayPlanError(
            f"manifest {path} columns differ: {tuple(reader.fieldnames or ())}"
        )
    rows = list(reader)
    if not rows:
        raise ReplayPlanError(f"manifest {path} is empty")
    return raw, rows


def _load_receipt(path: Path) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ReplayPlanError(f"cannot load receipt {path}: {error}") from error
    return _mapping(value, "receipt")


def _verify_receipt(
    path: Path,
    receipt_path: Path,
    dataset: DatasetRef,
    filename: str,
) -> dict[str, Any]:
    raw = path.read_bytes()
    receipt = _load_receipt(receipt_path)
    expected = {
        "dataset_owner": dataset.owner,
        "dataset_slug": dataset.slug,
        "dataset_version": dataset.version,
        "requested_filename": filename,
        "actual_bytes": len(raw),
        "sha256": _sha256(raw),
    }
    mismatches = [
        key for key, expected_value in expected.items() if receipt.get(key) != expected_value
    ]
    if mismatches:
        raise ReplayPlanError(f"receipt mismatch for {path}: {', '.join(mismatches)}")
    provider = receipt.get("provider")
    retrieved = receipt.get("retrieved_at_utc")
    if not isinstance(provider, str) or not provider:
        raise ReplayPlanError("receipt provider is missing")
    if not isinstance(retrieved, str) or not retrieved:
        raise ReplayPlanError("receipt retrieval timestamp is missing")
    return {
        "dataset_owner": dataset.owner,
        "dataset_slug": dataset.slug,
        "dataset_version": dataset.version,
        "manifest_filename": filename,
        "manifest_bytes": len(raw),
        "manifest_sha256": _sha256(raw),
        "retrieved_at_utc": retrieved,
        "provider": provider,
    }


def _int(text: str, name: str) -> int:
    try:
        value = int(text)
    except ValueError as error:
        raise ReplayPlanError(f"{name} is not an integer: {text!r}") from error
    return value


def _float(text: str, name: str) -> float:
    try:
        value = float(text)
    except ValueError as error:
        raise ReplayPlanError(f"{name} is not numeric: {text!r}") from error
    if not math.isfinite(value):
        raise ReplayPlanError(f"{name} is not finite")
    return value


def _nearest_rank(values: Iterable[float], quantile: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ReplayPlanError("cannot compute a quantile over an empty population")
    rank = max(1, math.ceil(quantile * len(ordered)))
    return ordered[rank - 1]


def _stable_rank(seed: int, stratum: str, block: int, episode_id: str) -> str:
    text = f"{seed}:{stratum}:{block}:{episode_id}"
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _rotated_blocks(seed: int, stratum: str, blocks: list[int]) -> list[int]:
    if not blocks:
        return []
    digest = hashlib.sha256(f"{seed}:{stratum}:block-order".encode("utf-8")).digest()
    offset = int.from_bytes(digest[:8], "big") % len(blocks)
    return blocks[offset:] + blocks[:offset]


def _balanced_select(
    rows: list[dict[str, Any]], quota: int, seed: int, stratum: str
) -> list[dict[str, Any]]:
    if quota <= 0 or not rows:
        return []
    cells: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        cells.setdefault(int(row["time_block"]), []).append(row)
    for block, items in cells.items():
        items.sort(key=lambda row: _stable_rank(seed, stratum, block, row["episode_id"]))
    block_order = _rotated_blocks(seed, stratum, sorted(cells))
    selected: list[dict[str, Any]] = []
    positions = {block: 0 for block in block_order}
    while len(selected) < min(quota, len(rows)):
        progressed = False
        for block in block_order:
            index = positions[block]
            if index < len(cells[block]):
                selected.append(cells[block][index])
                positions[block] += 1
                progressed = True
                if len(selected) == min(quota, len(rows)):
                    break
        if not progressed:
            break
    return selected


def _scaled_quotas(original: Mapping[str, int], target: int) -> dict[str, int]:
    total = sum(original.values())
    if target < 0 or target > total:
        raise ReplayPlanError("scaled quota target is outside the original quota range")
    if target == 0:
        return {name: 0 for name in STRATUM_ORDER}
    raw = {name: target * original[name] / total for name in STRATUM_ORDER}
    result = {name: math.floor(raw[name]) for name in STRATUM_ORDER}
    remainder = target - sum(result.values())
    order = sorted(
        STRATUM_ORDER,
        key=lambda name: (-(raw[name] - result[name]), STRATUM_ORDER.index(name)),
    )
    for name in order[:remainder]:
        result[name] += 1
    return result


def _prepare_daily_rows(
    rows: list[dict[str, str]], config: PlannerConfig
) -> tuple[list[dict[str, Any]], float, float]:
    parsed: list[dict[str, Any]] = []
    seen: set[str] = set()
    for position, row in enumerate(rows):
        episode_id = row["episode_id"].strip()
        if not episode_id.isdigit() or episode_id in seen:
            raise ReplayPlanError(f"invalid or duplicate episode_id at row {position + 2}")
        seen.add(episode_id)
        size = _int(row["size_bytes"], f"size_bytes[{episode_id}]")
        agent_count = _int(row["agent_count"], f"agent_count[{episode_id}]")
        if size <= 0 or agent_count <= 0:
            raise ReplayPlanError(f"nonpositive size or agent_count for episode {episode_id}")
        create_time = row["create_time"].strip()
        if not create_time.startswith(config.source_date + "T"):
            raise ReplayPlanError(f"create_time falls outside source date for {episode_id}")
        parsed.append(
            {
                "episode_id": episode_id,
                "remote_filename": f"{episode_id}.json",
                "create_time": create_time,
                "avg_score": _float(row["avg_score"], f"avg_score[{episode_id}]"),
                "min_score": _float(row["min_score"], f"min_score[{episode_id}]"),
                "sum_score": _float(row["sum_score"], f"sum_score[{episode_id}]"),
                "agent_count": agent_count,
                "declared_bytes": size,
            }
        )
    avg_threshold = _nearest_rank(
        (row["avg_score"] for row in parsed), config.avg_score_quantile
    )
    min_threshold = _nearest_rank(
        (row["min_score"] for row in parsed), config.min_score_quantile
    )
    chronological = sorted(parsed, key=lambda row: (row["create_time"], row["episode_id"]))
    total = len(chronological)
    for position, row in enumerate(chronological):
        row["time_block"] = min(config.time_blocks - 1, position * config.time_blocks // total)
        if row["avg_score"] >= avg_threshold and row["min_score"] >= min_threshold:
            row["stratum"] = "elite_dual"
        elif row["avg_score"] >= avg_threshold:
            row["stratum"] = "elite_avg"
        else:
            row["stratum"] = "broad_time"
        if row["agent_count"] != 2:
            row["eligibility_reason"] = "agent_count_not_two"
        elif row["declared_bytes"] > config.caps.max_file_bytes:
            row["eligibility_reason"] = "file_exceeds_max_file_bytes"
        else:
            row["eligibility_reason"] = None
    return chronological, avg_threshold, min_threshold


def build_plan(
    config: PlannerConfig,
    index_manifest: Path,
    index_receipt: Path,
    daily_manifest: Path,
    daily_receipt: Path,
) -> dict[str, Any]:
    index_raw, index_rows = _read_csv(index_manifest, INDEX_COLUMNS)
    daily_raw, daily_rows = _read_csv(daily_manifest, DAILY_COLUMNS)
    index_source = _verify_receipt(
        index_manifest, index_receipt, config.index_dataset, "manifest.csv"
    )
    daily_source = _verify_receipt(
        daily_manifest, daily_receipt, config.daily_dataset, "manifest.csv"
    )
    index_match = [
        row
        for row in index_rows
        if row["date"] == config.source_date
        and row["daily_dataset_slug"] == config.daily_dataset.slug
    ]
    if len(index_match) != 1:
        raise ReplayPlanError("index does not contain exactly one selected daily dataset row")
    index_row = index_match[0]
    declared_count = _int(index_row["episode_count"], "index.episode_count")
    declared_bytes = _int(index_row["total_bytes"], "index.total_bytes")
    if declared_count != len(daily_rows):
        raise ReplayPlanError("daily row count differs from the selected index row")
    if daily_source["manifest_bytes"] != len(daily_raw) or index_source["manifest_bytes"] != len(
        index_raw
    ):
        raise ReplayPlanError("manifest byte accounting changed after receipt verification")

    rows, avg_threshold, min_threshold = _prepare_daily_rows(daily_rows, config)
    if sum(row["declared_bytes"] for row in rows) != declared_bytes:
        raise ReplayPlanError("sum(size_bytes) differs from the selected index row")

    eligible = [row for row in rows if row["eligibility_reason"] is None]
    selected: list[dict[str, Any]] = []
    final_quotas = dict(config.quotas)
    for target in range(config.caps.max_files, -1, -1):
        quotas = _scaled_quotas(config.quotas, target)
        candidate_selection: list[dict[str, Any]] = []
        for stratum in STRATUM_ORDER:
            candidates = [row for row in eligible if row["stratum"] == stratum]
            candidate_selection.extend(
                _balanced_select(candidates, quotas[stratum], config.seed, stratum)
            )
        selected_ids_for_target = {row["episode_id"] for row in candidate_selection}
        remaining = [row for row in eligible if row["episode_id"] not in selected_ids_for_target]
        shortfall = target - len(candidate_selection)
        if shortfall > 0:
            candidate_selection.extend(
                _balanced_select(remaining, shortfall, config.seed, "spillover")
            )
        if sum(row["declared_bytes"] for row in candidate_selection) <= config.caps.max_total_bytes:
            selected = candidate_selection
            final_quotas = {
                stratum: sum(row["stratum"] == stratum for row in selected)
                for stratum in STRATUM_ORDER
            }
            break
    else:
        raise ReplayPlanError("no selection can satisfy the total-byte cap")

    selected_ids = {row["episode_id"] for row in selected}
    cell_population: dict[tuple[str, int], int] = {}
    cell_selected: dict[tuple[str, int], int] = {}
    for row in eligible:
        cell = (str(row["stratum"]), int(row["time_block"]))
        cell_population[cell] = cell_population.get(cell, 0) + 1
    for row in selected:
        cell = (str(row["stratum"]), int(row["time_block"]))
        cell_selected[cell] = cell_selected.get(cell, 0) + 1

    plan_rows: list[dict[str, Any]] = []
    for row in rows:
        cell = (str(row["stratum"]), int(row["time_block"]))
        selected_row = row["episode_id"] in selected_ids
        reason = row["eligibility_reason"]
        if reason is None and not selected_row:
            reason = "not_selected_by_deterministic_cell_quota"
        population = cell_population.get(cell, 0)
        selected_count = cell_selected.get(cell, 0)
        plan_rows.append(
            {
                **row,
                "selection_status": "SELECTED" if selected_row else "REJECTED",
                "rejection_reason": None if selected_row else reason,
                "cell_population": population,
                "cell_selected": selected_count,
                "inclusion_probability": selected_count / population if population else 0.0,
            }
        )

    selected_items = [
        {
            "dataset_owner": config.daily_dataset.owner,
            "dataset_slug": config.daily_dataset.slug,
            "dataset_version": config.daily_dataset.version,
            "episode_id": row["episode_id"],
            "remote_filename": row["remote_filename"],
            "declared_bytes": row["declared_bytes"],
            "create_time": row["create_time"],
            "avg_score": row["avg_score"],
            "min_score": row["min_score"],
            "stratum": row["stratum"],
            "time_block": row["time_block"],
        }
        for row in sorted(selected, key=lambda item: (item["stratum"], item["time_block"], item["episode_id"]))
    ]
    total_selected_bytes = sum(item["declared_bytes"] for item in selected_items)
    if len(selected_items) > config.caps.max_files:
        raise ReplayPlanError("selected file count exceeds cap")
    if total_selected_bytes > config.caps.max_total_bytes:
        raise ReplayPlanError("selected byte total exceeds cap")
    if any(item["declared_bytes"] > config.caps.max_file_bytes for item in selected_items):
        raise ReplayPlanError("selected file exceeds per-file cap")

    plan: dict[str, Any] = {
        "schema_version": 1,
        "planner_version": config.planner_version,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "source": {
            "index": index_source,
            "daily": daily_source,
            "source_date": config.source_date,
            "index_episode_count": declared_count,
            "index_episode_bytes": declared_bytes,
        },
        "selection_profile": {
            "seed": config.seed,
            "quantile_method": "nearest_rank_ceil",
            "avg_score_quantile": config.avg_score_quantile,
            "min_score_quantile": config.min_score_quantile,
            "avg_score_threshold": avg_threshold,
            "min_score_threshold": min_threshold,
            "time_blocks": config.time_blocks,
            "requested_quotas": dict(config.quotas),
            "final_quotas": final_quotas,
            "caps": {
                "max_files": config.caps.max_files,
                "max_total_bytes": config.caps.max_total_bytes,
                "max_file_bytes": config.caps.max_file_bytes,
            },
            "selection_algorithm": "stratum-by-source-day-time-block; deterministic hash rank; no size preference",
        },
        "summary": {
            "manifest_rows": len(rows),
            "eligible_rows": len(eligible),
            "oversize_rows": sum(
                row["eligibility_reason"] == "file_exceeds_max_file_bytes" for row in rows
            ),
            "selected_files": len(selected_items),
            "selected_bytes": total_selected_bytes,
            "max_selected_file_bytes": max(
                (item["declared_bytes"] for item in selected_items), default=0
            ),
            "episode_json_transferred": 0,
        },
        "selected_items": selected_items,
        "rows": plan_rows,
    }
    hash_payload = dict(plan)
    hash_payload.pop("created_at_utc")
    plan["plan_sha256"] = _sha256(_canonical(hash_payload))
    return plan


def write_plan(plan: Mapping[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def verify_plan(plan: Mapping[str, Any]) -> dict[str, Any]:
    value = dict(plan)
    claimed = value.pop("plan_sha256", None)
    value.pop("created_at_utc", None)
    actual = _sha256(_canonical(value))
    if claimed != actual:
        raise ReplayPlanError("plan SHA-256 does not match canonical contents")
    selected = plan.get("selected_items")
    profile = plan.get("selection_profile")
    if not isinstance(selected, list) or not isinstance(profile, Mapping):
        raise ReplayPlanError("plan selected_items or selection_profile is malformed")
    caps = _mapping(profile.get("caps"), "plan.selection_profile.caps")
    max_files = _positive_int(caps.get("max_files"), "plan.caps.max_files")
    max_total = _positive_int(caps.get("max_total_bytes"), "plan.caps.max_total_bytes")
    max_file = _positive_int(caps.get("max_file_bytes"), "plan.caps.max_file_bytes")
    sizes = [_positive_int(item.get("declared_bytes"), "selected.declared_bytes") for item in selected]
    if len(selected) > max_files or sum(sizes) > max_total or any(size > max_file for size in sizes):
        raise ReplayPlanError("plan violates its declared caps")
    return {
        "status": "pass",
        "plan_sha256": actual,
        "selected_files": len(selected),
        "selected_bytes": sum(sizes),
        "max_selected_file_bytes": max(sizes, default=0),
    }
