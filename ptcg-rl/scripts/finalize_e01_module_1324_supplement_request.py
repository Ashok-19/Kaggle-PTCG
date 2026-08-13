from __future__ import annotations

import copy
import csv
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
CREATED_AT = "2026-08-05T07:31:25Z"

OLD_REQUEST = ROOT / "configs/e01_corpus_v2_target_shortfall_supplement_request_v1.json"
PROBE_REQUEST = ROOT / "configs/e01_majkel_module_1324_compatibility_probe_request_v1.json"
PROBE_REVIEW = ROOT / "reports/artifacts/e01-majkel-module-1324-compatibility-probe-review-v1.json"
PROBE_OUTPUT_MANIFEST = ROOT / "reports/artifacts/e01-majkel-module-1324-compatibility-probe-output-manifest-v1.json"
BASE_MANIFEST = ROOT / "reports/artifacts/e01-approved-replay-corpus-manifest-v2.json"
INVENTORY = ROOT / "scratch/agents/chatgpt/e01-source-refresh-20260805/dataset_files.csv"
RUNNER = ROOT / "scripts/e01_corpus_target_supplement_review_v2.py"
SOURCE_RECHECK = ROOT / "reports/artifacts/raw/e01-module-1324-supplement-source-recheck-20260805-v1.json"
DECISION = ROOT / "docs/decisions/DEC-031_E01_MODULE_1324_SUPPLEMENT_REQUEST.md"
REQUEST = ROOT / "configs/e01_corpus_v2_target_shortfall_supplement_request_v2.json"
REVIEW = ROOT / "reports/artifacts/e01-corpus-v2-target-shortfall-supplement-contract-review-v2.json"
DECISIONS = ROOT / "reports/decisions/current.json"
TASKS = ROOT / "reports/tasks/current.json"
GATE = ROOT / "reports/gates/g3b.json"
PROJECT_STATUS = ROOT / "PROJECT_STATUS.md"
PROGRESS = ROOT / "PROGRESS_REPORT.md"

EXPECTED = {
    OLD_REQUEST: "d94c12e424ba26a06a4085c7273faeadd512351828b2b2aa84b85bf014a2f92e",
    PROBE_REQUEST: "dc38df7b76e01682d3e735499aab352e963c9d454423c71756ededee98b69331",
    PROBE_REVIEW: "e956d010552bcab7489852daa8367a8c11eb06138b98dc21486c11b9ae30d4f2",
    PROBE_OUTPUT_MANIFEST: "72f467b09326d488fd860221cae6647b6ceafd8b4b00c2d4f3fa54844e1a89e3",
    BASE_MANIFEST: "ccc247edbc4cac0aba11c6acb26fc5e2a8c75e0a4f005d1441ce6949c0c4997f",
    INVENTORY: "5620e055a25407c47e7744eaa0ffb9ab2a04fe2287b0f6180f54726cf7a00f77",
    RUNNER: "2acdfe06fa0dd6a79c29e6add267d9c3ca75a5577cdf4ace51d157369c08b30f",
}

BASE_EPISODES = 337
BASE_TARGETS = 23_460
TARGET_FLOOR = 25_000
PROBE_TARGETS = 69
EFFECTIVE_START_TARGETS = BASE_TARGETS + PROBE_TARGETS
REMAINING_SHORTFALL = TARGET_FLOOR - EFFECTIVE_START_TARGETS
OLD_FILES = 48
NEW_BODY_FILES = 47
OLD_BYTES = 180_695_173
PROBE_BYTES = 4_882_237
NEW_BODY_BYTES = OLD_BYTES - PROBE_BYTES
ACCEPTED_MODULES = ["1.32.2", "1.32.3", "1.32.4"]


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def pretty_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def sha_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def self_hash(value: Mapping[str, Any], field: str) -> str:
    payload = copy.deepcopy(dict(value))
    payload.pop(field, None)
    return sha_bytes(canonical_bytes(payload))


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(pretty_bytes(value))


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value.rstrip() + "\n", encoding="utf-8")


def require_hashes() -> None:
    for path, expected in EXPECTED.items():
        actual = sha_file(path)
        if actual != expected:
            raise ValueError(f"input hash differs for {path.relative_to(ROOT)}: {actual}")


def load_inventory() -> dict[str, int]:
    values: dict[str, int] = {}
    with INVENTORY.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != ["name", "total_bytes", "creation_date"]:
            raise ValueError("inventory columns differ")
        for row in reader:
            name = str(row["name"])
            if name in values:
                raise ValueError(f"duplicate inventory filename: {name}")
            values[name] = int(row["total_bytes"])
    if len(values) != 4_812 or sum(name.endswith(".json") for name in values) != 4_811:
        raise ValueError("inventory counts differ")
    if sum(values.values()) != 21_457_813_826:
        raise ValueError("inventory bytes differ")
    return values


def replace_line(text: str, prefix: str, replacement: str) -> str:
    pattern = re.compile(rf"(?m)^{re.escape(prefix)}.*$")
    if not pattern.search(text):
        raise ValueError(f"missing markdown line prefix: {prefix}")
    return pattern.sub(replacement, text, count=1)


