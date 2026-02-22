import { useState } from "react";
import { getDocumentUrl } from "../api";

export default function PdfPreview({ filename, onClose, sources = [] }) {
  const [activePage, setActivePage] = useState(null);

  if (!filename) return null;

  const isPdf = filename.toLowerCase().endsWith(".pdf");
  const baseUrl = getDocumentUrl(filename);

  const getPageFragment = () => {
    if (!isPdf) return "";
    if (activePage) return `#page=${activePage}`;
    return "#toolbar=1";
  };

  const handleSourceClick = (chunk) => {
    const firstPage = parseInt(chunk.pages.split(",")[0], 10);
    if (!isNaN(firstPage)) {
      setActivePage(firstPage);
    }
  };

  return (
    <aside className="pdf-preview">
      <div className="pdf-preview-header">
        <span className="pdf-preview-title" title={filename}>
          {filename}
        </span>
        <button className="pdf-preview-close" onClick={onClose}>
          ✕
        </button>
      </div>

      {sources.length > 0 && (
        <div className="pdf-sources">
          <div className="pdf-sources-header">
            Sources ({sources.length})
          </div>
          <div className="pdf-sources-list">
            {sources.map((chunk, i) => {
              const firstPage = parseInt(chunk.pages.split(",")[0], 10);
              const isActive = activePage === firstPage;
              return (
                <button
                  key={i}
                  className={`pdf-source-card ${isActive ? "active" : ""}`}
                  onClick={() => handleSourceClick(chunk)}
                >
                  <div className="pdf-source-meta">
                    <span className="pdf-source-citation">{chunk.citation}</span>
                    <span className="pdf-source-page">p. {chunk.pages}</span>
                    <span className="pdf-source-score">
                      {(chunk.score * 100).toFixed(1)}%
                    </span>
                  </div>
                  <p className="pdf-source-text">{chunk.chunk_text}</p>
                </button>
              );
            })}
          </div>
        </div>
      )}

      <iframe
        className="pdf-preview-frame"
        src={`${baseUrl}${getPageFragment()}`}
        title={`Preview: ${filename}`}
      />
    </aside>
  );
}
