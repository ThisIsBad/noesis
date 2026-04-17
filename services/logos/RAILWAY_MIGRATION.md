# Logos Railway Migration

Logos was previously deployed from the standalone repo
`ThisIsBad/logos`. It has been absorbed into this monorepo as
`services/logos/`. This document describes the Railway steps to cut the
existing Logos service over to the monorepo build.

## Why the absorption happened

- Schema drift: `ProofCertificate` existed in two incompatible shapes
  (Noesis Pydantic stub vs. Logos dataclass). Mneme could not consume
  Logos output without a translation layer.
- `ConfidenceLevel` / `RiskLevel` / `EscalationDecision` lived only in
  Logos; other services had no shared vocabulary.
- Two repos meant two CI pipelines for coupled contracts.

After absorption:
- `noesis_schemas.ProofCertificate` is a Pydantic mirror of Logos's
  `to_dict()` output — there is one wire format.
- `ConfidenceLevel` and friends moved into `schemas/` so any service
  can emit and consume them without importing Logos internals.
- Logos's internal `ProofCertificate` dataclass is unchanged — only the
  shared-contract side was aligned.

## Railway steps

The external `ThisIsBad/logos` Railway service keeps running until this
migration completes. Nothing is torn down in the old repo.

1. **Create new Railway service** in the existing Noesis Railway project:
   - GitHub repo: `ThisIsBad/noesis`
   - Settings → Build:
     - Root Directory: *(empty — repo root)*
     - Dockerfile Path: `services/logos/Dockerfile`
   - Settings → Variables:
     ```
     PORT=8000
     ```
   - No volume needed — Logos is stateless.

2. **Deploy and smoke-test** the new service. Verify:
   - `GET /` (root) responds (Railway healthcheck path is `/` per
     `railway.toml`).
   - MCP endpoint `/mcp` lists expected tools:
     `verify_argument`, `certify_claim`, `certificate_store`,
     `check_assumptions`, `check_beliefs`, `counterfactual_branch`,
     `z3_check`, `check_contract`, `check_policy`, `z3_session`,
     `orchestrate_proof`, `proof_carrying_action`.

3. **Switch MCP clients** (Claude Code `~/.claude/settings.json`,
   other services) from the old Logos URL to the new Railway URL.

4. **Verify in production** for a few days that certificates issued by
   the new service pass through Mneme / Techne consumers without
   schema errors.

5. **Archive `ThisIsBad/logos`** on GitHub and shut down its Railway
   service. Keep the repo archived (not deleted) as a historical
   reference.

## Deployment parity

- Dockerfile uses repo-root build context (matches `services/mneme/`
  pattern) — `COPY services/logos/...` and `pip install .[http]`.
- Procfile entrypoint unchanged: `python -m logos.mcp_server_http`.
- `railway.toml` healthcheck path `/` unchanged.
- Python pinned to 3.11 to match rest of monorepo (was 3.10+).

## Rollback

If the new service has issues:

1. Point MCP clients back at the old Logos URL.
2. Old Railway service stays live until step 5 above — no rollback
   window risk.
