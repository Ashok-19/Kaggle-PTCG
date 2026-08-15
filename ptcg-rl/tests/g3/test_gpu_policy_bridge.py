from __future__ import annotations

from types import SimpleNamespace

import torch

from ptcg_rl.g3.gpu_policy_bridge import build_torch_policy_batch


def _projection_fixture():
    envs = 3
    globals_ = torch.zeros((envs, 24), dtype=torch.int32)
    globals_[:, 0] = torch.tensor([3, 4, 5])
    globals_[:, 1] = 2
    globals_[:, 2] = torch.tensor([0, 1, 0])
    globals_[:, 6] = torch.tensor([7, 1, 3])  # native select types 6, 0, 2
    globals_[:, 7] = torch.tensor([2, 1, 3])  # native contexts 1, 0, 2
    globals_[:, 8] = 1
    globals_[:, 9] = 1
    globals_[:, 10] = 4
    globals_[:, 11] = 2
    globals_[:, 16] = torch.tensor([0, 100, 0])
    globals_[:, 17] = torch.tensor([0, 0, 200])
    globals_[:, 12:16] = torch.tensor(
        [[1, 0, 1, 0], [0, 1, 0, 1], [1, 1, 1, 1]]
    )

    players = torch.zeros((envs, 2, 12), dtype=torch.int32)
    players[:, 0, :7] = torch.tensor([40, 7, 4, 1, 3, 5, 0])
    players[:, 1, :7] = torch.tensor([35, 5, 3, 0, 2, 5, 0])

    entities = torch.zeros((envs, 8, 19), dtype=torch.int32)
    entity_counts = torch.tensor([4, 2, 4], dtype=torch.int32)
    for env in range(envs):
        entities[env, 0, :15] = torch.tensor(
            [100 + env, 0, 4, 1, 1, 220, 220, 0, 0, 1, 0, 0, 0, 0, 0]
        )
        entities[env, 1, :15] = torch.tensor(
            [200 + env, 1, 4, 1, 1, 180, 180, 0, 0, 0, 0, 0, 0, 0, 0]
        )
    entities[0, 0, 18] = 20
    entities[0, 1, 18] = 30
    entities[1, 0, 18] = 40
    entities[1, 1, 18] = 41
    entities[2, 0, 18] = 31
    entities[2, 1, 18] = 32
    # Env 0: bench + hidden prize slot exercise canonical role/missing conversion.
    entities[0, 2, :15] = torch.tensor(
        [300, 0, 5, 3, 1, 100, 120, 20, 1, 0, 0, 0, 0, 0, 0]
    )
    entities[0, 2, 18] = 9
    entities[0, 3, :5] = torch.tensor([0, 1, 6, 2, 0])
    # Env 2: an attached energy. Deliberately use raw role 5; source lookup must
    # use public card id + parent role rather than the attachment list ordinal.
    entities[2, 0, 16] = 1 << 6  # native energy-index presence: type 6
    entities[2, 2, :18] = torch.tensor(
        [6, 0, 8, 5, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 4]
    )
    entities[2, 2, 18] = 10
    # Same card id and same parent as row2, but a distinct physical attachment/ref.
    entities[2, 3, :18] = torch.tensor(
        [6, 0, 8, 6, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 4]
    )
    entities[2, 3, 18] = 12

    options = torch.zeros((envs, 4, 20), dtype=torch.int32)
    option_counts = torch.ones(envs, dtype=torch.int32)
    # Env 0: ATTACK. GPU intentionally omits its source; bridge restores active source.
    options[0, 0, 0] = 13
    options[0, 0, 1] = 7
    options[0, 0, 2] = 2
    options[0, 0, 3] = 77
    options[0, 0, 16] = 77
    options[0, 0, 19] = 1
    # Env 1: RETREAT. Same canonical active-source rule.
    options[1, 0, 0] = 12
    options[1, 0, 1] = 1
    options[1, 0, 2] = 1
    options[1, 0, 13] = 4
    options[1, 0, 14] = 1
    options[1, 0, 15] = 0
    options[1, 0, 19] = 1
    # Env 2: ENERGY_CARD. Public raw fields identify parent + attachment ordinal.
    options[2, 0, 0] = 5
    options[2, 0, 1] = 3
    options[2, 0, 2] = 3
    options[2, 0, 3:7] = torch.tensor([4, 0, 0, 0])
    options[2, 0, 8] = 6
    options[2, 0, 9] = 102
    options[2, 0, 17] = 12  # exact second duplicate attachment, bridge-only
    options[2, 0, 10:16] = torch.tensor([8, 1, 0, 4, 1, 0])
    options[2, 0, 19] = 1

    projection = SimpleNamespace(
        globals=globals_,
        players=players,
        entities=entities,
        entity_counts=entity_counts,
        options=options,
        option_counts=option_counts,
        status=torch.zeros(envs, dtype=torch.uint32),
    )

    event_rows = torch.zeros((envs, 5, 10), dtype=torch.int32)
    event_counts = torch.tensor([3, 0, 1], dtype=torch.int32)
    # Env 0: DRAW card55 serial9, ATTACH by opponent card6 serial10 -> target serial20,
    # then PLAY card55 serial9 again. Identity 9 must retain the same compact id.
    event_rows[0, 0, :5] = torch.tensor([4, 3, 0, 55, 9])
    event_rows[0, 1, :7] = torch.tensor([11, 5, 1, 6, 10, 100, 20])
    event_rows[0, 2, :5] = torch.tensor([10, 3, 0, 55, 9])
    # Env 2: HP change by actor1 relative to current actor1.
    event_rows[2, 0, :7] = torch.tensor([16, 5, 1, 202, 31, -40, 1])
    events = SimpleNamespace(
        events=event_rows,
        counts=event_counts,
        status=torch.zeros(envs, dtype=torch.uint32),
    )
    status = SimpleNamespace(
        select_players=torch.tensor([0, 1, 1], dtype=torch.int8),
        game_results=torch.zeros(envs, dtype=torch.uint8),
    )
    return projection, events, status


