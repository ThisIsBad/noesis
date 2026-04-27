// Console chat — thin glue between the textarea + the Console backend.
//
// Flow:
//   1. user types prompt + clicks Send
//   2. POST /api/chat → {session_id}
//   3. open EventSource on /api/stream?session_id=…
//   4. for every event:
//        chat-shaped events (assistant.text, assistant.thinking, etc.)
//          → append a bubble to #chat-history
//        trace.update events
//          → fire `noesis:trace` custom event so trace.js re-renders
//        session.done / session.error
//          → close the stream, re-enable Send

const form = document.getElementById("chat-form");
const input = document.getElementById("chat-input");
const sendBtn = document.getElementById("chat-send");
const status = document.getElementById("chat-status");
const history = document.getElementById("chat-history");
const authInput = document.getElementById("auth-input");

// Persist the bearer token across reloads (browser-local; the secret
// already lives client-side anyway in the SSE connection).
const SECRET_KEY = "noesis_console_secret";
authInput.value = localStorage.getItem(SECRET_KEY) || "";
authInput.addEventListener("change", () =>
  localStorage.setItem(SECRET_KEY, authInput.value)
);

let currentEventSource = null;

form.addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const prompt = input.value.trim();
  if (!prompt) return;
  if (currentEventSource) {
    currentEventSource.close();
    currentEventSource = null;
  }

  appendMsg("user", prompt);
  input.value = "";
  setSending(true);
  window.dispatchEvent(new CustomEvent("noesis:reset"));

  let session_id;
  try {
    const headers = { "Content-Type": "application/json" };
    const tok = authInput.value.trim();
    if (tok) headers["Authorization"] = "Bearer " + tok;
    const resp = await fetch("/api/chat", {
      method: "POST",
      headers,
      body: JSON.stringify({ prompt }),
    });
    if (!resp.ok) {
      const text = await resp.text();
      throw new Error(`POST /api/chat → ${resp.status}: ${text}`);
    }
    ({ session_id } = await resp.json());
  } catch (err) {
    appendMsg("error", String(err.message || err));
    setSending(false);
    return;
  }

  status.textContent = `session ${session_id.slice(0, 8)}…`;
  openStream(session_id);
});

function openStream(sessionId) {
  // EventSource doesn't allow custom headers, so the bearer must come
  // through a query param on /api/stream when CONSOLE_SECRET is set.
  // Phase-1 simplification: same-origin behind a localhost-only deploy
  // means we can skip that. When CONSOLE_SECRET is enforced for the
  // SSE endpoint, a future revision will switch to fetch + ReadableStream.
  const url = `/api/stream?session_id=${encodeURIComponent(sessionId)}`;
  const es = new EventSource(url);
  currentEventSource = es;

  const dispatch = (ev) => {
    let data;
    try {
      data = JSON.parse(ev.data);
    } catch {
      return;
    }
    handleEvent(data);
  };

  // The backend emits typed events (event: assistant.text, etc.). Browsers
  // fire those by name; if no listener matches they fall back to "message".
  // We register a handler for every type Phase 1 produces.
  for (const t of [
    "session.start",
    "assistant.text",
    "assistant.thinking",
    "tool.pending",
    "tool.result",
    "trace.update",
    "session.done",
    "session.error",
    "message",
  ]) {
    es.addEventListener(t, dispatch);
  }

  es.onerror = () => {
    appendMsg("error", "SSE connection dropped");
    es.close();
    currentEventSource = null;
    setSending(false);
  };
}

function handleEvent(ev) {
  switch (ev.type) {
    case "session.start":
      appendMsg(
        "system",
        `session ${ev.session_id.slice(0, 8)}… started; trace ${ev.trace_id}`
      );
      break;
    case "assistant.text":
      appendMsg("assistant", ev.text);
      break;
    case "assistant.thinking":
      appendMsg("thinking", ev.text);
      break;
    case "tool.pending":
      appendMsg(
        "system",
        `→ ${ev.tool_name} (${summariseInput(ev.input)})`
      );
      break;
    case "tool.result":
      appendMsg(
        "system",
        ev.is_error
          ? `✗ ${ev.tool_name}: ${ev.text}`
          : `← ${ev.tool_name}: ${ev.text}`
      );
      break;
    case "trace.update":
      window.dispatchEvent(
        new CustomEvent("noesis:trace", { detail: { trace: ev.trace } })
      );
      break;
    case "session.done":
      appendMsg(
        "system",
        `done · cost $${(ev.cost_usd ?? 0).toFixed(4)} · ${ev.duration_ms}ms`
      );
      if (currentEventSource) currentEventSource.close();
      currentEventSource = null;
      setSending(false);
      break;
    case "session.error":
      appendMsg("error", ev.error || "unknown error");
      if (currentEventSource) currentEventSource.close();
      currentEventSource = null;
      setSending(false);
      break;
    default:
      // Unknown event types are silently ignored — Console can add new
      // ones over time without breaking older clients.
      break;
  }
}

function appendMsg(role, text) {
  const div = document.createElement("div");
  div.className = `chat-msg ${role}`;
  div.textContent = text;
  history.appendChild(div);
  history.scrollTop = history.scrollHeight;
}

function setSending(busy) {
  sendBtn.disabled = busy;
  if (!busy) status.textContent = "";
}

function summariseInput(input) {
  if (!input || typeof input !== "object") return "";
  const parts = [];
  for (const [k, v] of Object.entries(input)) {
    let s = typeof v === "string" ? v : JSON.stringify(v);
    if (s.length > 40) s = s.slice(0, 37) + "…";
    parts.push(`${k}=${s}`);
  }
  return parts.join(", ");
}
