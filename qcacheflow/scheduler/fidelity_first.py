from __future__ import annotations

from typing import List

from qcacheflow.compiler.compiler_service import CompilerService
from qcacheflow.core.backend import BackendModel
from qcacheflow.core.job import Job
from qcacheflow.scheduler.base import Scheduler, estimate_uncached


class FidelityFirstScheduler(Scheduler):
    name = "fidelity-first"

    def choose_backend(self, job: Job, backends: List[BackendModel], compiler: CompilerService, now: float) -> BackendModel:
        def score(b: BackendModel) -> tuple[float, float]:
            _, fidelity = estimate_uncached(job, b)
            return fidelity, -b.queue_delay_at(now)

        return max(backends, key=score)

