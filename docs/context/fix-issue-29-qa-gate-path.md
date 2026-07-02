# Context: fix-issue-29-qa-gate-path

## Request Summary
Issue #29: `core/hooks/qa_gate.py` löst den Pfad zu `workflow.py` über `find_plugin_root()` auf statt über den eigenen Skript-Pfad. Dadurch wird `adversary_verdict` in Consumer-Projekten nie (oder gegen die falsche `workflow.py`-Version) geschrieben, obwohl `qa_gate.py` Erfolg meldet — Fehler wird durch `capture_output=True` ohne Return-Code-Check verschluckt.

## Related Files
| File | Relevance |
|------|-----------|
| `core/hooks/qa_gate.py` | Enthält den Bug: 3 Stellen (Zeile 34, 47, 112, 138) nutzen `_plugin_root / "core" / "hooks" / "workflow.py"` statt `Path(__file__).parent / "workflow.py"` |
| `core/hooks/hook_utils.py` | `find_plugin_root()` (Zeile 301-310): liefert bei gesetztem `CLAUDE_PLUGIN_ROOT` die generische Plugin-Installation zurück (nicht das projekteigene, evtl. geforkte `workflow.py`); ohne Env-Var einen Fallback-Pfad, der in Consumer-Projekten nicht existiert |
| `core/hooks/workflow.py` | Liegt als Geschwisterdatei neben `qa_gate.py` im selben Verzeichnis (sowohl im Framework-Repo unter `core/hooks/` als auch nach `setup.py`-Installation in Consumer-Projekten unter `.claude/hooks/`) — genau das sollte referenziert werden |

## Existing Patterns
- Andere Hooks (`edit_gate.py`, `bash_gate.py`) nutzen ebenfalls `find_project_root()`/`find_plugin_root()` aus `hook_utils.py`, aber nicht zur Auflösung von Geschwister-Skripten — nur zur Root-Erkennung für State-/Spec-Dateien. Der `qa_gate.py`-Fall ist ein Sonderfall: er ruft ein *anderes Skript im selben Verzeichnis* auf, wofür `Path(__file__).parent` der korrekte, robuste Ansatz ist (funktioniert unabhängig von `CLAUDE_PLUGIN_ROOT`-Zustand oder Installationsart).
- Bereits im Issue vorgeschlagene Lösung: `workflow_py = Path(__file__).parent / "workflow.py"`.
- Tests in `tests/` nutzen echte Subprocess-Aufrufe (kein Mocking von `workflow.py`), z.B. `tests/test_gate_coverage.py` patcht nur `config_loader.load_config`, ruft aber reale Funktionen direkt auf. Für den Regressionstest ist ein echter Subprocess-Test gegen ein `tmp_path`-Fake-Workflow-Verzeichnis sinnvoll (mock-frei, wie im Issue gefordert).

## Dependencies
- Upstream: `qa_gate.py` wird typischerweise am Ende von `/40-tdd-red` bzw. `/50-implement`/Adversary-Flow aufgerufen, um `adversary_verdict` zu setzen (`workflow.py set-field adversary_verdict <verdict>`).
- Downstream: `bash_gate.py` prüft bei `git commit`, ob ein `VERIFIED`-Verdict im Workflow-State vorliegt. Wenn `qa_gate.py` das Verdict nie schreibt, blockiert `bash_gate.py` Commits fälschlich dauerhaft (oder lässt in schlimmeren Fällen ungeprüfte Commits durch, falls die Prüfung anders herum fehlschlägt — zu verifizieren, aber nicht Teil dieses Fixes).

## Existing Specs
- Keine dedizierte Spec zu `qa_gate.py` in `docs/specs/` gefunden (reines Hook-Tooling, siehe Scope im Issue: "Reines `.claude/hooks/qa_gate.py`-Tooling, kein Produktcode").

## Risks & Considerations
- Der Fix betrifft 3 Stellen im selben File (Zeile 47 in `_set_verdict()`, Zeile 112 in `--check`-Branch, Zeile 138 in `main()` für Workflow-Namen-Ermittlung) — alle sollten konsistent auf `Path(__file__).parent / "workflow.py"` umgestellt werden.
- Issue fordert zusätzlich: Return-Code von `subprocess.run(...)` in `_set_verdict()` prüfen und bei Fehler laut fehlschlagen, statt `capture_output=True` den Fehler verschlucken zu lassen.
- `find_plugin_root`-Import wird nach dem Fix in `qa_gate.py` evtl. ungenutzt — prüfen und ggf. entfernen (kein totes Zeug stehen lassen).
- Verwandt zu bereits behobenem Issue #960 (Adversary-Gate-Bypass, PR #27, siehe Memory) — gleiche Kategorie "Verdict wird nicht zuverlässig persistiert", aber anderer Root Cause (Pfadauflösung statt Bypass-Logik).
- Dieses Repo (agent-os-openspec) ist selbst das Framework — hier existiert `core/hooks/workflow.py`, der Bug manifestiert sich primär in Consumer-Projekten nach Plugin-Installation (dort liegt `workflow.py` unter `.claude/hooks/`). Der Regressionstest muss das simulieren (z.B. `qa_gate.py` aus einem anderen Arbeitsverzeichnis mit `CLAUDE_PLUGIN_ROOT` auf einen Fake-Pfad gesetzt aufrufen, oder direkt die Pfadauflösungs-Logik isoliert testen).

