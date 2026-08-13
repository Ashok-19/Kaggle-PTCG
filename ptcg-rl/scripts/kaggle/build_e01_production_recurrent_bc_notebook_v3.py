from __future__ import annotations

import argparse
import base64
import json
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WRAPPER = Path(__file__).with_name("e01_production_recurrent_bc_notebook_v3.py")
IMPLEMENTATION = ROOT / "src/ptcg_rl/g3/bc_production_v2.py"
REQUEST = ROOT / "configs/e01_production_recurrent_bc_request_v2.json"


def encoded(path: Path) -> str:
    """Return a compact ASCII payload for a UTF-8 source/config file."""
    return base64.b64encode(zlib.compress(path.read_bytes(), level=9)).decode("ascii")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Kaggle source for E01 production recurrent BC.")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    wrapper_payload = encoded(WRAPPER)
    implementation_payload = encoded(IMPLEMENTATION)
    request_payload = encoded(REQUEST)

    source = (
        "from __future__ import annotations\n"
        "import base64\n"
        "import pathlib\n"
        "import subprocess\n"
        "import sys\n"
        "import zlib\n"
        "bootstrap = pathlib.Path('/kaggle/working/e01-production-recurrent-bc-bootstrap-v3')\n"
        "bootstrap.mkdir(parents=True, exist_ok=False)\n"
        "wrapper = bootstrap / 'e01_production_recurrent_bc_notebook_v3.py'\n"
        "implementation = bootstrap / 'bc_production_v2.py'\n"
        "request = bootstrap / 'e01_production_recurrent_bc_request_v2.json'\n"
        "def unpack(payload, path):\n"
        "    path.write_bytes(zlib.decompress(base64.b64decode(payload)))\n"
        f"unpack({wrapper_payload!r}, wrapper)\n"
        f"unpack({implementation_payload!r}, implementation)\n"
        f"unpack({request_payload!r}, request)\n"
        "subprocess.run([sys.executable, str(wrapper), '--request-source', str(request), '--implementation-source', str(implementation)], check=True)\n"
    )
    raw = source.encode("utf-8")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(raw)
    print(json.dumps({"source_bytes": len(raw)}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
