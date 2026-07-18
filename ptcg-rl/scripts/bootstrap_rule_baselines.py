#!/usr/bin/env python3
"""Verify supplied notebooks and extract their private rule-agent modules."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_exact(path: Path, content: bytes) -> None:
    if path.exists():
        if path.read_bytes() != content:
            raise ValueError(f"refusing to replace different private artifact: {path.name}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def extract_main(notebook: dict[str, Any]) -> bytes:
    cells = [
        "".join(cell.get("source", []))
        for cell in notebook.get("cells", [])
        if cell.get("cell_type") == "code"
        and "".join(cell.get("source", [])).startswith("%%writefile main.py\n")
    ]
    if len(cells) != 1:
        raise ValueError(f"expected one main.py cell, found {len(cells)}")
    return cells[0].split("\n", 1)[1].encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--notebooks", type=Path, required=True)
    parser.add_argument("--private-root", type=Path)
    args = parser.parse_args()
    repo = args.repo.resolve()
    private_root = (args.private_root or repo / "private" / "baselines").resolve()
    config = json.loads((repo / "configs" / "g1r_rule_baselines.json").read_text())
    receipts = []
    for item in config["baselines"]:
        notebook_path = (args.notebooks / item["notebook"]).resolve(strict=True)
        if sha256(notebook_path) != item["notebook_sha256"]:
            raise ValueError(f"notebook hash mismatch for {item['id']}")
        notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
        sources = notebook.get("metadata", {}).get("kaggle", {}).get("dataSources", [])
        expected = {
            "datasetId": item["dataset_id"],
            "databundleVersionId": item["version_id"],
            "sourceId": item["source_id"],
            "sourceType": "datasetVersion",
        }
        if expected not in sources:
            raise ValueError(f"notebook dataset metadata mismatch for {item['id']}")
        directory = private_root / item["id"]
        deck = directory / "deck.csv"
        if deck.stat().st_size != item["deck_bytes"] or sha256(deck) != item["deck_sha256"]:
            raise ValueError(f"deck receipt mismatch for {item['id']}")
        module = directory / "main.py"
        write_exact(module, extract_main(notebook))
        receipt = {
            "schema_version": 1,
            "baseline_id": item["id"],
            "policy_id": f"official-rule-{item['id']}-v1",
            "notebook": {"bytes": notebook_path.stat().st_size, "sha256": sha256(notebook_path)},
            "module": {"bytes": module.stat().st_size, "sha256": sha256(module)},
            "deck": {"bytes": deck.stat().st_size, "sha256": sha256(deck)},
        }
        write_exact(
            directory / "receipt.json",
            (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode(),
        )
        receipts.append(receipt)
    print(json.dumps({"status": "pass", "receipts": receipts}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
