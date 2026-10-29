# Context: feat-467-herdr-auto-clear

## Request Summary
Läuft Claude Code in einem Herdr-Pane, soll an Phasengrenzen automatisch `/clear` und danach der nächste Workflow-Befehl (`/<cmd> #N`) eingetippt werden, damit der Kontext klein bleibt. Der State liegt vollständig auf Platte/GitHub; die `#N`-Wiedereinstiege der Commands stellen ihn wieder her.

## PO-Entscheidungen (Intake)
- Voller Prozess
- Opt-in: `herdr.auto_clear.enabled: false` als Default
- Nur `/clear`, kein `/compact`
- Freigaben (`approved`, `go`) bleiben manuell → #468

## Related Files
| File | Relevance |
|------|-----------|
| `core/hooks/herdr_bridge.py` | Basis aus #466: `_pane()`/`_binary()`/`_enabled()`-Gate, `run_herdr(args, wait, timeout)`, `_launch` (Popen detached, DEVNULL, start_new_session) |
| `core/hooks/footer_gate.py` | Stop-Hook bei jedem Turn-Ende. Bekommt `last_assistant_message`, parst die LETZTE ❗Du-Zeile (`_footer_commands`), kennt den erwarteten Befehl (`_expected_command` → `workflow.expected_footer_command`). Pfad „Fußzeile korrekt“ endet in `sys.exit(0)` (Zeile ~205) — natürlicher Auslösepunkt |
| `core/hooks/workflow.py` | `expected_footer_command()`, `next_step()`, `issue_number()` |
| `core/commands/10-context.md`, `20-analyse.md`, `30-write-spec.md`, `40-tdd-red.md`, `50-implement.md` | Checkpoint-Positivblock „✅ **`/clear` ist jetzt gefahrlos**“ nur, wenn alles auf Platte gesichert ist; sonst Negativblock „⚠️ **`/clear` jetzt NICHT**“ |
| `hooks/hooks.json:134` | footer_gate als Stop-Hook registriert |
| `config.yaml` | Abschnitt `herdr:` aus #466 |
| `tests/test_herdr_sidebar_466.py` | Stub-Binary-Muster, conftest-Isolation |

## Herdr-Schnittstelle (Doku im Repo ogulcancelik/herdr, cli-reference.mdx / agent-automation.mdx)
- Target = Pane-ID des Agents (`$HERDR_PANE_ID`), manuell gestartete Agents sind darüber adressierbar
- `herdr agent wait <target> [--until STATUS]... [--timeout MS]` — Default idle|done|blocked; Erfolg JSON auf stdout `.result.agent`, Timeout/Fehler JSON auf stderr, Exit 1
- `herdr agent prompt <target> <text>` — Text + Enter als eine Übergabe (bracketed paste). Bei `blocked` → `agent_blocked`, nichts gesendet. `--wait` nach Prompt aus Nicht-working-State: 5 s Frist bis `working` beobachtet, sonst `agent_prompt_stalled` → für `/clear` (kein sichtbares Arbeiten) ungeeignet
- `idle` und `done` = bereit für Eingabe; `blocked` = Rückfrage-/Freigabe-Dialog; `unknown` = unklar
- Timeout/stalled beweist nicht, dass nichts gesendet wurde
- `herdr notification show <title> --body …` für Vorankündigung

