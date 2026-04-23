"""Shared test doubles for the Noesis ecosystem.

Every service that depends on the Logos sidecar eventually reaches for
a ``FakeLogosClient`` in its own test suite — Mneme has one, Praxis
has one, the Phase-1 E2E gate has one, and future consumers (Telos
when it wires a sidecar, Kosmos, ...) will too. Prior to this module
those were three copies of essentially the same class. Extracting
them here keeps the fake's contract a single artifact that moves with
the real ``LogosClient``.

Exports:

- :class:`FakeLogosClient` — drop-in for ``noesis_clients.LogosClient``
  that returns whatever certificate (or None) the test pre-loaded and
  records every call argument for assertions.
- :func:`verified_certificate` / :func:`refuted_certificate` — canned
  ``ProofCertificate`` factories so tests don't re-type the same
  five-field constructor.

These stand-ins expose only the subset of the real client API that
downstream tests actually exercise. If a consumer needs a broader
surface (e.g. a streaming tool call), widen this module — don't make
another private fake.
"""

from __future__ import annotations

from noesis_schemas import ProofCertificate


class FakeLogosClient:
    """Drop-in replacement for ``noesis_clients.LogosClient``.

    Usage::

        from noesis_clients.testing import FakeLogosClient, verified_certificate

        fake = FakeLogosClient(verified_certificate())
        core = PraxisCore(logos_client=fake)
        ...
        assert fake.calls == ["plan rendering ..."]

    The fake matches the real client on the subset that services use:

    * ``await certify_claim(argument)`` returns the pre-loaded response
      (a ``ProofCertificate`` or ``None``).
    * ``last_error`` mirrors the real client's diagnostic attribute and
      is settable at construction time so tests can simulate "Logos
      unreachable, see this error".
    * ``calls`` records every argument string passed to
      ``certify_claim`` — handy for pinning the exact claim Praxis or
      Mneme renders before shipping it off.

    No side effects, no I/O, no thread safety guarantees — tests
    should instantiate one per test case.
    """

    def __init__(
        self,
        response: ProofCertificate | None = None,
        *,
        last_error: str | None = None,
    ) -> None:
        self._response = response
        self.last_error = last_error
        self.calls: list[str] = []

    async def certify_claim(self, argument: str) -> ProofCertificate | None:
        """Record the call and return the pre-loaded response."""
        self.calls.append(argument)
        return self._response

    @property
    def last_argument(self) -> str | None:
        """The most-recent argument passed to ``certify_claim``.

        Handy when a test only cares about the latest call ("did
        Mneme actually forward the claim I stored?") without
        reaching into the ``calls`` list.
        """
        return self.calls[-1] if self.calls else None


def verified_certificate(
    *,
    claim: str = "Pre-canned verified claim",
    method: str = "z3_propositional",
    claim_type: str = "propositional",
    timestamp: str = "2026-04-23T17:00:00+00:00",
) -> ProofCertificate:
    """Factory for a ``ProofCertificate`` with ``verified=True``.

    Every argument has a default so ``verified_certificate()`` is the
    canonical "give me a passing certificate" expression.
    """
    return ProofCertificate(
        claim_type=claim_type,
        claim=claim,
        method=method,
        verified=True,
        timestamp=timestamp,
    )


def refuted_certificate(
    *,
    claim: str = "Pre-canned refuted claim",
    method: str = "z3_propositional",
    claim_type: str = "propositional",
    timestamp: str = "2026-04-23T17:00:00+00:00",
) -> ProofCertificate:
    """Factory for a ``ProofCertificate`` with ``verified=False``."""
    return ProofCertificate(
        claim_type=claim_type,
        claim=claim,
        method=method,
        verified=False,
        timestamp=timestamp,
    )


__all__ = [
    "FakeLogosClient",
    "verified_certificate",
    "refuted_certificate",
]
