import { useRef, useState } from "react";

export default function FileUpload({ onUpload }) {
  const inputRef = useRef(null);
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);

  const handleFile = async (file) => {
    if (!file) return;
    setUploading(true);
    try {
      await onUpload(file);
    } finally {
      setUploading(false);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    handleFile(file);
  };

  return (
    <div
      className={`file-upload ${dragOver ? "drag-over" : ""}`}
      onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
      onDragLeave={() => setDragOver(false)}
      onDrop={handleDrop}
      onClick={() => !uploading && inputRef.current?.click()}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".pdf,.txt,.md"
        hidden
        onChange={(e) => handleFile(e.target.files[0])}
      />
      {uploading ? (
        <span className="upload-status">Uploading...</span>
      ) : (
        <>
          <span className="upload-icon">⬆</span>
          <span>Upload PDF, TXT, or MD</span>
        </>
      )}
    </div>
  );
}
