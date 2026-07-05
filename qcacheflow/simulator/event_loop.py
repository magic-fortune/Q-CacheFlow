from __future__ import annotations

import random
from typing import Iterable, List, Optional

from qcacheflow.cache.compiler_cache import CompilerCache
from qcacheflow.cache.invalidation import apply_calibration_update
from qcacheflow.compiler.estimator import estimate_fidelity
from qcacheflow.compiler.compiler_service import CompilerService
from qcacheflow.core.backend import BackendModel
from qcacheflow.core.job import Job, JobResult
from qcacheflow.scheduler.base import Scheduler


class Simulator:
    def __init__(
        self,
        backends: List[BackendModel],
        scheduler: Scheduler,
        cache_policy: str = "pass-level",
        invalidation_policy: str = "soft",
        calibration_interval: Optional[float] = None,
        seed: int = 1,
    ) -> None:
        self.backends = backends
        self.scheduler = scheduler
        self.cache = CompilerCache(cache_policy)
        self.compiler = CompilerService(self.cache)
        self.invalidation_policy = invalidation_policy
        self.calibration_interval = calibration_interval
        self.rng = random.Random(seed)
        self.next_calibration_time = calibration_interval if calibration_interval else None

    def run(self, jobs: Iterable[Job]) -> List[JobResult]:
        results: List[JobResult] = []
        for job in sorted(jobs, key=lambda j: (j.arrival_time, j.job_id)):
            self._maybe_calibrate(job.arrival_time)
            now = job.arrival_time
            if hasattr(self.scheduler, "decide"):
                decision = self.scheduler.decide(job, self.backends, self.compiler, now)
                if not decision.accepted or decision.backend is None:
                    results.append(
                        JobResult(
                            job_id=job.job_id,
                            scheduler=self.scheduler.name,
                            backend_id="REJECTED",
                            arrival_time=job.arrival_time,
                            start_time=now,
                            finish_time=now,
                            turnaround_time=0.0,
                            queue_delay=0.0,
                            compile_time=0.0,
                            execution_time=0.0,
                            estimated_fidelity=0.0,
                            actual_fidelity=0.0,
                            fidelity_target=job.fidelity_target,
                            deadline=job.deadline,
                            deadline_miss=True,
                            fidelity_violation=True,
                            slo_met=False,
                            cache_state="rejected",
                            full_compile_time=0.0,
                            compile_time_saved=0.0,
                            accepted=False,
                            rejected=True,
                            reject_reason=decision.reason,
                            decision_reason=decision.reason,
                        )
                    )
                    continue
                backend = decision.backend
                batch_id = decision.batch_id
                decision_reason = decision.reason
                selected_estimate = decision.estimate
            else:
                backend = self.scheduler.choose_backend(job, self.backends, self.compiler, now)
                batch_id = -1
                decision_reason = self.scheduler.name
                selected_estimate = None
            compile_result = self.compiler.compile_or_cache(job, backend)
            queue_delay = backend.queue_delay_at(now)
            start_time = max(now, backend.next_available_time) + compile_result.compile_time
            finish_time = start_time + compile_result.execution_time
            backend.next_available_time = finish_time
            backend.executed_time += compile_result.execution_time
            deadline_miss = finish_time > job.deadline
            actual_fidelity = estimate_fidelity(backend, compile_result.circuit)
            fidelity_violation = actual_fidelity < job.fidelity_target
            results.append(
                JobResult(
                    job_id=job.job_id,
                    scheduler=self.scheduler.name,
                    backend_id=backend.backend_id,
                    arrival_time=job.arrival_time,
                    start_time=start_time,
                    finish_time=finish_time,
                    turnaround_time=finish_time - job.arrival_time,
                    queue_delay=queue_delay,
                    compile_time=compile_result.compile_time,
                    execution_time=compile_result.execution_time,
                    estimated_fidelity=compile_result.estimated_fidelity,
                    actual_fidelity=actual_fidelity,
                    fidelity_target=job.fidelity_target,
                    deadline=job.deadline,
                    deadline_miss=deadline_miss,
                    fidelity_violation=fidelity_violation,
                    slo_met=not deadline_miss and not fidelity_violation,
                    cache_state=compile_result.cache_state,
                    full_compile_time=compile_result.full_compile_time,
                    compile_time_saved=max(0.0, compile_result.full_compile_time - compile_result.compile_time),
                    decision_reason=decision_reason,
                    batch_id=batch_id,
                    template_hit=compile_result.template_hit,
                    structural_hit=compile_result.structural_hit,
                    metadata_hit=compile_result.metadata_hit,
                    metadata_stale=compile_result.metadata_stale,
                    metadata_confidence=compile_result.metadata_confidence,
                    metadata_epoch=compile_result.metadata_epoch,
                    backend_calibration_epoch=compile_result.backend_calibration_epoch,
                    predicted_cache_state=selected_estimate.cache_lookup.state if selected_estimate else "",
                    predicted_compile_time=selected_estimate.predicted_compile_time if selected_estimate else 0.0,
                    predicted_execution_time=selected_estimate.predicted_execution_time if selected_estimate else 0.0,
                    predicted_fidelity=selected_estimate.predicted_fidelity if selected_estimate else 0.0,
                    predicted_finish_time=selected_estimate.predicted_finish_time if selected_estimate else 0.0,
                )
            )
        return results

    def _maybe_calibrate(self, now: float) -> None:
        if self.next_calibration_time is None or self.calibration_interval is None:
            return
        while now >= self.next_calibration_time:
            for backend in self.backends:
                backend.perturb_calibration(self.rng)
                apply_calibration_update(self.cache, backend, self.invalidation_policy)
            self.next_calibration_time += self.calibration_interval
