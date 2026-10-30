# Kontext + Analyse: fix-495-autoclear-mechanisch (Issue #495)

## Request Summary
Auto-/clear (#467/#489) loest im Konsumentenprojekt nie aus. Log: `skip: Marker fehlt oder Negativmarker`. PO verlangt eine gruendlich recherchierte, robuste Loesung statt weiterer Versuche.

## Recherche (Claude-Code-Doku: hooks, commands, headless)
- Kein Hook kann Kontext leeren, eine neue Session starten oder einen Prompt absenden. Stop `decision:"block"` + `reason` setzt nur im selben Kontext fort.
- SessionStart `source:"clear"` beobachtet ein `/clear` nur; `initialUserMessage` nur in `-p`.
- Stop-Input enthaelt `last_assistant_message`, `stop_hook_active` — Entscheidung soll aus dem State auf Platte fallen, nicht aus Prosa.
- Im TUI bleibt externes Tippen (Herdr `agent prompt`) der einzige Weg → Herdr-Runner bleibt, nur der Ausloeser wird ersetzt.

## Ursache (Code-Beleg)
- `core/hooks/herdr_bridge.py` `maybe_auto_clear` (~Z. 418): Bedingung `has_clear_marker(message)` verlangt den Satz „`/clear` ist jetzt gefahrlos“ (`POSITIVE_MARKER`, Z. 259) ausserhalb von Code-Fences vor der letzten ❗Du-Zeile. Das Modell laesst den Checkpoint-Block weg oder formuliert um → `_ac_skip("Marker fehlt oder Negativmarker")`.
- Aufruf: `core/hooks/footer_gate.py` `_maybe_auto_clear` (~Z. 176) auf dem Pfad „Fusszeile korrekt“.
- Grenz-Signal existiert schon: alle Phasenbefehle (10–50) rufen an der Grenze `workflow.py autoclear` (`cmd_autoclear`, workflow.py ~Z. 3032) — wird bisher nur ausgegeben, nicht vermerkt.

## Related Files
- core/hooks/herdr_bridge.py — `maybe_auto_clear`, `has_clear_marker`, Marker-Konstanten, `_acquire_lock`
- core/hooks/workflow.py — `cmd_autoclear`, `expected_footer_command`, State-Speichern (`_save_active`/`_read_active`)
- core/hooks/footer_gate.py — Aufrufer
- core/commands/10-context.md … 50-implement.md — rufen `autoclear` an der Grenze
- tests/test_herdr_auto_clear_467.py (Ausloesebedingungen inkl. Marker), tests/test_clear_checkpoint_blocks.py (Checkpoint-Text in Befehlen)

## Loesungsrichtung
- `workflow.py autoclear`: bei `AUTO_CLEAR=on` und aktivem Workflow im State `auto_clear_boundary = {"phase": current_phase, "command": expected_footer_command(data), "at": iso}` speichern (fail-open, Ausgabe unveraendert).
- `maybe_auto_clear`: statt Positiv-Marker gilt: `auto_clear_boundary` vorhanden, `phase` == aktuelle Phase, `command` == erwarteter Befehl. Negativ-Marker bleibt als Veto (kann nur verhindern). Fusszeilen-Pruefung bleibt.
- Log-Grund bei Fehlen: `skip: keine Grenze vermerkt`.

## Risks
- Ausloesen ohne gesicherten Stand: Vermerk entsteht erst beim `autoclear`-Aufruf am Ende der Phase (nach Phasenwechsel/Commit laut Befehlstext); Once-Lock bleibt.
- Alter Workflow-State ohne Feld → kein Ausloesen (wie heute).
