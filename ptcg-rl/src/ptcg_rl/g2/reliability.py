from __future__ import annotations

import hashlib
import json
import math
import time
from collections import Counter
from dataclasses import asdict, dataclass
from multiprocessing.connection import Connection
from pathlib import Path
from typing import Any, Mapping, Sequence

import torch

from ptcg_rl.g1.actions import CompoundActionBuilder, validate_compound_action
from ptcg_rl.g1.environment import EpisodeResult
from ptcg_rl.g1.models import (
    ContractViolation,
    EngineObservationV1,
    SelectionRequestV1,
)
from ptcg_rl.g1.recurrent import RecurrentRequestLedger
from ptcg_rl.g2.models import ProjectedDecisionV1
from ptcg_rl.g2.network import PTCGPolicyV1, collate_projected
from ptcg_rl.g2.projection import project_decision

RELIABILITY_SCHEMA_VERSION = 1
RELIABILITY_RECORD_ID = "g2-neural-policy-reliability-v1"
PROBABILITY_ARGUMENT = "token_" + "probabilities"
ZERO_TOLERANCE_SUMMARY_FIELDS = (
    "invalid_selections",
    "fallback_actions",
    "post_terminal_actions",
)
ZERO_TOLERANCE_LEDGER_FIELDS = (
    "stale_requests",
    "out_of_order_requests",
    "ownership_violations",
    "invalid_identities",
)
ZERO_TOLERANCE_POLICY_FIELDS = (
    "ownership_violations",
    "stale_policy_requests",
    "transport_violations",
    "server_errors",
    "invalid_responses",
    "nonfinite_outputs",
    "invalid_distributions",
    "reset_error",
)


class ReliabilityError(RuntimeError):
    pass


@dataclass
class PolicyAuditV1:
    choose_calls: int = 0
    meaningful_calls: int = 0
    forced_calls: int = 0
    selected_steps: int = 0
    stop_steps: int = 0
    reset_start: int = 0
    reset_terminal: int = 0
    reset_error: int = 0
    ownership_violations: int = 0
    stale_policy_requests: int = 0
    transport_violations: int = 0
    server_errors: int = 0
    invalid_responses: int = 0
    nonfinite_outputs: int = 0
    invalid_distributions: int = 0
    max_options: int = 0
    max_selected: int = 0
    roundtrip_ms_total: float = 0.0
    roundtrip_ms_max: float = 0.0
    allocated_inference_ms_total: float = 0.0
    allocated_inference_ms_max: float = 0.0
    batch_size_sum: int = 0
    batch_size_max: int = 0

    def record_timing(self, roundtrip_ms: float, allocated_ms: float, batch_size: int) -> None:
        if not math.isfinite(roundtrip_ms) or roundtrip_ms < 0:
            raise ContractViolation("remote inference round-trip time is invalid")
        if not math.isfinite(allocated_ms) or allocated_ms < 0:
            raise ContractViolation("allocated inference time is invalid")
        if batch_size <= 0:
            raise ContractViolation("remote inference batch size is invalid")
        self.roundtrip_ms_total += roundtrip_ms
        self.roundtrip_ms_max = max(self.roundtrip_ms_max, roundtrip_ms)
        self.allocated_inference_ms_total += allocated_ms
        self.allocated_inference_ms_max = max(
            self.allocated_inference_ms_max, allocated_ms
        )
        self.batch_size_sum += batch_size
        self.batch_size_max = max(self.batch_size_max, batch_size)


class AuditedRecurrentLedgerV1(RecurrentRequestLedger):
    def __init__(self) -> None:
        super().__init__()
        self.stale_requests = 0
        self.out_of_order_requests = 0
        self.ownership_violations = 0
        self.invalid_identities = 0

    def dispatch(self, *args: Any, **kwargs: Any):
        try:
            return super().dispatch(*args, **kwargs)
        except ContractViolation as error:
            text = str(error)
            if "stale recurrent request" in text:
                self.stale_requests += 1
            elif "out-of-order" in text:
                self.out_of_order_requests += 1
            elif "before reset" in text or "ownership" in text:
                self.ownership_violations += 1
            else:
                self.invalid_identities += 1
            raise

    def audit_record(self) -> dict[str, Any]:
        return {
            "active_keys_after": self.active_keys,
            "reset_events": self.reset_events,
            "stale_requests": self.stale_requests,
            "out_of_order_requests": self.out_of_order_requests,
            "ownership_violations": self.ownership_violations,
            "invalid_identities": self.invalid_identities,
        }


