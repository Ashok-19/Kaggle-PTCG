from __future__ import annotations

import argparse
from pathlib import Path

from ptcg_rl.g3.local_correctness import run_local_correctness, write_local_correctness_report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the bounded G3a local toy correctness matrix")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    arguments = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    config = arguments.config.resolve()
    output = arguments.output.resolve()
    report = run_local_correctness(
        root=root,
        config_path=config,
        source_commit=arguments.source_commit,
    )
    write_local_correctness_report(output, report)
    print(output)
    return 0 if report["decision"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
