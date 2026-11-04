---
entity_id: fix-513-issue-nummer
type: bugfix
created: 2026-11-04
updated: 2026-11-04
status: draft
version: "1.0"
workflow: fix-513-issue-nummer
tags: [workflow, footer, session-register, tdd-red]
---

# Richtige Issue-Nummer statt erster Ziffer im Namen; /40-tdd-red meldet RED (Issue #513, Teil 1+2)

## Approval

- [ ] Approved

## Purpose

Der Workflow leitet die Issue-Nummer aus der ersten Ziffernfolge im Workflow-Namen ab. Aus `i18n-a2-e2e-2681` wird `18`, aus `e2e-2681` wird `2`. Die falsche Nummer steht dann in der ❗Du-Fußzeile, in der Statuszeile, im Plan-Pane, im Auto-/clear-Folgebefehl und im Sitzungsregister. Künftig gilt eine eigene Issue-Nummer im State (`start --issue N`) und sonst eine Namensregel, die nur eindeutige Positionen wertet. Beide Hooks nutzen dieselbe Funktion. Außerdem setzt `/40-tdd-red` nach dem Registrieren der RED-Artefakte `mark-red`, damit Phase 5 nicht dauerhaft sich selbst als nächsten Schritt nennt.

Teil 3–5 aus #513 (`reconcile`, `phase-skip`, `step_override` im Footer-Gate) gehören nicht zu dieser Spec. Sie greifen in die Gate-Logik ein und bekommen ein eigenes Folge-Issue (siehe `docs/context/fix-513-issue-nummer.md`).

## Source

