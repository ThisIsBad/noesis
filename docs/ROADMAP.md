# Noesis — AGI Stack Roadmap

**Erstellt:** 2026-04-14  
**Basis:** `logos/docs/agi_roadmap_v2.md` (Claude Opus 4.6, 2026-03-20)

---

## Kernthese

> AGI entsteht nicht durch Skalierung allein. Ein plausiblerer Pfad ist eine
> koordinierte kognitive Architektur: Foundation Model + persistentes Gedächtnis
> + Planning + Verifikation + Grounding + aktives Lernen + Ziel-Governance.

LLMs sind probabilistische Token-Generatoren. Sie brauchen deterministische
Leitplanken. Noesis liefert diese Leitplanken als eigenständige MCP-Services.

---

## AGI Stage Map

| Stage | Bezeichnung | Status | Schlüssel-Capabilities |
|-------|-------------|--------|------------------------|
| **1** | Language Agent | ✅ | MMLU ≥ 85%, HumanEval ≥ 85% |
| **2** | Tool Agent | ✅ | MCP-Tools, Logos deployed |
| **3** | Reflexive Agent | 🔶 | Planning, Persistenz, Kalibrierung |
| **4** | Learning Agent | 🔬 | Episodisches Lernen, Skill-Akkumulation |
| **5** | General Cognitive | 🔭 | Cross-Domain Transfer, stabile Agency |

---

## Gap-Analyse

| Gap | Warum LLMs allein nicht reichen | Noesis-Service |
|-----|----------------------------------|----------------|
| Verifikation | Plausibel ≠ korrekt | **Logos** ✅ |
| Ziel-Governance | Ohne explizite Ziel-Repräsentation: Drift | **Logos** + **Telos** |
| Persistentes Gedächtnis | Context Windows ephemer, kein Lifelong Learning | **Mneme** |
| Planning & Search | Autoregressive Planung, kein State-Space-Search | **Praxis** |
| Selbst-Modellierung | Kalibrierung strukturell lösbar, aber nicht nativ | **Episteme** |
| Welt-Modellierung | Korrelationen ≠ Kausalstruktur | **Kosmos** |
| Aktives Lernen | Kein Exploration-Exploitation-Loop nach Deployment | **Empiria** |
| Skill-Akkumulation | Strategien nicht persistent speicherbar | **Techne** |

---

## Phase 1 — Stage 3 Completion

### Mneme — Persistentes Gedächtnis

**Repo:** `ThisIsBad/mneme` (geplant)  
**Stack:** Python 3.12 · ChromaDB · SQLite · FastAPI · MCP HTTP

Episodisches Gedächtnis (Was ist wann passiert?) + semantisches Gedächtnis
(Was ist wahr/bekannt?). Memories mit Logos-ProofCertificate erhalten `proven=True`.

| MCP-Tool | Funktion |
|----------|----------|
| `store_memory` | Inhalt mit Typ, Konfidenz, optionalem Proof-Zertifikat speichern |
| `retrieve_memory` | Semantische Suche (k-nearest, min_confidence) |
| `consolidate` | Ähnliche Memories zusammenfassen |
| `forget` | Memory mit Begründung löschen (Audit-Trail) |
| `list_proven_beliefs` | Alle via Logos verifizierten Memories |

---

### Praxis — Planning & Search

**Repo:** `ThisIsBad/praxis` (geplant)  
**Stack:** Python 3.12 · NetworkX · Logos-Client · FastAPI · MCP HTTP  
**Inspiration:** Tree of Thoughts (Yao et al., 2023), RAP (Hao et al., 2023)

Hierarchische Ziel-Dekomposition mit Tree-of-Thoughts Search und Backtracking.
Pläne werden via Logos GoalContract verifiziert.

| MCP-Tool | Funktion |
|----------|----------|
| `decompose_goal` | Goal → Sub-Goals → Steps |
| `evaluate_step` | Machbarkeit + Risiken eines Schritts |
| `backtrack` | Alternative Pfade nach Fehler |
| `verify_plan` | Logos GoalContract-Check |
| `commit_step` | Schritt als ausgeführt markieren + Outcome speichern |

---

## Phase 2 — Stage 3→4 Bridge

### Episteme — Metakognition & Kalibrierung

