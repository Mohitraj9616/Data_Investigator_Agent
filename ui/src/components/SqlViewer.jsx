import React, { useState } from "react"

export default function SqlViewer({ queries }) {
  const [open, setOpen] = useState(false)
  const [copied, setCopied] = useState(null)

  const copy = (sql, i) => {
    navigator.clipboard.writeText(sql)
    setCopied(i)
    setTimeout(() => setCopied(null), 1500)
  }

  return (
    <div style={{ maxWidth: "75%", paddingLeft: "4px" }}>
      <button
        onClick={() => setOpen(!open)}
        style={{
          background: "none",
          border: "none",
          color: "#555",
          fontSize: "11px",
          cursor: "pointer",
          padding: "0",
          display: "flex",
          alignItems: "center",
          gap: "4px",
        }}
      >
        {open ? "▼" : "▶"} View SQL {queries.length > 1 ? `(${queries.length} queries)` : ""}
      </button>

      {open && (
        <div style={{ marginTop: "8px", display: "flex", flexDirection: "column", gap: "8px" }}>
          {queries.map((sql, i) => (
            <div key={i} style={{
              background: "#0d0d0d",
              border: "1px solid #2a2a2a",
              borderRadius: "8px",
              padding: "12px 40px 12px 12px",
              fontFamily: "monospace",
              fontSize: "12px",
              color: "#a8d8a8",
              whiteSpace: "pre-wrap",
              wordBreak: "break-word",
              position: "relative",
            }}>
              {sql}
              <button
                onClick={() => copy(sql, i)}
                style={{
                  position: "absolute",
                  top: "8px",
                  right: "8px",
                  background: "#1e1e1e",
                  border: "1px solid #333",
                  borderRadius: "4px",
                  color: copied === i ? "#4ade80" : "#666",
                  fontSize: "10px",
                  padding: "2px 6px",
                  cursor: "pointer",
                }}
              >
                {copied === i ? "✓" : "copy"}
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
