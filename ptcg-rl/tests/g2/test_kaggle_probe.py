from __future__ import annotations

import ast
import json
from pathlib import Path


def test_kaggle_environment_probe_is_bounded_and_source_controlled() -> None:
    root = Path(__file__).resolve().parents[2]
    config = json.loads(
        (root / "configs" / "kaggle" / "g2_environment_probe.json").read_text(
            encoding="utf-8"
        )
    )
    script = root / config["source_script"]
    ast.parse(script.read_text(encoding="utf-8"))
    assert config["private"] is True
    assert config["internet"] is False
    assert config["gpu"] is False
    assert config["tpu"] is False
    assert config["timeout_seconds"] == 600
    assert config["requested_docker_image"] == "gcr.io/kaggle-images/python:v163"
