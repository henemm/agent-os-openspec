---
entity_id: fix-445-guard-no-git
type: bugfix
created: 2026-10-23
updated: 2026-10-23
status: draft
version: "1.0"
tags: [session-singleton-guard, worktree, no-git]
---

# fix-445-guard-no-git

## Approval

- [ ] Approved

## Purpose

Der Sitzungs-Wächter sperrt Bash, Edit, Write, Task und Agent in jedem Ordner außerhalb von `.claude/worktrees/<name>/` und verweist auf `EnterWorktree`. In Ordnern ohne Git scheitert `EnterWorktree` ("not in a git repository"); die Sitzung ist ausgesperrt, Ausweg nur per `override` (Issue #445). Der Wächter soll dort nichts erzwingen, wo er nichts isolieren kann.

## Source

- **File:** `core/hooks/session_singleton_guard.py`
- **Identifier:** `_do_guard`, neue Hilfsfunktion `_is_git_dir`

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `core/hooks/session_singleton_guard.py::_read_branch` | Funktion (Muster) | Erkennt `.git` bereits per Dateizugriff ohne Subprozess — gleiches Vorgehen |
| `tests/test_session_singleton_guard.py` | Tests | Bestandstests der Guard-Entscheidung, werden angepasst |

## Scope

- **Affected Files:** `core/hooks/session_singleton_guard.py` (MODIFY), `tests/test_session_singleton_guard.py` (MODIFY), `CHANGELOG.md` (MODIFY)
- **Estimated Changes:** ~15 LoC Code, ~60 LoC Tests

## Implementation Details

```python
def _is_git_dir(cwd: str) -> bool:
    """True, wenn cwd oder ein Elternordner ein .git (Ordner ODER Datei) enthaelt.

    Reiner Dateisystem-Check, kein Subprozess. Fail-safe: nicht existierender
    oder nicht lesbarer Pfad, jede Exception -> False (= nichts erzwingen).
    """
    try:
        p = Path(cwd)
        return any((q / ".git").exists() for q in (p, *p.parents))
    except Exception:
        return False
```

In `_do_guard` direkt nach dem `_is_worktree_cwd`-Ausstieg:

```python
# Ohne Git ist kein Worktree moeglich (EnterWorktree scheitert) — nichts zu erzwingen (#445).
if not _is_git_dir(cwd):
    sys.exit(0)
```

Der Hinweistext bleibt unverändert; im Nicht-Git-Fall wird er nie erreicht, damit entfällt die Sackgasse. Heartbeat läuft weiterhin vor dem Ausstieg. `worktree_write_guard.py` bleibt unverändert (kein Git-Bezug).

## Expected Behavior

- **Input:** Tool-Aufruf (Bash/Edit/Write/Task/Agent) mit `cwd` außerhalb eines Worktrees
- **Output:** `cwd` ohne `.git` in sich und allen Elternordnern → Exit 0 (erlaubt). `cwd` mit `.git` (Ordner oder Datei, auch im Elternordner) und ohne Worktree → weiter Exit 2 mit unverändertem Hinweistext.
- **Side effects:** keine; Heartbeat/Session-Register unverändert.

## Known Limitations

- Projekte mit eigenem `WorktreeCreate`-Hook könnten auch ohne Git Worktrees anlegen; dort wird die Worktree-Pflicht nun nicht mehr erzwungen. Alternative (WorktreeCreate-Hook für Nicht-Git-Ordner) verworfen: aufwendiger, Nutzen unklar.
- Nicht existierender oder nicht lesbarer `cwd` gilt als "kein Git" (erlauben, gemäß Modulregel "Guard darf niemals fälschlich blockieren"). Echte Git-Ordner haben immer ein `.git`, daher keine Sicherheitslücke.

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] Eine Sitzung in einem Ordner ohne Git (z. B. Notizordner) kann Bash/Edit/Write ohne `override` nutzen
- [ ] In Git-Projekten gilt die Worktree-Pflicht unverändert
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf grün)

## Acceptance Criteria

- **AC-1:** Given ein Ordner ohne `.git` (auch in keinem Elternordner) / When Bash, Edit oder Write aufgerufen wird / Then beendet sich der Wächter mit Exit 0
  - Test: tests/test_session_singleton_guard.py::test_no_git_dir_allows_bash_edit_write
- **AC-2:** Given ein Git-Ordner (`.git` als Ordner) außerhalb eines Worktrees / When Bash, Edit oder Write aufgerufen wird / Then Exit 2 mit Hinweistext
  - Test: tests/test_session_singleton_guard.py::test_git_dir_without_worktree_still_blocks
- **AC-3:** Given `.git` als Datei (Worktree/Submodul-Stil) im Arbeitsordner / When ein schreibendes Tool aufgerufen wird / Then Exit 2
  - Test: tests/test_session_singleton_guard.py::test_git_file_counts_as_git
- **AC-4:** Given `.git` nur in einem Elternordner, Sitzung in einem Unterordner / When ein schreibendes Tool aufgerufen wird / Then Exit 2
  - Test: tests/test_session_singleton_guard.py::test_git_in_parent_dir_still_blocks
- **AC-5:** Given ein nicht existierender `cwd` / When ein schreibendes Tool aufgerufen wird / Then Exit 0 (fail-safe)
  - Test: tests/test_session_singleton_guard.py::test_nonexistent_cwd_allows
- **AC-6:** Given ein Ordner ohne `.git` / When der Wächter läuft / Then wird der Heartbeat weiterhin geschrieben
  - Test: tests/test_session_singleton_guard.py::test_no_git_dir_still_heartbeats

> Die Test-Zuordnung wird **bei der Spec-Erstellung** eingetragen, nicht nachträglich:
> Nach der Freigabe ist diese Datei eingefroren (#230) — jede Änderung verschiebt den
> PO-Briefing-Hash und blockt den Workflow-Abschluss. Stimmt der Testname später nicht
> mehr, gehört die Korrektur in die TDD-RED-Artefakte (`workflow.py add-artifact`),
> nicht in diese Datei.

## Test Plan

Automatische Tests (jeweils an eine AC oben gebunden):
- `pytest tests/test_session_singleton_guard.py`
- Bestehende Block-Tests (Edit/Write/Bash/hermetisch) werden von fiktivem `MAIN_CWD` auf ein echtes `tmp_path` mit `.git` umgestellt, sonst würden sie wegen "kein Git" erlauben.

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Lokale Korrektur eines Ausstiegs in einem bestehenden Guard; keine neue Architektur, Mechanismus und Fail-Richtung folgen der Modulregel.

## Changelog

- 2026-10-23: Initial spec created
