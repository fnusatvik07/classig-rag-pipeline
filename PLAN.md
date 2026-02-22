# Plan: Multi-Tier RAG Caching System

## Context

The current chatbot runs the full RAG pipeline (Pinecone retrieval → reranking → LLM generation) on **every single question**, even if the exact same question was asked 5 seconds ago. This wastes LLM tokens, adds unnecessary latency, and hammers the vector DB. We need a caching layer that sits in front of the pipeline and short-circuits when possible.

We implement **3 tiers of caching**, each catching a different type of redundancy. Both **Redis** and **SQLite** backends are supported via a `CACHE_BACKEND` config toggle so students can compare both approaches.

---

## Architecture: 3-Tier Cache

```
User Question
     │
     ▼
┌─────────────────────┐
│ Tier 1: Exact Cache  │  ← hash(normalize(query)) lookup — instant, O(1)
│ Hit? Return answer   │
└────────┬────────────┘
         │ miss
         ▼
┌─────────────────────┐
│ Tier 2: Semantic     │  ← embed query, cosine similarity against cached embeddings
│ Cache (≥0.95 sim)    │  ← catches rephrasings: "Apple revenue?" ≈ "What was Apple's revenue?"
│ Hit? Return answer   │
└────────┬────────────┘
         │ miss
         ▼
┌─────────────────────┐
│ Tier 3: Retrieval    │  ← cache the retrieved chunks for a query embedding
│ Cache                │  ← same context fetched → skip Pinecone, still call LLM
│ Hit? Skip retrieval  │
└────────┬────────────┘
         │ miss
         ▼
   Full RAG Pipeline
   (retrieve → rerank → generate)
         │
         ▼
   Store results in all 3 tiers
```

### What each tier saves

| Tier | Caches What | Saves | Lookup Speed |
|------|------------|-------|-------------|
| **Tier 1: Exact** | Normalized query hash → full answer + sources | LLM call + retrieval + reranking | O(1) hash lookup |
| **Tier 2: Semantic** | Query embedding → full answer + sources | LLM call + retrieval + reranking | O(N) cosine sim |
| **Tier 3: Retrieval** | Query embedding → retrieved chunks | Pinecone API call + reranking | O(N) cosine sim |

---

## Cache Invalidation Strategy

Three mechanisms working together:

1. **TTL-based** — each cache entry has a `ttl_seconds` (default 7 days for Tier 1/2, 1 day for Tier 3). Expired entries are skipped on lookup and cleaned up periodically.

2. **Event-driven** — when a new document is ingested via `/upload` or `/ingest`, ALL cache tiers are cleared. New documents may change answers to existing questions.

3. **Version tagging** — each cache entry stores a `doc_version` integer. A global `doc_version` counter increments on every ingestion. Cache lookups compare versions — if the entry's version is behind, it's a miss. This is more surgical than full clearing.

---

## Backend Toggle: Redis vs SQLite

```
CACHE_BACKEND=sqlite   →  uses SQLite (file-based, zero infra, great for local dev)
CACHE_BACKEND=redis    →  uses Redis (in-memory, production-grade, faster)
```

Both backends implement the **same interface** (`CacheBackend` abstract class), so the rest of the code doesn't care which one is active. Students swap one env var and see the difference.

### Redis via Docker

Redis runs in a Docker container via `docker-compose.yml`. No local install needed.

```yaml
# docker-compose.yml
services:
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
volumes:
  redis_data:
```

**Usage:**
- `docker-compose up -d` — start Redis in background
- `docker-compose down` — stop Redis
- `docker-compose down -v` — stop + delete data
- Redis UI: optionally add RedisInsight on port 8001 for visual inspection

---

## New Files to Create

### `apps/cache/base.py` — Abstract cache interface
```python
class CacheBackend(ABC):
    # Tier 1
    def get_exact(self, query_hash: str) -> dict | None
    def set_exact(self, query_hash: str, question: str, answer: str, sources: list, doc_version: int)

    # Tier 2
    def get_semantic(self, embedding: list[float], threshold: float) -> dict | None
    def set_semantic(self, question: str, embedding: list[float], answer: str, sources: list, doc_version: int)

    # Tier 3
    def get_retrieval(self, embedding: list[float], threshold: float) -> list[dict] | None
    def set_retrieval(self, question: str, embedding: list[float], chunks: list[dict], doc_version: int)

    # Management
    def clear_all(self) -> dict  # returns {tier1: N, tier2: N, tier3: N}
    def get_stats(self) -> dict
    def cleanup_expired(self) -> int
    def invalidate_by_version(self, current_version: int) -> int
```

### `apps/cache/sqlite_backend.py` — SQLite implementation
- Uses `data/rag_cache.db`
- Embeddings stored as BLOB (numpy float32 bytes)
- Cosine similarity computed via numpy in Python
- WAL mode for concurrent read access