def replace_or_append_section(text: str, header: str, body: str) -> str:
    section = f"{header}\n\n{body.strip()}\n"
    pattern = re.compile(rf"(?ms)^{re.escape(header)}\n.*?(?=^### |^## |\Z)")
    if pattern.search(text):
        return pattern.sub(section, text, count=1)
    return text.rstrip() + "\n\n" + section


def authorization_block() -> dict[str, bool]:
    return {
        "agent_logs": False,
        "corpus_v3_qualified_only_finalization": False,
        "external_compute_private_kaggle_cpu": False,
        "git_commit": False,
        "git_push": False,
        "gpu": False,
        "label_materialization": False,
        "model_mutation": False,
        "model_promotion": False,
        "optimizer_steps": False,
        "prequalified_probe_record_promotion": False,
        "raw_exports": False,
        "replay_body_exports": False,
        "replay_body_reads_exact_named_files": False,
        "submission": False,
        "tpu": False,
        "training": False,
    }


def requested_authorization() -> dict[str, bool]:
    values = authorization_block()
    values.update(
        {
            "corpus_v3_qualified_only_finalization": True,
            "external_compute_private_kaggle_cpu": True,
            "prequalified_probe_record_promotion": True,
            "replay_body_reads_exact_named_files": True,
        }
    )
    return values