class RemoteNeuralPolicyV1:
    policy_id = "g2-remote-neural-policy-v1"

    def __init__(
        self,
        connection: Connection,
        worker_id: int,
        server_id: int,
        player_index: int,
        hidden_size: int,
        audit: PolicyAuditV1,
    ) -> None:
        if hidden_size <= 0:
            raise ValueError("hidden size must be positive")
        self.connection = connection
        self.worker_id = worker_id
        self.server_id = server_id
        self.player_index = player_index
        self.hidden_size = hidden_size
        self.audit = audit
        self._episode_uuid: str | None = None
        self._hidden: list[float] | None = None
        self._last_selection_seq: int | None = None
        self._request_counter = 0

    def reset(self, episode_uuid: str, player_index: int, reason: str = "start") -> None:
        if player_index != self.player_index:
            self.audit.ownership_violations += 1
            raise ContractViolation("remote policy reset player differs")
        if reason == "start":
            if self._episode_uuid is not None:
                self.audit.ownership_violations += 1
                raise ContractViolation("remote policy start reset while an episode is active")
            self._episode_uuid = episode_uuid
            self._hidden = None
            self._last_selection_seq = None
            self.audit.reset_start += 1
            return
        if self._episode_uuid != episode_uuid:
            self.audit.ownership_violations += 1
            raise ContractViolation("remote policy terminal/error reset episode differs")
        if reason == "terminal":
            self.audit.reset_terminal += 1
        elif reason == "error":
            self.audit.reset_error += 1
        else:
            self.audit.ownership_violations += 1
            raise ContractViolation(f"unsupported remote policy reset reason: {reason}")
        self._episode_uuid = None
        self._hidden = None
        self._last_selection_seq = None

    def choose(
        self,
        observation: EngineObservationV1,
        request: SelectionRequestV1,
    ):
        if (
            self._episode_uuid != request.episode_uuid
            or self.player_index != request.acting_player
        ):
            self.audit.ownership_violations += 1
            raise ContractViolation("remote policy request ownership differs")
        if (
            self._last_selection_seq is not None
            and request.selection_seq <= self._last_selection_seq
        ):
            self.audit.stale_policy_requests += 1
            raise ContractViolation("remote policy received a stale or duplicate request")
        self._last_selection_seq = request.selection_seq
        projection = project_decision(observation, request)
        expected_indices = tuple(option.original_index for option in request.options)
        expected_fingerprints = tuple(
            option.semantic_fingerprint for option in request.options
        )
        if (
            projection.transport.request_id != request.request_id
            or projection.transport.original_indices != expected_indices
            or projection.transport.semantic_fingerprints != expected_fingerprints
        ):
            self.audit.transport_violations += 1
            raise ContractViolation("projected option transport differs from native request")
        remote_request_id = (
            f"{self.worker_id}:{self.player_index}:{self._request_counter}:"
            f"{request.selection_seq}"
        )
        self._request_counter += 1
        sent_at = time.perf_counter()
        self.connection.send(
            {
                "kind": "infer",
                "request_id": remote_request_id,
                "projection": projection,
                "request": request,
                "hidden": self._hidden,
            }
        )
        try:
            response = self.connection.recv()
        except (EOFError, OSError) as error:
            self.audit.server_errors += 1
            raise ContractViolation("inference server connection closed") from error
        roundtrip_ms = (time.perf_counter() - sent_at) * 1_000
        if response.get("kind") == "error":
            self.audit.server_errors += 1
            raise ContractViolation(f"inference server failed: {response.get('error')}")
        if (
            response.get("kind") != "response"
            or response.get("request_id") != remote_request_id
            or response.get("server_id") != self.server_id
        ):
            self.audit.invalid_responses += 1
            raise ContractViolation("inference response identity differs")
        hidden = response.get("hidden")
        if (
            not isinstance(hidden, list)
            or len(hidden) != self.hidden_size
            or any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                for value in hidden
            )
        ):
            self.audit.invalid_responses += 1
            raise ContractViolation("inference response hidden state is invalid")
        self._hidden = [float(value) for value in hidden]
        builder = CompoundActionBuilder(request)
        steps = response.get("steps")
        if not isinstance(steps, list):
            self.audit.invalid_responses += 1
            raise ContractViolation("inference response steps are missing")
        selected = 0
        try:
            for step in steps:
                if not isinstance(step, Mapping):
                    raise ContractViolation("inference response step is invalid")
                probabilities = step.get("probabilities")
                if not isinstance(probabilities, list):
                    raise ContractViolation("inference response probabilities are missing")
                probability_kwargs = {PROBABILITY_ARGUMENT: probabilities}
                if step.get("kind") == "choose":
                    index = step.get("index")
                    if isinstance(index, bool) or not isinstance(index, int):
                        raise ContractViolation("inference response option index is invalid")
                    builder.choose(index, **probability_kwargs)
                    selected += 1
                    self.audit.selected_steps += 1
                elif step.get("kind") == "stop":
                    builder.stop(**probability_kwargs)
                    self.audit.stop_steps += 1
                else:
                    raise ContractViolation("inference response step kind differs")
        except ContractViolation:
            self.audit.invalid_responses += 1
            raise
        batch_size = response.get("batch_size")
        server_ms = response.get("server_ms")
        if (
            isinstance(batch_size, bool)
            or not isinstance(batch_size, int)
            or batch_size <= 0
            or isinstance(server_ms, bool)
            or not isinstance(server_ms, (int, float))
            or not math.isfinite(float(server_ms))
            or float(server_ms) < 0
        ):
            self.audit.invalid_responses += 1
            raise ContractViolation("inference response timing or batch size is invalid")
        allocated_ms = float(server_ms) / batch_size
        self.audit.record_timing(roundtrip_ms, allocated_ms, batch_size)
        self.audit.choose_calls += 1
        self.audit.meaningful_calls += int(not request.has_only_one_outcome)
        self.audit.forced_calls += int(request.has_only_one_outcome)
        self.audit.max_options = max(self.audit.max_options, len(request.options))
        self.audit.max_selected = max(self.audit.max_selected, selected)
        try:
            return validate_compound_action(request, builder.build())
        except ContractViolation:
            self.audit.invalid_responses += 1
            raise