def test_gpu_bridge_maps_players_globals_entities_and_option_links() -> None:
    projection, events, status = _projection_fixture()
    batch, meta = build_torch_policy_batch(projection, events, status)

    assert batch.batch_size == 3
    assert meta.actors.tolist() == [0, 1, 1]
    assert batch.player_categorical[:, :, 0].tolist() == [[0, 1], [0, 1], [0, 1]]
    assert batch.player_categorical[:, :, 1].tolist() == [[1, 0], [1, 0], [1, 0]]
    assert batch.global_categorical[:, 2].tolist() == [6, 0, 2]
    assert batch.global_categorical[:, 3].tolist() == [1, 0, 2]
    assert batch.global_categorical_missing[:, 1].all()  # ongoing state => terminal result missing
    assert batch.global_categorical_missing[:, 5].tolist() == [True, False, True]
    assert batch.global_categorical_missing[:, 6].tolist() == [True, True, False]
    assert batch.global_categorical[:, 7:11].tolist() == [
        [1, 0, 1, 0], [0, 1, 0, 1], [1, 1, 1, 1]
    ]

    # Env0 entity rows occupy [0:4]. Bench raw role 3 becomes canonical position 2;
    # hidden prize card id/HP are missing but visibility/count/status fields are observed.
    assert batch.entity_categorical[2, 3].item() == 2
    assert batch.entity_categorical[3, 3].item() == 0
    assert batch.entity_categorical_missing[3, 0]
    assert batch.entity_numeric_missing[3, :4].all()
    assert not batch.entity_numeric_missing[3, 4:].any()
    assert batch.entity_parent_indices.tolist() == [-1, -1, -1, -1, -1, -1, -1, -1, 6, 6]
    assert batch.entity_energy_values.tolist() == [6]
    assert batch.entity_energy_offsets.tolist() == [0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1]

    # Attack and retreat sources are active entities. Env2 ENERGY_CARD source is
    # the exact second duplicate attached energy (flattened entity 9) and target is env2 active (6).
    assert batch.option_source_entity_indices.tolist() == [0, 4, 9]
    assert batch.option_target_entity_indices.tolist() == [-1, -1, 6]
    assert batch.option_categorical[:, 3].tolist() == [1, 1, 1]
    assert batch.option_categorical[:, 4].tolist() == [0, 0, 1]
    assert batch.option_categorical[0, 9].item() == 77
    assert not batch.option_categorical_missing[0, 9]


def test_gpu_bridge_matches_cpu_first_occurrence_event_identities_and_exact_links() -> None:
    projection, events, status = _projection_fixture()
    batch, _ = build_torch_policy_batch(projection, events, status)

    assert batch.event_offsets.tolist() == [0, 3, 3, 4]
    # DRAW serial9 is the first public identity => token1, independent of entity row.
    assert batch.event_categorical[0, 0].item() == 4
    assert batch.event_categorical[0, 1].item() == 0
    assert batch.event_categorical[0, 3].item() == 55
    assert batch.event_identity[0, 0].item() == 1
    # ATTACH serial10 is second identity; target serial20 is third, regardless of entity rows.
    assert batch.event_categorical[1, 1].item() == 1
    assert batch.event_categorical[1, 10].item() == 100
    assert batch.event_identity[1, 0].item() == 2
    assert batch.event_identity[1, 5].item() == 3
    # PLAY reuses serial9 and therefore first-occurrence token1.
    assert batch.event_identity[2, 0].item() == 1
    # HP_CHANGE value and putDamageCounter are mapped separately.
    assert batch.event_numeric[3, 0].item() == -40
    assert batch.event_categorical[3, 12].item() == 1
    assert not batch.event_numeric_missing[3, 0]
    # Current-entity references are restored exactly; event-only serial10 stays unlinked.
    expected_links = torch.full((4, 6), -1, dtype=torch.long)
    expected_links[0, 0] = 2
    expected_links[1, 5] = 0
    expected_links[2, 0] = 2
    expected_links[3, 0] = 6
    assert torch.equal(batch.event_entity_indices.cpu(), expected_links)
    # Env2 HP_CHANGE serial31 is env2 entity0 => local identity token1.
    assert batch.event_identity[3, 0].item() == 1
