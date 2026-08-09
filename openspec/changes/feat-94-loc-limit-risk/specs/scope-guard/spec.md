---
entity_id: scope_guard_loc_delta
type: module
created: 2026-08-09
updated: 2026-08-09
status: draft
version: "1.0"
tags: [scope-guard, edit-gate, hooks]
test_targets: [tests/test_gate_coverage.py]
---

# Scope Guard — LoC-Delta Risiko-Check

## Approval

- [x] Approved

## GitHub Issue

- **Issue:** #94 — Zeilen-Limit misst Aenderungs-Churn statt Risiko

## Purpose

`_check_loc_delta()` in `core/hooks/edit_gate.py` begrenzt, wie viel
unreviewter neuer/veraenderter Code in einem Workflow-Schritt entstehen darf
(Scope-Creep-Schutz). Diese Spec beschreibt die korrigierte Zaehlweise: nur
hinzugefuegte Zeilen zaehlen (nicht `added + deleted`), und Test- und
Produktivcode werden getrennt gegen eigene Schwellwerte geprueft, statt in
einer gemeinsamen Summe gegen ein einziges Limit.

## Source

- **File:** `core/hooks/edit_gate.py`
- **Identifier:** `def _check_loc_delta`
- **File:** `core/hooks/config_loader.py`
- **Identifier:** `def get_scope_loc_config`, `def get_scope_test_loc_config`

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `config_loader.get_scope_loc_config()` | function | Liefert `(max_loc_delta, loc_exclude_patterns)` fuer den Produktiv-Bucket |
| `config_loader.get_scope_test_loc_config()` | function | Liefert `(max_test_loc_delta, test_path_patterns)` fuer den Test-Bucket |
| `git diff HEAD --numstat` | subprocess | Datenquelle fuer added/deleted pro Datei |
| `hook_utils.gate_diagnostics()` | function | Baut den Diagnose-Suffix der Blockade-Meldung |
| `workflow.<name>.json` (`loc_limit_override`, `test_loc_limit_override`, `loc_delta_current`, `loc_delta_test_current`) | state | Persistente Override- und Status-Felder |

## Implementation Details

```python
def _check_loc_delta(config: dict, workflow: dict) -> str | None:
    max_loc, exclude_patterns = get_scope_loc_config()
    max_loc = int(workflow.get("loc_limit_override") or max_loc)
    max_test_loc, test_patterns = get_scope_test_loc_config()
    max_test_loc = int(workflow.get("test_loc_limit_override") or max_test_loc)

    prod_total = 0
    test_total = 0
    for added, deleted, file_name in parse_numstat():
        if matches_any(file_name, exclude_patterns):
            continue
        bucket = test_total if matches_any(file_name, test_patterns) else prod_total
        bucket += added  # NICHT + deleted

    if prod_total > max_loc or test_total > max_test_loc:
        return (
            f"BLOCKED: LoC delta exceeds limit — "
            f"Produktiv {prod_total}/{max_loc}, Tests {test_total}/{max_test_loc}. "
            "Split the change or: workflow.py set-field loc_limit_override <N> "
            "(Produktiv) / test_loc_limit_override <N> (Tests) "
            + gate_diagnostics(workflow, ...)
        )
    # persist loc_delta_current="+{prod_total}", loc_delta_test_current="+{test_total}"
```

## Expected Behavior

- **Input:** Uncommitted Git-Diff des Workdirs (`git diff HEAD --numstat`),
  Config (`scope_guard.*`), aktiver Workflow-State.
- **Output:** `None` wenn beide Buckets innerhalb ihrer Limits liegen (Edit
  wird erlaubt), sonst ein `BLOCKED:`-String mit getrennter
  Produktiv/Test-Aufschluesselung (Edit wird verweigert).
- **Side effects:** Schreibt bei erfolgreicher Pruefung `loc_delta_current`
  und `loc_delta_test_current` in die aktive Workflow-JSON.

## Error Handling

- Git-Fehler (Timeout, `git` nicht gefunden) → fail-soft: `None`
  zurueckgeben, Edit wird NICHT blockiert (unveraendertes Verhalten).
- Binaerdateien (`numstat` liefert `-` statt Zahlen) → als 0 gewertet,
  zaehlen weder in Produktiv- noch Test-Bucket (unveraendertes Verhalten).
