#!/usr/bin/env python3
"""Print a compact JSON summary of a cProfile artifact."""

from __future__ import annotations

import argparse
import json
import pstats
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("profile", type=Path)
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()
    stats = pstats.Stats(str(args.profile))
    rows = []
    for (filename, line, function), values in stats.stats.items():
        primitive, calls, own, cumulative, _ = values
        rows.append({"file": Path(filename).name, "line": line, "function": function,
                     "primitive_calls": primitive, "calls": calls,
                     "own_seconds": own, "cumulative_seconds": cumulative})
    rows.sort(key=lambda row: row["cumulative_seconds"], reverse=True)
    print(json.dumps({"total_calls": stats.total_calls, "total_seconds": stats.total_tt,
                      "top_by_cumulative": rows[:args.limit]}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
