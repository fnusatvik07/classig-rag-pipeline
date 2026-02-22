import { useState, useRef, useCallback, useEffect } from "react";
import { getDocumentUrl } from "../api";

export default function PdfPreview({ filename, onClose, sources = [], width, onWidthChange }) {
  const [activePage, setActivePage] = useState(null);
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const dragRef = useRef(null);

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

  // Drag handle for resizing
  const handleMouseDown = useCallback((e) => {
    e.preventDefault();
    const startX = e.clientX;
    const startWidth = width;
    setIsDragging(true);

    const handleMouseMove = (e) => {
      const delta = startX - e.clientX;
      const newWidth = Math.max(300, Math.min(900, startWidth + delta));
      onWidthChange(newWidth);
    };

    const handleMouseUp = () => {
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
      setIsDragging(false);
    };

    document.addEventListener("mousemove", handleMouseMove);
    document.addEventListener("mouseup", handleMouseUp);
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  }, [width, onWidthChange]);

  return (
    <aside className="pdf-preview" style={{ width, minWidth: width }}>
      <div
        className="pdf-resize-handle"
        onMouseDown={handleMouseDown}
        ref={dragRef}
      />
      <div className="pdf-preview-header">
        <span className="pdf-preview-title" title={filename}>
          {filename}
        </span>
        <button className="pdf-preview-close" onClick={onClose}>
          ✕
        </button>
      </div>

      {sources.length > 0 && (
        <div className={`pdf-sources ${sourcesOpen ? "open" : ""}`}>
          <button
            className="pdf-sources-header"
            onClick={() => setSourcesOpen((o) => !o)}
          >
            <span className="pdf-sources-arrow">{sourcesOpen ? "▾" : "▸"}</span>
            Sources ({sources.length})
          </button>
          {sourcesOpen && (
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
          )}
        </div>
      )}

      <iframe
        key={activePage || "default"}
        className="pdf-preview-frame"
        style={isDragging ? { pointerEvents: "none" } : undefined}
        src={`${baseUrl}${getPageFragment()}`}
        title={`Preview: ${filename}`}
      />
    </aside>
  );
}
