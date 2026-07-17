---
entity_id: fix-71-qa-gate-zero-failed
type: bugfix
created: 2026-07-17
updated: 2026-07-17
status: draft
version: "1.0"
tags: [bugfix, hooks, qa-gate, pytest-parsing, consumer-projects]
test_targets:
  - core/hooks/qa_gate.py
  - tests/test_qa_gate.py
---

# Fix #71: qa_gate.py wertet die pytest-Erfolgsmeldung `0 failed` als Fehlschlag

## Approval

- [ ] Approved

## GitHub Issue

- **Issue:** #71 — qa_gate wertet die pytest-Erfolgsmeldung `0 failed` als Fehlschlag.
- **Consumer-Tracker:** henemm/gregor_zwanzig#1281 (zweite Hälfte, Verdict-Parsing, ist seit 3.9.2 behoben; diese Spec schließt die erste Hälfte).

## Purpose

Behebt einen doppelten Parsing-Fehler im pytest-Zweig von `core/hooks/qa_gate.py::validate_test_output()`: Ein globaler, nicht zeilengebundener Regex-Scan über die gesamte Testausgabe kombiniert mit einer fehlenden `> 0`-Prüfung der gefundenen Fehlerzahl führt dazu, dass eine vollständig grüne pytest-Ausgabe wie `754 passed, 0 failed, 3 skipped` mit der in sich widersprüchlichen Meldung `Tests FAILED: 0 failed` blockiert wird. Der Fix bindet die Erkennung an die echte pytest-Summary-Zeile und prüft die Fehleranzahl korrekt, damit `0 failed` als das erkannt wird, was es ist: ein Erfolg.

## Source

- **File:** `core/hooks/qa_gate.py`
- **Identifier:** `validate_test_output()`

## Dependencies

