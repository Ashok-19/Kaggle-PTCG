from __future__ import annotations

import copy
import csv
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
CREATED_AT = "2026-08-05T05:13:52Z"

SCRATCH = ROOT / "scratch/agents/chatgpt/e01-source-refresh-20260805"
MANIFEST_CSV = SCRATCH / "manifest.csv"
DATASET_FILES_CSV = SCRATCH / "dataset_files.csv"
EPISODE_METADATA = SCRATCH / "majkel_submission_55186239_episodes.json"
LIVE_SOURCE_IDENTITY = SCRATCH / "live_source_identity.json"
SELECTION_SCRATCH = SCRATCH / "supplement_selection_v1.json"
CORPUS_V2 = ROOT / "reports/artifacts/e01-approved-replay-corpus-manifest-v2.json"
SOURCE_WAIT_V2 = ROOT / "configs/e01_corpus_v2_target_shortfall_source_wait_v2.json"
RAW_REFRESH = ROOT / "reports/artifacts/raw/e01-corpus-v2-source-refresh-20260805-v1.json"
REQUEST = ROOT / "configs/e01_corpus_v2_target_shortfall_supplement_request_v1.json"
REVIEW = ROOT / "reports/artifacts/e01-corpus-v2-target-shortfall-supplement-contract-review-v1.json"
DECISION = ROOT / "docs/decisions/DEC-029_E01_CORPUS_TARGET_SUPPLEMENT_REQUEST.md"
DECISIONS = ROOT / "reports/decisions/current.json"
TASKS = ROOT / "reports/tasks/current.json"
GATE = ROOT / "reports/gates/g3b.json"
PROJECT = ROOT / "PROJECT_STATUS.md"
PROGRESS = ROOT / "PROGRESS_REPORT.md"

DATASET_REF = "kaggle/pokemon-tcg-ai-battle-episodes-2026-08-04"
DATASET_ID = 11_506_836
DATASET_VERSION = 1
DATASET_INFO_TOTAL_BYTES = 21_457_813_826
DATASET_SEARCH_CARD_DOWNLOAD_BYTES = 742_933_013
DATASET_LAST_UPDATED_UTC = "2026-08-05T00:11:02.203Z"
TEACHER_SUBMISSION_ID = 55_186_239
TEACHER_TEAM_ID = 16_374_395
TEACHER_TEAM = "Majkel1337"
TEACHER_DECK_SHA256 = "dc8571d0bc2e546a1f85b938696cfc40a1451c68a4ccc1f695e7c3e1c74f1278"
CORPUS_V2_SHA256 = "ccc247edbc4cac0aba11c6acb26fc5e2a8c75e0a4f005d1441ce6949c0c4997f"
STRATA = ("seat_0_loss", "seat_0_win", "seat_1_loss", "seat_1_win")


def canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def self_hash(value: Mapping[str, Any], field: str) -> str:
    payload = copy.deepcopy(dict(value))
    payload.pop(field, None)
    return hashlib.sha256(canonical(payload)).hexdigest()


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False).encode("utf-8") + b"\n")


def update_prefixed_line(text: str, prefix: str, replacement: str) -> str:
    lines = text.splitlines()
    found = False
    for index, line in enumerate(lines):
        if line.startswith(prefix):
            lines[index] = replacement
            found = True
            break
    if not found:
        raise ValueError(f"missing line prefix: {prefix}")
    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")


