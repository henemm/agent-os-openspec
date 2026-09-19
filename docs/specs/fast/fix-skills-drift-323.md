# Fast Track: Skills-Drift beheben, Session-Banner, knappes PO-Briefing (3.23.0)

## Problem

Das Plugin lädt zur Laufzeit nur `skills/<name>/SKILL.md`. Seit 2026-07-03 wurde fast nur
`core/commands/*.md` geändert. 3.18–3.22 kamen deshalb bei keinem Plugin-Nutzer an. Beleg:
gregor_zwanzig, feat-1681 (19.9.): Freigabetext ohne PO-Briefing.

## Scope

- `scripts/sync_skills.py` (neu): generiert `skills/` aus `core/commands/`, `--check` für release_check
- `core/hooks/session_banner.py` + `core/hooks/alias_sync.py` (neu), `hooks/hooks.json`: SessionStart-Banner
- `core/hooks/workflow.py`, `scripts/ci_spec_gate.py`, `config.yaml`: Wortgrenze für das PO-Briefing
- `core/agents/po-briefer.md`, `core/commands/30-write-spec.md`: knappes Briefing, keine Doppel-Zusammenfassung, Marker-Zeile
- Nicht enthalten: `setup.py` → #150

## Definition of Done

Eine neu gestartete Session zeigt die Plugin-Version an, und der Freigabetext besteht aus dem
unabhängigen Briefing (≤ 150 Wörter) plus Marker-Zeile mit Versionsnummer.

## Acceptance Criteria

- **AC-1:** Given eine Änderung an `core/commands/<name>.md` ohne Neugenerierung, When `release_check.py` läuft, Then blockiert die Prüfung „Skills“ das Release.
- **AC-2:** Given das Plugin ist installiert, When eine Session startet, Then sieht der User `agent-os-openspec <Version> aktiv`.
- **AC-3:** Given eine veraltete eingebettete Alias-Kopie in `~/.claude/commands`, When eine Session startet, Then nennt der Banner sie samt Befehl zum Neuerzeugen.
- **AC-4:** Given ein Briefing mit mehr als `po_briefing_gate.max_words` Wörtern, When die Freigabe versucht wird (lokal oder CI), Then blockiert das Gate mit Wortzahl und Grenze.
- **AC-5:** Given `/30-write-spec` aus dem Plugin, When die Freigabe ausgegeben wird, Then steht darunter die Marker-Zeile mit der echten Versionsnummer statt eines Platzhalters.

## Test Plan

- `tests/test_skills_sync.py` (AC-1, AC-5), `tests/test_session_banner.py` (AC-2, AC-3),
  `tests/test_po_briefing_gate.py` + `tests/test_ci_spec_gate.py` (AC-4)
- Volle Suite: 794 passed; Banner gegen die echte Umgebung ausgeführt (findet 5 veraltete Kopien)
