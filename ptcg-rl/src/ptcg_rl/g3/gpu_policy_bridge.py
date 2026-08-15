from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import torch
from torch import Tensor

from ptcg_rl.g2.network import TorchDecisionBatch


class GpuPolicyBridgeError(ValueError):
    """Raised when a GPU-CABT public projection cannot be mapped safely."""


@dataclass(frozen=True)
class GpuPolicyDecisionMetaV1:
    env_indices: Tensor
    actors: Tensor
    minimum_counts: Tensor
    maximum_counts: Tensor
    option_counts: Tensor


def _require_integer_tensor(value: Any, name: str, ndim: int) -> Tensor:
    if not isinstance(value, Tensor) or value.ndim != ndim:
        raise GpuPolicyBridgeError(f"{name} must be a {ndim}-dimensional tensor")
    if value.dtype not in {
        torch.int8,
        torch.uint8,
        torch.int16,
        torch.int32,
        torch.int64,
        torch.uint32,
        torch.uint64,
    }:
        raise GpuPolicyBridgeError(f"{name} must use an integer dtype")
    return value


def _offsets(lengths: Tensor) -> Tensor:
    return torch.cat(
        (
            torch.zeros(1, dtype=torch.long, device=lengths.device),
            lengths.to(torch.long).cumsum(0),
        )
    )


def _flat_owner(lengths: Tensor) -> Tensor:
    return torch.repeat_interleave(
        torch.arange(lengths.numel(), dtype=torch.long, device=lengths.device),
        lengths.to(torch.long),
    )


def _flatten_padded(rows: Tensor, counts: Tensor) -> tuple[Tensor, Tensor]:
    if rows.ndim < 2 or rows.shape[0] != counts.numel():
        raise GpuPolicyBridgeError("padded projection shape differs from counts")
    capacity = rows.shape[1]
    if torch.any(counts < 0) or torch.any(counts > capacity):
        raise GpuPolicyBridgeError("projection count exceeds padded capacity")
    mask = torch.arange(capacity, device=rows.device).unsqueeze(0) < counts.unsqueeze(1)
    return rows[mask], _offsets(counts)


def _position_key(env: Tensor, relative_player: Tensor, area: Tensor, raw_role: Tensor) -> Tensor:
    rel = relative_player.to(torch.long)
    area_long = area.to(torch.long)
    # Native stadium lookup is owner-agnostic when there is a single stadium card.
    rel = torch.where(area_long == 7, torch.full_like(rel, 2), rel)
    return (((env.to(torch.long) * 4 + rel) * 32 + area_long) * 256 + raw_role.to(torch.long))


def _attachment_key(
    env: Tensor,
    relative_player: Tensor,
    area: Tensor,
    card_id: Tensor,
    parent_role: Tensor,
) -> Tensor:
    return (
        ((((env.to(torch.long) * 2 + relative_player.to(torch.long)) * 32 + area.to(torch.long))
          * 2048 + card_id.to(torch.long)) * 256)
        + parent_role.to(torch.long)
    )


def _lookup_sorted(entity_keys: Tensor, query_keys: Tensor, required: Tensor) -> Tensor:
    if query_keys.shape != required.shape or required.dtype != torch.bool:
        raise GpuPolicyBridgeError("entity lookup query mask differs")
    result = torch.full(query_keys.shape, -1, dtype=torch.long, device=query_keys.device)
    if entity_keys.numel() == 0 or query_keys.numel() == 0 or not torch.any(required):
        if torch.any(required):
            raise GpuPolicyBridgeError("required entity reference has no visible candidates")
        return result
    sorted_keys, permutation = torch.sort(entity_keys)
    positions = torch.searchsorted(sorted_keys, query_keys)
    clamped = positions.clamp_max(max(sorted_keys.numel() - 1, 0))
    matched = (positions < sorted_keys.numel()) & (sorted_keys[clamped] == query_keys)
    if torch.any(required & ~matched):
        raise GpuPolicyBridgeError("required option entity reference is absent from public entities")
    selected = permutation[clamped]
    return torch.where(required & matched, selected, result)


def _kind_from_area(area: Tensor) -> Tensor:
    area = area.to(torch.long)
    return torch.where(
        area == 11,
        torch.full_like(area, 2),
        torch.where(
            (area >= 15) & (area <= 23),
            torch.full_like(area, 3),
            torch.where(area == 24, torch.full_like(area, 4), torch.ones_like(area)),
        ),
    )


