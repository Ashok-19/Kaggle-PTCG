from __future__ import annotations

import argparse
import json
from pathlib import Path

from ptcg_rl.g3.bc_production_v2 import execute_training


def main() -> None:
    parser = argparse.ArgumentParser(description="Run E01 production recurrent behavior cloning.")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--retained-root", type=Path, required=True)
    parser.add_argument("--august-3-root", type=Path, required=True)
    parser.add_argument("--august-4-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    report = execute_training(
        args.root.resolve(),
        args.request.resolve(),
        {
            "retained_private": args.retained_root.resolve(),
            "august_3_daily": args.august_3_root.resolve(),
            "august_4_daily": args.august_4_root.resolve(),
        },
        args.output_dir.resolve(),
    )
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
