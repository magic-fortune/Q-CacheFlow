from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from qcacheflow.compiler.compiler_service import CompilerService
from qcacheflow.compiler.estimator import estimate_execution_time, estimate_fidelity
from qcacheflow.core.backend import BackendModel
from qcacheflow.core.job import Job


class Scheduler(ABC):
    name = "base"

    @abstractmethod
    def choose_backend(self, job: Job, backends: List[BackendModel], compiler: CompilerService, now: float) -> BackendModel:
        raise NotImplementedError


def estimate_uncached(job: Job, backend: BackendModel) -> tuple[float, float]:
    return estimate_execution_time(job, backend, job.circuit), estimate_fidelity(backend, job.circuit)

