from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ptcg_rl.g3.gold_path import review_gold_path, write_review  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--work-orders",
        type=Path,
        default=ROOT / "configs/gold_path_work_orders_v1.json",
    )
    parser.add_argument(
        "--dry-run",
        type=Path,
        default=ROOT / "reports/artifacts/e01a-public-replay-dry-run-v1.json",
    )
    parser.add_argument(
        "--decision",
        type=Path,
        default=(
            ROOT
            / "docs/decisions/DEC-028_E01_CORPUS_V2_AND_BC_CANARY_RESULTS.md"
        ),
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "reports/artifacts/gold-path-work-orders-review-v1.json",
    )
    args = parser.parse_args()
    report = review_gold_path(
        ROOT.parent,
        work_orders_path=args.work_orders,
        dry_run_path=args.dry_run,
        decision_path=args.decision,
    )
    write_review(report, args.out)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
