# Hegemonikon gateway — bring-up checklist

This document is the canonical post-merge playbook for taking the
Hegemonikon gateway from "code on master" to "Walking Skeleton walks".
Read it top-to-bottom; each step has an explicit pass/fail signal so
you don't have to guess whether to move on.

The reverse direction — code-level architecture, why-this-shape, what
the gateway actually does — lives in [`hegemonikon.md`](hegemonikon.md)
and the source comments under `services/hegemonikon/src/hegemonikon/`.

## Prerequisites

- [ ] PR #99 (rename Console → Hegemonikon) merged on master.
- [ ] PR #100 (gateway code) merged on master.
- [ ] Railway service (the one that was "console" before) reachable
      under whatever URL slug it now has — typically
      `noesis-<slug>.up.railway.app`.

## Step 1 — Railway service config

Open the Railway dashboard, click into the service tile.

- [ ] **Settings → Build → Dockerfile path** =
      `services/hegemonikon/Dockerfile` (was `services/console/Dockerfile`).
- [ ] **Settings → Source** confirms it's tracking `master`.
- [ ] (optional, cosmetic) **Settings → Service → Display name** =
      `hegemonikon`. The URL slug only changes if you also rename the
      domain — leave the URL alone unless you have a reason.

## Step 2 — Railway env vars

Variables tab. The minimum-viable set for Walking Skeleton:

- [ ] `HEGEMONIKON_SECRET` = a fresh random value (e.g.
      `openssl rand -hex 32`). This is the bearer for the auth gate
      on `/api/*` and `/gateway/*`. Save the value somewhere — you
      need it again for the local smoke test and for Claude Code Web's
      env settings.
- [ ] `NOESIS_<SVC>_URL` for each of the 8 backends, where each URL
      points at that backend's Railway service base (no trailing
      `/sse`). Copy the canonical URL from each backend's Railway
      service tile — usually `https://noesis-<svc>.up.railway.app`.
      Backends:
      - [ ] `NOESIS_LOGOS_URL`
      - [ ] `NOESIS_MNEME_URL`
      - [ ] `NOESIS_PRAXIS_URL`
      - [ ] `NOESIS_TELOS_URL`
      - [ ] `NOESIS_EPISTEME_URL`
      - [ ] `NOESIS_KOSMOS_URL`
      - [ ] `NOESIS_EMPIRIA_URL`
      - [ ] `NOESIS_TECHNE_URL`

Optional (only if backends have their own bearer secrets set — check
each backend's `<SVC>_SECRET` env on its Railway tile):

- [ ] `NOESIS_<SVC>_SECRET` for each backend that requires auth. The
      gateway sends this value as the bearer when it talks to that
      backend. Mismatch = 401 from backend = gateway lists empty
      tools for that service.

Skip if backends are in open-mode (no `<SVC>_SECRET` env on the
backend service). Walking Skeleton is fine with open-mode backends —
Hegemonikon is the auth boundary the world sees.

## Step 3 — Trigger a real rebuild

Important: Railway's "Redeploy" button restarts the existing image
without rebuilding from source. To pick up the new code, you need a
true rebuild.

- [ ] Service tile → **Deployments** tab.
- [ ] Three-dot menu on the most-recent deployment → look for
      "Redeploy with rebuild" or "Force rebuild" (label varies by
      Railway version).
- [ ] If only "Redeploy" is offered, push an empty commit on master
      to force a fresh build:
      `git commit --allow-empty -m "chore: trigger railway rebuild" && git push`.
- [ ] Watch the build logs. Look for `COPY services/hegemonikon/...`
      lines — confirms the Dockerfile path is now correct.
- [ ] Build status flips to **Success**, container becomes Active.

## Step 4 — Reachability check

Replace `<host>` with your service's hostname.

```bash
curl -i https://<host>/health
```

Expected: `HTTP/1.1 200` with body containing
- `"service": "hegemonikon"` — confirms post-rename code is live.
- `"mcp_servers": [<8 backend names>]` — confirms all 8 URL env vars
  are set correctly. Fewer than 8 = some `NOESIS_<SVC>_URL` is missing
  or typo'd.

If `service` reads `"console"` instead, you're hitting a stale image
— go back to Step 3 and force a rebuild.

## Step 5 — Auth gate verify

```bash
# Without bearer — should be 401.
curl -i https://<host>/api/chat \
  -X POST -H "Content-Type: application/json" \
  -d '{"prompt":"x"}'

# With valid bearer — should be 202 (or 400 if claude CLI isn't
# bundled in the image, which is fine — the auth gate passed).
export HEGEMONIKON_SECRET="<your-bearer-value>"
curl -i https://<host>/api/chat \
  -X POST -H "Content-Type: application/json" \
  -H "Authorization: Bearer $HEGEMONIKON_SECRET" \
  -d '{"prompt":"x"}'
```

Both responses behaving as described = bearer middleware is wired.

## Step 6 — Gateway endpoint smoke

```bash
curl -i -N --max-time 5 https://<host>/gateway/sse \
  -H "Authorization: Bearer $HEGEMONIKON_SECRET"
```

Expected: HTTP 200, `Content-Type: text/event-stream`, an `event:
endpoint` line in the body, then connection closes after 5s
(timeout, intentional — you have no MCP client on the receiving end).

If 401: bearer mismatch. If 404: gateway routes weren't mounted (PR
#100 didn't take — check `services/hegemonikon/src/hegemonikon/gateway.py`
exists in the deployed image).

