---
entity_id: fix-508-tap-yaml-zitat
type: bugfix
created: 2026-11-04
updated: 2026-11-04
status: draft
version: "1.0"
workflow: fix-508-tap-yaml-zitat
tags: [tdd, tdd_enforcement, placeholder, tap, node]
---

# TAP-YAML-Diagnoseblöcke gelten als Zitat (Issue #508)

## Approval

- [ ] Approved

## Purpose

Die Platzhalter-Suche in `tdd_enforcement` lehnt echte RED-Artefakte von `node --test` ab, sobald der geprüfte Inhalt ein Wort wie `placeholder:` (z. B. die Tailwind-Klasse `placeholder:text-muted-foreground`) enthält. Der Runner zitiert diesen Inhalt im YAML-Diagnoseblock (`---` … `...`) unter der `not ok`-Zeile; die Suche hält den Block heute für Runner-Rahmen und sperrt damit in Phase 6 jeden Edit. Künftig gilt ein TAP-YAML-Diagnoseblock als Zitat, wie die pytest-Zitate aus #262. Die Platzhalter-Suche im übrigen Rahmen und die Fehler-Evidenz-Prüfung bleiben unverändert.

## Source

- **File:** `core/hooks/tdd_enforcement.py`
- **Identifier:** `tdd_enforcement._iter_frame_lines` (geändert), `tdd_enforcement._tap_yaml_quote_lines` (neu); genutzt, unverändert: `tdd_enforcement._find_placeholder`, `tdd_enforcement._validate_artifact`, `hook_utils.strip_ansi`

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `tdd_enforcement._iter_frame_lines` (#262, #421) | function | liefert die Rahmenzeilen; bekommt die TAP-YAML-Ausnahme |
| `tdd_enforcement._find_placeholder` | function | einziger Nutzer von `_iter_frame_lines`; unverändert |
| `tdd_enforcement._PLACEHOLDER_RE` (#89) | regex | bleibt unverändert |
| `tdd_enforcement._FAILURE_RE` | regex | läuft weiter auf dem ganzen Inhalt; unverändert |
| `hook_utils.strip_ansi` | function | Marker werden auf ANSI-bereinigten Zeilen erkannt |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| core/hooks/tdd_enforcement.py | MODIFY | neue Funktion `_tap_yaml_quote_lines`, `_iter_frame_lines` überspringt deren Zeilen; Modul-Docstring und Blockier-Hinweis nennen TAP-YAML-Blöcke |
| tests/test_tdd_enforcement_tap_yaml_508.py | CREATE | echter node-TAP-Fall, verschachtelte Subtests, Negativfälle (unvollständiger Block, falsche Stelle, falsche Einrückung), Rahmen nach dem Block |
| CHANGELOG.md | MODIFY | Eintrag unter [Unreleased] |

### Estimated Changes

- Files: 1 neu, 2 geändert
- LoC: +35/−3 Produktion / +220 Test
- Risk Level: MEDIUM (das Gate sieht weniger Zeilen: Platzhalter in einem formgerechten TAP-YAML-Block werden nicht mehr gemeldet; Fehler-Evidenz bleibt Pflicht, die Form ist eng definiert, unvollständige Blöcke bleiben Rahmen)

## Implementation Details

**`_tap_yaml_quote_lines(lines: list[str]) -> set[int]`** (neu, direkt vor `_iter_frame_lines`). Liefert die 0-basierten Indizes aller Zeilen, die zu einem TAP-YAML-Diagnoseblock gehören, Marker eingeschlossen. Alle Vergleiche auf `hook_utils.strip_ansi(line)`.

1. **Testzeile:** `^(\s*)(?:not )?ok\b` — Einrückung `t`.
2. **Blockbeginn** an Zeile `i`: Zeile `i` ist genau `<e>---` (nur Leerzeichen/Tab davor, nichts dahinter außer Whitespace), Zeile `i-1` ist eine Testzeile, und `len(e) > len(t)`.
3. **Blockende:** die erste Zeile `j > i`, deren `rstrip()` genau `e + "..."` ist (gleiche Einrückung wie `---`).
4. Gibt es `j`, gehören `i..j` zum Zitat; die Suche läuft bei `j+1` weiter. Gibt es kein `j`, gehört nichts davon zum Zitat (fail-closed: ein abgeschnittener Block bleibt Rahmen).

**`_iter_frame_lines`** berechnet die Menge einmal über `content.splitlines()` und überspringt diese Zeilen zusätzlich zu den bisherigen Ausnahmen. Zeilennummern im Ergebnis bleiben die des Originals. Die übrigen Ausnahmen (E/>-Zeilen, Captured-Blöcke, TAP-Summary, Compiler-Echo) bleiben in Reihenfolge und Wirkung gleich.

**Blockier-Meldung** in `_validate_artifact`: Der Hinweis „Zitierte Bereiche (…) sind ausgenommen“ nennt zusätzlich „TAP-YAML-Blöcke“. Sonst keine Textänderung.

**Warum eine `...`-Zeile auf Marker-Höhe sicher das Ende ist:** Die Schlüssel im Block stehen auf Höhe der Marker, Inhalte von Block-Skalaren (`error: |-`, `actual: |-`, `stack: |-`) tiefer. Eine `...`-Zeile mit genau der Marker-Einrückung kann deshalb kein zitierter Inhalt sein.

## Expected Behavior

- **Input:** Inhalt eines registrierten `test_output`-Artefakts
- **Output:** Platzhalter-Wörter (`TODO`, `PLACEHOLDER`, `FIXME`, Phrasen) in einem formgerechten TAP-YAML-Diagnoseblock führen nicht mehr zur Ablehnung. Dieselben Wörter außerhalb solcher Blöcke werden weiter mit Zeilennummer gemeldet.
- **Side effects:** keine; kein State, keine Dateien

## Known Limitations

- Der spec-Reporter (`node --test --test-reporter=spec`) zitiert die Assertion-Diff ohne YAML-Klammer unter `✖ failing tests:`. Ein `placeholder:` dort wird weiter gemeldet. Folge-Issue.
- Steht `placeholder:` im Testnamen (`not ok 1 - placeholder: …`) oder in einer `# Subtest:`-Zeile, bleibt es Rahmen und wird gemeldet. Der Testname ist Teil der eigenen Testdatei und lässt sich ändern.
- Wer ein Artefakt fälscht, kann Platzhalter in einen formgerechten YAML-Block legen. Die Fehler-Evidenz-Prüfung (`_FAILURE_RE` über den ganzen Inhalt), Größe, Alter und Beschreibung gelten weiter; die Platzhalter-Suche war nie ein Fälschungsschutz, sondern ein Copy-Paste-Filter.

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] Die im Kontext nachgestellte `node --test`-Ausgabe mit `placeholder:text-muted-foreground` wird als gültiges RED-Artefakt akzeptiert (Test)
- [ ] Die Tests aus #73, #89, #262, #349 und #421 bleiben unverändert grün
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf `pytest tests/` grün)

