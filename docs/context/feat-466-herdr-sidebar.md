# Context: feat-466-herdr-sidebar

## Request Summary
Läuft Claude Code in einem Herdr-Pane, soll der Workflow-Stand (Issue, Phase x/8, nächster Schritt) in der Herdr-Sidebar sichtbar sein. Basis für #467 (Auto-`/clear` via Herdr).

## Related Files
| File | Relevance |
|------|-----------|
| `core/hooks/workflow.py` | `PHASE_NUMBERS`, `TOTAL_PHASES`, `PHASE_NAMES`, `next_step()`, `expected_footer_command()`, `issue_number()`, `status_note()` liefern alle Anzeige-Werte. Phasen-Schreibstellen: `cmd_start` (~1246), `cmd_phase` (1389), Abschluss `complete` (1796); alle über `_save_active()`/`_atomic_write()` |
| `core/hooks/phase_listener.py:583` | Freigabe setzt `phase4_approved` direkt im eigenen Prozess (nicht über `cmd_phase`) |
| `core/hooks/session_banner.py` | SessionStart-Hook, `build_output()` kennt `source` (startup/resume/clear/compact) — Stelle für Initial-Report |
| `core/hooks/footer_gate.py` | Stop-Hook bei jedem Turn-Ende; nutzt `expected_footer_command()` |
| `core/hooks/config_loader.py` | `load_config()` (YAML + settings.local.json), Kill-Switch-Muster wie `po_briefing_gate.enabled` |
| `config.yaml` | Template — neuer Abschnitt `herdr:` |
| `setup.py:368,473` | kopiert `core/hooks/*.py` per Glob → neue Datei wird automatisch mitinstalliert |
| `hooks/hooks.json` | nur nötig, falls eigener Hook-Eintrag |
| `tests/` | pytest, 154 Dateien, Muster `test_<thema>_<issue>.py` |

## Herdr-Schnittstelle (Quelle: github.com/ogulcancelik/herdr, docs/preview/website/src/content/docs)
- Env im Pane: `HERDR_ENV=1`, `HERDR_PANE_ID`, `HERDR_BIN_PATH`, `HERDR_SOCKET_PATH` — vererbt an alle Kindprozesse (also auch Claude-Hooks und `workflow.py` aus dem Bash-Tool)
- `"$HERDR_BIN_PATH" pane report-metadata <pane> --source user:<x> --agent claude --title ... --display-agent ... --token k=v --clear-token k --state-label working=... --ttl-ms N`
  - display-only, übernimmt nicht die State-Autorität der offiziellen Claude-Integration
  - Tokens: max 16 pro Report, 32 pro Pane, Name 1–32 `[A-Za-z0-9_-]`; in Sidebar-Zeilen als `$name` (configuration.mdx → Sidebar row layouts, `[ui.sidebar.agents.rows_by_agent]`)
  - Token-Metadata wird nach Herdr-Server-Restart nicht wiederhergestellt
- `herdr notification show <title> --body ...` (title ≤80, body ≤240 Zeichen)
- `workspace report-metadata` für Space-Zeilen
- Empfehlung Herdr: im Hintergrund/kurzer Timeout, Fehler ignorieren

## Existing Patterns
- Fail-open-Hilfen (`try/except Exception: pass`) in `session_banner.py`, `footer_gate.py`
- Anzeige-Logik zentral in `workflow.py` (`status_note`, `expected_footer_command`) — nicht duplizieren
- Kill-Switches unter `config.yaml` → `<feature>.enabled`

## Dependencies
- Upstream: Herdr-CLI (extern, optional), `workflow.py`-Phasentabellen
- Downstream: #467 nutzt denselben Herdr-Aufruf-Helper

## Risks & Considerations
- Phasenwechsel an 4 Stellen (start, phase, complete, phase_listener-Approval) → zentraler Aufrufpunkt nötig, sonst Drift
- `workflow.py` ist Kern-Pfad: Herdr-Aufruf darf nie blockieren, nie Exit-Code ändern, nie stdout verschmutzen (stdout von Hooks ist teils JSON)
- Herdr in dieser Cloud-Umgebung nicht installiert → Tests mit Stub-Binary über `HERDR_BIN_PATH`
- `HERDR_PANE_ID` gehört zur Session; Worktree-Sessions in getrennten Panes melden nur ihren eigenen Workflow
- Nach `finish`/`abandon` Tokens räumen

