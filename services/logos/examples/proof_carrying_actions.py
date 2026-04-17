"""Proof-carrying actions demo for AI-agent workflows.

Run with:
    python examples/proof_carrying_actions.py
"""

from __future__ import annotations

from logos import ProofCertificate, certify, verify_certificate


def main() -> None:
    # 1) Agent certifies a claim before using it downstream.
    print("== Step 1: certify a valid argument ==")
    valid_cert = certify("P -> Q, P |- Q")
    print(f"method={valid_cert.method}")
    print(f"verified={valid_cert.verified}")

    # 2) Consumer performs zero-trust re-verification.
    print("\n== Step 2: independent re-check ==")
    print(f"verify_certificate(valid_cert)={verify_certificate(valid_cert)}")

    # 3) Certificate can be serialized and transferred.
    print("\n== Step 3: JSON roundtrip ==")
    payload = valid_cert.to_json()
    restored = ProofCertificate.from_json(payload)
    print(f"roundtrip_verified={restored.verified}")
    print(f"roundtrip_recheck={verify_certificate(restored)}")

    # 4) Failed certification is explicit and machine-readable.
    print("\n== Step 4: failed certification example ==")
    invalid_cert = certify("P -> Q, Q |- P")
    print(f"verified={invalid_cert.verified}")
    print(f"rule={invalid_cert.verification_artifact.get('rule')}")
    print(f"recheck={verify_certificate(invalid_cert)}")


if __name__ == "__main__":
    main()
