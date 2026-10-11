---
entity_id: fix-421-compiler-echo
type: bugfix
created: 2026-10-11
updated: 2026-10-11
status: draft
workflow: fix-421-compiler-echo
version: "1.0"
tags: [tdd-enforcement, red-artifact, placeholder, compiler-echo, swift, false-positive]
test_targets: ["tests/test_tdd_enforcement_compiler_echo_421.py"]
---

# RED-Gate lehnt echtes Artefakt wegen Compiler-Quellzeilen-Echo ab — #421

## Approval

- [ ] Approved

## GitHub Issue

- **Issue:** #421 (Fundort: henemm/loose-ends, Workflow 279-pegel-mikrofon). Die Ausnahme für pytest-Zitate ist in #262/#274 geregelt und nicht Teil dieser Spec.

## Purpose

`tdd_enforcement._find_placeholder` lehnt ein echtes RED-Artefakt als „Platzhalter-Text“ ab, weil der Swift-Compiler eine Quellzeile des Prüfgegenstands zitiert, die das Wort „placeholder“ enthält: `79 |     @Test("Not listening with an empty field shows the usual placeholder")`. Die Folge: Jede Bearbeitung von Produktcode in phase6 ist gesperrt, obwohl das Artefakt echte Fehler zeigt.

Nachgestellt am 2026-10-11: Das Original-Artefakt `loose-ends/docs/artifacts/279-pegel-mikrofon/test-red-hinweis.txt` wurde direkt durch `_find_placeholder()` geschickt. Ergebnis: Fund in Zeile 30 (die Echo-Zeile oben). Hat es bisher funktioniert? Nein: Die Ausnahme aus #262 kennt nur pytest-Zitate (`E `, `> `, `Captured …`); das Quellzeilen-Echo des Swift-Compilers (Format `NN | code`, Swift-6-Standarddiagnose) war nie ausgenommen. Es ist also kein Rückschritt, sondern eine Lücke.

Die Lösung ist regelbasiert (eine Regex auf ein festes Zeilenformat), ohne Modell. Ohne Modell geht es, weil das Echo ein starres Zeilenformat hat: Nummer, Leerraum, Pipe, Quelltext.

## Source

- **Analyse:** `docs/context/fix-421-compiler-echo.md` (Abschnitte „Reproduktion“, „Zielformat des Echos“, „Analysis“, „Alternativen“)
- **Ursprungsanfrage:** GitHub-Issue #421
- **Vorbild:** #262/#274 (zitierter Fremdinhalt gehört nicht zum Runner-Rahmen), #73/#349 (`_TAP_SUMMARY_RE`)
- **Bestandstests:** `tests/test_tdd_enforcement_embedded_content_262.py`, `tests/test_tdd_enforcement_placeholder_wordboundary_89.py`

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `core/hooks/tdd_enforcement.py` (`_iter_frame_lines`, `_find_placeholder`, `_QUOTED_LINE_RE`) | Modul | Hier liegt die Lücke; einzige Aufrufstelle der Rahmen-Suche ist `_validate_artifact` |
| `core/hooks/hook_utils.py` (`strip_ansi`) | Modul | Wird bereits für `_FAILURE_RE` genutzt; farbige Echo-Zeilen tragen `ESC[36m` vor der Nummer |
| `tests/test_tdd_enforcement_embedded_content_262.py` | Test | Bestandstest (Zitat ausgenommen, Fälschung blockiert, Meldung nennt Zeile); muss grün bleiben |
| `tests/test_tdd_enforcement_placeholder_wordboundary_89.py` | Test | Bestandstest Wortgrenze; muss grün bleiben |
| Downstream | Kern-Gates | PreToolUse Edit/Write in allen Konsumentenprojekten (RED-Artefakt-Validierung) |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| `core/hooks/tdd_enforcement.py` | MODIFY | Neue `_COMPILER_ECHO_RE = ^\s*\d+\s\|`; in `_iter_frame_lines` wird die Zeile nach `hook_utils.strip_ansi` geprüft und bei Treffer wie ein Zitat übersprungen |
| `tests/test_tdd_enforcement_compiler_echo_421.py` | CREATE | Echo plain und mit ANSI ausgenommen; Fälschungen und Tabellenzeile weiter geblockt; Meldung nennt Originalzeile; Original-Fixture akzeptiert |
| `CHANGELOG.md` | MODIFY | Eintrag unter `[Unreleased]`, keine Versionsanhebung |

### Estimated Changes

