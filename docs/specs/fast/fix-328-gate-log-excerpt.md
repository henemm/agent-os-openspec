# Fast Track: Gate-Event-Log — Befehlsausschnitt und Version bei den Kern-Gates (#328, Folge von #181)

## Problem

Die erste Auswertung echter Logs (3.291 Blockaden, 22.09.–02.10.2026, 7 Projekt/Rechner-Paare)
zeigt: Bei `bash_gate` (382), `edit_gate` (76), `tdd_enforcement` (16) und
`post_implementation_gate` (11) fehlt `command_excerpt` in 100 % der Fälle, weil
`hook_utils._log_gate_event_for_block` den Ausschnitt nur aus der Umgebungsvariable
`CLAUDE_TOOL_INPUT` ableitet. Claude Code liefert das Tool-Input über stdin. Die Tests für #181
setzen die Variable und fangen den Unterschied nicht. Folge: Die Fehlalarm-Triage dieser Gates ist
unmöglich, obwohl sie der Zweck des Logs ist. Außerdem trägt kein Ereignis eine Framework-Version,
sodass Auswertungen Fixes über die Zeit (z. B. #237 für `/dev/null`) nicht zuordnen können.

## Scope

- `core/hooks/hook_utils.py`:
  - `get_tool_input()` merkt sich die über stdin gelieferte Hook-Eingabe (`tool_name`, `tool_input`)
    in einem Modul-Zwischenspeicher. Die vier Gates rufen es ohnehin auf, bevor sie blockieren;
    an den Gates selbst ändert sich nichts.
  - `_log_gate_event_for_block()` nutzt den Zwischenspeicher als Fallback für `tool` und
    `command_excerpt`, wenn die Umgebungsvariablen leer sind. Reihenfolge: ausdrücklich
    übergeben → Umgebungsvariable → stdin-Zwischenspeicher.
  - `log_gate_event()` schreibt zusätzlich `framework_version` (aus `.claude-plugin/plugin.json`
    neben dem Hook-Ordner; leer, wenn nicht ermittelbar).
- `CHANGELOG.md` unter [Unreleased].
- **Nicht enthalten:** `footer_gate` (Stop-Hook ohne Tool-Eingabe, hat keinen Ausschnitt),
  `secret_egress_guard` (übergibt den Ausschnitt bewusst leer, bleibt unverändert).

## Definition of Done

Blockiert eines der vier Gates mit Tool-Input nur über stdin, steht der maskierte Ausschnitt im
Ereignis. Jedes Ereignis trägt `framework_version`. Ein Logging-Fehler ändert nie den Exit-Code.
`secret_egress_guard` loggt weiterhin ohne Inhalt.

## Acceptance Criteria

- **AC-1:** Given ein Hook liest sein Tool-Input über stdin (`tool_name`, `tool_input.command`),
  ohne dass `CLAUDE_TOOL_INPUT`/`CLAUDE_TOOL_NAME` gesetzt sind, When er über `block()` blockiert,
  Then enthält das Ereignis `tool` und den maskierten `command_excerpt`.
- **AC-2:** Given dasselbe über `edit_gate.py` als echter Hook-Prozess mit einem Datei-Edit,
  When er blockiert, Then enthält das Ereignis den Dateipfad als `command_excerpt`.
- **AC-3:** Given ein Ereignis, When es geschrieben wird, Then enthält es `framework_version`
  gleich dem Versionsfeld aus `.claude-plugin/plugin.json`.
- **AC-4:** Given `secret_egress_guard` blockiert mit stdin-Eingabe, Then bleibt `command_excerpt`
  leer und kein ausgeschriebener Wert steht im Log (Verhalten aus #181 unverändert).
- **AC-5:** Given ein Geheimnis-Schlüsselwort im Ausschnitt aus stdin, Then wird er maskiert
  (`API_KEY=***`), wie bei der Umgebungsvariable.
- **AC-6:** Given Umgebungsvariable und stdin-Eingabe gleichzeitig, Then gewinnt die Umgebungsvariable
  (unverändertes Verhalten), und ausdrücklich übergebene Werte gewinnen vor beiden.

## Test Plan

`tests/test_gate_event_excerpt_328.py`: Einheitstests mit stdin-Eingabe in einem Unterprozess
(imitiert das Muster der Gates: `get_tool_input()` dann `block()`), ein Test mit dem echten
`edit_gate.py`, ein Test für `secret_egress_guard`, ein Test für die Version. Bestehende Tests
(`test_gate_event_log_181.py`, `test_gate_event_log_worktree_280.py`) laufen unverändert.
