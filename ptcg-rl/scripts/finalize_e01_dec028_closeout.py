from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CREATED_AT = "2026-08-04T15:55:00Z"
APPROVED_AT = "2026-08-04T15:24:13Z"
PRIOR_EXPANSION_SHA = "7652f617e9bba2cd5a18a3d4b9956d348438989359e0fb200ef0f6066a590d3c"
PRIOR_CANARY_SHA = "5e78bcd7595a1f30b5eba5ab179203aa53ecad43f0ef3275a773a4b0ee4f2299"


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()


def pretty_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def self_hash(value: dict[str, Any], field: str) -> str:
    payload = copy.deepcopy(value)
    payload.pop(field, None)
    return hashlib.sha256(canonical_bytes(payload)).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = pretty_bytes(value)
    if path.exists() and path.read_bytes() == data:
        return
    partial = path.with_suffix(path.suffix + ".partial")
    partial.write_bytes(data)
    partial.replace(path)


def upsert(rows: list[dict[str, Any]], key: str, value: str, row: dict[str, Any]) -> None:
    indices = [index for index, item in enumerate(rows) if item.get(key) == value]
    if len(indices) > 1:
        raise ValueError(f"duplicate {key}={value}")
    if indices:
        rows[indices[0]] = row
    else:
        rows.append(row)


