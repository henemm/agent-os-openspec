# Context: feat-480-auto-clear-global

## Request Summary
(1) Auto-/clear (#467) soll für alle Projekte einschaltbar sein, nicht nur per Projekt-Config (PO: "ja, Schalter für alle Projekte bauen"). Diagnose beim PO: `optin False`, `herdr-config None` in Projekten ohne Eintrag. (2) Bug: `process_watchdog.py` hat als einzige in `hooks/hooks.json` direkt aufgerufene Datei git-Modus 100644 → "Permission denied" nach jedem Bash-Aufruf, Dauerlast-Schutz (#462) lief nie.

## Related Files
| File | Relevance |
|------|-----------|
| `core/hooks/herdr_bridge.py` | `_auto_clear_config()` / `auto_clear_enabled()`: strikter Opt-in nur aus Projekt-Config |
| `core/hooks/process_watchdog.py` | PostToolUse Bash `hook`, SessionEnd `end`; Shebang vorhanden, Modus 100644 |
| `hooks/hooks.json` | ruft alle Hooks direkt als `${CLAUDE_PLUGIN_ROOT}/core/hooks/<datei>.py` auf |
| `tests/test_herdr_auto_clear_467.py`, `tests/test_herdr_plan_deploy_sessionstart_478.py` | Stub-Muster |

## Analysis
- Benutzerweiter Schalter: Umgebungsvariable `OPENSPEC_HERDR_AUTO_CLEAR` (Claude Code reicht `env` aus `~/.claude/settings.json` an Hooks weiter). Keine neue Config-Datei, kein neuer Lade-Pfad.
- Vorrang: Projekt `enabled: false` (explizit) > Projekt `enabled: true` > Env `1`/`true` (Groß/Klein egal) > aus. `herdr.enabled: false` bleibt Eltern-Kill-Switch (über `_pane()`).
- Watchdog: nur Dateimodus 100755 + Test über alle in `hooks.json` referenzierten Dateien. Achtung: aktiviert erstmals den seit 3.43.0 gewollten, aber nie gelaufenen Dauerlast-Schutz (beendet Suchen ab `/`/`~` nach Zeitlimit).
- Risk: LOW–MEDIUM; ~+10 LoC Prod, ~+100 Test