**Repo:** `ThisIsBad/episteme` (geplant)  
**Stack:** Python 3.12 · SQLite · scipy · FastAPI · MCP HTTP

Verfolgt Konfidenz vs. tatsächliche Korrektheit über Zeit.
Ziel: ECE ≤ 0.10 über 200 diverse Claims (Stage 3 Acceptance Criterion).

| MCP-Tool | Funktion |
|----------|----------|
| `log_prediction` | Vorhersage mit Konfidenz + Domäne speichern |
| `log_outcome` | Tatsächliches Ergebnis nachbuchen |
| `get_calibration` | ECE, Bias, Sharpness pro Domäne |
| `should_escalate` | Eskalations-Entscheidung bei niedriger Konfidenz |
| `get_competence_map` | Systematische Stärken/Schwächen |

---

### Kosmos — Kausales World-Model

**Repo:** `ThisIsBad/kosmos` (geplant)  
**Stack:** Python 3.12 · NetworkX · pgmpy · Logos-Client · FastAPI · MCP HTTP  
**Inspiration:** Pearl (2000, 2009), Schölkopf et al. (2021)

Kausalgrafen mit Do-Calculus (Pearl's 3 Ebenen: Assoziation → Intervention → Kontrafaktisch).

| MCP-Tool | Funktion |
|----------|----------|
| `add_causal_edge` | Kausal-Beziehung hinzufügen |
| `compute_intervention` | do(X=x) → Downstream-Effekte |
| `counterfactual` | Was wäre passiert wenn...? |
| `query_causes` | Kausalkette für einen Effekt |

---

## Phase 3 — Stage 4: Learning Agent

### Empiria — Erfahrungs-Akkumulation

**Repo:** `ThisIsBad/empiria` (geplant)  
**Stack:** Python 3.12 · SQLite · ChromaDB · FastAPI · MCP HTTP  
**Inspiration:** Reflexion (Shinn et al., 2023)

Jede Aktion wird mit Outcome gespeichert. Mustererkennung über ähnliche
Erfahrungen. Lessons abrufbar für zukünftige Tasks.

---

### Techne — Verified Skill Library

**Repo:** `ThisIsBad/techne` (geplant)  
**Stack:** Python 3.12 · ChromaDB · SQLite · Logos-Client · FastAPI · MCP HTTP  
**Inspiration:** Voyager (Wang et al., 2023)

Bewährte Strategien als verifizierte, wiederverwendbare Skills. Nur Skills
mit Logos-ProofCertificate erhalten `verified=True`.

---

### Telos — Goal Stability Monitor

**Repo:** `ThisIsBad/telos` (geplant)  
**Stack:** Python 3.12 · SQLite · Logos-Client · FastAPI · MCP HTTP  
**Inspiration:** Hubinger et al. (2019) — Mesa-Optimization

Registrierte Ziele mit Logos GoalContract. Jede Aktion wird gegen aktive
Ziele geprüft. Drift-Score-Tracking über Zeit.

---

## Build-Priorität

| Prio | Service | Lücke | Aufwand |
|------|---------|-------|---------|
| **1** | Mneme | Persistenz | Mittel |
| **2** | Praxis | Planning | Mittel–Hoch |
| **3** | Episteme | Kalibrierung | Niedrig |
| **4** | Kosmos | Kausalität | Hoch |
| **5** | Empiria | Lernen | Niedrig |
| **6** | Techne | Skills | Mittel |
| **7** | Telos | Drift | Niedrig |

---

## Stage 3 Acceptance Criteria (Ziel Phase 1+2)

| Kriterium | Benchmark | Schwellwert |
|-----------|-----------|-------------|
| Novel task generalization | ARC-AGI | ≥ 50% |
| Self-evaluation calibration | ECE auf 200 Claims | ≤ 0.10 |
| Multi-step planning | ALFWorld / WebArena | ≥ 60% |
| Error self-detection | 100 gesäte Fehler | ≥ 30% erkannt |
| Replanning after failure | Re-attempt success rate | ≥ 50% |

---

## Changelog

| Datum | Änderung |
|-------|----------|
| 2026-04-14 | Noesis Hub angelegt, Roadmap aus Logos-Repo überführt |
