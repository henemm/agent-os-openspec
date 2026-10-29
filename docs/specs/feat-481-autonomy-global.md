---
entity_id: feat-481-autonomy-global
type: feature
created: 2026-10-29
updated: 2026-10-29
status: draft
version: "1.0"
workflow: feat-481-autonomy-global
tags: [autonomy, config, security, hooks]
---

# Autonomie-Modus für alle Projekte einschaltbar (Issue #481)

## Approval

- [ ] Approved

## Purpose

Der Autonomie-Modus (#469–#472) laesst sich einmal fuer alle Projekte einschalten: ueber die Umgebungsvariable `OPENSPEC_AUTONOMY=auto` in `~/.claude/settings.json` unter `env`. Dann entfaellt das `go` nach der Implementierung ueberall, und die Spec-Freigabe braucht den PO nur noch bei roter Ampel. Ein Projekt mit eigenem `autonomy.mode`-Eintrag entscheidet weiterhin selbst. Damit sich Claude diese Autonomie nicht selbst geben kann, werden die persoenlichen Claude-Einstellungsdateien in den Config-Schutz (#473) aufgenommen, und Bash-Befehle, die `OPENSPEC_AUTONOMY` setzen, werden geblockt.

## Source

- **File:** `core/hooks/workflow.py`, `core/hooks/config_loader.py`, `core/hooks/edit_gate.py`, `core/hooks/bash_gate.py`, `config.yaml` (Kommentar)
- **Identifier:** `autonomy_mode`; `user_settings_paths`; `_config_edit_hit` (Schritt 0a); `_writes_effective_config` und eine neue Pruefung auf `OPENSPEC_AUTONOMY`-Zuweisungen in bash_gate

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `core/hooks/workflow.py` (#469/#470) | module | `trusted_config()`, `autonomy_mode()` |
| `core/hooks/config_loader.py` (#473) | module | `protected_config_paths`, `config_path_hit` |
| `core/hooks/edit_gate.py` (#473) | hook | Schritt 0a Config-Schutz, Ausweg `override` |
| `core/hooks/bash_gate.py` (#473) | hook | Schreibziele auf geschuetzte Config |
| Claude Code `settings.json` → `env` | extern | reicht Umgebungsvariablen an Hooks und Bash weiter |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| core/hooks/workflow.py | MODIFY | `autonomy_mode()` beruecksichtigt `OPENSPEC_AUTONOMY`, wenn das Projekt keinen `autonomy.mode`-Eintrag hat |
| core/hooks/config_loader.py | MODIFY | `user_settings_paths()` → `~/.claude/settings.json`, `~/.claude/settings.local.json` |
| core/hooks/edit_gate.py | MODIFY | Schritt 0a: Treffer auch fuer `user_settings_paths()` |
| core/hooks/bash_gate.py | MODIFY | Schreibziele auf `user_settings_paths()` und Zuweisungen an `OPENSPEC_AUTONOMY` blocken (Ausweg `override`) |
| config.yaml | MODIFY | Kommentar am Abschnitt `autonomy`; Template-Eintrag `mode: manual` wird auskommentiert, damit kopierte Projekte den Benutzer-Schalter nicht ueberstimmen |
| tests/test_autonomy_global_481.py | CREATE | Vorrang, Schutz der Benutzer-Einstellungen, Bash-Zuweisungen |
| tests/test_autonomy_schalter_469.py | MODIFY | Default-Test an das auskommentierte Template anpassen (falls er das Literal `manual` erwartet) |
| CHANGELOG.md | MODIFY | Eintrag unter [Unreleased] |

### Estimated Changes

- Files: 1 neu, 7 geaendert
- LoC: +45 Produktion / +160 Test
- Risk Level: MEDIUM (Freigabe-Logik und Schreibschutz)

## Implementation Details

**Vorrang in `autonomy_mode()`** (weiter fail-closed, wirft nie):

1. `trusted_config()` liefert kein dict → `manual` (unveraendert).
2. Die Projekt-Config hat einen Abschnitt `autonomy` (dict) mit Schluessel `mode` → das Projekt entscheidet: `auto` nur beim exakten Literal `auto`, sonst `manual` (unveraendert).
3. Sonst: `auto` genau dann, wenn `os.environ.get("OPENSPEC_AUTONOMY", "").strip().lower() == "auto"`; sonst `manual`.

Alle bisherigen Aufrufer (`auto-approve`, `auto-green`, `post_implementation_gate`, Befehlstexte) nutzen `autonomy_mode()` und erben das Verhalten. Was im Auto-Modus menschlich bleibt (rote Ampel, AMBIGUOUS, zweites BROKEN, Override, Deploy, Stop-Lock), bleibt unveraendert.

**Schutz der Benutzer-Einstellungen.** `config_loader.user_settings_paths() -> list[Path]`: `Path(os.path.expanduser("~/.claude/settings.json"))` und `.../settings.local.json` (auch wenn nicht vorhanden; Anlegen zaehlt). `edit_gate` Schritt 0a gibt Treffer, wenn `config_path_hit(file_path, user_settings_paths())`; `bash_gate._writes_effective_config` prueft Schreibziele zusaetzlich gegen diese Liste. Ausweg wie bei #473: der User tippt `override`. Meldungstext nennt den Grund („persoenliche Claude-Einstellungen“).

**Bash-Zuweisungen.** `bash_gate` blockt (Ausweg `override`) Befehle, in denen `OPENSPEC_AUTONOMY` als Zuweisung vorkommt: `OPENSPEC_AUTONOMY=…` am Segmentanfang oder nach `export`/`env`/`declare`/`set`. Reines Lesen (`echo $OPENSPEC_AUTONOMY`, `env | grep OPENSPEC_AUTONOMY`) bleibt erlaubt.

**Template.** In `config.yaml` wird `mode: manual` unter `autonomy:` auskommentiert und ein Kommentar ergaenzt: benutzerweit per `"env": {"OPENSPEC_AUTONOMY": "auto"}` in `~/.claude/settings.json`; ein Projekteintrag `mode: manual|auto` hat Vorrang.

## Expected Behavior

- **Input:** Sitzung in einem Projekt ohne `autonomy.mode`, `OPENSPEC_AUTONOMY=auto` in der Umgebung von Claude Code
- **Output:** `workflow.py autonomy` meldet `AUTONOMY=auto`; GREEN wird automatisch freigegeben, Spec-Freigabe bei gruener Ampel automatisch
- **Side effects:** Claude kann `~/.claude/settings.json`/`settings.local.json` nur noch nach `override` aendern; Bash-Zuweisungen an `OPENSPEC_AUTONOMY` werden geblockt

## Known Limitations

- Die Umgebungsvariable wirkt erst nach einem Neustart von Claude Code.
- Den Schalter traegt der PO selbst ein oder Claude nach `override`.
- Auch harmlose Aenderungen an den persoenlichen Claude-Einstellungen (z. B. neue Erlaubnisse) brauchen kuenftig `override`.
- Ein Schreibweg ausserhalb von Edit/Write/Bash (z. B. ein anderes Werkzeug) ist nicht abgedeckt.
- Adversary-Befunde (MEDIUM, Folge-Issue): Bash-Zuweisungen an `OPENSPEC_AUTONOMY` hinter Wrappern (`env -u X`, `sudo`, `nohup`, `eval`, `sh -lc`, mehrere Ebenen `bash -c`, Variablen-Indirektion) werden nicht erkannt; die Projektdatei `.claude/settings.local.json` ist per Bash beschreibbar und koennte per `env` die Variable nach einem Neustart setzen.

## Definition of Done

Fertig ist diese Aenderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] Mit `OPENSPEC_AUTONOMY=auto` in `~/.claude/settings.json` laeuft ein Workflow in einem Projekt ohne eigenen Eintrag ohne `go` durch (manuelle Abnahme durch den PO)
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf gruen, insbesondere #469–#473-Tests)

## Acceptance Criteria

- **AC-1:** Given eine Projekt-Config ohne `autonomy`-Abschnitt und `OPENSPEC_AUTONOMY` jeweils `auto`, ` AUTO `, `Auto` / When `workflow.py autonomy` laeuft / Then gibt es `AUTONOMY=auto` aus; bei nicht gesetzter Variable, `manual`, `1`, `true` oder leer `AUTONOMY=manual`
  - Test: tests/test_autonomy_global_481.py::test_env_switch_without_project_entry

- **AC-2:** Given Projekt `autonomy.mode: manual` und `OPENSPEC_AUTONOMY=auto` / When `workflow.py autonomy` laeuft / Then `AUTONOMY=manual`; Given Projekt `mode: auto` und Variable nicht gesetzt / Then `AUTONOMY=auto`; Given Projekt `autonomy: {}` (ohne `mode`) und Variable `auto` / Then `AUTONOMY=auto`
  - Test: tests/test_autonomy_global_481.py::test_project_entry_wins_over_env

- **AC-3:** Given ein Edit- bzw. Write-Aufruf auf `~/.claude/settings.json` bzw. `~/.claude/settings.local.json` (HOME auf ein Testverzeichnis gesetzt) ohne Override-Token / When `edit_gate.py` laeuft / Then Exit 2 mit Hinweis auf `override`; mit gueltigem Override-Token Exit 0
  - Test: tests/test_autonomy_global_481.py::test_edit_gate_protects_user_settings

- **AC-4:** Given Bash-Befehle `echo '{}' > ~/.claude/settings.json`, `export OPENSPEC_AUTONOMY=auto`, `OPENSPEC_AUTONOMY=auto python3 x.py`, `env OPENSPEC_AUTONOMY=auto python3 x.py` ohne Override-Token / When `bash_gate.py` laeuft / Then jeweils Exit 2; Given `echo $OPENSPEC_AUTONOMY` bzw. `env | grep OPENSPEC_AUTONOMY` / Then Exit 0
  - Test: tests/test_autonomy_global_481.py::test_bash_gate_blocks_settings_and_env_assignment

- **AC-5:** Given die Repo-`config.yaml` ohne `OPENSPEC_AUTONOMY` / When `autonomy_mode()` mit dieser Config laeuft / Then `manual`; und die Config enthaelt keinen aktiven `autonomy.mode`-Eintrag
  - Test: tests/test_autonomy_global_481.py::test_template_does_not_override_user_switch

## Test Plan

Subprozess-Aufrufe gegen `core/hooks/workflow.py autonomy`, `edit_gate.py`, `bash_gate.py` mit isoliertem Projekt (`CLAUDE_PROJECT_DIR`), `HOME` auf ein Testverzeichnis und gesetzter bzw. entfernter Umgebungsvariable; Override-Token ueber den bestehenden Mechanismus (`override_token.py`, Muster aus `tests/test_config_edit_schutz_473.py`).

- `pytest tests/test_autonomy_global_481.py`
- Regressionslauf: `pytest tests/`
- Syntaxpruefung: `python3 -m py_compile core/hooks/workflow.py core/hooks/config_loader.py core/hooks/edit_gate.py core/hooks/bash_gate.py`
- Manuell: PO-Abnahme

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Zusaetzlicher Eingang fuer den bestehenden Autonomie-Schalter nach dem Muster von #480 plus Erweiterung des bestehenden Config-Schutzes (#473) um zwei Dateien. Kein neues State-Feld, keine neue Gate-Art. Reversibel durch Entfernen der Variable bzw. Projekteintrag `mode: manual`.

## Changelog

- 2026-10-29: Initial spec created
