from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class Job:
    job_id: int
    user_id: int
    circuit: Any
    template_id: str
    arrival_time: float
    deadline: float
    shots: int
    fidelity_target: float
    priority: int = 0
    template_hash: Optional[str] = None


@dataclass
class JobResult:
    job_id: int
    scheduler: str
    backend_id: str
    arrival_time: float
    start_time: float
    finish_time: float
    turnaround_time: float
    queue_delay: float
    compile_time: float
    execution_time: float
    estimated_fidelity: float
    actual_fidelity: float
    fidelity_target: float
    deadline: float
    deadline_miss: bool
    fidelity_violation: bool
    slo_met: bool
    cache_state: str
    full_compile_time: float
    compile_time_saved: float
    accepted: bool = True
    rejected: bool = False
    reject_reason: str = ""
    decision_reason: str = ""
    batch_id: int = -1
    profile_time: float = 0.0
    admission_time: float = 0.0
    compile_start_time: float = 0.0
    compile_finish_time: float = 0.0
    execution_start_time: float = 0.0
    execution_finish_time: float = 0.0
    template_hit: bool = False
    structural_hit: bool = False
    metadata_hit: bool = False
    metadata_stale: bool = False
    metadata_confidence: float = 1.0
    metadata_epoch: int = -1
    backend_calibration_epoch: int = -1
    predicted_cache_state: str = ""
    predicted_compile_time: float = 0.0
    predicted_execution_time: float = 0.0
    predicted_fidelity: float = 0.0
    predicted_finish_time: float = 0.0
