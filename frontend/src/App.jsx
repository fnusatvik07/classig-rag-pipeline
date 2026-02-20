import { useState, useEffect } from "react";
import Sidebar from "./components/Sidebar";
import ChatArea from "./components/ChatArea";
import Dashboard from "./components/Dashboard";
import PdfPreview from "./components/PdfPreview";
import { sendChat, uploadDocument, fetchDocuments, exportChatAsMarkdown } from "./api";
import "./App.css";

export default function App() {
  const [messages, setMessages] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [showSources, setShowSources] = useState(true);
  const [documents, setDocuments] = useState([]);
  const [selectedDoc, setSelectedDoc] = useState(null);
  const [status, setStatus] = useState("Idle");
  const [view, setView] = useState("chat");
  const [previewDoc, setPreviewDoc] = useState(null);
  const [darkMode, setDarkMode] = useState(false);

  // Apply dark mode to root element
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", darkMode ? "dark" : "light");
  }, [darkMode]);

  // Fetch documents on mount
  useEffect(() => {
    fetchDocuments()
      .then((data) => setDocuments(data.documents))
      .catch(() => {});
  }, []);

  const handleSend = async (question) => {
    setMessages((prev) => [...prev, { role: "user", content: question }]);
    setIsLoading(true);
    setStatus("Thinking");

    try {
      const data = await sendChat(question);
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: data.answer,
          sources: data.sources,
          retrieved: data.retrieved,
          reranked: data.reranked,
        },
      ]);
      setStatus("Idle");
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: `**Error:** ${err.message}` },
      ]);
      setStatus("Error");
      setTimeout(() => setStatus("Idle"), 3000);
    } finally {
      setIsLoading(false);
    }
  };

  const handleUpload = async (file) => {
    try {
      setStatus("Uploading");
      await uploadDocument(file);
      const data = await fetchDocuments();
      setDocuments(data.documents);
      setStatus("Idle");
    } catch (err) {
      alert(`Upload failed: ${err.message}`);
      setStatus("Error");
      setTimeout(() => setStatus("Idle"), 3000);
    }
  };

  const handleClearChat = () => {
    setMessages([]);
    setStatus("Idle");
  };

  const handleExport = () => {
    if (messages.length === 0) return;
    const md = exportChatAsMarkdown(messages);
    const blob = new Blob([md], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "mychat-export.md";
    a.click();
    URL.revokeObjectURL(url);
  };

  const handlePreviewDoc = (filename) => {
    setPreviewDoc((prev) => (prev === filename ? null : filename));
  };

  return (
    <div className={`app ${previewDoc ? "with-preview" : ""}`}>
      <Sidebar
        documents={documents}
        selectedDoc={selectedDoc}
        onSelectDoc={setSelectedDoc}
        showSources={showSources}
        onToggleSources={() => setShowSources((s) => !s)}
        onClearChat={handleClearChat}
        onUpload={handleUpload}
        view={view}
        onSetView={setView}
        onPreviewDoc={handlePreviewDoc}
        darkMode={darkMode}
        onToggleDark={() => setDarkMode((d) => !d)}
        messageCount={messages.length}
        onExport={handleExport}
      />

      <main className="main">
        <header className="header">
          <div className="header-spacer" />
          <span className="header-title">MyChat</span>
          <span className={`status-badge ${status.toLowerCase()}`}>
            {status}
          </span>
        </header>

        {view === "chat" ? (
          <ChatArea
            messages={messages}
            isLoading={isLoading}
            showSources={showSources}
            onSend={handleSend}
          />
        ) : (
          <Dashboard documents={documents} onPreview={handlePreviewDoc} />
        )}
      </main>

      {previewDoc && (
        <PdfPreview filename={previewDoc} onClose={() => setPreviewDoc(null)} />
      )}
    </div>
  );
}
