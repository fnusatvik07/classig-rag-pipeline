const suggestions = [
  {
    icon: "📝",
    title: "Summarize",
    text: "Summarize the key points of this document",
  },
  {
    icon: "🔍",
    title: "Key Findings",
    text: "What are the most important findings or takeaways?",
  },
  {
    icon: "📊",
    title: "Extract Data",
    text: "Extract the main data points and statistics mentioned",
  },
  {
    icon: "❓",
    title: "Explain",
    text: "Explain the main concepts in simple terms",
  },
];

export default function SuggestedQuestions({ onSelect }) {
  return (
    <div className="suggested-questions">
      <p className="suggested-label">Try asking</p>
      <div className="suggested-grid">
        {suggestions.map((s, i) => (
          <button
            key={i}
            className="suggested-card"
            onClick={() => onSelect(s.text)}
          >
            <span className="suggested-icon">{s.icon}</span>
            <span className="suggested-title">{s.title}</span>
            <span className="suggested-text">{s.text}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
