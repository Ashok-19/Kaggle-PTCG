from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NOW = "2026-08-04T10:40:05Z"


def load(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def write_json(path: str, value) -> None:
    (ROOT / path).write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def sha(path: str) -> str:
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def replace_line(text: str, prefix: str, replacement: str) -> str:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.startswith(prefix):
            lines[index] = replacement
            return "\n".join(lines) + "\n"
    raise ValueError(f"missing line prefix: {prefix}")


def upsert_task(tasks: list[dict], task: dict) -> None:
    for index, current in enumerate(tasks):
        if current.get("task_id") == task["task_id"]:
            tasks[index] = task
            return
    tasks.append(task)


def main() -> int:
    live_path = "reports/artifacts/raw/e01-live-gold-refresh-20260804-v1.json"
    request_path = "configs/e01_majkel_live_gold_teacher_probe_request_v1.json"
    request_review_path = "reports/artifacts/e01-majkel-live-gold-teacher-contract-review-v1.json"
    manifest_path = "reports/artifacts/e01-approved-replay-corpus-manifest-v1.json"
    corpus_review_path = "reports/artifacts/e01-approved-replay-corpus-review-v1.json"
    recount_path = "reports/artifacts/e01-approved-replay-policy-loss-recount-v1.json"
    canary_path = "configs/e01_bc_engineering_canary_request_v1.json"
    canary_review_path = "reports/artifacts/e01-bc-engineering-canary-contract-review-v1.json"
    preflight_path = "reports/artifacts/e01-bc-engineering-canary-preflight-v1.json"
    preflight_review_path = "reports/artifacts/e01-bc-engineering-canary-preflight-review-v1.json"
    decision_doc = "docs/decisions/DEC-025_E01_LIVE_GOLD_REFRESH_CORPUS_FREEZE.md"

    live = load(live_path)
    request_review = load(request_review_path)
    manifest = load(manifest_path)
    corpus_review = load(corpus_review_path)
    recount = load(recount_path)
    canary_review = load(canary_review_path)
    preflight_review = load(preflight_review_path)

    work_path = "configs/gold_path_work_orders_v1.json"
    work = load(work_path)
    work["decision_id"] = "DEC-025"
    e01 = work["work_orders"]["E01-A"]
    e01.update(
        {
            "accepted_daily_manifest_sha256": live["daily_dataset"]["manifest_sha256"],
            "blocking_requirements": [
                "separate_exact_two_file_majkel_replay_approval",
                "separate_exact_64_step_local_cpu_bc_canary_optimizer_approval",
                "minimum_200_qualified_teacher_episodes",
                "minimum_25000_valid_policy_loss_targets",
                "held_out_and_on_policy_competence_evaluation",
                "separate_production_training_and_submission_approvals",
            ],
            "confirmation_observed_recent_teacher_episodes": 66,
            "confirmation_observed_recent_teacher_decisions": 7140,
            "confirmation_observed_recent_teacher_active_requests": 7542,
            "confirmation_observed_forced_teacher_requests": 402,
            "confirmation_episode_shortfall": 134,
            "confirmation_decision_shortfall": 17860,
            "current_daily_manifest_sha256": live["daily_dataset"]["manifest_sha256"],
            "current_rank_1_team_id": 16374395,
            "current_rank_1_team_name": "Majkel1337",
            "current_rank_1_rank": 1,
            "current_rank_1_score": 1253.6,
            "current_rank_1_score_is_snapshot_only": True,
            "current_rank_1_submission_id": 55186239,
            "current_rank_1_public_episode_count": 573,
            "current_rank_1_completed_public_episode_count": 571,
            "current_rank_1_public_episode_strata": {
                "seat_0_loss": 34,
                "seat_0_win": 97,
                "seat_1_loss": 54,
                "seat_1_win": 86,
            },
            "current_rank_1_latest_complete_daily_dataset": "kaggle/pokemon-tcg-ai-battle-episodes-2026-08-03/1",
            "current_rank_1_latest_dataset_json_files": 4720,
            "current_rank_1_latest_dataset_manifest_rows": 4724,
            "current_rank_1_latest_dataset_manifest_rows_without_json": 4,
            "current_rank_1_latest_dataset_declared_json_bytes": 21451459378,
            "current_rank_1_latest_dataset_inventory_sha256": "3f1d4c27d13eb3308d9efe3e32cb45a543439711e1dfd1f51dd30baa6ba0436d",
            "current_rank_1_dataset_intersection_files": 271,
            "current_rank_1_dataset_intersection_bytes": 1031040048,
            "current_rank_1_source_ready": True,
            "current_rank_1_source_wait_active": False,
            "current_rank_1_probe_request_exists": True,
            "current_rank_1_probe_request_ready": True,
            "current_rank_1_output_exists": False,
            "live_current_rank_1_refresh": live_path,
            "live_current_rank_1_refresh_sha256": sha(live_path),
            "live_current_rank_1_refresh_evidence_sha256": live["evidence_sha256"],
            "live_current_rank_1_probe_request": request_path,
            "live_current_rank_1_probe_request_sha256": sha(request_path),
            "live_current_rank_1_probe_request_files": 2,
            "live_current_rank_1_probe_request_bytes": 832877,
            "live_current_rank_1_probe_request_authorized": False,
            "live_current_rank_1_probe_review": request_review_path,
            "live_current_rank_1_probe_review_sha256": sha(request_review_path),
            "live_current_rank_1_probe_review_self_hash": request_review["review_sha256"],
            "approved_replay_corpus_manifest": manifest_path,
            "approved_replay_corpus_manifest_sha256": sha(manifest_path),
            "approved_replay_corpus_manifest_self_hash": manifest["manifest_sha256"],
            "approved_replay_corpus_review": corpus_review_path,
            "approved_replay_corpus_review_sha256": sha(corpus_review_path),
            "approved_replay_corpus_review_self_hash": corpus_review["review_sha256"],
            "approved_replay_policy_loss_recount": recount_path,
            "approved_replay_policy_loss_recount_sha256": sha(recount_path),
            "approved_replay_policy_loss_recount_self_hash": recount["review_sha256"],
            "approved_replay_files": 82,
            "approved_replay_bytes": 453143981,
            "approved_replay_qualified_episodes": 66,
            "approved_replay_policy_loss_targets": 7140,
            "approved_replay_teacher_active_requests": 7542,
            "approved_replay_forced_teacher_requests": 402,
            "approved_replay_split_counts": {"train": 50, "validation": 8, "test": 8},
            "bc_engineering_canary_request": canary_path,
            "bc_engineering_canary_request_sha256": sha(canary_path),
            "bc_engineering_canary_request_ready": True,
            "bc_engineering_canary_request_authorized": False,
            "bc_engineering_canary_maximum_optimizer_steps": 64,
            "bc_engineering_canary_optimizer_steps_executed": 0,
            "bc_engineering_canary_contract_review": canary_review_path,
            "bc_engineering_canary_contract_review_sha256": sha(canary_review_path),
            "bc_engineering_canary_contract_review_self_hash": canary_review["review_sha256"],
            "bc_engineering_canary_preflight": preflight_path,
            "bc_engineering_canary_preflight_sha256": sha(preflight_path),
            "bc_engineering_canary_preflight_review": preflight_review_path,
            "bc_engineering_canary_preflight_review_sha256": sha(preflight_review_path),
            "bc_engineering_canary_preflight_review_self_hash": preflight_review["review_sha256"],
            "next_stage": "awaiting_separate_replay_and_bc_canary_approvals",
            "state": "SOURCE_READY_REQUESTS_PREPARED_UNAUTHORIZED",
            "source_provenance_status": "PASS_TWO_RECENT_TEACHERS_LIVE_SOURCE_READY_CORPUS_FROZEN_REQUESTS_UNAUTHORIZED",
            "transfer_authorized": False,
        }
    )
    write_json(work_path, work)

    gate_path = "reports/gates/g3b.json"
    gate = load(gate_path)
    gate["updated_at_utc"] = NOW
    gate["authorization"] = "DEC_025_LIVE_SOURCE_READY_CORPUS_FROZEN_REQUESTS_PREPARED_UNAUTHORIZED_TRAINING_BLOCKED"
    gate["approved_next_action"] = (
        "Request separate explicit approval for either the exact two-file Majkel replay probe or the exact hash-bound 64-step local-CPU BC engineering canary. Do not retrieve either replay body or execute any optimizer step until the corresponding unchanged request is approved. Production training, external compute, model promotion and submission remain separately blocked."
    )
    gate["blockers"] = [
        "The confirmation corpus contains 66 episodes and 7140 valid policy-loss targets, with 7542 active teacher requests including 402 forced singleton recurrence calls. Shortfalls remain 134 episodes and 17860 policy-loss targets.",
        "The exact two-file Majkel current-rank-1 probe is source-ready but unauthorized; no replay body has been transferred.",
        "The exact eight-episode, 64-step local-CPU BC engineering canary is preflight-qualified but optimizer steps remain unauthorized. Production competence, held-out/on-policy evaluation, production training and submission remain incomplete.",
    ]
    additions = [
        ("DEC-025 authenticated live leaderboard, daily source and forum refresh", live_path),
        ("DEC-025 exact two-file Majkel request contract", request_review_path),
        ("DEC-025 immutable approved replay corpus and episode-level split review", corpus_review_path),
        ("DEC-025 corrected policy-loss target recount", recount_path),
        ("DEC-025 bounded BC engineering canary preflight", preflight_review_path),
    ]
    existing = {item.get("name") for item in gate["technical_checks"]}
    for name, evidence in additions:
        if name not in existing:
            gate["technical_checks"].append({"evidence": evidence, "name": name, "status": "PASS"})
    gate["warnings"] = [
        "G2 reliability, G3a toy PPO correctness and the E04 zero-update bridge do not establish Pokemon policy competence.",
        "The 7140 policy-loss targets exclude 402 deterministic forced singleton calls while preserving those calls in recurrent sequence context.",
        "Simulation ratings are dynamic snapshots; stable team, submission, dataset, episode and byte identities are the authorization basis.",
        "DEC-025 prepares two separate unauthorized requests. Neither replay transfer nor optimizer execution may occur without exact explicit approval.",
    ]
    write_json(gate_path, gate)

    task_path = "reports/tasks/current.json"
    tasks = load(task_path)
    for item in tasks:
        if item.get("task_id") == "T-E01-CURRENT-RANK-1-SOURCE-WAIT-024":
            item["status"] = "SUCCEEDED_SUPERSEDED"
            item["completed_at_utc"] = NOW
            item["updated_at_utc"] = NOW
            item["blocker"] = "Superseded by DEC-025 after the August 3 version-1 dataset produced an exact 271-file Majkel intersection."
            item["completion_evidence"] = list(dict.fromkeys(item["completion_evidence"] + [live_path, decision_doc]))
    upsert_task(
        tasks,
        {
            "schema_version": 1,
            "record_id": "task-e01-live-gold-refresh-20260804",
            "source_path": task_path,
            "task_id": "T-E01-LIVE-GOLD-REFRESH-20260804",
            "title": "Refresh live gold state and freeze training readiness",
            "phase": "E01-A",
            "priority": 13,
            "producer": "chatgpt-local-agent",
            "created_at_utc": NOW,
            "updated_at_utc": NOW,
            "completed_at_utc": NOW,
            "status": "SUCCEEDED",
            "depends_on": ["DEC-024", "DEC-025"],
            "completion_evidence": [live_path, manifest_path, corpus_review_path, recount_path, request_review_path, canary_review_path, preflight_review_path, decision_doc],
            "source_ready": True,
            "current_rank_1_submission_id": 55186239,
            "dataset_intersection_files": 271,
            "dataset_intersection_bytes": 1031040048,
            "approved_replay_files": 82,
            "approved_replay_bytes": 453143981,
            "qualified_episodes": 66,
            "policy_loss_targets": 7140,
            "forced_teacher_requests": 402,
            "episode_shortfall": 134,
            "policy_loss_shortfall": 17860,
            "replay_transfer_authorized": False,
            "optimizer_steps_authorized": False,
            "external_compute_authorized": False,
            "training_authorized": False,
            "submission_authorized": False,
            "done_when": "Authenticated live state, exact intersections, forum evidence, immutable corpus, leakage-safe splits, corrected policy-loss count and bounded unauthorized requests are independently reviewed and recorded.",
        },
    )
    upsert_task(
        tasks,
        {
            "schema_version": 1,
            "record_id": "task-e01-majkel-live-probe-025",
            "source_path": task_path,
            "task_id": "T-E01-MAJKEL-LIVE-GOLD-PROBE-025",
            "title": "Approve or reject the exact two-file Majkel probe",
            "phase": "E01-A",
            "priority": 14,
            "producer": "chatgpt-local-agent",
            "created_at_utc": NOW,
            "updated_at_utc": NOW,
            "status": "BLOCKED_APPROVAL",
            "depends_on": ["DEC-025"],
            "request": request_path,
            "request_sha256": sha(request_path),
            "files": 2,
            "bytes": 832877,
            "request_ready": True,
            "authorized": False,
            "replay_transfer_authorized": False,
            "training_authorized": False,
            "done_when": "The exact unchanged request is explicitly approved or rejected; if approved, retrieve only the two named replay bodies and stop after contract review.",
        },
    )
    upsert_task(
        tasks,
        {
            "schema_version": 1,
            "record_id": "task-e01-bc-engineering-canary-025",
            "source_path": task_path,
            "task_id": "T-E01-BC-ENGINEERING-CANARY-025",
            "title": "Approve or reject the bounded BC engineering canary",
            "phase": "E01-BC",
            "priority": 14,
            "producer": "chatgpt-local-agent",
            "created_at_utc": NOW,
            "updated_at_utc": NOW,
            "status": "BLOCKED_APPROVAL",
            "depends_on": ["DEC-025"],
            "request": canary_path,
            "request_sha256": sha(canary_path),
            "episodes": 8,
            "maximum_optimizer_steps": 64,
            "request_ready": True,
            "authorized": False,
            "optimizer_steps_authorized": False,
            "production_training_authorized": False,
            "external_compute_authorized": False,
            "done_when": "The exact unchanged local-CPU canary is explicitly approved or rejected; no production continuation is implied by approval or pass.",
        },
    )
    write_json(task_path, tasks)

    project_path = ROOT / "PROJECT_STATUS.md"
    project = project_path.read_text(encoding="utf-8")
    project = replace_line(project, "Last completed milestone:", "Last completed milestone: DEC-025 authenticated the August 4 live state, made the current rank-1 source ready, froze the approved corpus and prepared exact replay and BC-canary requests without authorizing either")
    project = replace_line(project, "Gold-path status:", "Gold-path status: DEC-025 LIVE SOURCE READY / APPROVED CORPUS FROZEN / EXACT REPLAY REQUEST READY UNAUTHORIZED / BC ENGINEERING CANARY READY UNAUTHORIZED / TRAINING BLOCKED / SUBMISSION BLOCKED")
    project = replace_line(project, "| G3b Pokemon policy competence", "| G3b Pokemon policy competence | blocked | `docs/decisions/DEC-025_E01_LIVE_GOLD_REFRESH_CORPUS_FREEZE.md`, `reports/artifacts/raw/e01-live-gold-refresh-20260804-v1.json`, `reports/artifacts/e01-approved-replay-corpus-manifest-v1.json`, `reports/artifacts/e01-approved-replay-corpus-review-v1.json`, `reports/artifacts/e01-approved-replay-policy-loss-recount-v1.json`, `configs/e01_majkel_live_gold_teacher_probe_request_v1.json`, `configs/e01_bc_engineering_canary_request_v1.json`, `reports/gates/g3b.json` | Current rank-1 Majkel submission `55186239` has a 271-file August 3 source intersection. The approved corpus is 82 files / 453,143,981 bytes / 66 episodes / 7,140 policy-loss targets; 402 forced calls are retained for recurrence but excluded from policy loss. Shortfalls are 134 episodes and 17,860 targets. Both exact requests remain unauthorized; no replay transfer, optimizer step, training, external compute or submission occurred. |")
    project = replace_line(project, "No active long-running jobs.", "No active long-running jobs. DEC-025 refreshed the official deadline/rules, dynamic leaderboard and active submission identities, exact episode inventories and August 3 source intersections, plus exact post-July-30 forum messages. It retrieved metadata only and no replay body. The immutable approved corpus contains exactly 82 previously approved files totaling 453,143,981 bytes and 66 qualified episodes. Its episode-level split is 50 train, 8 validation and 8 test with no leakage. Correct policy-loss coverage is 7,140 targets from 7,542 active teacher requests after excluding 402 forced singleton calls from loss while retaining recurrence. The exact Majkel two-file request totals 832,877 bytes and is unauthorized. The exact eight-episode, 64-step local-CPU BC engineering canary is preflight-qualified and unauthorized. Training, external compute, model promotion and submission remain blocked. Verified project compute cost remains USD `0`.")
    project = project.replace("17,458 decisions", "17,860 policy-loss targets").replace("7,542 decisions total", "7,140 policy-loss targets from 7,542 active requests")
    if "### DEC-025 - Live source ready and approved corpus frozen" not in project:
        marker = "### DEC-024 - Wait for a versioned current-rank-1 source"
        section = "### DEC-025 - Live source ready and approved corpus frozen\n\n- Evidence: `reports/artifacts/raw/e01-live-gold-refresh-20260804-v1.json`, `reports/artifacts/e01-approved-replay-corpus-manifest-v1.json`, `reports/artifacts/e01-approved-replay-corpus-review-v1.json`, `reports/artifacts/e01-approved-replay-policy-loss-recount-v1.json`, `reports/artifacts/e01-majkel-live-gold-teacher-contract-review-v1.json`, `reports/artifacts/e01-bc-engineering-canary-preflight-review-v1.json`.\n- Outcome: current rank-1 Majkel source ready; exact two-file replay request and exact 64-step BC engineering canary request prepared but unauthorized; corpus frozen at 66 episodes and 7,140 valid policy-loss targets; training and submission remain blocked.\n\n"
        project = project.replace(marker, section + marker)
    project_path.write_text(project, encoding="utf-8")

    progress_path = ROOT / "PROGRESS_REPORT.md"
    progress = progress_path.read_text(encoding="utf-8")
    progress = replace_line(progress, "Gold-path status:", "Gold-path status: **DEC-025 LIVE SOURCE READY; APPROVED CORPUS FROZEN; EXACT REPLAY REQUEST READY UNAUTHORIZED; BC ENGINEERING CANARY READY UNAUTHORIZED; TRAINING AND SUBMISSION BLOCKED**")
    progress = replace_line(progress, "Latest completed milestone:", "Latest completed milestone: **DEC-025 authenticated the August 4 live state, froze the approved corpus, corrected policy-loss coverage to 7,140, and prepared two exact unauthorized requests**")
    progress = progress.replace("17,458 decisions", "17,860 policy-loss targets").replace("66 episodes and 7,542 decisions", "66 episodes and 7,140 policy-loss targets from 7,542 active requests")
    if "## DEC-025 live refresh and corpus freeze" not in progress:
        progress += "\n## DEC-025 live refresh and corpus freeze\n\nAuthenticated metadata proves current rank-1 Majkel submission `55186239` intersects the complete August 3 version-1 dataset in 271 available JSON files totaling 1,031,040,048 bytes. The smallest opposite-seat, both-winning pair is `89651832.json` plus `89802438.json`, exactly 832,877 bytes; it remains unauthorized and no body was retrieved. The already approved corpus is frozen at 82 files, 453,143,981 bytes, 66 episodes, 7,140 valid policy-loss targets, 402 forced recurrence-only calls, and leakage-safe 50/8/8 episode splits. A separate eight-episode, 64-step local-CPU BC engineering canary request is preflight-qualified but unauthorized. No optimizer step, external compute, production training, model promotion or submission occurred.\n"
    progress_path.write_text(progress, encoding="utf-8")

    review_path = "reports/artifacts/gold-path-work-orders-review-v1.json"
    if (ROOT / review_path).exists():
        review = load(review_path)
        if review.get("reviewed_decision") == "DEC-025" and review.get("status") == "PASS":
            decisions_path = "reports/decisions/current.json"
            decisions = load(decisions_path)
            decisions = [item for item in decisions if item.get("decision_id") != "DEC-025"]
            decisions.append(
                {
                    "schema_version": 1,
                    "record_id": "decision-dec-025",
                    "decision_id": "DEC-025",
                    "title": "Refresh live gold state, freeze the approved corpus and prepare bounded unauthorized requests",
                    "created_at_utc": NOW,
                    "updated_at_utc": NOW,
                    "producer": "decision-sidecar",
                    "source_path": decision_doc,
                    "status": "ACCEPTED_REQUESTS_PREPARED_UNAUTHORIZED",
                    "decision": "Accept the authenticated live refresh and immutable approved corpus; prepare the exact two-file Majkel replay probe and exact 64-step local-CPU BC engineering canary without authorizing either execution.",
                    "rationale": "The August 3 dataset contains an exact 271-file current-rank-1 intersection, while the approved corpus can now be frozen reproducibly. Forced singleton calls must remain recurrent context but cannot count as policy-loss targets.",
                    "live_refresh_sha256": sha(live_path),
                    "live_refresh_evidence_sha256": live["evidence_sha256"],
                    "work_orders_sha256": sha(work_path),
                    "work_orders_review_sha256": sha(review_path),
                    "work_orders_review_self_hash": review["review_sha256"],
                    "current_rank_1": {
                        "team_name": "Majkel1337",
                        "team_id": 16374395,
                        "submission_id": 55186239,
                        "score_snapshot": 1253.6,
                        "score_is_authorization_basis": False,
                        "latest_complete_daily_dataset": "kaggle/pokemon-tcg-ai-battle-episodes-2026-08-03/1",
                        "dataset_intersection_files": 271,
                        "dataset_intersection_bytes": 1031040048,
                    },
                    "exact_replay_request": {
                        "path": request_path,
                        "sha256": sha(request_path),
                        "files": ["89651832.json", "89802438.json"],
                        "total_bytes": 832877,
                        "request_ready": True,
                        "authorized": False,
                    },
                    "approved_corpus": {
                        "manifest_path": manifest_path,
                        "manifest_sha256": manifest["manifest_sha256"],
                        "files": 82,
                        "bytes": 453143981,
                        "qualified_episodes": 66,
                        "teacher_active_requests": 7542,
                        "forced_teacher_requests": 402,
                        "policy_loss_targets": 7140,
                        "split_counts": {"train": 50, "validation": 8, "test": 8},
                        "episode_shortfall": 134,
                        "policy_loss_shortfall": 17860,
                    },
                    "bc_engineering_canary": {
                        "path": canary_path,
                        "sha256": sha(canary_path),
                        "episodes": 8,
                        "maximum_optimizer_steps": 64,
                        "optimizer_steps_executed": 0,
                        "request_ready": True,
                        "authorized": False,
                        "production_checkpoint_eligible": False,
                    },
                    "authorization": {
                        "replay_transfer": False,
                        "agent_logs": False,
                        "raw_exports": False,
                        "label_generation": False,
                        "optimizer_steps": False,
                        "production_training": False,
                        "external_compute": False,
                        "model_promotion": False,
                        "submission": False,
                        "git_commit": False,
                        "git_push": False,
                    },
                    "training_authorized": False,
                    "submission_authorized": False,
                    "external_compute_authorized": False,
                    "revisit_trigger": "Either exact request is approved or changes; any source, corpus, split, semantic, code, asset or review hash changes; or any replay, optimizer, production-training, external-compute, submission, commit or push scope is proposed.",
                }
            )
            write_json(decisions_path, decisions)

    print(
        json.dumps(
            {
                "decision_id": "DEC-025",
                "work_orders_sha256": sha(work_path),
                "gate_sha256": sha(gate_path),
                "tasks_sha256": sha(task_path),
                "decision_registry_updated": any(
                    item.get("decision_id") == "DEC-025"
                    for item in load("reports/decisions/current.json")
                ),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
