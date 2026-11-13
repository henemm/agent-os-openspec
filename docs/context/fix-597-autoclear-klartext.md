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

## Analysis

### Type
Bug (Ursache belegt, siehe Ursachenkette oben).

### Leitidee (Antwort auf den PO-Einwand "zu kompliziert")
Eine Regel statt Sonderfälle: **Jedes saubere Antwortende darf die Übergabe starten, ein
späteres ersetzt ein früheres, als erledigt gilt sie erst, wenn wirklich getippt wurde.**
- Der Grenz-Vermerk `auto_clear_boundary` ist das einzige Einmal-Token (Idempotenz-Schlüssel):
  der Runner nimmt es atomar unmittelbar vor dem Tippen von `/clear`; wer es nicht bekommt,
  tippt nicht. Der 10-min-Once-Lock (`herdr_auto_clear_state.json`) entfällt dadurch.
- Kein Verbrauch beim Spawn, keine Sonderbehandlung von `stop_hook_active`.
- Bricht ein Runner ab, weil Claude weiterarbeitet, bleibt das Token liegen; der nächste
  saubere Stop startet einen neuen Runner (der alte bricht von selbst ab, weil er den neueren
  Stop sieht). Andere Abbrüche (Nutzer schreibt, Fehler, Deadline) verwerfen das Token wie bisher.
- Prüfen vor Handeln: `maybe_auto_clear` fragt den Klartext-Prüfer (gleiche Funktion, gleiche
  Ausnahmen) und startet bei Zurückweisung gar nicht erst (Token bleibt).
- Herdr bleibt Tastatur (Begründung #506; Herdr-eigene Claude-Integration mappt Stop→idle und
  hat dieselbe Lücke).

Verworfene Variante "Debounce in einem Runner" (Plan-Review): gleichwertig in der Wirkung, aber
größerer Umbau des bewährten Runners (Ruhefenster, Stop-Verdict im Signal, Lock-Übernahme,
Exit-Race). Die Ersetzungs-Variante hält den Runner fast unverändert und braucht keinen Lock.

### Affected Files (with changes)
| File | Change Type | Description |
|------|-------------|-------------|
| core/hooks/herdr_bridge.py | MODIFY | `maybe_auto_clear`: stop_hook_active-Zweig und Verbrauch beim Spawn raus, Once-Lock raus, Klartext-Vorprüfung; neu `_take_boundary` (atomar unter flock) im Runner vor `/clear`; Abbruchbehandlung: bei "Claude arbeitet weiter" vor `/clear` Token behalten/zurücklegen, sonst verwerfen |
| core/hooks/klartext_gate.py | MODIFY | `main` in reine Funktion `pruefe(payload) -> list[str]` + dünnes `main`; Verhalten unverändert |
| core/hooks/footer_gate.py | MODIFY (klein/keins) | nur falls Payload-Weitergabe nötig; `_discard_boundary` (#497a) bleibt |
| core/commands/40-tdd-red.md, 50-implement.md, 60-validate.md (+ skills/ via sync_skills.py) | MODIFY | Git-Wörter aus Ausgabeblöcken und wörtlichen Fragen entfernen |
| tests/test_autoclear_retry_597.py | CREATE | neue Tests (RED) |
| tests/test_vorlagen_klartext_597.py | CREATE | jeder Ausgabeblock und jede „…“-Frage der Vorlagen durch `klartext_gate.treffer` |
| tests/test_herdr_auto_clear_467.py, test_autoclear_boundary_495.py, test_autoclear_eigene_signale_506.py (+ ggf. 489/497) | MODIFY | Erwartungen an neues Verhalten anpassen (stop_hook_active, Once-Lock, Verbrauchszeitpunkt) |
| CHANGELOG.md | MODIFY | [Unreleased] |

### Scope Assessment
- Files: ~10 (+ generierte skills)
- Estimated LoC: ~+250/-120 (davon ~60 % Tests)
- Risk Level: HIGH (Stop-Hook-Pfad in jedem Projekt; Tipp-Sicherheit bei Berechtigungsdialogen)

### Technical Approach
1. Vorlagen + Vorlagen-Test (schneller Gewinn, beseitigt den beobachteten Auslöser).
2. `klartext_gate.pruefe` extrahieren; `maybe_auto_clear` nutzt sie als Vorprüfung.
3. Token-Modell: kein Verbrauch beim Spawn, kein Once-Lock, `_take_boundary` im Runner, Abbruchregeln.
4. Alte Tests auf neues Verhalten umschreiben, E2E-Szenario R (fremder Stop-Hook blockt einmal,
   Neufassung, danach genau ein `/clear`) in `scripts/e2e_auto_clear.sh` ergänzen (lokal beim PO, nicht CI).

### Risiken
- Tipp-Sicherheit (#506 Szenario P): unverändert, Runner bricht bei jeder Aktivität nach seinem Stop ab.
- Restlücke (wie heute, Known Limitation): fremder Stop-Hook blockt, Claude schreibt ohne Werkzeugaufruf
  länger als `grace` neu → kein Signal; der Klartext-Fall ist durch die Vorprüfung deterministisch abgedeckt.
- Doppeltes Tippen: ausgeschlossen durch atomare Token-Entnahme (flock).
- Plugin-Hooks greifen erst nach Neustart von Claude Code (#599).

### Dependencies
Siehe oben; zusätzlich `fcntl` (nur POSIX, wie bestehende `_pp_flock`).

### Open Questions
- keine (Nebenbefund als #599 ausgelagert)
