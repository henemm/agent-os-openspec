# Kontext: fix-508-tap-yaml-zitat (Issue #508)

## Anfrage (PO, 2026-11-04)

Der PO hat #508 an den Tech Lead (Claude) übergeben, Arbeitsweise „autonom wie #509“. Technische Entscheidungen, auch Umfang und Ort der Lösung, sind delegiert.

## Issue #508 in Kurzform

`tdd_enforcement._find_placeholder` lehnte ein echtes RED-Artefakt von `node --test` (TAP) als „Platzhalter-Text“ ab (gregor_zwanzig #2194, Plugin 4.4.9). Folge: In Phase 6 war jeder Write/Edit gesperrt. Auslöser: die Tailwind-Klasse `placeholder:text-muted-foreground` im zitierten HTML einer fehlgeschlagenen Assertion, im TAP-YAML-Block `error: |-` (dort auch in der `+ actual / - expected`-Diff) und in `actual: |-`.

## Befund im Code (Stand 4.5.1, Commit 00a6284)

- `core/hooks/tdd_enforcement.py:71–75` `_PLACEHOLDER_RE`: `\b(TODO|PLACEHOLDER|FIXME)\b` mit IGNORECASE. Trifft `placeholder:` (Doppelpunkt ist Wortgrenze).
- `core/hooks/tdd_enforcement.py:123–148` `_iter_frame_lines`: überspringt als Zitat nur pytest-`E`/`>`-Zeilen (#262), `Captured …`-Blöcke (#262), TAP-Summary `# todo 0` (#73/#349) und Compiler-Echo `NN |` (#421). TAP-YAML-Diagnoseblöcke laufen als Rahmen durch.
- `core/hooks/tdd_enforcement.py:151–158` `_find_placeholder`: einziger Nutzer von `_iter_frame_lines`; Aufruf in `_validate_artifact` Z. 219.
- `_FAILURE_RE` (Fehler-Evidenz) läuft auf dem Original-Inhalt und ist nicht betroffen.

## Nachgestellt (node v22.23.4, 2026-11-04)

`node --test` schreibt ohne TTY standardmäßig TAP 13. Jede fehlgeschlagene Zeile `not ok N - name` trägt einen YAML-Diagnoseblock, zwei Leerzeichen tiefer eingerückt als die Testzeile, von `---` bis `...` auf derselben Einrückung. Verschachtelte Subtests rücken Testzeile und Block jeweils um vier Leerzeichen weiter ein. Der Block enthält `error: |-` (Assertion-Text mit Diff), `expected:`, `actual: |-` (Wert aus dem Prüfgegenstand) und `stack: |-`. Inhaltszeilen der Block-Skalare sind immer tiefer eingerückt als die Marker, eine `...`-Zeile auf Marker-Höhe kann also nur das Blockende sein.

Mit `assert.equal('<input class="placeholder:text-muted-foreground border">…', …)` meldet `_find_placeholder` heute die Zeile im `error`-Block als Platzhalter.

## Abgrenzung

- `--test-reporter=spec` gibt die Assertion-Diff ohne YAML-Klammer aus (`✖ failing tests:` + eingerückter Block). Die Zeilen mit `placeholder:` stehen dort ebenfalls im Rahmen. Nicht Teil von #508 (gemeldet ist TAP); Folge-Issue.
- `_PLACEHOLDER_RE` bleibt unverändert: Eine Verengung (z. B. `placeholder:` ausnehmen) würde auch echte Platzhalter im Rahmen durchlassen. Mit der Zitat-Ausnahme entfällt der gemeldete Fall.

## Vorbilder

- #262 (`tests/test_tdd_enforcement_embedded_content_262.py`): pytest-Zitat; Stil der Tests (direkter Aufruf von `_validate_artifact`, echte Dateien in `tmp_path`).
- #421 (`tests/test_tdd_enforcement_compiler_echo_421.py`): Compiler-Echo als Zitat.
