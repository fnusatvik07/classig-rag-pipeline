import { useEffect, useRef } from "react";
import ChatMessage from "./ChatMessage";
import ChatInput from "./ChatInput";
import SuggestedQuestions from "./SuggestedQuestions";

export default function ChatArea({ messages, isLoading, showSources, onSend, documents, previewDoc, onPreviewDoc, selectedDoc, onSelectDoc }) {
  const bottomRef = useRef(null);

  // Auto-scroll to latest message
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  return (
    <div className="chat-area">
      {documents && documents.length > 0 && (
        <div className="doc-toolbar">
          <label className="doc-toolbar-label" htmlFor="doc-selector">
            CHAT WITH
          </label>
          <select
            id="doc-selector"
            className="doc-selector"
            value={selectedDoc || ""}
            onChange={(e) => onSelectDoc(e.target.value || null)}
          >
            <option value="">All Documents</option>
            {documents.map((doc) => {
              const name = typeof doc === "string" ? doc : doc.name;
              return (
                <option key={name} value={name}>
                  {name}
                </option>
              );
            })}
          </select>
          {selectedDoc && (
            <button
              className={`doc-chip ${previewDoc === selectedDoc ? "active" : ""}`}
              onClick={() => onPreviewDoc(selectedDoc)}
              title="Preview selected document"
            >
              Preview
            </button>
          )}
        </div>
      )}
      <div className="chat-messages">
        {messages.length === 0 && (
          <div className="empty-state">
            <h2>MyChat</h2>
            <p className="empty-subtitle">Your AI-powered document assistant</p>
            <p>Upload documents and ask questions to get instant, cited answers.</p>
            <SuggestedQuestions onSelect={onSend} />
          </div>
        )}

        {messages.map((msg, i) => (
          <ChatMessage key={i} message={msg} showSources={showSources} />
        ))}

        {isLoading && (
          <div className="chat-message assistant">
            <div className="message-avatar">AI</div>
            <div className="message-content thinking">
              <span className="dot" />
              <span className="dot" />
              <span className="dot" />
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      <div className="chat-input-wrapper">
        <ChatInput onSend={onSend} disabled={isLoading} />
        <span className="input-hint">Press Enter to send, Shift+Enter for new line</span>
      </div>
    </div>
  );
}
