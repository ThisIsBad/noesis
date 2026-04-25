# Eval-harness env template

The A/B harness reads service URLs + bearer tokens from
`eval/.env.e2e` (gitignored). This file is the **safe template**:
copy the relevant block below into `eval/.env.e2e`, fill in real
values, and never commit that file.

> Why this is a `.md` and not a `.env.example`: a previous
> `eval/.env.e2e.example` leaked real Railway URLs and bearer
> secrets for all 8 services (see PR #75). The `.env.*` glob in the
> repo `.gitignore` is the guard against that mistake; we keep the
> guard wide and ship the template outside the glob instead.

Lines with empty URLs are silently skipped by the eval harness — leave
them blank to *exclude* a service from the treatment surface (useful
when a service is down or you want to ablate one).

## Option A — local docker-compose stack

Boot the stack with `docker compose up -d --build` from the repo
root, then paste this verbatim into `eval/.env.e2e`. The secrets
match the dev defaults in `docker-compose.yml`.

```env
NOESIS_LOGOS_URL=http://localhost:8001
NOESIS_LOGOS_SECRET=dev-logos-secret

NOESIS_MNEME_URL=http://localhost:8002
NOESIS_MNEME_SECRET=dev-mneme-secret

NOESIS_PRAXIS_URL=http://localhost:8003
NOESIS_PRAXIS_SECRET=dev-praxis-secret

NOESIS_TELOS_URL=http://localhost:8004
NOESIS_TELOS_SECRET=dev-telos-secret

NOESIS_EPISTEME_URL=http://localhost:8005
NOESIS_EPISTEME_SECRET=dev-episteme-secret

NOESIS_KOSMOS_URL=http://localhost:8006
NOESIS_KOSMOS_SECRET=dev-kosmos-secret

NOESIS_EMPIRIA_URL=http://localhost:8007
NOESIS_EMPIRIA_SECRET=dev-empiria-secret

NOESIS_TECHNE_URL=http://localhost:8008
NOESIS_TECHNE_SECRET=dev-techne-secret

NOESIS_AB_MAX_BUDGET_USD=0.25
```

## Option B — Railway deploys

Replace each `<...>` placeholder with the deployed Railway URL and the
matching `<SVC>_SECRET` from the Railway env panel. See
`docs/operations/secrets.md` for the rotation runbook and
`docs/operations/deploy-runbook.md` for the deploy click-path.

```env
NOESIS_LOGOS_URL=<https://logos-...up.railway.app>
NOESIS_LOGOS_SECRET=<from Railway: LOGOS_SECRET>

NOESIS_MNEME_URL=<https://mneme-...up.railway.app>
NOESIS_MNEME_SECRET=<from Railway: MNEME_SECRET>

NOESIS_PRAXIS_URL=<https://praxis-...up.railway.app>
NOESIS_PRAXIS_SECRET=<from Railway: PRAXIS_SECRET>

NOESIS_TELOS_URL=<https://telos-...up.railway.app>
NOESIS_TELOS_SECRET=<from Railway: TELOS_SECRET>

NOESIS_EPISTEME_URL=<https://episteme-...up.railway.app>
NOESIS_EPISTEME_SECRET=<from Railway: EPISTEME_SECRET>

NOESIS_KOSMOS_URL=<https://kosmos-...up.railway.app>
NOESIS_KOSMOS_SECRET=<from Railway: KOSMOS_SECRET>

NOESIS_EMPIRIA_URL=<https://empiria-...up.railway.app>
NOESIS_EMPIRIA_SECRET=<from Railway: EMPIRIA_SECRET>

NOESIS_TECHNE_URL=<https://techne-...up.railway.app>
NOESIS_TECHNE_SECRET=<from Railway: TECHNE_SECRET>

NOESIS_AB_MAX_BUDGET_USD=0.25
```
