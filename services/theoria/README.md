# Theoria — Decision Logic Visualizer

> θεωρία — _"contemplation, viewing"_. The visual observatory for Noesis decisions.

Theoria ingests **decision traces** from any service in the Noesis ecosystem
and renders them as an interactive reasoning DAG in your browser. It
gives human operators a single place to see _why_ an agent / service
made a particular call — what premises it considered, which rules
fired, which alternatives it pruned, and how it reached its verdict.

![](docs/screenshot.png) <!-- optional; add later -->

## What it visualizes

| Source service | Decision kind | What you see |
|----------------|---------------|--------------|
| **Logos** | `policy` | Action observations → triggered rule checks → verdict (`ALLOW` / `REVIEW_REQUIRED` / `BLOCK`) |
| **Logos** | `proof` | Z3 assertions → `check()` → theorem holds / refuted |
| **Praxis** | `plan` | Subgoals → beam branches → pruned alternatives → selected plan |
| **Telos** | `goal` | Goal anchor → observed actions → similarity + postcondition checks → drift verdict |
| **Any** | `custom` | Nested reasoning tree via `trace_from_tree()` |

## Running the server

Theoria is **zero-dependency**. No `pip install` needed to try it.

```bash
cd services/theoria
PYTHONPATH=src python -m theoria
# → http://127.0.0.1:8765
```

Or install it properly (also no runtime deps):

```bash
pip install -e services/theoria
theoria --host 0.0.0.0 --port 8765
```

Options:

| Flag | Env var | Default | Purpose |
|------|---------|---------|---------|
| `--host` | `THEORIA_HOST` | `127.0.0.1` | Bind host |
| `--port` | `THEORIA_PORT` | `8765` | Bind port |
| `--persist PATH` | `THEORIA_PERSIST` | *(off)* | Append each trace to a JSONL file, reload on start |
| `--no-samples` | — | off | Skip loading the built-in demo traces |
| `--log-level` | `THEORIA_LOG_LEVEL` | `INFO` | Python logging level |

Open the URL. The first time you launch you'll see four built-in sample
traces that cover the main decision shapes. Click nodes to inspect
premises / rules / evidence; pan with drag, zoom with the mouse wheel.

## Emitting a trace from another service

### Option A — already have a Logos `ActionPolicyResult`?

```python
from theoria.ingest import trace_from_logos_policy
from theoria.models import DecisionTrace
import json, urllib.request

result = engine.evaluate(action)   # logos ActionPolicyEngine
trace = trace_from_logos_policy(result, action=action, question="Delete /data?")

urllib.request.urlopen(urllib.request.Request(
    "http://theoria:8765/api/traces",
    data=json.dumps(trace.to_dict()).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST",
))
```

### Option B — build a tree from scratch

```python
from theoria.ingest import trace_from_tree
from theoria.models import Outcome

trace = trace_from_tree(
    trace_id="deploy-check-2026-04-23",
    title="Deploy-window check",
    question="Is a Friday-afternoon deploy acceptable?",
    source="ci",
    kind="policy",
    tree={
        "id": "q", "kind": "question", "label": "Deploy now?",
        "children": [
            {"id": "ci",   "kind": "observation", "label": "CI green",        "status": "ok"},
            {"id": "time", "kind": "constraint",  "label": "Friday 16:30",    "status": "triggered"},
            {"id": "d",    "kind": "conclusion",  "label": "Block until Mon", "status": "failed",
             "relation": "yields"},
        ],
    },
    outcome=Outcome(verdict="block", summary="Freeze window violated."),
)
```

### Option C — POST raw JSON

Theoria also accepts plain JSON via `POST /api/traces`. See the schema
section below.

See [`examples/post_trace.py`](examples/post_trace.py) for a complete
runnable example.

## HTTP API

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/` | Web UI (single page) |
| GET | `/health` | Liveness + trace count |
| GET | `/api/traces` | List all traces (most-recent first) |
| GET | `/api/traces/{id}` | Single trace |
| GET | `/api/traces/{id}/export?format=mermaid\|dot\|markdown` | Render as Mermaid / Graphviz DOT / reviewable Markdown |
| GET | `/api/stream` | Server-Sent Events — pushes `trace_put` / `trace_delete` / `trace_clear` |
| POST | `/api/traces` | Ingest a trace (JSON body) |
| DELETE | `/api/traces/{id}` | Remove a trace |
| POST | `/api/samples/load` | Load the built-in sample traces |
| POST | `/api/clear` | Clear all traces |

### Live streaming

The UI subscribes to `/api/stream` on load; any POST of a new trace
from any client updates every connected browser in place. To consume
it from your own tooling:

```python
import json, urllib.request
with urllib.request.urlopen("http://theoria:8765/api/stream") as resp:
    for raw in resp:
        line = raw.decode().rstrip()
        if line.startswith("data:"):
            event = json.loads(line[len("data:"):].strip())
            print(event["type"], event.get("id"))
