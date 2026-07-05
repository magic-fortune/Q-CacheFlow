from __future__ import annotations

from qcacheflow.pipeline.slo_scheduler import SLOAwareQCacheFlowScheduler


class QCacheFlowScheduler(SLOAwareQCacheFlowScheduler):
    name = "qcacheflow"