## Step 7 — Full smoke (Bronze + Silver)

The script under `tools/gateway_smoke.py` does an actual MCP
round-trip — `tools/list` + a `telos__register_goal` +
`telos__list_active_goals` to verify a goal lands.

```bash
python tools/gateway_smoke.py \
  --base-url https://<host> \
  --level silver
```

Expected output: a list of green checkmarks ending with
`all checks passed`. Exit code 0.

The script leaves a marker goal in Telos's DB (description
`_smoke_test_<random>`). Telos has no delete tool, so manual cleanup
through whatever DB-admin path you use — or just let the markers
accumulate as a smoke-test trail.

## Step 8 — Wire Claude Code Web

- [ ] Claude Code Web → Environment Settings dialog (settings icon
      next to environment name in the top bar) → add:
      `NOESIS_HEGEMONIKON_SECRET=<same value as HEGEMONIKON_SECRET>`.
- [ ] Merge the `.mcp.json` swap PR (when ready — separate PR after
      this checklist passes Step 7).
- [ ] **Restart the Claude Code Web session** — env vars are only
      read at session start, mid-session changes don't take effect.

## Step 9 — Walking Skeleton verification

In a fresh Claude Code Web session, ask Claude to call a real
gateway-mediated tool. Suggested prompt:

> List the active goals in Telos using the `telos__list_active_goals`
> tool. Tell me what you see.

Expected: Claude makes the tool call, gets back the smoke marker
goals (or whatever's in Telos), reports them. **That's the Walking
Skeleton walking** — Claude → Hegemonikon → Telos backend → DB →
back to Claude → back to you.

## Failure-mode index

| Symptom | Diagnosis | Fix |
|---|---|---|
| `/health` returns `service: console` | stale image, Railway didn't rebuild | force rebuild (Step 3) |
| `/health` lists < 8 backends | some `NOESIS_<SVC>_URL` missing | set the missing env vars (Step 2) |
| `/gateway/sse` returns 401 with valid-looking bearer | shell var unexpanded or value mismatch | `echo $HEGEMONIKON_SECRET` to verify; copy literal from Railway |
| `/gateway/sse` returns 404 | gateway routes not in image | confirm `services/hegemonikon/src/hegemonikon/gateway.py` is on master and image was rebuilt |
| Smoke script: tools/list returns empty | gateway can't reach any backend | check Hegemonikon logs for "tools/list failed" warnings; usually backend URLs wrong or backends require auth gateway doesn't have |
| Smoke script: subset of backends contributed tools | some backends down or auth-gating gateway out | check those backends' `/health`; set `NOESIS_<SVC>_SECRET` if backend requires auth |
| Claude Code Web doesn't see hegemonikon tools after .mcp.json swap | env var not set in Web settings, or session not restarted | Step 8 redo |

## When to declare "Walking Skeleton done"

Bronze + Silver pass on `gateway_smoke.py` + Claude can successfully
invoke at least one gateway-mediated tool from a fresh session. That's
it. Gold-tier (cross-service composition) is Phase 1, not Walking
Skeleton.
