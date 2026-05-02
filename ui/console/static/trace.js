// Live DecisionTrace renderer.
//
// Consumes the same JSON shape Theoria does (theoria.models.DecisionTrace
// .to_dict()), renders it as a left-to-right SVG DAG. Re-rendered every
// time a `trace.update` SSE event arrives (cheap because traces are
// small in Phase 1 — typical session is <50 nodes).
//
// Phase-1 layout: simple BFS-by-depth columns, no fancy crossing
// minimisation. Good enough to show the structure; replace with
// Theoria's full layout when we promote this to its own component.
//
// Node shape:
//
//      ┌────────────────────┐
//      │ <kind> <label>     │   ← node-text.label
//      │ <truncated detail> │   ← node-text.detail
//      └────────────────────┘
//
// Click a node → its full step JSON drops into #trace-step-detail.

const SVG_NS = "http://www.w3.org/2000/svg";
const NODE_W = 220;
const NODE_H = 56;
const COL_GAP = 60;
const ROW_GAP = 22;
const PAD = 28;

const canvas = document.getElementById("trace-canvas");
const titleEl = document.getElementById("trace-title");
const outcomeEl = document.getElementById("trace-outcome");
const detailBody = document.getElementById("trace-step-detail-body");

let currentTrace = null;

window.addEventListener("noesis:trace", (ev) => {
  currentTrace = ev.detail.trace;
  renderTrace(currentTrace);
});

window.addEventListener("noesis:reset", () => {
  currentTrace = null;
  canvas.innerHTML = "";
  titleEl.textContent = "no session yet";
  outcomeEl.textContent = "";
  outcomeEl.className = "";
  detailBody.textContent = "click a node…";
});

function renderTrace(trace) {
  if (!trace || !trace.steps || trace.steps.length === 0) return;

  titleEl.textContent = trace.title || trace.id;
  if (trace.outcome) {
    outcomeEl.textContent = `→ ${trace.outcome.verdict}`;
    outcomeEl.className = trace.outcome.verdict || "";
  } else {
    outcomeEl.textContent = "(in flight)";
    outcomeEl.className = "";
  }

  const layered = layerByDepth(trace);
  const positions = positionNodes(layered);
  const width = (layered.length + 1) * (NODE_W + COL_GAP) + PAD * 2;
  const maxRows = Math.max(...layered.map((c) => c.length), 1);
  const height = maxRows * (NODE_H + ROW_GAP) + PAD * 2;

  canvas.setAttribute("viewBox", `0 0 ${width} ${height}`);
  canvas.setAttribute("width", width);
  canvas.setAttribute("height", height);
  canvas.innerHTML = "";

  // Arrowhead marker definition.
  const defs = document.createElementNS(SVG_NS, "defs");
  defs.innerHTML = `
    <marker id="arrowhead" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="6" markerHeight="6" orient="auto">
      <path d="M 0 0 L 10 5 L 0 10 Z" fill="#30363d" />
    </marker>`;
  canvas.appendChild(defs);

  // Edges first so they sit under nodes.
  for (const edge of trace.edges || []) {
    const sp = positions.get(edge.source);
    const tp = positions.get(edge.target);
    if (!sp || !tp) continue;
    const x1 = sp.x + NODE_W;
    const y1 = sp.y + NODE_H / 2;
    const x2 = tp.x;
    const y2 = tp.y + NODE_H / 2;
    const cx = (x1 + x2) / 2;
    const path = document.createElementNS(SVG_NS, "path");
    path.setAttribute(
      "d",
      `M ${x1} ${y1} C ${cx} ${y1}, ${cx} ${y2}, ${x2} ${y2}`
    );
    path.setAttribute("class", "edge-path");
    canvas.appendChild(path);
  }

  for (const step of trace.steps) {
    const p = positions.get(step.id);
    if (!p) continue;
    const g = document.createElementNS(SVG_NS, "g");
    g.setAttribute("transform", `translate(${p.x}, ${p.y})`);

    const rect = document.createElementNS(SVG_NS, "rect");
    rect.setAttribute("width", NODE_W);
    rect.setAttribute("height", NODE_H);
    rect.setAttribute("rx", 6);
    rect.setAttribute(
      "class",
      `node-rect kind-${step.kind || "info"} status-${step.status || "info"}`
    );
    rect.addEventListener("click", () => showDetail(step));
    g.appendChild(rect);

    const labelText = document.createElementNS(SVG_NS, "text");
    labelText.setAttribute("x", 8);
    labelText.setAttribute("y", 18);
    labelText.setAttribute("class", "node-text label");
    labelText.textContent = truncate(step.label || "(untitled)", 30);
    g.appendChild(labelText);

    const detailText = document.createElementNS(SVG_NS, "text");
    detailText.setAttribute("x", 8);
    detailText.setAttribute("y", 36);
    detailText.setAttribute("class", "node-text detail");
    detailText.textContent = truncate(
      step.detail || step.kind || "",
      32
    );
    g.appendChild(detailText);

    if (step.confidence != null) {
      const conf = document.createElementNS(SVG_NS, "text");
      conf.setAttribute("x", NODE_W - 8);
      conf.setAttribute("y", 18);
      conf.setAttribute("text-anchor", "end");
      conf.setAttribute("class", "node-text detail");
      conf.textContent = `c=${step.confidence.toFixed(2)}`;
      g.appendChild(conf);
    }

    canvas.appendChild(g);
  }
}

function showDetail(step) {
  detailBody.textContent = JSON.stringify(step, null, 2);
}

function layerByDepth(trace) {
  // BFS from root, assigning each node to the column of its first
  // discovery; gives a stable left-to-right rendering even as the
  // trace mutates.
  const stepById = new Map(trace.steps.map((s) => [s.id, s]));
  const children = new Map();
  for (const s of trace.steps) children.set(s.id, []);
  for (const e of trace.edges || []) {
    if (children.has(e.source)) children.get(e.source).push(e.target);
  }
  const depth = new Map();
  depth.set(trace.root, 0);
  const queue = [trace.root];
  while (queue.length) {
    const id = queue.shift();
    const d = depth.get(id);
    for (const ch of children.get(id) || []) {
      if (!depth.has(ch)) {
        depth.set(ch, d + 1);
        queue.push(ch);
      }
    }
  }
  // Any orphan steps (e.g. system errors not yet linked) → final column.
  let maxDepth = 0;
  for (const v of depth.values()) if (v > maxDepth) maxDepth = v;
  for (const s of trace.steps) {
    if (!depth.has(s.id)) depth.set(s.id, maxDepth + 1);
  }

  const finalMaxDepth = Math.max(...depth.values(), 0);
  const columns = Array.from({ length: finalMaxDepth + 1 }, () => []);
  for (const s of trace.steps) {
    columns[depth.get(s.id)].push(s);
  }
  return columns;
}

function positionNodes(columns) {
  const positions = new Map();
  for (let col = 0; col < columns.length; col++) {
    const colSteps = columns[col];
    for (let row = 0; row < colSteps.length; row++) {
      positions.set(colSteps[row].id, {
        x: PAD + col * (NODE_W + COL_GAP),
        y: PAD + row * (NODE_H + ROW_GAP),
      });
    }
  }
  return positions;
}

function truncate(text, max) {
  if (!text) return "";
  return text.length > max ? text.slice(0, max - 1) + "…" : text;
}