## Analysis

### Type
Bug

### Root Cause (bestätigt durch bug-intake + Plan/Sonnet Review)
`qa_gate.py` löst `workflow.py` über `find_plugin_root()` auf. Diese Funktion geht bei fehlendem `CLAUDE_PLUGIN_ROOT` von `Path(__file__).parent.parent.parent` **relativ zu `hook_utils.py`** aus und setzt eine `core/hooks/`-Verschachtelung voraus. `setup.py` kopiert Hook-Dateien aber **flach** nach `.claude/hooks/` in Consumer-Projekten — dort zeigt `_plugin_root/"core"/"hooks"/"workflow.py"` ins Leere. Downstream blockiert `bash_gate.py` Commits dauerhaft, weil `adversary_verdict` nie `VERIFIED` wird (Fail-Closed, kein Security-Bypass, aber ein blockierender Produktivitätsbug). Im Framework-Repo selbst (hier) tritt der Bug NICHT auf, weil `core/hooks/`-Nesting zufällig existiert — daher reproduziert ein In-Repo-Test den Bug nicht.

### Affected Files (with changes)
| File | Change Type | Description |
|------|-------------|-------------|
| `core/hooks/qa_gate.py` | MODIFY | 3× `workflow_py = _plugin_root / "core" / "hooks" / "workflow.py"` → `Path(__file__).parent / "workflow.py"` (Zeilen 47, 112, 138); Return-Code-Check in `_set_verdict()` und `main()`-Status-Abfrage ergänzen; toten Import (`find_project_root`, `find_plugin_root`) und ungenutzte `_root`/`_plugin_root`-Variablen entfernen |
| `tests/test_qa_gate.py` | CREATE | Regressionstest (siehe unten) |

### Scope Assessment
- Files: 2 (1 Fix, 1 neuer Test)
- Estimated LoC: ~10-15 (Fix) + ~40-70 (Test)
- Risk Level: LOW — `_set_verdict()` wird nur intern in `qa_gate.py` aufgerufen, kein anderer Hook nutzt `find_plugin_root()` für Geschwister-Skript-Auflösung, Blast Radius auf diese Datei beschränkt

### Technical Approach
`Path(__file__).parent / "workflow.py"` an allen 3 Stellen — korrekt, da `workflow.py` garantiert Geschwisterdatei ist (Framework-Repo und Consumer-Install gleichermaßen). Return-Code-Check und Pfad-Fix im selben Commit (derselbe Silent-Failure-Mechanismus, minimaler Umfang, kein Overhead durch Split). Toten Import im selben Commit entfernen.

### Regressionstest-Design (mock-frei, Subprocess-Pattern)
Muss die Consumer-Installation simulieren, sonst reproduziert der Test den Bug nicht:
1. `tmp_path` als Fake-Projekt mit `.claude/workflows/<name>.json` (aktiver Workflow, `adversary_verdict: null`)
2. `qa_gate.py`, `workflow.py`, `hook_utils.py`, `config_loader.py`, `override_token.py` **flach** nach `tmp_path/fake_hooks/` kopieren (simuliert `.claude/hooks/`-Flat-Layout ohne `core/hooks/`-Nesting)
3. Gültige "PASSED"-Test-Output-Datei erzeugen
4. `qa_gate.py` per `subprocess.run` aus `fake_hooks/` mit `CLAUDE_PROJECT_DIR=tmp_path`, `OPENSPEC_ACTIVE_WORKFLOW=<name>` aufrufen
5. Assertion: `returncode == 0` UND State-JSON enthält `"adversary_verdict": "VERIFIED:..."` (nicht `None`)
6. Zweiter Testfall: `workflow.py` im Fake-Verzeichnis fehlt → `qa_gate.py` muss jetzt laut fehlschlagen (returncode != 0 / stderr-Meldung), nicht mehr "Commit is now allowed." bei stillem Subprocess-Fehler ausgeben

### Dependencies
Keine externen Abhängigkeiten, unabhängig von Issue #960 (anderer Root Cause, siehe Memory `project_issue960_adversary_gate_bypass`).

### Open Questions
Keine offenen Fragen — Scope ist klar begrenzt und vollständig verstanden.
