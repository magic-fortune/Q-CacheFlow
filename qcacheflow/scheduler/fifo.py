from __future__ import annotations

from typing import List

from qcacheflow.compiler.compiler_service import CompilerService
from qcacheflow.core.backend import BackendModel
from qcacheflow.core.job import Job
from qcacheflow.scheduler.base import Scheduler


class FIFOScheduler(Scheduler):
    name = "fifo"

    def choose_backend(self, job: Job, backends: List[BackendModel], compiler: CompilerService, now: float) -> BackendModel:
        return backends[0]

