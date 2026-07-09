import React, { useState, useRef, useEffect } from "react"
import MessageBubble from "./components/MessageBubble"

const API_URL = import.meta.env.VITE_API_URL || "http://3.6.91.181:8000"

const SAMPLE_QUESTIONS = [
  "Which product category had the highest return rate in 2024?",
  "Which city tier has the highest Cash on Delivery usage?",
  "What is the most popular payment method for male customers?",
  "Which seller had the highest total revenue from delivered orders?",
  "What is the average order value on weekends vs weekdays?",
]

export default function App() {
  const [messages, setMessages] = useState([
    {
      role: "assistant",
      content: "Hi! I am your Data Investigator Agent. Ask me anything about sales, customers, orders, or delivery performance.",
      sql_queries: null,
      turns_taken: null,
    }
  ])
  const [input, setInput] = useState("")
  const [loading, setLoading] = useState(false)
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages])

  const sendMessage = async (question) => {
    const q = question || input.trim()
    if (!q || loading) return

    setInput("")
    setMessages(prev => [...prev, { role: "user", content: q }])
    setLoading(true)

    try {
      const response = await fetch(`${API_URL}/agent/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: q, max_retries: 5 }),
      })

      if (!response.ok) {
        const err = await response.json()
        throw new Error(err.detail || "Agent failed to answer")
      }

      const data = await response.json()
      setMessages(prev => [...prev, {
        role: "assistant",
        content: data.display || data.answer || "No answer returned",
        sql_queries: data.sql_queries,
        turns_taken: data.turns_taken,
      }])
    } catch (err) {
      setMessages(prev => [...prev, {
        role: "assistant",
        content: `Sorry, something went wrong: ${err.message}`,
        sql_queries: null,
        turns_taken: null,
        error: true,
      }])
    } finally {
      setLoading(false)
    }
  }

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  return (
    <div style={styles.container}>
      <style>{`
        @keyframes pulse {
          0%, 80%, 100% { opacity: 0.3; transform: scale(0.8); }
          40% { opacity: 1; transform: scale(1); }
        }
      `}</style>

      <div style={styles.header}>
        <div style={styles.headerIcon}>📊</div>
        <div>
          <div style={styles.headerTitle}>Data Investigator Agent</div>
          <div style={styles.headerSubtitle}>Powered by AI — ask anything about your data</div>
        </div>
      </div>

      <div style={styles.chatWindow}>
        {messages.map((msg, i) => (
          <MessageBubble key={i} message={msg} />
        ))}

        {loading && (
          <div style={styles.loadingRow}>
            <div style={styles.loadingBubble}>
              <div style={{...styles.dot, animationDelay: "0s"}} />
              <div style={{...styles.dot, animationDelay: "0.2s"}} />
              <div style={{...styles.dot, animationDelay: "0.4s"}} />
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {messages.length === 1 && (
        <div style={styles.samples}>
          <div style={styles.samplesLabel}>Try asking:</div>
          <div style={styles.sampleChips}>
            {SAMPLE_QUESTIONS.map((q, i) => (
              <button key={i} style={styles.chip} onClick={() => sendMessage(q)}>
                {q}
              </button>
            ))}
          </div>
        </div>
      )}

      <div style={styles.inputRow}>
        <textarea
          style={styles.input}
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask a business question about your data..."
          rows={1}
          disabled={loading}
        />
        <button
          style={{
            ...styles.sendButton,
            opacity: loading || !input.trim() ? 0.5 : 1,
          }}
          onClick={() => sendMessage()}
          disabled={loading || !input.trim()}
        >
          ➤
        </button>
      </div>
    </div>
  )
}

const styles = {
  container: {
    display: "flex",
    flexDirection: "column",
    height: "100vh",
    maxWidth: "800px",
    margin: "0 auto",
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
    background: "#0f0f0f",
    color: "#e8e8e8",
  },
  header: {
    display: "flex",
    alignItems: "center",
    gap: "12px",
    padding: "20px 24px",
    borderBottom: "1px solid #1e1e1e",
    background: "#141414",
  },
  headerIcon: { fontSize: "28px" },
  headerTitle: { fontSize: "18px", fontWeight: "600", color: "#ffffff" },
  headerSubtitle: { fontSize: "12px", color: "#666", marginTop: "2px" },
  chatWindow: {
    flex: 1,
    overflowY: "auto",
    padding: "24px",
    display: "flex",
    flexDirection: "column",
    gap: "16px",
  },
  loadingRow: { display: "flex", justifyContent: "flex-start" },
  loadingBubble: {
    background: "#1e1e1e",
    borderRadius: "12px",
    padding: "14px 18px",
    display: "flex",
    gap: "6px",
    alignItems: "center",
  },
  dot: {
    width: "8px",
    height: "8px",
    borderRadius: "50%",
    background: "#555",
    animation: "pulse 1.4s infinite ease-in-out",
  },
  samples: { padding: "0 24px 16px" },
  samplesLabel: { fontSize: "12px", color: "#555", marginBottom: "8px" },
  sampleChips: { display: "flex", flexWrap: "wrap", gap: "8px" },
  chip: {
    background: "#1a1a1a",
    border: "1px solid #2a2a2a",
    borderRadius: "20px",
    padding: "8px 14px",
    fontSize: "12px",
    color: "#aaa",
    cursor: "pointer",
  },
  inputRow: {
    display: "flex",
    gap: "12px",
    padding: "16px 24px",
    borderTop: "1px solid #1e1e1e",
    background: "#141414",
    alignItems: "flex-end",
  },
  input: {
    flex: 1,
    background: "#1e1e1e",
    border: "1px solid #2a2a2a",
    borderRadius: "12px",
    padding: "12px 16px",
    color: "#e8e8e8",
    fontSize: "14px",
    resize: "none",
    outline: "none",
    fontFamily: "inherit",
  },
  sendButton: {
    background: "#2563eb",
    border: "none",
    borderRadius: "10px",
    width: "44px",
    height: "44px",
    color: "white",
    fontSize: "18px",
    cursor: "pointer",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
  },
}