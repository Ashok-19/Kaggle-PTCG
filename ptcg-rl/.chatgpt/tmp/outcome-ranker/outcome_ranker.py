"""Scratch-only terminal-outcome option ranker.

The frozen G2 network remains the public-state projector/trunk.  This module
only learns a small option-conditioned scalar head and is not imported by any
production policy or PPO path.
"""

from __future__ import annotations

import io
import json
import hashlib
import math
import pickle
import subprocess
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any, Mapping, Sequence

import torch
from torch import Tensor, nn
from torch.nn import functional as F

from ptcg_rl.g1.models import ContractViolation, stable_hash
from ptcg_rl.g2.checkpoint import load_checkpoint_package, state_dict_sha256
from ptcg_rl.g2.models import (
    ModelInputV1,
    OptionTransportMapV1,
    ProjectedDecisionV1,
    model_schema_sha256,
)
from ptcg_rl.g2.network import PTCGPolicyV1, collate_projected


class OutcomeRankerError(ValueError):
    """Raised when a dataset row cannot support the minimal Q contract."""


_REPO_ROOT = Path(__file__).resolve().parents[3]
G2_PACKAGE_RELATIVE = Path("private/g2/checkpoint-v1/g2-policy-checkpoint-v1.zip")
BC_TRUNK_RELATIVE = Path(".chatgpt/tmp/e01-bc-candidates-dataset/epoch-4.pt")
G2_PACKAGE_SHA256 = "4dfba2adb9f97607cfa5dabadba075236bb7aae51eafab264584e947feae3827"
G2_MODEL_SCHEMA_SHA256 = "61f6f71008c847b03bbab913d767da2c6bc6469311a0fe7249f3d03ee512bf68"
BC_TRUNK_CHECKPOINT_SHA256 = "76478ade97742697cc36aab311373b254ff186c787d772ab39d97cfb27ffafde"
BC_TRUNK_STATE_SHA256 = "b1efa5a137ce51347694daa41417efe080e19c4d6fad3f9bd48ebe268c6e2e1f"
BC_TRUNK_OPTIMIZER_STEPS = 840
RANKER_CHECKPOINT_SCHEMA_VERSION = 2
GATE1_HIDDEN_WIDTH = 160
GATE1_OPTION_WIDTH = 128
GATE1_RANKER_WIDTH = 96


@dataclass(frozen=True)
class TrunkBindingV1:
    """Immutable provenance required by a Gate-1 head checkpoint."""

    g2_package_sha256: str
    g2_model_schema_sha256: str
    bc_trunk_checkpoint_sha256: str
    bc_trunk_state_sha256: str
    bc_trunk_optimizer_steps: int
    mode: str = "FROZEN_BC_EPOCH4_HEAD_ONLY"

    def __post_init__(self) -> None:
        expected = {
            "g2_package_sha256": G2_PACKAGE_SHA256,
            "g2_model_schema_sha256": G2_MODEL_SCHEMA_SHA256,
            "bc_trunk_checkpoint_sha256": BC_TRUNK_CHECKPOINT_SHA256,
            "bc_trunk_state_sha256": BC_TRUNK_STATE_SHA256,
            "bc_trunk_optimizer_steps": BC_TRUNK_OPTIMIZER_STEPS,
            "mode": "FROZEN_BC_EPOCH4_HEAD_ONLY",
        }
        observed = asdict(self)
        if observed != expected:
            raise OutcomeRankerError("Gate-1 trunk provenance differs from the pinned BC epoch-4 binding")