### `apps/cache/redis_backend.py` — Redis implementation
- Uses Redis hashes for Tier 1 (exact match)
- Uses Redis + numpy for Tier 2/3 (store embeddings as bytes, load and compare in Python)
- Native TTL support via Redis EXPIRE
- Connection via `redis-py` with connection pooling

### `apps/cache/__init__.py` — Factory function
```python
def get_cache_backend() -> CacheBackend:
    if CACHE_BACKEND == "redis":
        return RedisCacheBackend()
    return SQLiteCacheBackend()  # default
```

### `apps/cache/embeddings.py` — Embedding helper
- `embed_query(text: str) -> list[float]` — uses `langchain_openai.OpenAIEmbeddings` with `text-embedding-3-small`
- `normalize_query(text: str) -> str` — lowercase, strip, collapse whitespace, remove trailing punctuation
- `hash_query(normalized: str) -> str` — SHA256 hex digest
- `cosine_similarity(a, b) -> float` — numpy dot product

---

## Database Schemas

### SQLite (`data/rag_cache.db`)

```sql
-- Global metadata
CREATE TABLE cache_metadata (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL
);
-- Stores: doc_version (int as text)

-- Tier 1: Exact query cache
CREATE TABLE exact_cache (
    query_hash      TEXT PRIMARY KEY,
    question_text   TEXT NOT NULL,
    answer_text     TEXT NOT NULL,
    sources_json    TEXT NOT NULL,
    doc_version     INTEGER NOT NULL,
    created_at      REAL NOT NULL,        -- unix timestamp
    ttl_seconds     INTEGER NOT NULL,
    hit_count       INTEGER DEFAULT 0,
    last_hit_at     REAL
);

-- Tier 2: Semantic cache
CREATE TABLE semantic_cache (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    question_text   TEXT NOT NULL,
    question_embedding BLOB NOT NULL,     -- numpy float32 bytes
    answer_text     TEXT NOT NULL,
    sources_json    TEXT NOT NULL,
    doc_version     INTEGER NOT NULL,
    created_at      REAL NOT NULL,
    ttl_seconds     INTEGER NOT NULL,
    hit_count       INTEGER DEFAULT 0,
    last_hit_at     REAL
);

-- Tier 3: Retrieval cache
CREATE TABLE retrieval_cache (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    question_text   TEXT NOT NULL,
    question_embedding BLOB NOT NULL,
    chunks_json     TEXT NOT NULL,         -- JSON list of chunk dicts
    doc_version     INTEGER NOT NULL,
    created_at      REAL NOT NULL,
    ttl_seconds     INTEGER NOT NULL,
    hit_count       INTEGER DEFAULT 0,
    last_hit_at     REAL
);
```

### Redis key structure
```
cache:exact:<hash>          → JSON {question, answer, sources, doc_version, created_at}
cache:semantic:<id>         → JSON {question, embedding_b64, answer, sources, doc_version}
cache:retrieval:<id>        → JSON {question, embedding_b64, chunks, doc_version}
cache:metadata:doc_version  → integer
cache:semantic:index        → sorted set of IDs (for iteration)
cache:retrieval:index       → sorted set of IDs (for iteration)
```

---

## Files to Modify

### `apps/config.py` — add cache configuration
```python
# Cache Settings
CACHE_BACKEND = os.getenv("CACHE_BACKEND", "sqlite")          # "sqlite" or "redis"
CACHE_ENABLED = os.getenv("CACHE_ENABLED", "true").lower() == "true"
EXACT_CACHE_TTL = int(os.getenv("EXACT_CACHE_TTL", "604800"))         # 7 days
SEMANTIC_CACHE_TTL = int(os.getenv("SEMANTIC_CACHE_TTL", "604800"))    # 7 days
SEMANTIC_CACHE_THRESHOLD = float(os.getenv("SEMANTIC_CACHE_THRESHOLD", "0.95"))
RETRIEVAL_CACHE_TTL = int(os.getenv("RETRIEVAL_CACHE_TTL", "86400"))   # 1 day
RETRIEVAL_CACHE_THRESHOLD = float(os.getenv("RETRIEVAL_CACHE_THRESHOLD", "0.90"))
DATABASE_PATH = os.path.join(BASE_DIR, "data", "rag_cache.db")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
OPENAI_EMBED_MODEL = os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-small")
```

### `apps/api.py` — major changes
1. **Startup**: initialize cache backend + run `cleanup_expired()`
2. **`ChatResponse`**: add `cache_hit: bool = False`, `cache_tier: str | None = None`
3. **`chat_endpoint`**: insert cache check before RAG, store after generation
4. **`upload_endpoint` / `ingest_endpoint`**: bump `doc_version`, invalidate stale cache
5. **New endpoints**:
   - `POST /cache/clear` — clears all tiers, returns counts
   - `GET /cache/stats` — returns per-tier entry counts, hit counts, backend type