def _map_event_identities(
    raw_values: Tensor,
    missing: Tensor,
    owner: Tensor,
    entity_raw_refs: Tensor,
    entity_offsets: Tensor,
) -> tuple[Tensor, Tensor]:
    """Compact public serial equality independently from current-entity links.

    Identity ids are assigned by first public occurrence within each decision.
    Raw GPU card refs are used only to recover event->current-entity indices;
    their magnitude and entity row order never enter the identity embedding.
    """
    if raw_values.ndim != 2 or missing.shape != raw_values.shape or owner.ndim != 1:
        raise GpuPolicyBridgeError("event identity tensors have incompatible shapes")
    if raw_values.shape[0] != owner.numel():
        raise GpuPolicyBridgeError("event identity owner mapping differs")
    if entity_raw_refs.ndim != 1 or entity_offsets.ndim != 1:
        raise GpuPolicyBridgeError("entity identity transport tensors have incompatible shapes")
    batch_size = int(entity_offsets.numel()) - 1
    if batch_size < 0 or int(entity_offsets[-1].item()) != int(entity_raw_refs.numel()):
        raise GpuPolicyBridgeError("entity offsets do not consume all raw refs")

    identities = torch.zeros_like(raw_values, dtype=torch.long)
    entity_indices = torch.full_like(raw_values, -1, dtype=torch.long)
    if raw_values.numel() == 0:
        return identities, entity_indices
    flat_owner = owner.unsqueeze(1).expand(-1, raw_values.shape[1]).reshape(-1)
    flat_values = raw_values.to(torch.long).reshape(-1)
    flat_missing = missing.reshape(-1)
    valid = ~flat_missing
    if not torch.any(valid):
        return identities, entity_indices
    valid_positions = torch.nonzero(valid, as_tuple=False).squeeze(1)
    valid_owner = flat_owner[valid]
    valid_values = flat_values[valid]
    if torch.any(valid_values <= 0):
        raise GpuPolicyBridgeError("public event serial identity must be positive")

    # First-public-occurrence compaction, exactly matching CPU row-major event/slot order.
    composite = (valid_owner << 32) | valid_values
    unique_keys, inverse = torch.unique(composite, sorted=True, return_inverse=True)
    first = torch.full(
        (unique_keys.numel(),),
        torch.iinfo(torch.long).max,
        dtype=torch.long,
        device=composite.device,
    )
    first.scatter_reduce_(0, inverse, valid_positions, reduce="amin", include_self=True)
    unique_owner = unique_keys >> 32
    order_key = unique_owner * (raw_values.numel() + 1) + first
    order = torch.argsort(order_key)
    owner_sorted = unique_owner[order]
    sorted_positions = torch.arange(order.numel(), dtype=torch.long, device=order.device)
    starts = torch.ones(order.numel(), dtype=torch.bool, device=order.device)
    if order.numel() > 1:
        starts[1:] = owner_sorted[1:] != owner_sorted[:-1]
    start_positions = torch.where(starts, sorted_positions, torch.zeros_like(sorted_positions))
    start_positions = torch.cummax(start_positions, dim=0).values
    ranks_sorted = sorted_positions - start_positions + 1
    ranks_by_unique = torch.empty_like(ranks_sorted)
    ranks_by_unique[order] = ranks_sorted
    identities.reshape(-1)[valid_positions] = ranks_by_unique[inverse]

    # Independent current-entity lookup via bridge-only visible card refs.
    entity_counts = entity_offsets[1:] - entity_offsets[:-1]
    entity_owner = torch.repeat_interleave(
        torch.arange(batch_size, dtype=torch.long, device=entity_raw_refs.device), entity_counts
    )
    current = entity_raw_refs > 0
    current_keys = (entity_owner[current] << 32) | entity_raw_refs[current].to(torch.long)
    current_indices = torch.nonzero(current, as_tuple=False).squeeze(1)
    if current_keys.numel() > 1:
        sorted_current, _ = torch.sort(current_keys)
        if torch.any(sorted_current[1:] == sorted_current[:-1]):
            raise GpuPolicyBridgeError("visible entity raw ref is not unique within a decision")
    if current_keys.numel():
        sorted_keys, current_order = torch.sort(current_keys)
        positions = torch.searchsorted(sorted_keys, composite)
        clamped = positions.clamp_max(sorted_keys.numel() - 1)
        matched = (positions < sorted_keys.numel()) & (sorted_keys[clamped] == composite)
        matched_indices = torch.full_like(valid_values, -1)
        matched_indices[matched] = current_indices[current_order[clamped[matched]]]
        entity_indices.reshape(-1)[valid_positions] = matched_indices
    return identities, entity_indices

