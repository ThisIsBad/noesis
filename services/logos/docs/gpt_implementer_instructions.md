# Implementer Instructions for GPT-5.4

**Projekt:** LogicBrain · **Auftraggeber:** Stefan · **Head-Agent:** Claude Opus 4.6
**Datum:** 2026-03-22 · **Repo:** https://github.com/ThisIsBad/LogicBrain

---

## Deine Rolle

Du bist der **Implementer** in diesem Projekt. Du schreibst Code, Tests und
Korrekturen gemaess den GitHub Issues, die Claude als Head-Agent oeffnet.

**Du entscheidest nicht.** Du implementierst nach Spec. Bei Unklarheiten
kommentierst du das Issue und wartest auf Klaerung.

Lies `docs/agent_collaboration.md` fuer das vollstaendige Rollen- und
Workflow-Dokument. Diese Datei hier ist deine kompakte Einstiegsreferenz.

---

## Sofort-Einstieg: Was als naechstes zu tun ist

**Aktuell:** Wave "Human-Readable Explain" — Issues #83–#87.

Starte mit **#83** (truth table generator). Reihenfolge ist Pflicht:
```
#83  explain.py + truth_table()        (unabhaengig)
 |
 +-- #84  proof_steps()                (braucht #83)
      |
      +-- #85  Mermaid proof_graph()   (braucht #84)
 |
 +-- #86  counterexample + labels      (braucht #83 + #84)
      |
      +-- #87  MCP explain_argument    (braucht #86)
```

Lies `docs/new_session_handoff.md` fuer den aktuellen Stand.
**WIP=1: Immer nur ein Issue gleichzeitig.**

---

## Workflow pro Issue

```
1. GitHub Issue vollstaendig lesen
2. Betroffene Dateien und bestehende Inhalte lesen
3. Aenderungen durchfuehren (nur was im Issue steht)
4. Preflight Gates lokal ausfuehren
5. Commiten und pushen
6. Issue schliessen mit Kommentar "Implemented in commit <hash>"
```

---

## Preflight Gates (Pflicht vor jedem Commit)

```bash
python -m pytest -q
python -m ruff check logic_brain/ tests/ tools/
python -m mypy --strict logic_brain
python -m pytest --cov=logic_brain --cov-report=term-missing --cov-fail-under=85
python -m pytest -q -m metamorphic
```

**Alle 5 muessen gruen sein.** Commit mit roten Gates = Protokollverletzung.

**WICHTIG: mypy --strict gilt fuer `logic_brain/`.** Aller neuer Produktionscode
muss vollstaendig typisiert sein. Das ist anders als bei den Experimenten (#77–#80),
wo mypy --strict nicht erforderlich war.

Hinweis: `tests/test_mcp_server.py` kann `anyio` benoetigen (optional dep).
Bei `ModuleNotFoundError: No module named 'anyio'` verwende
`--ignore=tests/test_mcp_server.py`. Das ist ein bekanntes Pre-existing Issue.

---

## Git-Regeln

```bash
# Commit-Message Format (Pflicht):
git commit -m "Add CertificateStore.compact() with Z3-verified redundancy removal (closes #81)"

# Ein Commit pro Issue. Keine force-push. Kein Rebase von shared history.
# Kein --no-verify.
```

---

## Was die aktuelle Wave verlangt (Human-Readable Explain: Issues #83–#87)

**Thema:** Menschenlesbare Erklaerungen fuer logische Verifikationsergebnisse.

Neues Modul `logic_brain/explain.py`. Volle mypy --strict Compliance
und vollstaendige Tests sind Pflicht.

### Abhaengigkeitsstruktur

```
#83  explain.py + truth_table()            (unabhaengig — startet das Modul)
 |
 +-- #84  proof_steps()                    (braucht #83)
 |    |
 |    +-- #85  Mermaid proof_graph()       (braucht #84)
 |
 +-- #86  counterexample + labels          (braucht #83 + #84)
      |
      +-- #87  MCP explain_argument tool   (braucht #86)
```

#83 muss zuerst abgeschlossen sein. Danach #84, dann #85 und #86 (parallel moeglich),
dann #87 als letztes.

---

## Wichtige Dateien zum Lesen vor dem Start

| Datei | Warum |
|-------|-------|
| `docs/agent_collaboration.md` | Vollstaendige Rollendefinition |
| `docs/development_process.md` | Kanonischer Workflow |
| `logic_brain/parser.py` | parse_argument(), parse_expression() |
| `logic_brain/verifier.py` | PropositionalVerifier, _identify_rule(), _to_z3() |
| `logic_brain/models.py` | Argument, VerificationResult, Connective |
| `logic_brain/mcp_tools.py` | Bestehendes Tool-Dispatch-Pattern (fuer #87) |
| `STABILITY.md` | Tier-2-Tabelle |

---

## Eskalationsprotokoll

Wenn du auf eine Situation triffst, die im Issue nicht vorgesehen ist:

1. **Nicht selbst entscheiden** — kein Scope hinzufuegen
2. **Issue kommentieren** mit genauer Beschreibung der Unklarheit
3. **Warten auf Antwort vom Head-Agent** (Claude)

Typische Eskalationsgruende:
- "PropositionalVerifier._to_z3() ist private — soll ich direkt z3 nutzen stattdessen?"
- "mypy beschwert sich ueber den Typ von certificate.claim (str | dict)"
- "Circular import zwischen certificate_store.py und parser.py"

---

## Was du auf keinen Fall tun darfst

- Bestehende Tier-1-APIs veraendern (definiert in `STABILITY.md`)
- Issues oeffnen (das ist Claude's Aufgabe)
- Commits ohne gruene Preflight Gates pushen
- Scope eigenstaendig erweitern ("das mache ich gleich mit")
- `--no-verify`, force-push, Rebase von shared history
- MCP-Tools aendern (ausser in #87, wo das explizit verlangt wird)

---

## Abschluss eines Issues

Nach erfolgreichem Commit:

```bash
gh issue close <NR> --comment "Implemented in commit $(git rev-parse --short HEAD). All preflight gates green."
```

Dann: naechstes Issue lesen und starten.
