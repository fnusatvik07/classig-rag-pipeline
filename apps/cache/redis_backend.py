"""
Redis cache backend.

Stores all 3 cache tiers in Redis.
Production-grade, in-memory, fast.
Requires a running Redis instance (see docker-compose.yml).

Key design decisions:
- Tier 1 (exact): Redis hash per entry, keyed by query hash
- Tier 2/3 (semantic/retrieval): Embeddings stored as bytes in Redis,
  loaded into Python for cosine similarity (Redis doesn't have native
  vector similarity without RediSearch module)
- Native TTL via Redis EXPIRE on all keys
- Connection pooling via redis-py
"""

import json
import time
import uuid
from typing import Optional

import numpy as np
import redis

from apps.config import REDIS_URL
from .base import CacheBackend
from .embeddings import (
    cosine_similarity,
    embedding_to_bytes,
    bytes_to_embedding,
)

# Key prefixes
_EXACT_PREFIX = "cache:exact:"
_SEMANTIC_PREFIX = "cache:semantic:"
_RETRIEVAL_PREFIX = "cache:retrieval:"
_SEMANTIC_INDEX = "cache:semantic:index"
_RETRIEVAL_INDEX = "cache:retrieval:index"
_DOC_VERSION_KEY = "cache:metadata:doc_version"
_DOC_HASH_PREFIX = "doc:hash:"
_DOC_HASH_INDEX = "doc:hash:index"