## Analysis

### Type
Feature

### Korrektur zum Kontext
Nicht alle Phasen-Schreibstellen laufen über `_save_active`: `cmd_start` nutzt `_atomic_write` direkt, `complete`/`abandon` archivieren ohne Save, `cmd_switch` setzt nur den Zeiger, `phase_listener` schreibt über eigenes `_save_workflow`.

### Affected Files (with changes)
| File | Change Type | Description |
|------|-------------|-------------|
| core/hooks/herdr_bridge.py | CREATE | Env-/Config-Gate, `build_report(data)`, `report_workflow(data)`, `clear()`, generisches `run_herdr(args, wait, timeout)` (Basis #467) |
| core/hooks/workflow.py | MODIFY | Aufruf in `_save_active`, `cmd_start`, `cmd_switch`, Clear in `complete`/`abandon` |
| core/hooks/phase_listener.py | MODIFY | Aufruf am Ende von `_save_workflow` |
| core/hooks/session_banner.py | MODIFY | Republish in `main()` (startup/resume/clear/compact) |
| core/hooks/config_loader.py | MODIFY | `herdr` in `PLUGIN_CONFIG_KEYS` |
| config.yaml | MODIFY | Abschnitt `herdr:` + Sidebar-Beispiel als Kommentar |
| tests/conftest.py | MODIFY | autouse: `HERDR_*`-Env entfernen (Entwickler in Herdr) |
| tests/test_herdr_sidebar_466.py | CREATE | Stub-Binary-Tests |
| CHANGELOG.md, CLAUDE.md-Tabelle | MODIFY | Doku |

### Scope Assessment
- Files: 2 neu, ~7 geändert
- Estimated LoC: +150 Prod / +250 Test
- Risk Level: MEDIUM (Kern-Pfad, aber fail-open/no-op)

### Technical Approach
- Gate: `HERDR_ENV == "1"`, `HERDR_PANE_ID` gesetzt, `HERDR_BIN_PATH` absolute, ausführbare reguläre Datei, `herdr.enabled != false`.
- Aufruf detached: `Popen(argv, stdin/stdout/stderr=DEVNULL, start_new_session=True, close_fds=True)`, kein Shell, alles in `try/except Exception`.
- `--seq` = Millisekunden-Zeitstempel (Herdr ignoriert ältere Reports → Reihenfolge-Rennen der detachten Prozesse unschädlich).
- argv: `pane report-metadata <pane> --source user:openspec --agent claude --seq <ms> --title "#466 5/8 TDD-RED" --token workflow=… --token issue=… --token phase=5/8 --token step=TDD-RED --token next=…`
- Kurzlabels: CONTEXT, ANALYSE, SPEC, APPROVED, TDD-RED, IMPLEMENT, ADVERSARY (6b), VALIDATE, DONE.
- `next` = `expected_footer_command()`; Freitext (Freigabe) → `approved`.
- Clear (complete/abandon/kein Workflow/phase8): `--clear-title` + `--clear-token` für alle 5 Tokens.
- Kein TTL, kein Stop-Hook in v1.

### Herdr-Fakten (verifiziert, Herdr 0.9.5, Tokens seit 0.7.4)
- Token-Werte, Titel: max 80 Zeichen, Control-Chars entfernt, leer = clear; unerwähnte Tokens bleiben (Patch-Semantik).
- `--clear-title`, `--clear-token NAME` existieren; max 32 sequenzierte Quellen pro Pane-Lebenszeit (wir nutzen 1).

### Risiken
- Herdr-Server-Restart verliert Tokens bis zum nächsten Statewechsel/SessionStart.
- `HERDR_BIN_PATH` wird ausgeführt: nur absolute reguläre Datei, kein Shell.
- Tests dürfen die echte Sidebar des Entwicklers nicht bespielen → conftest-Fixture.
