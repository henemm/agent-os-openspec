---
entity_id: fix-275-testausgabe-erkennung
type: bugfix
created: 2026-10-01
updated: 2026-10-01
status: draft
version: "1.0"
tags: [test-output, ansi, xcbeautify, skipped, qa-gate, tdd-gate, post-bash]
test_targets: ["tests/test_testausgabe_erkennung_275.py"]
---

# Testausgaben richtig erkennen: ANSI, xcbeautify, „übersprungen" (#275)

## Approval

- [ ] Approved

## GitHub Issue

- **Issue:** #275 — Sammel-Vorgang, fasst #201 (ANSI-Farbcodes verdecken `FAIL`), #202
  (`Executed … skipped and …` wird nicht gelesen) und #256① (xcbeautify markiert Fehler nur mit
  „❌"). Dazu die PO-Entscheidung vom 2026-09-28 (Kommentar „Zusatz aus #273"): Ein Lauf ohne
  bestandene Tests und mit Übersprungenem ist kein Erfolg.

## Purpose

Die Gates lesen Testausgaben mit Textmustern, die zu eng sind: Mit ANSI-Farbcodes ummantelte
Fehlerzeilen, xcbeautify-Ausgaben mit „❌"/„✖" und die xcodebuild-Summary mit „skipped" werden
nicht oder falsch erkannt. Die Folge sind zu Unrecht abgewiesene RED-Artefakte, die Fehlermeldung
„Could not determine test result." statt einer Zahl und — in Gegenrichtung gefährlicher — ein
Lauf, in dem nichts bestanden hat und alles übersprungen wurde, gilt als grün. Diese Spec macht die
Erkennung robust (Scheibe A) und führt die Regel „null bestanden + übersprungen ≠ Erfolg" ein
(Scheibe B). Rein regelbasiert, kein Modell: es sind Textmuster.

## Source

- **File:** `core/hooks/hook_utils.py` — neu `strip_ansi()`
- **File:** `core/hooks/tdd_enforcement.py` — `_FAILURE_RE` und die Prüfung „RED-Artefakt zeigt
  keine Fehler-Evidenz"
- **File:** `core/hooks/qa_gate.py` — `validate_test_output()`, `_find_pytest_summary_line()`
  (eigenes `ansi_re` entfällt)
