#!/usr/bin/env bash
set -Eeuo pipefail

# Runs only the four repetitive G1R acceptance jobs. It never trains, downloads,
# submits, pushes, or mutates private assets.

repo=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$repo"

usage() {
  cat <<'EOF'
usage: scripts/g1r_run_long_acceptance.sh --accept-proposed-thresholds [--run-dir DIR]
       scripts/g1r_run_long_acceptance.sh --check-only

The approval flag confirms the preregistered values in
docs/G1R_THRESHOLD_DECISION_PROPOSAL.md. The runner is resumable: invoke the
same command again after an interruption. Asset paths may be overridden with
PTCG_ENGINE_ROOT, PTCG_BUILT_ENGINE_ROOT, PTCG_CARD_DATA,
PTCG_DEFAULT_DECK, and PTCG_BASELINES.
EOF
}

approved=false
check_only=false
run_root=${G1R_LONG_RUN_DIR:-runs/g1r-user-long-acceptance}
while (($#)); do
  case "$1" in
    --accept-proposed-thresholds) approved=true ;;
    --check-only) check_only=true ;;
    --run-dir)
      [[ $# -ge 2 ]] || { usage >&2; exit 2; }
      run_root=$2
      shift
      ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

if [[ $approved != true && $check_only != true ]]; then
  echo "Refusing to run without explicit threshold approval." >&2
  echo "Review docs/G1R_THRESHOLD_DECISION_PROPOSAL.md, then pass --accept-proposed-thresholds." >&2
  exit 2
fi

python="$repo/.venv/bin/python"
ptcg="$repo/.venv/bin/ptcg"
journal_runner="$repo/scripts/run_evidence_command.py"
engine_root=${PTCG_ENGINE_ROOT:-$repo/private/assets/official/sample_submission/sample_submission}
built_engine_root=${PTCG_BUILT_ENGINE_ROOT:-$repo/private/build/july17-source}
card_data=${PTCG_CARD_DATA:-$repo/private/assets/official/EN_Card_Data.csv}
default_deck=${PTCG_DEFAULT_DECK:-$repo/private/assets/official/sample_submission/sample_submission/deck.csv}
baselines=${PTCG_BASELINES:-$repo/private/baselines}

[[ -x $python && -x $ptcg ]] || {
  echo "Missing project environment; run the declared bootstrap first." >&2
  exit 2
}
for required in \
  "$engine_root/cg/libcg.so" "$built_engine_root/cg/libcg.so" "$card_data" \
  "$default_deck" "$baselines/dragapult-ex/deck.csv" "$baselines/iono/deck.csv" \
  "$baselines/mega-abomasnow-ex/deck.csv" "$baselines/mega-lucario-ex/deck.csv"; do
  [[ -f $required ]] || { echo "Missing required local asset: $required" >&2; exit 2; }
done

if [[ $check_only == true ]]; then
  "$ptcg" g1 engine-compare --help >/dev/null
  "$ptcg" g1 arena --help >/dev/null
  "$ptcg" g1 benchmark --help >/dev/null
  "$ptcg" g1 rss-soak --help >/dev/null
  echo "G1R long-run preflight passed; no acceptance work was started."
  exit 0
fi

mkdir -p "$run_root/journal" "$run_root/completed"
run_root=$(cd "$run_root" && pwd)
journal="$run_root/journal"
current_pid=""

stop_current() {
  trap - INT TERM
  if [[ -n $current_pid ]] && kill -0 "$current_pid" 2>/dev/null; then
    kill -TERM -- "-$current_pid" 2>/dev/null || true
    wait "$current_pid" 2>/dev/null || true
  fi
  echo "Interrupted. Re-run the same command to resume arena/soak." >&2
  exit 130
}
trap stop_current INT TERM

journal_command() {
  "$python" "$journal_runner" "$journal" -- "$@"
}

validate_and_mark() {
  local name=$1 output=$2 marker=$3
  "$python" - "$name" "$output/run_manifest.json" "$marker" <<'PY'
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

name, manifest_name, marker_name = sys.argv[1:]
manifest = Path(manifest_name)
if not manifest.is_file():
    raise SystemExit(f"{name}: missing {manifest}")
payload = json.loads(manifest.read_text(encoding="utf-8"))
verdict = str(payload.get("internal_verdict", payload.get("status", ""))).upper()
if verdict not in {"PASS", "SUCCEEDED"}:
    raise SystemExit(f"{name}: manifest verdict is {verdict or 'MISSING'}")
receipt = {
    "schema_version": 1,
    "step": name,
    "completed_at_utc": datetime.now(timezone.utc).isoformat(),
    "manifest": os.path.relpath(manifest),
    "manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
    "verdict": verdict,
}
marker = Path(marker_name)
marker.open("x", encoding="utf-8").write(
    json.dumps(receipt, indent=2, sort_keys=True) + "\n"
)
PY
}

run_step() {
  local name=$1 output=$2 resumable=$3
  shift 3
  local marker="$run_root/completed/$name.json"
  local -a command=("$@")
  if [[ -f $marker ]]; then
    echo "[$name] already complete; skipping."
    return
  fi
  if [[ -e $output ]]; then
    if [[ $resumable == true ]]; then
      command+=(--resume)
      echo "[$name] resuming existing evidence."
    else
      local original_output=$output attempt=2 index
      while [[ -e ${original_output}-attempt-${attempt} ]]; do ((attempt++)); done
      output=${original_output}-attempt-${attempt}
      for index in "${!command[@]}"; do
        [[ ${command[$index]} == "$original_output" ]] && command[$index]=$output
      done
      echo "[$name] preserving the failed attempt and retrying in $output."
    fi
  fi

  echo "[$name] starting at $(date -u +%FT%TZ)."
  setsid "$python" "$journal_runner" "$journal" -- "${command[@]}" &
  current_pid=$!
  while kill -0 "$current_pid" 2>/dev/null; do
    sleep 60 & wait $! || true
    kill -0 "$current_pid" 2>/dev/null && echo "[$name] still running at $(date -u +%FT%TZ)."
  done
  wait "$current_pid"
  current_pid=""
  validate_and_mark "$name" "$output" "$marker"
  echo "[$name] complete."
}

write_final_receipt() {
  local exit_code=$1 recalc_exit=$2 rebuild_exit=$3 doctor_exit=$4
  "$python" - "$run_root" "$exit_code" "$repo/reports/gates/g1r.json" \
    "$recalc_exit" "$rebuild_exit" "$doctor_exit" <<'PY'
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

root, exit_code, gate_name = Path(sys.argv[1]), int(sys.argv[2]), Path(sys.argv[3])
recalc_exit, rebuild_exit, doctor_exit = map(int, sys.argv[4:7])
markers = {}
for path in sorted((root / "completed").glob("*.json")):
    markers[path.stem] = json.loads(path.read_text(encoding="utf-8"))
gate = json.loads(gate_name.read_text(encoding="utf-8")) if gate_name.is_file() else {}
journal = root / "journal" / "command-journal.jsonl"
payload = {
    "schema_version": 1,
    "created_at_utc": datetime.now(timezone.utc).isoformat(),
    "runner_exit_code": exit_code,
    "completed_steps": markers,
    "gate": {"status": gate.get("status"), "decision": gate.get("decision"),
             "blockers": gate.get("blockers", [])},
    "journal": {"entries": sum(1 for _ in journal.open(encoding="utf-8")) if journal.is_file() else 0,
                "sha256": hashlib.sha256(journal.read_bytes()).hexdigest() if journal.is_file() else None},
    "projection_exit_codes": {"recalculate_gate": recalc_exit,
                              "dashboard_rebuild": rebuild_exit,
                              "dashboard_doctor": doctor_exit},
    "dashboard_rebuilt": rebuild_exit == 0 and doctor_exit == 0,
}
receipt = root / f"completion-receipt-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.json"
receipt.open("x", encoding="utf-8").write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
print(f"Completion receipt: {receipt}")
print(f"G1R projection: {payload['gate']['status']} / {payload['gate']['decision']}")
PY
}

finalize() {
  local exit_code=$?
  local recalc_exit rebuild_exit doctor_exit final_exit
  trap - EXIT
  set +e
  echo "Refreshing independent gate verdict and dashboard..."
  journal_command "$ptcg" g1 recalculate-gate
  recalc_exit=$?
  journal_command "$ptcg" dashboard rebuild
  rebuild_exit=$?
  journal_command "$ptcg" dashboard doctor
  doctor_exit=$?
  final_exit=$exit_code
  if [[ $final_exit -eq 0 && ($recalc_exit -ne 0 || $rebuild_exit -ne 0 || $doctor_exit -ne 0) ]]; then
    final_exit=1
  fi
  write_final_receipt "$final_exit" "$recalc_exit" "$rebuild_exit" "$doctor_exit"
  echo "Dashboard data is current. Review G1R there, then provide the completion receipt for engineering review."
  exit "$final_exit"
}
trap finalize EXIT

compare_output="$run_root/engine-compare"
arena_output="$run_root/arena"
benchmark_output="$run_root/benchmark"
soak_output="$run_root/rss-soak"

run_step engine-compare "$compare_output" false \
  "$ptcg" g1 engine-compare \
  --shipped-engine-root "$engine_root" --built-engine-root "$built_engine_root" \
  --card-data "$card_data" --default-deck "$default_deck" \
  --private-baselines "$baselines" --games-per-library 1000 --workers 8 \
  --ks-max 0.10 --mean-relative-max 0.10 --mean-se-floor 2 \
  --output "$compare_output"

run_step benchmark "$benchmark_output" false \
  "$ptcg" g1 benchmark \
  --engine-root "$engine_root" --card-data "$card_data" \
  --default-deck "$default_deck" --private-baselines "$baselines" \
  --workers 1,2,4,8 --games-per-point 200 --output "$benchmark_output"

run_step arena "$arena_output" true \
  "$ptcg" g1 arena \
  --engine-root "$engine_root" --card-data "$card_data" \
  --default-deck "$default_deck" --private-baselines "$baselines" \
  --policies random,first,rule:dragapult-ex,rule:iono,rule:mega-abomasnow-ex,rule:mega-lucario-ex \
  --games-per-cell 280 --workers 8 --wall-seconds 7200 \
  --max-evidence-bytes 1073741824 --output "$arena_output"

run_step rss-soak "$soak_output" true \
  "$ptcg" g1 rss-soak \
  --engine-root "$engine_root" --card-data "$card_data" \
  --default-deck "$default_deck" --private-baselines "$baselines" \
  --policy first --workers 4 --duration-seconds 21600 --sample-seconds 60 \
  --warmup-seconds 1800 --peak-bytes-per-worker 2147483648 \
  --slope-upper-mib-per-hour 1.0 --force-restart-after-seconds 300 \
  --max-evidence-bytes 1073741824 --output "$soak_output"
