# Caching System — Implementation Changelog

> This file tracks every change made during the `rag-caching` branch.
> Read this to understand what was built, why, and how it all connects.

---

## Overview

**Branch**: `rag-caching`
**Goal**: Add a 3-tier caching layer (Exact → Semantic → Retrieval) to the RAG pipeline with swappable backends (SQLite / Redis via Docker).

### Architecture Concept

Before running the expensive RAG pipeline (Pinecone retrieval + reranking + LLM generation), we check 3 cache tiers. Each tier catches a different kind of redundancy:

```
User Question
     │
     ▼
┌─────────────────────┐
│ Tier 1: Exact Cache  │  hash(normalize(query)) → O(1) lookup
└────────┬────────────┘
         │ miss
         ▼
┌─────────────────────┐
│ Tier 2: Semantic     │  embed(query) → cosine similarity ≥ 0.95
└────────┬────────────┘
         │ miss
         ▼
┌─────────────────────┐
│ Tier 3: Retrieval    │  embed(query) → cached chunks (still calls LLM)
└────────┬────────────┘
         │ miss
         ▼
   Full RAG Pipeline → Store in all 3 tiers
```

| Tier | Catches | Example | Saves |
|------|---------|---------|-------|
| Exact | Same question repeated | "What was Apple's revenue?" → same hash | LLM + Pinecone + reranker |
| Semantic | Rephrasings | "Apple revenues?" ≈ "What was Apple's revenue?" | LLM + Pinecone + reranker |
| Retrieval | Same context needed | Different question, same chunks | Pinecone + reranker (still calls LLM) |

### Cache Invalidation (3 mechanisms)

1. **TTL-based** — entries expire after configurable time (7 days exact/semantic, 1 day retrieval)
2. **Version tagging** — each entry stores a `doc_version`; when new docs are ingested, version bumps and stale entries are skipped
3. **Manual clear** — `POST /cache/clear` endpoint wipes all tiers

### Backend Toggle

```
CACHE_BACKEND=sqlite   →  SQLite file at data/rag_cache.db (zero infra)
CACHE_BACKEND=redis    →  Redis via Docker (production-grade)
```

Both implement the same `CacheBackend` abstract interface. Swap with one env var.

---

## File-by-File Changes

### New Files Created (7)

#### `apps/cache/__init__.py` — Factory
- `get_cache_backend()` — singleton factory, returns SQLite or Redis backend based on `CACHE_BACKEND` config
- `reset_cache_backend()` — resets singleton (for testing)
- Lazy imports to avoid loading unused backend

#### `apps/cache/base.py` — Abstract Interface
- `CacheBackend` ABC with methods for all 3 tiers:
  - `get_exact() / set_exact()` — Tier 1
  - `get_semantic() / set_semantic()` — Tier 2
  - `get_retrieval() / set_retrieval()` — Tier 3
  - `get_doc_version() / bump_doc_version()` — version management
  - `clear_all()` — wipe all tiers
  - `get_stats()` — per-tier counts and hit stats
  - `cleanup_expired()` — remove TTL-expired entries
- **Key concept**: Any new backend (e.g., PostgreSQL, DynamoDB) just needs to implement this interface

#### `apps/cache/embeddings.py` — Shared Utilities
- `embed_query(text)` — generates 1536-dim vector via OpenAI `text-embedding-3-small` (~$0.00002/query)
- `normalize_query(text)` — lowercase, strip, collapse whitespace, remove trailing punctuation
- `hash_query(text)` — SHA256 hex digest for Tier 1 keys
- `cosine_similarity(a, b)` — numpy dot product, returns float [-1, 1]
- `embedding_to_bytes() / bytes_to_embedding()` — serialize numpy float32 arrays for storage
- **Key concept**: Lazy singleton for the OpenAI embeddings client (created on first call)

#### `apps/cache/sqlite_backend.py` — SQLite Implementation
- Creates `data/rag_cache.db` with WAL mode (concurrent reads)
- 4 tables: `cache_metadata`, `exact_cache`, `semantic_cache`, `retrieval_cache`
- Embeddings stored as BLOB (numpy float32 bytes)
- Semantic/retrieval lookup: loads all entries, computes cosine similarity in Python
- Hit tracking: `hit_count` and `last_hit_at` updated on every cache hit
- Thread-safe: new connection per operation
- **Key concept**: For <100K entries, loading all embeddings and doing numpy cosine sim is fast enough (~milliseconds)

