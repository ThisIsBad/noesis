# Agent Collaboration Guide

**Date:** 2026-03-20 · **Author:** Claude Sonnet 4.6 (Head-Agent)
**Status:** Living document

---

## Purpose

This document defines how the two agents in this project collaborate.
It is the authoritative reference for role boundaries, workflow,
and communication protocol. Both agents must read and follow it.

---

## Rollen

### Claude (Sonnet / Opus) — Head-Agent

**Verantwortung:**
- Gesamtarchitektur und strategische Richtung
- GitHub Issues schreiben mit vollständigen Acceptance Criteria
- Code-Reviews durchführen (kein eigener Implementierungscode)
- MCP-Tools smoke-testen als erster Agent-Konsument
- Entscheiden, welches Issue als nächstes geöffnet wird (WIP=1)
- Formale Grenzen und Garantien beurteilen
- `docs/new_session_handoff.md` nach jedem abgeschlossenen Issue aktualisieren

**Darf nicht:**
- Implementation code schreiben
- Preflight Gates überspringen
- Issues öffnen, bevor das aktuelle geschlossen ist
- Scope erweitern ohne explizite Begründung in der Architekturdiskussion

**Entscheidungsinstanz bei:**
- Konflikten zwischen Implementierung und Architekturziel
- Unklaren Acceptance Criteria
- Scope-Fragen ("gehört das noch zu diesem Issue?")
- Fragen zur formalen Korrektheit von Garantien

---

### GPT-5.4 — Implementer

**Verantwortung:**
- Implementierung nach Issue-Spec (kein mehr, kein weniger)
- Unit-Tests und metamorphische Tests für alle neuen Module
- Preflight Gates lokal durchführen vor jedem Commit
- Einen Commit pro Issue, mit Issue-Nummer im Commit-Message
- Bei Unklarheiten: Issue kommentieren, nicht selbst entscheiden

**Darf nicht:**
- Scope eigenständig erweitern
- Neue Module einführen, die nicht im Issue spezifiziert sind
- Architekturentscheidungen treffen
- Ohne grüne Preflight Gates commiten und pushen
- Bestehende Tier-1 APIs verändern

**Darf autonom:**
- Alle Preflight Gates bestehen → commit + push ohne Rückfrage
- Interne Implementierungsdetails entscheiden (Variablennamen, Hilfsklassen)
- Tests schreiben, die über die Mindestanforderungen hinausgehen (solange sie grün bleiben)

---

## Workflow

```
┌─────────────────────────────────────────────────────┐
│  1. HEAD-AGENT (Claude)                             │
│     Öffnet GitHub Issue mit:                        │
│     - Problemstellung                               │
│     - Betroffene Module                             │
│     - Acceptance Criteria (messbar, testbar)        │
│     - Nicht-Ziele (was gehört nicht dazu)           │
│     - Hinweise auf Abhängigkeiten                   │
└────────────────────┬────────────────────────────────┘
                     │ Issue ist offen
                     ▼
┌─────────────────────────────────────────────────────┐
│  2. IMPLEMENTER (GPT-5.4)                           │
│     Liest Issue vollständig                         │
│     Implementiert nach Spec                         │
│     Schreibt Tests (Unit + Metamorphic)             │
│     Führt Preflight Gates aus                       │
│     Commitet + pusht (wenn Gates grün)              │
└────────────────────┬────────────────────────────────┘
                     │ Commit auf main
                     ▼
┌─────────────────────────────────────────────────────┐
│  3. HEAD-AGENT (Claude)                             │
│     Reviewt Commit gegen Acceptance Criteria        │
│     Führt eigene Smoke-Tests via MCP durch          │
│     Genehmigt oder öffnet Follow-up Issue           │
│     Aktualisiert new_session_handoff.md             │
│     Öffnet nächstes Issue                           │
└─────────────────────────────────────────────────────┘
```

---

## Issue-Format (Pflicht)

Jedes Issue, das Claude öffnet, muss diese Abschnitte enthalten:

