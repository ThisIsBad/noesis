"""Federated trust-domain ledger for exchanged proof bundles."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from logos.proof_exchange import ProofBundle, ProofExchangeResult, verify_proof_bundle

SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class TrustPolicy:
    """Explicit trust boundaries for cross-domain proof acceptance."""

    domain_id: str
    trusted_domains: tuple[str, ...]
    allowed_schema_versions: tuple[str, ...] = (SCHEMA_VERSION,)


@dataclass(frozen=True)
class LedgerRecord:
    """One accepted or rejected cross-domain proof decision."""

    bundle_id: str
    remote_domain_id: str
    accepted: bool
    accepted_at: str
    expires_at: str | None
    revoked_at: str | None
    revocation_reason: str | None
    diagnostics: tuple[dict[str, str], ...]
    verification: ProofExchangeResult


@dataclass(frozen=True)
class LedgerQueryResult:
    """Explainable answer to why a bundle is accepted or rejected."""

    bundle_id: str
    accepted: bool
    usable: bool
    reasons: tuple[str, ...]
    diagnostics: tuple[dict[str, str], ...]
    what_changed: tuple[str, ...]


class FederatedProofLedger:
    """Store deterministic trust decisions for exchanged proof bundles."""

    def __init__(self, policy: TrustPolicy) -> None:
        self.policy = policy
        self._records: dict[str, LedgerRecord] = {}

    def evaluate_bundle(
        self,
        *,
        bundle_id: str,
        remote_domain_id: str,
        bundle: ProofBundle,
        accepted_at: str | None = None,
        expires_at: str | None = None,
    ) -> LedgerRecord:
        """Accept or reject a bundle under explicit trust policy."""
        timestamp = accepted_at or _now_iso()
        diagnostics: list[dict[str, str]] = []
        accepted = True

        if remote_domain_id not in set(self.policy.trusted_domains):
            accepted = False
            diagnostics.append(
                {
                    "code": "untrusted_domain",
                    "bundle_id": bundle_id,
                    "message": f"Domain '{remote_domain_id}' is not trusted by '{self.policy.domain_id}'",
                }
            )

        if bundle.schema_version not in set(self.policy.allowed_schema_versions):
            accepted = False
            diagnostics.append(
                {
                    "code": "schema_not_allowed",
                    "bundle_id": bundle_id,
                    "message": f"Schema version '{bundle.schema_version}' is not allowed by policy",
                }
            )

        verification = verify_proof_bundle(bundle)
        if verification.valid_bundle is False or verification.complete is False:
            accepted = False
            diagnostics.extend(verification.diagnostics)

        record = LedgerRecord(
            bundle_id=bundle_id,
            remote_domain_id=remote_domain_id,
            accepted=accepted,
            accepted_at=timestamp,
            expires_at=expires_at,
            revoked_at=None,
            revocation_reason=None,
            diagnostics=tuple(
                sorted(
                    diagnostics,
                    key=lambda item: (
                        item.get("code", ""),
                        item.get("bundle_id", item.get("node_id", "")),
                        item.get("message", ""),
                    ),
                )
            ),
            verification=verification,
        )
        self._records[bundle_id] = record
        return record

    def revoke_bundle(self, bundle_id: str, *, revoked_at: str | None = None, reason: str) -> LedgerRecord:
        """Mark a previously recorded bundle as revoked."""
        record = self.get_record(bundle_id)
        updated = LedgerRecord(
            bundle_id=record.bundle_id,
            remote_domain_id=record.remote_domain_id,
            accepted=record.accepted,
            accepted_at=record.accepted_at,
            expires_at=record.expires_at,
            revoked_at=revoked_at or _now_iso(),
            revocation_reason=reason,
            diagnostics=record.diagnostics,
            verification=record.verification,
        )
        self._records[bundle_id] = updated
        return updated

    def get_record(self, bundle_id: str) -> LedgerRecord:
        """Return a previously evaluated ledger record."""
        if bundle_id not in self._records:
            raise ValueError(f"Unknown bundle '{bundle_id}'")
        return self._records[bundle_id]

    def query_bundle(self, bundle_id: str, *, as_of: str | None = None) -> LedgerQueryResult:
        """Explain whether a bundle is accepted, usable, and what changed."""
        record = self.get_record(bundle_id)
        query_time = _parse_iso(as_of) if as_of is not None else None
        reasons: list[str] = []
        changes: list[str] = []

        if record.accepted:
            reasons.append("accepted_by_explicit_trust_policy")
        else:
            reasons.append("rejected_by_policy_or_bundle_validation")

        usable = record.accepted
        if record.revoked_at is not None and (query_time is None or _parse_iso(record.revoked_at) <= query_time):
            usable = False
            reasons.append("revoked")
            changes.append("revocation_recorded")

        if record.expires_at is not None and (query_time is None or _parse_iso(record.expires_at) <= query_time):
            usable = False
            reasons.append("expired")
            changes.append("expiry_reached")

        if record.verification.complete is False:
            usable = False
            reasons.append("incomplete_bundle")
        if record.verification.valid_bundle is False:
            usable = False
            reasons.append("invalid_bundle")

        return LedgerQueryResult(
            bundle_id=bundle_id,
            accepted=record.accepted,
            usable=usable,
            reasons=tuple(reasons),
            diagnostics=record.diagnostics,
            what_changed=tuple(changes),
        )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value)
