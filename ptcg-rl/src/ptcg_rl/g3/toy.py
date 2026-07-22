from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from typing import Any

import torch
from torch import Tensor, nn

from ptcg_rl.g1.models import stable_hash
from ptcg_rl.g3.ppo import (
    CompoundActionV1,
    CompoundReplayV1,
    LocalExecutionLimitsV1,
    PPOContractError,
    apply_local_execution_limits,
    ppo_loss,
    replay_compound_action,
    require_finite_gradients,
    validate_local_workload,
    verify_probability_replay,
)

TOY_OBSERVATION_WIDTH = 8
TOY_OPTION_WIDTH = 8
TOY_TASK_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class ToyCaseV1:
    case_id: str
    observations: tuple[tuple[float, ...], ...]
    option_features: tuple[tuple[float, ...], ...]
    available_mask: tuple[bool, ...]
    minimum_count: int
    maximum_count: int
    target_indices: tuple[int, ...]

    def __post_init__(self) -> None:
        if not self.case_id:
            raise PPOContractError("toy case ID must be nonempty")
        if not self.observations or any(len(row) != TOY_OBSERVATION_WIDTH for row in self.observations):
            raise PPOContractError("toy observations must be nonempty fixed-width rows")
        if len(self.option_features) != len(self.available_mask):
            raise PPOContractError("toy option features and mask must have equal length")
        if any(len(row) != TOY_OPTION_WIDTH for row in self.option_features):
            raise PPOContractError("toy option features have the wrong width")
        if isinstance(self.minimum_count, bool) or isinstance(self.maximum_count, bool):
            raise PPOContractError("toy selection bounds must be integers")
        if self.minimum_count < 0 or self.maximum_count < self.minimum_count:
            raise PPOContractError("toy selection bounds are invalid")
        action = CompoundActionV1(self.target_indices, True)
        available = sum(self.available_mask)
        effective_maximum = min(self.maximum_count, available)
        if len(action.selected_indices) < self.minimum_count or len(action.selected_indices) > effective_maximum:
            raise PPOContractError("toy target count violates selection bounds")
        for index in action.selected_indices:
            if index < 0 or index >= len(self.available_mask) or not self.available_mask[index]:
                raise PPOContractError("toy target selects an unavailable option")

    @property
    def target_action(self) -> CompoundActionV1:
        return CompoundActionV1(self.target_indices, True)


