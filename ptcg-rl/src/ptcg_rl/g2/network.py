from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, Iterable, Sequence

import torch
from torch import Tensor, nn

from ptcg_rl.g1.models import ContractViolation, stable_hash

from .card_table import CardTableV1
from .models import ProjectedDecisionV1

CARD_STATIC_FEATURE_WIDTH = 7 + 12 + 13 + 13 + 4 + 16
ENTITY_NONCARD_FEATURE_WIDTH = 4 + 16 + 8 + 64
EVENT_FEATURE_WIDTH = (
    16
    + 4
    + 4
    + (6 * 16)
    + 8
    + 8
    + 16
    + (3 * 4)
    + 4
    + 8
    + (6 * 8)
    + (6 * 8)
    + 2
)
GLOBAL_NONCARD_FEATURE_WIDTH = 4 + 4 + 16 + 16 + 4 + 64
OPTION_NONENTITY_FEATURE_WIDTH = 16 + 16 + (7 * 8) + 4 + 16 + 16


@dataclass(frozen=True)
class PolicyConfigV1:
    schema_version: int = 1
    model_width: int = 128
    entity_heads: int = 4
    entity_layers: int = 2
    entity_ff_width: int = 256
    card_id_dim: int = 64
    attack_id_dim: int = 32
    event_width: int = 64
    event_hidden: int = 64
    public_hidden: int = 160
    selection_hidden: int = 96
    option_width: int = 128
    max_trainable_parameters: int = 2_000_000
    target_trainable_parameters: int = 1_250_000

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported policy config schema version")
        if self.model_width % self.entity_heads:
            raise ValueError("model width must be divisible by entity heads")
        for name, value in asdict(self).items():
            if name == "schema_version":
                continue
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")

    @property
    def config_sha256(self) -> str:
        return stable_hash(asdict(self))


@dataclass(frozen=True)
class TorchDecisionBatch:
    batch_size: int
    player_categorical: Tensor
    player_categorical_missing: Tensor
    player_numeric: Tensor
    player_numeric_missing: Tensor
    entity_categorical: Tensor
    entity_categorical_missing: Tensor
    entity_numeric: Tensor
    entity_numeric_missing: Tensor
    entity_parent_indices: Tensor
    entity_energy_values: Tensor
    entity_energy_offsets: Tensor
    entity_offsets: Tensor
    event_categorical: Tensor
    event_categorical_missing: Tensor
    event_numeric: Tensor
    event_numeric_missing: Tensor
    event_identity: Tensor
    event_identity_missing: Tensor
    event_entity_indices: Tensor
    event_offsets: Tensor
    option_categorical: Tensor
    option_categorical_missing: Tensor
    option_numeric: Tensor
    option_numeric_missing: Tensor
    option_source_entity_indices: Tensor
    option_target_entity_indices: Tensor
    option_available: Tensor
    option_offsets: Tensor
    global_categorical: Tensor
    global_categorical_missing: Tensor
    global_numeric: Tensor
    global_numeric_missing: Tensor

    def to(self, device: torch.device | str) -> TorchDecisionBatch:
        values: dict[str, Any] = {"batch_size": self.batch_size}
        for name, value in self.__dict__.items():
            if name == "batch_size":
                continue
            values[name] = value.to(device)
        return TorchDecisionBatch(**values)


@dataclass(frozen=True)
class PolicyOutputV1:
    option_logits: Tensor
    values: Tensor
    hidden: Tensor
    entity_embeddings: Tensor
    option_embeddings: Tensor
    entity_offsets: Tensor
    option_offsets: Tensor


def _tensor_rows(values: Sequence[Sequence[Any]], dtype: torch.dtype) -> Tensor:
    if not values:
        return torch.empty((0, 0), dtype=dtype)
    return torch.tensor(values, dtype=dtype)


def _offsets(lengths: Iterable[int]) -> tuple[int, ...]:
    result = [0]
    for length in lengths:
        result.append(result[-1] + int(length))
    return tuple(result)


def _adjust_indices(rows: Sequence[Sequence[int]], offset: int) -> list[list[int]]:
    return [[value + offset if value >= 0 else -1 for value in row] for row in rows]


