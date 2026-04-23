/* Theoria frontend — zero-dep vanilla JS renderer for decision traces.
 *
 * Layout strategy:
 *  - compute longest-path layer for each node from the root (topological)
 *  - within a layer, order by first-appearance in DFS
 *  - position nodes on a grid; draw edges as cubic Bezier curves
 *  - support click-to-select and pan/zoom on the SVG
 */

const SVG_NS = "http://www.w3.org/2000/svg";
const NODE_W = 220;
const NODE_H = 64;
const COL_GAP = 80;
const ROW_GAP = 26;
const PAD_X = 40;
const PAD_Y = 40;

const KIND_COLORS = {
  question: "#ffd166",
  premise: "#9ecbff",
  observation: "#79c0ff",
  rule_check: "#ffa657",
  constraint: "#ffa657",
  inference: "#a5d6ff",
  evidence: "#56d4dd",
  alternative: "#b388eb",
  counterfactual: "#b388eb",
  conclusion: "#7ee787",
  note: "#8b98a5",
};

const STATUS_FILL = {
  ok: "#12321f",
  triggered: "#3a2a12",
  failed: "#3a1a1a",
  rejected: "#2a1f3a",
  pending: "#332f14",
  unknown: "#1f2630",
  info: "#1b242d",
};

const STATUS_LABEL = {
  ok: "OK",
  triggered: "TRIGGERED",
  failed: "FAILED",
  rejected: "REJECTED",
  pending: "PENDING",
  unknown: "UNKNOWN",
  info: "INFO",
};

const state = {
  traces: [],
  selectedTrace: null,
  selectedStep: null,
  view: { tx: 0, ty: 0, k: 1 },
  dragging: null,
};

// ----- API ----------------------------------------------------------------

