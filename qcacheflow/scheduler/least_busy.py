from __future__ import annotations

from typing import List

from qcacheflow.compiler.compiler_service import CompilerService
from qcacheflow.core.backend import BackendModel
from qcacheflow.core.job import Job
from qcacheflow.scheduler.base import Scheduler


class LeastBusyScheduler(Scheduler):
    name = "least-busy"

    def choose_backend(self, job: Job, backends: List[BackendModel], compiler: CompilerService, now: float) -> BackendModel:
        return min(backends, key=lambda b: (b.queue_delay_at(now), b.backend_id))