```

### Exporting a trace

```bash
curl 'http://theoria:8765/api/traces/my-trace/export?format=mermaid'  > trace.mmd
curl 'http://theoria:8765/api/traces/my-trace/export?format=dot'      > trace.dot
curl 'http://theoria:8765/api/traces/my-trace/export?format=markdown' > trace.md
```

Or programmatically:

```python
from theoria.export import to_mermaid, to_graphviz, to_markdown
print(to_mermaid(trace))
print(to_graphviz(trace))
print(to_markdown(trace))   # embeds a ```mermaid``` block by default
```

The Markdown exporter produces a reviewable narrative: a metadata
table, the question as a blockquote, an embedded Mermaid diagram
(GitHub/GitLab render it inline), then one section per reasoning step
in topological order with incoming-edge provenance. Paste the output
straight into a PR description or issue comment — no server needed
at the reading end.

## Decision-trace schema

A decision trace is a DAG of reasoning steps plus a verdict:

```jsonc
{
  "id": "logos-policy-7a8c",
  "title": "Logos blocks unauthorized destruction",
  "question": "May the agent delete /data/user-uploads?",
  "source": "logos",
  "kind": "policy",
  "root": "q",
  "steps": [
    { "id": "q", "kind": "question", "label": "May the agent delete /data?",
      "status": "info" },
    { "id": "f1", "kind": "observation", "label": "destructive=true",
      "status": "ok" },
    { "id": "r1", "kind": "rule_check",
      "label": "Rule: no_unauthorized_destruction",
      "status": "failed", "detail": "severity=error" },
    { "id": "c", "kind": "conclusion", "label": "Decision: BLOCK",
      "status": "failed", "confidence": 1.0 }
  ],
  "edges": [
    { "source": "q",  "target": "f1", "relation": "considers" },
    { "source": "f1", "target": "r1", "relation": "supports" },
    { "source": "r1", "target": "c",  "relation": "implies"  }
  ],
  "outcome": { "verdict": "block", "summary": "Unauthorized destructive action",
               "confidence": 1.0 },
  "tags": ["logos", "policy", "block"]
}
```

**`StepKind`**: `question` · `premise` · `observation` · `rule_check` · `constraint`
· `inference` · `evidence` · `alternative` · `counterfactual` · `conclusion` · `note`

**`StepStatus`**: `ok` · `triggered` · `failed` · `rejected` · `pending` · `unknown` · `info`

**`EdgeRelation`**: `supports` · `contradicts` · `implies` · `requires` ·
`considers` · `prunes` · `yields` · `witness`

## Development

```bash
cd services/theoria
pip install -e ".[dev]"
python -m pytest -q
python -m ruff check src/ tests/
python -m mypy --strict src/
```

## Design notes

- **Zero runtime dependencies** — stdlib only (`http.server`, `json`,
  `dataclasses`). Keeps Theoria runnable from a clean checkout.
- **Service-agnostic schema** — traces from Logos / Praxis / Telos /
  Kosmos / ad-hoc code all share one visualization surface.
- **Duck-typed adapters** — `ingest.trace_from_logos_policy` reads
  `ActionPolicyResult`-shaped objects without importing Logos, so the
  services stay decoupled at module-load time.
- **DAG, not just tree** — decisions often involve the same evidence
  feeding multiple rules or alternatives converging on one conclusion.
- **In-memory first, persistence opt-in** — a JSONL path is all the
  persistence this service needs; Mneme is the right home for durable
  storage once it ships.

## Roadmap

- [x] Live streaming via Server-Sent Events (new trace → push to all
  connected UIs)
- [x] Praxis beam-search state adapter
- [x] Telos alignment / drift adapter
- [x] Exporter: decision trace → Mermaid / Graphviz DOT / Markdown
- [ ] Kairos OpenTelemetry span ingestion adapter
- [ ] MCP-over-HTTP wrapping for uniform Noesis deployment
- [ ] Trace diff (compare two traces side-by-side)
