# Context: fix-421-compiler-echo

## Request Summary
`tdd_enforcement` lehnt ein echtes RED-Artefakt als „Platzhalter-Text“ ab, weil der Swift-Compiler eine
Quellzeile mit dem Wort „placeholder“ zitiert (`79 |     @Test("… the usual placeholder")`). Dadurch ist
jede Bearbeitung von Produktcode gesperrt (Issue #421, Fundort: henemm/loose-ends, Workflow 279-pegel-mikrofon).

## Reproduktion (2026-10-11)
Das Original-Artefakt `loose-ends/docs/artifacts/279-pegel-mikrofon/test-red-hinweis.txt` wurde direkt durch
`tdd_enforcement._find_placeholder()` geschickt. Ergebnis: Fund in Zeile 30
(`79 |     @Test("Not listening with an empty field shows the usual placeholder")`). Fehler reproduziert.

Hat es bisher funktioniert? Nein. Die Korrektur aus #262 (PR #274) nimmt nur pytest-Zitate aus (`E `, `> `,
`Captured …`). Quellzeilen-Echos des Swift-Compilers (Format `NN | code`, Swift 6 Standard-Diagnosestil) waren nie
ausgenommen.

## Related Files
| File | Relevance |
|------|-----------|
| core/hooks/tdd_enforcement.py:102 `_QUOTED_LINE_RE` | erkennt nur pytest-Zitate (`E`, `>`) |
| core/hooks/tdd_enforcement.py:117 `_iter_frame_lines` | liefert die Zeilen, die als „Runner-Rahmen“ gelten; hier fehlt die Ausnahme für `NN |`-Echos |
| core/hooks/tdd_enforcement.py:141 `_find_placeholder` | einzige Aufrufstelle der Rahmen-Suche (Zeile 209) |
| core/hooks/hook_utils.py `strip_ansi` | wird schon für `_FAILURE_RE` benutzt; Echo-Zeilen tragen im Original teils Farbcodes (`ESC[36m70 |`) |
| tests/test_tdd_enforcement_embedded_content_262.py | Vorbild: Klassen für „Zitat ausgenommen“, „Fälschung weiter blockiert“, „Meldung nennt Zeile“ |

## Existing Patterns
- #262: Platzhalter-Suche sieht nur den Rahmen des Runners; zitierter Fremdinhalt ist ausgenommen.
- #73/#349: `_TAP_SUMMARY_RE` entfernt Zusammenfassungszeilen vor der Suche.
- Leitsatz aus #262: Fehlalarme beseitigt man, ohne das Gate zu lockern (kein pauschales Durchwinken).

## Zielformat des Echos (aus echten Artefakten in Loose Ends)
- `79 |     @Test("…")` – Nummer, `|`, Quelltext (Compiler-Echo einer Zeile)
- `ESC[36m70 |     func foo() {ESC[0m` – dasselbe, farbig
- Das Echo steht nach einer `❌ pfad:zeile:spalte: …`-Fehlerzeile; xcbeautify/xcodebuild liefern es mit.
- Rauschen-Beispiele ohne das Wort (46 |, 210 |, 170 |) zeigen: das Format ist durchgehend, nicht ein Einzelfall.

## Dependencies
- Upstream: `re`, `hook_utils.strip_ansi`
- Downstream: Registrierung von RED-Artefakten in allen Konsumenten-Projekten (PreToolUse Edit|Write)

## Existing Specs
- Keine Spec zu #262/#274 im Repo gefunden, die zu ändern wäre; Verhalten ist durch die Tests in
  `tests/test_tdd_enforcement_embedded_content_262.py` und `…placeholder_wordboundary_89.py` festgelegt.

## Risks & Considerations
- **Fälschungsrisiko:** Wer ein Artefakt erfindet, könnte „TODO“ in eine Zeile `12 | …` setzen. Mitigation: nur das
  strenge Format `^\s*\d+\s\|` (Nummer, Leerraum, Pipe) wird ausgenommen; Text ohne diese Form bleibt geprüft. Ein
  erfundenes Artefakt braucht ohnehin weiter echte Fehler-Evidenz (`_FAILURE_RE`).
- **Zeilen wie `| Spalte |` in Markdown-Tabellen** beginnen ohne Zahl und bleiben unberührt.
- **ANSI:** Muster muss nach `strip_ansi` greifen, sonst bleibt die farbige Variante ein Fehlalarm.
- Alternative (verworfen): nur auf Compiler-Fehlerzeilen reagieren (`error:`/`❌`) – bricht bei Runnern ohne diese Marker.

## Analysis

### Type
Bug (Fehlalarm im Gate). Reproduziert am Original-Artefakt, siehe oben. Kein Rückschritt: Swift-Echo war nie ausgenommen.

### Ohne Modell geht es, weil
Rein deterministisch: Das Echo hat ein festes Zeilenformat (`NN | code`). Eine Regex genügt, kein Modell.

### Affected Files (with changes)
| File | Change Type | Description |
|------|-------------|-------------|
| core/hooks/tdd_enforcement.py | MODIFY | `_COMPILER_ECHO_RE` (`^\s*\d+\s\|`) und Prüfung in `_iter_frame_lines` nach `hook_utils.strip_ansi(line)` |
| tests/test_tdd_enforcement_compiler_echo_421.py | CREATE | Echo ausgenommen (plain + ANSI), Fälschung `TODO` in Rahmenzeile weiter geblockt, `| TODO |`-Tabellenzeile weiter geblockt, Meldung nennt Zeile |
| CHANGELOG.md | MODIFY | Eintrag unter [Unreleased] |

### Scope Assessment
- Files: 3
- Estimated LoC: +~10 Produktcode, +~90 Test, +3 Changelog
- Risk Level: LOW — verengt nur die Suche, jede Echo-Zeile verlangt Ziffern + Leerraum + Pipe am Zeilenanfang

### Technical Approach
Gleiches Muster wie #262: Zitat-Zeilen gehören nicht zum Runner-Rahmen. Neue Regex für Compiler-Echo, angewandt auf die ANSI-bereinigte Zeile (farbiges Echo trägt `ESC[36m` vor der Nummer). `_FAILURE_RE` bleibt unverändert, ein erfundenes Artefakt braucht weiter echte Fehler-Evidenz.

### Alternativen
1. **Wortliste enger fassen** (Issue-Erwartung: nur `<placeholder>`, `TODO: output`, `[test output here]`): lockert das Gate pauschal, widerspricht dem Leitsatz aus #262 („Fehlalarme beseitigen, ohne das Gate zu lockern“). Verworfen.
2. **Nur Zeilen nach einer `❌`/`error:`-Zeile ausnehmen**: bricht bei Runnern ohne diese Marker, mehr Zustand. Verworfen.
3. **Gate abschaffen, Fälschung nur per `_FAILURE_RE` erkennen**: kippt die Entscheidung aus #73/#89. Nicht empfohlen.
Gekippte frühere Entscheidung bei der Empfehlung: keine.

### Dependencies
`re`, `hook_utils.strip_ansi` (bereits importiert und in Zeile 221 genutzt).

### Open Questions
- Keine. Unnummerierte Gutter-Zeilen (`   |   ^~~~`) bleiben bewusst geprüft (Markdown-Tabellen `| TODO |` dürfen nicht durchrutschen); sie enthalten in der Praxis keine Platzhalterwörter.
