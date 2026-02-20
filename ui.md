# Prompt to Generate UI

You are a senior frontend engineer.

Build a clean, modern, production‑style UI for a RAG chatbot application. The UI should feel like a real AI product, focusing on usability, clarity, and smooth interaction — not just a simple demo page.

Refer any chatbot application in market- example pdf.ai,chatgpt oe any other viral one

### Application Context

* The UI connects to an existing RAG backend API.
* Endpoint: POST /chat and Post/ingest
* Input JSON: Refer to API Specs in apps/api folder
* Output JSON: Refer to API Specs in apps/api folder
* The backend already performs retrieval, reranking, and LLM generation.
* The UI is only responsible for user interaction, API communication, and displaying responses.


### Layout Requirements

Create a clean, structured layout with the following sections:

1. Header

   * Application title: "RAG Assistant"
   * Status indicator (Idle / Thinking / Error)

2. Main Chat Area

   * Scrollable chat history
   * Chat bubbles for User and AI
   * Markdown rendering for AI responses
   * Clean readable spacing
   

3. Input Section

   * Text input box
   * Send button
   * Press Enter to send
   * Disable input while waiting for response

4. Sidebar (optional but recommended)

   * Clear chat button
   * Toggle "Show Sources"
   * Session info placeholder


### Functional Requirements

* Send user query to POST /chat
* Show loading / thinking indicator while waiting
* Display AI response clearly
* Auto‑scroll to latest message
* Handle API errors gracefully
* Prevent multiple sends while request is active
* Maintain chat history in memory during session
* Create a sapce to show all the user uploaded documents
* If user has uploaded multiple, give him an option to select to for chatting



### RAG‑Specific Features

* Option to display retrieved sources and reranked answers below answers
* Toggle show/hide sources
* Proper formatting for long answers
* Clear separation of answer vs sources
* Show Citations


### UX and Product Feel

* Smooth chat experience
* Typing / thinking indicator ("Thinking...")
* Clean, modern UI
* Proper spacing and readability
* Minimal but professional styling
* Responsive layout (desktop focused)



### Code Constraints

* Keep code simple and readable
* Avoid unnecessary complexity
* Organize files cleanly
* Comment important logic (API call, rendering, state)
* Make UI easy to extend later



### Optional Enhancements (Generate Only If Asked Later)

* Streaming response support (token by token)
* Dark mode
* Chat persistence
* Session ID handling
* Document upload UI
* Multi‑user support (conceptual)



### Output Expectations

* Provide complete working frontend code
* Ensure API call integration is correct
* UI should be directly runnable
* Code should be clean and modifiable

