import React from "react"
import SqlViewer from "./SqlViewer"

export default function MessageBubble({ message }) {
  const isUser = message.role === "user"

  return (
    <div style={{
      display: "flex",
      flexDirection: "column",
      alignItems: isUser ? "flex-end" : "flex-start",
      gap: "6px",
    }}>
      <div style={{
        maxWidth: "75%",
        background: isUser ? "#2563eb" : "#1e1e1e",
        borderRadius: isUser ? "18px 18px 4px 18px" : "18px 18px 18px 4px",
        padding: "12px 16px",
        fontSize: "14px",
        lineHeight: "1.6",
        color: isUser ? "#ffffff" : "#e8e8e8",
        border: message.error ? "1px solid #dc2626" : "none",
        whiteSpace: "pre-wrap",
      }}>
        {message.content}
      </div>

      {!isUser && message.turns_taken && (
        <div style={{ fontSize: "11px", color: "#444", paddingLeft: "4px" }}>
          {message.turns_taken} LLM {message.turns_taken === 1 ? "call" : "calls"}
        </div>
      )}

      {!isUser && message.sql_queries && message.sql_queries.length > 0 && (
        <SqlViewer queries={message.sql_queries} />
      )}
    </div>
  )
}
