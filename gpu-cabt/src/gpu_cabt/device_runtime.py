from __future__ import annotations

import os

from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np

from .nvrtc import load_cupy_module
from .rule_static import RuleTableBlob, extract_rule_tables
from .source import build_cuda_source as build_canonical_cuda_source

_KERNEL_NAMES = (
    "gpu_cabt_runtime_info", "gpu_cabt_runtime_status", "gpu_cabt_game_reset",
    "gpu_cabt_game_reset_selected", "gpu_cabt_post_setup_begin", "gpu_cabt_game_step",
    "gpu_cabt_project_policy", "gpu_cabt_project_events",
)


@dataclass(frozen=True)
class RuntimeAbi:
    state_bytes: int
    runtime_bytes: int
    global_width: int
    player_width: int
    entity_capacity: int
    entity_width: int
    option_capacity: int
    option_width: int
    selected_capacity: int
    deck_size: int
    all_card_capacity: int
    runtime_option_capacity: int
    public_log_capacity: int
    public_event_width: int


@dataclass(frozen=True)
class PolicyProjectionBatch:
    globals: Any
    players: Any
    entities: Any
    entity_counts: Any
    options: Any
    option_counts: Any
    status: Any

    def torch(self, torch_module: ModuleType | None = None) -> "PolicyProjectionBatch":
        if torch_module is None:
            import torch as torch_module  # type: ignore[no-redef]
        convert = torch_module.from_dlpack
        return PolicyProjectionBatch(
            globals=convert(self.globals), players=convert(self.players),
            entities=convert(self.entities), entity_counts=convert(self.entity_counts),
            options=convert(self.options), option_counts=convert(self.option_counts),
            status=convert(self.status),
        )


@dataclass(frozen=True)
class PublicEventBatch:
    events: Any
    counts: Any
    status: Any

    def torch(self, torch_module: ModuleType | None = None) -> "PublicEventBatch":
        if torch_module is None:
            import torch as torch_module  # type: ignore[no-redef]
        convert = torch_module.from_dlpack
        return PublicEventBatch(
            events=convert(self.events), counts=convert(self.counts), status=convert(self.status)
        )


@dataclass(frozen=True)
class RuntimeStatusBatch:
    error_flags: Any
    game_results: Any
    select_types: Any
    select_players: Any
    turns: Any

    def torch(self, torch_module: ModuleType | None = None) -> "RuntimeStatusBatch":
        if torch_module is None:
            import torch as torch_module  # type: ignore[no-redef]
        convert = torch_module.from_dlpack
        return RuntimeStatusBatch(
            error_flags=convert(self.error_flags), game_results=convert(self.game_results),
            select_types=convert(self.select_types), select_players=convert(self.select_players),
            turns=convert(self.turns),
        )


def package_root() -> Path:
    return Path(__file__).resolve().parent


def repo_root() -> Path:
    """Return the standalone gpu-cabt project root."""
    return package_root().parents[1]


