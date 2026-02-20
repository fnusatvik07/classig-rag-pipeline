import { useState } from "react";

export default function ChunkComparison({ retrieved, reranked, sources }) {
  const [tab, setTab] = useState("sources");
  const [expanded, setExpanded] = useState(false);

  const hasRetrieved = retrieved && retrieved.length > 0;
  const hasReranked = reranked && reranked.length > 0;
  const hasSources = sources && sources.length > 0;

  if (!hasSources && !hasRetrieved && !hasReranked) return null;

  const tabs = [];
  if (hasSources) tabs.push({ key: "sources", label: `Sources (${sources.length})` });
  if (hasRetrieved) tabs.push({ key: "retrieved", label: `Retrieved (${retrieved.length})` });
  if (hasReranked) tabs.push({ key: "reranked", label: `Reranked (${reranked.length})` });

  const activeChunks =
    tab === "sources" ? sources :
    tab === "retrieved" ? retrieved :
    reranked;

  return (
    <div className="chunk-comparison">
      <button className="chunk-toggle" onClick={() => setExpanded(!expanded)}>
        <span className="source-icon">📄</span>
        View chunks & sources
        <span className={`arrow ${expanded ? "open" : ""}`}>▸</span>
      </button>

      {expanded && (
        <div className="chunk-panel">
          <div className="chunk-tabs">
            {tabs.map((t) => (
              <button
                key={t.key}
                className={`chunk-tab ${tab === t.key ? "active" : ""}`}
                onClick={() => setTab(t.key)}
              >
                {t.label}
              </button>
            ))}
          </div>

          <div className="chunk-list">
            {activeChunks?.map((chunk, i) => (
              <div key={i} className="chunk-item">
                <div className="chunk-header">
                  <span className="citation">{chunk.citation}</span>
                  <span className="source-file">{chunk.source}</span>
                  {chunk.pages && <span className="source-pages">p. {chunk.pages}</span>}
                  <span className="source-score">
                    {(chunk.score * 100).toFixed(1)}%
                  </span>
                </div>
                <p className="source-text">{chunk.chunk_text}</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
