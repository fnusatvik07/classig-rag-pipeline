import { useEffect, useRef } from "react";
import ChatMessage from "./ChatMessage";
import ChatInput from "./ChatInput";
import SuggestedQuestions from "./SuggestedQuestions";

export default function ChatArea({ messages, isLoading, showSources, onSend, documents, previewDoc, onPreviewDoc }) {
  const bottomRef = useRef(null);

  // Auto-scroll to latest message
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  return (
    <div className="chat-area">
      {documents && documents.length > 0 && (
        <div className="doc-toolbar">
          <span className="doc-toolbar-label">DOCUMENTS</span>
          <div className="doc-toolbar-chips">
            {documents.map((doc) => {
              const name = typeof doc === "string" ? doc : doc.name;
              return (
                <button
                  key={name}
                  className={`doc-chip ${previewDoc === name ? "active" : ""}`}
                  onClick={() => onPreviewDoc(name)}
                  title={name}
                >
                  📄 {name}
                </button>
              );
            })}
          </div>
        </div>
      )}
      <div className="chat-messages">
        {messages.length === 0 && (
          <div className="empty-state">
            <div className="empty-icon">💬</div>
            <h2>MyChat</h2>
            <p>Upload a document and start asking questions.</p>
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
