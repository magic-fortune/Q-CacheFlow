from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from qcacheflow.cache.compiler_cache import CompilerCache
from qcacheflow.compiler.compiler_service import CompilerService
from qcacheflow.core.backend import clone_backends, make_backends
from qcacheflow.core.metrics import summarize_results
from qcacheflow.scheduler.cache_unaware import CacheUnawareScheduler
from qcacheflow.scheduler.qcacheflow import QCacheFlowScheduler
from qcacheflow.simulator.event_driven import EventDrivenSimulator
from qcacheflow.simulator.workload import generate_workload


def warm_cache(sim: EventDrivenSimulator, jobs, backends, limit: int = 24) -> None:
    """Create a reproducible warm compiler-cache state before measured jobs."""
    compiler = CompilerService(CompilerCache("pass-level"))
    seen: set[tuple[str, str]] = set()
    for job in jobs[:limit]:
        template_hash = job.template_hash or job.template_id
        backend = backends[int(template_hash[:8], 16) % len(backends)]
        key = (template_hash, backend.backend_id)
        if key in seen:
            continue
        compiler.compile_or_cache(job, backend)
        seen.add(key)

    sim.cache = compiler.cache
    sim.compiler = compiler


def run_policy(name: str, scheduler, jobs, backends):
    sim = EventDrivenSimulator(
        clone_backends(backends),
        scheduler,
        cache_policy="pass-level",
        invalidation_policy="soft",
        calibration_interval=8.0,
        seed=11,
    )
    warm_cache(sim, jobs, list(sim.backends.values()))
    summary = summarize_results(sim.run(jobs))
    return {
        "policy": name,
        "slo_goodput": summary["slo_goodput"],
        "p95_turnaround": summary["p95_turnaround_time"],
        "cache_hit_rate": summary["cache_hit_rate"],
        "deadline_miss_ratio": summary["deadline_miss_ratio"],
        "fidelity_violation_ratio": summary["fidelity_target_violation_ratio"],
    }


def main() -> None:
    jobs = generate_workload(num_jobs=80, repetition_ratio=0.7, arrival_rate=2.0, seed=11)
    backends = make_backends(num_backends=3, seed=112)
    rows = [
        run_policy("cache-unaware", CacheUnawareScheduler(), jobs, backends),
        run_policy("qcacheflow", QCacheFlowScheduler(), jobs, backends),
    ]

    header = f"{'policy':<15} {'slo':>7} {'p95':>9} {'hit':>7} {'dmr':>7} {'fvr':>7}"
    print(header)
    print("-" * len(header))
    for row in rows:
        print(
            f"{row['policy']:<15} "
            f"{row['slo_goodput']:>7.3f} "
            f"{row['p95_turnaround']:>9.3f} "
            f"{row['cache_hit_rate']:>7.3f} "
            f"{row['deadline_miss_ratio']:>7.3f} "
            f"{row['fidelity_violation_ratio']:>7.3f}"
        )


if __name__ == "__main__":
    main()
