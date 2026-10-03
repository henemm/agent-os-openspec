# Context: fix-313-327-qa-gate-testausgabe

## Request Summary
`qa_gate.validate_test_output` erkennt grüne und rote Läufe von `python3 -m unittest` (#313) und
`node --test` (TAP- und Spec-Reporter, #327) nicht. Folge: `FAILED — Could not determine test
result`, Adversary-Verdict kann nicht gesetzt werden, Commit-/Deploy-Weg blockt fälschlich.
Gehört zur Testausgabe-Gruppe aus Epic #273 (#306/#307/#308 bereits geschlossen).

## Reproduktion (Ist-Zustand, echte Läufe, Node 26.5.1 / Python 3)
`validate_test_output(datei, infra=True)` gegen frisch erzeugte Ausgaben:

| Ausgabe | Ergebnis heute | Ursache |
|---|---|---|
| unittest grün (Standard, 1 Test) | `Test output too small (98 bytes)` | Größen-Gate (<100 Byte) |
| unittest grün `-v` | `matched 0/13 patterns` | TEST_PATTERNS kennt `Ran N tests`/`OK` nicht |
| unittest rot (`FAILED (failures=1, errors=1, skipped=1)`) | `Could not determine test result` | kein Zweig |
| node Spec grün / rot | `matched 1/13 patterns` | TEST_PATTERNS kennt `ℹ tests N` nicht |
| node TAP grün / rot | `Could not determine test result` | kein Zweig |

→ Es sind **zwei Stufen** betroffen: der Muster-Vorfilter (`TEST_PATTERNS`, Z. 34–41, verlangt ≥2
Treffer) UND der Auswertungszweig. Nur einen Zweig zu ergänzen genügt nicht. Die Issues nennen nur
den Zweig.

## Formate (belegt an echten Läufen)
- **unittest:** `Ran N test[s] in X.XXXs`, dann `OK` | `OK (skipped=S)` | `OK (expected failures=E)` |
  `FAILED (failures=F, errors=E[, skipped=S])`. Leerer Lauf: `NO TESTS RAN`.
- **node Spec** (bei Node 26 auch bei Umleitung in Datei Standard): Block `ℹ tests N / ℹ suites / ℹ pass /
  ℹ fail / ℹ cancelled / ℹ skipped / ℹ todo / ℹ duration_ms`.
  **Wichtig:** Bei Fehlschlag steht der Block NICHT am Dateiende — danach folgt `✖ failing tests:` mit
  Stacktraces. Die Idee aus #327 „nur Abschlussblock am Dateiende werten“ trägt deshalb nicht; richtig
  ist: letzten zusammenhängenden Block werten, ohne Dateiende-Bindung.
- **node TAP** (`--test-reporter=tap`, älteres Node: Default bei Umleitung): `# tests N / # suites / # pass /
  # fail / # cancelled / # skipped / # todo`.

## Related Files
| Datei | Relevanz |
|---|---|
| `core/hooks/qa_gate.py` | `TEST_PATTERNS` (Z. 34), `validate_test_output` (Z. 152–222), Zweige xcodebuild/pytest/go/cargo; Hilfsfunktion `_not_passed_skipped` (#273-Regel) |
| `tests/test_qa_gate.py` | bestehende Tests (tmp_path-Dateien mit Summary-Zeilen); hier kommen die neuen Tests hin |
| `core/hooks/hook_utils.py` | `strip_ansi` (wird bereits vor Auswertung angewandt) |
| `core/hooks/post_bash.py` | erkennt `unittest`/`node` NICHT, schreibt aber nur Hinweis `last_test_run`, kein Verdict → außerhalb des Scopes |
| `CHANGELOG.md` | Eintrag unter [Unreleased] |

## Existing Patterns
- Reihenfolge der Zweige: xcodebuild → pytest-Summary → go → cargo → Marker. Fehlerrichtung überall:
  **jede FAIL-Evidenz gewinnt**, zitierter Text mitten in Prosa zählt nicht (AC-4-Grenze pytest,
  Suffix-Pflicht bei go gegen TAP-Fehldeutung).
- #273-Regel: 0 bestanden + Übersprungenes ist kein Erfolg; 0 Tests gelaufen ist kein Erfolg.
- **Reihenfolge-Falle:** Der go-Zweig `^ok\s+\S+\s+(Dauer|cached)` ist bewusst so streng, dass TAP-Zeilen
  `ok 1 - x` nicht greifen. Neue Zweige müssen VOR dem generischen Marker-Fallback stehen
  (`"FAILED" in …` / `TEST SUCCEEDED`), sonst gewinnt der Fallback bei gemischten Ausgaben.

## Dependencies / Dependents
- Upstream: `strip_ansi`, `workflow.py set-field adversary_verdict`.
- Downstream: Adversary-Verdict (`/50-implement` → `/60-validate`), `bash_gate` verlangt gestempelten
  Dialog, `qa_gate` ist im Konsumenten-Projekt (loose-ends #145, gregor_zwanzig) der Weg zum Verdict.

## Risiken & Beobachtungen
- **False-Pass ist das Hauptrisiko** (Gate ist Verdict-Weg). Gemischte Ausgaben (unittest + xcodebuild
  wie in #313; node + anderer Runner): jede rote Evidenz gewinnt, auch wenn die letzte Summary grün ist.
- Kleine unittest-Läufe (<100 Byte) scheitern am Größen-Gate. Das Gate soll Fälschungen abfangen;
  eine Lockerung für echte Mini-Läufe muss das Fälschungsmotiv respektieren (Entscheidung in der Analyse).
- #327 nennt `fix-2375…` mit Verdict `Tests PASSED: 3714 tests, 0 failures` aus unbekannter Quelle
  (Verdacht: von Hand angehängte Summary-Zeile). Das ist Gate-Erosion in einem anderen Projekt und
  nicht Teil dieses Fixes; nur als Kommentar festhalten.
- Scoping: Ziel `qa_gate.py` + `tests/test_qa_gate.py` + CHANGELOG → 3 Dateien, im Limit.

## Existing Specs
Keine Spec zu qa_gate-Testausgabe-Zweigen; Vorgänger #275 (xcodebuild, Null-Zählungen) und #273-Regel.

## Analysis

### Type
Bug (zwei Issues, ein Ziel: #313 unittest, #327 node --test). Gebündelt, weil dieselbe Funktion und dieselbe Fehlerrichtung.

### Recherche (vor Analyse)
- unittest `TextTestRunner`: `Ran N test(s) in X.XXXs`, dann `OK[ (skipped=S, expected failures=E, unexpected successes=U)]` | `FAILED (failures=F, errors=E[, skipped=S])`; Quelle: Python-Stdlib `unittest/runner.py` (Spiegel: docs.djangoproject.com/en/2.1/_modules/unittest/runner).
- node:test: Reporter `spec` und `tap`; die genauen Summary-Zeilen stehen nicht in der Websuche — belegt stattdessen durch die echten Läufe oben (Node 26.5.1). Ausgabeformat ist reporterabhängig und versionsabhängig (Default bei Umleitung wechselte) → beide Reporter erkennen.
- Es gibt keinen Fallbericht, der das Gate-Problem anders löst; Gate ist projekteigen.

### Regeln vor Modell
Rein deterministische Regex-Auswertung strukturierter Runner-Summaries. Ein Modell wird nicht gebraucht, weil beide Formate feste Zeilen haben.

### Affected Files (with changes)
| File | Change Type | Description |
|------|-------------|-------------|
| core/hooks/qa_gate.py | MODIFY | Zwei Auswerter (`_evaluate_unittest`, `_evaluate_node_test`) + Einbindung in `validate_test_output` |
| tests/test_qa_gate.py | MODIFY | Tests: unittest grün/rot/skipped/leer, node Spec+TAP grün/rot/cancelled, gemischt, zitierter Text |
| CHANGELOG.md | MODIFY | Eintrag unter [Unreleased] |

### Technischer Ansatz (Empfehlung)
1. **Strukturelle Summary-Auswerter, zeilenverankert** (`^Ran N tests? in X.XXXs$` + Folgezeile; `^ℹ tests N`-Block bzw. `^# tests N`-Block). Zitierter Text mitten in Prosa zählt nicht (AC-4-Grenze wie pytest).
2. **Rote Evidenz zuerst:** Die neuen Auswerter laufen für das ROTE Ergebnis VOR dem `Executed`-Zweig. Sonst gewinnt bei gemischter Ausgabe (unittest rot + xcodebuild grün — genau der Fall aus #313) das Grün der xcodebuild-Zeilen: False-Pass. Grün aus den neuen Auswertern gilt erst nach pytest/go, vor cargo/Marker-Fallback.
3. **Vorfilter umgehen:** `TEST_PATTERNS` verlangt ≥2 Treffer; unittest `-v` und node Spec treffen 0–1. Ein erkannter Runner-Summary-Block gilt selbst als Beleg (Vorfilter wird für ihn übersprungen); der Vorfilter bleibt für alles andere.
4. **node-Block:** letzten zusammenhängenden Block werten, KEINE Bindung ans Dateiende (bei Rot folgen Stacktraces — Vorschlag in #327 trägt daher nicht). `fail>0` oder `cancelled>0` → rot; `tests==0` → nicht bestanden; `pass==0` bei `skipped/todo>0` → #273-Regel (`_not_passed_skipped`).
5. **unittest:** `FAILED (…)` → rot; `NO TESTS RAN`/`Ran 0 tests` → nicht bestanden; `OK (skipped=S)` mit `N−S==0` → #273-Regel; `expected failures` zählen als bestanden, `unexpected successes` → rot (unittest selbst wertet den Lauf dann als nicht erfolgreich).
6. **Größen-Gate unverändert (100 Byte):** Der Einzeltest-Lauf (98 Byte) scheitert weiter. Begründung: Das Gate ist der einzige Fälschungs-Filter („echo 'OK' > datei"); eine Ausnahme für `Ran 1 test … OK` würde genau die handschreibbare Zeile freigeben. Reale Adversary-Läufe sind größer (`-v`).

### Alternativen
- **A (empfohlen): Regex-Auswerter je Runner** (oben). Kleinster Eingriff, folgt dem bestehenden Muster.
- **B: Gate führt den Test selbst aus** (`qa_gate.py --run <Befehl>`, echter Exit-Code statt Textparsing). Beseitigt Parsing-Wettlauf UND Fälschung an der Wurzel — kippt aber das Prinzip „Datei rein, Urteil raus" (Adversary-Dialog, `/50-implement`, `/60-validate`, Konsumenten-Projekte) und ist deutlich größer als das Scoping-Limit. Als eigenes Issue anlegen, nicht jetzt.
- **C: Größen-Gate für erkannte Runner-Summaries lockern.** Verworfen (siehe 6).

### Scope Assessment
- Files: 3
- Estimated LoC: +~70 (Gate) / +~130 (Tests) / +4 (Changelog)
- Risk Level: MEDIUM — Gate ist der Verdict-Weg; False-Pass ist das Risiko, deshalb Rot-zuerst und Gemischt-Tests.

### Dependencies
`strip_ansi` (bereits angewandt), `_not_passed_skipped`, `workflow.py set-field adversary_verdict`. `post_bash.py` bleibt außerhalb (kein Verdict).

### Open Questions
- [x] Größen-Gate lockern? → Nein (Empfehlung, kein PO-Thema).
- [ ] Kommentar zu `fix-2375…` (angehängte Summary-Zeile, Gate-Erosion in gregor_zwanzig) gehört als Kommentar in #327, nicht in diesen Fix.
