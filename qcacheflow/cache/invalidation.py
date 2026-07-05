from __future__ import annotations

from qcacheflow.cache.compiler_cache import CompilerCache
from qcacheflow.core.backend import BackendModel


def apply_calibration_update(cache: CompilerCache, backend: BackendModel, policy: str) -> None:
    if policy == "full":
        cache.allow_stale_metadata = False
        cache.reuse_stale_metadata = False
        cache.invalidate_backend_full(backend.backend_id)
    elif policy == "soft":
        cache.allow_stale_metadata = True
        cache.reuse_stale_metadata = False
    elif policy == "none":
        cache.allow_stale_metadata = False
        cache.reuse_stale_metadata = True
        return
    else:
        raise ValueError(f"Unknown invalidation policy: {policy}")
