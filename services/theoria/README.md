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
| **Kairos** | `trace` | OTEL span tree — service·operation per span, success → status, parent→child as YIELDS |
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
theoria
```

Open the URL. The first time you launch you'll see four built-in sample
traces that cover the main decision shapes. Click nodes to inspect
premises / rules / evidence; pan with drag, zoom with the mouse wheel.

## CLI

Run any subcommand with `python -m theoria <cmd> [args]` or, if installed,
`theoria <cmd> [args]`. Calling `theoria` with no subcommand (or with only
server flags like `--port`) runs the server.

| Command | Purpose |
|---------|---------|
| `theoria serve [--host --port --persist --no-samples]` | Run the HTTP server |
| `theoria post <file\|->` | POST a trace JSON file (or stdin) to a running server |
| `theoria export --id X [--format markdown\|mermaid\|dot\|json]` | Fetch + render one trace |
| `theoria list [--source --kind --verdict --tag --q --limit --format table\|ids\|json]` | Filtered trace list |
| `theoria diff <a_id> <b_id> [--format markdown\|mermaid\|json]` | Compare two traces |
| `theoria tail` | Subscribe to the `/api/stream` SSE feed and print events |
| `theoria sample [--index N]` | Print a built-in sample trace as JSON |

Remote commands honour `THEORIA_URL` (default `http://127.0.0.1:8765`) or
a per-call `--url`. Examples:

```bash
# Pipe a generated trace into a running server:
my-tool --emit-trace | theoria post -

# Find every Logos block and view it as Markdown:
theoria list --source logos --verdict block --format ids \
  | head -1 | xargs -I {} theoria export --id {} --format markdown

# Watch decisions stream by:
theoria tail
```

### Server options

| Flag | Env var | Default | Purpose |
|------|---------|---------|---------|
| `--host` | `THEORIA_HOST` | `127.0.0.1` | Bind host |
| `--port` | `THEORIA_PORT` | `8765` | Bind port |
| `--persist PATH` | `THEORIA_PERSIST` | *(off)* | Append each trace to a JSONL file, reload on start |
| `--no-samples` | — | off | Skip loading the built-in demo traces |
| `--log-level` | `THEORIA_LOG_LEVEL` | `INFO` | Python logging level |

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
| GET | `/api/traces` | List traces (most-recent first). Supports `?source=` `?kind=` `?verdict=` `?tag=` (repeatable) `?q=` `?since=` `?until=` `?limit=` |
| GET | `/api/traces/{id}` | Single trace |
| GET | `/api/traces/{id}/export?format=mermaid\|dot\|markdown` | Render as Mermaid / Graphviz DOT / reviewable Markdown |
| GET | `/api/traces/{a}/diff/{b}?format=json\|markdown\|mermaid` | Structural diff of two traces |
| GET | `/api/stats` | Aggregate counts (`?top_n=N` caps the lists) |
| GET | `/api/stream` | Server-Sent Events — pushes `trace_put` / `trace_delete` / `trace_clear` |
| POST | `/api/traces` | Ingest a trace (JSON body) |
| POST | `/api/traces/search` | Pattern query: step/edge predicates (JSON body) |
| DELETE | `/api/traces/{id}` | Remove a trace |
| POST | `/api/samples/load` | Load the built-in sample traces |
| POST | `/api/clear` | Clear all traces |

### Filtering

`GET /api/traces` accepts AND-combined filters; tag membership is OR:

```bash
# Every Logos block from the last day:
curl 'http://theoria:8765/api/traces?source=logos&verdict=block&since=2026-04-22T00:00:00Z'

# Anything tagged policy or plan, containing "auth" in title/question/labels, top 5:
curl 'http://theoria:8765/api/traces?tag=policy,plan&q=auth&limit=5'
```

Timestamps accept ISO-8601 with `Z` or `+00:00` offsets. Malformed dates are
silently ignored (the filter becomes no-op for that field).

### Pattern queries

For anything more expressive than the simple query-string filters,
`POST /api/traces/search` accepts step/edge predicates:

```bash
# Every trace where a rule_check step triggered with "destroy" in its label:
curl -X POST http://theoria:8765/api/traces/search \
  -H 'Content-Type: application/json' \
  -d '{
    "any_step": [
      {"kind": "rule_check", "status": "triggered", "label_contains": "destroy"}
    ]
  }'

# Every trace containing a contradicts edge + failed conclusion (AND across lists):
curl -X POST http://theoria:8765/api/traces/search \
  -H 'Content-Type: application/json' \
  -d '{
    "all_edges": [{"relation": "contradicts"}],
    "all_steps":  [{"kind": "conclusion", "status": "failed"}]
  }'
```

Predicate fields: ``id``, ``kind``, ``status``, ``label_contains``,
``detail_contains``, ``confidence_gte``, ``confidence_lte``
(steps); ``source``, ``target``, ``relation``, ``label_contains``
(edges). Unknown fields → HTTP 400 (typos don't silently match
everything).

### Trace diff

```bash
curl 'http://theoria:8765/api/traces/v1/diff/v2?format=markdown' > diff.md
curl 'http://theoria:8765/api/traces/v1/diff/v2?format=mermaid' > diff.mmd
curl 'http://theoria:8765/api/traces/v1/diff/v2?format=json'   | jq .
```

Returned fields: `added_steps`, `removed_steps`, `changed_steps`
(with per-field before/after), `added_edges`, `removed_edges`,
`outcome_change`, `unchanged_step_ids`. The Markdown rendering
includes a merged Mermaid graph that colour-codes added (green),
removed (red), and changed (amber) nodes.

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

The full preflight gates (matching the rest of the monorepo):

```bash
cd services/theoria
pip install -e ".[dev]"
python -m pytest -q                                          # 110 tests
python -m ruff check src/ tests/                             # lint
python -m mypy --strict src/                                 # type check
python -m pytest --cov=src/theoria --cov-fail-under=85       # coverage ≥ 85%
```

All four are currently green on this branch.

## Deploying on Railway

Matches the other Noesis services:

1. **New Service → GitHub repo → `ThisIsBad/noesis`**
2. **Settings → Build**
   - Root Directory: *(leave empty — repo root)*
   - Dockerfile Path: `services/theoria/Dockerfile`
3. **Settings → Variables** (all optional):
   ```
   THEORIA_PERSIST=/data/traces.jsonl       # durable trace storage
   PORT=8000
   ```
4. **Settings → Volumes** — mount `/data` if you set `THEORIA_PERSIST`.
5. Health endpoint: `/health`.

The Dockerfile runs `theoria serve --host 0.0.0.0 --port $PORT`.

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
- [x] Trace diff (compare two traces — added / removed / changed)
- [x] Filter/search API on `/api/traces`
- [x] CLI: `post`, `export`, `list`, `tail`, `diff`, `sample`
- [x] Pattern query API (`POST /api/traces/search`)
- [x] Native adapters for `noesis_schemas.{ProofCertificate, GoalContract, Plan}`
- [x] Railway deploy config (`Dockerfile`, `railway.toml`)
- [x] `ruff` / `mypy --strict` / `coverage ≥ 85%` preflight gates green
- [x] Kairos OpenTelemetry span ingestion adapter (`trace_from_trace_spans`)
- [x] Aggregate stats endpoint (`GET /api/stats`)
- [ ] MCP-over-HTTP wrapping for uniform Noesis deployment