def decode_batched_actions(
    model: PTCGPolicyV1,
    batch: Any,
    output: Any,
    requests: Sequence[SelectionRequestV1],
) -> list[dict[str, Any]]:
    responses: list[dict[str, Any]] = []
    for item_index, request in enumerate(requests):
        start = int(output.option_offsets[item_index])
        end = int(output.option_offsets[item_index + 1])
        options = output.option_embeddings[start:end]
        available = batch.option_available[start:end].clone()
        builder = CompoundActionBuilder(request)
        prefix = model.decoder_initial(output.hidden[item_index])
        steps: list[dict[str, Any]] = []
        while not builder.complete:
            logits = model.decoder_logits(prefix, options, available, builder.can_stop)
            if torch.isnan(logits).any() or torch.isposinf(logits).any():
                raise ContractViolation("batched decoder emitted NaN or positive infinity")
            probabilities = torch.softmax(logits.double(), dim=0)
            values = probabilities.detach().cpu().tolist()
            if (
                any(not math.isfinite(value) or value < 0 for value in values)
                or not math.isclose(sum(values), 1.0, rel_tol=0, abs_tol=1e-12)
            ):
                raise ContractViolation("batched decoder distribution is invalid")
            choice = int(torch.argmax(probabilities).item())
            probability_kwargs = {PROBABILITY_ARGUMENT: values}
            if choice == len(request.options):
                builder.stop(**probability_kwargs)
                steps.append({"kind": "stop", "probabilities": values})
            else:
                builder.choose(choice, **probability_kwargs)
                available[choice] = False
                prefix = model.decoder_advance(prefix, options[choice])
                steps.append(
                    {"kind": "choose", "index": choice, "probabilities": values}
                )
        validate_compound_action(request, builder.build())
        hidden = output.hidden[item_index].detach().cpu()
        if not torch.isfinite(hidden).all():
            raise ContractViolation("batched model emitted nonfinite recurrent state")
        responses.append({"steps": steps, "hidden": hidden.tolist()})
    return responses


