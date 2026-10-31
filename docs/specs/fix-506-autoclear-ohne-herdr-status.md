---
entity_id: fix-506-autoclear-ohne-herdr-status
type: bugfix
created: 2026-10-31
updated: 2026-10-31
status: draft
version: "1.2"
workflow: fix-506-autoclear-ohne-herdr-status
tags: [herdr, auto-clear, hooks, signals, e2e]
---

# Auto-/clear mit eigenen Plugin-Signalen statt Herdr-Status (Issue #506)

## Approval

- [ ] Approved

## Purpose

Auto-/clear bricht beim PO an Phasengrenzen fast immer ab (24 Abbrueche, 3 Erfolge, Log: `ABBRUCH: wait 1/2: agent wait Exit 1 timed out waiting for agent status`). Der Runner wartet per `herdr agent wait --until idle --until done` auf einen Zustand, den Herdr per lokalem Erkennungs-Manifest (`~/.config/herdr/agent-detection/claude.toml`, Prio 960) klassifiziert: Eine Antwort, die mit `❗ Du: …` endet, gilt als `blocked`. Genau diese Zeile verlangt das Plugin an jeder Phasengrenze, also wird Herdr dort nie `idle`. Statt Herdrs Heuristik zu umgehen, nutzt das Plugin kuenftig eigene, vom Plugin selbst erzeugte Signale (Hook-Marker je Pane); Herdr wird nur noch als "Tastatur" benutzt (`pane send-text` + `pane send-keys … enter`); `agent wait`, jede Statusabfrage und jeder `agent`-Befehl entfallen. Beleg am echten Herdr 0.9.5 (E2E Szenario G mit PO-Manifest): `herdr agent prompt` lehnt ab, solange der Pane `blocked` ist (`{"error":{"code":"agent_blocked",...}}`, Runner-Log `ABBRUCH: agent prompt '/clear' Exit 1`), weil Herdr die Eingabe bei `blocked` nicht sendet. `pane send-text` gefolgt von `pane send-keys enter` tippt dagegen zuverlaessig (real: `❯ /clear`, `SessionStart:clear`, Marker geschrieben). Wichtig (Adversary R1): Der Stop-Hook ist nicht zwingend das Turn-Ende. Blockt ein ANDERER Stop-Hook (`decision: block`), setzt Claude den Turn fort, ohne dass `UserPromptSubmit` feuert; oeffnet sich dabei ein Berechtigungsdialog, wuerde ein blind getipptes Enter ihn bestaetigen (Beleg: `docs/artifacts/fix-506-autoclear-ohne-herdr-status/adversary-probe-P-stophook-permission.txt`, Dialog `1. Yes` vom Runner bestaetigt). Deshalb erzeugt das Plugin zusaetzlich zu den Eingabe- und SessionStart-Markern eigene Aktivitaets- und Stop-Marker; jede Aktivitaet von Claude hinterlaesst ein Hook-Signal, das das Plugin selbst schreibt, und der Runner tippt nur, wenn seit dem Stop-Zeitpunkt keines davon eintraf.

## Source

