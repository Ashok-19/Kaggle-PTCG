"""Scratch-only MAIN option-Q adapter for the qualified Grim controller.

The adapter deliberately has one narrow job: advance the frozen public G2
trunk for every semantic request and rank complete singleton MAIN requests
with a supplied terminal-outcome head.  Every other request is delegated to
the byte-preserved Grim controller.
"""

from __future__ import annotations

import collections
import copy
import hashlib
import importlib.util
import json
import os
import sys
import uuid
import zipfile
from pathlib import Path
from types import ModuleType
from typing import Any, Mapping, Sequence

import torch

from outcome_ranker import (
    BC_TRUNK_CHECKPOINT_SHA256,
    BC_TRUNK_STATE_SHA256,
    G2_MODEL_SCHEMA_SHA256,
    G2_PACKAGE_SHA256,
    OutcomeRankerError,
    TrunkBindingV1,
    load_checkpoint,
    semantic_equivalence_key,
)
from ptcg_rl.g1.models import stable_hash
from ptcg_rl.g1.semantic import semantic_snapshot
from ptcg_rl.g2.checkpoint import load_checkpoint_package, state_dict_sha256
from ptcg_rl.g2.network import collate_projected
from ptcg_rl.g2.projection import project_decision


class OutcomeMainAdapterError(RuntimeError):
    """Raised when the candidate package cannot satisfy its strict contract."""


