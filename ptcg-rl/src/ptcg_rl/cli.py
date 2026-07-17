from __future__ import annotations

import argparse
import json
from pathlib import Path

from .assets import AssetError, import_assets, verify_assets
from .audit import audit_repository
from .doctor import run_doctor


def _repo() -> Path:
    return Path(__file__).resolve().parents[2]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ptcg")
    commands = parser.add_subparsers(dest="command", required=True)
    assets = commands.add_parser("assets").add_subparsers(dest="asset_command", required=True)
    importer = assets.add_parser("import")
    importer.add_argument("--official-archive", type=Path, required=True)
    importer.add_argument("--sample-agents", type=Path, required=True)
    importer.add_argument("--research", type=Path, required=True)
    importer.add_argument("--force", action="store_true")
    assets.add_parser("verify")
    doctor = commands.add_parser("doctor")
    doctor.add_argument("--json", type=Path)
    doctor.add_argument("--cloud", action="store_true")
    commands.add_parser("provenance")
    commands.add_parser("audit-staged")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    repo = _repo()
    try:
        if args.command == "assets" and args.asset_command == "import":
            result = import_assets(repo, args.official_archive, args.sample_agents, args.research, args.force)
        elif args.command == "assets":
            issues = verify_assets(repo)
            result = {"status": "fail" if issues else "pass", "issues": issues}
        elif args.command == "doctor":
            result = run_doctor(repo, args.cloud)
            if args.json:
                output = args.json if args.json.is_absolute() else repo / args.json
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        elif args.command == "provenance":
            path = repo / "asset_hashes.redacted.json"
            result = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"status": "missing"}
        else:
            restricted = audit_repository(repo)
            result = {"status": "fail" if restricted else "pass", "restricted_paths": restricted}
        print(json.dumps(result, indent=2, sort_keys=True))
        return int(result.get("status") == "fail")
    except (AssetError, OSError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "fail", "error": str(error)}, indent=2))
        return 1

