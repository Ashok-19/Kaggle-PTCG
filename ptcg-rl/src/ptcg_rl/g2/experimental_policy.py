from __future__ import annotations

import math
from dataclasses import asdict, dataclass

import torch
from torch import Tensor, nn

from ptcg_rl.g1.models import ContractViolation, stable_hash

from .card_table import CardTableV1
from .network import PTCGPolicyV1, PolicyConfigV1, PolicyOutputV1, TorchDecisionBatch


@dataclass(frozen=True)
class OptionEntityCrossAttentionConfigV1:
    """Experimental legal-option -> board-entity cross-attention block."""

    schema_version: int = 1
    attention_width: int = 64
    attention_heads: int = 4
    gated_residual: bool = False

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported cross-attention config schema version")
        if isinstance(self.attention_width, bool) or self.attention_width <= 0:
            raise ValueError("attention width must be positive")
        if isinstance(self.attention_heads, bool) or self.attention_heads <= 0:
            raise ValueError("attention heads must be positive")
        if self.attention_width % self.attention_heads:
            raise ValueError("attention width must be divisible by attention heads")
        if not isinstance(self.gated_residual, bool):
            raise ValueError("gated residual must be boolean")

    @property
    def config_sha256(self) -> str:
        return stable_hash(asdict(self))


class PTCGPolicyCrossAttentionV1(PTCGPolicyV1):
    """PTCGPolicyV1 augmented with option-conditioned attention over board entities.

    The sealed PTCGPolicyV1 is intentionally left unchanged. This class is an
    experimental ablation path that reuses all proven encoders/recurrent state and
    enriches each legal-option embedding with a board context selected by that option.
    """

    def __init__(
        self,
        table: CardTableV1,
        config: PolicyConfigV1 | None = None,
        cross_attention: OptionEntityCrossAttentionConfigV1 | None = None,
    ) -> None:
        super().__init__(table, config)
        self.cross_attention_config = cross_attention or OptionEntityCrossAttentionConfigV1()
        width = self.cross_attention_config.attention_width
        self.option_cross_query = nn.Linear(self.config.option_width, width, bias=False)
        self.entity_cross_key = nn.Linear(self.config.model_width, width, bias=False)
        self.entity_cross_value = nn.Linear(self.config.model_width, width, bias=False)
        self.option_entity_attention = nn.MultiheadAttention(
            embed_dim=width,
            num_heads=self.cross_attention_config.attention_heads,
            dropout=0.0,
            batch_first=True,
        )
        self.option_cross_output = nn.Linear(width, self.config.option_width, bias=False)
        self.option_cross_norm = nn.LayerNorm(self.config.option_width)
        self.null_cross_entity = nn.Parameter(torch.zeros(self.config.model_width))
        self.option_cross_gate: nn.Linear | None = None
        if self.cross_attention_config.gated_residual:
            self.option_cross_gate = nn.Linear(self.config.option_width * 2, self.config.option_width)

        self._initialize_cross_attention()

    def _initialize_cross_attention(self) -> None:
        for module in (
            self.option_cross_query,
            self.entity_cross_key,
            self.entity_cross_value,
            self.option_cross_output,
        ):
            nn.init.orthogonal_(module.weight, gain=1.0)
        nn.init.xavier_uniform_(self.option_entity_attention.in_proj_weight)
        if self.option_entity_attention.in_proj_bias is not None:
            nn.init.zeros_(self.option_entity_attention.in_proj_bias)
        nn.init.xavier_uniform_(self.option_entity_attention.out_proj.weight)
        if self.option_entity_attention.out_proj.bias is not None:
            nn.init.zeros_(self.option_entity_attention.out_proj.bias)
        nn.init.zeros_(self.null_cross_entity)
        if self.option_cross_gate is not None:
            nn.init.zeros_(self.option_cross_gate.weight)
            nn.init.constant_(self.option_cross_gate.bias, -2.0)

    @property
    def architecture_sha256(self) -> str:
        return stable_hash(
            {
                "kind": "ptcg-policy-option-entity-cross-attention-v1",
                "base_config": asdict(self.config),
                "cross_attention_config": asdict(self.cross_attention_config),
                "card_table_sha256": self.card_table_sha256,
                "parameter_shapes": {
                    name: tuple(parameter.shape)
                    for name, parameter in self.named_parameters()
                },
            }
        )

    def _option_conditioned_entity_context(
        self,
        options: Tensor,
        entities: Tensor,
        option_offsets: Tensor,
        entity_offsets: Tensor,
    ) -> Tensor:
        if options.shape[0] == 0:
            return options
        batch_size = int(option_offsets.shape[0] - 1)
        option_lengths = option_offsets[1:] - option_offsets[:-1]
        entity_lengths = entity_offsets[1:] - entity_offsets[:-1]
        max_options = int(option_lengths.max().item())
        max_entities = int(entity_lengths.max().item())

        padded_options = options.new_zeros((batch_size, max_options, self.config.option_width))
        option_padding = torch.ones(
            (batch_size, max_options), dtype=torch.bool, device=options.device
        )
        option_owner = torch.repeat_interleave(
            torch.arange(batch_size, device=options.device, dtype=torch.long), option_lengths
        )
        option_local = torch.arange(options.shape[0], device=options.device, dtype=torch.long)
        option_local = option_local - torch.repeat_interleave(option_offsets[:-1], option_lengths)
        padded_options[option_owner, option_local] = options
        option_padding[option_owner, option_local] = False

        # Position zero is a learned null entity. It makes attention numerically safe
        # even for an observation with no board entities.
        padded_entities = entities.new_zeros(
            (batch_size, max_entities + 1, self.config.model_width)
        )
        entity_padding = torch.ones(
            (batch_size, max_entities + 1), dtype=torch.bool, device=entities.device
        )
        padded_entities[:, 0] = self.null_cross_entity
        entity_padding[:, 0] = False
        if entities.shape[0]:
            entity_owner = torch.repeat_interleave(
                torch.arange(batch_size, device=entities.device, dtype=torch.long), entity_lengths
            )
            entity_local = torch.arange(entities.shape[0], device=entities.device, dtype=torch.long)
            entity_local = entity_local - torch.repeat_interleave(entity_offsets[:-1], entity_lengths)
            padded_entities[entity_owner, entity_local + 1] = entities
            entity_padding[entity_owner, entity_local + 1] = False

        query = self.option_cross_query(padded_options)
        key = self.entity_cross_key(padded_entities)
        value = self.entity_cross_value(padded_entities)
        attended, _ = self.option_entity_attention(
            query,
            key,
            value,
            key_padding_mask=entity_padding,
            need_weights=False,
        )
        context = self.option_cross_output(attended)
        if self.option_cross_gate is None:
            enriched = self.option_cross_norm(padded_options + context)
        else:
            gate = torch.sigmoid(
                self.option_cross_gate(torch.cat((padded_options, context), dim=-1))
            )
            enriched = self.option_cross_norm(padded_options + gate * context)
        enriched = enriched.masked_fill(option_padding.unsqueeze(-1), 0.0)
        return enriched[option_owner, option_local]

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
        options = self._option_conditioned_entity_context(
            options,
            entities,
            batch.option_offsets,
            batch.entity_offsets,
        )
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
