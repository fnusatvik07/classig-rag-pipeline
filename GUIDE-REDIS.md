# Redis — Complete Beginner's Guide

> This guide explains Redis from scratch — what it is, how it works internally, why it's fast,
> and how we use it in our RAG caching system. No prior Redis knowledge needed.

---

## Table of Contents

1. [What is Redis?](#1-what-is-redis)
2. [Why is Redis So Fast?](#2-why-is-redis-so-fast)
3. [Redis vs Traditional Databases](#3-redis-vs-traditional-databases)
4. [Core Data Types](#4-core-data-types)
5. [How Redis Stores Data (Internals)](#5-how-redis-stores-data-internals)
6. [TTL — Auto-Expiring Keys](#6-ttl--auto-expiring-keys)
7. [Persistence — How Redis Survives Restarts](#7-persistence--how-redis-survives-restarts)
8. [Setup Guide — Running Redis Locally](#8-setup-guide--running-redis-locally)
9. [Redis CLI — Hands-On Commands](#9-redis-cli--hands-on-commands)
10. [RedisInsight — Visual Dashboard](#10-redisinsight--visual-dashboard)
11. [How We Use Redis in Our RAG Cache](#11-how-we-use-redis-in-our-rag-cache)
12. [Redis in Production](#12-redis-in-production)
13. [Common Pitfalls](#13-common-pitfalls)
14. [Interview Questions](#14-interview-questions)

---

## 1. What is Redis?

**Redis** = **RE**mote **DI**ctionary **S**erver

It's an **in-memory key-value store**. Think of it as a giant Python dictionary that:
- Lives in RAM (not on disk) → extremely fast
- Is accessible over the network → any app can connect to it
- Supports multiple data types (not just strings)
- Can optionally persist data to disk

```
Traditional database:     Data lives on DISK, loaded into memory when needed
Redis:                    Data lives in MEMORY, optionally saved to disk

                    ┌──────────────┐
Your App ──────────→│    Redis     │
                    │  (in RAM)    │
                    │              │
                    │  key1 → val1 │
                    │  key2 → val2 │
                    │  key3 → val3 │
                    └──────┬───────┘
                           │ (optional)
                           ▼
                    ┌──────────────┐
                    │    Disk      │
                    │  (backup)    │
                    └──────────────┘
```

### Real-World Analogy

Think of a **library**:
- **Traditional DB** = Books on shelves. To read something, you walk to the shelf, find the book, bring it to your desk. Slow but you have millions of books.
- **Redis** = A small desk with the 100 most-used books already open on it. Instant access, but limited space (RAM is expensive).

### Where Redis is Used

- **Caching** — store frequently accessed data (our use case)
- **Session storage** — user login sessions in web apps
- **Rate limiting** — track API request counts per user
- **Real-time leaderboards** — sorted sets for gaming/ranking
- **Pub/Sub messaging** — real-time chat, notifications
- **Job queues** — background task processing (Celery, Sidekiq)

Companies using Redis: Twitter, GitHub, Snapchat, Stack Overflow, Airbnb.

---

## 2. Why is Redis So Fast?

Redis can handle **100,000+ operations per second** on a single server. Here's why:

### Reason 1: In-Memory Storage

```
Disk read:    ~10,000,000 nanoseconds  (10 ms)
RAM read:     ~100 nanoseconds          (0.0001 ms)

RAM is ~100,000x faster than disk.
```

Everything in Redis lives in RAM. No disk seeks, no I/O waits.

### Reason 2: Single-Threaded Event Loop

```
Multi-threaded DB:
  Thread 1: read key A ──→ lock ──→ read ──→ unlock
  Thread 2: read key B ──→ lock ──→ wait... ──→ read ──→ unlock
  Thread 3: write key A ──→ lock ──→ wait... ──→ wait... ──→ write

Redis (single-threaded):
  read A → read B → write A → read C → write B → ...
  (no locks, no waiting, no context switching)
```

Counterintuitive: one thread is FASTER than many threads because:
- No lock contention (threads don't fight over resources)
- No context switching (CPU doesn't waste time switching between threads)
- Operations are so fast (microseconds) that one thread handles them all

### Reason 3: Simple Data Structures

Redis uses optimized C data structures (hash tables, skip lists, zip lists) tuned for in-memory access. No SQL parsing, no query planning, no join operations.

### Reason 4: Efficient Protocol

Redis uses RESP (Redis Serialization Protocol) — a simple text protocol:
```
Client sends:  *3\r\n$3\r\nSET\r\n$4\r\nname\r\n$5\r\nAlice\r\n
Server sends:  +OK\r\n
```
Minimal overhead. No HTTP headers, no XML, no JSON wrapping.

---

## 3. Redis vs Traditional Databases

```
┌──────────────────┬─────────────┬──────────────┬──────────────┐
│                  │   Redis     │   SQLite     │  PostgreSQL  │
├──────────────────┼─────────────┼──────────────┼──────────────┤
│ Storage          │ RAM         │ File on disk │ Disk + cache │
│ Speed (read)     │ ~0.1ms      │ ~0.5ms       │ ~1-5ms       │
│ Speed (write)    │ ~0.1ms      │ ~1ms         │ ~2-10ms      │
│ Data model       │ Key-Value   │ Relational   │ Relational   │
│ Query language   │ Commands    │ SQL          │ SQL          │
│ Max data size    │ RAM size    │ Disk size    │ Disk size    │
│ Persistence      │ Optional    │ Always       │ Always       │
│ Schema           │ Schema-less │ Tables       │ Tables       │
│ Concurrent users │ Thousands   │ ~10          │ Hundreds     │
│ Infrastructure   │ Server      │ None (file)  │ Server       │
│ Best for         │ Cache, temp │ Local, small │ Production   │
└──────────────────┴─────────────┴──────────────┴──────────────┘
```

### When to use what?

```
"I need to cache API responses"          → Redis
"I need a local database for an app"     → SQLite
"I need a production database"           → PostgreSQL
"I need both caching AND a database"     → Redis + PostgreSQL
"I'm learning and want zero setup"       → SQLite
```

---

## 4. Core Data Types

Redis isn't just key→string. It supports 5 main data types:

### 4.1 Strings

The simplest type. A key maps to a single value.

```redis
SET name "Alice"          -- store
GET name                  -- retrieve → "Alice"
SET counter 0             -- numbers are stored as strings
INCR counter              -- atomic increment → 1
INCR counter              -- → 2
SETEX temp 60 "data"      -- set with 60-second TTL (auto-deletes)
```

**We use this for**: Tier 1 exact cache entries, doc_version counter.

### 4.2 Hashes

A key maps to a collection of field-value pairs (like a Python dict inside a dict).

```redis
HSET user:1 name "Alice" age "30" city "NYC"
HGET user:1 name          -- → "Alice"
HGETALL user:1             -- → {name: "Alice", age: "30", city: "NYC"}
```

```
Key "user:1" → { name: "Alice", age: "30", city: "NYC" }
```

### 4.3 Lists

Ordered collection (like a Python list). Supports push/pop from both ends.

```redis
LPUSH queue "task1"        -- push to left (front)
LPUSH queue "task2"
RPUSH queue "task3"        -- push to right (back)
LRANGE queue 0 -1          -- → ["task2", "task1", "task3"]
RPOP queue                 -- pop from right → "task3"
```

**Used for**: Job queues, recent activity logs, chat message history.

### 4.4 Sets

Unordered collection of unique values (like a Python set).

```redis
SADD tags "python" "redis" "caching"
SADD tags "python"          -- duplicate, ignored
SMEMBERS tags               -- → {"python", "redis", "caching"}
SISMEMBER tags "redis"      -- → 1 (true)
SCARD tags                  -- → 3 (count)
```

**We use this for**: Tracking all semantic/retrieval cache entry IDs (`cache:semantic:index`).

### 4.5 Sorted Sets

Like sets, but each member has a score. Automatically sorted by score.

```redis
ZADD leaderboard 100 "Alice"
ZADD leaderboard 85 "Bob"
ZADD leaderboard 95 "Charlie"
ZRANGE leaderboard 0 -1 WITHSCORES
-- → [("Bob", 85), ("Charlie", 95), ("Alice", 100)]
ZREVRANGE leaderboard 0 0
-- → "Alice" (top scorer)
```

**Used for**: Leaderboards, priority queues, time-series with timestamps as scores.

### Visual summary

```
STRING:      key → "value"
HASH:        key → { field1: val1, field2: val2, ... }
LIST:        key → [ val1, val2, val3, ... ]      (ordered)
SET:         key → { val1, val2, val3, ... }       (unique, unordered)
SORTED SET:  key → { (score1, val1), (score2, val2), ... }  (unique, sorted)
```

---

## 5. How Redis Stores Data (Internals)

### The Hash Table

At its core, Redis is a **hash table** — the same data structure as Python's `dict`.

```
Hash table (simplified):

Index  Bucket
  0    → NULL
  1    → "name" → "Alice"
  2    → NULL
  3    → "age" → "30"
  4    → "cache:exact:abc" → "{answer: ...}"
  5    → NULL
  ...

hash("name") % table_size = 1    → stored at index 1
hash("age") % table_size = 3     → stored at index 3
```

**Lookup is O(1)**: compute hash → go directly to index → get value. No scanning.

### Memory Layout

```
Redis process in RAM:
┌─────────────────────────────────────────────┐
│  Global hash table                           │
│  ┌─────────────────────────────────────┐    │
│  │ key1 → pointer to value object      │    │
│  │ key2 → pointer to value object      │    │
│  │ key3 → pointer to value object      │    │
│  └─────────────────────────────────────┘    │
│                                              │
│  Value objects:                               │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐    │
│  │ type:str  │ │ type:set │ │ type:str │    │
│  │ data:     │ │ data:    │ │ data:    │    │
│  │ "hello"   │ │ {a,b,c}  │ │ "{json}" │    │
│  │ ttl: 300  │ │ ttl: -1  │ │ ttl: 86k │    │
│  └──────────┘ └──────────┘ └──────────┘    │
│                                              │
│  Expires table (keys with TTL):              │
│  ┌─────────────────────────────────────┐    │
│  │ key1 → expires at 1708617600        │    │
│  │ key3 → expires at 1708704000        │    │
│  └─────────────────────────────────────┘    │
└─────────────────────────────────────────────┘
```

### Memory Overhead

Each key-value pair has overhead:
- Key: ~40 bytes + key string length
- Value: ~16 bytes + value data
- Total per entry: ~60-100 bytes overhead

**Example**: 10,000 cache entries with 1KB values each:
- Data: 10,000 × 1KB = 10MB
- Overhead: 10,000 × 80B = 0.8MB
- Total: ~11MB of RAM

---

## 6. TTL — Auto-Expiring Keys

One of Redis's most powerful features. Set a key to auto-delete after N seconds.

### How TTL works

```redis
SET session:abc "user_data"     -- key exists forever
EXPIRE session:abc 3600         -- will auto-delete in 1 hour
TTL session:abc                 -- → 3598 (seconds remaining)

-- Or set + expire in one command:
SETEX session:abc 3600 "user_data"
```

```
Timeline:
  t=0s      SET session:abc "data" with TTL=3600
  t=1800s   TTL session:abc → 1800 (30 minutes left)
  t=3599s   TTL session:abc → 1 (1 second left)
  t=3600s   Key vanishes automatically. GET returns nil.
```

### How Redis implements TTL (internally)

Redis uses two strategies:

**1. Lazy expiration**: When you `GET` a key, Redis checks if it's expired. If yes, delete it and return nil. Cheap, but expired keys linger until accessed.

**2. Active expiration**: Every 100ms, Redis randomly samples 20 keys with TTL. If >25% are expired, it samples 20 more. This gradually cleans up expired keys in the background.

```
Every 100ms:
  1. Pick 20 random keys that have TTL
  2. Delete the expired ones
  3. If more than 25% were expired → repeat immediately
  4. Otherwise → wait 100ms and repeat
```

### How we use TTL

```python
# In our Redis cache backend:
self._redis.setex(key, ttl_seconds, data)

# Tier 1 + 2: TTL = 604800 (7 days)
# Tier 3:     TTL = 86400  (1 day)
```

Redis handles cleanup automatically — no cron job, no background thread in Python.

Compare with SQLite where WE have to check and delete expired entries:
```python
# SQLite: manual TTL check on every lookup
if now - row["created_at"] > row["ttl_seconds"]:
    conn.execute("DELETE ...")  # we do it ourselves
```

---

## 7. Persistence — How Redis Survives Restarts

Redis is in-memory, but it CAN persist data to disk. Two mechanisms:

### RDB (Redis Database) Snapshots

Takes a full snapshot of all data at intervals.

```
Config: save 900 1        → snapshot if 1+ keys changed in 900 seconds
Config: save 300 10       → snapshot if 10+ keys changed in 300 seconds

Timeline:
  t=0      Redis has 1000 keys in RAM
  t=300    15 keys changed → trigger snapshot
           Redis forks a child process
           Child writes ALL data to dump.rdb
           Parent continues serving requests (no downtime)
  t=301    dump.rdb saved to disk (complete backup)
```

**Pro**: Compact file, fast restart
**Con**: Can lose last few minutes of data (between snapshots)

### AOF (Append Only File)

Logs every write command to a file.

```
appendonly.aof:
  SET cache:exact:abc "{...}"
  SET cache:semantic:def "{...}"
  INCR cache:metadata:doc_version
  DEL cache:exact:abc
  ...
```

On restart, Redis replays the AOF file to reconstruct the data.

**Pro**: At most 1 second of data loss (with `appendfsync everysec`)
**Con**: Larger file, slower restart (must replay all commands)

### What we use

Our `docker-compose.yml` uses the Redis default: RDB snapshots. For a cache, this is fine — losing a few cached entries on crash is acceptable (they'll be regenerated on the next query).

```yaml
volumes:
  - redis_data:/data    # This is where dump.rdb lives
```

### What if Redis crashes?

```
Scenario: Redis crashes, restarts

WITH persistence (our setup):
  1. Redis starts
  2. Loads dump.rdb from /data volume
  3. Cache data restored (minus last few minutes of changes)
  4. App continues working

WITHOUT persistence:
  1. Redis starts
  2. Empty database
  3. All cache is cold — first queries will be slow (cache miss)
  4. Cache rebuilds over time as questions are asked
```

For a **cache**, both are acceptable. Caches are designed to be rebuildable. This is different from a primary database where data loss is catastrophic.

---

## 8. Setup Guide — Running Redis Locally

### Prerequisites

- **Docker Desktop** installed ([download here](https://www.docker.com/products/docker-desktop/))
- Our `docker-compose.yml` in the project root

### Step-by-Step

#### Step 1: Start Docker Desktop

- **macOS**: `Cmd + Space` → type "Docker" → open Docker Desktop
- **Windows**: Start menu → "Docker Desktop"
- **Linux**: `sudo systemctl start docker`

Wait until the whale icon stops animating (engine is ready).

```bash
# Verify Docker is running
docker --version         # Docker version 27.x.x
docker ps                # Should show empty table (no error)
```

If you see `Cannot connect to the Docker daemon` → Docker Desktop isn't open yet.

#### Step 2: Start Redis + RedisInsight

```bash
cd ~/Desktop/rag-pipeline-classic
docker compose up -d
```

This starts two containers:
- `rag-redis` — Redis server on port 6379
- `rag-redisinsight` — Web dashboard on port 5540

Expected output:
```
[+] Running 3/3
 ✔ Network rag-pipeline-classic_default  Created
 ✔ Container rag-redis                   Started
 ✔ Container rag-redisinsight            Started
```

#### Step 3: Verify

```bash
# Check containers are running
docker ps
# Should show both rag-redis and rag-redisinsight

# Ping Redis
docker exec rag-redis redis-cli ping
# → PONG
```

#### Step 4: Connect to RedisInsight (Web UI)

1. Open **http://localhost:5540** in your browser
2. **Accept the license** — toggle the "I have read and understood..." checkbox and click **CONFIRM**
3. On the welcome screen, click **"I already have a database"**
4. Click **"Connect to a Redis Database"**
5. You'll see a connection form with a URL field pre-filled as `redis://default@127.0.0.1:6379`.
   **Change the host** from `127.0.0.1` to `redis` so the URL becomes:
   ```
   redis://default@redis:6379
   ```
   > **Why `redis` and not `localhost`/`127.0.0.1`?**
   > Both containers (Redis + RedisInsight) live inside the same Docker network
   > created by `docker-compose.yml`. Inside that network, containers find each
   > other by their **service name**, not by localhost. Our Redis service is named
   > `redis` in docker-compose.yml, so that's the hostname RedisInsight uses.
6. Give it a name — type `RAG Cache` in the **Database Alias** field
7. Click **"Add Redis Database"**
8. Click on **"RAG Cache"** in the database list to connect

You'll land on the **Browser** tab — this is where you can explore all keys, values, TTLs, and memory usage. Right now it will be empty because the FastAPI backend hasn't started yet. Once you set `CACHE_BACKEND=redis` in `.env` and start the backend, keys will appear here as you ask questions.

#### Step 5: Switch your app to Redis backend

Edit `.env`:
```
CACHE_BACKEND=redis
```

Restart the backend:
```bash
uv run python main.py
```

### Common Docker Commands

```bash
# Start containers (background)
docker compose up -d

# Stop containers (data preserved)
docker compose down

# Stop containers AND delete all data
docker compose down -v

# View logs
docker compose logs redis
docker compose logs redisinsight

# Restart just Redis
docker compose restart redis

# Check container health
docker ps
```

### What's in `docker-compose.yml`?

```yaml
services:
  redis:
    image: redis:7-alpine         # Redis 7 on Alpine Linux (~30MB)
    container_name: rag-redis      # Fixed name for easy reference
    ports:
      - "6379:6379"               # Expose Redis port to host machine
    volumes:
      - redis_data:/data          # Persist snapshots across restarts
    restart: unless-stopped        # Auto-restart on crash
    healthcheck:                   # Docker monitors Redis health
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 3

  redisinsight:
    image: redis/redisinsight:latest   # Official Redis web UI
    container_name: rag-redisinsight
    ports:
      - "5540:5540"                    # Web dashboard port
    depends_on:
      - redis                          # Start after Redis is ready
    restart: unless-stopped

volumes:
  redis_data:                     # Named Docker volume for persistence
```

**Why Alpine?** Alpine Linux is ~5MB. `redis:7-alpine` is ~30MB vs `redis:7` at ~130MB. Same Redis, smaller download.

**Why `depends_on`?** RedisInsight needs Redis to be running first. Docker starts Redis, then RedisInsight.

**Why a named volume?** Without it, data is lost when the container stops. The `redis_data` volume persists across `docker compose down` and `docker compose up`.

### Troubleshooting

| Problem | Cause | Solution |
|---------|-------|----------|
| `Cannot connect to Docker daemon` | Docker Desktop not running | Open Docker Desktop, wait for startup |
| `Port 6379 already in use` | Another Redis/service on that port | `lsof -i :6379` to find it, or change port in docker-compose.yml to `"6380:6379"` |
| `redis.exceptions.ConnectionError` in Python | Redis container not running | `docker compose up -d` |
| RedisInsight shows "Unable to connect" | Wrong host | Try `host.docker.internal` instead of `redis` |
| Container starts then immediately stops | Image issue or port conflict | `docker compose logs redis` to see error |
| Data gone after restart | Used `docker compose down -v` | The `-v` flag deletes volumes. Use `down` without `-v` |

---

## 9. Redis CLI — Hands-On Commands

### Opening the CLI

```bash
docker exec -it rag-redis redis-cli
```

You'll see:
```
127.0.0.1:6379>
```

Type `QUIT` or `exit` to leave.

### Essential Commands

#### Basic Operations
```redis
-- Set a key
SET greeting "Hello World"

-- Get a key
GET greeting
-- → "Hello World"

-- Check if key exists
EXISTS greeting
-- → 1 (true)

-- Delete a key
DEL greeting
-- → 1 (deleted)

-- Get all keys (careful in production!)
KEYS *

-- Count total keys
DBSIZE

-- Delete everything (dangerous!)
FLUSHDB
```

#### TTL Operations
```redis
-- Set key with 60-second expiry
SETEX temp 60 "expires soon"

-- Check remaining TTL
TTL temp
-- → 58 (seconds left)

-- Key without TTL
SET permanent "stays forever"
TTL permanent
-- → -1 (no expiry)

-- Add TTL to existing key
EXPIRE permanent 3600

-- Remove TTL (make permanent again)
PERSIST permanent
```

#### Working with our cache data
```redis
-- See all cache keys
KEYS cache:*

-- View doc version
GET cache:metadata:doc_version

-- View an exact cache entry (returns JSON)
GET cache:exact:<paste-a-hash-here>

-- View all semantic cache entry IDs
SMEMBERS cache:semantic:index

-- Check how many semantic entries exist
SCARD cache:semantic:index

-- Check TTL on a cache entry
TTL cache:exact:<hash>
```

#### Useful info commands
```redis
-- Server info
INFO server

-- Memory usage
INFO memory

-- How many keys in the database
INFO keyspace

-- All connected clients
CLIENT LIST

-- Performance stats
INFO stats
```

### CLI Tips

```redis
-- Pretty-print JSON (pipe through jq outside CLI)
-- In terminal (not inside redis-cli):
docker exec rag-redis redis-cli GET cache:exact:abc123 | python3 -m json.tool

-- Monitor all commands in real-time (great for debugging):
-- In terminal:
docker exec rag-redis redis-cli MONITOR
-- Now use your app — you'll see every Redis command fly by
```

---

## 10. RedisInsight — Visual Dashboard

### What is RedisInsight?

It's the **official Redis GUI** — a web app that lets you browse, search, and manage Redis data visually. Like phpMyAdmin for MySQL, but for Redis.

### Accessing it

Open **http://localhost:5540** after running `docker compose up -d`.

### Key Features

#### Browser Tab
- See all keys in a searchable list
- Click any key to view its value, type, TTL, memory usage
- Filter by key pattern (e.g., `cache:exact:*`)
- Add, edit, or delete keys visually

#### CLI Tab
- Built-in Redis CLI in the browser
- Auto-complete for commands
- Command history

#### Profiler Tab
- Real-time view of all commands being executed
- Like `MONITOR` but visual
- Great for debugging: ask a question in the chatbot, watch the Redis commands

#### Database Analysis
- Memory usage breakdown by key pattern
- Key count by type
- TTL distribution

### What to look for in our cache

After using the chatbot with `CACHE_BACKEND=redis`:

1. **Filter by `cache:exact:*`** — see all Tier 1 entries. Each is a JSON string with question, answer, sources.
2. **Filter by `cache:semantic:*`** — see Tier 2 entries. These include `embedding_hex` (the vector as hex bytes).
3. **Check `cache:metadata:doc_version`** — should be an integer. Increases when documents are uploaded.
4. **Check `cache:semantic:index`** — a SET containing all semantic entry UUIDs.
5. **Click any key** → see its TTL countdown in real-time.

---

## 11. How We Use Redis in Our RAG Cache

### Our key structure

```
cache:exact:<sha256_hash>         STRING   JSON with question, answer, sources
cache:semantic:<uuid>             STRING   JSON with question, embedding, answer, sources
cache:retrieval:<uuid>            STRING   JSON with question, embedding, chunks
cache:metadata:doc_version        STRING   integer counter
cache:semantic:index              SET      all semantic entry UUIDs
cache:retrieval:index             SET      all retrieval entry UUIDs
```

### Example: What happens when you ask "What was Apple's revenue?"

**First time (cache miss):**
```
1. CACHE_BACKEND=redis
2. Normalize → "what was apple's revenue" → hash → "0d95..."
3. GET cache:exact:0d95...                          → nil (miss)
4. Embed via OpenAI → [0.023, -0.015, ...]
5. SMEMBERS cache:semantic:index                    → empty (miss)
6. SMEMBERS cache:retrieval:index                   → empty (miss)
7. Full RAG pipeline runs → answer generated
8. SETEX cache:exact:0d95... 604800 '{"answer":...}'    ← store Tier 1
9. SETEX cache:semantic:<uuid> 604800 '{"answer":...}'  ← store Tier 2
10. SADD cache:semantic:index <uuid>                     ← track in index
11. SETEX cache:retrieval:<uuid> 86400 '{"chunks":...}'  ← store Tier 3
12. SADD cache:retrieval:index <uuid>                     ← track in index
```

**Second time (exact hit):**
```
1. Normalize → "what was apple's revenue" → hash → "0d95..."
2. GET cache:exact:0d95...                          → '{"answer": "Apple reported..."}'
3. HIT! Return cached answer instantly.
   No embedding, no Pinecone, no LLM.
```

**Third time with rephrasing "Apple revenues?" (semantic hit):**
```
1. Normalize → "apple revenues" → hash → "7f3a..." (different hash)
2. GET cache:exact:7f3a...                          → nil (Tier 1 miss)
3. Embed "Apple revenues?" → [0.022, -0.016, ...]
4. SMEMBERS cache:semantic:index                    → {<uuid>}
5. GET cache:semantic:<uuid>                        → load entry
6. Deserialize embedding, compute cosine similarity → 0.97
7. 0.97 >= 0.95 threshold → HIT!
8. Return cached answer.
   Cost: only one OpenAI embedding call ($0.00002).
```

### Why we use SETs for indexes

Redis doesn't have "tables" like SQL. We can't do `SELECT * FROM semantic_cache`. Instead:

```
Problem: How do we find ALL semantic cache entries to scan?
Solution: Keep a SET of all entry UUIDs

cache:semantic:index = { "a1b2c3", "d4e5f6", "g7h8i9" }

To scan all entries:
  1. SMEMBERS cache:semantic:index    → get all IDs
  2. For each ID: GET cache:semantic:<id>   → get data
  3. Compare embeddings, find best match
```

The SET stays in sync because:
- `set_semantic()` calls both `SETEX` (store data) and `SADD` (add to index)
- When a key expires (TTL), the SET still has the UUID → `get_semantic()` detects this (`GET` returns nil) and calls `SREM` to clean up the orphan

### The `INCR` trick for doc_version

```redis
-- When a document is uploaded, we increment the version:
INCR cache:metadata:doc_version
-- → 1

-- INCR is ATOMIC — even if 100 uploads happen simultaneously,
-- each gets a unique incremented value. No race conditions.

-- Compare with SQLite where we need: read → add 1 → write (3 steps, not atomic)
```

---

## 12. Redis in Production

### Managed Redis Services

In production, you typically don't run Redis on Docker. Instead use managed services:

| Service | Provider | Free Tier |
|---------|----------|-----------|
| Redis Cloud | Redis Inc. | 30MB free |
| ElastiCache | AWS | No free tier |
| Azure Cache for Redis | Microsoft | No free tier |
| Memorystore | Google Cloud | No free tier |
| Upstash | Upstash | 10K commands/day free |

To switch from local Docker to a cloud Redis:
```bash
# Just change the URL in .env:
REDIS_URL=redis://default:password@redis-12345.c1.us-east-1.ec2.cloud.redislabs.com:12345
```

No code changes needed — our `RedisCacheBackend` connects to whatever URL is in `REDIS_URL`.

### Redis Cluster (Horizontal Scaling)

Single Redis: ~100K ops/sec, limited by RAM of one machine.

Redis Cluster: Split keys across multiple machines.
```
Key hash → slot 0-5460     → Node 1 (32GB RAM)
Key hash → slot 5461-10922 → Node 2 (32GB RAM)
Key hash → slot 10923-16383 → Node 3 (32GB RAM)

Total capacity: 96GB RAM, ~300K ops/sec
```

### Redis Sentinel (High Availability)

Automatic failover if the primary Redis dies:
```
              ┌──────────┐
              │ Sentinel │ (monitors)
              └────┬─────┘
                   │
          ┌────────┴────────┐
          ▼                 ▼
    ┌──────────┐     ┌──────────┐
    │ Primary  │────→│ Replica  │
    │ (writes) │     │ (reads)  │
    └──────────┘     └──────────┘

If Primary dies → Sentinel promotes Replica to Primary
```

---

## 13. Common Pitfalls

### Pitfall 1: Using KEYS in Production
```redis
KEYS *          -- Scans ALL keys. Blocks Redis for seconds on large databases.
SCAN 0          -- Use SCAN instead. Non-blocking, returns results in batches.
```

### Pitfall 2: Storing Large Values
```
BAD:  SET big_key <10MB JSON blob>
GOOD: Break into smaller keys or use a different storage for large data
```
Redis is optimized for values under 100KB. Large values block the single thread.

### Pitfall 3: Not Setting TTL on Cache Keys
```
BAD:  SET cache:query:abc "{answer}"      -- lives forever, RAM fills up
GOOD: SETEX cache:query:abc 604800 "..."  -- auto-expires in 7 days
```
Without TTL, your Redis memory grows until the server runs out of RAM and crashes.

### Pitfall 4: Assuming Redis is a Database
Redis CAN persist data, but it's primarily a cache. Design your system so that:
- If Redis loses all data → the app still works (just slower, cache rebuilds)
- Critical data belongs in PostgreSQL/MySQL, not Redis

### Pitfall 5: Using the Wrong Data Type
```
BAD:  Storing a list as a JSON string in a STRING key, then parsing in Python
GOOD: Using a native LIST type and LPUSH/RPOP commands
```
Redis data types have built-in operations. Use them instead of doing everything in your application.

---

## 14. Interview Questions

**Q: What is Redis and why is it fast?**
A: Redis is an in-memory key-value store. It's fast because: (1) data lives in RAM (~100,000x faster than disk), (2) single-threaded event loop avoids lock contention and context switching, (3) optimized C data structures, (4) simple wire protocol.

**Q: What happens when Redis runs out of memory?**
A: Depends on the `maxmemory-policy` config:
- `noeviction` (default): Returns error on writes, reads still work
- `allkeys-lru`: Evicts least recently used keys to make room
- `volatile-lru`: Only evicts keys that have a TTL set
- `allkeys-random`: Evicts random keys
For a cache, `allkeys-lru` is usually the best policy.

**Q: How does Redis persist data?**
A: Two mechanisms: (1) RDB snapshots — periodic full dumps to disk, fast restart but can lose recent data. (2) AOF — logs every write command, minimal data loss but slower restart. You can use both together.

**Q: Is Redis single-threaded? Isn't that slow?**
A: Redis is single-threaded for command processing, but uses I/O threads for network operations (since Redis 6). Single-threaded is FASTER for Redis's workload because: no locks, no context switches, and operations are microsecond-fast. The bottleneck is network I/O, not CPU.

**Q: Redis vs Memcached?**
A: Redis has richer data types (lists, sets, sorted sets, hashes), built-in persistence, pub/sub, Lua scripting, and cluster support. Memcached is simpler (string-only), slightly faster for pure string caching, and uses multi-threading. For most modern applications, Redis is preferred.

**Q: How would you handle cache invalidation with Redis?**
A: Three approaches: (1) TTL — set expiry on keys, Redis auto-deletes. (2) Event-driven — explicitly delete or version-tag entries when source data changes. (3) Manual — provide an API endpoint to clear the cache. We use all three in our RAG cache.

**Q: What's the difference between `EXPIRE` and `SETEX`?**
A: `SETEX key ttl value` sets the key AND TTL atomically in one command. `SET key value` + `EXPIRE key ttl` is two commands — if the app crashes between them, you have a key without TTL (memory leak). Always prefer `SETEX` for cache entries.

---

## Quick Reference Card

```
┌────────────────────────────────────────────────────────────┐
│  REDIS QUICK REFERENCE                                      │
├────────────────────────────────────────────────────────────┤
│                                                             │
│  Start Redis:    docker compose up -d                       │
│  Stop Redis:     docker compose down                        │
│  Open CLI:       docker exec -it rag-redis redis-cli       │
│  Web UI:         http://localhost:5540                       │
│                                                             │
│  STRINGS:                                                   │
│    SET key val         GET key           DEL key            │
│    SETEX key ttl val   TTL key           EXISTS key         │
│    INCR key            DECR key          KEYS pattern       │
│                                                             │
│  SETS:                                                      │
│    SADD key member     SMEMBERS key      SCARD key          │
│    SREM key member     SISMEMBER key member                 │
│                                                             │
│  INFO:                                                      │
│    DBSIZE              INFO memory       INFO keyspace      │
│    MONITOR             CLIENT LIST       CONFIG GET *       │
│                                                             │
│  DANGER ZONE:                                               │
│    FLUSHDB             FLUSHALL          KEYS * (in prod)   │
│                                                             │
│  Our cache keys:                                            │
│    cache:exact:<hash>           Tier 1 (exact match)        │
│    cache:semantic:<uuid>        Tier 2 (semantic match)     │
│    cache:retrieval:<uuid>       Tier 3 (retrieval cache)    │
│    cache:metadata:doc_version   Document version counter    │
│    cache:semantic:index         SET of Tier 2 entry IDs     │
│    cache:retrieval:index        SET of Tier 3 entry IDs     │
│                                                             │
└────────────────────────────────────────────────────────────┘
```
