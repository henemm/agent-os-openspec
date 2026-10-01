# Fixtures für #275 (Testausgaben-Erkennung)

Alle Dateien sind unveränderte Ausgaben echter Läufe vom 2026-10-01 (macOS, Xcode 27.0 / Build
27A266a, Apple Swift 6.4, xcbeautify 3.2.1, Python 3.14, pytest 9.1.1). Nichts ist von Hand
geschrieben oder nachbearbeitet. Die Testpakete lagen nur im Sitzungs-Scratchpad, nicht im Repo.

## xcodebuild (XCTest, kleines Swift-Paket `Demo`, Scheme `Demo-Package`)

Befehl je Variante, im Paketordner:

```
xcodebuild test -scheme Demo-Package -destination 'platform=macOS' -derivedDataPath <dd> > <datei> 2>&1
```

| Datei | Testinhalt | Exit | Summary |
|-------|-----------|------|---------|
| `xcodebuild_fail_raw.txt` | 1 bestanden, 1 `XCTAssertEqual` absichtlich falsch | 65 | `Executed 2 tests, with 1 failure (0 unexpected)`, `** TEST FAILED **` |
| `xcodebuild_mixed_raw.txt` | 4 bestanden, 1 `XCTSkip` | 0 | `Executed 5 tests, with 1 test skipped and 0 failures (0 unexpected)`, `** TEST SUCCEEDED **` |
| `xcodebuild_allskipped_raw.txt` | 3× `XCTSkip` | 0 | `Executed 3 tests, with 3 tests skipped and 0 failures (0 unexpected)`, `** TEST SUCCEEDED **` |
| `xcodebuild_skipfail_raw.txt` | 1 bestanden, 1 `XCTSkip`, 3 absichtlich falsch | 65 | `Executed 5 tests, with 1 test skipped and 3 failures (0 unexpected)`, `** TEST FAILED **` |
| `xcodebuild_compileerror_raw.txt` | Test benutzt nicht existierendes Symbol `LeaveOneOut` (Nachstellung von #256) | 65 | Compilerfehler `cannot find 'LeaveOneOut' in scope`, `** TEST FAILED **` |

Die `Executed …`-Zeile steht in jeder Datei dreimal (Suite `DemoTests`, `DemoTests.xctest`,
`All tests`); die Gesamtsumme ist die letzte.

## xcbeautify

Befehl (Standard-Renderer, Farben nicht abgeschaltet; xcbeautify färbt auch in eine Datei):

```
/opt/homebrew/bin/xcbeautify < xcodebuild_<variante>_raw.txt > xcbeautify_<variante>.txt
```

| Datei | Quelle | Fehlermarkierung |
|-------|--------|------------------|
| `xcbeautify_compileerror.txt` | `xcodebuild_compileerror_raw.txt` | **„❌"** vor dem Compilerfehler, Meldung ANSI-rot; kein `error`, kein `FAILED`, kein `failed` — genau das Bild aus #256 |
| `xcbeautify_fail.txt` | `xcodebuild_fail_raw.txt` | **„✖"** (ANSI-rot) vor dem fehlgeschlagenen Test; xcbeautify erzeugt für *Test*-Fehlschläge kein „❌", nur für Compilerfehler. Enthält zusätzlich `Test Suite '…' failed at …` |

## pytest mit Farben

Befehl, gegen eine Wegwerf-Testdatei im Scratchpad:

```
python -m pytest --color=yes -p no:cacheprovider test_wegwerf_fail.py > pytest_color_fail.txt 2>&1   # Exit 1
python -m pytest --color=yes -p no:cacheprovider test_wegwerf_pass.py > pytest_color_pass.txt 2>&1   # Exit 0
```

| Datei | Summary |
|-------|---------|
| `pytest_color_fail.txt` | `1 failed, 1 passed in 0.02s`, ANSI-gefärbt |
| `pytest_color_pass.txt` | `2 passed in 0.01s`, ANSI-gefärbt |
