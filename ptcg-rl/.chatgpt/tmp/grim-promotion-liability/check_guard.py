"""Fresh-process checks for the isolated Dragapult ToActive guard."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PACKAGE = ROOT / ".chatgpt/tmp/grim-promotion-liability/arena-agents/grim-promotion-dragapult"
FIXTURE_CHECK = ROOT / ".chatgpt/tmp/grim-promotion-liability-fixture/check_fixture.py"
REPLAY = ROOT / ".chatgpt/tmp/grim-live-55372188/replays/91269364.json"
CONTROL_TAR = ROOT / ".chatgpt/tmp/submissions/kptcg-grim-control-v1.tar.gz"
ENGINE = ROOT / "private/assets/official/sample_submission/sample_submission"
WORKER = r'''
import json
import human_controller as hc
obs = json.load(__import__("sys").stdin)
memory = {"plan": "survive", "profile": "", "active_ko_risk": False}
guard = hc._dragapult_promotion_guard(obs)
direct = hc._direct_selection(obs, memory)
options = (obs.get("select") or {}).get("option") or []
maximum = int((obs.get("select") or {}).get("maxCount", 0) or 0)
baseline = [min(len(options), maximum) - 1] if options and maximum else []
candidates = {name: baseline for name in ("baseline_route", "model", "strategic", "mirror", "tempo", "coalition")}
action = hc.choose(obs, candidates)
print(json.dumps({"action": action, "direct": direct, "guard": guard}, sort_keys=True))
'''


REPLAY_WORKER = r'''
import json
import sys
import main
import human_controller as hc
import policy_features as pf

obs = json.load(sys.stdin)
action = main.agent(obs)
guard = hc._dragapult_promotion_guard(obs) if hasattr(hc, "_dragapult_promotion_guard") else None
options = (obs.get("select") or {}).get("option") or []
current = obs.get("current") or {}
players = current.get("players") or []
your = current.get("yourIndex")
opponent = players[1 - your] if len(players) == 2 and your in (0, 1) else {}
opponent_active = (opponent.get("active") or [{}])[0] or {}
energy_cards = opponent_active.get("energyCards") or []
energy_check = (
    [bool(hc._energy_for_colorless(card)) for card in energy_cards]
    if hasattr(hc, "_energy_for_colorless")
    else None
)

def semantic(action):
    if not isinstance(action, list):
        return None
    result = []
    for index in action:
        if not isinstance(index, int) or not 0 <= index < len(options):
            return None
        item = pf.semantic(obs, options[index])
        result.append(tuple((key, item.get(key)) for key in ("type", "source_id", "target_id", "attack_id", "area", "inplay_area")))
    return result

print(json.dumps({
    "action": action,
    "energy_ids": [card.get("id") for card in energy_cards],
    "energy_ok": energy_check,
    "guard": guard,
    "semantic": semantic(action),
}, sort_keys=True))
'''


SEQUENTIAL_WORKER = r'''
import json
import sys
import main
import human_controller as hc
import policy_features as pf

payload = json.load(sys.stdin)
startup = payload.get("startup")
if startup is not None:
    deck = main.agent(startup)
    if not isinstance(deck, list) or len(deck) != 60:
        raise RuntimeError("startup callback did not return the 60-card deck")

def semantic(obs, action):
    options = (obs.get("select") or {}).get("option") or []
    if not isinstance(action, list):
        return None
    result = []
    for index in action:
        if not isinstance(index, int) or not 0 <= index < len(options):
            return None
        item = pf.semantic(obs, options[index])
        result.append(tuple((key, item.get(key)) for key in ("type", "source_id", "target_id", "attack_id", "area", "inplay_area")))
    return result

results = []
for step, obs in payload["observations"]:
    action = main.agent(obs)
    results.append({
        "action": action,
        "guard": hc._dragapult_promotion_guard(obs) if hasattr(hc, "_dragapult_promotion_guard") else None,
        "semantic": semantic(obs, action),
        "step": step,
    })
print(json.dumps(results, sort_keys=True))
'''


def card(card_id: int, hp: int, max_hp: int, *, serial: int | None = None, energy: list[int] | None = None) -> dict:
    value = {"id": card_id, "hp": hp, "maxHp": max_hp, "energyCards": [{"id": item} for item in energy or []]}
    if serial is not None:
        value["serial"] = serial
    return value


def observation() -> dict:
    bench = [
        card(104, 90, 90, serial=73),
        card(112, 100, 110, serial=77),
        card(112, 80, 110, serial=76),
        card(646, 10, 70, serial=81),
        card(646, 70, 70, serial=79),
    ]
    return {
        "current": {
            "yourIndex": 0,
            "players": [
                {"active": [], "bench": bench},
                {"active": [card(121, 320, 320, serial=1210, energy=[7])], "bench": []},
            ],
        },
        "select": {
            "context": 4,
            "minCount": 1,
            "maxCount": 1,
            "option": [{"area": 5, "index": index} for index in range(len(bench))],
        },
    }


def run(obs: dict) -> dict:
    global RUN_COUNT
    RUN_COUNT += 1
    result = subprocess.run(
        [sys.executable, "-c", WORKER],
        cwd=PACKAGE,
        env={**os.environ, "PYTHONPATH": str(PACKAGE)},
        input=json.dumps(obs),
        text=True,
        capture_output=True,
        check=True,
    )
    return json.loads(result.stdout)


def expect_abstain(obs: dict, label: str) -> None:
    result = run(obs)
    assert result["guard"] is None, (label, result)


def _run_replay_observation(package: Path, obs: dict) -> dict:
    result = subprocess.run(
        [sys.executable, "-c", REPLAY_WORKER, str(package), str(ENGINE)],
        cwd=package,
        env={**os.environ, "PYTHONPATH": os.pathsep.join((str(ENGINE), str(package)))},
        input=json.dumps(obs),
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or f"worker exit {result.returncode}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid worker output: {result.stdout!r}") from exc


def _run_sequential_replay(package: Path, payload: dict) -> list[dict]:
    result = subprocess.run(
        [sys.executable, "-c", SEQUENTIAL_WORKER, str(package), str(ENGINE)],
        cwd=package,
        env={**os.environ, "PYTHONPATH": os.pathsep.join((str(ENGINE), str(package)))},
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or f"worker exit {result.returncode}")
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid sequential worker output: {result.stdout!r}") from exc
    if not isinstance(value, list):
        raise TypeError("sequential worker output is not a list")
    return value


def _extract_control(destination: Path) -> Path:
    with tarfile.open(CONTROL_TAR, "r:gz") as archive:
        for member in archive.getmembers():
            path = Path(member.name)
            if path.is_absolute() or ".." in path.parts:
                raise RuntimeError(f"unsafe control archive member: {member.name!r}")
        archive.extractall(destination, filter="data")
    return destination


def replay_audit() -> None:
    replay_hash = hashlib.sha256(REPLAY.read_bytes()).hexdigest()
    assert replay_hash == "e0658d6a180a1e527979dc792ba621bbbc390c73bdf8e43f6ae29168c682abcc"
    replay = json.loads(REPLAY.read_text(encoding="utf-8"))
    nnmax = replay["info"]["TeamNames"].index("NNMax")
    observations = []
    for step, records in enumerate(replay["steps"][:-1]):
        record = records[nnmax]
        observation = record.get("observation") or {}
        if record.get("status") != "ACTIVE" or observation.get("select") is None:
            continue
        observations.append((step, observation))
    assert len(observations) == 73, len(observations)
    sequential_payload = {
        "startup": replay["steps"][0][nnmax].get("observation"),
        "observations": [[step, observation] for step, observation in observations],
    }

    with tempfile.TemporaryDirectory(dir=ROOT / ".chatgpt/tmp/grim-promotion-liability") as temporary:
        control = _extract_control(Path(temporary))
        candidate_results = {}
        control_results = {}
        exceptions = []
        for step, observation in observations:
            for label, package, results in (
                ("candidate", PACKAGE, candidate_results),
                ("control", control, control_results),
            ):
                try:
                    results[step] = _run_replay_observation(package, observation)
                except RuntimeError as exc:  # retain every failed isolated process for the audit
                    exceptions.append({"agent": label, "step": step, "error": repr(exc)})
        sequential_results = {}
        for label, package in (("candidate", PACKAGE), ("control", control)):
            try:
                sequential_results[label] = _run_sequential_replay(package, sequential_payload)
            except RuntimeError as exc:
                exceptions.append({"agent": label, "audit": "sequential", "error": repr(exc)})

    assert not exceptions, exceptions
    activations = [step for step, result in candidate_results.items() if result["guard"] is not None]
    assert activations == [158], activations
    assert candidate_results[158]["guard"] == [1]
    assert candidate_results[158]["action"] == [1]
    assert candidate_results[158]["energy_ids"] == [5, 2]
    assert candidate_results[158]["energy_ok"] == [True, True]
    assert control_results[158]["action"] == [4]
    assert candidate_results[123]["guard"] is None
    assert candidate_results[123]["action"] == control_results[123]["action"]

    semantic_matches = sum(
        candidate_results[step]["semantic"] == control_results[step]["semantic"]
        for step, _ in observations
    )
    changed = [
        step for step, _ in observations
        if candidate_results[step]["semantic"] != control_results[step]["semantic"]
    ]
    fixes = [step for step in changed if step == 158]
    breaks = [step for step in changed if step != 158]
    assert changed == [158], changed
    assert fixes == [158] and not breaks

    sequential_candidate = sequential_results["candidate"]
    sequential_control = sequential_results["control"]
    assert len(sequential_candidate) == len(sequential_control) == len(observations)
    sequential_candidate_by_step = {item["step"]: item for item in sequential_candidate}
    sequential_control_by_step = {item["step"]: item for item in sequential_control}
    assert [step for step, item in sequential_candidate_by_step.items() if item["guard"] is not None] == [158]
    assert sequential_candidate_by_step[158]["action"] == [1]
    assert sequential_control_by_step[158]["action"] == [4]
    assert sequential_candidate_by_step[123]["guard"] is None
    sequential_matches = sum(
        sequential_candidate_by_step[step]["semantic"] == sequential_control_by_step[step]["semantic"]
        for step, _ in observations
    )
    sequential_changed = [
        step for step, _ in observations
        if sequential_candidate_by_step[step]["semantic"] != sequential_control_by_step[step]["semantic"]
    ]
    assert sequential_changed == [158], sequential_changed

    step158 = replay["steps"][158][nnmax]["observation"]
    active = step158["current"]["players"][1 - step158["current"]["yourIndex"]]["active"][0]
    attached = [card.get("id") for card in active.get("energyCards") or []]
    assert active.get("id") == 121 and attached == [5, 2], (active, attached)
    print(
        "REPLAY PASS: 91269364 "
        f"observations={len(observations)} exceptions={len(exceptions)} "
        f"semantic_matches={semantic_matches}/{len(observations)} "
        f"guard_activations={activations} fix_minus_break={len(fixes)}-{len(breaks)} "
        f"step158_dragapult_energy_ids={attached} "
        f"energy_ok={candidate_results[158]['energy_ok']} "
        f"step123_guard={candidate_results[123]['guard']}"
    )
    print(
        "RECORDED-CONTROL TRAJECTORY PASS (not counterfactual outcome evidence): "
        f"observations={len(observations)} exceptions=0 "
        f"semantic_matches={sequential_matches}/{len(observations)} "
        f"changes={sequential_changed}"
    )


def main() -> None:
    global RUN_COUNT
    RUN_COUNT = 0
    receipt = json.loads((PACKAGE / "receipt.json").read_text(encoding="utf-8"))
    assert receipt["module"] == {
        "bytes": (PACKAGE / "main.py").stat().st_size,
        "sha256": hashlib.sha256((PACKAGE / "main.py").read_bytes()).hexdigest(),
    }
    assert receipt["experiment_sources"]["human_controller"] == {
        "bytes": (PACKAGE / "human_controller.py").stat().st_size,
        "sha256": hashlib.sha256((PACKAGE / "human_controller.py").read_bytes()).hexdigest(),
    }
    fixture = subprocess.run([sys.executable, str(FIXTURE_CHECK)], check=True, capture_output=True, text=True)
    assert "PASS" in fixture.stdout

    positive = observation()
    assert run(positive) == {"action": [1], "direct": [4], "guard": [1]}

    case = copy.deepcopy(positive)
    case["current"]["players"][1]["active"][0]["energyCards"] = []
    expect_abstain(case, "uncharged Dragapult")

    for wrong_energy in (1219, 15):
        case = copy.deepcopy(positive)
        case["current"]["players"][1]["active"][0]["energyCards"] = [{"id": wrong_energy}]
        expect_abstain(case, f"wrong energy {wrong_energy}")

    case = copy.deepcopy(positive)
    case["current"]["players"][1]["active"][0]["id"] = 96
    expect_abstain(case, "non-Dragapult")

    case = copy.deepcopy(positive)
    case["current"]["players"][0]["bench"][1]["hp"] = 80
    case["current"]["players"][0]["bench"][2]["hp"] = 80
    expect_abstain(case, "no Munkidori survives 70")

    case = copy.deepcopy(positive)
    case["current"]["players"][0]["bench"] = case["current"]["players"][0]["bench"][:3]
    case["select"]["option"] = case["select"]["option"][:3]
    expect_abstain(case, "no Impidimp")
    expect_abstain(case, "second ToActive without Impidimp")

    for bad_option in (
        {"index": 0},
        {"area": 5, "index": 99},
        {"area": 5, "index": 1},
    ):
        case = copy.deepcopy(positive)
        case["select"]["option"][0] = bad_option
        if bad_option == {"area": 5, "index": 1}:
            case["select"]["option"][1] = {"area": 5, "index": 1}
        expect_abstain(case, f"malformed option {bad_option}")

    for minimum, maximum in ((0, 1), (1, 2)):
        case = copy.deepcopy(positive)
        case["select"]["minCount"] = minimum
        case["select"]["maxCount"] = maximum
        expect_abstain(case, f"selection bounds {minimum}/{maximum}")

    case = copy.deepcopy(positive)
    case["select"]["option"] = [
        {"area": 5, "index": 4},
        {"area": 5, "index": 2},
        {"area": 5, "index": 1},
        {"area": 5, "index": 0},
        {"area": 5, "index": 3},
    ]
    assert run(case) == {"action": [2], "direct": [0], "guard": [2]}

    case = copy.deepcopy(positive)
    case["current"]["players"][0]["bench"][1]["hp"] = 75
    case["current"]["players"][0]["bench"][2]["hp"] = 100
    assert run(case) == {"action": [2], "direct": [4], "guard": [2]}

    case = copy.deepcopy(positive)
    case["current"]["players"][0]["bench"].append(card(104, 90, 90, serial=74))
    case["select"]["option"].append({"area": 5, "index": 5})
    expect_abstain(case, "stacked Froslass")

    case = copy.deepcopy(positive)
    case["current"]["players"][0]["bench"][0] = None
    expect_abstain(case, "ambiguous Froslass projection")

    replay_audit()

    print(f"PASS: Dragapult ToActive promotion guard matrix ({RUN_COUNT} fresh processes)")


if __name__ == "__main__":
    main()
