from __future__ import annotations

from qcacheflow.scheduler.latency_first import LatencyFirstScheduler


class CacheUnawareScheduler(LatencyFirstScheduler):
    name = "cache-unaware"