- **File:** `core/hooks/hook_utils.py`, `core/hooks/workflow.py`, `core/hooks/session_singleton_guard.py`, `core/hooks/herdr_bridge.py`, `core/commands/40-tdd-red.md`, `core/commands/00-intake.md`, `core/commands/10-context.md`
- **Identifier:** neu `hook_utils.issue_number_from_name`, neu `hook_utils.workflow_issue_number`, `workflow.issue_number`, `workflow.expected_footer_command`, `workflow.status_note`, `workflow.render_plan`, `workflow.cmd_start`, `workflow.cmd_find`, `session_singleton_guard._extract_issue_number`, `herdr_bridge` (Sidebar-Meldung)

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `core/hooks/hook_utils.py` | module | gemeinsamer Ort der einen Regel; beide Hooks importieren ihn schon |
| `core/hooks/footer_gate.py` (#234) | hook | prüft gegen `expected_footer_command()`; profitiert ohne eigene Änderung |
| `core/hooks/herdr_bridge.py` (#466/#467) | utility | Sidebar und Auto-/clear nutzen die Nummer |
| `skills/*/SKILL.md` | generiert | per `scripts/sync_skills.py` aus `core/commands/` |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| core/hooks/hook_utils.py | MODIFY | `issue_number_from_name(name)`, `workflow_issue_number(data)` |
| core/hooks/workflow.py | MODIFY | `issue_number()` delegiert; Aufrufer mit State nutzen `workflow_issue_number`; `start --issue N`; `find` prüft auch das State-Feld |
| core/hooks/session_singleton_guard.py | MODIFY | `_extract_issue_number` delegiert an `hook_utils`; Registerfeld `issue` nutzt das State-Feld |
| core/hooks/herdr_bridge.py | MODIFY | Sidebar nutzt `workflow_issue_number(data)` |
| core/commands/40-tdd-red.md | MODIFY | `workflow.py mark-red "<Ergebnis>"` nach dem Registrieren der Artefakte |
| core/commands/00-intake.md | MODIFY | `start … --issue <N>`, wenn die Nummer bekannt ist |
| core/commands/10-context.md | MODIFY | `start … --issue <N>`, wenn die Nummer bekannt ist |
| skills/40-tdd-red/SKILL.md, skills/00-intake/SKILL.md, skills/10-context/SKILL.md | MODIFY | regeneriert |
| tests/test_issue_number_513.py | CREATE | Regel, State-Feld, Footer, Status, find, start, Guard, Befehlstext |
| CHANGELOG.md | MODIFY | Eintrag unter [Unreleased] |

### Estimated Changes

- Files: 1 neu, 10 geändert
- LoC: +70 Produktion / +200 Test
- Risk Level: LOW (Anzeige- und Zuordnungslogik; keine Gate-Entscheidung hängt an der Nummer, außer der Erwartung des Footer-Gates, die dadurch richtig wird)

## Implementation Details

**Namensregel `hook_utils.issue_number_from_name(name) -> str | None`.** Der Name wird an `-` und `_` in Teile zerlegt (leere Teile entfallen). „Zahl“ heißt: der Teil besteht ganz aus ASCII-Ziffern (`[0-9]+`). In dieser Reihenfolge:

1. Erster Teil ist eine Zahl → diese (`513-foo` → `513`).
2. Erster Teil ist ein Präfix aus `fix`, `feat`, `feature`, `bug`, `issue`, `gh` (Groß-/Kleinschreibung egal) und der zweite Teil ist eine Zahl → diese (`fix-1761-xyz` → `1761`).
3. Letzter Teil ist eine Zahl und der vorletzte Teil ist keine Zahl (oder fehlt) → diese (`i18n-a2-e2e-2681` → `2681`, `p2p-77` → `77`).
4. Sonst `None` (`i18n-feature`, `fix-v2-login`, `release-4-0-0`).

Teile wie `a2`, `e2e`, `i18n`, `v2` sind nie eine Zahl. Leerer oder Nicht-String-Name → `None`. Die Funktion wirft nie.

**State-Feld.** `issue_number` im Workflow-JSON, als String aus Ziffern. `hook_utils.workflow_issue_number(data) -> str | None`: Ist `data["issue_number"]` ein String aus `[0-9]+` (ein führendes `#` wird entfernt) oder eine positive Ganzzahl, gilt dieser Wert. Sonst die Namensregel auf `data["name"]`. Kein dict → `None`. Wirft nie.

**`workflow.py start <name> [--type …] [--issue N]`.** `N` darf ein führendes `#` haben und muss danach aus `[0-9]+` bestehen, sonst Exit 1 mit Meldung, kein Workflow angelegt. Mit `--issue` wird `issue_number` gespeichert; ohne bleibt das Feld weg (Nummer aus dem Namen). Der Titel-Abruf (#490) nutzt dieselbe Nummer. Nachträglich korrigierbar mit dem vorhandenen `workflow.py set-field issue_number <N>`.

**Aufrufer.** `workflow.issue_number(name)` bleibt als Hülle für die Namensregel bestehen (Rückwärtskompatibilität). Wo der State vorliegt, gilt `workflow_issue_number(data)`: `expected_footer_command`, `status_note`, `render_plan`, `_with_issue_title`, `_plan_fetch_missing`, `cmd_start`, `herdr_bridge`. So zeigen Fußzeile, Statuszeile, Plan-Pane, Sidebar und Auto-/clear dieselbe Nummer.

**`workflow.py find <N>`.** Treffer ist ein Workflow, dessen Name wie bisher das Muster `(^|[-_])N([-_]|$)` enthält **oder** dessen `workflow_issue_number(data)` gleich `N` ist.

**Sitzungsregister.** `session_singleton_guard._extract_issue_number(name)` ruft `hook_utils.issue_number_from_name` (lazy import, fail-safe → `None`). Beim Feld `issue` des Registereintrags liest der Guard den State (wie schon für `phase`) und nimmt `workflow_issue_number(state)`; ist der State nicht lesbar, die Namensregel. Das Claim-Verhalten (`_claim_holds`) nutzt dieselbe Nummer.

**`/40-tdd-red`.** Neuer Schritt nach „Register Artifacts“: `python3 .claude/hooks/workflow.py mark-red "<kurzes Ergebnis, z. B. 3 tests failed>"`. Die RED-Checkliste und der Checkpoint nennen ihn. Damit meldet `next_step()` in `phase5_tdd_red` `/50-implement`, sobald RED belegt ist, auch wenn der Turn vor dem Phasenwechsel endet.

**`/00-intake`, `/10-context`.** Die `start`-Beispiele bekommen `--issue <N>` mit dem Hinweis „wenn die Issue-Nummer bekannt ist“.

## Expected Behavior

- **Input:** Workflow-Name, optional `--issue N` beim Start oder `issue_number` im State
- **Output:** Fußzeile, Statuszeile, Plan, Sidebar, Auto-/clear und Sitzungsregister nennen die echte Issue-Nummer oder keine
- **Side effects:** `start --issue N` schreibt `issue_number`; `/40-tdd-red` setzt `red_test_done`

## Known Limitations

- Laufende Workflows ohne State-Feld und mit mehrdeutigem Namen (z. B. `fix-v2-login-77-neu`) bekommen keine Nummer, bis jemand `set-field issue_number <N>` setzt. Vorher bekamen sie oft eine falsche.
- Namen mit der Nummer in der Mitte ohne Präfix (`login-513-neu`) ergeben keine Nummer. Das ist Absicht: dort ist nicht entscheidbar, welche Zahl gemeint ist.
- `mark-red` steht als Anweisung im Befehlstext; ein Modell, das den Schritt auslässt, verhält sich wie bisher (der Phasenwechsel am Ende schaltet trotzdem weiter).

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] Ein Workflow `i18n-a2-e2e-2681` zeigt in Fußzeile und Statuszeile `#2681` (Test)
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf `pytest tests/` grün)

## Acceptance Criteria

- **AC-1:** Given die Namen `i18n-a2-e2e-2681`, `e2e-2681`, `p2p-77`, `fix-1761-xyz`, `feat-106-login`, `513-foo`, `bug_42_crash` / When `hook_utils.issue_number_from_name` läuft / Then ergibt sich `2681`, `2681`, `77`, `1761`, `106`, `513`, `42`
  - Test: tests/test_issue_number_513.py::test_name_rule_finds_real_number

- **AC-2:** Given die Namen `i18n-feature`, `fix-v2-login`, `release-4-0-0`, `""`, `None` / When `hook_utils.issue_number_from_name` läuft / Then ergibt sich jeweils `None`, ohne Ausnahme
  - Test: tests/test_issue_number_513.py::test_name_rule_returns_none_when_ambiguous

- **AC-3:** Given ein State `{"name": "i18n-a2-e2e-18", "issue_number": "2681"}` bzw. `{"name": "x", "issue_number": 2681}` bzw. `{"name": "fix-12-a", "issue_number": "abc"}` / When `hook_utils.workflow_issue_number` läuft / Then `2681`, `2681` bzw. `12` (ungültiges Feld fällt auf den Namen zurück)
  - Test: tests/test_issue_number_513.py::test_state_field_wins_over_name

- **AC-4:** Given ein State `{"name": "i18n-a2-e2e-2681", "current_phase": "phase4_approved"}` / When `workflow.expected_footer_command` und `workflow.status_note` laufen / Then lautet der Footer-Befehl `/40-tdd-red #2681` und die Statuszeile enthält `#2681`, nicht `#18`
  - Test: tests/test_issue_number_513.py::test_footer_and_status_use_real_number

- **AC-5:** Given ein Projekt / When `workflow.py start login-neu --issue 77` läuft / Then Exit 0 und der State enthält `"issue_number": "77"`; Given `--issue abc` / Then Exit 1 und keine Workflow-Datei
  - Test: tests/test_issue_number_513.py::test_start_with_issue_flag

- **AC-6:** Given ein laufender Workflow `login-neu` mit `issue_number` `77` / When `workflow.py find 77` läuft / Then enthält die Ausgabe `GEFUNDEN: login-neu` und `NAME=login-neu`
  - Test: tests/test_issue_number_513.py::test_find_uses_state_field

- **AC-7:** Given `session_singleton_guard._extract_issue_number` / When mit `i18n-a2-e2e-2681` bzw. `fix-v2-login` aufgerufen / Then `2681` bzw. `None` — dieselben Werte wie `hook_utils.issue_number_from_name`
  - Test: tests/test_issue_number_513.py::test_guard_uses_shared_rule

- **AC-8:** Given ein aktiver Workflow `login-neu` mit `issue_number` `77` / When der Guard die Kontextfelder des Registereintrags bildet (`_context_fields`) / Then ist `issue` gleich `77`
  - Test: tests/test_issue_number_513.py::test_guard_register_uses_state_field

- **AC-9:** Given `core/commands/40-tdd-red.md` / When gelesen / Then steht `workflow.py mark-red` nach dem Abschnitt „Register Artifacts“ und vor dem Phasenwechsel `phase phase6_implement`; `skills/40-tdd-red/SKILL.md` ist synchron (`scripts/sync_skills.py --check` Exit 0)
  - Test: tests/test_issue_number_513.py::test_tdd_red_command_marks_red

- **AC-10:** Given ein State in `phase5_tdd_red` mit `red_test_done: true` und Name `i18n-a2-e2e-2681` / When `workflow.expected_footer_command` läuft / Then `/50-implement #2681`
  - Test: tests/test_issue_number_513.py::test_phase5_after_mark_red_points_to_implement

## Test Plan

- `pytest tests/test_issue_number_513.py`
- Regressionslauf: `pytest tests/`
- `python3 -m py_compile core/hooks/hook_utils.py core/hooks/workflow.py core/hooks/session_singleton_guard.py core/hooks/herdr_bridge.py`
- `python3 scripts/sync_skills.py --check`

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Korrektur einer Ableitungsregel plus ein optionales, rein informatives State-Feld. Keine neue Gate-Wirkung, reversibel durch Entfernen des Feldes. Die Regel liegt in `hook_utils.py`, weil beide Hooks es schon importieren (eine Quelle statt zwei Kopien).

## Changelog

- 2026-11-04: Initial spec created
