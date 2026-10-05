---
entity_id: fix-352-349-gates
type: bugfix
created: 2026-10-05
updated: 2026-10-05
status: draft
version: "1.0"
tags: [bash-gate, rebase-pflicht, merge-head, tdd-enforcement, spec-reporter, fehlalarm]
test_targets: ["tests/test_bash_gate_merge_head_352.py", "tests/test_tdd_enforcement_spec_reporter_349.py"]
---

# Zwei fälschlich blockierende Gates: Merge-Commit (#352) und spec-Reporter (#349)

## Approval

- [ ] Approved

## GitHub Issue

- **Issue #352** — `bash_gate` 5b blockt den Merge-Commit, der den Rückstand zu `origin/main` beseitigt.
- **Issue #349** — `tdd_enforcement` blockt fälschlich: spec-Reporter-Zeile `ℹ todo 0` wird nicht als Summary erkannt.

Gemeinsames Ziel: Ein Gate blockt nur echte Verstöße. Beide Fälle sind Fehlalarme mit belegter Wirkung in einem Konsumenten-Projekt (gregor_zwanzig #2284).

## Purpose

**#352:** Der Commit-Gate-Abschnitt 5b zählt `HEAD..origin/main` und blockt jedes `git commit` bei Rückstand > 0. Während eines laufenden Merges (`MERGE_HEAD` gesetzt) ist `HEAD` noch der Vor-Merge-Stand; der abschließende Commit, der den Rückstand beseitigt, wird so selbst geblockt. Die Meldung rät zudem zu `rebase --autostash`, das bei gepushtem Branch einen Force-Push erzwingt. Während eines Merges wird der Rückstand künftig gegen `MERGE_HEAD` gemessen.

**#349:** `tdd_enforcement._TAP_SUMMARY_RE` entfernt Summary-Zeilen von `node --test` nur in der TAP-Form (`# todo 0`). Der spec-Reporter schreibt dieselben Zeilen als `ℹ todo 0`; die Platzhaltersuche trifft `todo` und blockt ein echtes RED-Artefakt. Die Regex erkennt künftig beide Formen.

Nicht betroffen (im Kontext widerlegt): `qa_gate.py` erkennt `(ℹ|#)` bereits (Z. 161).

## Source

- **File:** `core/hooks/bash_gate.py` — **Identifier:** `main()`, Abschnitt 5b (Rebase-Pflicht)
- **File:** `core/hooks/tdd_enforcement.py` — **Identifier:** `_TAP_SUMMARY_RE`

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `git rev-parse -q --verify MERGE_HEAD` | CLI | Feststellen, ob ein Merge läuft |
| `git rev-list --count <Basis>..origin/main` | CLI | Rückstand messen (Basis = `MERGE_HEAD` oder `HEAD`) |
| `tests/test_bash_gate_erkennung_299.py` (`_origin_mit_klon`, `_gate`, `_git`) | Testhelfer | Wegwerf-Repo mit `origin` und Gate-Aufruf wiederverwendet |
| `node --test --test-reporter=spec` | CLI | Erzeugt die echte Fixture-Ausgabe für #349 |

## Scope

- **Affected Files:**
  - Code: `core/hooks/bash_gate.py`, `core/hooks/tdd_enforcement.py`
  - Tests: `tests/test_bash_gate_merge_head_352.py` (neu), `tests/test_tdd_enforcement_spec_reporter_349.py` (neu)
  - Doku: `CHANGELOG.md` (nur `[Unreleased]`, kein Versions-Bump)
- **Estimated Changes:** Produktivcode ~+25/−5 LoC, Tests ~+110 LoC → insgesamt ~140 LoC, 5 Dateien (innerhalb der Scoping-Limits)

## Implementation Details

**1. `bash_gate.py` 5b.** Vor dem `rev-list`:

```
merge_head = git rev-parse -q --verify MERGE_HEAD   (cwd wie bisher, Timeout 5s)
basis = "MERGE_HEAD" wenn rc == 0 und Ausgabe nicht leer, sonst "HEAD"
behind = git rev-list --count <basis>..origin/main
```

- Läuft kein Merge (rc ≠ 0, „nicht vorhanden"): Verhalten Byte-identisch zu heute (Basis `HEAD`, bestehende Meldung mit `--autostash`).
- `rev-parse` schlägt anders fehl (Timeout, `OSError`): Basis `HEAD` — der alte Pfad, fail-open bleibt wie bisher.
- Basis `MERGE_HEAD` und `behind > 0` (Merge holt `origin/main` nicht vollständig herein): Block mit Merge-Meldung, **ohne** `--autostash`-Rat: „Merge bringt origin/main nicht vollständig herein — erst `git fetch origin && git merge origin/main`".
- Basis `MERGE_HEAD` und `behind == 0`: kein Block durch 5b.

**2. `tdd_enforcement.py`.** `_TAP_SUMMARY_RE` von `^#\s*(…)` auf `^[#ℹ]\s*(…)` erweitern (gleiche Schlüsselwörter, gleiches `\b.*$`). Die Fehler-Evidenz (`_FAILURE_RE`) läuft weiter auf dem Original; ein echtes TODO im Runner-Rahmen blockt weiterhin.

**3. Tests.** `test_bash_gate_merge_head_352.py` baut Wegwerf-Repos mit den Helfern aus `test_bash_gate_erkennung_299.py`. `test_tdd_enforcement_spec_reporter_349.py` erzeugt die Fixture zur Laufzeit aus einem echten `node --test --test-reporter=spec`-Lauf mit einem roten Test (übersprungen, falls `node` fehlt — dann `skip` mit Begründung, nicht stilles Bestehen).

## Expected Behavior

- **Input #352:** `git commit` bei laufendem Merge von `origin/main` mit gelösten Konflikten.
- **Output #352:** Commit wird nicht von 5b geblockt; unvollständiger Merge bleibt geblockt, Meldung ohne `--autostash`.
- **Input #349:** RED-Artefakt mit spec-Reporter-Ausgabe (`ℹ tests 3`, `ℹ todo 0`, `ℹ fail 1`).
- **Output #349:** Kein Platzhalter-Block durch die Summary-Zeilen; echte Platzhalter im Rahmen blocken weiter.
- **Side effects:** keine.

## Known Limitations

- `git merge --continue` wird vom Gate nicht erfasst (es prüft nur das Subcommand `commit`). Das Gate ist damit inkonsistent; das ist **bewusst nicht Teil** dieses Bündels. Folgearbeit wird als eigenes Issue angelegt (zuvor Duplikatsuche).
- Andere Reporter-Formen als TAP und spec (z. B. `dot`, `junit`) werden nicht untersucht.

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] Ein Merge von `origin/main` mit gelösten Konflikten lässt sich mit `git commit` abschließen, ohne dass das Gate blockt; der Fehlalarm aus gregor_zwanzig #2284 ist nachgestellt und weg
- [ ] Ein RED-Artefakt aus einem echten `node --test`-Lauf mit spec-Reporter wird nicht mehr als Platzhalter-Fälschung geblockt
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf grün, insbesondere AC-17/18/19 aus `test_bash_gate_erkennung_299.py`)