def main() -> int:
    require_hashes()
    old_request = load_json(OLD_REQUEST)
    probe_request = load_json(PROBE_REQUEST)
    probe_review = load_json(PROBE_REVIEW)
    probe_output_manifest = load_json(PROBE_OUTPUT_MANIFEST)
    base_manifest = load_json(BASE_MANIFEST)
    inventory = load_inventory()

    if old_request.get("maximum_files") != OLD_FILES or old_request.get("maximum_declared_bytes") != OLD_BYTES:
        raise ValueError("old supplement request bounds differ")
    old_selected = old_request.get("files")
    if not isinstance(old_selected, list) or len(old_selected) != OLD_FILES:
        raise ValueError("old supplement request file set differs")
    first = old_selected[0]
    if not isinstance(first, Mapping) or int(first.get("episode_id", -1)) != 90_037_133:
        raise ValueError("old request first episode differs")
    if int(first.get("declared_bytes", -1)) != PROBE_BYTES or str(first.get("file_name")) != "90037133.json":
        raise ValueError("old request first file differs")

    if probe_request.get("status") != "READY_UNAUTHORIZED":
        raise ValueError("probe request pre-execution state differs")
    if probe_review.get("status") != "PASS_COMPATIBLE_FOR_FUTURE_EXACT_REQUEST_ONLY":
        raise ValueError("probe review status differs")
    if probe_review.get("review_sha256") != "ba28a9baabd2799934936138386aaeec2e58e666e6f3d486e9b378113b797faa":
        raise ValueError("probe review self hash differs")
    if self_hash(probe_review, "review_sha256") != probe_review["review_sha256"]:
        raise ValueError("probe review self hash does not verify")
    if probe_output_manifest.get("manifest_sha256") != "3521bda8656c2c5a05408f069205b79cf79f372894da4a9a96be163f3c1bf2f5":
        raise ValueError("probe output manifest self hash differs")
    if self_hash(probe_output_manifest, "manifest_sha256") != probe_output_manifest["manifest_sha256"]:
        raise ValueError("probe output manifest self hash does not verify")

    episode = probe_review.get("episode")
    if not isinstance(episode, Mapping):
        raise ValueError("probe episode metadata missing")
    expected_probe = {
        "episode_id": 90_037_133,
        "file_name": "90037133.json",
        "bytes": PROBE_BYTES,
        "sha256": "6cd39f9c21eb5c62abe3b44fcaa69ef8423bb7fcabfc8b14a1693a9d88abbf9e",
        "module_version": "1.32.4",
        "teacher_deck_multiset_sha256": "dc8571d0bc2e546a1f85b938696cfc40a1451c68a4ccc1f695e7c3e1c74f1278",
        "policy_loss_targets": PROBE_TARGETS,
        "candidate_split_if_later_separately_authorized": "train",
        "candidate_split_key_sha256": "7050afb9f461fee156b930c27ae174412db82b4ef469356405ab6def4b2b6b5b",
    }
    for key, expected in expected_probe.items():
        if episode.get(key) != expected:
            raise ValueError(f"probe episode {key} differs")
    if probe_review.get("qualification", {}).get("corpus_promotion") is not False:
        raise ValueError("probe unexpectedly promoted corpus")

    base_corpus = base_manifest.get("qualified_training_corpus")
    if not isinstance(base_corpus, Mapping):
        raise ValueError("base corpus payload missing")
    if base_corpus.get("episodes") != BASE_EPISODES or base_corpus.get("policy_loss_targets") != BASE_TARGETS:
        raise ValueError("base corpus counts differ")
    base_records = base_corpus.get("episode_records")
    if not isinstance(base_records, list) or len(base_records) != BASE_EPISODES:
        raise ValueError("base corpus records differ")
    known_ids = {int(item["episode_id"]) for item in base_records}
    known_hashes = {str(item["sha256"]) for item in base_records}
    if 90_037_133 in known_ids or str(episode["sha256"]) in known_hashes:
        raise ValueError("prequalified probe overlaps corpus v2")

    remaining: list[dict[str, Any]] = []
    for new_order, item_value in enumerate(old_selected[1:], start=1):
        if not isinstance(item_value, Mapping):
            raise ValueError("remaining request file entry differs")
        item = copy.deepcopy(dict(item_value))
        item["prior_dec029_review_order"] = int(item["review_order"])
        item["review_order"] = new_order
        name = str(item["file_name"])
        declared = int(item["declared_bytes"])
        if inventory.get(name) != declared:
            raise ValueError(f"remaining inventory byte mismatch: {name}")
        if int(item["episode_id"]) in known_ids:
            raise ValueError(f"remaining episode overlaps corpus v2: {name}")
        remaining.append(item)
    if len(remaining) != NEW_BODY_FILES:
        raise ValueError("remaining file count differs")
    if sum(int(item["declared_bytes"]) for item in remaining) != NEW_BODY_BYTES:
        raise ValueError("remaining byte total differs")

    body_strata = Counter(str(item["stratum"]) for item in remaining)
    if body_strata != Counter({"seat_0_loss": 11, "seat_0_win": 12, "seat_1_loss": 12, "seat_1_win": 12}):
        raise ValueError(f"remaining strata differ: {body_strata}")

    source_recheck: dict[str, Any] = {
        "schema_version": 1,
        "record_id": "e01-module-1324-supplement-source-recheck-20260805-v1",
        "source_path": "reports/artifacts/raw/e01-module-1324-supplement-source-recheck-20260805-v1.json",
        "created_at_utc": CREATED_AT,
        "producer": "chatgpt-local-agent",
        "status": "PASS_SOURCE_IDENTITY_UNCHANGED",
        "dataset": {
            "reference": "kaggle/pokemon-tcg-ai-battle-episodes-2026-08-04",
            "id": 11_506_836,
            "version": 1,
            "status": "READY",
            "total_bytes": 21_457_813_826,
            "last_updated_utc": "2026-08-05T00:11:02.203Z",
            "inventory_files": 4_812,
            "inventory_json_files": 4_811,
            "inventory_sha256": EXPECTED[INVENTORY],
            "manifest_sha256": "bb190f62f0585dc2a1db2b02752a4d7e6fa6de15a800ed9e769d8daecd8bf9a1",
        },
        "teacher": {
            "team_id": 16_374_395,
            "team_name": "Majkel1337",
            "active_submission_id": 55_186_239,
            "active_submission_public_score_snapshot": 1256.3,
            "public_score_is_dynamic_and_not_authorization_basis": True,
        },
        "probe": {
            "request_sha256": EXPECTED[PROBE_REQUEST],
            "review_sha256": EXPECTED[PROBE_REVIEW],
            "review_self_hash": probe_review["review_sha256"],
            "output_manifest_sha256": EXPECTED[PROBE_OUTPUT_MANIFEST],
            "output_manifest_self_hash": probe_output_manifest["manifest_sha256"],
            "module_1324_compatible": True,
        },
        "authorization": {
            "replay_body_reads": 0,
            "corpus_promotion": False,
            "optimizer_steps": 0,
            "training": False,
            "submission": False,
            "git_commit": False,
            "git_push": False,
        },
        "record_sha256": None,
    }
    source_recheck["record_sha256"] = self_hash(source_recheck, "record_sha256")
    write_json(SOURCE_RECHECK, source_recheck)
    source_recheck_file_sha = sha_file(SOURCE_RECHECK)

    decision_text = f"""# DEC-031 - Renew corpus supplement after module 1.32.4 qualification

- Status: accepted request preparation; execution unauthorized
- Date: 2026-08-05

## Decision

Accept module `1.32.4` for the bounded supplemental corpus review only because the exact one-file DEC-030 compatibility probe passed the existing Mega Lucario deck, current-card construction, terminal/reward and complete lag-aligned compound-action contract.

Prepare one new exact request that may, only after separate hash-bound approval, promote the already-qualified metadata record for `90037133.json` without a third replay-body read and then review at most the remaining 47 frozen DEC-029 files in their preserved relative order. The maximum new replay-body transfer is `{NEW_BODY_BYTES}` bytes. Promotion of the prequalified record contributes `{PROBE_TARGETS}` policy-loss targets, making the effective starting count `{EFFECTIVE_START_TARGETS}` and leaving `{REMAINING_SHORTFALL}` targets to reach the frozen floor of `{TARGET_FLOOR}`.

The request must stop at the first completed qualified file that reaches the floor. It may finalize qualified-only corpus v3 metadata, but it may not export replay bodies or agent logs, generate labels, create or step an optimizer, train, mutate or promote a model, submit, commit or push.

## Next boundary

Execution remains unauthorized until the user explicitly approves `configs/e01_corpus_v2_target_shortfall_supplement_request_v2.json` at its exact SHA-256 and repeats the bounded private-Kaggle-CPU scope. Production recurrent BC remains a separate approval after corpus-v3 evidence is independently accepted.
"""
    write_text(DECISION, decision_text)
    decision_sha = sha_file(DECISION)

    prequalified_record = {
        "episode_id": int(episode["episode_id"]),
        "file_name": str(episode["file_name"]),
        "bytes": int(episode["bytes"]),
        "sha256": str(episode["sha256"]),
        "schema_version": 1,
        "environment_name": "cabt",
        "environment_version": "1.0.0",
        "module_version": "1.32.4",
        "teacher_player_index": int(episode["teacher_player_index"]),
        "teacher_reward": float(episode["teacher_reward"]),
        "teacher_team_id": 16_374_395,
        "teacher_team": "Majkel1337",
        "teacher_submission_id": 55_186_239,
        "teacher_key": "majkel",
        "stratum": "seat_0_loss",
        "teacher_deck_multiset_sha256": str(episode["teacher_deck_multiset_sha256"]),
        "opponent_deck_multiset_sha256": str(episode["opponent_deck_multiset_sha256"]),
        "teacher_active_requests": int(episode["teacher_active_requests"]),
        "forced_teacher_requests": int(episode["forced_teacher_requests"]),
        "meaningful_teacher_decisions": int(episode["policy_loss_targets"]),
        "policy_loss_targets": int(episode["policy_loss_targets"]),
        "stop_targets": int(episode["stop_targets"]),
        "ordered_requests": int(episode["ordered_requests"]),
        "maximum_option_count": int(episode["maximum_option_count"]),
        "maximum_selection_count": int(episode["maximum_selection_count"]),
        "action_alignment": "PASS",
        "current_asset_construction_compatibility": "PASS",
        "source_dataset_path": "90037133.json",
        "source_review": "reports/artifacts/e01-majkel-module-1324-compatibility-probe-review-v1.json",
        "body_reread_for_v3": False,
        "split": str(episode["candidate_split_if_later_separately_authorized"]),
        "split_key_sha256": str(episode["candidate_split_key_sha256"]),
    }

    request: dict[str, Any] = {
        "schema_version": 2,
        "source_path": "configs/e01_corpus_v2_target_shortfall_supplement_request_v2.json",
        "created_at_utc": CREATED_AT,
        "producer": "chatgpt-local-agent",
        "status": "READY_UNAUTHORIZED",
        "authorized": False,
        "authorization_consumed": False,
        "authorization_scope": "UNAUTHORIZED_EXACT_ONE_PREQUALIFIED_METADATA_PROMOTION_PLUS_MAX_47_FILE_PRIVATE_KAGGLE_CPU_BODY_REVIEW_AND_QUALIFIED_CORPUS_V3_FINALIZATION_ONLY",
        "authorization": authorization_block(),
        "requested_authorization": requested_authorization(),
        "decision_id": "DEC-031",
        "decision_path": "docs/decisions/DEC-031_E01_MODULE_1324_SUPPLEMENT_REQUEST.md",
        "decision_sha256": decision_sha,
        "execution_support": {
            "runner_path": "scripts/e01_corpus_target_supplement_review_v2.py",
            "runner_sha256": EXPECTED[RUNNER],
            "approved_request_sha256_argument_required": True,
        },
        "compute": {
            "platform": "private-kaggle-cpu",
            "notebook_slug": "kptcg-e01-corpus-target-supplement-v2",
            "cpu_threads_maximum": 4,
            "wall_seconds_maximum": 10_800,
            "internet": False,
            "gpu": False,
            "tpu": False,
        },
        "corpus_policy": {
            "base_manifest": "reports/artifacts/e01-approved-replay-corpus-manifest-v2.json",
            "base_manifest_sha256": EXPECTED[BASE_MANIFEST],
            "base_qualified_episodes": BASE_EPISODES,
            "base_policy_loss_targets": BASE_TARGETS,
            "prequalified_probe_records": 1,
            "prequalified_probe_policy_loss_targets": PROBE_TARGETS,
            "effective_starting_qualified_episodes_if_approved": BASE_EPISODES + 1,
            "effective_starting_policy_loss_targets_if_approved": EFFECTIVE_START_TARGETS,
            "remaining_target_shortfall_after_prequalified_promotion": REMAINING_SHORTFALL,
            "minimum_policy_loss_targets": TARGET_FLOOR,
            "stop_review_when_cumulative_qualified_targets_reach_floor": True,
            "corpus_v3_final_only_after_approved_promotion_and_body_review": True,
            "episode_level_split_only": True,
            "split_seed": 20_260_804,
            "split_algorithm": "SHA256(seed|module_version|stratum|episode_id), deterministic 80/10/10 within module-by-stratum groups",
            "forced_calls": "advance recurrence but contribute zero policy loss",
            "target_count_projection_is_guarantee": False,
        },
        "source": {
            "dataset_reference": "kaggle/pokemon-tcg-ai-battle-episodes-2026-08-04",
            "dataset_id": 11_506_836,
            "dataset_version": 1,
            "dataset_status": "READY",
            "dataset_info_total_bytes": 21_457_813_826,
            "dataset_last_updated_utc": "2026-08-05T00:11:02.203Z",
            "dataset_inventory_files": 4_812,
            "dataset_inventory_json_files": 4_811,
            "dataset_inventory_total_bytes": 21_457_813_826,
            "dataset_inventory_sha256": EXPECTED[INVENTORY],
            "manifest_sha256": "bb190f62f0585dc2a1db2b02752a4d7e6fa6de15a800ed9e769d8daecd8bf9a1",
            "source_recheck": "reports/artifacts/raw/e01-module-1324-supplement-source-recheck-20260805-v1.json",
            "source_recheck_sha256": source_recheck_file_sha,
            "source_recheck_self_hash": source_recheck["record_sha256"],
        },
        "teacher": {
            "team_id": 16_374_395,
            "team_name": "Majkel1337",
            "submission_id": 55_186_239,
            "deck_multiset_sha256": "dc8571d0bc2e546a1f85b938696cfc40a1451c68a4ccc1f695e7c3e1c74f1278",
            "accepted_module_versions": ACCEPTED_MODULES,
        },
        "prequalified_probe": {
            "request_path": "configs/e01_majkel_module_1324_compatibility_probe_request_v1.json",
            "request_sha256": EXPECTED[PROBE_REQUEST],
            "review_path": "reports/artifacts/e01-majkel-module-1324-compatibility-probe-review-v1.json",
            "review_sha256": EXPECTED[PROBE_REVIEW],
            "review_self_hash": probe_review["review_sha256"],
            "output_manifest_path": "reports/artifacts/e01-majkel-module-1324-compatibility-probe-output-manifest-v1.json",
            "output_manifest_sha256": EXPECTED[PROBE_OUTPUT_MANIFEST],
            "output_manifest_self_hash": probe_output_manifest["manifest_sha256"],
            "body_reread_authorized": False,
            "promotion_requires_this_new_request_approval": True,
            "record": prequalified_record,
        },
        "files": remaining,
        "maximum_files": NEW_BODY_FILES,
        "maximum_declared_bytes": NEW_BODY_BYTES,
        "maximum_total_corpus_additions": OLD_FILES,
        "selection": {
            "selection_origin": "DEC-029 exact balanced 48-file request with the qualified first file removed from body-read scope",
            "preserved_relative_order": True,
            "body_read_selected_by_stratum": dict(sorted(body_strata.items())),
            "combined_with_prequalified_record_by_stratum": {
                "seat_0_loss": 12,
                "seat_0_win": 12,
                "seat_1_loss": 12,
                "seat_1_win": 12,
            },
            "excluded_corpus_v2_episode_ids": True,
        },
        "review_contract": {
            "accepted_module_versions": ACCEPTED_MODULES,
            "prequalified_record_reuse": "exact probe metadata only; no third replay-body read",
            "review_order": "remaining DEC-029 order after removing 90037133.json",
            "stop_after_target_floor": True,
            "body_checks": [
                "schema and environment identity",
                "exact Mega Lucario deck multiset",
                "teacher player and terminal reward identity",
                "current-card construction compatibility",
                "lag-aligned full-compound action validity including STOP",
                "forced-singleton recurrence-only classification",
                "duplicate episode and split leakage exclusion",
            ],
        },
        "output_contract": {
            "metadata_files": [
                "e01-corpus-target-supplement-review-v2.json",
                "e01-approved-replay-corpus-manifest-v3.json",
                "e01-approved-replay-corpus-review-v3.json",
                "e01-corpus-target-supplement-output-manifest-v2.json",
            ],
            "raw_replay_body_outputs": 0,
            "agent_log_outputs": 0,
            "training_label_outputs": 0,
        },
        "fail_closed_if": [
            "request hash, source recheck, dataset ID, version, inventory hash or manifest hash differs",
            "teacher team or active submission identity changes",
            "probe request, probe review, probe self hash, output manifest or reconstructed prequalified record differs",
            "any of the 47 selected filenames, declared bytes or preserved relative order differs",
            "any selected episode is already present in corpus v2 or duplicates the prequalified probe",
            "any body module is outside 1.32.2, 1.32.3 or 1.32.4",
            "body-level deck, action, terminal, reward, duplicate or split review fails",
            "the target floor is not reached within the exact 47-file and 175812936-byte cap",
            "any raw export, agent log, label, optimizer, training, accelerator, model mutation, promotion, submission, commit or push is attempted",
        ],
    }
    write_json(REQUEST, request)
    request_sha = sha_file(REQUEST)

    review: dict[str, Any] = {
        "schema_version": 2,
        "record_id": "e01-corpus-v2-target-shortfall-supplement-contract-review-v2",
        "source_path": "reports/artifacts/e01-corpus-v2-target-shortfall-supplement-contract-review-v2.json",
        "created_at_utc": CREATED_AT,
        "producer": "chatgpt-local-agent",
        "status": "PASS_READY_UNAUTHORIZED",
        "decision": "ACCEPT_PREQUALIFIED_90037133_METADATA_PROMOTION_PLUS_EXACT_REMAINING_47_FILE_REQUEST_READY_UNAUTHORIZED",
        "reviewed_decision": "DEC-031",
        "inputs": {
            "decision": {"path": str(DECISION.relative_to(ROOT)), "sha256": decision_sha},
            "request": {"path": str(REQUEST.relative_to(ROOT)), "sha256": request_sha},
            "runner": {"path": str(RUNNER.relative_to(ROOT)), "sha256": EXPECTED[RUNNER]},
            "old_consumed_request": {"path": str(OLD_REQUEST.relative_to(ROOT)), "sha256": EXPECTED[OLD_REQUEST]},
            "base_manifest": {"path": str(BASE_MANIFEST.relative_to(ROOT)), "sha256": EXPECTED[BASE_MANIFEST]},
            "probe_review": {
                "path": str(PROBE_REVIEW.relative_to(ROOT)),
                "sha256": EXPECTED[PROBE_REVIEW],
                "self_hash": probe_review["review_sha256"],
            },
            "source_recheck": {
                "path": str(SOURCE_RECHECK.relative_to(ROOT)),
                "sha256": source_recheck_file_sha,
                "self_hash": source_recheck["record_sha256"],
            },
        },
        "qualification": {
            "accepted_module_versions": ACCEPTED_MODULES,
            "prequalified_metadata_records": 1,
            "prequalified_replay_body_rereads": 0,
            "prequalified_policy_loss_targets": PROBE_TARGETS,
            "effective_starting_policy_loss_targets": EFFECTIVE_START_TARGETS,
            "remaining_shortfall": REMAINING_SHORTFALL,
            "exact_body_read_files": NEW_BODY_FILES,
            "exact_body_read_bytes": NEW_BODY_BYTES,
            "combined_balanced_strata": True,
            "remaining_files_present_in_frozen_inventory": True,
            "remaining_file_bytes_match_frozen_inventory": True,
            "replay_bodies_read_during_preparation": 0,
            "corpus_promotion_during_preparation": False,
            "optimizer_steps": 0,
            "training": False,
            "model_mutation": False,
            "submission": False,
        },
        "authorization": authorization_block(),
        "review_sha256": None,
    }
    review["review_sha256"] = self_hash(review, "review_sha256")
    write_json(REVIEW, review)
    review_file_sha = sha_file(REVIEW)

    decisions = load_json(DECISIONS)
    if not isinstance(decisions, list):
        raise ValueError("decision sidecar is not a list")
    decision_record = {
        "schema_version": 1,
        "record_id": "decision-dec-031",
        "source_path": str(DECISION.relative_to(ROOT)),
        "created_at_utc": CREATED_AT,
        "producer": "decision-sidecar",
        "decision_id": "DEC-031",
        "title": "Renew corpus supplement after module 1.32.4 qualification",
        "status": "ACCEPTED_REQUEST_READY_UNAUTHORIZED",
        "decision": "Reuse the exact compatible 90037133 probe metadata without rereading its body, then permit at most the remaining 47 frozen files only after separate exact approval.",
        "rationale": "The one-file module-1.32.4 probe passed all existing semantic checks and contributes 69 targets, while the remaining DEC-029 order and source inventory are unchanged.",
        "request_path": str(REQUEST.relative_to(ROOT)),
        "request_sha256": request_sha,
        "review_path": str(REVIEW.relative_to(ROOT)),
        "review_sha256": review_file_sha,
        "review_self_hash": review["review_sha256"],
        "revisit_trigger": "The exact v2 request is approved or rejected, or any source, teacher, probe, filename, byte count or hash identity changes.",
    }
    decisions = [item for item in decisions if not (isinstance(item, Mapping) and item.get("decision_id") == "DEC-031")]
    decisions.append(decision_record)
    write_json(DECISIONS, decisions)

    tasks = load_json(TASKS)
    if not isinstance(tasks, list):
        raise ValueError("task sidecar is not a list")
    probe_task = {
        "schema_version": 1,
        "record_id": "task-e01-module-1324-compatibility-probe-030",
        "source_path": "reports/tasks/current.json",
        "created_at_utc": "2026-08-05T05:39:27Z",
        "updated_at_utc": CREATED_AT,
        "completed_at_utc": "2026-08-05T06:21:41.583574Z",
        "producer": "chatgpt-local-agent",
        "task_id": "T-E01-MODULE-1324-COMPATIBILITY-PROBE-030",
        "title": "Qualify module 1.32.4 against the existing replay contract",
        "phase": "E01-A",
        "priority": 16,
        "status": "SUCCEEDED",
        "depends_on": ["DEC-030", "T-E01-CORPUS-TARGET-SHORTFALL-028"],
        "done_when": "The exact one-file private CPU probe checks module 1.32.4 against deck, construction, terminal, reward and full action alignment and stops without corpus promotion.",
        "request": str(PROBE_REQUEST.relative_to(ROOT)),
        "request_sha256": EXPECTED[PROBE_REQUEST],
        "review": str(PROBE_REVIEW.relative_to(ROOT)),
        "review_sha256": EXPECTED[PROBE_REVIEW],
        "review_self_hash": probe_review["review_sha256"],
        "output_manifest": str(PROBE_OUTPUT_MANIFEST.relative_to(ROOT)),
        "output_manifest_sha256": EXPECTED[PROBE_OUTPUT_MANIFEST],
        "module_version": "1.32.4",
        "episode_id": 90_037_133,
        "replay_bodies_read": 1,
        "replay_body_bytes_read": PROBE_BYTES,
        "policy_loss_targets_observed": PROBE_TARGETS,
        "corpus_promotion": False,
        "optimizer_steps": 0,
        "training_authorized": False,
        "submission_authorized": False,
    }
    tasks = [item for item in tasks if not (isinstance(item, Mapping) and item.get("task_id") == probe_task["task_id"])]
    tasks.append(probe_task)
    target_task = next((item for item in tasks if isinstance(item, dict) and item.get("task_id") == "T-E01-CORPUS-TARGET-SHORTFALL-028"), None)
    if target_task is None:
        raise ValueError("target-shortfall task missing")
    target_task.update(
        {
            "updated_at_utc": CREATED_AT,
            "status": "BLOCKED_APPROVAL",
            "blocker": "Module 1.32.4 compatibility passed. The renewed exact request can promote one prequalified metadata record and read at most the remaining 47 frozen bodies, but it is READY_UNAUTHORIZED.",
            "decision_id": "DEC-031",
            "decision_path": str(DECISION.relative_to(ROOT)),
            "decision_sha256": decision_sha,
            "request": str(REQUEST.relative_to(ROOT)),
            "request_sha256": request_sha,
            "execution_runner": str(RUNNER.relative_to(ROOT)),
            "execution_runner_sha256": EXPECTED[RUNNER],
            "request_ready": True,
            "review": str(REVIEW.relative_to(ROOT)),
            "review_sha256": review_file_sha,
            "review_self_hash": review["review_sha256"],
            "expected_module_versions": ACCEPTED_MODULES,
            "compatibility_probe_request_authorized": False,
            "compatibility_probe_request_ready": False,
            "compatibility_probe_status": "SUCCEEDED",
            "compatibility_probe_review": str(PROBE_REVIEW.relative_to(ROOT)),
            "compatibility_probe_review_sha256": EXPECTED[PROBE_REVIEW],
            "compatibility_probe_review_self_hash": probe_review["review_sha256"],
            "prequalified_probe_records": 1,
            "prequalified_probe_episode_id": 90_037_133,
            "prequalified_probe_policy_loss_targets": PROBE_TARGETS,
            "prequalified_probe_body_reread_planned": False,
            "effective_starting_policy_loss_targets_if_approved": EFFECTIVE_START_TARGETS,
            "target_floor_shortfall_after_prequalified_promotion": REMAINING_SHORTFALL,
            "exact_selected_files": NEW_BODY_FILES,
            "exact_selected_bytes": NEW_BODY_BYTES,
            "maximum_planned_files": NEW_BODY_FILES,
            "replay_transfer_authorized": False,
            "optimizer_steps_authorized": False,
            "training_authorized": False,
            "submission_authorized": False,
        }
    )
    write_json(TASKS, tasks)

    gate = load_json(GATE)
    if not isinstance(gate, dict):
        raise ValueError("gate sidecar is not an object")
    gate["updated_at_utc"] = CREATED_AT
    gate["decision"] = "DEC-031_MODULE_1324_SUPPLEMENT_REQUEST_READY_UNAUTHORIZED"
    gate["authorization"] = "NO_REPLAY_READ_CORPUS_PROMOTION_OR_TRAINING_AUTHORIZED_RENEWED_47_FILE_REQUEST_READY_UNAUTHORIZED"
    gate["approved_next_action"] = (
        f"Request separate exact approval for configs/e01_corpus_v2_target_shortfall_supplement_request_v2.json at SHA-256 {request_sha}. "
        f"If approved, promote the exact prequalified 90037133 metadata record without rereading its body, read only the remaining 47 named bodies up to {NEW_BODY_BYTES} bytes on private Kaggle CPU, stop at 25000 targets, finalize corpus v3 metadata only, and do not train."
    )
    gate["blockers"] = [
        "Corpus v2 remains at 337 episodes and 23460 policy-loss targets until a new request is exactly approved.",
        "The compatible 90037133 metadata record contributes 69 targets only if its promotion is explicitly approved under DEC-031.",
        f"The renewed exact remaining-47-file request is READY_UNAUTHORIZED; the post-promotion shortfall is {REMAINING_SHORTFALL} targets and all training remains blocked.",
    ]
    checks = gate.get("technical_checks")
    if not isinstance(checks, list):
        raise ValueError("gate technical checks missing")
    found_030 = False
    found_031 = False
    for item in checks:
        if not isinstance(item, dict):
            continue
        if item.get("name") == "DEC-030 module 1.32.4 compatibility gate":
            item["evidence"] = str(PROBE_REVIEW.relative_to(ROOT))
            item["status"] = "PASS"
            found_030 = True
        if item.get("name") == "DEC-031 renewed module-1.32.4-aware supplemental request":
            item["evidence"] = str(REVIEW.relative_to(ROOT))
            item["status"] = "PASS"
            found_031 = True
    if not found_030:
        checks.append({"name": "DEC-030 module 1.32.4 compatibility gate", "evidence": str(PROBE_REVIEW.relative_to(ROOT)), "status": "PASS"})
    if not found_031:
        checks.append({"name": "DEC-031 renewed module-1.32.4-aware supplemental request", "evidence": str(REVIEW.relative_to(ROOT)), "status": "PASS"})
    write_json(GATE, gate)

    project = PROJECT_STATUS.read_text(encoding="utf-8")
    project = replace_line(project, "Last updated UTC:", "Last updated UTC: 2026-08-05")
    project = replace_line(project, "Last completed milestone:", "Last completed milestone: DEC-031 froze a renewed module-1.32.4-aware supplemental request after the exact compatibility probe passed")
    project = replace_line(project, "Current gate:", f"Current gate: exact request `{REQUEST.relative_to(ROOT)}` at SHA-256 `{request_sha}` is READY_UNAUTHORIZED; no corpus promotion, replay read or training is authorized")
    project = replace_line(project, "Gold-path status:", f"Gold-path status: MODULE 1.32.4 COMPATIBILITY PASS / PREQUALIFIED 69 TARGETS NOT YET PROMOTED / REMAINING 47-FILE CAP {NEW_BODY_BYTES} BYTES / EFFECTIVE SHORTFALL {REMAINING_SHORTFALL} IF APPROVED / TRAINING BLOCKED")
    project = replace_or_append_section(
        project,
        "### DEC-031 - Renew supplement after module 1.32.4 qualification",
        f"""- Exact compatibility evidence: `{PROBE_REVIEW.relative_to(ROOT)}` SHA-256 `{EXPECTED[PROBE_REVIEW]}`, self-hash `{probe_review['review_sha256']}`.
- The prequalified `90037133.json` record contains `{PROBE_TARGETS}` policy-loss targets and may be promoted only under the new exact approval, without rereading its body.
- Renewed request: `{REQUEST.relative_to(ROOT)}` SHA-256 `{request_sha}`; exact execution runner `{RUNNER.relative_to(ROOT)}` SHA-256 `{EXPECTED[RUNNER]}`; contract review SHA-256 `{review_file_sha}`, self-hash `{review['review_sha256']}`.
- New body-read scope is exactly `{NEW_BODY_FILES}` remaining files and at most `{NEW_BODY_BYTES}` bytes. Module versions `1.32.2`, `1.32.3`, and `1.32.4` are accepted for this bounded review.
- No replay body was read and no corpus record was promoted during request preparation. Labels, optimizer steps, training, accelerators, model mutation, submission, commit and push remain unauthorized.""",
    )
    write_text(PROJECT_STATUS, project)

    progress = PROGRESS.read_text(encoding="utf-8")
    progress = replace_line(progress, "Current gate:", f"Current gate: **DEC-031 renewed exact 47-file supplement request plus one prequalified metadata promotion is READY_UNAUTHORIZED at `{request_sha}`**")
    progress = replace_line(progress, "Gold-path status:", f"Gold-path status: **MODULE 1.32.4 COMPATIBILITY PASS; 69 PREQUALIFIED TARGETS AWAIT APPROVAL; REMAINING BODY CAP {NEW_BODY_FILES} FILES / {NEW_BODY_BYTES} BYTES; EFFECTIVE SHORTFALL {REMAINING_SHORTFALL}; TRAINING BLOCKED**")
    progress = replace_or_append_section(
        progress,
        "### DEC-031 - Renewed supplement request prepared",
        f"""- Passed module-1.32.4 probe metadata is bound at SHA-256 `{EXPECTED[PROBE_REVIEW]}` and is not yet part of corpus v2 or v3.
- New request `{REQUEST.relative_to(ROOT)}` has SHA-256 `{request_sha}`, binds runner `{RUNNER.relative_to(ROOT)}` at SHA-256 `{EXPECTED[RUNNER]}`, and may reuse the exact probe record without a third body read.
- The only prospective new transfer is the remaining `{NEW_BODY_FILES}` frozen files, capped at `{NEW_BODY_BYTES}` bytes, stopping at the first qualified file that raises the corpus to at least `{TARGET_FLOOR}` targets.
- Preparation performed zero replay-body reads, zero corpus promotion, zero labels, zero optimizer steps, zero training, zero accelerator use, zero submission, and zero Git commit/push.""",
    )
    write_text(PROGRESS, progress)

    summary = {
        "status": "PASS_RENEWED_REQUEST_READY_UNAUTHORIZED",
        "decision_sha256": decision_sha,
        "request_sha256": request_sha,
        "review_sha256": review_file_sha,
        "runner_sha256": EXPECTED[RUNNER],
        "review_self_hash": review["review_sha256"],
        "source_recheck_sha256": source_recheck_file_sha,
        "source_recheck_self_hash": source_recheck["record_sha256"],
        "prequalified_episode_id": 90_037_133,
        "prequalified_policy_loss_targets": PROBE_TARGETS,
        "effective_starting_policy_loss_targets_if_approved": EFFECTIVE_START_TARGETS,
        "remaining_shortfall": REMAINING_SHORTFALL,
        "remaining_body_files": NEW_BODY_FILES,
        "remaining_body_bytes": NEW_BODY_BYTES,
        "replay_bodies_read_during_preparation": 0,
        "corpus_promotion_during_preparation": False,
        "optimizer_steps": 0,
        "training": False,
        "submission": False,
        "git_commit": False,
        "git_push": False,
        "sidecar_sha256": {
            "decisions": sha_file(DECISIONS),
            "tasks": sha_file(TASKS),
            "gate": sha_file(GATE),
            "project_status": sha_file(PROJECT_STATUS),
            "progress_report": sha_file(PROGRESS),
        },
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
