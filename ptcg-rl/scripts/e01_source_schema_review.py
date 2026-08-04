from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
DRY_RUN = ROOT / "reports/artifacts/e01a-public-replay-dry-run-v1.json"
RAW = ROOT / "reports/artifacts/raw/e01-public-source-schema-reconciliation-raw-v1.json"
DECISION = ROOT / "docs/decisions/DEC-014_E01_SOURCE_SCHEMA_RECONCILED.md"
REQUEST = ROOT / "configs/e01_provenance_probe_request_v2.json"
OUTPUT = ROOT / "reports/artifacts/e01-source-schema-reconciliation-v1.json"


class E01SourceSchemaReviewError(ValueError):
    pass


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise E01SourceSchemaReviewError(f"JSON root must be an object: {path}")
    return value


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def self_hash(value: Mapping[str, Any], field: str) -> str:
    payload = dict(value)
    payload.pop(field, None)
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def normalize_time(value: str) -> str:
    return value.removesuffix("Z").rstrip("0").rstrip(".")


def review() -> dict[str, Any]:
    dry_run = load_json(DRY_RUN)
    raw = load_json(RAW)
    request = load_json(REQUEST)
    decision_text = DECISION.read_text(encoding="utf-8")

    if dry_run.get("status") != "DRY_RUN_PASS_TRANSFER_BLOCKED":
        raise E01SourceSchemaReviewError("accepted E01-A dry run differs")
    if dry_run.get("episode_json_transferred") != 0:
        raise E01SourceSchemaReviewError("dry run transferred replay bodies")
    boundary = raw.get("collection_boundary")
    if not isinstance(boundary, Mapping) or any(boundary.values()):
        raise E01SourceSchemaReviewError("raw reconciliation crossed metadata boundary")
    client = raw.get("client")
    if not isinstance(client, Mapping) or (
        client.get("kaggle_cli_version") != "2.2.4"
        or client.get("source_commit")
        != "f0afa32699d28c97f82691728ada3ed8c16c5abf"
    ):
        raise E01SourceSchemaReviewError("raw reconciliation client differs")
    score_status = raw.get("score_field_status")
    if not isinstance(score_status, Mapping) or any(score_status.values()):
        raise E01SourceSchemaReviewError("rating field is incorrectly claimed")

    accepted_items = dry_run.get("selected_items")
    selected = raw.get("selected")
    if not isinstance(accepted_items, list) or len(accepted_items) != 8:
        raise E01SourceSchemaReviewError("accepted candidate set differs")
    if not isinstance(selected, list) or len(selected) != 8:
        raise E01SourceSchemaReviewError("reconciled candidate set differs")
    accepted = {int(item["episode_id"]): item for item in accepted_items}
    observed = {int(item["episode_id"]): item for item in selected}
    if set(accepted) != set(observed):
        raise E01SourceSchemaReviewError("candidate episode identities differ")

    reconciled: list[dict[str, Any]] = []
    for episode_id in sorted(accepted):
        old = accepted[episode_id]
        new = observed[episode_id]
        file_meta = new.get("file_metadata")
        episode_meta = new.get("episode_metadata")
        if not isinstance(file_meta, Mapping) or not isinstance(episode_meta, Mapping):
            raise E01SourceSchemaReviewError("reconciled item is incomplete")
        agents = episode_meta.get("agents")
        if not isinstance(agents, list) or len(agents) != 2:
            raise E01SourceSchemaReviewError("episode agent identity is incomplete")
        if (
            file_meta.get("file_name") != old["remote_filename"]
            or file_meta.get("total_bytes") != old["declared_bytes"]
            or episode_meta.get("id") != episode_id
            or normalize_time(str(episode_meta.get("createTime")))
            != normalize_time(str(old["create_time"]))
            or episode_meta.get("state") != "COMPLETED"
            or episode_meta.get("type") != "EPISODE_TYPE_PUBLIC"
        ):
            raise E01SourceSchemaReviewError(
                f"candidate metadata does not reproduce: {episode_id}"
            )
        reconciled.append(
            {
                "episode_id": episode_id,
                "file_name": file_meta["file_name"],
                "total_bytes": file_meta["total_bytes"],
                "create_time": episode_meta["createTime"],
                "end_time": episode_meta["endTime"],
                "agents": agents,
            }
        )

    smallest = min(reconciled, key=lambda item: (item["total_bytes"], item["episode_id"]))
    if smallest["episode_id"] != 87703034 or smallest["total_bytes"] != 3_641_302:
        raise E01SourceSchemaReviewError("smallest accepted candidate differs")

    if (
        request.get("record_id") != "e01-provenance-probe-request-v2"
        or request.get("decision_id") != "DEC-014"
        or request.get("decision_sha256") != sha256_file(DECISION)
        or request.get("dry_run_sha256") != sha256_file(DRY_RUN)
        or request.get("raw_reconciliation_sha256") != sha256_file(RAW)
        or request.get("status") != "READY_UNAUTHORIZED"
        or request.get("request_ready") is not True
        or request.get("authorized") is not False
        or request.get("maximum_files") != 1
        or request.get("maximum_total_bytes") != 3_641_302
    ):
        raise E01SourceSchemaReviewError("exact provenance request differs")
    request_episode = request.get("episode")
    if not isinstance(request_episode, Mapping) or (
        request_episode.get("episode_id") != smallest["episode_id"]
        or request_episode.get("file_name") != smallest["file_name"]
        or request_episode.get("declared_bytes") != smallest["total_bytes"]
        or request_episode.get("create_time") != smallest["create_time"]
        or request_episode.get("end_time") != smallest["end_time"]
    ):
        raise E01SourceSchemaReviewError("request episode binding differs")
    if request.get("selection_basis", {}).get("accepted_rank_scores_used_for_authorization") is not False:
        raise E01SourceSchemaReviewError("missing rating field influences authorization")
    inspection = request.get("inspection_boundary")
    if not isinstance(inspection, Mapping) or (
        inspection.get("replay_files") != 1
        or inspection.get("agent_log_downloads") != 0
        or inspection.get("additional_replay_downloads") != 0
        or inspection.get("raw_step_exports") != 0
        or inspection.get("action_sequence_exports") != 0
        or inspection.get("observation_exports") != 0
        or inspection.get("training_label_exports") != 0
        or inspection.get("optimizer_steps") != 0
        or inspection.get("external_compute") is not False
        or inspection.get("training") is not False
        or inspection.get("submission") is not False
    ):
        raise E01SourceSchemaReviewError("request inspection boundary differs")
    output_directory = ROOT / str(request.get("output_directory", ""))
    if output_directory.exists():
        raise E01SourceSchemaReviewError("provenance output directory already exists")
    for required in (
        "Status: Accepted",
        "select the smallest member",
        "does **not** authorize the file transfer",
        "Benarg",
        "junlee789",
    ):
        if required not in decision_text:
            raise E01SourceSchemaReviewError(f"DEC-014 missing text: {required}")

    report: dict[str, Any] = {
        "schema_version": 1,
        "record_id": "e01-source-schema-reconciliation-v1",
        "created_at_utc": "2026-07-24T15:30:17Z",
        "source_path": "reports/artifacts/e01-source-schema-reconciliation-v1.json",
        "producer": "scripts/e01_source_schema_review.py",
        "status": "PASS",
        "decision": "ACCEPT_PROVENANCE_ADAPTER_AND_ONE_FILE_REQUEST",
        "reviewed_decision": "DEC-014",
        "inputs": {
            "dry_run": {"path": DRY_RUN.relative_to(ROOT).as_posix(), "sha256": sha256_file(DRY_RUN)},
            "raw_reconciliation": {"path": RAW.relative_to(ROOT).as_posix(), "sha256": sha256_file(RAW)},
            "decision": {"path": DECISION.relative_to(ROOT).as_posix(), "sha256": sha256_file(DECISION)},
            "request": {"path": REQUEST.relative_to(ROOT).as_posix(), "sha256": sha256_file(REQUEST)},
        },
        "adapter": {
            "episode_identity_reproduced": True,
            "timestamp_reproduced": True,
            "file_byte_count_reproduced": True,
            "team_identity_reproduced": True,
            "submission_identity_reproduced": True,
            "rating_field_reproduced": False,
            "rating_field_used_for_probe": False,
            "candidate_set_reranked": False,
        },
        "selected_candidates": reconciled,
        "probe": {
            "episode_id": 87703034,
            "file_name": "87703034.json",
            "declared_bytes": 3_641_302,
            "smallest_accepted_candidate": True,
            "request_ready": True,
            "request_authorized": False,
            "output_directory_exists": False,
            "files_authorized": 1,
            "agent_logs_authorized": False,
            "additional_replays_authorized": False,
            "training_authorized": False,
            "external_compute_authorized": False,
        },
        "qualification": {
            "source_schema_reconciled_for_probe": True,
            "teacher_strength_qualified": False,
            "deck_qualified": False,
            "policy_consistency_qualified": False,
            "e01_screening_gate_passed": False,
            "replay_transfer_authorized": False,
        },
        "next_action": "REQUEST_EXPLICIT_APPROVAL_FOR_EXACT_ONE_FILE_PROVENANCE_PROBE",
        "cost_usd": 0.0,
    }
    report["review_sha256"] = self_hash(report, "review_sha256")
    atomic_json(OUTPUT, report)
    return report


def main() -> int:
    print(json.dumps(review(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
