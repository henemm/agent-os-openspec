# Fast Track: Fehlalarm-Paket aus der Backlog-Triage (#335, #353, #347, #185)

## Problem

Die Backlog-Triage vom 2026-10-05 fand vier Stellen, an denen das Framework Arbeit aufhält oder
falsch auskunftet: Go-Testdateien gelten als Produktivcode (#335), eine unlesbare Datei bricht
`--command-aliases` ab (#353), das QA-Gate wertet grüne Läufe in Randfällen rot (#347), und ein
veralteter Haupt-Ordner bleibt beim Sitzungsstart unsichtbar (#185). PO-Vorgabe: als Tech Lead
ohne Workflow umsetzen; Fast Track, weil jede Änderung lokal, klein und per Test belegt ist.

## Scope

- `core/hooks/hook_utils.py`, `core/hooks/edit_gate.py`, `core/hooks/config_loader.py`: Testdatei-Muster
- `setup.py`: `_read_or_none` in `generate_command_aliases`
- `core/hooks/qa_gate.py`: Marker-Form, node-Blöcke, Plausibilität
- `core/hooks/session_banner.py`, `config.yaml`: Rückstands-Warnung
- Nicht enthalten: #292 (Sicherheitsabwägung, PO-Entscheidung offen)

## Definition of Done

Jeder Befund ist durch einen Test belegt, der ohne die Änderung rot ist; die volle Suite bleibt grün.

## Acceptance Criteria

- **AC-1:** Given ein Workflow in phase5_tdd_red, When `notified_test.go` angelegt wird, Then erlaubt edit_gate das; `notified.go` und `test_helpers.go` bleiben blockiert.
- **AC-2:** Given eine Nicht-UTF-8-Datei `50-implement.md` im Befehlsordner, When `setup.py --command-aliases` läuft, Then endet der Lauf mit Exit 0, die Datei bleibt unverändert und die übrigen Aliase entstehen.
- **AC-3:** Given ein grüner node- oder unittest-Lauf, dessen Testname oder Docstring „TEST FAILED“ enthält, When qa_gate ihn prüft, Then ist das Ergebnis grün; die echte Form `** TEST FAILED **` bleibt rot.
- **AC-4:** Given zwei node-Summaries ohne Trennzeile oder eine Summary mit unplausiblen Zahlen, When qa_gate sie prüft, Then ist das Ergebnis nicht grün.
- **AC-5:** Given ein Haupt-Ordner zwei Commits hinter origin/main, When eine Sitzung im Haupt-Ordner oder in einem Worktree startet, Then nennt der Banner die Zahl und `sync-main`; scheitert der Fetch, erscheint keine Zeile.

## Test Plan

- `tests/test_test_file_patterns_335.py` (AC-1), `tests/test_alias_robust_350.py` (AC-2)
- `tests/test_qa_gate_edge_cases_347.py` (AC-3, AC-4), `tests/test_banner_behind_origin_185.py` (AC-5)
- Volle Suite
