"""Experiment: Proof Template Transfer (Gap 4 — Strategy Transfer).

Tests whether verified certificates can be generalized into reusable
templates via uniform proposition substitution and instantiated for new
problems while preserving formal validity.

Key insight: Propositional logic validity is preserved under uniform
substitution of proposition variables.  This experiment validates that
LogicBrain's verification correctly handles this and measures transfer
rates across multiple reasoning patterns.

No production code changes — experiment only.
"""

from __future__ import annotations

import json
import re

from logos import CertificateStore, certify, verify


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_propositions(claim: str) -> set[str]:
    """Extract single-uppercase-letter proposition labels from *claim*."""
    return set(re.findall(r"\b[A-Z]\b", claim))


def _substitute(claim: str, mapping: dict[str, str]) -> str:
    """Uniformly substitute proposition labels in *claim*.

    Sorts by length descending to avoid partial replacements.
    """
    result = claim
    for old, new in sorted(mapping.items(), key=lambda x: -len(x[0])):
        result = re.sub(r"\b" + re.escape(old) + r"\b", new, result)
    return result


# ---------------------------------------------------------------------------
# Template patterns (valid)
# ---------------------------------------------------------------------------

VALID_TEMPLATES: list[tuple[str, str]] = [
    ("P -> Q, P |- Q", "modus_ponens"),
    ("P -> Q, ~Q |- ~P", "modus_tollens"),
    ("P -> Q, Q -> R |- P -> R", "hypothetical_syllogism"),
    ("P | Q, ~P |- Q", "disjunctive_syllogism"),
    ("P & Q |- P", "simplification"),
    ("P |- P | Q", "addition"),
    ("P -> Q |- ~Q -> ~P", "contrapositive"),
]

INVALID_TEMPLATES: list[tuple[str, str]] = [
    ("P -> Q, Q |- P", "affirming_consequent"),
    ("P -> Q, ~P |- ~Q", "denying_antecedent"),
]

