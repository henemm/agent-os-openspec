# Kontext: fix-71-qa-gate-zero-failed

**Issue:** #71 — qa_gate wertet die pytest-Erfolgsmeldung `0 failed` als Fehlschlag.
**Consumer-Tracker:** henemm/gregor_zwanzig#1281 (dessen zweite Hälfte, Verdict-Parsing, ist seit 3.9.2 behoben).
**Plugin-Version bei Fund:** 3.9.1/3.9.2 (Stelle unverändert).

## Ursache (am Code verifiziert)

`core/hooks/qa_gate.py:92-95`:
```python
pytest_match = re.search(r"(\d+) passed", content)
pytest_fail = re.search(r"(\d+) failed", content)
if pytest_match:
    if pytest_fail:
        return False, f"Tests FAILED: {pytest_fail.group(1)} failed"
```

Zwei Fehler in einem: (1) `re.search` läuft über den **gesamten** Datei-Inhalt statt über die pytest-Summary-Zeile, (2) die Trefferzahl wird nicht auf `> 0` geprüft. Ein Output mit `754 passed, 0 failed, 3 skipped` blockt mit der in sich widersprüchlichen Meldung `FAILED — Tests FAILED: 0 failed`.

## Reale Vorfälle

- 2026-07-16, Consumer-Workflow zu gregor#1268: alle Suiten grün (`754 passed, 0 failed` + `28 passed, 0 failed`), Gate blockt. Kategorie c (fälschlich blockierendes Gate).
- Seither zwingt der Workaround alle Consumer-Workflows in ein Format-Korsett: Testausgabe muss via `-v -p no:warnings` erzeugt werden und darf keinen `0 failed`-String enthalten (dokumentiert in gregor-Memory) — Formatzwang statt Fix.

## Fix-Richtung

Beide Dimensionen schließen, analog zur 3.9.2-Systematik (kein naiver Ganztext-Scan über strukturierten Output):
1. Trefferzahl prüfen: `int(pytest_fail.group(1)) > 0` — `0 failed` ist ein Erfolg.
2. Scan auf die pytest-**Summary-Zeile** binden (`=== N passed[, M failed]... ===`- Muster bzw. letzte Summary-Zeile), damit nicht irgendwo zitierter Text („der Fix behebt `3 failed`…") das Verdict kippt — in beide Richtungen: weder False-Block durch zitiertes `N failed` noch False-Pass durch zitiertes `N passed`, wenn die echte Summary fehlt.

## Angrenzende Formate im selben Codeblock (nicht kaputtmachen)

`qa_gate.py` erkennt neben pytest auch node --test/Go-TAP (angehängte `Executed N tests, with M failures`-Zeile, siehe gregor-Memory zu QA-Gate-Formaten). Deren Verhalten muss unverändert bleiben — Scope ist NUR der pytest-Zweig, es sei denn, derselbe Doppel-Fehler (Ganztext + fehlende >0-Prüfung) liegt dort nachweislich auch vor; dann in einem Zug, mit eigenen Tests.

## Randbedingungen

- Tests: `tests/test_qa_gate.py` existiert als Vorbild/Bestand — erweitern, nicht parallel neu bauen.
- CHANGELOG `[Unreleased]`, Version-Bump 3.9.3 beim Release, Verteilung via `claude plugin update agent-os-openspec@henemm-private`.
- Nach Verteilung: gregor#1281 schließen + Workaround-Memory in gregor anpassen.
- Fence-Ausblendung aus 3.9.2 (`_strip_fenced_code_blocks` in adversary_dialog.py) ist ggf. wiederverwendbar, wenn der Summary-Scan Zitat-sicher gemacht wird — geteilt nutzen statt duplizieren, falls einschlägig.
