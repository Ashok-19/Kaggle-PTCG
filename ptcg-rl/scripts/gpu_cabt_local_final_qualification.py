# ruff: noqa: E701,E702
from __future__ import annotations

import argparse
import gc
import json
import math
import os
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

import numpy as np

from ptcg_rl.gpu_cabt.device_runtime import GpuCabtRuntime, default_official_dir, repo_root
from ptcg_rl.gpu_cabt.nvrtc import load_cupy_module
from ptcg_rl.gpu_cabt.rule_static import extract_rule_tables

LUCARIO = Path(".chatgpt/tmp/today-lucario-variants/lucario-modern-v1/deck.csv")
OPPONENTS = (
    ("dragapult", Path(".chatgpt/tmp/aura-upgrade/arena-agents/dragapult-ex/deck.csv")),
    ("alakazam", Path(".chatgpt/tmp/grim-source-oracle/arena-agents/alakazam-v9/deck.csv")),
    ("lopunny", Path(".chatgpt/tmp/grim-source-oracle/arena-agents/lopunny-v9/deck.csv")),
    ("iono", Path(".chatgpt/tmp/aura-upgrade/arena-agents/iono/deck.csv")),
    ("abomasnow", Path(".chatgpt/tmp/aura-upgrade/arena-agents/mega-abomasnow-ex/deck.csv")),
    ("grim", Path(".chatgpt/tmp/grim-lana-current-eval-agents/grim-v15-control/deck.csv")),
)
DEFAULT_ENV_COUNTS = (384, 768, 1536, 3072, 4608, 6000)
SELECTOR_SOURCE = r'''
typedef unsigned char u8; typedef unsigned int u32; typedef unsigned long long u64; typedef int i32;
extern "C" __global__ void first_min(
 const u8* results,const u8* select_types,const i32* globals,i32 global_width,
 const u32* policy_status,const u32* event_status,u8* present,i32* counts,
 i32* selected,i32 stride,u64* decisions,u32* errors,i32 n) {
 i32 i=(i32)(blockDim.x*blockIdx.x+threadIdx.x); if(i>=n)return;
 if(results[i]!=0){present[i]=0;counts[i]=0;return;}
 if(select_types[i]==0){errors[i]|=1u;present[i]=0;counts[i]=0;return;}
 if(policy_status[i]!=0)errors[i]|=2u; if(event_status[i]!=0)errors[i]|=4u;
 const i32* row=globals+(long long)i*global_width; i32 mn=row[8],mx=row[9],opts=row[22];
 if(mn<0||mx<mn||mn>opts||opts<0||opts>stride){errors[i]|=8u;present[i]=0;counts[i]=0;return;}
 present[i]=1;counts[i]=mn;for(i32 j=0;j<mn;++j)selected[(long long)i*stride+j]=j;decisions[i]+=1ull;
}
'''


def load_decks(root: Path) -> tuple[list[str], list[np.ndarray]]:
    names = ["lucario"]
    paths = [LUCARIO]
    for name, path in OPPONENTS:
        names.append(name)
        paths.append(path)
    decks = [np.loadtxt(root / path, dtype=np.int32) for path in paths]
    for path, deck in zip(paths, decks, strict=True):
        if deck.shape != (60,):
            raise ValueError(f"{path} is not an exact 60-card deck: {deck.shape}")
    return names, decks


def matchups(decks: list[np.ndarray], count: int) -> np.ndarray:
    base = []
    for opp in decks[1:]:
        base.extend((np.stack((decks[0], opp)), np.stack((opp, decks[0]))))
    return np.stack((base * math.ceil(count / 12))[:count]).astype(np.int32, copy=False)


def pct(values: list[float]) -> dict[str, float]:
    a = np.asarray(values, dtype=np.float64)
    return {"p50": float(np.percentile(a, 50)), "p95": float(np.percentile(a, 95)), "p99": float(np.percentile(a, 99))}


