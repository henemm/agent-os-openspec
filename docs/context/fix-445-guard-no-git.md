# Context: fix-445-guard-no-git

## Request Summary
Der Sitzungs-Wächter (`session_singleton_guard.py guard`) sperrt Edit/Write/Bash/Task/Agent in jedem Ordner außerhalb von `.claude/worktrees/<name>/` und verweist auf `EnterWorktree`. In Ordnern ohne Git scheitert `EnterWorktree` ("not in a git repository"). Die Sitzung ist ausgesperrt, Ausweg nur per `override`.

## Related Files
| File | Relevance |
|------|-----------|
| `core/hooks/session_singleton_guard.py:649-708` | `_do_guard`: Sperre ohne Prüfung, ob ein Worktree dort überhaupt möglich ist. Fix-Ort. |
| `core/hooks/session_singleton_guard.py:234-236` | `_is_worktree_cwd`: reine Pfad-Regex, kennt kein Git |
| `core/hooks/session_singleton_guard.py:299-320` | `_read_branch`: liest `.git` bereits per Dateizugriff ohne Subprozess (Muster für Git-Erkennung) |
| `tests/test_session_singleton_guard.py:128-240` | Bestandstests der Guard-Entscheidung |
| `core/hooks/worktree_write_guard.py` | Anderer Guard (Edit/Write); in der Suche keine Git-Abhängigkeit gefunden, separat bestätigen |

## Existing Patterns
- Fail-safe-Regel im Modulkopf: "Jede unerwartete Exception → exit(0). Der Guard darf niemals fälschlich blockieren."
- Ausstiege in `_do_guard` als Kette von `sys.exit(0)` (Worktree, Rescue, sync-main, Override-Token). Neuer Ausstieg passt direkt davor.
- Git-Erkennung ohne Subprozess über Dateisystem (`Path(cwd) / ".git"`), wie in `_read_branch`.

## Dependencies
- Upstream: nur `os`, `re`, `pathlib`; `hook_utils.log_gate_event` fürs Protokoll.
- Downstream: Registrierung für alle Tools in `hooks/hooks.json`; `session_banner.py` und weitere Tests importieren das Modul.

## Existing Specs
- `docs/specs/feat-106-session-register.md`, `docs/specs/fix-120-121-session-register.md`: Session-Register, nicht die Sperrlogik.

## Risks & Considerations
- **Bestandstests brechen:** `MAIN_CWD = "/home/user/myproject"` existiert nicht auf der Platte. Eine Git-Prüfung würde dort "kein Git" ergeben und erlauben. Die vier Block-Tests (Edit/Write/Bash/hermetisch) müssen auf ein echtes `tmp_path` mit `.git` umgestellt werden.
- **Fail-Richtung:** Nicht existierender oder nicht lesbarer Pfad. Modulkopf sagt "niemals fälschlich blockieren", also erlauben. Echte Git-Ordner haben immer ein `.git`, also keine Sicherheitslücke.
- **Git-Erkennung:** `.git` kann Ordner (normales Repo) oder Datei (Worktree/Submodul) sein; Elternordner mitprüfen, weil Sitzungen in Unterordnern eines Repos laufen können (Hook-Pfad-Regel #165).
- **WorktreeCreate-Hook:** Im Repo nirgends konfiguriert (grep leer). Projekte mit eigenem Hook könnten auch ohne Git Worktrees anlegen. Für diesen Fix nicht berücksichtigt, in der Spec als Known Limitation nennen.
- **Hoher Blast Radius:** Der Guard läuft bei jedem Tool-Aufruf in allen Projekten. Zu großzügige Erkennung würde die Worktree-Pflicht in Git-Projekten aushebeln.
- Der Hinweistext bleibt im Git-Fall unverändert; im Nicht-Git-Fall wird er nie erreicht.

## Analysis

### Type
Bug

### Affected Files (with changes)
| File | Change Type | Description |
|------|-------------|-------------|
| core/hooks/session_singleton_guard.py | MODIFY | Neue Hilfsfunktion `_is_git_dir(cwd)` (Dateisystem, `.git` im Ordner oder Elternordner, Ordner ODER Datei) + Ausstieg in `_do_guard` nach dem Worktree-Check |
| tests/test_session_singleton_guard.py | MODIFY | Block-Tests auf echtes `tmp_path` mit `.git` umstellen; neue Tests: ohne `.git` → Exit 0 (Bash/Edit/Write), mit `.git` ohne Worktree → Exit 2, `.git` als Datei, `.git` im Elternordner |
| CHANGELOG.md | MODIFY | Eintrag unter [Unreleased] |

### Scope Assessment
- Files: 3
- Estimated LoC: +~15 Code, +~60 Tests
- Risk Level: MEDIUM (Guard läuft bei jedem Tool-Aufruf in allen Projekten; zu großzügige Erkennung würde Worktree-Pflicht aushebeln)

### Technical Approach
- Ausstieg direkt nach `_is_worktree_cwd`: kein `.git` in cwd oder Eltern → `sys.exit(0)` (kein Worktree möglich, nichts zu erzwingen). Fail-safe: Exception/nicht existierender Pfad → erlauben (Modulkopf-Regel).
- Reiner Dateisystem-Check, kein Subprozess (Muster `_read_branch`). Heartbeat läuft davor und bleibt unberührt.
- Hinweistext bleibt unverändert: Im Nicht-Git-Fall wird er nie erreicht, damit entfällt die Sackgasse. Die DoD-Zeile "Hinweistext nennt den Nicht-Git-Fall nicht mehr als Sackgasse" ist dadurch erfüllt.
- `worktree_write_guard.py`: kein Git-Bezug in der Suche, unverändert.
- Alternative WorktreeCreate-Hook verworfen (aufwendiger, Nutzen unklar); als Known Limitation nennen.

### Dependencies
Nur `os`/`re`/`pathlib`; Modul wird von `session_banner.py` und Tests importiert (Signaturen unverändert).

### Befunde gegen den Plan
Keine: Echte Git-Ordner haben immer `.git`; Bestandstests mit fiktivem `MAIN_CWD` müssen umgestellt werden (kein Produktivrisiko).

### Open Questions
- [ ] Keine blockierenden. Tech-Lead-Entscheidung: Elternordner-Suche inkl. `.git` als Datei, Fail-Richtung = erlauben.
