# Fast Track: Klartext-Gate prüft Antworten auf Git-Wörter (#582)

## Problem

Nutzer ohne Technikprofil (siehe CLAUDE.md des Nutzers) bekommen in Abschlussmeldungen immer
wieder Git-Interna zu lesen (Branch, Commit, PR, Merge, Push, Worktree, CI), obwohl Regeln in
CLAUDE.md das verbieten. Textregeln haben nicht gereicht. In der globalen
`~/.claude/settings.json` kann die Prüfung nicht stehen (Schreibschutz durch `edit_gate.py`,
#481), deshalb liefert das Plugin sie für alle Projekte aus.

## Scope

- `core/hooks/klartext_gate.py`: neuer Stop-Hook nach dem Muster von `footer_gate.py`
  (hook_utils, fail-open, Blockade per `block()` mit Exit 2)
- `hooks/hooks.json`: Registrierung unter Stop neben `footer_gate.py`; `.claude/settings.json`
  per `scripts/sync_cloud_hooks.py` nachgezogen
- Nicht enthalten: Zwischenmeldungen während der Arbeit (nur die letzte Antwort eines Zuges),
  Antworten von Subagenten (`SubagentStop`)

## Definition of Done

Alle ACs sind durch Tests belegt; die volle Suite bleibt grün; `sync_cloud_hooks.py --check`
meldet keine Drift.

## Acceptance Criteria

- **AC-1:** Given eine Antwort mit Git-Wörtern außerhalb von Code-Angaben, When der Stop-Hook läuft, Then endet er mit Exit 2 und nennt die gefundenen Wörter.
- **AC-2:** Given Git-Wörter nur in Backticks, Codeblöcken, Adressen, Pfaden oder als Wortteil (CIA, PRAXIS, Commitment), When der Hook läuft, Then Exit 0.
- **AC-3:** Given die letzte echte Nutzernachricht enthält selbst ein Git-Wort, When der Hook läuft, Then Exit 0; Harness-Blöcke (Agenten-Meldungen, System-Hinweise) zählen nicht als Nutzernachricht.
- **AC-4:** Given `stop_hook_active` oder `OPENSPEC_KLARTEXT=0`, When der Hook läuft, Then Exit 0.
- **AC-5:** Given ein kaputtes oder fehlendes Transkript oder eine kaputte Payload, When der Hook läuft, Then Exit 0.

## Test Plan

- `tests/test_klartext_gate_582.py` (AC-1 bis AC-5, Registrierung), volle Suite
