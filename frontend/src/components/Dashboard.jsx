export default function Dashboard({ documents, onPreview, onDelete, cacheStats }) {
  const formatSize = (bytes) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const formatDate = (iso) => {
    const d = new Date(iso);
    return d.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  return (
    <div className="dashboard">
      {/* Stats Cards */}
      {cacheStats && (
        <>
          <div className="dashboard-section-header">
            <h2>System Overview</h2>
          </div>
          <div className="stats-grid">
            <div className="stats-card">
              <div className="stats-card-header">System</div>
              <div className="stats-card-body">
                <div className="stats-row">
                  <span className="stats-label">Backend</span>
                  <span className="stats-value">{cacheStats.backend}</span>
                </div>
                <div className="stats-row">
                  <span className="stats-label">Doc Version</span>
                  <span className="stats-value">{cacheStats.doc_version}</span>
                </div>
                <div className="stats-row">
                  <span className="stats-label">Documents</span>
                  <span className="stats-value">{documents.length}</span>
                </div>
              </div>
            </div>

            <div className="stats-card">
              <div className="stats-card-header">Exact Cache</div>
              <div className="stats-card-body">
                <div className="stats-row">
                  <span className="stats-label">Entries</span>
                  <span className="stats-value">{cacheStats.exact?.entries ?? 0}</span>
                </div>
                <div className="stats-row">
                  <span className="stats-label">Total Hits</span>
                  <span className="stats-value">{cacheStats.exact?.total_hits ?? 0}</span>
                </div>
              </div>
            </div>

            <div className="stats-card">
              <div className="stats-card-header">Semantic Cache</div>
              <div className="stats-card-body">
                <div className="stats-row">
                  <span className="stats-label">Entries</span>
                  <span className="stats-value">{cacheStats.semantic?.entries ?? 0}</span>
                </div>
                <div className="stats-row">
                  <span className="stats-label">Total Hits</span>
                  <span className="stats-value">{cacheStats.semantic?.total_hits ?? 0}</span>
                </div>
              </div>
            </div>

            <div className="stats-card">
              <div className="stats-card-header">Retrieval Cache</div>
              <div className="stats-card-body">
                <div className="stats-row">
                  <span className="stats-label">Entries</span>
                  <span className="stats-value">{cacheStats.retrieval?.entries ?? 0}</span>
                </div>
                <div className="stats-row">
                  <span className="stats-label">Total Hits</span>
                  <span className="stats-value">{cacheStats.retrieval?.total_hits ?? 0}</span>
                </div>
              </div>
            </div>
          </div>
        </>
      )}

      {/* Document Library */}
      <div className="dashboard-section-header" style={{ marginTop: cacheStats ? 32 : 0 }}>
        <h2>Document Library</h2>
        <span className="dashboard-count">
          {documents.length} document{documents.length !== 1 ? "s" : ""}
        </span>
      </div>

      {documents.length === 0 ? (
        <div className="dashboard-empty">
          <span className="dashboard-empty-icon">📂</span>
          <p>No documents uploaded yet.</p>
          <p className="dashboard-empty-hint">
            Upload PDFs, TXT, or MD files from the sidebar to get started.
          </p>
        </div>
      ) : (
        <div className="dashboard-grid">
          {documents.map((doc) => (
            <div key={doc.name} className="dashboard-card">
              <div className="dashboard-card-icon">📄</div>
              <div className="dashboard-card-info">
                <span className="dashboard-card-name" title={doc.name}>
                  {doc.name}
                </span>
                <span className="dashboard-card-meta">
                  {formatSize(doc.size)} &middot; {formatDate(doc.uploaded_at)}
                </span>
              </div>
              <button
                className="dashboard-card-action"
                onClick={() => onPreview(doc.name)}
                title="Preview document"
              >
                👁
              </button>
              <button
                className="dashboard-card-delete"
                onClick={() => onDelete(doc.name)}
                title="Delete document"
              >
                🗑
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
