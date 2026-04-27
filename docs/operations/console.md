# Console — interactive chat surface for the full Noesis stack

`services/console/` is the third orchestration surface, alongside
direct Claude Code (developer dev loop) and `eval/` (batch A/B
benchmark). It's a Starlette app that:

1. accepts a chat prompt over `POST /api/chat`,
2. spawns a Claude session with all eight Noesis MCP servers wired,
3. streams the SDK's intermediate messages back over SSE
   (`GET /api/stream?session_id=...`) as typed events,
4. accumulates the tool-call graph into a
   `theoria.models.DecisionTrace` as it grows,
5. POSTs the finalised trace to Theoria's `/api/traces` so it shows
   up alongside every other trace in the visualizer.

The frontend (`ui/console/`) is a vanilla-JS three-pane chat shell
(chat history | live trace SVG | service-health strip), zero build
step. Browser hits `http://localhost:8010/`, types a prompt, watches
the trace build node-by-node as Claude calls Logos / Mneme / Praxis /
Telos / Episteme / Kosmos / Empiria / Techne in whatever sequence it
chooses.

## Required env vars

| Var | Required | Default | Purpose |
|---|:-:|---|---|
| `CONSOLE_SECRET` | recommended | unset = open mode | bearer token gating `/api/chat` and `/api/stream`. `/health`, `/`, `/index.html`, `/static/*` always exempt so a browser can fetch the chat shell pre-auth. |
| `CONSOLE_SECRET_PREV` | no | unset | grace-period token during rotation (same model as every other Noesis service). |
| `ANTHROPIC_API_KEY` | yes | — | the `claude-agent-sdk` spawns the `claude` CLI subprocess, which authenticates via this key (or any other `claude` auth method on the host). |
| `NOESIS_<SVC>_URL` × 8 | partial | unset → service skipped | per-service base URL. Console silently drops services whose URL is unset, so a partial deploy yields a working Console with fewer tools. |
| `NOESIS_<SVC>_SECRET` × 8 | partial | empty | per-service bearer for the sidecar MCP connections. |
| `THEORIA_URL` | recommended | unset = don't post finals | where to POST the finalised `DecisionTrace`; usually the same Theoria instance the dev uses to browse history. |
| `THEORIA_SECRET` | recommended | unset | Theoria's bearer token (needed when `THEORIA_SECRET` is set on Theoria). |
| `CONSOLE_MODEL` | no | `claude-sonnet-4-6` | `claude-haiku-4-5-20251001` for cheap dev runs. |
| `CONSOLE_MAX_TURNS` | no | `12` | per-session ceiling on Claude turns. |
| `CONSOLE_MAX_BUDGET_USD` | no | `0.25` | per-session hard cost cap; the SDK aborts when crossed. |
| `CONSOLE_SESSION_MAX_AGE_S` | no | `3600` | how long an idle session lives before the sweeper kills it. |
| `CONSOLE_LOG_LEVEL` | no | `INFO` | stdlib logging level. |
| `CONSOLE_UI_DIR` | no | autodetected (`/app/ui/console` in container, `<repo>/ui/console` locally) | override the chat-shell root if you want to ship the Console-server without UI assets, or to point at a forked UI. |

## Local boot — bare-metal (no docker)

```bash
# Repo root
PYTHONPATH=schemas/src:kairos/src:clients/src:ui/theoria/src:services/console/src \
ANTHROPIC_API_KEY=<your-key> \
CONSOLE_SECRET=dev-console-secret \
NOESIS_LOGOS_URL=http://localhost:8001    NOESIS_LOGOS_SECRET=dev-logos-secret \
NOESIS_MNEME_URL=http://localhost:8002    NOESIS_MNEME_SECRET=dev-mneme-secret \
NOESIS_PRAXIS_URL=http://localhost:8003   NOESIS_PRAXIS_SECRET=dev-praxis-secret \
NOESIS_TELOS_URL=http://localhost:8004    NOESIS_TELOS_SECRET=dev-telos-secret \
NOESIS_EPISTEME_URL=http://localhost:8005 NOESIS_EPISTEME_SECRET=dev-episteme-secret \
NOESIS_KOSMOS_URL=http://localhost:8006   NOESIS_KOSMOS_SECRET=dev-kosmos-secret \
NOESIS_EMPIRIA_URL=http://localhost:8007  NOESIS_EMPIRIA_SECRET=dev-empiria-secret \
NOESIS_TECHNE_URL=http://localhost:8008   NOESIS_TECHNE_SECRET=dev-techne-secret \
THEORIA_URL=http://localhost:8765         THEORIA_SECRET=dev-theoria-secret \
PORT=8010 \
python -m console.mcp_server_http
```

Then `open http://localhost:8010/`.

## Local boot — docker-compose (once PR #84 lands)

When the `docker-compose.yml` from PR #84 is on master, append this
service block (don't forget the `depends_on` + the `noesis-net`
membership):

