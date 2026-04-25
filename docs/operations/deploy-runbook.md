# Deploy runbook — Railway, all services

Click-by-click for taking the six MVP services from "code is green
in CI" to "live on Railway, registered in `.mcp.json`, exercisable
by Claude as orchestrator." Targets the Monday session where the
operator is in front of a real machine; anything that requires
human Railway-UI clicks lives here, anything codeable lives in the
companion PRs.

> **Pre-flight:** PR `claude/weekend-testability` is merged. That
> PR ships the docker-compose stack, the Logos+Mneme middleware
> migration, the eval harness's eight-service surface, and the
> first Kairos `Dockerfile` + `railway.toml`. Without those, the
> deploy lanes below are missing their target images.

## Phase 0 — current Railway state (2026-04-25)

| Service | Deployed? | Public URL | `<SVC>_SECRET` set? |
|---------|-----------|------------|----------------------|
| logos    | ✅ yes |   …    |   ✅   |
| mneme    | ✅ yes | `mneme-production-c227.up.railway.app` |   ✅   |
| praxis   | ❌ no  |   —    |   —    |
| telos    | ❌ no  |   —    |   —    |
| episteme | ❌ no  |   —    |   —    |
| kosmos   | ❌ no  |   —    |   —    |
| empiria  | ❌ no  |   —    |   —    |
| techne   | ❌ no  |   —    |   —    |
| kairos   | ❌ no (no Dockerfile previously) | — | — |

**Goal of this runbook:** flip the six `❌`s to `✅`, plus get
Kairos deployed for cross-service tracing, plus update `.mcp.json`
so Claude sees the whole loop.

## Phase 1 — generate the secrets (one-time, ~5 min)

In a scratch terminal:

```bash
for svc in praxis telos episteme kosmos empiria techne kairos; do
  printf '%s_SECRET=%s\n' "${svc^^}" "$(openssl rand -hex 32)"
done > /tmp/noesis-secrets.txt
```

Treat `/tmp/noesis-secrets.txt` like a vault: paste it into your
password manager and **delete the file** when this runbook is done.
You'll need each value twice (once on the Railway service, once in
`eval/.env.e2e`).

## Phase 2 — create one Railway service per repo service (~2 min each)

For each of `praxis`, `telos`, `episteme`, `kosmos`, `empiria`,
`techne`, `kairos`:

1. **New Service → GitHub repo → `ThisIsBad/noesis`**.
2. **Settings → Build:**
   - Root Directory: *(empty — repo root)*
   - Dockerfile Path: `services/<svc>/Dockerfile` (or `kairos/Dockerfile`).
3. **Settings → Variables:** paste the matching line from
   `/tmp/noesis-secrets.txt`. For services with persistence
   (`praxis`, `techne`, `mneme`), also set:
   - `<SVC>_DATA_DIR=/data`
4. **Settings → Volumes:** for `praxis` / `techne` / `mneme`, mount
   `/data` (1 GB is plenty for MVP). Stateless services
   (`logos` / `telos` / `episteme` / `kosmos` / `empiria` /
   `kairos`) don't need a volume.
5. **Networking → Generate Domain.** Copy the public URL.

## Phase 3 — wire the inter-service URLs (~3 min)

A few services call others as sidecars. After Phase 2 you have all
the URLs; set them on the relevant services:

