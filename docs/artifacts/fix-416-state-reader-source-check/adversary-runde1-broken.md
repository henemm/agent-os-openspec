# Adversary-Lauf 1 — fix-416-state-reader-source-check — Verdict BROKEN

Datum: 2026-10-11. Tests: 2472 passed, 23 skipped, 0 failed. Checkliste 20/21 (Input offen).

## Findings

- **F001 HIGH spec_violation** — `core/hooks/workflow.py:2084` `cmd_cleanup_stale_locks`: `_read_workflow` in
  `try/except Exception: pass`; `UnsafeStateError` wird verschluckt, danach werden `pending_validation_<wf>.json`
  und `user_approved_validation_<wf>` gelöscht. Reproduktion: harter Verweis auf State (nlink 2, phase7_validate)
  plus Sperrdatei → `workflow.py cleanup-stale-locks` → "Removed: pending_validation_demo.json", rc=0.
  Kontrolle normaler State phase6 → "SKIPPED". Fix: `except UnsafeStateError` vor `except Exception`,
  SKIPPED mit Grund, Marker nicht löschen, Test ergänzen.
- **F002 LOW edge_case** — `core/hooks/edit_gate.py:173` `_find_workflow_for_file`: ein fremder unsicherer State
  blockt Code-Edits, wenn der aktive State nicht gelesen wird. Als Known Limitation dokumentieren.
- **F003 LOW edge_case** — `core/hooks/hook_utils.py:1419` `_state_walk_start`: Pfad außerhalb der Wurzel → nur
  letztes Glied geprüft; in Produktion nicht erreichbar. Im Docstring festhalten.

## Ohne Befund

FIFO (kein Hängen), Ordner statt Datei, dangling Symlink, `_archive` als Symlink, hart verlinkter Archiv-State,
Wurzel hinter Symlink, echter Hauptordner-State, qa_gate-Stempel (restriktiv), alle übrigen Leser gemäß Spec-Tabelle.

## Entscheidung Orchestrator

F001 und F003 werden gefixt (gezielter Developer-Auftrag). F002 kommt als Known Limitation in den CHANGELOG-Eintrag
(die Spec ist nach der Freigabe eingefroren, #230). Danach genau eine weitere Adversary-Runde.
