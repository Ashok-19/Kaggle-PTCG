"""Check the sanitized Dragapult promotion-liability evidence fixture."""

from __future__ import annotations

import json
import re
from pathlib import Path


FIXTURE = Path(__file__).with_name("fixture.json")
SHA256 = re.compile(r"[0-9a-f]{64}")


def check() -> None:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert data["schema_version"] == 1
    assert data["scope"] == "FIXTURE_ONLY"

    source = data["source"]
    assert source["replay_episode_id"] == 91269364
    assert source["replay_body_embedded"] is False
    assert source["replay_sha256"] == (
        "e0658d6a180a1e527979dc792ba621bbbc390c73bdf8e43f6ae29168c682abcc"
    )
    assert SHA256.fullmatch(source["package_sha256"])

    observation = data["observation"]
    assert observation["selection_context"] == "ToActive"
    candidates = observation["candidates"]
    assert len(candidates) == observation["option_count"] == 5
    assert [candidate["index"] for candidate in candidates] == list(range(5))
    assert len({candidate["physical_id"] for candidate in candidates}) == 5
    assert observation["current_package_choice_index"] == 4
    assert candidates[4]["physical_id"] == "Impidimp79"

    expected_max_hp = {
        "Froslass73": 90,
        "Munkidori77": 110,
        "Munkidori76": 110,
        "Impidimp81": 70,
        "Impidimp79": 70,
    }
    for candidate in candidates:
        assert candidate["max_hp"] == expected_max_hp[candidate["physical_id"]]
        assert (
            0
            <= candidate["post_checkup_hp"]
            <= candidate["pre_checkup_hp"]
            <= candidate["max_hp"]
        )
        expected_hp = max(
            candidate["pre_checkup_hp"] - candidate["checkup_damage"], 0
        )
        assert candidate["post_checkup_hp"] == expected_hp

    def survivors(damage: int) -> list[str]:
        return [
            candidate["physical_id"]
            for candidate in candidates
            if candidate["post_checkup_hp"] > damage
        ]

    assert survivors(observation["attacks"]["jet_headbutt"]["damage"]) == [
        "Froslass73",
        "Munkidori77",
    ]
    assert survivors(observation["attacks"]["phantom_dive"]["damage"]) == []

    evolution = observation["evolution_damage_preservation"]
    assert evolution["source_hp"] + evolution["damage_before_evolution"] == evolution[
        "source_max_hp"
    ]
    assert evolution["damage_after_evolution"] == evolution["damage_before_evolution"]
    assert evolution["evolved_hp"] == evolution["evolved_max_hp"] - evolution[
        "damage_after_evolution"
    ]
    assert (evolution["source_physical_id"], evolution["evolved_physical_id"]) == (
        "Impidimp81",
        "Morgrem85",
    )

    hypothesis = data["declared_hypothesis"]
    assert hypothesis == {
        "preferred_physical_id": "Munkidori77",
        "comparison_physical_id": "Froslass73",
        "reason": "retains_engine_role",
        "status": "DECLARED_HYPOTHESIS_NOT_PROVEN",
        "win_authority": False,
    }

    for control in data["controls"]:
        post_hp = control["post_checkup_hp"]
        has_survivor = any(hp > control["jet_headbutt_damage"] for hp in post_hp)
        trigger = control["dragapult_charged"] and has_survivor
        assert trigger is control["expected_trigger"]
        if not control["dragapult_charged"]:
            assert control["expected_reason"] == "DRAGAPULT_NOT_CHARGED"
        else:
            assert not has_survivor
            assert control["expected_reason"] == "NO_SURVIVOR_AT_70"

if __name__ == "__main__":
    check()
    print("PASS: sanitized Dragapult promotion-liability fixture")
