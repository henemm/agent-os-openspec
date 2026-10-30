---
entity_id: fix-489-kette-auto-clear
type: feature
created: 2026-10-30
updated: 2026-10-30
status: draft
version: "1.0"
workflow: fix-489-kette-auto-clear
tags: [herdr, auto-clear, autonomy, commands]
---

# Kette beendet den Turn an Phasengrenzen, wenn Auto-/clear aktiv ist (Issue #489)

## Approval

- [ ] Approved

## Purpose

Auto-`/clear` (#467) loest nur am Ende einer Antwort aus. Die Befehle rufen den naechsten Schritt aber oft im selben Turn selbst auf: 10→20 und 20→30 im Auto-Modus, 30→40, 40→50 und 50→60 immer. Damit wird an diesen Grenzen nie geleert. Ist Auto-`/clear` in einem Herdr-Pane aktiv, beenden die Befehle kuenftig die Antwort an der Phasengrenze mit dem Checkpoint und der ❗Du-Zeile `/<naechster> #N`; Herdr tippt dann `/clear` und den Folgebefehl. Ohne aktives Auto-`/clear` bleibt die Kette wie bisher.

## Source

- **File:** `core/hooks/workflow.py`, `core/commands/10-context.md`, `20-analyse.md`, `30-write-spec.md`, `40-tdd-red.md`, `50-implement.md` (+ generierte `skills/`)
- **Identifier:** CLI `workflow.py autoclear`; Abschnitte zur Kettenfortsetzung in den Befehlen

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `core/hooks/herdr_bridge.py` (#467/#480) | module | `auto_clear_enabled()`, `_pane()` |
| `core/hooks/workflow.py` | module | CLI-Dispatch `COMMANDS` |
| `core/commands/*` | commands | Kettenfortsetzung (#472) |
| `scripts/sync_skills.py` | script | erzeugt `skills/` |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| core/hooks/workflow.py | MODIFY | `cmd_autoclear`: genau eine Zeile `AUTO_CLEAR=on|off`, Exit 0 |
| core/commands/10-context.md | MODIFY | Kettenfortsetzung prueft `AUTO_CLEAR` |
| core/commands/20-analyse.md | MODIFY | dito |
| core/commands/30-write-spec.md | MODIFY | dito (nach Freigabe und nach Auto-Freigabe) |
| core/commands/40-tdd-red.md | MODIFY | dito |
| core/commands/50-implement.md | MODIFY | dito |
| skills/*/SKILL.md | MODIFY | per `sync_skills.py` |
| tests/test_kette_auto_clear_489.py | CREATE | CLI + Textvertraege |
| CHANGELOG.md | MODIFY | [Unreleased] |

### Estimated Changes

- Files: 1 neu, ~12 geaendert (davon 5 generiert)
- LoC: +20 Produktion / +40 Anweisungstext / +80 Test
- Risk Level: LOW (Anweisungstext + reine Auskunfts-CLI)

## Implementation Details

**CLI.** `workflow.py autoclear` gibt genau eine Zeile `AUTO_CLEAR=on` aus, wenn `herdr_bridge._pane()` eine Pane-ID liefert UND `herdr_bridge.auto_clear_enabled()` wahr ist, sonst `AUTO_CLEAR=off`. Jede Ausnahme → `off`. Kein aktiver Workflow noetig, Exit immer 0 (Vorbild `cmd_autonomy`).

**Befehle.** An jeder Stelle, an der der Befehl den naechsten Skill im selben Turn selbst aufruft (10→20, 20→30, 30→40 inkl. Auto-Freigabe-Pfad, 40→50, 50→60), steht vorher: `python3 .claude/hooks/workflow.py autoclear` ausfuehren. Bei `AUTO_CLEAR=on`: den Skill NICHT selbst aufrufen, sondern die Antwort mit dem Positiv-Checkpoint („`/clear` ist jetzt gefahrlos“) und der ❗Du-Zeile `/<naechster Befehl> #<N>` beenden — Herdr tippt `/clear` und den Folgebefehl. Ist der Negativ-Block noetig (etwas nicht gesichert), gilt er wie bisher. Bei `AUTO_CLEAR=off`: unveraendert.

## Expected Behavior

- **Input:** Workflow in Herdr mit aktivem Auto-`/clear`, Phase endet
- **Output:** Antwort endet an der Phasengrenze; Herdr leert und startet den naechsten Befehl
- **Side effects:** keine

## Known Limitations

- Ob Claude die Anweisung befolgt, ist Modellverhalten; die Tests pruefen den Anweisungstext und die CLI.
- Echte Wirkung nur in Herdr pruefbar.

## Definition of Done

Fertig ist diese Aenderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] In Herdr mit aktivem Auto-`/clear` wird an jeder Phasengrenze geleert und der naechste Befehl gestartet (manuelle Abnahme durch den PO)
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf gruen)

## Acceptance Criteria

- **AC-1:** Given gueltiges Herdr-Env (Stub-Binary) und `OPENSPEC_HERDR_AUTO_CLEAR=1` / When `workflow.py autoclear` laeuft / Then ist die Ausgabe genau `AUTO_CLEAR=on`, Exit 0; ohne Herdr-Env bzw. ohne Opt-in `AUTO_CLEAR=off`, Exit 0
  - Test: tests/test_kette_auto_clear_489.py::test_autoclear_cli

- **AC-2:** Given die Befehle 10-context, 20-analyse, 30-write-spec, 40-tdd-red, 50-implement (Quelle und generierte Skills) / When ihre Kettenfortsetzung gelesen wird / Then enthaelt jeder den Aufruf `workflow.py autoclear` und die Anweisung, bei `AUTO_CLEAR=on` den naechsten Skill nicht selbst aufzurufen, sondern die Antwort mit Checkpoint und ❗Du-Zeile zu beenden
  - Test: tests/test_kette_auto_clear_489.py::test_chain_commands_check_autoclear

- **AC-3:** Given die generierten Skills / When `scripts/sync_skills.py --check` laeuft / Then meldet es keine Abweichung
  - Test: tests/test_kette_auto_clear_489.py::test_skills_in_sync

## Test Plan

CLI per Subprozess mit Stub-Binary (Muster `tests/test_auto_clear_global_480.py`); Textvertraege per Dateilesen; Skill-Sync per Skript.

- `pytest tests/test_kette_auto_clear_489.py`
- Regressionslauf: `pytest tests/`

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Abstimmung zweier bestehender Mechanismen (#467, #472) ueber eine reine Auskunfts-CLI und Anweisungstext; keine neue Struktur.

## Changelog

- 2026-10-30: Initial spec created
