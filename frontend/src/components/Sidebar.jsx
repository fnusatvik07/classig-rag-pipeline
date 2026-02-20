import FileUpload from "./FileUpload";

export default function Sidebar({
  documents,
  selectedDoc,
  onSelectDoc,
  showSources,
  onToggleSources,
  onClearChat,
  onUpload,
  view,
  onSetView,
  onPreviewDoc,
  darkMode,
  onToggleDark,
  messageCount,
  onExport,
}) {
  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <h1>MyChat</h1>
      </div>

      {/* Navigation */}
      <div className="sidebar-nav">
        <button
          className={`nav-btn ${view === "chat" ? "active" : ""}`}
          onClick={() => onSetView("chat")}
        >
          💬 Chat
        </button>
        <button
          className={`nav-btn ${view === "dashboard" ? "active" : ""}`}
          onClick={() => onSetView("dashboard")}
        >
          📂 Documents
        </button>
      </div>

      <div className="sidebar-section">
        <FileUpload onUpload={onUpload} />
      </div>

      <div className="sidebar-section sidebar-docs">
        <h3>Documents</h3>
        {documents.length === 0 ? (
          <p className="sidebar-hint">No documents uploaded yet.</p>
        ) : (
          <ul className="doc-list">
            {documents.map((doc) => {
              const name = typeof doc === "string" ? doc : doc.name;
              return (
                <li
                  key={name}
                  className={`doc-item ${selectedDoc === name ? "active" : ""}`}
                  onClick={() => onSelectDoc(name)}
                >
                  <span className="doc-icon">📄</span>
                  <span className="doc-name">{name}</span>
                  <button
                    className="doc-preview-btn"
                    onClick={(e) => {
                      e.stopPropagation();
                      onPreviewDoc(name);
                    }}
                    title="Preview PDF"
                  >
                    👁
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      {/* Session info */}
      {messageCount > 0 && (
        <div className="session-info">
          {messageCount} message{messageCount !== 1 ? "s" : ""} in session
        </div>
      )}

      <div className="sidebar-controls">
        <label className="toggle-row">
          <input
            type="checkbox"
            checked={showSources}
            onChange={onToggleSources}
          />
          <span>Show Sources</span>
        </label>
        <label className="toggle-row">
          <input
            type="checkbox"
            checked={darkMode}
            onChange={onToggleDark}
          />
          <span>Dark Mode</span>
        </label>
        <button className="btn-secondary" onClick={onExport}>
          Export Chat
        </button>
        <button className="btn-clear" onClick={onClearChat}>
          Clear Chat
        </button>
      </div>
    </aside>
  );
}