- Files: 3 (innerhalb der Grenze von 4-5 Dateien).
- LoC: ca. +103 (Produktcode ca. +10, Tests ca. +90, CHANGELOG ca. +3); innerhalb von ±250. Spec, Kontext und Briefing zählen im LoC-Gate zusätzlich als Code (#294, Fehlalarm).
- Alle Funktionen bleiben unter 50 Zeilen.
- Risiko LOW: Die Änderung verengt nur die Suche; jede ausgenommene Zeile verlangt Ziffern, Leerraum und Pipe am Zeilenanfang.

## Implementation Details

**1. Regex.** Neben `_QUOTED_LINE_RE` kommt `_COMPILER_ECHO_RE = re.compile(r"^\s*\d+\s\|")` mit Kommentar: Quellzeilen-Echo des Compilers (Swift 6, xcodebuild/xcbeautify), z. B. `79 |     @Test("…")`. Das Echo ist zitierter Fremdinhalt, gleiche Begründung wie #262.

**2. Anwendung in `_iter_frame_lines`.** Nach den bestehenden Prüfungen (`_QUOTED_LINE_RE`, `_TAP_SUMMARY_RE`) wird `_COMPILER_ECHO_RE.match(hook_utils.strip_ansi(line))` geprüft; bei Treffer `continue`. Die ANSI-Bereinigung ist nötig, weil farbiges Echo (`ESC[36m70 |     func foo() {ESC[0m`) sonst nicht am Zeilenanfang mit der Nummer beginnt. Die Zeilennummern bleiben die des Originals (`enumerate` über `content.splitlines()` unverändert), damit die Blockier-Meldung weiter die richtige Fundzeile nennt.

**3. Unverändert.** `_FAILURE_RE` bleibt wie es ist: Ein erfundenes Artefakt braucht weiter echte Fehler-Evidenz. `_PLACEHOLDER_RE`, Blockier-Meldung und alle Pytest-Ausnahmen bleiben.

**4. Reihenfolge der Umsetzung:** RED-Tests, Regex plus Prüfung, CHANGELOG, Bestandstests, Vollsuite, Adversary.

## Expected Behavior

- **Input:** Ein `test_output`-Artefakt, in dem der Compiler eine Quellzeile des Prüfgegenstands mit einem Platzhalterwort zitiert (`NN | code`), plain oder mit ANSI-Farbcodes.
- **Output:** Die Echo-Zeile wird bei der Platzhalter-Suche übersprungen; das Artefakt wird akzeptiert, sofern es echte Fehler-Evidenz enthält. Platzhalter in Rahmenzeilen ohne die Form `NN |` und in Tabellenzeilen `| TODO |` blockieren weiter, die Meldung nennt die Originalzeile.
- **Side effects:** Keine neuen Abhängigkeiten, Config-Keys, State-Formate oder Dateipfade. Keine Änderung an Signaturen.

## Known Limitations

- **Unnummerierte Gutter-Zeilen bleiben bewusst geprüft** (`   |   ^~~~`, `   | `): Sie beginnen ohne Zahl und könnten mit Markdown-Tabellen `| TODO |` verwechselt werden, die nicht durchrutschen dürfen. In der Praxis enthalten sie keine Platzhalterwörter.
- **Fälschungsrisiko in der Echo-Form:** Wer ein Artefakt erfindet, könnte „TODO“ in eine Zeile `12 | …` setzen und so der Wortsuche entgehen. Das ist durch `_FAILURE_RE` begrenzt: Ohne echte Fehler-Evidenz bleibt das Artefakt abgelehnt. Das Gate war nie fälschungssicher gegen absichtliche Täuschung, es fängt Versehen.
- Verteilung: wirkt in Konsumentenprojekten erst nach dem Plugin-Update.

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Der Fehlalarm ist durch einen vorher roten, danach grünen automatischen Test belegt (RED-Artefakt registriert)
- [ ] Die Gegenproben (Fälschung, Tabellenzeile) bleiben geblockt
- [ ] Die Bestandstests aus #262 und #89 sind unverändert grün, die Vollsuite ist grün
- [ ] `CHANGELOG.md` ist unter `[Unreleased]` aktualisiert, ohne Versionsanhebung
- [ ] Adversary-Dialog (Hook-Code) hat VERIFIED mit gültigem Artefakt

## Acceptance Criteria

Testdatei: `tests/test_tdd_enforcement_compiler_echo_421.py`. Die Bestandstests aus #262 und #89 laufen unverändert mit.

- **AC-1:** Given ein Artefakttext mit einer Compiler-Echo-Zeile `79 |     @Test("… the usual placeholder")` (plain) / When `_find_placeholder` ihn prüft / Then wird kein Fund gemeldet (`None`; vor der Änderung rot)
  - Test: tests/test_tdd_enforcement_compiler_echo_421.py::test_echo_zeile_plain_wird_nicht_gefunden
- **AC-2:** Given dieselbe Zeile mit ANSI-Farbcodes (`ESC[36m70 |     func foo() { // placeholder ESC[0m`) / When `_find_placeholder` prüft / Then wird kein Fund gemeldet
  - Test: tests/test_tdd_enforcement_compiler_echo_421.py::test_echo_zeile_mit_ansi_wird_nicht_gefunden
- **AC-3:** Given „TODO“ bzw. „placeholder“ in einer Rahmenzeile ohne die Form `NN |` (z. B. `Test output: TODO`) / When `_find_placeholder` prüft / Then wird sie weiter gefunden (Fälschung bleibt geblockt)
  - Test: tests/test_tdd_enforcement_compiler_echo_421.py::test_faelschung_in_rahmenzeile_bleibt_geblockt
- **AC-4:** Given eine Markdown-Tabellenzeile `| TODO |` ohne führende Zahl / When `_find_placeholder` prüft / Then wird sie weiter gefunden
  - Test: tests/test_tdd_enforcement_compiler_echo_421.py::test_tabellenzeile_ohne_zahl_bleibt_geblockt
- **AC-5:** Given ein Artefakt mit Echo-Zeile (übersprungen) und einer späteren echten Platzhalter-Rahmenzeile / When `_validate_artifact` es prüft / Then nennt die Blockier-Meldung die Zeilennummer des Originals und die Fundzeile
  - Test: tests/test_tdd_enforcement_compiler_echo_421.py::test_meldung_nennt_originalzeile
- **AC-6:** Given ein nachgebautes Original-Artefakt der Reproduktion (Compiler-Fehlerzeile `❌ pfad:zeile:spalte: …`, Echo mit „placeholder“, echte Fehler-Evidenz) / When `_validate_artifact` es prüft / Then wird es akzeptiert (`None`; vor der Änderung rot)
  - Test: tests/test_tdd_enforcement_compiler_echo_421.py::test_original_artefakt_der_reproduktion_wird_akzeptiert
- **AC-7:** Given der Bestandstestbestand / When `tests/test_tdd_enforcement_embedded_content_262.py` und `tests/test_tdd_enforcement_placeholder_wordboundary_89.py` laufen / Then bleiben sie grün
  - Test: tests/test_tdd_enforcement_embedded_content_262.py und tests/test_tdd_enforcement_placeholder_wordboundary_89.py (unverändert, Lauf grün)
- **AC-8:** Given `CHANGELOG.md` / When er gelesen wird / Then enthält `[Unreleased]` einen Eintrag zu #421 und es gibt keine Versionsanhebung
  - Test: tests/test_tdd_enforcement_compiler_echo_421.py::test_changelog_nennt_421

> Die Test-Zuordnung wird **bei der Spec-Erstellung** eingetragen, nicht nachträglich:
> Nach der Freigabe ist diese Datei eingefroren (#230). Stimmt ein Testname später nicht
> mehr, gehört die Korrektur in die TDD-RED-Artefakte, nicht in diese Datei.

## Test Plan

### Automated Tests (TDD RED)

Datei: `tests/test_tdd_enforcement_compiler_echo_421.py`; Aufbau wie `tests/test_tdd_enforcement_embedded_content_262.py` (Klassen für „Zitat ausgenommen“, „Fälschung weiter blockiert“, „Meldung nennt Zeile“).

- [ ] Test 1 (AC-1, AC-2): GIVEN Echo-Zeile plain bzw. mit ANSI, WHEN `_find_placeholder`, THEN `None` (RED vor Fix: Fund)
- [ ] Test 2 (AC-3, AC-4): GIVEN Rahmenzeile mit TODO bzw. `| TODO |`, WHEN `_find_placeholder`, THEN Fund (vor und nach der Änderung grün)
- [ ] Test 3 (AC-5): GIVEN Echo plus späterer echter Fund, WHEN `_validate_artifact`, THEN Meldung nennt die Originalzeile
- [ ] Test 4 (AC-6): GIVEN nachgebautes Original-Artefakt, WHEN `_validate_artifact`, THEN akzeptiert (RED vor Fix: Ablehnung)
- [ ] Test 5 (AC-7, AC-8): GIVEN Bestandstests und CHANGELOG, WHEN sie laufen, THEN grün

Der RED-Lauf wird als Artefakt registriert.

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Die Änderung erweitert die in #262 getroffene Entscheidung („die Platzhalter-Suche sieht nur den Runner-Rahmen, zitierter Fremdinhalt ist ausgenommen“) um eine weitere Zitatform. Keine bestehende ADR wird gekippt, kein neues Format, keine Abhängigkeit, keine Migration.

**Entscheidung:** Neue Regex `^\s*\d+\s\|` auf der ANSI-bereinigten Zeile, Echo-Zeilen werden wie Zitate übersprungen. Regelweg zuerst: Das Echo hat ein festes Zeilenformat, ein Modell ist nicht nötig.

**Alternativen (bewertet):**

- **Wortliste enger fassen** (Issue-Erwartung: nur `<placeholder>`, `TODO: output`, `[test output here]`): lockert das Gate pauschal und widerspricht dem Leitsatz aus #262 („Fehlalarme beseitigen, ohne das Gate zu lockern“). Verworfen.
- **Nur Zeilen nach einer `❌`/`error:`-Zeile ausnehmen:** bricht bei Runnern ohne diese Marker und braucht Zustand über Zeilen hinweg. Verworfen.
- **Gate abschaffen, Fälschung nur per `_FAILURE_RE` erkennen:** kippt die Entscheidung aus #73/#89. Nicht empfohlen, verworfen.
- **Nichts tun:** Jede Swift-Testausgabe, die ein Platzhalterwort zitiert, sperrt die Code-Bearbeitung. Verworfen.

Gekippte frühere Entscheidung: keine.

## Changelog

- 2026-10-11: Initial spec created (#421)