def execute_inference_batch(
    model: PTCGPolicyV1,
    messages: Sequence[Mapping[str, Any]],
    device: torch.device,
) -> list[dict[str, Any]]:
    if not messages:
        raise ReliabilityError("inference batch must not be empty")
    projections: list[ProjectedDecisionV1] = []
    requests: list[SelectionRequestV1] = []
    hidden_rows: list[list[float]] = []
    for message in messages:
        projection = message.get("projection")
        request = message.get("request")
        hidden = message.get("hidden")
        if not isinstance(projection, ProjectedDecisionV1):
            raise ReliabilityError("inference message projection type differs")
        if not isinstance(request, SelectionRequestV1):
            raise ReliabilityError("inference message request type differs")
        if projection.transport.request_id != request.request_id:
            raise ReliabilityError("inference projection/request identity differs")
        projections.append(projection)
        requests.append(request)
        if hidden is None:
            hidden_rows.append([0.0] * model.config.public_hidden)
        elif (
            isinstance(hidden, list)
            and len(hidden) == model.config.public_hidden
            and all(
                not isinstance(value, bool)
                and isinstance(value, (int, float))
                and math.isfinite(float(value))
                for value in hidden
            )
        ):
            hidden_rows.append([float(value) for value in hidden])
        else:
            raise ReliabilityError("inference message hidden state is invalid")
    batch = collate_projected(tuple(projections), device=device)
    hidden_tensor = torch.tensor(hidden_rows, dtype=torch.float32, device=device)
    with torch.inference_mode():
        output = model(batch, hidden_tensor)
        if not torch.isfinite(output.option_logits).all() or not torch.isfinite(
            output.values
        ).all():
            raise ContractViolation("batched model emitted nonfinite actor/value output")
        return decode_batched_actions(model, batch, output, requests)


def game_record(
    result: EpisodeResult,
    policy_audits: Mapping[int, PolicyAuditV1],
    ledger: AuditedRecurrentLedgerV1,
    worker_id: int,
    server_id: int,
    game_index: int,
) -> dict[str, Any]:
    return {
        "schema_version": RELIABILITY_SCHEMA_VERSION,
        "record_id": f"{RELIABILITY_RECORD_ID}-game-{game_index:05d}",
        "game_index": game_index,
        "worker_id": worker_id,
        "server_id": server_id,
        "summary": asdict(result.summary),
        "policy_audits": {
            str(player): asdict(policy_audits[player]) for player in (0, 1)
        },
        "ledger": ledger.audit_record(),
        "transition_count": len(result.transitions),
        "action_transition_count": sum(
            transition.action is not None for transition in result.transitions
        ),
        "terminal_transition_count": sum(
            transition.terminal_result is not None for transition in result.transitions
        ),
    }


