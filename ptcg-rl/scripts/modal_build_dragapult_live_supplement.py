from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
import sys
import zipfile
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping

import modal

if modal.is_local():
    ROOT = Path(__file__).resolve().parents[2]
else:
    ROOT = Path("/workspace")
PTCG_RL = ROOT / "ptcg-rl"
CONFIG_PATH = PTCG_RL / "configs/bc_dragapult_live_v6.json"
VOLUME_NAME = "kptcg-training"
SECRET_NAME = "kaggle" + "-credentials"
REMOTE_CORPUS_ROOT = Path("/data/corpora/bc-dragapult-live-v6")
RAW_ROOT = Path("/tmp/kptcg-live-v6-replays")
EXISTING_MANIFESTS = (
    Path("/data/materialized/bc-dragapult-archetype-v3-featurefix-v3/manifest.json"),
    Path("/data/materialized/bc-dragapult-hq-v2-featurefix-v3/manifest.json"),
)

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("kaggle==2.2.3")
    .add_local_dir(PTCG_RL / "src", remote_path="/workspace/ptcg-rl/src")
    .add_local_file(
        PTCG_RL / "scripts/build_bc_dragapult_corpus.py",
        remote_path="/workspace/ptcg-rl/scripts/build_bc_dragapult_corpus.py",
    )
    .add_local_file(
        CONFIG_PATH,
        remote_path="/workspace/ptcg-rl/configs/bc_dragapult_live_v6.json",
    )
)

app = modal.App("kptcg-bc-dragapult-live-v6", image=image)
training_volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)
client_auth = modal.Secret.from_name(SECRET_NAME)

