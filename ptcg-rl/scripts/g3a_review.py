from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ptcg_rl.g3.evaluation import (
    EvaluationContractError,
    canonical_json_bytes,
    load_evaluation_contract,
    load_json_object,
    review_g3a_evidence,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Independently review G3a evidence")
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        contract = load_evaluation_contract(args.contract)
        evidence = load_json_object(args.evidence, "G3a evidence")
        review = review_g3a_evidence(contract, evidence)
        raw = canonical_json_bytes(review)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_suffix(args.output.suffix + ".partial")
        temporary.write_bytes(raw)
        temporary.replace(args.output)
        print(json.dumps(review, indent=2, sort_keys=True, allow_nan=False))
        return 0 if review["decision"] == "PASS" else 1
    except (EvaluationContractError, OSError) as error:
        print(f"G3a review invalid: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
