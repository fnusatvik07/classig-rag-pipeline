import { useState } from "react";
import ReactMarkdown from "react-markdown";
import ChunkComparison from "./ChunkComparison";

export default function ChatMessage({ message, showSources }) {
  const isUser = message.role === "user";
  const [feedback, setFeedback] = useState(null); // "up" | "down" | null

  return (
    <div className={`chat-message ${isUser ? "user" : "assistant"}`}>
      <div className="message-avatar">{isUser ? "You" : "AI"}</div>
      <div className="message-content">
        {isUser ? (
          <p>{message.content}</p>
        ) : (
          <>
            <ReactMarkdown>{message.content}</ReactMarkdown>

            {/* Response metadata */}
            {message.response_time_ms != null && (
              <div className="response-meta">
                <span className="meta-badge meta-time">
                  {message.response_time_ms.toFixed(0)}ms
                </span>
                <span
                  className={`meta-badge ${
                    message.cache_hit ? "meta-cache-hit" : "meta-cache-miss"
                  }`}
                >
                  {message.cache_hit
                    ? `Cache HIT (${message.cache_tier})`
                    : "Cache MISS"}
                </span>
              </div>
            )}

            {/* Feedback buttons */}
            <div className="message-actions">
              <button
                className={`feedback-btn ${feedback === "up" ? "active" : ""}`}
                onClick={() => setFeedback(feedback === "up" ? null : "up")}
                title="Helpful"
              >
                👍
              </button>
              <button
                className={`feedback-btn ${feedback === "down" ? "active" : ""}`}
                onClick={() => setFeedback(feedback === "down" ? null : "down")}
                title="Not helpful"
              >
                👎
              </button>
            </div>

            {/* Chunk comparison: sources, retrieved, reranked */}
            {showSources && (
              <ChunkComparison
                sources={message.sources}
                retrieved={message.retrieved}
                reranked={message.reranked}
              />
            )}
          </>
        )}
      </div>
    </div>
  );
}