async function api(path, opts = {}) {
  const res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${body}`);
  }
  if (res.status === 204) return null;
  return res.json();
}

async function loadTraces() {
  const data = await api("/api/traces");
  state.traces = data.traces || [];
  renderTraceList();
  if (state.traces.length > 0 && !state.selectedTrace) {
    selectTrace(state.traces[0].id);
  } else if (state.traces.length === 0) {
    clearCanvas();
  }
}

// ----- Trace list ---------------------------------------------------------

function renderTraceList() {
  const ul = document.getElementById("trace-list");
  const filter = (document.getElementById("filter").value || "").toLowerCase().trim();
  ul.innerHTML = "";

  const matches = state.traces.filter((t) => {
    if (!filter) return true;
    const hay = [t.title, t.source, t.kind, ...(t.tags || [])].join(" ").toLowerCase();
    return hay.includes(filter);
  });

  if (matches.length === 0) {
    const empty = document.createElement("li");
    empty.className = "muted";
    empty.textContent = "No traces — click \"Load samples\".";
    empty.style.padding = "8px";
    ul.appendChild(empty);
    return;
  }

  for (const t of matches) {
    const li = document.createElement("li");
    li.className = "trace-item" + (state.selectedTrace && state.selectedTrace.id === t.id ? " active" : "");
    li.innerHTML = `
      <div class="title">${escapeHtml(t.title)}</div>
      <div class="meta">
        <span class="tag">${escapeHtml(t.source)}</span>
        <span class="tag">${escapeHtml(t.kind)}</span>
        ${(t.tags || []).map((tag) => `<span class="tag">${escapeHtml(tag)}</span>`).join("")}
      </div>`;
    li.addEventListener("click", () => selectTrace(t.id));
    ul.appendChild(li);
  }
}

async function selectTrace(id) {
  const trace = await api(`/api/traces/${encodeURIComponent(id)}`);
  state.selectedTrace = trace;
  state.selectedStep = null;
  renderTraceList();
  renderTraceHeader(trace);
  renderGraph(trace);
  renderDetails(null);
}

function renderTraceHeader(trace) {
  document.getElementById("trace-title").textContent = trace.title;
  document.getElementById("trace-question").textContent = trace.question || "";
  const outcomeEl = document.getElementById("trace-outcome");
  if (trace.outcome) {
    const cls = (trace.outcome.verdict || "").toLowerCase();
    outcomeEl.className = `outcome ${cls}`;
    outcomeEl.innerHTML = `
      <div class="verdict">${escapeHtml(trace.outcome.verdict)}</div>
      <div class="summary">${escapeHtml(trace.outcome.summary || "")}</div>`;
  } else {
    outcomeEl.className = "outcome";
    outcomeEl.textContent = "";
  }
}

// ----- Layout -------------------------------------------------------------

function computeLayout(trace) {
  const stepById = new Map(trace.steps.map((s) => [s.id, s]));
  const outgoing = new Map(trace.steps.map((s) => [s.id, []]));
  const incoming = new Map(trace.steps.map((s) => [s.id, []]));
  for (const edge of trace.edges) {
    if (!stepById.has(edge.source) || !stepById.has(edge.target)) continue;
    outgoing.get(edge.source).push(edge);
    incoming.get(edge.target).push(edge);
  }

  // Longest-path layering from the root.
  const depth = new Map();
  const stack = [[trace.root, 0]];
  const seen = new Set();
  while (stack.length) {
    const [id, d] = stack.pop();
    const prev = depth.get(id);
    if (prev !== undefined && prev >= d) continue;
    depth.set(id, d);
    for (const e of outgoing.get(id) || []) {
      // Don't let cycles blow the stack; bail if we'd revisit at a shallower depth.
      const key = `${id}→${e.target}`;
      if (seen.has(key) && (depth.get(e.target) ?? -1) >= d + 1) continue;
      seen.add(key);
      stack.push([e.target, d + 1]);
    }
  }
  // Any node unreachable from the root — place it one layer beyond its max predecessor.
  let changed = true;
  while (changed) {
    changed = false;
    for (const step of trace.steps) {
      if (depth.has(step.id)) continue;
      const preds = incoming.get(step.id) || [];
      const pd = preds.map((e) => depth.get(e.source)).filter((x) => x !== undefined);
      if (pd.length > 0) {
        depth.set(step.id, Math.max(...pd) + 1);
        changed = true;
      }
    }
  }
  // Still-unreachable nodes → layer 0 (shouldn't happen post-validate, defensive).
  for (const step of trace.steps) {
    if (!depth.has(step.id)) depth.set(step.id, 0);
  }

  // Group by layer, preserving original step order for stable rows.
  const layers = new Map();
  for (const step of trace.steps) {
    const d = depth.get(step.id);
    if (!layers.has(d)) layers.set(d, []);
    layers.get(d).push(step);
  }

  const positions = new Map();
  const maxDepth = Math.max(...depth.values());
  let maxRows = 0;
  for (let d = 0; d <= maxDepth; d++) {
    const column = layers.get(d) || [];
    maxRows = Math.max(maxRows, column.length);
    column.forEach((step, i) => {
      positions.set(step.id, {
        x: PAD_X + d * (NODE_W + COL_GAP),
        y: PAD_Y + i * (NODE_H + ROW_GAP),
      });
    });
  }

  const width = PAD_X * 2 + (maxDepth + 1) * NODE_W + maxDepth * COL_GAP;
  const height = PAD_Y * 2 + maxRows * NODE_H + (maxRows - 1) * ROW_GAP;
  return { positions, width, height, stepById };
}

// ----- Rendering ----------------------------------------------------------

function clearCanvas() {
  const svg = document.getElementById("graph");
  svg.innerHTML = "";
  document.getElementById("trace-title").textContent = "Select a trace";
  document.getElementById("trace-question").textContent = "";
  document.getElementById("trace-outcome").textContent = "";
  renderLegend();
}

function renderLegend() {
  const legend = document.getElementById("legend");
  const items = [
    ["ok", "OK / satisfied"],
    ["triggered", "Triggered"],
    ["failed", "Failed / blocked"],
    ["rejected", "Pruned"],
    ["unknown", "Unknown"],
  ];
  legend.innerHTML = items
    .map(([k, label]) => {
      const color = {
        ok: "#7ee787",
        triggered: "#f5a623",
        failed: "#ff6b6b",
        rejected: "#b388eb",
        unknown: "#6f7a8a",
      }[k];
      return `<div><span class="swatch" style="background:${color}"></span>${label}</div>`;
    })
    .join("");
}

function renderGraph(trace) {
  const svg = document.getElementById("graph");
  svg.innerHTML = "";

  const { positions, width, height } = computeLayout(trace);

  const viewport = document.createElementNS(SVG_NS, "g");
  viewport.setAttribute("id", "viewport");
  svg.appendChild(viewport);

  // Arrowhead markers.
  const defs = document.createElementNS(SVG_NS, "defs");
  for (const [name, color] of [
    ["arrow-default", "#8b98a5"],
    ["arrow-supports", "#56d4dd"],
    ["arrow-requires", "#9ecbff"],
    ["arrow-considers", "#b388eb"],
    ["arrow-contradicts", "#ff6b6b"],
    ["arrow-prunes", "#ff6b6b"],
    ["arrow-implies", "#7ee787"],
    ["arrow-yields", "#7ee787"],
    ["arrow-witness", "#f5a623"],
  ]) {
    const marker = document.createElementNS(SVG_NS, "marker");
    marker.setAttribute("id", name);
    marker.setAttribute("viewBox", "0 0 10 10");
    marker.setAttribute("refX", "9");
    marker.setAttribute("refY", "5");
    marker.setAttribute("markerWidth", "6");
    marker.setAttribute("markerHeight", "6");
    marker.setAttribute("orient", "auto");
    const path = document.createElementNS(SVG_NS, "path");
    path.setAttribute("d", "M 0 0 L 10 5 L 0 10 z");
    path.setAttribute("fill", color);
    marker.appendChild(path);
    defs.appendChild(marker);
  }
  svg.appendChild(defs);

  // Edges.
  const edgesG = document.createElementNS(SVG_NS, "g");
  edgesG.setAttribute("id", "edges");
  viewport.appendChild(edgesG);

  for (const edge of trace.edges) {
    const a = positions.get(edge.source);
    const b = positions.get(edge.target);
    if (!a || !b) continue;
    const x1 = a.x + NODE_W;
    const y1 = a.y + NODE_H / 2;
    const x2 = b.x;
    const y2 = b.y + NODE_H / 2;
    const dx = Math.max(40, (x2 - x1) * 0.5);

    const path = document.createElementNS(SVG_NS, "path");
    path.setAttribute("class", `edge ${edge.relation}`);
    path.setAttribute("d", `M ${x1} ${y1} C ${x1 + dx} ${y1} ${x2 - dx} ${y2} ${x2} ${y2}`);
    path.setAttribute("marker-end", `url(#arrow-${edge.relation})`);
    edgesG.appendChild(path);

    if (edge.label) {
      const mx = (x1 + x2) / 2;
      const my = (y1 + y2) / 2 - 6;
      const lbl = document.createElementNS(SVG_NS, "text");
      lbl.setAttribute("x", mx);
      lbl.setAttribute("y", my);
      lbl.setAttribute("text-anchor", "middle");
      lbl.setAttribute("class", "edge-label");
      lbl.textContent = edge.label;
      edgesG.appendChild(lbl);
    }
  }

  // Nodes.
  const nodesG = document.createElementNS(SVG_NS, "g");
  nodesG.setAttribute("id", "nodes");
  viewport.appendChild(nodesG);

  for (const step of trace.steps) {
    const pos = positions.get(step.id);
    if (!pos) continue;
    const g = document.createElementNS(SVG_NS, "g");
    g.setAttribute("class", "node");
    g.setAttribute("transform", `translate(${pos.x}, ${pos.y})`);
    g.dataset.id = step.id;

    const rect = document.createElementNS(SVG_NS, "rect");
    rect.setAttribute("width", NODE_W);
    rect.setAttribute("height", NODE_H);
    rect.setAttribute("rx", 8);
    rect.setAttribute("ry", 8);
    rect.setAttribute("fill", STATUS_FILL[step.status] || "#1b242d");
    rect.setAttribute("stroke", KIND_COLORS[step.kind] || "#8b98a5");
    g.appendChild(rect);

    const kindLbl = document.createElementNS(SVG_NS, "text");
    kindLbl.setAttribute("x", 12);
    kindLbl.setAttribute("y", 16);
    kindLbl.setAttribute("class", "kind-label");
    const kindTxt = step.kind.replace("_", " ");
    const statusTxt = STATUS_LABEL[step.status] || step.status.toUpperCase();
    kindLbl.textContent = `${kindTxt}  ·  ${statusTxt}`;
    g.appendChild(kindLbl);

    const lbl = document.createElementNS(SVG_NS, "text");
    lbl.setAttribute("x", 12);
    lbl.setAttribute("y", 36);
    const label = truncate(step.label, 38);
    lbl.textContent = label;
    g.appendChild(lbl);

    if (step.confidence !== null && step.confidence !== undefined) {
      const conf = document.createElementNS(SVG_NS, "text");
      conf.setAttribute("x", 12);
      conf.setAttribute("y", 54);
      conf.setAttribute("class", "kind-label");
      conf.textContent = `confidence: ${(step.confidence * 100).toFixed(0)}%`;
      g.appendChild(conf);
    }

    g.addEventListener("click", (ev) => {
      ev.stopPropagation();
      selectStep(step.id);
    });
    nodesG.appendChild(g);
  }

  // Fit SVG viewBox to content.
  svg.setAttribute("viewBox", `0 0 ${Math.max(width, 400)} ${Math.max(height, 300)}`);
  svg.setAttribute("preserveAspectRatio", "xMidYMid meet");

  // Reset pan/zoom transform.
  state.view = { tx: 0, ty: 0, k: 1 };
  applyTransform();

  renderLegend();
}

