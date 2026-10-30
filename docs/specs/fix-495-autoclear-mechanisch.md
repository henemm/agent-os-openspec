---
entity_id: fix-495-autoclear-mechanisch
type: bugfix
created: 2026-10-30
updated: 2026-10-30
status: draft
version: "1.0"
workflow: fix-495-autoclear-mechanisch
tags: [herdr, auto-clear, workflow, stop-hook, footer-gate]
---

# Auto-/clear mechanisch an der Phasengrenze ausloesen statt ueber Prosa-Marker (Issue #495)

## Approval

- [ ] Approved

## Purpose

Der Auto-/clear (#467/#489) loest im Konsumentenprojekt nie aus: `maybe_auto_clear` verlangt den Satz „`/clear` ist jetzt gefahrlos“ in der Antwort, das Modell laesst den Checkpoint-Block aber weg oder formuliert um (Log: `skip: Marker fehlt oder Negativmarker`). Kuenftig entscheidet ein auf Platte vermerkter Zustand statt Prosa: `workflow.py autoclear` — das die Befehle ohnehin an der Phasengrenze aufrufen — vermerkt im Workflow-State die Grenze (Phase + erwarteter Befehl), und der Stop-Hook loest aus, wenn dieser Vermerk zum aktuellen Stand passt. Der Negativ-Satz bleibt als reines Veto.

## Source

- **File:** `core/hooks/herdr_bridge.py` (Ausloeser), `core/hooks/workflow.py` (Vermerk)
- **Identifier:** `maybe_auto_clear`, `has_clear_marker`, `POSITIVE_MARKER`, `NEGATIVE_MARKER`; `cmd_autoclear`, `expected_footer_command`

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `core/hooks/herdr_bridge.py` (#467/#478/#480) | module | `maybe_auto_clear`, `_ac_skip`, `_acquire_lock`, `spawn_auto_clear`, `auto_clear_enabled`, `_pane` |
| `core/hooks/workflow.py` (#489) | module | `cmd_autoclear`, `expected_footer_command`, `_read_active`, `_save_active` |
| `core/hooks/footer_gate.py` | module | Aufrufer `_maybe_auto_clear` auf dem Pfad „Fusszeile korrekt“; unveraendert |
| `core/commands/10-context.md` … `50-implement.md` | commands | rufen `workflow.py autoclear` an der Grenze; unveraendert |
| `tests/test_herdr_auto_clear_467.py` | test infra | Hook-/Runner-Helfer (`_project`, `_hook_case`, `_run_hook`, Stub-Herdr) als Vorbild |
| `tests/test_kette_auto_clear_489.py`, `tests/test_auto_clear_global_480.py` | tests | Regression |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| core/hooks/workflow.py | MODIFY | `cmd_autoclear`: bei `on` und aktivem Workflow Vermerk `auto_clear_boundary` im State speichern (fail-open) |
| core/hooks/herdr_bridge.py | MODIFY | `maybe_auto_clear`: Positiv-Marker-Bedingung ersetzt durch Grenz-Vermerk-Pruefung; Negativ-Marker als Veto; `has_clear_marker` bleibt |
| tests/test_autoclear_boundary_495.py | CREATE | Tests zu AC-1 bis AC-8 |
| tests/test_herdr_auto_clear_467.py | MODIFY | Nur wo der Positiv-Marker Pflicht ist: Spawn-Faelle erhalten `auto_clear_boundary` im State, `test_no_spawn_without_positive_marker` und `test_no_spawn_when_marker_only_in_code_fence` werden auf „ohne Vermerk“ umgestellt; sonst keine Verhaltensaenderung |
| CHANGELOG.md | MODIFY | Eintrag unter [Unreleased] / Fixed (#495) |

### Estimated Changes

- Files: 1 neu, 4 geaendert
- LoC: +35 Produktion / +220 Test
- Risk Level: LOW bis MEDIUM (nur mit Opt-in und in Herdr wirksam; jeder Fehler fuehrt zu „kein Spawn“)

## Implementation Details

**Vermerk (`workflow.py autoclear`).** Ausgabe bleibt `AUTO_CLEAR=on|off`, Exit 0. Zusaetzlich, nur bei `on` und aktivem Workflow (`_read_active`-Ergebnis, ohne `sys.exit`): `data["auto_clear_boundary"] = {"phase": data["current_phase"], "command": expected_footer_command(data), "at": <iso>}`, dann `_save_active(data)`. Ist `expected_footer_command` kein String (kein Befehl bestimmbar), wird nichts gespeichert. Jede Ausnahme (kein Workflow, Lesefehler, Schreibfehler) wird geschluckt; Ausgabe und Exit-Code bleiben unberuehrt. Bei `off` wird nichts gespeichert und ein vorhandener Vermerk nicht angefasst.

**Ausloeser (`herdr_bridge.maybe_auto_clear`).** Reihenfolge der Bedingungen bleibt (Pane, Opt-in, `stop_hook_active`, Slash-Befehl, kein `/clear`, Fusszeile nennt Befehl). Der Block `has_clear_marker(message)` wird ersetzt durch:

1. Enthaelt die Nachricht den Negativ-Satz (`NEGATIVE_MARKER`, `**` ignoriert, auch in Fences): `_ac_skip("Negativmarker")`.
2. `data["auto_clear_boundary"]` ist kein dict, oder `phase` != `data["current_phase"]`, oder `command` != erwarteter Befehl: `_ac_skip("keine Grenze vermerkt")`.

Danach unveraendert: Once-Lock (`name|phase|command`), Spawn. `has_clear_marker` bleibt als Funktion bestehen (Rueckwaertskompatibilitaet, vorhandener Test), wird aber nicht mehr als Ausloese-Bedingung genutzt. Befehlstexte in `core/commands` bleiben unveraendert.

**Warum das sicher ist.** Der Vermerk entsteht erst beim `autoclear`-Aufruf am Ende der Phase (nach Phasenwechsel/Commit laut Befehlstext). Rueckt der Workflow danach weiter, passt `phase` nicht mehr; ein alter State ohne Feld loest nie aus (wie heute). Der Once-Lock verhindert Doppel-Spawns bei identischem Vermerk.

## Expected Behavior

- **Input:** Befehl 10–50 ruft am Phasenende `workflow.py autoclear` (Herdr, Opt-in an), die Antwort endet mit korrekter ❗Du-Zeile, auch ohne Positiv-Satz
- **Output:** Stop-Hook spawnt den Auto-/clear-Runner; im Log kein `skip`
- **Side effects:** Feld `auto_clear_boundary` im Workflow-State; Log-Grund `skip: keine Grenze vermerkt`, wenn kein passender Vermerk existiert

## Known Limitations

- Ruft ein Befehl `autoclear` nicht auf, entsteht kein Vermerk und es gibt keinen Auto-/clear (wie bisher ohne Marker).
- Der Vermerk garantiert nicht, dass der Befehl den Stand wirklich gesichert hat; das bleibt Aufgabe der Befehlstexte. Das Negativ-Veto schuetzt nur, wenn das Modell es ausgibt.
- Das Feld `auto_clear_boundary` bleibt nach dem Auslesen im State stehen; es wirkt nur bei passender Phase und passendem Befehl, der Once-Lock deckt Wiederholung ab (10 min).
- Echtes TUI-Verhalten (Herdr tippt `/clear`) ist nur im realen Herdr pruefbar; Tests nutzen ein Stub-Binary.

## Definition of Done

Fertig ist diese Aenderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] In einem echten Herdr mit Opt-in: ein Phasenende ohne Positiv-Satz loest Auto-/clear aus (manuelle Abnahme durch den PO)
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf gruen, insbesondere #467-/#480-/#489-Tests)

## Acceptance Criteria

- **AC-1:** Given Herdr-Pane, Auto-/clear aktiviert und ein aktiver Workflow / When `workflow.py autoclear` laeuft / Then ist die Ausgabe `AUTO_CLEAR=on` mit Exit 0, und der State enthaelt `auto_clear_boundary` mit `phase` = aktuelle Phase, `command` = erwarteter Befehl und `at`
  - Test: tests/test_autoclear_boundary_495.py::test_autoclear_on_records_boundary

- **AC-2:** Given Auto-/clear aus (oder kein aktiver Workflow) / When `workflow.py autoclear` laeuft / Then ist die Ausgabe `AUTO_CLEAR=off` bzw. unveraendert, Exit 0, und der State enthaelt keinen Vermerk
  - Test: tests/test_autoclear_boundary_495.py::test_autoclear_off_or_no_workflow_records_nothing

- **AC-3:** Given passender Vermerk, korrekte Fusszeile und eine Antwort OHNE Positiv-Satz / When der Stop-Hook laeuft / Then wird der Runner gespawnt
  - Test: tests/test_autoclear_boundary_495.py::test_spawn_with_boundary_without_positive_marker

- **AC-4:** Given kein Vermerk im State / When der Stop-Hook laeuft / Then wird nicht gespawnt, und das Log enthaelt `skip: keine Grenze vermerkt`
  - Test: tests/test_autoclear_boundary_495.py::test_no_spawn_without_boundary_logs_reason

- **AC-5:** Given ein Vermerk mit aelterer Phase (Phase weitergerueckt) oder mit anderem Befehl / When der Stop-Hook laeuft / Then wird nicht gespawnt
  - Test: tests/test_autoclear_boundary_495.py::test_no_spawn_with_stale_phase_or_other_command

- **AC-6:** Given passender Vermerk und ein Negativ-Satz in der Antwort / When der Stop-Hook laeuft / Then wird nicht gespawnt
  - Test: tests/test_autoclear_boundary_495.py::test_negative_marker_vetoes_boundary

- **AC-7:** Given passender Vermerk / When der Stop-Hook zweimal mit gleichem Vermerk laeuft / Then gibt es genau einen Spawn (Once-Lock)
  - Test: tests/test_autoclear_boundary_495.py::test_once_lock_single_spawn

- **AC-8:** Given die bestehenden Tests / When `pytest tests/test_herdr_auto_clear_467.py tests/test_auto_clear_global_480.py tests/test_kette_auto_clear_489.py tests/test_clear_checkpoint_blocks.py` laeuft / Then sind sie gruen (Positiv-Marker-Pflicht in #467-Tests durch Vermerk ersetzt, sonst ohne Verhaltensaenderung)
  - Test: tests/test_herdr_auto_clear_467.py, tests/test_auto_clear_global_480.py, tests/test_kette_auto_clear_489.py (Regressionslauf)

## Test Plan

Muster `tests/test_herdr_auto_clear_467.py`: isoliertes Projekt, Stub-Herdr (`HERDR_BIN_PATH`), `footer_gate.py` per Subprozess mit Stop-Payload, `workflow.py autoclear` per Subprozess mit `OPENSPEC_ACTIVE_WORKFLOW`. Der Vermerk wird in den Hook-Tests teils ueber `autoclear`, teils direkt im State-JSON gesetzt.

- `pytest tests/test_autoclear_boundary_495.py`
- Regressionslauf: `pytest tests/` (insbesondere #467, #480, #489)
- Syntaxpruefung: `python3 -m py_compile core/hooks/workflow.py core/hooks/herdr_bridge.py`
- Manuell (nicht automatisierbar): Phasenende im echten Herdr mit Opt-in

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Fehlerkorrektur im Herdr-Utility: ersetzt einen unzuverlaessigen Prosa-Ausloeser durch ein additives State-Feld, das der bestehende `autoclear`-Aufruf setzt. Kein Gate, keine Hook-Registrierung, kein Breaking Change am State-Format (fehlendes Feld = kein Ausloesen); reversibel.

## Changelog

- 2026-10-30: Initial spec created
