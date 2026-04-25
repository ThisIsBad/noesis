# Local Noesis stack — `docker compose`

The whole eight-service cognitive architecture, plus Kairos (tracing)
and Theoria (decision-DAG visualizer), boots from a single
`docker-compose.yml` at the repo root. This is the **canonical
testable surface** for development: deterministic, reset-able, no
Railway cost, and the eval harness can target it without code
changes.

> **For Railway deploys**, see
> [`deploy-runbook.md`](deploy-runbook.md). Both targets share the
> same env-var envelope (`NOESIS_<SVC>_URL` / `NOESIS_<SVC>_SECRET`),
> so swapping local↔production is just a `eval/.env.e2e` swap.

## TL;DR

```bash
# 1. Boot the stack (first run takes a few minutes — 8 image builds).
docker compose up -d --build

# 2. Wait for everything to report healthy.
docker compose ps

# 3. Sanity-probe one service.
curl http://localhost:8001/health   # → {"status":"ok","service":"logos"}

# 4. Point the eval harness at it.
cp eval/.env.e2e.example eval/.env.e2e   # if you have one; else:
# Open eval/env-template.md and copy the "Option A" block into eval/.env.e2e.
python -m pytest eval/tests/test_phase1_inprocess.py -q

# 5. Tear down (volumes preserved).
docker compose down
# … or wipe state too:
docker compose down -v
```

## Host port map

Every container listens on `:8000` internally; each service is
mapped to a unique host port for direct curl/Theoria access:

| Service  | Internal | Host  | Container name      |
|----------|----------|-------|---------------------|
| logos    | 8000     | 8001  | `noesis-logos`      |
| mneme    | 8000     | 8002  | `noesis-mneme`      |
| praxis   | 8000     | 8003  | `noesis-praxis`     |
| telos    | 8000     | 8004  | `noesis-telos`      |
| episteme | 8000     | 8005  | `noesis-episteme`   |
| kosmos   | 8000     | 8006  | `noesis-kosmos`     |
| empiria  | 8000     | 8007  | `noesis-empiria`    |
| techne   | 8000     | 8008  | `noesis-techne`     |
| kairos   | 8000     | 8009  | `noesis-kairos`     |
| theoria  | 8000     | 8765  | `noesis-theoria`    |

Inside the docker network (e.g. for service-to-service calls like
Praxis → Logos), services reach each other by hostname:
`http://logos:8000`, `http://kairos:8000`, etc. The compose file
already wires this for you (see `LOGOS_URL` / `KAIROS_URL` in each
service's `environment:` block).

## Dev secrets

Hardcoded in `docker-compose.yml` for ease of use — **never reuse in
production**. Each service has its own:

| Env var          | Value                  |
|------------------|------------------------|
| `LOGOS_SECRET`   | `dev-logos-secret`     |
| `MNEME_SECRET`   | `dev-mneme-secret`     |
| `PRAXIS_SECRET`  | `dev-praxis-secret`    |
| `TELOS_SECRET`   | `dev-telos-secret`     |
| `EPISTEME_SECRET`| `dev-episteme-secret`  |
| `KOSMOS_SECRET`  | `dev-kosmos-secret`    |
| `EMPIRIA_SECRET` | `dev-empiria-secret`   |
| `TECHNE_SECRET`  | `dev-techne-secret`    |

These match the "Option A — local docker-compose stack" block in
[`eval/env-template.md`](../../eval/env-template.md), so copying that
block into `eval/.env.e2e` wires the harness to the running stack.

## Persistence

Three named volumes back the stateful services. Survive `docker
compose down`; wiped by `docker compose down -v`:

| Volume        | Mount         | Service | Contents                         |
|---------------|---------------|---------|----------------------------------|
| `mneme_data`  | `/data`       | mneme   | `mneme.db`, `chroma/`            |
| `praxis_data` | `/data`       | praxis  | `praxis.db`                      |
| `techne_data` | `/data`       | techne  | `techne.db`, `techne_chroma/`    |

To inspect the SQLite directly:

```bash
docker compose exec mneme sqlite3 /data/mneme.db ".tables"
```

## Troubleshooting

* **A service stuck in `health: starting` for >60 s.** Look at its
  logs: `docker compose logs -f <service>`. Boot order is gated on
  `kairos: service_healthy` and `logos: service_healthy` for the
  ones that depend on them; if Kairos is wedged, the rest hold.
* **Port already in use on the host.** Either stop the conflicting
  process or change the host-side port in `docker-compose.yml`
  (e.g. `"8011:8000"` instead of `"8001:8000"` for Logos). The
  internal port is fixed at 8000.
* **Build is slow.** `docker compose build --parallel` parallelises
  the eight image builds; the first cold build is the expensive one
  because of `chromadb` / `hnswlib` native compilation in Mneme +
  Techne. Subsequent rebuilds are layer-cached.
* **Eval harness can't reach a service.** Confirm the URL in
  `eval/.env.e2e` matches the host port (8001…8008), not the
  internal 8000. The harness runs on the host, not inside the
  compose network.

## Resetting state for a clean run

```bash
docker compose down -v      # wipe volumes + containers
docker compose up -d --build
```

This is the right reset between A/B experiments where you want
Mneme to start with no memories and Techne with no skills.