EXPECTED_HEAD_BINDING = TrunkBindingV1(
    g2_package_sha256=G2_PACKAGE_SHA256,
    g2_model_schema_sha256=G2_MODEL_SCHEMA_SHA256,
    bc_trunk_checkpoint_sha256=BC_TRUNK_CHECKPOINT_SHA256,
    bc_trunk_state_sha256=BC_TRUNK_STATE_SHA256,
    bc_trunk_optimizer_steps=840,
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _find_root(explicit: Path | None = None) -> Path:
    candidates: list[Path] = []
    if explicit is not None:
        candidates.append(explicit)
    configured = os.environ.get("PTCG_OUTCOME_ASSET_ROOT")
    if configured:
        candidates.append(Path(configured))
    if "__file__" in globals():
        candidates.append(Path(__file__).resolve().parent)
    candidates.extend((Path("/kaggle_simulations/agent"), Path.cwd()))
    for candidate in candidates:
        root = candidate.resolve()
        if (root / "qualified_grim_main.py").is_file():
            return root
    raise OutcomeMainAdapterError(
        "candidate package root is not discoverable; expected qualified_grim_main.py"
    )


def _load_module(path: Path) -> ModuleType:
    name = f"qualified_grim_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise OutcomeMainAdapterError(f"cannot load qualified controller: {path}")
    module = importlib.util.module_from_spec(spec)
    old_path = sys.path.copy()
    old_cwd = Path.cwd()
    try:
        sys.path.insert(0, str(path.parent))
        os.chdir(path.parent)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    except Exception as error:
        raise OutcomeMainAdapterError(
            f"qualified Grim controller failed to load: {type(error).__name__}: {error}"
        ) from error
    finally:
        sys.path[:] = old_path
        os.chdir(old_cwd)
    if not callable(getattr(module, "agent", None)):
        raise OutcomeMainAdapterError("qualified controller has no callable agent")
    return module


def _load_card_data_hash(package_path: Path) -> str:
    try:
        with zipfile.ZipFile(package_path) as archive:
            value = json.loads(archive.read("card-table-v1.json"))
    except (OSError, KeyError, json.JSONDecodeError, UnicodeDecodeError, zipfile.BadZipFile) as error:
        raise OutcomeMainAdapterError("G2 package card table cannot be read") from error
    card_hash = value.get("card_data_sha256") if isinstance(value, Mapping) else None
    if (
        not isinstance(card_hash, str)
        or len(card_hash) != 64
        or any(character not in "0123456789abcdef" for character in card_hash)
    ):
        raise OutcomeMainAdapterError("G2 card-data provenance is missing or malformed")
    return card_hash


def _load_frozen_trunk(root: Path) -> tuple[torch.nn.Module, str]:
    package_path = root / ".assets/g2-policy-checkpoint-v1.zip"
    bc_path = root / ".assets/epoch-4.pt"
    if _sha256_file(package_path) != G2_PACKAGE_SHA256:
        raise OutcomeMainAdapterError("candidate G2 package SHA-256 differs from the pinned package")
    if _sha256_file(bc_path) != BC_TRUNK_CHECKPOINT_SHA256:
        raise OutcomeMainAdapterError("candidate BC checkpoint SHA-256 differs from epoch 4")
    try:
        loaded = load_checkpoint_package(
            package_path,
            device="cpu",
            expected_package_sha256=G2_PACKAGE_SHA256,
        )
        value = torch.load(bc_path, map_location="cpu", weights_only=True)
    except Exception as error:
        raise OutcomeMainAdapterError("frozen G2/BC trunk cannot be loaded") from error
    if not isinstance(value, Mapping) or value.get("kind") != "KPTCG_G3_TRAINING_CHECKPOINT":
        raise OutcomeMainAdapterError("BC checkpoint kind differs from the pinned training checkpoint")
    counters = value.get("counters")
    if not isinstance(counters, Mapping) or counters.get("optimizer_steps") != 840:
        raise OutcomeMainAdapterError("BC checkpoint optimizer step count is not epoch 4")
    state = value.get("model_state")
    if not isinstance(state, Mapping) or state_dict_sha256(state) != BC_TRUNK_STATE_SHA256:
        raise OutcomeMainAdapterError("BC checkpoint state SHA-256 differs from the pinned epoch 4 state")
    try:
        loaded.model.load_state_dict(state, strict=True)
    except (RuntimeError, TypeError) as error:
        raise OutcomeMainAdapterError("BC state is not strict-compatible with frozen G2") from error
    loaded.model.eval()
    loaded.model.requires_grad_(False)
    if any(parameter.requires_grad for parameter in loaded.model.parameters()):
        raise OutcomeMainAdapterError("frozen G2 trunk still has trainable parameters")
    if state_dict_sha256(loaded.model.state_dict()) != BC_TRUNK_STATE_SHA256:
        raise OutcomeMainAdapterError("loaded frozen G2 state changed during installation")
    if G2_MODEL_SCHEMA_SHA256 != loaded.manifest.get("model_schema_sha256"):
        raise OutcomeMainAdapterError("frozen G2 model schema differs from the pinned schema")
    return loaded.model, _load_card_data_hash(package_path)


class OutcomeMainAdapter:
    """Stateful raw callback adapter with strict MAIN-only ranking."""

    def __init__(self, root: Path | None = None, head_path: Path | None = None) -> None:
        self.root = _find_root(root)
        self._head_path = head_path or self.root / ".assets/outcome_head.pt"
        if not self._head_path.is_file():
            raise OutcomeMainAdapterError(f"outcome head checkpoint is missing: {self._head_path}")
        self._delegate = _load_module(self.root / "qualified_grim_main.py")
        self._trunk, self._card_data_sha256 = _load_frozen_trunk(self.root)
        try:
            self._ranker = load_checkpoint(self._head_path.read_bytes(), map_location="cpu")
        except (OSError, OutcomeRankerError) as error:
            raise OutcomeMainAdapterError("outcome head checkpoint failed strict loading") from error
        binding = getattr(self._ranker, "_gate1_trunk_binding", None)
        if binding != EXPECTED_HEAD_BINDING:
            raise OutcomeMainAdapterError("outcome head is not bound to frozen BC epoch 4")
        self._ranker.eval()
        self._ranker.requires_grad_(False)
        if any(parameter.requires_grad for parameter in self._ranker.parameters()):
            raise OutcomeMainAdapterError("outcome head still has trainable parameters")
        self._head_sha256 = _sha256_file(self._head_path)
        self._counters: collections.Counter[str] = collections.Counter()
        self._episode_number = 0
        self._episode_uuid = ""
        self._transition_id = 0
        self._previous_request_ref: str | None = None
        self._previous_action_ref: str | None = None
        self._hidden = torch.empty((1, 160), dtype=torch.float32)
        self._reset_state()

    def _reset_state(self) -> None:
        self._episode_number += 1
        self._episode_uuid = f"outcome-main-{self._episode_number}"
        self._transition_id = 0
        self._previous_request_ref = None
        self._previous_action_ref = None
        self._hidden = self._trunk.initial_hidden(1, "cpu")
        self._counters["resets"] += 1

    def diagnostics(self) -> dict[str, Any]:
        values = {key: int(value) for key, value in sorted(self._counters.items())}
        values.update(
            {
                "episode_number": self._episode_number,
                "head_sha256": self._head_sha256,
                "g2_package_sha256": G2_PACKAGE_SHA256,
                "bc_trunk_state_sha256": BC_TRUNK_STATE_SHA256,
                "card_data_sha256": self._card_data_sha256,
                "hidden_shape": list(self._hidden.shape),
            }
        )
        return values

    @staticmethod
    def _request_view(request: Any) -> dict[str, Any]:
        return {
            "selection_type": request.selection_type,
            "selection_context": request.selection_context,
            "min_count": request.min_count,
            "max_count": request.max_count,
            "ordering": request.ordering,
        }

    @staticmethod
    def _option_view(option: Any) -> dict[str, Any]:
        return {"is_stop": option.option_type == 14}

    def _remember(self, request: Any, action: Sequence[int]) -> None:
        self._previous_request_ref = request.request_id
        self._previous_action_ref = stable_hash(
            {"request_id": request.request_id, "original_indices": list(action)}
        )
        self._transition_id += 1

    def _delegate_action(self, raw: Mapping[str, Any]) -> list[int]:
        try:
            result = self._delegate.agent(copy.deepcopy(raw))
        except Exception as error:
            self._counters["delegate_errors"] += 1
            raise OutcomeMainAdapterError("qualified Grim callback failed") from error
        if not isinstance(result, list):
            self._counters["delegate_invalid_outputs"] += 1
            raise OutcomeMainAdapterError("qualified Grim callback did not return a list")
        return result

    def _rank_main(self, request: Any, decision: Any, batch: Any, output: Any) -> list[int]:
        if request.min_count != 1 or request.max_count != 1 or request.ordering != "UNORDERED":
            raise OutcomeMainAdapterError("MAIN request is not a complete singleton action set")
        options = tuple(request.options)
        if not options or tuple(option.original_index for option in options) != tuple(range(len(options))):
            raise OutcomeMainAdapterError("MAIN legal option transport is incomplete or reordered")
        option_count = len(options)
        if output.option_embeddings.shape != (option_count, 128):
            raise OutcomeMainAdapterError("G2 option embeddings do not cover complete MAIN options")
        if output.option_offsets.tolist() != [0, option_count]:
            raise OutcomeMainAdapterError("G2 option offsets do not cover complete MAIN options")
        if batch.option_available.shape != (option_count,) or not bool(batch.option_available.all()):
            raise OutcomeMainAdapterError("MAIN legal option mask is incomplete")
        request_view = self._request_view(request)
        option_views = tuple(self._option_view(option) for option in options)
        keys = tuple(
            semantic_equivalence_key(request_view, option_views, decision.model, index)
            for index in range(option_count)
        )
        scores = self._ranker(
            output.hidden,
            output.option_embeddings,
            torch.tensor([0, option_count], dtype=torch.long),
        )
        if scores.shape != (option_count,) or not torch.isfinite(scores).all():
            self._counters["nonfinite_outputs"] += 1
            raise OutcomeMainAdapterError("outcome head emitted nonfinite or incomplete scores")
        groups: dict[str, list[int]] = {}
        for index, key in enumerate(keys):
            groups.setdefault(key, []).append(index)
        self._counters["duplicate_classes"] += sum(len(indices) > 1 for indices in groups.values())
        pooled: list[tuple[float, int, str, list[int]]] = []
        for key, indices in groups.items():
            values = [float(scores[index].item()) for index in indices]
            pooled_score = sum(values) / len(values)
            if not torch.isfinite(torch.tensor(pooled_score)):
                self._counters["nonfinite_outputs"] += 1
                raise OutcomeMainAdapterError("pooled outcome score is nonfinite")
            canonical = min(indices, key=lambda index: options[index].original_index)
            pooled.append((pooled_score, options[canonical].original_index, key, indices))
        if not pooled:
            raise OutcomeMainAdapterError("MAIN legal option set is empty")
        _, _, _, selected_indices = max(pooled, key=lambda item: (item[0], -item[1], item[2]))
        selected = min(selected_indices, key=lambda index: options[index].original_index)
        action = [options[selected].original_index]
        if len(action) != 1 or action[0] not in range(option_count):
            self._counters["invalid_ranker_actions"] += 1
            raise OutcomeMainAdapterError("outcome head produced an illegal MAIN action")
        return action

    def agent(self, raw: Mapping[str, Any]) -> list[int]:
        if not isinstance(raw, Mapping):
            raise OutcomeMainAdapterError("raw callback observation must be a mapping")
        self._counters["callbacks"] += 1
        delegated = self._delegate_action(raw)
        if raw.get("select") is None:
            self._reset_state()
            return delegated
        try:
            observation, request = semantic_snapshot(
                raw,
                self._episode_uuid,
                self._transition_id,
                self._card_data_sha256,
                self._previous_action_ref,
                self._previous_request_ref,
            )
            if request is None:
                self._counters["terminal_callbacks"] += 1
                self._reset_state()
                return delegated
            decision = project_decision(observation, request)
            batch = collate_projected((decision,), device="cpu")
            with torch.inference_mode():
                output = self._trunk(batch, self._hidden)
            if (
                not torch.isfinite(output.hidden).all()
                or not torch.isfinite(output.option_embeddings).all()
                or not torch.isfinite(output.values).all()
            ):
                self._counters["nonfinite_outputs"] += 1
                raise OutcomeMainAdapterError("frozen G2 emitted nonfinite output")
            self._hidden = output.hidden.detach().clone()
            self._counters["trunk_steps"] += 1
            if request.selection_type != 0 or request.selection_context != 0:
                self._counters["non_main_delegations"] += 1
                self._remember(request, delegated)
                return delegated
            try:
                action = self._rank_main(request, decision, batch, output)
            except Exception:
                self._counters["ranker_fallbacks"] += 1
                self._remember(request, delegated)
                return delegated
            self._counters["main_ranked"] += 1
            self._remember(request, action)
            return action
        except Exception:
            self._counters["projection_fallbacks"] += 1
            self._reset_state()
            return delegated


__all__ = ["OutcomeMainAdapter", "OutcomeMainAdapterError"]
