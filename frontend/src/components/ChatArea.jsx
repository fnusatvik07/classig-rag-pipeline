import { useEffect, useRef } from "react";
import ChatMessage from "./ChatMessage";
import ChatInput from "./ChatInput";
import SuggestedQuestions from "./SuggestedQuestions";

export default function ChatArea({ messages, isLoading, showSources, onSend }) {
  const bottomRef = useRef(null);

  // Auto-scroll to latest message
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  return (
    <div className="chat-area">
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