def validate_game_record(record: Mapping[str, Any]) -> list[str]:
    failures: list[str] = []
    summary = record.get("summary")
    ledger = record.get("ledger")
    policy_audits = record.get("policy_audits")
    if not isinstance(summary, Mapping):
        return ["summary missing"]
    if not isinstance(ledger, Mapping):
        return ["ledger missing"]
    if not isinstance(policy_audits, Mapping) or set(policy_audits) != {"0", "1"}:
        return ["policy audits missing"]
    if summary.get("terminal_result") is None:
        failures.append("game did not reach terminal result")
    if summary.get("failure_kind") is not None:
        failures.append(f"game failure: {summary.get('failure_kind')}")
    for field_name in ZERO_TOLERANCE_SUMMARY_FIELDS:
        if summary.get(field_name) != 0:
            failures.append(f"summary {field_name} is nonzero")
    for field_name in ZERO_TOLERANCE_LEDGER_FIELDS:
        if ledger.get(field_name) != 0:
            failures.append(f"ledger {field_name} is nonzero")
    if ledger.get("active_keys_after") != []:
        failures.append("recurrent ledger retains active keys")
    reset_events = ledger.get("reset_events")
    if not isinstance(reset_events, list) or len(reset_events) != 4:
        failures.append("recurrent ledger reset event count differs")
    else:
        reasons = [
            event[1]
            for event in reset_events
            if isinstance(event, (list, tuple)) and len(event) == 2
        ]
        if reasons.count("start") != 2 or reasons.count("terminal") != 2:
            failures.append("recurrent ledger start/terminal reset pattern differs")
    choose_calls = 0
    allocated_ms = 0.0
    roundtrip_ms = 0.0
    for player in ("0", "1"):
        audit = policy_audits[player]
        if not isinstance(audit, Mapping):
            failures.append(f"policy audit {player} is invalid")
            continue
        for field_name in ZERO_TOLERANCE_POLICY_FIELDS:
            if audit.get(field_name) != 0:
                failures.append(f"policy {player} {field_name} is nonzero")
        if audit.get("reset_start") != 1 or audit.get("reset_terminal") != 1:
            failures.append(f"policy {player} reset pattern differs")
        choose_calls += int(audit.get("choose_calls", -1))
        allocated_ms += float(audit.get("allocated_inference_ms_total", math.nan))
        roundtrip_ms += float(audit.get("roundtrip_ms_total", math.nan))
    engine_requests = summary.get("engine_requests")
    if choose_calls != engine_requests:
        failures.append("policy choose-call count differs from engine requests")
    if record.get("action_transition_count") != engine_requests:
        failures.append("action transition count differs from engine requests")
    if record.get("terminal_transition_count") != 1:
        failures.append("terminal transition count differs")
    if record.get("transition_count") != engine_requests + 1:
        failures.append("total transition count differs")
    if not math.isfinite(allocated_ms) or allocated_ms < 0:
        failures.append("allocated inference total is invalid")
    if not math.isfinite(roundtrip_ms) or roundtrip_ms < 0:
        failures.append("round-trip inference total is invalid")
    return failures


def percentile(values: Sequence[float], fraction: float) -> float | None:
    if not values:
        return None
    if not 0 <= fraction <= 1:
        raise ValueError("percentile fraction must be between zero and one")
    ordered = sorted(float(value) for value in values)
    index = min(len(ordered) - 1, int(fraction * (len(ordered) - 1)))
    return ordered[index]


def canonical_json_line(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )


def read_game_records(path: Path) -> tuple[list[dict[str, Any]], str, int]:
    digest = hashlib.sha256()
    records: list[dict[str, Any]] = []
    total_bytes = 0
    with path.open("rb") as handle:
        for line_number, raw in enumerate(handle, start=1):
            total_bytes += len(raw)
            digest.update(raw)
            try:
                value = json.loads(raw.decode("utf-8"))
            except (UnicodeError, json.JSONDecodeError) as error:
                raise ReliabilityError(
                    f"game record line {line_number} is not valid UTF-8 JSON"
                ) from error
            if not isinstance(value, dict):
                raise ReliabilityError(f"game record line {line_number} is not an object")
            if canonical_json_line(value) != raw:
                raise ReliabilityError(f"game record line {line_number} is not canonical JSON")
            records.append(value)
    return records, digest.hexdigest(), total_bytes


