from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from qcacheflow.circuits.profiler import CircuitProfile
from qcacheflow.cache.compiler_cache import CacheLookup
from qcacheflow.core.backend import BackendModel


@dataclass(frozen=True)
class BackendEstimate:
    backend: BackendModel
    profile: CircuitProfile
    cache_lookup: CacheLookup
    predicted_compile_time: float
    full_compile_time: float
    predicted_execution_time: float
    predicted_fidelity: float
    queue_delay: float
    predicted_finish_time: float
    deadline_slack: float
    can_meet_deadline: bool
    can_meet_fidelity: bool
    score: float


@dataclass(frozen=True)
class SchedulingDecision:
    accepted: bool
    backend: BackendModel | None
    estimate: BackendEstimate | None
    reason: str
    batch_id: int = -1
    alternatives: tuple[BackendEstimate, ...] = ()