- **File:** `core/hooks/post_bash.py` — `_FAILURE_EVIDENCE_RE`, `_detect_test_output()` (`pass_patterns`)
- **File:** `core/commands/60-validate.md`, `core/commands/82-test.md`,
  `core/agents/implementation-validator.md`, `core/agents/test-runner.md` — Report-Vorlagen

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `qa_gate.validate_test_output()` | function | Setzt das Verdict, das `bash_gate.py` beim Commit prüft — ein Fehler hier blockiert Commits oder öffnet sie zu Unrecht |
| `tdd_enforcement._check_red_artifact` (Prüfung `test_output`) | function | Entscheidet, ob Edits in phase6 erlaubt sind |
| `post_bash.last_test_run` | State-Feld | Nur Hinweis (#253), kein Verdict; Konsument ist die Adversary-Evidenz. Per grep geprüft: nichts gated auf den Wert `passed` allein |
| `scripts/sync_skills.py` | script | Regeneriert `skills/*/SKILL.md` aus `core/commands/` — Vorlagen nur in `core/` ändern |
| `tests/fixtures/` | directory | Existiert (`precondition_origins/`); neu `tests/fixtures/testausgabe_275/` |
| `xcbeautify` (lokal installiert, v3.2.1) | tool | Erzeugt die echte Fixture für den „❌"-Fall; nur beim Erstellen der Fixture nötig, nicht zur Testlaufzeit |

## Scope

**Bewusste Ausnahme vom Scoping-Limit (4–5 Dateien / ±250 LoC).** PO-Entscheidung vom 2026-10-01:
alles in einem Vorgang, obwohl der Umfang das Limit überschreitet (≈ 9 Dateien, ≈ +260 LoC, dazu
generierte `skills/`-Dateien). Begründung: Dieselben vier Hook-Stellen und dieselben vier Vorlagen
werden von beiden Scheiben angefasst; getrennt würden sie zweimal gelesen, zweimal getestet und
einmal überschrieben. Zur Risikobegrenzung gilt die Reihenfolge **Scheibe A (Erkennung) vor
Scheibe B (skipped-Regel + Vorlagen), je ein eigener Commit**; beide Commits kompilieren und sind
einzeln grün.

- **Affected Files:**
  - Scheibe A: `core/hooks/hook_utils.py`, `core/hooks/tdd_enforcement.py`, `core/hooks/qa_gate.py`
  - Scheibe B: `core/hooks/qa_gate.py`, `core/hooks/post_bash.py`, `core/commands/60-validate.md`,
    `core/commands/82-test.md`, `core/agents/implementation-validator.md`,
    `core/agents/test-runner.md` (+ `skills/*/SKILL.md` per `python3 scripts/sync_skills.py`,
    nie von Hand)
  - Doku: `CHANGELOG.md` (Abschnitt `[Unreleased]`, Scope des Vorgangs erwähnen; **kein
    Versions-Bump**)
  - Tests: `tests/test_testausgabe_erkennung_275.py` (neu), `tests/fixtures/testausgabe_275/` (neu)
- **Estimated Changes:** Produktivcode ≈ +130/−15 LoC (hook_utils ~8, tdd_enforcement ~20,
  qa_gate ~55, post_bash ~20, Vorlagen ~8), Tests + Fixtures ≈ +130 LoC

## Implementation Details

### Scheibe A — Erkennung (#201, #202, #256①)

**A1. `hook_utils.strip_ansi(text) -> str`.** Einzige ANSI-Entfernung im Framework:
`re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", text)`. `qa_gate._find_pytest_summary_line()` benutzt sie
statt des eigenen `ansi_re`; `tdd_enforcement` und `post_bash` rufen sie auf, bevor sie Muster
anwenden.

**A2. `tdd_enforcement`: Fehler-Evidenz auf bereinigtem Text.** Die Prüfung läuft auf
`strip_ansi(content)`. `_FAILURE_RE` wird um Muster erweitert, die Fehler belegen:
`❌`, `✖`, `✘`, `TEST FAILED`, `Test run with … failed` (Swift Testing),
`\b[1-9]\d*\s+failures?\b` und `\bEXIT=[1-9]\d*\b`. **`0 failures` darf nie matchen** — die Zahl
muss mit 1–9 beginnen. Bestehende Alternativen (`FAILED`, `ERROR`, `Traceback`, …) bleiben
unverändert. Der Platzhalter-Check (`_find_placeholder`) bleibt auf dem Rohtext.

**A3. `qa_gate`: `Executed`-Zweig.** Neue Regex akzeptiert die Apple-Variante:
`Executed (\d+) tests?, with (?:(\d+) tests? skipped and )?(\d+) failures?`. Gewertet wird nur
die **letzte** Treffer-Zeile (die Gesamtsumme steht zuletzt; Summieren über Suite-Zeilen
verdoppelt die Zahlen). `failures > 0` → `(False, "Tests FAILED: M/N failures")` — also eine
Zahl statt „Could not determine test result.". Die Auswertung läuft auf `strip_ansi(content)`.

### Scheibe B — „null bestanden + übersprungen ≠ Erfolg" (#273-Regel)

**B1. `qa_gate`: Skipped extrahieren und die Regel anwenden.**
- `Executed`-Zweig: `passed = total − skipped − failures`. Ist `passed == 0` und `skipped > 0`
  → `(False, "Tests NOT PASSED: 0 passed, S skipped (nichts bestanden)")`. Ist `total == 0`
  (`Executed 0 tests, with 0 failures`) → `(False, "Tests NOT PASSED: 0 tests executed (nichts
  gelaufen)")` — Wortlaut der Anforderung aus #273: „Ein Lauf, in dem nichts gelaufen ist, darf
  kein Gate öffnen."
- pytest-Summary: `(\d+)\s+skipped` wird neben passed/failed aus der Summary-Zeile gelesen.
  Ist passed 0/fehlend und skipped > 0 → `(False, …)` mit derselben Meldung. `_find_pytest_summary_line`
  erkennt `0 passed, 5 skipped in 0.31s` und `5 skipped in 0.31s` bereits als Summary
  (`skipped` steht im `\d+ \w+`-Muster der Zeilenform); `status_re` wird um `skipped` erweitert,
  damit auch die reine `5 skipped`-Zeile als Summary gilt.
- Fallback `** TEST SUCCEEDED **`: wird nur noch angewendet, wenn die Ausgabe keine
  `Executed …`-Zeile mit `passed == 0` enthält — der Fallback darf die Regel nicht
  aushebeln (heute der Weg, auf dem ein vollständig übersprungener xcodebuild-Lauf grün wird).
- Bestandener gemischter Lauf (≥ 1 bestanden, ≥ 1 übersprungen) bleibt **grün**, die Meldung
  nennt die Zahl: `Tests PASSED: 4 tests, 0 failures (1 skipped)` bzw.
  `Tests PASSED: 4 passed (1 skipped)`.

**B2. `tdd_enforcement`: RED-Artefakt nur mit Übersprungenem.** Keine Codeänderung nötig —
`skipped`/`⊘` steht nicht in `_FAILURE_RE`, ein solches Artefakt wird heute schon mit „keine
Fehler-Evidenz" abgewiesen. Es wird ein Regressionstest ergänzt, damit eine künftige
Muster-Erweiterung das nicht stillschweigend kippt.

**B3. `post_bash`: Fail-Guard und Hinweiswert `skipped`.**
- `_detect_test_output()` wendet `_FAILURE_EVIDENCE_RE` auf `strip_ansi(stdout)` an; das Muster
  wird um `✖`, `❌` und `\b[1-9]\d*\s+failures?\b` erweitert. Heute ergibt eine `✖`-/ANSI-Ausgabe
  zusammen mit irgendeinem Pass-Muster fälschlich `passed` (False-Pass).
- Gibt es keine bestandene Zählung (`\b[1-9]\d*\s+passed\b` fehlt, kein `Tests:.*passed`, kein
  `ok`/`test result: ok`) aber ein `\b[1-9]\d*\s+(?:tests?\s+)?skipped\b`, wird
  `last_test_run.result = "skipped"` geschrieben statt `passed`. Ein `** TEST SUCCEEDED **` allein
  zählt in diesem Fall nicht als bestanden. Es bleibt ein Hinweis (#253), kein Verdict.

**B4. Report-Vorlagen.** In allen vier Vorlagen bekommt die Testergebniszeile ein Feld
„übersprungen":
`60-validate.md` („Unit Tests: [N] passed, [N] failed, [N] übersprungen", ebenso Integration und
Full Suite), `82-test.md` („Tests: X passed, Y failed, Z übersprungen" in beiden Blöcken),
`implementation-validator.md` („Tests: X passed, 0 failed, Z übersprungen" in beiden Blöcken),
`test-runner.md` (beide Blöcke). Dazu je ein Satz: Ein Lauf mit 0 bestanden und ≥ 1 übersprungen
ist nicht grün. `skills/*/SKILL.md` danach per `python3 scripts/sync_skills.py` regenerieren
(`--check` meldet keine Drift).

### Fixtures (echte Ausgaben, nichts erfunden)

Unter `tests/fixtures/testausgabe_275/` liegen nur Ausgaben aus echten Läufen. Vorgehen, das in
`/40-tdd-red` ausgeführt wird (nicht im Spec-Schritt):
1. **xcbeautify „❌":** Ein xcodebuild-Rohlog mit Compiler-/Testfehler erzeugen (kleines
   Swift-Testpaket mit absichtlich fehlschlagendem Test, `xcodebuild test`), den Rohlog durch den
   lokal installierten `xcbeautify` (v3.2.1) leiten und die Ausgabe unverändert als Fixture
   speichern. Der Rohlog liegt als zweite Fixture daneben (Herkunft nachvollziehbar).
2. **ANSI-gefärbtes pytest-/Runner-FAIL:** Echter Lauf mit `pytest --color=yes` gegen einen
   fehlschlagenden Test, Ausgabe unverändert speichern.
3. **xcodebuild-Summary mit „skipped":** Echter `xcodebuild test`-Lauf mit einem `XCTSkip`-Test
   (einmal gemischt, einmal nur übersprungen), Summary-Zeile unverändert.
Lässt sich ein Fixture nicht echt erzeugen, wird das gemeldet — es wird nicht handgeschrieben.

## Expected Behavior

- **Input:** Test-/Artefakt-Ausgabetext (Datei bzw. Bash-stdout), ggf. mit ANSI-Codes, xcbeautify-
  Symbolen, `Executed … skipped …`-Summary oder pytest-Summary mit `skipped`.
- **Output:**
  - `tdd_enforcement`: Artefakt wird akzeptiert, wenn echte Fehler-Evidenz (auch hinter ANSI,
    `❌`/`✖`/`✘`, `TEST FAILED`, `Test run with … failed`, `N≥1 failures`, `EXIT≥1`) vorliegt;
    sonst abgewiesen wie bisher.
  - `qa_gate`: `(False, "Tests FAILED: …")` mit Zahl bei Fehlschlägen auch in der skipped-Variante;
    `(False, …)` bei 0 bestanden + ≥ 1 übersprungen (alle drei Wege) und bei
    `Executed 0 tests` (auch mit `TEST SUCCEEDED`); `(True, …)` mit genannter
    Zahl Übersprungener bei gemischtem Lauf.
  - `post_bash`: `failed` bei jeder Fehler-Evidenz (auch ANSI/`✖`/`❌`), `skipped` bei Lauf ohne
    Bestandenes und mit Übersprungenem, sonst wie bisher.
- **Side effects:** `last_test_run.result` kann neu den Wert `skipped` annehmen (nur Hinweis).

## Error Handling

- Alle neuen Muster sind rein lesend; ein nicht erkennbarer Output bleibt unbestimmbar
  (`Could not determine test result.` bzw. State unberührt) — die Fehlerrichtung ist überall
  „im Zweifel nicht grün": jede Fehler-Evidenz gewinnt gegen jedes Pass-Muster.
- `strip_ansi()` auf `None`/Nicht-String ist nicht vorgesehen; Aufrufer übergeben immer `str`
  (Datei mit `errors="replace"`, stdout aus `_extract_stdout`).

## Known Limitations

- Die Swift-Testing-Summary `Test run with N tests passed after …` kennt `qa_gate` weiterhin
  nicht (liefert „Could not determine test result."). Nur im RED-Check (`tdd_enforcement`) wird die
  Fehlerzeile `Test run with … failed` mit aufgenommen. Außer Scope.
- „Nichts gelaufen" wird in `qa_gate` nur über die `Executed 0 tests`-Zeile erkannt. Die
  pytest-Form `no tests ran` erkennt `_find_pytest_summary_line` heute nicht als Summary; sie
  bleibt wie bisher „Could not determine test result." (also ohnehin nicht grün). `post_bash`
  vermerkt einen Null-Lauf weiterhin nicht gesondert (nur Hinweis, kein Gate).
- Alternative für später: Statt Textmuster den Exit-Code bzw. das `.xcresult` auswerten
  (`EXIT=` steht schon in vielen Artefakten). Würde ANSI und „skipped" strukturell lösen, ist aber
  runner-spezifisch und scheitert an Artefakten, die den Exit-Code verlieren (xcbeautify-Pipes).
  Nicht Teil dieser Spec.
- Bewusst gesetzte Tests mit `XCTSkip`/`pytest.skip` in Projekten, die nur aus solchen Tests
  bestehen, gelten künftig als nicht bestanden. Das ist die beabsichtigte PO-Entscheidung vom
  2026-09-28 (Herkunft: Blindstelle 4 in #273).

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] Die drei Fehlerfälle (ANSI-`FAIL`, xcbeautify „❌", `Executed … skipped and 3 failures`) sind
      vor dem Fix gegen den heutigen Stand reproduziert (RED-Artefakt) und danach grün
- [ ] Die Gegenprobe ist grün: ein RED-Artefakt ohne jede Fehler-Evidenz (grüner Lauf) bleibt
      abgewiesen, `0 failures` öffnet nichts
- [ ] Fixtures stammen aus echten Läufen (xcbeautify-Fixture aus echtem `xcbeautify`-Lauf)
- [ ] Scheibe A und Scheibe B sind zwei getrennte Commits, in dieser Reihenfolge, beide grün
- [ ] `python3 scripts/sync_skills.py --check` meldet keine Drift
- [ ] `CHANGELOG.md` hat einen `[Unreleased]`-Eintrag (mit Scope-Hinweis), kein Versions-Bump
- [ ] Regressionslauf grün (insbesondere `tests/test_qa_gate.py`,
      `tests/test_gate_parser_fixes_73_76_79.py`)

## Acceptance Criteria

- **AC-1:** Given ein Text mit ANSI-Codes (`\x1b[31mFAIL\x1b[0m`) / When `hook_utils.strip_ansi()`
  darauf läuft / Then ist das Ergebnis `FAIL` ohne Steuerzeichen; Text ohne ANSI bleibt
  unverändert.
  - Test: `tests/test_testausgabe_erkennung_275.py::test_strip_ansi_removes_codes_keeps_plain`

- **AC-2:** Given eine ANSI-gefärbte pytest-Summary (echte Fixture, `--color=yes`) / When
  `qa_gate.validate_test_output()` läuft / Then entscheidet es wie bisher korrekt (grün bzw. rot);
  `qa_gate` enthält kein eigenes ANSI-Muster mehr (nur noch `hook_utils.strip_ansi`).
  - Test: `test_qa_gate_uses_shared_strip_ansi_pytest_color_summary`

- **AC-3 (#201):** Given ein RED-Artefakt, in dem `FAIL` von ANSI-Codes umgeben ist
  (`\x1b[31mFAIL\x1b[0m`) plus `EXIT=1`, ohne weitere Fehlerwörter / When die Fehler-Evidenz-Prüfung
  in `tdd_enforcement` läuft / Then wird das Artefakt akzeptiert.
  - Test: `test_ansi_wrapped_fail_with_exit1_accepted_as_red`

- **AC-4 (#256①):** Given die echte xcbeautify-Fixture, die Fehler nur mit „❌" (und ANSI) markiert,
  ohne `error:`/`FAILED` / When die Fehler-Evidenz-Prüfung läuft / Then wird das Artefakt
  akzeptiert; ebenso je ein Artefakt mit nur `✖`, nur `✘`, nur `TEST FAILED`, nur
  `Test run with 3 tests failed after 0.1 seconds`, nur `3 failures`.
  - Test: `test_xcbeautify_cross_mark_fixture_accepted_as_red` und
    `test_other_failure_markers_each_accepted_as_red`

- **AC-5 (Gegenprobe):** Given ein RED-Artefakt eines grünen Laufs ohne jede Fehler-Evidenz — auch
  eines, das `0 failures`, `EXIT=0` und ANSI-gefärbtes `PASSED` enthält / When die Prüfung läuft /
  Then wird es weiterhin abgewiesen („keine Fehler-Evidenz"); `0 failures` und `EXIT=0` öffnen
  nichts.
  - Test: `test_green_run_artifact_still_rejected_zero_failures_exit0`

- **AC-6 (#202):** Given `Executed 5 tests, with 1 test skipped and 3 failures (3 unexpected)` /
  When `qa_gate.validate_test_output()` läuft / Then ist das Ergebnis `False` mit Meldung
  `Tests FAILED` und der Zahl 3 — nicht „Could not determine test result.".
  - Test: `test_executed_skipped_variant_with_failures_reports_failed_count`

- **AC-7:** Given eine Ausgabe mit mehreren `Executed …`-Zeilen (Suite-Zeilen und Gesamtsumme am
  Ende) / When `qa_gate` läuft / Then zählt nur die letzte Zeile; die Meldung nennt die Zahlen der
  Gesamtsumme, nicht die Summe über alle Zeilen.
  - Test: `test_executed_uses_last_line_only`

- **AC-8:** Given `Executed 5 tests, with 1 test skipped and 0 failures` (4 bestanden) / When
  `qa_gate` läuft / Then ist das Ergebnis `True` und die Meldung nennt `1 skipped`.
  - Test: `test_executed_mixed_run_is_green_and_names_skipped`

- **AC-9 (#273-Regel, Executed + Fallback):** Given `Executed 5 tests, with 5 tests skipped and 0
  failures` und zusätzlich `** TEST SUCCEEDED **` / When `qa_gate` läuft / Then ist das Ergebnis
  `False` — weder der Executed-Zweig noch der `TEST SUCCEEDED`-Fallback werten es grün; die Meldung
  nennt 5 übersprungen. Ebenso `Executed 0 tests, with 0 failures` + `** TEST SUCCEEDED **`
  → `False` (nichts gelaufen).
  - Test: `test_executed_all_skipped_with_test_succeeded_is_not_green` und
    `test_executed_zero_tests_with_test_succeeded_is_not_green`

- **AC-10 (#273-Regel, pytest):** Given die pytest-Summary `0 passed, 5 skipped in 0.31s` bzw.
  `5 skipped in 0.31s` / When `qa_gate` läuft / Then `False`; Given `4 passed, 1 skipped in 0.31s`
  / Then `True` mit Meldung, die `1 skipped` nennt.
  - Test: `test_pytest_all_skipped_not_green_mixed_green_names_skipped`

- **AC-11 (RED nur mit Übersprungenem):** Given ein RED-Artefakt, das nur Übersprungenes zeigt
  (`5 skipped`, `⊘`, `Executed 5 tests, with 5 tests skipped and 0 failures`) und keinen
  Fehlschlag / When die Fehler-Evidenz-Prüfung läuft / Then wird es abgewiesen.
  - Test: `test_red_artifact_with_only_skipped_rejected`

- **AC-12 (post_bash Fail-Guard):** Given Bash-stdout eines `xcodebuild`-/`pytest`-Laufs mit ANSI-
  gefärbtem `✖` oder `❌` und zugleich einem Pass-Muster (z. B. `3 passed`) / When
  `post_bash._detect_test_output()` läuft / Then wird `last_test_run.result = "failed"`
  geschrieben, nicht `passed`.
  - Test: `test_post_bash_ansi_cross_marks_with_pass_pattern_recorded_failed`

- **AC-13 (post_bash skipped):** Given stdout ohne Bestandenes und mit Übersprungenem
  (`0 passed, 5 skipped` bzw. `5 tests skipped` + `** TEST SUCCEEDED **`) / When
  `_detect_test_output()` läuft / Then ist `last_test_run.result == "skipped"`; Given
  `4 passed, 1 skipped` / Then `"passed"`.
  - Test: `test_post_bash_only_skipped_recorded_skipped_mixed_passed`

- **AC-14 (Vorlagen):** Given `core/commands/60-validate.md`, `core/commands/82-test.md`,
  `core/agents/implementation-validator.md` und `core/agents/test-runner.md` / When man ihre
  Ergebniszeilen liest / Then enthält jede ein Feld „übersprungen" und den Satz, dass 0 bestanden +
  ≥ 1 übersprungen nicht grün ist; die generierten `skills/*/SKILL.md` sind synchron
  (`sync_skills.py --check` ohne Drift).
  - Test: `test_report_templates_have_skipped_field_and_skills_in_sync`

- **AC-15 (Regression):** Given die bestehenden Parser-Tests / When die Vollsuite läuft / Then
  bleiben `tests/test_qa_gate.py` und `tests/test_gate_parser_fixes_73_76_79.py` unverändert grün
  (Executed ohne skipped, Playwright-/go-test-/TAP-Fälle).
  - Test: `tests/test_qa_gate.py` und `tests/test_gate_parser_fixes_73_76_79.py` (Regressionslauf);
    zusätzlich `test_executed_without_skipped_unchanged_green_and_red`

## Test Plan

Automatische Tests (jeweils an eine AC gebunden), alle gegen die echten Hook-Funktionen:
- `python3 -m pytest tests/test_testausgabe_erkennung_275.py -q` (AC-1 bis AC-15)
- Regressionslauf: `python3 -m pytest tests/ -q` (insbesondere `tests/test_qa_gate.py`,
  `tests/test_gate_parser_fixes_73_76_79.py`, `tests/test_tdd_enforcement_embedded_content_262.py`,
  `tests/test_tdd_enforcement_placeholder_wordboundary_89.py`,
  `tests/test_tdd_enforcement_worktree_artifact_path_1478.py`,
  `tests/test_adversary_evidence_gate_253.py` — Letzterer konsumiert `last_test_run`)
- Drift-Check: `python3 scripts/sync_skills.py --check`
- Reihenfolge TDD-RED: zuerst Fixtures erzeugen (siehe „Fixtures"), dann Tests; die Tests zu
  AC-3/4/6/9/10/12/13 müssen gegen den heutigen Stand rot sein (Reproduktion), AC-5/AC-11/AC-15
  dürfen schon heute grün sein — sie sind Gegenproben bzw. Regressionsschutz.
- Pytest läuft im Scratchpad-venv mit `pytest` und `pyyaml` (kein System-pytest).

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine (`docs/adr/` existiert nicht; Entscheidungen stehen in den Specs)
- **Rationale:** Keine neue Architektur — Textmuster werden verbreitert, eine Regel kommt dazu,
  die ANSI-Entfernung wird von einer lokalen Stelle (`qa_gate`) an eine gemeinsame (`hook_utils`)
  gehoben. Ohne Modell, weil es deterministische Textmuster sind.
  *Verworfene Alternative 1 — Exit-Code/`.xcresult` statt Textmuster:* würde „skipped" und ANSI
  strukturell lösen, kippt aber die Entscheidung „Fehler-Evidenz per Text" (3.27.0); Artefakte
  ohne `EXIT=` (xcbeautify-Pipes verlieren ihn) wären unbewertbar. Als Ergänzung für später
  vermerkt (Known Limitations), nicht als Ersatz.
  *Verworfene Alternative 2 — „skipped" nur warnen statt als Fehlschlag werten:* weniger riskant
  für Projekte mit bewusstem `XCTSkip`, kippt aber die PO-Entscheidung vom 2026-09-28. Die Regel
  ist deshalb eng geschnitten: nur bei **null** Bestandenen; gemischte Läufe bleiben grün und
  nennen die Zahl.
  *Verworfene Alternative 3 — zwei getrennte Vorgänge/PRs:* wäre scoping-konform, wurde per
  PO-Entscheidung vom 2026-10-01 zugunsten eines Vorgangs mit zwei Commits verworfen (siehe
  Scope).

## Changelog

- 2026-10-01: Initial spec created