function selectStep(id) {
  state.selectedStep = id;
  for (const g of document.querySelectorAll(".node")) {
    g.classList.toggle("selected", g.dataset.id === id);
  }
  const step = state.selectedTrace.steps.find((s) => s.id === id);
  renderDetails(step);
}

function renderDetails(step) {
  const body = document.getElementById("details-body");
  if (!step) {
    body.innerHTML = `<p class="muted">Click a node to inspect the reasoning step.</p>`;
    return;
  }
  const fields = [
    ["ID", `<code>${escapeHtml(step.id)}</code>`],
    ["Kind", `<span class="pill">${escapeHtml(step.kind)}</span>`],
    ["Status", `<span class="pill">${escapeHtml(step.status)}</span>`],
  ];
  if (step.confidence !== null && step.confidence !== undefined) {
    fields.push(["Confidence", `${(step.confidence * 100).toFixed(0)}%`]);
  }
  const label = `<div style="font-weight:600;margin-bottom:8px">${escapeHtml(step.label)}</div>`;
  const dl = `<dl>${fields.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join("")}</dl>`;
  const detail = step.detail ? `<div class="detail">${escapeHtml(step.detail)}</div>` : "";
  const sourceRef = step.source_ref ? `<div class="source-ref">↪ ${escapeHtml(step.source_ref)}</div>` : "";
  const meta = step.meta && Object.keys(step.meta).length
    ? `<div class="detail">${escapeHtml(JSON.stringify(step.meta, null, 2))}</div>` : "";
  body.innerHTML = label + dl + detail + sourceRef + meta;
}

