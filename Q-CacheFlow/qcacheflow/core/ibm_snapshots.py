from __future__ import annotations

import importlib.util
import json
import os
from dataclasses import dataclass
from pathlib import Path
from statistics import mean, median
from typing import Iterable

from qcacheflow.core.backend import BackendModel


DEFAULT_SNAPSHOT_BACKENDS = ["manila", "jakarta", "lagos", "guadalupe", "hanoi"]


@dataclass(frozen=True)
class IBMSnapshotSummary:
    snapshot: str
    backend_name: str
    n_qubits: int
    coupling_edges: int
    basis_gates: str
    last_update_date: str
    one_qubit_error_median: float
    two_qubit_error_median: float
    readout_error_mean: float
    one_qubit_duration_ns_median: float
    two_qubit_duration_ns_median: float


def default_snapshot_root() -> Path | None:
    override = os.environ.get("QCACHEFLOW_IBM_SNAPSHOT_ROOT")
    if override:
        return Path(override)
    spec = importlib.util.find_spec("qiskit_ibm_runtime")
    if spec is None or spec.submodule_search_locations is None:
        return None
    root = Path(next(iter(spec.submodule_search_locations))) / "fake_provider" / "backends"
    return root if root.exists() else None


def available_snapshots(root: Path | None = None) -> list[str]:
    root = root or default_snapshot_root()
    if root is None or not root.exists():
        return []
    names = []
    for child in root.iterdir():
        if not child.is_dir():
            continue
        if (child / f"conf_{child.name}.json").exists() and (child / f"props_{child.name}.json").exists():
            names.append(child.name)
    return sorted(names)


def load_ibm_snapshot_backends(
    names: Iterable[str] | None = None,
    *,
    root: Path | None = None,
    limit: int | None = None,
) -> tuple[list[BackendModel], list[IBMSnapshotSummary]]:
    root = root or default_snapshot_root()
    if root is None or not root.exists():
        raise FileNotFoundError(
            "IBM fake backend snapshots not found. Install qiskit-ibm-runtime or set QCACHEFLOW_IBM_SNAPSHOT_ROOT."
        )
    selected = list(names or DEFAULT_SNAPSHOT_BACKENDS)
    if limit is not None:
        selected = selected[:limit]
    backends: list[BackendModel] = []
    summaries: list[IBMSnapshotSummary] = []
    for idx, name in enumerate(selected):
        conf_path = root / name / f"conf_{name}.json"
        props_path = root / name / f"props_{name}.json"
        if not conf_path.exists() or not props_path.exists():
            raise FileNotFoundError(f"Missing IBM fake backend snapshot files for {name!r} under {root}")
        conf = json.loads(conf_path.read_text(encoding="utf-8"))
        props = json.loads(props_path.read_text(encoding="utf-8"))
        backend, summary = _snapshot_to_backend(name, idx, conf, props)
        backends.append(backend)
        summaries.append(summary)
    return backends, summaries


def _snapshot_to_backend(name: str, idx: int, conf: dict, props: dict) -> tuple[BackendModel, IBMSnapshotSummary]:
    gates = props.get("gates", [])
    one_qubit_gates = [gate for gate in gates if len(gate.get("qubits", [])) == 1 and gate.get("gate") in {"id", "sx", "x"}]
    two_qubit_gates = [gate for gate in gates if len(gate.get("qubits", [])) == 2 and gate.get("gate") in {"cx", "ecr"}]
    one_errors = _gate_param_values(one_qubit_gates, "gate_error")
    two_errors = _gate_param_values(two_qubit_gates, "gate_error")
    one_lengths = _gate_param_values(one_qubit_gates, "gate_length")
    two_lengths = _gate_param_values(two_qubit_gates, "gate_length")
    readout_errors = _qubit_param_values(props.get("qubits", []), "readout_error")

    one_error = _median_or(one_errors, 0.001)
    two_error = _median_or(two_errors, min(0.20, one_error * 4.0))
    readout_error = mean(readout_errors) if readout_errors else 0.03
    one_duration_ns = _median_or(one_lengths, 50.0)
    two_duration_ns = _median_or(two_lengths, one_duration_ns * 8.0)
    fixed_overhead = _median_or(_qubit_param_values(props.get("qubits", []), "readout_length"), 1000.0) * 1e-9

    coupling_map = [tuple(edge) for edge in conf.get("coupling_map", []) if len(edge) == 2]
    basis_gates = list(conf.get("basis_gates", ["id", "rz", "sx", "x", "cx"]))
    backend_name = conf.get("backend_name", name)
    backend = BackendModel(
        backend_id=f"ibm_{name}_{idx}",
        num_qubits=int(conf.get("n_qubits", len(props.get("qubits", [])) or 1)),
        coupling_map=coupling_map,
        basis_gates=basis_gates,
        gate_error_rate=one_error,
        readout_error_rate=readout_error,
        gate_duration=one_duration_ns * 1e-9,
        fixed_overhead=fixed_overhead,
        two_qubit_gate_error_rate=two_error,
        two_qubit_gate_duration=two_duration_ns * 1e-9,
    )
    summary = IBMSnapshotSummary(
        snapshot=name,
        backend_name=backend_name,
        n_qubits=backend.num_qubits,
        coupling_edges=len(coupling_map),
        basis_gates=";".join(basis_gates),
        last_update_date=str(props.get("last_update_date", "")),
        one_qubit_error_median=one_error,
        two_qubit_error_median=two_error,
        readout_error_mean=readout_error,
        one_qubit_duration_ns_median=one_duration_ns,
        two_qubit_duration_ns_median=two_duration_ns,
    )
    return backend, summary


def _gate_param_values(gates: Iterable[dict], name: str) -> list[float]:
    values: list[float] = []
    for gate in gates:
        for param in gate.get("parameters", []):
            if param.get("name") == name and isinstance(param.get("value"), (int, float)):
                values.append(float(param["value"]))
    return values


def _qubit_param_values(qubits: Iterable[list[dict]], name: str) -> list[float]:
    values: list[float] = []
    for qubit in qubits:
        for param in qubit:
            if param.get("name") == name and isinstance(param.get("value"), (int, float)):
                values.append(float(param["value"]))
    return values


def _median_or(values: list[float], fallback: float) -> float:
    return float(median(values)) if values else fallback