#### `apps/cache/redis_backend.py` — Redis Implementation
- Connects via `redis-py` with configurable `REDIS_URL`
- Tier 1: `cache:exact:<hash>` keys with JSON values + Redis native TTL via `SETEX`
- Tier 2/3: entries stored as JSON with embedding as hex bytes; Redis SETs track all entry IDs for iteration
- Embeddings stored as hex-encoded bytes in JSON (Redis doesn't support binary in JSON natively)
- `cleanup_expired()` removes orphaned index entries (Redis handles actual key expiry natively)
- **Key concept**: Redis handles TTL automatically, but we still need to clean up the SET indexes when keys expire

#### `docker-compose.yml` — Redis + RedisInsight
- `redis:7-alpine` image (lightweight, ~30MB) on port 6379
- `redis/redisinsight:latest` web UI on port 5540
- Persistent volume `redis_data`, health check via `redis-cli ping`
- `docker compose up -d` to start, `docker compose down` to stop

#### `PLAN.md` — Master Plan
- Full architecture documentation
- Database schemas (SQLite + Redis)
- API contract changes
- Verification plan
- Future phases (router, memory, observability)

---

### Modified Files (4)

#### `apps/config.py`
**Added constants:**
- `BASE_DIR` — project root path (used by DATABASE_PATH)
- `CACHE_BACKEND` — "sqlite" or "redis" (default: sqlite)
- `CACHE_ENABLED` — master on/off (default: true)
- `EXACT_CACHE_TTL` — 604800 seconds (7 days)
- `SEMANTIC_CACHE_TTL` — 604800 seconds (7 days)
- `SEMANTIC_CACHE_THRESHOLD` — 0.95 cosine similarity
- `RETRIEVAL_CACHE_TTL` — 86400 seconds (1 day)
- `RETRIEVAL_CACHE_THRESHOLD` — 0.90 cosine similarity
- `DATABASE_PATH` — `data/rag_cache.db`
- `REDIS_URL` — `redis://localhost:6379/0`
- `OPENAI_EMBED_MODEL` — `text-embedding-3-small`

#### `apps/api.py`
**Major rewrite of the chat endpoint. Changes:**

1. **Lifespan handler** — runs `cleanup_expired()` on startup
2. **`ChatResponse` model** — added `cache_hit: bool`, `cache_tier: Optional[str]`, and `response_time_ms: Optional[float]` (backward compatible, all default to False/None)
3. **`chat_endpoint`** — new flow (timed with `time.time()` for `response_time_ms`):
   - Check Tier 1 (exact hash) → return if hit
   - Embed query → check Tier 2 (semantic cosine) → return if hit
   - Check Tier 3 (retrieval cosine) → if hit, call LLM with cached chunks, promote to Tier 1+2
   - On full miss: run pipeline, store in all 3 tiers
4. **`ingest_endpoint` / `upload_endpoint`** — call `cache.bump_doc_version()` after ingestion to invalidate stale cache entries
5. **New endpoints:**
   - `POST /cache/clear` — clears all 3 tiers, returns `{cleared: {exact: N, semantic: N, retrieval: N}}`
   - `GET /cache/stats` — returns per-tier entry counts, hit counts, backend type, doc version
6. **Helper functions** — `_sources_to_json()` and `_json_to_sources()` for serializing SourceChunk lists
7. **Version bumped** — 0.1.0 → 0.2.0

#### `pyproject.toml`
**Added dependencies:**
- `numpy>=1.26.0` — cosine similarity computation, embedding serialization
- `redis>=5.0.0` — Redis client for Redis backend

#### `frontend/vite.config.js`
**Added proxy rule:**
- `/cache` → `http://localhost:8000` (for cache stats/clear endpoints)

#### `.env`
**Added variables:**
```
CACHE_BACKEND=sqlite
CACHE_ENABLED=true
REDIS_URL=redis://localhost:6379/0
```

---

## New API Endpoints

### `GET /cache/stats`
Returns per-tier cache statistics.
```json
{
  "backend": "sqlite",
  "db_path": "data/rag_cache.db",
  "doc_version": 0,
  "exact":     { "entries": 5, "total_hits": 12 },
  "semantic":  { "entries": 5, "total_hits": 3 },
  "retrieval": { "entries": 5, "total_hits": 1 }
}
```

### `POST /cache/clear`
Clears all cache tiers.
```json
{
  "message": "Cache cleared successfully",
  "cleared": { "exact": 5, "semantic": 5, "retrieval": 5 }
}
```

### Updated `POST /chat` response
Three new fields (backward compatible):
```json
{
  "answer": "...",
  "sources": [...],
  "cache_hit": true,
  "cache_tier": "semantic",
  "response_time_ms": 42.17
}
```

`response_time_ms` shows how long the entire `/chat` request took in milliseconds. This makes the cache benefit visible:

| Scenario | Typical `response_time_ms` |
|----------|---------------------------|
| Full pipeline (cache miss) | 3000–8000 ms |
| Tier 3 retrieval hit (skip Pinecone, still calls LLM) | 2000–4000 ms |
| Tier 2 semantic hit | 50–200 ms |
| Tier 1 exact hit | 1–10 ms |

---

## Things to Review / Understand

### 1. The `CacheBackend` Abstract Class Pattern
Both SQLite and Redis implement the same interface defined in `base.py`. This is the **Strategy Pattern** — the algorithm (cache lookup/store) is the same, but the storage mechanism varies. The factory in `__init__.py` picks the right one based on config.

### 2. Embedding Cost
Every cache MISS on Tier 1 triggers an OpenAI embedding call (~$0.00002). This is the "cost of caching" — you pay a tiny embedding cost to potentially save a much larger LLM call cost.

### 3. Why Tier 3 Still Calls LLM
Tier 3 caches the *retrieved chunks*, not the answer. This is useful when different questions need the same context. The LLM still generates a fresh answer tailored to the specific question, but we skip the expensive Pinecone retrieval + reranking step.

### 4. Cache Promotion
When Tier 3 hits, we generate an answer and then "promote" the result into Tier 1 + 2. Next time the same or similar question is asked, it'll be a faster Tier 1 or 2 hit instead.

### 5. Version-Based Invalidation vs TTL
- **TTL** is time-based — entries expire after N seconds regardless
- **Version** is event-based — entries become stale when new documents are ingested
- Both are checked on every lookup. An entry must pass BOTH checks to be a valid hit.

### 6. SQLite WAL Mode
Write-Ahead Logging allows concurrent readers while one writer is active. Critical for a web server where multiple requests may hit the cache simultaneously.

---

## How to Test

### Prerequisites
- Docker Desktop running (for Redis backend)
- `docker compose up -d` (starts Redis + RedisInsight)

### Test 1: Start the backend
```bash
uv run python main.py
```

### Test 2: Health check
```bash
curl http://localhost:8000/health
# → {"status": "ok"}
```

### Test 3: Cache stats (empty)
```bash
curl http://localhost:8000/cache/stats
# → entries: 0 across all tiers
```

### Test 4: Ask a question (cache MISS)
```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "What was Apple revenue?"}'
# → cache_hit: false, cache_tier: null, response_time_ms: ~5000
```

### Test 5: Same question again (Tier 1 exact HIT)
```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "What was Apple revenue?"}'
# → cache_hit: true, cache_tier: "exact", response_time_ms: ~5
```

### Test 6: Rephrase the question (Tier 2 semantic HIT)
```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "What were Apples revenues?"}'
# → cache_hit: true, cache_tier: "semantic", response_time_ms: ~100
```

### Test 7: Check stats (should have entries)
```bash
curl http://localhost:8000/cache/stats
```

### Test 8: Clear cache
```bash
curl -X POST http://localhost:8000/cache/clear
```

### Test 9: Switch to Redis and repeat
```bash
# 1. Edit .env → CACHE_BACKEND=redis
# 2. Restart backend (Ctrl+C → uv run python main.py)
# 3. Repeat Tests 4-8
# 4. Open RedisInsight at http://localhost:5540 to see keys appear
```

### What to verify

| Test | Expected |
|------|----------|
| Same exact question twice | `cache_tier: "exact"`, `response_time_ms` drops from ~5000 to ~5 |
| Rephrased question | `cache_tier: "semantic"`, `response_time_ms` ~100 |
| `/cache/stats` | Entry counts increase after questions |
| `/cache/clear` | All tiers reset to 0 |
| Upload a new document | `doc_version` bumps, old cache becomes stale |
| Switch `sqlite` ↔ `redis` | Same behavior, different backend |
