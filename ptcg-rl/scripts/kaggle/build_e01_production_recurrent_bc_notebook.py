from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path

WRAPPER = Path(__file__).with_name("e01_production_recurrent_bc_notebook_v1.py")


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Build deterministic Kaggle source for E01 production recurrent BC.")
    parser.add_argument("--approval-receipt", type=Path, required=True)
    parser.add_argument("--notebook-request-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt-copy", type=Path)
    args = parser.parse_args()
    wrapper_raw = WRAPPER.read_bytes()
    receipt_raw = args.approval_receipt.read_bytes()
    receipt = json.loads(receipt_raw)
    if receipt.get("wrapper_sha256") != sha256_bytes(wrapper_raw):
        raise ValueError("approval receipt wrapper SHA differs")
    if receipt.get("notebook_request_sha256") != args.notebook_request_sha256:
        raise ValueError("approval receipt notebook request SHA differs")
    wrapper_b64 = base64.b64encode(wrapper_raw).decode()
    receipt_b64 = base64.b64encode(receipt_raw).decode()
    source = (
        "from __future__ import annotations\n"
        "import base64\n"
        "import pathlib\n"
        "import subprocess\n"
        "import sys\n"
        "bootstrap = pathlib.Path(\"/kaggle/working/e01-production-recurrent-bc-bootstrap-v1\")\n"
        "bootstrap.mkdir(parents=True, exist_ok=False)\n"
        "wrapper = bootstrap / \"e01_production_recurrent_bc_notebook_v1.py\"\n"
        "approval = bootstrap / \"e01-production-recurrent-bc-approval-v1.json\"\n"
        f"wrapper.write_bytes(base64.b64decode({wrapper_b64!r}))\n"
        f"approval.write_bytes(base64.b64decode({receipt_b64!r}))\n"
        f"subprocess.run([sys.executable, str(wrapper), \"--approval-receipt\", str(approval), \"--notebook-request-sha256\", {args.notebook_request_sha256!r}], check=True)\n"
    )
    raw = source.encode()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(raw)
    if args.receipt_copy is not None:
        args.receipt_copy.parent.mkdir(parents=True, exist_ok=True)
        args.receipt_copy.write_bytes(receipt_raw)
    print(json.dumps({"source_sha256": sha256_bytes(raw), "source_bytes": len(raw), "wrapper_sha256": sha256_bytes(wrapper_raw), "receipt_sha256": sha256_bytes(receipt_raw)}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
