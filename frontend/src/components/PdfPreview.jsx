import { getDocumentUrl } from "../api";

export default function PdfPreview({ filename, onClose }) {
  if (!filename) return null;

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
      <iframe
        className="pdf-preview-frame"
        src={getDocumentUrl(filename)}
        title={`Preview: ${filename}`}
      />
    </aside>
  );
}
