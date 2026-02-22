# RAG Caching System — Detailed Teaching Notes

> **Branch**: `rag-caching`
> These notes explain every file, every function, every design decision.

---

## Table of Contents

1. [Why Caching in RAG?](#1-why-caching-in-rag)
2. [Architecture — 3 Tier Cache](#2-architecture--3-tier-cache)
3. [File-by-File Deep Dive](#3-file-by-file-deep-dive)
   - [config.py — Configuration](#31-configpy--configuration)
   - [cache/base.py — The Contract (Abstract Class)](#32-cachebasepy--the-contract)
   - [cache/embeddings.py — The Math Layer](#33-cacheembeddingspy--the-math-layer)
   - [cache/sqlite_backend.py — SQLite Implementation](#34-cachesqlite_backendpy--sqlite-implementation)
   - [cache/redis_backend.py — Redis Implementation](#35-cacheredis_backendpy--redis-implementation)
   - [cache/__init__.py — The Factory](#36-cacheinitpy--the-factory)
   - [api.py — Putting It All Together](#37-apipy--putting-it-all-together)
4. [Design Patterns Used](#4-design-patterns-used)
5. [Cache Invalidation — The Hard Problem](#5-cache-invalidation--the-hard-problem)
6. [SQLite vs Redis — When to Use What](#6-sqlite-vs-redis--when-to-use-what)
7. [Setup Guide — Running Redis Locally](#7-setup-guide--running-redis-locally)
8. [Cost Analysis](#8-cost-analysis)
9. [Common Interview Questions](#9-common-interview-questions)

---

## 1. Why Caching in RAG?

### The Problem

Without caching, every question triggers the FULL pipeline:

```
User asks "What was Apple's revenue?"
  → Pinecone retrieval (network call, ~500ms)
  → Reranking (network call, ~300ms)
  → LLM generation (API call, ~2-5 seconds, costs ~$0.001)
Total: ~3-6 seconds, ~$0.001

User asks the SAME question 10 seconds later
  → Same Pinecone call, same reranking, same LLM call
  → Same answer, same cost, same latency
```

This is wasteful because:
- **Same question = same answer** (documents haven't changed)
- **Similar question ≈ same answer** ("Apple revenue?" vs "What was Apple's revenue?")
- **LLM calls are expensive** ($0.001 may seem small, but at 10K queries/day = $10/day)
- **Latency hurts UX** (3-6 seconds vs instant)

### The Solution

Put a cache in front of the pipeline. Check it first. Only run the expensive pipeline on cache miss.

```
WITH CACHING:
First ask:  3-6 seconds (cache miss, full pipeline, stores result)
Second ask: <100ms (cache hit, instant return)
Savings:    99% latency reduction, 100% cost reduction on hits
```

---

## 2. Architecture — 3 Tier Cache

### Why 3 tiers instead of 1?

A single cache would only catch exact duplicates. But users ask the same thing in different ways:

| What the user asks | What they mean | Which tier catches it |
|---|---|---|
| "What was Apple's revenue?" | Apple revenue question | Tier 1 (exact hash match) |
| "What was Apple's revenue?" (again) | Same question | Tier 1 (exact hash match) |
| "Apple revenues?" | Same intent, different words | Tier 2 (semantic similarity) |
| "What were Apple's quarterly earnings?" | Same context needed | Tier 3 (retrieval cache) |
| "How did Nike perform?" | Different topic entirely | MISS (full pipeline) |

### The 3 Tiers Explained

```
┌─────────────────────────────────────────────────────────┐
│                    INCOMING QUESTION                      │
│              "What was Apple's revenue?"                  │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────┐
│  TIER 1: EXACT CACHE                                      │
│                                                           │
│  How it works:                                            │
│    1. Normalize: "what was apple's revenue"                │
│    2. Hash: SHA256 → "0d9515fdd008f3f9..."                │
│    3. Lookup hash in database → O(1)                      │
│                                                           │
│  What it stores: hash → {answer, sources}                 │
│  What it saves:  LLM + Pinecone + Reranker (everything)  │
│  Speed: Instant (dictionary lookup)                       │
│  Catches: EXACT same question asked again                 │
│                                                           │
│  Analogy: Looking up a word in a dictionary by page #     │
└──────────────────────┬──────────────────────────────────┘
                       │ MISS
                       ▼
┌──────────────────────────────────────────────────────────┐
│  TIER 2: SEMANTIC CACHE                                    │
│                                                           │
│  How it works:                                            │
│    1. Embed question → 1536-dim vector via OpenAI         │
│    2. Compare against ALL cached embeddings               │
│    3. Cosine similarity ≥ 0.95 = match                    │
│                                                           │
│  What it stores: embedding → {answer, sources}            │
│  What it saves:  LLM + Pinecone + Reranker (everything)  │
│  Speed: O(N) where N = cached entries (~1ms for 1000)     │
│  Catches: Rephrasings, typos, slight variations           │
│                                                           │
│  Analogy: "Do you mean...?" like Google's autocorrect     │
│                                                           │
│  Example matches:                                         │
│    "Apple revenue?" ≈ "What was Apple's revenue?" (0.97)  │
│    "AAPL earnings" ≈ "Apple quarterly earnings"   (0.95)  │
│    "Nike sales" ≠ "Apple revenue"                 (0.34)  │
└──────────────────────┬──────────────────────────────────┘
                       │ MISS
                       ▼
┌──────────────────────────────────────────────────────────┐
│  TIER 3: RETRIEVAL CACHE                                   │
│                                                           │
│  How it works:                                            │
│    1. Use same embedding from Tier 2 (no extra API call)  │
│    2. Compare against cached retrieval embeddings         │
│    3. Cosine similarity ≥ 0.90 = match (lower threshold)  │
│                                                           │
│  What it stores: embedding → {chunks from Pinecone}       │
│  What it saves:  Pinecone + Reranker (NOT the LLM)       │
│  Still calls:    LLM (generates fresh answer from chunks)  │
│  Speed: O(N) cosine scan                                  │
│  Catches: Different questions needing same document chunks │
│                                                           │
│  Analogy: "I already have the book open to that page"     │
│                                                           │
│  Example: Q1 asked about Apple Q2 revenue, Q2 asks about  │
│  Apple Q2 expenses — SAME chunks, DIFFERENT question      │
│                                                           │
│  KEY INSIGHT: Lower threshold (0.90) because we're        │
│  matching context similarity, not question similarity     │
└──────────────────────┬──────────────────────────────────┘
                       │ MISS
                       ▼
┌──────────────────────────────────────────────────────────┐
│  FULL RAG PIPELINE                                        │
│                                                           │
│  1. Pinecone retrieval (search for relevant chunks)       │
│  2. BGE reranking (reorder by relevance)                  │
│  3. LLM generation (generate answer with citations)       │
│  4. STORE result in ALL 3 cache tiers for next time       │
└──────────────────────────────────────────────────────────┘
```

### Cache Promotion (Advanced Concept)

When Tier 3 hits, we call the LLM with cached chunks. Now we have a FULL answer. So we "promote" it:
- Store in Tier 1 (exact) — next time this exact question = instant
- Store in Tier 2 (semantic) — next time a similar question = instant

This means the cache gets smarter over time. A Tier 3 hit today becomes a Tier 1/2 hit tomorrow.

---

## 3. File-by-File Deep Dive

### 3.1 `config.py` — Configuration

**File**: `apps/config.py`

Every cache setting is an **environment variable** with a sensible default. This means:
- Development: just works out of the box (SQLite, all defaults)
- Production: override via `.env` file or deployment config
- Testing: override programmatically

```python
# Which storage backend to use
CACHE_BACKEND = os.getenv("CACHE_BACKEND", "sqlite")      # "sqlite" or "redis"

# Master on/off switch — set to "false" to disable all caching
CACHE_ENABLED = os.getenv("CACHE_ENABLED", "true").lower() == "true"

# Tier 1: How long exact cache entries live (seconds)
EXACT_CACHE_TTL = int(os.getenv("EXACT_CACHE_TTL", "604800"))       # 7 days

# Tier 2: How long semantic cache entries live
SEMANTIC_CACHE_TTL = int(os.getenv("SEMANTIC_CACHE_TTL", "604800"))  # 7 days

# Tier 2: Minimum cosine similarity to count as a "hit"
# 0.95 = very similar (rephrasings only)
# 0.90 = somewhat similar (broader matches, more false positives)
# 0.99 = nearly identical (barely catches anything)
SEMANTIC_CACHE_THRESHOLD = float(os.getenv("SEMANTIC_CACHE_THRESHOLD", "0.95"))

# Tier 3: Retrieval cache lives shorter (context changes more often)
RETRIEVAL_CACHE_TTL = int(os.getenv("RETRIEVAL_CACHE_TTL", "86400"))   # 1 day
RETRIEVAL_CACHE_THRESHOLD = float(os.getenv("RETRIEVAL_CACHE_THRESHOLD", "0.90"))

# Where the SQLite database file lives
DATABASE_PATH = os.getenv("DATABASE_PATH", os.path.join(BASE_DIR, "data", "rag_cache.db"))

# Redis connection string (only used if CACHE_BACKEND=redis)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Which OpenAI model to use for embeddings (for cache similarity)
# This is DIFFERENT from the Pinecone embedding model (multilingual-e5-large)
# We use a separate, cheaper model for cache lookups
OPENAI_EMBED_MODEL = os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-small")
```

**Teaching point**: Why `text-embedding-3-small` and NOT `multilingual-e5-large`?
- Pinecone uses `multilingual-e5-large` internally for document retrieval (we can't access those embeddings)
- For cache, we need to compute embeddings LOCALLY to do cosine similarity
- `text-embedding-3-small` is cheap ($0.00002/query), fast, and good enough for question-to-question similarity
- We're comparing questions to questions, not questions to documents — different task

---

### 3.2 `cache/base.py` — The Contract

**File**: `apps/cache/base.py`

This is an **Abstract Base Class (ABC)**. It defines WHAT the cache must do, but not HOW.

```python
from abc import ABC, abstractmethod

class CacheBackend(ABC):
    """Every cache backend must implement these 11 methods."""
```

**Why abstract?** Because we want two different implementations (SQLite, Redis) to be interchangeable. The rest of the code calls `cache.get_exact()` without knowing or caring if it's talking to SQLite or Redis.

**The 11 methods, grouped by purpose:**

```
TIER 1 (Exact):
  get_exact(query_hash)      → Look up by hash, return answer or None
  set_exact(hash, q, a, ...) → Store a Q&A pair keyed by hash

TIER 2 (Semantic):
  get_semantic(embedding, threshold) → Find similar cached question by cosine sim
  set_semantic(q, embedding, a, ...) → Store Q&A with its embedding vector

TIER 3 (Retrieval):
  get_retrieval(embedding, threshold) → Find similar query, return cached chunks
  set_retrieval(q, embedding, chunks) → Store retrieval chunks for a query

MANAGEMENT:
  get_doc_version()   → Read the document version counter
  bump_doc_version()  → Increment it (called on document ingestion)
  clear_all()         → Nuke everything, return counts
  get_stats()         → Return per-tier statistics
  cleanup_expired()   → Remove entries past their TTL
```

**Design pattern**: This is the **Strategy Pattern**. The algorithm (cache lookup) is fixed, but the implementation (SQLite vs Redis) is pluggable.

```
api.py says: cache.get_exact("abc123")

If CACHE_BACKEND=sqlite:  → SQLiteCacheBackend.get_exact() → queries SQLite file
If CACHE_BACKEND=redis:   → RedisCacheBackend.get_exact()  → queries Redis server
If CACHE_BACKEND=postgres: → (future) PostgresCacheBackend.get_exact() → queries PostgreSQL
```

**Key point for students**: You can NEVER instantiate `CacheBackend()` directly. Try it and Python raises `TypeError: Can't instantiate abstract class`. You MUST use a concrete subclass.

---

### 3.3 `cache/embeddings.py` — The Math Layer

**File**: `apps/cache/embeddings.py`

This file contains the 6 utility functions that both backends share. No storage logic — just text processing and vector math.

#### Function 1: `embed_query(text) → list[float]`

```python
def embed_query(text: str) -> list[float]:
    client = _get_embeddings_client()     # singleton OpenAI client
    return client.embed_query(text)       # returns 1536 floats
```

**What it does**: Sends text to OpenAI API, gets back a 1536-dimensional vector.

**What a vector looks like**:
```python
embed_query("What was Apple's revenue?")
# → [0.0234, -0.0156, 0.0891, ..., -0.0412]  (1536 numbers)

embed_query("Apple revenues?")
# → [0.0229, -0.0161, 0.0887, ..., -0.0408]  (very similar numbers!)

embed_query("How is the weather?")
# → [0.0782, 0.0341, -0.0234, ..., 0.0567]   (completely different numbers)
```

**Teaching point — Singleton pattern**:
```python
_embeddings_client = None  # module-level variable

def _get_embeddings_client():
    global _embeddings_client
    if _embeddings_client is None:           # first call: create it
        _embeddings_client = OpenAIEmbeddings(...)
    return _embeddings_client                # all subsequent calls: reuse it
```

Why? Creating the client involves API key validation and config. We only want to do that once, not on every cache lookup.

#### Function 2: `normalize_query(text) → str`

```python
"  What was  Apple's Revenue?? "
    ↓ .lower()
"  what was  apple's revenue?? "
    ↓ .strip()
"what was  apple's revenue??"
    ↓ re.sub(r"\s+", " ", text)     # collapse multiple spaces
"what was apple's revenue??"
    ↓ re.sub(r"[?.!]+$", "", text)  # remove trailing punctuation
"what was apple's revenue"
```

**Why normalize?** Without it, these would be treated as different questions:
- `"What was Apple's revenue?"` (original)
- `"what was apple's revenue?"` (lowercase)
- `"What was Apple's revenue"` (no question mark)
- `"  What was  Apple's  revenue??  "` (extra spaces and punctuation)

After normalization, ALL of these become `"what was apple's revenue"` → same hash → Tier 1 hit.

#### Function 3: `hash_query(text) → str`

```python
hashlib.sha256("what was apple's revenue".encode("utf-8")).hexdigest()
# → "0d9515fdd008f3f9a2b1c4e5d6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5"
```

**Why SHA256?**
- Deterministic: same input ALWAYS produces same hash
- Fixed length: always 64 hex characters, regardless of query length
- Collision-resistant: virtually impossible for two different queries to produce the same hash
- Fast: no network call, no API cost

**Teaching point**: This is the same hashing concept used in:
- Git (commit hashes)
- Password storage
- Blockchain
- File integrity checks (checksums)

#### Function 4: `cosine_similarity(vec_a, vec_b) → float`

```python
def cosine_similarity(vec_a, vec_b):
    a = np.array(vec_a, dtype=np.float32)
    b = np.array(vec_b, dtype=np.float32)
    dot_product = np.dot(a, b)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    return dot_product / (norm_a * norm_b)
```

**The math** (for students who want to understand):

```
Cosine similarity = (A · B) / (||A|| × ||B||)

Where:
  A · B     = sum of (a_i × b_i) for all dimensions  (dot product)
  ||A||     = sqrt(sum of a_i²)                       (magnitude/length)
  ||B||     = sqrt(sum of b_i²)

Result is between -1 and 1:
  1.0  = vectors point same direction = same meaning
  0.0  = vectors are perpendicular = unrelated
  -1.0 = vectors point opposite = opposite meaning (rare in practice)
```

**Visual intuition** (2D simplified — real vectors are 1536D):

```
         ↑ "Apple revenue"
        /
       /  ← angle is small = cosine is high (0.97)
      /
     /
    "Apple earnings"  ──→

         ↑ "Apple revenue"
         |
         |   ← angle is ~90° = cosine is ~0 (0.15)
         |
    "Weather today"  ──→
```

#### Functions 5 & 6: `embedding_to_bytes()` / `bytes_to_embedding()`

```python
# list of 1536 floats → compact binary blob (6144 bytes)
embedding_to_bytes([0.0234, -0.0156, ...])
# → b'\x9a\x99\xb9>\xcd\xcc...'

# binary blob → back to list of floats
bytes_to_embedding(b'\x9a\x99\xb9>\xcd\xcc...')
# → [0.0234, -0.0156, ...]
```

**Why?**
- A list of 1536 Python floats takes ~50KB as JSON text
- The same data as numpy float32 bytes takes ~6KB (8x smaller)
- SQLite stores this as a BLOB column (binary large object)
- Redis stores it as hex-encoded string

---

### 3.4 `cache/sqlite_backend.py` — SQLite Implementation

**File**: `apps/cache/sqlite_backend.py`

This is the "teach it in class" backend. No infrastructure, no servers — just a file.

#### Constructor — What happens on startup

```python
def __init__(self, db_path=None):
    self._db_path = db_path or DATABASE_PATH     # "data/rag_cache.db"
    os.makedirs(os.path.dirname(...), exist_ok=True)  # create data/ directory
    self._init_tables()                           # create tables if not exist
```

#### Connection management

```python
def _get_conn(self):
    conn = sqlite3.connect(self._db_path)
    conn.row_factory = sqlite3.Row    # rows behave like dicts: row["column_name"]
    conn.execute("PRAGMA journal_mode=WAL")    # Write-Ahead Logging
    conn.execute("PRAGMA foreign_keys=ON")
    return conn
```

**Teaching point — WAL mode**:

Normal SQLite locks the ENTIRE database during writes. WAL mode allows:
- Multiple readers at the same time
- One writer while readers continue reading
- Critical for a web server where multiple HTTP requests arrive simultaneously

```
Without WAL:  Request A writes → Request B waits → B reads  (sequential)
With WAL:     Request A writes → Request B reads simultaneously (parallel)
```

#### Database schema — 4 tables

```sql
-- 1. Metadata table (stores doc_version counter)
cache_metadata:  key TEXT PRIMARY KEY, value TEXT

-- 2. Tier 1: exact cache
exact_cache:
  query_hash       TEXT PRIMARY KEY     ← the SHA256 hash (lookup key)
  question_text    TEXT                 ← original question for display
  answer_text      TEXT                 ← the cached LLM answer
  sources_json     TEXT                 ← JSON-serialized source chunks
  doc_version      INTEGER             ← version tag for invalidation
  created_at       REAL                ← unix timestamp (e.g., 1708531200.0)
  ttl_seconds      INTEGER             ← how long this entry is valid
  hit_count        INTEGER DEFAULT 0   ← how many times this was used
  last_hit_at      REAL                ← when it was last used

-- 3. Tier 2: semantic cache (same as exact + embedding)
semantic_cache:
  id                    INTEGER PRIMARY KEY AUTOINCREMENT
  question_text         TEXT
  question_embedding    BLOB              ← 6144 bytes of numpy float32
  answer_text           TEXT
  sources_json          TEXT
  doc_version, created_at, ttl_seconds, hit_count, last_hit_at

-- 4. Tier 3: retrieval cache (stores chunks instead of answer)
retrieval_cache:
  id, question_text, question_embedding
  chunks_json           TEXT              ← JSON list of chunk dicts from Pinecone
  doc_version, created_at, ttl_seconds, hit_count, last_hit_at
```

**Why TEXT for JSON?** SQLite doesn't have a native JSON column type. Storing as TEXT works fine — we serialize/deserialize in Python. PostgreSQL would use a `JSONB` column instead.

#### Tier 1 lookup — `get_exact()` walkthrough

```python
def get_exact(self, query_hash):
    # 1. Open connection, get current time and doc version
    conn = self._get_conn()
    now = time.time()
    doc_version = self._get_doc_version_raw(conn)

    # 2. Query by hash (O(1) — PRIMARY KEY lookup)
    row = conn.execute(
        "SELECT ... FROM exact_cache WHERE query_hash = ?",
        (query_hash,)
    ).fetchone()

    if row is None:
        return None              # ← MISS: never seen this question

    # 3. Check TTL (time-to-live)
    if now - row["created_at"] > row["ttl_seconds"]:
        conn.execute("DELETE ...")  # expired → remove it
        return None              # ← MISS: entry too old

    # 4. Check document version
    if row["doc_version"] < doc_version:
        conn.execute("DELETE ...")  # stale → new docs were added
        return None              # ← MISS: entry from before new documents

    # 5. HIT! Update usage statistics
    conn.execute(
        "UPDATE exact_cache SET hit_count = hit_count + 1, last_hit_at = ? ...",
        (now, query_hash)
    )

    # 6. Return the cached answer
    return {"question": ..., "answer": ..., "sources_json": ...}
```

**The 3 gates** every cache entry must pass:
1. **Existence** — is the hash in the database at all?
2. **TTL** — was it created recently enough? (now - created_at < ttl_seconds)
3. **Version** — was it created with the current document set? (entry.version >= current.version)

Only if ALL 3 pass → cache HIT.

#### Tier 2 lookup — `get_semantic()` walkthrough

```python
def get_semantic(self, embedding, threshold):
    # 1. Load ALL cached entries
    rows = conn.execute("SELECT ... FROM semantic_cache").fetchall()

    best_match = None
    best_similarity = 0.0

    for row in rows:
        # Skip expired or stale entries
        if now - row["created_at"] > row["ttl_seconds"]: continue
        if row["doc_version"] < doc_version: continue

        # 2. Deserialize the stored embedding
        cached_embedding = bytes_to_embedding(row["question_embedding"])

        # 3. Compute cosine similarity
        sim = cosine_similarity(embedding, cached_embedding)

        # 4. Track the best match above threshold
        if sim >= threshold and sim > best_similarity:
            best_similarity = sim
            best_match = row

    return {"answer": ..., "similarity": best_similarity}
```

**Why load ALL entries?** We need to compare the incoming vector against EVERY cached vector to find the best match. There's no shortcut for cosine similarity in a flat list — you must check each one.

**Performance**: For 1000 entries, that's 1000 cosine similarity computations. Each one is a numpy dot product on 1536-dim vectors. Total time: ~1ms. Even 10,000 entries takes ~10ms. Only becomes a problem at 100K+ entries.

**Future optimization**: Use approximate nearest neighbor (ANN) algorithms like FAISS or HNSW for 100K+ scale. But for a teaching project, brute-force scan is perfectly fine and easier to understand.

---

### 3.5 `cache/redis_backend.py` — Redis Implementation

**File**: `apps/cache/redis_backend.py`

Same logic as SQLite, but stores everything in Redis (in-memory key-value store).

#### Key differences from SQLite

| Aspect | SQLite | Redis |
|--------|--------|-------|
| Storage | File on disk (`data/rag_cache.db`) | In-memory (with disk persistence) |
| Speed | Fast (~1ms reads) | Faster (~0.1ms reads) |
| TTL handling | Manual check in Python | Native `SETEX` with auto-expiry |
| Concurrent access | WAL mode (limited) | Built-in (thousands of clients) |
| Data types | Tables with rows | Key-value with JSON strings |
| Infrastructure | None (just a file) | Requires Redis server (Docker) |
| Persistence | Always persisted | Configurable (RDB/AOF/none) |

#### Redis key structure

```
cache:exact:<sha256_hash>              → JSON string
cache:semantic:<uuid>                  → JSON string
cache:retrieval:<uuid>                 → JSON string
cache:metadata:doc_version             → integer
cache:semantic:index                   → SET of UUIDs
cache:retrieval:index                  → SET of UUIDs
```

**Why the naming convention `cache:exact:...`?**
Redis has a flat key space (no tables). Using `:` as a separator is the Redis convention for logical grouping. It's like folder paths: `cache/exact/abc123`.

#### The SET index problem

**Problem**: Redis doesn't have tables you can `SELECT * FROM`. To iterate all semantic cache entries, we need to know all their keys.

**Solution**: Maintain a Redis SET called `cache:semantic:index` that contains all entry UUIDs:

```
cache:semantic:index = { "a1b2c3d4", "e5f6g7h8", "i9j0k1l2" }

When looking up semantic cache:
  1. SMEMBERS cache:semantic:index → get all UUIDs
  2. For each UUID: GET cache:semantic:<uuid> → get entry data
  3. Deserialize, compute cosine similarity
```

**The TTL race condition**: Redis auto-deletes keys when they expire (`SETEX`). But the SET index doesn't know! An entry can expire while its UUID still exists in the index. That's why `get_semantic()` handles this:

```python
data = self._redis.get(key)
if data is None:
    # Key expired, but UUID is still in the index → clean it up
    self._redis.srem(_SEMANTIC_INDEX, member_id)
    continue
```

#### Native TTL — Redis's superpower

```python
# SQLite: TTL is manual — we store created_at + ttl_seconds, check in Python
if now - row["created_at"] > row["ttl_seconds"]:
    conn.execute("DELETE ...")  # we have to delete it ourselves

# Redis: TTL is built-in — Redis auto-deletes after N seconds
self._redis.setex(key, ttl_seconds, data)  # "set with expiry"
# After ttl_seconds pass, the key just vanishes. No cleanup needed.
```

#### `bump_doc_version()` — Redis one-liner

```python
# SQLite: read → increment → write (3 operations)
def bump_doc_version(self):
    current = self._get_doc_version_raw(conn)
    new_version = current + 1
    conn.execute("UPDATE cache_metadata SET value = ? ...", (new_version,))
    return new_version

# Redis: atomic increment (1 operation, thread-safe)
def bump_doc_version(self):
    return int(self._redis.incr(_DOC_VERSION_KEY))  # INCR is atomic!
```

**Teaching point — Atomicity**: `INCR` in Redis is atomic. Even if 100 requests call `bump_doc_version()` simultaneously, each one gets a unique incremented value. No race conditions. SQLite would need explicit locking for the same guarantee.

---

### 3.6 `cache/__init__.py` — The Factory

**File**: `apps/cache/__init__.py`

```python
_backend_instance = None  # singleton

def get_cache_backend():
    global _backend_instance
    if _backend_instance is not None:
        return _backend_instance         # already created → reuse

    if CACHE_BACKEND == "redis":
        from .redis_backend import RedisCacheBackend
        _backend_instance = RedisCacheBackend()
    else:
        from .sqlite_backend import SQLiteCacheBackend
        _backend_instance = SQLiteCacheBackend()

    return _backend_instance
```

**Two patterns in one:**

1. **Factory Pattern**: `get_cache_backend()` decides which class to instantiate based on config. The caller doesn't know or care which backend they get.

2. **Singleton Pattern**: The instance is created once and reused. Why? Because both backends hold state (SQLite file handle, Redis connection pool). Creating a new one per request would be wasteful.

**Lazy imports**: Notice `from .redis_backend import RedisCacheBackend` is INSIDE the if-block. This means if you're using SQLite, the Redis library is never imported. No `import redis` error even if redis isn't installed (though it is in our case).

---

### 3.7 `api.py` — Putting It All Together

**File**: `apps/api.py`

#### Lifespan — startup/shutdown

```python
@asynccontextmanager
async def lifespan(_app: FastAPI):
    # STARTUP: clean expired cache entries
    if CACHE_ENABLED:
        cache = get_cache_backend()
        removed = cache.cleanup_expired()
    yield
    # SHUTDOWN: nothing needed
```

**Teaching point**: FastAPI's `lifespan` replaces the old `@app.on_event("startup")`. It uses Python's `asynccontextmanager` — everything before `yield` runs on startup, everything after runs on shutdown.

#### Response timing — `response_time_ms`

Every `/chat` response includes `response_time_ms` — the total time in milliseconds from when the request started to when the response is ready. This lets students SEE the cache benefit:

```python
start_time = time.time()
# ... cache checks / pipeline ...
return ChatResponse(
    answer=...,
    cache_hit=True,
    cache_tier="exact",
    response_time_ms=round((time.time() - start_time) * 1000, 2),  # e.g., 4.23
)
```

| Scenario | Typical `response_time_ms` |
|----------|---------------------------|
| Full pipeline (cache miss) | 3000–8000 ms |
| Tier 3 retrieval hit | 2000–4000 ms |
| Tier 2 semantic hit | 50–200 ms |
| Tier 1 exact hit | 1–10 ms |

The jump from ~5000ms to ~5ms is dramatic and makes the value of caching immediately obvious.

#### The `/chat` endpoint — full flow with cache

```python
@app.post("/chat")
def chat_endpoint(req: ChatRequest):
    start_time = time.time()
    cache = get_cache_backend() if CACHE_ENABLED else None

    # ── TIER 1: Exact ──────────────────────────────────
    if cache:
        normalized = normalize_query(req.question)   # "what was apple's revenue"
        query_hash = hash_query(normalized)           # "0d9515fdd008f3f9..."
        exact_hit = cache.get_exact(query_hash)

        if exact_hit:
            return ChatResponse(
                answer=exact_hit["answer"],
                sources=_json_to_sources(exact_hit["sources_json"]),
                cache_hit=True,           # ← tells frontend it was cached
                cache_tier="exact",       # ← tells frontend WHICH tier
                response_time_ms=round((time.time() - start_time) * 1000, 2),
            )

    # ── TIER 2: Semantic ───────────────────────────────
    embedding = None
    if cache:
        embedding = embed_query(req.question)    # OpenAI API call (~100ms)
        semantic_hit = cache.get_semantic(embedding, SEMANTIC_CACHE_THRESHOLD)

        if semantic_hit:
            return ChatResponse(
                answer=semantic_hit["answer"],
                cache_hit=True,
                cache_tier="semantic",
            )

    # ── TIER 3: Retrieval ──────────────────────────────
    if cache and embedding:
        retrieval_hit = cache.get_retrieval(embedding, RETRIEVAL_CACHE_THRESHOLD)

        if retrieval_hit:
            cached_chunks = json.loads(retrieval_hit["chunks_json"])
            answer = generate_answer(req.question, cached_chunks)  # LLM call

            # PROMOTE to Tier 1 + 2 for next time
            cache.set_exact(...)
            cache.set_semantic(...)

            return ChatResponse(answer=answer, cache_hit=True, cache_tier="retrieval")

    # ── FULL PIPELINE (all miss) ───────────────────────
    retrieved_chunks = search(req.question)       # Pinecone
    chunks = rerank(req.question)                 # BGE reranker
    answer = generate_answer(req.question, chunks) # LLM

    # STORE in all 3 tiers
    if cache:
        cache.set_exact(...)
        cache.set_semantic(...)
        cache.set_retrieval(...)

    return ChatResponse(answer=answer, cache_hit=False, cache_tier=None)
```

**Key insight**: The embedding computed for Tier 2 is REUSED for Tier 3. No extra API call. This is why `embedding` is declared outside the if-blocks — it's a shared variable.

#### Cache invalidation on document upload

```python
@app.post("/upload")
async def upload_endpoint(file):
    # ... save and ingest file ...

    # After ingestion: bump version so all old cache entries become stale
    if CACHE_ENABLED:
        cache = get_cache_backend()
        cache.bump_doc_version()
```

This doesn't DELETE entries — it just makes them stale. On next lookup, the version check fails, and the entry is skipped (and eventually cleaned up).

#### Helper functions for serialization

```python
def _sources_to_json(sources: List[SourceChunk]) -> str:
    """SourceChunk objects → JSON string for cache storage."""
    return json.dumps([s.model_dump() for s in sources])

def _json_to_sources(sources_json: str) -> List[SourceChunk]:
    """JSON string → SourceChunk objects for API response."""
    return [SourceChunk(**s) for s in json.loads(sources_json)]
```

**Why serialize?** SQLite and Redis store strings, not Python objects. We need to convert `SourceChunk` Pydantic models ↔ JSON text.

---

## 4. Design Patterns Used

| Pattern | Where | Why |
|---------|-------|-----|
| **Strategy** | `CacheBackend` ABC + SQLite/Redis implementations | Swap storage backends without changing any other code |
| **Factory** | `get_cache_backend()` | Centralized creation logic — one place decides which backend |
| **Singleton** | `_backend_instance` in `__init__.py` | Don't create new DB connections on every request |
| **Lazy Initialization** | `_embeddings_client` in `embeddings.py` | Don't call OpenAI API until we actually need an embedding |
| **Template Method** | `get_exact()` flow (check existence → TTL → version → hit) | Same validation logic, different storage mechanism |

---

## 5. Cache Invalidation — The Hard Problem

> "There are only two hard things in Computer Science: cache invalidation and naming things."
> — Phil Karlton

### Our 3 invalidation mechanisms:

#### 1. TTL (Time-To-Live)
```
Entry created at:     2024-02-21 10:00:00
TTL:                  604800 seconds (7 days)
Expires at:           2024-02-28 10:00:00
```
**Pro**: Simple, automatic
**Con**: Stale data for up to 7 days if documents change

#### 2. Version Tagging
```
State: doc_version = 3

Entry stored with version=3     → VALID (3 >= 3)
User uploads new document       → doc_version bumps to 4
Entry now has version=3         → STALE (3 < 4, skip it)
```
**Pro**: Immediate invalidation when documents change
**Con**: Invalidates ALL cache entries, even if the new document is unrelated

#### 3. Manual Clear (`POST /cache/clear`)
**Pro**: Full control
**Con**: Requires human/automated trigger

### What we DON'T do (future improvements):
- **Per-document invalidation**: Only invalidate cache entries that used chunks from the changed document
- **LRU eviction**: Remove least-recently-used entries when cache is full
- **Semantic invalidation**: Re-check if cached answer is still correct given new documents

---

## 6. SQLite vs Redis — When to Use What

```
┌─────────────────────────────────────────────────────┐
│              USE SQLITE WHEN...                       │
├─────────────────────────────────────────────────────┤
│  - Local development / learning                      │
│  - Single server deployment                          │
│  - < 10K cached entries                              │
│  - Don't want to manage extra infrastructure         │
│  - Data must survive server restarts                 │
│  - Cost matters (free, no cloud service)             │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│              USE REDIS WHEN...                        │
├─────────────────────────────────────────────────────┤
│  - Production deployment                             │
│  - Multiple server instances (shared cache)          │
│  - > 10K cached entries (faster reads)               │
│  - Need native TTL (auto-cleanup)                    │
│  - Need atomic operations (INCR, etc.)               │
│  - Sub-millisecond latency matters                   │
│  - Already running Docker infrastructure             │
└─────────────────────────────────────────────────────┘
```

**Benchmark comparison** (approximate):

| Operation | SQLite | Redis |
|-----------|--------|-------|
| Tier 1 exact lookup | ~0.5ms | ~0.1ms |
| Tier 2 semantic scan (1000 entries) | ~2ms | ~3ms* |
| Tier 2 semantic scan (10K entries) | ~15ms | ~25ms* |
| Write new entry | ~1ms | ~0.2ms |
| Startup (cold) | ~5ms | ~50ms (connection) |

*Redis is slower for semantic scan because of network overhead per key fetch. SQLite loads everything in one query.

---

## 7. Setup Guide — Running Redis Locally

### Prerequisites

- **Docker Desktop** installed ([download here](https://www.docker.com/products/docker-desktop/))
- Our `docker-compose.yml` in the project root (already created)

### Step-by-Step Setup

#### Step 1: Start Docker Desktop

Open the **Docker Desktop** application:
- macOS: `Cmd + Space` → type "Docker" → open Docker Desktop
- Windows: Search "Docker Desktop" in Start menu
- Linux: `sudo systemctl start docker`

Wait until the whale icon in the menu bar/taskbar **stops animating** (means the Docker engine is ready).

**How to verify Docker is running:**
```bash
docker --version
# Docker version 27.x.x, build ...

docker ps
# Should show an empty table (no error)
```

If you see `Cannot connect to the Docker daemon` → Docker Desktop is not running yet. Open it and wait.

#### Step 2: Start Redis Container

```bash
cd ~/Desktop/rag-pipeline-classic
docker compose up -d
```

**What this does:**
- Downloads the `redis:7-alpine` image (~30MB, lightweight Alpine Linux)
- Creates a container named `rag-redis`
- Maps port `6379` (Redis default) from container to your machine
- Creates a persistent volume `redis_data` so data survives container restarts
- `-d` = detached mode (runs in background)

**Expected output:**
```
[+] Running 2/2
 ✔ Network rag-pipeline-classic_default  Created
 ✔ Container rag-redis                   Started
```

#### Step 3: Verify Redis is Running

```bash
# Check container status
docker ps
# Should show: rag-redis ... Up X seconds ... 0.0.0.0:6379->6379/tcp

# Ping Redis
docker exec rag-redis redis-cli ping
# Should print: PONG

# Check Redis info
docker exec rag-redis redis-cli info server | head -5
```

#### Step 4: Switch to Redis Backend

Edit `.env`:
```
CACHE_BACKEND=redis
```

Restart the backend:
```bash
uv run python main.py
```

Now all cache operations use Redis instead of SQLite.

### Common Docker Commands

```bash
# Start Redis (background)
docker compose up -d

# Stop Redis (data preserved in volume)
docker compose down

# Stop Redis AND delete all data
docker compose down -v

# View Redis logs
docker compose logs redis

# Open Redis CLI (interactive shell)
docker exec -it rag-redis redis-cli

# Inside Redis CLI:
#   KEYS cache:*          → list all cache keys
#   GET cache:exact:abc   → view a specific entry
#   DBSIZE                → count total keys
#   FLUSHDB               → delete everything
#   exit                  → quit CLI
```

### Inspecting Cache Data in Redis CLI

```bash
# Open interactive Redis CLI
docker exec -it rag-redis redis-cli

# See all cache keys
KEYS cache:*

# Check how many keys exist
DBSIZE

# View a specific exact cache entry
GET cache:exact:<hash>

# Check TTL remaining on a key (seconds until expiry)
TTL cache:exact:<hash>

# View all semantic cache entry IDs
SMEMBERS cache:semantic:index

# View doc version
GET cache:metadata:doc_version

# Clear everything (use with caution!)
FLUSHDB
```

### What's in `docker-compose.yml`?

```yaml
services:
  redis:
    image: redis:7-alpine       # Redis 7 on Alpine Linux (~30MB)
    container_name: rag-redis    # Fixed name so we can reference it
    ports:
      - "6379:6379"             # Host port : Container port
    volumes:
      - redis_data:/data        # Persist data across restarts
    restart: unless-stopped      # Auto-restart if it crashes
    healthcheck:                 # Docker checks if Redis is healthy
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 3

  redisinsight:
    image: redis/redisinsight:latest   # Official Redis web UI
    container_name: rag-redisinsight
    ports:
      - "5540:5540"                    # Web dashboard
    depends_on:
      - redis                          # Start after Redis
    restart: unless-stopped

volumes:
  redis_data:                   # Named volume for persistence
```

**RedisInsight** (http://localhost:5540) is a visual web UI for browsing Redis data. After connecting (use host `redis`, port `6379`), you can filter keys by `cache:exact:*`, `cache:semantic:*` etc., view TTLs, and watch cache entries appear in real-time as you ask questions.

**Teaching point — Why Alpine?**
Alpine Linux is a minimal Linux distro (~5MB). `redis:7-alpine` is ~30MB vs `redis:7` at ~130MB. Same Redis, smaller image, faster download.

**Teaching point — Why a volume?**
Without the volume, all Redis data is lost when the container stops. With `redis_data:/data`, Redis writes its RDB snapshots to a Docker-managed volume that persists across container restarts.

### Troubleshooting

| Problem | Solution |
|---------|----------|
| `Cannot connect to Docker daemon` | Open Docker Desktop app and wait for it to start |
| `Port 6379 already in use` | Another Redis is running. Run `lsof -i :6379` to find it, or change port in docker-compose.yml |
| `redis.exceptions.ConnectionError` in Python | Redis container isn't running. Run `docker compose up -d` |
| Container starts but immediately stops | Check logs: `docker compose logs redis` |
| Data disappeared after restart | You ran `docker compose down -v` (the `-v` deletes volumes). Use `docker compose down` (without `-v`) to keep data |

### Switching Between Backends

```bash
# Use SQLite (default, zero setup)
# In .env:
CACHE_BACKEND=sqlite

# Use Redis (needs Docker running)
# In .env:
CACHE_BACKEND=redis

# Restart backend after changing:
# Stop the running server (Ctrl+C) and re-run:
uv run python main.py
```

**Note**: SQLite and Redis have separate data stores. Switching backends means starting with an empty cache. Data in the other backend is preserved — switch back and it's still there.

---

## 8. Cost Analysis

### Per-question cost breakdown:

```
WITHOUT CACHE:
  Pinecone retrieval:   ~$0.0001  (API call)
  Reranking:            ~$0.0001  (API call)
  LLM generation:       ~$0.001   (GPT-4o-mini, ~1000 tokens out)
  Total:                ~$0.0012/question

WITH CACHE (hit):
  Cache embedding:      ~$0.00002  (text-embedding-3-small, Tier 2/3 only)
  Cache lookup:          $0        (local computation)
  Total:                ~$0.00002/question on Tier 2/3 hit
  Total:                 $0/question on Tier 1 hit

SAVINGS ON HIT:         ~98% cost reduction
```

### At scale (10,000 questions/day, 60% cache hit rate):

```
Without cache:  10,000 × $0.0012 = $12.00/day  = $360/month
With cache:     4,000 × $0.0012 + 6,000 × $0.00002 = $4.92/day = $148/month
Savings:        $212/month (59% reduction)
```

---

## 9. Common Interview Questions

**Q: Why not just use Redis for everything? Why have SQLite as an option?**
A: SQLite requires zero infrastructure — no server, no Docker, no cloud service. For a single-server deployment or local development, it's simpler and free. Redis adds a network hop and requires running a separate process.

**Q: Why 3 tiers? Why not just semantic cache?**
A: Tier 1 (exact) is O(1) and free (no embedding API call). If the same question is asked 100 times, Tier 1 handles 99 of them instantly. Tier 2 requires an OpenAI embedding call (~$0.00002). Tier 3 catches cases where different questions need the same context. Each tier has a different cost/coverage tradeoff.

**Q: What happens if the cache returns a stale answer?**
A: Three safeguards: TTL (entries expire after 7 days), version tagging (entries invalidated when new documents are uploaded), and manual clear (`POST /cache/clear`).

**Q: How does this scale to millions of cached entries?**
A: Our brute-force cosine scan is O(N). At 100K+ entries, you'd switch to approximate nearest neighbor (ANN) using libraries like FAISS, or use Redis with the RediSearch module which supports native vector similarity search.

**Q: Why use a separate embedding model for cache vs retrieval?**
A: Pinecone uses `multilingual-e5-large` internally for document retrieval — we can't access those embeddings. For cache, we need local embeddings to compute cosine similarity. `text-embedding-3-small` is cheaper and fast enough for question-to-question comparison.

**Q: What's the Strategy Pattern and why use it here?**
A: The Strategy Pattern defines a family of algorithms (SQLite storage, Redis storage), encapsulates each one in a class, and makes them interchangeable. The `api.py` calls `cache.get_exact()` without knowing which backend it's using. You can add a new backend (PostgreSQL, DynamoDB) by implementing the `CacheBackend` interface — zero changes to any other file.

---

## Quick Reference — File Map

```
apps/cache/
├── __init__.py          ← Factory: get_cache_backend() → returns SQLite or Redis
├── base.py              ← CacheBackend ABC: 11 abstract methods (the contract)
├── embeddings.py        ← Shared utilities: embed, normalize, hash, cosine sim
├── sqlite_backend.py    ← SQLiteCacheBackend: implements all 11 methods with SQLite
└── redis_backend.py     ← RedisCacheBackend: implements all 11 methods with Redis

apps/config.py           ← All cache settings (thresholds, TTLs, backend choice)
apps/api.py              ← /chat endpoint with 3-tier cache, response_time_ms, /cache/clear, /cache/stats
docker-compose.yml       ← Redis 7 + RedisInsight containers
.env                     ← CACHE_BACKEND=sqlite, CACHE_ENABLED=true, REDIS_URL=...
```
