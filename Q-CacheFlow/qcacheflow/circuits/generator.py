from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Any, List, Tuple

try:
    from qiskit import QuantumCircuit
    from qiskit.circuit import ParameterVector
    from qiskit.circuit.library import EfficientSU2, QFT, TwoLocal
except Exception:  # pragma: no cover - exercised only without qiskit
    QuantumCircuit = None
    ParameterVector = None
    EfficientSU2 = None
    QFT = None
    TwoLocal = None

from qcacheflow.circuits.profiler import template_hash
from qcacheflow.core.job import Job


def qiskit_available() -> bool:
    return QuantumCircuit is not None


@dataclass(frozen=True)
class SimpleOp:
    name: str


@dataclass(frozen=True)
class SimpleInstruction:
    operation: SimpleOp
    qubits: tuple[int, ...]
    clbits: tuple[int, ...] = ()


class SimpleCircuit:
    def __init__(self, num_qubits: int, name: str = "simple") -> None:
        self.num_qubits = num_qubits
        self.name = name
        self.data: list[SimpleInstruction] = []
        self.parameters: list[str] = []

    def h(self, q: int) -> None:
        self.data.append(SimpleInstruction(SimpleOp("h"), (q,)))

    def ry(self, param: object, q: int) -> None:
        self.parameters.append(str(param))
        self.data.append(SimpleInstruction(SimpleOp("ry"), (q,)))

    def rz(self, param: object, q: int) -> None:
        self.parameters.append(str(param))
        self.data.append(SimpleInstruction(SimpleOp("rz"), (q,)))

    def cx(self, a: int, b: int) -> None:
        self.data.append(SimpleInstruction(SimpleOp("cx"), (a, b)))

    def depth(self) -> int:
        return max(1, len(self.data) // max(1, self.num_qubits))

    def copy(self) -> "SimpleCircuit":
        other = SimpleCircuit(self.num_qubits, self.name)
        other.data = list(self.data)
        other.parameters = list(self.parameters)
        return other


def _fallback_circuit(num_qubits: int, name: str) -> Any:
    if QuantumCircuit is None:
        qc = SimpleCircuit(num_qubits, name=name)
        for q in range(num_qubits):
            qc.h(q)
        for q in range(num_qubits - 1):
            qc.cx(q, q + 1)
        return qc
    qc = QuantumCircuit(num_qubits, name=name)
    for q in range(num_qubits):
        qc.h(q)
    for q in range(num_qubits - 1):
        qc.cx(q, q + 1)
    return qc


def make_template(kind: str, num_qubits: int, reps: int, rng: random.Random) -> Any:
    if kind == "vqe":
        if EfficientSU2 is not None:
            return EfficientSU2(num_qubits, reps=reps, entanglement="linear")
        return _fallback_circuit(num_qubits, "vqe")
    if kind == "qaoa":
        if TwoLocal is not None:
            return TwoLocal(num_qubits, ["ry", "rz"], "cx", entanglement="linear", reps=reps)
        return _fallback_circuit(num_qubits, "qaoa")
    if kind == "qft":
        if QFT is not None:
            return QFT(num_qubits, do_swaps=False)
        return _fallback_circuit(num_qubits, "qft")
    if kind == "ghz":
        qc = QuantumCircuit(num_qubits) if QuantumCircuit is not None else SimpleCircuit(num_qubits, "ghz")
        qc.h(0)
        for q in range(num_qubits - 1):
            qc.cx(q, q + 1)
        return qc
    qc = QuantumCircuit(num_qubits) if QuantumCircuit is not None else SimpleCircuit(num_qubits, "random")
    angles = ParameterVector("theta", length=max(1, num_qubits * reps)) if ParameterVector is not None else [f"theta_{i}" for i in range(max(1, num_qubits * reps))]
    idx = 0
    for _ in range(reps):
        for q in range(num_qubits):
            qc.ry(angles[idx % len(angles)], q)
            idx += 1
        for q in range(num_qubits - 1):
            if rng.random() < 0.75:
                qc.cx(q, q + 1)
    return qc


def bind_random_parameters(circuit: Any, rng: random.Random) -> Any:
    if isinstance(circuit, SimpleCircuit):
        return circuit.copy()
    params = sorted(getattr(circuit, "parameters", []), key=lambda p: p.name)
    if not params:
        return circuit.copy()
    values = {p: rng.uniform(0.0, 2.0 * math.pi) for p in params}
    try:
        return circuit.assign_parameters(values, inplace=False)
    except Exception:
        return circuit.bind_parameters(values)


def generate_workload(
    num_jobs: int,
    repetition_ratio: float,
    arrival_rate: float,
    seed: int,
    bursty: bool = False,
) -> List[Job]:
    rng = random.Random(seed)
    kinds = ["qaoa", "vqe", "qft", "ghz", "random"]
    reusable_templates = max(1, int(max(1.0, num_jobs * (1.0 - repetition_ratio)) / 8))
    templates: List[Tuple[str, Any]] = []
    for i in range(reusable_templates):
        kind = kinds[i % len(kinds)]
        nq = rng.choice([4, 5, 6, 7, 8])
        reps = rng.choice([1, 2, 3])
        templates.append((f"{kind}_{i}", make_template(kind, nq, reps, rng)))

    jobs: List[Job] = []
    now = 0.0
    for job_id in range(num_jobs):
        if bursty and job_id % 100 < 20:
            interarrival = rng.expovariate(arrival_rate * 4.0)
        else:
            interarrival = rng.expovariate(arrival_rate)
        now += interarrival

        if rng.random() < repetition_ratio:
            template_id, template = rng.choice(templates)
        else:
            kind = rng.choice(kinds)
            template_id = f"{kind}_unique_{job_id}"
            template = make_template(kind, rng.choice([4, 5, 6, 7, 8]), rng.choice([1, 2, 3]), rng)

        circuit = bind_random_parameters(template, rng)
        slack = rng.uniform(0.8, 5.0) + 0.015 * len(circuit.data) * rng.uniform(1.0, 2.0)
        shots = rng.choice([1024, 2048, 4096, 8192])
        jobs.append(
            Job(
                job_id=job_id,
                user_id=rng.randrange(1, 20),
                circuit=circuit,
                template_id=template_id,
                arrival_time=now,
                deadline=now + slack,
                shots=shots,
                fidelity_target=rng.uniform(0.3, 0.9),
                priority=rng.randrange(0, 3),
                template_hash=template_hash(circuit),
            )
        )
    return jobs
