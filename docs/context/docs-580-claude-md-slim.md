# Kontext: docs-580-claude-md-slim (Issue #580)

## Problem
`CLAUDE.md` hat 39 904 Bytes (≈ 10–11 k Token) und wird in jedem Hauptzug und jedem
Teilagenten-Start mitgelesen. Messung dieser Cloud-Sitzung: erster Modellaufruf nach dem
Start 101 018 Token Kontext; `workflow.py context` beim ersten Aufruf 120 306 (nach Issue-Lesen).
Epic #649: frische Cloud-Sitzung lag bei #665 mit 199 501 über der Schwelle.

## Größte Abschnitte (Bytes)
Architektur-Baum 4163, Wichtige Dateien 4028, Hook-Architektur 4005, 8-Phasen-Diagramm 3095,
Konventionen 3055, Parallele Workflows 2750, Adversary System 2383, Improvement-Flow 1788,
Kontext-Haushalt 1755. Rollen/Arbeitsweise/Orchestrator/Isolation/Adversary-Limit ≈ 5,5 KB.

## Abhängige Dateien (lesen CLAUDE.md-Inhalt)
- `scripts/release_check.py` — nur `**Version**:`-Zeile (bleibt).
- `core/hooks/claude_md_protection.py` — `max_lines` 600 + verbotene Muster; Kürzung unkritisch.
- `tests/test_rueckbau_autoclear_663.py` — Version + keine Auto-/clear-Tokens (bleibt erfüllt).
- `tests/test_state_files_source_422.py` — `hook_utils.py`-Zeile mit 3 Funktionsnamen (Tabelle wandert).
- `tests/test_cloud_agents_577.py` — nennt `scripts/sync_cloud_agents.py` und `.claude/agents/`.
- `tests/test_agent_dispatch_drift_279.py` — Agenten in CLAUDE.md / Modell-Tabelle.
- weitere Tests (`test_readme_version_195`, `test_release_check_93`, …) nur Version.
- `docs/arbeitsweise.md` existiert bereits (Volltext Arbeitsweise).

## Analyse / Ansatz
Referenzteile wörtlich nach neuer Datei `docs/architektur.md` verschieben, CLAUDE.md behält
Rollen, Arbeitsweise, Projektzweck, Orchestrator-Prinzip, Phasen-Kurzliste, Workflow-Aufruf-Kern,
Kontext-Haushalt (kurz), harte Regeln (Infrastruktur-Schutz, Hook-Pfade, Hook-Entwicklung,
skills generiert, Workflow-Isolation, Adversary-Limit) und einen Verweis-Satz.
Tests, die Referenzinhalt prüfen, lesen künftig CLAUDE.md + docs/architektur.md zusammen.
Neuer Größenwächter-Test: CLAUDE.md ≤ 12 288 Bytes, docs/architektur.md existiert und ist verlinkt.
Risiko: niedrig (Doku + Tests); kein Hook-Code.