def _sha256_file(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as error:
        raise OutcomeRankerError(f"required trunk artifact cannot be read: {path}") from error


def load_gate1_trunk(
    *,
    package_path: Path | None = None,
    bc_checkpoint_path: Path | None = None,
    device: torch.device | str = "cpu",
) -> tuple[PTCGPolicyV1, TrunkBindingV1]:
    """Load the exact G2 package and strictly replace it with BC epoch-4 state.

    Gate 1 deliberately freezes this trunk. End-to-end fine-tuning requires
    retained public prefix tensors/replay and is not represented by this API.
    """

    package_path = package_path or (_REPO_ROOT / G2_PACKAGE_RELATIVE)
    bc_checkpoint_path = bc_checkpoint_path or (_REPO_ROOT / BC_TRUNK_RELATIVE)
    if _sha256_file(package_path) != G2_PACKAGE_SHA256:
        raise OutcomeRankerError("G2 package SHA-256 differs from the pinned Gate-1 package")
    if _sha256_file(bc_checkpoint_path) != BC_TRUNK_CHECKPOINT_SHA256:
        raise OutcomeRankerError("BC epoch-4 checkpoint SHA-256 differs from the pinned trunk")
    try:
        loaded = load_checkpoint_package(
            package_path,
            device=device,
            expected_package_sha256=G2_PACKAGE_SHA256,
        )
        value = torch.load(bc_checkpoint_path, map_location=device, weights_only=True)
    except (OSError, RuntimeError, TypeError, ValueError, pickle.UnpicklingError) as error:
        raise OutcomeRankerError(f"Gate-1 trunk checkpoint cannot be loaded: {error}") from error
    if not isinstance(value, Mapping) or value.get("kind") != "KPTCG_G3_TRAINING_CHECKPOINT":
        raise OutcomeRankerError("BC trunk checkpoint kind is not the pinned training checkpoint")
    counters = value.get("counters")
    if not isinstance(counters, Mapping) or counters.get("optimizer_steps") != BC_TRUNK_OPTIMIZER_STEPS:
        raise OutcomeRankerError("BC trunk optimizer step count differs from the pinned epoch-4 state")
    state = value.get("model_state")
    if not isinstance(state, Mapping):
        raise OutcomeRankerError("BC trunk checkpoint lacks a model_state mapping")
    if state_dict_sha256(state) != BC_TRUNK_STATE_SHA256:
        raise OutcomeRankerError("BC trunk semantic state SHA-256 differs from the pinned state")
    try:
        loaded.model.load_state_dict(state, strict=True)
    except (RuntimeError, TypeError) as error:
        raise OutcomeRankerError(f"BC trunk is not strict-compatible with G2: {error}") from error
    if model_schema_sha256() != G2_MODEL_SCHEMA_SHA256:
        raise OutcomeRankerError("current G2 model schema differs from the pinned schema")
    loaded.model.eval()
    loaded.model.requires_grad_(False)
    binding = TrunkBindingV1(
        g2_package_sha256=loaded.package_sha256,
        g2_model_schema_sha256=G2_MODEL_SCHEMA_SHA256,
        bc_trunk_checkpoint_sha256=BC_TRUNK_CHECKPOINT_SHA256,
        bc_trunk_state_sha256=BC_TRUNK_STATE_SHA256,
        bc_trunk_optimizer_steps=BC_TRUNK_OPTIMIZER_STEPS,
    )
    loaded.model._gate1_trunk_binding = binding  # type: ignore[attr-defined]
    return loaded.model, binding


def _validate_gate1_trunk(frozen_g2: PTCGPolicyV1) -> None:
    """Reject base, random, or trainable models at the dataset boundary."""

    if not isinstance(frozen_g2, PTCGPolicyV1):
        raise OutcomeRankerError("dataset loader requires a PTCGPolicyV1 Gate-1 trunk")
    config = frozen_g2.config
    if config.public_hidden != GATE1_HIDDEN_WIDTH or config.option_width != GATE1_OPTION_WIDTH:
        raise OutcomeRankerError("Gate-1 trunk dimensions differ from the pinned G2 dimensions")
    if any(parameter.requires_grad for parameter in frozen_g2.parameters()):
        raise OutcomeRankerError("Gate-1 trunk must be fully frozen")
    state = frozen_g2.state_dict()
    if any(not torch.isfinite(value).all().item() for value in state.values()):
        raise OutcomeRankerError("Gate-1 trunk contains nonfinite weights")
    if state_dict_sha256(state) != BC_TRUNK_STATE_SHA256:
        raise OutcomeRankerError("Gate-1 trunk state SHA-256 is not the pinned BC epoch-4 state")
    if model_schema_sha256() != G2_MODEL_SCHEMA_SHA256:
        raise OutcomeRankerError("current G2 model schema differs from the pinned schema")
    binding = getattr(frozen_g2, "_gate1_trunk_binding", None)
    if binding is not None and not isinstance(binding, TrunkBindingV1):
        raise OutcomeRankerError("Gate-1 trunk binding is malformed")
    if binding is not None and binding != TrunkBindingV1(
        g2_package_sha256=G2_PACKAGE_SHA256,
        g2_model_schema_sha256=G2_MODEL_SCHEMA_SHA256,
        bc_trunk_checkpoint_sha256=BC_TRUNK_CHECKPOINT_SHA256,
        bc_trunk_state_sha256=BC_TRUNK_STATE_SHA256,
        bc_trunk_optimizer_steps=BC_TRUNK_OPTIMIZER_STEPS,
    ):
        raise OutcomeRankerError("Gate-1 trunk binding differs from the pinned BC epoch-4 binding")


@dataclass(frozen=True)
class RankerBatch:
    """Ragged option tensors and grouped terminal targets."""

    public_hidden: Tensor
    option_embeddings: Tensor
    option_available: Tensor
    option_offsets: Tensor
    target: Tensor
    target_stderr: Tensor
    target_weight: Tensor
    target_mask: Tensor
    group_offsets: Tensor
    state_group_ids: tuple[str, ...]
    action_ids: tuple[str, ...]
    semantic_fingerprints: tuple[str, ...]
    semantic_equivalence_keys: tuple[str, ...]
    # One immutable diagnostic record per state group; never fed to the model.
    equivalence_class_metadata: tuple[tuple[Mapping[str, Any], ...], ...] = ()


class OutcomeRankerV1(nn.Module):
    """Small option-conditioned Q head over the complete ragged option set."""

    def __init__(
        self,
        hidden_width: int = 160,
        option_width: int = 128,
        ranker_width: int = 96,
    ) -> None:
        super().__init__()
        if min(hidden_width, option_width, ranker_width) <= 0:
            raise ValueError("ranker dimensions must be positive")
        self.hidden_width = hidden_width
        self.option_width = option_width
        self.ranker_width = ranker_width
        self.head = nn.Sequential(
            nn.Linear(hidden_width + option_width, ranker_width),
            nn.GELU(),
            nn.Linear(ranker_width, 1),
        )

    def forward(
        self,
        public_hidden: Tensor,
        option_embeddings: Tensor,
        option_offsets: Tensor,
    ) -> Tensor:
        if public_hidden.ndim != 2 or public_hidden.shape[1] != self.hidden_width:
            raise OutcomeRankerError("public hidden shape differs from ranker width")
        if option_embeddings.ndim != 2 or option_embeddings.shape[1] != self.option_width:
            raise OutcomeRankerError("option embedding shape differs from ranker width")
        if not torch.isfinite(public_hidden).all() or not torch.isfinite(option_embeddings).all():
            raise OutcomeRankerError("ranker inputs contain nonfinite values")
        if option_offsets.ndim != 1 or option_offsets.shape[0] != public_hidden.shape[0] + 1:
            raise OutcomeRankerError("option offsets must have one entry per state plus one")
        if option_offsets.dtype != torch.long:
            raise OutcomeRankerError("option offsets must be int64")
        if int(option_offsets[0]) != 0 or int(option_offsets[-1]) != option_embeddings.shape[0]:
            raise OutcomeRankerError("option offsets do not cover the option tensor")
        lengths = option_offsets[1:] - option_offsets[:-1]
        if (lengths < 0).any():
            raise OutcomeRankerError("option offsets must be nondecreasing")
        if (lengths == 0).any():
            raise OutcomeRankerError("ranker groups cannot be empty")
        repeated_hidden = torch.repeat_interleave(public_hidden, lengths, dim=0)
        scores = self.head(torch.cat((repeated_hidden, option_embeddings), dim=-1)).squeeze(-1)
        if not torch.isfinite(scores).all():
            raise OutcomeRankerError("ranker logits are nonfinite")
        return scores

    @staticmethod
    def mask_scores(scores: Tensor, available: Tensor) -> Tensor:
        if scores.ndim != 1 or available.dtype != torch.bool or available.shape != scores.shape:
            raise OutcomeRankerError("score and legal-mask shapes differ")
        if not torch.isfinite(scores).all():
            raise OutcomeRankerError("nonfinite ranker score")
        return scores.masked_fill(~available, float("-inf"))


def choose_legal_option(
    scores: Tensor,
    available: Tensor,
    fallback_index: int = 0,
) -> int:
    """Return a deterministic legal argmax; nonfinite legal scores fail closed."""

    if scores.ndim != 1 or available.dtype != torch.bool or scores.shape != available.shape:
        raise OutcomeRankerError("score and legal-mask shapes differ")
    legal = torch.nonzero(available, as_tuple=False).flatten().tolist()
    if not legal:
        raise ContractViolation("no legal option is available")
    masked = OutcomeRankerV1.mask_scores(scores, available)
    # torch.argmax is intentionally first-index deterministic for equal scores.
    return int(torch.argmax(masked).item())


def deterministic_legal_fallback(available: Tensor, fallback_index: int = 0) -> int:
    """Return the fixed legal fallback used by an outer inference adapter."""

    if available.ndim != 1 or available.dtype != torch.bool:
        raise OutcomeRankerError("legal fallback mask must be a one-dimensional bool tensor")
    legal = torch.nonzero(available, as_tuple=False).flatten().tolist()
    if not legal:
        raise ContractViolation("no legal option is available")
    return fallback_index if fallback_index in legal else int(legal[0])


def grouped_ranker_loss(
    scores: Tensor,
    target: Tensor,
    target_mask: Tensor,
    group_offsets: Tensor,
    *,
    target_weight: Tensor | None = None,
    pairwise_weight: float = 0.25,
    temperature: float = 0.25,
    semantic_fingerprints: Sequence[str] | None = None,
    semantic_equivalence_keys: Sequence[str] | None = None,
) -> Tensor:
    """State-normalized uncertainty-weighted Huber plus Bradley-Terry loss."""

    if scores.ndim != 1 or target.ndim != 1 or target_mask.ndim != 1:
        raise OutcomeRankerError("ranker scores, targets, and masks must be one-dimensional")
    if scores.shape != target.shape or scores.shape != target_mask.shape:
        raise OutcomeRankerError("ranker targets and masks must match scores")
    if not scores.is_floating_point() or not target.is_floating_point():
        raise OutcomeRankerError("ranker scores and targets must be floating-point tensors")
    if not torch.isfinite(scores).all() or not torch.isfinite(target).all():
        raise OutcomeRankerError("ranker scores and targets must be finite")
    if group_offsets.dtype != torch.long or group_offsets.ndim != 1:
        raise OutcomeRankerError("group offsets must be one-dimensional int64")
    if group_offsets.numel() < 2 or (group_offsets < 0).any():
        raise OutcomeRankerError("group offsets must be nonnegative and contain at least one group")
    if (group_offsets[1:] < group_offsets[:-1]).any():
        raise OutcomeRankerError("group offsets must be nondecreasing")
    if group_offsets[0].item() != 0 or group_offsets[-1].item() != scores.numel():
        raise OutcomeRankerError("group offsets do not cover scores")
    try:
        temperature_value = float(temperature)
        pairwise_weight_value = float(pairwise_weight)
    except (TypeError, ValueError) as error:
        raise OutcomeRankerError("pairwise temperature/weight must be finite scalars") from error
    if (
        isinstance(temperature, bool)
        or isinstance(pairwise_weight, bool)
        or not math.isfinite(temperature_value)
        or not math.isfinite(pairwise_weight_value)
        or temperature_value <= 0
        or pairwise_weight_value < 0
    ):
        raise OutcomeRankerError("pairwise temperature/weight must be finite and nonnegative")
    if target_mask.dtype != torch.bool:
        raise OutcomeRankerError("target mask must be bool")
    if target_weight is None:
        weights = torch.ones_like(scores)
    else:
        if (
            target_weight.ndim != 1
            or target_weight.shape != scores.shape
            or not target_weight.is_floating_point()
            or not torch.isfinite(target_weight).all()
            or (target_weight < 0).any()
        ):
            raise OutcomeRankerError("target weights are invalid")
        weights = target_weight
    if semantic_fingerprints is not None and len(semantic_fingerprints) != scores.numel():
        raise OutcomeRankerError("semantic fingerprint sidecar does not match scores")
    if semantic_equivalence_keys is not None and len(semantic_equivalence_keys) != scores.numel():
        raise OutcomeRankerError("semantic equivalence sidecar does not match scores")
    pair_keys = semantic_equivalence_keys or semantic_fingerprints

    group_huber: list[Tensor] = []
    group_pairwise: list[Tensor] = []
    for start, end in zip(group_offsets[:-1].tolist(), group_offsets[1:].tolist()):
        valid = target_mask[start:end]
        if not valid.any():
            raise OutcomeRankerError("empty legal target group")
        positions = torch.nonzero(valid, as_tuple=False).flatten().tolist()
        if pair_keys is not None:
            representative_positions: list[int] = []
            seen_pair_keys: set[str] = set()
            for local_position in positions:
                key = pair_keys[start + local_position]
                if key in seen_pair_keys:
                    continue
                seen_pair_keys.add(key)
                representative_positions.append(local_position)
        else:
            representative_positions = positions
        representative_indexes = [start + position for position in representative_positions]
        local_weights = weights[representative_indexes]
        if not (local_weights > 0).all():
            raise OutcomeRankerError("legal target group has nonpositive uncertainty weight")
        # Normalize within each state, then average groups: legal-set width cannot
        # dominate the batch.  A factual equivalence class contributes one pooled
        # representative to both terms, so alias multiplicity cannot change loss.
        local_weights = local_weights / local_weights.mean().clamp_min(1e-8)
        local_scores = scores[representative_indexes]
        local_target = target[representative_indexes]
        huber_component = (
            (F.huber_loss(local_scores, local_target, reduction="none") * local_weights).sum()
            / local_weights.sum().clamp_min(1e-8)
        )
        if not torch.isfinite(huber_component).all().item():
            raise OutcomeRankerError("grouped Huber loss component is nonfinite")
        group_huber.append(huber_component)
        if pairwise_weight_value == 0:
            continue
        pair_terms: list[Tensor] = []
        pair_weights: list[Tensor] = []
        local_weight_by_position = {
            local_position: local_weights[position]
            for position, local_position in enumerate(representative_positions)
        }
        for left_position, left_local in enumerate(representative_positions):
            for right_local in representative_positions[left_position + 1 :]:
                left = start + left_local
                right = start + right_local
                if pair_keys is not None and pair_keys[left] == pair_keys[right]:
                    continue
                delta = target[left] - target[right]
                if float(delta) == 0.0:
                    continue
                confidence = torch.sqrt(
                    local_weight_by_position[left_local] * local_weight_by_position[right_local]
                )
                pair_weight = confidence * min(2.0, abs(float(delta)) + 0.25)
                pair_term = F.softplus(
                    -delta.sign() * (scores[left] - scores[right]) / temperature_value
                )
                if not torch.isfinite(pair_weight).all().item() or not torch.isfinite(pair_term).all().item():
                    raise OutcomeRankerError("Bradley-Terry loss component is nonfinite")
                pair_weights.append(pair_weight)
                pair_terms.append(pair_term)
        if pair_terms:
            pair_weight_tensor = torch.stack(pair_weights)
            group_pairwise.append(
                (torch.stack(pair_terms) * pair_weight_tensor).sum()
                / pair_weight_tensor.sum().clamp_min(1e-8)
            )
    huber_loss = torch.stack(group_huber).mean()
    if not torch.isfinite(huber_loss).all().item():
        raise OutcomeRankerError("grouped Huber loss is nonfinite")
    if pairwise_weight_value == 0 or not group_pairwise:
        return huber_loss
    pairwise_loss = torch.stack(group_pairwise).mean()
    if not torch.isfinite(pairwise_loss).all().item():
        raise OutcomeRankerError("grouped Bradley-Terry loss is nonfinite")
    loss = huber_loss + pairwise_weight_value * pairwise_loss
    if not torch.isfinite(loss).all().item():
        raise OutcomeRankerError("grouped ranker loss is nonfinite")
    return loss


def _tupleize(value: Any) -> Any:
    if isinstance(value, list):
        return tuple(_tupleize(item) for item in value)
    if isinstance(value, dict):
        return {key: _tupleize(item) for key, item in value.items()}
    return value


def _projected_decision(value: Mapping[str, Any]) -> ProjectedDecisionV1:
    if not isinstance(value, Mapping):
        raise OutcomeRankerError("public_tensor.projected_decision must be an object")
    model_value = value.get("model_input")
    transport_value = value.get("transport_sidecar")
    if not isinstance(model_value, Mapping) or not isinstance(transport_value, Mapping):
        raise OutcomeRankerError("projected decision lacks G2 model/transport records")
    model_fields = {field.name for field in fields(ModelInputV1)}
    transport_fields = {field.name for field in fields(OptionTransportMapV1)}
    if set(model_value) != model_fields or set(transport_value) != transport_fields:
        raise OutcomeRankerError("projected decision fields differ from the frozen G2 schema")
    if int(value.get("schema_version", 0)) != 1:
        raise OutcomeRankerError("projected decision schema version differs")
    return ProjectedDecisionV1(
        model=ModelInputV1(**_tupleize(dict(model_value))),
        transport=OptionTransportMapV1(**_tupleize(dict(transport_value))),
        schema_version=int(value.get("schema_version", 0)),
    )


def _hidden_from_history(public_tensor: Mapping[str, Any]) -> Tensor:
    tokens = public_tensor.get("history_tokens")
    if not isinstance(tokens, list) or len(tokens) != 1 or not isinstance(tokens[0], Mapping):
        raise OutcomeRankerError("public tensor must contain exactly one history token")
    token = tokens[0]
    expected_fields = {
        "history_schema_version",
        "history_source",
        "history_steps",
        "prefix_digest",
        "model_schema_sha256",
        "public_hidden",
    }
    if set(token) != expected_fields:
        raise OutcomeRankerError("history token fields differ from the public-prefix contract")
    provenance = public_tensor.get("prefix_provenance")
    if not isinstance(provenance, Mapping):
        raise OutcomeRankerError("public tensor lacks prefix provenance")
    if token["prefix_digest"] != provenance.get("prefix_digest"):
        raise OutcomeRankerError("history token prefix digest is not bound to provenance")
    if token["model_schema_sha256"] != G2_MODEL_SCHEMA_SHA256:
        raise OutcomeRankerError("history token model schema differs from the pinned G2 schema")
    if token["history_source"] != provenance.get("history_source") or token["history_steps"] != provenance.get("history_steps"):
        raise OutcomeRankerError("history token metadata is not bound to prefix provenance")
    hidden = tokens[0].get("public_hidden")
    if not isinstance(hidden, Mapping) or hidden.get("shape") != [1, 160]:
        raise OutcomeRankerError("history token must contain pre-root public hidden [1,160]")
    values = hidden.get("values")
    if not isinstance(values, list) or len(values) != 1 or len(values[0]) != 160:
        raise OutcomeRankerError("history token hidden values have the wrong shape")
    result = torch.tensor(values, dtype=torch.float32)
    if not torch.isfinite(result).all():
        raise OutcomeRankerError("history token hidden is nonfinite")
    return result


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(
        character in "0123456789abcdef" for character in value
    )


def _validate_prefix_provenance(public_tensor: Mapping[str, Any]) -> None:
    provenance = public_tensor.get("prefix_provenance")
    if not isinstance(provenance, Mapping):
        raise OutcomeRankerError("public tensor prefix provenance is required")
    expected_fields = {
        "source",
        "prefix_digest",
        "history_schema_version",
        "history_source",
        "history_steps",
        "initial_hidden_source",
        "model_schema_sha256",
        "full_public_prefix_retained",
    }
    if set(provenance) != expected_fields:
        raise OutcomeRankerError("prefix provenance fields differ from the frozen contract")
    if provenance["source"] != "ACTOR_OWNED_PUBLIC_PREFIX":
        raise OutcomeRankerError("prefix source is not actor-owned public history")
    if not _is_sha256(provenance["prefix_digest"]):
        raise OutcomeRankerError("prefix digest is not a lowercase SHA-256")
    if provenance["history_schema_version"] != 1 or provenance["model_schema_sha256"] != G2_MODEL_SCHEMA_SHA256:
        raise OutcomeRankerError("prefix history/model schema provenance differs")
    if provenance["history_source"] not in {
        "RECORDED_PUBLIC_GRU_HIDDEN",
        "PRODUCTION_INITIAL_HIDDEN_EPISODE_START",
    }:
        raise OutcomeRankerError("prefix history source is unsupported")
    if not isinstance(provenance["history_steps"], int) or isinstance(provenance["history_steps"], bool) or provenance["history_steps"] < 0:
        raise OutcomeRankerError("prefix history steps are invalid")
    if provenance["full_public_prefix_retained"] is not False:
        raise OutcomeRankerError("raw public prefix retention is forbidden")
    if provenance["initial_hidden_source"] not in {
        "RECORDED_PUBLIC_GRU_HIDDEN",
        "PRODUCTION_INITIAL_HIDDEN_EPISODE_START",
    }:
        raise OutcomeRankerError("prefix initial hidden source is unsupported")
    if (
        provenance["history_source"], provenance["initial_hidden_source"]
    ) not in {
        ("RECORDED_PUBLIC_GRU_HIDDEN", "PRODUCTION_INITIAL_HIDDEN_EPISODE_START"),
        ("PRODUCTION_INITIAL_HIDDEN_EPISODE_START", "PRODUCTION_INITIAL_HIDDEN_EPISODE_START"),
    }:
        raise OutcomeRankerError("prefix history/initial-hidden provenance pair is unsupported")


def _validate_schema_shape(dataset: Mapping[str, Any]) -> None:
    if dataset.get("schema_version") != 1:
        raise OutcomeRankerError("dataset schema_version must be 1")
    for field in ("run", "state_groups"):
        if field not in dataset:
            raise OutcomeRankerError(f"dataset missing required top-level field: {field}")
    run = dataset["run"]
    if not isinstance(run, Mapping) or run.get("label_firewall") != "COUNTERFACTUAL_NATIVE_ONLY_NOT_PPO_ROLLOUT":
        raise OutcomeRankerError("dataset label firewall differs from the frozen schema")
    if run.get("model_schema_sha256") != G2_MODEL_SCHEMA_SHA256 or model_schema_sha256() != G2_MODEL_SCHEMA_SHA256:
        raise OutcomeRankerError("dataset run model schema hash differs from frozen G2")
    if run.get("g2_package_sha256") != G2_PACKAGE_SHA256:
        raise OutcomeRankerError("dataset run G2 package hash is not pinned")
    if run.get("bc_trunk_checkpoint_sha256") != BC_TRUNK_CHECKPOINT_SHA256:
        raise OutcomeRankerError("dataset run BC checkpoint hash is not pinned")
    if run.get("bc_trunk_state_sha256") != BC_TRUNK_STATE_SHA256:
        raise OutcomeRankerError("dataset run BC trunk state hash is not pinned")
    if run.get("trunk_mode") != "FROZEN_BC_EPOCH4_HEAD_ONLY":
        raise OutcomeRankerError("dataset run is not the frozen Gate-1 trunk mode")
    groups = dataset["state_groups"]
    if not isinstance(groups, list) or not groups:
        raise OutcomeRankerError("dataset state_groups must be a nonempty array")
    schema_path = Path(__file__).with_name("counterfactual_action_dataset_v1.schema.json")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    try:
        import jsonschema
    except ImportError:
        script = (
            "const fs=require('fs');"
            "const Ajv2020=require('ajv/dist/2020');"
            f"const schema=JSON.parse(fs.readFileSync({json.dumps(str(schema_path))},'utf8'));"
            "const data=JSON.parse(fs.readFileSync(0,'utf8'));"
            "const validate=new Ajv2020({allErrors:true,strict:false}).compile(schema);"
            "if(validate(data)) process.stdout.write('[]');"
            "else {process.stdout.write(JSON.stringify(validate.errors));process.exitCode=1;}"
        )
        try:
            result = subprocess.run(
                ["node", "-e", script],
                input=json.dumps(dataset),
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise OutcomeRankerError(f"schema validator unavailable: {error}") from error
        if result.returncode:
            try:
                errors = json.loads(result.stdout)
            except (TypeError, json.JSONDecodeError) as error:
                raise OutcomeRankerError(
                    f"Ajv schema validation failed: {result.stderr[-500:]}"
                ) from error
            detail = "; ".join(
                f"{item.get('instancePath', '$')}: {item.get('message', 'schema error')}"
                for item in errors[:5]
            )
            raise OutcomeRankerError(f"dataset fails counterfactual schema: {detail}")
        return
    errors = list(jsonschema.Draft202012Validator(schema).iter_errors(dataset))
    if errors:
        detail = "; ".join(error.message for error in errors[:5])
        raise OutcomeRankerError(f"dataset fails counterfactual schema: {detail}")


def _target_weight(stderr: float, visits: int) -> float:
    if not math.isfinite(stderr) or stderr < 0 or visits <= 0:
        raise OutcomeRankerError("replicate uncertainty/count is invalid")
    # Inverse empirical variance is bounded; grouped loss normalizes this again
    # within each state so a large legal set or duplicate cannot dominate.
    return min(25.0, max(0.25, 1.0 / (stderr * stderr + 1e-3)))


def _close(left: float, right: float, *, tolerance: float = 1e-6) -> bool:
    return math.isfinite(left) and math.isfinite(right) and abs(left - right) <= tolerance


def _derived_summary(rewards: Sequence[int]) -> dict[str, Any]:
    if not rewards or any(reward not in (-1, 0, 1) for reward in rewards):
        raise OutcomeRankerError("raw action outcomes must be nonempty W/D/L rewards")
    count = len(rewards)
    mean = sum(rewards) / count
    if count == 1:
        stderr = 0.0
    else:
        stderr = math.sqrt(sum((reward - mean) ** 2 for reward in rewards) / (count * (count - 1)))
    return {
        "replicate_count": count,
        "wdl_counts": {
            "W": sum(reward == 1 for reward in rewards),
            "D": sum(reward == 0 for reward in rewards),
            "L": sum(reward == -1 for reward in rewards),
        },
        "mean_reward": mean,
        "reward_stderr": stderr,
        "ci95_low": max(-1.0, mean - 1.96 * stderr),
        "ci95_high": min(1.0, mean + 1.96 * stderr),
    }


def _derived_equivalence_summary(clusters: Sequence[Sequence[int]]) -> dict[str, Any]:
    """Pool duplicate options inside each paired world, then across worlds."""

    if not clusters or any(not cluster for cluster in clusters):
        raise OutcomeRankerError("equivalence class has an empty determinization cluster")
    if any(reward not in (-1, 0, 1) for cluster in clusters for reward in cluster):
        raise OutcomeRankerError("equivalence class contains a non-WDL branch")
    means = [sum(cluster) / len(cluster) for cluster in clusters]
    particle_count = len(means)
    mean = sum(means) / particle_count
    stderr = 0.0 if particle_count == 1 else math.sqrt(
        sum((value - mean) ** 2 for value in means) / (particle_count * (particle_count - 1))
    )
    branches = [reward for cluster in clusters for reward in cluster]
    disagreement_count = sum(len(set(cluster)) > 1 for cluster in clusters)
    return {
        "replicate_count": particle_count,
        "branch_count": len(branches),
        "particle_count": particle_count,
        "sample_unit": "PAIRED_DETERMINIZATION_EQUIVALENCE_CLUSTER_MEAN",
        "disagreement": bool(disagreement_count),
        "disagreement_count": disagreement_count,
        "wdl_counts": {
            "W": sum(reward == 1 for reward in branches),
            "D": sum(reward == 0 for reward in branches),
            "L": sum(reward == -1 for reward in branches),
        },
        "mean_reward": mean,
        "reward_stderr": stderr,
        "ci95_low": max(-1.0, mean - 1.96 * stderr),
        "ci95_high": min(1.0, mean + 1.96 * stderr),
    }


def _terminal_reward(terminal: Mapping[str, Any], root_player: int) -> int:
    winner = terminal.get("winner_player")
    is_draw = terminal.get("is_draw")
    if not isinstance(is_draw, bool):
        raise OutcomeRankerError("terminal draw flag is invalid")
    if is_draw:
        if winner is not None:
            raise OutcomeRankerError("draw terminal result cannot name a winner")
        return 0
    if winner not in (0, 1):
        raise OutcomeRankerError("non-draw terminal result must name one winner")
    return 1 if winner == root_player else -1


def _semantic_action_id(ordering: str, fingerprints: Sequence[str] | str) -> str:
    path = [fingerprints] if isinstance(fingerprints, str) else list(fingerprints)
    if not path or any(not _is_sha256(fingerprint) for fingerprint in path):
        raise OutcomeRankerError("semantic action fingerprint path is invalid")
    return stable_hash({"ordering": ordering, "semantic_path": path})


def _semantic_action_fingerprint(path: Sequence[Mapping[str, Any]]) -> str:
    if not path or any(not isinstance(option, Mapping) for option in path):
        raise OutcomeRankerError("raw action semantic path is incomplete")
    return stable_hash([dict(option) for option in path])


def _feature_row(
    *,
    index: int,
    categorical_names: Sequence[str],
    categorical_values: Sequence[Sequence[int]],
    categorical_missing: Sequence[Sequence[bool]],
    numeric_names: Sequence[str],
    numeric_values: Sequence[Sequence[float]],
    numeric_missing: Sequence[Sequence[bool]],
) -> dict[str, Any] | None:
    """Resolve one public endpoint without retaining its entity/index identity."""

    if index == -1:
        return None
    if index < 0 or index >= len(categorical_values):
        raise OutcomeRankerError("option endpoint entity index is outside the public tensor")
    if not (
        len(categorical_values) == len(categorical_missing)
        and len(numeric_values) == len(numeric_missing) == len(categorical_values)
    ):
        raise OutcomeRankerError("public endpoint feature rows have inconsistent lengths")
    if (
        len(categorical_names) != len(categorical_values[index])
        or len(categorical_names) != len(categorical_missing[index])
        or len(numeric_names) != len(numeric_values[index])
        or len(numeric_names) != len(numeric_missing[index])
    ):
        raise OutcomeRankerError("public endpoint feature columns have inconsistent lengths")
    categorical = tuple(
        (str(name), int(value), bool(missing))
        for name, value, missing in zip(
            categorical_names, categorical_values[index], categorical_missing[index]
        )
    )
    numeric = tuple(
        (str(name), float(value), bool(missing))
        for name, value, missing in zip(
            numeric_names, numeric_values[index], numeric_missing[index]
        )
    )
    if any(not math.isfinite(value) for _, value, _ in numeric):
        raise OutcomeRankerError("public endpoint feature row is nonfinite")
    return {"categorical": categorical, "numeric": numeric}


def _entity_semantic_path(model: ModelInputV1, endpoint_index: int) -> tuple[Mapping[str, Any], ...] | None:
    """Return endpoint-to-root public semantics, rejecting malformed topology."""

    entity_count = len(model.entity_categorical_values)
    if not (
        len(model.entity_categorical_missing) == entity_count
        and len(model.entity_numeric_values) == entity_count
        and len(model.entity_numeric_missing) == entity_count
        and len(model.entity_parent_indices) == entity_count
        and len(model.entity_energy_offsets) == entity_count + 1
    ):
        raise OutcomeRankerError("public entity topology has inconsistent lengths")
    if endpoint_index != -1 and (endpoint_index < 0 or endpoint_index >= entity_count):
        raise OutcomeRankerError("public endpoint entity index is outside the public tensor")

    parent_indices: list[int] = []
    for parent in model.entity_parent_indices:
        if isinstance(parent, bool) or not isinstance(parent, int):
            raise OutcomeRankerError("public entity parent index is not an integer")
        if parent != -1 and (parent < 0 or parent >= entity_count):
            raise OutcomeRankerError("public entity parent index is unknown")
        parent_indices.append(parent)

    offsets = list(model.entity_energy_offsets)
    if any(isinstance(offset, bool) or not isinstance(offset, int) for offset in offsets):
        raise OutcomeRankerError("public entity energy offset is not an integer")
    if not offsets or offsets[0] != 0 or offsets[-1] != len(model.entity_energy_values):
        raise OutcomeRankerError("public entity energy offsets do not cover values")
    if any(offset < 0 for offset in offsets) or any(
        right < left for left, right in zip(offsets, offsets[1:])
    ):
        raise OutcomeRankerError("public entity energy offsets are not nondecreasing")
    if any(isinstance(value, bool) or not isinstance(value, int) for value in model.entity_energy_values):
        raise OutcomeRankerError("public entity energy value is not an integer")
    if any(value < 0 or value > 11 for value in model.entity_energy_values):
        raise OutcomeRankerError("public entity energy value is outside enum range 0..11")

    # Validate every component, not only the selected endpoint, so an unrelated
    # cycle cannot make the key depend on which option happened to be queried.
    for start in range(entity_count):
        seen: set[int] = set()
        current = start
        while current != -1:
            if current in seen:
                raise OutcomeRankerError("public entity parent path contains a cycle")
            seen.add(current)
            current = parent_indices[current]

    if endpoint_index == -1:
        return None
    path: list[Mapping[str, Any]] = []
    current = endpoint_index
    while current != -1:
        start = offsets[current]
        end = offsets[current + 1]
        path.append(
            {
                "features": _feature_row(
                    index=current,
                    categorical_names=model.entity_categorical_names,
                    categorical_values=model.entity_categorical_values,
                    categorical_missing=model.entity_categorical_missing,
                    numeric_names=model.entity_numeric_names,
                    numeric_values=model.entity_numeric_values,
                    numeric_missing=model.entity_numeric_missing,
                ),
                "energy_values": tuple(model.entity_energy_values[start:end]),
            }
        )
        current = parent_indices[current]
    return tuple(path)


def semantic_equivalence_key(
    request: Mapping[str, Any],
    options: Sequence[Mapping[str, Any]],
    model: ModelInputV1,
    option_index: int,
) -> str:
    """Return the factual, order-invariant class key used only to pool labels.

    The key deliberately excludes option order, raw positions, entity serials,
    transport IDs, and action/fingerprint hashes.  Endpoint card identity and
    state come from the resolved public G2 entity rows, not ``option.card_id``.
    """

    if not isinstance(request, Mapping) or not isinstance(options, Sequence):
        raise OutcomeRankerError("semantic equivalence input is malformed")
    if option_index < 0 or option_index >= len(options):
        raise OutcomeRankerError("semantic equivalence option index is outside the request")
    option = options[option_index]
    if not isinstance(option, Mapping):
        raise OutcomeRankerError("semantic equivalence option is not an object")
    if len(model.option_categorical_values) != len(options):
        raise OutcomeRankerError("G2 option rows do not cover the request options")
    if not (
        len(model.option_categorical_missing) == len(options)
        and len(model.option_numeric_values) == len(options)
        and len(model.option_numeric_missing) == len(options)
        and len(model.option_source_entity_indices) == len(options)
        and len(model.option_target_entity_indices) == len(options)
    ):
        raise OutcomeRankerError("G2 option sidecars do not cover the request options")
    categorical = tuple(
        (str(name), int(value), bool(missing))
        for name, value, missing in zip(
            model.option_categorical_names,
            model.option_categorical_values[option_index],
            model.option_categorical_missing[option_index],
        )
    )
    numeric = tuple(
        (str(name), float(value), bool(missing))
        for name, value, missing in zip(
            model.option_numeric_names,
            model.option_numeric_values[option_index],
            model.option_numeric_missing[option_index],
        )
    )
    if any(not math.isfinite(value) for _, value, _ in numeric):
        raise OutcomeRankerError("G2 option numeric features are nonfinite")
    key_material = {
        "request": {
            "selection_type": request.get("selection_type"),
            "selection_context": request.get("selection_context"),
            "min_count": request.get("min_count"),
            "max_count": request.get("max_count"),
            "ordering": request.get("ordering"),
        },
        "option": {
            "categorical": categorical,
            "numeric": numeric,
            "is_stop": bool(option.get("is_stop", False)),
        },
        "source": _entity_semantic_path(
            model, int(model.option_source_entity_indices[option_index])
        ),
        "target": _entity_semantic_path(
            model, int(model.option_target_entity_indices[option_index])
        ),
    }
    return stable_hash(key_material)


def load_counterfactual_dataset(
    path: str | Path,
    frozen_g2: PTCGPolicyV1,
    *,
    device: torch.device | str = "cpu",
) -> RankerBatch:
    """Load strict-schema rows and derive ranker tensors through frozen G2.

    The schema intentionally stores the public ``ProjectedDecisionV1`` rather
    than arbitrary tensors.  This loader reconstructs that record, executes
    the frozen G2 forward once per state, and joins singleton action aggregates
    by stable semantic fingerprint.  Compound action paths are rejected until
    a path-conditioned Q contract is separately approved.
    """

    dataset = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(dataset, Mapping):
        raise OutcomeRankerError("dataset root must be an object")
    _validate_schema_shape(dataset)
    _validate_gate1_trunk(frozen_g2)
    frozen_g2.eval()
    hidden_rows: list[Tensor] = []
    option_rows: list[Tensor] = []
    available_rows: list[Tensor] = []
    target_rows: list[Tensor] = []
    stderr_rows: list[Tensor] = []
    weight_rows: list[Tensor] = []
    mask_rows: list[Tensor] = []
    option_offsets = [0]
    group_offsets = [0]
    state_ids: list[str] = []
    action_ids: list[str] = []
    fingerprints: list[str] = []
    equivalence_keys: list[str] = []
    equivalence_metadata_rows: list[tuple[Mapping[str, Any], ...]] = []
    seen_state_ids: set[str] = set()

    for group in dataset["state_groups"]:
        if not isinstance(group, Mapping):
            raise OutcomeRankerError("state group must be an object")
        state_id = group.get("state_group_id")
        split_key = group.get("split_group_key")
        if not isinstance(state_id, str) or not state_id or state_id in seen_state_ids:
            raise OutcomeRankerError("state group identity is missing or duplicated")
        if not isinstance(split_key, str) or not split_key:
            raise OutcomeRankerError("state group split key is missing")
        root_player = group.get("root_player")
        acting_player = group.get("acting_player")
        if root_player not in (0, 1) or acting_player not in (0, 1) or root_player != acting_player:
            raise OutcomeRankerError("root/acting player orientation is missing or inconsistent")
        if not _is_sha256(group.get("public_state_sha256")):
            raise OutcomeRankerError("public state digest is not a lowercase SHA-256")
        seen_state_ids.add(state_id)
        public_tensor = group.get("public_tensor")
        request = group.get("request")
        replicates = group.get("replicates")
        aggregates = group.get("action_aggregates")
        if not isinstance(public_tensor, Mapping) or not isinstance(request, Mapping):
            raise OutcomeRankerError("state group lacks public tensor/request")
        if not isinstance(replicates, list) or not replicates:
            raise OutcomeRankerError("state group has no complete raw replicates")
        if not isinstance(aggregates, list):
            raise OutcomeRankerError("state group action_aggregates must be an array")
        if (
            public_tensor.get("public_only") is not True
            or public_tensor.get("raw_observation_retained") is not False
            or public_tensor.get("forbidden_actor_features_absent") is not True
            or public_tensor.get("feature_source") != "G2_PROJECTED_PUBLIC_ONLY"
        ):
            raise OutcomeRankerError("public tensor boundary flags differ from schema")
        if public_tensor.get("model_schema_sha256") != G2_MODEL_SCHEMA_SHA256:
            raise OutcomeRankerError("public tensor model schema hash differs from frozen G2")
        if "search_begin_input" in public_tensor or "hidden_determinization_output" in public_tensor:
            raise OutcomeRankerError("search/determinization fields are forbidden in public tensor")
        _validate_prefix_provenance(public_tensor)
        decision = _projected_decision(public_tensor.get("projected_decision", {}))
        hidden = _hidden_from_history(public_tensor)

        options = request.get("options")
        ordering = request.get("ordering")
        request_id = request.get("request_id")
        if not isinstance(options, list) or not options or ordering not in ("ORDERED", "UNORDERED"):
            raise OutcomeRankerError("request options/ordering are invalid or empty")
        if not isinstance(request_id, str) or not request_id:
            raise OutcomeRankerError("request identity is missing")
        if request.get("min_count") != 1 or request.get("max_count") != 1:
            raise OutcomeRankerError("COMPOUND_ACTION_PATH_NOT_SUPPORTED_BY_OPTION_Q_V1")
        if group.get("compound_coverage") != "SINGLE_CHOICE":
            raise OutcomeRankerError("Gate-1 loader requires complete singleton action coverage")
        transport = decision.transport
        expected_fingerprints: tuple[str, ...] = tuple(
            option.get("semantic_fingerprint") if isinstance(option, Mapping) else ""
            for option in options
        )
        if any(not _is_sha256(fingerprint) for fingerprint in expected_fingerprints):
            raise OutcomeRankerError("request semantic fingerprint is missing or malformed")
        if transport.request_id != request_id:
            raise OutcomeRankerError("request identity is not bound to ProjectedDecisionV1.transport")
        if tuple(transport.semantic_fingerprints) != expected_fingerprints:
            raise OutcomeRankerError("transport semantic fingerprints/order differ from request")
        if len(transport.original_indices) != len(options) or sorted(transport.original_indices) != list(range(len(options))):
            raise OutcomeRankerError("transport original indices do not cover the exact option order")
        if len(options) != len(decision.model.option_available_mask):
            raise OutcomeRankerError("request option count differs from projected G2 option count")
        option_equivalence_keys = tuple(
            semantic_equivalence_key(request, options, decision.model, option_index)
            for option_index in range(len(options))
        )
        batch = collate_projected((decision,), device=device)
        hidden_device = hidden.to(device)
        with torch.inference_mode():
            output = frozen_g2(batch, hidden_device)
        for output_name in ("hidden", "option_embeddings", "option_logits", "values"):
            output_value = getattr(output, output_name)
            if not torch.isfinite(output_value).all():
                raise OutcomeRankerError(f"frozen G2 emitted nonfinite {output_name}")
        if batch.option_available.dtype != torch.bool or not batch.option_available.any():
            raise OutcomeRankerError("state group has no legal options")
        available = [bool(value) for value in batch.option_available.tolist()]
        available_indexes = [index for index, value in enumerate(available) if value]
        if group.get("legal_action_count") != len(available_indexes) or group.get("enumerated_action_count") != len(available_indexes):
            raise OutcomeRankerError("legal/enumerated action counts do not match the projected mask")
        if group.get("action_enumeration_complete") is not True:
            raise OutcomeRankerError("complete legal action enumeration is not asserted")

        original_to_option = {original: index for index, original in enumerate(transport.original_indices)}
        replicate_ids: set[int] = set()
        determinization_ids: set[str] = set()
        rewards_by_replicate: dict[int, dict[str, list[int]]] = {}
        equivalence_rewards_by_replicate: dict[int, dict[str, list[int]]] = {}
        for replicate in replicates:
            if not isinstance(replicate, Mapping):
                raise OutcomeRankerError("replicate must be an object")
            replicate_id = replicate.get("replicate_id")
            if isinstance(replicate_id, bool) or not isinstance(replicate_id, int) or replicate_id in replicate_ids:
                raise OutcomeRankerError("replicate identity is missing or duplicated")
            replicate_ids.add(replicate_id)
            determinization_id = replicate.get("determinization_id")
            if (
                not isinstance(determinization_id, str)
                or not determinization_id
                or determinization_id in determinization_ids
            ):
                raise OutcomeRankerError("replicate determinization_id is missing or duplicated")
            determinization_ids.add(determinization_id)
            actions = replicate.get("actions")
            if not isinstance(actions, list) or len(actions) != len(available_indexes):
                raise OutcomeRankerError("replicate does not contain the complete legal action set")
            rewards_by_replicate[replicate_id] = {}
            equivalence_rewards_by_replicate[replicate_id] = {}
            seen_originals: set[int] = set()
            for action in actions:
                if not isinstance(action, Mapping):
                    raise OutcomeRankerError("raw action result must be an object")
                transport_indices = action.get("transport_original_indices")
                if not isinstance(transport_indices, list) or len(transport_indices) != 1:
                    raise OutcomeRankerError("Gate-1 raw actions must be singleton transport paths")
                original = transport_indices[0]
                if isinstance(original, bool) or not isinstance(original, int) or original in seen_originals:
                    raise OutcomeRankerError("raw action transport index is missing or duplicated")
                option_index = original_to_option.get(original)
                if option_index is None or not available[option_index]:
                    raise OutcomeRankerError("raw action transport index is not a legal projected option")
                seen_originals.add(original)
                fingerprint = expected_fingerprints[option_index]
                path = action.get("semantic_path")
                if not isinstance(path, list) or len(path) != 1 or not isinstance(path[0], Mapping):
                    raise OutcomeRankerError("raw action semantic path is incomplete")
                if path[0].get("semantic_fingerprint") != fingerprint:
                    raise OutcomeRankerError("raw action semantic path differs from transport fingerprint")
                if dict(path[0]) != dict(options[option_index]):
                    raise OutcomeRankerError("raw action semantic path differs from request option")
                expected_action_id = _semantic_action_id(
                    ordering, [str(option.get("semantic_fingerprint")) for option in path]
                )
                if action.get("action_id") != expected_action_id:
                    raise OutcomeRankerError("raw action_id is not bound to ordering/fingerprint transport")
                if action.get("semantic_action_fingerprint") != _semantic_action_fingerprint(path):
                    raise OutcomeRankerError("raw semantic_action_fingerprint is not bound to the full semantic path")
                terminal = action.get("terminal_engine_result")
                if not isinstance(terminal, Mapping):
                    raise OutcomeRankerError("raw action terminal result is missing")
                reward = _terminal_reward(terminal, root_player)
                supplied_reward = action.get("reward_for_actor")
                if isinstance(supplied_reward, bool) or not isinstance(supplied_reward, int) or supplied_reward != reward:
                    raise OutcomeRankerError("raw reward_for_actor disagrees with terminal/root orientation")
                if action.get("completed") is not True or action.get("fallback_used") is not False or action.get("nonfinite") is not False or action.get("error") is not None:
                    raise OutcomeRankerError("failed/fallback/nonfinite raw branch cannot enter training")
                rewards_by_replicate[replicate_id].setdefault(fingerprint, []).append(reward)
                equivalence_key = option_equivalence_keys[option_index]
                equivalence_rewards_by_replicate[replicate_id].setdefault(
                    equivalence_key, []
                ).append(reward)
            if seen_originals != {transport.original_indices[index] for index in available_indexes}:
                raise OutcomeRankerError("replicate action set is incomplete")

        unique_fingerprints = tuple(dict.fromkeys(expected_fingerprints[index] for index in available_indexes))
        derived_by_id: dict[str, dict[str, Any]] = {}
        for fingerprint in unique_fingerprints:
            pooled_rewards: list[int] = []
            for replicate_id in replicate_ids:
                values = rewards_by_replicate[replicate_id].get(fingerprint, [])
                if not values:
                    raise OutcomeRankerError("raw replicates omit a legal semantic action")
                # Duplicate semantic options are pooled per replicate. A semantic
                # collision with different terminal outcomes is ambiguous, so fail
                # closed rather than turn it into false certainty.
                if len(set(values)) != 1:
                    raise OutcomeRankerError("duplicate semantic options disagree within a replicate")
                pooled_rewards.append(values[0])
            derived_by_id[_semantic_action_id(ordering, fingerprint)] = _derived_summary(pooled_rewards)

        unique_equivalence_keys = tuple(
            dict.fromkeys(option_equivalence_keys[index] for index in available_indexes)
        )
        derived_by_equivalence: dict[str, dict[str, Any]] = {}
        for equivalence_key in unique_equivalence_keys:
            clusters: list[list[int]] = []
            for replicate_id in sorted(replicate_ids):
                values = equivalence_rewards_by_replicate[replicate_id].get(equivalence_key, [])
                if not values:
                    raise OutcomeRankerError("raw replicates omit a legal equivalence class")
                clusters.append(values)
            derived_by_equivalence[equivalence_key] = _derived_equivalence_summary(clusters)

        aggregate_by_id: dict[str, Mapping[str, Any]] = {}
        if len(aggregates) != len(unique_fingerprints):
            raise OutcomeRankerError("action aggregates do not cover each semantic legal action exactly once")
        for aggregate in aggregates:
            if not isinstance(aggregate, Mapping):
                raise OutcomeRankerError("action aggregate must be an object")
            action_id = aggregate.get("action_id")
            if not isinstance(action_id, str) or action_id in aggregate_by_id or action_id not in derived_by_id:
                raise OutcomeRankerError("action aggregate identity is missing, duplicated, or unexpected")
            aggregate_by_id[action_id] = aggregate
        for action_id, aggregate in aggregate_by_id.items():
            expected = derived_by_id[action_id]
            if aggregate.get("replicate_count") != expected["replicate_count"] or aggregate.get("wdl_counts") != expected["wdl_counts"]:
                raise OutcomeRankerError("action aggregate counts differ from raw branch outcomes")
            for field in ("mean_reward", "reward_stderr", "ci95_low", "ci95_high"):
                try:
                    observed = float(aggregate.get(field))
                except (TypeError, ValueError) as error:
                    raise OutcomeRankerError(f"action aggregate {field} is not numeric") from error
                if not _close(observed, float(expected[field])):
                    raise OutcomeRankerError(f"action aggregate {field} differs from raw branch outcomes")
        for action_id, aggregate in aggregate_by_id.items():
            baseline_id = aggregate.get("baseline_action_id")
            advantage = aggregate.get("advantage_vs_fallback")
            if baseline_id is not None:
                if baseline_id not in aggregate_by_id:
                    raise OutcomeRankerError("aggregate baseline action identity is unknown")
                if advantage is None or not _close(float(advantage), float(derived_by_id[action_id]["mean_reward"] - derived_by_id[baseline_id]["mean_reward"])):
                    raise OutcomeRankerError("aggregate baseline advantage differs from raw-derived targets")
            elif advantage is not None:
                raise OutcomeRankerError("aggregate advantage requires an explicit baseline action")

        targets: list[float] = []
        stderrs: list[float] = []
        weights: list[float] = []
        masks: list[bool] = []
        group_action_ids: list[str] = []
        group_fingerprints: list[str] = []
        group_equivalence_keys: list[str] = []
        for option_index, fingerprint in enumerate(expected_fingerprints):
            action_id = _semantic_action_id(ordering, fingerprint)
            group_action_ids.append(action_id)
            group_fingerprints.append(fingerprint)
            equivalence_key = option_equivalence_keys[option_index]
            group_equivalence_keys.append(equivalence_key)
            if not available[option_index]:
                targets.append(0.0)
                stderrs.append(0.0)
                weights.append(0.0)
                masks.append(False)
                continue
            derived = derived_by_equivalence[equivalence_key]
            targets.append(float(derived["mean_reward"]))
            stderrs.append(float(derived["reward_stderr"]))
            weights.append(
                _target_weight(float(derived["reward_stderr"]), int(derived["particle_count"]))
            )
            masks.append(True)
        group_metadata: list[Mapping[str, Any]] = []
        for equivalence_key in unique_equivalence_keys:
            derived = derived_by_equivalence[equivalence_key]
            members = [
                index for index, key in enumerate(group_equivalence_keys) if key == equivalence_key
            ]
            group_metadata.append(
                {
                    "semantic_equivalence_key": equivalence_key,
                    "member_indices": members,
                    "member_action_ids": [group_action_ids[index] for index in members],
                    "member_semantic_fingerprints": [
                        group_fingerprints[index] for index in members
                    ],
                    "target": float(derived["mean_reward"]),
                    "stderr": float(derived["reward_stderr"]),
                    "weight": _target_weight(
                        float(derived["reward_stderr"]), int(derived["particle_count"])
                    ),
                    "replicate_count": int(derived["replicate_count"]),
                    "branch_count": int(derived["branch_count"]),
                    "particle_count": int(derived["particle_count"]),
                    "sample_unit": derived["sample_unit"],
                    "disagreement": bool(derived["disagreement"]),
                    "disagreement_count": int(derived["disagreement_count"]),
                    "wdl_counts": dict(derived["wdl_counts"]),
                }
            )
        hidden_rows.append(output.hidden[0].detach().cpu())
        option_rows.append(output.option_embeddings.detach().cpu())
        available_rows.append(batch.option_available.detach().cpu())
        target_rows.append(torch.tensor(targets, dtype=torch.float32))
        stderr_rows.append(torch.tensor(stderrs, dtype=torch.float32))
        weight_rows.append(torch.tensor(weights, dtype=torch.float32))
        mask_rows.append(torch.tensor(masks, dtype=torch.bool))
        option_offsets.append(option_offsets[-1] + len(options))
        group_offsets.append(group_offsets[-1] + len(options))
        state_ids.append(state_id)
        action_ids.extend(group_action_ids)
        fingerprints.extend(group_fingerprints)
        equivalence_keys.extend(group_equivalence_keys)
        equivalence_metadata_rows.append(tuple(group_metadata))

    return RankerBatch(
        public_hidden=torch.stack(hidden_rows),
        option_embeddings=torch.cat(option_rows),
        option_available=torch.cat(available_rows),
        option_offsets=torch.tensor(option_offsets, dtype=torch.long),
        target=torch.cat(target_rows),
        target_stderr=torch.cat(stderr_rows),
        target_weight=torch.cat(weight_rows),
        target_mask=torch.cat(mask_rows),
        group_offsets=torch.tensor(group_offsets, dtype=torch.long),
        state_group_ids=tuple(state_ids),
        action_ids=tuple(action_ids),
        semantic_fingerprints=tuple(fingerprints),
        semantic_equivalence_keys=tuple(equivalence_keys),
        equivalence_class_metadata=tuple(equivalence_metadata_rows),
    )


def checkpoint_bytes(model: OutcomeRankerV1, binding: TrunkBindingV1) -> bytes:
    if not isinstance(binding, TrunkBindingV1):
        raise OutcomeRankerError("Gate-1 checkpoint requires a strict BC trunk binding")
    _validate_ranker_model(model)
    payload = {
        "schema_version": RANKER_CHECKPOINT_SCHEMA_VERSION,
        "checkpoint_kind": "OUTCOME_RANKER_GATE1_HEAD_ONLY",
        "trunk_binding": asdict(binding),
        "hidden_width": model.hidden_width,
        "option_width": model.option_width,
        "ranker_width": model.ranker_width,
        "state_dict": model.state_dict(),
    }
    stream = io.BytesIO()
    torch.save(payload, stream)
    return stream.getvalue()


def _validate_ranker_model(model: OutcomeRankerV1) -> None:
    if not isinstance(model, OutcomeRankerV1):
        raise OutcomeRankerError("Gate-1 checkpoint model type differs")
    if (
        model.hidden_width != GATE1_HIDDEN_WIDTH
        or model.option_width != GATE1_OPTION_WIDTH
        or model.ranker_width != GATE1_RANKER_WIDTH
    ):
        raise OutcomeRankerError("Gate-1 ranker dimensions differ from the frozen contract")
    state = model.state_dict()
    if any(not torch.isfinite(value).all().item() for value in state.values()):
        raise OutcomeRankerError("ranker checkpoint contains nonfinite weights")
    parameter = next(model.parameters())
    hidden = torch.zeros(
        (1, GATE1_HIDDEN_WIDTH), dtype=parameter.dtype, device=parameter.device
    )
    options = torch.zeros(
        (1, GATE1_OPTION_WIDTH), dtype=parameter.dtype, device=parameter.device
    )
    offsets = torch.tensor([0, 1], dtype=torch.long, device=parameter.device)
    try:
        with torch.inference_mode():
            scores = model(hidden, options, offsets)
    except (RuntimeError, TypeError, ValueError) as error:
        raise OutcomeRankerError(f"ranker checkpoint finite-output probe failed: {error}") from error
    if not torch.isfinite(scores).all():
        raise OutcomeRankerError("ranker checkpoint finite-output probe was nonfinite")


def load_checkpoint(payload: bytes, *, map_location: torch.device | str = "cpu") -> OutcomeRankerV1:
    try:
        value = torch.load(io.BytesIO(payload), map_location=map_location, weights_only=True)
    except (OSError, RuntimeError, ValueError, TypeError, EOFError, pickle.UnpicklingError) as error:
        raise OutcomeRankerError(f"ranker checkpoint cannot be loaded: {error}") from error
    if (
        not isinstance(value, Mapping)
        or value.get("schema_version") != RANKER_CHECKPOINT_SCHEMA_VERSION
        or value.get("checkpoint_kind") != "OUTCOME_RANKER_GATE1_HEAD_ONLY"
    ):
        raise OutcomeRankerError("ranker checkpoint schema differs")
    try:
        binding = TrunkBindingV1(**dict(value["trunk_binding"]))
    except (KeyError, TypeError, ValueError) as error:
        raise OutcomeRankerError("ranker checkpoint lacks the pinned BC trunk binding") from error
    try:
        dimensions = (
            int(value["hidden_width"]), int(value["option_width"]), int(value["ranker_width"])
        )
    except (KeyError, TypeError, ValueError) as error:
        raise OutcomeRankerError("ranker checkpoint dimensions are missing") from error
    if dimensions != (GATE1_HIDDEN_WIDTH, GATE1_OPTION_WIDTH, GATE1_RANKER_WIDTH):
        raise OutcomeRankerError("ranker checkpoint dimensions differ from the Gate-1 contract")
    model = OutcomeRankerV1(*dimensions)
    try:
        model.load_state_dict(value["state_dict"], strict=True)
    except (RuntimeError, TypeError) as error:
        raise OutcomeRankerError(f"ranker checkpoint state differs: {error}") from error
    _validate_ranker_model(model)
    model._gate1_trunk_binding = binding  # type: ignore[attr-defined]
    return model


__all__ = [
    "OutcomeRankerError",
    "OutcomeRankerV1",
    "RankerBatch",
    "TrunkBindingV1",
    "BC_TRUNK_CHECKPOINT_SHA256",
    "BC_TRUNK_STATE_SHA256",
    "G2_MODEL_SCHEMA_SHA256",
    "G2_PACKAGE_SHA256",
    "checkpoint_bytes",
    "choose_legal_option",
    "deterministic_legal_fallback",
    "grouped_ranker_loss",
    "load_gate1_trunk",
    "load_checkpoint",
    "load_counterfactual_dataset",
    "semantic_equivalence_key",
]