// ----- Pan/zoom -----------------------------------------------------------

function applyTransform() {
  const vp = document.getElementById("viewport");
  if (!vp) return;
  const { tx, ty, k } = state.view;
  vp.setAttribute("transform", `translate(${tx}, ${ty}) scale(${k})`);
}

function initPanZoom() {
  const svg = document.getElementById("graph");

  svg.addEventListener("mousedown", (e) => {
    if (e.target.closest(".node")) return;
    state.dragging = { x: e.clientX, y: e.clientY, tx: state.view.tx, ty: state.view.ty };
  });
  window.addEventListener("mousemove", (e) => {
    if (!state.dragging) return;
    state.view.tx = state.dragging.tx + (e.clientX - state.dragging.x);
    state.view.ty = state.dragging.ty + (e.clientY - state.dragging.y);
    applyTransform();
  });
  window.addEventListener("mouseup", () => {
    state.dragging = null;
  });

  svg.addEventListener("wheel", (e) => {
    e.preventDefault();
    const factor = e.deltaY < 0 ? 1.1 : 0.9;
    const next = Math.max(0.25, Math.min(3, state.view.k * factor));
    state.view.k = next;
    applyTransform();
  }, { passive: false });

  svg.addEventListener("click", (e) => {
    if (e.target.closest(".node")) return;
    state.selectedStep = null;
    for (const g of document.querySelectorAll(".node.selected")) g.classList.remove("selected");
    renderDetails(null);
  });
}

// ----- Misc ---------------------------------------------------------------

function truncate(text, n) {
  if (!text) return "";
  return text.length > n ? text.slice(0, n - 1) + "…" : text;
}

function escapeHtml(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

// ----- Wire up ------------------------------------------------------------

document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("btn-load-samples").addEventListener("click", async () => {
    await api("/api/samples/load", { method: "POST" });
    await loadTraces();
  });
  document.getElementById("btn-refresh").addEventListener("click", loadTraces);
  document.getElementById("btn-clear").addEventListener("click", async () => {
    if (!confirm("Delete all traces?")) return;
    await api("/api/clear", { method: "POST" });
    state.selectedTrace = null;
    await loadTraces();
    clearCanvas();
  });
  document.getElementById("filter").addEventListener("input", renderTraceList);

  initPanZoom();
  renderLegend();
  loadTraces();
});
