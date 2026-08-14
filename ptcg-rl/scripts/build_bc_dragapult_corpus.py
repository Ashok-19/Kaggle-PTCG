from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ptcg_rl.bc.dragapult_corpus import (  # noqa: E402
    CURRENT_REPLAY_MODULE_VERSION,
    DOMINANT_DRAGAPULT_DECK_SHA256,
    DragapultCorpusPolicy,
    EliteTeacher,
    choose_dragapult_winner_teacher,
    quality_tier,
)
from ptcg_rl.bc.source import (  # noqa: E402
    BCSourceError,
    ReplayArchiveEntry,
    ReplayEpisodeRecord,
    ReplayQualityRecord,
    archive_inventory,
    load_archive_manifest,
    replay_record_from_bytes,
    scan_replay_prefix,
    sha256_file,
)

PREFIX_BYTES = 65_536


def canonical_sha256(value: Any) -> str:
    raw = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def locate_archive(root: Path, day: str) -> Path:
    candidates = sorted((root / day / "archive").glob("*.zip"))
    if len(candidates) != 1:
        raise BCSourceError(
            f"expected exactly one downloaded archive for {day}, found {len(candidates)}"
        )
    return candidates[0]


def load_elite_teachers(path: Path | None) -> tuple[dict[str, EliteTeacher], dict[str, Any] | None]:
    if path is None:
        return {}, None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise BCSourceError(f"cannot read elite-teacher snapshot: {error}") from error
    teams = payload.get("teams") if isinstance(payload, Mapping) else None
    if not isinstance(teams, list):
        raise BCSourceError("elite-teacher snapshot has no teams list")
    result: dict[str, EliteTeacher] = {}
    for position, row in enumerate(teams):
        if not isinstance(row, Mapping):
            raise BCSourceError(f"elite-teacher row {position} is not an object")
        try:
            rank = int(row["rank"])
            name = str(row["team_name"])
            score = float(row["score"])
        except (KeyError, TypeError, ValueError) as error:
            raise BCSourceError(f"elite-teacher row {position} is malformed") from error
        if rank <= 0 or not name or score <= 0 or name in result:
            raise BCSourceError(f"elite-teacher row {position} violates identity contract")
        result[name] = EliteTeacher(team_name=name, rank=rank, score=score)
    if not result:
        raise BCSourceError("elite-teacher snapshot is empty")
    return result, dict(payload)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a large high-quality exact-deck Dragapult BC replay corpus"
    )
    parser.add_argument("--archive-root", type=Path, required=True)
    parser.add_argument("--days", nargs="+", required=True)
    parser.add_argument(
        "--target-deck-sha256",
        default=DOMINANT_DRAGAPULT_DECK_SHA256,
    )
    parser.add_argument("--module-version", default=CURRENT_REPLAY_MODULE_VERSION)
    parser.add_argument("--base-min-score", type=float, default=1090.0)
    parser.add_argument("--elite-rescue-min-score", type=float, default=1090.0)
    parser.add_argument("--elite-teachers", type=Path)
    parser.add_argument("--split-seed", type=int, default=20260815)
    parser.add_argument("--minimum-selected", type=int, default=500)
    parser.add_argument("--minimum-active-requests", type=int, default=30_000)
    parser.add_argument("--record-id", default="bc-dragapult-hq-v1")
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if len(args.days) != len(set(args.days)):
        raise BCSourceError("days contain duplicates")
    if args.minimum_selected <= 0 or args.minimum_active_requests <= 0:
        raise BCSourceError("minimum corpus size requirements must be positive")
    policy = DragapultCorpusPolicy(
        target_deck_sha256=args.target_deck_sha256,
        module_version=args.module_version,
        base_min_score=args.base_min_score,
        elite_rescue_min_score=args.elite_rescue_min_score,
    )
    elite_teachers, elite_snapshot = load_elite_teachers(args.elite_teachers)

    archives: dict[str, Path] = {}
    inventories: dict[str, dict[int, ReplayArchiveEntry]] = {}
    candidate_specs: list[
        tuple[str, ReplayArchiveEntry, ReplayQualityRecord, int, str]
    ] = []
    source_reports: list[dict[str, Any]] = []
    discovery_rejections: Counter[str] = Counter()
    seen_episode_ids: set[int] = set()

    discovery_floor = min(policy.base_min_score, policy.elite_rescue_min_score)
    for day in args.days:
        archive_path = locate_archive(args.archive_root, day)
        archives[day] = archive_path
        entries = archive_inventory(archive_path)
        quality = load_archive_manifest(archive_path)
        quality_by_id = {item.episode_id: item for item in quality}
        if {item.episode_id for item in entries} != set(quality_by_id):
            raise BCSourceError(f"archive/manifest episode sets differ for {day}")
        for entry in entries:
            if quality_by_id[entry.episode_id].size_bytes != entry.bytes:
                raise BCSourceError(
                    f"manifest replay byte count differs for {day}/{entry.episode_id}"
                )
            if entry.episode_id in seen_episode_ids:
                raise BCSourceError(f"duplicate episode ID across days: {entry.episode_id}")
            seen_episode_ids.add(entry.episode_id)
        inventories[day] = {item.episode_id: item for item in entries}

        scanned = 0
        target_deck_seen = 0
        selected = 0
        score_floor_selected = 0
        rescue_selected = 0
        module_counts: Counter[str] = Counter()
        with zipfile.ZipFile(archive_path) as archive:
            for entry in entries:
                score = quality_by_id[entry.episode_id]
                if score.min_score < discovery_floor:
                    continue
                scanned += 1
                try:
                    with archive.open(entry.name, "r") as source:
                        prefix = source.read(PREFIX_BYTES)
                    discovered = scan_replay_prefix(prefix)
                except BCSourceError as error:
                    discovery_rejections[str(error).split(":")[0]] += 1
                    continue
                module_counts[discovered.module_version] += 1
                winner = discovered.winner_player_index
                if winner in (0, 1) and discovered.deck_sha256[winner] == policy.target_deck_sha256:
                    target_deck_seen += 1
                choice = choose_dragapult_winner_teacher(
                    discovered,
                    score,
                    policy=policy,
                    elite_teachers=elite_teachers,
                )
                if choice is None:
                    continue
                teacher_player_index, admission_reason = choice
                candidate_specs.append(
                    (day, entry, score, teacher_player_index, admission_reason)
                )
                selected += 1
                score_floor_selected += int(admission_reason == "score_floor")
                rescue_selected += int(admission_reason == "live_top20_rescue")
        source_reports.append(
            {
                "date": day,
                "dataset_slug": f"kaggle/pokemon-tcg-ai-battle-episodes-{day}",
                "archive_sha256": sha256_file(archive_path),
                "archive_compressed_bytes": archive_path.stat().st_size,
                "episodes": len(entries),
                "uncompressed_replay_bytes": sum(item.bytes for item in entries),
                "prefix_scanned": scanned,
                "module_counts_at_discovery_floor": dict(sorted(module_counts.items())),
                "target_deck_winner_seen_at_discovery_floor": target_deck_seen,
                "selected_before_full_parse": selected,
                "selected_score_floor": score_floor_selected,
                "selected_top20_rescue": rescue_selected,
            }
        )

    if len(candidate_specs) < args.minimum_selected:
        raise BCSourceError(
            f"Dragapult discovery selected {len(candidate_specs)} trajectories; "
            f"minimum is {args.minimum_selected}"
        )

    full_parse_rejections: Counter[str] = Counter()
    retained: list[tuple[ReplayQualityRecord, ReplayEpisodeRecord, str]] = []
    specs_by_day: dict[
        str, list[tuple[ReplayArchiveEntry, ReplayQualityRecord, int, str]]
    ] = {day: [] for day in args.days}
    for day, entry, quality, teacher, reason in candidate_specs:
        specs_by_day[day].append((entry, quality, teacher, reason))

    for day in args.days:
        with zipfile.ZipFile(archives[day]) as archive:
            for entry, quality, teacher, admission_reason in sorted(
                specs_by_day[day], key=lambda item: item[0].episode_id
            ):
                raw = archive.read(entry.name)
                try:
                    record = replay_record_from_bytes(
                        raw,
                        expected_episode_id=entry.episode_id,
                        date=day,
                        relative_path=entry.name,
                        split_seed=args.split_seed,
                        teacher_player_index=teacher,
                    )
                except BCSourceError as error:
                    full_parse_rejections[str(error).split(":")[0]] += 1
                    continue
                if record.module_version != policy.module_version:
                    full_parse_rejections[f"module:{record.module_version}"] += 1
                    continue
                if record.teacher_deck_sha256 != policy.target_deck_sha256:
                    raise BCSourceError(
                        f"full parser target deck differs for episode {entry.episode_id}"
                    )
                if record.teacher_result != "win":
                    raise BCSourceError(
                        f"non-winning teacher reached retained corpus: {entry.episode_id}"
                    )
                retained.append((quality, record, admission_reason))

    active_requests = sum(record.teacher_active_requests for _, record, _ in retained)
    if len(retained) < args.minimum_selected:
        raise BCSourceError(
            f"Dragapult full parse retained {len(retained)} trajectories; "
            f"minimum is {args.minimum_selected}"
        )
    if active_requests < args.minimum_active_requests:
        raise BCSourceError(
            f"Dragapult full parse retained {active_requests} teacher requests; "
            f"minimum is {args.minimum_active_requests}"
        )

    records: list[dict[str, Any]] = []
    team_counts: Counter[str] = Counter()
    tier_counts: Counter[str] = Counter()
    opponent_decks: Counter[str] = Counter()
    admission_counts: Counter[str] = Counter()
    per_day: Counter[str] = Counter()
    for quality, record, admission_reason in sorted(
        retained, key=lambda item: (item[1].date, item[1].episode_id)
    ):
        tier, sample_weight = quality_tier(quality.min_score)
        elite = elite_teachers.get(record.teacher_team_name)
        row = asdict(record)
        row.update(
            {
                "source_avg_score": quality.avg_score,
                "source_min_score": quality.min_score,
                "source_sum_score": quality.sum_score,
                "teacher_sample_weight": sample_weight,
                "teacher_quality_tier": tier,
                "teacher_policy_source": "exact_dragapult_winning_player",
                "admission_reason": admission_reason,
                "live_leaderboard_rank": None if elite is None else elite.rank,
                "live_leaderboard_score": None if elite is None else elite.score,
            }
        )
        records.append(row)
        team_counts[record.teacher_team_name] += 1
        tier_counts[tier] += 1
        opponent_decks[record.opponent_deck_sha256] += 1
        admission_counts[admission_reason] += 1
        per_day[record.date] += 1

    split_counts = Counter(row["split"] for row in records)
    largest_teacher_count = max(team_counts.values())
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "record_id": args.record_id,
        "status": "PASS_DRAGAPULT_HIGH_QUALITY_CORPUS_READY",
        "selection": {
            "days": args.days,
            "target_deck_sha256": policy.target_deck_sha256,
            "required_module_version": policy.module_version,
            "winner_only_labels": True,
            "base_min_score": policy.base_min_score,
            "elite_rescue_min_score": policy.elite_rescue_min_score,
            "elite_teacher_snapshot": elite_snapshot,
            "split_seed": args.split_seed,
            "minimum_selected": args.minimum_selected,
            "minimum_active_requests": args.minimum_active_requests,
            "prefix_bytes": PREFIX_BYTES,
            "quality_weights_retained_for_future_curriculum": True,
            "current_materialized_trainer_consumes_quality_weights": False,
        },
        "summary": {
            "episodes": len(records),
            "teacher_active_requests": active_requests,
            "selected_raw_bytes": sum(int(row["bytes"]) for row in records),
            "split_counts": dict(sorted(split_counts.items())),
            "teacher_teams": len(team_counts),
            "opponent_decks": len(opponent_decks),
            "quality_tiers": dict(sorted(tier_counts.items())),
            "admission_counts": dict(sorted(admission_counts.items())),
            "per_day": dict(sorted(per_day.items())),
            "minimum_selected_min_score": min(float(row["source_min_score"]) for row in records),
            "mean_selected_min_score": sum(float(row["source_min_score"]) for row in records)
            / len(records),
            "largest_teacher_share": largest_teacher_count / len(records),
            "discovery_rejections": sum(discovery_rejections.values()),
            "full_parse_rejections": sum(full_parse_rejections.values()),
        },
        "source_archives": source_reports,
        "discovery_rejection_counts": dict(sorted(discovery_rejections.items())),
        "full_parse_rejection_counts": dict(sorted(full_parse_rejections.items())),
        "records": records,
    }
    manifest["manifest_sha256"] = canonical_sha256(manifest)
    manifest_raw = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")

    if args.bundle.exists() and not args.force:
        raise BCSourceError(f"bundle already exists: {args.bundle}")
    args.bundle.parent.mkdir(parents=True, exist_ok=True)
    partial = args.bundle.with_suffix(args.bundle.suffix + ".partial")
    partial.unlink(missing_ok=True)
    record_by_id = {int(row["episode_id"]): row for row in records}
    if len(record_by_id) != len(records):
        raise BCSourceError("Dragapult corpus contains duplicate episode IDs")
    with zipfile.ZipFile(
        partial, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6
    ) as output:
        output.writestr("manifest.json", manifest_raw)
        for day in args.days:
            episode_ids = sorted(
                int(row["episode_id"])
                for row in records
                if row["date"] == day
            )
            with zipfile.ZipFile(archives[day]) as source:
                for episode_id in episode_ids:
                    entry = inventories[day][episode_id]
                    raw = source.read(entry.name)
                    record = record_by_id[episode_id]
                    if (
                        len(raw) != int(record["bytes"])
                        or hashlib.sha256(raw).hexdigest() != record["sha256"]
                    ):
                        raise BCSourceError(
                            f"selected replay changed while bundling: {episode_id}"
                        )
                    output.writestr(f"episodes/{episode_id}.json", raw)
    partial.replace(args.bundle)

    report = {
        "schema_version": 1,
        "record_id": args.record_id + "-build-report",
        "status": "PASS",
        "manifest_sha256": manifest["manifest_sha256"],
        "bundle_path": args.bundle.as_posix(),
        "bundle_sha256": sha256_file(args.bundle),
        "bundle_bytes": args.bundle.stat().st_size,
        "summary": manifest["summary"],
        "top_teacher_teams": team_counts.most_common(24),
        "top_opponent_decks": opponent_decks.most_common(24),
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    report_partial = args.report.with_suffix(args.report.suffix + ".partial")
    report_partial.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    report_partial.replace(args.report)
    print(json.dumps(report, indent=2, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
