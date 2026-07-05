from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field
from typing import List, Sequence, Tuple


def _hash_obj(value: object) -> str:
    return hashlib.sha256(repr(value).encode("utf-8")).hexdigest()[:16]


@dataclass
class BackendModel:
    backend_id: str
    num_qubits: int
    coupling_map: List[Tuple[int, int]]
    basis_gates: List[str]
    gate_error_rate: float
    readout_error_rate: float
    gate_duration: float
    fixed_overhead: float
    two_qubit_gate_error_rate: float | None = None
    two_qubit_gate_duration: float | None = None
    calibration_epoch: int = 0
    next_available_time: float = 0.0
    executed_time: float = 0.0

    @property
    def topology_hash(self) -> str:
        return _hash_obj(sorted(self.coupling_map))

    @property
    def basis_gates_hash(self) -> str:
        return _hash_obj(sorted(self.basis_gates))

    def queue_delay_at(self, now: float) -> float:
        return max(0.0, self.next_available_time - now)

    def reset_runtime(self) -> None:
        self.next_available_time = 0.0
        self.executed_time = 0.0

    def perturb_calibration(self, rng: random.Random, scale: float = 0.20) -> None:
        multiplier = 1.0 + rng.uniform(-scale, scale)
        readout_multiplier = 1.0 + rng.uniform(-scale, scale)
        self.gate_error_rate = min(0.08, max(0.0005, self.gate_error_rate * multiplier))
        if self.two_qubit_gate_error_rate is not None:
            self.two_qubit_gate_error_rate = min(0.20, max(0.001, self.two_qubit_gate_error_rate * multiplier))
        self.readout_error_rate = min(0.20, max(0.001, self.readout_error_rate * readout_multiplier))
        self.calibration_epoch += 1


def make_backends(num_backends: int, seed: int) -> List[BackendModel]:
    rng = random.Random(seed)
    backends: List[BackendModel] = []
    sizes = [5, 7, 9, 12, 15, 20]
    for i in range(num_backends):
        n = sizes[i % len(sizes)]
        line = [(q, q + 1) for q in range(n - 1)]
        extra = [(q, q + 2) for q in range(0, n - 2, 3)]
        coupling = line + extra
        backends.append(
            BackendModel(
                backend_id=f"backend_{i}",
                num_qubits=n,
                coupling_map=coupling,
                basis_gates=["id", "rz", "sx", "x", "cx"],
                gate_error_rate=rng.uniform(0.002, 0.018) * (1.0 + i * 0.08),
                readout_error_rate=rng.uniform(0.01, 0.055) * (1.0 + i * 0.05),
                gate_duration=rng.uniform(1.0e-7, 4.0e-7),
                fixed_overhead=rng.uniform(0.01, 0.05),
            )
        )
    return backends


def clone_backends(backends: Sequence[BackendModel]) -> List[BackendModel]:
    return [
        BackendModel(
            backend_id=b.backend_id,
            num_qubits=b.num_qubits,
            coupling_map=list(b.coupling_map),
            basis_gates=list(b.basis_gates),
            gate_error_rate=b.gate_error_rate,
            readout_error_rate=b.readout_error_rate,
            gate_duration=b.gate_duration,
            fixed_overhead=b.fixed_overhead,
            two_qubit_gate_error_rate=b.two_qubit_gate_error_rate,
            two_qubit_gate_duration=b.two_qubit_gate_duration,
            calibration_epoch=b.calibration_epoch,
        )
        for b in backends
    ]
