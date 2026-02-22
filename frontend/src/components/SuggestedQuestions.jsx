const suggestions = [
  { title: "Summarize", text: "Summarize the key points of this document" },
  { title: "Key Findings", text: "What are the most important findings or takeaways?" },
  { title: "Extract Data", text: "Extract the main data points and statistics mentioned" },
  { title: "Explain", text: "Explain the main concepts in simple terms" },
];

const features = [
  {
    icon: "ai",
    title: "AI-Powered Search",
    description: "Semantic search with reranking finds the most relevant passages across your documents.",
  },
  {
    icon: "docs",
    title: "Multi-Document Support",
    description: "Upload multiple PDFs, TXT, or Markdown files and query them individually or together.",
  },
  {
    icon: "sources",
    title: "Source Citations",
    description: "Every answer includes source citations with page numbers so you can verify the information.",
  },
];

const steps = [
  { number: "1", title: "Upload", description: "Drop your PDF, TXT, or Markdown files in the sidebar." },
  { number: "2", title: "Ask", description: "Type your question in the chat input below." },
  { number: "3", title: "Explore", description: "Review AI answers with cited sources and preview documents side-by-side." },
];

export default function SuggestedQuestions({ onSelect }) {
  return (
    <div className="landing-page">
      <div className="landing-features">
        {features.map((f, i) => (
          <div key={i} className="landing-feature-card">
            <div className={`landing-feature-icon landing-feature-icon--${f.icon}`} />
            <h4 className="landing-feature-title">{f.title}</h4>
            <p className="landing-feature-desc">{f.description}</p>
          </div>
        ))}
      </div>

      <div className="landing-steps">
        <p className="landing-steps-label">Getting Started</p>
        <div className="landing-steps-row">
          {steps.map((s, i) => (
            <div key={i} className="landing-step">
              <span className="landing-step-number">{s.number}</span>
              <div>
                <strong>{s.title}</strong>
                <p>{s.description}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="suggested-questions">
        <p className="suggested-label">Try asking</p>
        <div className="suggested-grid">
          {suggestions.map((s, i) => (
            <button
              key={i}
              className="suggested-card"
              onClick={() => onSelect(s.text)}
            >
              <span className="suggested-title">{s.title}</span>
              <span className="suggested-text">{s.text}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
