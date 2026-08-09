from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / ".chatgpt/tmp/grim-punk-tuning/arena-agents/grim-punk-floor4"
OUTPUT = ROOT / ".chatgpt/tmp/grim-promotion-liability/arena-agents/grim-promotion-dragapult"
POLICY_ID = "grim-promotion-dragapult"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


HELPER = '''

def _safe_card_id(card):
    if not isinstance(card, dict):
        return None
    value = card.get("id")
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _energy_for_colorless(card):
    card_id = _safe_card_id(card)
    if card_id is None:
        return False
    metadata = pf.cards.get(card_id)
    if not metadata or metadata.get("Stage (Pokémon)/Type (Energy and Trainer)") not in ("Basic Energy", "Special Energy"):
        return False
    # Team Rocket's Energy is illegal on Dragapult ex even though it is an Energy card.
    return card_id != 15


def _dragapult_promotion_guard(obs):
    sel = obs.get("select") or {}
    if sel.get("context") != 4 or sel.get("minCount") != 1 or sel.get("maxCount") != 1:
        return None
    opts = sel.get("option")
    if not isinstance(opts, list) or not opts:
        return None

    cur = obs.get("current") or {}
    players = cur.get("players")
    your = cur.get("yourIndex")
    if not isinstance(players, list) or len(players) != 2 or your not in (0, 1):
        return None
    me, opp = players[your], players[1 - your]
    if not isinstance(me, dict) or not isinstance(opp, dict) or me.get("active"):
        return None

    opp_active = opp.get("active")
    if not isinstance(opp_active, list) or len(opp_active) != 1:
        return None
    dragapult = opp_active[0]
    if _safe_card_id(dragapult) != 121 or not isinstance(dragapult.get("energyCards"), list):
        return None
    if not dragapult["energyCards"] or not all(_energy_for_colorless(card) for card in dragapult["energyCards"]):
        return None

    froslass_count = 0
    for player in players:
        if not isinstance(player, dict):
            return None
        for area in ("active", "bench"):
            cards = player.get(area)
            if not isinstance(cards, list):
                return None
            for card in cards:
                card_id = _safe_card_id(card)
                if card_id is None:
                    return None
                if card_id == FROSLASS:
                    froslass_count += 1
    if froslass_count != 1:
        return None

    bench = me.get("bench")
    if not isinstance(bench, list):
        return None
    resolved = []
    references = set()
    for option_index, option in enumerate(opts):
        if not isinstance(option, dict) or option.get("area") != 5:
            return None
        if "playerIndex" in option and option.get("playerIndex") != your:
            return None
        bench_index = option.get("index")
        if isinstance(bench_index, bool) or not isinstance(bench_index, int):
            return None
        reference = (your, bench_index)
        if reference in references or not 0 <= bench_index < len(bench):
            return None
        references.add(reference)
        card = bench[bench_index]
        card_id = _safe_card_id(card)
        if card_id is None or card_id not in pf.cards:
            return None
        hp = card.get("hp")
        max_hp = card.get("maxHp")
        if isinstance(hp, bool) or isinstance(max_hp, bool) or not isinstance(hp, int) or not isinstance(max_hp, int) or not 0 < hp <= max_hp:
            return None
        resolved.append((option_index, card_id, hp))

    if not any(card_id == IMPIDIMP for _, card_id, _ in resolved):
        return None
    surviving_munkidori = [
        (option_index, hp - 10)
        for option_index, card_id, hp in resolved
        if card_id == MUNKIDORI and hp - 10 > 70
    ]
    if not surviving_munkidori:
        return None
    return [max(surviving_munkidori, key=lambda item: item[1])[0]]
'''


def build() -> Path:
    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    shutil.copytree(SOURCE, OUTPUT)

    controller = OUTPUT / "human_controller.py"
    text = controller.read_text(encoding="utf-8")
    helper_anchor = "def _direct_selection(obs,mem):\n"
    if helper_anchor not in text:
        raise RuntimeError("direct-selection function anchor missing")
    text = text.replace(helper_anchor, HELPER + "\n" + helper_anchor, 1)

    newline = chr(10)
    choose_anchor = "def choose(obs,candidates):" + newline + "    mem=hm.update(obs);baseline=candidates.get('baseline_route',[]);coalition=candidates.get('coalition',[])" + newline
    choose_guard = "def choose(obs,candidates):" + newline + "    mem=hm.update(obs);baseline=candidates.get('baseline_route',[]);coalition=candidates.get('coalition',[])" + newline + "    guarded = _dragapult_promotion_guard(obs)" + newline + "    if guarded is not None and _legal(obs,guarded):" + newline + "        return guarded" + newline
    if choose_anchor not in text:
        raise RuntimeError("human choose insertion anchor missing")
    text = text.replace(choose_anchor, choose_guard, 1)
    controller.write_text(text, encoding="utf-8")

    receipt_path = OUTPUT / "receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["baseline_id"] = POLICY_ID
    receipt["policy_id"] = POLICY_ID
    receipt["deck"] = {"bytes": (OUTPUT / "deck.csv").stat().st_size, "sha256": sha256(OUTPUT / "deck.csv")}
    main_module = OUTPUT / "main.py"
    receipt["module"] = {"bytes": main_module.stat().st_size, "sha256": sha256(main_module)}
    receipt["experiment_sources"] = {
        "human_controller": {"bytes": controller.stat().st_size, "sha256": sha256(controller)}
    }
    receipt["experiment"] = "dragapult-toactive-promotion-liability-guard-v1"
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return OUTPUT


if __name__ == "__main__":
    path = build()
    print(path)
    print(json.dumps(json.loads((path / "receipt.json").read_text()), indent=2))
