from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ptcg_rl.g3.bc_canary import (  # noqa: E402
    BCCanaryContractError,
    execute_authorized_canary,
    run_preflight,
)


def write_report(report: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(path.suffix + ".partial")
    partial.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    partial.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--request",
        type=Path,
        default=ROOT / "configs/e01_bc_engineering_canary_request_v1.json",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "reports/artifacts/e01-bc-engineering-canary-preflight-v1.json",
    )
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    try:
        report = (
            execute_authorized_canary(ROOT, args.request)
            if args.execute
            else run_preflight(ROOT, args.request)
        )
    except BCCanaryContractError as error:
        print(str(error), file=sys.stderr)
        return 2
    if not args.execute:
        write_report(report, args.out)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