def main() -> None:
    expansion_path = ROOT / "configs/e01_majkel_corpus_expansion_request_v1.json"
    canary_path = ROOT / "configs/e01_bc_engineering_canary_request_v1.json"
    run_path = ROOT / "reports/artifacts/e01-majkel-corpus-review-v1.json"
    corpus_path = ROOT / "reports/artifacts/e01-approved-replay-corpus-manifest-v2.json"
    corpus_review_path = ROOT / "reports/artifacts/e01-approved-replay-corpus-review-v2.json"
    output_manifest_path = ROOT / "reports/artifacts/e01-majkel-corpus-review-v1-output-manifest.json"
    canary_report_path = ROOT / "reports/evaluations/e01-bc-engineering-canary-v1.json"
    canary_review_path = ROOT / "reports/artifacts/e01-bc-engineering-canary-execution-review-v1.json"
    checkpoint_path = ROOT / "private/g3/e01/bc-engineering-canary-v1/step-32.pt"
    checkpoint_manifest_path = ROOT / "private/g3/e01/bc-engineering-canary-v1/step-32.pt.manifest.json"

    expected = {
        run_path: "31fdff1a40de058407b07de5975e2bf531fdc417aae456f54e88759386918d16",
        corpus_path: "ccc247edbc4cac0aba11c6acb26fc5e2a8c75e0a4f005d1441ce6949c0c4997f",
        corpus_review_path: "87eaee15513189d7f2ff4ca44e631016b3f937165df31db8696383a30c1cad56",
        output_manifest_path: "ef8ce73b6185e183ac8f32ea8267e50b3e3bb67e161cee22016c25d4ee7ef2ed",
        canary_report_path: "51e06333619f1e8fc34ebb889d84cb196997632b0e347c731fe558df7813c1ee",
        canary_review_path: "1f25828a78400801f6dc5d2d8630890579e29584762ad95b18af795ca810c100",
        checkpoint_path: "c8df3666c87a895639092d6898b3ab8254ca6f0785c44980f1fba96d0000ec5d",
        checkpoint_manifest_path: "cf0b6317976733ed2acad214e644fbd0c86def35ca96930d22427dc139f404e7",
    }
    for path, expected_hash in expected.items():
        observed = sha(path)
        if observed != expected_hash:
            raise ValueError(f"hash differs for {path}: {observed}")

    run = json.loads(run_path.read_text())
    corpus = json.loads(corpus_path.read_text())
    corpus_review = json.loads(corpus_review_path.read_text())
    output_manifest = json.loads(output_manifest_path.read_text())
    canary = json.loads(canary_path.read_text())
    canary_report = json.loads(canary_report_path.read_text())
    canary_review = json.loads(canary_review_path.read_text())

    for value, field, expected_hash in (
        (run, "review_sha256", "124f4d08bc1cd0143c8709af8f109ba9290911dd28068ddcdc768f5d1ea2990b"),
        (corpus, "manifest_sha256", "e736f609209805c28bb4aa97106e163386667d639b9b21573f8ea749b11925b6"),
        (corpus_review, "review_sha256", "dc995dfd07d509c0271f1c7e4138408248cabbe2a64134b04439b9b121ced6c3"),
        (output_manifest, "manifest_sha256", "dd9c53fa64ba8be1a86af5d10f39215bf4352236dab2385673ea970e9cbc4233"),
        (canary_review, "review_sha256", "2f365281ed62e91139b67a9cb3b0fdb5a7149fed1fd7ec9cbd7d43097175280d"),
    ):
        if self_hash(value, field) != expected_hash or value[field] != expected_hash:
            raise ValueError(f"self hash differs for {field}")

    qualified = corpus["qualified_training_corpus"]
    if (
        run["status"] != "PASS"
        or run["transfer"]["named_replay_bodies_read"] != 269
        or run["transfer"]["new_bytes_read"] != 1_030_207_171
        or run["transfer"]["replay_body_outputs"] != 0
        or run["review"]["qualified_new_files"] != 269
        or run["review"]["rejected_new_files"] != 0
        or qualified["episodes"] != 337
        or qualified["policy_loss_targets"] != 23_460
        or corpus_review["status"] != "BLOCKED_FLOORS"
        or corpus_review["qualification"]["minimum_200_episodes"] is not True
        or corpus_review["qualification"]["minimum_25000_policy_loss_targets"] is not False
    ):
        raise ValueError("corpus-v2 result differs")
    if (
        canary.get("status") != "CONSUMED_PASS_NON_PROMOTABLE"
        or canary.get("authorization_consumed") is not True
        or canary_report.get("optimizer_steps") != 64
        or canary_report.get("prior_failed_attempt_optimizer_steps") != 10
        or canary_report.get("successful_attempt_optimizer_steps") != 54
        or canary_report.get("production_checkpoint_eligible") is not False
        or canary_review.get("status") != "PASS"
    ):
        raise ValueError("canary result differs")

    expansion = json.loads(expansion_path.read_text())
    expansion_current_hash = sha(expansion_path)
    if expansion_current_hash == PRIOR_EXPANSION_SHA:
        if (
            expansion.get("status") != "READY_UNAUTHORIZED"
            or expansion.get("request_ready") is not True
            or expansion.get("authorized") is not False
            or expansion.get("authorization_consumed") is not False
        ):
            raise ValueError("expansion request is not the approved prior state")
        approval = {
            "approved_by": "user",
            "approved_at_utc": APPROVED_AT,
            "approved_prior_request_sha256": PRIOR_EXPANSION_SHA,
            "approval_scope": "AUTHORIZED_EXACT_269_FILE_PRIVATE_KAGGLE_CPU_MAJKEL_REVIEW_AND_QUALIFIED_CORPUS_V2_FINALIZATION_ONLY",
            "one_time": True,
            "maximum_new_files": 269,
            "maximum_new_bytes": 1_030_207_171,
            "private_kaggle_cpu_authorized": True,
            "named_replay_body_reads_authorized": True,
            "qualified_only_corpus_v2_finalization_authorized": True,
            "replay_body_exports_authorized": False,
            "training_label_materialization_authorized": False,
            "optimizer_steps_authorized": False,
            "training_authorized": False,
            "model_promotion_authorized": False,
            "submission_authorized": False,
            "git_commit_authorized": False,
            "git_push_authorized": False,
        }
        authorized = copy.deepcopy(expansion)
        authorized.update(
            status="AUTHORIZED_ONE_TIME_EXECUTION",
            request_ready=False,
            authorized=True,
            authorization_consumed=False,
            approval=approval,
        )
        authorized["authorization"].update(
            replay_transfer=True,
            external_compute=True,
            corpus_promotion=True,
        )
        approval["authorized_payload_sha256"] = hashlib.sha256(canonical_bytes(authorized)).hexdigest()
        expansion.update(
            status="CONSUMED_PASS_CORPUS_V2_BLOCKED_TARGET_FLOOR",
            request_ready=False,
            authorized=False,
            authorization_consumed=True,
            approval=approval,
            completed_at_utc=CREATED_AT,
            execution_receipt={
                "approved_prior_request_sha256": PRIOR_EXPANSION_SHA,
                "authorized_payload_sha256": approval["authorized_payload_sha256"],
                "notebook_id": 129_704_016,
                "notebook_slug": "ashok205/kptcg-e01-majkel-corpus-review-v1",
                "successful_saved_version": 2,
                "failed_closed_saved_versions": [1],
                "private": True,
                "internet": False,
                "gpu": False,
                "tpu": False,
                "source_dataset": "kaggle/pokemon-tcg-ai-battle-episodes-2026-08-03/1",
                "input_bundle_dataset": "ashok205/kptcg-e01-majkel-corpus-review-inputs/1",
                "input_bundle_dataset_id": 11_501_808,
                "named_replay_bodies_read": 269,
                "new_bytes_read": 1_030_207_171,
                "reused_probe_bodies_without_reread": 2,
                "qualified_new_files": 269,
                "rejected_new_files": 0,
                "replay_body_outputs": 0,
                "agent_logs_read": 0,
                "optimizer_steps": 0,
                "training": False,
                "corpus_manifest": str(corpus_path.relative_to(ROOT)),
                "corpus_manifest_sha256": sha(corpus_path),
                "corpus_manifest_self_hash": corpus["manifest_sha256"],
                "corpus_review": str(corpus_review_path.relative_to(ROOT)),
                "corpus_review_sha256": sha(corpus_review_path),
                "corpus_review_self_hash": corpus_review["review_sha256"],
                "qualified_episodes": 337,
                "policy_loss_targets": 23_460,
                "production_target_shortfall": 1_540,
                "production_training_authorized": False,
                "git_commit": False,
                "git_push": False,
            },
        )
        for key in expansion["authorization"]:
            expansion["authorization"][key] = False
        write_json(expansion_path, expansion)
    elif expansion.get("status") != "CONSUMED_PASS_CORPUS_V2_BLOCKED_TARGET_FLOOR":
        raise ValueError(f"unexpected expansion request hash/state: {expansion_current_hash}")

    canary["request_ready"] = False
    canary["updated_at_utc"] = CREATED_AT
    canary["closeout_decision"] = "DEC-028"
    canary["closeout_status"] = "PASS_NON_PROMOTABLE_AUTHORIZATION_CONSUMED"
    write_json(canary_path, canary)

    job = {
        "schema_version": 1,
        "record_id": "job-e01-majkel-corpus-review-v1",
        "source_path": "reports/jobs/e01-majkel-corpus-review-v1.json",
        "created_at_utc": CREATED_AT,
        "producer": "scripts/finalize_e01_dec028_closeout.py",
        "status": "SUCCEEDED_CORPUS_V2_BLOCKED_TARGET_FLOOR",
        "decision": "PRIVATE_KAGGLE_CPU_EXACT_269_FILE_REVIEW_PASS",
        "notebook": {
            "id": 129_704_016,
            "owner": "ashok205",
            "slug": "kptcg-e01-majkel-corpus-review-v1",
            "private": True,
            "successful_saved_version": 2,
            "failed_closed_versions": [
                {
                    "version": 1,
                    "failure": "source bundle lookup assumed an archive instead of Kaggle's expanded read-only directory",
                    "replay_bodies_read": 0,
                }
            ],
            "internet": False,
            "gpu": False,
            "tpu": False,
            "dataset_sources": [
                "ashok205/kptcg-e01-majkel-corpus-review-inputs/1",
                "kaggle/pokemon-tcg-ai-battle-episodes-2026-08-03/1",
            ],
            "competition_source": "pokemon-tcg-ai-battle",
        },
        "execution": {
            "named_replay_bodies_read": 269,
            "new_bytes_read": 1_030_207_171,
            "reused_probe_bodies_without_reread": 2,
            "qualified_new_files": 269,
            "rejected_new_files": 0,
            "replay_body_outputs": 0,
            "agent_logs_read": 0,
            "optimizer_created": False,
            "optimizer_steps": 0,
            "training": False,
        },
        "corpus_v2": {
            "episodes": 337,
            "bytes": 1_414_841_670,
            "teacher_active_requests": 25_058,
            "forced_teacher_requests": 1_598,
            "policy_loss_targets": 23_460,
            "episode_floor_passed": True,
            "policy_target_floor_passed": False,
            "policy_target_shortfall": 1_540,
            "manifest_path": str(corpus_path.relative_to(ROOT)),
            "manifest_sha256": sha(corpus_path),
            "manifest_self_hash": corpus["manifest_sha256"],
            "review_path": str(corpus_review_path.relative_to(ROOT)),
            "review_sha256": sha(corpus_review_path),
            "review_self_hash": corpus_review["review_sha256"],
        },
        "authorization": {
            "replay_authorization_consumed": True,
            "further_replay_reads": False,
            "training_label_materialization": False,
            "optimizer_steps": False,
            "production_training": False,
            "model_promotion": False,
            "submission": False,
            "git_commit": False,
            "git_push": False,
        },
        "receipt_sha256": None,
    }
    job["receipt_sha256"] = self_hash(job, "receipt_sha256")
    job_path = ROOT / job["source_path"]
    write_json(job_path, job)

    decision_md = """# DEC-028 - Complete the Majkel corpus review and BC engineering canary\n\n- Status: accepted with production corpus target floor still blocked\n- Date: 2026-08-04\n\n## Decision\n\nConsume both exact one-time approvals. Accept the private Kaggle CPU review of the 269 named Majkel replay bodies and accept the bounded 64-step local-CPU BC engineering canary as non-promotable engineering evidence. Preserve the frozen 25,000-policy-target production floor. Do not start production BC from corpus v2 because it contains 23,460 valid policy-loss targets, a shortfall of 1,540.\n\n## Results\n\n- All 269 newly read Majkel files qualified; zero were rejected.\n- Exactly 1,030,207,171 new bytes were read; the two prior probe bodies were reused without rereading.\n- No replay body or agent log was exported.\n- Corpus v2 contains 337 episodes, 25,058 teacher requests, 1,598 forced recurrent calls and 23,460 policy-loss targets.\n- The 200-episode floor passes; the 25,000-target floor remains blocked by 1,540 targets.\n- The BC canary consumed exactly 64 cumulative AdamW steps: 10 steps before a fail-closed forced-only-chunk scheduler error and 54 recovery steps after the scheduler was corrected to skip that zero-loss chunk.\n- Loss and gradients remained finite; the step-32 checkpoint restored exactly. The checkpoint is permanently non-promotable and establishes no policy competence.\n\n## Boundaries\n\nProduction label materialization, production training, further optimizer steps, additional replay reads, GPU/TPU use, model promotion, deck freeze, submission, Git commit and Git push remain unauthorized. The next admissible data action is an exact, separately approved supplemental replay review expected to add at least 1,540 valid policy-loss targets while preserving the frozen data and split contracts.\n"""
    decision_path = ROOT / "docs/decisions/DEC-028_E01_CORPUS_V2_AND_BC_CANARY_CLOSEOUT.md"
    decision_path.write_text(decision_md, encoding="utf-8")

    decision = {
        "schema_version": 1,
        "record_id": "decision-dec-028",
        "decision_id": "DEC-028",
        "source_path": str(decision_path.relative_to(ROOT)),
        "title": "Complete the Majkel corpus review and BC engineering canary",
        "created_at_utc": CREATED_AT,
        "updated_at_utc": CREATED_AT,
        "producer": "decision-sidecar",
        "status": "ACCEPTED_CORPUS_V2_QUALIFIED_TARGET_FLOOR_BLOCKS_PRODUCTION_BC",
        "decision": "Consume both exact approvals, accept corpus v2 and the non-promotable BC canary, and preserve the 25,000-target production floor.",
        "rationale": "All named replay bodies qualified and the engineering path passed, but 23,460 valid targets remain 1,540 below the frozen production floor.",
        "corpus_v2": job["corpus_v2"],
        "bc_engineering_canary": {
            "status": "PASS_NON_PROMOTABLE",
            "episodes": 8,
            "cumulative_optimizer_steps": 64,
            "failed_closed_attempt_steps": 10,
            "recovery_steps": 54,
            "checkpoint_step": 32,
            "checkpoint_payload_sha256": "c8df3666c87a895639092d6898b3ab8254ca6f0785c44980f1fba96d0000ec5d",
            "execution_report": str(canary_report_path.relative_to(ROOT)),
            "execution_report_sha256": sha(canary_report_path),
            "execution_review": str(canary_review_path.relative_to(ROOT)),
            "execution_review_sha256": sha(canary_review_path),
            "execution_review_self_hash": canary_review["review_sha256"],
            "production_checkpoint_eligible": False,
            "policy_competence_claimed": False,
        },
        "initial_training_deck_frozen": True,
        "model_architecture_frozen": True,
        "gold_strategy_sequence_frozen": True,
        "training_corpus_final": False,
        "production_training_authorized": False,
        "optimizer_steps_authorized": False,
        "replay_transfer_authorized": False,
        "submission_authorized": False,
        "revisit_trigger": "A hash-bound supplemental replay request closes the 1,540-target shortfall, or any production training, label materialization, architecture, deck, accelerator, promotion or submission scope changes.",
        "decision_sha256": sha(decision_path),
    }

    decisions_path = ROOT / "reports/decisions/current.json"
    decisions = json.loads(decisions_path.read_text())
    upsert(decisions, "decision_id", "DEC-028", decision)
    write_json(decisions_path, decisions)

    tasks_path = ROOT / "reports/tasks/current.json"
    tasks = json.loads(tasks_path.read_text())
    canary_task = next(item for item in tasks if item.get("task_id") == "T-E01-BC-ENGINEERING-CANARY-025")
    canary_task.update(
        status="SUCCEEDED",
        request_ready=False,
        explicit_exact_approval_required=False,
        authorization_consumed=True,
        completed_at_utc=CREATED_AT,
        optimizer_steps_authorized=False,
        cumulative_optimizer_steps=64,
        failed_closed_attempt_optimizer_steps=10,
        recovery_optimizer_steps=54,
        production_checkpoint_eligible=False,
        completion_evidence=[
            str(canary_path.relative_to(ROOT)),
            str(canary_report_path.relative_to(ROOT)),
            str(canary_review_path.relative_to(ROOT)),
        ],
        consumed_request_sha256=sha(canary_path),
        execution_review_self_hash=canary_review["review_sha256"],
        updated_at_utc=CREATED_AT,
    )
    expansion_task = next(item for item in tasks if item.get("task_id") == "T-E01-MAJKEL-CORPUS-EXPANSION-027")
    expansion_task.update(
        status="SUCCEEDED",
        request_ready=False,
        explicit_exact_approval_required=False,
        authorization_consumed=True,
        completed_at_utc=CREATED_AT,
        external_compute_authorized=False,
        replay_transfer_authorized=False,
        corpus_promotion_authorized=False,
        qualified_new_files=269,
        rejected_new_files=0,
        new_bytes_read=1_030_207_171,
        replay_body_outputs=0,
        qualified_episodes=337,
        policy_loss_targets=23_460,
        production_target_shortfall=1_540,
        production_training_authorized=False,
        result="PASS_CORPUS_V2_BLOCKED_TARGET_FLOOR",
        completion_evidence=[
            str(expansion_path.relative_to(ROOT)),
            str(job_path.relative_to(ROOT)),
            str(run_path.relative_to(ROOT)),
            str(corpus_path.relative_to(ROOT)),
            str(corpus_review_path.relative_to(ROOT)),
        ],
        consumed_request_sha256=sha(expansion_path),
        updated_at_utc=CREATED_AT,
    )
    shortfall_task = {
        "schema_version": 1,
        "record_id": "task-e01-corpus-v2-target-shortfall-028",
        "task_id": "T-E01-CORPUS-V2-TARGET-SHORTFALL-028",
        "source_path": "reports/tasks/current.json",
        "title": "Close the remaining corpus-v2 policy-target shortfall",
        "created_at_utc": CREATED_AT,
        "updated_at_utc": CREATED_AT,
        "producer": "chatgpt-local-agent",
        "phase": "E01-DATA",
        "priority": 16,
        "status": "BLOCKED_SOURCE_REFRESH_AND_APPROVAL",
        "depends_on": ["DEC-028", "T-E01-MAJKEL-CORPUS-EXPANSION-027"],
        "current_qualified_episodes": 337,
        "current_policy_loss_targets": 23_460,
        "minimum_required_policy_loss_targets": 25_000,
        "policy_loss_target_shortfall": 1_540,
        "episode_floor_passed": True,
        "target_floor_passed": False,
        "done_when": "A separately approved hash-bound supplemental body review adds enough qualified targets to reach at least 25,000 without label materialization or training.",
        "request_ready": False,
        "replay_transfer_authorized": False,
        "training_authorized": False,
        "optimizer_steps_authorized": False,
    }
    upsert(tasks, "task_id", shortfall_task["task_id"], shortfall_task)
    write_json(tasks_path, tasks)

    gate_path = ROOT / "reports/gates/g3b.json"
    gate = json.loads(gate_path.read_text())
    gate.update(
        status="BLOCKED",
        decision="NOT_REVIEWED",
        authorization="DEC_028_CORPUS_V2_QUALIFIED_BC_CANARY_PASS_TARGET_FLOOR_BLOCKS_PRODUCTION_TRAINING",
        approved_next_action="Refresh the latest versioned Majkel source and prepare the smallest exact supplemental replay request expected to add at least 1,540 valid policy-loss targets. Keep label materialization and production training separately approval-gated.",
        blockers=[
            "Corpus v2 contains 337 qualified episodes and 23,460 valid policy-loss targets. The episode floor passes, but the frozen 25,000-target production floor remains short by 1,540 targets.",
            "The 64-step local-CPU BC engineering canary passed and is permanently non-promotable; it establishes engineering readiness but not policy competence.",
            "Production label materialization, production BC, held-out/on-policy competence evaluation, PPO, final deck freeze and submission remain incomplete and separately unauthorized.",
        ],
        updated_at_utc=CREATED_AT,
    )
    names = {item.get("name") for item in gate.get("technical_checks", [])}
    additions = [
        {
            "name": "DEC-028 exact 269-file Majkel private CPU review and corpus-v2 finalization",
            "status": "PASS",
            "evidence": str(corpus_review_path.relative_to(ROOT)),
        },
        {
            "name": "DEC-028 exact 64-step local-CPU BC engineering canary",
            "status": "PASS",
            "evidence": str(canary_review_path.relative_to(ROOT)),
        },
        {
            "name": "minimum 25,000 valid policy-loss targets",
            "status": "BLOCKED",
            "evidence": str(corpus_review_path.relative_to(ROOT)),
        },
    ]
    for item in additions:
        if item["name"] not in names:
            gate.setdefault("technical_checks", []).append(item)
    write_json(gate_path, gate)

    work_path = ROOT / "configs/gold_path_work_orders_v1.json"
    work = json.loads(work_path.read_text())
    e01 = work["work_orders"]["E01-A"]
    e01.update(
        approved_replay_bytes=1_414_841_670,
        approved_replay_corpus_manifest=str(corpus_path.relative_to(ROOT)),
        approved_replay_corpus_manifest_self_hash=corpus["manifest_sha256"],
        approved_replay_corpus_manifest_sha256=sha(corpus_path),
        approved_replay_corpus_review=str(corpus_review_path.relative_to(ROOT)),
        approved_replay_corpus_review_self_hash=corpus_review["review_sha256"],
        approved_replay_corpus_review_sha256=sha(corpus_review_path),
        approved_replay_files=337,
        approved_replay_forced_teacher_requests=1_598,
        approved_replay_policy_loss_targets=23_460,
        approved_replay_qualified_episodes=337,
        approved_replay_split_counts={
            "train": 266,
            "validation": 29,
            "test": 42,
        },
        approved_replay_teacher_active_requests=25_058,
        approved_replay_target_floor_shortfall=1_540,
        approved_replay_episode_floor_passed=True,
        approved_replay_target_floor_passed=False,
        bc_engineering_canary_request_ready=False,
        bc_engineering_canary_request_authorized=False,
        bc_engineering_canary_request_sha256=sha(canary_path),
        bc_engineering_canary_optimizer_steps_executed=64,
        bc_engineering_canary_authorization_consumed=True,
        bc_engineering_canary_passed=True,
        bc_engineering_canary_execution_report=str(canary_report_path.relative_to(ROOT)),
        bc_engineering_canary_execution_report_sha256=sha(canary_report_path),
        bc_engineering_canary_execution_review=str(canary_review_path.relative_to(ROOT)),
        bc_engineering_canary_execution_review_sha256=sha(canary_review_path),
        bc_engineering_canary_execution_review_self_hash=canary_review["review_sha256"],
        bc_engineering_canary_production_checkpoint_eligible=False,
        majkel_corpus_expansion_authorization_consumed=True,
        majkel_corpus_expansion_request=str(expansion_path.relative_to(ROOT)),
        majkel_corpus_expansion_request_sha256=sha(expansion_path),
        majkel_corpus_expansion_files_read=269,
        majkel_corpus_expansion_bytes_read=1_030_207_171,
        majkel_corpus_expansion_qualified_files=269,
        majkel_corpus_expansion_rejected_files=0,
        majkel_corpus_expansion_replay_body_outputs=0,
        majkel_corpus_expansion_job=str(job_path.relative_to(ROOT)),
        majkel_corpus_expansion_job_sha256=sha(job_path),
        state="CORPUS_V2_337_EPISODES_23460_TARGETS_BC_CANARY_PASS_PRODUCTION_TRAINING_BLOCKED",
        source_provenance_status="PASS_MAJKEL_271_EPISODES_CORPUS_V2_FROZEN_BC_CANARY_PASS_TARGET_FLOOR_BLOCKED",
        next_stage="resolve_1540_target_shortfall_then_request_production_bc_approval",
        blocking_requirements=[
            "minimum_25000_valid_policy_loss_targets_shortfall_1540",
            "held_out_and_on_policy_competence_evaluation",
            "separate_production_training_and_submission_approvals",
        ],
    )
    work["updated_at_utc"] = CREATED_AT
    write_json(work_path, work)

    project_path = ROOT / "PROJECT_STATUS.md"
    project = project_path.read_text()
    active_start = project.index("## Active Experiments And Jobs")
    blockers_start = project.index("## Open Blockers And Review Boundaries")
    active = """## Active Experiments And Jobs\n\nNo active long-running jobs. DEC-028 consumed both exact approvals. Private Kaggle CPU notebook `ashok205/kptcg-e01-majkel-corpus-review-v1` saved version 2 read exactly 269 named August 3 Majkel replay bodies totaling 1,030,207,171 new bytes, reused the two reviewed probe bodies without rereading, qualified all 269 files, rejected zero files and exported no replay body or agent log. Corpus v2 is frozen at 337 qualified episodes, 1,414,841,670 bytes, 25,058 teacher requests, 1,598 forced recurrent calls and 23,460 policy-loss targets. The episode floor passes, but the 25,000-target production floor remains short by 1,540.\n\nThe exact local-CPU BC engineering canary is also consumed. A forced-only recurrent chunk caused a fail-closed stop after 10 optimizer steps; the scheduler was corrected to skip that zero-loss chunk and exactly 54 additional steps completed, preserving the approved 64-step cumulative cap. Loss and gradients were finite and the step-32 checkpoint restored exactly. The checkpoint is permanently non-promotable and no policy competence is claimed. Production label materialization and training remain unauthorized.\n\n"""
    project = project[:active_start] + active + project[blockers_start:]
    if "### DEC-028 - Corpus v2 and BC canary closeout" not in project:
        marker = "## Immediate Next Actions"
        section = """### DEC-028 - Corpus v2 and BC canary closeout\n\n- Exact Majkel review: 269/269 files qualified, zero rejected, 1,030,207,171 new bytes read, zero replay exports.\n- Corpus v2: 337 episodes and 23,460 valid targets; the 25,000-target production floor is short by 1,540.\n- BC canary: 64 cumulative local CPU AdamW steps, finite loss/gradients, exact step-32 restore, permanently non-promotable.\n- Production training remains blocked pending a separately approved supplemental corpus review and a new exact training approval.\n\n"""
        project = project.replace(marker, section + marker)
    immediate = project.index("## Immediate Next Actions")
    project = project[:immediate] + """## Immediate Next Actions\n\n1. Refresh the latest versioned Majkel replay source and prepare the smallest exact supplemental request expected to add at least 1,540 valid policy-loss targets.\n2. After the 25,000-target floor passes and corpus v3 is independently reviewed, request separate exact approval for production recurrent BC.\n3. Keep additional replay reads, label materialization, optimizer steps, GPU/TPU use, model promotion, final deck freeze, submission, commit and push blocked until their respective approvals.\n"""
    project_path.write_text(project, encoding="utf-8")

    progress_path = ROOT / "PROGRESS_REPORT.md"
    progress = progress_path.read_text()
    note = """\n## 2026-08-04 DEC-028 closeout\n\n- The exact 269-file private Kaggle CPU Majkel review passed: 269 qualified, zero rejected, 1,030,207,171 new bytes read and zero replay-body exports.\n- Corpus v2 now contains 337 episodes and 23,460 policy-loss targets. The episode floor passes; the target floor is short by 1,540.\n- The 64-step local-CPU BC engineering canary passed within the cumulative cap after a fail-closed 10-step scheduler bug and 54-step recovery. Its checkpoint is non-promotable.\n- Production training remains unauthorized and blocked on the supplemental target shortfall plus a separate exact training approval.\n"""
    if "## 2026-08-04 DEC-028 closeout" not in progress:
        progress += note
    progress_path.write_text(progress, encoding="utf-8")

    closeout = {
        "schema_version": 1,
        "record_id": "e01-dec028-closeout-review-v1",
        "source_path": "reports/artifacts/e01-dec028-closeout-review-v1.json",
        "created_at_utc": CREATED_AT,
        "producer": "scripts/finalize_e01_dec028_closeout.py",
        "status": "PASS",
        "reviewed_decision": "DEC-028",
        "qualification": {
            "exact_269_file_review_passed": True,
            "qualified_new_files": 269,
            "rejected_new_files": 0,
            "corpus_v2_episodes": 337,
            "corpus_v2_policy_loss_targets": 23_460,
            "production_target_shortfall": 1_540,
            "bc_canary_cumulative_optimizer_steps": 64,
            "bc_canary_non_promotable": True,
            "production_training_authorized": False,
            "further_replay_reads_authorized": False,
            "submission_authorized": False,
        },
        "inputs": {
            "decision": {"path": str(decision_path.relative_to(ROOT)), "sha256": sha(decision_path)},
            "expansion_request": {"path": str(expansion_path.relative_to(ROOT)), "sha256": sha(expansion_path)},
            "corpus_manifest": {"path": str(corpus_path.relative_to(ROOT)), "sha256": sha(corpus_path), "self_hash": corpus["manifest_sha256"]},
            "corpus_review": {"path": str(corpus_review_path.relative_to(ROOT)), "sha256": sha(corpus_review_path), "self_hash": corpus_review["review_sha256"]},
            "canary_request": {"path": str(canary_path.relative_to(ROOT)), "sha256": sha(canary_path)},
            "canary_execution_review": {"path": str(canary_review_path.relative_to(ROOT)), "sha256": sha(canary_review_path), "self_hash": canary_review["review_sha256"]},
            "job": {"path": str(job_path.relative_to(ROOT)), "sha256": sha(job_path), "self_hash": job["receipt_sha256"]},
        },
        "review_sha256": None,
    }
    closeout["review_sha256"] = self_hash(closeout, "review_sha256")
    closeout_path = ROOT / closeout["source_path"]
    write_json(closeout_path, closeout)

    print(json.dumps({
        "status": "PASS",
        "decision": str(decision_path.relative_to(ROOT)),
        "decision_sha256": sha(decision_path),
        "expansion_consumed_sha256": sha(expansion_path),
        "canary_consumed_sha256": sha(canary_path),
        "job_sha256": sha(job_path),
        "job_self_hash": job["receipt_sha256"],
        "closeout_review_sha256": sha(closeout_path),
        "closeout_review_self_hash": closeout["review_sha256"],
        "corpus_v2_episodes": 337,
        "corpus_v2_policy_loss_targets": 23_460,
        "production_target_shortfall": 1_540,
        "production_training_authorized": False,
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