## Acceptance Criteria

Testaufbau: direkter Aufruf von `tdd_enforcement._validate_artifact(art, tmp_path)` bzw. `tdd_enforcement._find_placeholder(content)` mit echten Dateien in `tmp_path`, Artefakt-Typ `test_output`, Beschreibung ≥ 10 Zeichen (Stil wie `tests/test_tdd_enforcement_embedded_content_262.py`). Kein Mock.

- **AC-1:** Given die wörtliche TAP-Ausgabe von `node --test` (node v22) mit `placeholder:text-muted-foreground` und `TODO` im `error: |-`-Block (inkl. `+ actual - expected`-Diff) und im `actual: |-`-Block, abschließender Summary `# fail 3` / When `_validate_artifact` läuft / Then ist das Ergebnis `None`
  - Test: tests/test_tdd_enforcement_tap_yaml_508.py::TestRealNodeTap::test_real_node_tap_output_with_placeholder_in_yaml_is_valid

- **AC-2:** Given eine TAP-Ausgabe mit verschachteltem Subtest (Testzeile 4 Leerzeichen eingerückt, YAML-Block 6 Leerzeichen) und `placeholder:` nur im inneren Block / When `_find_placeholder` läuft / Then ist das Ergebnis `None`
  - Test: tests/test_tdd_enforcement_tap_yaml_508.py::TestRealNodeTap::test_nested_subtest_yaml_block_is_quote

- **AC-3:** Given eine TAP-Ausgabe, deren YAML-Block hinter `not ok` mit `---` beginnt, aber kein `...` auf gleicher Einrückung folgt, und `placeholder:` im Block / When `_find_placeholder` läuft / Then wird die Zeile mit `placeholder:` mit ihrer Original-Zeilennummer gemeldet
  - Test: tests/test_tdd_enforcement_tap_yaml_508.py::TestNegativeCasesStayFrame::test_unclosed_yaml_block_stays_frame