def default_official_dir() -> Path:
    """Resolve official competition engine headers without copying protected assets."""
    override = os.environ.get("GPU_CABT_OFFICIAL_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return (repo_root().parent / "pokemon-tcg-ai-battle/ptcg_engine/ptcgProgram 22").resolve()


def build_cuda_source() -> str:
    return build_canonical_cuda_source(include_policy=True)


class GpuCabtRuntime:
    """Batched GPU-resident CABT simulator and public policy projection."""

    def __init__(
        self,
        env_count: int,
        *,
        cupy_module: ModuleType | None = None,
        official_dir: Path | None = None,
        rule_tables: RuleTableBlob | None = None,
        stack_size_bytes: int = 16 * 1024,
    ) -> None:
        if env_count <= 0:
            raise ValueError("env_count must be positive")
        if stack_size_bytes < 4 * 1024:
            raise ValueError("stack_size_bytes must retain at least the qualified 4 KiB floor")
        if cupy_module is None:
            import cupy as cupy_module  # type: ignore[no-redef]
        self.cp = cupy_module
        self.env_count = int(env_count)
        self.stack_size_bytes = int(stack_size_bytes)
        self.official_dir = (official_dir or default_official_dir()).resolve()
        self.rule_tables = rule_tables or extract_rule_tables(self.official_dir, repo_root())

        self.cp.cuda.runtime.deviceSetLimit(0, self.stack_size_bytes)
        self.module = load_cupy_module(
            self.cp, build_cuda_source(), kernel_names=_KERNEL_NAMES,
        )
        self._kernels = {name: self.module.get_function(name) for name in _KERNEL_NAMES}
        self.abi = self._read_abi()
        if self.abi.deck_size != 60 or self.abi.all_card_capacity < 123:
            raise RuntimeError(f"unexpected GPU CABT ABI: {self.abi}")

        self._rules = self._upload_rules(self.rule_tables)
        cp = self.cp
        n = self.env_count
        self.states = cp.empty(n * self.abi.state_bytes, dtype=cp.uint8)
        self.runtimes = cp.empty(n * self.abi.runtime_bytes, dtype=cp.uint8)
        self._projection = PolicyProjectionBatch(
            globals=cp.empty((n, self.abi.global_width), dtype=cp.int32),
            players=cp.empty((n, 2, self.abi.player_width), dtype=cp.int32),
            entities=cp.empty((n, self.abi.entity_capacity, self.abi.entity_width), dtype=cp.int32),
            entity_counts=cp.empty(n, dtype=cp.int32),
            options=cp.empty((n, self.abi.option_capacity, self.abi.option_width), dtype=cp.int32),
            option_counts=cp.empty(n, dtype=cp.int32),
            status=cp.empty(n, dtype=cp.uint32),
        )
        self._status = RuntimeStatusBatch(
            error_flags=cp.empty(n, dtype=cp.uint32),
            game_results=cp.empty(n, dtype=cp.uint8),
            select_types=cp.empty(n, dtype=cp.uint8),
            select_players=cp.empty(n, dtype=cp.int8),
            turns=cp.empty(n, dtype=cp.int32),
        )
        self._events: PublicEventBatch | None = None

    @property
    def blocks(self) -> int:
        return (self.env_count + 127) // 128

    @property
    def threads(self) -> int:
        return 128

    def _read_abi(self) -> RuntimeAbi:
        out = self.cp.empty(14, dtype=self.cp.int32)
        self._kernels["gpu_cabt_runtime_info"]((1,), (1,), (out,))
        self.cp.cuda.Stream.null.synchronize()
        values = tuple(int(value) for value in out.get().tolist())
        return RuntimeAbi(*values)

    def _upload_bytes(self, value: bytes) -> Any:
        return self.cp.asarray(np.frombuffer(value, dtype=np.uint8).copy())

    def _upload_rules(self, rules: RuleTableBlob) -> tuple[Any, ...]:
        return (
            self._upload_bytes(rules.cards), self._upload_bytes(rules.skills),
            self._upload_bytes(rules.attacks), self._upload_bytes(rules.effects),
            self._upload_bytes(rules.triggers), self._upload_bytes(rules.substring_masks),
            np.int32(rules.card_count), np.int32(rules.skill_count),
            np.int32(rules.attack_count), np.int32(rules.effect_count),
            np.int32(rules.trigger_count), np.int32(rules.substring_mask_count),
            np.int32(rules.substring_mask_words),
        )

    def _as_device(self, value: Any, *, dtype: Any) -> Any:
        cp = self.cp
        if isinstance(value, cp.ndarray):
            result = value
        elif isinstance(value, np.ndarray):
            result = cp.asarray(value)
        elif hasattr(value, "__dlpack__"):
            result = cp.from_dlpack(value)
        else:
            result = cp.asarray(value)
        if result.dtype != dtype:
            result = result.astype(dtype, copy=False)
        return cp.ascontiguousarray(result)

    def reset(self, decks: Any, *, seed: int, stream_base: int = 0) -> None:
        deck_array = self._as_device(decks, dtype=self.cp.int32)
        expected = (self.env_count, 2, self.abi.deck_size)
        if tuple(deck_array.shape) != expected:
            raise ValueError(f"decks shape must be {expected}, got {tuple(deck_array.shape)}")
        self._kernels["gpu_cabt_game_reset"](
            (self.blocks,), (self.threads,),
            (self.states, self.runtimes, deck_array, np.uint64(seed),
             np.uint64(stream_base), np.int32(self.env_count)),
        )

    def reset_selected(
        self,
        decks: Any,
        reset_mask: Any,
        *,
        seed: int,
        stream_base: int = 0,
    ) -> None:
        """Reset only environments whose byte mask is nonzero, entirely on device."""
        deck_array = self._as_device(decks, dtype=self.cp.int32)
        expected = (self.env_count, 2, self.abi.deck_size)
        if tuple(deck_array.shape) != expected:
            raise ValueError(f"decks shape must be {expected}, got {tuple(deck_array.shape)}")
        mask = self._as_device(reset_mask, dtype=self.cp.uint8)
        if tuple(mask.shape) != (self.env_count,):
            raise ValueError("reset_mask must have shape (env_count,)")
        self._kernels["gpu_cabt_game_reset_selected"](
            (self.blocks,), (self.threads,),
            (self.states, self.runtimes, deck_array, mask, np.uint64(seed),
             np.uint64(stream_base), np.int32(self.env_count)),
        )

    def begin_post_setup(self) -> None:
        self._kernels["gpu_cabt_post_setup_begin"](
            (self.blocks,), (self.threads,),
            (self.states, self.runtimes) + self._rules + (np.int32(self.env_count),),
        )

    def step(self, response_present: Any, selected_counts: Any, selected_indices: Any) -> None:
        present = self._as_device(response_present, dtype=self.cp.uint8)
        counts = self._as_device(selected_counts, dtype=self.cp.int32)
        indices = self._as_device(selected_indices, dtype=self.cp.int32)
        if tuple(present.shape) != (self.env_count,):
            raise ValueError("response_present must have shape (env_count,)")
        if tuple(counts.shape) != (self.env_count,):
            raise ValueError("selected_counts must have shape (env_count,)")
        if indices.ndim != 2 or indices.shape[0] != self.env_count:
            raise ValueError("selected_indices must have shape (env_count, stride)")
        stride = int(indices.shape[1])
        if stride <= 0 or stride > self.abi.selected_capacity:
            raise ValueError(f"selected_indices stride must be within 1..{self.abi.selected_capacity}")
        self._kernels["gpu_cabt_game_step"](
            (self.blocks,), (self.threads,),
            (self.states, self.runtimes) + self._rules
            + (present, counts, indices, np.int32(stride), np.int32(self.env_count)),
        )

    def project_policy(self) -> PolicyProjectionBatch:
        p = self._projection
        self._kernels["gpu_cabt_project_policy"](
            (self.blocks,), (self.threads,),
            (self.states, self.runtimes) + self._rules
            + (p.globals, p.players, p.entities, p.entity_counts, p.options,
               p.option_counts, p.status, np.int32(self.env_count)),
        )
        return p

    def project_events(self, *, acknowledge: bool = True) -> PublicEventBatch:
        cp = self.cp
        if self._events is None:
            n = self.env_count
            self._events = PublicEventBatch(
                events=cp.empty(
                    (n, self.abi.public_log_capacity, self.abi.public_event_width),
                    dtype=cp.int32,
                ),
                counts=cp.empty(n, dtype=cp.int32),
                status=cp.empty(n, dtype=cp.uint32),
            )
        batch = self._events
        self._kernels["gpu_cabt_project_events"](
            (self.blocks,), (self.threads,),
            (self.states, self.runtimes, batch.events, batch.counts, batch.status,
             np.uint8(1 if acknowledge else 0), np.int32(self.env_count)),
        )
        return batch

    def status(self) -> RuntimeStatusBatch:
        s = self._status
        self._kernels["gpu_cabt_runtime_status"](
            (self.blocks,), (self.threads,),
            (self.states, self.runtimes, s.error_flags, s.game_results,
             s.select_types, s.select_players, s.turns, np.int32(self.env_count)),
        )
        return s

    def synchronize(self) -> None:
        self.cp.cuda.Stream.null.synchronize()

    def memory_bytes(self) -> int:
        arrays = [
            self.states, self.runtimes, *self._rules[:6],
            self._projection.globals, self._projection.players,
            self._projection.entities, self._projection.entity_counts,
            self._projection.options, self._projection.option_counts,
            self._projection.status, self._status.error_flags,
            self._status.game_results, self._status.select_types,
            self._status.select_players, self._status.turns,
        ]
        if self._events is not None:
            arrays.extend((self._events.events, self._events.counts, self._events.status))
        return sum(int(array.nbytes) for array in arrays)
