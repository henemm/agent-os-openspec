# Context: fix-275-testausgabe-erkennung

## Request Summary
Issue #275 (fasst #201, #202, #256①): Die Erkennung von Testläufen ist zu eng gefasst und blockiert
legitime Arbeit — ANSI-Farbcodes verdecken `FAIL`, xcbeautify markiert Fehler nur mit „❌",
xcodebuild-Summary mit „skipped" wird nicht gelesen. Per PO-Entscheidung 2026-09-28 (Kommentar am
Issue) kommt aus #273 dazu: **ein Lauf ohne bestandene Tests und mit Übersprungenem ist kein Erfolg.**

## Related Files
| File | Relevance |
|------|-----------|
| `core/hooks/qa_gate.py` | `validate_test_output()` — `Executed N tests, with M failures` (Z.133, kennt kein `skipped`); pytest-Summary (`_find_pytest_summary_line`, hat eigenen `ansi_re`, Z.100); `TEST SUCCEEDED`-Fallback |
| `core/hooks/tdd_enforcement.py` | `_FAILURE_RE` (Z.54) mit `\b`, Prüfung Z.218 auf Rohtext — kein ANSI-Strip, kein „❌" |
| `core/hooks/post_bash.py` | `_FAILURE_EVIDENCE_RE` (Z.33), `pass_patterns` (Z.81) — kennt weder ANSI, „❌" noch „skipped" |
| `core/hooks/hook_utils.py` | Ziel für den gemeinsamen Helfer (ANSI-Entfernung an genau einer Stelle) |
| `core/agents/implementation-validator.md` (Z.148,178), `core/agents/test-runner.md` (Z.39,46), `core/commands/82-test.md` (Z.59,65), `core/commands/60-validate.md` (Z.206-208) + gespiegelte `skills/*/SKILL.md` | Report-Vorlagen kennen nur passed/failed (Feld für „skipped" fehlt) |
| `tests/test_qa_gate.py` (13 Tests), `tests/test_gate_parser_fixes_73_76_79.py` | Bestehende Tests für die Parser; hier kommen die Regressionstests hin |

## Existing Patterns
- ANSI-Entfernung existiert schon einmal lokal in `qa_gate._find_pytest_summary_line` (`\x1b\[[0-9;]*[A-Za-z]`), wird pro Zeile angewendet.
- Fehlerrichtung ist überall „im Zweifel nicht grün": jede FAIL-Evidenz gewinnt gegen PASS (go test, post_bash-Guard).
- `skills/` wird per `scripts/sync_skills.py` aus `core/commands/` erzeugt → Vorlagen nur in `core/` ändern, dann Sync.

## Dependencies
- Upstream: nur Python-Stdlib (`re`, `pathlib`).
- Downstream: `qa_gate` setzt das Verdict → `bash_gate` prüft es beim Commit; `tdd_enforcement` erlaubt/blockiert Edits in phase6; `post_bash` schreibt `last_test_run` → Adversary-Nachweis (#253). Ein Fehler in der Erkennung blockiert Commits bzw. Neuanlagen von Dateien.

## Existing Specs
- Keine Spec zu den Parsern. Verwandt: #273 (Epic Erreichbarkeit, Blindstelle 4 „übersprungen"), Kontext `docs/context/feat-273-erreichbarkeitspruefung.md`.

## Risks & Considerations
- **Scope-Überschreitung:** Issue schätzt <120 Zeilen für 3 Dateien. Mit der „skipped"-Regel aus #273 sind es 4 Hooks + 4 Vorlagen + Sync + Tests → über dem Limit von 4-5 Dateien/±250 LoC. In `/20-analyse` Schnitt vorschlagen (z. B. Scheibe A: ANSI + xcbeautify + `Executed…skipped`; Scheibe B: „skipped ≠ Erfolg" + Vorlagen).
- **False-Pass-Richtung:** Jede neue Erkennung darf nie einen echten Fehlschlag grün werten. Gegenprobe Pflicht (RED-Artefakt ohne jede Evidenz bleibt abgewiesen).
- `Executed 0 tests` / nur-Übersprungenes: Regel „nichts gelaufen öffnet kein Gate" muss auch den `** TEST SUCCEEDED **`-Fallback abdecken (heute grün).
- Echte Beispielausgaben nötig (xcbeautify mit „❌", ANSI-gefärbtes FAIL) — als Fixtures unter `tests/fixtures/`; keine erfundenen.
- Reproduktion zuerst: die drei Fälle gegen den heutigen Stand auslösen, bevor etwas geändert wird.
- Alternative zur Verbreiterung der Regex: Statt Text-Mustern xcodebuild-Exit-Code/`.xcresult` auswerten (`EXIT=` steht schon in Artefakten) — würde #273-Blindstelle 4 strukturell lösen; Preis: Runner-spezifisch, Artefakte müssen den Exit-Code enthalten.

## Analysis

### Type
Bugfix (drei Erkennungslücken, #201/#202/#256①) + eine neue Regel (#273: „nichts bestanden + übersprungen = kein Erfolg"). Rein regelbasiert, kein Modell nötig — es sind Textmuster.

### Recherche (vor allem anderen, mit Quellen)
- xcbeautify-Quelltext `Sources/XcbeautifyLib/Constants.swift` (cpisciotta/xcbeautify, v3.2.1 lokal installiert): Testfall-Fehlschlag `✖`, bestanden `✔`, übersprungen `⊘`, **Fehler/Compilerfehler `❌`** (ASCII-Variante `[x]`); Farbe per ANSI (`ESC[31m…ESC[0m`). Die `Executed N tests, with …`-Summary reicht xcbeautify unverändert durch (`formatExecutedWith(out)Skipped → group.wholeResult`). Swift Testing: `Test run with N tests failed after …`.
- xcodebuild-Summary: `Executed 5 tests, with 1 test skipped and 0 failures (0 unexpected) in …` (Apple-Format, bestätigt durch Parser in Chromium `xcode_log_parser.py` u. a.). Es gibt eine eigene `ExecutedWithSkipped`-Variante — die „skipped"-Form ist also ein regulärer, kein seltener Fall.

### Reproduktion (heutiger Stand, echte Hook-Funktionen, Skript `repro275.py` im Scratchpad)
| Fall | Heute |
|---|---|
| #201 `ESC[31mFAILESC[0m` + `EXIT=1` als RED-Artefakt | **abgewiesen** („keine Fehler-Evidenz") ✔ reproduziert |
| #256 xcbeautify nur mit `❌` + ANSI, ohne `error:`/`FAILED` | **abgewiesen** ✔ reproduziert |
| Gegenprobe grüner Lauf als RED | abgewiesen (richtig, muss so bleiben) |
| #202 `Executed 5…1 test skipped and 3 failures` | `Could not determine test result.` ✔ (falsche Meldung; richtig wäre FAILED 3) |
| #202 `…1 skipped and 0 failures` + `** TEST SUCCEEDED **` | grün nur über den Fallback, `Executed`-Zweig bleibt blind |
| #273 `Executed 5 tests, with 5 tests skipped…` + `TEST SUCCEEDED` | **grün** ✔ (soll: nicht grün) |
| #273 pytest `0 passed, 5 skipped` | **grün** ✔ (soll: nicht grün) |
| **Neu gefunden:** `post_bash` mit `✖`/ANSI + irgendeinem Pass-Muster | `passed` — das Fail-Guard kennt weder `✖` noch `❌` noch ANSI (False-Pass-Richtung) |
| `post_bash` Lauf nur mit Übersprungenem | `passed` |

### Affected Files (with changes)
| File | Change Type | Description |
|------|-------------|-------------|
| `core/hooks/hook_utils.py` | MODIFY | `strip_ansi()` — ANSI-Entfernung an genau einer Stelle |
| `core/hooks/tdd_enforcement.py` | MODIFY | `_FAILURE_RE` auf ANSI-bereinigtem Text; zusätzlich `❌ ✖ ✘`, `TEST FAILED`, `[1-9]\d* failures?`, `EXIT=[1-9]`, `Test run with … failed` |
| `core/hooks/qa_gate.py` | MODIFY | `Executed`-Regex mit optionalem `N tests skipped and`; skipped extrahieren; Regel „0 bestanden + skipped>0 = FAILED"; eigenes `ansi_re` durch `strip_ansi` ersetzen; pytest-skipped extrahieren |
| `core/hooks/post_bash.py` | MODIFY | Fail-Guard um ANSI/`✖`/`❌`; Lauf ohne Bestandenes + mit Übersprungenem nicht als `passed` |
| `core/commands/60-validate.md`, `82-test.md`, `core/agents/implementation-validator.md`, `test-runner.md` (+ `skills/*` per Sync) | MODIFY | Report-Feld „übersprungen" |
| `tests/…` + `tests/fixtures/` | CREATE | Regressionstests; Fixtures aus echten Läufen (xcbeautify lokal installiert → Rohlog durch echten `xcbeautify` erzeugen, nichts erfinden) |

### Scope Assessment
- Gesamt: 4 Hooks + 4 Vorlagen (+4 generierte Skills) + Tests ≈ 9 Dateien, ≈ +260 LoC → **über dem Limit (4–5 Dateien / ±250 LoC)**.
- Risk Level: MEDIUM — ein zu laxer Treffer öffnet ein Gate (False-Pass), ein zu strenger blockiert Arbeit. Gegenprobe (Lauf ohne Evidenz bleibt abgewiesen) ist Pflicht-Test.

### Technical Approach
Empfehlung: **zwei Scheiben, nacheinander, je eigener PR**.
- **A (#201/#202/#256①):** `hook_utils.strip_ansi`, `tdd_enforcement`, `qa_gate` (nur Lesbarkeit der `Executed…skipped`-Zeile + ANSI-Helfer) + Tests. 3 Hooks + Tests, ≈ 130 LoC.
- **B (#273-Regel „skipped ≠ Erfolg"):** `qa_gate` (Regel), `post_bash` (Regel + Fail-Guard), 4 Vorlagen + Sync + Tests. Baut auf A auf.
Details für die Spec:
- `Executed`: nur die **letzte** Zeile zählen (Gesamtsumme steht zuletzt; Summieren über Suite-Zeilen verdoppelt Zahlen, für Ja/Nein harmlos, in der Meldung irreführend).
- Fehler-Evidenz nur mit Zahl > 0 (`\b[1-9]\d*\s+failures?\b`); `0 failures` darf nie matchen.
- RED-Artefakt nur mit Übersprungenem: wird heute schon abgewiesen (keine Evidenz) — nur Regressionstest nötig.
- `post_bash`: Lauf ohne Bestandenes + mit Übersprungenem → neuer Hinweiswert `skipped` (nichts gated auf `last_test_run`; nur Hinweis laut #253, geprüft per grep).

### Alternativen (bewusst gegen die bisherige Richtung)
1. **Exit-Code statt Textmuster:** Gate wertet `EXIT=`/`.xcresult` aus. Löst „skipped" und ANSI strukturell, kippt die Entscheidung „Fehler-Evidenz per Text" (3.27.0); Preis: Artefakte ohne `EXIT=` (xcbeautify-Pipes verlieren ihn) wären unbewertbar. → als Ergänzung für später, nicht als Ersatz.
2. **„skipped" nur warnen statt Fehlschlag:** wäre weniger riskant für bestehende Projekte (z. B. Tests mit bewusstem `XCTSkip`), kippt aber die PO-Entscheidung vom 2026-09-28. Mildere Variante, die ich **nicht** empfehle: Regel nur bei **null** Bestandenen (so ist sie ohnehin zugeschnitten — gemischte Läufe bleiben grün, Zahl wird genannt).
3. **Ein Pass statt zwei Scheiben:** alles in einem PR, ≈ 9 Dateien — widerspricht dem Scoping-Limit.

### Dependencies
Nur Python-Stdlib. Downstream: `qa_gate` → Verdict → `bash_gate` beim Commit; `tdd_enforcement` → Edits in phase6; `post_bash` → `last_test_run` (nur Hinweis, Konsumenten: Adversary-Evidenz #253).

### Open Questions
- [x] **Entschieden (PO, 2026-10-01): alles in einem Vorgang**, trotz Überschreitung des Scoping-Limits (≈ 9 Dateien / ≈ 260 LoC). Die Spec muss das Limit ausdrücklich als bewusste Ausnahme benennen; Reihenfolge innerhalb des Vorgangs: Scheibe A (Erkennung) vor Scheibe B (skipped-Regel + Vorlagen), je eigener Commit.
- Nicht in Scope, zu notieren: Swift-Testing-Summary (`Test run with N tests passed`) kennt `qa_gate` nicht („Could not determine"); nur im RED-Check (tdd) wird die Fehlerzeile mit aufgenommen.