sys.path.insert(0, str(PTCG_RL / "src"))
from ptcg_rl.bc.dragapult_corpus import (  # noqa: E402
    DRAGAPULT_EX_CARD_ID,
    DragapultCorpusPolicy,
    quality_tier,
)
from ptcg_rl.bc.source import (  # noqa: E402
    BCSourceError,
    replay_record_from_bytes,
    scan_replay_prefix,
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(16 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_config() -> dict[str, Any]:
    payload = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise RuntimeError("unsupported Dragapult corpus config")
    if payload.get("winner_only_labels") is not False:
        raise RuntimeError("production Dragapult live-v6 corpus must retain all qualified teacher outcomes")
    if payload.get("archetype_wide") is not True:
        raise RuntimeError("production Dragapult live-v6 corpus must be archetype-wide")
    if int(payload.get("required_archetype_card_id", -1)) != DRAGAPULT_EX_CARD_ID:
        raise RuntimeError("production Dragapult live-v6 archetype card contract differs")
    teams = payload.get("teams")
    if not isinstance(teams, list) or not teams:
        raise RuntimeError("Dragapult live-v6 config has no teacher teams")
    return payload


def _install_client_auth() -> None:
    if not os.environ.get("KAGGLE_USERNAME") or not os.environ.get("KAGGLE_KEY"):
        raise RuntimeError("Modal Kaggle credential secret is missing required environment fields")



def _canonical_sha256(value: Any) -> str:
    raw = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


class _RequestPacer:
    def __init__(self, interval_seconds: float = 2.05) -> None:
        self.interval_seconds = interval_seconds
        self.last_started = 0.0

    def wait(self) -> None:
        now = time.monotonic()
        delay = self.interval_seconds - (now - self.last_started)
        if delay > 0:
            time.sleep(delay)
        self.last_started = time.monotonic()


def _api_call(pacer: _RequestPacer, function: Any, *args: Any, **kwargs: Any) -> Any:
    retryable = {429, 500, 502, 503, 504}
    for attempt in range(4):
        pacer.wait()
        try:
            return function(*args, **kwargs)
        except Exception as error:
            status = getattr(getattr(error, "response", None), "status_code", None)
            if status not in retryable or attempt == 3:
                raise
            delay = 60.0 if status == 429 else 10.0 * (2**attempt)
            print(
                json.dumps(
                    {
                        "event": "kaggle_api_backoff",
                        "status": status,
                        "attempt": attempt + 1,
                        "sleep_seconds": delay,
                    },
                    sort_keys=True,
                ),
                flush=True,
            )
            time.sleep(delay)
    raise RuntimeError("unreachable API retry state")


def _episode_metadata(api: Any, config: Mapping[str, Any], pacer: _RequestPacer) -> tuple[list[dict[str, Any]], dict[int, list[dict[str, Any]]]]:
    submissions: list[dict[str, Any]] = []
    by_episode: dict[int, list[dict[str, Any]]] = {}
    floor = float(config["teacher_score_floor"])
    for team in config["teams"]:
        team_id = int(team["team_id"])
        team_name = str(team["team_name"])
        rows = _api_call(pacer, api.competition_team_submissions, team_id) or []
        for row in rows:
            payload = row.to_dict() if hasattr(row, "to_dict") else row
            try:
                submission_id = int(payload["id"])
                score = float(payload.get("publicScore"))
            except (KeyError, TypeError, ValueError):
                continue
            if score < floor:
                continue
            completed: list[int] = []
            for episode in _api_call(pacer, api.competition_list_episodes, submission_id) or []:
                item = episode.to_dict() if hasattr(episode, "to_dict") else episode
                if str(item.get("state")) != "COMPLETED" or str(item.get("type")) != "EPISODE_TYPE_PUBLIC":
                    continue
                episode_id = int(item["id"])
                completed.append(episode_id)
                by_episode.setdefault(episode_id, []).append(
                    {
                        "team_id": team_id,
                        "team_name": team_name,
                        "submission_id": submission_id,
                        "submission_score": score,
                    }
                )
            submissions.append(
                {
                    "team_id": team_id,
                    "team_name": team_name,
                    "submission_id": submission_id,
                    "submission_score": score,
                    "completed_public_episodes": len(completed),
                }
            )
    submissions.sort(key=lambda row: (-float(row["submission_score"]), int(row["submission_id"])))
    return submissions, by_episode


def _choose_source(prefix: Any, sources: list[dict[str, Any]], policy: DragapultCorpusPolicy) -> tuple[int, dict[str, Any]] | None:
    candidates: list[tuple[float, int, int, dict[str, Any]]] = []
    for source in sources:
        for seat in (0, 1):
            if prefix.team_names[seat] != source["team_name"]:
                continue
            if policy.archetype_wide:
                if DRAGAPULT_EX_CARD_ID not in prefix.deck_card_ids[seat]:
                    continue
            elif prefix.deck_sha256[seat] != policy.target_deck_sha256:
                continue
            is_winner = int(prefix.winner_player_index == seat)
            candidates.append((float(source["submission_score"]), is_winner, -int(source["submission_id"]), source | {"seat": seat}))
    if not candidates:
        return None
    candidates.sort(reverse=True, key=lambda item: (item[0], item[1], item[2]))
    selected = candidates[0][3]
    return int(selected["seat"]), selected


@app.function(
    cpu=4,
    memory=16384,
    timeout=6 * 60 * 60,
    secrets=[client_auth],
    volumes={"/data": training_volume},
)
def build(force: bool = False) -> dict[str, Any]:
    started = time.perf_counter()
    config = _load_config()
    policy = DragapultCorpusPolicy(
        target_deck_sha256=str(config["target_deck_sha256"]),
        module_version=str(config["required_module_version"]),
        teacher_score_floor=float(config["teacher_score_floor"]),
        archetype_wide=True,
    )
    bundle = REMOTE_CORPUS_ROOT / "bc-dragapult-live-v6.zip"
    report_path = REMOTE_CORPUS_ROOT / "build-report.json"
    if REMOTE_CORPUS_ROOT.exists():
        if not force:
            if bundle.is_file() and report_path.is_file():
                existing = json.loads(report_path.read_text(encoding="utf-8"))
                return {"status": "EXISTS", **existing.get("summary", {})}
            raise RuntimeError(f"partial live supplement exists at {REMOTE_CORPUS_ROOT}")
        shutil.rmtree(REMOTE_CORPUS_ROOT)
    REMOTE_CORPUS_ROOT.mkdir(parents=True, exist_ok=False)
    raw_root = Path("/tmp/kptcg-live-replays")
    selected_root = Path("/tmp/kptcg-live-selected")
    shutil.rmtree(raw_root, ignore_errors=True)
    shutil.rmtree(selected_root, ignore_errors=True)
    raw_root.mkdir(parents=True)
    selected_root.mkdir(parents=True)

    try:
        _install_client_auth()
        from kaggle.api.kaggle_api_extended import KaggleApi

        api = KaggleApi()
        api.authenticate()
        pacer = _RequestPacer()
        source_submissions, episode_sources = _episode_metadata(api, config, pacer)
        existing_episode_ids: set[int] = set()
        existing_sources: list[dict[str, Any]] = []
        for manifest_path in EXISTING_MANIFESTS:
            if not manifest_path.is_file():
                raise RuntimeError(f"required v5 materialized manifest is missing: {manifest_path}")
            materialized = json.loads(manifest_path.read_text(encoding="utf-8"))
            ids = {int(row["episode_id"]) for row in materialized["records"]}
            existing_episode_ids.update(ids)
            existing_sources.append({
                "path": str(manifest_path),
                "manifest_sha256": str(materialized["manifest_sha256"]),
                "episodes": len(ids),
            })
        records: list[dict[str, Any]] = []
        rejections: Counter[str] = Counter()
        teacher_counts: Counter[str] = Counter()
        outcome_counts: Counter[str] = Counter()
        teacher_decks: Counter[str] = Counter()
        opponent_decks: Counter[str] = Counter()
        active_requests = 0
        all_candidate_ids = set(episode_sources)
        unique_ids = sorted(all_candidate_ids - existing_episode_ids)
        for position, episode_id in enumerate(unique_ids, 1):
            target = raw_root / f"episode-{episode_id}-replay.json"
            try:
                _api_call(pacer, api.competition_episode_replay, episode_id, path=str(raw_root), quiet=True)
                raw = target.read_bytes()
                prefix_record = scan_replay_prefix(raw[:65536])
                if prefix_record.module_version != policy.module_version:
                    rejections[f"module:{prefix_record.module_version}"] += 1
                    continue
                chosen = _choose_source(prefix_record, episode_sources[episode_id], policy)
                if chosen is None:
                    rejections["not_exact_target_deck_for_qualified_submission"] += 1
                    continue
                teacher_seat, source = chosen
                record = replay_record_from_bytes(
                    raw,
                    expected_episode_id=episode_id,
                    date="live",
                    relative_path=f"{episode_id}.json",
                    split_seed=int(config["split_seed"]),
                    teacher_player_index=teacher_seat,
                )
                if record.module_version != policy.module_version or record.teacher_deck_sha256 != policy.target_deck_sha256:
                    raise RuntimeError(f"full replay contract drift for {episode_id}")
                tier, weight = quality_tier(float(source["submission_score"]))
                row = asdict(record)
                row.update(
                    {
                        "source_submission_id": int(source["submission_id"]),
                        "source_submission_score": float(source["submission_score"]),
                        "teacher_score_qualification_basis": "submission_public_score",
                        "teacher_score_qualification_value": float(source["submission_score"]),
                        "teacher_quality_tier": tier,
                        "teacher_sample_weight": weight,
                        "source_kind": "live_submission_episode_api",
                    }
                )
                records.append(row)
                (selected_root / f"{episode_id}.json").write_bytes(raw)
                active_requests += int(record.teacher_active_requests)
                teacher_counts[record.teacher_team_name] += 1
                teacher_decks[record.teacher_deck_sha256] += 1
                outcome_counts[record.teacher_result] += 1
                opponent_decks[record.opponent_deck_sha256] += 1
            except (OSError, ValueError, BCSourceError, RuntimeError) as error:
                rejections[type(error).__name__ + ":" + str(error).split(":")[0][:80]] += 1
            finally:
                target.unlink(missing_ok=True)
            if position % 100 == 0:
                print(json.dumps({"event":"live_scan_progress","processed":position,"total":len(unique_ids),"selected":len(records)},sort_keys=True),flush=True)

        if not records:
            raise RuntimeError("live Dragapult supplement selected zero trajectories")
        records.sort(key=lambda row: int(row["episode_id"]))
        split_counts = Counter(str(row["split"]) for row in records)
        manifest: dict[str, Any] = {
            "schema_version": 1,
            "record_id": str(config["record_id"]),
            "status": "PASS_DRAGAPULT_LIVE_V6_READY",
            "selection": {
                "target_deck_sha256_reference": policy.target_deck_sha256,
                "archetype_wide": True,
                "required_archetype_card_id": DRAGAPULT_EX_CARD_ID,
                "required_module_version": policy.module_version,
                "teacher_submission_score_floor": policy.teacher_score_floor,
                "opponent_score_used_for_admission": False,
                "teacher_outcome_used_for_admission": False,
                "split_seed": int(config["split_seed"]),
                "source_submissions": source_submissions,
                "excluded_existing_sources": existing_sources,
            },
            "summary": {
                "candidate_submission_count": len(source_submissions),
                "candidate_episode_references": sum(int(row["completed_public_episodes"]) for row in source_submissions),
                "unique_candidate_episodes_before_v5_dedup": len(all_candidate_ids),
                "excluded_existing_episode_ids": len(all_candidate_ids & existing_episode_ids),
                "unique_candidate_episodes": len(unique_ids),
                "episodes": len(records),
                "teacher_active_requests": active_requests,
                "teacher_teams": len(teacher_counts),
                "teacher_decks": len(teacher_decks),
                "opponent_decks": len(opponent_decks),
                "split_counts": dict(sorted(split_counts.items())),
                "teacher_outcomes": dict(sorted(outcome_counts.items())),
                "minimum_teacher_submission_score": min(float(row["source_submission_score"]) for row in records),
                "mean_teacher_submission_score": sum(float(row["source_submission_score"]) for row in records) / len(records),
                "top_teacher_teams": teacher_counts.most_common(24),
                "top_teacher_decks": teacher_decks.most_common(24),
                "top_opponent_decks": opponent_decks.most_common(48),
                "rejection_count": sum(rejections.values()),
            },
            "rejection_counts": dict(sorted(rejections.items())),
            "records": records,
        }
        unhashed = dict(manifest)
        manifest["manifest_sha256"] = _canonical_sha256(unhashed)
        manifest_raw = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
        partial = bundle.with_suffix(".zip.partial")
        partial.unlink(missing_ok=True)
        with zipfile.ZipFile(partial, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as output:
            output.writestr("manifest.json", manifest_raw)
            for row in records:
                episode_id = int(row["episode_id"])
                raw = (selected_root / f"{episode_id}.json").read_bytes()
                if hashlib.sha256(raw).hexdigest() != row["sha256"]:
                    raise RuntimeError(f"selected replay hash drift for {episode_id}")
                output.writestr(f"episodes/{episode_id}.json", raw)
        partial.replace(bundle)
        report = {
            "schema_version": 1,
            "record_id": "bc-dragapult-live-v6-build-report",
            "status": "PASS",
            "bundle_sha256": _sha256_file(bundle),
            "bundle_bytes": bundle.stat().st_size,
            "manifest_sha256": manifest["manifest_sha256"],
            "summary": manifest["summary"],
            "elapsed_seconds": time.perf_counter() - started,
        }
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        training_volume.commit()
        print(json.dumps(report, indent=2, sort_keys=True), flush=True)
        return report
    except Exception:
        shutil.rmtree(REMOTE_CORPUS_ROOT, ignore_errors=True)
        raise
    finally:
        shutil.rmtree(raw_root, ignore_errors=True)
        shutil.rmtree(selected_root, ignore_errors=True)
