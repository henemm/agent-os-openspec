---
entity_id: fix-404-qa-stempel-faelschung
type: bugfix
created: 2026-10-13
updated: 2026-10-13
status: draft
version: "1.0"
tags: [qa-gate, qa-run-stamp, bash-gate, faelschung, f003]
test_targets: ["tests/test_qa_stamp_forgery_404.py"]
---

# QA-Stempel gegen Fälschung per Python-Import schützen — Befund F003 aus #404

## Approval

- [ ] Approved

## GitHub Issue

- **Issue:** #404, nur Befund F003 (MEDIUM). Teil A (Ausrollen), Teil B (`require_run` durchsetzen), F004 (Secrets-Prüfung bei `--run`) und F002 (Randfälle `run_and_capture`) bleiben im Issue offen und sind NICHT Teil dieser Spec.

## Purpose

`qa_run_stamp` (aus #345) soll belegen: „das QA-Gate hat den Testbefehl selbst ausgeführt". `workflow.write_qa_run_stamp(dict)` schreibt aber jedes beliebige dict, ohne Herkunftsprüfung. Ein Agent kann den Stempel mit `python3 -c "from workflow import write_qa_run_stamp; …"` oder aus einer vorher angelegten Skriptdatei fälschen. Heute ist das folgenlos, weil der Stempel noch nirgends gelesen wird; sobald Teil B ihn durchsetzt, wäre er wertlos. Diese Spec schließt die Fälschung auf zwei Ebenen: die Schreibfunktion akzeptiert nur den Prozess `qa_gate.py`, und `bash_gate.py` blockt den sichtbaren Aufruf im Bash-Kommando.

## Source

- **File:** `core/hooks/workflow.py`, `core/hooks/bash_gate.py`
- **Identifier:** `write_qa_run_stamp`, neue Prüffunktion in `bash_gate.py` (Block 3b-Nähe in `main()`)

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `core/hooks/qa_gate.py` (`_write_stamp`) | Module | einziger legitimer Aufrufer, muss unverändert funktionieren |
| `SECRETS_FREETEXT_FLAGS`, `_command_args` in `bash_gate.py` | Funktion | Freitext (Commit-Message, Issue-Body) nicht als Code werten (#30/#53) |
| `docs/specs/feat-345-qa-gate-selbst-ausfuehren.md` | Spec | Known Limitation zu genau diesem Befund |

## Scope

- **Affected Files:** `core/hooks/workflow.py` (~+12 LoC), `core/hooks/bash_gate.py` (~+25 LoC), `tests/test_qa_stamp_forgery_404.py` (neu), `CHANGELOG.md`
- **Estimated Changes:** ~+40 LoC Code, ~+120 LoC Tests
- Nicht im Scope: Lesen/Durchsetzen des Stempels (Teil B), Hash-Gegenprüfung gegen die Ausgabedatei, kryptografische Signatur (verworfen: derselbe OS-Benutzer kann den Schlüssel lesen).

## Implementation Details

**Ebene 1 — Aufrufer-Prüfung (`workflow.py`).** `write_qa_run_stamp` prüft vor dem Schreiben den Einstiegspunkt des Prozesses: `Path(getattr(sys.modules.get("__main__"), "__file__", "") or "").name == "qa_gate.py"`. Trifft das nicht zu (kein `__file__` bei `python3 -c`, anderer Skriptname, interaktiv), wirft die Funktion `PermissionError` mit Hinweis „nur qa_gate.py --run darf den Stempel schreiben", und schreibt nichts. Dasselbe gilt für ein Skript, das `qa_gate.py` nur importiert: Einstiegspunkt ist dann das Skript. `qa_gate.py` fängt den Fehler schon heute still ab (`_write_stamp`); das Verhalten dort bleibt: kein Stempel, kein Absturz.

**Ebene 2 — Bash-Regel (`bash_gate.py`).** Nennt ein Bash-Kommando (nach Entfernen der Freitext-Argumente wie `-m`, `--body`, `--title`) die Namen `write_qa_run_stamp` oder `qa_run_stamp` UND enthält eine Python-Ausführung (`python`/`python3`, `-c`, Heredoc `<<` oder Skriptaufruf), blockt das Gate mit „BLOCKED: QA-Stempel darf nur qa_gate.py --run schreiben". Ohne Python-Ausführung (z. B. `grep qa_run_stamp`, `git log --grep`, `gh issue comment --body "… write_qa_run_stamp …"`) blockt nichts. Der Aufruf `python3 …/qa_gate.py --run` nennt die Namen nicht und bleibt frei.

## Expected Behavior

- **Input:** Aufruf von `write_qa_run_stamp(stamp)` bzw. ein Bash-Kommando.
- **Output:** Aus `qa_gate.py` als Hauptprogramm: Stempel wird geschrieben wie bisher. Aus jedem anderen Einstiegspunkt: `PermissionError`, `qa_run_stamp` bleibt unverändert. Bash-Kommandos mit Stempel-Schreibversuch per Python: Exit 2.
- **Side effects:** keine; der Stempel wird weiterhin nirgends gelesen.

## Known Limitations

- **Ehrliche Restgrenze:** Wer `sys.modules["__main__"]` oder `__file__` bewusst überschreibt, umgeht Ebene 1. Das ist sichtbarer Vorsatz im Code, keine Gate-Garantie. Eine echte Fälschungssicherheit liefert erst die Gegenprüfung beim Lesen (Teil B: `output_sha256` gegen die Datei, Zeitstempel gegen den Lauf).
- Ebene 2 sieht nur, was im Bash-Kommando steht. Ein per Edit/Write angelegtes Skript, das den Namen nur im Dateiinhalt trägt, fängt allein Ebene 1 ab.
- `python3 -m qa_gate` ist kein vorgesehener Aufruf; dabei ist `__main__.__file__` ebenfalls `qa_gate.py`, Ebene 1 lässt es also zu. Das ist unschädlich, weil dort ohnehin das Gate selbst misst.

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] `python3 -c "from workflow import write_qa_run_stamp; write_qa_run_stamp({...})"` schreibt keinen Stempel mehr und wird im Bash-Gate geblockt
- [ ] `python3 …/qa_gate.py --run` schreibt den Stempel weiterhin
- [ ] Ein Issue-Kommentar oder eine Commit-Message, die `write_qa_run_stamp` erwähnt, wird nicht geblockt
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf grün)

