from __future__ import annotations

import argparse
import json
from pathlib import Path

from ptcg_rl.g3.bc_production import stage_authorized_publication


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Stage the exact retained train/validation replay subset after a hash-bound approval."
    )
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--approval-receipt", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    report = stage_authorized_publication(
        args.root.resolve(),
        args.request.resolve(),
        args.approval_receipt.resolve(),
        args.output_dir.resolve(),
    )
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