def collate_projected(
    decisions: Sequence[ProjectedDecisionV1],
    device: torch.device | str | None = None,
) -> TorchDecisionBatch:
    if not decisions:
        raise ContractViolation("cannot collate an empty decision batch")
    models = [decision.model for decision in decisions]
    reference = models[0]
    for model in models[1:]:
        for name in (
            "player_categorical_names",
            "player_numeric_names",
            "entity_categorical_names",
            "entity_numeric_names",
            "event_categorical_names",
            "event_numeric_names",
            "event_identity_names",
            "option_categorical_names",
            "option_numeric_names",
            "global_categorical_names",
            "global_numeric_names",
        ):
            if getattr(model, name) != getattr(reference, name):
                raise ContractViolation(f"model feature names differ for {name}")
        if len(model.player_categorical_values) != 2:
            raise ContractViolation("every decision must contain exactly two player rows")

    entity_lengths = [len(model.entity_categorical_values) for model in models]
    event_lengths = [len(model.event_categorical_values) for model in models]
    option_lengths = [len(model.option_categorical_values) for model in models]
    entity_offsets = _offsets(entity_lengths)
    event_offsets = _offsets(event_lengths)
    option_offsets = _offsets(option_lengths)

    def flatten(name: str) -> list[Any]:
        result: list[Any] = []
        for model in models:
            result.extend(getattr(model, name))
        return result

    parent_indices: list[int] = []
    event_entity_indices: list[list[int]] = []
    option_source_indices: list[int] = []
    option_target_indices: list[int] = []
    energy_values: list[int] = []
    energy_offsets = [0]
    for batch_index, model in enumerate(models):
        entity_offset = entity_offsets[batch_index]
        parent_indices.extend(
            value + entity_offset if value >= 0 else -1
            for value in model.entity_parent_indices
        )
        event_entity_indices.extend(
            _adjust_indices(model.event_entity_indices, entity_offset)
        )
        option_source_indices.extend(
            value + entity_offset if value >= 0 else -1
            for value in model.option_source_entity_indices
        )
        option_target_indices.extend(
            value + entity_offset if value >= 0 else -1
            for value in model.option_target_entity_indices
        )
        for entity_index in range(len(model.entity_categorical_values)):
            start = model.entity_energy_offsets[entity_index]
            end = model.entity_energy_offsets[entity_index + 1]
            energy_values.extend(model.entity_energy_values[start:end])
            energy_offsets.append(len(energy_values))

    batch = TorchDecisionBatch(
        batch_size=len(models),
        player_categorical=torch.tensor(
            [model.player_categorical_values for model in models], dtype=torch.long
        ),
        player_categorical_missing=torch.tensor(
            [model.player_categorical_missing for model in models], dtype=torch.bool
        ),
        player_numeric=torch.tensor(
            [model.player_numeric_values for model in models], dtype=torch.float32
        ),
        player_numeric_missing=torch.tensor(
            [model.player_numeric_missing for model in models], dtype=torch.bool
        ),
        entity_categorical=_tensor_rows(flatten("entity_categorical_values"), torch.long),
        entity_categorical_missing=_tensor_rows(
            flatten("entity_categorical_missing"), torch.bool
        ),
        entity_numeric=_tensor_rows(flatten("entity_numeric_values"), torch.float32),
        entity_numeric_missing=_tensor_rows(
            flatten("entity_numeric_missing"), torch.bool
        ),
        entity_parent_indices=torch.tensor(parent_indices, dtype=torch.long),
        entity_energy_values=torch.tensor(energy_values, dtype=torch.long),
        entity_energy_offsets=torch.tensor(energy_offsets, dtype=torch.long),
        entity_offsets=torch.tensor(entity_offsets, dtype=torch.long),
        event_categorical=_tensor_rows(flatten("event_categorical_values"), torch.long),
        event_categorical_missing=_tensor_rows(
            flatten("event_categorical_missing"), torch.bool
        ),
        event_numeric=_tensor_rows(flatten("event_numeric_values"), torch.float32),
        event_numeric_missing=_tensor_rows(
            flatten("event_numeric_missing"), torch.bool
        ),
        event_identity=_tensor_rows(flatten("event_identity_values"), torch.long),
        event_identity_missing=_tensor_rows(
            flatten("event_identity_missing"), torch.bool
        ),
        event_entity_indices=_tensor_rows(event_entity_indices, torch.long),
        event_offsets=torch.tensor(event_offsets, dtype=torch.long),
        option_categorical=_tensor_rows(flatten("option_categorical_values"), torch.long),
        option_categorical_missing=_tensor_rows(
            flatten("option_categorical_missing"), torch.bool
        ),
        option_numeric=_tensor_rows(flatten("option_numeric_values"), torch.float32),
        option_numeric_missing=_tensor_rows(
            flatten("option_numeric_missing"), torch.bool
        ),
        option_source_entity_indices=torch.tensor(option_source_indices, dtype=torch.long),
        option_target_entity_indices=torch.tensor(option_target_indices, dtype=torch.long),
        option_available=torch.tensor(flatten("option_available_mask"), dtype=torch.bool),
        option_offsets=torch.tensor(option_offsets, dtype=torch.long),
        global_categorical=torch.tensor(
            [model.global_categorical_values for model in models], dtype=torch.long
        ),
        global_categorical_missing=torch.tensor(
            [model.global_categorical_missing for model in models], dtype=torch.bool
        ),
        global_numeric=torch.tensor(
            [model.global_numeric_values for model in models], dtype=torch.float32
        ),
        global_numeric_missing=torch.tensor(
            [model.global_numeric_missing for model in models], dtype=torch.bool
        ),
    )
    return batch if device is None else batch.to(device)


