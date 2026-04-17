"""Transport-safe proof bundle exchange across process boundaries."""

from __future__ import annotations

import json
from dataclasses import dataclass

from logos.certificate import ProofCertificate, verify_certificate
from logos.schema_utils import (
    load_json_object,
    require_dict,
    require_list,
    require_list_of_str,
    require_str,
)

SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class ProofExchangeNode:
    """One certificate node and its dependency links."""

    node_id: str
    certificate: ProofCertificate
    depends_on: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProofBundle:
    """Versioned bundle for proof exchange."""

    schema_version: str
    nodes: dict[str, ProofExchangeNode]
    roots: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        """Serialize to dictionary payload."""
        return {
            "schema_version": self.schema_version,
            "roots": list(self.roots),
            "nodes": [
                {
                    "node_id": node.node_id,
                    "certificate": node.certificate.to_dict(),
                    "depends_on": list(node.depends_on),
                }
                for node in self.nodes.values()
            ],
        }

    def to_json(self) -> str:
        """Serialize bundle to JSON."""
        return json.dumps(self.to_dict(), sort_keys=True)

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "ProofBundle":
        """Deserialize bundle from dictionary payload."""
        schema_version = require_str(
            payload.get("schema_version"),
            "Proof bundle field 'schema_version' must be a string",
        )
        if schema_version != SCHEMA_VERSION:
            raise ValueError(f"Unsupported proof bundle schema version '{schema_version}'")
        roots = require_list_of_str(
            payload.get("roots"),
            "Proof bundle field 'roots' must be list[str]",
        )
        nodes = require_list(
            payload.get("nodes"),
            "Proof bundle field 'nodes' must be a list",
        )

        parsed_nodes: dict[str, ProofExchangeNode] = {}
        for item in nodes:
            item_dict = require_dict(item, "Proof bundle node entries must be objects")

            node_id = require_str(
                item_dict.get("node_id"),
                "Proof node field 'node_id' must be a string",
            )
            cert_payload = require_dict(
                item_dict.get("certificate"),
                "Proof node field 'certificate' must be an object",
            )
            depends_on = require_list_of_str(
                item_dict.get("depends_on", []),
                "Proof node field 'depends_on' must be list[str]",
            )

            certificate = ProofCertificate.from_dict(cert_payload)
            parsed_nodes[node_id] = ProofExchangeNode(
                node_id=node_id,
                certificate=certificate,
                depends_on=tuple(depends_on),
            )

        return cls(schema_version=schema_version, nodes=parsed_nodes, roots=tuple(roots))

    @classmethod
    def from_json(cls, raw_json: str) -> "ProofBundle":
        """Deserialize bundle from JSON string."""
        payload = load_json_object(
            raw_json,
            invalid_error="Invalid proof bundle JSON",
            object_error="Proof bundle JSON must be an object",
        )
        return cls.from_dict(payload)


@dataclass(frozen=True)
class ProofExchangeResult:
    """Verification result for a received proof bundle."""

    valid_bundle: bool
    complete: bool
    invalid_nodes: list[str]
    invalid_roots: list[str]
    missing_dependencies: list[str]
    diagnostics: list[dict[str, str]]


def create_proof_bundle(
    nodes: dict[str, ProofCertificate],
    dependencies: dict[str, list[str]] | None = None,
    roots: list[str] | None = None,
) -> ProofBundle:
    """Create a versioned proof bundle for exchange."""
    deps = dependencies or {}
    root_ids = tuple(roots or list(nodes.keys()))

    parsed_nodes: dict[str, ProofExchangeNode] = {}
    for node_id, certificate in nodes.items():
        parsed_nodes[node_id] = ProofExchangeNode(
            node_id=node_id,
            certificate=certificate,
            depends_on=tuple(deps.get(node_id, [])),
        )

    return ProofBundle(
        schema_version=SCHEMA_VERSION,
        nodes=parsed_nodes,
        roots=root_ids,
    )


def verify_proof_bundle(bundle: ProofBundle) -> ProofExchangeResult:
    """Verify exchanged proof bundle including partial-bundle status."""
    if bundle.schema_version != SCHEMA_VERSION:
        raise ValueError(f"Unsupported proof bundle schema version '{bundle.schema_version}'")

    invalid_nodes: list[str] = []
    invalid_roots: list[str] = []
    missing_dependencies: list[str] = []
    diagnostics: list[dict[str, str]] = []

    for root_id in bundle.roots:
        if root_id not in bundle.nodes:
            invalid_roots.append(root_id)
            diagnostics.append(
                {
                    "code": "invalid_root",
                    "node_id": root_id,
                    "message": f"Root '{root_id}' is missing from bundle nodes",
                }
            )

    for node_id, node in bundle.nodes.items():
        for dep in node.depends_on:
            if dep not in bundle.nodes:
                missing_dependencies.append(f"{node_id}->{dep}")
                diagnostics.append(
                    {
                        "code": "missing_dependency",
                        "node_id": node_id,
                        "message": f"Dependency '{dep}' required by '{node_id}' is missing",
                    }
                )

        try:
            if not verify_certificate(node.certificate):
                invalid_nodes.append(node_id)
                diagnostics.append(
                    {
                        "code": "certificate_mismatch",
                        "node_id": node_id,
                        "message": "Certificate verification returned False",
                    }
                )
        except ValueError as exc:
            invalid_nodes.append(node_id)
            diagnostics.append(
                {
                    "code": "certificate_error",
                    "node_id": node_id,
                    "message": str(exc),
                }
            )

    valid_bundle = len(invalid_nodes) == 0
    complete = len(missing_dependencies) == 0 and len(invalid_roots) == 0

    return ProofExchangeResult(
        valid_bundle=valid_bundle,
        complete=complete,
        invalid_nodes=sorted(invalid_nodes),
        invalid_roots=sorted(invalid_roots),
        missing_dependencies=sorted(missing_dependencies),
        diagnostics=sorted(
            diagnostics,
            key=lambda item: (
                item["code"],
                item["node_id"],
                item["message"],
            ),
        ),
    )
