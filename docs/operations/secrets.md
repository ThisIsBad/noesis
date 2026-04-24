# Secrets — current state, risks, and forward path

> **Status: 2026-04-23.** Written as part of the Tier-3 action list in
> [architect-review-2026-04-23.md](../architect-review-2026-04-23.md).

## What we have today

Every service (and Theoria, and the Logos sidecar client) guards its
HTTP surface with a **per-service bearer token** read from the
environment at startup.

| Component | Env var |
|-----------|---------|
| Logos | `LOGOS_SECRET` |
| Mneme | `MNEME_SECRET` |
| Praxis | `PRAXIS_SECRET` |
| Telos | `TELOS_SECRET` |
| Episteme | `EPISTEME_SECRET` |
| Kosmos | `KOSMOS_SECRET` |
| Empiria | `EMPIRIA_SECRET` |
| Techne | `TECHNE_SECRET` |
| Theoria (UI) | `THEORIA_SECRET` |
| Logos sidecar client | `LOGOS_SECRET` (same value as Logos) |

Each service reads the value at import time, builds an ASGI
middleware that compares every incoming request's `Authorization:
Bearer <token>` header, and 401s on mismatch. `/health` is exempt.
When the env var is unset the middleware is a no-op (open mode for
local dev — each service logs `secret_set=...` at boot).

In effect this is **N independent symmetric secrets, stored as
Railway environment variables, with no central authority**.

## What this gives us

- Basic protection against the public internet for each deployed
  service. Railway public URLs are Google-indexable by default.
- Separation of concerns: compromising one service's secret doesn't
  automatically compromise another's.
- Simple bootstrap: `openssl rand -hex 32` per service, paste into
  Railway dashboard, done.

## What this does NOT give us

1. **No rotation.** Changing `LOGOS_SECRET` requires coordinated
   restart of Logos + every caller that has `LOGOS_SECRET`
   configured (Mneme, Praxis, Theoria, eval harness, ...). No
   overlap window; no automated rollout.
2. **No granularity.** A service has exactly two audiences: "anyone
   with the secret" and "anyone without". No per-caller attribution,
   no revocation of a single client, no scoped permissions.
3. **No mTLS despite the architecture doc claiming it.**
   `docs/architecture.md` §Kommunikations-Protokoll mentions
   "Railway-interne mTLS oder API-Key". Today only the API-Key half
   is implemented.
4. **No audit trail.** The middleware 401s on mismatch but doesn't
   log attempted-auth events in any structured way.
5. **Near-duplicate middleware in every service.** The bearer check
   is written four different ways across `services/*`, `ui/theoria`,
   and the review's own work on this PR.

## Immediate-risk triage

- **Leaked secret in logs.** Not observed, but low-friction to get
  wrong. Every service should redact `Authorization` headers before
  structured-log emission.
- **Secret in CI.** None of the CI workflows currently have real
  secrets — they test without them. Adding them to GitHub Actions
  Secrets and exposing via `env:` on a specific job is safe when the
  time comes.
- **Secret in `.mcp.json`.** The root `.mcp.json` does not embed
  secrets today; Claude Code reads them from the user's
  `~/.claude/settings.json`. Keep it that way.

## Forward path

Three stages, cheapest first.

### Stage 1 — DRY the middleware (1 PR, 1 day)

Extract the bearer-check ASGI middleware into a shared helper in
`clients/src/noesis_clients/` (for example
`noesis_clients.auth.bearer_middleware(env_var, exempt_paths)`).
Every service gets a one-line import + mount. Shrinks ~30 lines × 9
services, standardises exempt-path handling, and gives us one place
to later add structured audit logging.

Concrete shape:

```python
# services/<svc>/src/<svc>/mcp_server_http.py
from noesis_clients.auth import bearer_middleware

app.add_middleware(bearer_middleware, env_var="MNEME_SECRET")
```

This is strictly refactoring — no auth-model change. **Ship this
regardless of what we decide about Stage 2/3.**

### Stage 2 — Rotatable tokens ✅ landed

`noesis_clients.auth.bearer_middleware` accepts two environment
variables per service: `<SVC>_SECRET` (active) and, by default,
`<SVC>_SECRET_PREV` (grace-period). The middleware trusts a request
whose token matches either during the rotation window. Override the
previous-env-var name with `prev_env_var=...` if your service uses a
non-standard convention.

**Rotation runbook:**

1. Generate a new token: `openssl rand -hex 32`.
2. Deploy the service with `<SVC>_SECRET=<new>` and
   `<SVC>_SECRET_PREV=<old>`. Both tokens now accepted.
3. Update every caller's config to `<new>`. Restart each caller.
4. Deploy the service again with `<SVC>_SECRET_PREV` **unset** to
   close the rotation window.

Wall time: ≈ 30 minutes, zero downtime, zero lost requests. Tests
in `clients/tests/test_auth.py::test_rotation_*` pin the behaviour.

If you skip step 4 permanently you effectively double your valid
secrets — don't.

### Stage 3 — Central auth (roadmap, not committed)

When service count or sensitivity grows, two realistic options:

- **Option A — mTLS via Railway private networking.** All inter-service
  traffic uses `<svc>.railway.internal` with certificates minted by a
  shared CA. Public edge still uses bearer tokens for Claude. Lowest
  runtime overhead, highest deployment complexity.
- **Option B — gateway + JWT.** A single edge proxy (Traefik,
  Caddy, or Railway's built-in) terminates TLS and injects JWTs
  keyed by caller identity. Services verify the JWT signature and
  extract scopes. Plays well with tools outside Noesis; more moving
  parts.

Either way, defer until the per-service bearer model actually bites
(first rotation fire drill, or first ops request that can't be
served by it).

## Checklist

- [x] Document the current auth model accurately (**this file**).
- [x] Stage 1 — extract `noesis_clients.auth.bearer_middleware`.
- [x] Stage 2 — rotatable `<SVC>_SECRET_PREV` in the shared
      middleware (no service migration yet — see below).
- [ ] Migrate each service from its hand-rolled `_BearerAuth` class
      to `bearer_middleware(env_var)` from `noesis_clients.auth`.
      The MVP services (Telos, Episteme, Kosmos, Empiria, Techne,
      Praxis) are straightforward. Logos and Mneme are
      production-deployed — their sweep should be its own PR with
      explicit per-service review.
- [ ] Add `Authorization` redaction to every service's structured
      log emitter.
- [ ] Decide between Stage-3 options (mTLS vs gateway-JWT) when the
      per-service bearer model starts biting operationally.
