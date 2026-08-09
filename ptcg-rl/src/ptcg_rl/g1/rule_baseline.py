from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
import sys
import uuid
from pathlib import Path
from types import ModuleType
from typing import Any, Mapping

from .actions import CompoundActionBuilder, validate_compound_action
from .models import CompoundActionV1, ContractViolation, EngineObservationV1, SelectionRequestV1
from .native import load_deck


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class NativeRulePolicy:
    """Private official rule module behind the same final action validator as every policy."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory.resolve(strict=True)
        receipt = json.loads((self.directory / "receipt.json").read_text(encoding="utf-8"))
        self.policy_id = receipt["policy_id"]
        self.deck_sha256 = receipt["deck"]["sha256"]
        self.deck = load_deck(self.directory / "deck.csv")
        if _sha256(self.directory / "deck.csv") != self.deck_sha256:
            raise ContractViolation("private rule baseline deck hash mismatch")
        module_path = self.directory / "main.py"
        if _sha256(module_path) != receipt["module"]["sha256"]:
            raise ContractViolation("private rule baseline module hash mismatch")
        self._module = self._load_module(module_path)
        if not callable(getattr(self._module, "agent", None)):
            raise ContractViolation("private rule baseline has no callable agent")

    def _load_module(self, path: Path) -> ModuleType:
        name = f"ptcg_private_rule_{uuid.uuid4().hex}"
        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None or spec.loader is None:
            raise ContractViolation("cannot load private rule baseline module")
        module = importlib.util.module_from_spec(spec)
        previous = Path.cwd()
        previous_sys_path = sys.path.copy()
        try:
            os.chdir(self.directory)
            sys.path.insert(0, str(self.directory))
            sys.modules[name] = module
            spec.loader.exec_module(module)
        finally:
            sys.path[:] = previous_sys_path
            os.chdir(previous)
        return module

    def reset(self, episode_uuid: str, player_index: int, reason: str = "start") -> None:
        return None

    def choose(self, observation: EngineObservationV1, request: SelectionRequestV1) -> CompoundActionV1:
        raise ContractViolation("native rule policy requires the raw official observation")

    def choose_native(
        self,
        raw: Mapping[str, Any],
        observation: EngineObservationV1,
        request: SelectionRequestV1,
    ) -> CompoundActionV1:
        returned = self._module.agent(copy.deepcopy(raw))
        if not isinstance(returned, list):
            raise ContractViolation("native rule policy output must be a list")
        by_original = {option.original_index: index for index, option in enumerate(request.options)}
        builder = CompoundActionBuilder(request)
        for original_index in returned:
            if isinstance(original_index, bool) or not isinstance(original_index, int):
                raise ContractViolation("native rule policy indices must be integers")
            if original_index not in by_original:
                raise ContractViolation("native rule policy returned an unavailable index")
            builder.choose(by_original[original_index])
        if not builder.complete:
            builder.stop()
        return validate_compound_action(request, builder.build())