- **File:** `core/hooks/herdr_bridge.py` (Runner, Marker-API), `core/hooks/phase_listener.py` (UserPromptSubmit-Marker), `core/hooks/session_banner.py` (SessionStart-Marker), `core/hooks/session_singleton_guard.py` (PreToolUse-Aktivitaets-Marker), `core/hooks/footer_gate.py` (Stop-Marker), `hooks/hooks.json` (Notification/PermissionRequest)
- **Identifier:** `_Runner` (`_wait_ready` entfaellt, `run`, `__init__`, neu `_check_activity`), `_ac_base`, `AC_DEFAULTS`, `READY_STATES`, neu `record_signal(kind, source=None, cwd=None)`, neu CLI-Modus `herdr_bridge.py signal <kind>`, `_parse_since`; `phase_listener.main`; `session_banner.main`; `session_singleton_guard` (Modus `guard`); `footer_gate.main`

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `core/hooks/herdr_bridge.py` (#467/#495/#497/#499) | module | `_Runner`, `_recheck`, Once-Lock, `/99-reset`-Sperre (`MANUAL_COMMANDS`), `resolve_command_form`, `_ac_log`, `_ac_base` bleiben; nur das Warten wird ersetzt |
| `core/hooks/hook_utils.py` | module | `atomic_write_json`, `read_state_json`, `framework_disabled` |
| `hooks/hooks.json` | config | Reihenfolge SessionStart (`session_singleton_guard register` vor `session_banner`), PreToolUse (`session_singleton_guard guard` zuerst, Matcher `""`), UserPromptSubmit (`phase_listener`) und Stop (`footer_gate`) bleibt; neu nur Eintraege fuer `Notification` (Matcher `permission_prompt`) und `PermissionRequest` mit `herdr_bridge.py signal activity` (siehe Implementation Details) |
| `core/hooks/session_singleton_guard.py`, `core/hooks/footer_gate.py` | modules | schreiben je einen Marker (Aktivitaet bzw. Stop) ueber `herdr_bridge.record_signal`; `footer_gate` nutzt `hook_utils.adopt_payload_cwd` bereits |
| `tests/test_herdr_auto_clear_467.py`, `test_auto_clear_global_480.py`, `test_herdr_plan_deploy_sessionstart_478.py` | tests | Stub-Herdr beantwortet `agent wait`/`agent prompt`; Stub und Erwartungen auf `pane send-text`/`pane send-keys` anpassen |
| `scripts/e2e_auto_clear.sh` (#495/#497/#499) | script | echter E2E mit Herdr 0.9.5, Claude-TUI und Plugin |
| Herdr 0.9.5 (`pane send-text`, `pane send-keys`, Erkennungs-Manifest-Format) | extern | nur noch Tippen (Tastatur); `agent prompt` scheidet aus (lehnt bei `blocked` ab); Manifestformat fuer Szenario G am echten Binary belegt |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| core/hooks/herdr_bridge.py | MODIFY | `record_signal(kind, source, cwd)` (Marker input/session/activity/stop schreiben, fail-open, Basis aus Payload-cwd); leichter CLI-Modus `signal activity`; `_Runner`: `_wait_ready` entfernt, neu Fortsetzungs-Pruefung (input/activity/stop) nach grace und unmittelbar vor jedem Tippen (vor `/clear` relativ zu `since`, vor Folgebefehl relativ zu `t_clear` + Toleranz) und Warten auf SessionStart-`clear`; Tippen per `pane send-text` + `pane send-keys enter` statt `agent prompt`; `--since` nur endlich und nicht in der Zukunft; Spawner (`maybe_auto_clear`) uebergibt `--since <epoch>`; Budget/Docstring angepasst; `READY_STATES` entfernt, falls ungenutzt |
| core/hooks/phase_listener.py | MODIFY | Am Anfang von `main` (nach `framework_disabled`) `record_signal("input")`, eine Zeile, `try/except`, ohne Ausgabe |
| core/hooks/session_banner.py | MODIFY | Am Anfang von `main` (nach `framework_disabled`, vor Wartung/Git-Sync) `record_signal("session", source, cwd=<Payload-cwd>)` |
| core/hooks/session_singleton_guard.py | MODIFY | Modus `guard` (PreToolUse, alle Tools): als allererste Handlung nach dem Payload-Parsen `record_signal("activity", "pretooluse", cwd=<Payload-cwd>)`, vor jeder Pruefung und jedem Blockieren; still, fail-open |
| core/hooks/footer_gate.py | MODIFY | `main`: unmittelbar nach `adopt_payload_cwd(payload)` und vor allen Ausgaengen (`stop_hook_active`, `framework_disabled`, Fusszeilen-Fehler, Block, Erfolg) `record_signal("stop")`; vor der `since`-Bildung in `maybe_auto_clear` |
| hooks/hooks.json | MODIFY | Eintraege `Notification` (Matcher `permission_prompt`) und `PermissionRequest`: `${CLAUDE_PLUGIN_ROOT}/core/hooks/herdr_bridge.py signal activity`, Timeout 5; entfaellt (mit Begruendung im CHANGELOG), falls ein Event in der installierten Claude-Code-Doku nicht existiert |
| tests/test_autoclear_eigene_signale_506.py | CREATE | Tests zu AC-1 bis AC-22 |
| tests/test_herdr_auto_clear_467.py, tests/test_auto_clear_global_480.py, tests/test_herdr_plan_deploy_sessionstart_478.py | MODIFY | Stub: kein `agent wait`/`agent prompt` mehr; `pane send-text <pane> /clear` gefolgt von `pane send-keys <pane> enter` im Stub schreibt den SessionStart-Marker; Erwartungssequenz `send-text`, `send-keys`, `send-text`, `send-keys`; `test_runner_reads_real_agent_status_field` entfaellt bzw. wird durch AC-1 ersetzt |
| scripts/e2e_auto_clear.sh | MODIFY | Szenario G (PO-Manifest nachgebaut) samt Gegenprobe G0 (alter Code), Szenario H (Eingabe in der Grace-Zeit), Szenario P (blockierender fremder Stop-Hook + Berechtigungsdialog), Szenario Q (Turn laeuft per `sleep 12` weiter); `H agent wait` der bestehenden Szenarien durch Pane-Text-Polling ersetzen |
| CHANGELOG.md | MODIFY | Eintrag unter [Unreleased] / Fixed (#506) |

### Estimated Changes

- Files: 1 neu, 11 geaendert
- LoC: +150/-50 Produktion, +420 Test, +150 E2E-Skript
- Risk Level: MEDIUM (Auto-/clear laeuft nur mit Herdr und Opt-in; fuenf Hooks bekommen einen Schreibzugriff, der strikt fail-open, ohne Ausgabe und ohne messbare Verzoegerung bleibt; der PreToolUse-Hook laeuft bei jedem Tool-Aufruf)

## Implementation Details

**Marker.** `herdr_bridge.record_signal(kind, source=None, cwd=None)`: tut nichts, wenn `HERDR_ENV != "1"` oder `HERDR_PANE_ID` leer ist; der Import von `herdr_bridge` in den Hooks erfolgt erst nach dieser Env-Pruefung. Vier Dateien je Pane unter `_ac_base()/.claude/herdr_signals/` (je Art eine eigene Datei, damit nie Lesen-Aendern-Schreiben auf derselben Datei noetig ist):
- `<pane>.input.json` `{"at": <time.time()>}` (UserPromptSubmit)
- `<pane>.session.json` `{"source": "<clear|startup|resume|compact>", "at": ...}` (SessionStart)
- `<pane>.activity.json` `{"kind": "<pretooluse|notification|permission>", "at": ...}` (Claude arbeitet: Tool-Aufruf, Berechtigungsdialog)
- `<pane>.stop.json` `{"at": ...}` (Stop-Hook lief)

Die Pane-Id wird fuer den Dateinamen auf `[A-Za-z0-9_.-]` reduziert. Schreiben per `hook_utils.atomic_write_json`; jede Ausnahme wird verschluckt, nichts geht auf stdout/stderr, kein `sleep`, kein Subprozess. Die Wanduhr (`time.time()`) ist gewollt: Hook und Runner sind verschiedene Prozesse auf demselben Rechner.

**Marker-Basis (Payload-cwd).** `_ac_base()` entscheidet ueber das Arbeitsverzeichnis. Der Spawner (`maybe_auto_clear` im Stop-Hook) laeuft nach `adopt_payload_cwd(payload)` und startet den Runner mit diesem Ordner; die Marker muessen im selben Ordner liegen, sonst liest der Runner leere Ordner und tippt blind. Darum uebergeben alle Schreiber das Payload-`cwd`: `footer_gate` und der CLI-Modus rufen `adopt_payload_cwd` (wie `footer_gate` heute), `phase_listener`, `session_banner` und `session_singleton_guard guard` uebergeben `cwd=payload.get("cwd")` an `record_signal`, das die Basis mit derselben Funktion wie der Spawner fuer dieses Verzeichnis ermittelt, ohne den Prozess-cwd der Hooks zu aendern. Fehlt `cwd` im Payload oder existiert das Verzeichnis nicht, gilt der Prozess-cwd (Verhalten wie bisher).

**Hook-Stellen.**
- `phase_listener.main`: unmittelbar nach `framework_disabled()`, vor der Nachrichtenauswertung: `record_signal("input")` (auch injizierte Notification-Turns zaehlen als Eingabe; Abbruch ist die sichere Seite).
- `session_banner.main`: vor `build_output`, weil Wartung und Haupt-Ordner-Sync Sekunden dauern koennen und der Runner auf dieses Signal wartet; `source` aus dem Payload.
- `session_singleton_guard.py guard` (PreToolUse, Matcher `""`, damit fuer jedes Tool): `record_signal("activity", "pretooluse")` als erste Handlung nach dem Payload-Parsen, vor allen Pruefungen und vor jedem Block. PreToolUse laeuft vor dem Berechtigungsdialog des Tool-Aufrufs, das Signal liegt also bereits vor, bevor ein Dialog auf dem Bildschirm steht. Ohne `HERDR_PANE_ID` ein reiner Env-Check (keine Datei, kein Import); mit Pane-Id ein atomarer Mini-Write (keine Verzoegerung ueber die Schreibzeit hinaus, kein Subprozess, kein `sleep`).
- `footer_gate.main` (Stop): `record_signal("stop")` unmittelbar nach `adopt_payload_cwd(payload)` und VOR allen Ausgaengen, also auch bei `stop_hook_active`, bei ausgeschaltetem Framework, bei Fusszeilen-Fehler, bei Block (Exit 2) und bei Erfolg. Das Schreiben erfolgt vor der `since`-Bildung des Spawners; der eigene Stop hat daher `at <= since` und loest die Pruefung nicht selbst aus. Jeder weitere Stop (ein blockierender fremder Hook setzt den Turn fort und endet in einem neuen Stop) liefert ein neues `at > since`.
- Notification/PermissionRequest: Claude Code kennt laut Hooks-Referenz die Ereignisse `Notification` (u. a. `permission_prompt`, `idle_prompt`) und `PermissionRequest`. In `hooks/hooks.json` neu: `Notification` mit Matcher `permission_prompt` (bewusst NICHT `idle_prompt`: die Leerlauf-Meldung kommt nach dem Stop und wuerde sonst jeden Lauf faelschlich abbrechen) und `PermissionRequest`, beide mit `herdr_bridge.py signal activity`. Dieser leichte Modus liest den Payload von stdin, nimmt dessen `cwd`, schreibt `record_signal("activity", <notification|permission>)`, gibt nichts aus, endet mit Exit 0, importiert nichts ausser `herdr_bridge` und `hook_utils` und startet keine Subprozesse. Das ist der Gurt zum Hosenträger PreToolUse (Dialoge, die nicht aus einem Tool-Aufruf stammen). Vor der Umsetzung prueft der Entwickler die Ereignisnamen und Matcher gegen die Claude-Code-Doku; existiert eines nicht, wird dessen Eintrag weggelassen und die Auslassung im CHANGELOG begruendet (PreToolUse deckt Tool-Dialoge unabhaengig davon ab).

**Referenzzeitpunkt und `--since`.** Massgeblich fuer "weitergemacht seit…" ist der Zeitpunkt des Stop-Hooks, nicht der Runner-Start: `maybe_auto_clear` nimmt `since = time.time()` (nach dem Stop-Marker) und uebergibt ihn dem Runner als `--since <epoch>`. Das schliesst die ~100-ms-Luecke zwischen Stop-Hook und Runner-Start. `_parse_since(value, now)` akzeptiert nur Werte, die sich als Float parsen lassen, endlich sind (kein `nan`, `inf`) und nicht in der Zukunft liegen (`<= now + 5 s`); sonst und bei fehlendem `--since` gilt der Runner-Start, mit Vermerk im Log. Verhindert, dass `--since nan` (alle Vergleiche falsch, Pruefung blind) oder ein Zukunftswert (alle echten Marker "zu alt") die Pruefung aushebelt.

**Tippen.** Der Runner tippt ausschliesslich per `herdr pane send-text <pane> <text>`, gefolgt von `herdr pane send-keys <pane> enter`; beide Aufrufe muessen Exit 0 liefern, sonst `_Abort` (`ABBRUCH`). Kein `agent prompt` (lehnt bei `blocked` mit `agent_blocked` ab), kein `agent wait`, keine Statusabfrage, kein `agent`-Befehl: Herdr dient nur noch als Tastatur.

**Fortsetzungs-Pruefung (`_check_activity(ref)`).** Liest im Marker-Verzeichnis des eigenen Panes `input`, `activity` und `stop` (fremde Panes ignoriert, fehlende oder unlesbare Datei = kein Signal). Ist bei einer dieser Dateien `at > ref`: `input` -> `_Abort("Nutzer hat weitergeschrieben")`, `activity`/`stop` -> `_Abort("Claude arbeitet weiter")`; der Grund nennt die Art und die Zeitdifferenz.

**Runner (`_Runner.run`).** `since` aus `_parse_since`. Ablauf:
1. `/99-reset`-Sperre (unveraendert), Ankuendigung, Grace-Pause.
2. `_check_activity(since)` nach der Grace-Zeit.
3. settle, `_recheck("vor /clear")`, `_check_activity(since)` ein zweites Mal unmittelbar vor dem Tippen, dann `t_clear = time.time()` und `pane send-text /clear` + `pane send-keys enter`.
4. Warten (Poll alle 0,2 s, hoechstens `idle_timeout_s`) auf `<pane>.session.json` mit `source == "clear"` und `at >= t_clear`. Ein aelterer Marker zaehlt nicht. Zeitablauf -> `_Abort("nach /clear: kein SessionStart(clear)")`, kein Folgebefehl.
5. settle, `_recheck("vor Folgebefehl")`, `_check_activity(t_clear + AC_CLEAR_TOLERANCE_S)` unmittelbar vor dem Tippen (Konstante, 2,0 s: deckt den eigenen SessionStart und ein moegliches UserPromptSubmit des getippten `/clear` ab), dann `pane send-text <resolve_command_form(command)>` + `pane send-keys enter`. Auch waehrend des Wartens aus Schritt 4 wird `_check_activity(t_clear + AC_CLEAR_TOLERANCE_S)` je Poll-Durchlauf geprueft, damit eine Fortsetzung nach dem `/clear` den Folgebefehl nicht trifft.

Der Config-Schluessel `idle_timeout_s` und das CLI-Argument `--idle-timeout` bleiben (Frist fuer das Eintreffen des `/clear`-Signals); neue interne Runner-Option ist nur `--since`, keine neue Konfiguration. Das Gesamt-Budget enthaelt nur noch eine Wartephase. Once-Lock, `_recheck`, Vermerk, Log-Tag und `/99-reset`-Sperre bleiben unveraendert. Zur Berechtigungsdialog-Frage: Der Runner startet im Stop-Hook, aber ein Stop ist nicht zwingend das Turn-Ende (blockender fremder Stop-Hook, `decision: block`). Dann setzt Claude den Turn fort; jeder Tool-Aufruf schreibt per PreToolUse (vor einem Dialog) ein Aktivitaets-Signal, jeder weitere Stop ein Stop-Signal, und der Runner bricht ab, statt in den Dialog zu tippen.

**Nachtrag Adversary R2 (AMBIGUOUS, F001-F003, PO-Auftrag).**
- F001: Default `grace_s` (`AC_DEFAULTS`, Template `config.yaml`) von 3 auf 10 s. Fremde Stop-Hooks laufen parallel zu `footer_gate` und erzeugen waehrend ihrer Laufzeit kein Signal; blockt einer erst nach laengerer Laufzeit, kommt die Fortsetzung (PreToolUse/Stop) erst danach. Mit 10 s + settle 2 s deckt der Default fremde Stop-Hooks bis etwa 8 s plus Modell-Latenz bis zum ersten Tool-Aufruf ab (E2E S: Block nach 8,0 s, PreToolUse nach 9,9 s, Abbruch bei der Pruefung nach grace). Nach `/clear` und vor dem Folgebefehl wird wie bisher geprueft.
- F002: `_prompt(text, ref, label, own_clear)` prueft zwischen `pane send-text` und `pane send-keys enter` erneut `_check_activity`. Bei Abbruch loescht `pane send-keys <pane> ctrl+u` (`AC_CLEAR_KEY`) die Eingabezeile und nichts wird abgeschickt; Log `… [zwischen Text und Enter, Zeile geloescht]`. Key-Name am echten Herdr 0.9.5 belegt: `ctrl+u` (und `ctrl+U`) Exit 0, `ctrl-u`/`C-u` -> `invalid_key`; im Claude-TUI leert `ctrl+u` die Zeile `❯ /clear` bzw. `❯ /agent-os-openspec:50-implement #506`.
- F003: Zusaetzlicher SessionEnd-Eintrag in `hooks/hooks.json` direkt nach `plan-pane-close`: `herdr_bridge.py signal activity` (timeout 2) schreibt `activity` mit `kind=session_end` und `reason` aus dem Payload. `_check_activity` bricht bei `session_end` ab ("Sitzung beendet"), nach dem eigenen `/clear` (`own_clear=True`, Warten und Folgebefehl) ausser bei `reason=clear` (SessionEnd des eigenen `/clear`). Ein `session`-Marker mit `source != clear` und `at > ref` (Claude im Pane neu gestartet/fortgesetzt) bricht ebenfalls ab ("Sitzung neu gestartet").

**E2E.** Szenario G: wie A (Testdouble `20-analyse`), aber der Test-Herdr bekommt `$XDG_CONFIG_HOME/herdr/agent-detection/claude.toml` mit den PO-Regeln (Antwort endet mit `❗ Du:` -> `blocked`, `ℹ️ Nichts zu tun` -> `working`, Prio 960). Das Format wird am echten 0.9.5 belegt (Herdr-Doku bzw. `agent explain`), nicht geraten; ein Vorab-Check im Skript bestaetigt, dass die Regel greift (`blocked`). Erwartung: Log `OK`, im TUI `❯ /clear` und `❯ /20-analyse #999`. Gegenprobe G0: dasselbe Szenario mit dem Code von `origin/main` (Worktree, `--plugin-dir`) muss mit `ABBRUCH: wait 1` enden. Szenario H: wie A mit `grace_s` 25; waehrend der Grace-Zeit sendet das Skript einen neuen Prompt; erwartet: Log `ABBRUCH` mit "Nutzer hat weitergeschrieben", kein `❯ /clear` danach. Szenario P: wie A plus ein Projekt-Stop-Hook, der genau einmal blockt (`decision: block`, Grund: "lege <W>/PERM-PROBE-FILE per Bash an"), sodass Claude den Turn fortsetzt und einen Bash-Berechtigungsdialog oeffnet (Projektregeln erzwingen Nachfrage), `grace_s` gross genug, dass der Tool-Aufruf davor liegt; erwartet: Log `ABBRUCH` mit "Claude arbeitet weiter", der Runner sendet weder Enter noch `/clear`, der Dialog bleibt offen und `<W>/PERM-PROBE-FILE` wird NICHT angelegt (Skript wartet nach dem Abbruch und prueft das Fehlen der Datei, bevor es den Dialog selbst mit Escape schliesst). Szenario Q: wie A, aber ein fremder Stop-Hook setzt den Turn fort, und Claude fuehrt `sleep 12` per Bash aus (mit Rueckfrage-freier Erlaubnis); `grace_s` kuerzer als 12 s und laenger als die Latenz bis zum Tool-Aufruf; erwartet: Log `ABBRUCH` mit "Claude arbeitet weiter", kein `❯ /clear` im TUI, solange der Turn laeuft. Bestehende `herdr agent wait`-Aufrufe des Skripts dienen nur als Testhilfe und werden, wo sie im Manifest-Szenario haengen wuerden, durch Polling auf den Pane-Text ersetzt. A'-D und F laufen unveraendert.

## Expected Behavior

- **Input:** Auto-/clear ist aktiv, ein Grenz-Phasenwechsel hat einen Vermerk gesetzt, die Antwort endet mit `❗ Du: /<naechster> #N`, Herdr klassifiziert den Pane als `blocked`
- **Output:** Nach der Grace-Zeit tippt der Runner (`pane send-text` + `pane send-keys enter`) `/clear`, wartet auf das SessionStart(clear)-Signal des Plugins und tippt dann den Folgebefehl; Herdrs Agent-Status spielt keine Rolle
- **Abbruch statt Tippen:** Hat seit dem Stop-Zeitpunkt eine Eingabe, eine Aktivitaet (Tool-Aufruf, Berechtigungsdialog) oder ein weiterer Stop stattgefunden, tippt der Runner nichts (weder `/clear` noch Enter noch Folgebefehl)
- **Side effects:** Dateien unter `.claude/herdr_signals/` (input, session, activity, stop); Runner-Log wie bisher; Abbruchgruende "Nutzer hat weitergeschrieben", "Claude arbeitet weiter", "kein SessionStart(clear)" und "pane send-text/send-keys Exit N" im Log

## Known Limitations

- Hat der Nutzer in der Grace-Zeit Text getippt, aber nicht abgeschickt, erkennt das Plugin das nicht (es sieht nur abgeschickte Prompts); der Text wuerde mit `/clear` vermischt. Das Zeitfenster dafuer ist mit grace 10 s (+ settle) laenger als frueher (~12 s statt ~5 s). Kommt genau zwischen `send-text` und dem Recheck ein Signal, loescht `ctrl+u` die ganze Zeile einschliesslich dieses nicht abgeschickten Nutzertexts.
- Eingaben nach dem getippten `/clear`, aber vor dem Folgebefehl, werden nicht erkannt (unklar, ob `/clear` einen UserPromptSubmit ausloest; eine Pruefung koennte das Verfahren faelschlich immer abbrechen).
- Die Marker-Dateien je Pane werden nicht aufgeraeumt (wenige Bytes je Pane); bei Herdr-Pane-Wiederverwendung gilt der letzte Stand, die Zeitvergleiche gegen `spawn_at`/`t_clear` machen aeltere Staende wirkungslos.
- Die Hooks schreiben in jedem Herdr-Pane Marker, auch bei ausgeschaltetem Auto-/clear (billig, ohne Konfigurationszugriff); der PreToolUse-Hook schreibt bei jedem Tool-Aufruf eine kleine Datei (atomar, wenige Bytes).
- Setzt ein blockierender Stop-Hook den Turn fort und Claude antwortet NUR mit Text, ohne Tool-Aufruf, und endet dieser Turn erst nach Ablauf von grace + settle, entsteht weder ein Aktivitaets- noch (vor dessen Ende) ein Stop-Signal; der Runner wuerde dann `/clear` in den laufenden Turn tippen. Das Plugin sieht keine Token-Ausgabe. Eine reine Text-Fortsetzung ist ueblicherweise kuerzer als die Grace-Zeit; ein weiterer Stop am Ende wird erkannt, falls er vor dem Tippen eintrifft.
- Berechtigungsdialoge, die nicht aus einem Tool-Aufruf stammen und fuer die Claude Code kein `Notification`/`PermissionRequest` liefert, sind nur ueber das nachgelagerte Stop-Signal erkennbar.
- Das Fenster `AC_CLEAR_TOLERANCE_S` (2 s nach dem getippten `/clear`) ignoriert Signale, die in dieser Zeit eintreffen; echte Eingabe in genau diesem Fenster wird nicht erkannt.
- Echtes TUI-/Manifest-Verhalten ist nur im realen Herdr pruefbar.
- Fremde Stop-Hooks, die laenger als grace + settle (Default 10 + 2 s) laufen und DANN blocken (oder deren Fortsetzung den ersten Tool-Aufruf erst danach macht), erzeugen bis dahin kein Signal; der Runner tippt `/clear` dann in den noch laufenden Turn, Claude reiht es ein und fuehrt es nach der Fortsetzung aus (Adversary R2, S2). Ein Berechtigungsdialog wird dabei nicht bestaetigt (R2, S). Abhilfe im Projekt: `herdr.auto_clear.grace_s` groesser als die Laufzeit der eigenen Stop-Hooks setzen. Ein Hook-Event "alle Stop-Hooks fertig" gibt es nicht.
- Zwischen der Pruefung nach `send-text` und dem Enter liegt weiterhin ein Herdr-Aufruf (wenige ms); entsteht genau darin ein Dialog, wird er nicht erkannt. Die Zeile wird per `ctrl+u` geloescht, Claude-Code-Tastenbelegung vorausgesetzt.
- Beendet der Nutzer Claude ohne SessionEnd-Hook (Absturz, `kill -9`), entsteht kein Marker; der Runner tippt dann ggf. in die Shell.

## Definition of Done

Fertig ist diese Aenderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt (AC-12 durch das E2E-Skript)
- [ ] E2E G gruen mit neuem Code und G0 scheitert mit altem Code; H, P, Q, A'-D, F gruen; Belege (Log, Pane-Auszug, Fehlen von `PERM-PROBE-FILE`) liegen vor
- [ ] Regressionslauf gruen, insbesondere #467-/#478-/#480-/#495-/#497-/#499-Tests

## Acceptance Criteria

- **AC-1:** Given ein Stub-Herdr, der jeden Aufruf protokolliert / When der Runner einen vollstaendigen Lauf macht / Then enthaelt das Protokoll keinen `agent wait` und keinen `agent prompt`; getippt wird per `pane send-text` (`/clear`, dann Folgebefehl) jeweils gefolgt von `pane send-keys … enter`
  - Test: tests/test_autoclear_eigene_signale_506.py::test_runner_never_calls_agent_wait

- **AC-2:** Given eine Eingabe-Marke mit `at` nach dem Stop-Hook-Zeitpunkt `--since` (Nutzer schreibt in der Grace-Zeit weiter) / When der Runner vor `/clear` prueft / Then Abbruch "Nutzer hat weitergeschrieben", weder `/clear` noch Folgebefehl getippt (kein `pane send-text`/`send-keys`)
  - Test: tests/test_autoclear_eigene_signale_506.py::test_new_input_since_spawn_aborts_without_typing

- **AC-3:** Given keine oder nur aeltere Eingabe-Marke (`at <= since`) / When der Runner prueft / Then wird `/clear` per `pane send-text` + `pane send-keys enter` getippt
  - Test: tests/test_autoclear_eigene_signale_506.py::test_no_new_input_types_clear

- **AC-4:** Given ein SessionStart-Marker `source=clear` nach dem eigenen `/clear` / When der Runner wartet / Then tippt er nach settle und `_recheck` den Folgebefehl
  - Test: tests/test_autoclear_eigene_signale_506.py::test_session_clear_after_own_clear_types_followup

- **AC-5:** Given der SessionStart-Marker bleibt bis `idle_timeout_s` aus / When die Frist ablaeuft / Then Abbruch im Log, Folgebefehl nicht getippt
  - Test: tests/test_autoclear_eigene_signale_506.py::test_missing_session_signal_aborts_without_followup

- **AC-6:** Given ein SessionStart(clear)-Marker, dessen `at` vor dem eigenen `/clear` liegt, oder `source` ist nicht `clear` / When der Runner wartet / Then zaehlt er nicht (Abbruch nach Frist, kein Folgebefehl)
  - Test: tests/test_autoclear_eigene_signale_506.py::test_session_start_before_own_clear_does_not_count

- **AC-7:** Given Marker fuer ein fremdes Pane (andere `HERDR_PANE_ID`) / When der Runner prueft und wartet / Then beeinflussen sie weder die Eingabe-Pruefung noch das Warten
  - Test: tests/test_autoclear_eigene_signale_506.py::test_markers_are_per_pane

- **AC-8:** Given `HERDR_PANE_ID` fehlt oder `HERDR_ENV != "1"` / When `phase_listener.py` und `session_banner.py` als Hook laufen / Then entsteht keine Datei unter `.claude/herdr_signals/`; mit gesetztem Pane schreiben sie `<pane>.input.json` bzw. `<pane>.session.json` (`source` aus dem Payload)
  - Test: tests/test_autoclear_eigene_signale_506.py::test_hooks_write_marker_only_with_pane_id

- **AC-9:** Given ein nicht schreibbares Markerverzeichnis oder ungueltige Daten / When die Hooks laufen / Then kein Fehler, kein Exit-Code ungleich 0, keine Ausgabe auf stdout/stderr durch das Marker-Schreiben, und der uebrige Hook-Ablauf bleibt unveraendert
  - Test: tests/test_autoclear_eigene_signale_506.py::test_marker_write_is_fail_open_and_silent

- **AC-10:** Given Folgebefehl `/99-reset #N`, bereits gesetzter Once-Lock bzw. geaenderte Phase/erwarteter Befehl / When `maybe_auto_clear` bzw. der Runner laeuft / Then verhalten sie sich wie vor der Aenderung (kein Spawn bzw. Abbruch, `_recheck` vor `/clear` und vor dem Folgebefehl)
  - Test: tests/test_autoclear_eigene_signale_506.py::test_manual_lock_and_recheck_unchanged

- **AC-11:** Given die angepassten Bestandstests / When `pytest tests/test_herdr_auto_clear_467.py tests/test_auto_clear_global_480.py tests/test_herdr_plan_deploy_sessionstart_478.py tests/test_autoclear_boundary_495.py tests/test_autoclear_transition_497.py tests/test_befehlsform_context_titel_499.py` laufen / Then sind sie gruen
  - Test: Regressionslauf `pytest tests/`

- **AC-14:** Given eine Eingabe-Marke mit `at` zwischen Stop-Hook-Zeitpunkt (`--since`) und Runner-Start / When der Runner vor `/clear` prueft / Then wird sie als neue Eingabe erkannt: Abbruch "Nutzer hat weitergeschrieben", nichts getippt (die ~100-ms-Luecke ist geschlossen); ohne `--since` gilt der Runner-Start als Referenz
  - Test: tests/test_autoclear_eigene_signale_506.py::test_input_between_stop_and_runner_start_aborts

- **AC-12:** Given echtes Herdr 0.9.5 mit nachgebautem PO-Manifest (`❗ Du:` -> `blocked`; `agent prompt` wuerde hier mit `agent_blocked` abgelehnt) und Claude-TUI / When Szenario G laeuft / Then Log `OK` (getippt per `pane send-text` + `pane send-keys enter`) und im TUI `❯ /clear` und `❯ /20-analyse #999`; die Gegenprobe G0 mit dem Code von `origin/main` endet mit `ABBRUCH: wait 1`
  - Test: scripts/e2e_auto_clear.sh (ONLY="G G0")

- **AC-13:** Given echtes Herdr und Szenario H (Nutzer schickt in der Grace-Zeit einen neuen Prompt) / When der Runner prueft / Then Log `ABBRUCH` mit "Nutzer hat weitergeschrieben" und kein `❯ /clear`; Szenarien A'-D und F bleiben gruen
  - Test: scripts/e2e_auto_clear.sh (ONLY="H A B C D F")

- **AC-15:** Given eine Aktivitaets-Marke (`activity.json`) mit `at > since`, auch wenn sie erst waehrend settle/`_recheck` entsteht, bzw. ein `activity`-Marker mit `at` nach `t_clear + AC_CLEAR_TOLERANCE_S` / When der Runner nach grace, unmittelbar vor `/clear` oder unmittelbar vor dem Folgebefehl prueft / Then Abbruch "Claude arbeitet weiter"; im ersten und zweiten Fall wird nichts getippt (kein `send-text`, kein `send-keys`), im dritten ist `/clear` getippt, der Folgebefehl nicht; ein `activity`-Marker innerhalb der Toleranz (`at <= t_clear + AC_CLEAR_TOLERANCE_S`) oder mit `at <= since` zaehlt nicht
  - Test: tests/test_autoclear_eigene_signale_506.py::test_activity_after_since_aborts_without_typing

- **AC-16:** Given ein weiterer Stop (`stop.json` mit `at > since`) bzw. nach `t_clear + AC_CLEAR_TOLERANCE_S` / When der Runner vor `/clear` bzw. vor dem Folgebefehl prueft / Then Abbruch "Claude arbeitet weiter", vor `/clear` ohne jedes Tippen, vor dem Folgebefehl ohne Folgebefehl; der eigene Stop (`at <= since`) loest keinen Abbruch aus
  - Test: tests/test_autoclear_eigene_signale_506.py::test_second_stop_after_since_aborts

- **AC-17:** Given ein Eingabe-, Aktivitaets- oder Stop-Marker nach `t_clear + AC_CLEAR_TOLERANCE_S`, der waehrend des Wartens auf SessionStart(clear) eintrifft / When der Runner wartet / Then Abbruch ohne Folgebefehl, auch wenn der SessionStart(clear)-Marker anschliessend eintrifft
  - Test: tests/test_autoclear_eigene_signale_506.py::test_activity_during_wait_for_clear_prevents_followup

- **AC-18:** Given `HERDR_ENV=1` und `HERDR_PANE_ID` gesetzt / When `session_singleton_guard.py guard` als PreToolUse-Hook laeuft (auch wenn der Guard den Aufruf anschliessend blockt) / Then liegt danach `<pane>.activity.json` mit `kind=pretooluse` und `at` im Basisordner des Payload-`cwd` vor, ohne Ausgabe auf stdout/stderr durch das Schreiben, mit unveraendertem Exit-Code und Block-Verhalten des Guards; ohne Pane-Id oder bei nicht schreibbarem Verzeichnis entsteht nichts und der Hook bleibt fail-open; der Marker-Write dauert pro Aufruf unter 50 ms (kein Subprozess, kein `sleep`)
  - Test: tests/test_autoclear_eigene_signale_506.py::test_pretooluse_guard_writes_activity_marker_silently

- **AC-19:** Given `hooks/hooks.json` / When geladen / Then enthaelt sie Eintraege `Notification` (Matcher `permission_prompt`, nicht `idle_prompt`) und `PermissionRequest` mit `herdr_bridge.py signal activity` (oder, falls ein Event laut Claude-Code-Doku nicht existiert, fehlt dessen Eintrag mit Begruendung im CHANGELOG); der Modus `signal activity` schreibt mit Pane-Id `<pane>.activity.json` (`kind` notification bzw. permission) im Payload-`cwd`, gibt nichts aus, endet mit Exit 0 und tut ohne Pane-Id oder bei ungueltigem Payload nichts
  - Test: tests/test_autoclear_eigene_signale_506.py::test_signal_activity_cli_and_hooks_json_registration

- **AC-20:** Given `HERDR_PANE_ID` gesetzt / When `footer_gate.py` laeuft auf jedem Pfad (`stop_hook_active`, Framework ausgeschaltet, Fusszeile fehlerhaft/Block mit Exit 2, Fusszeile ok) / Then liegt `<pane>.stop.json` mit aktuellem `at` vor, geschrieben vor der Ausgabe bzw. dem Exit; der Marker-Fehler (nicht schreibbar) aendert Exit-Code und Ausgabe des Gates nicht; `maybe_auto_clear` bildet `since` nach dem Stop-Marker, sodass `stop.at <= since` des eigenen Stops gilt
  - Test: tests/test_autoclear_eigene_signale_506.py::test_footer_gate_writes_stop_marker_on_all_paths

- **AC-21:** Given `--since` mit `nan`, `inf`, `-inf`, nicht numerischem Wert, 0/negativem Wert oder Wert > jetzt + 5 s / When der Runner startet / Then wird der Wert verworfen und der Runner-Start als Referenz benutzt (Vermerk im Log); ein gueltiger Wert (endlich, in der Vergangenheit oder <= jetzt + 5 s) wird unveraendert uebernommen; mit verworfenem Wert erkennt die Pruefung weiterhin einen Marker mit `at` nach Runner-Start
  - Test: tests/test_autoclear_eigene_signale_506.py::test_since_validation_falls_back_to_runner_start

- **AC-22:** Given eine Hook-Sitzung, deren Prozess-cwd vom Payload-`cwd` (Worktree) abweicht / When `phase_listener`, `session_banner`, `session_singleton_guard guard`, `footer_gate` und `herdr_bridge signal activity` Marker schreiben / Then liegen alle im selben Basisordner, den der Spawner und der Runner fuer dieses Payload-`cwd` verwenden (`_ac_base`), und der Runner findet sie; ohne `cwd` im Payload gilt der Prozess-cwd
  - Test: tests/test_autoclear_eigene_signale_506.py::test_markers_use_payload_cwd_base

- **AC-23:** Given echtes Herdr 0.9.5 mit Claude-TUI / When Szenario P laeuft (blockierender fremder Stop-Hook, Claude oeffnet den Bash-Berechtigungsdialog) / Then Log `ABBRUCH` mit "Claude arbeitet weiter", der Runner sendet kein Enter und kein `/clear`, `PERM-PROBE-FILE` wird nicht angelegt; When Szenario Q laeuft (fremder Stop-Hook setzt den Turn fort, `sleep 12`) / Then Log `ABBRUCH` mit "Claude arbeitet weiter" und kein `❯ /clear` im TUI waehrend des Turns
  - Test: scripts/e2e_auto_clear.sh (ONLY="P Q")

## Test Plan

Muster `tests/test_herdr_auto_clear_467.py` (isoliertes Projekt, Stub-Herdr mit Protokoll, `HOME` auf Wegwerf-Verzeichnis). Die Hook-Tests (AC-18 bis AC-20, AC-22) starten die echten Hook-Skripte als Subprozess mit `HERDR_ENV=1`, `HERDR_PANE_ID` und einem Payload-`cwd`, das vom Prozess-cwd abweicht. Der Stub kennt nur `pane send-text`, `pane send-keys` (und `notification show`); er protokolliert jeden Aufruf; bei `pane send-text <pane> /clear` gefolgt von `pane send-keys <pane> enter` schreibt er optional den SessionStart-Marker im selben Format wie `record_signal`. Der Runner wird mit explizitem `--since` gestartet. Marker fuer Eingaben und fremde Panes legen die Tests direkt als Dateien an.

### Automated Tests (TDD RED)

- [ ] Test 1: GIVEN vollstaendiger Lauf WHEN Stub-Protokoll gelesen THEN kein `agent wait`
- [ ] Test 2: GIVEN Eingabe-Marke juenger als Runner-Start WHEN Runner THEN Abbruch, nichts getippt
- [ ] Test 3: GIVEN keine neue Eingabe WHEN Runner THEN `/clear` getippt
- [ ] Test 4: GIVEN Marker `clear` nach eigenem `/clear` WHEN Runner THEN Folgebefehl getippt
- [ ] Test 5: GIVEN kein Marker bis Timeout WHEN Runner THEN Abbruch, kein Folgebefehl
- [ ] Test 6: GIVEN Marker vor `/clear` oder `source=startup` WHEN Runner THEN zaehlt nicht
- [ ] Test 7: GIVEN Marker fremdes Pane WHEN Runner THEN ohne Einfluss
- [ ] Test 8: GIVEN Hooks mit/ohne Pane-Id WHEN ausgefuehrt THEN Marker nur mit Pane-Id
- [ ] Test 9: GIVEN Markerverzeichnis nicht schreibbar WHEN Hook THEN Exit 0 ohne Ausgabe
- [ ] Test 10: GIVEN `/99-reset`, Once-Lock, Phasenwechsel WHEN Auto-/clear THEN wie bisher
- [ ] Test 11: GIVEN Eingabe-Marke zwischen `--since` und Runner-Start WHEN Runner THEN Abbruch, nichts getippt (`test_input_between_stop_and_runner_start_aborts`)
- [ ] Test 12: GIVEN activity-Marker `at > since` (auch erst waehrend settle) bzw. nach `t_clear` + Toleranz WHEN Runner THEN Abbruch "Claude arbeitet weiter", vor `/clear` nichts getippt, vor Folgebefehl kein Folgebefehl; Marker innerhalb der Toleranz zaehlt nicht
- [ ] Test 13: GIVEN stop-Marker `at > since` bzw. nach `t_clear` + Toleranz WHEN Runner THEN Abbruch; eigener Stop (`at <= since`) ohne Wirkung
- [ ] Test 14: GIVEN Signal waehrend des Wartens auf SessionStart(clear) WHEN Runner THEN kein Folgebefehl
- [ ] Test 15: GIVEN PreToolUse-`guard` mit Pane-Env (auch bei Block) WHEN Hook THEN `activity.json` `kind=pretooluse`, still, Exit-Code unveraendert, ohne Pane-Env keine Datei
- [ ] Test 16: GIVEN `signal activity`-Modus und `hooks.json` WHEN ausgefuehrt/geladen THEN Marker bzw. Registrierung (`Notification` nur `permission_prompt`)
- [ ] Test 17: GIVEN `footer_gate` auf allen Pfaden WHEN ausgefuehrt THEN `stop.json` vor dem Exit, Gate-Verhalten unveraendert
- [ ] Test 18: GIVEN `--since` `nan`/`inf`/Zukunft/Muell WHEN Runner THEN Fallback Runner-Start
- [ ] Test 19: GIVEN Payload-`cwd` ungleich Prozess-cwd WHEN Hooks schreiben THEN Marker im Basisordner des Payload-`cwd`, vom Runner gefunden
- [ ] Test 20 (R2-F001): GIVEN Runner ohne `--grace`, PreToolUse-Marker 8,5 s nach `since` WHEN Runner THEN nichts getippt; `AC_DEFAULTS`/Template `grace_s >= 10` (`test_slow_foreign_stop_hook_within_default_grace_no_clear`)
- [ ] Test 21 (R2-F002): GIVEN Signal zwischen `send-text` und Enter (vor `/clear` bzw. Folgebefehl) WHEN Runner THEN `send-keys ctrl+u`, kein Enter (`test_recheck_between_text_and_enter_clears_line`)
- [ ] Test 22 (R2-F003): GIVEN SessionStart `startup`/`resume` bzw. `session_end` nach `since`, SessionEnd-Registrierung, CLI `kind=session_end`, SessionEnd(`clear`) des eigenen `/clear` WHEN Runner/CLI THEN Abbruch bzw. Marker, eigenes `/clear` ohne Wirkung (`test_session_end_or_restart_aborts`)
- E2E Szenario S (R2-F001): fremder Stop-Hook schlaeft 8 s, blockt, Fortsetzung `sleep 3`, Config ohne `grace_s` -> ABBRUCH "Claude arbeitet weiter", kein `❯ /clear`

Weitere Laeufe:

- `pytest tests/test_autoclear_eigene_signale_506.py`, danach `pytest tests/`
- Syntaxpruefung: `python3 -m py_compile core/hooks/herdr_bridge.py core/hooks/phase_listener.py core/hooks/session_banner.py core/hooks/session_singleton_guard.py core/hooks/footer_gate.py`
- E2E: `ONLY="G G0 H P Q A B C D F" bash scripts/e2e_auto_clear.sh`

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** ADR-0506 (Konvention: ADR-Nummer = Issue-Nummer)
- **Rationale:** Der Runner entscheidet kuenftig auf Basis eigener, deterministischer Plugin-Signale (Eingabe, Aktivitaet, Stop, SessionStart-`clear` je Pane) statt auf Herdrs Statusklassifikation. Alternativen: (1) Konfig-Option/Herdr-Manifest anpassen, verworfen, weil es die Abhaengigkeit von einer lokalen Heuristik bestehen laesst, die jede Regel oder Herdr-Version verschieben kann, und der PO ausdruecklich das Plugin aendern statt sich arrangieren will; (2) ueber `agent read` den Bildschirmtext auswerten, verworfen, weil ebenfalls eine Bildschirmheuristik. Gewaehlt: Hooks laufen ohnehin bei jedem Prompt, Tool-Aufruf, Stop und Sessionstart. Die Annahme "nach dem Stop gibt es keinen Berechtigungsdialog" ist falsch (Adversary R1: ein blockierender fremder Stop-Hook setzt den Turn ohne UserPromptSubmit fort, ein Dialog wird vom Runner mit Enter bestaetigt) und wird gestrichen. Tragend ist stattdessen: Jede Claude-Aktivitaet erzeugt eigene Hook-Signale, die das Plugin selbst schreibt (PreToolUse vor jedem Tool-Aufruf und damit vor jedem Tool-Dialog, Stop, optional Notification/PermissionRequest), und der Runner tippt nur, wenn seit dem Stop keines davon eintraf. Folge: kleine Schreibzugriffe in fuenf Hooks (fail-open, still, ohne Verzoegerung), eine leichte neue Registrierung fuer Notification/PermissionRequest, Wegfall der Herdr-Statusabhaengigkeit; Restrisiko siehe Known Limitations (reine Text-Fortsetzung laenger als grace).

## Changelog

- 2026-10-31: Initial spec created
- 2026-10-31: v1.1 Nachtrag nach E2E G am echten Herdr 0.9.5: `agent prompt` wird bei `blocked` abgelehnt (`agent_blocked`); Runner tippt stattdessen per `pane send-text` + `pane send-keys enter` (Herdr nur noch als Tastatur). Referenzzeitpunkt fuer "neue Eingabe seit…" ist der Stop-Hook-Zeitpunkt (`--since <epoch>`, vom Spawner uebergeben) statt Runner-Start; die ~100-ms-Luecke entfaellt aus Known Limitations. Neues AC-14, AC-1/2/3/12 angepasst.
- 2026-10-31: v1.2 Nachtrag nach Adversary R1 (BROKEN, F001-F004): Die Annahme "nach Stop kein Berechtigungsdialog" ist gestrichen (ADR/Purpose/Runner). Eigene Signale ergaenzt: Aktivitaets-Marker (PreToolUse im `guard`, optional Notification/PermissionRequest) und Stop-Marker (`footer_gate` auf allen Pfaden); Runner tippt nur ohne input-/activity-/stop-Signal seit `since` (vor `/clear`) bzw. `t_clear` + Toleranz (vor Folgebefehl), geprueft nach grace und unmittelbar vor jedem Tippen (F001/F002). `--since` nur endlich und nicht in der Zukunft (F003). Marker-Basis aus Payload-`cwd` (F004). Neue AC-15 bis AC-23, E2E P und Q, Known Limitations ergaenzt.
- 2026-10-31: Nachtrag nach Adversary R2 (AMBIGUOUS, PO-Auftrag; nur Implementation Details, Known Limitations, Test Plan): Default-grace 10 s (F001), Pruefung zwischen Text und Enter mit `ctrl+u` (F002), SessionEnd-Marker und SessionStart `source != clear` als Abbruch (F003); E2E S, Tests 20-22.
