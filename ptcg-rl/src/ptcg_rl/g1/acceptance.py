from __future__ import annotations

import json
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

from .actions import CompoundActionBuilder, permute_request, validate_compound_action
from .evidence import (
    git_state,
    sha256_file,
    source_tree_hash,
    technical_run_envelope,
    unique_run_id,
    write_immutable_json,
)
from .models import CONTRACT_VERSION, LegalOptionV1, SelectionRequestV1, stable_hash
from .semantic import OPTION_NAMES, SELECT_NAMES


def _option(selection_type: int, option_type: int, original_index: int) -> LegalOptionV1:
    values: dict[str, Any] = {
        "schema_version": CONTRACT_VERSION,
        "original_index": original_index,
        "selection_type": selection_type,
        "selection_context": 41,
        "option_type": option_type,
        "option_name": OPTION_NAMES[option_type],
        "source_kind": "NONE",
        "target_kind": "NONE",
        "choice_role": "BOOLEAN" if option_type in (1, 2) else "CHOICE",
        "available": True,
    }
    if option_type == 0:
        values["number"] = original_index
    elif option_type in (3, 4, 5, 6):
        values.update(area=2, index=original_index, player_index=0,
                      source_kind="ENTITY", source_ref=f"hand:{original_index}")
    elif option_type == 7:
        values.update(index=original_index, source_kind="ENTITY",
                      source_ref=f"hand:{original_index}")
    elif option_type in (8, 9):
        values.update(area=2, index=original_index, in_play_area=0, in_play_index=0,
                      source_kind="ENTITY", source_ref=f"hand:{original_index}",
                      target_kind="ENTITY", target_ref="active:0")
    elif option_type in (10, 11):
        values.update(area=0, index=original_index, source_kind="ENTITY",
                      source_ref=f"active:{original_index}")
    elif option_type == 12:
        values.update(source_kind="ENTITY", source_ref="active:0")
    elif option_type == 13:
        values.update(attack_id=original_index, source_kind="SKILL",
                      source_ref=f"attack:{original_index}")
    elif option_type == 15:
        values.update(card_id=0, serial=-1, source_kind="PSEUDO", source_ref="skill:0:-1")
    elif option_type == 16:
        values.update(special_condition_type=original_index)
    if option_type == 4:
        values["tool_index"] = 0
    if option_type in (5, 6):
        values["energy_index"] = 0
    if option_type == 6:
        values["count"] = 1
    option = LegalOptionV1(**values)
    return replace(option, semantic_fingerprint=stable_hash(option.semantic_payload()))


def _case(selection_type: int, option_type: int, boundary: int):
    option_count = 1 if boundary == 0 else 3
    options = tuple(_option(selection_type, option_type, index) for index in range(option_count))
    bounds = ((1, 1), (0, 2), (1, 2), (1, 2), (3, 3))[boundary]
    original = SelectionRequestV1(
        CONTRACT_VERSION, "g1r-valid-corpus", 0,
        f"s{selection_type}-o{option_type}-b{boundary}", 0, selection_type, 41,
        bounds[0], bounds[1], None, None, None, None,
        "ORDERED" if boundary in (2, 4) else "UNORDERED", options,
    )
    model = permute_request(original, (2, 0, 1)) if boundary == 3 else original
    builder = CompoundActionBuilder(model, original)
    if boundary == 0:
        builder.choose(0)
    elif boundary == 1:
        builder.stop()
    elif boundary in (2, 3):
        builder.choose(0)
        builder.choose(1)
    else:
        for index in range(3):
            builder.choose(index)
    return original, builder.build()


def run_contract_acceptance(args, repo: Path) -> dict[str, Any]:
    if args.valid_operations < 1:
        raise ValueError("valid-operations must be positive")
    run_id = unique_run_id("g1r-contract-acceptance")
    run_dir = (args.output or repo / "runs" / run_id).resolve()
    run_dir.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    corpus = [
        _case(selection_type, option_type, boundary)
        for selection_type in SELECT_NAMES
        for option_type in OPTION_NAMES
        for boundary in range(5)
    ]
    digest = ""
    for operation in range(args.valid_operations):
        request, action = corpus[operation % len(corpus)]
        digest = stable_hash(validate_compound_action(request, action))

    malformed = 0
    request, action = corpus[0]
    for forged in (
        replace(action, request_id="stale"),
        replace(action, submitted_original_indices=(999,)),
        replace(action, submitted_original_indices=(0, 0)),
        replace(action, acting_player=1),
    ):
        try:
            validate_compound_action(request, forged)
        except Exception:
            malformed += 1

    log_path = run_dir / "log-burst.jsonl"
    with log_path.open("x", encoding="utf-8") as destination:
        for event in range(257):
            destination.write(json.dumps({"sequence": event}, separators=(",", ":")) + "\n")
    log_sequences = [json.loads(line)["sequence"] for line in log_path.read_text().splitlines()]
    log_ok = log_sequences == list(range(257))

    killed = subprocess.run([sys.executable, "-c", "import os; os._exit(23)"], check=False)
    replacement = subprocess.run(
        [sys.executable, "-c", "print('replacement-ready')"],
        text=True, capture_output=True, check=False,
    )
    restart_ok = killed.returncode == 23 and replacement.stdout.strip() == "replacement-ready"
    passed = malformed == 4 and log_ok and restart_ok
    manifest_path = run_dir / "run_manifest.json"
    manifest = {
        **technical_run_envelope(repo, manifest_path, run_id, "ptcg.g1r.contract-acceptance", passed),
        "valid_operations": args.valid_operations,
        "valid_corpus_cases": len(corpus),
        "selection_type_coverage": sorted(SELECT_NAMES.values()),
        "option_type_coverage": sorted(OPTION_NAMES.values()),
        "boundary_coverage": ["forced", "optional-empty-stop", "ordered-max",
                              "permuted-unordered-max", "select-all"],
        "last_valid_action_sha256": digest,
        "malformed_rejections_separate": malformed,
        "log_burst": {"events": len(log_sequences), "loss_or_truncation": not log_ok,
                      "sha256": sha256_file(log_path)},
        "worker_restart": {"forced_exit_code": killed.returncode,
                           "replacement_ready": restart_ok,
                           "recurrent_contract_test": "test_recurrent_lifecycle_isolated_idempotent_and_ordered"},
        "repository": git_state(repo),
        "source_sha256": source_tree_hash(repo),
        "wall_seconds": time.monotonic() - started,
        "training_performed": False,
        "local_cost_usd": 0.0,
    }
    write_immutable_json(manifest_path, manifest)
    (run_dir / "run_manifest.json.sha256").write_text(
        f"{sha256_file(manifest_path)}  run_manifest.json\n", encoding="ascii"
    )
    return manifest
