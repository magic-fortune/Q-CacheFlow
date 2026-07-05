from __future__ import annotations

from typing import Iterable, List

from qcacheflow.circuits.profiler import CircuitProfile, profile_circuit
from qcacheflow.compiler.compiler_service import CompilerService
from qcacheflow.core.backend import BackendModel
from qcacheflow.core.job import Job
from qcacheflow.pipeline.decision import BackendEstimate


class BackendEstimator:
    def __init__(self, compiler: CompilerService) -> None:
        self.compiler = compiler

    def estimate_all(self, job: Job, backends: Iterable[BackendModel], now: float) -> List[BackendEstimate]:
        profile = profile_circuit(job.circuit)
        estimates = []
        for backend in backends:
            estimates.append(self.estimate(job, backend, profile, now))
        return estimates

    def estimate(self, job: Job, backend: BackendModel, profile: CircuitProfile, now: float) -> BackendEstimate:
        compile_time, execution_time, fidelity, lookup, full_compile_time = self.compiler.estimate_cached_metadata(job, backend)
        queue_delay = backend.queue_delay_at(now)
        finish = now + queue_delay + compile_time + execution_time
        slack = job.deadline - finish
        deadline_miss = max(0.0, -slack)
        fidelity_gap = max(0.0, job.fidelity_target - fidelity)
        cache_penalty = 0.0 if lookup.state in {"full_hit", "partial_hit", "metadata_stale"} else compile_time
        score = deadline_miss * 10.0 + (queue_delay + compile_time + execution_time) + fidelity_gap * 0.5 + cache_penalty * 0.25
        return BackendEstimate(
            backend=backend,
            profile=profile,
            cache_lookup=lookup,
            predicted_compile_time=compile_time,
            full_compile_time=full_compile_time,
            predicted_execution_time=execution_time,
            predicted_fidelity=fidelity,
            queue_delay=queue_delay,
            predicted_finish_time=finish,
            deadline_slack=slack,
            can_meet_deadline=slack >= 0.0,
            can_meet_fidelity=fidelity >= job.fidelity_target,
            score=score,
        )
