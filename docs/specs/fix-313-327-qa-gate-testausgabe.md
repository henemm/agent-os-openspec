---
entity_id: fix-313-327-qa-gate-testausgabe
type: bugfix
created: 2026-10-03
updated: 2026-10-03
status: draft
version: "1.0"
tags: [qa-gate, unittest, node-test, tap, test-output, verdict]
test_targets: ["tests/test_qa_gate_unittest_node_313_327.py"]
---

# QA-Gate erkennt `unittest` und `node --test` (#313, #327)

## Approval

- [ ] Approved

## GitHub Issue

- **Issue #313:** `qa_gate` erkennt die Ausgabe von `python3 -m unittest` nicht.
- **Issue #327:** `qa_gate` erkennt die Ausgabe von `node --test` (Spec- und TAP-Reporter) nicht.
- Gebündelt in einer Spec, weil dieselbe Funktion (`validate_test_output`) und dieselbe
  Fehlerrichtung („jede rote Evidenz gewinnt") betroffen sind. Gehört zur Testausgabe-Gruppe
  aus Epic #273 (#306/#307/#308 sind bereits geschlossen, #275 ist der Vorgänger).

## Purpose

`qa_gate.validate_test_output` liefert für grüne wie für rote Läufe von `unittest` und
`node --test` kein Urteil („Could not determine test result", „matched 0/13 patterns" oder
„too small"). Das Adversary-Verdict kann dann nicht gesetzt werden, und der Commit- und
Deploy-Weg blockt zu Unrecht. Diese Spec ergänzt zwei zeilenverankerte Auswerter, die beide
Runner zuverlässig als grün, rot oder „nicht bestanden" klassifizieren — mit dem Schwerpunkt
auf der gefährlicheren Gegenrichtung: ein roter Lauf darf nie als grün durchgehen. Rein
regelbasiert, kein Modell: beide Formate haben feste Summary-Zeilen.

## Source

- **File:** `core/hooks/qa_gate.py`
- **Identifier:** `validate_test_output()` (Z. 152–222), `TEST_PATTERNS` (Z. 34–41), neu
  `_evaluate_unittest()` und `_evaluate_node_test()`; wiederverwendet: `_not_passed_skipped()`
  (#273-Regel), `strip_ansi()`

## Reproduktion (Ist-Zustand)

Echte Läufe (Node 26.5.1, Python 3), `validate_test_output(datei, infra=True)`:

| Ausgabe | Ergebnis heute | Ursache |
|---|---|---|
| unittest grün (Standard, 1 Test) | `Test output too small (98 bytes)` | Größen-Gate (<100 Byte) |
| unittest grün `-v` | `matched 0/13 patterns` | `TEST_PATTERNS` kennt `Ran N tests`/`OK` nicht |
| unittest rot (`FAILED (failures=1, errors=1, skipped=1)`) | `Could not determine test result` | kein Auswertungszweig |
| node Spec grün / rot | `matched 1/13 patterns` | `TEST_PATTERNS` kennt `ℹ tests N` nicht |
| node TAP grün / rot | `Could not determine test result` | kein Auswertungszweig |

Es sind zwei Stufen betroffen: der Muster-Vorfilter (≥ 2 Treffer aus `TEST_PATTERNS`) und der
Auswertungszweig. Beides muss geändert werden.

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `qa_gate.validate_test_output()` | function | Setzt das Verdict, das `bash_gate.py` beim Commit prüft; ein Fehler hier blockiert Commits oder öffnet sie zu Unrecht (False-Pass) |
| `qa_gate._not_passed_skipped()` | function | #273-Regel: 0 bestanden + Übersprungenes ist kein Erfolg |
| `hook_utils.strip_ansi()` | function | Wird bereits vor der Auswertung angewandt |
| `tests/fixtures/qa_gate_313_327/` | directory | Echte Beispielausgaben (neu, siehe „Fixtures") |
| `tests/test_qa_gate.py` | tests | Regressionsschutz der bestehenden Zweige (xcodebuild, pytest, go, cargo) |

## Scope

- **Affected Files:** `core/hooks/qa_gate.py`, `tests/test_qa_gate_unittest_node_313_327.py`
  (neu), `CHANGELOG.md` (Abschnitt `[Unreleased]`, **kein Versions-Bump**). Dazu Fixtures unter
  `tests/fixtures/qa_gate_313_327/` (Daten, keine Logik).
- **Estimated Changes:** ≈ +70 LoC Gate, ≈ +130 LoC Tests, ≈ +4 LoC Changelog
  (innerhalb der Scoping-Limits: 3 Code-/Doku-Dateien, < 250 LoC).
- **Außerhalb des Scopes:**
  - `core/hooks/post_bash.py` (erkennt `unittest`/`node` nicht, schreibt aber nur den Hinweis
    `last_test_run`, kein Verdict).
  - Der Kommentar zu `fix-2375…` (Verdict `Tests PASSED: 3714 tests, 0 failures` aus unbekannter
    Quelle in gregor_zwanzig) steht bereits in #327.
  - Die Alternative „Gate führt Tests selbst aus" ist Issue #345.

## Implementation Details

### 1. Zwei neue Auswerter

Beide geben `tuple[bool, str] | None` zurück (`None` = Format nicht erkannt), je ≤ 50 LoC,
ohne Seiteneffekte, auf dem bereits ANSI-bereinigten Text. Alle Muster sind zeilenverankert
(`(?m)^…$`): Text, der mitten in einer Prosa-Zeile zitiert wird (`… hat Ran 5 tests in 0.1s
gemeldet`, `x ℹ pass 3`), zählt nicht.

**`_evaluate_unittest(content)`**
- Anker: Zeile `^Ran (\d+) tests? in [\d.]+s$`; gewertet wird die **nächste nichtleere Zeile**
  danach: `OK`, `OK (skipped=S, expected failures=E, unexpected successes=U)` (beliebige
  Teilmenge der Zähler), `FAILED (failures=F, errors=E[, skipped=S][, …])` oder — ohne `Ran`-
  Zeile — `NO TESTS RAN`.
- `FAILED (…)` → `(False, "Tests FAILED: F failures, E errors (unittest)")` mit den Zahlen.
- `NO TESTS RAN` oder `Ran 0 tests` → `(False, "Tests NOT PASSED: 0 tests executed (nichts gelaufen)")`.
- `OK` mit `unexpected successes` > 0 → rot (`False`, Meldung nennt die Zahl); unittest selbst
  wertet den Lauf dann als nicht erfolgreich.
- `OK (skipped=S)` mit `N − S == 0` → `_not_passed_skipped(S)` (#273-Regel).
- Sonst `OK` (auch mit `expected failures`, die als bestanden zählen) →
  `(True, "Tests PASSED: N tests (unittest)")`, bei `skipped` mit Zusatz ` (S skipped)`.
- Mehrere `Ran`-Blöcke in einer Datei (mehrere Läufe): jede rote bzw. „nicht bestanden"-Evidenz
  gewinnt; grün nur, wenn alle erkannten Läufe grün sind.

**`_evaluate_node_test(content)`**
- Zwei Reporter, je ein zusammenhängender Summary-Block:
  - Spec: `ℹ tests N` / `ℹ suites` / `ℹ pass` / `ℹ fail` / `ℹ cancelled` / `ℹ skipped` /
    `ℹ todo` / `ℹ duration_ms`, jede Zeile mit `^ℹ <name> <zahl>$`.
  - TAP: dieselben Felder als `^# <name> <zahl>$`.
- Gewertet wird der **letzte zusammenhängende Block**. Es gibt **keine Bindung ans
  Dateiende**: Bei Rot folgen auf den Block `✖ failing tests:` mit Stacktraces; eine
  Dateiende-Regel (Vorschlag in #327) würde genau die roten Läufe verfehlen.
- `fail > 0` oder `cancelled > 0` → `(False, "Tests FAILED: F failed, C cancelled (node --test)")`.
- `tests == 0` → `(False, "Tests NOT PASSED: 0 tests executed (nichts gelaufen)")`.
- `pass == 0` und `skipped + todo > 0` → `_not_passed_skipped(skipped + todo)` (#273-Regel).
- Sonst `(True, "Tests PASSED: P passed (node --test)")`, bei Übersprungenem mit Zusatz.
- Fehlt `tests` oder `pass`/`fail` im Block, ist das Format nicht erkannt → `None`.

### 2. Einbindung in `validate_test_output` (Reihenfolge ist sicherheitsrelevant)

1. **Vorfilter-Umgehung.** Ein von einem neuen Auswerter erkannter Summary-Block gilt selbst
   als Beleg: Liefert `_evaluate_unittest` oder `_evaluate_node_test` ein Ergebnis (nicht
   `None`), wird der `TEST_PATTERNS`-Vorfilter (≥ 2 Treffer) für diese Ausgabe übersprungen.
   Für alle übrigen Ausgaben bleibt der Vorfilter unverändert.
2. **Rot zuerst.** Ein ROTES oder „nicht bestanden"-Ergebnis der neuen Auswerter wird **vor**
   dem `Executed`-Zweig zurückgegeben. Sonst gewinnt bei gemischter Ausgabe (unittest rot +
   xcodebuild grün — genau der Fall aus #313) das Grün der xcodebuild-Zeilen: False-Pass.
3. **Grün danach.** Ein GRÜNES Ergebnis der neuen Auswerter gilt erst nach dem `Executed`-,
   pytest- und go-Zweig und vor dem cargo-/Marker-Fallback. Folglich gewinnt bei gemischter
   Ausgabe unittest grün + pytest rot das Rot des pytest-Zweigs; jede rote Evidenz gewinnt.
4. Bestehende Zweige (xcodebuild, pytest, go, cargo, Marker) bleiben textlich unverändert.

### 3. Größen-Gate bleibt unverändert

`size < 100` → „too small / looks fabricated" bleibt, wie es ist. Begründung: Es ist der
einzige Fälschungsfilter (`echo 'OK' > datei`). Eine Ausnahme für `Ran 1 test … OK` würde
exakt die handschreibbare Zeile freigeben. Reale Adversary-Läufe sind größer (`-v`).

### Fixtures (echte Ausgaben, nichts erfunden)

Unter `tests/fixtures/qa_gate_313_327/` liegen nur unveränderte Ausgaben echter Läufe; die
Fixtures erzeugt die TDD-RED-Phase (`/40-tdd-red`), nicht dieser Spec-Schritt:

- `unittest_green_verbose.txt` (`python3 -m unittest -v`, mehrere Tests)
- `unittest_red_failures_errors_skipped.txt` (`FAILED (failures=1, errors=1, skipped=1)`)
- `unittest_only_skipped.txt` (`OK (skipped=N)`)
- `unittest_no_tests_ran.txt` (`NO TESTS RAN`)
- `unittest_unexpected_success.txt`, `unittest_expected_failure.txt`
- `node_spec_green.txt`, `node_spec_red_with_stacktraces.txt` (Block, danach `✖ failing tests:`)
- `node_tap_green.txt`, `node_tap_red.txt`, `node_cancelled.txt`, `node_zero_tests.txt`

Lässt sich ein Fixture nicht echt erzeugen, wird das gemeldet und nicht handgeschrieben.
Gemischte Ausgaben (unittest + xcodebuild/pytest) werden im Test aus zwei echten Fixtures
konkateniert; Prosa-Zitate sind Inline-Strings im Test.

## Expected Behavior

- **Input:** Testausgabe-Datei (< 30 min alt, ≥ 100 Byte) mit `unittest`- oder
  `node --test`-Summary, ggf. gemischt mit Ausgaben anderer Runner.
- **Output:** `(True, "Tests PASSED: …")` bei grünem Lauf, `(False, "Tests FAILED: …")` mit
  Zahlen bei rotem Lauf, `(False, "Tests NOT PASSED: …")` bei 0 Tests oder 0 bestanden +
  Übersprungenem. Jede rote Evidenz einer Datei gewinnt.
- **Side effects:** keine; `validate_test_output` bleibt rein lesend. Kein neuer State, keine
  neue Konfiguration.

## Error Handling

- Nicht erkanntes Format bleibt `None` und fällt durch auf die bestehenden Zweige
  (am Ende weiter „Could not determine test result.") — die Fehlerrichtung ist überall „im
  Zweifel nicht grün".
- Ein unvollständiger Summary-Block (z. B. nur `ℹ tests 3` ohne `pass`/`fail`) wird nicht als
  grün geraten, sondern als nicht erkannt behandelt.

## Known Limitations

- **Einzeltest-Lauf ohne `-v` scheitert weiter am Größen-Gate** (98 Byte: `.` / `Ran 1 test in
  0.000s` / `OK`). Beabsichtigt, siehe Abschnitt 3. Abhilfe für Anwender: `-v` nutzen oder
  mehrere Tests laufen lassen.
- Das Ausgabeformat von `node --test` ist reporter- und versionsabhängig (der Default bei
  Umleitung wechselte). Erkannt werden Spec (`ℹ`) und TAP (`#`); ein anderer Reporter
  (`dot`, `junit`) bleibt unbestimmbar und damit nicht grün.
- `node --test` mit `--test-reporter=spec` auf einem Terminal ohne Unicode kann `ℹ` durch ein
  anderes Zeichen ersetzen; nicht erkannt, daher nicht grün.
- Das Gate bleibt textbasiert und damit von Hand fälschbar (oberhalb von 100 Byte). Die
  Alternative „Gate führt den Test selbst aus und nutzt den Exit-Code" ist Issue #345 und
  würde das Prinzip „Datei rein, Urteil raus" ändern.

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] Die Fehlerfälle aus „Reproduktion" (unittest grün `-v`, unittest rot, node Spec/TAP grün
      und rot) sind vor dem Fix gegen den heutigen Stand reproduziert (RED-Artefakt) und danach
      grün
- [ ] Der False-Pass-Fall (unittest rot + xcodebuild grün in einer Datei) liefert `FAILED`
- [ ] Fixtures stammen aus echten `unittest`- und `node --test`-Läufen
- [ ] Das Größen-Gate ist unverändert (eine Datei < 100 Byte wird weiter abgewiesen)
- [ ] `CHANGELOG.md` hat einen `[Unreleased]`-Eintrag, kein Versions-Bump
- [ ] Regressionslauf grün (insbesondere `tests/test_qa_gate.py`)
- [ ] Der Adversary-Weg ist praktisch nutzbar: ein echter `unittest -v`-Lauf einer Beispiel-
      suite lässt sich über `qa_gate.py <datei> --infra` zu einem Verdict auswerten

## Acceptance Criteria

- **AC-1:** Given die Ausgabe eines grünen `python3 -m unittest -v`-Laufs (echte Fixture,
  `Ran N tests in X.XXXs` + `OK`) / When `validate_test_output()` läuft / Then ist das Ergebnis
  `True` mit `Tests PASSED` und der Zahl der Tests — obwohl der Muster-Vorfilter 0 Treffer hätte.
  - Test: tests/test_qa_gate_unittest_node_313_327.py::test_unittest_green_verbose_passed

- **AC-2:** Given ein roter unittest-Lauf (`FAILED (failures=1, errors=1, skipped=1)`) / When
  `validate_test_output()` läuft / Then ist das Ergebnis `False` mit `Tests FAILED` und den
  Zahlen für failures und errors — nicht „Could not determine test result".
  - Test: tests/test_qa_gate_unittest_node_313_327.py::test_unittest_red_failed_with_counts

- **AC-3:** Given ein unittest-Lauf `OK (skipped=N)`, in dem alle Tests übersprungen wurden
  (`N − S == 0`) / When `validate_test_output()` läuft / Then ist das Ergebnis `False` mit
  `Tests NOT PASSED` und der Zahl der Übersprungenen (#273-Regel); Given `OK (expected
  failures=E)` / Then `True` (erwartete Fehlschläge zählen als bestanden).
  - Test: tests/test_qa_gate_unittest_node_313_327.py::test_unittest_all_skipped_not_passed_expected_failures_green

- **AC-4:** Given eine unittest-Ausgabe `NO TESTS RAN` bzw. `Ran 0 tests in 0.000s` / When
  `validate_test_output()` läuft / Then ist das Ergebnis `False` mit `Tests NOT PASSED`
  (nichts gelaufen).
  - Test: tests/test_qa_gate_unittest_node_313_327.py::test_unittest_no_tests_ran_not_passed

- **AC-5:** Given ein unittest-Lauf mit `OK (unexpected successes=1)` / When
  `validate_test_output()` läuft / Then ist das Ergebnis `False` (rot, Meldung nennt die Zahl).
  - Test: tests/test_qa_gate_unittest_node_313_327.py::test_unittest_unexpected_success_is_red

- **AC-6:** Given ein grüner `node --test`-Lauf im Spec-Reporter (`ℹ tests N` … `ℹ fail 0`) /
  When `validate_test_output()` läuft / Then ist das Ergebnis `True` mit `Tests PASSED`.
  - Test: tests/test_qa_gate_unittest_node_313_327.py::test_node_spec_green_passed

- **AC-7:** Given ein roter `node --test`-Lauf im Spec-Reporter, bei dem nach dem Summary-Block
  `✖ failing tests:` mit Stacktraces folgt / When `validate_test_output()` läuft / Then ist das
  Ergebnis `False` mit `Tests FAILED` und der Zahl der Fehlschläge — der Block wird trotz
  nachfolgender Zeilen gewertet (keine Dateiende-Bindung).
  - Test: tests/test_qa_gate_unittest_node_313_327.py::test_node_spec_red_with_trailing_stacktraces_failed

- **AC-8:** Given ein grüner `node --test`-Lauf im TAP-Reporter (`# tests N` … `# fail 0`) /
  When `validate_test_output()` läuft / Then ist das Ergebnis `True`.
  - Test: tests/test_qa_gate_unittest_node_313_327.py::test_node_tap_green_passed

- **AC-9:** Given ein roter `node --test`-Lauf im TAP-Reporter (`# fail 2`) / When
  `validate_test_output()` läuft / Then ist das Ergebnis `False` mit `Tests FAILED` und der
  Zahl 2.
  - Test: tests/test_qa_gate_unittest_node_313_327.py::test_node_tap_red_failed

- **AC-10:** Given ein `node --test`-Lauf mit `cancelled > 0` und `fail 0` (Spec und TAP) /
  When `validate_test_output()` läuft / Then ist das Ergebnis `False` (abgebrochen ist rot).
  - Test: tests/test_qa_gate_unittest_node_313_327.py::test_node_cancelled_is_red

- **AC-11:** Given ein `node --test`-Lauf mit `tests 0`, sowie einer mit `pass 0` und
  `skipped > 0` / When `validate_test_output()` läuft / Then ist das Ergebnis jeweils `False`
  mit `Tests NOT PASSED` (nichts gelaufen bzw. nichts bestanden, #273-Regel).
  - Test: tests/test_qa_gate_unittest_node_313_327.py::test_node_zero_tests_and_all_skipped_not_passed

- **AC-12 (False-Pass-Schutz, Rot zuerst):** Given eine Datei mit rotem unittest-Lauf
  (`FAILED (failures=1)`) UND grünen xcodebuild-Zeilen (`Executed 5 tests, with 0 failures`,
  `** TEST SUCCEEDED **`) / When `validate_test_output()` läuft / Then ist das Ergebnis `False`
  mit `Tests FAILED` — das Grün des xcodebuild-Zweigs gewinnt nicht.
  - Test: tests/test_qa_gate_unittest_node_313_327.py::test_mixed_unittest_red_xcodebuild_green_is_failed

- **AC-13 (jede rote Evidenz gewinnt):** Given eine Datei mit grünem unittest-Lauf und rotem
  pytest-Lauf (`1 failed, 4 passed`), sowie eine mit zwei unittest-Läufen (erst grün, dann rot)
  / When `validate_test_output()` läuft / Then ist das Ergebnis jeweils `False`.
  - Test: tests/test_qa_gate_unittest_node_313_327.py::test_mixed_unittest_green_pytest_red_and_two_runs_is_failed

- **AC-14 (zitierter Text zählt nicht):** Given eine Datei, die `Ran 5 tests in 0.1s` bzw.
  `ℹ pass 3` nur mitten in Prosa-Zeilen enthält (nicht am Zeilenanfang) und sonst keine
  Testausgabe / When `validate_test_output()` läuft / Then wird kein Summary erkannt: das
  Ergebnis ist `False` (Vorfilter bzw. „Could not determine"), niemals `True`.
  - Test: tests/test_qa_gate_unittest_node_313_327.py::test_quoted_summary_in_prose_not_recognized

- **AC-15 (Größen-Gate und Vorfilter unverändert):** Given eine echte Einzeltest-Ausgabe von
  `python3 -m unittest` ohne `-v` (unter 100 Byte) / When `validate_test_output()` läuft /
  Then ist das Ergebnis weiter `False` mit `too small`; Given Text ohne erkennbaren Runner-
  Block und mit nur einem Muster-Treffer / Then weiter `Doesn't look like test output`.
  - Test: tests/test_qa_gate_unittest_node_313_327.py::test_size_gate_and_prefilter_unchanged

- **AC-16 (Regression):** Given die bestehenden QA-Gate-Tests / When die Vollsuite läuft / Then
  bleibt `tests/test_qa_gate.py` unverändert grün (xcodebuild-`Executed`, pytest, go, cargo,
  Marker-Fälle).
  - Test: tests/test_qa_gate.py (Regressionslauf); zusätzlich
    tests/test_qa_gate_unittest_node_313_327.py::test_existing_branches_unchanged_pytest_executed_go

## Test Plan

Automatische Tests (jeweils an eine AC oben gebunden), alle gegen die echte
`validate_test_output()` mit Dateien aus `tests/fixtures/qa_gate_313_327/` bzw. `tmp_path`:
- `python3 -m pytest tests/test_qa_gate_unittest_node_313_327.py -q` (AC-1 bis AC-16)
- Regressionslauf: `python3 -m pytest tests/ -q` (insbesondere `tests/test_qa_gate.py`,
  `tests/test_gate_parser_fixes_73_76_79.py`, `tests/test_testausgabe_erkennung_275.py`)
- TDD-RED: Zuerst Fixtures aus echten Läufen erzeugen, dann Tests schreiben. AC-1 bis AC-13
  müssen gegen den heutigen Stand rot sein (Reproduktion); AC-14, AC-15 und AC-16 dürfen schon
  heute grün sein — sie sind Gegenproben bzw. Regressionsschutz.
- Pytest läuft im Scratchpad-venv mit `pytest` und `pyyaml` (kein System-pytest).
- Durchlauf als Nutzer (Pflicht vor Übergabe): echte `unittest -v`- und `node --test`-Läufe
  einer kleinen Beispielsuite in eine Datei umleiten und `python3 core/hooks/qa_gate.py
  <datei> --infra` aufrufen; grün und rot je einmal.

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine (`docs/adr/` existiert nicht; Entscheidungen stehen in den Specs)
- **Rationale:** Keine neue Architektur — zwei Auswerter nach dem bestehenden Muster der
  Runner-Zweige. Ohne Modell, weil beide Formate feste Zeilen haben (Regel vor Modell).
  *Verworfene Alternative B — Gate führt den Test selbst aus* (`qa_gate.py --run <Befehl>`,
  echter Exit-Code statt Textparsing): beseitigt Parsing-Wettlauf und Fälschung an der Wurzel,
  kippt aber das Prinzip „Datei rein, Urteil raus" (Adversary-Dialog, `/50-implement`,
  `/60-validate`, Konsumenten-Projekte) und sprengt das Scoping-Limit; als Issue #345
  angelegt.
  *Verworfene Alternative C — Größen-Gate für erkannte Runner-Summaries lockern:* würde die
  handschreibbare Zeile `Ran 1 test … OK` freigeben und den einzigen Fälschungsfilter
  aushöhlen.
  *Verworfen — nur den Auswertungszweig ergänzen (so nennen es die Issues):* ließe den
  Vorfilter bestehen; `-v`-unittest und node Spec erreichten den neuen Zweig nie.

## Changelog

- 2026-10-03: Initial spec created
