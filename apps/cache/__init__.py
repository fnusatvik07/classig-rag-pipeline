"""
Cache package — 3-tier caching for the RAG pipeline.

Usage:
    from apps.cache import get_cache_backend
    cache = get_cache_backend()     # returns SQLite or Redis based on config
    cache.get_exact(query_hash)     # Tier 1
    cache.get_semantic(embedding)   # Tier 2
    cache.get_retrieval(embedding)  # Tier 3

Switch backend via CACHE_BACKEND env var ("sqlite" or "redis").
"""

from apps.config import CACHE_BACKEND
from .base import CacheBackend

# Singleton instance — created on first call, reused after
_backend_instance: CacheBackend | None = None


def get_cache_backend() -> CacheBackend:
    """Get the configured cache backend (singleton).

    Returns SQLiteCacheBackend or RedisCacheBackend based on
    the CACHE_BACKEND config setting.
    """
    global _backend_instance

    if _backend_instance is not None:
        return _backend_instance

    if CACHE_BACKEND == "redis":
        from .redis_backend import RedisCacheBackend
        _backend_instance = RedisCacheBackend()
    else:
        from .sqlite_backend import SQLiteCacheBackend
        _backend_instance = SQLiteCacheBackend()

    return _backend_instance


def reset_cache_backend() -> None:
    """Reset the singleton (useful for testing or backend switch)."""
    global _backend_instance
    _backend_instance = None