class SmiSampler:
    def __init__(self) -> None:
        self.rows: list[tuple[float, float, float, float]] = []
        self.proc: subprocess.Popen[str] | None = None
        self.thread: threading.Thread | None = None

    def start(self) -> None:
        self.proc = subprocess.Popen([
            "nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total,power.draw",
            "--format=csv,noheader,nounits", "-lms", "100",
        ], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1)

        def read() -> None:
            assert self.proc is not None and self.proc.stdout is not None
            for line in self.proc.stdout:
                try:
                    values = tuple(float(x.strip()) for x in line.split(","))
                except ValueError:
                    continue
                if len(values) == 4:
                    self.rows.append(values)

        self.thread = threading.Thread(target=read, daemon=True)
        self.thread.start()

    def stop(self) -> dict[str, float | int | None]:
        if self.proc is not None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.proc.kill(); self.proc.wait(timeout=3)
        if self.thread is not None:
            self.thread.join(timeout=3)
        if not self.rows:
            return {"samples": 0, "utilization_mean_pct": None, "utilization_p95_pct": None, "memory_used_max_mib": None, "memory_total_mib": None, "power_mean_w": None}
        a = np.asarray(self.rows, dtype=np.float64)
        return {"samples": len(self.rows), "utilization_mean_pct": float(a[:, 0].mean()), "utilization_p95_pct": float(np.percentile(a[:, 0], 95)), "memory_used_max_mib": float(a[:, 1].max()), "memory_total_mib": float(a[:, 2].max()), "power_mean_w": float(a[:, 3].mean())}


def run_sample(runtime: GpuCabtRuntime, decks_gpu: Any, selector: Any, *, seed: int, check_interval: int, telemetry: bool) -> dict[str, Any]:
    cp, n, stride = runtime.cp, runtime.env_count, runtime.abi.selected_capacity
    present = cp.empty(n, dtype=cp.uint8); counts = cp.empty(n, dtype=cp.int32)
    selected = cp.empty((n, stride), dtype=cp.int32); decisions = cp.zeros(n, dtype=cp.uint64); selector_errors = cp.zeros(n, dtype=cp.uint32)
    runtime.reset(decks_gpu, seed=seed ^ 0x5A5A5A5A); runtime.status(); runtime.project_policy(); runtime.project_events(acknowledge=False); runtime.synchronize()
    sampler = SmiSampler() if telemetry else None
    if sampler: sampler.start()
    terminal_ms = np.full(n, np.nan); boundaries = 0; failure = None; start = time.perf_counter()
    runtime.reset(decks_gpu, seed=seed)
    try:
        while boundaries < 5000:
            for _ in range(min(check_interval, 5000 - boundaries)):
                status = runtime.status(); events = runtime.project_events(acknowledge=True); projection = runtime.project_policy()
                selector((runtime.blocks,), (runtime.threads,), (status.game_results, status.select_types, projection.globals, np.int32(runtime.abi.global_width), projection.status, events.status, present, counts, selected, np.int32(stride), decisions, selector_errors, np.int32(n)))
                runtime.step(present, counts, selected); boundaries += 1
            status = runtime.status(); runtime.synchronize(); elapsed_ms = (time.perf_counter() - start) * 1000
            errs, results, sel_errs = status.error_flags.get(), status.game_results.get(), selector_errors.get()
            terminal_ms[(results != 0) & np.isnan(terminal_ms)] = elapsed_ms
            if np.any(errs) or np.any(sel_errs):
                failure = {"kind": "runtime-or-projection", "runtime_error_envs": int(np.count_nonzero(errs)), "selector_error_envs": int(np.count_nonzero(sel_errs)), "runtime_error_or": int(np.bitwise_or.reduce(errs, initial=0)), "selector_error_or": int(np.bitwise_or.reduce(sel_errs, initial=0))}; break
            if np.all(results != 0):
                final_events = runtime.project_events(acknowledge=True); runtime.synchronize()
                ev = final_events.status.get()
                if np.any(ev): failure = {"kind": "terminal-event", "event_error_envs": int(np.count_nonzero(ev))}
                break
        else:
            failure = {"kind": "boundary-limit"}
    finally:
        runtime.synchronize(); seconds = time.perf_counter() - start; telemetry_row = sampler.stop() if sampler else None
    status = runtime.status(); runtime.synchronize(); results = status.game_results.get(); errs = status.error_flags.get(); sel_errs = selector_errors.get(); d = int(decisions.get().sum())
    all_terminal = bool(np.all(results != 0)); zero_errors = bool(np.all(errs == 0) and np.all(sel_errs == 0))
    if not all_terminal and failure is None: failure = {"kind": "incomplete"}
    lat = terminal_ms[np.isfinite(terminal_ms)].tolist()
    return {"status": "PASS" if failure is None and all_terminal and zero_errors else "FAIL", "games": n, "decisions": d, "seconds": seconds, "games_per_second": n / seconds, "decisions_per_second": d / seconds, "boundaries": boundaries, "all_terminal": all_terminal, "zero_errors": zero_errors, "failure": failure, "game_latency_ms": pct(lat) if lat else {"p50": 0.0, "p95": 0.0, "p99": 0.0}, "max_turn": int(status.turns.get().max()), "telemetry": telemetry_row}