@dataclass(frozen=True)
class ToyTaskV1:
    schema_version: int
    task_id: str
    kind: str
    cases: tuple[ToyCaseV1, ...]
    recurrent_required: bool

    def __post_init__(self) -> None:
        if self.schema_version != TOY_TASK_SCHEMA_VERSION:
            raise PPOContractError("unsupported toy task schema version")
        if not self.task_id or not self.kind or not self.cases:
            raise PPOContractError("toy task identity and cases must be nonempty")
        case_ids = [case.case_id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise PPOContractError("toy task case IDs must be unique")

    @property
    def task_sha256(self) -> str:
        return stable_hash(asdict(self))

    def case(self, case_id: str) -> ToyCaseV1:
        for case in self.cases:
            if case.case_id == case_id:
                return case
        raise PPOContractError(f"unknown toy case: {case_id}")


def _one_hot(index: int, width: int) -> tuple[float, ...]:
    if index < 0 or index >= width:
        raise PPOContractError("one-hot index is out of range")
    return tuple(1.0 if position == index else 0.0 for position in range(width))


def masked_bandit_task_v1() -> ToyTaskV1:
    masks = (
        (True, True, False, True),
        (False, True, True, True),
        (True, False, True, True),
        (True, True, True, False),
    )
    targets = (0, 2, 3, 1)
    cases = []
    options = tuple(_one_hot(index, TOY_OPTION_WIDTH) for index in range(4))
    for index, (mask, target) in enumerate(zip(masks, targets, strict=True)):
        observation = list(_one_hot(index, TOY_OBSERVATION_WIDTH))
        observation[7] = 1.0
        cases.append(
            ToyCaseV1(
                case_id=f"bandit-{index}",
                observations=(tuple(observation),),
                option_features=options,
                available_mask=mask,
                minimum_count=1,
                maximum_count=1,
                target_indices=(target,),
            )
        )
    return ToyTaskV1(1, "masked-bandit-v1", "masked_bandit", tuple(cases), False)


def recurrent_cue_task_v1() -> ToyTaskV1:
    cases = []
    options = tuple(_one_hot(index, TOY_OPTION_WIDTH) for index in range(2))
    decision_observation = list(_one_hot(5, TOY_OBSERVATION_WIDTH))
    decision_observation[7] = 1.0
    for cue in (0, 1):
        cue_observation = list(_one_hot(cue, TOY_OBSERVATION_WIDTH))
        cue_observation[4] = 1.0
        cases.append(
            ToyCaseV1(
                case_id=f"cue-{cue}",
                observations=(tuple(cue_observation), tuple(decision_observation)),
                option_features=options,
                available_mask=(True, True),
                minimum_count=1,
                maximum_count=1,
                target_indices=(cue,),
            )
        )
    return ToyTaskV1(
        1,
        "recurrent-cue-v1",
        "recurrent_partial_observation",
        tuple(cases),
        True,
    )


def variable_option_multiselect_task_v1() -> ToyTaskV1:
    definitions = (
        ("multi-one", 2, (True, True), 1, 1, (1,)),
        ("multi-empty", 3, (True, False, True), 0, 1, ()),
        ("multi-ordered", 3, (True, True, True), 1, 2, (2, 0)),
        ("multi-exact-two", 2, (True, True), 2, 2, (1, 0)),
    )
    cases = []
    for context, (case_id, option_count, mask, minimum, maximum, target) in enumerate(definitions):
        observation = list(_one_hot(context, TOY_OBSERVATION_WIDTH))
        observation[6] = 1.0
        options = tuple(_one_hot(index, TOY_OPTION_WIDTH) for index in range(option_count))
        cases.append(
            ToyCaseV1(
                case_id=case_id,
                observations=(tuple(observation),),
                option_features=options,
                available_mask=mask,
                minimum_count=minimum,
                maximum_count=maximum,
                target_indices=target,
            )
        )
    return ToyTaskV1(
        1,
        "variable-option-multiselect-v1",
        "variable_option_multi_select",
        tuple(cases),
        False,
    )


def toy_task_registry_v1() -> dict[str, ToyTaskV1]:
    tasks = (
        masked_bandit_task_v1(),
        recurrent_cue_task_v1(),
        variable_option_multiselect_task_v1(),
    )
    return {task.task_id: task for task in tasks}


@dataclass(frozen=True)
class ToyPolicyConfigV1:
    observation_width: int = TOY_OBSERVATION_WIDTH
    option_feature_width: int = TOY_OPTION_WIDTH
    hidden_width: int = 32
    option_embedding_width: int = 24
    decoder_hidden_width: int = 24

    def __post_init__(self) -> None:
        for name, value in self.__dict__.items():
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise PPOContractError(f"toy policy {name} must be a positive integer")
        if self.observation_width != TOY_OBSERVATION_WIDTH:
            raise PPOContractError("toy observation width differs from the task contract")
        if self.option_feature_width != TOY_OPTION_WIDTH:
            raise PPOContractError("toy option width differs from the task contract")

    @property
    def config_sha256(self) -> str:
        return stable_hash(asdict(self))


@dataclass(frozen=True)
class ToyDecisionV1:
    public_hidden: Tensor
    value: Tensor
    prefix_hidden: Tensor
    option_embeddings: Tensor
    available_mask: Tensor


class ToyRecurrentPolicyV1(nn.Module):
    def __init__(self, config: ToyPolicyConfigV1 | None = None) -> None:
        super().__init__()
        self.config = config or ToyPolicyConfigV1()
        self.observation_projection = nn.Sequential(
            nn.Linear(self.config.observation_width, self.config.hidden_width),
            nn.Tanh(),
        )
        self.public_gru = nn.GRUCell(self.config.hidden_width, self.config.hidden_width)
        self.option_projection = nn.Sequential(
            nn.Linear(self.config.option_feature_width, self.config.option_embedding_width),
            nn.Tanh(),
        )
        self.decoder_initial_projection = nn.Linear(
            self.config.hidden_width, self.config.decoder_hidden_width
        )
        self.decoder_option_projection = nn.Linear(
            self.config.option_embedding_width,
            self.config.decoder_hidden_width,
            bias=False,
        )
        self.decoder_gru = nn.GRUCell(
            self.config.option_embedding_width,
            self.config.decoder_hidden_width,
        )
        self.stop_embedding = nn.Parameter(torch.empty(self.config.decoder_hidden_width))
        self.value_head = nn.Sequential(
            nn.Linear(self.config.hidden_width, self.config.hidden_width),
            nn.Tanh(),
            nn.Linear(self.config.hidden_width, 1),
        )
        nn.init.normal_(self.stop_embedding, mean=0.0, std=0.02)

    @property
    def trainable_parameter_count(self) -> int:
        return sum(parameter.numel() for parameter in self.parameters() if parameter.requires_grad)

    def initial_hidden(self, device: torch.device | str = "cpu") -> Tensor:
        return torch.zeros(self.config.hidden_width, device=device)

    def encode_case(self, case: ToyCaseV1, *, stateless: bool = False) -> ToyDecisionV1:
        device = next(self.parameters()).device
        observations = torch.tensor(case.observations, dtype=torch.float32, device=device)
        if stateless:
            observations = observations[-1:]
        hidden = self.initial_hidden(device)
        for observation in observations:
            encoded = self.observation_projection(observation)
            hidden = self.public_gru(encoded, hidden)
        option_features = torch.tensor(case.option_features, dtype=torch.float32, device=device)
        option_embeddings = self.option_projection(option_features)
        prefix = torch.tanh(self.decoder_initial_projection(hidden))
        available = torch.tensor(case.available_mask, dtype=torch.bool, device=device)
        value = self.value_head(hidden).squeeze(-1)
        if not torch.isfinite(hidden).all() or not torch.isfinite(prefix).all() or not torch.isfinite(value):
            raise PPOContractError("toy policy produced nonfinite state or value")
        return ToyDecisionV1(hidden, value, prefix, option_embeddings, available)

    def decoder_logits(
        self,
        prefix_hidden: Tensor,
        option_embeddings: Tensor,
        available_mask: Tensor,
        stop_available: bool,
    ) -> Tensor:
        option_state = self.decoder_option_projection(option_embeddings)
        option_logits = (option_state * prefix_hidden).sum(dim=-1) / self.config.decoder_hidden_width**0.5
        option_logits = option_logits.masked_fill(~available_mask, float("-inf"))
        stop_logit = (self.stop_embedding * prefix_hidden).sum() / self.config.decoder_hidden_width**0.5
        if not stop_available:
            stop_logit = stop_logit.masked_fill(torch.tensor(True, device=stop_logit.device), float("-inf"))
        return torch.cat((option_logits, stop_logit.reshape(1)))

    def decoder_advance(self, prefix_hidden: Tensor, selected_option: Tensor) -> Tensor:
        return self.decoder_gru(selected_option.unsqueeze(0), prefix_hidden.unsqueeze(0))[0]


@dataclass(frozen=True)
class ToyEpisodeV1:
    case_id: str
    action: CompoundActionV1
    old_log_probability: float
    old_value: float
    reward: float
    stateless: bool


@dataclass(frozen=True)
class ToyTrainingConfigV1:
    total_non_forced_choices: int = 1024
    choices_per_update: int = 64
    ppo_epochs: int = 4
    learning_rate: float = 0.005
    adam_epsilon: float = 1e-5
    clip_coefficient: float = 0.2
    value_clip_coefficient: float = 0.2
    value_coefficient: float = 0.5
    entropy_coefficient: float = 0.01
    maximum_gradient_norm: float = 0.5

    def __post_init__(self) -> None:
        for name in ("total_non_forced_choices", "choices_per_update", "ppo_epochs"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise PPOContractError(f"{name} must be a positive integer")
        if self.total_non_forced_choices % self.choices_per_update:
            raise PPOContractError("toy total choices must be divisible by choices per update")
        for name in (
            "learning_rate",
            "adam_epsilon",
            "clip_coefficient",
            "value_clip_coefficient",
            "value_coefficient",
            "entropy_coefficient",
            "maximum_gradient_norm",
        ):
            value = getattr(self, name)
            if not isinstance(value, (int, float)) or not torch.isfinite(torch.tensor(float(value))):
                raise PPOContractError(f"{name} must be finite")
            if value < 0:
                raise PPOContractError(f"{name} must be nonnegative")


@dataclass(frozen=True)
class ToyTrainingResultV1:
    task_id: str
    seed: int
    stateless: bool
    choices: int
    updates: int
    initial_score: float
    final_score: float
    maximum_probability_replay_error: float
    maximum_initial_ratio_error: float
    maximum_gradient_norm_before_clip: float
    wall_seconds: float
    zero_tolerance_counters: dict[str, int]


def replay_toy_episode(
    model: ToyRecurrentPolicyV1,
    task: ToyTaskV1,
    episode: ToyEpisodeV1,
) -> tuple[Tensor, Tensor, Tensor]:
    case = task.case(episode.case_id)
    decision = model.encode_case(case, stateless=episode.stateless)
    replay = replay_compound_action(
        initial_prefix=decision.prefix_hidden,
        option_embeddings=decision.option_embeddings,
        available_mask=decision.available_mask,
        action=episode.action,
        minimum_count=case.minimum_count,
        maximum_count=case.maximum_count,
        decoder_logits=model.decoder_logits,
        decoder_advance=model.decoder_advance,
    )
    return replay.log_probability, decision.value, replay.normalized_entropy


def _choose_from_logits(logits: Tensor, mask: Tensor, *, generator: torch.Generator | None) -> int:
    masked = logits.masked_fill(~mask, float("-inf"))
    probabilities = torch.softmax(masked, dim=0)
    if generator is None:
        return int(torch.argmax(probabilities).item())
    return int(torch.multinomial(probabilities, 1, generator=generator).item())


def choose_toy_action(
    model: ToyRecurrentPolicyV1,
    case: ToyCaseV1,
    *,
    stateless: bool,
    generator: torch.Generator | None,
) -> tuple[CompoundActionV1, CompoundReplayV1, Tensor]:
    decision = model.encode_case(case, stateless=stateless)
    prefix = decision.prefix_hidden
    available = decision.available_mask.clone()
    selected: list[int] = []
    effective_maximum = min(case.maximum_count, int(available.sum().item()))
    for _ in range(effective_maximum + 1):
        stop_available = len(selected) >= case.minimum_count
        if len(selected) >= effective_maximum:
            available[:] = False
        logits = model.decoder_logits(prefix, decision.option_embeddings, available, stop_available)
        mask = torch.cat(
            (available, torch.tensor([stop_available], dtype=torch.bool, device=available.device))
        )
        choice = _choose_from_logits(logits, mask, generator=generator)
        if choice == decision.option_embeddings.shape[0]:
            action = CompoundActionV1(tuple(selected), True)
            replay = replay_compound_action(
                initial_prefix=decision.prefix_hidden,
                option_embeddings=decision.option_embeddings,
                available_mask=decision.available_mask,
                action=action,
                minimum_count=case.minimum_count,
                maximum_count=case.maximum_count,
                decoder_logits=model.decoder_logits,
                decoder_advance=model.decoder_advance,
            )
            return action, replay, decision.value
        if choice in selected or not bool(available[choice]):
            raise PPOContractError("toy policy sampled an invalid or duplicate option")
        selected.append(choice)
        prefix = model.decoder_advance(prefix, decision.option_embeddings[choice])
        available[choice] = False
    raise PPOContractError("toy compound decoder failed to terminate")


def collect_toy_episodes(
    model: ToyRecurrentPolicyV1,
    task: ToyTaskV1,
    *,
    count: int,
    start_case_index: int,
    generator: torch.Generator,
    stateless: bool,
) -> tuple[ToyEpisodeV1, ...]:
    if count <= 0:
        raise PPOContractError("toy episode collection count must be positive")
    episodes = []
    was_training = model.training
    model.eval()
    try:
        with torch.no_grad():
            for offset in range(count):
                case = task.cases[(start_case_index + offset) % len(task.cases)]
                action, replay, value = choose_toy_action(
                    model, case, stateless=stateless, generator=generator
                )
                reward = 1.0 if action == case.target_action else 0.0
                episodes.append(
                    ToyEpisodeV1(
                        case_id=case.case_id,
                        action=action,
                        old_log_probability=float(replay.log_probability.cpu()),
                        old_value=float(value.cpu()),
                        reward=reward,
                        stateless=stateless,
                    )
                )
    finally:
        model.train(was_training)
    return tuple(episodes)


def evaluate_toy_policy(
    model: ToyRecurrentPolicyV1,
    task: ToyTaskV1,
    *,
    stateless: bool = False,
) -> dict[str, Any]:
    was_training = model.training
    model.eval()
    case_results = []
    try:
        with torch.no_grad():
            for case in task.cases:
                action, replay, value = choose_toy_action(
                    model, case, stateless=stateless, generator=None
                )
                case_results.append(
                    {
                        "case_id": case.case_id,
                        "passed": action == case.target_action,
                        "selected_indices": list(action.selected_indices),
                        "target_indices": list(case.target_indices),
                        "log_probability": float(replay.log_probability.cpu()),
                        "value": float(value.cpu()),
                    }
                )
    finally:
        model.train(was_training)
    passed = sum(int(item["passed"]) for item in case_results)
    return {
        "task_id": task.task_id,
        "stateless": stateless,
        "score": passed / len(case_results),
        "passed_cases": passed,
        "total_cases": len(case_results),
        "cases": case_results,
    }


def train_toy_policy(
    task: ToyTaskV1,
    *,
    seed: int,
    config: ToyTrainingConfigV1 | None = None,
    stateless: bool = False,
    limits: LocalExecutionLimitsV1 | None = None,
) -> tuple[ToyRecurrentPolicyV1, torch.optim.Optimizer, Any, ToyTrainingResultV1]:
    config = config or ToyTrainingConfigV1()
    limits = limits or LocalExecutionLimitsV1()
    validate_local_workload(
        non_forced_choices=config.total_non_forced_choices,
        worker_processes=0,
        device="cpu",
        limits=limits,
    )
    apply_local_execution_limits(limits)
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise PPOContractError("toy training seed must be a nonnegative integer")
    torch.manual_seed(seed)
    generator = torch.Generator(device="cpu")
    generator.manual_seed(seed ^ 0x5A17)
    model = ToyRecurrentPolicyV1().cpu()
    optimizer = torch.optim.Adam(
        model.parameters(), lr=config.learning_rate, eps=config.adam_epsilon
    )
    total_updates = config.total_non_forced_choices // config.choices_per_update
    scheduler = torch.optim.lr_scheduler.LinearLR(
        optimizer, start_factor=1.0, end_factor=0.25, total_iters=max(total_updates, 1)
    )
    initial_score = float(evaluate_toy_policy(model, task, stateless=stateless)["score"])
    maximum_replay_error = 0.0
    maximum_ratio_error = 0.0
    maximum_gradient_norm = 0.0
    start = time.monotonic()
    model.train()

    for update in range(total_updates):
        if time.monotonic() - start > limits.max_wall_seconds:
            raise PPOContractError("local toy training exceeded the wall-time safety envelope")
        episodes = collect_toy_episodes(
            model,
            task,
            count=config.choices_per_update,
            start_case_index=update * config.choices_per_update,
            generator=generator,
            stateless=stateless,
        )
        old_log_probabilities = torch.tensor(
            [episode.old_log_probability for episode in episodes], dtype=torch.float32
        )
        old_values = torch.tensor([episode.old_value for episode in episodes], dtype=torch.float32)
        returns = torch.tensor([episode.reward for episode in episodes], dtype=torch.float32)
        advantages = returns - old_values
        with torch.no_grad():
            replayed = torch.stack([replay_toy_episode(model, task, episode)[0] for episode in episodes])
        replay_check = verify_probability_replay(old_log_probabilities, replayed)
        maximum_replay_error = max(
            maximum_replay_error, replay_check.maximum_log_probability_absolute_error
        )
        maximum_ratio_error = max(
            maximum_ratio_error, replay_check.maximum_ratio_absolute_error_from_one
        )

        for _ in range(config.ppo_epochs):
            outputs = [replay_toy_episode(model, task, episode) for episode in episodes]
            new_log_probabilities = torch.stack([item[0] for item in outputs])
            new_values = torch.stack([item[1] for item in outputs])
            entropies = torch.stack([item[2] for item in outputs])
            loss = ppo_loss(
                new_log_probabilities=new_log_probabilities,
                old_log_probabilities=old_log_probabilities,
                advantages=advantages,
                new_values=new_values,
                old_values=old_values,
                returns=returns,
                normalized_entropies=entropies,
                policy_mask=torch.ones(len(episodes), dtype=torch.bool),
                clip_coefficient=config.clip_coefficient,
                value_clip_coefficient=config.value_clip_coefficient,
                value_coefficient=config.value_coefficient,
                entropy_coefficient=config.entropy_coefficient,
            )
            optimizer.zero_grad(set_to_none=True)
            loss.total.backward()
            gradient_norm = require_finite_gradients(tuple(model.parameters()))
            maximum_gradient_norm = max(maximum_gradient_norm, gradient_norm)
            torch.nn.utils.clip_grad_norm_(model.parameters(), config.maximum_gradient_norm)
            optimizer.step()
        scheduler.step()

    final_score = float(evaluate_toy_policy(model, task, stateless=stateless)["score"])
    wall_seconds = time.monotonic() - start
    counters = {
        "crashes": 0,
        "fallbacks": 0,
        "hidden_state_cross_owner_events": 0,
        "invalid_actions": 0,
        "nan_inf": 0,
        "stale_inference_requests": 0,
        "timeouts": 0,
        "unclassified_truncations": 0,
    }
    result = ToyTrainingResultV1(
        task_id=task.task_id,
        seed=seed,
        stateless=stateless,
        choices=config.total_non_forced_choices,
        updates=total_updates,
        initial_score=initial_score,
        final_score=final_score,
        maximum_probability_replay_error=maximum_replay_error,
        maximum_initial_ratio_error=maximum_ratio_error,
        maximum_gradient_norm_before_clip=maximum_gradient_norm,
        wall_seconds=wall_seconds,
        zero_tolerance_counters=counters,
    )
    return model, optimizer, scheduler, result


def recurrent_margin(
    recurrent_result: ToyTrainingResultV1,
    stateless_result: ToyTrainingResultV1,
) -> float:
    if recurrent_result.task_id != "recurrent-cue-v1" or stateless_result.task_id != "recurrent-cue-v1":
        raise PPOContractError("recurrent margin requires recurrent-cue results")
    if recurrent_result.seed != stateless_result.seed:
        raise PPOContractError("recurrent and stateless results must use the same seed")
    if recurrent_result.stateless or not stateless_result.stateless:
        raise PPOContractError("recurrent margin result roles are reversed")
    return recurrent_result.final_score - stateless_result.final_score


def toy_result_record(result: ToyTrainingResultV1) -> dict[str, Any]:
    value = asdict(result)
    value["zero_tolerance_total"] = sum(result.zero_tolerance_counters.values())
    return value
