"""Print the sealed, native-launch-blocked B1 component qualification plan.

The script is intentionally planning-only.  It does not import the native
engine, start games, invoke Kaggle, or write evidence.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ptcg_rl.deterministic.b1_component_harness import B1ComponentPlanV1, DEFAULT_PLAN_PATH, STAGE_CANARY, STAGE_SCREEN


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect the bounded Phase B1 component plan (native launch remains blocked).")
    parser.add_argument("--plan", default=DEFAULT_PLAN_PATH)
    parser.add_argument("--arm-matrix", action="store_true", help="print exact natural-seat arm cells")
    parser.add_argument("--stage", choices=(STAGE_CANARY, STAGE_SCREEN), default=STAGE_CANARY)
    parser.add_argument("--review-receipt", type=Path, help="stage-0 independent review JSON required for the gated screen")
    args = parser.parse_args()
    plan = B1ComponentPlanV1.from_path(Path(args.plan))
    value = {
        "experiment_id": plan.payload["experiment_id"],
        "status": plan.payload["status"],
        "plan_sha256": plan.plan_sha256,
        "arms": plan.arms,
        "anchors": plan.anchors,
        "stage": args.stage,
        "games_per_arm": int(plan.payload["stages"][args.stage]["games_per_arm"]),
        "games_all_arms": int(plan.payload["stages"][args.stage]["games_all_arms"]),
        "native_launch_authorized": False,
    }
    if args.arm_matrix:
        review = None
        if args.review_receipt:
            review = json.loads(args.review_receipt.read_text(encoding="utf-8"))
        value["arm_matrix"] = plan.arm_matrix(args.stage, canary_review=review)
    print(json.dumps(value, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