class SafeEmbedding(nn.Module):
    def __init__(self, max_value: int, dimension: int) -> None:
        super().__init__()
        self.max_value = max_value
        self.unknown_index = max_value + 2
        self.embedding = nn.Embedding(max_value + 3, dimension, padding_idx=0)

    def forward(self, values: Tensor, missing: Tensor) -> Tensor:
        valid = (values >= 0) & (values <= self.max_value) & ~missing
        indices = torch.where(valid, values + 1, self.unknown_index)
        indices = torch.where(missing, torch.zeros_like(indices), indices)
        return self.embedding(indices)


class StaticCatalogEncoder(nn.Module):
    def __init__(self, table: CardTableV1, config: PolicyConfigV1) -> None:
        super().__init__()
        self.unknown_card_id = table.unknown_card_id
        self.unknown_attack_id = table.unknown_attack_id
        self.card_id_embedding = nn.Embedding(
            table.unknown_card_id + 1, config.card_id_dim, padding_idx=0
        )
        self.attack_id_embedding = nn.Embedding(
            table.unknown_attack_id + 1, config.attack_id_dim, padding_idx=0
        )
        card_static = torch.zeros(
            (table.unknown_card_id + 1, CARD_STATIC_FEATURE_WIDTH), dtype=torch.float32
        )
        max_attacks = max((len(card.attack_ids) for card in table.cards), default=0)
        card_attacks = torch.zeros(
            (table.unknown_card_id + 1, max_attacks), dtype=torch.long
        )
        card_attack_mask = torch.zeros(
            (table.unknown_card_id + 1, max_attacks), dtype=torch.bool
        )
        for card in table.cards:
            features: list[float] = []
            features.extend(float(card.card_type == value) for value in range(7))
            features.extend(float(card.energy_type == value) for value in range(12))
            features.extend(float(card.weakness_type == value) for value in range(-1, 12))
            features.extend(float(card.resistance_type == value) for value in range(-1, 12))
            features.extend(float(card.stage_code == value) for value in range(4))
            features.extend(
                (
                    card.hp / 350.0,
                    card.retreat_cost / 4.0,
                    float(card.basic),
                    float(card.stage1),
                    float(card.stage2),
                    float(card.ex),
                    float(card.mega_ex),
                    float(card.tera),
                    float(card.ace_spec),
                    float(card.ancient),
                    float(card.future),
                    float(card.fossil),
                    float(card.technical_machine),
                    float(card.trainers_pokemon),
                    card.skill_count / 2.0,
                    len(card.attack_ids) / 2.0,
                )
            )
            if len(features) != card_static.shape[1]:
                raise ValueError("card static feature width changed unexpectedly")
            card_static[card.card_id] = torch.tensor(features)
            for index, attack_id in enumerate(card.attack_ids):
                card_attacks[card.card_id, index] = attack_id
                card_attack_mask[card.card_id, index] = True

        attack_static = torch.zeros(
            (table.unknown_attack_id + 1, 13), dtype=torch.float32
        )
        for attack in table.attacks:
            attack_static[attack.attack_id] = torch.tensor(
                (attack.damage / 350.0, *(value / 5.0 for value in attack.energy_counts))
            )
        self.register_buffer("card_static", card_static, persistent=True)
        self.register_buffer("card_attacks", card_attacks, persistent=True)
        self.register_buffer("card_attack_mask", card_attack_mask, persistent=True)
        self.register_buffer("attack_static", attack_static, persistent=True)
        self.card_static_mlp = nn.Sequential(
            nn.Linear(card_static.shape[1], 64), nn.GELU(), nn.LayerNorm(64)
        )
        self.attack_static_mlp = nn.Sequential(
            nn.Linear(attack_static.shape[1], 16), nn.GELU(), nn.LayerNorm(16)
        )
        self.attack_pool_projection = nn.Linear(config.attack_id_dim + 16, 32)
        self.card_projection = nn.Sequential(
            nn.Linear(config.card_id_dim + 64 + 32, config.model_width),
            nn.GELU(),
            nn.LayerNorm(config.model_width),
        )

    def normalize_card_ids(self, values: Tensor, missing: Tensor | None = None) -> Tensor:
        valid = (values >= 1) & (values < self.unknown_card_id)
        indices = torch.where(valid, values, self.unknown_card_id)
        if missing is not None:
            indices = torch.where(missing, torch.zeros_like(indices), indices)
        return indices

    def normalize_attack_ids(self, values: Tensor, missing: Tensor | None = None) -> Tensor:
        valid = (values >= 1) & (values < self.unknown_attack_id)
        indices = torch.where(valid, values, self.unknown_attack_id)
        if missing is not None:
            indices = torch.where(missing, torch.zeros_like(indices), indices)
        return indices

    def encode_attack(self, attack_ids: Tensor, missing: Tensor | None = None) -> Tensor:
        indices = self.normalize_attack_ids(attack_ids, missing)
        return torch.cat(
            (
                self.attack_id_embedding(indices),
                self.attack_static_mlp(self.attack_static[indices]),
            ),
            dim=-1,
        )

    def encode_card(self, card_ids: Tensor, missing: Tensor | None = None) -> Tensor:
        indices = self.normalize_card_ids(card_ids, missing)
        attack_ids = self.card_attacks[indices]
        attack_mask = self.card_attack_mask[indices]
        if attack_ids.shape[-1]:
            attack_values = self.encode_attack(attack_ids)
            weights = attack_mask.unsqueeze(-1).to(attack_values.dtype)
            pooled = (attack_values * weights).sum(dim=-2) / weights.sum(dim=-2).clamp_min(1.0)
        else:
            pooled = torch.zeros(
                (*indices.shape, self.attack_id_embedding.embedding_dim + 16),
                dtype=self.card_static.dtype,
                device=indices.device,
            )
        return self.card_projection(
            torch.cat(
                (
                    self.card_id_embedding(indices),
                    self.card_static_mlp(self.card_static[indices]),
                    self.attack_pool_projection(pooled),
                ),
                dim=-1,
            )
        )


