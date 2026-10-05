# Fast Track: Fremde `config.yaml` nicht als Plugin-Config lesen, Freigabe-Sperre sichtbar (#372)

## Problem

1. `config_loader` sucht die Plugin-Config unter `openspec.yaml`, `config.yaml`, `.openspec.yaml`.
   In Projekten, deren App selbst eine `config.yaml` im Root hat (Fundprojekt: Go-Dienst, Datei
   gitignored, enthält ein Bot-Token), liest das Plugin diese App-Datei als Projekt-Config. Ein
   gleichnamiger Schlüssel der App würde ein Gate umkonfigurieren; `config_source_note()` meldet
   „Grenzen aus: …/config.yaml". Die Datei bestimmt außerdem beim Hochlaufen in
   `find_project_root()` die Projektwurzel.
2. `scripts/ci_spec_gate.py` liest seinen Kill-Switch nur aus `<root>/config.yaml` — die von
   `setup.py` erzeugte `openspec.yaml` kennt es gar nicht.
3. Eine an `_check_adr`/`_check_po_briefing` gescheiterte Freigabe meldet `phase_listener.py` nur
   per `systemMessage` (für den Nutzer). Claude erfährt den Grund nicht und kann die Spec nicht
   reparieren. Bei beiden Fehlern wird nur der erste genannt.
4. Der spec-validator behandelt das ADR-Feld nicht ausdrücklich als ERROR, obwohl es die Freigabe
   hart blockiert.

## Scope

- `core/hooks/config_loader.py`: Plugin-Schlüssel-Erkennung für `config.yaml` im Projekt-Root
  (`is_plugin_config()`), angewandt in `_find_config_file()` und `find_project_root()`;
  `config_source_note()` nennt eine übergangene Datei.
- `scripts/ci_spec_gate.py`: `_config()` löst die Config-Datei wie `config_loader` auf
  (Fallback ohne Import).
- `core/hooks/phase_listener.py`: Sperrgrund zusätzlich als `additionalContext`, alle Gründe.
- `core/agents/spec-validator.md`: ADR-Feld als ERROR.
- Nicht enthalten: `core/tools/output_validator.py`, `core/tools/e2e_test_harness.py` (eigene,
  ungebundene Werkzeuge).

## Migration

Keine Breaking Change für bestehende Projekte: Die Suchreihenfolge bleibt; `openspec.yaml`
gewinnt weiterhin. Eine Root-`config.yaml` wird weiter gelesen, sobald sie mindestens einen
Plugin-Block enthält — jede aus dem Template entstandene Datei tut das. Neu übergangen wird nur
eine Root-`config.yaml` ohne jeden Plugin-Block bzw. nur mit allgemeinen Namen (`project`,
`agents`, `deploy`, `modules`, `hooks`), die auch eine App verwenden könnte. `.claude/config.yaml`
bleibt ungeprüft gültig (Plugin-Ordner). Die Notiz in `config_source_note()` zeigt eine
übergangene Datei und rät zu `openspec.yaml`.

## Definition of Done

Jeder Befund ist durch einen Test belegt, der ohne die Änderung rot ist; die volle Suite bleibt grün.

## Acceptance Criteria

- **AC-1:** Given ein Projekt-Root mit einer `config.yaml` ohne Plugin-Block (z. B. `bot_token:`, `project:`), When `load_config()` läuft, Then stammen die Werte aus den Voreinstellungen und `config_source_note()` nennt die Datei als übergangen.
- **AC-2:** Given eine Root-`config.yaml` mit einem Plugin-Block (z. B. `adr_gate:` oder `scope_guard:`), When `load_config()` läuft, Then gelten ihre Werte wie bisher.
- **AC-3:** Given `openspec.yaml` und eine App-`config.yaml` im Root, When `load_config()` läuft, Then gilt `openspec.yaml`.
- **AC-4:** Given ein Unterordner mit App-`config.yaml` unter einem Git-Repo, When `find_project_root()` ohne `CLAUDE_PROJECT_DIR` aus dem Unterordner läuft, Then ist die Wurzel das Git-Repo.
- **AC-5:** Given `ci_spec_gate.enabled: false` in `openspec.yaml`, When das CI-Gate läuft, Then ist es abgeschaltet; eine App-`config.yaml` mit gleichem Schlüssel-Namen ohne Plugin-Block wird nicht gelesen.
- **AC-6:** Given eine Spec mit leerem ADR-Feld in phase3_spec, When der Nutzer „approved" schreibt, Then enthält die Hook-Ausgabe den Sperrgrund als `additionalContext`; scheitern ADR und Briefing, stehen beide Gründe darin.
- **AC-7:** Jeder Top-Level-Schlüssel der Template-`config.yaml` ist entweder als Plugin-Block oder als allgemeiner Name eingeordnet (Drift-Test).

## Test Plan

- `tests/test_app_config_yaml_372.py` (AC-1 bis AC-7)
- Volle Suite
