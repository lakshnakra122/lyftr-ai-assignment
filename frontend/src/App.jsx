import { useEffect, useRef, useState } from 'react'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

function newSessionId() {
  const rand = Math.random().toString(16).slice(2, 8)
  return `s-${rand}`
}

export default function App() {
  // A new session starts on each page load
  const [sessionId] = useState(newSessionId)
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [systemPrompt, setSystemPrompt] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, error])

  async function send() {
    const text = input.trim()
    if (!text || loading) return
    setInput('')
    setError('')
    setMessages((prev) => [...prev, { role: 'user', content: text }])
    setLoading(true)
    try {
      const body = { session_id: sessionId, message: text }
      if (systemPrompt.trim()) body.system_prompt = systemPrompt.trim()
      const res = await fetch(`${API_URL}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) {
        const detail = typeof data.detail === 'string' ? data.detail : `Request failed (${res.status})`
        setError(res.status === 503 ? 'All providers are unavailable right now. Please try again in a moment.' : detail)
        return
      }
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: data.reply, metadata: data.metadata },
      ])
    } catch (e) {
      setError('Could not reach the server. Please check your connection and try again.')
    } finally {
      setLoading(false)
    }
  }

  function onKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      send()
    }
  }

  return (
    <div className="page">
      <header className="header">
        <h1>Lyftr AI Chatbot</h1>
        <p>Multi-turn chat with key failover, caching and per-request token tracking</p>
        <span className="session">Session: {sessionId}</span>
      </header>

      <label className="system-label" htmlFor="system-prompt">System prompt (optional)</label>
      <input
        id="system-prompt"
        data-testid="system-prompt-input"
        className="system-input"
        type="text"
        placeholder="e.g. Answer like a friendly teacher, in simple English"
        value={systemPrompt}
        onChange={(e) => setSystemPrompt(e.target.value)}
      />

      <main className="chat-box">
        {messages.length === 0 && (
          <p className="empty">Send a message to start. Try: “What is the capital of France?” — send the same first message in a new tab/session to see a cache hit.</p>
        )}
        {messages.map((m, i) =>
          m.role === 'user' ? (
            <div key={i} className="msg user-msg">
              <div className="bubble user-bubble">{m.content}</div>
            </div>
          ) : (
            <div key={i} className="msg assistant-msg" data-testid="assistant-message">
              <div className="bubble assistant-bubble">
                <p>{m.content}</p>
                {m.metadata && (
                  <div className="meta">
                    <span data-testid="meta-source">{m.metadata.resolution_source}</span>
                    <span data-testid="meta-model">{m.metadata.model}</span>
                    <span data-testid="meta-latency">{m.metadata.latency_ms} ms</span>
                    <span>In: <span data-testid="meta-input-tokens">{m.metadata.input_tokens}</span></span>
                    <span>Out: <span data-testid="meta-output-tokens">{m.metadata.output_tokens}</span></span>
                    <span>Key: {m.metadata.key_id ?? '—'}</span>
                    <span>Fallbacks: {m.metadata.fallback_attempts}</span>
                  </div>
                )}
              </div>
            </div>
          ),
        )}
        {loading && <p className="loading">Thinking…</p>}
        {error && <div className="error-box" role="alert">{error}</div>}
        <div ref={bottomRef} />
      </main>

      <div className="composer">
        <textarea
          data-testid="chat-input"
          rows={2}
          placeholder="Type your message… (Enter to send)"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKeyDown}
        />
        <button data-testid="send-button" onClick={send} disabled={loading}>
          Send
        </button>
      </div>
    </div>
  )
}