def gpu_point(cp: Any, rules: Any, selector: Any, decks: list[np.ndarray], *, env_count: int, stack_bytes: int, samples: int, seed: int, check_interval: int, telemetry: bool) -> dict[str, Any]:
    runtime = GpuCabtRuntime(env_count, cupy_module=cp, rule_tables=rules, stack_size_bytes=stack_bytes); decks_gpu = cp.asarray(matchups(decks, env_count))
    runtime.reset(decks_gpu, seed=seed ^ 0x11111111); runtime.project_events(acknowledge=False); runtime.synchronize(); free_b, total_b = cp.cuda.runtime.memGetInfo(); memory_b = runtime.memory_bytes()
    rows = []
    try:
        for sample in range(samples):
            row = run_sample(runtime, decks_gpu, selector, seed=seed + sample * 1000003, check_interval=check_interval, telemetry=telemetry); rows.append(row)
            if row["status"] != "PASS": break
    finally:
        del runtime, decks_gpu; gc.collect(); cp.get_default_memory_pool().free_all_blocks()
    good = [r for r in rows if r["status"] == "PASS"]
    if not good:
        return {"status": "FAIL", "env_count": env_count, "stack_bytes": stack_bytes, "runtime_memory_bytes": memory_b, "free_vram_after_allocation_bytes": int(free_b), "total_vram_bytes": int(total_b), "samples": rows}
    games = sum(int(r["games"]) for r in good); decisions = sum(int(r["decisions"]) for r in good); seconds = sum(float(r["seconds"]) for r in good)
    return {"status": "PASS" if len(good) == samples else "FAIL", "env_count": env_count, "stack_bytes": stack_bytes, "runtime_memory_bytes": memory_b, "runtime_memory_bytes_per_env": memory_b / env_count, "free_vram_after_allocation_bytes": int(free_b), "total_vram_bytes": int(total_b), "aggregate_games": games, "aggregate_decisions": decisions, "aggregate_seconds": seconds, "games_per_second": games / seconds, "decisions_per_second": decisions / seconds, "sample_seconds": [float(r["seconds"]) for r in good], "sample_seconds_percentiles": pct([float(r["seconds"]) for r in good]), "samples": rows}


