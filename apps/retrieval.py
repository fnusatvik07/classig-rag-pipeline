from typing import List, Dict

from pinecone import Pinecone

from .config import (
    PINECONE_API_KEY,
    PINECONE_INDEX_NAME,
    PINECONE_NAMESPACE,
)


DEFAULT_TOP_K = 5
_pc = Pinecone(api_key=PINECONE_API_KEY)

def search(query: str, top_k: int = DEFAULT_TOP_K, source_filter: str = None) -> List[Dict]:
    query = query.strip()
    if not query:
        return []

    if not _pc.has_index(PINECONE_INDEX_NAME):
        raise ValueError(f"Pinecone index '{PINECONE_INDEX_NAME}' does not exist.")

    index = _pc.Index(PINECONE_INDEX_NAME)

    query_params = {
        "top_k": top_k,
        "inputs": {"text": query},
    }
    if source_filter:
        query_params["filter"] = {"source": {"$eq": source_filter}}

    results = index.search(
        namespace=PINECONE_NAMESPACE,
        query=query_params,
        fields=["chunk_text", "source", "pages"]
    )

    hits = []

    for item in results.get("result", {}).get("hits", []):
        fields = item.get("fields", {})
        hits.append(
            {
                "id": item.get("_id", ""),
                "score": item.get("_score", 0.0),
                "chunk_text": fields.get("chunk_text", ""),
                "source": fields.get("source", ""),
                "pages": fields.get("pages", ""),

            }
        )

    return hits


if __name__ == "__main__":
    try:
        hits = search("growth in last 3 months", 3)
        print(f"hits={len(hits)}")
        if hits:
            print(hits)
    except Exception as e:
        print(f"Retrieval test failed: {e}")