- **AC-4:** Given eine `---`/`...`-Klammer mit `TODO` darin, deren `---` (a) am Dateianfang steht, (b) auf eine Kommentarzeile `# Subtest: x` folgt, (c) auf eine Leerzeile nach `not ok 1 - x` folgt / When `_find_placeholder` läuft / Then wird jeweils die `TODO`-Zeile gemeldet
  - Test: tests/test_tdd_enforcement_tap_yaml_508.py::TestNegativeCasesStayFrame::test_yaml_block_without_preceding_test_line_stays_frame

- **AC-5:** Given `not ok 1 - x` gefolgt von `---` auf derselben Einrückung (nicht tiefer), `TODO` und `...` / When `_find_placeholder` läuft / Then wird die `TODO`-Zeile gemeldet
  - Test: tests/test_tdd_enforcement_tap_yaml_508.py::TestNegativeCasesStayFrame::test_yaml_block_not_indented_deeper_stays_frame

- **AC-6:** Given ein formgerechter YAML-Block mit `placeholder:` und danach eine Rahmenzeile `# TODO: echte Ausgabe einfuegen` / When `_validate_artifact` läuft / Then lautet das Ergebnis „Artefakt enthält Platzhalter-Text“ mit der Zeilennummer der `# TODO`-Zeile
  - Test: tests/test_tdd_enforcement_tap_yaml_508.py::TestNegativeCasesStayFrame::test_frame_after_yaml_block_is_still_checked

- **AC-7:** Given ein formgerechter YAML-Block, dessen Inhalt eine tiefer eingerückte `...`-Zeile und danach `placeholder:` enthält / When `_find_placeholder` läuft / Then ist das Ergebnis `None` (nur `...` auf Marker-Höhe beendet den Block)
  - Test: tests/test_tdd_enforcement_tap_yaml_508.py::TestNegativeCasesStayFrame::test_deeper_indented_dots_do_not_end_block

- **AC-8:** Given eine TAP-Ausgabe nur mit `ok`-Zeilen und YAML-Blöcken ohne Fehlerwörter, Summary `# pass 1` / When `_validate_artifact` läuft / Then lautet das Ergebnis weiterhin „RED-Artefakt zeigt keine Fehler-Evidenz“
  - Test: tests/test_tdd_enforcement_tap_yaml_508.py::TestUnchangedBehaviour::test_failure_evidence_check_unchanged

- **AC-9:** Given ein Artefakt mit `placeholder:` im Rahmen / When `_validate_artifact` es ablehnt / Then nennt die Meldung „TAP-YAML“ unter den ausgenommenen Bereichen
  - Test: tests/test_tdd_enforcement_tap_yaml_508.py::TestUnchangedBehaviour::test_block_message_mentions_tap_yaml

- **AC-10:** Given `CHANGELOG.md` / When gelesen / Then steht unter `[Unreleased]` oder im obersten Versionsabschnitt (Release im selben PR) ein Eintrag, der `#508` nennt
  - Test: tests/test_tdd_enforcement_tap_yaml_508.py::test_changelog_mentions_508

## Test Plan

- `pytest tests/test_tdd_enforcement_tap_yaml_508.py`
- `pytest tests/test_tdd_enforcement_embedded_content_262.py tests/test_tdd_enforcement_compiler_echo_421.py tests/test_tdd_enforcement_spec_reporter_349.py tests/test_tdd_enforcement_placeholder_wordboundary_89.py tests/test_gate_parser_fixes_73_76_79.py`
- Regressionslauf: `pytest tests/`
- `python3 -m py_compile core/hooks/tdd_enforcement.py`

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Fehlerkorrektur innerhalb der vorhandenen Zitat-Logik (#262/#421): eine weitere, eng umrissene Zitat-Form. Kein neues State-Feld, kein neues Gate, reversibel durch Rückbau der Funktion. Verworfen: (a) `_PLACEHOLDER_RE` verengen (`placeholder:` ausnehmen) — ließe echte Platzhalter im Rahmen durch und hilft nicht bei `TODO` im Zitat; (b) ganze Zeilen ab `error:` bis Dateiende überspringen — zu grob, versteckt Rahmen; (c) unvollständige Blöcke bis Dateiende als Zitat werten — fail-open.

## Changelog

- 2026-11-04: Initial spec created
- 2026-11-04: Test-IDs mit Klassennamen der Testdatei
