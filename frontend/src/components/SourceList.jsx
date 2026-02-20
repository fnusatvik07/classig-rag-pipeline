import { useState } from "react";

export default function SourceList({ sources }) {
  const [expanded, setExpanded] = useState(false);

  if (!sources || sources.length === 0) return null;

  return (
    <div className="source-list">
      <button className="source-toggle" onClick={() => setExpanded(!expanded)}>
        <span className="source-icon">📄</span>
        {sources.length} source{sources.length > 1 ? "s" : ""}
        <span className={`arrow ${expanded ? "open" : ""}`}>▸</span>
      </button>

      {expanded && (
        <div className="source-items">
          {sources.map((src, i) => (
            <div key={i} className="source-item">
              <div className="source-header">
                <span className="citation">{src.citation}</span>
                <span className="source-file">{src.source}</span>
                {src.pages && <span className="source-pages">p. {src.pages}</span>}
                <span className="source-score">{(src.score * 100).toFixed(0)}%</span>
              </div>
              <p className="source-text">{src.chunk_text}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