```markdown
## Problem
[Was ist das Problem / die Lücke?]

## Betroffene Module
- `module_a.py`
- `module_b.py`

## Acceptance Criteria
- [ ] Kriterium 1 (messbar)
- [ ] Kriterium 2 (testbar via pytest)
- [ ] Metamorphic test für Invariante X

## Nicht-Ziele
- [Was explizit nicht Teil dieses Issues ist]

## Abhängigkeiten
- Requires: #XX (falls vorhanden)
```

---

## Preflight Gates (beide Agenten)

Vor jedem Commit müssen alle Gates grün sein:

```bash
python -m pytest -q
python -m ruff check logic_brain/ tests/ tools/
python -m mypy --strict logic_brain
python -m pytest --cov=logic_brain --cov-report=term-missing --cov-fail-under=85
python -m pytest -q -m metamorphic
```

Ein Commit mit roten Gates ist eine Protokollverletzung.

---

## Review-Protokoll (Head-Agent)

Nach jedem GPT-5.4-Commit prüft Claude:

1. **Acceptance Criteria:** Sind alle Checkboxen im Issue erfüllbar?
2. **Formale Korrektheit:** Hält die Implementierung, was sie verspricht?
   Insbesondere: Werden Z3-Garantien wirklich über Z3 erbracht?
3. **Scope:** Hat der Implementer Scope hinzugefügt, der nicht im Issue war?
4. **Tests:** Gibt es metamorphische Tests für relationale Invarianten?
5. **API-Stabilität:** Wurden Tier-1 APIs verändert? (→ sofortige Eskalation)

**Bewertung:**
- ✅ Approve → Issue schließen, nächstes Issue öffnen
- 🔧 Minor → Follow-up Issue für kleine Korrekturen
- 🔴 Reject → Issue wieder öffnen mit detailliertem Feedback

---

## Eskalation

Wenn GPT-5.4 auf eine Situation trifft, die im Issue nicht vorgesehen ist:

1. **Issue kommentieren** mit genauer Beschreibung der Unklarheit
2. **Nicht selbst entscheiden** — kein Scope hinzufügen
3. **Claude wartet auf Klärung** bevor Implementierung fortgesetzt wird

Wenn Claude feststellt, dass eine Architekturentscheidung falsch war:

1. Neues Issue öffnen (keine force-push, keine Commits amenden)
2. Bestehenden Commit nicht rückgängig machen — nur vorwärts korrigieren
3. `docs/new_session_handoff.md` mit dem Blocker updaten

---

## WIP-Regel

**Maximal ein Issue gleichzeitig in Arbeit.** Kein Issue wird geöffnet,
bevor das aktuelle committed und reviewed ist. Diese Regel verhindert
Kontext-Verlust und Scope-Drift.

---

## Strategische Grenze

LogicBrain ist ein **Engineering-Projekt bis AGI-Stage 3**.
Kein Issue sollte Module einführen, die Stage 4+ antizipieren wollen,
ohne dass ein konkreter externer Forschungsdurchbruch dies rechtfertigt.
Neue Module brauchen eine explizite Begründung in `vision_and_roadmap.md`.

Referenz: `vision_and_roadmap.md` — Strategischer Nächster Horizont

---

## Schlüsseldokumente

| Dokument | Inhalt |
|----------|--------|
| `docs/agi_roadmap_v2.md` | Theoretischer AGI-Rahmen (Stage 1–5) |
| `docs/logicbrain_development_roadmap.md` | Konkrete Issue-Queue und Milestones |
| `docs/new_session_handoff.md` | Aktueller Stand, WIP, offene Issues |
| `docs/development_process.md` | Kanonischer Workflow (Pflichtlektüre) |
| `docs/formal_guarantees.md` | Was Z3 kann und nicht kann |
| `STABILITY.md` | API-Stabilitätsvertrag (Tier 1–3) |
| `vision_and_roadmap.md` | Strategische Richtung und Motivation |
