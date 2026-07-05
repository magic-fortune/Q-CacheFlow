from __future__ import annotations

from typing import List

from qcacheflow.compiler.compiler_service import CompilerService
from qcacheflow.core.backend import BackendModel
from qcacheflow.core.job import Job
from qcacheflow.scheduler.base import Scheduler, estimate_uncached


class LatencyFirstScheduler(Scheduler):
    name = "latency-first"

    def choose_backend(self, job: Job, backends: List[BackendModel], compiler: CompilerService, now: float) -> BackendModel:
        def score(b: BackendModel) -> tuple[float, str]:
            execution, _ = estimate_uncached(job, b)
            return b.queue_delay_at(now) + execution, b.backend_id

        return min(backends, key=score)

