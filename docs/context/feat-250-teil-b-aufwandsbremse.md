# Context: feat-250-teil-b-aufwandsbremse

## Request Summary
#250 Teil B: Überschreitet ein Workflow sein Stufen-Budget, wird der PO gefragt statt still weitergearbeitet.
Die 15-Minuten-Bremse wird nach Stufe abgestuft, die Änderungsgröße beim Abschluss verlässlich erfasst.
Gegenprüfung (Adversary) wird nie abgeschnitten.

## Related Files
| File | Relevance |
|------|-----------|
| core/hooks/workflow.py:570 `record_transition` | einzige Stelle für Phasenwechsel — Einhängepunkt der Budget-Prüfung |
| core/hooks/workflow.py:1175 `cmd_phase` | gibt die Rückfrage aus; zählt `fix_loop_iterations` (Z. 1194) |
| core/hooks/workflow.py:1341 `cmd_write_log`, :1400 `cmd_complete` | Abschluss-LoC (`loc_delta_final`) |
| core/hooks/post_implementation_gate.py:53 `_BATCH_WINDOW_S` | feste 15 min, wird stufenabhängig |
| core/hooks/config_loader.py | neuer Getter `get_effort_budget` |
| config.yaml | neuer Block `effort_budget` |
| core/hooks/edit_gate.py `_check_loc_delta` | Ausschlüsse/Test-Muster für die Abschluss-LoC wiederverwenden |

## Existing Patterns
- Kill-Switch: nur ein ausdrückliches `false` schaltet ab (z. B. `po_briefing_gate.enabled`).
- Protokoll über `hook_utils.log_gate_event` (#181/#328).
- Typ `bug` ist seit #333 entfernt; State kennt `feature-fast` und `feature`.

## Dependencies
- Upstream: `phase_transitions`, `fix_loop_iterations` im State; `base_commit`; `git diff --numstat`.
- Downstream: alle Projekte mit dem Framework (jeder Phasenwechsel läuft durch `record_transition`).

## Existing Specs
- `docs/specs/feat-250-teil-b-aufwandsbremse.md` (Entwurf, Briefing `docs/briefings/feat-250-teil-b-aufwandsbremse.md`)
- Analyse: `docs/context/feat-250-prozess-abstufung.md`

## Risks & Considerations
- `record_transition` darf nie einen Wechsel verweigern oder abstürzen (Fail-open).
- Abschluss-LoC-Messung darf `complete` nie blockieren.
- Offene PO-Entscheidung: Deckelung der Adversary-Runden widerspricht der Entscheidung vom 26.09. und bleibt außerhalb.
- Änderung an `core/hooks`: Override nötig (installiertes Plugin 3.34.0 ohne #322).

## Analysis

### Type
Feature (Prozess-Mechanik im Framework, kein UI).

### Affected Files (with changes)
| File | Change Type | Description |
|------|-------------|-------------|
| core/hooks/workflow.py | MODIFY | `effort_budget_exceeded`, Aufruf aus `record_transition`, Ausgabe in `cmd_phase`, `_final_loc`, `write-log`/`complete` |
| core/hooks/post_implementation_gate.py | MODIFY | `_BATCH_WINDOW_S` (Z. 53, genutzt Z. 188/190) → `_batch_window_s(workflow)` |
| core/hooks/config_loader.py | MODIFY | `get_effort_budget(workflow_type)` |
| config.yaml | MODIFY | Block `effort_budget` |
| tests/test_effort_budget_250b.py | CREATE | AC-1 bis AC-9 |
| CHANGELOG.md | MODIFY | unter [Unreleased] |

### Scope Assessment
- Files: 6 (4 Logik, Hausregel 4–5 eingehalten)
- Estimated LoC: ca. +150 Logik / +200 Tests
- Risk Level: MEDIUM — `record_transition` läuft bei jedem Phasenwechsel in allen Konsumenten-Projekten; Fail-open ist Pflicht.

### Technical Approach
Regelweg, kein Modell: Zähler aus dem State (`fix_loop_iterations`, Wiedereintritte aus `phase_transitions`), Grenzen in `config.yaml`, Ausgabe als Anweisung. Ohne Modell geht es, weil alles deterministisch zählbar ist. Kein Phasenwechsel wird je verweigert; Adversary-Konstanten bleiben unverändert.

Im Code geprüfte Befunde für die Spec:
1. **Reihenfolge-Falle:** `cmd_phase` erhöht `fix_loop_iterations` erst NACH `record_transition` (workflow.py:1193–1194). Eine Prüfung innerhalb `record_transition` sähe den Fix-Loop des aktuellen Wechsels noch nicht → AC-2 (2 Fix-Loops, Grenze 1) würde einen Wechsel zu spät melden. Lösung: Fix-Loop-Zähler vor dem Aufruf erhöhen oder die Prüfung nach der Erhöhung in `cmd_phase` auslösen; die Spec-Formulierung „`record_transition` ruft sie auf" muss das berücksichtigen (Rückgabe bleibt, Aufrufer bekommt Liste).
2. `record_transition` gibt heute `None` zurück; weitere Aufrufer (Freigabe-Pfad in `phase_listener`) ignorieren den Rückgabewert — Rückgabe einer Liste ist abwärtskompatibel.
3. Typ-Fallback: `workflow_type` kennt nur `feature`/`feature-fast` (workflow.py:1063); Altbestand `bug` fällt auf `feature`-Werte.
4. `_check_loc_delta` (edit_gate.py:435) nutzt `git diff HEAD` — nur Uncommittetes; für `loc_delta_final` daher `git diff <base_commit> --numstat` mit denselben Ausschluss-/Test-Mustern aus `config_loader`.

### Alternativen
- Nur die 15-Minuten-Bremse abstufen, keine Zähler (kleinster Schnitt, lässt Fix-Loops/Wiedereintritte unsichtbar).
- Stundenbudget als Sperre / hartes `max_adversary_rounds`: verworfen (Entscheidung 26.09.); würde die Entscheidung „Gegenprüfung nie abschneiden" kippen.

### Dependencies
`hook_utils.log_gate_event`, `config_loader`, `git diff --numstat`; Downstream: jeder Phasenwechsel in allen Projekten.

### Open Questions
- [ ] Startwerte (Fix-Loops 1/2, Wiedereintritte 1/2, Fenster 30/15 min) — bleiben Startwerte, pro Projekt änderbar; PO bestätigt in der Freigabe.
- [ ] Override für `core/hooks` nötig (Plugin 3.34.0 ohne #322) — erst ab Phase 6 relevant.
