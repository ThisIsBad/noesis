# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in Noesis, please **do not** open a
public issue. Instead, report it privately via GitHub's Security Advisories:

  https://github.com/ThisIsBad/noesis/security/advisories/new

Please include:

- A description of the vulnerability and its potential impact
- Steps to reproduce (proof-of-concept code is welcome)
- The affected component (`schemas`, `kairos`, `clients`, one of the eight
  services in `services/`, the `eval` harness, or the `ui/console` /
  `ui/theoria` surfaces)
- The commit SHA or version you tested against

We aim to acknowledge reports within 72 hours and to provide a fix or
mitigation timeline within 14 days.

## Supported Versions

Noesis is in active development. Only the `main` branch and the most recent
release tag receive security fixes.

## Scope

In scope:

- Authentication and authorization gaps in any service's HTTP surface
- Injection or sandbox-escape via the Console agent loop
- Data leakage between sessions, services, or persistence backends
- Supply-chain issues in declared dependencies (`pyproject.toml`)

Out of scope:

- Vulnerabilities in third-party services (Anthropic API, Railway, GitHub) —
  please report those upstream
- Issues that require local code execution or compromised developer machines
- Theoretical attacks without a demonstrable exploit path