def native_benchmark(root: Path, decks: list[np.ndarray], repeats: int) -> dict[str, Any]:
    official = root / "private/assets/official/ptcg_engine/ptcgProgram 22"; source = root / "scripts/gpu_cabt_native_final_benchmark.cpp"; payload = " ".join(str(int(c)) for deck in decks for c in deck) + "\n"
    with tempfile.TemporaryDirectory(prefix="gpu-cabt-native-final-") as tmp:
        exe = Path(tmp) / "benchmark"; t = time.perf_counter(); subprocess.run(["g++", "-std=c++23", "-O3", "-DNDEBUG", "-I", str(official), str(source), "-o", str(exe)], check=True); compile_s = time.perf_counter() - t
        output = subprocess.check_output([str(exe), str(repeats)], input=payload.encode()).decode()
    rows = [json.loads(line) for line in output.splitlines() if line.strip()]
    if {r["mode"] for r in rows} != {"core", "public"}: raise RuntimeError(f"unexpected native output: {rows}")
    return {"compile_seconds_excluded": compile_s, "modes": rows}


def device_info(cp: Any) -> dict[str, Any]:
    p = cp.cuda.runtime.getDeviceProperties(0); name = p["name"].decode() if isinstance(p["name"], bytes) else str(p["name"])
    return {"name": name, "compute_capability": f"{int(p['major'])}.{int(p['minor'])}", "multiprocessors": int(p["multiProcessorCount"]), "total_global_memory_bytes": int(p["totalGlobalMem"])}


