# Context: fix-404-qa-stempel-faelschung

## Request Summary
#404 Befund F003 (MEDIUM): Der Stempel `qa_run_stamp` (Beleg „das Gate hat selbst gemessen“, aus #345) lässt sich
per Python-Import fälschen. Nur dieser Befund; Teil A (Ausrollen), Teil B (`require_run` durchsetzen), F004
(Secrets-Prüfung bei `--run`) und F002 (Randfälle `run_and_capture`) bleiben im Issue.

## Ist-Zustand (belegt)
- `core/hooks/workflow.py:411` `write_qa_run_stamp(stamp: dict)` nimmt jedes dict, holt den aktiven Workflow und
  schreibt `data["qa_run_stamp"]` über `_save_active` (`workflow.py:534`). Keine Herkunftsprüfung.
- Einziger legitimer Aufrufer: `core/hooks/qa_gate.py:490-497` (`_write_stamp`), In-Process-Import,
  Stempelfelder `source`, `exit_code`, `output_sha256`, `timestamp`, Befehls-Hash.
- Schutz heute: nur `set-field` auf den Key ist gesperrt (`_SET_FIELD_PROTECTED`, `workflow.py:1389`, Test AC-9
  `tests/test_qa_gate_run_345.py::test_set_field_on_stamp_key_is_blocked`). Bewusst kein CLI-Unterbefehl.
- `bash_gate.py` 3b blockt Schreibzugriff nur, wenn das Kommando einen geschützten Pfad (`.claude/workflows/…json`)
  nennt UND einen Schreib-Indikator enthält. `python3 -c "from workflow import write_qa_run_stamp; …"` nennt keinen
  Pfad -> kein Treffer. Zusätzlich sind `workflow.py`/`qa_gate.py` in der Bash-Whitelist (`bash_gate.py:131`).
- Der Stempel wird NOCH NIRGENDS gelesen oder durchgesetzt (das ist Teil B). Die Fälschung hat heute also keine
  Wirkung, wird aber relevant, sobald `require_run` ihm vertraut.

## Angriffswege auf den Stempel
1. `python3 -c "from workflow import write_qa_run_stamp; write_qa_run_stamp({...})"` im Bash-Kommando (sichtbar).
2. Dasselbe aus einer vorher per Edit/Write angelegten Skriptdatei (im Bash-Kommando unsichtbar).
3. Direktes Schreiben der Workflow-JSON: bereits durch 3b gesperrt, kein Teil dieses Fixes.