def select_records() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if sha(CORPUS_V2) != CORPUS_V2_SHA256:
        raise ValueError("corpus-v2 manifest hash changed")
    with MANIFEST_CSV.open(newline="", encoding="utf-8-sig") as handle:
        manifest = {int(row["episode_id"]): row for row in csv.DictReader(handle)}
    with DATASET_FILES_CSV.open(newline="", encoding="utf-8-sig") as handle:
        inventory = {row["name"]: row for row in csv.DictReader(handle)}
    public_episodes = load(EPISODE_METADATA)["episodes"]
    corpus = load(CORPUS_V2)
    existing = {int(row["episode_id"]) for row in corpus["qualified_training_corpus"]["episode_records"]}

    eligible: dict[str, list[dict[str, Any]]] = {key: [] for key in STRATA}
    counts = {
        "public_episode_records": len(public_episodes),
        "manifest_rows": len(manifest),
        "inventory_files": len(inventory),
        "inventory_json_files": sum(name.endswith(".json") for name in inventory),
        "manifest_rows_without_json_body": sum(
            f"{episode_id}.json" not in inventory for episode_id in manifest
        ),
        "inventory_json_without_manifest_row": sum(
            name.endswith(".json") and int(Path(name).stem) not in manifest
            for name in inventory
        ),
        "existing_corpus_ids": len(existing),
        "completed_manifest_intersection": 0,
        "already_in_corpus": 0,
        "ambiguous_teacher_agents": 0,
        "non_binary_reward": 0,
        "eligible_unique_teacher_agent": 0,
    }
    for episode in public_episodes:
        episode_id = int(episode["id"])
        if episode.get("state") != "completed" or episode_id not in manifest:
            continue
        file_name = f"{episode_id}.json"
        if file_name not in inventory:
            continue
        metadata = manifest[episode_id]
        if int(metadata["size_bytes"]) != int(inventory[file_name]["total_bytes"]):
            raise ValueError(f"dataset inventory byte mismatch for {file_name}")
        counts["completed_manifest_intersection"] += 1
        if episode_id in existing:
            counts["already_in_corpus"] += 1
            continue
        teacher_agents = [
            agent
            for agent in episode.get("agents", [])
            if int(agent.get("submissionId", 0)) == TEACHER_SUBMISSION_ID
            and int(agent.get("teamId", 0)) == TEACHER_TEAM_ID
        ]
        if len(teacher_agents) != 1:
            counts["ambiguous_teacher_agents"] += 1
            continue
        teacher = teacher_agents[0]
        seat = int(teacher["index"])
        reward = float(teacher["reward"])
        if seat not in (0, 1) or reward not in (-1.0, 1.0):
            counts["non_binary_reward"] += 1
            continue
        opponent_agents = [agent for agent in episode.get("agents", []) if int(agent.get("index", -1)) != seat]
        if len(opponent_agents) != 1:
            counts["ambiguous_teacher_agents"] += 1
            continue
        opponent = opponent_agents[0]
        stratum = f"seat_{seat}_{'win' if reward == 1.0 else 'loss'}"
        eligible[stratum].append(
            {
                "create_time": metadata["create_time"],
                "declared_bytes": int(metadata["size_bytes"]),
                "end_time": episode.get("endTime"),
                "episode_id": episode_id,
                "file_name": file_name,
                "opponent_player_index": int(opponent["index"]),
                "opponent_reward": float(opponent["reward"]),
                "opponent_submission_id": int(opponent["submissionId"]),
                "opponent_team_id": int(opponent["teamId"]),
                "opponent_team_name": opponent.get("teamName", ""),
                "public_create_time": episode["createTime"],
                "state": "COMPLETED",
                "stratum": stratum,
                "teacher_player_index": seat,
                "teacher_reward": reward,
                "teacher_submission_id": TEACHER_SUBMISSION_ID,
                "teacher_team_id": TEACHER_TEAM_ID,
                "teacher_team_name": TEACHER_TEAM,
                "type": str(episode.get("type", "public")).upper(),
            }
        )
        counts["eligible_unique_teacher_agent"] += 1

    for records in eligible.values():
        records.sort(key=lambda row: (row["create_time"], row["episode_id"]), reverse=True)
    selected_by_stratum = {key: eligible[key][:12] for key in STRATA}
    if any(len(selected_by_stratum[key]) != 12 for key in STRATA):
        raise ValueError("cannot construct exact 12-per-stratum selection")

    selected: list[dict[str, Any]] = []
    for index in range(12):
        for stratum in STRATA:
            record = copy.deepcopy(selected_by_stratum[stratum][index])
            record["review_order"] = len(selected) + 1
            selected.append(record)
    selected_ids = [row["episode_id"] for row in selected]
    if len(selected) != 48 or len(set(selected_ids)) != 48 or set(selected_ids) & existing:
        raise ValueError("selected file identity check failed")

    summary = {
        "counts": counts,
        "eligible_by_stratum": {key: len(eligible[key]) for key in STRATA},
        "selected_by_stratum": {key: len(selected_by_stratum[key]) for key in STRATA},
        "selected_files": len(selected),
        "selected_total_bytes": sum(row["declared_bytes"] for row in selected),
        "selected_episode_ids": selected_ids,
        "manifest_rows_total_declared_bytes": sum(int(row["size_bytes"]) for row in manifest.values()),
        "inventory_total_bytes": sum(int(row["total_bytes"]) for row in inventory.values()),
    }
    return summary, selected


