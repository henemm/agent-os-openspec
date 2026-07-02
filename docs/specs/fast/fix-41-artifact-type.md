# Mini-Spec: fix-41-artifact-type

Issue #41: Die Skills `50-implement` (Step 8c) dokumentieren
`workflow.py add-artifact adversary_dialog ...`, aber `VALID_ARTIFACT_TYPES` in
`core/hooks/workflow.py` kennt diesen Typ nicht — der dokumentierte Befehl schlägt
mit "Invalid artifact type" fehl (heute live in zwei Workflows getroffen, Workaround
war jeweils der generische Typ `file`).

## Was ändert sich
- `core/hooks/workflow.py`: `"adversary_dialog"` wird in `VALID_ARTIFACT_TYPES`
  aufgenommen (der Typ ist semantisch sinnvoll — das Adversary-Protokoll ist ein
  eigenständiges Pflicht-Artefakt des Workflows).
- `CHANGELOG.md`: Eintrag unter `[Unreleased]` → `### Fixed`.

## Was darf sich nicht ändern
- Bestehende Typen bleiben unverändert gültig; keine Änderung an der
  `add-artifact`-Logik selbst.

## Manuelle Test-Schritte
1. `workflow.py add-artifact adversary_dialog <pfad> <beschreibung> phase6b_adversary`
   → wird akzeptiert.
2. `workflow.py add-artifact quatsch ...` → weiterhin abgelehnt mit Liste gültiger Typen.

## Inline-Test (wird während Implementierung geschrieben)
- [ ] Test: `adversary_dialog` ist in `VALID_ARTIFACT_TYPES` enthalten und
  `add-artifact adversary_dialog` läuft gegen einen tmp-Workflow erfolgreich durch.