## Existing Patterns
- Fail-open in footer_gate (jede Ausnahme → Exit 0)
- Detached Popen in herdr_bridge (#466)
- Kill-Switch-Muster `<feature>.enabled`

## Dependencies
- Upstream: #466 (`herdr_bridge`), Herdr-CLI ≥ Version mit `agent wait/prompt`
- Downstream: #468 (Autonomie) kann denselben Mechanismus für Freigaben nutzen

## Risks & Considerations
- Fehlauslöser löscht Kontext mitten in Arbeit (Hintergrund-Agent läuft, ℹ️-Zeile) → nur ❗Du-Zeile mit erwartetem Slash-Befehl + Positivblock-Marker
- Doppel-Auslösung (footer_gate läuft mehrfach pro Turn bei Exit-2-Korrektur) → Einmal-Sperre je Workflow+Phase+Befehl
- User tippt gleichzeitig → Text vermischt sich; Mitigation: Vorankündigung + Wartezeit + Recheck des States vor jedem Senden
- `/clear` = neue Session-ID; Session-Register und Herdr-Resume müssen damit umgehen (Herdr-Claude-Integration matcht `SessionStart source=clear`)
- Stop-Hook darf nicht warten → Ablauf in eigenem detachten Prozess
- Herdr nicht real testbar → Stub-Binary

## Analysis

### Type
Feature

### Affected Files (with changes)
| File | Change Type | Description |
|------|-------------|-------------|
| core/hooks/herdr_bridge.py | MODIFY | Strikter Opt-in-Reader `auto_clear` (respektiert `herdr.enabled` als Eltern-Kill-Switch), Marker-Detektor (pure function), Once-Lock, `spawn_auto_clear`, Runner + CLI `python3 herdr_bridge.py auto-clear …` |
| core/hooks/footer_gate.py | MODIFY | Auf dem Pfad „Fußzeile korrekt“ (heute `if not expected or expected in actuals: sys.exit(0)`) fail-open an herdr_bridge delegieren (~12 LoC) |
| config.yaml | MODIFY | `herdr.auto_clear` (enabled false, grace_s 3, idle_timeout_s 120, announce true) |
| tests/test_herdr_auto_clear_467.py | CREATE | Verzweigender Stub (agent wait/prompt/notification), Runner synchron über CLI, Hook-Seite per Subprozess |
| CHANGELOG.md | MODIFY | [Unreleased] |

Keine Änderung an hooks.json (footer_gate ist bereits Stop-Hook), session_singleton_guard, session_banner (ruft `report_active` schon bei jeder source).

### Trigger-Bedingungen (Reihenfolge, alle fail-open → kein Auslösen)
1. `herdr_bridge._pane()` gültig (Env, Pane, Binary, `herdr.enabled`)
2. `herdr.auto_clear.enabled is True` (nur literal True)
3. `stop_hook_active` nicht True
4. Fußzeile korrekt: erwarteter Befehl beginnt mit `/`, ist nicht `/clear`, steht in der letzten ❗Du-Zeile. Vollständiger Befehl inkl. `#N` aus `workflow.expected_footer_command(data)` (footer_gate kürzt auf das erste Wort)
5. Positivmarker `` `/clear` ist jetzt gefahrlos `` (Bold-tolerant) außerhalb von Code-Fences, vor der letzten ❗Du-Zeile; Negativmarker `` `/clear` jetzt NICHT `` irgendwo → kein Auslösen
6. Once-Lock: Schlüssel `workflow|phase|befehl`, worktree-lokal `.claude/herdr_auto_clear_state.json`, Ablauf 10 min; vor Spawn setzen, bei Spawn-Fehler löschen

### Runner (detacht, eigener Prozess, Deadline, immer Exit 0, Log `.claude/herdr_auto_clear.log`)
1. optional `notification show` + `grace_s` warten
2. `agent wait P --until idle --until done --timeout …` → nur Exit 0 und Status idle/done weiter; blocked/unknown/working/Timeout/unparsebar → Abbruch
3. Settle-Delay, State-Recheck (gleiche Phase, gleicher erwarteter Befehl)
4. `agent prompt P /clear` ohne `--wait` (sonst `agent_prompt_stalled`), kein Retry
5. Delay, zweites `agent wait`, State-Recheck
6. `agent prompt P "<befehl #N>"` ohne `--wait`
Delays per CLI-Flags überschreibbar (Tests: 0).

### Scope Assessment
- Files: 4 geändert/neu + Test
- Estimated LoC: +140 Prod / +300 Test
- Risk Level: HIGH (tippt ins Terminal, löscht Kontext) — Opt-in begrenzt

### Risiken (für Spec / Known Limitations)
- Gleichzeitiges Tippen des Users vermischt sich mit gesendetem Text; nur Vorankündigung + Recheck als Mitigation
- Positivmarker ist Modell-Konvention, nicht mechanisch geprüft
- Idle-Race direkt nach Stop (Herdr sieht evtl. noch `working`) → Settle-Delay; nur manuell in echtem Herdr prüfbar
- Kettenlauf Phase 1→2→3 beabsichtigt; Freigaben brechen die Kette, weil der erwartete Schritt kein Slash-Befehl ist
