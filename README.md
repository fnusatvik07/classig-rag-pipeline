# RAG Classic Pipeline

A production-ready Retrieval-Augmented Generation (RAG) chatbot with a **3-tier caching system**, React frontend, and FastAPI backend.

## Architecture

```
User Question
     |
     v
[ Tier 1: Exact Cache ]  ──hit──>  Return cached answer instantly
     |miss
     v
[ Tier 2: Semantic Cache ] ──hit──>  Return cached answer (rephrased question)
     |miss
     v
[ Tier 3: Retrieval Cache ] ──hit──>  Reuse chunks, re-generate answer via LLM
     |miss
     v
[ Full RAG Pipeline ]
  1. Pinecone vector search (top_k=10)
  2. BGE reranker (top_n=5)
  3. GPT-4o-mini generation
  4. Store results in all 3 cache tiers
```

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- [Pinecone](https://www.pinecone.io/) account (free tier works)
- [OpenAI](https://platform.openai.com/) API key

### 1. Clone and install dependencies

```bash
# Python dependencies (using uv)
uv sync

# Frontend dependencies
cd frontend && npm install && cd ..
```

### 2. Configure environment

Create a `.env` file in the project root:

```env
# Required — API keys
PINECONE_API_KEY=your-pinecone-api-key
OPENAI_API_KEY=your-openai-api-key

# Cache settings (all optional — defaults shown)
CACHE_BACKEND=sqlite                  # "sqlite" or "redis"
CACHE_ENABLED=true
EXACT_CACHE_TTL=604800                # 7 days (seconds)
SEMANTIC_CACHE_TTL=604800             # 7 days
SEMANTIC_CACHE_THRESHOLD=0.92         # cosine similarity for semantic match
RETRIEVAL_CACHE_TTL=86400             # 1 day
RETRIEVAL_CACHE_THRESHOLD=0.85        # cosine similarity for retrieval match
DATABASE_PATH=data/rag_cache.db       # SQLite DB path
REDIS_URL=redis://localhost:6379/0    # only needed if CACHE_BACKEND=redis
OPENAI_EMBED_MODEL=text-embedding-3-small
```

### 3. Start the backend

```bash
python main.py
```

This starts FastAPI on `http://localhost:8000` with auto-reload.

### 4. Start the frontend

```bash
cd frontend
npm run dev
```

Opens on `http://localhost:5173`. The Vite dev server proxies API calls to `:8000`.

### 5. Use the app

1. Upload a PDF/TXT/MD file via the sidebar
2. Ask questions in the chat
3. View source citations, preview PDFs, and monitor cache hits

---

## RAG Pipeline Steps

| Step | Module | Description |
|------|--------|-------------|
| 1 | `apps/ingestion.py` | Extract text from PDF/TXT/MD, track page numbers |
| 2 | `apps/ingestion.py` | Chunk text (512 chars, 64 overlap) with page tracking |
| 3 | `apps/embedding.py` | Create Pinecone index (`multilingual-e5-large` embeddings) |
| 4 | `apps/embedding.py` | Generate embeddings and upsert to Pinecone |
| 5 | `apps/retrieval.py` | Semantic search via Pinecone (top_k=10) |
| 6 | `apps/reranker.py` | Rerank results with `bge-reranker-v2-m3` (top_n=5) |
| 7 | `apps/generation.py` | Generate answer with GPT-4o-mini |
| 8 | `apps/api.py` | FastAPI endpoints orchestrating the full pipeline |

---

## 3-Tier Caching System

### How it works

Every chat query passes through 3 cache tiers before hitting the full pipeline:

**Tier 1 — Exact Match** (hash lookup, O(1))
- Normalized query is hashed with SHA256
- Identical questions return the cached answer instantly
- Source-aware: "What is revenue?" for `Apple.pdf` is cached separately from "All Documents"

**Tier 2 — Semantic Match** (cosine similarity, threshold >= 0.92)
- Embedding of the query is compared against all cached embeddings
- Catches rephrasings: "What is Apple's revenue?" matches "How much revenue did Apple make?"
- Returns the full cached answer without calling the LLM
- Source-aware: only matches entries with the same document filter

**Tier 3 — Retrieval Match** (cosine similarity, threshold >= 0.85)
- Similar to Tier 2, but only caches the retrieved chunks (not the answer)
- Skips the Pinecone call but still runs LLM generation with a fresh answer
- Looser threshold is safe because the LLM adapts the answer to the actual question
- On hit, promotes the result to Tier 1 + 2 for future instant lookups

### Why these thresholds?

| Tier | Threshold | Reasoning |
|------|-----------|-----------|
| Exact | Hash match | Must be identical (after normalization) |
| Semantic | 0.92 | Strict — only true rephrasings deserve the same verbatim answer |
| Retrieval | 0.85 | Looser — similar topics need the same chunks, but LLM generates a fresh answer |

### Cache invalidation

- **Document version**: Uploading or deleting a document bumps a global `doc_version` counter. All cache entries from older versions are automatically invalidated on read.
- **TTL expiry**: Each tier has its own TTL. Expired entries are cleaned up on access and during startup.
- **Manual clear**: Use the Dashboard or `POST /cache/clear` to wipe all tiers.

---

## Cache Backends

### SQLite (default)

Zero infrastructure. Cache is stored in `data/rag_cache.db`.

```env
CACHE_BACKEND=sqlite
DATABASE_PATH=data/rag_cache.db
```

**Inspect the cache directly:**

```bash
# See cache entry counts
sqlite3 data/rag_cache.db "SELECT 'exact', COUNT(*) FROM exact_cache UNION ALL SELECT 'semantic', COUNT(*) FROM semantic_cache UNION ALL SELECT 'retrieval', COUNT(*) FROM retrieval_cache;"

# See exact cache entries
sqlite3 data/rag_cache.db "SELECT query_hash, question_text, hit_count FROM exact_cache;"

# See semantic cache with source filter
sqlite3 data/rag_cache.db "SELECT question_text, source_filter, hit_count FROM semantic_cache;"

# Check doc version
sqlite3 data/rag_cache.db "SELECT * FROM cache_metadata;"

# Clear all cache
sqlite3 data/rag_cache.db "DELETE FROM exact_cache; DELETE FROM semantic_cache; DELETE FROM retrieval_cache;"
```

### Redis

Production-grade, in-memory. Requires a running Redis instance.

**Start Redis with Docker:**

```bash
docker compose up -d
```

This starts:
- **Redis** on port `6379`
- **RedisInsight** (GUI) on port `5540` — open `http://localhost:5540` to browse keys

**Switch to Redis backend:**

```env
CACHE_BACKEND=redis
REDIS_URL=redis://localhost:6379/0
```

**Inspect with redis-cli:**

```bash
# Connect
docker exec -it rag-redis redis-cli

# List all cache keys
KEYS cache:*

# Check exact cache entry
GET cache:exact:<hash>

# Check semantic cache index
SMEMBERS cache:semantic:index

# See a semantic entry
GET cache:semantic:<entry-id>

# Check doc version
GET cache:metadata:doc_version

# Flush everything
FLUSHDB
```

---

## API Endpoints

### Chat

```bash
# Ask a question (full pipeline with caching)
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the revenue?", "use_reranker": true, "debug": true}'

# Filter to a specific document
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the revenue?", "source": "Apple.pdf", "debug": true}'
```

**Response fields:**
- `answer` — LLM-generated response
- `sources` — cited chunks with page numbers and scores
- `cache_hit` — `true` if served from cache
- `cache_tier` — `"exact"`, `"semantic"`, or `"retrieval"` (null if cache miss)
- `response_time_ms` — end-to-end latency
- `retrieved` / `reranked` — debug info (only when `debug: true`)

### Documents

```bash
# Upload a document
curl -X POST http://localhost:8000/upload \
  -F "file=@/path/to/document.pdf"

# List all documents
curl http://localhost:8000/documents

# Preview/download a document
curl http://localhost:8000/documents/Apple.pdf --output Apple.pdf

# Delete a single document (file + vectors + hash)
curl -X DELETE http://localhost:8000/documents/Apple.pdf
```

### Cache Management

```bash
# Get cache stats (per-tier entry counts and hit counts)
curl http://localhost:8000/cache/stats

# Clear all cache tiers
curl -X POST http://localhost:8000/cache/clear
```

**Example `/cache/stats` response:**

```json
{
  "backend": "sqlite",
  "db_path": "/path/to/data/rag_cache.db",
  "doc_version": 3,
  "exact":     { "entries": 5,  "total_hits": 12 },
  "semantic":  { "entries": 5,  "total_hits": 3  },
  "retrieval": { "entries": 4,  "total_hits": 1  }
}
```

### Vector Store

```bash
# Nuclear reset: delete ALL vectors, cache, and uploaded files
curl -X DELETE http://localhost:8000/vectors
```

### Health Check

```bash
curl http://localhost:8000/health
# {"status": "ok"}
```

---

## Testing Cache Behavior

Here's how to verify each cache tier is working:

```bash
# 1. Clear cache first
curl -X POST http://localhost:8000/cache/clear

# 2. First query — should be a cache MISS
curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "What is Apple revenue?"}' | python3 -m json.tool | grep -E "cache_hit|cache_tier|response_time"
# cache_hit: false, cache_tier: null, response_time_ms: ~3000-5000

# 3. Exact same question — should be EXACT HIT
curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "What is Apple revenue?"}' | python3 -m json.tool | grep -E "cache_hit|cache_tier|response_time"
# cache_hit: true, cache_tier: "exact", response_time_ms: ~1-5

# 4. Rephrased question — should be SEMANTIC HIT (if similarity >= 0.92)
curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "How much revenue did Apple generate?"}' | python3 -m json.tool | grep -E "cache_hit|cache_tier|response_time"
# cache_hit: true, cache_tier: "semantic", response_time_ms: ~50-100

# 5. Related but different question — should be RETRIEVAL HIT (if similarity >= 0.85)
curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "Tell me about Apple financial performance"}' | python3 -m json.tool | grep -E "cache_hit|cache_tier|response_time"
# cache_hit: true, cache_tier: "retrieval", response_time_ms: ~1000-2000 (LLM still called)

# 6. Check stats after all queries
curl -s http://localhost:8000/cache/stats | python3 -m json.tool
```

---

## Environment Variables Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `PINECONE_API_KEY` | (required) | Pinecone API key |
| `OPENAI_API_KEY` | (required) | OpenAI API key |
| `CACHE_BACKEND` | `sqlite` | `"sqlite"` or `"redis"` |
| `CACHE_ENABLED` | `true` | Set to `"false"` to disable caching entirely |
| `EXACT_CACHE_TTL` | `604800` | Tier 1 TTL in seconds (7 days) |
| `SEMANTIC_CACHE_TTL` | `604800` | Tier 2 TTL in seconds (7 days) |
| `SEMANTIC_CACHE_THRESHOLD` | `0.92` | Cosine similarity threshold for semantic cache |
| `RETRIEVAL_CACHE_TTL` | `86400` | Tier 3 TTL in seconds (1 day) |
| `RETRIEVAL_CACHE_THRESHOLD` | `0.85` | Cosine similarity threshold for retrieval cache |
| `DATABASE_PATH` | `data/rag_cache.db` | SQLite database file path |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection URL |
| `OPENAI_EMBED_MODEL` | `text-embedding-3-small` | Embedding model for cache similarity |

---

## Project Structure

```
rag-pipeline-classic/
├── main.py                        # FastAPI entry point (uvicorn on :8000)
├── .env                           # Environment variables (API keys, cache config)
├── docker-compose.yml             # Redis + RedisInsight containers
├── pyproject.toml                 # Python dependencies
│
├── apps/
│   ├── api.py                     # All REST endpoints + cache orchestration
│   ├── config.py                  # Configuration from env vars
│   ├── ingestion.py               # PDF/TXT/MD text extraction + chunking
│   ├── embedding.py               # Pinecone index management + upsert/delete
│   ├── retrieval.py               # Pinecone vector search (with source filtering)
│   ├── reranker.py                # BGE reranker (with source filtering)
│   ├── generation.py              # GPT-4o-mini answer generation
│   └── cache/
│       ├── __init__.py            # Cache factory (singleton, backend selection)
│       ├── base.py                # Abstract cache interface (3 tiers)
│       ├── embeddings.py          # normalize_query, hash_query, cosine_similarity
│       ├── sqlite_backend.py      # SQLite implementation
│       └── redis_backend.py       # Redis implementation
│
├── frontend/
│   ├── src/
│   │   ├── App.jsx                # Main app (state, handlers, layout)
│   │   ├── api.js                 # API client functions
│   │   ├── App.css                # All component styles
│   │   ├── index.css              # CSS variables, themes
│   │   └── components/
│   │       ├── ChatArea.jsx       # Chat view with document selector
│   │       ├── ChatInput.jsx      # Message input with Shift+Enter
│   │       ├── ChatMessage.jsx    # Message bubble with markdown + sources
│   │       ├── ChunkComparison.jsx# Retrieved vs reranked chunks comparison
│   │       ├── Dashboard.jsx      # Cache stats + document management
│   │       ├── FileUpload.jsx     # Drag-and-drop file upload
│   │       ├── PdfPreview.jsx     # Resizable PDF viewer + source cards
│   │       ├── Sidebar.jsx        # Navigation, documents, controls
│   │       ├── SourceList.jsx     # Source citations list
│   │       └── SuggestedQuestions.jsx # Landing page with features
│   └── vite.config.js             # Dev proxy to :8000
│
├── data/                          # SQLite cache DB (auto-created)
└── uploads/                       # Uploaded documents (auto-created)
```

---

## Frontend Features

- **Document selector**: Chat with all documents or filter to a specific one
- **PDF preview**: Side panel with resizable width (drag the left edge)
- **Source cards**: Collapsible panel showing reranked chunks with page jump
- **Cache indicators**: Each response shows cache tier hit and response time
- **Chat persistence**: Messages survive page refresh (localStorage)
- **Dark mode**: Toggle in sidebar, preference persisted
- **Dashboard**: Cache stats cards + document management with delete
- **Export**: Download chat history as Markdown
