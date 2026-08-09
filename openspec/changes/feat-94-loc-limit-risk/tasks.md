# Tasks — feat-94-loc-limit-risk

## 1. config_loader.py

- [ ] `get_scope_loc_config()` unveraendert lassen (Signatur/Defaults), aber
      sicherstellen, dass sie tatsaechlich von `edit_gate.py` aufgerufen wird
      (bisher toter Code).
- [ ] Neue Konstante `DEFAULT_TEST_PATH_PATTERNS` (Regex-Liste): deckt
      `tests/`, `__tests__/`, `Tests/`, `UITests/`, `test_*.py`, `*_test.py`,
      `*.test.{ts,tsx,js,jsx}`, `*.spec.{ts,tsx,js,jsx}` ab.
- [ ] Neue Funktion `get_scope_test_loc_config() -> tuple[int, list]`:
      liest `scope_guard.max_test_loc_delta` (Default 500) und
      `scope_guard.test_path_patterns` (Default `DEFAULT_TEST_PATH_PATTERNS`).

## 2. edit_gate.py — `_check_loc_delta()`

- [ ] Produktiv-Limit/Excludes ueber `config_loader.get_scope_loc_config()`
      statt inline-dupliziertem `config.get(...)`.
- [ ] Test-Limit/Patterns ueber `config_loader.get_scope_test_loc_config()`.
- [ ] Pro Datei aus `git diff HEAD --numstat`: Exclude-Pattern zuerst pruefen
      (wie bisher, Vorrang vor Test-Klassifikation). Danach: matched
      `test_path_patterns` → `test_total += added`, sonst →
      `prod_total += added` (NICHT `+ deleted`).
- [ ] `max_loc` weiterhin ueberschreibbar via `workflow.loc_limit_override`
      (unveraendert). Neu: `max_test_loc` ueberschreibbar via
      `workflow.test_loc_limit_override` (gleiches Muster).
- [ ] Block, wenn `prod_total > max_loc` ODER `test_total > max_test_loc`.
      Meldungsformat: `"BLOCKED: LoC delta exceeds limit — Produktiv
      {prod_total}/{max_loc}, Tests {test_total}/{max_test_loc}."` +
      Hinweis auf beide Override-Kommandos + `gate_diagnostics(...)`.
- [ ] Status-Persistenz: `loc_delta_current` bleibt `"+{prod_total}"`
      (Backward-Compat). Neu: `loc_delta_test_current = "+{test_total}"`
      im selben Schreibvorgang (gleiche Tempfile-Rename-Technik).

## 3. workflow.py

- [ ] `cmd_status()`: Zeile "LoC Delta: ..." um Test-Anteil ergaenzen, z.B.
      `LoC Delta: Produktiv +98/250, Tests +286/500 (override)` — Override-
      Hinweis nur zeigen, wenn der jeweilige Override gesetzt ist.
- [ ] Write-Log (~Zeile 811): zusaetzlich `scope_loc_delta_test:
      {loc_delta_test_current}` schreiben.
- [ ] Retro-Anzeige (~Zeile 1110): `loc_delta_test_current` analog zu
      `loc_delta_current` mit Log-Fallback lesen und anzeigen.

## 4. Dokumentation

- [ ] `core/commands/80-workflow.md`: Abschnitt "Override LoC Limit" um
      `test_loc_limit_override`-Beispiel ergaenzen.
- [ ] `CHANGELOG.md`: Eintrag unter `[Unreleased]` (Fix: LoC-Gate misst jetzt
      Risiko statt Aenderungs-Churn, Closes #94).

## 5. Tests

- [ ] `tests/test_gate_coverage.py::TestGetLocDelta` /
      `TestCheckLocDelta`: bestehende Faelle auf `added`-only-Semantik
      umstellen (z.B. `test_counts_added_and_deleted` → umbenennen/anpassen,
      da "10+5=15" mit neuer Logik zu "10" wird).
- [ ] Neue Tests: Datei in `tests/`-Pfad zaehlt in Test-Bucket, nicht in
      Produktiv-Bucket. Produktiv unter Limit + Test unter eigenem
      (hoeheren) Limit → kein Block, auch wenn Summe > 250 (Regressionstest
      fuer die 98+286-Beleg-Session aus Issue #94).
      Breakdown-Meldungsformat pruefen (`"Produktiv"` und `"Tests"` beide im
      Blocktext).
      `test_loc_limit_override` hebt nur den Test-Bucket-Limit an, nicht das
      Produktiv-Limit (Abgrenzungstest zu `loc_limit_override`).
- [ ] `config_loader.get_scope_test_loc_config()`: Default- und
      YAML-Override-Test (analog zu bestehendem `TestScopeConfig`).
- [ ] `tests/test_selfexplaining_gates.py`: bei Bedarf pruefen, ob die
      Blockade-Meldung weiterhin die per `gate_diagnostics()` erwarteten
      Marker enthaelt (kein Change an `gate_diagnostics()` selbst noetig).

## Reihenfolge / TDD

RED zuerst fuer die Faelle in Abschnitt 5, dann Implementierung in der
Reihenfolge 1 → 2 → 3 → 4, damit `edit_gate.py` von Anfang an gegen die
finalen Config-Funktionen entwickelt wird statt gegen einen Zwischenstand.
