from __future__ import annotations

import math
from typing import Any

from qcacheflow.circuits.profiler import profile_circuit
from qcacheflow.core.backend import BackendModel
from qcacheflow.core.job import Job


def estimate_execution_time(job: Job, backend: BackendModel, circuit: Any) -> float:
    profile = profile_circuit(circuit)
    alpha = backend.gate_duration * 50.0
    beta_duration = backend.two_qubit_gate_duration if backend.two_qubit_gate_duration is not None else backend.gate_duration
    beta = beta_duration * 200.0
    return backend.fixed_overhead + alpha * job.shots * profile.depth + beta * job.shots * profile.two_qubit_gate_count


def estimate_fidelity(backend: BackendModel, circuit: Any) -> float:
    profile = profile_circuit(circuit)
    one_qubit = max(0, profile.num_gates - profile.two_qubit_gate_count)
    two_qubit = profile.two_qubit_gate_count
    measurements = profile.num_qubits
    gate_err = min(0.5, backend.gate_error_rate)
    two_qubit_error = backend.two_qubit_gate_error_rate if backend.two_qubit_gate_error_rate is not None else backend.gate_error_rate * 4.0
    two_err = min(0.8, two_qubit_error)
    readout_err = min(0.8, backend.readout_error_rate)
    log_f = one_qubit * math.log(max(1e-12, 1.0 - gate_err))
    log_f += two_qubit * math.log(max(1e-12, 1.0 - two_err))
    log_f += measurements * math.log(max(1e-12, 1.0 - readout_err))
    return max(0.0, min(1.0, math.exp(log_f)))
