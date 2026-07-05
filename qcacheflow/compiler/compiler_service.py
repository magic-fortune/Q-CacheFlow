from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, Tuple

try:
    from qiskit import transpile
except Exception:  # pragma: no cover
    transpile = None

from qcacheflow.cache.compiler_cache import CompilerCache
from qcacheflow.cache.compiler_cache import CacheLookup
from qcacheflow.circuits.profiler import profile_circuit
from qcacheflow.compiler.estimator import estimate_execution_time, estimate_fidelity
from qcacheflow.core.backend import BackendModel
from qcacheflow.core.job import Job


@dataclass
class CompileResult:
    circuit: Any
    cache_state: str
    compile_time: float
    full_compile_time: float
    execution_time: float
    estimated_fidelity: float
    depth: int
    gate_count: int
    two_qubit_gate_count: int
    template_hit: bool = False
    structural_hit: bool = False
    metadata_hit: bool = False
    metadata_stale: bool = False
    metadata_confidence: float = 1.0
    metadata_epoch: int = -1
    backend_calibration_epoch: int = -1


class CompilerService:
    def __init__(
        self,
        cache: CompilerCache,
        optimization_level: int = 3,
        cache_lookup_overhead: float = 0.0005,
        partial_ratio: float = 0.30,
    ) -> None:
        self.cache = cache
        self.optimization_level = optimization_level
        self.cache_lookup_overhead = cache_lookup_overhead
        self.partial_ratio = partial_ratio
        self.full_compile_times: Dict[Tuple[str, str], float] = {}

    def predict_compile_time(self, job: Job, backend: BackendModel) -> tuple[float, str, float]:
        thash = job.template_hash or profile_circuit(job.circuit).template_hash
        lookup = self.cache.lookup(thash, backend, self.optimization_level)
        full = self.full_compile_times.get((thash, backend.backend_id), self._fallback_compile_time(job, backend))
        if lookup.state == "full_hit":
            return self.cache_lookup_overhead, lookup.state, full
        if lookup.state in {"partial_hit", "metadata_stale"}:
            return max(self.cache_lookup_overhead, self.partial_ratio * full), lookup.state, full
        return full, "miss", full

    def estimate_cached_metadata(self, job: Job, backend: BackendModel) -> tuple[float, float, str, CacheLookup, float]:
        thash = job.template_hash or profile_circuit(job.circuit).template_hash
        lookup = self.cache.peek(thash, backend, self.optimization_level)
        full = self.full_compile_times.get((thash, backend.backend_id), self._fallback_compile_time(job, backend))
        compile_time = self._compile_time_from_lookup(lookup, full)
        circuit = lookup.structural or job.circuit
        if lookup.state == "full_hit" and lookup.metadata is not None:
            execution_time = lookup.metadata["execution_time"]
            fidelity = lookup.metadata["estimated_fidelity"] * lookup.confidence
        else:
            metadata = self._metadata(job, backend, circuit, full)
            execution_time = metadata["execution_time"]
            fidelity = metadata["estimated_fidelity"] * lookup.confidence
        return compile_time, execution_time, fidelity, lookup, full

    def compile_or_cache(self, job: Job, backend: BackendModel) -> CompileResult:
        thash = job.template_hash or profile_circuit(job.circuit).template_hash
        lookup = self.cache.lookup(thash, backend, self.optimization_level)

        if lookup.state == "full_hit" and lookup.structural is not None and lookup.metadata is not None:
            circuit = lookup.structural
            metadata = lookup.metadata
            full = self.full_compile_times.get((thash, backend.backend_id), metadata.get("full_compile_time", 0.0))
            profile = profile_circuit(circuit)
            return CompileResult(
                circuit=circuit,
                cache_state="full_hit",
                compile_time=self.cache_lookup_overhead,
                full_compile_time=full,
                execution_time=metadata["execution_time"],
                estimated_fidelity=metadata["estimated_fidelity"],
                depth=profile.depth,
                gate_count=profile.num_gates,
                two_qubit_gate_count=profile.two_qubit_gate_count,
                template_hit=lookup.template_hit,
                structural_hit=lookup.structural_hit,
                metadata_hit=lookup.metadata_hit,
                metadata_stale=lookup.metadata_stale,
                metadata_confidence=lookup.confidence,
                metadata_epoch=metadata.get("calibration_epoch", -1),
                backend_calibration_epoch=backend.calibration_epoch,
            )

        if lookup.structural is not None:
            circuit = lookup.structural
            full = self.full_compile_times.get((thash, backend.backend_id), self._fallback_compile_time(job, backend))
            compile_time = self._compile_time_from_lookup(lookup, full)
            metadata = self._metadata(job, backend, circuit, full)
            self.cache.store(thash, backend, self.optimization_level, circuit, metadata)
            profile = profile_circuit(circuit)
            return CompileResult(circuit, lookup.state, compile_time, full, metadata["execution_time"], metadata["estimated_fidelity"], profile.depth, profile.num_gates, profile.two_qubit_gate_count, lookup.template_hit, lookup.structural_hit, lookup.metadata_hit, lookup.metadata_stale, lookup.confidence, metadata["calibration_epoch"], backend.calibration_epoch)

        circuit, full = self._full_transpile(job, backend)
        self.full_compile_times[(thash, backend.backend_id)] = full
        metadata = self._metadata(job, backend, circuit, full)
        self.cache.store(thash, backend, self.optimization_level, circuit, metadata)
        profile = profile_circuit(circuit)
        return CompileResult(circuit, "miss", full, full, metadata["execution_time"], metadata["estimated_fidelity"], profile.depth, profile.num_gates, profile.two_qubit_gate_count, lookup.template_hit, lookup.structural_hit, lookup.metadata_hit, lookup.metadata_stale, lookup.confidence, metadata["calibration_epoch"], backend.calibration_epoch)

    def _metadata(self, job: Job, backend: BackendModel, circuit: Any, full_compile_time: float) -> dict:
        return {
            "execution_time": estimate_execution_time(job, backend, circuit),
            "estimated_fidelity": estimate_fidelity(backend, circuit),
            "full_compile_time": full_compile_time,
            "calibration_epoch": backend.calibration_epoch,
        }

    def _compile_time_from_lookup(self, lookup: CacheLookup, full_compile_time: float) -> float:
        if lookup.state == "full_hit":
            return self.cache_lookup_overhead
        if lookup.state in {"partial_hit", "metadata_stale"}:
            return max(self.cache_lookup_overhead, self.partial_ratio * full_compile_time)
        return full_compile_time

    def _full_transpile(self, job: Job, backend: BackendModel) -> tuple[Any, float]:
        if transpile is None:
            return job.circuit, self._fallback_compile_time(job, backend)
        kwargs = {
            "basis_gates": backend.basis_gates,
            "coupling_map": backend.coupling_map,
            "optimization_level": self.optimization_level,
        }
        start = time.perf_counter()
        try:
            circuit = transpile(job.circuit, **kwargs)
        except Exception:
            fallback_kwargs = {"basis_gates": backend.basis_gates, "optimization_level": min(1, self.optimization_level)}
            circuit = transpile(job.circuit, **fallback_kwargs)
        elapsed = time.perf_counter() - start
        return circuit, max(elapsed, self._fallback_compile_time(job, backend) * 0.05)

    def _fallback_compile_time(self, job: Job, backend: BackendModel) -> float:
        profile = profile_circuit(job.circuit)
        topology_penalty = max(1.0, profile.num_qubits / max(1, backend.num_qubits))
        return 0.03 + 0.004 * profile.num_gates * topology_penalty + 0.01 * profile.two_qubit_gate_count