```yaml
  # ── Console: chat-driven orchestration + live decision-DAG visualization ──
  console:
    <<: *service-base
    container_name: noesis-console
    build:
      context: .
      dockerfile: services/console/Dockerfile
    ports: ["8010:8000"]
    environment:
      PORT: "8000"
      CONSOLE_SECRET: dev-console-secret
      ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY:?required for Claude}
      NOESIS_LOGOS_URL:    http://logos:8000
      NOESIS_LOGOS_SECRET: dev-logos-secret
      NOESIS_MNEME_URL:    http://mneme:8000
      NOESIS_MNEME_SECRET: dev-mneme-secret
      NOESIS_PRAXIS_URL:   http://praxis:8000
      NOESIS_PRAXIS_SECRET: dev-praxis-secret
      NOESIS_TELOS_URL:    http://telos:8000
      NOESIS_TELOS_SECRET: dev-telos-secret
      NOESIS_EPISTEME_URL:    http://episteme:8000
      NOESIS_EPISTEME_SECRET: dev-episteme-secret
      NOESIS_KOSMOS_URL:    http://kosmos:8000
      NOESIS_KOSMOS_SECRET: dev-kosmos-secret
      NOESIS_EMPIRIA_URL:    http://empiria:8000
      NOESIS_EMPIRIA_SECRET: dev-empiria-secret
      NOESIS_TECHNE_URL:    http://techne:8000
      NOESIS_TECHNE_SECRET: dev-techne-secret
      THEORIA_URL:    http://theoria:8000
      THEORIA_SECRET: ""
    depends_on:
      logos: { condition: service_healthy }
```

Note `ANTHROPIC_API_KEY` is taken from the host environment so the
key never touches `docker-compose.yml`. Set it in your shell before
running `docker compose up`:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
docker compose up -d --build
```

## Railway deploy

Same shape as every other Noesis service — `services/console/railway.toml`
declares the build + healthcheck, and the env-var checklist above is
the variables tab. **Two extra Railway-only steps** beyond the
existing 8-service deploy runbook:

1. Set `ANTHROPIC_API_KEY` as a Railway variable (once; it's a billing
   secret so do not commit it to any `.env.example`).
2. Set the eight `NOESIS_<SVC>_URL` variables to the **public** Railway
   URLs of each service (not internal `http://logos:8000` because
   Railway services don't share a docker network — they reach each
   other through the public edge).

After deploy, append Console to `.mcp.json` only if you want the
chat surface itself to be addressable as an MCP server from another
Claude Code session (uncommon — Console is the orchestrator, not a
tool). For Phase 1 it stays out of `.mcp.json`.

## Where Console fits

```
                  ┌────────────────────────────────────────┐
                  │  Three orchestration surfaces          │
                  │  (all read the same .mcp.json envelope)│
                  ├────────────────────────────────────────┤
                  │                                        │
   developer ──→  │  Claude Code + .mcp.json (fast loop)   │
                  │                                        │
   demoer    ──→  │  Console     (interactive, recorded,   │
                  │              shareable; this PR)       │
                  │                                        │
   regression ─→  │  eval/       (batch A/B, CI-gated,     │
                  │              cost-capped)              │
                  │                                        │
                  └────────────────────────────────────────┘
                                   │
                                   ▼
                  the same eight MCP services + Kairos + Theoria
```

Console is **additive**, not a replacement. Both other surfaces stay
the right tool for their respective jobs. See `docs/architect-review-2026-04-23.md`
§"Where Console sits" for the longer rationale.

## Phase-1 limitations (known + intentional)

* **No HITL approval gate.** Claude runs to completion; the user
  watches. Add `?approve_state_changes=1` on the chat endpoint when
  this becomes a real demo concern.
* **No replay.** Saved `DecisionTrace`s land in Theoria, but Console
  doesn't yet support "load this trace, replay against current
  Logos." Phase 4 of the plan.
* **No A/B compare.** Theoria already has the `/api/traces/{a}/diff/{b}`
  endpoint; Console will surface it as a UI page in Phase 2.
* **No Z3-counterexample sidebar.** When Logos refutes a claim,
  the trace pane shows it as a red node — but the structured
  counterexample (input values → invariant) isn't pretty-printed
  inline yet. Phase 3.
* **EventSource limitation.** Browsers don't allow custom headers on
  `EventSource`; Console's `/api/stream` therefore relies on
  same-origin (chat shell + stream both served by Console) for
  bearer auth. When Console is deployed to a different origin than
  the chat client, switch to `fetch` + `ReadableStream` (5-line
  change in `ui/console/static/chat.js`).

## Cost discipline

`CONSOLE_MAX_BUDGET_USD` (default $0.25 per session) is an SDK-level
cap; the Claude CLI aborts a single `act` when crossed. Override with
`{"prompt": "...", "max_budget_usd": 0.10}` in the POST body for cheap
demo runs. There's no separate per-day cap — pair with whatever
Anthropic-account billing controls you have.

## Health probes

* `GET /health` on Console returns `{status, service, active_sessions, mcp_servers}`.
  `mcp_servers` is the list of MCP services Console managed to wire at
  boot — empty list = no `NOESIS_<SVC>_URL` was set.
* `tools/probe_live_stack.py` (PR #85) recognises Console once it's in
  `.mcp.json`; until then, `curl http://localhost:8010/health` is enough.