def main() -> int:
    for path in (
        MANIFEST_CSV,
        DATASET_FILES_CSV,
        EPISODE_METADATA,
        LIVE_SOURCE_IDENTITY,
        CORPUS_V2,
        SOURCE_WAIT_V2,
    ):
        if not path.is_file():
            raise FileNotFoundError(path)

    live_source = load(LIVE_SOURCE_IDENTITY)
    if live_source["dataset"] != {
        "current_version_number": DATASET_VERSION,
        "dataset_id": DATASET_ID,
        "dataset_info_total_bytes": DATASET_INFO_TOTAL_BYTES,
        "dataset_reference": DATASET_REF,
        "last_updated_utc": DATASET_LAST_UPDATED_UTC,
        "search_card_download_bytes": DATASET_SEARCH_CARD_DOWNLOAD_BYTES,
        "version_status": "Ready",
    }:
        raise ValueError("live dataset identity snapshot changed")
    if live_source["teacher"]["active_submission_id"] != TEACHER_SUBMISSION_ID:
        raise ValueError("live teacher submission identity changed")
    if live_source["teacher"]["team_id"] != TEACHER_TEAM_ID:
        raise ValueError("live teacher team identity changed")

    summary, selected = select_records()
    manifest_sha = sha(MANIFEST_CSV)
    inventory_sha = sha(DATASET_FILES_CSV)
    public_metadata_sha = sha(EPISODE_METADATA)
    live_source_sha = sha(LIVE_SOURCE_IDENTITY)
    source_wait_sha = sha(SOURCE_WAIT_V2)

    raw = {
        "authorization": {
            "agent_logs": False,
            "external_compute": False,
            "git_commit": False,
            "git_push": False,
            "gpu": False,
            "label_materialization": False,
            "model_promotion": False,
            "optimizer_steps": False,
            "raw_exports": False,
            "replay_body_reads": False,
            "replay_transfer": False,
            "submission": False,
            "tpu": False,
            "training": False,
        },
        "created_at_utc": CREATED_AT,
        "dataset": {
            "dataset_id": DATASET_ID,
            "dataset_info_total_bytes": DATASET_INFO_TOTAL_BYTES,
            "inventory_files": summary["counts"]["inventory_files"],
            "inventory_json_files": summary["counts"]["inventory_json_files"],
            "inventory_path": "dataset_files.csv",
            "inventory_sha256": inventory_sha,
            "inventory_total_bytes": summary["inventory_total_bytes"],
            "last_updated_utc": DATASET_LAST_UPDATED_UTC,
            "manifest_path": "manifest.csv",
            "manifest_rows": summary["counts"]["manifest_rows"],
            "manifest_rows_without_json_body": summary["counts"]["manifest_rows_without_json_body"],
            "manifest_sha256": manifest_sha,
            "reference": DATASET_REF,
            "search_card_download_bytes": DATASET_SEARCH_CARD_DOWNLOAD_BYTES,
            "status": "READY",
            "version": DATASET_VERSION,
        },
        "decision_id": "DEC-029",
        "intersection": summary,
        "producer": "chatgpt-local-agent",
        "live_source_identity": {
            "path": str(LIVE_SOURCE_IDENTITY.relative_to(ROOT)),
            "sha256": live_source_sha,
        },
        "public_episode_metadata": {
            "records": summary["counts"]["public_episode_records"],
            "sha256": public_metadata_sha,
            "source": f"/api/v1/competitions/submissions/{TEACHER_SUBMISSION_ID}/episodes",
        },
        "record_id": "e01-corpus-v2-source-refresh-20260805-v1",
        "replay_bodies_read": 0,
        "schema_version": 1,
        "selected_records": selected,
        "source_path": str(RAW_REFRESH.relative_to(ROOT)),
        "source_wait_plan": str(SOURCE_WAIT_V2.relative_to(ROOT)),
        "source_wait_plan_sha256": source_wait_sha,
        "status": "PASS_SOURCE_READY_EXACT_REQUEST_PREPARED",
        "teacher": {
            "active_submission": True,
            "deck_multiset_sha256": TEACHER_DECK_SHA256,
            "observed_public_rank": live_source["teacher"]["leaderboard_rank"],
            "observed_public_score_dynamic": live_source["teacher"]["public_score_dynamic"],
            "score_is_authorization_basis": False,
            "submission_id": TEACHER_SUBMISSION_ID,
            "team_id": TEACHER_TEAM_ID,
            "team_name": TEACHER_TEAM,
        },
        "evidence_sha256": None,
    }
    raw["evidence_sha256"] = self_hash(raw, "evidence_sha256")
    write_json(RAW_REFRESH, raw)

    decision_text = f"""# DEC-029 - Freeze the exact corpus-target supplemental request\n\n- Status: accepted request preparation; execution unauthorized\n- Date: 2026-08-05\n\n## Decision\n\nAccept the version-pinned August 4 daily source as READY and freeze one exact balanced supplemental request for the remaining 1,540-policy-target corpus shortfall. The request names 48 Majkel replay files, exactly 12 per seat/result stratum, in deterministic newest-first round-robin review order. It may be executed only after separate exact approval.\n\n## Evidence\n\n- Source: `{DATASET_REF}/{DATASET_VERSION}`, dataset id `{DATASET_ID}`.\n- Dataset inventory: `{summary['counts']['inventory_files']}` files / `{summary['inventory_total_bytes']}` bytes, SHA-256 `{inventory_sha}`.\n- Manifest SHA-256: `{manifest_sha}`; `{summary['counts']['manifest_rows_without_json_body']}` manifest rows have no JSON body and none are selected.\n- Public episode metadata SHA-256: `{public_metadata_sha}`.\n- Eligible new completed Majkel episodes: `{summary['selected_files'] and summary['counts']['eligible_unique_teacher_agent']}`.\n- Eligible strata: `{json.dumps(summary['eligible_by_stratum'], sort_keys=True)}`.\n- Selected request: 48 files, `{summary['selected_total_bytes']}` exact declared bytes, 12 per stratum.\n- Corpus v2 remains 337 episodes and 23,460 targets; no corpus mutation occurred.\n\n## Boundaries\n\nNo replay body was read while preparing this request. Execution, qualified-only corpus-v3 finalization, replay-body reads, label materialization, optimizer steps, training, accelerators, model mutation or promotion, submission, Git commit and Git push remain unauthorized. A later exact approval must bind the request path and file SHA-256.\n"""
    DECISION.parent.mkdir(parents=True, exist_ok=True)
    DECISION.write_text(decision_text, encoding="utf-8")

    requested_authorization = {
        "agent_logs": False,
        "corpus_v3_qualified_only_finalization": True,
        "external_compute_private_kaggle_cpu": True,
        "git_commit": False,
        "git_push": False,
        "gpu": False,
        "label_materialization": False,
        "model_mutation": False,
        "model_promotion": False,
        "optimizer_steps": False,
        "raw_exports": False,
        "replay_body_exports": False,
        "replay_body_reads_exact_named_files": True,
        "submission": False,
        "tpu": False,
        "training": False,
    }
    authorization = {key: False for key in requested_authorization}
    request = {
        "authorization": authorization,
        "authorization_consumed": False,
        "authorization_scope": "UNAUTHORIZED_EXACT_MAX_48_FILE_PRIVATE_KAGGLE_CPU_BODY_REVIEW_AND_QUALIFIED_CORPUS_V3_FINALIZATION_ONLY",
        "authorized": False,
        "compute": {
            "cpu_threads_maximum": 4,
            "gpu": False,
            "internet": False,
            "notebook_slug": "kptcg-e01-corpus-target-supplement-v1",
            "platform": "private-kaggle-cpu",
            "tpu": False,
            "wall_seconds_maximum": 10800,
        },
        "corpus_policy": {
            "base_manifest": str(CORPUS_V2.relative_to(ROOT)),
            "base_manifest_sha256": sha(CORPUS_V2),
            "base_policy_loss_targets": 23460,
            "base_qualified_episodes": 337,
            "corpus_v3_final_only_after_body_review": True,
            "episode_level_split_only": True,
            "forced_calls": "advance recurrence but contribute zero policy loss",
            "minimum_policy_loss_targets": 25000,
            "remaining_target_shortfall": 1540,
            "split_algorithm": "SHA256(seed|module_version|stratum|episode_id), deterministic 80/10/10 within module-by-stratum groups",
            "split_seed": 20260804,
            "stop_review_when_cumulative_qualified_targets_reach_floor": True,
            "target_count_projection_is_guarantee": False,
        },
        "created_at_utc": CREATED_AT,
        "decision_id": "DEC-029",
        "decision_path": str(DECISION.relative_to(ROOT)),
        "decision_sha256": sha(DECISION),
        "fail_closed_if": [
            "teacher team or active submission identity changes",
            "dataset version or manifest hash changes",
            "any selected filename or declared byte count changes",
            "any selected episode is already present in corpus v2",
            "body-level deck, module, action, terminal or duplicate review fails",
            "the exact review order or cumulative target stop rule cannot be reproduced",
        ],
        "files": selected,
        "maximum_declared_bytes": summary["selected_total_bytes"],
        "maximum_files": 48,
        "output_contract": {
            "agent_log_outputs": 0,
            "metadata_files": [
                "e01-corpus-target-supplement-review-v1.json",
                "e01-approved-replay-corpus-manifest-v3.json",
                "e01-approved-replay-corpus-review-v3.json",
                "e01-corpus-target-supplement-output-manifest-v1.json",
            ],
            "raw_replay_body_outputs": 0,
            "training_label_outputs": 0,
        },
        "producer": "chatgpt-local-agent",
        "requested_authorization": requested_authorization,
        "review_contract": {
            "accepted_module_versions": ["1.32.2", "1.32.3"],
            "body_checks": [
                "schema and environment identity",
                "exact Mega Lucario deck multiset",
                "teacher player and terminal reward identity",
                "current-card construction compatibility",
                "lag-aligned full-compound action validity including STOP",
                "forced-singleton recurrence-only classification",
                "duplicate episode and split leakage exclusion",
            ],
            "review_order": "round-robin seat_0_loss, seat_0_win, seat_1_loss, seat_1_win; newest first within each stratum",
            "stop_after_target_floor": True,
        },
        "schema_version": 1,
        "selection": {
            "eligible_by_stratum": summary["eligible_by_stratum"],
            "excluded_corpus_v2_episode_ids": True,
            "selected_by_stratum": summary["selected_by_stratum"],
            "selection_algorithm": "newest completed eligible episodes within each stratum",
        },
        "source": {
            "dataset_id": DATASET_ID,
            "dataset_info_total_bytes": DATASET_INFO_TOTAL_BYTES,
            "dataset_inventory_files": summary["counts"]["inventory_files"],
            "dataset_inventory_json_files": summary["counts"]["inventory_json_files"],
            "dataset_inventory_sha256": inventory_sha,
            "dataset_inventory_total_bytes": summary["inventory_total_bytes"],
            "dataset_last_updated_utc": DATASET_LAST_UPDATED_UTC,
            "dataset_reference": DATASET_REF,
            "dataset_search_card_download_bytes": DATASET_SEARCH_CARD_DOWNLOAD_BYTES,
            "dataset_status": "READY",
            "dataset_version": DATASET_VERSION,
            "live_source_identity_sha256": live_source_sha,
            "manifest_rows_without_json_body": summary["counts"]["manifest_rows_without_json_body"],
            "manifest_sha256": manifest_sha,
            "public_episode_metadata_sha256": public_metadata_sha,
            "raw_refresh": str(RAW_REFRESH.relative_to(ROOT)),
            "raw_refresh_sha256": sha(RAW_REFRESH),
            "raw_refresh_self_hash": raw["evidence_sha256"],
        },
        "source_path": str(REQUEST.relative_to(ROOT)),
        "status": "READY_UNAUTHORIZED",
        "teacher": {
            "accepted_module_versions": ["1.32.2", "1.32.3"],
            "deck_multiset_sha256": TEACHER_DECK_SHA256,
            "submission_id": TEACHER_SUBMISSION_ID,
            "team_id": TEACHER_TEAM_ID,
            "team_name": TEACHER_TEAM,
        },
    }
    write_json(REQUEST, request)

    review = {
        "authorization": authorization,
        "created_at_utc": CREATED_AT,
        "decision": "ACCEPT_EXACT_BALANCED_48_FILE_REQUEST_READY_UNAUTHORIZED",
        "inputs": {
            "corpus_v2_manifest": {"path": str(CORPUS_V2.relative_to(ROOT)), "sha256": sha(CORPUS_V2)},
            "decision": {"path": str(DECISION.relative_to(ROOT)), "sha256": sha(DECISION)},
            "raw_refresh": {"path": str(RAW_REFRESH.relative_to(ROOT)), "sha256": sha(RAW_REFRESH), "self_hash": raw["evidence_sha256"]},
            "request": {"path": str(REQUEST.relative_to(ROOT)), "sha256": sha(REQUEST)},
            "source_wait_v2": {"path": str(SOURCE_WAIT_V2.relative_to(ROOT)), "sha256": source_wait_sha},
        },
        "producer": "chatgpt-local-agent",
        "qualification": {
            "all_selected_files_exist_in_dataset_inventory": True,
            "all_selected_files_have_exact_inventory_and_manifest_bytes": True,
            "all_selected_ids_absent_from_corpus_v2": True,
            "balanced_12_per_stratum": True,
            "candidate_request_ready": True,
            "dataset_ready": True,
            "exact_files": 48,
            "exact_maximum_bytes": summary["selected_total_bytes"],
            "optimizer_steps": 0,
            "replay_bodies_read": 0,
            "teacher_identity_unchanged": True,
            "training": False,
        },
        "record_id": "e01-corpus-v2-target-shortfall-supplement-contract-review-v1",
        "review_sha256": None,
        "reviewed_decision": "DEC-029",
        "schema_version": 1,
        "source_path": str(REVIEW.relative_to(ROOT)),
        "status": "PASS_READY_UNAUTHORIZED",
    }
    review["review_sha256"] = self_hash(review, "review_sha256")
    write_json(REVIEW, review)

    decisions = load(DECISIONS)
    decisions = [row for row in decisions if row.get("decision_id") != "DEC-029"]
    decisions.append(
        {
            "created_at_utc": CREATED_AT,
            "decision": "Accept the READY August 4 source and freeze the exact balanced 48-file supplemental corpus request; execution remains separately unauthorized.",
            "decision_id": "DEC-029",
            "producer": "decision-sidecar",
            "rationale": "The version-pinned source contains 236 completed new Majkel episodes, supports 12 inventory-verified candidates in every seat/result stratum and binds exact filenames and 180695173 declared bytes without reading replay bodies.",
            "record_id": "decision-dec-029",
            "request_path": str(REQUEST.relative_to(ROOT)),
            "request_sha256": sha(REQUEST),
            "review_path": str(REVIEW.relative_to(ROOT)),
            "review_sha256": sha(REVIEW),
            "review_self_hash": review["review_sha256"],
            "revisit_trigger": "The request is explicitly approved or rejected, source identity changes, or any selected filename, byte count, teacher identity or corpus-v2 hash changes.",
            "schema_version": 1,
            "source_path": str(DECISION.relative_to(ROOT)),
            "status": "ACCEPTED_REQUEST_READY_UNAUTHORIZED",
            "title": "Freeze exact corpus-target supplemental request",
        }
    )
    write_json(DECISIONS, decisions)

    tasks = load(TASKS)
    task = next(row for row in tasks if row.get("task_id") == "T-E01-CORPUS-TARGET-SHORTFALL-028")
    task.update(
        {
            "blocker": "The exact balanced 48-file request is ready but replay-body reads and qualified-only corpus-v3 finalization require separate exact approval.",
            "daily_source_available": True,
            "decision_id": "DEC-029",
            "decision_path": str(DECISION.relative_to(ROOT)),
            "decision_sha256": sha(DECISION),
            "eligible_new_episodes": summary["counts"]["eligible_unique_teacher_agent"],
            "exact_selected_bytes": summary["selected_total_bytes"],
            "exact_selected_files": 48,
            "request": str(REQUEST.relative_to(ROOT)),
            "request_ready": True,
            "request_sha256": sha(REQUEST),
            "review": str(REVIEW.relative_to(ROOT)),
            "review_self_hash": review["review_sha256"],
            "review_sha256": sha(REVIEW),
            "selected_strata": summary["selected_by_stratum"],
            "source_dataset": DATASET_REF,
            "source_dataset_id": DATASET_ID,
            "source_dataset_version": DATASET_VERSION,
            "source_dataset_inventory_sha256": inventory_sha,
            "source_dataset_inventory_files": summary["counts"]["inventory_files"],
            "source_manifest_sha256": manifest_sha,
            "status": "BLOCKED_APPROVAL",
            "updated_at_utc": CREATED_AT,
        }
    )
    write_json(TASKS, tasks)

    gate = load(GATE)
    gate["approved_next_action"] = f"Request separate exact approval for {REQUEST.relative_to(ROOT)} at SHA-256 {sha(REQUEST)}. If approved, read only the 48 named bodies up to 180695173 bytes on private Kaggle CPU, stop when corpus targets reach 25000, finalize qualified-only corpus v3, and stop before labels or training."
    gate["authorization"] = "EXACT_48_FILE_SUPPLEMENT_REQUEST_READY_UNAUTHORIZED_NO_BODY_READ_OR_TRAINING_AUTHORIZED"
    gate["blockers"] = [
        "Corpus v2 remains at 337 episodes and 23460 policy-loss targets, 1540 below the frozen 25000 floor.",
        "The exact 48-file, 180695173-byte balanced supplemental request is READY_UNAUTHORIZED and requires separate exact replay-body approval.",
        "Production recurrent BC, label materialization, GPU/TPU use, model promotion and submission remain separately unauthorized.",
    ]
    gate["decision"] = "DEC-029_EXACT_48_FILE_CORPUS_SUPPLEMENT_REQUEST_READY_UNAUTHORIZED"
    checks = gate.setdefault("technical_checks", [])
    checks = [row for row in checks if row.get("name") != "DEC-029 exact balanced corpus-target supplemental request"]
    checks.append({"evidence": str(REVIEW.relative_to(ROOT)), "name": "DEC-029 exact balanced corpus-target supplemental request", "status": "PASS"})
    gate["technical_checks"] = checks
    write_json(GATE, gate)

    project = PROJECT.read_text(encoding="utf-8")
    project = update_prefixed_line(project, "Last completed milestone:", "Last completed milestone: the August 4 version-1 source became READY and DEC-029 froze an exact balanced 48-file, 180,695,173-byte corpus supplemental request without reading replay bodies")
    project = update_prefixed_line(project, "Current gate:", "Current gate: the exact supplemental request is READY_UNAUTHORIZED; corpus v2 remains 1,540 targets short and production training remains blocked")
    project = update_prefixed_line(project, "Gold-path status:", "Gold-path status: DEC-029 EXACT 48-FILE SUPPLEMENT REQUEST READY / 12 PER STRATUM / 180,695,173 BYTES / CORPUS V2 23,460 TARGETS / BODY REVIEW BLOCKED APPROVAL / TRAINING BLOCKED")
    decision_section = f"""\n### DEC-029 - Exact corpus-target supplemental request ready\n\n- Source `{DATASET_REF}/{DATASET_VERSION}` is READY; dataset id `{DATASET_ID}`, inventory SHA-256 `{inventory_sha}`, manifest SHA-256 `{manifest_sha}`.\n- 236 completed new Majkel episodes intersect both inventory and manifest and are absent from corpus v2.\n- Exact request: 48 files, 12 per seat/result stratum, 180,695,173 declared bytes.\n- Request SHA-256 `{sha(REQUEST)}`; contract review self-hash `{review['review_sha256']}`.\n- No replay body was read. Execution, corpus-v3 finalization, labels, training, accelerators, model promotion and submission remain separately unauthorized.\n"""
    decision_heading = "\n### DEC-029 - Exact corpus-target supplemental request ready\n"
    actions_marker = "\n## Immediate Next Actions\n"
    if actions_marker not in project:
        raise ValueError("project immediate actions marker missing")
    if decision_heading in project:
        decision_start = project.index(decision_heading)
        decision_end = project.index(actions_marker, decision_start)
        project = project[:decision_start] + decision_section + project[decision_end:]
    else:
        project = project.replace(actions_marker, decision_section + actions_marker, 1)
    new_actions = f"""## Immediate Next Actions\n\n1. Obtain separate exact approval for `{REQUEST.relative_to(ROOT)}` at SHA-256 `{sha(REQUEST)}`.\n2. If approved, run only the bounded private Kaggle CPU body review, stop when the 25,000-target floor is reached, and finalize qualified-only corpus v3.\n3. After corpus v3 independently passes, prepare a new separate exact production recurrent-BC request; keep labels, optimizer steps, accelerators, model promotion, final deck freeze, submission, commit and push blocked meanwhile.\n"""
    actions_start = project.index(actions_marker) + 1
    source_wait_marker = "\n<!-- E01_SOURCE_WAIT_V2:START -->"
    if source_wait_marker not in project[actions_start:]:
        raise ValueError("project source-wait marker missing")
    actions_end = project.index(source_wait_marker, actions_start)
    project = project[:actions_start] + new_actions + project[actions_end:]
    PROJECT.write_text(project, encoding="utf-8")

    progress = PROGRESS.read_text(encoding="utf-8")
    progress = update_prefixed_line(progress, "Current gate:", "Current gate: **DEC-029 froze the exact balanced 48-file corpus supplement request; replay-body review requires separate exact approval**")
    progress = update_prefixed_line(progress, "Gold-path status:", "Gold-path status: **AUGUST 4 SOURCE READY; EXACT 48-FILE / 180,695,173-BYTE REQUEST READY_UNAUTHORIZED; CORPUS V2 1,540 TARGETS SHORT; TRAINING BLOCKED**")
    progress = update_prefixed_line(progress, "Latest completed milestone:", "Latest completed milestone: **metadata-only source refresh and exact supplemental request freeze completed with zero replay-body reads**")
    progress_start_marker = "<!-- E01_DEC029:START -->"
    progress_end_marker = "<!-- E01_DEC029:END -->"
    progress_section = f"""\n{progress_start_marker}\n## 2026-08-05 — Exact corpus-target supplemental request\n\n- Version-pinned source: `{DATASET_REF}/{DATASET_VERSION}`, dataset id `{DATASET_ID}`, READY, inventory SHA-256 `{inventory_sha}`, manifest SHA-256 `{manifest_sha}`.\n- 236 completed new Majkel episodes are eligible after corpus-v2 exclusion.\n- Exact selection: 48 files, 12 per seat/result stratum, 180,695,173 declared bytes.\n- Request: `{REQUEST.relative_to(ROOT)}`, SHA-256 `{sha(REQUEST)}`.\n- Contract review: `{REVIEW.relative_to(ROOT)}`, SHA-256 `{sha(REVIEW)}`, self-hash `{review['review_sha256']}`.\n- Replay bodies read: 0. Corpus promotion, labels, optimizer steps, training, accelerators, model promotion and submission remain unauthorized.\n{progress_end_marker}\n"""
    if progress_start_marker in progress:
        start = progress.index(progress_start_marker)
        end = progress.index(progress_end_marker, start) + len(progress_end_marker)
        progress = progress[:start] + progress_section.lstrip("\n").rstrip("\n") + progress[end:]
    elif "\n## 2026-08-05 — Exact corpus-target supplemental request\n" in progress:
        start = progress.index("\n## 2026-08-05 — Exact corpus-target supplemental request\n")
        progress = progress[:start] + progress_section
    else:
        progress += progress_section
    PROGRESS.write_text(progress, encoding="utf-8")

    print(
        json.dumps(
            {
                "status": "PASS_READY_UNAUTHORIZED",
                "dataset": f"{DATASET_REF}/{DATASET_VERSION}",
                "eligible_new_episodes": summary["counts"]["eligible_unique_teacher_agent"],
                "selected_files": 48,
                "selected_bytes": summary["selected_total_bytes"],
                "selected_by_stratum": summary["selected_by_stratum"],
                "request": str(REQUEST.relative_to(ROOT)),
                "request_sha256": sha(REQUEST),
                "review": str(REVIEW.relative_to(ROOT)),
                "review_sha256": sha(REVIEW),
                "review_self_hash": review["review_sha256"],
                "dataset_id": DATASET_ID,
                "dataset_inventory_files": summary["counts"]["inventory_files"],
                "dataset_inventory_sha256": inventory_sha,
                "manifest_rows_without_json_body": summary["counts"]["manifest_rows_without_json_body"],
                "raw_refresh_sha256": sha(RAW_REFRESH),
                "raw_refresh_self_hash": raw["evidence_sha256"],
                "replay_bodies_read": 0,
                "training_authorized": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