class RedisCacheBackend(CacheBackend):
    """Redis-based implementation of the 3-tier cache."""

    def __init__(self, redis_url: str | None = None):
        self._redis = redis.from_url(
            redis_url or REDIS_URL,
            decode_responses=False,  # we handle bytes manually for embeddings
        )
        # Initialize doc_version if not set
        if self._redis.get(_DOC_VERSION_KEY) is None:
            self._redis.set(_DOC_VERSION_KEY, b"0")

    def _str(self, val: bytes | str | None) -> str:
        """Safely decode bytes to str."""
        if val is None:
            return ""
        if isinstance(val, bytes):
            return val.decode("utf-8")
        return val

    # ── Tier 1: Exact Cache ────────────────────────────────────

    def get_exact(self, query_hash: str) -> Optional[dict]:
        key = f"{_EXACT_PREFIX}{query_hash}"
        data = self._redis.get(key)
        if data is None:
            return None

        entry = json.loads(data)

        # Check doc version
        current_version = self.get_doc_version()
        if entry.get("doc_version", 0) < current_version:
            self._redis.delete(key)
            return None

        # Update hit stats
        entry["hit_count"] = entry.get("hit_count", 0) + 1
        entry["last_hit_at"] = time.time()
        # Re-store with remaining TTL preserved
        ttl = self._redis.ttl(key)
        if ttl and ttl > 0:
            self._redis.setex(key, ttl, json.dumps(entry).encode("utf-8"))

        return {
            "question": entry["question"],
            "answer": entry["answer"],
            "sources_json": entry["sources_json"],
        }

    def set_exact(
        self,
        query_hash: str,
        question: str,
        answer: str,
        sources_json: str,
        doc_version: int,
        ttl_seconds: int,
    ) -> None:
        key = f"{_EXACT_PREFIX}{query_hash}"
        entry = {
            "question": question,
            "answer": answer,
            "sources_json": sources_json,
            "doc_version": doc_version,
            "created_at": time.time(),
            "hit_count": 0,
            "last_hit_at": None,
        }
        self._redis.setex(key, ttl_seconds, json.dumps(entry).encode("utf-8"))

    # ── Tier 2: Semantic Cache ─────────────────────────────────

    def get_semantic(
        self, embedding: list[float], threshold: float
    ) -> Optional[dict]:
        current_version = self.get_doc_version()

        # Get all semantic cache entry IDs
        member_ids = self._redis.smembers(_SEMANTIC_INDEX)
        if not member_ids:
            return None

        best_match = None
        best_similarity = 0.0
        best_key = None

        for member_id in member_ids:
            key = f"{_SEMANTIC_PREFIX}{self._str(member_id)}"
            data = self._redis.get(key)
            if data is None:
                # Key expired, remove from index
                self._redis.srem(_SEMANTIC_INDEX, member_id)
                continue

            entry = json.loads(data)

            # Check doc version
            if entry.get("doc_version", 0) < current_version:
                self._redis.delete(key)
                self._redis.srem(_SEMANTIC_INDEX, member_id)
                continue

            cached_embedding = bytes_to_embedding(
                bytes.fromhex(entry["embedding_hex"])
            )
            sim = cosine_similarity(embedding, cached_embedding)

            if sim >= threshold and sim > best_similarity:
                best_similarity = sim
                best_match = entry
                best_key = key

        if best_match is None:
            return None

        # Update hit stats
        best_match["hit_count"] = best_match.get("hit_count", 0) + 1
        best_match["last_hit_at"] = time.time()
        ttl = self._redis.ttl(best_key)
        if ttl and ttl > 0:
            self._redis.setex(best_key, ttl, json.dumps(best_match).encode("utf-8"))

        return {
            "question": best_match["question"],
            "answer": best_match["answer"],
            "sources_json": best_match["sources_json"],
            "similarity": best_similarity,
        }

    def set_semantic(
        self,
        question: str,
        embedding: list[float],
        answer: str,
        sources_json: str,
        doc_version: int,
        ttl_seconds: int,
    ) -> None:
        entry_id = uuid.uuid4().hex
        key = f"{_SEMANTIC_PREFIX}{entry_id}"
        entry = {
            "question": question,
            "embedding_hex": embedding_to_bytes(embedding).hex(),
            "answer": answer,
            "sources_json": sources_json,
            "doc_version": doc_version,
            "created_at": time.time(),
            "hit_count": 0,
            "last_hit_at": None,
        }
        self._redis.setex(key, ttl_seconds, json.dumps(entry).encode("utf-8"))
        self._redis.sadd(_SEMANTIC_INDEX, entry_id.encode("utf-8"))

    # ── Tier 3: Retrieval Cache ────────────────────────────────

    def get_retrieval(
        self, embedding: list[float], threshold: float
    ) -> Optional[dict]:
        current_version = self.get_doc_version()

        member_ids = self._redis.smembers(_RETRIEVAL_INDEX)
        if not member_ids:
            return None

        best_match = None
        best_similarity = 0.0
        best_key = None

        for member_id in member_ids:
            key = f"{_RETRIEVAL_PREFIX}{self._str(member_id)}"
            data = self._redis.get(key)
            if data is None:
                self._redis.srem(_RETRIEVAL_INDEX, member_id)
                continue

            entry = json.loads(data)

            if entry.get("doc_version", 0) < current_version:
                self._redis.delete(key)
                self._redis.srem(_RETRIEVAL_INDEX, member_id)
                continue

            cached_embedding = bytes_to_embedding(
                bytes.fromhex(entry["embedding_hex"])
            )
            sim = cosine_similarity(embedding, cached_embedding)

            if sim >= threshold and sim > best_similarity:
                best_similarity = sim
                best_match = entry
                best_key = key

        if best_match is None:
            return None

        # Update hit stats
        best_match["hit_count"] = best_match.get("hit_count", 0) + 1
        best_match["last_hit_at"] = time.time()
        ttl = self._redis.ttl(best_key)
        if ttl and ttl > 0:
            self._redis.setex(best_key, ttl, json.dumps(best_match).encode("utf-8"))

        return {
            "question": best_match["question"],
            "chunks_json": best_match["chunks_json"],
            "similarity": best_similarity,
        }

    def set_retrieval(
        self,
        question: str,
        embedding: list[float],
        chunks_json: str,
        doc_version: int,
        ttl_seconds: int,
    ) -> None:
        entry_id = uuid.uuid4().hex
        key = f"{_RETRIEVAL_PREFIX}{entry_id}"
        entry = {
            "question": question,
            "embedding_hex": embedding_to_bytes(embedding).hex(),
            "chunks_json": chunks_json,
            "doc_version": doc_version,
            "created_at": time.time(),
            "hit_count": 0,
            "last_hit_at": None,
        }
        self._redis.setex(key, ttl_seconds, json.dumps(entry).encode("utf-8"))
        self._redis.sadd(_RETRIEVAL_INDEX, entry_id.encode("utf-8"))

    # ── Management ─────────────────────────────────────────────

    def get_doc_version(self) -> int:
        val = self._redis.get(_DOC_VERSION_KEY)
        return int(val) if val else 0

    def bump_doc_version(self) -> int:
        return int(self._redis.incr(_DOC_VERSION_KEY))

    def clear_all(self) -> dict:
        counts = {"exact": 0, "semantic": 0, "retrieval": 0}

        # Clear exact cache
        cursor = 0
        while True:
            cursor, keys = self._redis.scan(cursor, match=f"{_EXACT_PREFIX}*")
            if keys:
                counts["exact"] += len(keys)
                self._redis.delete(*keys)
            if cursor == 0:
                break

        # Clear semantic cache
        member_ids = self._redis.smembers(_SEMANTIC_INDEX)
        for member_id in member_ids:
            key = f"{_SEMANTIC_PREFIX}{self._str(member_id)}"
            self._redis.delete(key)
        counts["semantic"] = len(member_ids)
        self._redis.delete(_SEMANTIC_INDEX)

        # Clear retrieval cache
        member_ids = self._redis.smembers(_RETRIEVAL_INDEX)
        for member_id in member_ids:
            key = f"{_RETRIEVAL_PREFIX}{self._str(member_id)}"
            self._redis.delete(key)
        counts["retrieval"] = len(member_ids)
        self._redis.delete(_RETRIEVAL_INDEX)

        return counts

    def get_stats(self) -> dict:
        def _count_and_hits(index_key: str, prefix: str) -> dict:
            member_ids = self._redis.smembers(index_key)
            entries = 0
            total_hits = 0
            for member_id in member_ids:
                key = f"{prefix}{self._str(member_id)}"
                data = self._redis.get(key)
                if data is not None:
                    entries += 1
                    entry = json.loads(data)
                    total_hits += entry.get("hit_count", 0)
            return {"entries": entries, "total_hits": total_hits}

        # Count exact cache entries
        exact_entries = 0
        exact_hits = 0
        cursor = 0
        while True:
            cursor, keys = self._redis.scan(cursor, match=f"{_EXACT_PREFIX}*")
            for key in keys:
                data = self._redis.get(key)
                if data:
                    exact_entries += 1
                    entry = json.loads(data)
                    exact_hits += entry.get("hit_count", 0)
            if cursor == 0:
                break

        return {
            "backend": "redis",
            "redis_url": REDIS_URL,
            "doc_version": self.get_doc_version(),
            "exact": {"entries": exact_entries, "total_hits": exact_hits},
            "semantic": _count_and_hits(_SEMANTIC_INDEX, _SEMANTIC_PREFIX),
            "retrieval": _count_and_hits(_RETRIEVAL_INDEX, _RETRIEVAL_PREFIX),
        }

    def cleanup_expired(self) -> int:
        """Redis handles TTL expiry natively — just clean up stale index entries."""
        removed = 0

        for index_key, prefix in [
            (_SEMANTIC_INDEX, _SEMANTIC_PREFIX),
            (_RETRIEVAL_INDEX, _RETRIEVAL_PREFIX),
        ]:
            member_ids = self._redis.smembers(index_key)
            for member_id in member_ids:
                key = f"{prefix}{self._str(member_id)}"
                if not self._redis.exists(key):
                    self._redis.srem(index_key, member_id)
                    removed += 1

        return removed

    # ── Document Hash Deduplication ──────────────────────────────

    def get_document_hash(self, file_hash: str) -> Optional[dict]:
        key = f"{_DOC_HASH_PREFIX}{file_hash}"
        data = self._redis.get(key)
        if data is None:
            return None
        return json.loads(data)

    def set_document_hash(self, file_hash: str, metadata: dict) -> None:
        key = f"{_DOC_HASH_PREFIX}{file_hash}"
        self._redis.set(key, json.dumps(metadata).encode("utf-8"))
        self._redis.sadd(_DOC_HASH_INDEX, file_hash.encode("utf-8"))

    def clear_document_hashes(self) -> int:
        member_ids = self._redis.smembers(_DOC_HASH_INDEX)
        count = 0
        for member_id in member_ids:
            key = f"{_DOC_HASH_PREFIX}{self._str(member_id)}"
            self._redis.delete(key)
            count += 1
        self._redis.delete(_DOC_HASH_INDEX)
        return count
