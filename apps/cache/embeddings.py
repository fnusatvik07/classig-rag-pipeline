"""
Embedding utilities for the cache system.

- embed_query()        — generate embedding vector via OpenAI
- normalize_query()    — clean/normalize query text for exact matching
- hash_query()         — SHA256 hash of normalized text
- cosine_similarity()  — compare two embedding vectors
"""

import hashlib
import re

import numpy as np
from langchain_openai import OpenAIEmbeddings

from apps.config import OPENAI_API_KEY, OPENAI_EMBED_MODEL


# Lazy-initialized embeddings client (created on first call)
_embeddings_client: OpenAIEmbeddings | None = None


def _get_embeddings_client() -> OpenAIEmbeddings:
    """Get or create the OpenAI embeddings client (singleton)."""
    global _embeddings_client
    if _embeddings_client is None:
        _embeddings_client = OpenAIEmbeddings(
            model=OPENAI_EMBED_MODEL,
            api_key=OPENAI_API_KEY,
        )
    return _embeddings_client


def embed_query(text: str) -> list[float]:
    """Generate an embedding vector for a query string.

    Uses OpenAI text-embedding-3-small (1536 dimensions).
    Cost: ~$0.00002 per query — negligible.
    """
    client = _get_embeddings_client()
    return client.embed_query(text)


def normalize_query(text: str) -> str:
    """Normalize a query for exact-match caching.

    Steps:
    1. Lowercase
    2. Strip leading/trailing whitespace
    3. Collapse multiple spaces into one
    4. Remove trailing punctuation (?, !, .)

    Example: "  What was  Apple's Revenue?? " → "what was apple's revenue"
    """
    text = text.lower().strip()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[?.!]+$", "", text).strip()
    return text


def hash_query(normalized_text: str) -> str:
    """SHA256 hash of a normalized query string.

    Used as the key for Tier 1 (exact cache) lookups.
    Deterministic: same input always produces same hash.
    """
    return hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Compute cosine similarity between two vectors.

    Returns a float in [-1, 1] where:
    - 1.0  = identical direction (same meaning)
    - 0.0  = orthogonal (unrelated)
    - -1.0 = opposite direction

    Uses numpy for fast computation.
    """
    a = np.array(vec_a, dtype=np.float32)
    b = np.array(vec_b, dtype=np.float32)

    dot_product = np.dot(a, b)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return float(dot_product / (norm_a * norm_b))


def embedding_to_bytes(embedding: list[float]) -> bytes:
    """Serialize embedding list to bytes for storage (SQLite BLOB / Redis)."""
    return np.array(embedding, dtype=np.float32).tobytes()


def bytes_to_embedding(data: bytes) -> list[float]:
    """Deserialize bytes back to embedding list."""
    return np.frombuffer(data, dtype=np.float32).tolist()
