# Railway deploy checklist

Per-service settings that must be configured in the Railway dashboard.
None of this is in `railway.toml` because Railway's config-as-code surface
is partial — the items below live in the dashboard only.

Run through this list once per service when onboarding, and again after
any major reconfiguration. The 8 cognitive services are: `logos`, `mneme`,
`praxis`, `telos`, `episteme`, `kosmos`, `empiria`, `techne`. Plus
`hegemonikon` (orchestration UI) and `theoria` (browse UI).

## Per-service checklist

### Source

| Field | Required value |
|---|---|
| Repository | `ThisIsBad/noesis` |
| Branch | `master` |
| Auto Deploys on push | enabled |
| Pinned/Locked Deployment | **none** |

A pinned deployment will silently keep the service on a stale SHA even
after pushes to master. We hit this once with `empiria`: the only fix
was to push an empty commit to master to force a fresh source pull.

### Build

| Field | Required value |
|---|---|
| Builder | `Dockerfile` |
| Dockerfile Path | `services/<svc>/Dockerfile` (or `ui/<svc>/Dockerfile`) |
| Watch Paths | leave empty for now |

### Config-as-code File Path

| Field | Required value |
|---|---|
| Railway Config File | `services/<svc>/railway.toml` |

Without this, the committed `railway.toml` (which sets `startCommand`,
`healthcheckPath`, `restartPolicy`) is **ignored** and you're depending
on dashboard defaults. Setting it makes the repo-side toml authoritative.

### Networking

| Field | Required value |
|---|---|
| Public Domain | `noesis-<svc>.up.railway.app` |
| Target Port | `8080` |

All Dockerfiles `EXPOSE 8080` and the services read `PORT` from the
environment (default 8000 if unset, but Railway sets it to the target
port).

### Volumes

| Service | Volume needed | Mount path |
|---|---|---|
| `mneme` | yes (SQLite + ChromaDB) | `/data` |
| `praxis` | yes (SQLite) | `/data` |
| `techne` | yes (SQLite + ChromaDB) | `/data` |
| `logos` | no | — |
| `telos` | no (in-memory, by Phase-1 design) | — |
| `episteme` | no | — |
| `kosmos` | no | — |
| `empiria` | no (chromadb declared but not yet wired) | — |
| `hegemonikon` | no | — |
| `theoria` | yes (snapshot store) | `/data` |

5 GB is a sane starting size. SQLite + ChromaDB embeddings stay
small for normal workloads.

### Environment variables

Every service needs:

| Var | Notes |
|---|---|
| `<SVC>_SECRET` | 32-hex bearer token. Same value the eval/integration suite injects. |
| `<SVC>_ALLOWED_HOSTS` | `noesis-<svc>.up.railway.app`. Without this the transport-security middleware rejects all external requests with `421` / `403 host_not_allowed`. |
| `<SVC>_LOG_LEVEL` | optional, default `INFO` |
| `<SVC>_DATA_DIR` | optional, default `/data` (only relevant for stateful services) |

Cross-service:

| Var | Status | Notes |
|---|---|---|
| `KAIROS_URL` | currently unset on all services | When set, services emit OTel-style spans to Kairos. Empty → tracing is a no-op. Pending product decision: do we wire Kairos in as the central tracing collector, and where do we deploy it? |

## Verification

After all of the above is set, the service should pass:

```bash
curl -sS -i https://noesis-<svc>.up.railway.app/health
# expect: HTTP/2 200, body {"status":"ok"} (or similar)
```

If you see:
- `502` — container crashed at boot. Read runtime logs.
- `403 host_not_allowed` — `<SVC>_ALLOWED_HOSTS` not set or doesn't include the public domain.
- `404` — `healthcheckPath` not picked up; verify Config-as-code File Path is set.
- `421` — same as `403 host_not_allowed`, older Railway edge.
