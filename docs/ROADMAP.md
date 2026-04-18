# Noesis — AGI Stack Roadmap

**Erstellt:** 2026-04-14
**Letzte Revision:** 2026-04-16
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
| **3** | Reflexive Agent | 🔶 | Planning, Persistenz, Kalibrierung, Goal-Governance |
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
| Beobachtbarkeit | Cross-Service-Tracing fehlt | **Kairos** (Querschnitt) |
| Schema-Konsistenz | Geteilte Verträge zwischen Services | **noesis-schemas** (Querschnitt) |

---

## Phase 1 — Stage 3 Foundation

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

**Acceptance Criteria:**
- Recall@10 ≥ 0.80 auf 500 query/expected-pair Benchmark (semantic + episodic)
- Consolidation reduziert Duplikate ≥ 40% ohne Recall-Verlust > 5pp
- p99 Latency `retrieve_memory` ≤ 200ms bei 100k Einträgen
- Schema-Migration ohne Datenverlust für ≥ 2 Versionen rückwärts

---

### Praxis — Planning & Search

**Repo:** `ThisIsBad/praxis` (geplant)
**Stack:** Python 3.12 · NetworkX · Logos-Client · FastAPI · MCP HTTP
**Sprach-Option:** Rust-Reimplementierung erwägen, sobald Search-Latenz
zum Bottleneck wird (siehe [Polyglot-Strategie](#polyglot-strategie)).
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

**Acceptance Criteria:**
- ALFWorld success rate ≥ 50% (Stage 3), ≥ 65% (Stage 4)
- Backtrack-Recovery ≥ 50% auf 50 injizierten Step-Failures
- Plan-Tiefe bis 8 ohne Halluzination von nicht-vorhandenen Tools
- `verify_plan` rejected Pläne ohne Goal-Coverage zu 100%

---

### Telos — Goal Stability Monitor (vorgezogen)

**Repo:** `ThisIsBad/telos` (geplant)
**Stack:** Python 3.12 · SQLite · Logos-Client · FastAPI · MCP HTTP
**Sprach-Option:** Rust-Kandidat — wird auf jeder Action getriggert,
Latenz-kritisch.
**Inspiration:** Hubinger et al. (2019) — Mesa-Optimization

Telos wurde gegenüber dem Original-Plan **vorgezogen**: sobald Mneme + Praxis
laufen, kann Goal-Drift entstehen. Ohne paralleles Monitoring entwickelt sich
das System ungovernt.

Registrierte Ziele mit Logos GoalContract. Jede Aktion wird gegen aktive
Ziele geprüft. Drift-Score-Tracking über Zeit.

| MCP-Tool | Funktion |
|----------|----------|
| `register_goal` | Ziel mit GoalContract aktivieren |
| `check_action_alignment` | Aktion vs. aktive Ziele bewerten |
| `get_drift_score` | Drift-Trend über Zeitfenster |
| `list_active_goals` | Alle aktiven Ziele mit Status |

**Acceptance Criteria:**
- Drift-Detection ≥ 80% auf 50 gesäte goal-misalignment cases
- False-positive rate ≤ 10% auf 200 aligned actions
- p99 Latency `check_action_alignment` ≤ 50ms (Hot-Path!)

---

## Phase 2 — Stage 3 Completion

### Episteme — Metakognition & Kalibrierung

**Repo:** `ThisIsBad/episteme` (geplant)
**Stack:** Python 3.12 · SQLite · scipy · FastAPI · MCP HTTP

Verfolgt Konfidenz vs. tatsächliche Korrektheit über Zeit.

| MCP-Tool | Funktion |
|----------|----------|
| `log_prediction` | Vorhersage mit Konfidenz + Domäne speichern |
| `log_outcome` | Tatsächliches Ergebnis nachbuchen |
| `get_calibration` | ECE, Bias, Sharpness pro Domäne |
| `should_escalate` | Eskalations-Entscheidung bei niedriger Konfidenz |
| `get_competence_map` | Systematische Stärken/Schwächen |

**Acceptance Criteria:**
- ECE ≤ 0.10 über 200 diverse Claims (Stage 3 Standard)
- Brier-Score ≤ 0.20 pro Domäne
- Competence-Map identifiziert ≥ 3 systematische Schwächen nach 500 Predictions

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

**Acceptance Criteria:**
- Korrekte Intervention-Effekte auf 30 synthetischen DAGs (≥ 90% match mit ground truth)
- Counterfactual-Konsistenz: gleiche Query → gleiche Antwort über 100 runs
- Erkennt Confounder in 10/10 klassischen Pearl-Beispielen

---

## Phase 3 — Stage 4: Learning Agent

### Empiria — Erfahrungs-Akkumulation

**Repo:** `ThisIsBad/empiria` (geplant)
**Stack:** Python 3.12 · SQLite · ChromaDB · FastAPI · MCP HTTP
**Inspiration:** Reflexion (Shinn et al., 2023)

Jede Aktion wird mit Outcome gespeichert. Mustererkennung über ähnliche
Erfahrungen. Lessons abrufbar für zukünftige Tasks.

**Acceptance Criteria:**
- Lesson-Retrieval verbessert Task-Success ≥ 15pp gegenüber Baseline (no-lesson)
- Pattern-Mining identifiziert ≥ 80% wiederkehrender Failure-Modes nach 200 Episoden
- Setzt valide Episteme-Kalibrierung voraus (`should_escalate` ≥ 0.7 Genauigkeit)

---

### Techne — Verified Skill Library

**Repo:** `ThisIsBad/techne` (geplant)
**Stack:** Python 3.12 · ChromaDB · SQLite · Logos-Client · FastAPI · MCP HTTP
**Inspiration:** Voyager (Wang et al., 2023)

Bewährte Strategien als verifizierte, wiederverwendbare Skills. Nur Skills
mit Logos-ProofCertificate erhalten `verified=True`.

**Acceptance Criteria:**
- Skill-Reuse-Rate ≥ 30% nach 100 Tasks
- Verified-Skill-Anteil ≥ 60% (über Logos certified)
- Cross-Session-Transfer: Skills aus Session A verbessern Session B um ≥ 10pp

---

## Phase 4 — Querschnittskomponenten

Diese sind keine kognitiven Services, sondern Infrastruktur. Sie sollten
**parallel zu Phase 1** entstehen, nicht nachgelagert.

### noesis-schemas — Shared Contracts

**Repo:** `ThisIsBad/noesis-schemas` (geplant, Prio 0)
**Stack:** JSON Schema + generierte Bindings (Python `pydantic`, Rust `serde`)

Geteilte Datenverträge zwischen Services: `ProofCertificate`, `GoalContract`,
`Memory`, `Plan`, `Skill`, `Lesson`. Verhindert Schema-Drift bei 8+ Services.

Versioniert via SemVer; jeder Service pinnt eine Schema-Version.

### noesis-eval — Reproduzierbares Benchmark-Harness

**Repo:** `ThisIsBad/noesis-eval` (geplant)
**Stack:** Python 3.12 · pytest · Docker

Führt die Acceptance-Benchmarks (ARC-AGI, ALFWorld, WebArena, ECE-Suite,
Drift-Suite) reproduzierbar gegen die deployed Services aus. Ohne dieses
Repo bleiben die Acceptance Criteria oben Lippenbekenntnis.

### Kairos — Observability & Tracing

**Repo:** `ThisIsBad/kairos` (geplant)
**Stack:** Python 3.12 · OpenTelemetry · ClickHouse oder Tempo · FastAPI

Cross-Service-Tracing: jeder Claude-Tool-Call bekommt eine Trace-ID, die
durch alle nachfolgenden Service-Calls propagiert wird. Misst Latency,
Token-Cost, Cache-Hits, Verifikations-Round-Trips.

Bei 8 Services ist Debugging ohne Tracing blind.

---

## Build-Priorität (revidiert)

| Prio | Service | Lücke | Phase | Aufwand |
|------|---------|-------|-------|---------|
| **0** | noesis-schemas | Schema-Drift | Querschnitt | Niedrig |
| **0** | noesis-eval | Falsifizierbarkeit | Querschnitt | Mittel |
| **1** | Mneme | Persistenz | 1 | Mittel |
| **2** | Kairos | Observability | Querschnitt | Mittel |
| **3** | Praxis | Planning | 1 | Mittel–Hoch |
| **4** | Telos | Goal-Drift (vorgezogen!) | 1 | Mittel |
| **5** | Episteme | Kalibrierung | 2 | Niedrig |
| **6** | Kosmos | Kausalität | 2 | Hoch |
| **7** | Empiria | Lernen | 3 | Niedrig |
| **8** | Techne | Skills | 3 | Mittel |

**Änderungen ggü. v1:**
- Telos von Prio 7 auf Prio 4 (Goal-Drift entsteht ab Tag 1 mit Praxis)
- Episteme vor Empiria/Techne (Kalibrierung ist Voraussetzung für Lesson-Quality)
- Schemas + Eval als Prio 0 (sonst Tech-Debt-Spirale)
- Kairos von Prio 5 auf Prio 2: Structured Logging muss stehen, bevor Praxis/Telos
  Daten erzeugen, die Episteme später für Calibration braucht. Retrofitten von
  Observability nach 4 Services ist teurer als Prebuild.

## Build-Strategie: Skeleton-First

Die obige Prio-Tabelle ist **nicht linear abzuarbeiten**. Die kognitiven Services
haben zyklische Abhängigkeiten:

- Logos kann nicht selbst-kalibrieren ohne Outcome-Daten aus Episteme/Telos/Praxis.
- Mnemes Belief-Graduation (`certificate` setzen) braucht einen laufenden Logos.
- Praxis kann keine Lessons ziehen ohne Empiria, die wiederum auf
  Episteme-Kalibrierung angewiesen ist.

**Konsequenz:** Alle neun Services bekommen von Tag 1 eine Stub-Implementierung
mit vollständigem MCP-Interface, minimaler Logik. Die Prio-Reihenfolge oben
beschreibt nur, **wo zuerst Production-Quality investiert wird** — nicht, wann
ein Service überhaupt existieren darf.

**Beispiele für Stubs:**
- Mneme: ChromaDB-Store, Retrieval, aber ohne Consolidation-Tuning.
- Logos: existiert bereits (✅) — keine Stub-Phase nötig.
- Episteme: loggt Predictions/Outcomes in SQLite, liefert hardcoded
  `ConfidenceLevel.UNKNOWN` zurück bis genug Daten da sind.
- Telos: registriert Goals, `check_action_alignment` gibt pauschal `aligned=true`
  zurück bis echte Drift-Metriken implementiert sind.
- Kosmos/Empiria/Techne: leere MCP-Endpoints, die `NotImplementedError`-Payloads
  zurückgeben, aber die Schema-Verträge aus `noesis-schemas` respektieren.

**Vorteile:**
- End-to-End-Datenfluss wird früh sichtbar (Claude → Telos → Praxis → Logos → Mneme).
- Integrations-Probleme (SSE-Setup, Schema-Drift, mTLS) tauchen früh auf.
- Feedback-Loops sammeln Daten, während Services crude sind — Episteme baut
  Baseline-Kalibrierung aus Stub-Outputs, bevor die richtige Logik live geht.
- Kein "Service-Insel"-Problem, bei dem ein fertiger Service monatelang auf
  einen Caller wartet.

**Regel:** Prio 0–2 in Production-Quality. Prio 3+ als Stub mit vollständigem
Interface, Production-Reife inkrementell nach Prio-Reihenfolge.

---

## Stage 3 Acceptance Criteria (Ziel Phase 1+2)

| Kriterium | Benchmark | Schwellwert | Owner-Service |
|-----------|-----------|-------------|---------------|
| Novel task generalization | ARC-AGI | ≥ 50% | Praxis + Mneme |
| Self-evaluation calibration | ECE auf 200 Claims | ≤ 0.10 | Episteme |
| Multi-step planning | ALFWorld | ≥ 50% | Praxis |
| Multi-step planning (web) | WebArena | ≥ 40% (Stage 3), ≥ 60% (Stage 4) | Praxis |
| Error self-detection | 100 gesäte Fehler | ≥ 30% erkannt | Episteme + Praxis |
| Replanning after failure | Re-attempt success rate | ≥ 50% | Praxis |
| Goal-drift detection | 50 misalignment cases | ≥ 80% erkannt | Telos |

**Anpassung:** WebArena ≥ 60% war für Stage 3 unrealistisch (über aktuellem
SOTA). Auf 40% (Stage 3) / 60% (Stage 4) gestaffelt.

---

## Polyglot-Strategie

Default: **Python**, wegen Ökosystem (ChromaDB, pgmpy, scipy, MCP-SDK-Reife).

**Rust-Kandidaten** (nicht zwingend, aber begründet):

| Service | Begründung | Trigger für Migration |
|---------|------------|------------------------|
| **Praxis** | Tree-of-Thoughts/Graph-Search ist CPU-bound; `petgraph` > NetworkX | p99 Search-Latenz > 1s |
| **Telos** | Hot-Path: jede Action triggert `check_action_alignment` | p99 > 50ms anhaltend |
| **Logos (Hot-Path)** | Z3 hat solide Rust-Bindings (`z3.rs`); nur `z3_check` extrahieren | Verifikation > 100ms p99 |

**Nicht migrieren:**
- Mneme, Kosmos, Empiria, Techne — abhängig von Python-only Libraries
- Logos-Hauptservice — funktioniert; Rewrite-Kosten > Nutzen

**Voraussetzung für Polyglot:** `noesis-schemas` als sprach-agnostischer
Vertrag (JSON Schema generiert Pydantic + Serde Bindings).

**Regel:** Erst messen, dann migrieren. Keine Rewrites auf Verdacht.

---

## Kommunikations-Pattern (revidiert)

**Default:** Claude orchestriert; keine direkte Service-zu-Service-Kommunikation.

**Ausnahme — Logos als Verifikations-Sidecar:** Services dürfen Logos
direkt aufrufen für **read-only, idempotente** Verifikations-Calls
(`certify_claim`, `z3_check`, `check_policy`, `verify_argument`).

**Begründung:** Der Roundtrip Mneme → Claude → Logos → Claude → Mneme
kostet 4× Token-Latenz. Bei häufiger Verifikation wird das prohibitiv.

**Bedingungen für Direct-Calls:**
1. Nur Logos darf Empfänger sein
2. Nur read-only Tools (kein `assume`, kein State-Mutation)
3. Audit-Log via Kairos (Trace-ID propagiert)
4. Authenticated via Railway-internal mTLS oder API-Key

State-Mutationen (`store_memory`, `register_goal`, `commit_step`) bleiben
strikt Claude-orchestriert.

---

## Test-Strategie

Pro Service (siehe `architecture.md`):
- Unit-Tests, Coverage ≥ 85%
- Ruff + Mypy strict

**Neu — Cross-Service Integration:**
- `noesis-eval` Repo führt End-to-End-Szenarien aus, die ≥ 3 Services touchen
- Mindestens ein E2E-Szenario pro Phase als Release-Gate
- Beispiel-Szenario: „Goal registrieren (Telos) → Plan dekomponieren (Praxis)
  → Plan verifizieren (Logos) → Outcome speichern (Mneme) → Lesson extrahieren (Empiria)"

---

## Changelog

| Datum | Änderung |
|-------|----------|
| 2026-04-14 | Noesis Hub angelegt, Roadmap aus Logos-Repo überführt |
| 2026-04-16 | Per-Service Acceptance Criteria; Telos vorgezogen (Prio 3); Episteme vor Empiria; Schemas/Eval/Kairos als Querschnitts-Komponenten; Polyglot-Strategie (Rust für Praxis/Telos/Logos-Hot-Path); Logos-Sidecar für read-only Verifikation; WebArena-Schwelle realistischer gestaffelt |
| 2026-04-18 | Kairos auf Prio 2 vorgezogen (Observability muss vor Feedback-Datenproduzenten stehen); Skeleton-First-Strategie explizit (alle Services ab Tag 1 als Stub mit vollständigem MCP-Interface, Production-Reife nach Prio-Reihenfolge); `ClaimKind` in `noesis-schemas.Memory` als Routing-Hint für Logos-Graduation |