## Acceptance Criteria

- **AC-1:** Given ein Wegwerf-Repo mit Rückstand zu `origin/main` und einem durchgeführten `git merge --no-commit --no-ff origin/main` (`MERGE_HEAD` gesetzt, `MERGE_HEAD..origin/main` = 0) / When das Gate `git commit -m x` prüft / Then blockt 5b nicht (Exit 0)
  - Test: `tests/test_bash_gate_merge_head_352.py::test_abschliessender_merge_commit_wird_durchgelassen`
- **AC-2:** Given ein laufender Merge, der `origin/main` nicht vollständig hereinholt (`MERGE_HEAD..origin/main` > 0) / When das Gate `git commit` prüft / Then blockt es (Exit 2), die Meldung nennt `git merge origin/main` und enthält **nicht** `--autostash`
  - Test: `tests/test_bash_gate_merge_head_352.py::test_unvollstaendiger_merge_blockt_ohne_autostash_rat`
- **AC-3:** Given kein laufender Merge und Rückstand > 0 / When das Gate `git commit` prüft / Then blockt es wie bisher mit der `--autostash`-Meldung (Verhalten unverändert)
  - Test: `tests/test_bash_gate_merge_head_352.py::test_ohne_merge_bleibt_rueckstand_block_unveraendert`
- **AC-4:** Given `rev-parse` für `MERGE_HEAD` schlägt mit Timeout bzw. `OSError` fehl / When das Gate `git commit` prüft / Then fällt es auf den alten Pfad (Basis `HEAD`) zurück und stürzt nicht ab
  - Test: `tests/test_bash_gate_merge_head_352.py::test_rev_parse_fehler_faellt_auf_head_zurueck`
- **AC-5:** Given die Ausgabe eines echten `node --test --test-reporter=spec`-Laufs mit einem roten Test / When `tdd_enforcement._find_placeholder` sie prüft / Then liefert es `None` (die Zeile `ℹ todo 0` löst keinen Block aus)
  - Test: `tests/test_tdd_enforcement_spec_reporter_349.py::test_spec_reporter_summary_ist_kein_platzhalter`
- **AC-6:** Given eine Ausgabe im Runner-Rahmen mit einem echten Platzhalter (z. B. `TODO: fill in`) neben spec-Reporter-Summary-Zeilen / When `_find_placeholder` sie prüft / Then wird der echte Platzhalter weiterhin gefunden
  - Test: `tests/test_tdd_enforcement_spec_reporter_349.py::test_echter_platzhalter_blockt_weiterhin`
- **AC-7:** Given die TAP-Form (`# todo 0`) / When `_find_placeholder` sie prüft / Then liefert es weiterhin `None` (Bestandsverhalten aus #73 bleibt)
  - Test: `tests/test_tdd_enforcement_spec_reporter_349.py::test_tap_summary_bleibt_unbeanstandet`

> Die Test-Zuordnung steht bei der Spec-Erstellung; nach der Freigabe ist diese Datei eingefroren (#230).

## Test Plan

Automatische Tests (jeweils an eine AC oben gebunden):
- `pytest tests/test_bash_gate_merge_head_352.py tests/test_tdd_enforcement_spec_reporter_349.py`
- Regression: `pytest tests/test_bash_gate_erkennung_299.py tests/test_gate_fixes_26_38_34.py tests/test_tdd_enforcement_*.py`

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Beide Änderungen lockern ein bestehendes Gate in einem eng definierten Fall, ohne neues Muster oder neue Abhängigkeit. Reflexion der Alternativen: #352 (a) 5b bei `MERGE_HEAD` ganz überspringen — verworfen, ließe unvollständige Merges durch; #352 (b) Rückstandsprüfung streichen und der CI überlassen — verworfen, kippte die Rebase-Pflicht aus #284, und das CI-Spec-Gate fängt Rückstand nicht; #349 (a) Summary-Block generisch erkennen (Zeilen vor `duration_ms`) — verworfen, fragil gegenüber Reporter-Versionen; #349 (b) RED-Artefakte nur im TAP-Reporter zulassen — verworfen, schiebt Aufwand auf Nutzer ohne Gewinn. Keine frühere ADR wird gekippt.

## Changelog

- 2026-10-05: Initial spec created
