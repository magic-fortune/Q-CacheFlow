from __future__ import annotations

import heapq
import random
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional

from qcacheflow.cache.compiler_cache import CompilerCache
from qcacheflow.cache.invalidation import apply_calibration_update
from qcacheflow.circuits.profiler import profile_circuit
from qcacheflow.compiler.estimator import estimate_fidelity
from qcacheflow.compiler.compiler_service import CompileResult, CompilerService
from qcacheflow.core.backend import BackendModel
from qcacheflow.core.job import Job, JobResult
from qcacheflow.pipeline.decision import BackendEstimate
from qcacheflow.scheduler.base import Scheduler


@dataclass(order=True)
class Event:
    time: float
    seq: int
    event_type: str
    job_id: int = -1
    backend_id: str = ""


@dataclass
class JobContext:
    job: Job
    profile_time: float = 0.0
    admission_time: float = 0.0
    backend: BackendModel | None = None
    batch_id: int = -1
    decision_reason: str = ""
    selected_estimate: BackendEstimate | None = None
    compile_result: CompileResult | None = None
    compile_start: float = 0.0
    compile_finish: float = 0.0
    execution_start: float = 0.0
    execution_finish: float = 0.0


class EventDrivenSimulator:
    def __init__(
        self,
        backends: List[BackendModel],
        scheduler: Scheduler,
        cache_policy: str = "pass-level",
        invalidation_policy: str = "soft",
        calibration_interval: Optional[float] = None,
        seed: int = 1,
        profile_cost: float = 0.0002,
    ) -> None:
        self.backends = {b.backend_id: b for b in backends}
        self.scheduler = scheduler
        self.cache = CompilerCache(cache_policy)
        self.compiler = CompilerService(self.cache)
        self.invalidation_policy = invalidation_policy
        self.calibration_interval = calibration_interval
        self.profile_cost = profile_cost
        self.rng = random.Random(seed)
        self._seq = 0
        self._events: list[Event] = []
        self._contexts: Dict[int, JobContext] = {}
        self.results: List[JobResult] = []

    def run(self, jobs: Iterable[Job]) -> List[JobResult]:
        for job in sorted(jobs, key=lambda j: (j.arrival_time, j.job_id)):
            self._contexts[job.job_id] = JobContext(job)
            self._push(job.arrival_time, "JOB_ARRIVAL", job.job_id)
        if self.calibration_interval:
            self._push(self.calibration_interval, "CALIBRATION_UPDATE")

        while self._events:
            event = heapq.heappop(self._events)
            if event.event_type == "JOB_ARRIVAL":
                self._on_arrival(event)
            elif event.event_type == "PROFILE_FINISH":
                self._on_profile_finish(event)
            elif event.event_type == "SCHEDULE_DECISION":
                self._on_schedule(event)
            elif event.event_type == "COMPILE_START":
                self._on_compile_start(event)
            elif event.event_type == "COMPILE_FINISH":
                self._on_compile_finish(event)
            elif event.event_type == "EXECUTION_START":
                self._on_execution_start(event)
            elif event.event_type == "EXECUTION_FINISH":
                self._on_execution_finish(event)
            elif event.event_type == "CALIBRATION_UPDATE":
                self._on_calibration_update(event)
        return sorted(self.results, key=lambda r: r.job_id)

    def _on_arrival(self, event: Event) -> None:
        ctx = self._contexts[event.job_id]
        profile_circuit(ctx.job.circuit)
        ctx.profile_time = event.time + self.profile_cost
        self._push(ctx.profile_time, "PROFILE_FINISH", ctx.job.job_id)

    def _on_profile_finish(self, event: Event) -> None:
        self._push(event.time, "SCHEDULE_DECISION", event.job_id)

    def _on_schedule(self, event: Event) -> None:
        ctx = self._contexts[event.job_id]
        ctx.admission_time = event.time
        backends = list(self.backends.values())
        if hasattr(self.scheduler, "decide"):
            decision = self.scheduler.decide(ctx.job, backends, self.compiler, event.time)
            ctx.batch_id = decision.batch_id
            ctx.decision_reason = decision.reason
            ctx.selected_estimate = decision.estimate
            if not decision.accepted or decision.backend is None:
                self._record_reject(ctx, event.time, decision.reason)
                return
            ctx.backend = decision.backend
        else:
            ctx.backend = self.scheduler.choose_backend(ctx.job, backends, self.compiler, event.time)
            ctx.decision_reason = self.scheduler.name
        self._push(event.time, "COMPILE_START", event.job_id, ctx.backend.backend_id)

    def _on_compile_start(self, event: Event) -> None:
        ctx = self._contexts[event.job_id]
        backend = self.backends[event.backend_id]
        ctx.compile_start = max(event.time, backend.next_available_time)
        ctx.compile_result = self.compiler.compile_or_cache(ctx.job, backend)
        ctx.compile_finish = ctx.compile_start + ctx.compile_result.compile_time
        self._push(ctx.compile_finish, "COMPILE_FINISH", event.job_id, backend.backend_id)

    def _on_compile_finish(self, event: Event) -> None:
        self._push(event.time, "EXECUTION_START", event.job_id, event.backend_id)

    def _on_execution_start(self, event: Event) -> None:
        ctx = self._contexts[event.job_id]
        backend = self.backends[event.backend_id]
        compile_result = ctx.compile_result
        if compile_result is None:
            raise RuntimeError("compile result missing")
        ctx.execution_start = max(event.time, backend.next_available_time)
        ctx.execution_finish = ctx.execution_start + compile_result.execution_time
        backend.next_available_time = ctx.execution_finish
        backend.executed_time += compile_result.execution_time
        self._push(ctx.execution_finish, "EXECUTION_FINISH", event.job_id, backend.backend_id)

    def _on_execution_finish(self, event: Event) -> None:
        ctx = self._contexts[event.job_id]
        self._record_finish(ctx)

    def _on_calibration_update(self, event: Event) -> None:
        if len(self.results) >= len(self._contexts):
            return
        for backend in self.backends.values():
            backend.perturb_calibration(self.rng)
            apply_calibration_update(self.cache, backend, self.invalidation_policy)
        if self.calibration_interval and len(self.results) < len(self._contexts):
            self._push(event.time + self.calibration_interval, "CALIBRATION_UPDATE")

    def _record_reject(self, ctx: JobContext, now: float, reason: str) -> None:
        self.results.append(
            JobResult(
                job_id=ctx.job.job_id,
                scheduler=self.scheduler.name,
                backend_id="REJECTED",
                arrival_time=ctx.job.arrival_time,
                start_time=now,
                finish_time=now,
                turnaround_time=0.0,
                queue_delay=0.0,
                compile_time=0.0,
                execution_time=0.0,
                estimated_fidelity=0.0,
                actual_fidelity=0.0,
                fidelity_target=ctx.job.fidelity_target,
                deadline=ctx.job.deadline,
                deadline_miss=True,
                fidelity_violation=True,
                slo_met=False,
                cache_state="rejected",
                full_compile_time=0.0,
                compile_time_saved=0.0,
                accepted=False,
                rejected=True,
                reject_reason=reason,
                decision_reason=reason,
                batch_id=-1,
                profile_time=ctx.profile_time,
                admission_time=ctx.admission_time,
            )
        )

    def _record_finish(self, ctx: JobContext) -> None:
        compile_result = ctx.compile_result
        backend = ctx.backend
        if compile_result is None or backend is None:
            raise RuntimeError("finished job missing backend or compile result")
        deadline_miss = ctx.execution_finish > ctx.job.deadline
        actual_fidelity = estimate_fidelity(backend, compile_result.circuit)
        fidelity_violation = actual_fidelity < ctx.job.fidelity_target
        estimate = ctx.selected_estimate
        self.results.append(
            JobResult(
                job_id=ctx.job.job_id,
                scheduler=self.scheduler.name,
                backend_id=backend.backend_id,
                arrival_time=ctx.job.arrival_time,
                start_time=ctx.compile_start,
                finish_time=ctx.execution_finish,
                turnaround_time=ctx.execution_finish - ctx.job.arrival_time,
                queue_delay=max(0.0, ctx.compile_start - ctx.job.arrival_time),
                compile_time=compile_result.compile_time,
                execution_time=compile_result.execution_time,
                estimated_fidelity=compile_result.estimated_fidelity,
                actual_fidelity=actual_fidelity,
                fidelity_target=ctx.job.fidelity_target,
                deadline=ctx.job.deadline,
                deadline_miss=deadline_miss,
                fidelity_violation=fidelity_violation,
                slo_met=not deadline_miss and not fidelity_violation,
                cache_state=compile_result.cache_state,
                full_compile_time=compile_result.full_compile_time,
                compile_time_saved=max(0.0, compile_result.full_compile_time - compile_result.compile_time),
                decision_reason=ctx.decision_reason,
                batch_id=ctx.batch_id,
                profile_time=ctx.profile_time,
                admission_time=ctx.admission_time,
                compile_start_time=ctx.compile_start,
                compile_finish_time=ctx.compile_finish,
                execution_start_time=ctx.execution_start,
                execution_finish_time=ctx.execution_finish,
                template_hit=compile_result.template_hit,
                structural_hit=compile_result.structural_hit,
                metadata_hit=compile_result.metadata_hit,
                metadata_stale=compile_result.metadata_stale,
                metadata_confidence=compile_result.metadata_confidence,
                metadata_epoch=compile_result.metadata_epoch,
                backend_calibration_epoch=compile_result.backend_calibration_epoch,
                predicted_cache_state=estimate.cache_lookup.state if estimate else "",
                predicted_compile_time=estimate.predicted_compile_time if estimate else 0.0,
                predicted_execution_time=estimate.predicted_execution_time if estimate else 0.0,
                predicted_fidelity=estimate.predicted_fidelity if estimate else 0.0,
                predicted_finish_time=estimate.predicted_finish_time if estimate else 0.0,
            )
        )

    def _push(self, time: float, event_type: str, job_id: int = -1, backend_id: str = "") -> None:
        self._seq += 1
        heapq.heappush(self._events, Event(time, self._seq, event_type, job_id, backend_id))
