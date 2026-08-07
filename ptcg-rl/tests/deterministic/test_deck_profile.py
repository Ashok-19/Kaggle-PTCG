from __future__ import annotations

from dataclasses import asdict
from collections import Counter

import pytest

from ptcg_rl.deterministic.deck_profile import (
    AttackRequirementV1,
    DeckProfileError,
    DeckProfileV1,
    EvolutionRequirementV1,
    MEGA_ABOMASNOW_CARD_COUNTS,
    MEGA_ABOMASNOW_ORDERED_CARD_IDS,
    RoleAssignmentV1,
    mega_abomasnow_profile,
)
from ptcg_rl.g1.models import stable_hash
from ptcg_rl.g2.card_table import AttackStaticV1, CardStaticV1, CardTableV1


def card_table() -> CardTableV1:
    ids = sorted(set(MEGA_ABOMASNOW_ORDERED_CARD_IDS))
    cards = tuple(
        CardStaticV1(
            card_id=card_id,
            card_type=(0 if card_id in {721, 722, 723} else 1 if card_id in {1121, 1126} else 3 if card_id in {1192, 1227} else 4 if card_id == 1262 else 5),
            energy_type=3 if card_id == 3 else 0,
            weakness_type=-1,
            resistance_type=-1,
            stage_code=1 if card_id == 721 else (2 if card_id == 722 else 3 if card_id == 723 else 0),
            hp=100,
            retreat_cost=1,
            basic=card_id == 721,
            stage1=card_id == 722,
            stage2=card_id == 723,
            ex=card_id == 723,
            mega_ex=card_id == 723,
            tera=False,
            ace_spec=card_id == 1126,
            ancient=False,
            future=False,
            fossil=False,
            technical_machine=False,
            trainers_pokemon=False,
            skill_count=0,
            attack_ids=(1,) if card_id in {721, 723} else (),
        )
        for card_id in ids
    )
    attacks = (AttackStaticV1(1, 100, (0, 0, 0, 2, 0, 0, 0, 0, 0, 0, 0, 0)),)
    payload = {
        "schema_version": 1,
        "card_data_sha256": "c" * 64,
        "engine_library_sha256": "e" * 64,
        "wrapper_api_sha256": "a" * 64,
        "padding_card_id": 0,
        "unknown_card_id": len(cards) + 1,
        "padding_attack_id": 0,
        "unknown_attack_id": len(attacks) + 1,
        "cards": [asdict(card) for card in cards],
        "attacks": [asdict(attack) for attack in attacks],
        "csv_rows": len(cards),
        "ambiguous_type_cards": 0,
    }
    hash_payload = {
        **payload, "cards": [asdict(card) for card in cards], "attacks": [asdict(attack) for attack in attacks]
    }
    return CardTableV1(
        **{**payload, "cards": cards, "attacks": attacks},
        table_sha256=stable_hash(hash_payload),
    )


def all_roles() -> tuple[RoleAssignmentV1, ...]:
    return (
        RoleAssignmentV1(3, ("BASIC_ENERGY",)),
        RoleAssignmentV1(721, ("BASIC_POKEMON", "OPENING")),
        RoleAssignmentV1(722, ("EVOLUTION_PIECE",)),
        RoleAssignmentV1(723, ("PRIMARY_ATTACKER",)),
        RoleAssignmentV1(1121, ("SEARCH",)),
        RoleAssignmentV1(1126, ("ACE_SPEC", "SEARCH")),
        RoleAssignmentV1(1192, ("SUPPORTER",)),
        RoleAssignmentV1(1227, ("SUPPORTER",)),
        RoleAssignmentV1(1262, ("STADIUM",)),
    )


def test_exact_mega_abomasnow_fixture_is_numeric_and_exact_60() -> None:
    profile = mega_abomasnow_profile(card_table())
    assert len(profile.ordered_card_ids) == 60
    assert Counter(profile.ordered_card_ids) == Counter({
        3: 34, 721: 2, 722: 4, 723: 4, 1121: 4,
        1126: 1, 1192: 4, 1227: 4, 1262: 3,
    })
    assert profile.multiset == MEGA_ABOMASNOW_CARD_COUNTS
    assert profile.multiset_hash == "54d2e50f6afd8dab71b96d936bac48510e5f89e93f6f1dc0b97bb5d501f51cb5"
    assert profile.multiset == (
        (3, 34), (721, 2), (722, 4), (723, 4), (1121, 4),
        (1126, 1), (1192, 4), (1227, 4), (1262, 3),
    )
    assert profile.deck_id == "mega-abomasnow-ex"
    assert profile.evolution_requirements == (EvolutionRequirementV1(723, (722,)),)
    assert tuple(row.card_id for row in profile.attack_requirements) == (721, 723)
    assert profile.attack_requirements[-1].energy_counts[3] == 2
    assert "name" not in repr(profile).lower()
    assert "text" not in repr(profile).lower()


