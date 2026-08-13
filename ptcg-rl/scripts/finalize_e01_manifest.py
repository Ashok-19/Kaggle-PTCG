from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "reports/artifacts/e01-approved-replay-corpus-manifest-v1.json"
CANARY = ROOT / "configs/e01_bc_engineering_canary_request_v1.json"


def main() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    manifest["policy_loss_recount"] = {
        "forced_teacher_requests": 402,
        "path": "reports/artifacts/e01-approved-replay-policy-loss-recount-v1.json",
        "policy_loss_targets": 7140,
        "producer": "scripts/e01_policy_loss_recount.py",
        "recorded_active_request_mismatch_episodes": 0,
        "teacher_active_requests": 7542,
    }
    payload = copy.deepcopy(manifest)
    payload.pop("manifest_sha256", None)
    manifest["manifest_sha256"] = hashlib.sha256(
        (
            json.dumps(
                payload,
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
    ).hexdigest()
    MANIFEST.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    canary = json.loads(CANARY.read_text(encoding="utf-8"))
    canary["corpus"]["manifest_sha256"] = manifest["manifest_sha256"]
    CANARY.write_text(
        json.dumps(canary, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(manifest["manifest_sha256"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
