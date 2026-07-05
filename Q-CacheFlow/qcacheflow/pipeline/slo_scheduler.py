from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, Iterable, List

from qcacheflow.compiler.compiler_service import CompilerService
from qcacheflow.core.backend import BackendModel
from qcacheflow.core.job import Job
from qcacheflow.pipeline.decision import BackendEstimate, SchedulingDecision
from qcacheflow.pipeline.estimator import BackendEstimator
from qcacheflow.scheduler.base import Scheduler


@dataclass
class SLOPolicy:
    admission: bool = True
    allow_best_effort: bool = True
    batch_window: float = 0.15
    min_batch_size: int = 2
    max_batch_size: int = 8


class SLOAwareQCacheFlowScheduler(Scheduler):
    name = "qcacheflow"

    def __init__(self, policy: SLOPolicy | None = None) -> None:
        self.policy = policy or SLOPolicy()
        self._next_batch_id = 0
        self._pending_by_template: Dict[str, List[int]] = defaultdict(list)

    def choose_backend(self, job: Job, backends: List[BackendModel], compiler: CompilerService, now: float) -> BackendModel:
        decision = self.decide(job, backends, compiler, now)
        if not decision.accepted or decision.backend is None:
            return min(backends, key=lambda b: b.queue_delay_at(now))
        return decision.backend

    def decide(self, job: Job, backends: Iterable[BackendModel], compiler: CompilerService, now: float) -> SchedulingDecision:
        estimates = BackendEstimator(compiler).estimate_all(job, backends, now)
        feasible = [e for e in estimates if e.can_meet_deadline and e.can_meet_fidelity]
        if feasible:
            selected = min(feasible, key=lambda e: (e.predicted_finish_time, e.predicted_compile_time, e.backend.backend_id))
            return SchedulingDecision(True, selected.backend, selected, "meets_deadline_and_fidelity", self._batch_id(job), tuple(estimates))

        deadline_only = [e for e in estimates if e.can_meet_deadline]
        if deadline_only and self.policy.allow_best_effort:
            selected = min(deadline_only, key=lambda e: (job.fidelity_target - e.predicted_fidelity, e.predicted_finish_time))
            return SchedulingDecision(True, selected.backend, selected, "best_effort_fidelity", self._batch_id(job), tuple(estimates))

        selected = min(estimates, key=lambda e: e.score)
        if self.policy.admission:
            return SchedulingDecision(False, None, selected, "reject_slo_unmet", -1, tuple(estimates))
        return SchedulingDecision(True, selected.backend, selected, "admitted_despite_slo_risk", self._batch_id(job), tuple(estimates))

    def _batch_id(self, job: Job) -> int:
        thash = job.template_hash or job.template_id
        bucket = self._pending_by_template[thash]
        bucket.append(job.job_id)
        if len(bucket) < self.policy.min_batch_size:
            return -1
        if len(bucket) >= self.policy.max_batch_size:
            batch_id = self._next_batch_id
            self._next_batch_id += 1
            bucket.clear()
            return batch_id
        return self._next_batch_id