| Komponente | Typ | Abhängigkeit |
|-----------|-----|-------------|
| `core/hooks/qa_gate.py::validate_test_output()` | Zu ändernde Funktion | Enthält den betroffenen pytest-Zweig (Zeilen 90-96) sowie die unveränderten Nachbarzweige (node --test / Go-TAP via `Executed N tests, with M failures`, `test result: ok`, generische `TEST FAILED`/`TEST SUCCEEDED`-Marker) |
| `tests/test_qa_gate.py` | Bestehende Testdatei | Vorlage für Teststil (Subprozess über `fake_hooks`-Kopie, `tmp_path`-Fixtures, mock-freier Aufruf); wird erweitert, nicht parallel neu gebaut. Bestehende Fälle (`test_verdict_persisted_in_flat_consumer_layout`, `test_missing_workflow_py_fails_loudly`) dürfen nach dem Fix nicht rot werden |
| `core/hooks/adversary_dialog.py::_strip_fenced_code_blocks()` | Geprüfte, NICHT übernommene Utility | Entfernt Markdown-Fenced-Code-Blöcke aus Spec-/Dialog-Artefakten. Geprüft und bewusst **nicht** wiederverwendet — Begründung siehe „Architektur-Entscheidung (ADR)" |
| Consumer-Workaround (gregor_zwanzig-Memory: „Testausgabe via `-v -p no:warnings` erzeugen, kein `0 failed`-String") | Nachgelagert entfallende Doku | Wird nach Verteilung dieses Fixes hinfällig; Anpassung ist Teil von „Out of Scope / Verteilung" |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|--------------|
| `core/hooks/qa_gate.py` | MODIFY | Pytest-Zweig in `validate_test_output()` durch summary-zeilengebundene Erkennung mit korrekter `> 0`-Prüfung ersetzen (neue private Hilfsfunktion `_find_pytest_summary_line()`) |
| `tests/test_qa_gate.py` | MODIFY | Neue Testfälle für `0 failed`-Erfolg, `N failed`-Regression, zitierten Text außerhalb der echten Summary-Zeile (False-Block- und False-Pass-Richtung), sowie eine dokumentierende Prüfung, dass der node/Go-TAP-Zweig unverändert bleibt |
| `CHANGELOG.md` | MODIFY | Neuer Eintrag unter `[Unreleased]` |
| `.claude-plugin/plugin.json` | MODIFY | Version-Bump auf `3.9.3` beim Release (analog zur bestehenden `_read_plugin_version()`-Quelle) |

### Estimated Changes

- Files: 4 (1 MODIFY Kern-Code + 1 MODIFY Test + 2 MODIFY Meta/Release)
- LoC: +90/-8 (neue Hilfsfunktion ~20 LoC, Integrationsänderung im pytest-Zweig ~10 LoC, Tests ~60 LoC)
- Risk Level: LOW (isolierte Änderung eines einzelnen Zweigs, keine Verhaltensänderung an Nachbarzweigen oder an der Verdict-Persistenz-Logik)

## Root Cause

`core/hooks/qa_gate.py:90-96`:

```python
# Pattern: pytest "N passed"
pytest_match = re.search(r"(\d+) passed", content)
pytest_fail = re.search(r"(\d+) failed", content)
if pytest_match:
    if pytest_fail:
        return False, f"Tests FAILED: {pytest_fail.group(1)} failed"
    return True, f"Tests PASSED: {pytest_match.group(1)} passed"
```

Zwei Fehler in einer Codestelle, dieselbe Fehlerklasse wie die in 3.9.2 behobenen Fälle (naiver globaler Regex-Scan über strukturierten Output statt Bindung an die tatsächliche Strukturzeile):

1. `re.search` läuft über den **gesamten** Datei-Inhalt (`content`), nicht über die pytest-Summary-Zeile. Jede Zeichenkette `N failed` irgendwo in der Datei — auch zitiert in einer Log-Zeile eines anderen Tools, in einer Test-Docstring oder in einem eingebetteten Codeblock, der über den Fix selbst berichtet — kippt das Verdict.
2. `pytest_fail` wird nur auf Truthiness geprüft (`if pytest_fail:`), nicht auf `int(pytest_fail.group(1)) > 0`. Ein Treffer für `0 failed` ist truthy und blockiert deshalb, obwohl er den Erfolgsfall ausdrückt.

Beide Fehler zusammen erzeugen den konkreten Vorfall: Eine reale Testausgabe `754 passed, 0 failed, 3 skipped` matcht `pytest_match` (`754 passed`) und `pytest_fail` (`0 failed`) — die Funktion liefert `False, "Tests FAILED: 0 failed"`, eine in sich widersprüchliche Blockmeldung für eine vollständig grüne Suite.

### Geprüfte Nachbarzweige (node --test / Go-TAP)

`core/hooks/qa_gate.py:82-88`:

```python
exec_matches = re.findall(r"Executed (\d+) tests?, with (\d+) failures?", content)
if exec_matches:
    total = sum(int(m[0]) for m in exec_matches)
    failures = sum(int(m[1]) for m in exec_matches)
    if failures > 0:
        return False, f"Tests FAILED: {failures}/{total} failures"
    return True, f"Tests PASSED: {total} tests, 0 failures"
```

Dieser Zweig teilt zwar die erste Dimension des Fehlers (`re.findall` über den gesamten Inhalt, nicht zeilengebunden), **aber nicht** die zweite: `if failures > 0` ist bereits korrekt vorhanden — ein `Executed 5 tests, with 0 failures` wird bereits heute richtig als Erfolg gewertet. Der für Issue #71 namensgebende Doppel-Fehler (Ganztext-Scan **UND** fehlende `> 0`-Prüfung gemeinsam) liegt hier nachweislich **nicht** vor. Dieser Zweig bleibt daher unverändert außerhalb des Scopes dieses Fixes — siehe AC-5.

Die übrigen Zweige (`"test result: ok"`, generische `TEST FAILED`/`TEST SUCCEEDED`-Marker) sind bereits heute entweder ohne Zahlenwert (reine String-Präsenz) oder auf die letzten 5 Zeilen begrenzt (`content.upper().split("\n")[-5:]`) und damit von keiner der beiden Fehlerdimensionen betroffen; sie bleiben unangetastet.

## Implementierungsdetails

### 1. Neue Hilfsfunktion `_find_pytest_summary_line()` in `qa_gate.py`

```python
def _find_pytest_summary_line(content: str) -> str | None:
    """Findet die letzte echte pytest-Summary-Zeile in der Testausgabe.

    Bindet den Scan an das strukturelle pytest-Summary-Format (Liste aus
    '<N> <status>'-Tokens, optional von '='-Rahmen umschlossen, optional mit
    'in X.Ys' Laufzeit-Suffix) statt an eine beliebige Fundstelle im
    Gesamttext. Verhindert False-BLOCK durch anderswo zitierten Text
    (z.B. eine Zeile, die über den Fix berichtet und dabei eine Zahl+"failed"
    nennt) UND False-PASS durch zitierten Text (eine Zahl+"passed" ohne
    echte Summary-Zeile).

    Liegen mehrere echte Summary-Zeilen vor (mehrere aneinandergehaengte
    Testlaeufe in derselben Datei), wird die LETZTE zurueckgegeben.
    """
    line_re = re.compile(r"^\s*=*\s*(?:\d+\s+\w+\s*,?\s*)+(?:in\s+[\d.]+s\s*)?=*\s*$")
    status_re = re.compile(r"\d+\s+(passed|failed|error)")
    last = None
    for line in content.splitlines():
        if line_re.match(line) and status_re.search(line):
            last = line
    return last
```

### 2. Pytest-Zweig in `validate_test_output()` ersetzt den Ganztext-Scan

Vorher/Nachher-Kontrast:

```python
# vorher: globaler Scan ueber die ganze Datei, Trefferzahl nur truthy geprueft
pytest_match = re.search(r"(\d+) passed", content)
pytest_fail = re.search(r"(\d+) failed", content)
if pytest_match:
    if pytest_fail:
        return False, f"Tests FAILED: {pytest_fail.group(1)} failed"
    return True, f"Tests PASSED: {pytest_match.group(1)} passed"

# nachher: Bindung an die echte Summary-Zeile, Trefferzahl > 0 geprueft
summary_line = _find_pytest_summary_line(content)
if summary_line is not None:
    pytest_fail = re.search(r"(\d+)\s+failed", summary_line)
    pytest_pass = re.search(r"(\d+)\s+passed", summary_line)
    if pytest_fail and int(pytest_fail.group(1)) > 0:
        return False, f"Tests FAILED: {pytest_fail.group(1)} failed"
    if pytest_pass or pytest_fail:
        n = pytest_pass.group(1) if pytest_pass else "0"
        return True, f"Tests PASSED: {n} passed"
```

Damit wird `0 failed` in der echten Summary-Zeile korrekt als Erfolg gewertet, `N failed` mit `N > 0` blockt weiterhin, und ein Fall ohne jede `passed`-Zählung aber mit `N failed > 0` (reine Fehlschlag-Suite ohne einen einzigen bestandenen Test) blockt jetzt ebenfalls korrekt über denselben Pfad — eine Verbesserung gegenüber dem bisherigen `if pytest_match:`-Gate, das ohne `passed`-Treffer den ganzen Zweig übersprang.

## Expected Behavior

- **Input:** Eine Testausgabe-Datei, deren Inhalt eine pytest-Summary-Zeile enthält (mit oder ohne `=`-Rahmen, mit oder ohne `in X.Ys`-Laufzeit-Suffix), optional umgeben von weiterem Text, der selbst Zahl+`passed`/`failed`-Zeichenketten zitiert.
- **Output — Erfolg:** Enthält die echte Summary-Zeile `0 failed` (mit oder ohne `N passed`), liefert `validate_test_output()` `(True, "Tests PASSED: ...")`.
- **Output — Fehlschlag:** Enthält die echte Summary-Zeile `N failed` mit `N > 0`, liefert die Funktion `(False, "Tests FAILED: N failed")`.
- **Output — Zitierter Text ohne echte Summary:** Enthält der Text irgendwo Zahl+`failed`/`passed`, aber KEINE Zeile, die dem Summary-Zeilen-Muster entspricht, wird dieser Fund ignoriert; die Funktion fällt auf die nachgelagerten Erkennungsmuster (`test result: ok`, generische Marker) bzw. auf `"Could not determine test result."` zurück.
- **Side effects:** Keine. Reine Lese-/Auswertungslogik innerhalb einer bestehenden Funktion, keine Persistenz-Änderungen, keine Änderung der Aufrufschnittstelle von `validate_test_output()`.

## Error Handling

- Keine pytest-Summary-Zeile im Inhalt gefunden (`_find_pytest_summary_line()` liefert `None`) → unverändertes Verhalten: Kontrolle fällt an die nachgelagerten Zweige (`test result: ok`, generische Marker), wie es der bestehende Code für den Fall ohne `pytest_match`-Treffer bereits tut.
- Summary-Zeile gefunden, aber weder `passed` noch `failed` darin (z.B. nur `3 skipped in 1.2s`) → kein Treffer im pytest-Zweig, Kontrolle fällt ebenfalls an die nachgelagerten Zweige.
- Mehrere echte Summary-Zeilen (mehrere Testläufe in derselben Datei aneinandergehängt) → die letzte wird gewertet, analog zur „letzter statt erster Treffer"-Systematik aus 3.9.2 (`validate_dialog_artifact()`).

## Known Limitations
- Handgeschriebene Report-Zeilen mit Präfix (z.B. `Frontend Node (...): 754 passed, 0 failed`) sind KEINE pytest-Summary-Zeilen und werden bewusst nicht gewertet — das Gate antwortet dann `Could not determine test result.` (fail-safe Block). Das folgt aus AC-4 (Prosa-Fundstellen zählen nicht); rohe pytest-Ausgabe endet immer mit einer strukturellen Summary-Zeile und wird erkannt. Consumer registrieren rohe Runner-Ausgabe, keine Prosa-Zusammenfassungen. (Festgehalten nach GREEN, PO-Linie „ehrlich blocken statt raten"; Entwickler-Meldung 2026-07-17.)


- Der Fix wirkt in Consumer-Projekten erst nach Version-Bump und Verteilung (`python3 setup.py <project> --update`) — siehe „Out of Scope / Verteilung" unten.
- Das Summary-Zeilen-Muster deckt die Standardformate von `pytest` (mit und ohne `-v`, mit und ohne `-p no:warnings`, mit und ohne `=`-Rahmen) ab. Stark abweichende Drittanbieter-Runner, die „passed"/„failed" in einem völlig anderen Zeilenformat ausgeben, fallen weiterhin auf die generischen Marker-Zweige zurück — unverändertes Bestandsverhalten, nicht Gegenstand dieses Fixes.
- Der node/Go-TAP-Zweig (`Executed N tests, with M failures`) bleibt bewusst unangetastet — er ist nachweislich nicht von der zweiten Fehlerdimension (fehlende `> 0`-Prüfung) betroffen (siehe Root Cause). Sein Ganztext-Scan-Verhalten (erste Fehlerdimension) bleibt bestehen und ist nicht Gegenstand dieser Spec.

## Out of Scope / Verteilung

- Version-Bump von `.claude-plugin/plugin.json` auf `3.9.3` und Eintrag in `CHANGELOG.md` unter `[Unreleased]` sind Teil der Implementierung dieses Fixes, aber die **Verteilung** in Consumer-Projekte (`python3 setup.py <project> --update`) ist ein separater, nachgelagerter Schritt außerhalb dieser Spec.
- Nach Verteilung: `henemm/gregor_zwanzig#1281` schließen und die Workaround-Dokumentation in der gregor_zwanzig-Memory (Testausgabe via `-v -p no:warnings`, kein `0 failed`-String) als hinfällig markieren — beides nachgelagert, kein Bestandteil dieser Spec.
- Eine Härtung des node/Go-TAP-Zweigs gegen die erste Fehlerdimension (Ganztext-Scan) ist kein Bestandteil dieses Fixes, da der für Issue #71 namensgebende Doppel-Fehler dort nicht vorliegt (siehe Root Cause). Bei Bedarf eigenes Issue.

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Geprüft wurde, ob `adversary_dialog.py::_strip_fenced_code_blocks()` für die Zitat-Sicherheit des Summary-Scans wiederverwendet werden soll (im Kontext-Dokument als Option benannt). Entscheidung: **nicht wiederverwenden**. `_strip_fenced_code_blocks()` ist auf Markdown-Spec-/Dialog-Artefakte zugeschnitten (CommonMark-Fenced-Code-Block-Semantik mit ` ``` `/`~~~`-Öffnern). `qa_gate.py` verarbeitet dagegen rohe Testrunner-Ausgabe (pytest/node/Go-Terminal-Output), kein Markdown-Dokument — der Fenced-Code-Block-Begriff passt kategorial nicht auf dieses Eingabeformat, und ein Import würde eine domänenfremde Abhängigkeit erzeugen, ohne einen zusätzlichen Schutz zu bieten: Die Bindung an die echte, strukturell erkennbare pytest-Summary-Zeile (`_find_pytest_summary_line()`) löst die Zitat-Sicherheit bereits vollständig und direkt an der Quelle, unabhängig davon, ob zitierter Text in Backticks, in einem eingebetteten Codeblock oder in einfacher Prosa steht. Keine neue Architekturentscheidung, keine strukturelle Weichenstellung, die eine eigene ADR-Aufzeichnung rechtfertigt.

## Acceptance Criteria

- **AC-1:** Given eine Testausgabe-Datei, deren echte pytest-Summary-Zeile `754 passed, 0 failed, 3 skipped in 12.3s` lautet (vollständig grüne Suite) / When `validate_test_output()` (bzw. `qa_gate.py` end-to-end über den Subprozess-Aufruf) diese Ausgabe prüft / Then liefert die Funktion `(True, ...)` mit einer PASSED-Meldung — es erscheint keine `Tests FAILED: 0 failed`-Meldung mehr, unabhängig davon, ob die Summary-Zeile von `=`-Zeichen umrahmt ist oder nicht.

- **AC-2:** Given eine Testausgabe-Datei, deren echte pytest-Summary-Zeile `2 failed, 750 passed in 12.3s` lautet (N größer null) / When `validate_test_output()` diese Ausgabe prüft / Then liefert die Funktion weiterhin `(False, "Tests FAILED: 2 failed")` — der bereits korrekt blockierende Fall bleibt Regressions-geschützt unverändert erhalten.

- **AC-3:** Given eine Testausgabe-Datei, die außerhalb jeder echten pytest-Summary-Zeile eine Zeichenkette mit einer Zahl gefolgt von `failed` enthält (z.B. eine Log-Zeile eines fremden Tools oder einen zitierten Beispieltext über den Fix selbst), deren tatsächliche pytest-Summary-Zeile aber `5 passed, 0 failed in 1.1s` lautet / When `validate_test_output()` diese Ausgabe prüft / Then wird ausschließlich die echte Summary-Zeile gewertet und die Ausgabe als bestanden zurückgegeben — die anderswo zitierte Fundstelle darf das Verdict nicht in Richtung Fehlschlag kippen.

- **AC-4:** Given eine Testausgabe-Datei, die außerhalb jeder echten pytest-Summary-Zeile eine Zeichenkette mit einer Zahl gefolgt von `passed` enthält, aber KEINE Zeile im Inhalt dem pytest-Summary-Zeilen-Muster entspricht / When `validate_test_output()` diese Ausgabe prüft / Then wird diese Fundstelle nicht als Erfolgsmeldung gewertet, und die Funktion greift auf die nachgelagerten generischen Erkennungsmuster zurück bzw. liefert `"Could not determine test result."` statt fälschlich ein PASSED-Verdict zu liefern.

- **AC-5:** Given der `Executed N tests, with M failures`-Zweig (node --test / Go-TAP) in `core/hooks/qa_gate.py` nach diesem Fix / When der Quellcode dieses Zweigs auf dieselbe Doppel-Fehlerklasse geprüft wird, die im pytest-Zweig behoben wurde (Ganztext-Scan ohne Zeilenbindung UND fehlende `> 0`-Prüfung gemeinsam) / Then bestätigt die Prüfung, dass die `> 0`-Prüfung dort bereits vor diesem Fix vorhanden ist (`if failures > 0`) und der Zweig unverändert bleibt — nur der pytest-Zweig wird durch diese Spec geändert.

- **AC-6:** Given die bestehenden Testfälle in `tests/test_qa_gate.py` (`test_verdict_persisted_in_flat_consumer_layout`, `test_missing_workflow_py_fails_loudly`) vor diesem Fix / When sie nach der Umstellung des pytest-Zweigs auf `_find_pytest_summary_line()` erneut ausgeführt werden / Then bleiben beide Ergebnisse unverändert grün — die bereits mit `5 passed in 1.2s` (dreifach wiederholt) formatierte Fixture wird weiterhin korrekt als bestanden erkannt.

## Test Plan

### Automated Tests (TDD RED)

- [ ] Test 1 (deckt AC-1 ab): GIVEN eine `tmp_path`-Testausgabe-Datei mit Inhalt `"...\n754 passed, 0 failed, 3 skipped in 12.34s\n"` WHEN `qa_gate.py` per Subprozess (Muster aus `_run_qa_gate()`) darauf angewendet wird THEN `returncode == 0` und stdout enthält keine `Tests FAILED`-Meldung.
- [ ] Test 2 (deckt AC-1 ab, `=`-Rahmen-Variante): GIVEN dieselbe Fixture, aber die Summary-Zeile von `=`-Zeichen umrahmt (`"============ 754 passed, 0 failed in 12.34s ============="`) WHEN derselbe Aufruf erfolgt THEN `returncode == 0`.
- [ ] Test 3 (deckt AC-2 ab): GIVEN eine Testausgabe-Datei mit Summary-Zeile `"2 failed, 750 passed in 12.34s"` WHEN `qa_gate.py` aufgerufen wird THEN `returncode == 1` und stdout enthält `"2 failed"`.
- [ ] Test 4 (deckt AC-3 ab): GIVEN eine Testausgabe-Datei, die zunächst eine Fließtext-Zeile mit `"Fix behebt vormals 3 failed"` enthält und anschließend eine echte Summary-Zeile `"5 passed, 0 failed in 1.1s"` WHEN `qa_gate.py` aufgerufen wird THEN `returncode == 0`.
- [ ] Test 5 (deckt AC-4 ab): GIVEN eine Testausgabe-Datei mit einer Zeile `"Fremdes Tool meldete 5 passed"` ohne jede echte pytest-Summary-Zeile im übrigen Inhalt WHEN `validate_test_output()` direkt aufgerufen wird THEN liefert es `(False, "Could not determine test result.")` (oder einen anderen nachgelagerten Fallback-Zweig, aber kein `True`).
- [ ] Test 6 (deckt AC-5 ab): GIVEN der Quellcode von `core/hooks/qa_gate.py` nach dem Fix WHEN der `Executed N tests, with M failures`-Zweig per Text-Suche gegen den Stand vor dem Fix verglichen wird THEN ist der Zweig zeichengleich unverändert.
- [ ] Test 7 (deckt AC-6 ab, Regression): GIVEN `tests/test_qa_gate.py::test_verdict_persisted_in_flat_consumer_layout` und `::test_missing_workflow_py_fails_loudly` WHEN sie nach der Umstellung erneut laufen THEN bleiben beide grün mit identischem Verhalten.
- [ ] Test 8 (Zusatzfall, deckt AC-1/AC-2 ab): GIVEN eine Testausgabe-Datei mit Summary-Zeile `"3 failed in 2.1s"` OHNE jede `passed`-Zählung (reine Fehlschlag-Suite) WHEN `qa_gate.py` aufgerufen wird THEN `returncode == 1` und stdout enthält `"3 failed"`.

### Test-Implementierung

Subprozess-Muster analog `tests/test_qa_gate.py::_run_qa_gate()` (fake_hooks-Kopie, `CLAUDE_PROJECT_DIR`-Env, `OPENSPEC_ACTIVE_WORKFLOW`-Env); direkter Funktionsaufruf von `validate_test_output()` und `_find_pytest_summary_line()` für die feingranularen Fälle (Test 5), analog zum bestehenden mock-freien Teststil.

Ausführung:

```bash
python3 -m pytest tests/test_qa_gate.py -v
```

## Changelog

- 2026-07-17: Initial spec erstellt für #71 (henemm/gregor_zwanzig#1281)
