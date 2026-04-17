# Proof Exchange Migration Guide

This guide documents schema evolution strategy for `logic_brain.proof_exchange`.

## Current Schema

- Bundle schema version: `1.0`
- Certificate schema version: follows `ProofCertificate` versioning (`1.0`)

## Compatibility Rules

1. Consumers must reject unsupported bundle schema versions.
2. Producers must emit explicit `schema_version` in every bundle.
3. New required fields require a major schema bump.
4. New optional fields may be added in minor schema updates when old consumers
   can safely ignore them.
5. Certificate schema and bundle schema evolve independently; both are validated.

## Upgrade Pattern

When introducing a new schema version:

1. Add parser + validator for the new version.
2. Keep old parser for at least one minor release if feasible.
3. Add migration tests for old->new conversion.
4. Document deprecation timeline in `CHANGELOG.md`.

## Operational Guidance

- Prefer forward-additive changes.
- Keep node ids stable across migrations for dependency graph continuity.
- Re-run independent verification (`verify_proof_bundle`) after migration.
