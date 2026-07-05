from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CircuitProfile:
    num_qubits: int
    num_gates: int
    depth: int
    two_qubit_gate_count: int
    parameter_count: int
    template_hash: str


def _operation_name(instruction: Any) -> str:
    operation = getattr(instruction, "operation", None)
    if operation is not None:
        return operation.name
    return instruction[0].name


def _instruction_qubits(instruction: Any) -> Any:
    if hasattr(instruction, "qubits"):
        return instruction.qubits
    return instruction[1]


def _instruction_clbits(instruction: Any) -> Any:
    if hasattr(instruction, "clbits"):
        return instruction.clbits
    return instruction[2] if len(instruction) > 2 else []


def _qubit_index(circuit: Any, qubit: Any) -> int:
    if isinstance(qubit, int):
        return qubit
    try:
        return circuit.find_bit(qubit).index
    except Exception:
        return getattr(qubit, "index", 0)


def template_hash(circuit: Any) -> str:
    parts = [f"q={circuit.num_qubits}"]
    for item in circuit.data:
        op = _operation_name(item)
        qubits = _instruction_qubits(item)
        clbits = _instruction_clbits(item)
        qidx = tuple(_qubit_index(circuit, q) for q in qubits)
        parts.append(f"{op}:{qidx}:c{len(clbits)}")
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:20]


def profile_circuit(circuit: Any) -> CircuitProfile:
    two_qubit = 0
    for item in circuit.data:
        qubits = _instruction_qubits(item)
        if len(qubits) == 2:
            two_qubit += 1
    return CircuitProfile(
        num_qubits=circuit.num_qubits,
        num_gates=len(circuit.data),
        depth=int(circuit.depth() or 0),
        two_qubit_gate_count=two_qubit,
        parameter_count=len(getattr(circuit, "parameters", [])),
        template_hash=template_hash(circuit),
    )