SUBSTITUTION_SETS: list[dict[str, str]] = [
    {"P": "A", "Q": "B", "R": "C"},
    {"P": "X", "Q": "Y", "R": "Z"},
    {"P": "M", "Q": "N", "R": "K"},
]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestProofTemplateTransfer:
    """Validate that proof certificates transfer via uniform substitution."""

    def test_modus_ponens_transfers(self) -> None:
        original = "P -> Q, P |- Q"
        cert = certify(original)
        assert cert.verified

        transferred = _substitute(original, {"P": "A", "Q": "B"})
        assert verify(transferred).valid

    def test_chain_reasoning_transfers(self) -> None:
        original = "P -> Q, Q -> R |- P -> R"
        cert = certify(original)
        assert cert.verified

        transferred = _substitute(original, {"P": "X", "Q": "Y", "R": "Z"})
        assert verify(transferred).valid

    def test_contrapositive_transfers(self) -> None:
        original = "P -> Q |- ~Q -> ~P"
        cert = certify(original)
        assert cert.verified

        transferred = _substitute(original, {"P": "M", "Q": "N"})
        assert verify(transferred).valid

    def test_invalidity_preserved_under_substitution(self) -> None:
        """An invalid argument remains invalid after substitution."""
        original = "P -> Q, Q |- P"
        cert = certify(original)
        assert not cert.verified

        transferred = _substitute(original, {"P": "A", "Q": "B"})
        assert not verify(transferred).valid

    def test_full_transfer_matrix(self) -> None:
        """All valid templates transfer at 100% across all substitution sets."""
        total = 0
        successful = 0

        for template, _name in VALID_TEMPLATES:
            cert = certify(template)
            assert cert.verified, f"Template {_name} should be valid"

            for mapping in SUBSTITUTION_SETS:
                props = _extract_propositions(template)
                relevant = {k: v for k, v in mapping.items() if k in props}
                transferred = _substitute(template, relevant)

                result = verify(transferred)
                total += 1
                if result.valid:
                    successful += 1

        transfer_rate = successful / total
        assert transfer_rate == 1.0, f"Transfer rate: {transfer_rate:.2%} ({successful}/{total})"

    def test_invalid_transfer_matrix(self) -> None:
        """All invalid templates stay invalid across all substitution sets."""
        total = 0
        preserved = 0

        for template, _name in INVALID_TEMPLATES:
            cert = certify(template)
            assert not cert.verified, f"Template {_name} should be invalid"

            for mapping in SUBSTITUTION_SETS:
                props = _extract_propositions(template)
                relevant = {k: v for k, v in mapping.items() if k in props}
                transferred = _substitute(template, relevant)

                result = verify(transferred)
                total += 1
                if not result.valid:
                    preserved += 1

        preservation_rate = preserved / total
        assert preservation_rate == 1.0, f"Invalidity preservation rate: {preservation_rate:.2%} ({preserved}/{total})"

    def test_template_store_retrieve_and_apply(self) -> None:
        """Templates stored with tags can be retrieved and applied."""
        store = CertificateStore()

        for claim, pattern_name in VALID_TEMPLATES:
            cert = certify(claim)
            store.store(cert, tags={"pattern": pattern_name})

        results = store.query(tags={"pattern": "modus_ponens"})
        assert len(results) == 1

        template_claim = results[0].certificate.claim
        assert isinstance(template_claim, str)

        transferred = _substitute(template_claim, {"P": "A", "Q": "B"})
        assert verify(transferred).valid

    def test_ranked_retrieval_finds_relevant_template(self) -> None:
        """query_ranked returns templates sharing proposition tokens."""
        store = CertificateStore()
        for claim, pattern_name in VALID_TEMPLATES:
            store.store(certify(claim), tags={"pattern": pattern_name})

        ranked = store.query_ranked("P Q")
        assert ranked.total_candidates > 0
        # Top result should mention P and Q
        top = ranked.results[0]
        assert isinstance(top.entry.certificate.claim, str)
        top_props = _extract_propositions(top.entry.certificate.claim)
        assert {"P", "Q"} & top_props

    def test_compaction_preserves_template_utility(self) -> None:
        """After compaction, remaining certs still serve as templates."""
        store = CertificateStore()
        claims = [
            "P |- P",
            "P -> Q, P |- Q",
            "P -> Q, Q -> R, P |- R",
            "P -> Q, Q -> R |- P -> R",
        ]
        for claim in claims:
            store.store(certify(claim))

        before = store.stats().valid
        compaction = store.compact()
        after = store.stats().valid

        assert compaction.verification_passed
        assert after <= before

        for entry in store.query():
            claim = entry.certificate.claim
            if isinstance(claim, str) and entry.certificate.verified:
                props = _extract_propositions(claim)
                mapping = {p: chr(ord("A") + i) for i, p in enumerate(sorted(props))}
                transferred = _substitute(claim, mapping)
                assert verify(transferred).valid

    def test_experiment_summary(self) -> None:
        """Produce a JSON summary of all transfer results."""
        results: dict[str, object] = {
            "experiment": "proof_template_transfer",
            "valid_templates": len(VALID_TEMPLATES),
            "invalid_templates": len(INVALID_TEMPLATES),
            "substitution_sets": len(SUBSTITUTION_SETS),
        }

        # Valid transfers
        valid_total = 0
        valid_ok = 0
        for template, name in VALID_TEMPLATES:
            for mapping in SUBSTITUTION_SETS:
                props = _extract_propositions(template)
                relevant = {k: v for k, v in mapping.items() if k in props}
                transferred = _substitute(template, relevant)
                valid_total += 1
                if verify(transferred).valid:
                    valid_ok += 1

        # Invalid preservation
        invalid_total = 0
        invalid_ok = 0
        for template, name in INVALID_TEMPLATES:
            for mapping in SUBSTITUTION_SETS:
                props = _extract_propositions(template)
                relevant = {k: v for k, v in mapping.items() if k in props}
                transferred = _substitute(template, relevant)
                invalid_total += 1
                if not verify(transferred).valid:
                    invalid_ok += 1

        results["valid_transfer_rate"] = valid_ok / valid_total if valid_total else 0
        results["invalid_preservation_rate"] = invalid_ok / invalid_total if invalid_total else 0
        results["valid_transfers"] = f"{valid_ok}/{valid_total}"
        results["invalid_preserved"] = f"{invalid_ok}/{invalid_total}"

        summary = json.dumps(results, indent=2)
        print(f"\n--- Proof Template Transfer Results ---\n{summary}")

        assert valid_ok == valid_total
        assert invalid_ok == invalid_total
