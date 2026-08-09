"""Direct, label-audit-only ceiling probe for the restricted v1 sidecar.
Only the root dataset supplies model features.  Labels are joined by exact
state/action/replicate and projection/history bindings; the sidecar never
becomes a model-input source.  This module does not run the engine or train
an RL policy.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import random
import subprocess
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
import torch
from torch import Tensor, nn
PARTICLES = 4
FEATURE_WIDTH = 288
SPLITS = ("train", "tune", "test")
FEATURE_NAMES = ("pre_root_public_hidden[160]", "candidate_option_embedding[128]")
G2_SCHEMA_SHA256 = "61f6f71008c847b03bbab913d767da2c6bc6469311a0fe7249f3d03ee512bf68"
LABEL_SCHEMA = Path(__file__).resolve().parents[1] / "outcome-ranker" / "opponent_transition_label_v1.schema.json"
class InterchangeError(ValueError):
    """The sidecar cannot be joined exactly to the root dataset."""
class FirewallError(ValueError):
    """A private, opponent, or audit-only field crossed the feature boundary."""
@dataclass(frozen=True)
class Candidate:
    root: str
    root_key: str
    family: str
    seat: str
    feature: tuple[float, ...]
    targets: tuple[str, ...]
    legal_counts: tuple[int, ...]
    @property
    def stratum(self) -> tuple[str, str]:
        return self.family, self.seat
def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
def _stable_hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()
def _sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def _hash(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)
def _helpers() -> Any:
    path = str(Path(__file__).resolve().parents[1] / "outcome-ranker")
    if path not in sys.path:
        sys.path.insert(0, path)
    import outcome_ranker  # type: ignore
    return outcome_ranker
def _walk_firewall(value: Any, path: str = "public_tensor") -> None:
    forbidden = {
        "opponent_view", "opponent_observation", "opponent_actor_observation",
        "opponent_legal_options", "private_observation", "hidden_observation",
        "determinization_output", "search_input", "search_begin_input",
        "policy_memory", "anchor_identity", "true_anchor_identity", "wdl",
        "terminal_engine_result", "legal_options", "legal_set",
    }
    if isinstance(value, Mapping):
        for key, child in value.items():
            if str(key).lower() in forbidden:
                raise FirewallError(f"forbidden public feature field {path}.{key}")
            _walk_firewall(child, f"{path}.{key}")
    elif isinstance(value, list):
        for i, child in enumerate(value):
            _walk_firewall(child, f"{path}[{i}]")
def _guard_public_tensor(tensor: Mapping[str, Any]) -> None:
    if tensor.get("public_only") is not True:
        raise FirewallError("root public_tensor.public_only is not true")
    if tensor.get("raw_observation_retained") is not False:
        raise FirewallError("raw observation is retained in root public tensor")
    if tensor.get("forbidden_actor_features_absent") is not True:
        raise FirewallError("forbidden actor features are not absent")
    _walk_firewall(tensor)
def _root_projection(tensor: Mapping[str, Any]) -> tuple[str, str]:
    projected = tensor.get("projected_decision")
    if not isinstance(projected, Mapping):
        raise InterchangeError("root public tensor lacks projected G2 decision")
    tokens = tensor.get("history_tokens")
    provenance = tensor.get("prefix_provenance")
    if not isinstance(tokens, list) or len(tokens) != 1 or not isinstance(tokens[0], Mapping):
        raise InterchangeError("root public tensor lacks one history token")
    if not isinstance(provenance, Mapping):
        raise InterchangeError("root public tensor lacks prefix provenance")
    token = tokens[0]
    if token.get("prefix_digest") != provenance.get("prefix_digest"):
        raise InterchangeError("history token/provenance digest differs")
    if token.get("model_schema_sha256") != G2_SCHEMA_SHA256:
        raise InterchangeError("history token is not bound to frozen G2 schema")
    return _stable_hash(projected), str(token["prefix_digest"])
def _hidden(tensor: Mapping[str, Any]) -> Tensor:
    try:
        return _helpers()._hidden_from_history(tensor)
    except (ImportError, AttributeError, KeyError, TypeError, ValueError, RuntimeError) as error:
        raise InterchangeError(f"G2 hidden helper rejected root history: {error}") from error
def _feature(
    tensor: Mapping[str, Any], option_index: int, trunk: Any | None = None
) -> tuple[float, ...]:
    _guard_public_tensor(tensor)
    hidden = _hidden(tensor).detach().cpu()
    if hidden.shape != (1, 160):
        raise InterchangeError("G2 hidden shape is not [1,160]")
    try:
        helpers = _helpers()
        if trunk is None:
            trunk, _ = helpers.load_gate1_trunk(device="cpu")
        decision = helpers._projected_decision(tensor["projected_decision"])
        batch = helpers.collate_projected((decision,), device="cpu")
        with torch.inference_mode():
            output = trunk(batch, hidden)
        embeddings = output.option_embeddings.detach().cpu()
    except (ImportError, AttributeError, KeyError, TypeError, ValueError, RuntimeError) as error:
        raise InterchangeError(f"frozen G2 option embedding extraction failed: {error}") from error
    if embeddings.ndim != 2 or embeddings.shape[1] != 128 or option_index not in range(embeddings.shape[0]):
        raise InterchangeError("candidate option embedding is outside [option_count,128]")
    values = torch.cat((hidden[0], embeddings[option_index])).tolist()
    if len(values) != FEATURE_WIDTH or not all(math.isfinite(float(x)) for x in values):
        raise FirewallError("G2 public feature vector is malformed or nonfinite")
    return tuple(float(x) for x in values)
def _call_extractor(
    extractor: Callable[..., Sequence[float]], tensor: Mapping[str, Any], index: int, trunk: Any | None
) -> tuple[float, ...]:
    try:
        values = extractor(tensor, index, trunk)
    except TypeError:
        values = extractor(tensor, index)
    values = tuple(float(x) for x in values)
    if len(values) != FEATURE_WIDTH or not all(math.isfinite(x) for x in values):
        raise FirewallError("injected feature extractor returned wrong/nonfinite width")
    return values
def _resolve_dataset_path(sidecar_path: Path, raw: str, root_path: Path) -> bool:
    declared = Path(raw)
    candidates = [declared]
    if not declared.is_absolute():
        candidates += [sidecar_path.parent / declared, Path.cwd() / declared]
    return any(candidate.resolve() == root_path.resolve() for candidate in candidates)
def _load_json(path: str | Path) -> Mapping[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise InterchangeError(f"{path} is not a JSON object")
    return value
def _validate_label_schema(sidecar: Mapping[str, Any]) -> None:
    try:
        import jsonschema
    except ImportError:
        jsonschema = None
    schema = _load_json(LABEL_SCHEMA)
    value = json.loads(json.dumps(sidecar))
    if jsonschema is not None:
        errors = list(jsonschema.Draft202012Validator(schema).iter_errors(value))
    else:
        script = "const fs=require('fs');const Ajv2020=require('ajv/dist/2020');const s=JSON.parse(fs.readFileSync(process.argv[1]));const d=JSON.parse(fs.readFileSync(0));const v=new Ajv2020({allErrors:true,strict:false}).compile(s);process.stdout.write(JSON.stringify(v(d)?[]:v.errors));"
        result = subprocess.run(["node", "-e", script, str(LABEL_SCHEMA)], input=json.dumps(value), text=True, capture_output=True, check=False)
        if result.returncode != 0 or not result.stdout:
            raise InterchangeError("schema validator failed closed")
        try:
            parsed = json.loads(result.stdout)
        except json.JSONDecodeError as error:
            raise InterchangeError("schema validator returned malformed output") from error
        if not isinstance(parsed, list):
            raise InterchangeError("schema validator returned malformed errors")
        errors = [type("SchemaError", (), {"message": item.get("message", "schema error")}) for item in parsed if isinstance(item, Mapping)]
    if errors:
        raise InterchangeError("sidecar schema validation failed: " + "; ".join(error.message for error in errors[:3]))
def _root_index(root_path: Path) -> tuple[dict[str, Mapping[str, Any]], str]:
    document = _load_json(root_path)
    groups = document.get("state_groups")
    run = document.get("run")
    if not isinstance(groups, list) or not isinstance(run, Mapping) or not isinstance(run.get("run_id"), str):
        raise InterchangeError("root dataset lacks run/state_groups")
    result: dict[str, Mapping[str, Any]] = {}
    for group in groups:
        if not isinstance(group, Mapping) or not isinstance(group.get("state_group_id"), str):
            raise InterchangeError("root state group is malformed")
        state = str(group["state_group_id"])
        if state in result:
            raise InterchangeError(f"duplicate root state_group_id: {state}")
        if not _hash(group.get("public_state_sha256")):
            raise InterchangeError(f"root public_state_sha256 is malformed: {state}")
        tensor = group.get("public_tensor")
        if not isinstance(tensor, Mapping):
            raise InterchangeError(f"root public tensor is missing: {state}")
        _guard_public_tensor(tensor)
        _root_projection(tensor)
        replicates = group.get("replicates")
        if not isinstance(replicates, list) or {rep.get("replicate_id") for rep in replicates if isinstance(rep, Mapping)} != set(range(PARTICLES)) or len(replicates) != PARTICLES:
            raise InterchangeError(f"root replicates are not exactly 0,1,2,3: {state}")
        projected = tensor.get("projected_decision")
        transport = projected.get("transport_sidecar") if isinstance(projected, Mapping) else None
        original_indices = transport.get("original_indices") if isinstance(transport, Mapping) else None
        options = group.get("request", {}).get("options", []) if isinstance(group.get("request"), Mapping) else []
        expected_indices = [option.get("original_index", index) for index, option in enumerate(options) if isinstance(option, Mapping)]
        if not isinstance(original_indices, list) or len(original_indices) != len(options) or len(set(original_indices)) != len(options) or sorted(original_indices) != sorted(expected_indices):
            raise InterchangeError(f"G2 transport original_indices are not a complete option permutation: {state}")
        determinization_ids = [rep.get("determinization_id") for rep in replicates]
        action_sets = [{action.get("action_id") for action in rep.get("actions", []) if isinstance(action, Mapping)} for rep in replicates]
        if any(not isinstance(value, str) or not value for value in determinization_ids) or len(set(determinization_ids)) != PARTICLES or any(not values for values in action_sets) or len({frozenset(values) for values in action_sets}) != 1:
            raise InterchangeError(f"root determinization/action coverage is inconsistent: {state}")
        for rep in replicates:
            for action in rep.get("actions", []):
                if not isinstance(action, Mapping) or not _hash(action.get("semantic_action_fingerprint")):
                    raise InterchangeError(f"root action fingerprint is malformed: {state}")
        result[state] = group
    return result, str(run["run_id"])
def _projection_bindings(sidecar: Mapping[str, Any], roots: Mapping[str, Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    projection = sidecar["public_projection_binding"]
    if not isinstance(projection, Mapping) or projection.get("model_schema_sha256") != G2_SCHEMA_SHA256:
        raise InterchangeError("public projection binding is not frozen-G2 bound")
    rows = projection.get("groups") if isinstance(projection, Mapping) else None
    if not isinstance(rows, list):
        raise InterchangeError("public projection binding groups are missing")
    result: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping) or not isinstance(row.get("state_group_id"), str):
            raise InterchangeError("public projection binding row is malformed")
        state = str(row["state_group_id"])
        if state in result or state not in roots:
            raise InterchangeError(f"projection binding state is not unique/root-bound: {state}")
        root = roots[state]
        projection_digest, history_digest = _root_projection(root["public_tensor"])
        if row.get("public_state_sha256") != root["public_state_sha256"]:
            raise InterchangeError(f"public state binding differs: {state}")
        if row.get("public_projection_sha256") != projection_digest:
            raise InterchangeError(f"public projection binding differs: {state}")
        if row.get("history_prefix_digest") != history_digest:
            raise InterchangeError(f"history prefix binding differs: {state}")
        expected_history = _stable_hash(root["public_tensor"]["history_tokens"])
        if row.get("history_tokens_sha256") != expected_history:
            raise InterchangeError(f"history_tokens_sha256 binding differs: {state}")
        result[state] = row
    if set(result) != set(roots):
        raise InterchangeError("public projection bindings do not cover every root")
    return result
def _action_index(group: Mapping[str, Any], replicate_id: int, action_id: str) -> tuple[int, str | None]:
    for replicate in group.get("replicates", []):
        if not isinstance(replicate, Mapping) or replicate.get("replicate_id") != replicate_id:
            continue
        for action in replicate.get("actions", []):
            if isinstance(action, Mapping) and action.get("action_id") == action_id:
                indices = action.get("transport_original_indices")
                if not isinstance(indices, list) or len(indices) != 1 or not isinstance(indices[0], int):
                    raise InterchangeError("root action is not a singleton candidate transport path")
                return indices[0], action.get("semantic_action_fingerprint")
    raise InterchangeError("label action_id/replicate_id is not bound to root")
def _learner_index(group: Mapping[str, Any], original_index: int) -> int:
    if original_index < 0:
        raise InterchangeError("root original index is negative")
    projected = group["public_tensor"].get("projected_decision")
    transport = projected.get("transport_sidecar") if isinstance(projected, Mapping) else None
    indices = transport.get("original_indices") if isinstance(transport, Mapping) else None
    if not isinstance(indices, list) or any(not isinstance(index, int) or index < 0 for index in indices):
        raise InterchangeError("G2 transport original_indices are missing or malformed")
    try:
        return indices.index(original_index)
    except ValueError as error:
        raise InterchangeError("root original index is absent from G2 transport map") from error
def _validate_sidecar(sidecar_path: Path, sidecar: Mapping[str, Any], root_path: Path) -> tuple[dict[str, Mapping[str, Any]], str, dict[str, Mapping[str, Any]], dict[tuple[str, str], str]]:
    _validate_label_schema(sidecar)
    if sidecar.get("schema_version") != 1 or sidecar.get("sidecar_kind") != "RESTRICTED_OPPONENT_TRANSITION_LABELS":
        raise InterchangeError("sidecar is not restricted opponent transition labels v1")
    for key in ("run", "dataset_binding", "public_projection_binding", "root_action_keys", "provenance", "firewall", "labels"):
        if key not in sidecar:
            raise InterchangeError(f"sidecar missing required field: {key}")
    binding = sidecar["dataset_binding"]
    if not isinstance(binding, Mapping) or not isinstance(binding.get("dataset_path"), str):
        raise InterchangeError("dataset binding path is missing")
    if not _resolve_dataset_path(sidecar_path, binding["dataset_path"], root_path):
        raise InterchangeError("sidecar dataset_path does not name the supplied root dataset")
    digest = _sha256(root_path)
    if binding.get("dataset_sha256") != digest:
        raise InterchangeError("sidecar dataset_sha256 does not bind supplied root dataset")
    roots, run_id = _root_index(root_path)
    run = sidecar["run"]
    if not isinstance(run, Mapping) or run.get("run_id") != run_id:
        raise InterchangeError("sidecar run_id does not bind root dataset")
    root_run = _load_json(root_path).get("run")
    if not isinstance(root_run, Mapping) or run.get("source_commit") != root_run.get("source_commit"):
        raise InterchangeError("sidecar source_commit does not bind root dataset")
    ids = binding.get("state_group_ids")
    if not isinstance(ids, list) or set(ids) != set(roots):
        raise InterchangeError("sidecar state_group_ids do not exactly bind root groups")
    firewall = sidecar["firewall"]
    expected = {
        "consumer": "LABEL_AUDIT_ONLY", "model_facing_fields_present": False,
        "public_root_source": "G2_PROJECTED_PUBLIC_ONLY", "opponent_view_retention": "NONE",
        "opponent_legal_set_retention": "SEMANTIC_LABEL_AUDIT_ONLY",
        "post_evidence_source": "NONE_FIRST_OPPONENT_ACTION_ONLY", "ppo_rollout_eligible": False,
    }
    if firewall != expected:
        raise FirewallError("sidecar firewall flags are not the restricted v1 contract")
    projection = _projection_bindings(sidecar, roots)
    action_keys: dict[tuple[str, str], str] = {}
    raw_keys = sidecar["root_action_keys"]
    if not isinstance(raw_keys, list) or not raw_keys:
        raise InterchangeError("root_action_keys is empty")
    for row in raw_keys:
        if not isinstance(row, Mapping) or not all(_hash(row.get(k)) for k in ("semantic_equivalence_key",)) or not all(isinstance(row.get(k), str) for k in ("state_group_id", "action_id")):
            raise InterchangeError("root action key row is malformed")
        key = (str(row["state_group_id"]), str(row["action_id"]))
        if key in action_keys and action_keys[key] != row["semantic_equivalence_key"]:
            raise InterchangeError("root action key is duplicated with a different equivalence")
        if key[0] not in roots:
            raise InterchangeError("root action key names an unknown state")
        action_keys[key] = str(row["semantic_equivalence_key"])
    for state, action_id in action_keys:
        if not any(action_id == action.get("action_id") for rep in roots[state].get("replicates", []) if isinstance(rep, Mapping) for action in rep.get("actions", []) if isinstance(action, Mapping)):
            raise InterchangeError("root action key does not name a root action")
    dataset_actions = {(state, action.get("action_id")) for state, root in roots.items() for rep in root.get("replicates", []) if isinstance(rep, Mapping) for action in rep.get("actions", []) if isinstance(action, Mapping)}
    if set(action_keys) != dataset_actions:
        raise InterchangeError("root_action_keys do not exactly cover root action IDs")
    return roots, run_id, projection, action_keys
def load_branch_sidecar(
    sidecar_path: str | Path,
    root_dataset_path: str | Path,
    *,
    trunk: Any | None = None,
    feature_extractor: Callable[..., Sequence[float]] | None = None,
    trusted_trunk: bool = False,
) -> tuple[list[Candidate], dict[str, Any]]:
    """Load actual ``labels`` and bind each supported row to root data."""
    sidecar_file, root_file = Path(sidecar_path), Path(root_dataset_path)
    sidecar = _load_json(sidecar_file)
    roots, run_id, projection, action_keys = _validate_sidecar(sidecar_file, sidecar, root_file)
    labels = sidecar.get("labels")
    if not isinstance(labels, list) or not labels:
        raise InterchangeError("sidecar labels is empty")
    extract = feature_extractor or _feature
    grouped: dict[tuple[str, str], dict[int, tuple[str, int, tuple[float, ...], str]]] = defaultdict(dict)
    particle_ids: dict[tuple[str, str, int], str] = {}
    errors: list[str] = []
    unsupported = 0
    supported = 0
    policy = str(sidecar["provenance"].get("opponent_policy_id", "UNKNOWN"))
    status_counts = Counter(str(label.get("status")) for label in labels if isinstance(label, Mapping))
    for i, label in enumerate(labels):
        try:
            if not isinstance(label, Mapping):
                raise InterchangeError("label is not an object")
            status = label.get("status")
            if status != "OBSERVED":
                unsupported += 1
                continue
            if label.get("error") is not None:
                raise InterchangeError("observed label carries an error")
            state = label.get("state_group_id")
            replicate = label.get("replicate_id")
            action_id = label.get("action_id")
            root = roots.get(str(state))
            if root is None or not isinstance(replicate, int) or not isinstance(action_id, str):
                raise InterchangeError("label state/replicate/action does not bind root")
            if replicate not in range(PARTICLES):
                raise InterchangeError("replicate_id must be exactly one of 0,1,2,3")
            root_player = root.get("root_player", root.get("acting_player"))
            if label.get("root_player") != root_player or label.get("opponent_player") != 1 - int(root_player):
                raise InterchangeError("label player roles do not bind root")
            root_particle = next((rep.get("determinization_id") for rep in root.get("replicates", []) if isinstance(rep, Mapping) and rep.get("replicate_id") == replicate), None)
            if label.get("particle_id") != root_particle:
                raise InterchangeError("particle_id does not bind root determinization_id")
            expected_root_key = action_keys.get((str(state), action_id))
            if expected_root_key != label.get("root_action_semantic_equivalence_key"):
                raise InterchangeError("label root action equivalence differs from root_action_keys")
            request = label.get("first_opponent_request")
            chosen = label.get("chosen_action")
            if not isinstance(request, Mapping) or not isinstance(chosen, Mapping):
                raise InterchangeError("observed label lacks request/chosen action")
            if request.get("selection_type") != 0 or request.get("selection_context") != 0 or request.get("min_count") != 1 or request.get("max_count") != 1:
                raise InterchangeError("OBSERVED request is not MAIN context0 singleton")
            indices = chosen.get("transport_original_indices")
            path = chosen.get("semantic_path")
            if not isinstance(indices, list) or len(indices) != 1 or not isinstance(indices[0], int) or indices[0] < 0:
                raise InterchangeError("chosen action original index is malformed")
            if not isinstance(path, list) or len(path) != 1 or not isinstance(path[0], Mapping):
                raise InterchangeError("chosen action semantic_path is not exactly one option")
            if int(request.get("option_count", -1)) != len(request.get("options", [])):
                raise InterchangeError("opponent request option_count is not exact")
            options = request.get("options")
            if not isinstance(options, list):
                raise InterchangeError("chosen opponent option is outside complete request")
            option_indices = [option.get("original_index", index) for index, option in enumerate(options) if isinstance(option, Mapping)]
            if len(option_indices) != len(options) or len(set(option_indices)) != len(options) or any(not isinstance(index, int) or index < 0 for index in option_indices):
                raise InterchangeError("opponent options lack unique nonnegative original indices")
            by_original = dict(zip(option_indices, options))
            selected = by_original.get(indices[0])
            if selected is None or _canonical(path[0]) != _canonical(selected):
                raise InterchangeError("chosen semantic path differs from selected legal option")
            selected_key = selected.get("semantic_equivalence_key")
            path_key = path[0].get("semantic_equivalence_key")
            if selected_key is not None and path_key != selected_key:
                raise InterchangeError("chosen canonical equivalence key differs from selected option")
            if path[0].get("semantic_fingerprint") != selected.get("semantic_fingerprint"):
                raise InterchangeError("chosen semantic fingerprint differs from selected option")
            target = chosen.get("semantic_equivalence_key")
            if not _hash(target):
                raise InterchangeError("chosen action semantic equivalence key is malformed")
            if selected_key is not None and target != selected_key:
                raise InterchangeError("chosen action key differs from selected option")
            if chosen.get("semantic_action_fingerprint") != _stable_hash(path):
                raise InterchangeError("chosen semantic action fingerprint does not bind path")
            option_index, root_fingerprint = _action_index(root, replicate, action_id)
            if label.get("root_action_semantic_fingerprint") != root_fingerprint:
                raise InterchangeError("label root action fingerprint differs from root action")
            option_index = _learner_index(root, option_index)
            projection_digest, history_digest = _root_projection(root["public_tensor"])
            bound = projection[str(state)]
            if bound["public_projection_sha256"] != projection_digest or bound["history_prefix_digest"] != history_digest:
                raise InterchangeError("label root projection/history binding drifted")
            feature = _call_extractor(extract, root["public_tensor"], option_index, trunk)
            legal_count = len(options)
            if legal_count < 1 or int(request.get("min_count", -1)) < 0 or int(request.get("max_count", -1)) < int(request.get("min_count", -1)) or int(request.get("max_count", -1)) > legal_count:
                raise InterchangeError("opponent request legal-count bounds are malformed")
            group = (str(state), str(expected_root_key))
            particle = label.get("particle_id")
            if not isinstance(particle, str) or not particle:
                raise InterchangeError("particle_id is malformed")
            particle_key = (str(state), str(expected_root_key), replicate)
            if particle_key in particle_ids and particle_ids[particle_key] != particle:
                raise InterchangeError("particle identity differs across aliases")
            particle_ids[particle_key] = particle
            previous = grouped[group].get(replicate)
            row = (str(target), legal_count, feature, action_id)
            if previous is not None and previous[:3] != row[:3]:
                raise InterchangeError("alias labels disagree within a replicate")
            grouped[group][replicate] = row
            supported += 1
        except (InterchangeError, FirewallError, KeyError, TypeError, ValueError) as error:
            errors.append(f"label[{i}]: {error}")
    candidates: list[Candidate] = []
    incomplete: list[str] = []
    for state in roots:
        for root_key in sorted({key for (key_state, action_id), key in action_keys.items() if key_state == state}):
            if (state, root_key) not in grouped:
                incomplete.append(f"{state}:{root_key}")
    for (state, root_key), rows in sorted(grouped.items()):
        if set(rows) != set(range(PARTICLES)):
            incomplete.append(f"{state}:{root_key}")
            continue
        ordered = [rows[key] for key in sorted(rows)]
        if len({item[2] for item in ordered}) != 1:
            errors.append(f"{state}:{root_key}:feature drift across particles")
            continue
        root = roots[state]
        candidates.append(Candidate(state, root_key, policy, f"P{root.get('root_player', root.get('acting_player', 'UNKNOWN'))}", ordered[0][2], tuple(item[0] for item in ordered), tuple(item[1] for item in ordered)))
    ingest = {
        "raw_label_count": len(labels), "supported_label_count": supported,
        "supported_group_count": len(candidates), "unsupported_label_count": unsupported,
        "join_errors": errors, "firewall_errors": [e for e in errors if "firewall" in e.lower() or "private" in e.lower() or "opponent" in e.lower()],
        "reliability_errors": [e for e in errors if "drift" in e.lower() or "alias" in e.lower()],
        "incomplete_groups": sorted(set(incomplete)), "declared_group_count": len({(state, key) for (state, _), key in action_keys.items()}), "dataset_sha256": _sha256(root_file), "run_id": run_id,
        "root_ids": sorted(roots), "config_sha256": sidecar["run"].get("config_sha256"), "profile": sidecar["run"].get("profile"), "status_counts": dict(status_counts),
        "custom_feature_extractor": feature_extractor is not None or (trunk is not None and not trusted_trunk), "source_commit": sidecar["run"].get("source_commit"), "anchor_policy": (sidecar["provenance"].get("anchor_baseline_id"), sidecar["provenance"].get("opponent_policy_id")),
    }
    return candidates, ingest
def stratified_group_split(records: Sequence[Candidate]) -> dict[str, list[Candidate]]:
    """Deterministically split whole roots, using family/seat strata."""
    by_root: dict[str, list[Candidate]] = defaultdict(list)
    strata: dict[str, tuple[str, str]] = {}
    for row in records:
        if row.root in strata and strata[row.root] != row.stratum:
            raise ValueError(f"root crosses family/seat strata: {row.root}")
        strata[row.root] = row.stratum
        by_root[row.root].append(row)
    result = {name: [] for name in SPLITS}
    for stratum in sorted(set(strata.values())):
        roots = sorted((root for root, value in strata.items() if value == stratum), key=lambda x: hashlib.sha256(x.encode()).hexdigest())
        n = len(roots)
        train_n = min(n, max(1 if n else 0, round(n * 0.625)))
        tune_n = min(n - train_n, round(n * 0.1875))
        for root, split in zip(roots, ["train"] * train_n + ["tune"] * tune_n + ["test"] * (n - train_n - tune_n)):
            result[split].extend(by_root[root])
    for values in result.values():
        values.sort(key=lambda row: (row.root, row.root_key))
    return result
class LinearProbe(nn.Module):
    def __init__(self, classes: int) -> None:
        super().__init__()
        self.linear = nn.Linear(FEATURE_WIDTH, classes)
    def forward(self, x: Tensor) -> Tensor:
        return self.linear(x)
def _fit(train: Sequence[Candidate]) -> tuple[LinearProbe | None, tuple[str, ...], dict[str, Any]]:
    classes = tuple(sorted({target for row in train for target in row.targets}))
    if not train or not classes:
        return None, classes, {"status": "BLOCKED_NO_TRAIN_LABELS"}
    torch.manual_seed(17)
    model = LinearProbe(len(classes))
    x = torch.tensor([row.feature for row in train], dtype=torch.float32)
    y = torch.tensor([classes.index(target) for row in train for target in row.targets], dtype=torch.long)
    x = x.repeat_interleave(PARTICLES, dim=0)
    optimizer = torch.optim.SGD(model.parameters(), lr=0.08)
    for _ in range(240):
        optimizer.zero_grad(set_to_none=True)
        loss = nn.functional.cross_entropy(model(x), y)
        if not torch.isfinite(loss):
            raise FirewallError("linear probe loss became nonfinite")
        loss.backward()
        optimizer.step()
    return model.eval(), classes, {"status": "FIT", "seed": 17, "steps": 240, "learning_rate": 0.08, "class_count": len(classes), "train_roots": len(train)}
def _ceiling(rows: Sequence[Candidate]) -> dict[str, Any]:
    values = []
    by_root: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        counts = sorted(Counter(row.targets).values(), reverse=True)
        top1 = counts[0] / PARTICLES
        top3 = min(PARTICLES, sum(counts[:3])) / PARTICLES
        values.append((top1, top3))
        by_root[row.root].append(top3)
    roots = [sum(v) / len(v) for v in by_root.values()]
    rng = random.Random(23)
    samples = sorted(sum(rng.choice(roots) for _ in roots) / len(roots) for _ in range(4000)) if roots else []
    return {"top1": sum(v[0] for v in values) / len(values) if values else None, "top3": sum(v[1] for v in values) / len(values) if values else None, "root_bootstrap_top3_lcb95": samples[99] if len(samples) >= 100 else None}
def _report(rows: Sequence[Candidate], train: Sequence[Candidate], model: LinearProbe | None, classes: tuple[str, ...]) -> dict[str, Any]:
    total = correct1 = correct3 = unseen = 0
    nll = 0.0
    top3_by_root: dict[str, list[float]] = defaultdict(list)
    prior_counts = Counter(target for row in train for target in row.targets)
    prior_denominator = sum(prior_counts.values()) + len(classes) + 1
    prior = {key: (prior_counts[key] + 1) / prior_denominator for key in classes}
    unknown = 1.0 / prior_denominator
    probabilities = model(torch.tensor([row.feature for row in rows], dtype=torch.float32)).softmax(1) if model and rows else torch.empty((0, len(classes)))
    for i, row in enumerate(rows):
        ranked = torch.argsort(probabilities[i], descending=True).tolist() if model else []
        for target in row.targets:
            total += 1
            if target not in classes:
                unseen += 1
                nll -= math.log(unknown)
                top3_by_root[row.root].append(0.0)
                continue
            index = classes.index(target)
            nll -= math.log(max(float(probabilities[i, index].detach()), 1e-12))
            correct1 += bool(ranked and ranked[0] == index)
            correct3 += bool(ranked and index in ranked[:3])
            top3_by_root[row.root].append(float(bool(ranked and index in ranked[:3])))
    prior_nll = sum(-math.log(prior.get(target, unknown)) for row in rows for target in row.targets) / total if total else None
    uniform_rows = [count for row in rows for count in row.legal_counts]
    root_scores = [sum(values) / len(values) for values in top3_by_root.values()]
    rng = random.Random(29)
    bootstrap = sorted(sum(rng.choice(root_scores) for _ in root_scores) / len(root_scores) for _ in range(4000)) if root_scores else []
    return {
        "roots": len({row.root for row in rows}), "rows": total,
        "top1": correct1 / total if total else None, "top3": correct3 / total if total else None,
        "nll": nll / total if total else None, "train_prior_nll": prior_nll,
        "nll_improvement_vs_train_prior": (prior_nll - nll / total) if total and prior_nll is not None else None,
        "unseen_class_rate": unseen / total if total else None,
        "root_bootstrap_top3_lcb95": bootstrap[99] if len(bootstrap) >= 100 else None,
        "repeatability": _ceiling(rows),
        "legal_uniform_audit": {"top1": sum(1 / n for n in uniform_rows) / len(uniform_rows) if uniform_rows else None, "top3": sum(min(3, n) / n for n in uniform_rows) / len(uniform_rows) if uniform_rows else None, "nll": sum(math.log(n) for n in uniform_rows) / len(uniform_rows) if uniform_rows else None, "feature_use": "audit-only"},
    }
def _collisions(rows: Sequence[Candidate]) -> dict[str, Any]:
    owners: dict[tuple[float, ...], set[tuple[str, str]]] = defaultdict(set)
    for row in rows:
        owners[row.feature].add((row.root, row.root_key))
    groups = [(_stable_hash(list(feature)), sorted(keys)) for feature, keys in owners.items() if len(keys) > 1]
    return {"collision_group_count": len(groups), "groups": [{"feature_sha256": digest, "owners": owners} for digest, owners in groups]}
def _analyze_records(records: Sequence[Candidate], ingests: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    root_ids = [root for ingest in ingests for root in ingest.get("root_ids", [])]
    duplicate_roots = sorted(root for root, count in Counter(root_ids).items() if count > 1)
    metadata = {(ingest.get("run_id"), ingest.get("config_sha256"), ingest.get("profile"), ingest.get("source_commit")) for ingest in ingests}
    pairs = [item.get("anchor_policy") for item in ingests]
    ingest = {"raw_label_count": sum(item.get("raw_label_count", 0) for item in ingests), "supported_label_count": sum(item.get("supported_label_count", 0) for item in ingests), "join_errors": [e for item in ingests for e in item.get("join_errors", [])], "firewall_errors": [e for item in ingests for e in item.get("firewall_errors", [])], "reliability_errors": [e for item in ingests for e in item.get("reliability_errors", [])], "incomplete_groups": [e for item in ingests for e in item.get("incomplete_groups", [])], "status_counts": dict(sum((Counter(item.get("status_counts", {})) for item in ingests), Counter())), "duplicate_root_ids": duplicate_roots, "root_count": len(set(root_ids)), "pair_count": len(ingests), "metadata_consistent": len(metadata) == 1, "declared_group_count": sum(item.get("declared_group_count", 0) for item in ingests), "custom_feature_extractor": any(item.get("custom_feature_extractor") for item in ingests), "anchor_policy_pairs": pairs}
    splits = stratified_group_split(records)
    model, classes, fit = _fit(splits["train"])
    reports = {name: _report(splits[name], splits["train"], model, classes) for name in SPLITS}
    collisions = _collisions(records)
    gates = {
        "six_pairs": len(ingests) == 6,
        "global_64_roots": len(set(root_ids)) == 64,
        "metadata_consistent": len(metadata) == 1,
        "source_commits_bound": len(metadata) == 1,
        "anchor_policy_pairs_six_distinct": len(set(pairs)) == 6 and None not in pairs,
        "root_allocation_11_11_11_11_10_10": sorted(len(item.get("root_ids", [])) for item in ingests) == [10, 10, 11, 11, 11, 11],
        "real_frozen_feature_path": not ingest["custom_feature_extractor"],
        "no_duplicate_roots": not duplicate_roots,
        "support_ge_0_90": ingest["supported_label_count"] / ingest["raw_label_count"] >= 0.90 if ingest["raw_label_count"] else False,
        "test_top3_ge_0_75": (reports["test"]["top3"] or 0) >= 0.75,
        "root_bootstrap_top3_lcb_ge_0_65": (reports["test"]["root_bootstrap_top3_lcb95"] or 0) >= 0.65,
        "nll_improvement_ge_0_20": (reports["test"]["nll_improvement_vs_train_prior"] or 0) >= 0.20,
        "unseen_le_0_10": (reports["test"]["unseen_class_rate"] if reports["test"]["unseen_class_rate"] is not None else 1) <= 0.10,
        "repeatability_top3_ge_0_90": (reports["test"]["repeatability"]["top3"] or 0) >= 0.90,
        "zero_join_firewall_reliability_collision_errors": not ingest["join_errors"] and not ingest["firewall_errors"] and not ingest["reliability_errors"] and not ingest["incomplete_groups"] and collisions["collision_group_count"] == 0,
    }
    mechanics = all(gates[key] for key in ("six_pairs", "global_64_roots", "metadata_consistent", "source_commits_bound", "anchor_policy_pairs_six_distinct", "root_allocation_11_11_11_11_10_10", "no_duplicate_roots", "real_frozen_feature_path", "zero_join_firewall_reliability_collision_errors"))
    ceiling = all(gates[key] for key in ("support_ge_0_90", "test_top3_ge_0_75", "root_bootstrap_top3_lcb_ge_0_65", "nll_improvement_ge_0_20", "unseen_le_0_10", "repeatability_top3_ge_0_90"))
    return {"status": "PASS_CEILING" if mechanics and ceiling else "KILLED_CEILING" if mechanics else "BLOCKED_MECHANICS", "features": {"public_only": list(FEATURE_NAMES), "excluded": ["IDs", "hashes", "legal_options", "anchor", "family", "seat", "determinization", "search", "memory", "WDL"]}, "fit": fit, "classes": list(classes), "split_root_counts": {name: len({row.root for row in rows}) for name, rows in splits.items()}, "reports": reports, "collisions": collisions, "ingest": ingest, "gates": gates, "target": "chosen_action.semantic_equivalence_key", "strength_evidence": False}
def analyze_pairs(pairs: Sequence[tuple[str | Path, str | Path]], *, config_path: str | Path | None = None, trunk: Any | None = None, feature_extractor: Callable[..., Sequence[float]] | None = None) -> dict[str, Any]:
    internal_trunk = False
    if feature_extractor is None and trunk is None:
        try:
            trunk, _ = _helpers().load_gate1_trunk(device="cpu")
            internal_trunk = True
        except (ImportError, AttributeError, OSError, RuntimeError, TypeError, ValueError) as error:
            raise InterchangeError(f"frozen G2 trunk load failed: {error}") from error
    records: list[Candidate] = []
    ingests: list[Mapping[str, Any]] = []
    for sidecar_path, root_path in pairs:
        values, ingest = load_branch_sidecar(sidecar_path, root_path, trunk=trunk, feature_extractor=feature_extractor, trusted_trunk=internal_trunk)
        records.extend(values)
        ingests.append(ingest)
    config_errors: list[str] = []
    config = None
    if config_path is None:
        config_errors.append("config_path is required for production mechanics")
    else:
        try:
            config = _load_json(config_path)
            config_sha = _sha256(config_path)
            current = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False).stdout.strip()
            if config.get("source_commit") != current:
                config_errors.append("config source_commit does not equal current HEAD")
            for ingest in ingests:
                if ingest.get("config_sha256") != config_sha:
                    config_errors.append("sidecar config_sha256 differs from config bytes")
                if ingest.get("source_commit") != config.get("source_commit"):
                    config_errors.append("sidecar source_commit differs from config")
            anchors = config.get("frozen_anchor_policies")
            cells = config.get("state_schedule", {}).get("anchor_cells") if isinstance(config.get("state_schedule"), Mapping) else None
            policies = {item.get("baseline_id"): item.get("policy_id") for item in anchors or [] if isinstance(item, Mapping)}
            expected = {(baseline, policy): next((cell.get("states") for cell in cells or [] if isinstance(cell, Mapping) and cell.get("anchor") == baseline), None) for baseline, policy in policies.items()}
            configured = {(cell.get("anchor"), policies.get(cell.get("anchor"))): cell.get("states") for cell in cells or [] if isinstance(cell, Mapping)}
            if not expected or expected != configured:
                config_errors.append("config anchor policy/cell schedule is malformed or differs")
            profile = config.get("state_schedule", {}).get("profile") if isinstance(config.get("state_schedule"), Mapping) else None
            if not profile or any(ingest.get("profile") != profile for ingest in ingests):
                config_errors.append("config state_schedule.profile does not bind sidecar profiles")
            for ingest in ingests:
                pair = ingest.get("anchor_policy")
                if pair not in configured or len(ingest.get("root_ids", [])) != configured.get(pair):
                    config_errors.append("pair anchor policy/root allocation differs from config")
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
            config_errors.append(f"config validation failed: {error}")
    if config_errors:
        ingests.append({"raw_label_count": 0, "supported_label_count": 0, "join_errors": config_errors, "firewall_errors": [], "reliability_errors": [], "incomplete_groups": [], "status_counts": {}, "root_ids": [], "run_id": "config", "config_sha256": None, "profile": None, "source_commit": None, "custom_feature_extractor": False, "anchor_policy": None, "declared_group_count": 0})
    return _analyze_records(records, ingests)
def analyze(sidecar_path: str | Path, root_dataset_path: str | Path, *, config_path: str | Path | None = None, trunk: Any | None = None, feature_extractor: Callable[..., Sequence[float]] | None = None) -> dict[str, Any]:
    return analyze_pairs([(sidecar_path, root_dataset_path)], config_path=config_path, trunk=trunk, feature_extractor=feature_extractor)
def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pair", nargs=2, action="append", metavar=("SIDECAR", "ROOT"), required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    payload = json.dumps(analyze_pairs(args.pair, config_path=args.config), indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")
if __name__ == "__main__":
    main()