## Acceptance Criteria

- **AC-1:** Given ein aktiver Workflow / When `write_qa_run_stamp({...})` aus einem Prozess ohne `qa_gate.py` als Einstiegspunkt (`python3 -c`) aufgerufen wird / Then `PermissionError`, und `qa_run_stamp` im Workflow-State ist unverändert
  - Test: `tests/test_qa_stamp_forgery_404.py::test_python_c_import_is_refused`
- **AC-2:** Given eine Skriptdatei mit beliebigem anderen Namen, die `write_qa_run_stamp` importiert und aufruft / When sie ausgeführt wird / Then `PermissionError`, kein Stempel
  - Test: `tests/test_qa_stamp_forgery_404.py::test_script_file_import_is_refused`
- **AC-3:** Given ein aktiver Workflow und ein konfigurierter Testbefehl / When `qa_gate.py --run` als Hauptprogramm läuft / Then wird `qa_run_stamp` wie bisher geschrieben
  - Test: `tests/test_qa_stamp_forgery_404.py::test_qa_gate_run_still_writes_stamp`
- **AC-4:** Given ein Bash-Kommando `python3 -c "from workflow import write_qa_run_stamp; …"` / When das Bash-Gate es prüft / Then Exit 2 mit Hinweis auf `qa_gate.py --run`
  - Test: `tests/test_qa_stamp_forgery_404.py::test_bash_gate_blocks_python_c_stamp_write`
- **AC-5:** Given ein Bash-Kommando mit Heredoc oder Skriptaufruf (`python3 <<EOF … qa_run_stamp … EOF`), das den Stempel anspricht / When das Bash-Gate es prüft / Then Exit 2
  - Test: `tests/test_qa_stamp_forgery_404.py::test_bash_gate_blocks_heredoc_stamp_write`
- **AC-6:** Given Freitext, der `write_qa_run_stamp` oder `qa_run_stamp` nennt (`gh issue comment --body`, `git commit -m`, `grep qa_run_stamp`) / When das Bash-Gate es prüft / Then wird nicht geblockt
  - Test: `tests/test_qa_stamp_forgery_404.py::test_bash_gate_allows_freetext_mentions`
- **AC-7:** Given der Aufruf `python3 <hooks>/qa_gate.py --run` / When das Bash-Gate ihn prüft / Then wird er nicht geblockt (bestehender Whitelist-Pfad)
  - Test: `tests/test_qa_gate_run_345.py::test_qa_gate_calls_pass_bash_gate`

## Test Plan

Automatische Tests (jeweils an eine AC oben gebunden):
- `pytest tests/test_qa_stamp_forgery_404.py`
- Regression: `pytest tests/test_qa_gate_run_345.py tests/test_bash_gate_*.py`

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Kleine Härtung an zwei vorhandenen Stellen nach bestehendem Muster (Marker-Regeln #30/#53); keine neue Architektur. Kryptografische Signatur wurde geprüft und verworfen (Schlüssel für denselben Benutzer lesbar, Scheinsicherheit).

## Changelog

- 2026-10-13: Initial spec created
