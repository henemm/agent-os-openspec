---
entity_id: feat-480-auto-clear-global
type: feature
created: 2026-10-29
updated: 2026-10-29
status: draft
version: "1.0"
workflow: feat-480-auto-clear-global
tags: [herdr, auto-clear, hooks, process-watchdog]
---

# Auto-/clear für alle Projekte einschaltbar; process_watchdog.py ausführbar (Issue #480)

## Approval

- [ ] Approved

## Purpose

Erstens laesst sich Auto-`/clear` (#467) einmal fuer alle Projekte einschalten: ueber die Umgebungsvariable `OPENSPEC_HERDR_AUTO_CLEAR`, die der PO in `~/.claude/settings.json` unter `env` setzt. Ein Projekt kann es weiterhin ausdruecklich ab- oder einschalten. Zweitens wird `core/hooks/process_watchdog.py` ausfuehrbar, damit der in `hooks/hooks.json` registrierte Aufruf nicht mehr mit „Permission denied“ scheitert; ein Test verhindert, dass einer registrierten Hook-Datei das Ausfuehrungsrecht erneut fehlt.

## Source

- **File:** `core/hooks/herdr_bridge.py`, `core/hooks/process_watchdog.py` (nur Dateimodus), `config.yaml` (nur Kommentar)
- **Identifier:** `_auto_clear_config`, `auto_clear_enabled`; Git-Modus von `process_watchdog.py`

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `core/hooks/herdr_bridge.py` (#467, #478) | module | Opt-in-Leser, `maybe_auto_clear`, Runner |
| `core/hooks/config_loader.py` | module | `load_config()` fuer den Projekt-Eintrag |
| `hooks/hooks.json` | config | ruft Hook-Dateien direkt (ohne `python3`) auf |
| `core/hooks/process_watchdog.py` (#462) | hook | PostToolUse Bash / SessionEnd |
| Claude Code `settings.json` → `env` | extern | reicht Umgebungsvariablen an Hooks weiter |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| core/hooks/herdr_bridge.py | MODIFY | `_auto_clear_config()` beruecksichtigt `OPENSPEC_HERDR_AUTO_CLEAR`, wenn das Projekt nichts sagt |
| core/hooks/process_watchdog.py | MODIFY | Git-Modus 100644 → 100755 (Inhalt unveraendert) |
| config.yaml | MODIFY | Kommentar am Abschnitt `herdr.auto_clear` zum benutzerweiten Schalter |
| tests/test_auto_clear_global_480.py | CREATE | Vorrang-Regeln, Ausfuehrungsrecht aller in hooks.json referenzierten Dateien |
| CHANGELOG.md | MODIFY | Eintrag unter [Unreleased] |

### Estimated Changes

- Files: 1 neu, 4 geaendert
- LoC: +15 Produktion / +100 Test
- Risk Level: MEDIUM (aktiviert den seit 3.43.0 registrierten, aber nie gelaufenen Dauerlast-Schutz)

## Implementation Details

**Vorrang beim Einschalten** (`_auto_clear_config()`):

1. Steht in der Projekt-Config `herdr.auto_clear.enabled` als Literal `false` → aus.
2. Literal `true` → an (mit den Projektwerten fuer `grace_s`, `idle_timeout_s`, `announce` wie bisher).
3. Sonst (Abschnitt fehlt oder `enabled` fehlt/kein bool): an genau dann, wenn `OPENSPEC_HERDR_AUTO_CLEAR` nach `strip().lower()` einer von `1`, `true`, `yes`, `on` ist; Werte `grace_s`, `idle_timeout_s`, `announce` aus dem Projektabschnitt, soweit vorhanden, sonst Defaults.

`herdr.enabled: false` schaltet wie bisher alles ab (Gate `_pane()` in `maybe_auto_clear`). Jede Ausnahme → aus.

**Konfig-Kommentar.** Am Abschnitt `herdr.auto_clear` in `config.yaml` eine Kommentarzeile: benutzerweit per `"env": {"OPENSPEC_HERDR_AUTO_CLEAR": "1"}` in `~/.claude/settings.json`; ein Projektwert `true/false` hat Vorrang. Der Wert `enabled: false` im Template bleibt, wird aber auskommentiert ersetzt durch einen Hinweis, damit das Template-Projekt nicht ausdruecklich abschaltet: `# enabled: false   # true = an, false = aus (auch gegen den benutzerweiten Schalter); weglassen = Benutzer-Schalter entscheidet`.

**process_watchdog.py.** Nur Dateimodus 100755 (git `update-index --chmod=+x`), Inhalt unveraendert.

## Expected Behavior

- **Input:** Claude-Code-Sitzung in Herdr in einem Projekt ohne `herdr.auto_clear`-Eintrag, `OPENSPEC_HERDR_AUTO_CLEAR=1` in der Umgebung; jeder Bash-Aufruf
- **Output:** `auto_clear_enabled()` ist wahr, Auto-`/clear` greift an Phasengrenzen; kein „Permission denied“ mehr nach Bash-Aufrufen
- **Side effects:** Der Dauerlast-Schutz (#462) laeuft erstmals tatsaechlich nach jedem Bash-Aufruf und am Sitzungsende

## Known Limitations

- Die Umgebungsvariable wirkt erst nach einem Neustart von Claude Code.
- Der Dauerlast-Schutz war seit 3.43.0 registriert, lief aber nie; mit diesem Fix beendet er erstmals lange Suchen ab `/`, `~` oder `$HOME` (Regeln aus #462 unveraendert).

## Definition of Done

Fertig ist diese Aenderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] Mit `OPENSPEC_HERDR_AUTO_CLEAR=1` in `~/.claude/settings.json` greift Auto-`/clear` in einem Projekt ohne eigenen Eintrag; nach Bash-Aufrufen erscheint kein „Permission denied“ mehr (manuelle Abnahme durch den PO)
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf gruen, insbesondere #467/#478/#462-Tests)

## Acceptance Criteria

- **AC-1:** Given eine Projekt-Config ohne `herdr.auto_clear` und `OPENSPEC_HERDR_AUTO_CLEAR` jeweils auf `1`, `true`, `YES`, ` on ` / When `auto_clear_enabled()` laeuft / Then ist das Ergebnis `True`; bei nicht gesetzter Variable, `0`, `false` oder leer `False`
  - Test: tests/test_auto_clear_global_480.py::test_env_switch_without_project_entry

- **AC-2:** Given Projekt-Config `herdr.auto_clear.enabled: false` und `OPENSPEC_HERDR_AUTO_CLEAR=1` / When `auto_clear_enabled()` laeuft / Then `False`; Given Projekt `enabled: true` und Variable nicht gesetzt bzw. `0` / Then `True`
  - Test: tests/test_auto_clear_global_480.py::test_project_value_wins_over_env

- **AC-3:** Given `OPENSPEC_HERDR_AUTO_CLEAR=1`, Projektabschnitt `herdr.auto_clear` nur mit `grace_s: 7` (ohne `enabled`) / When `_auto_clear_config()` laeuft / Then liefert es eine Config mit `grace_s` 7 und den Defaults fuer die uebrigen Werte
  - Test: tests/test_auto_clear_global_480.py::test_env_switch_uses_project_values

- **AC-4:** Given Herdr-Env gueltig (Stub), kein Projekt-Eintrag, `OPENSPEC_HERDR_AUTO_CLEAR=1`, Workflow mit erwartetem Slash-Befehl und Antwort mit Positivmarker / When `footer_gate.py` den Stop-Payload verarbeitet / Then wird der Auto-`/clear`-Runner gestartet (Stub protokolliert `agent wait`)
  - Test: tests/test_auto_clear_global_480.py::test_footer_gate_spawns_with_env_switch

- **AC-5:** Given `hooks/hooks.json` / When alle darin per `${CLAUDE_PLUGIN_ROOT}/...` referenzierten Dateien geprueft werden / Then hat jede den Git-Modus 100755 (`git ls-files -s`) und ist im Arbeitsbaum ausfuehrbar
  - Test: tests/test_auto_clear_global_480.py::test_all_registered_hooks_are_executable

## Test Plan

Opt-in-Leser per Subprozess mit isoliertem Projekt (`CLAUDE_PROJECT_DIR`, `config.yaml`) und gesetzter bzw. entfernter Umgebungsvariable; footer_gate-Lauf mit Stub-Binary nach Muster `tests/test_herdr_auto_clear_467.py`; Dateimodus per `git ls-files -s`.

- `pytest tests/test_auto_clear_global_480.py`
- Regressionslauf: `pytest tests/`
- Syntaxpruefung: `python3 -m py_compile core/hooks/herdr_bridge.py`
- Manuell: PO-Abnahme in echtem Herdr

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Ein zusaetzlicher Eingang (Umgebungsvariable) fuer einen bestehenden Opt-in, ohne neue Config-Datei oder Gate-Logik, plus Korrektur eines Dateimodus. Voll reversibel durch Entfernen der Variable bzw. Projektwert `false`.

## Changelog

- 2026-10-29: Initial spec created
