from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from qcacheflow.core.backend import BackendModel


@dataclass
class CacheLookup:
    state: str
    structural: Optional[Any] = None
    metadata: Optional[dict] = None
    template_hit: bool = False
    structural_hit: bool = False
    metadata_hit: bool = False
    metadata_stale: bool = False
    confidence: float = 1.0


class CompilerCache:
    def __init__(
        self,
        policy: str = "pass-level",
        template_capacity: Optional[int] = None,
        structural_capacity: Optional[int] = None,
        metadata_capacity: Optional[int] = None,
    ) -> None:
        self.policy = policy
        self.template_capacity = template_capacity
        self.structural_capacity = structural_capacity
        self.metadata_capacity = metadata_capacity
        self.allow_stale_metadata = False
        self.reuse_stale_metadata = False
        self.stale_confidence = 0.75
        self.template_cache: Dict[str, Any] = {}
        self.structural_cache: Dict[Tuple[str, str, str, str, int], Any] = {}
        self.metadata_cache: Dict[Tuple[str, str, int], dict] = {}
        self.lookups = 0
        self.hits = 0

    def structural_key(self, template_hash: str, backend: BackendModel, optimization_level: int) -> tuple:
        if self.policy == "whole-circuit":
            return (template_hash, backend.backend_id, "whole", "whole", optimization_level)
        return (
            template_hash,
            backend.backend_id,
            backend.topology_hash,
            backend.basis_gates_hash,
            optimization_level,
        )

    def metadata_key(self, template_hash: str, backend: BackendModel) -> tuple:
        return (template_hash, backend.backend_id, backend.calibration_epoch)

    def lookup(self, template_hash: str, backend: BackendModel, optimization_level: int) -> CacheLookup:
        self.lookups += 1
        result = self.peek(template_hash, backend, optimization_level)
        if result.state in {"full_hit", "partial_hit", "metadata_stale"}:
            self.hits += 1
        return result

    def peek(self, template_hash: str, backend: BackendModel, optimization_level: int) -> CacheLookup:
        if self.policy == "none":
            return CacheLookup("miss")
        skey = self.structural_key(template_hash, backend, optimization_level)
        mkey = self.metadata_key(template_hash, backend)
        structural = self.structural_cache.get(skey)
        metadata = self.metadata_cache.get(mkey)
        template_hit = template_hash in self.template_cache
        if structural is not None and metadata is not None:
            return CacheLookup("full_hit", structural, metadata, template_hit, True, True, False, 1.0)
        if structural is not None and self.reuse_stale_metadata:
            stale_metadata = self._latest_metadata(template_hash, backend.backend_id)
            if stale_metadata is not None:
                return CacheLookup("full_hit", structural, stale_metadata, template_hit, True, True, False, 1.0)
        if structural is not None and self.allow_stale_metadata:
            stale_metadata = self._latest_metadata(template_hash, backend.backend_id)
            if stale_metadata is not None:
                return CacheLookup("metadata_stale", structural, stale_metadata, template_hit, True, True, True, self.stale_confidence)
        if structural is not None and self._latest_metadata(template_hash, backend.backend_id) is not None:
            return CacheLookup("metadata_stale", structural, None, template_hit, True, False, True, 1.0)
        if structural is not None:
            return CacheLookup("partial_hit", structural, None, template_hit, True, False)
        if self.policy == "pass-level":
            reusable = self.template_cache.get(template_hash)
            if reusable is not None:
                return CacheLookup("partial_hit", reusable, None, True, False, False)
        if template_hit:
            return CacheLookup("metadata_stale", None, metadata, True, False, metadata is not None, metadata is None)
        return CacheLookup("miss", template_hit=False)

    def store(self, template_hash: str, backend: BackendModel, optimization_level: int, structural: Any, metadata: dict) -> None:
        if self.policy == "none":
            return
        self.template_cache[template_hash] = structural
        self._enforce_capacity(self.template_cache, self.template_capacity)
        self.structural_cache[self.structural_key(template_hash, backend, optimization_level)] = structural
        self._enforce_capacity(self.structural_cache, self.structural_capacity)
        self.metadata_cache[self.metadata_key(template_hash, backend)] = metadata
        self._enforce_capacity(self.metadata_cache, self.metadata_capacity)

    def invalidate_backend_full(self, backend_id: str) -> None:
        self.structural_cache = {k: v for k, v in self.structural_cache.items() if k[1] != backend_id}
        self.metadata_cache = {k: v for k, v in self.metadata_cache.items() if k[1] != backend_id}

    def invalidate_backend_metadata(self, backend_id: str) -> None:
        self.metadata_cache = {k: v for k, v in self.metadata_cache.items() if k[1] != backend_id}

    @property
    def hit_rate(self) -> float:
        return self.hits / self.lookups if self.lookups else 0.0

    def _latest_metadata(self, template_hash: str, backend_id: str) -> Optional[dict]:
        candidates = [
            (epoch, value)
            for (thash, bid, epoch), value in self.metadata_cache.items()
            if thash == template_hash and bid == backend_id
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda item: item[0])[1]

    def _enforce_capacity(self, cache: Dict[Any, Any], capacity: Optional[int]) -> None:
        if capacity is None or capacity <= 0:
            return
        while len(cache) > capacity:
            oldest = next(iter(cache))
            del cache[oldest]