class PTCGPolicyV1(nn.Module):
    def __init__(self, table: CardTableV1, config: PolicyConfigV1 | None = None) -> None:
        super().__init__()
        self.config = config or PolicyConfigV1()
        self.card_table_sha256 = table.table_sha256
        self.catalog = StaticCatalogEncoder(table, self.config)

        self.player_relative = SafeEmbedding(2, 4)
        self.binary = SafeEmbedding(1, 4)
        self.zone = SafeEmbedding(31, 16)
        self.role_position = SafeEmbedding(16, 8)
        self.selection_type = SafeEmbedding(31, 16)
        self.selection_context = SafeEmbedding(127, 16)
        self.option_type = SafeEmbedding(31, 8)
        self.kind = SafeEmbedding(31, 8)
        self.choice_role = SafeEmbedding(31, 8)
        self.special_condition = SafeEmbedding(15, 8)
        self.event_type = SafeEmbedding(127, 16)
        self.result = SafeEmbedding(7, 4)
        self.reason = SafeEmbedding(255, 8)

        self.player_numeric = nn.Sequential(
            nn.Linear(12, 32), nn.GELU(), nn.LayerNorm(32)
        )
        self.player_projection = nn.Sequential(
            nn.Linear(40, 64), nn.GELU(), nn.LayerNorm(64)
        )
        self.players_projection = nn.Sequential(
            nn.Linear(128, 64), nn.GELU(), nn.LayerNorm(64)
        )
        self.entity_numeric = nn.Sequential(
            nn.Linear(28, 64), nn.GELU(), nn.LayerNorm(64)
        )
        self.entity_projection = nn.Sequential(
            nn.Linear(
                self.config.model_width + ENTITY_NONCARD_FEATURE_WIDTH,
                self.config.model_width,
            ),
            nn.GELU(),
            nn.LayerNorm(self.config.model_width),
        )
        layer = nn.TransformerEncoderLayer(
            d_model=self.config.model_width,
            nhead=self.config.entity_heads,
            dim_feedforward=self.config.entity_ff_width,
            dropout=0.0,
            activation="gelu",
            batch_first=True,
            norm_first=True,
        )
        self.entity_transformer = nn.TransformerEncoder(
            layer, num_layers=self.config.entity_layers, enable_nested_tensor=False
        )
        self.entity_cls = nn.Parameter(torch.zeros(1, 1, self.config.model_width))

        self.event_card_roles = nn.ModuleList(
            nn.Linear(self.config.model_width, 16, bias=False) for _ in range(6)
        )
        self.event_attack = nn.Linear(self.config.attack_id_dim + 16, 16)
        self.event_entity_reference = nn.Linear(self.config.model_width, 8, bias=False)
        self.event_projection = nn.Sequential(
            nn.Linear(EVENT_FEATURE_WIDTH, self.config.event_width),
            nn.GELU(),
            nn.LayerNorm(self.config.event_width),
        )
        self.event_gru = nn.GRU(
            self.config.event_width, self.config.event_hidden, batch_first=True
        )
        self.empty_event = nn.Parameter(torch.zeros(self.config.event_hidden))

        self.global_numeric = nn.Sequential(
            nn.Linear(24, 64), nn.GELU(), nn.LayerNorm(64)
        )
        self.global_projection = nn.Sequential(
            nn.Linear(
                GLOBAL_NONCARD_FEATURE_WIDTH + (2 * self.config.model_width), 64
            ),
            nn.GELU(),
            nn.LayerNorm(64),
        )
        self.state_projection = nn.Sequential(
            nn.Linear(self.config.model_width + 64 + self.config.event_hidden + 64, 128),
            nn.GELU(),
            nn.LayerNorm(128),
        )
        self.public_gru = nn.GRUCell(128, self.config.public_hidden)

        self.option_numeric = nn.Sequential(
            nn.Linear(4, 16), nn.GELU(), nn.LayerNorm(16)
        )
        self.option_attack = nn.Linear(self.config.attack_id_dim + 16, 16)
        self.option_projection = nn.Sequential(
            nn.Linear(
                OPTION_NONENTITY_FEATURE_WIDTH + (3 * self.config.model_width),
                self.config.option_width,
            ),
            nn.GELU(),
            nn.LayerNorm(self.config.option_width),
        )
        self.policy_state = nn.Linear(self.config.public_hidden, self.config.option_width)
        self.policy_interaction = nn.Sequential(
            nn.Linear(self.config.option_width * 2, 128), nn.GELU(), nn.Linear(128, 1)
        )
        self.value_head = nn.Sequential(
            nn.Linear(self.config.public_hidden, 128), nn.GELU(), nn.Linear(128, 1)
        )

        self.selection_initial = nn.Linear(
            self.config.public_hidden, self.config.selection_hidden
        )
        self.selection_option = nn.Linear(
            self.config.option_width, self.config.selection_hidden
        )
        self.selection_gru = nn.GRUCell(
            self.config.option_width, self.config.selection_hidden
        )
        self.stop_embedding = nn.Parameter(torch.empty(self.config.selection_hidden))
        nn.init.normal_(self.stop_embedding, std=0.02)
        nn.init.normal_(self.entity_cls, std=0.02)
        self._initialize()
        parameters = self.trainable_parameter_count
        if parameters >= self.config.max_trainable_parameters:
            raise ValueError(
                f"policy has {parameters} trainable parameters; hard ceiling is "
                f"{self.config.max_trainable_parameters - 1}"
            )

    @property
    def trainable_parameter_count(self) -> int:
        return sum(parameter.numel() for parameter in self.parameters() if parameter.requires_grad)

    @property
    def architecture_sha256(self) -> str:
        return stable_hash(
            {
                "config": asdict(self.config),
                "card_table_sha256": self.card_table_sha256,
                "parameter_shapes": {
                    name: tuple(parameter.shape)
                    for name, parameter in self.named_parameters()
                },
            }
        )

    def _initialize(self) -> None:
        for module in self.modules():
            if isinstance(module, nn.Linear):
                nn.init.orthogonal_(module.weight, gain=math.sqrt(2))
                if module.bias is not None:
                    nn.init.zeros_(module.bias)
            elif isinstance(module, nn.MultiheadAttention):
                nn.init.xavier_uniform_(module.in_proj_weight)
                if module.in_proj_bias is not None:
                    nn.init.zeros_(module.in_proj_bias)
        for recurrent in (self.event_gru, self.public_gru, self.selection_gru):
            for name, parameter in recurrent.named_parameters():
                if "weight_hh" in name:
                    nn.init.orthogonal_(parameter)
                elif "weight_ih" in name:
                    nn.init.xavier_uniform_(parameter)
                elif "bias" in name:
                    nn.init.zeros_(parameter)

    def initial_hidden(self, batch_size: int, device: torch.device | str) -> Tensor:
        return torch.zeros((batch_size, self.config.public_hidden), device=device)

    @staticmethod
    def _numeric(values: Tensor, missing: Tensor) -> Tensor:
        return torch.cat((values, missing.to(values.dtype)), dim=-1)

    @staticmethod
    def _gather_or_zero(values: Tensor, indices: Tensor) -> Tensor:
        if values.shape[0] == 0:
            return torch.zeros(
                (*indices.shape, values.shape[-1]), dtype=values.dtype, device=values.device
            )
        safe = indices.clamp(min=0)
        gathered = values[safe]
        return gathered * (indices >= 0).unsqueeze(-1).to(values.dtype)

    @staticmethod
    def _identity_fourier(values: Tensor, missing: Tensor) -> Tensor:
        frequencies = torch.tensor(
            (1.0, 0.1, 0.01, 0.001), dtype=torch.float32, device=values.device
        )
        angles = values.to(torch.float32).unsqueeze(-1) * frequencies
        result = torch.cat((angles.sin(), angles.cos()), dim=-1)
        return result * (~missing).unsqueeze(-1).to(result.dtype)

    def _encode_players(self, batch: TorchDecisionBatch) -> Tensor:
        categorical = torch.cat(
            (
                self.player_relative(
                    batch.player_categorical[..., 0],
                    batch.player_categorical_missing[..., 0],
                ),
                self.binary(
                    batch.player_categorical[..., 1],
                    batch.player_categorical_missing[..., 1],
                ),
            ),
            dim=-1,
        )
        numeric = self.player_numeric(
            self._numeric(batch.player_numeric, batch.player_numeric_missing)
        )
        encoded = self.player_projection(torch.cat((categorical, numeric), dim=-1))
        return self.players_projection(encoded.reshape(batch.batch_size, -1))

    def _encode_entities(self, batch: TorchDecisionBatch) -> tuple[Tensor, Tensor]:
        if batch.entity_categorical.shape[0]:
            card = self.catalog.encode_card(
                batch.entity_categorical[:, 0], batch.entity_categorical_missing[:, 0]
            )
            categorical = torch.cat(
                (
                    self.player_relative(
                        batch.entity_categorical[:, 1],
                        batch.entity_categorical_missing[:, 1],
                    ),
                    self.zone(
                        batch.entity_categorical[:, 2],
                        batch.entity_categorical_missing[:, 2],
                    ),
                    self.role_position(
                        batch.entity_categorical[:, 3],
                        batch.entity_categorical_missing[:, 3],
                    ),
                ),
                dim=-1,
            )
            numeric = self.entity_numeric(
                self._numeric(batch.entity_numeric, batch.entity_numeric_missing)
            )
            raw = self.entity_projection(torch.cat((card, categorical, numeric), dim=-1))
        else:
            raw = self.entity_cls.new_empty((0, self.config.model_width))

        lengths = (batch.entity_offsets[1:] - batch.entity_offsets[:-1]).tolist()
        max_length = max(lengths, default=0)
        padded = raw.new_zeros((batch.batch_size, max_length + 1, self.config.model_width))
        padding = torch.ones(
            (batch.batch_size, max_length + 1), dtype=torch.bool, device=raw.device
        )
        padded[:, 0] = self.entity_cls
        padding[:, 0] = False
        for index, length in enumerate(lengths):
            if length:
                start = int(batch.entity_offsets[index])
                padded[index, 1 : length + 1] = raw[start : start + length]
                padding[index, 1 : length + 1] = False
        transformed = self.entity_transformer(padded, src_key_padding_mask=padding)
        pooled = transformed[:, 0]
        flat: list[Tensor] = []
        for index, length in enumerate(lengths):
            if length:
                flat.append(transformed[index, 1 : length + 1])
        entities = torch.cat(flat, dim=0) if flat else raw
        return entities, pooled

    def _encode_events(self, batch: TorchDecisionBatch, entities: Tensor) -> Tensor:
        count = batch.event_categorical.shape[0]
        if count:
            card_fields = []
            for role, field in enumerate((3, 6, 7, 8, 9, 10)):
                encoded = self.catalog.encode_card(
                    batch.event_categorical[:, field],
                    batch.event_categorical_missing[:, field],
                )
                card_fields.append(self.event_card_roles[role](encoded))
            attack = self.catalog.encode_attack(
                batch.event_categorical[:, 11],
                batch.event_categorical_missing[:, 11],
            )
            identities = self._identity_fourier(
                batch.event_identity, batch.event_identity_missing
            ).flatten(start_dim=1)
            entity_refs = self.event_entity_reference(
                self._gather_or_zero(entities, batch.event_entity_indices)
            ).flatten(start_dim=1)
            event_features = torch.cat(
                (
                    self.event_type(
                        batch.event_categorical[:, 0],
                        batch.event_categorical_missing[:, 0],
                    ),
                    self.player_relative(
                        batch.event_categorical[:, 1],
                        batch.event_categorical_missing[:, 1],
                    ),
                    self.binary(
                        batch.event_categorical[:, 2],
                        batch.event_categorical_missing[:, 2],
                    ),
                    *card_fields,
                    self.zone(
                        batch.event_categorical[:, 4],
                        batch.event_categorical_missing[:, 4],
                    )[..., :8],
                    self.zone(
                        batch.event_categorical[:, 5],
                        batch.event_categorical_missing[:, 5],
                    )[..., :8],
                    self.event_attack(attack),
                    self.binary(
                        batch.event_categorical[:, 12],
                        batch.event_categorical_missing[:, 12],
                    ),
                    self.binary(
                        batch.event_categorical[:, 13],
                        batch.event_categorical_missing[:, 13],
                    ),
                    self.binary(
                        batch.event_categorical[:, 14],
                        batch.event_categorical_missing[:, 14],
                    ),
                    self.result(
                        batch.event_categorical[:, 15],
                        batch.event_categorical_missing[:, 15],
                    ),
                    self.reason(
                        batch.event_categorical[:, 16],
                        batch.event_categorical_missing[:, 16],
                    ),
                    identities,
                    entity_refs,
                    self._numeric(batch.event_numeric, batch.event_numeric_missing),
                ),
                dim=-1,
            )
            events = self.event_projection(event_features)
        else:
            events = self.empty_event.new_empty((0, self.config.event_width))

        summaries: list[Tensor] = []
        for index in range(batch.batch_size):
            start = int(batch.event_offsets[index])
            end = int(batch.event_offsets[index + 1])
            if end == start:
                summaries.append(self.empty_event)
            else:
                _, hidden = self.event_gru(events[start:end].unsqueeze(0))
                summaries.append(hidden[-1, 0])
        return torch.stack(summaries)

    def _encode_global(self, batch: TorchDecisionBatch) -> Tensor:
        context_card = self.catalog.encode_card(
            batch.global_categorical[:, 5], batch.global_categorical_missing[:, 5]
        )
        effect_card = self.catalog.encode_card(
            batch.global_categorical[:, 6], batch.global_categorical_missing[:, 6]
        )
        categorical = torch.cat(
            (
                self.player_relative(
                    batch.global_categorical[:, 0],
                    batch.global_categorical_missing[:, 0],
                ),
                self.result(
                    batch.global_categorical[:, 1],
                    batch.global_categorical_missing[:, 1],
                ),
                self.selection_type(
                    batch.global_categorical[:, 2],
                    batch.global_categorical_missing[:, 2],
                ),
                self.selection_context(
                    batch.global_categorical[:, 3],
                    batch.global_categorical_missing[:, 3],
                ),
                self.binary(
                    batch.global_categorical[:, 4],
                    batch.global_categorical_missing[:, 4],
                ),
                context_card,
                effect_card,
            ),
            dim=-1,
        )
        numeric = self.global_numeric(
            self._numeric(batch.global_numeric, batch.global_numeric_missing)
        )
        return self.global_projection(torch.cat((categorical, numeric), dim=-1))

    def _encode_options(self, batch: TorchDecisionBatch, entities: Tensor) -> Tensor:
        if not batch.option_categorical.shape[0]:
            return entities.new_empty((0, self.config.option_width))
        source = self._gather_or_zero(entities, batch.option_source_entity_indices)
        target = self._gather_or_zero(entities, batch.option_target_entity_indices)
        card = self.catalog.encode_card(
            batch.option_categorical[:, 10], batch.option_categorical_missing[:, 10]
        )
        attack = self.catalog.encode_attack(
            batch.option_categorical[:, 9], batch.option_categorical_missing[:, 9]
        )
        categorical = torch.cat(
            (
                self.selection_type(
                    batch.option_categorical[:, 0],
                    batch.option_categorical_missing[:, 0],
                ),
                self.selection_context(
                    batch.option_categorical[:, 1],
                    batch.option_categorical_missing[:, 1],
                ),
                self.option_type(
                    batch.option_categorical[:, 2],
                    batch.option_categorical_missing[:, 2],
                ),
                self.kind(
                    batch.option_categorical[:, 3],
                    batch.option_categorical_missing[:, 3],
                ),
                self.kind(
                    batch.option_categorical[:, 4],
                    batch.option_categorical_missing[:, 4],
                ),
                self.choice_role(
                    batch.option_categorical[:, 5],
                    batch.option_categorical_missing[:, 5],
                ),
                self.zone(
                    batch.option_categorical[:, 6],
                    batch.option_categorical_missing[:, 6],
                )[..., :8],
                self.zone(
                    batch.option_categorical[:, 7],
                    batch.option_categorical_missing[:, 7],
                )[..., :8],
                self.player_relative(
                    batch.option_categorical[:, 8],
                    batch.option_categorical_missing[:, 8],
                ),
                self.option_attack(attack),
                card,
                self.special_condition(
                    batch.option_categorical[:, 11],
                    batch.option_categorical_missing[:, 11],
                ),
            ),
            dim=-1,
        )
        numeric = self.option_numeric(
            self._numeric(batch.option_numeric, batch.option_numeric_missing)
        )
        return self.option_projection(
            torch.cat((categorical, source, target, numeric), dim=-1)
        )

    def forward(
        self,
        batch: TorchDecisionBatch,
        hidden: Tensor | None = None,
    ) -> PolicyOutputV1:
        if hidden is None:
            hidden = self.initial_hidden(batch.batch_size, batch.global_numeric.device)
        if hidden.shape != (batch.batch_size, self.config.public_hidden):
            raise ContractViolation("public hidden state shape differs from batch and config")
        players = self._encode_players(batch)
        entities, entity_pool = self._encode_entities(batch)
        events = self._encode_events(batch, entities)
        global_features = self._encode_global(batch)
        state_input = self.state_projection(
            torch.cat((entity_pool, players, events, global_features), dim=-1)
        )
        new_hidden = self.public_gru(state_input, hidden)
        options = self._encode_options(batch, entities)
        repeated_state = torch.repeat_interleave(
            self.policy_state(new_hidden),
            batch.option_offsets[1:] - batch.option_offsets[:-1],
            dim=0,
        )
        if options.shape[0]:
            dot = (repeated_state * options).sum(dim=-1) / math.sqrt(
                self.config.option_width
            )
            interaction = self.policy_interaction(
                torch.cat((repeated_state, options), dim=-1)
            ).squeeze(-1)
            logits = dot + interaction
            logits = logits.masked_fill(~batch.option_available, float("-inf"))
        else:
            logits = options.new_empty((0,))
        return PolicyOutputV1(
            option_logits=logits,
            values=self.value_head(new_hidden).squeeze(-1),
            hidden=new_hidden,
            entity_embeddings=entities,
            option_embeddings=options,
            entity_offsets=batch.entity_offsets,
            option_offsets=batch.option_offsets,
        )

    def decoder_initial(self, public_hidden: Tensor) -> Tensor:
        return torch.tanh(self.selection_initial(public_hidden))

    def decoder_logits(
        self,
        prefix_hidden: Tensor,
        option_embeddings: Tensor,
        available_mask: Tensor,
        stop_available: Tensor | bool,
    ) -> Tensor:
        if prefix_hidden.ndim != 1 or prefix_hidden.shape[0] != self.config.selection_hidden:
            raise ContractViolation("decoder prefix hidden state has the wrong shape")
        if option_embeddings.ndim != 2 or option_embeddings.shape[1] != self.config.option_width:
            raise ContractViolation("decoder option embeddings have the wrong shape")
        if available_mask.shape != (option_embeddings.shape[0],):
            raise ContractViolation("decoder available mask has the wrong shape")
        option_state = self.selection_option(option_embeddings)
        option_logits = (option_state * prefix_hidden).sum(dim=-1) / math.sqrt(
            self.config.selection_hidden
        )
        option_logits = option_logits.masked_fill(~available_mask, float("-inf"))
        stop_logit = (self.stop_embedding * prefix_hidden).sum() / math.sqrt(
            self.config.selection_hidden
        )
        stop_tensor = torch.as_tensor(
            stop_available, dtype=torch.bool, device=option_embeddings.device
        )
        stop_logit = stop_logit.masked_fill(~stop_tensor, float("-inf"))
        return torch.cat((option_logits, stop_logit.reshape(1)))

    def decoder_advance(self, prefix_hidden: Tensor, chosen_option: Tensor) -> Tensor:
        if chosen_option.shape != (self.config.option_width,):
            raise ContractViolation("chosen decoder option has the wrong shape")
        return self.selection_gru(chosen_option.unsqueeze(0), prefix_hidden.unsqueeze(0))[0]


def policy_metadata(model: PTCGPolicyV1) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "architecture_sha256": model.architecture_sha256,
        "config_sha256": model.config.config_sha256,
        "card_table_sha256": model.card_table_sha256,
        "trainable_parameters": model.trainable_parameter_count,
        "config": asdict(model.config),
    }
