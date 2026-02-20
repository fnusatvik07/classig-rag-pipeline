export default function Dashboard({ documents, onPreview }) {
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
      <div className="dashboard-header">
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
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
