from __future__ import annotations

import copy
import importlib.util
import itertools
import sys
from pathlib import Path

ROOT = Path.cwd().resolve()
PLANNER_PATH = ROOT / ".chatgpt/tmp/current-engine-v1/symbolic_turn_planner.py"
_spec = importlib.util.spec_from_file_location("semantic_executor_planner", PLANNER_PATH)
assert _spec and _spec.loader
planner = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = planner
_spec.loader.exec_module(planner)


def legal(raw: dict, action: list[int]) -> bool:
    select = raw.get("select") or {}
    options = select.get("option") or []
    minimum = int(select.get("minCount", 0) or 0)
    maximum = int(select.get("maxCount", 0) or 0)
    return (
        isinstance(action, list)
        and minimum <= len(action) <= maximum
        and len(action) == len(set(action))
        and all(isinstance(index, int) and not isinstance(index, bool) and 0 <= index < len(options) for index in action)
    )


def _signature(raw: dict, action: list[int]):
    # Match the planner's functional path identity. Identical physical copies
    # from hand/discard/deck are interchangeable; in-play serials/targets are not.
    return planner.functional_signature(raw, action)


def remap_step(raw: dict, expected_step, *, max_assignments: int = 64):
    """Map a planned semantic step onto the current legal option indices.

    The expected order is preserved because some compound selections are ordered.
    Duplicate equivalent card copies are allowed; the lexicographically smallest
    valid mapping is chosen only when every chosen option has the requested
    functional semantic identity.
    """
    expected = tuple(tuple(int(v) for v in sig) for sig in expected_step)
    if not expected:
        return [] if legal(raw, []) else None
    options = (raw.get("select") or {}).get("option") or []
    per_position = []
    for wanted in expected:
        matches = []
        for index in range(len(options)):
            got = _signature(raw, [index])
            if len(got) == 1 and tuple(got[0]) == wanted:
                matches.append(index)
        if not matches:
            return None
        per_position.append(matches)

    assignments = []
    for values in itertools.product(*per_position):
        if len(assignments) >= max_assignments:
            break
        if len(values) != len(set(values)):
            continue
        action = list(values)
        if not legal(raw, action):
            continue
        if _signature(raw, action) == expected:
            assignments.append(action)
    if not assignments:
        return None
    assignments.sort()
    return assignments[0]


def _pending_snapshot(module):
    out = {}
    for name, value in vars(module).items():
        if not name.startswith("_PENDING"):
            continue
        try:
            out[name] = copy.deepcopy(value)
        except Exception:
            pass
    return out


def _restore_pending(module, state):
    for name, value in state.items():
        setattr(module, name, copy.deepcopy(value))


def _package_pending_modules(policy_module):
    rows = []
    seen = set()
    package = getattr(policy_module, "__package__", "") or ""
    prefix = package + "." if package else ""
    for name, module in list(sys.modules.items()):
        if module is not policy_module and not (prefix and name.startswith(prefix)):
            continue
        if module is None or id(module) in seen:
            continue
        seen.add(id(module))
        rows.append((module, _pending_snapshot(module)))
    return rows


def probe_policy_action(policy_module, raw: dict):
    """Process one observation once and retain the pre-choice action memory."""
    probe_state = {
        "history_before": copy.deepcopy(getattr(policy_module, "_HISTORY", [])),
        "pending_before": _package_pending_modules(policy_module),
    }
    predicted = list(policy_module.agent(copy.deepcopy(raw)))
    probe_state["predicted"] = predicted
    return predicted, probe_state


def apply_probe_choice(policy_module, raw: dict, chosen: list[int], probe_state: dict):
    """Rewrite a previously probed Dawn state to the action actually executed."""
    predicted = list((probe_state or {}).get("predicted") or [])
    if predicted == list(chosen):
        return {"predicted": predicted, "forced": False}
    options = (raw.get("select") or {}).get("option") or []
    semantics = [
        policy_module.pf.semantic(raw, options[index])
        for index in chosen
        if 0 <= index < len(options)
    ]
    if hasattr(policy_module, "_HISTORY"):
        history_before = copy.deepcopy((probe_state or {}).get("history_before") or [])
        policy_module._HISTORY = (history_before + semantics)[-8:]
    for module, pending in (probe_state or {}).get("pending_before") or []:
        _restore_pending(module, pending)
    return {"predicted": predicted, "forced": True}


def sync_policy_action(policy_module, raw: dict, chosen: list[int]):
    """Process one observation and synchronize policy state to the executed action."""
    predicted, probe_state = probe_policy_action(policy_module, raw)
    return apply_probe_choice(policy_module, raw, chosen, probe_state)


def next_planned_action(raw: dict, policy_module, plan: dict, step_index: int):
    """Return a remapped planned action and sync Dawn, or an explicit refusal."""
    semantic_path = (plan or {}).get("semantic_path") or []
    if not 0 <= int(step_index) < len(semantic_path):
        return None, {"ok": False, "reason": "plan_exhausted"}
    expected = semantic_path[int(step_index)]
    action = remap_step(raw, expected)
    if action is None:
        return None, {"ok": False, "reason": "semantic_unavailable", "expected": expected}
    actual = _signature(raw, action)
    wanted = tuple(tuple(int(v) for v in sig) for sig in expected)
    if actual != wanted:
        return None, {"ok": False, "reason": "semantic_mismatch", "expected": expected, "actual": actual}
    sync = sync_policy_action(policy_module, raw, action)
    return action, {
        "ok": True,
        "reason": "planned",
        "step_index": int(step_index),
        "semantic": [list(sig) for sig in actual],
        **sync,
    }