def main() -> None:
    ap = argparse.ArgumentParser(); ap.add_argument("--samples", type=int, default=1); ap.add_argument("--native-repeats", type=int, default=500); ap.add_argument("--stress-envs", type=int, default=6000); ap.add_argument("--stack-envs", type=int, default=768); ap.add_argument("--check-interval", type=int, default=16); ap.add_argument("--seed", type=int, default=20260814); ap.add_argument("--env-count", action="append", type=int); ap.add_argument("--output", type=Path, default=Path("reports/evaluations/gpu-cabt-final-local-qualification-v1.json")); args = ap.parse_args()
    if min(args.samples, args.native_repeats, args.stress_envs, args.stack_envs, args.check_interval) <= 0: ap.error("positive values required")
    configured_fast_compile = os.environ.get("GPU_CABT_NVRTC_FAST_COMPILE")
    if configured_fast_compile not in (None, "max"):
        raise RuntimeError("local final qualification requires GPU_CABT_NVRTC_FAST_COMPILE=max")
    os.environ["GPU_CABT_NVRTC_FAST_COMPILE"] = "max"
    import cupy as cp
    root = repo_root(); names, decks = load_decks(root); head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    t = time.perf_counter(); rules = extract_rule_tables(default_official_dir(), root); rule_s = time.perf_counter() - t
    t = time.perf_counter(); probe = GpuCabtRuntime(1, cupy_module=cp, rule_tables=rules, stack_size_bytes=16384); probe.synchronize(); abi = probe.abi.__dict__; build_s = time.perf_counter() - t; del probe; gc.collect(); cp.get_default_memory_pool().free_all_blocks()
    selector = load_cupy_module(cp, SELECTOR_SOURCE, kernel_names=("first_min",)).get_function("first_min")
    native = native_benchmark(root, decks, args.native_repeats)
    stack = [gpu_point(cp, rules, selector, decks, env_count=args.stack_envs, stack_bytes=s, samples=1, seed=args.seed+s, check_interval=args.check_interval, telemetry=False) for s in (8192,16384)]
    stress = gpu_point(cp, rules, selector, decks, env_count=args.stress_envs, stack_bytes=16384, samples=1, seed=args.seed+7000000, check_interval=args.check_interval, telemetry=True)
    sweep = []
    for n in (tuple(args.env_count) if args.env_count else DEFAULT_ENV_COUNTS):
        try: row = gpu_point(cp, rules, selector, decks, env_count=n, stack_bytes=16384, samples=args.samples, seed=args.seed+n*17, check_interval=args.check_interval, telemetry=True)
        except cp.cuda.memory.OutOfMemoryError as exc:
            row = {"status": "OOM_CAPACITY", "env_count": n, "stack_bytes": 16384, "error": str(exc)}; gc.collect(); cp.get_default_memory_pool().free_all_blocks()
        sweep.append(row)
    passed_points = [r for r in sweep if r["status"] == "PASS"]
    if not passed_points: raise RuntimeError("no GPU sweep point passed")
    best_g = max(passed_points, key=lambda r: float(r["games_per_second"])); best_d = max(passed_points, key=lambda r: float(r["decisions_per_second"])); cpu_public = next(r for r in native["modes"] if r["mode"] == "public"); non_capacity = [r for r in sweep if r["status"] not in {"PASS","OOM_CAPACITY"}]
    stack_16k = next(r for r in stack if int(r["stack_bytes"]) == 16384)
    passed = stack_16k["status"] == "PASS" and stress["status"] == "PASS" and int(stress["env_count"]) >= 6000 and not non_capacity and int(cpu_public["failures"]) == 0
    report = {"record_id":"gpu-cabt-final-local-qualification-v1","status":"PASS" if passed else "FAIL","source_head":head,"device":device_info(cp),"compile_mode":"nvrtc-fast-compile-max-conservative-local","cubin_build_seconds_excluded_from_throughput":build_s,"rule_extraction_seconds_excluded_from_throughput":rule_s,"abi":abi,"deck_families":names,"workload":{"matchup_cells":12,"policy":"first selectMin legal option indices at every decision boundary","gpu_public_path":"status + public events acknowledge + public policy projection + device first-min selection + GPU game step","cpu_public_path":"official BattleData + official ToJsonApi every decision/terminal boundary + first-min selection","timing_includes":"reset/shuffle/setup/gameplay/terminal; excludes compilation, rule extraction, persistent runtime allocation","native_rng_note":"native deployment-mode deviceRand=true uses system entropy; trajectories are not causally paired to GPU Philox games","gpu_check_interval_boundaries":args.check_interval},"native_single_process":native,"stack_sweep":stack,"stress":stress,"gpu_sweep":sweep,"best_gpu_games_per_second":{"env_count":int(best_g["env_count"]),"games_per_second":float(best_g["games_per_second"]),"decisions_per_second":float(best_g["decisions_per_second"])},"best_gpu_decisions_per_second":{"env_count":int(best_d["env_count"]),"games_per_second":float(best_d["games_per_second"]),"decisions_per_second":float(best_d["decisions_per_second"])},"cpu_vs_gpu_public_speedup":{"games_per_second":float(best_g["games_per_second"])/float(cpu_public["games_per_second"]),"decisions_per_second":float(best_d["decisions_per_second"])/float(cpu_public["decisions_per_second"]),"cpu_baseline":"single-process official native CABT with ToJsonApi"},"local_compile_safety":{"fully_optimized_nvrtc_attempt":"FORBIDDEN_ON_THIS_HOST_AFTER_CONFIRMED_OOM","observed_oom_anon_rss_bytes_approx":13665058816,"host_ram_gib_approx":15,"reason":"Kernel OOM killer terminated fully optimized NVRTC compile; fast-compile=max preserves engine semantics and yields a conservative local throughput measurement."},"completion_checks":{"production_stack_16k_pass":stack_16k["status"]=="PASS","stress_at_least_6000_games_pass":stress["status"]=="PASS" and int(stress["env_count"])>=6000,"native_public_zero_failures":int(cpu_public["failures"])==0,"gpu_sweep_no_non_capacity_failures":not non_capacity}}
    output = root / args.output; output.parent.mkdir(parents=True, exist_ok=True); output.write_text(json.dumps(report, indent=2, sort_keys=True)+"\n", encoding="utf-8")
    print(json.dumps({"status":report["status"],"output":args.output.as_posix(),"source_head":head,"best_gpu_games_per_second":report["best_gpu_games_per_second"],"best_gpu_decisions_per_second":report["best_gpu_decisions_per_second"],"cpu_vs_gpu_public_speedup":report["cpu_vs_gpu_public_speedup"],"stress_status":stress["status"],"stack_statuses":[r["status"] for r in stack]}, sort_keys=True))
    if not passed: raise SystemExit(1)


if __name__ == "__main__": main()
