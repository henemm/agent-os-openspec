# Context: feat-481-autonomy-global

## Request Summary
PO (2026-10-29): „ich möchte … nicht immer für ein "go" missbraucht werden. Setze das selbst! … nicht nur dieses Mal, sondern generell!!!!!“ — Der Autonomie-Modus (#469–#472) soll einmal für alle Projekte gelten. Heute nur `autonomy.mode: auto` in der wirksamen Projekt-Config (`workflow.trusted_config()`).

## Related Files
| File | Relevance |
|------|-----------|
| `core/hooks/workflow.py` | `trusted_config()`, `autonomy_mode()` (strikt: nur Literal `auto`, fail-closed) |
| `core/hooks/edit_gate.py` | Schritt 0a `_config_edit_hit` (#473): Config-Schutz, Ausweg override |
| `core/hooks/bash_gate.py` | `_writes_effective_config` (#473) |
| `core/hooks/config_loader.py` | `protected_config_paths`, `config_path_hit` |
| `core/hooks/herdr_bridge.py` | Muster #480: Env-Schalter `OPENSPEC_HERDR_AUTO_CLEAR` |
| `tests/test_autonomy_schalter_469.py`, `tests/test_config_edit_schutz_473.py` | bestehende Verträge |

## Analysis
- Schalter: Umgebungsvariable `OPENSPEC_AUTONOMY` aus `~/.claude/settings.json` → `env` (Claude Code reicht sie an alle Hooks und Bash weiter).
- Vorrang: Projekt-Config hat einen `autonomy.mode`-Eintrag → Projekt entscheidet (nur `auto` = auto). Sonst `OPENSPEC_AUTONOMY` nach strip/lower == `auto` → auto. Sonst manual.
- Sicherheit (#470/#473): Autonomie darf sich Claude nicht selbst geben. `~/.claude/settings.json` und `~/.claude/settings.local.json` liegen außerhalb des Projekts und sind bisher ungeschützt → in den Config-Schutz von edit_gate (Schritt 0a) und bash_gate aufnehmen, Ausweg wie bisher `override`. Nebenwirkung: Claude ändert persönliche Claude-Einstellungen nur noch nach `override`.
- Ein in der Sitzung per `export OPENSPEC_AUTONOMY=auto` gesetzter Wert erreicht Hooks nicht (Hooks laufen mit der Umgebung von Claude Code), wohl aber `workflow.py`-Aufrufe im Bash-Tool → `workflow.py auto-approve`/`auto-green` könnten so getäuscht werden. Gegenmaßnahme: bash_gate blockt Bash-Befehle, die `OPENSPEC_AUTONOMY` setzen/exportieren.
- Risk: MEDIUM (Freigabe-Logik), ~+40 LoC Prod, ~+150 Test
