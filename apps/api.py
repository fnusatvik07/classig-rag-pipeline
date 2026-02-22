import hashlib
import json
import logging
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional

from .ingestion import ingest_document
from .embedding import upsert_chunks, delete_all_vectors
from .retrieval import search
from .reranker import rerank
from .generation import generate_answer
from .config import (
    CACHE_ENABLED,
    EXACT_CACHE_TTL,
    SEMANTIC_CACHE_TTL,
    SEMANTIC_CACHE_THRESHOLD,
    RETRIEVAL_CACHE_TTL,
    RETRIEVAL_CACHE_THRESHOLD,
)
from .cache import get_cache_backend
from .cache.embeddings import embed_query, normalize_query, hash_query

logger = logging.getLogger(__name__)

# ── App Lifespan ───────────────────────────────────────────────

@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Startup/shutdown events."""
    # Startup: initialize cache and clean expired entries
    if CACHE_ENABLED:
        cache = get_cache_backend()
        removed = cache.cleanup_expired()
        if removed:
            logger.info(f"Cache startup cleanup: removed {removed} expired entries")
    yield
    # Shutdown: nothing needed

# ── FastAPI App ────────────────────────────────────────────────

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = FastAPI(
    title="RAG Classic Chatbot",
    description="A Classic RAG Chatbot with Multi-Tier Caching",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Request / Response Models ──────────────────────────────────

class IngestRequest(BaseModel):
    file_path: str

class IngestResponse(BaseModel):
    file: str
    chunks: int
    message: str


class ChatRequest(BaseModel):
    question: str
    use_reranker: bool = True
    debug: bool = False


class SourceChunk(BaseModel):
    id: str
    score: float
    source: str
    pages: str
    chunk_text: str
    citation: str


class ChatResponse(BaseModel):
    answer: str
    sources: List[SourceChunk]
    retrieved: Optional[List[SourceChunk]] = None
    reranked: Optional[List[SourceChunk]] = None
    cache_hit: bool = False
    cache_tier: Optional[str] = None
    response_time_ms: Optional[float] = None


class GenerateRequest(BaseModel):
    question: str
    top_k: int = 10
    top_n: int = 5
    use_reranker: bool = True


class GenerateResponse(BaseModel):
    question: str
    answer: str
    sources: List[SourceChunk]
    pipeline: str


class SearchRequest(BaseModel):
    query: str
    top_k: Optional[int] = 10
    user_reranker: bool = True


class UploadResponse(BaseModel):
    file: str
    chunks: int
    message: str


# ── Helper ─────────────────────────────────────────────────────

def _to_source(c, idx):
    """Convert a chunk dict to a SourceChunk model."""
    return SourceChunk(
        id=c["id"],
        score=c["score"],
        source=c["source"],
        pages=c.get("pages", ""),
        chunk_text=c["chunk_text"][:200] + "....",
        citation=f"[{idx}]",
    )


def _sources_to_json(sources: List[SourceChunk]) -> str:
    """Serialize SourceChunk list to JSON for cache storage."""
    return json.dumps([s.model_dump() for s in sources])


def _json_to_sources(sources_json: str) -> List[SourceChunk]:
    """Deserialize JSON back to SourceChunk list."""
    return [SourceChunk(**s) for s in json.loads(sources_json)]


# ── Endpoints ──────────────────────────────────────────────────

@app.get("/health")
def health_check():
    """Simple Health Check"""
    return {"status": "ok"}


@app.post("/ingest", response_model=IngestResponse)
def ingest_endpoint(req: IngestRequest):
    """Ingest a document, Extract Text, Chunk, Embed and Upsert to Pinecone."""
    try:
        records = ingest_document(req.file_path)
        upserted = upsert_chunks(records)

        # Invalidate cache — new documents may change answers
        if CACHE_ENABLED:
            cache = get_cache_backend()
            cache.bump_doc_version()
            logger.info(f"Doc version bumped after ingesting: {req.file_path}")

        return IngestResponse(
            file=req.file_path,
            chunks=upserted,
            message="Document Ingested Successfully",
        )

    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File Not Found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat", response_model=ChatResponse)
def chat_endpoint(req: ChatRequest):
    """Full RAG Pipeline with 3-Tier Cache:
    Tier 1 (exact) → Tier 2 (semantic) → Tier 3 (retrieval) → Full Pipeline
    """
    try:
        start_time = time.time()
        cache = get_cache_backend() if CACHE_ENABLED else None

        # ── TIER 1: Exact Match Cache ──────────────────────────
        if cache:
            normalized = normalize_query(req.question)
            query_hash = hash_query(normalized)
            exact_hit = cache.get_exact(query_hash)

            if exact_hit:
                logger.info(f"Cache HIT (exact): {req.question[:50]}...")
                return ChatResponse(
                    answer=exact_hit["answer"],
                    sources=_json_to_sources(exact_hit["sources_json"]),
                    cache_hit=True,
                    cache_tier="exact",
                    response_time_ms=round((time.time() - start_time) * 1000, 2),
                )

        # ── TIER 2: Semantic Match Cache ───────────────────────
        embedding = None
        if cache:
            embedding = embed_query(req.question)
            semantic_hit = cache.get_semantic(embedding, SEMANTIC_CACHE_THRESHOLD)

            if semantic_hit:
                logger.info(
                    f"Cache HIT (semantic, sim={semantic_hit['similarity']:.3f}): "
                    f"{req.question[:50]}..."
                )
                return ChatResponse(
                    answer=semantic_hit["answer"],
                    sources=_json_to_sources(semantic_hit["sources_json"]),
                    cache_hit=True,
                    cache_tier="semantic",
                    response_time_ms=round((time.time() - start_time) * 1000, 2),
                )

        # ── TIER 3: Retrieval Cache ────────────────────────────
        if cache and embedding:
            retrieval_hit = cache.get_retrieval(embedding, RETRIEVAL_CACHE_THRESHOLD)

            if retrieval_hit:
                logger.info(
                    f"Cache HIT (retrieval, sim={retrieval_hit['similarity']:.3f}): "
                    f"{req.question[:50]}..."
                )
                # We have cached chunks — skip Pinecone, still call LLM
                cached_chunks = json.loads(retrieval_hit["chunks_json"])
                answer = generate_answer(req.question, cached_chunks)
                sources = [_to_source(c, i) for i, c in enumerate(cached_chunks, 1)]

                # Promote to Tier 1 + 2 (we now have a full answer)
                doc_version = cache.get_doc_version()
                sources_json = _sources_to_json(sources)
                cache.set_exact(query_hash, req.question, answer, sources_json, doc_version, EXACT_CACHE_TTL)
                cache.set_semantic(req.question, embedding, answer, sources_json, doc_version, SEMANTIC_CACHE_TTL)

                return ChatResponse(
                    answer=answer,
                    sources=sources,
                    cache_hit=True,
                    cache_tier="retrieval",
                    response_time_ms=round((time.time() - start_time) * 1000, 2),
                )

        # ── FULL RAG PIPELINE (all cache miss) ─────────────────
        logger.info(f"Cache MISS: {req.question[:50]}...")

        # Step 1: Retrieve
        retrieved_chunks = search(req.question)

        # Step 2: Rerank if enabled
        if req.use_reranker:
            reranked_chunks = rerank(req.question)
            chunks = reranked_chunks
        else:
            chunks = retrieved_chunks

        if not chunks:
            return ChatResponse(
                answer="I could not find any relevant information in the documents",
                sources=[],
                response_time_ms=round((time.time() - start_time) * 1000, 2),
            )

        # Step 3: Generate answer
        answer = generate_answer(req.question, chunks)
        sources = [_to_source(c, i) for i, c in enumerate(chunks, 1)]

        # Step 4: Store in ALL 3 cache tiers
        if cache:
            doc_version = cache.get_doc_version()
            sources_json = _sources_to_json(sources)
            if embedding is None:
                embedding = embed_query(req.question)
            if not hasattr(chat_endpoint, '_query_hash'):
                normalized = normalize_query(req.question)
                query_hash = hash_query(normalized)

            # Tier 1: exact
            cache.set_exact(query_hash, req.question, answer, sources_json, doc_version, EXACT_CACHE_TTL)
            # Tier 2: semantic
            cache.set_semantic(req.question, embedding, answer, sources_json, doc_version, SEMANTIC_CACHE_TTL)
            # Tier 3: retrieval (store raw chunks for future LLM re-generation)
            cache.set_retrieval(req.question, embedding, json.dumps(chunks), doc_version, RETRIEVAL_CACHE_TTL)

        # Debug info
        debug_retrieved = None
        debug_reranked = None
        if req.debug:
            debug_retrieved = [_to_source(c, i) for i, c in enumerate(retrieved_chunks, 1)]
            if req.use_reranker:
                debug_reranked = [_to_source(c, i) for i, c in enumerate(reranked_chunks, 1)]

        return ChatResponse(
            answer=answer,
            sources=sources,
            retrieved=debug_retrieved,
            reranked=debug_reranked,
            cache_hit=False,
            cache_tier=None,
            response_time_ms=round((time.time() - start_time) * 1000, 2),
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/upload", response_model=UploadResponse)
async def upload_endpoint(file: UploadFile = File(...)):
    """Upload a file from browser, save it, then ingest into the RAG pipeline."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    allowed_ext = (".pdf", ".txt", ".md")
    if not file.filename.lower().endswith(allowed_ext):
        raise HTTPException(status_code=400, detail=f"Unsupported file type. Allowed: {allowed_ext}")

    try:
        # Read file content for hash deduplication
        file_content = await file.read()
        file_hash = hashlib.sha256(file_content).hexdigest()

        # Check for duplicate content
        cache = get_cache_backend() if CACHE_ENABLED else None
        if cache:
            existing = cache.get_document_hash(file_hash)
            if existing:
                raise HTTPException(
                    status_code=409,
                    detail=f"Duplicate: this file was already uploaded as '{existing['file_name']}'",
                )

        # Save file to disk
        save_path = os.path.join(UPLOAD_DIR, file.filename)
        with open(save_path, "wb") as f:
            f.write(file_content)

        records = ingest_document(save_path)
        upserted = upsert_chunks(records)

        # Store document hash
        if cache and upserted > 0:
            cache.set_document_hash(file_hash, {
                "file_name": file.filename,
                "file_size": len(file_content),
                "chunk_count": upserted,
            })

        # Invalidate cache — new documents may change answers
        if cache:
            cache.bump_doc_version()
            logger.info(f"Doc version bumped after upload: {file.filename}")

        return UploadResponse(
            file=file.filename,
            chunks=upserted,
            message="Document uploaded and ingested successfully",
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/documents")
def list_documents():
    """List all uploaded documents with metadata."""
    docs = []
    for f in os.listdir(UPLOAD_DIR):
        path = os.path.join(UPLOAD_DIR, f)
        if os.path.isfile(path):
            stat = os.stat(path)
            docs.append({
                "name": f,
                "size": stat.st_size,
                "uploaded_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            })
    docs.sort(key=lambda d: d["uploaded_at"], reverse=True)
    return {"documents": docs}


@app.get("/documents/{filename}")
def serve_document(filename: str):
    """Serve an uploaded document file for preview."""
    path = os.path.join(UPLOAD_DIR, filename)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path, filename=filename)


# ── Cache Management Endpoints ─────────────────────────────────

@app.post("/cache/clear")
def cache_clear():
    """Clear all 3 cache tiers. Returns count of entries removed per tier."""
    if not CACHE_ENABLED:
        return {"message": "Cache is disabled", "cleared": {}}

    cache = get_cache_backend()
    cleared = cache.clear_all()
    logger.info(f"Cache cleared: {cleared}")
    return {
        "message": "Cache cleared successfully",
        "cleared": cleared,
    }


@app.get("/cache/stats")
def cache_stats():
    """Get cache statistics — per-tier entry counts, hit counts, backend info."""
    if not CACHE_ENABLED:
        return {"message": "Cache is disabled", "stats": {}}

    cache = get_cache_backend()
    return cache.get_stats()


# ── Vector Store Management ───────────────────────────────────

@app.delete("/vectors")
def reset_vectors():
    """Delete all vectors from Pinecone namespace, clear cache, and remove uploaded files."""
    try:
        # 1. Delete all vectors from Pinecone
        delete_all_vectors()
        logger.info("All vectors deleted from Pinecone namespace")

        # 2. Clear all cache tiers
        cache_cleared = {}
        doc_hashes_cleared = 0
        if CACHE_ENABLED:
            cache = get_cache_backend()
            cache_cleared = cache.clear_all()
            doc_hashes_cleared = cache.clear_document_hashes()
            logger.info(f"Cache cleared: {cache_cleared}, doc hashes: {doc_hashes_cleared}")

        # 3. Remove uploaded files
        files_removed = 0
        for f in os.listdir(UPLOAD_DIR):
            path = os.path.join(UPLOAD_DIR, f)
            if os.path.isfile(path):
                os.remove(path)
                files_removed += 1

        return {
            "message": "Vector store reset successfully",
            "vectors_deleted": True,
            "cache_cleared": cache_cleared,
            "doc_hashes_cleared": doc_hashes_cleared,
            "files_removed": files_removed,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
