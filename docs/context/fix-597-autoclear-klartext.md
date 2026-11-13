# Context: fix-597-autoclear-klartext

## Request Summary
Der Auto-Modus mit Herdr-Auto-/clear bleibt an Phasengrenzen stehen (beobachtet nach
`/40-tdd-red`, `/50-implement`, laut PO "mehr oder weniger alle Phasen inkl. /70-deploy"),
sobald die Abschlussantwort einmal von einem anderen Stop-Hook zurückgewiesen wird
(konkret: `klartext_gate.py` wegen Git-Wörtern aus der Vorlage). PO-Auftrag (2026-11-13):
autonom umsetzen, zuerst Best Practice recherchieren; PO-Einwand: die Herdr-Anbindung wirkt
"total kompliziert gedacht" — gewünscht ist ein einfacheres, robustes Modell.

## Ursachenkette (belegt)
1. Vorlagen-Ausgabeblöcke enthalten Git-Wörter: `skills/40-tdd-red/SKILL.md:140,179`
   ("committed"), `skills/50-implement/SKILL.md:370,402` ("Commit", "committed"),
   `skills/60-validate` ("Commit", "committen"), weitere Treffer in 01/82/83/90/99
   (Scan aller `---`-Abschnitte mit `klartext_gate.treffer`).
2. Stop-Hooks laufen laut offizieller Doku **parallel**, ohne Reihenfolge, keiner sieht das
   Verdict des anderen ("When an event fires, its matching hooks run in parallel",
   code.claude.com/docs/en/hooks). `footer_gate.py` (main, Zeile ~265) spawnt per
   `herdr_bridge.maybe_auto_clear` den Runner, während `klartext_gate.py` denselben Stop per
   Exit 2 blockt.
3. `maybe_auto_clear` verbraucht beim Spawn die Grenze (`_consume_boundary`) und setzt den
   Once-Lock (`_acquire_lock`, 600 s). Der Runner sieht den Folge-Stop (Signal `stop`) und
   bricht mit "Claude arbeitet weiter" ab — der Lock bleibt, obwohl nichts getippt wurde.
4. Der Folge-Stop trägt `stop_hook_active: true` → `maybe_auto_clear` verwirft die Grenze
   explizit (#495) und loggt `skip: stop_hook_active`. Kein zweiter Versuch möglich.

Kernproblem: Claude Code hat kein Ereignis "Turn wirklich zu Ende, nachdem alle Stop-Hooks
durch sind". Aber: Ein geblockter Stop erzeugt immer einen weiteren Stop (Cap: 8 Blocks in
Folge, `CLAUDE_CODE_STOP_HOOK_BLOCK_CAP`). Der **letzte Stop nach einer Ruhephase** ist daher
per Konstruktion das echte Turn-Ende.

