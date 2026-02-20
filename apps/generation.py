from typing import List, Dict
from langchain_openai import ChatOpenAI

from .config import OPENAI_API_KEY, OPENAI_MODEL, MAX_TOKENS, TEMPERATURE
from .reranker import rerank as rerank_search


_llm = ChatOpenAI(
    model=OPENAI_MODEL,
    api_key=OPENAI_API_KEY,
    max_tokens=MAX_TOKENS,
    temperature=TEMPERATURE
)

SYSTEM_PROMPT = """You are a helpful assistant that answers questions based on the provided context.
Use ONLY the context below to answer. If the answer is not in the context, say "I don't have enough information to answer that."

CITATION RULES:
- Each context chunk is labeled [1], [2], etc. with its source document and page number(s).
- When you use information from a chunk, cite it inline like [1], [2], etc.
- At the end of your answer, add a "References" section listing each cited source with page numbers.
- Format: [n] source_filename, p.X

Example:
Apple's Q4 revenue was $94.9 billion [1], with Services reaching a record $25 billion [2].

References:
[1] Apple_Q24.pdf, p.3
[2] Apple_Q24.pdf, p.5"""



def build_context_block(chunks: List[Dict]) -> str:
    parts = []

    for i, c in enumerate(chunks, 1):
        source = c.get("source", "unknown")
        pages = c.get("pages", "")
        text = c.get("chunk_text", "")
        page_label = f", p.{pages}" if pages else ""
        parts.append(f"[{i}] (source: {source}{page_label})\n {text}")

    return "\n\n".join(parts)


def generate_answer(query: str, chunks: List[Dict]) -> str:
    query = query.strip()
    if not query:
        return "Question is empty."
    if not chunks:
        return "I don't have enough information to answer that."
    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY is missing.")

    context = build_context_block(chunks)

    messages = [
        ("system", SYSTEM_PROMPT),
        ("human", f"Context:\n{context}\n\n--\nQuestion: {query}"),
    ]

    ai_msg = _llm.invoke(messages)

    return ai_msg.content


if __name__ == "__main__":
    query = "What growth did Google and Apple show in last 3 months?"
    try:
        chunks = rerank_search(query)
        print(f"reranked_chunks={len(chunks)}")
        answer = generate_answer(query, chunks)
        print("\nGenerated Answer:\n")
        print(answer)
    except Exception as e:
        print(f"Generation test failed: {e}")
