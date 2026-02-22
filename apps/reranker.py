from typing import List, Dict

from pinecone import Pinecone
from .retrieval import search as retrieve_search

from .config import (
    PINECONE_API_KEY,
    PINECONE_INDEX_NAME,
    PINECONE_NAMESPACE,
    PINECONE_RERANK_MODEL,
    RERANK_TOP_N,
    TOP_K
)


_pc = Pinecone(api_key=PINECONE_API_KEY)

def rerank(query: str, top_k: int = TOP_K, top_n: int = RERANK_TOP_N, source_filter: str = None) -> List[Dict]:
    query = query.strip()
    if not query:
        return []
    if top_k <= 0:
        return []
    if top_n <= 0:
        return []

    top_n = min(top_n, top_k)

    if not _pc.has_index(PINECONE_INDEX_NAME):
        raise ValueError(f"Pinecone index '{PINECONE_INDEX_NAME}' does not exist.")

    index = _pc.Index(PINECONE_INDEX_NAME)

    query_params = {
        "top_k": top_k,
        "inputs": {"text": query},
    }
    if source_filter:
        query_params["filter"] = {"source": {"$eq": source_filter}}

    reranked = index.search(
        namespace=PINECONE_NAMESPACE,
        query=query_params,
        rerank={
            "model": PINECONE_RERANK_MODEL,
            "top_n": top_n,
            "rank_fields":["chunk_text"],
        },
        fields=["chunk_text", "source", "pages"]
    )

    hits = []

    for item in reranked.get("result", {}).get("hits", []):
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
    query = "growth in last 3 months"
    top_k = TOP_K
    top_n = RERANK_TOP_N

    try:
        top_k_hits = retrieve_search(query, top_k)
        reranked_hits = rerank(query, top_k, top_n)

        print(f"Query: {query}")
        print(f"\nTop-{top_k} Retrieval Results ({len(top_k_hits)} hits):")
        for i, hit in enumerate(top_k_hits, start=1):
            print(f"{i}. score={hit['score']} | source={hit['source']} | pages={hit['pages']}")

        print(f"\nReranked Top-{top_n} Results ({len(reranked_hits)} hits):")
        for i, hit in enumerate(reranked_hits, start=1):
            print(f"{i}. score={hit['score']} | source={hit['source']} | pages={hit['pages']}")
    except Exception as e:
        print(f"Reranker test failed: {e}")