def _map_events(
    event_rows: Tensor,
    event_counts: Tensor,
    actors: Tensor,
    entity_raw_refs: Tensor,
    entity_offsets: Tensor,
) -> tuple[Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor]:
    events, event_offsets = _flatten_padded(event_rows, event_counts)
    owner = _flat_owner(event_counts)
    count = events.shape[0]
    categorical = torch.zeros((count, 17), dtype=torch.long, device=events.device)
    categorical_missing = torch.ones((count, 17), dtype=torch.bool, device=events.device)
    numeric = torch.zeros((count, 1), dtype=torch.float32, device=events.device)
    numeric_missing = torch.ones((count, 1), dtype=torch.bool, device=events.device)
    identity_raw = torch.zeros((count, 6), dtype=torch.long, device=events.device)
    identity_missing = torch.ones((count, 6), dtype=torch.bool, device=events.device)
    entity_indices = torch.full((count, 6), -1, dtype=torch.long, device=events.device)
    if count == 0:
        return (
            categorical,
            categorical_missing,
            numeric,
            numeric_missing,
            identity_raw,
            identity_missing,
            entity_indices,
            event_offsets,
        )

    event_type = events[:, 0].to(torch.long)
    if torch.any((event_type < 0) | (event_type > 23)):
        raise GpuPolicyBridgeError("GPU public event type is outside the native contract")
    categorical[:, 0] = event_type
    categorical_missing[:, 0] = False

    has_player = event_type != 23
    player_value = events[:, 2].to(torch.long)
    event_actor = actors.index_select(0, owner).to(torch.long)
    if torch.any(has_player & ((player_value < 0) | (player_value > 1))):
        raise GpuPolicyBridgeError("GPU public event contains an invalid player reference")
    categorical[:, 1] = torch.where(player_value == event_actor, 0, 1)
    categorical_missing[:, 1] = ~has_player

    def set_cat(column: int, mask: Tensor, parameter: int) -> None:
        categorical[mask, column] = events[mask, 2 + parameter].to(torch.long)
        categorical_missing[mask, column] = False

    def set_identity(column: int, mask: Tensor, parameter: int) -> None:
        identity_raw[mask, column] = events[mask, 2 + parameter].to(torch.long)
        identity_missing[mask, column] = False

    mask = event_type == 1
    set_cat(2, mask, 1)

    main_card = torch.isin(event_type, torch.tensor((4, 6, 10, 11, 12, 13, 14, 15, 16), device=events.device))
    set_cat(3, main_card, 1)
    status_card = (event_type >= 17) & (event_type <= 21)
    set_cat(3, status_card, 2)

    move = event_type == 6
    set_cat(4, move, 3)
    set_cat(5, move, 4)
    move_reverse = event_type == 7
    set_cat(4, move_reverse, 1)
    set_cat(5, move_reverse, 2)

    switch = event_type == 8
    set_cat(6, switch, 1)
    set_cat(7, switch, 3)
    change = event_type == 9
    set_cat(8, change, 1)
    set_cat(9, change, 3)
    move_attached = event_type == 14
    set_cat(8, move_attached, 3)
    set_cat(9, move_attached, 5)
    targeted = (event_type >= 11) & (event_type <= 13)
    set_cat(10, targeted, 3)
    attack = event_type == 15
    set_cat(11, attack, 3)
    hp = event_type == 16
    set_cat(12, hp, 4)
    set_cat(13, status_card, 1)
    coin = event_type == 22
    set_cat(14, coin, 1)
    result = event_type == 23
    set_cat(15, result, 0)
    set_cat(16, result, 1)

    numeric[hp, 0] = events[hp, 5].to(torch.float32)
    numeric_missing[hp, 0] = False

    main_identity = torch.isin(
        event_type,
        torch.tensor((4, 6, 10, 11, 12, 13, 14, 15, 16), device=events.device),
    )
    set_identity(0, main_identity, 2)
    set_identity(0, status_card, 3)
    set_identity(1, switch, 2)
    set_identity(2, switch, 4)
    set_identity(3, change, 2)
    set_identity(4, change, 4)
    set_identity(3, move_attached, 4)
    set_identity(4, move_attached, 6)
    set_identity(5, targeted, 4)

    identities, entity_indices = _map_event_identities(
        identity_raw, identity_missing, owner, entity_raw_refs, entity_offsets
    )
    return (
        categorical,
        categorical_missing,
        numeric,
        numeric_missing,
        identities,
        identity_missing,
        entity_indices,
        event_offsets,
    )