def test_hashes_are_canonical_and_round_trip() -> None:
    profile = DeckProfileV1.build(
        card_table(),
        MEGA_ABOMASNOW_ORDERED_CARD_IDS,
        deck_id="fixture",
        roles=all_roles(),
        evolution_requirements=(EvolutionRequirementV1(723, (722,)),),
        attack_requirements=(
            AttackRequirementV1(721, 1, (0, 0, 0, 2, 0, 0, 0, 0, 0, 0, 0, 0)),
            AttackRequirementV1(723, 1, (0, 0, 0, 2, 0, 0, 0, 0, 0, 0, 0, 0)),
        ),
    )
    loaded = DeckProfileV1.from_mapping(profile.canonical_dict())
    assert loaded == profile
    assert loaded.profile_sha256 == profile.profile_hash
    assert set(profile.hashes) == {"ordered", "multiset", "role", "requirements", "profile"}


def test_exact_60_and_card_table_binding_fail_closed() -> None:
    with pytest.raises(DeckProfileError, match="exactly 60"):
        DeckProfileV1.build(card_table(), (3,) * 59, deck_id="short")
    with pytest.raises(DeckProfileError, match="absent"):
        DeckProfileV1.build(card_table(), (999,) + MEGA_ABOMASNOW_ORDERED_CARD_IDS[1:], deck_id="bad")


def test_requirement_mismatch_and_tampering_fail_closed() -> None:
    with pytest.raises(DeckProfileError, match="energy requirement"):
        DeckProfileV1.build(
            card_table(),
            MEGA_ABOMASNOW_ORDERED_CARD_IDS,
            deck_id="bad-requirement",
            roles=all_roles(),
            attack_requirements=(AttackRequirementV1(723, 1, (0,) * 12),),
        )
    profile = mega_abomasnow_profile(card_table())
    tampered = profile.canonical_dict()
    tampered["ordered_card_ids"] = list(reversed(tampered["ordered_card_ids"]))
    with pytest.raises(DeckProfileError, match="ordered_hash"):
        DeckProfileV1.from_mapping(tampered)


def test_role_coverage_ace_spec_and_provenance_fail_closed() -> None:
    with pytest.raises(DeckProfileError, match="role label"):
        RoleAssignmentV1(721, ("PRIVATE_SCORE",))
    with pytest.raises(DeckProfileError, match="cover every distinct"):
        DeckProfileV1.build(
            card_table(), MEGA_ABOMASNOW_ORDERED_CARD_IDS, deck_id="missing-role", roles=all_roles()[:-1]
        )
    duplicate_ace = list(MEGA_ABOMASNOW_ORDERED_CARD_IDS)
    duplicate_ace[-1] = 1126
    with pytest.raises(DeckProfileError, match="Ace Spec"):
        DeckProfileV1.build(
            card_table(), duplicate_ace, deck_id="two-ace-specs", roles=all_roles()
        )
    with pytest.raises(DeckProfileError, match="predecessor stage"):
        DeckProfileV1.build(
            card_table(), MEGA_ABOMASNOW_ORDERED_CARD_IDS, deck_id="bad-evolution", roles=all_roles(),
            evolution_requirements=(EvolutionRequirementV1(723, (721,)),),
        )


def test_profile_parser_rejects_type_coercion_and_exposes_asset_bindings() -> None:
    profile = mega_abomasnow_profile(card_table())
    assert profile.asset_hashes == {
        "card_table": profile.card_table_sha256,
        "card_data": profile.card_data_sha256,
        "engine_library": profile.engine_library_sha256,
        "wrapper_api": profile.wrapper_api_sha256,
    }
    tampered = profile.canonical_dict()
    tampered["roles"][0]["card_id"] = str(tampered["roles"][0]["card_id"])
    with pytest.raises(DeckProfileError, match="invalid deck profile mapping"):
        DeckProfileV1.from_mapping(tampered)
