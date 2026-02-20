from pathlib import Path
from typing import Dict, List

from config import RERANK_TOP_N, TOP_K
from embedding import is_file_ingested, upsert_chunks
from generation import generate_answer
from ingestion import ingest_document
from retrieval import search as retrieve_search
from reranker import search as rerank_search


def _ids(hits: List[Dict]) -> List[str]:
    return [h.get("id", "") for h in hits]


def _print_hits(title: str, hits: List[Dict]) -> None:
    print(f"\n{title} ({len(hits)} hits)")
    for i, hit in enumerate(hits, start=1):
        print(
            f"{i}. id={hit.get('id', '')} | score={hit.get('score', 0.0)} "
            f"| source={hit.get('source', '')} | pages={hit.get('pages', '')}"
        )
        text = hit.get("chunk_text", "").strip().replace("\n", " ")
        if text:
            print(f"   text: {text[:260]}")


def _ingest_docs(doc_paths: List[Path]) -> None:
    print("=== Ingestion Step ===")
    for doc_path in doc_paths:
        print(f"\nDocument: {doc_path.name}")
        try:
            records = ingest_document(str(doc_path))
            upserted = upsert_chunks(records)
            uploaded = is_file_ingested(doc_path.name)
            print(f"records={len(records)} | upserted={upserted} | uploaded={uploaded}")
        except Exception as e:
            print(f"ingestion failed for {doc_path.name}: {e}")


def _compare_ranking(query: str, top_k: int, top_n: int) -> None:
    print("\n" + "=" * 80)
    print("User Question")
    print(query)
    try:
        base_hits = retrieve_search(query, top_k=top_k)
        reranked_hits = rerank_search(query, top_k=top_k, top_n=top_n)
    except Exception as e:
        print(f"query test failed: {e}")
        return

    _print_hits("Retrieved Chunks", base_hits)
    _print_hits("Reranked Chunks", reranked_hits)

    base_order = _ids(base_hits)[:top_n]
    rerank_order = _ids(reranked_hits)
    changed = base_order != rerank_order
    print(f"\nReranker Changed Order: {changed}")
    if changed:
        print(f"Before: {base_order}")
        print(f"After : {rerank_order}")

    print("\nFinal Answer (with citation)")
    try:
        answer = generate_answer(query, reranked_hits)
        print(answer)
    except Exception as e:
        print(f"generation failed: {e}")


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    docs = [
        root / "docs" / "Nike_Sales.pdf",
    ]
    queries = [
        "What were NIKE, Inc. revenues in fiscal 2025 compared to fiscal 2024?",
        "How did Nike's sales perform across regions?",
        "What happened to NIKE Direct revenues in fiscal 2025?",
    ]

    _ingest_docs(docs)
    print("\n=== Retrieval vs Reranker Tests ===")
    for q in queries:
        _compare_ranking(q, top_k=TOP_K, top_n=RERANK_TOP_N)