## Related Files
| File | Relevance |
|------|-----------|
| core/hooks/herdr_bridge.py | `maybe_auto_clear` (Spawn, Grenz-Verbrauch, stop_hook_active-Skip), `_acquire_lock`/`_release_lock`, `_Runner` (`_check_activity` bricht bei jedem späteren Stop ab), `record_signal`, `run_auto_clear` |
| core/hooks/footer_gate.py | Stop-Hook; `_record_stop` (Stop-Signal je Pane), `_maybe_auto_clear` auf dem Pfad "Fußzeile korrekt", `_discard_boundary` bei zweimal falscher Fußzeile |
| core/hooks/klartext_gate.py | Stop-Hook; `treffer()`, Wortliste `MUSTER`, Ausnahmen (stop_hook_active, Nutzer fragt selbst, `OPENSPEC_KLARTEXT=0`) |
| core/hooks/workflow.py | `cmd_autoclear`/`_record_auto_clear_boundary` (Grenz-Vermerk bei `AUTO_CLEAR=on`), `_note_transition_boundary` (Vermerk beim Phasenwechsel, #497), `expected_footer_command` |
| hooks/hooks.json | Stop: footer_gate + klartext_gate (parallel) |
| skills/*/SKILL.md, core/commands/*.md | Ausgabeblöcke (Positiv-/Negativ-Block); `skills/` generiert aus `core/commands` via `scripts/sync_skills.py` |
| tests/test_herdr_auto_clear_467.py, test_autoclear_boundary_495.py, test_autoclear_transition_497.py, test_autoclear_eigene_signale_506.py, test_kette_auto_clear_489.py, test_auto_clear_global_480.py | Bestehende Tests; kodieren u. a. "kein Spawn bei stop_hook_active" und "Grenze bei stop_hook_active verbraucht" — Verhalten ändert sich bewusst |
| tests/test_klartext_gate_582.py | Tests Klartext-Gate |
| scripts/e2e_auto_clear.sh | E2E am echten Herdr (Szenarien A–Q), lokal beim PO, nicht in CI |

## Existing Patterns
- Hook-Signale je Pane in `.claude/herdr_signals/<pane>.<kind>.json` (#506): input (UserPromptSubmit), session (SessionStart), activity (PreToolUse, Notification permission_prompt, PermissionRequest, SessionEnd), stop (jeder Stop, footer_gate).
- Herdr nur als Tastatur (`pane send-text` + `pane send-keys enter`); `agent wait`/`agent prompt` bewusst entfernt (#506): PO-Manifest stuft `❗ Du:` als `blocked` ein, `agent prompt` lehnt bei `blocked` ab.
- Fail-open überall; Runner endet immer mit Exit 0 und loggt `OK`/`ABBRUCH`/`skip:` in `.claude/herdr_auto_clear.log`.
- Grenz-Vermerk `auto_clear_boundary {phase, command, at}` im Workflow-State, max. 15 min gültig.

## Recherche Best Practice
- Claude Code Hooks: parallel, keine Reihenfolge, Merge erst nach Abschluss aller Hooks; `stop_hook_active` = Claude läuft wegen eines Stop-Hooks weiter; Stop-Block-Cap 8.
- Herdr (`herdrdev/herdr`, INTEGRATIONS.md): offizielle Claude-Integration mappt `Stop → idle`, `UserPromptSubmit/PreToolUse → working`, `PermissionRequest → blocked` — dieselbe Lücke (erster Stop = idle). Zustandserkennung sonst per Bildschirm-Heuristik. `wait agent-state` ist CLI-Komfort über Event-Subscriptions. Kein Mechanismus "nach allen Stop-Hooks".
- Verteilte Systeme: Seiteneffekt erst nach bestandener Validierung; "acknowledge after success" (Vermerk erst nach erfolgreichem Tippen verbrauchen); Debounce (auf Ruhe warten, dann den letzten Zustand auswerten) statt "bei jeder Unruhe abbrechen"; idempotent via Schlüssel.

## Dependencies
- Upstream: hook_utils (`read_state_json`, `atomic_write_json`, `find_project_root`), workflow (`expected_footer_command`), Herdr-CLI (`HERDR_BIN_PATH`, `HERDR_PANE_ID`, `HERDR_ENV`).
- Downstream: footer_gate (Stop), phase_listener (input-Signal), session_banner (session-Signal), session_singleton_guard (activity-Signal), `herdr_bridge.py signal activity` (Notification/PermissionRequest), alle Phasen-Befehle (`workflow.py autoclear`).

## Existing Specs
- docs/specs/feat-467-herdr-auto-clear.md — Ursprung Auto-/clear
- docs/specs/fix-495-autoclear-mechanisch.md — Grenz-Vermerk, Verbrauch, stop_hook_active
- docs/specs/fix-497-autoclear-grenze-beim-phasenwechsel.md — Vermerk beim Phasenwechsel, Verwerfen nach zweimal falscher Fußzeile
- docs/specs/fix-506-autoclear-ohne-herdr-status.md — eigene Signale, Herdr als Tastatur, Abbruch bei Folge-Stop
- docs/specs/feat-582-* (Klartext-Gate)

## Nebenbefund (Hooks aus 4.11.0)
Claude Code liest Hook-Registrierungen beim Sitzungsstart ein; ein Plugin-Update während
einer laufenden Sitzung ändert Befehlstexte (Skills werden frisch gelesen), die Hooks laufen
aber bis zum Neustart aus dem alten Versionsordner. Am Konsumenten-Rechner nicht prüfbar;
in der Analyse klären, ob ein Hinweis (Versionsabgleich Hook-Pfad vs. geladene Version)
in den Scope gehört oder als eigenes Issue.

## Risks & Considerations
- Stop-Hooks laufen in JEDEM Projekt bei JEDEM Turn-Ende: fail-open bleibt tragend.
- Berechtigungsdialog-Schutz (#506 Szenario P) darf nicht verloren gehen: während Claude weiterarbeitet (activity/input), darf nie getippt werden.
- Nutzereingabe (input-Signal) muss weiterhin sofort und endgültig abbrechen.
- Doppelte Runner verhindern (ein Runner je Pane/Grenze), auch wenn mehrere Stops in Folge kommen.
- Bestehende Tests kodieren das alte Verhalten; bewusst anpassen, nicht löschen.
- `skills/` ist generiert: Vorlagen in `core/commands/` ändern und `scripts/sync_skills.py` laufen lassen.
