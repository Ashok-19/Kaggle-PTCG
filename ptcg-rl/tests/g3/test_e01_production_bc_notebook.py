from __future__ import annotations

import importlib.util
import json
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WRAPPER = ROOT / "scripts/kaggle/e01_production_recurrent_bc_notebook_v1.py"


def load_module():
    spec = importlib.util.spec_from_file_location("e01_notebook", WRAPPER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_embedded_contract_counts_and_hashes() -> None:
    module = load_module()
    assert module.sha256_bytes(module.REQUEST_BYTES) == module.TRAINING_REQUEST_SHA256
    assert module.sha256_bytes(module.VERIFIER_BYTES) == module.VERIFIER_SHA256
    assert len(module.SOURCE_BUNDLE_RECORDS) == 79
    assert sum(int(item["bytes"]) for item in module.SOURCE_BUNDLE_RECORDS) == 7_645_589
    assert len(module.SELECTED_REPLAY_RECORDS) == 316
    assert sum(int(item["bytes"]) for item in module.SELECTED_REPLAY_RECORDS) == 1_327_994_902


def test_canonical_inventory_hash_is_order_independent() -> None:
    module = load_module()
    records = [{"name": "b", "bytes": 2}, {"name": "a", "bytes": 1}]
    assert module.canonical_inventory_hash(records) == module.canonical_inventory_hash(list(reversed(records)))


def test_approval_rejects_expanded_scope() -> None:
    module = load_module()
    receipt = {
        "kind": "E01_PRODUCTION_RECURRENT_BC_APPROVAL_V1",
        "approved_by": "user",
        "request_sha256": module.TRAINING_REQUEST_SHA256,
        "runner_sha256": module.RUNNER_SHA256,
        "wrapper_sha256": "a" * 64,
        "notebook_request_sha256": "b" * 64,
        "authorization": {
            "notebook_create": True,
            "notebook_save_and_run": True,
            "replay_body_read": True,
            "optimizer_steps": True,
            "training": True,
            "private_kaggle_cpu": True,
            "notebook_output_download": True,
            "agent_logs": False,
            "gpu": False,
            "tpu": False,
            "internet": False,
            "test_replay_read": False,
            "label_materialization": False,
            "model_promotion": False,
            "submission": True,
            "git_commit": False,
            "git_push": False,
        },
    }
    with tempfile.TemporaryDirectory() as temporary:
        path = Path(temporary) / "approval.json"
        path.write_text(json.dumps(receipt))
        try:
            module.load_approval(path, "a" * 64, "b" * 64)
        except module.NotebookContractError:
            pass
        else:
            raise AssertionError("expanded submission authorization was accepted")
