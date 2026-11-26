# Context: fix-688-fast-track-anzeige (Issue #688)

## Request Summary
Fast Track (`feature-fast`) zeigt nach der Freigabe (`phase4_approved`) als nächsten
Schritt `/40-tdd-red`, obwohl der Fast Track TDD-RED überspringt und direkt `/50-implement`
folgt. Zusätzlich zeigt das Plan-Pane nach einer Auto-Freigabe `❗ Du:`, obwohl Claude
selbst weiterarbeitet.

## Related Files
- `core/hooks/workflow.py`
  - `NEXT_STEP` (Z. ~164): `phase4_approved -> /40-tdd-red`, typunabhängig
  - `next_step(data)` (Z. ~288): einzige Quelle für Hook-Hinweis (`status_note`),
    Fußzeilen-Gate (`expected_footer_command`), Seitenleiste (`herdr_bridge.build_report`
    Token `next`) und Plan-Schluss (`end_state` → `_end_state_open`)
  - `_end_state_open(data, self_driven)` (Z. ~507): ⏳ nur bei `self_driven`
    (Auto-Modus + autarker Auftrag), sonst `❗ Du` für Slash-Schritte
  - `_auto_approve_decision` / `record_approval(data, "spec", "auto", …)`: Auto-Freigabe
    hinterlässt in `data["approvals"]` einen Eintrag `{"gate": "spec", "by": "auto"}`
- `core/hooks/herdr_bridge.py`: liest `expected_footer_command` und `end_state` — keine eigene Logik
- `core/hooks/footer_gate.py`: prüft, dass der erwartete Befehl in der Fußzeile steht;
  die ⏳-Zeile „Claude führt /50-implement #N selbst aus“ enthält ihn

## Existing Patterns
- `next_step` hat bereits zustandsabhängige Ausnahmen (phase3_spec mit Spec, phase5 mit RED-Done).
- `_end_state_open` wandelt Slash-Schritte bei `self_driven` in ⏳ (#555).
- `PLAN_STEPS_FAST` blendet Phase 5 im Plan für den Fast Track bereits aus.

## Dependencies / Dependents
Tests: `tests/test_endzustand_550.py`, `tests/test_nacharbeit_555.py`,
`tests/test_footer_gate_234.py`, `tests/test_status_note_325.py`, `tests/test_spec_ampel_470.py`.

## Risks
- Footer-Gate läuft in allen Konsumenten-Projekten: Änderung muss rein datengetrieben
  bleiben (keine Config-Zugriffe in `end_state`) und fail-open.
- Manuelle Freigabe (`by: "po"`) zeigt weiterhin ❗.

## Analysis

- **Type:** Bugfix (Anzeige / Pflicht-Schritt)
- **Affected Files:**
  - `core/hooks/workflow.py` — MODIFY: `next_step` (Fast-Track-Fall in `phase4_approved`),
    `_end_state_open` (⏳ statt ❗ nach Auto-Freigabe in `phase4_approved`)
  - `tests/test_fast_track_anzeige_688.py` — CREATE
  - `CHANGELOG.md`, Versionsstellen — MODIFY (Release 4.26.6)
- **Scope/Risk:** ~15 LoC Code; Risiko mittel (Hook-Code, speist das Fußzeilen-Gate in allen Projekten).
- **Technical Approach:**
  1. `next_step`: `phase4_approved` + `workflow_type == "feature-fast"` → `/50-implement`.
     Speist automatisch `expected_footer_command`, `status_note`, Seitenleiste und Plan.
  2. `_end_state_open`: Liegt `current_phase == phase4_approved` und ist der jüngste
     `approvals`-Eintrag mit `gate == "spec"` von `by == "auto"`, liefert der Endzustand
     ⏳ „Claude führt <cmd> selbst aus“ (wie `self_driven`). Rein datengetrieben, kein
     Config-Zugriff; `cmd` bleibt gesetzt, sodass das Fußzeilen-Gate den Befehl findet.
     Manuelle Freigabe (`by: "po"`) bleibt ❗.
- **Dependencies:** `herdr_bridge.build_report` und `footer_gate` lesen nur diese Funktionen.
- **Open Questions:** keine.