- Kein aktiver Workflow beim Schreiben der Statusfelder → Schreibvorgang wird
  übersprungen, kein Crash (bestehendes try/except-Pattern beibehalten).

## Known Limitations

- Reine Loeschungen (Datei nur mit `deleted`-Zeilen) tragen mit `added=0`
  nichts zum Delta bei und koennen das Gate nicht mehr ausloesen. Bewusst in
  Kauf genommen: das Gate soll unreviewten NEUEN Code begrenzen, nicht
  Aufraeumarbeiten verhindern (siehe proposal.md, Abschnitt "Entscheidung").
- Ein Datei-Pfad, der sowohl auf ein `loc_exclude_pattern` als auch auf ein
  `test_path_pattern` passt, wird komplett ausgeschlossen (Exclude hat
  Vorrang) — unveraendert gegenueber dem bisherigen Verhalten.
- `test_path_patterns` ist konventionsbasiert (Pfad-/Dateiname-Regex, keine
  Analyse des Dateiinhalts). Ein Produktivfile mit `_test` im Namen, das
  keine Testdatei ist, wuerde faelschlich dem Test-Bucket zugeordnet — als
  Trade-off fuer Einfachheit akzeptiert, analog zur bestehenden
  `ALWAYS_ALLOWED_DIRS`-Logik im selben Hook.

## Acceptance Criteria

- **AC-1:** Given ein `git diff --numstat` mit einer reinen 1:1-Umbenennung
  (1 Zeile geloescht, 1 Zeile neu hinzugefuegt an derselben Stelle) / When
  `_check_loc_delta()` laeuft / Then traegt diese Zeile genau 1 zum
  jeweiligen Bucket-Total bei, nicht 2 (`added` zaehlt, `deleted` nicht).
  - Test: *(populated after TDD RED phase)*

- **AC-2:** Given eine geaenderte Datei, deren Pfad einem
  `test_path_patterns`-Eintrag entspricht (z.B. `tests/test_foo.py`,
  `src/bar.test.ts`) / When `_check_loc_delta()` laeuft / Then werden ihre
  hinzugefuegten Zeilen dem `test_total` zugerechnet und gegen
  `max_test_loc_delta` geprueft, nicht gegen `max_loc_delta`.
  - Test: *(populated after TDD RED phase)*

- **AC-3:** Given `prod_total` liegt bei 98 (Limit 250) und `test_total`
  liegt bei 286 (Limit 500, Default) / When `_check_loc_delta()` laeuft /
  Then wird der Edit NICHT blockiert, obwohl die alte Summenlogik
  (98+286=384 > 250) geblockt haette — dies ist der Regressionstest fuer die
  Beleg-Session aus Issue #94.
  - Test: *(populated after TDD RED phase)*

- **AC-4:** Given `prod_total` oder `test_total` ueberschreitet sein
  jeweiliges Limit / When die Blockade-Meldung gebaut wird / Then enthaelt
  sie beide Werte getrennt im Format `"Produktiv {prod}/{max_loc}, Tests
  {test}/{max_test_loc}"`, unabhaengig davon welcher der beiden Buckets das
  Limit ueberschritten hat.
  - Test: *(populated after TDD RED phase)*

- **AC-5:** Given ein Workflow mit Feld `test_loc_limit_override` gesetzt auf
  einen Wert groesser als der Test-Default / When `_check_loc_delta()`
  laeuft / Then wird ausschliesslich der Test-Bucket-Schwellwert angehoben;
  der Produktiv-Bucket bleibt beim Wert aus `loc_limit_override` bzw.
  `max_loc_delta` unveraendert.
  - Test: *(populated after TDD RED phase)*

- **AC-6:** Given eine Projekt-Config ohne `scope_guard.max_test_loc_delta`
  und ohne `scope_guard.test_path_patterns` (z.B. der bestehende
  gregor_zwanzig-Stand) / When `get_scope_test_loc_config()` aufgerufen wird
  / Then werden die eingebauten Defaults (500 bzw. die Standard-Testpfad-
  Patterns) verwendet, ohne dass eine Config-Aenderung noetig ist.
  - Test: *(populated after TDD RED phase)*

## Test Plan

Automated tests (linked to AC above):
- `pytest tests/test_gate_coverage.py -k loc_delta`
- `pytest tests/test_gate_coverage.py -k ScopeConfig`

## Changelog

- 2026-08-09: Initial spec created (Issue #94)
