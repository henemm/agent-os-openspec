# Fast Track: Sicherheits-Paket aus der Backlog-Triage (#279, #355, #252, #300, #295)

## Problem

Die Backlog-Triage vom 2026-10-05 fand fünf kleine, klar umrissene Lücken in den Wächtern:
Copy-Modus mit nur 4 von 13 Hooks (#279), `git merge --continue` am Commit-Gate vorbei (#355),
`../`-Umgehung von `extra_allowed_write_dirs` (#252/#245), `None == None` als Instanz-Identität
(#300), Testläufe aus Worktrees im echten Gate-Log (#295). PO-Vorgabe: als Tech Lead ohne
Workflow umsetzen; Fast Track, weil jede Änderung lokal, klein und per Regressionstest belegt ist.

## Scope

- `setup.py`: Copy-Modus-Registrierung aus `hooks/hooks.json`, Nachtrag bei `--update`
- `scripts/release_check.py`, `CLAUDE.md`: Versions-Header und Agenten-Tabelle gegen Drift
- `core/hooks/bash_gate.py`: `_creates_commit` (commit + merge --continue)
- `core/hooks/secret_egress_guard.py`: `_system_alias_forms`, `_is_system_symlink`
- `core/hooks/post_implementation_gate.py`: Lock ohne `workflow_created` verwerfen
- `core/hooks/hook_utils.py`: `_gate_events_root`
- Nicht enthalten: #365 (eigener, laufender Workflow), #246 (bewusst nicht normalisiert)

## Definition of Done

Jede der fünf Lücken ist durch einen Test belegt, der ohne die Änderung rot und mit ihr grün ist;
die volle Suite bleibt grün, auch aus einem Git-Worktree heraus (0 Zeilen im echten Gate-Log).

## Acceptance Criteria

- **AC-1:** Given ein frisch im Copy-Modus installiertes Projekt, When settings.json erzeugt wird, Then enthält sie genau die Hooks aus hooks/hooks.json inklusive SessionStart, SessionEnd und Stop.
- **AC-2:** Given eine settings.json im Stand vor #279 mit eigenem Hook, When `setup.py --update` läuft, Then fehlen danach keine Framework-Hooks, der eigene Hook und die Rechte bleiben, ein zweites Update ändert nichts.
- **AC-3:** Given ein Workflow in phase6 ohne Verdict, When `git merge --continue` ausgeführt werden soll, Then blockt bash_gate wie bei `git commit`.
- **AC-4:** Given `extra_allowed_write_dirs: ["^/tmp/"]`, When nach `/tmp/../etc/passwd` oder über einen selbst angelegten Symlink geschrieben wird, Then gilt das Ziel als außerhalb der Sicherheitszone.
- **AC-5:** Given ein Lock ohne `workflow_created` und ein Workflow ohne `created`, When ein passender Marker vorliegt, Then wirkt er nicht als Freigabe, und das Gate blockt nach Ablauf des Batch-Fensters weiterhin.
- **AC-6:** Given CLAUDE_PROJECT_DIR auf ein fremdes Projekt und die CWD in einem Worktree dieses Repos, When ein Gate blockt, Then landet das Event im Log des Projekts, nicht im Worktree.

## Test Plan

- `tests/test_copy_mode_hooks_279.py` (AC-1, AC-2), `tests/test_agent_dispatch_drift_279.py`, `tests/test_readme_version_195.py`
- `tests/test_merge_continue_gate_355.py` (AC-3), `tests/test_egress_path_compare_252.py` (AC-4)
- `tests/test_post_implementation_gate_marker_binding.py::TestIssue300MissingIdentity` (AC-5)
- `tests/test_gate_event_log_worktree_280.py` (AC-6)
- Volle Suite aus einem Git-Worktree; Zeilenzahl von `.claude/gate-events.jsonl` danach 0