def build_torch_policy_batch(
    projection: Any,
    events: Any,
    status: Any,
    *,
    env_indices: Tensor | None = None,
) -> tuple[TorchDecisionBatch, GpuPolicyDecisionMetaV1]:
    """Map qualified GPU-CABT public tensors directly into the existing G2 policy schema."""
    globals_all = _require_integer_tensor(projection.globals, "policy globals", 2)
    players_all = _require_integer_tensor(projection.players, "policy players", 3)
    entities_all = _require_integer_tensor(projection.entities, "policy entities", 3)
    entity_counts_all = _require_integer_tensor(projection.entity_counts, "entity counts", 1)
    options_all = _require_integer_tensor(projection.options, "policy options", 3)
    option_counts_all = _require_integer_tensor(projection.option_counts, "option counts", 1)
    projection_status_all = _require_integer_tensor(projection.status, "projection status", 1)
    event_rows_all = _require_integer_tensor(events.events, "public events", 3)
    event_counts_all = _require_integer_tensor(events.counts, "event counts", 1)
    event_status_all = _require_integer_tensor(events.status, "event status", 1)
    actors_all = _require_integer_tensor(status.select_players, "select players", 1)
    game_results_all = _require_integer_tensor(status.game_results, "game results", 1)

    env_count = globals_all.shape[0]
    if env_indices is None:
        env_indices = torch.arange(env_count, dtype=torch.long, device=globals_all.device)
    if not isinstance(env_indices, Tensor) or env_indices.ndim != 1 or env_indices.dtype != torch.long:
        raise GpuPolicyBridgeError("env_indices must be a one-dimensional long tensor")
    if env_indices.device != globals_all.device:
        env_indices = env_indices.to(globals_all.device)
    if env_indices.numel() == 0:
        raise GpuPolicyBridgeError("policy bridge requires at least one active environment")

    g = globals_all.index_select(0, env_indices).to(torch.long)
    players = players_all.index_select(0, env_indices).to(torch.long)
    entity_rows = entities_all.index_select(0, env_indices).to(torch.long)
    entity_counts = entity_counts_all.index_select(0, env_indices).to(torch.long)
    option_rows = options_all.index_select(0, env_indices).to(torch.long)
    option_counts = option_counts_all.index_select(0, env_indices).to(torch.long)
    projection_status = projection_status_all.to(torch.long).index_select(0, env_indices)
    event_rows = event_rows_all.index_select(0, env_indices).to(torch.long)
    event_counts = event_counts_all.index_select(0, env_indices).to(torch.long)
    event_status = event_status_all.to(torch.long).index_select(0, env_indices)
    actors = actors_all.index_select(0, env_indices).to(torch.long)
    game_results = game_results_all.index_select(0, env_indices).to(torch.long)

    if torch.any(projection_status != 0) or torch.any(event_status != 0):
        raise GpuPolicyBridgeError("GPU public projection status is nonzero")
    if torch.any(game_results != 0):
        raise GpuPolicyBridgeError("policy bridge received a terminal environment")
    if torch.any((actors < 0) | (actors > 1)):
        raise GpuPolicyBridgeError("policy bridge received an invalid acting player")
    if g.shape[1] < 23 or players.shape[1:] != (2, 12) or entity_rows.shape[2] < 19 or option_rows.shape[2] < 20:
        raise GpuPolicyBridgeError("GPU policy ABI widths differ from the qualified contract")

    batch_size = int(env_indices.numel())

    player_categorical = torch.empty((batch_size, 2, 2), dtype=torch.long, device=g.device)
    player_categorical[:, :, 0] = torch.tensor((0, 1), dtype=torch.long, device=g.device)
    player_categorical[:, 0, 1] = 1
    player_categorical[:, 1, 1] = 0
    player_categorical_missing = torch.zeros_like(player_categorical, dtype=torch.bool)
    player_numeric = torch.stack(
        (
            players[:, :, 5],
            players[:, :, 0],
            players[:, :, 1],
            players[:, :, 2],
            players[:, :, 3],
            players[:, :, 6],
        ),
        dim=2,
    ).to(torch.float32)
    player_numeric_missing = torch.zeros_like(player_numeric, dtype=torch.bool)

    raw_entities, entity_offsets = _flatten_padded(entity_rows, entity_counts)
    entity_owner = _flat_owner(entity_counts)
    entity_visible = raw_entities[:, 4] != 0
    entity_raw_refs = raw_entities[:, 18].to(torch.long)
    if torch.any(entity_visible & (entity_raw_refs <= 0)):
        raise GpuPolicyBridgeError("visible GPU entity is missing bridge-only raw ref")
    if torch.any((~entity_visible) & (entity_raw_refs != 0)):
        raise GpuPolicyBridgeError("hidden GPU entity exposes a bridge-only raw ref")
    entity_area = raw_entities[:, 2].to(torch.long)
    entity_role = torch.where(
        entity_area == 4,
        raw_entities[:, 3].to(torch.long),
        torch.where(entity_area == 5, raw_entities[:, 3].to(torch.long) - 1, torch.zeros_like(entity_area)),
    )
    entity_categorical = torch.stack(
        (raw_entities[:, 0], raw_entities[:, 1], raw_entities[:, 2], entity_role), dim=1
    ).to(torch.long)
    entity_categorical_missing = torch.zeros_like(entity_categorical, dtype=torch.bool)
    entity_categorical_missing[:, 0] = ~entity_visible
    bad_status = raw_entities[:, 14].to(torch.long)
    entity_numeric = torch.stack(
        (
            raw_entities[:, 5],
            raw_entities[:, 6],
            raw_entities[:, 7],
            raw_entities[:, 8],
            raw_entities[:, 9],
            raw_entities[:, 10],
            raw_entities[:, 11],
            raw_entities[:, 4],
            raw_entities[:, 12],
            raw_entities[:, 13],
            (bad_status == 1).to(torch.long),
            (bad_status == 2).to(torch.long),
            (bad_status == 3).to(torch.long),
        ),
        dim=1,
    ).to(torch.float32)
    entity_numeric_missing = torch.zeros_like(entity_numeric, dtype=torch.bool)
    pokemon_public = entity_visible & ((entity_area == 4) | (entity_area == 5))
    entity_numeric_missing[:, :4] = ~pokemon_public.unsqueeze(1)
    entity_position_keys = _position_key(
        entity_owner,
        raw_entities[:, 1].to(torch.long),
        raw_entities[:, 2].to(torch.long),
        raw_entities[:, 3].to(torch.long),
    )
    parent_role = raw_entities[:, 15].to(torch.long)
    attached_entity = torch.isin(
        entity_area, torch.tensor((8, 9, 10), device=g.device)
    ) & (parent_role > 0)
    parent_area = torch.where(
        parent_role == 1,
        torch.full_like(parent_role, 4),
        torch.full_like(parent_role, 5),
    )
    parent_query = _position_key(
        entity_owner,
        raw_entities[:, 1].to(torch.long),
        parent_area,
        parent_role,
    )
    entity_parent_indices = _lookup_sorted(
        entity_position_keys, parent_query, attached_entity
    )

    energy_index_mask = raw_entities[:, 16].to(torch.long)
    energy_bits = torch.arange(12, dtype=torch.long, device=g.device)
    energy_present = (
        energy_index_mask.unsqueeze(1) & (1 << energy_bits).unsqueeze(0)
    ) != 0
    energy_coordinates = torch.nonzero(energy_present, as_tuple=False)
    entity_energy_values = energy_coordinates[:, 1].to(torch.long)
    entity_energy_offsets = _offsets(energy_present.sum(dim=1).to(torch.long))

    raw_options, option_offsets = _flatten_padded(option_rows, option_counts)
    option_owner = _flat_owner(option_counts)
    option_type = raw_options[:, 0].to(torch.long)
    selection_type = raw_options[:, 1].to(torch.long) - 1
    selection_context = raw_options[:, 2].to(torch.long) - 1
    if torch.any((option_type < 0) | (option_type > 16)):
        raise GpuPolicyBridgeError("GPU option type is outside the native contract")

    source_area = raw_options[:, 10].to(torch.long).clone()
    source_role = raw_options[:, 11].to(torch.long).clone()
    source_relative = raw_options[:, 12].to(torch.long).clone()
    target_area = raw_options[:, 13].to(torch.long).clone()
    target_role = raw_options[:, 14].to(torch.long).clone()
    target_relative = raw_options[:, 15].to(torch.long).clone()

    retreat_or_attack = (option_type == 12) | (option_type == 13)
    source_area[retreat_or_attack] = 4
    source_role[retreat_or_attack] = 1
    source_relative[retreat_or_attack] = 0

    source_present = torch.isin(
        option_type,
        torch.tensor((3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 15), device=g.device),
    )
    default_skill = (option_type == 15) & (raw_options[:, 3] == 0)
    source_present &= ~default_skill
    target_present = torch.isin(
        option_type, torch.tensor((4, 5, 6, 8, 9), device=g.device)
    )

    source_kind = torch.zeros_like(option_type)
    source_kind[source_present] = _kind_from_area(source_area[source_present])
    source_kind[default_skill] = 3
    target_kind = torch.zeros_like(option_type)
    target_kind[target_present] = _kind_from_area(target_area[target_present])

    attached = torch.isin(option_type, torch.tensor((4, 5, 6), device=g.device))
    source_entity_required = source_present & (source_kind == 1) & ~attached
    target_entity_required = target_present & (target_kind == 1)
    source_query = _position_key(option_owner, source_relative, source_area, source_role)
    target_query = _position_key(option_owner, target_relative, target_area, target_role)
    option_source_indices = _lookup_sorted(
        entity_position_keys, source_query, source_entity_required
    )
    option_target_indices = _lookup_sorted(
        entity_position_keys, target_query, target_entity_required
    )

    if torch.any(attached):
        entity_attachment_keys = _attachment_key(
            entity_owner,
            raw_entities[:, 1].to(torch.long),
            raw_entities[:, 2].to(torch.long),
            raw_entities[:, 0].to(torch.long),
            raw_entities[:, 15].to(torch.long),
        )
        attached_query = _attachment_key(
            option_owner,
            source_relative,
            source_area,
            raw_options[:, 8].to(torch.long),
            target_role,
        )
        attached_indices = _lookup_sorted(
            entity_attachment_keys, attached_query, attached
        )
        option_source_indices = torch.where(attached, attached_indices, option_source_indices)

    option_categorical = torch.zeros((raw_options.shape[0], 12), dtype=torch.long, device=g.device)
    option_categorical_missing = torch.ones_like(option_categorical, dtype=torch.bool)
    option_categorical[:, 0] = selection_type
    option_categorical[:, 1] = selection_context
    option_categorical[:, 2] = option_type
    option_categorical[:, 3] = source_kind
    option_categorical[:, 4] = target_kind
    option_categorical[:, 5] = option_type + 1
    option_categorical_missing[:, :6] = False

    has_area = torch.isin(option_type, torch.tensor((3, 4, 5, 6, 8, 9, 10, 11), device=g.device))
    option_categorical[has_area, 6] = raw_options[has_area, 3]
    option_categorical_missing[has_area, 6] = False
    has_in_play = (option_type == 8) | (option_type == 9)
    option_categorical[has_in_play, 7] = raw_options[has_in_play, 5]
    option_categorical_missing[has_in_play, 7] = False
    has_player = torch.isin(option_type, torch.tensor((3, 4, 5, 6), device=g.device))
    absolute_player = raw_options[:, 5].to(torch.long)
    option_actor = actors.index_select(0, option_owner)
    relative_player = torch.where(absolute_player == option_actor, 0, 1)
    option_categorical[has_player, 8] = relative_player[has_player]
    option_categorical_missing[has_player, 8] = False
    attack_option = option_type == 13
    option_categorical[attack_option, 9] = raw_options[attack_option, 3]
    option_categorical_missing[attack_option, 9] = False
    skill = option_type == 15
    option_categorical[skill, 10] = raw_options[skill, 3]
    option_categorical_missing[skill, 10] = False
    special = option_type == 16
    option_categorical[special, 11] = raw_options[special, 3]
    option_categorical_missing[special, 11] = False

    option_numeric = torch.zeros((raw_options.shape[0], 2), dtype=torch.float32, device=g.device)
    option_numeric_missing = torch.ones_like(option_numeric, dtype=torch.bool)
    number = option_type == 0
    option_numeric[number, 0] = raw_options[number, 3].to(torch.float32)
    option_numeric_missing[number, 0] = False
    energy = option_type == 6
    option_numeric[energy, 1] = raw_options[energy, 7].to(torch.float32)
    option_numeric_missing[energy, 1] = False
    option_available = raw_options[:, 19] != 0

    (
        event_categorical,
        event_categorical_missing,
        event_numeric,
        event_numeric_missing,
        event_identity,
        event_identity_missing,
        event_entity_indices,
        event_offsets,
    ) = _map_events(
        event_rows, event_counts, actors, entity_raw_refs, entity_offsets
    )

    first_player = g[:, 2]
    native_selection_type = g[:, 6] - 1
    native_selection_context = g[:, 7] - 1
    global_categorical = torch.zeros((batch_size, 11), dtype=torch.long, device=g.device)
    global_categorical_missing = torch.zeros_like(global_categorical, dtype=torch.bool)
    global_categorical[:, 0] = first_player
    global_categorical_missing[:, 0] = first_player < 0
    global_categorical[:, 1] = 0
    global_categorical_missing[:, 1] = True
    global_categorical[:, 2] = native_selection_type
    global_categorical[:, 3] = native_selection_context
    global_categorical[:, 4] = ((native_selection_type == 5) & (native_selection_context == 34)).to(torch.long)
    global_categorical[:, 5] = g[:, 16]
    global_categorical_missing[:, 5] = g[:, 16] <= 0
    global_categorical[:, 6] = g[:, 17]
    global_categorical_missing[:, 6] = g[:, 17] <= 0
    global_categorical[:, 7:11] = g[:, 12:16]

    global_numeric = torch.stack(
        (
            g[:, 0],
            g[:, 1],
            g[:, 8],
            g[:, 9],
            g[:, 10],
            g[:, 11],
            players[:, 0, 0],
            players[:, 0, 1],
            players[:, 0, 2],
            players[:, 1, 0],
            players[:, 1, 1],
            players[:, 1, 2],
        ),
        dim=1,
    ).to(torch.float32)
    global_numeric_missing = torch.zeros_like(global_numeric, dtype=torch.bool)

    batch = TorchDecisionBatch(
        batch_size=batch_size,
        player_categorical=player_categorical,
        player_categorical_missing=player_categorical_missing,
        player_numeric=player_numeric,
        player_numeric_missing=player_numeric_missing,
        entity_categorical=entity_categorical,
        entity_categorical_missing=entity_categorical_missing,
        entity_numeric=entity_numeric,
        entity_numeric_missing=entity_numeric_missing,
        entity_parent_indices=entity_parent_indices,
        entity_energy_values=entity_energy_values,
        entity_energy_offsets=entity_energy_offsets,
        entity_offsets=entity_offsets,
        event_categorical=event_categorical,
        event_categorical_missing=event_categorical_missing,
        event_numeric=event_numeric,
        event_numeric_missing=event_numeric_missing,
        event_identity=event_identity,
        event_identity_missing=event_identity_missing,
        event_entity_indices=event_entity_indices,
        event_offsets=event_offsets,
        option_categorical=option_categorical,
        option_categorical_missing=option_categorical_missing,
        option_numeric=option_numeric,
        option_numeric_missing=option_numeric_missing,
        option_source_entity_indices=option_source_indices,
        option_target_entity_indices=option_target_indices,
        option_available=option_available,
        option_offsets=option_offsets,
        global_categorical=global_categorical,
        global_categorical_missing=global_categorical_missing,
        global_numeric=global_numeric,
        global_numeric_missing=global_numeric_missing,
    )
    meta = GpuPolicyDecisionMetaV1(
        env_indices=env_indices,
        actors=actors,
        minimum_counts=g[:, 8].to(torch.long),
        maximum_counts=g[:, 9].to(torch.long),
        option_counts=option_counts,
    )
    if torch.any(meta.minimum_counts < 0) or torch.any(meta.maximum_counts < meta.minimum_counts):
        raise GpuPolicyBridgeError("GPU selection bounds are invalid")
    if torch.any(meta.maximum_counts > meta.option_counts):
        raise GpuPolicyBridgeError("GPU selection maximum exceeds legal options")
    return batch, meta
