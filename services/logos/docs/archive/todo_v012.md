# LogicBrain - TODO / Session Handoff

Stand: 2026-03-13 (nach Umsetzung der Roadmap-Issues `#6` bis `#17`)

## Aktueller Zustand

- Release `v0.1.1` ist veroffentlicht.
- Teststatus: `144 passed` (lokal verifiziert).
- Roadmap-Issues `#1` bis `#5` sind geschlossen.
- Fokus laut Roadmap: CI + Tooling-Konsolidierung.

## Ergebnis der letzten Session

Abgeschlossen und auf `main` gepusht (Commit `47d82f2`):

- CI eingefuhrt: `.github/workflows/ci.yml` (Python 3.10/3.11, pip cache, `pytest -q`).
- Tooling konsolidiert: `tools/check_lean_results.py`, `tools/check_predicate_results.py`.
- `tools/check_results.py` vereinheitlicht (inkl. `--benchmarks` und `--answers`).
- Legacy-Wrapper umgestellt: `check_lean.py`, `check_predicate.py` (mit Deprecation-Hinweis).
- README aktualisiert (CI-Badge, Local Quickstart, Tooling-Kommandos, Release-Verweis).
- Release-Playbook erstellt: `docs/release_playbook.md` (inkl. Smoke-Test-Matrix).
- GitHub: Issues `#6` bis `#17` angelegt, in Project einsortiert, abgeschlossen.

## Session-Abschluss (2026-03-13)

Diese Session ist abgeschlossen. Der grosse Roadmap-Block (CI + Tooling + Release-Doku)
ist umgesetzt und auf `main` verfuegbar.

### Neustart-Checkliste fuer eine frische Session

1. `git pull` ausfuehren (falls noetig) und auf `main` starten.
2. Kurz pruefen, ob GitHub CI gruen ist (`.github/workflows/ci.yml`).
3. Mit den offenen Punkten unten starten (`C3`, dann `B7`, dann `B8`).
4. Am Ende wieder `todo.md` + `CHANGELOG.md` aktualisieren.

### Operative Annahmen (weiterhin gueltig)

- Python-Versionen fur CI: `3.10` und `3.11`.
- Testkommando: `pytest -q`.
- Installationsweg: `pip install -e ".[dev]"`.
- Legacy-Skripte im Repo bleiben vorerst erhalten, werden aber auf neue Tools verwiesen.
- Kein Release/Tagging ohne explizite Entscheidung.

---

## Sprint-Backlog (aus der Roadmap abgeleitet)

### Phase A - CI stabilisieren (P1, hoch)

- [x] A1: `.github/workflows/ci.yml` erstellen mit Triggern (`push`, `pull_request`).
- [x] A2: Matrix fur Python `3.10` und `3.11` konfigurieren.
- [x] A3: Workflow-Schritte definieren: Checkout, Setup Python, Install, Tests.
- [x] A4: `pip install -e ".[dev]"` im Workflow verankern.
- [x] A5: `pytest -q` im Workflow verankern.
- [x] A6: Fail-fast-Verhalten fur Matrix gepruft (`fail-fast: false` dokumentiert).
- [x] A7: CI-Badge in `README.md` ergaenzt.
- [x] A8: Lokalen Dry-Run der relevanten Befehle durchgefuehrt und dokumentiert.

### Phase B - Tooling konsolidieren (P2, hoch)

- [x] B1: Neues Tool `tools/check_lean_results.py` anlegen (CLI-kompatibel zu `tools/check_results.py`).
- [x] B2: Neues Tool `tools/check_predicate_results.py` anlegen (ohne hartkodierte Nutzerpfade).
- [x] B3: Gemeinsame CLI-Parameter festlegen (Dateipfade als Args, klare Defaults).
- [x] B4: Gemeinsame Ausgabeformate vereinheitlichen (`OK/WRONG/MISS`, Score-Zeile).
- [x] B5: Root-Skript `check_lean.py` als dunnen Wrapper oder mit Deprecation-Hinweis versehen.
- [x] B6: Root-Skript `check_predicate.py` als dunnen Wrapper oder mit Deprecation-Hinweis versehen.
- [x] B7: Optional: `verify_stress.py` an neues Tooling-Muster angleichen.
- [x] B8: Optional: `generate_exam.py`/`hardmode.py`/`escalate.py` auf `logic_brain.generator` evaluieren (nur TODO/Notiz, falls nicht in Stunde schaffbar).

### Phase C - Doku und UX angleichen (P2, mittel)

- [x] C1: `README.md` um Abschnitt "Tooling" mit aktuellen `tools/`-Kommandos erganzen.
- [x] C2: Veraltete Root-Kommandos in README ersetzen oder als legacy markieren.
- [x] C3: Kurze Migrationsnotiz in `CHANGELOG.md` (unreleased) vorbereiten.
- [x] C4: In `todo.md` Status aktualisieren (erledigt/offen + nachste sinnvolle Schritte).

### Phase D - Release-Prozess harten (P3, mittel)

- [x] D1: `docs/release_playbook.md` anlegen (Tagging, Test-Checklist, Release Notes).
- [x] D2: Minimal-Checkliste definieren: Tests, Changelog, Version, Tag, GitHub Release.
- [x] D3: Optionalen `gh`-Befehl fur auto-generierte Notes dokumentieren.

---

## Offene naechste Schritte

1. `#19` umsetzen: sicheren AST-Parser fuer `Z3Session` finalisieren und Regressionen pruefen.
2. `#18` umsetzen: Legacy-Skripte dauerhaft auf `tools/`-Flows migrieren.
3. `#20` umsetzen: FOL-Checker (`tools/check_fol_results.py`) als kanonischen Pfad dokumentieren.

## Definition of Done (Status)

- [x] CI-Workflow-Datei existiert und deckt Python 3.10/3.11 ab.
- [x] Legacy-Tools in `tools/` konsolidiert und kompatible Wrapper vorhanden.
- [x] README zeigt den neuen, bevorzugten Tooling-Pfad.
- [x] Offene Restpunkte sind im TODO dokumentiert.

## Referenzen

- Changelog: `CHANGELOG.md`
- Vision/Roadmap: `vision_and_roadmap.md`
- Extensions-Assessment: `docs/logic_extensions_assessment.md`
- Releases: `https://github.com/ThisIsBad/LogicBrain/releases`