| Service | Variable to add | Value |
|---------|------------------|-------|
| praxis | `LOGOS_URL`     | `https://<logos-url>` |
| praxis | `LOGOS_SECRET`  | (same value as Logos's `LOGOS_SECRET`) |
| mneme  | `LOGOS_URL`     | `https://<logos-url>` |
| mneme  | `LOGOS_SECRET`  | (same value as Logos's `LOGOS_SECRET`) |
| *(every service)* | `KAIROS_URL` | `https://<kairos-url>` |

Each Railway service auto-redeploys on variable change; wait for
the new deploy to go green before moving on.

## Phase 4 — sanity probes (~2 min)

```bash
for url in \
  https://<logos>.up.railway.app/health \
  https://<mneme>.up.railway.app/health \
  https://<praxis>.up.railway.app/health \
  https://<telos>.up.railway.app/health \
  https://<episteme>.up.railway.app/health \
  https://<kosmos>.up.railway.app/health \
  https://<empiria>.up.railway.app/health \
  https://<techne>.up.railway.app/health \
  https://<kairos>.up.railway.app/health
do
  printf '%s ' "$url"
  curl -s -o /dev/null -w '%{http_code}\n' "$url"
done
```

Every line should print `200`. Any `502` / `404` / `500` →
`docker compose logs <service>` analog: Railway UI → service →
"Logs" tab.

Then probe the bearer-token gate works:

```bash
# Should 401:
curl -s -o /dev/null -w '%{http_code}\n' https://<praxis>.up.railway.app/sse
# Should 200 (or whatever SSE looks like):
curl -s -o /dev/null -w '%{http_code}\n' \
  -H "Authorization: Bearer $PRAXIS_SECRET" \
  https://<praxis>.up.railway.app/sse
```

## Phase 5 — register MCP servers (~2 min)

Update `.mcp.json` at the repo root. The current file has only
Mneme; add the other seven (Theoria + Kairos are not in `.mcp.json`
because they're not MCP services — Theoria is a UI client, Kairos
is a tracing sink).

```json
{
  "mcpServers": {
    "logos":    { "type": "http", "url": "https://<logos>.up.railway.app/mcp" },
    "mneme":    { "type": "http", "url": "https://<mneme>.up.railway.app/mcp" },
    "praxis":   { "type": "http", "url": "https://<praxis>.up.railway.app/mcp" },
    "telos":    { "type": "http", "url": "https://<telos>.up.railway.app/mcp" },
    "episteme": { "type": "http", "url": "https://<episteme>.up.railway.app/mcp" },
    "kosmos":   { "type": "http", "url": "https://<kosmos>.up.railway.app/mcp" },
    "empiria":  { "type": "http", "url": "https://<empiria>.up.railway.app/mcp" },
    "techne":   { "type": "http", "url": "https://<techne>.up.railway.app/mcp" }
  }
}
```

Commit + push. A fresh Claude Code session will then load all eight
services as MCP tools.

> Note: each Claude Code session needs the corresponding bearer
> token in its session config (`~/.claude/settings.json`'s
> `mcpServers.<svc>.headers.Authorization: Bearer <token>`). The
> repo-root `.mcp.json` is the project-level allow-list; per-machine
> tokens stay local.

## Phase 6 — populate `eval/.env.e2e` (~3 min)

Open `eval/env-template.md`, copy the **Option B — Railway deploys**
block into a new file `eval/.env.e2e` (the file is gitignored — that
is intentional, see `docs/operations/secrets.md`), and paste in the
URLs and secrets you generated in Phase 1.

Verify the harness can talk to the live stack:

```bash
cd eval/
python -m pytest tests/test_phase1_e2e.py -q   # if it exists
# … or one of the integration tests marked `-m integration`
python -m pytest -m integration -q
```

## Phase 7 — run the canonical A/B (~10 min)

```bash
cd eval/
./run_ab.sh   # or however AB_RUNBOOK.md says to invoke
```

The harness now has all eight services in its treatment surface and
can compare against the no-tools baseline.

## Phase 8 — clean up

```bash
shred -u /tmp/noesis-secrets.txt   # don't leave the secrets file behind
```

If anything misbehaved, capture which service / phase and roll the
bearer token (see `docs/operations/secrets.md` §rotation).

## What's NOT in this runbook

* **Branch protection / required CI checks on Railway-tracked
  branches.** Out of scope; Railway redeploys on every push to
  master regardless. If you want gating, that's GitHub Actions, not
  Railway.
* **Cost monitoring.** Six new always-on services on Railway will
  consume free-tier credit; for serious eval runs, consider
  scaling-to-zero between sessions or moving the eval-side stack to
  the local docker-compose path documented in
  [`local-stack.md`](local-stack.md).
* **Persistence beyond what each service writes.** Mneme + Praxis +
  Techne use SQLite + ChromaDB on a Railway volume; Logos / Telos /
  Episteme / Kosmos / Empiria / Kairos are all stateless. The
  Postgres/pgvector consolidation lives in `T3.5` of the architect
  review and is deliberately deferred.
