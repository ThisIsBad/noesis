# Local-stack scripts

Bare-metal alternatives to `docker compose up` (the compose-based path
lands once PR #84 merges). Both PowerShell and bash variants here so
the same scripts work on Windows-native, WSL, Linux, and macOS.

```
scripts/
├── run-stack.ps1     # Windows-native: boots 8 services + Kairos
├── run-stack.sh      # bash equivalent
├── run-hegemonikon.ps1   # boots Hegemonikon on :8010, prompts for ANTHROPIC_API_KEY
├── run-hegemonikon.sh    # bash equivalent
├── probe-stack.ps1   # /health checks per service
├── probe-stack.sh    # bash equivalent
└── stop-stack.{ps1,sh}
```

State lives in `<repo>/.run/`:
* `<repo>/.run/<svc>.pid` — one per running service
* `<repo>/.run/logs/<svc>.log` — combined stdout+stderr
* `<repo>/.run/data/{mneme,praxis,techne,empiria}/` — SQLite + Chroma volumes

## Windows quickstart (PowerShell)

```powershell
# Repo root
.\scripts\run-stack.ps1
.\scripts\probe-stack.ps1                 # all green?

# In a new window:
$env:ANTHROPIC_API_KEY = 'sk-ant-...'
.\scripts\run-hegemonikon.ps1                 # foreground; Ctrl+C to stop

# Back in the first window when you're done:
.\scripts\stop-stack.ps1
```

Open <http://127.0.0.1:8010/>, paste `dev-hegemonikon-secret` in the Bearer
field, send a prompt.

## Linux / WSL / macOS quickstart

```bash
chmod +x scripts/*.sh
scripts/run-stack.sh
scripts/probe-stack.sh

# new shell
ANTHROPIC_API_KEY='sk-ant-...' scripts/run-hegemonikon.sh

# done
scripts/stop-stack.sh
```

## Troubleshooting

* **`ModuleNotFoundError: No module named 'X'`** — service deps aren't
  installed in the active Python. Cheapest fix:
  `pip install -e schemas/ kairos/ clients/ services/<svc>/`
  before re-running. Most services share `chromadb` / `mcp` /
  `starlette` / `uvicorn`; `pip install`-ing one usually pulls in the
  rest.
* **Port already in use** — another instance is still running. Check
  `.run/<svc>.pid` and `Get-Process -Id <pid>` (or `ps -p <pid>`).
* **chromadb fails to install on Windows** — Mneme + Techne + Empiria
  need it for ChromaDB persistence. If the wheel build fails, easiest
  fix is `pip install chromadb --only-binary=:all:`. Or skip those
  three services for the first chat-only smoke and accept the missing
  tools in the trace.
* **Hegemonikon boots but `mcp_servers: []`** — none of the
  `NOESIS_<SVC>_URL` env vars resolved at boot. Confirm
  `scripts/probe-stack.{ps1,sh}` shows the services as `200` first.
* **Browser shows the chat shell but `Send` does nothing** — open
  DevTools → Network tab. If `POST /api/chat` returns 401, the
  Bearer field doesn't match `HEGEMONIKON_SECRET`. If it returns 202 but
  `GET /api/stream` never delivers events, the SDK couldn't reach
  Anthropic — check `.run/logs/hegemonikon.log` for the actual error.

## Why bare-metal scripts at all when we have docker-compose?

Three reasons:

1. **Faster iteration.** `python -m hegemonikon.mcp_server_http` boots in
   under a second; `docker compose up --build hegemonikon` is 30 s+ on a
   fresh layer. For dev loops where you're tweaking trace_builder
   message-handlers, the speed difference matters.
2. **Native debugger.** PyCharm/VS Code attach to a `python` process
   directly; attaching to a docker-compose service requires extra
   `debugpy` plumbing.
3. **Windows-without-Docker.** Some Windows hosts (corporate laptops,
   restricted setups) can't run Docker Desktop but do have Python.

The compose path stays the canonical local stack for full-fidelity
runs and CI; these scripts are the dev-loop fallback.
