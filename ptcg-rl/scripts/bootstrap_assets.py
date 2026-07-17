from __future__ import annotations

import sys

from ptcg_rl.cli import main

raise SystemExit(main(["assets", "import", *sys.argv[1:]]))

