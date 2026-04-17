# Mneme

**AGI Stage:** 3–4 | **Phase:** 1 | **Status:** 🔲 Not implemented

Persistentes episodisches und semantisches Gedächtnis für AI-Agenten.
Schließt die Lücke: *"Context windows are bounded and ephemeral — no mechanism for lifelong knowledge accumulation."*

## Motivation

LLMs verlieren nach jeder Session ihren gesamten Kontext. Mneme speichert
Erkenntnisse, Fakten und Ereignisse dauerhaft — und macht sie semantisch abrufbar.
Memories die über Logos verifiziert wurden, erhalten das `proven=True` Flag.

## MCP-Tools

| Tool | Beschreibung |
|------|-------------|
| `store_memory` | Speichert einen Inhalt mit Typ, Konfidenz und optionalem Proof-Zertifikat |
| `retrieve_memory` | Semantische Suche über gespeicherte Memories (k-nearest) |
| `consolidate` | Fasst ähnliche Memories zusammen (periodisch ausführen) |
| `forget` | Löscht eine Memory mit Begründung (Audit-Trail) |
| `list_proven_beliefs` | Gibt alle Memories zurück die via Logos verifiziert sind |
| `get_memory_stats` | Statistiken: Anzahl, Typen, Alter, Konfidenz-Verteilung |

## Architektur

```
Mneme
├── Episodisches Gedächtnis  → Was ist wann passiert? (zeitlich)
├── Semantisches Gedächtnis  → Was ist wahr/bekannt? (konzeptuell)
├── Vector Store (ChromaDB)  → Semantische Ähnlichkeitssuche
├── SQLite                   → Metadaten, Timestamps, Konfidenz, Proof-Certs
└── Logos-Client        → Optionale Verifikation beim Speichern
```

## Memory-Typen

- `episodic` — Ereignisse mit Timestamp (Was ist passiert?)
- `semantic` — Fakten und Konzepte (Was ist wahr?)
- `procedural` — Abläufe und Strategien (Wie geht etwas?)
- `belief` — Überzeugungen mit Konfidenzwert (Was glaube ich?)

## Tech Stack

- Python 3.12
- FastAPI + MCP HTTP transport
- ChromaDB (Vector Storage)
- SQLite (Metadaten)
- Logos-Client (optional, für `proven` Flag)

## Deployment (Railway)

Folgt dem Logos-Muster: `Dockerfile` + `Procfile` + `railway.toml`

```
web: python -m memory_brain.mcp_server_http
```

## Referenzen

- RETRO: Borgeaud et al. (2022) — Retrieval-Enhanced Transformers
- Generative Agents: Park et al. (2023) — Persistent memory in agents
- `../Logos/` — Verifikations-Backend
- `../ROADMAP.md §4` — Vollständige Spec
