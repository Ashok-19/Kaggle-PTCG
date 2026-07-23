from __future__ import annotations

import argparse
from pathlib import Path

from ptcg_rl.g3.competence_plan import (
    canonical_json_bytes,
    load_competence_plan,
    review_competence_plan,
)


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description="Independently review the frozen G3b competence plan")
    value.add_argument("--plan", type=Path, required=True)
    value.add_argument("--repo", type=Path, default=Path("."))
    value.add_argument("--planner-commit", required=True)
    value.add_argument("--created-at-utc", required=True)
    value.add_argument("--source-path")
    value.add_argument("--output", type=Path, required=True)
    return value


def main() -> int:
    args = parser().parse_args()
    repo = args.repo.resolve(strict=True)
    plan_path = args.plan.resolve(strict=True)
    loaded = load_competence_plan(plan_path, repo)
    output = args.output
    if output.exists():
        raise FileExistsError(f"review output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    source_path = args.source_path
    if source_path is None:
        source_path = output.resolve().relative_to(repo).as_posix()
    review = review_competence_plan(
        loaded,
        created_at_utc=args.created_at_utc,
        source_path=source_path,
        planner_commit=args.planner_commit,
    )
    raw = canonical_json_bytes(review)
    output.write_bytes(raw)
    print(raw.decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
