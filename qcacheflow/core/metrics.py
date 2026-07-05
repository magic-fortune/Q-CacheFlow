from __future__ import annotations

import csv
from dataclasses import asdict
from pathlib import Path
from statistics import mean
from typing import Iterable, List, Mapping

from qcacheflow.core.job import JobResult


def percentile(values: List[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, int(round((pct / 100.0) * (len(ordered) - 1))))
    return ordered[idx]


def summarize_results(results: Iterable[JobResult]) -> dict:
    rows = list(results)
    if not rows:
        return {}
    turnaround = [r.turnaround_time for r in rows]
    accepted_rows = [r for r in rows if r.accepted and not r.rejected]
    cache_hits = [r for r in rows if r.cache_state in {"full_hit", "partial_hit", "metadata_stale"}]
    total_compile = [r.compile_time for r in rows]
    saved = [r.compile_time_saved for r in rows]
    utilization = {}
    user_goodput = {}
    user_total = {}
    horizon = max(r.finish_time for r in rows) or 1.0
    for r in rows:
        utilization.setdefault(r.backend_id, 0.0)
        utilization[r.backend_id] += r.execution_time
        user_id = r.job_id % 20
        user_total[user_id] = user_total.get(user_id, 0) + 1
        user_goodput[user_id] = user_goodput.get(user_id, 0) + int(r.slo_met)
    user_rates = [user_goodput.get(u, 0) / total for u, total in user_total.items()]
    return {
        "jobs": len(rows),
        "accepted_jobs": len(accepted_rows),
        "rejected_jobs": sum(r.rejected for r in rows),
        "admission_reject_ratio": sum(r.rejected for r in rows) / len(rows),
        "average_turnaround_time": mean(turnaround),
        "p95_turnaround_time": percentile(turnaround, 95),
        "deadline_miss_ratio": sum(r.deadline_miss for r in rows) / len(rows),
        "fidelity_target_violation_ratio": sum(r.fidelity_violation for r in rows) / len(rows),
        "slo_goodput": sum(r.slo_met for r in rows) / len(rows),
        "cache_hit_rate": len(cache_hits) / len(rows),
        "average_compile_time": mean(total_compile),
        "compilation_time_saved": sum(saved),
        "backend_utilization": mean([v / horizon for v in utilization.values()]) if utilization else 0.0,
        "batch_ratio": sum(1 for r in rows if r.batch_id >= 0) / len(rows),
        "template_hit_rate": sum(r.template_hit for r in rows) / len(rows),
        "structural_hit_rate": sum(r.structural_hit for r in rows) / len(rows),
        "metadata_hit_rate": sum(r.metadata_hit for r in rows) / len(rows),
        "fairness_jain": jain_index(user_rates),
    }


def jain_index(values: List[float]) -> float:
    if not values:
        return 0.0
    denom = len(values) * sum(v * v for v in values)
    if denom == 0.0:
        return 0.0
    return (sum(values) ** 2) / denom


def write_job_results(path: str | Path, rows: Iterable[JobResult]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = [asdict(r) for r in rows]
    if not data:
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(data[0].keys()))
        writer.writeheader()
        writer.writerows(data)


def write_summary(path: str | Path, rows: Iterable[Mapping[str, object]]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = list(rows)
    if not data:
        return
    fields = sorted({key for row in data for key in row.keys()})
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(data)
