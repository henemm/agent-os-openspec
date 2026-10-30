---
entity_id: fix-487-auto-approve-env
type: feature
created: 2026-10-30
updated: 2026-10-30
status: draft
version: "1.0"
workflow: fix-487-auto-approve-env
tags: [autonomy, auto-approve, bugfix]
---

# auto-approve beachtet den benutzerweiten Autonomie-Schalter (Issue #487)

## Approval

- [ ] Approved

## Purpose

Die automatische Spec-Freigabe (`workflow.py auto-approve`, #470) prueft den Autonomie-Modus bisher selbst ueber die Projekt-Config und uebersieht dadurch den benutzerweiten Schalter `OPENSPEC_AUTONOMY` aus #481. Folge: Trotz `AUTONOMY=auto` und gruener Ampel verlangt die Sitzung `approved`. Die Pruefung nutzt kuenftig `autonomy_mode()`, die einzige Quelle fuer den Modus.

## Source

- **File:** `core/hooks/workflow.py`
- **Identifier:** `_auto_approve_decision`

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `core/hooks/workflow.py` (#469/#470/#481) | module | `autonomy_mode()`, `trusted_config()`, `_auto_approve_decision()` |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| core/hooks/workflow.py | MODIFY | Modusprüfung in `_auto_approve_decision` über `autonomy_mode()` |
| tests/test_auto_approve_env_487.py | CREATE | Ende-zu-Ende mit Env-Schalter, Architekturtest |
| CHANGELOG.md | MODIFY | Eintrag unter [Unreleased] |

### Estimated Changes

- Files: 1 neu, 2 geaendert
- LoC: +3/-3 Produktion / +80 Test
- Risk Level: LOW

## Implementation Details

In `_auto_approve_decision()` ersetzt `if autonomy_mode() != "auto": return "human", "Modus manual", []` die direkte Pruefung von `config.get("autonomy")`. Die vorangehende Pruefung `trusted_config()` ist ein dict bleibt (Gate-Einstellungen fuer ADR und Briefing kommen weiter nur daraus).

## Expected Behavior

- **Input:** Projekt ohne `autonomy`-Eintrag, `OPENSPEC_AUTONOMY=auto`, Workflow in `phase3_spec` mit registriertem gruenem Briefing
- **Output:** `AUTO_APPROVE=done`, Spec freigegeben
- **Side effects:** Eintrag in `approvals` wie bisher

## Known Limitations

- Keine.

## Definition of Done

Fertig ist diese Aenderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] In einem Projekt mit Benutzer-Schalter laeuft eine Spec mit gruener Ampel ohne `approved` durch (manuelle Abnahme durch den PO)
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf gruen)

## Acceptance Criteria

- **AC-1:** Given ein Projekt ohne `autonomy`-Abschnitt, `OPENSPEC_AUTONOMY=auto`, Workflow in `phase3_spec` mit Spec und per `set-briefing` registriertem Briefing mit `Ampel: gruen` / When `workflow.py auto-approve` laeuft / Then lautet die Ausgabe `AUTO_APPROVE=done` und der Workflow steht in `phase4_approved`
  - Test: tests/test_auto_approve_env_487.py::test_auto_approve_honours_env_switch

- **AC-2:** Given dasselbe Projekt mit Projekteintrag `autonomy: {mode: manual}` und `OPENSPEC_AUTONOMY=auto` / When `workflow.py auto-approve` laeuft / Then `AUTO_APPROVE=human` mit `REASON=Modus manual`
  - Test: tests/test_auto_approve_env_487.py::test_project_manual_still_wins

- **AC-3:** Given der Quelltext von `core/hooks/workflow.py` / When nach Lesezugriffen auf den `mode`-Schluessel des `autonomy`-Abschnitts gesucht wird / Then kommen sie nur innerhalb von `autonomy_mode()` vor
  - Test: tests/test_auto_approve_env_487.py::test_mode_read_only_in_autonomy_mode

## Test Plan

Subprozess gegen `core/hooks/workflow.py` in isoliertem Projekt (Muster `tests/test_spec_ampel_470.py`), Umgebungsvariable gesetzt; Architekturtest per AST/Textsuche.

- `pytest tests/test_auto_approve_env_487.py`
- Regressionslauf: `pytest tests/`

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Fehlerbehebung: eine Stelle nutzt die vorhandene zentrale Funktion statt eigener Logik. Keine neue Struktur.

## Changelog

- 2026-10-30: Initial spec created