## Lösungsansätze (für /20-analyse)
- A. bash_gate-Regel: Kommando, das `write_qa_run_stamp` / `qa_run_stamp` zusammen mit Python-Aufruf nennt, blocken.
  Deckt Weg 1, nicht Weg 2. Vorbild: Marker-Regeln `APPROVAL_MARKER_PATTERNS_*` (Tier-1 mit Pfadbezug wegen Freitext,
  Issue #30).
- B. Aufrufer-Prüfung in `write_qa_run_stamp`: nur erlaubt, wenn der Einstiegspunkt der Prozess `qa_gate.py` ist
  (`sys.modules["__main__"].__file__`). Deckt Weg 1 und 2 gegen versehentliche/naive Fälschung; ein Angreifer, der
  `__main__` überschreibt, bleibt möglich, das ist aber bewusstes Umgehen im sichtbaren Code.
- C. Gegenprüfung beim Lesen (Teil B): `output_sha256` gegen die Datei am `output_path`, Stempel nicht älter als der
  Lauf. Vom Issue-Kommentar verlangt, gehört aber zur Durchsetzung und nicht zu F003.
- D. Kryptografischer Schlüssel (HMAC): vorab verworfen, derselbe OS-Benutzer kann den Schlüssel lesen,
  Scheinsicherheit.

## Bestehende Muster / Tests
- Bash-Gate-Tests: `tests/test_bash_gate_*.py` (z. B. `_ln_state_407`, `_main_write_417`, `_config_lock_418`).
- Stempel-Tests: `tests/test_qa_gate_run_345.py`. Spec zum Vorgänger: `docs/specs/feat-345-qa-gate-selbst-ausfuehren.md`
  (Known Limitations nennt genau diesen Befund).

## Risiken
- Falschalarme: Das Wort `write_qa_run_stamp` darf in Freitext (Issue-Bodies, `gh issue comment`, Commit-Messages)
  nicht blocken -> Freitext-Flag-Behandlung wie `SECRETS_FREETEXT_FLAGS` nutzen (#30/#53).
- Der legitime Pfad (`qa_gate.py --run`) darf nicht brechen: Test `test_qa_gate_calls_pass_bash_gate`.
- Kern-Gate-Änderung -> hohes Adversary-Risiko (2 Runden).

## Offene Entscheidung für die Analyse
Welche Kombination aus A und B (C bleibt Teil B)? Vorläufige Tendenz: A + B, weil A den sichtbaren Weg schließt und B
den Skript-Weg erschwert; ehrliche Restgrenze in der Spec nennen.

## Analysis

### Type
Bug (Sicherheitslücke, Befund F003, MEDIUM) — Teilumfang von #404. Wirkung heute nur latent: der Stempel wird noch nirgends gelesen (Teil B).

### Entscheidung: A + B (C bleibt Teil B, D verworfen)
- **B (Kern):** `write_qa_run_stamp` prüft den Einstiegspunkt: `Path(getattr(sys.modules["__main__"], "__file__", "") or "").name == "qa_gate.py"`, sonst `PermissionError`/False + Hinweis. Deckt `python3 -c` (kein `__file__`) und Skriptdateien (Weg 2). Restgrenze: `__main__` bewusst überschreiben = sichtbarer Vorsatz, keine Gate-Garantie.
- **A (Ergänzung, sichtbarer Weg):** bash_gate-Regel in Block 3b-Nähe: Token `write_qa_run_stamp` bzw. `qa_run_stamp` zusammen mit Python-Ausführung blockt. Pfadbezug fehlt hier, daher Token-Analyse mit Freitext-Ausnahme (`SECRETS_FREETEXT_FLAGS`, Muster #30/#53), damit Issue-Bodies/Commit-Messages nicht blocken. Nested `python3 -c` Code ist NICHT Freitext -> Roh-Scan.
- Legitimer Pfad `qa_gate.py --run` bleibt frei (Whitelist `bash_gate.py:131`, Test `test_qa_gate_calls_pass_bash_gate`).

### Affected Files
| File | Change | Beschreibung |
|------|--------|--------------|
| core/hooks/workflow.py | MODIFY | Aufrufer-Prüfung in `write_qa_run_stamp` (~+12 LoC) |
| core/hooks/bash_gate.py | MODIFY | Stempel-Fälschungs-Regel (~+25 LoC) |
| tests/test_qa_stamp_forgery_404.py | CREATE | RED-Tests: -c-Import, Skriptdatei, Freitext-OK, legitimer --run-Lauf |
| tests/test_qa_gate_run_345.py | CHECK | bestehende Tests, die `write_qa_run_stamp` direkt aus pytest rufen, ggf. anpassen |
| docs/specs/feat-345-...md, CHANGELOG.md | MODIFY | Known Limitation aktualisieren, Eintrag |

### Scope / Risiko
- 2 Code-Dateien + 1 Testdatei, ca. +40/-0 LoC (ohne Tests). Risiko: MITTEL (Kern-Gate bash_gate -> Adversary 2 Runden; Falschalarm-Gefahr durch Freitext).

### Dependencies
`qa_gate.py` (einziger legitimer Aufrufer), `hook_utils`, Freitext-Flag-Logik in bash_gate.

### Open Questions
- [ ] Prüfen: Rufen bestehende Tests `write_qa_run_stamp` in-process aus pytest? Dann Test-Hook/Monkeypatch statt Prüfung aufweichen.
- [ ] Ob `qa_gate` auch über `python3 -m` laufen soll (dann `__main__.__spec__.name` prüfen) — vermutlich nicht nötig.
