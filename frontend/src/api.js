// API helper functions for MyChat RAG chatbot

const BASE_URL = "";

export async function sendChat(question, useReranker = true) {
  const res = await fetch(`${BASE_URL}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      question,
      use_reranker: useReranker,
      debug: true,
    }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Request failed (${res.status})`);
  }

  return res.json();
}

export async function uploadDocument(file) {
  const form = new FormData();
  form.append("file", file);

  const res = await fetch(`${BASE_URL}/upload`, {
    method: "POST",
    body: form,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Upload failed (${res.status})`);
  }

  return res.json();
}

export async function fetchDocuments() {
  const res = await fetch(`${BASE_URL}/documents`);

  if (!res.ok) {
    throw new Error("Failed to fetch documents");
  }

  return res.json();
}

export async function fetchCacheStats() {
  const res = await fetch(`${BASE_URL}/cache/stats`);

  if (!res.ok) {
    throw new Error("Failed to fetch cache stats");
  }

  return res.json();
}

export async function deleteDocument(filename) {
  const res = await fetch(
    `${BASE_URL}/documents/${encodeURIComponent(filename)}`,
    { method: "DELETE" }
  );

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Delete failed (${res.status})`);
  }

  return res.json();
}

export async function resetVectorStore() {
  const res = await fetch(`${BASE_URL}/vectors`, { method: "DELETE" });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Reset failed (${res.status})`);
  }

  return res.json();
}

// Get the URL for previewing a document
export function getDocumentUrl(filename) {
  return `${BASE_URL}/documents/${encodeURIComponent(filename)}`;
}

// Export chat messages as markdown text
export function exportChatAsMarkdown(messages) {
  let md = "# MyChat — Conversation Export\n\n";
  for (const msg of messages) {
    if (msg.role === "user") {
      md += `**You:** ${msg.content}\n\n`;
    } else {
      md += `**AI:** ${msg.content}\n\n`;
      if (msg.sources?.length) {
        md += "**Sources:**\n";
        for (const s of msg.sources) {
          md += `- ${s.citation} ${s.source} (p. ${s.pages}) — ${s.chunk_text}\n`;
        }
        md += "\n";
      }
    }
  }
  return md;
}