def recalculate_reliability(
    records: Sequence[Mapping[str, Any]],
    expected_games: int,
    process_failures: Sequence[str] = (),
    server_failures: Sequence[str] = (),
) -> dict[str, Any]:
    if expected_games <= 0:
        raise ValueError("expected game count must be positive")
    indices = [record.get("game_index") for record in records]
    integer_indices = [
        value for value in indices if isinstance(value, int) and not isinstance(value, bool)
    ]
    duplicate_indices = sorted(
        value for value, count in Counter(integer_indices).items() if count > 1
    )
    expected_indices = set(range(expected_games))
    observed_indices = set(integer_indices)
    missing_indices = sorted(expected_indices - observed_indices)
    unexpected_indices = sorted(observed_indices - expected_indices)
    per_game_failures = {
        str(record.get("game_index")): validate_game_record(record)
        for record in records
    }
    failing_games = {
        index: failures for index, failures in per_game_failures.items() if failures
    }
    summaries = [record["summary"] for record in records if isinstance(record.get("summary"), Mapping)]
    audits = [
        audit
        for record in records
        for audit in (
            record.get("policy_audits", {}).values()
            if isinstance(record.get("policy_audits"), Mapping)
            else []
        )
        if isinstance(audit, Mapping)
    ]
    allocated_totals = [
        sum(
            float(audit.get("allocated_inference_ms_total", math.nan))
            for audit in record.get("policy_audits", {}).values()
        )
        for record in records
        if isinstance(record.get("policy_audits"), Mapping)
    ]
    roundtrip_totals = [
        sum(
            float(audit.get("roundtrip_ms_total", math.nan))
            for audit in record.get("policy_audits", {}).values()
        )
        for record in records
        if isinstance(record.get("policy_audits"), Mapping)
    ]
    summary_zero_totals = {
        field_name: sum(int(summary.get(field_name, 0)) for summary in summaries)
        for field_name in ZERO_TOLERANCE_SUMMARY_FIELDS
    }
    ledger_zero_totals = {
        field_name: sum(int(record.get("ledger", {}).get(field_name, 0)) for record in records)
        for field_name in ZERO_TOLERANCE_LEDGER_FIELDS
    }
    policy_zero_totals = {
        field_name: sum(int(audit.get(field_name, 0)) for audit in audits)
        for field_name in ZERO_TOLERANCE_POLICY_FIELDS
    }
    complete = (
        len(records) == expected_games
        and not duplicate_indices
        and not missing_indices
        and not unexpected_indices
    )
    allocated_p99 = percentile(allocated_totals, 0.99)
    roundtrip_p99 = percentile(roundtrip_totals, 0.99)
    inference_limit_pass = allocated_p99 is not None and allocated_p99 <= 120_000.0
    zero_tolerance = (
        all(value == 0 for value in summary_zero_totals.values())
        and all(value == 0 for value in ledger_zero_totals.values())
        and all(value == 0 for value in policy_zero_totals.values())
        and not failing_games
        and not process_failures
        and not server_failures
    )
    return {
        "schema_version": RELIABILITY_SCHEMA_VERSION,
        "record_id": f"{RELIABILITY_RECORD_ID}-review",
        "status": "PASS" if complete and zero_tolerance and inference_limit_pass else "FAIL",
        "expected_games": expected_games,
        "observed_games": len(records),
        "complete_game_index_set": complete,
        "duplicate_indices": duplicate_indices,
        "missing_indices": missing_indices[:100],
        "missing_index_count": len(missing_indices),
        "unexpected_indices": unexpected_indices[:100],
        "unexpected_index_count": len(unexpected_indices),
        "failing_games": dict(list(failing_games.items())[:100]),
        "failing_game_count": len(failing_games),
        "process_failures": list(process_failures),
        "server_failures": list(server_failures),
        "zero_tolerance": {
            "summary": summary_zero_totals,
            "ledger": ledger_zero_totals,
            "policy": policy_zero_totals,
        },
        "engine_requests": sum(int(summary.get("engine_requests", 0)) for summary in summaries),
        "meaningful_choices": sum(int(summary.get("meaningful_choices", 0)) for summary in summaries),
        "forced_requests": sum(int(summary.get("forced_requests", 0)) for summary in summaries),
        "multi_select_requests": sum(int(summary.get("multi_select_requests", 0)) for summary in summaries),
        "max_observed_options": max(
            (int(summary.get("max_observed_options", 0)) for summary in summaries),
            default=0,
        ),
        "max_observed_select_count": max(
            (int(summary.get("max_observed_select_count", 0)) for summary in summaries),
            default=0,
        ),
        "allocated_inference_ms_per_game": {
            "p50": percentile(allocated_totals, 0.50),
            "p95": percentile(allocated_totals, 0.95),
            "p99": allocated_p99,
            "max": max(allocated_totals, default=None),
        },
        "roundtrip_ms_per_game": {
            "p50": percentile(roundtrip_totals, 0.50),
            "p95": percentile(roundtrip_totals, 0.95),
            "p99": roundtrip_p99,
            "max": max(roundtrip_totals, default=None),
        },
        "projected_cpu_host_inference_limit": {
            "p99_limit_ms": 120_000.0,
            "observed_allocated_p99_ms": allocated_p99,
            "pass": inference_limit_pass,
        },
    }