### `pyproject.toml` — add dependencies
```
"numpy>=1.26.0",
"redis>=5.0.0",
```

### `.env` — add new vars
```
CACHE_BACKEND=sqlite
CACHE_ENABLED=true
```

### `frontend/vite.config.js` — add proxy for `/cache`

---

## Updated `/chat` Endpoint Flow

```python
def chat_endpoint(req: ChatRequest):
    cache = get_cache_backend()

    # --- TIER 1: Exact match ---
    normalized = normalize_query(req.question)
    query_hash = hash_query(normalized)
    exact_hit = cache.get_exact(query_hash)
    if exact_hit:
        return ChatResponse(answer=exact_hit["answer"], sources=...,
                           cache_hit=True, cache_tier="exact")

    # --- TIER 2: Semantic match ---
    embedding = embed_query(req.question)
    semantic_hit = cache.get_semantic(embedding, SEMANTIC_CACHE_THRESHOLD)
    if semantic_hit:
        return ChatResponse(answer=semantic_hit["answer"], sources=...,
                           cache_hit=True, cache_tier="semantic")

    # --- TIER 3: Retrieval cache ---
    retrieval_hit = cache.get_retrieval(embedding, RETRIEVAL_CACHE_THRESHOLD)
    if retrieval_hit:
        chunks = retrieval_hit["chunks"]
        # Still call LLM but skip Pinecone
        answer = generate_answer(req.question, chunks)
        # Store in Tier 1 + 2 (we now have a full answer)
        cache.set_exact(query_hash, req.question, answer, sources, doc_version)
        cache.set_semantic(req.question, embedding, answer, sources, doc_version)
        return ChatResponse(answer=answer, sources=...,
                           cache_hit=True, cache_tier="retrieval")

    # --- FULL PIPELINE (all cache miss) ---
    retrieved = search(req.question)
    chunks = rerank(req.question) if req.use_reranker else retrieved
    answer = generate_answer(req.question, chunks)

    # Store in ALL 3 tiers
    cache.set_exact(query_hash, req.question, answer, sources, doc_version)
    cache.set_semantic(req.question, embedding, answer, sources, doc_version)
    cache.set_retrieval(req.question, embedding, chunks_raw, doc_version)

    return ChatResponse(answer=answer, sources=...,
                       cache_hit=False, cache_tier=None)
```

---

## Complete File Inventory

### New files (5)
| File | Purpose |
|------|---------|
| `apps/cache/__init__.py` | Factory: `get_cache_backend()` based on config |
| `apps/cache/base.py` | `CacheBackend` abstract class — the interface both backends implement |
| `apps/cache/sqlite_backend.py` | SQLite implementation with numpy cosine similarity |
| `apps/cache/redis_backend.py` | Redis implementation with connection pooling |
| `apps/cache/embeddings.py` | `embed_query()`, `normalize_query()`, `hash_query()`, `cosine_similarity()` |

### Modified files (4)
| File | Changes |
|------|---------|
| `apps/config.py` | Add all cache config constants |
| `apps/api.py` | Cache check in /chat, cache clear on ingest, new /cache endpoints |
| `pyproject.toml` | Add numpy, redis dependencies |
| `frontend/vite.config.js` | Add `/cache` proxy rule |

---

## Verification Plan

1. **Start with SQLite** (`CACHE_BACKEND=sqlite`):
   - Ask "What was Apple's revenue?" → full pipeline, `cache_hit=false`
   - Ask same question again → `cache_hit=true, cache_tier="exact"`
   - Ask "What were Apple's revenues?" (rephrased) → `cache_hit=true, cache_tier="semantic"`
   - Upload a new document → cache clears (version bump)
   - Ask again → `cache_hit=false` (fresh answer)

2. **Switch to Redis** (`CACHE_BACKEND=redis`):
   - Same tests as above, verify identical behavior
   - Check `GET /cache/stats` shows Redis backend

3. **Check `/cache/stats`** — verify per-tier counts
4. **Check `POST /cache/clear`** — verify all tiers cleared

---

## Future Phases (Separate Branches)

### Phase 2: Query Router (branch: `rag-router`)
- Classify queries as "rag" vs "conversational"
- Rule-based + LLM hybrid classification
- Skip RAG pipeline for greetings/chitchat

### Phase 3: Conversation Memory (branch: `rag-memory`)
- Session management with UUIDs
- Message history stored in SQLite
- History passed to LLM for follow-up context

### Phase 4: Langfuse Observability (branch: `rag-observability`)
- Trace all LLM calls, retrieval, reranking
- Track latency, token usage, cache hits
- LangChain callback integration
