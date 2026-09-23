# Fast Track: edit_gate prüft jetzt die Pfad-Herkunft (#80, Epic #199, 3.30.3)

## Problem

`core/hooks/edit_gate.py` entschied bisher allein anhand von Dateiendung und Workflow-Phase, ob
ein Schreibvorgang erlaubt ist — ohne je zu prüfen, ob der Zielpfad überhaupt zum Projekt gehört.
Eine Wegwerf-Datei weit außerhalb des Repos wurde dadurch wie geschützter Projektcode behandelt:

```
Ziel:  /home/hem/.claude/jobs/<id>/tmp/paramscan/main.go
Phase: phase3_spec
→ BLOCKED (strict code gate)
```

Der PO sah dadurch eine irreführende Berechtigungsanfrage für eine Datei, die beim Aufräumen der
Sitzung ohnehin gelöscht wird, und lehnte zu Recht ab — der Agent musste mitten in der Arbeit
umgelenkt werden. Über Bash war das Gate zudem trivial umgehbar (Heredoc statt Write-Tool), verhinderte
also nichts, nur verlagerte es auf den unsaubereren Weg.

Herkunft: Backlog-Triage 21.09.2026, Epic #199, gefunden beim Bau von `gregor_zwanzig` #1396 S2
(2026-08-01).

## Scope

- `core/hooks/edit_gate.py`:
  - `_is_outside_project(file_path)` — neue Funktion: True, wenn der aufgelöste Zielpfad weder
    unter `_root` (Hauptrepo) noch unter dem aktuellen Worktree (`hook_utils.find_worktree_root()`)
    liegt. Beide Wurzeln geprüft, nicht nur `_root` — ein echter Git-Worktree kann per
    `git worktree add` außerhalb des Hauptrepos liegen (Standardverhalten, bereits so
    nachgebildet in `tests/test_loc_gate_worktree_root_96.py`); eine reine `_root`-Prüfung hätte
    jede Worktree-Sitzung fälschlich als „außerhalb" eingestuft und ihren gesamten Schutz
    abgeschaltet.
  - `Path.resolve()` folgt Symlinks — ein Link, der außerhalb liegt aber nach innen zeigt, rutscht
    dadurch nicht durch (explizite Anforderung aus dem Issue).
  - Neuer Schritt 1c in `main()`, eingefügt NACH den bestehenden Schritten 1 (Protected State
    Files) und 1b (Orchestrator-Dateien) — deren Vorrang bleibt für Pfade außerhalb des Projekts
    unverändert erhalten — und VOR allen übrigen Prüfungen (Always-Allowed, Code-Endung,
    Infrastruktur, Phase, TDD).
- **Nicht enthalten** (im Issue selbst als zweiter, unabhängiger Befund benannt): `go` als
  zusätzliche `APPROVAL_PHRASES`-Phrase in `phase_listener.py`. Geprüft gegen den aktuellen
  Stand — die im Issue zitierte CLAUDE.md-Aussage („go sei die universelle Freigabe") existiert
  in der aktuellen Doku nicht mehr (Grep über alle `.md`-Dateien: kein Treffer), und `go` steht
  bereits in `GREEN_PHRASES`. Der beschriebene Drift ist damit nicht mehr reproduzierbar — keine
  Änderung nötig.

## Definition of Done

Ein Schreibziel außerhalb von Projekt und aktuellem Worktree wird vom strict code gate nicht mehr
geprüft (sofort erlaubt), unabhängig von Phase oder aktivem Workflow. Ein Ziel innerhalb des
Projekts oder innerhalb eines Worktrees (auch wenn dieser außerhalb von `_root` liegt) durchläuft
das Gate unverändert vollständig. Protected-State- und Orchestrator-Dateien bleiben auch
außerhalb des Projekts gesperrt. Ein Symlink von außen nach innen wird nicht als „außerhalb"
gewertet.

## Acceptance Criteria

- **AC-1:** Given eine Code-Datei weit außerhalb von Projekt und Worktree, ohne aktiven Workflow
  (würde ohne Fix zwingend blocken), When `edit_gate.py` sie prüft, Then Exit 0.
- **AC-2:** Given dieselbe Konstellation, aber Ziel INNERHALB des Projekts, When geprüft, Then
  weiterhin Exit 2 („No active workflow") — unverändertes Bestandsverhalten.
- **AC-3:** Given ein echter Git-Worktree außerhalb von `_root` (Geschwister-Verzeichnis, Standard-
  `git worktree add`-Verhalten) mit einer Code-Datei darin, When geprüft (absoluter UND relativer
  Pfad), Then weiterhin Exit 2 — der Worktree wird korrekt als „innerhalb" erkannt, nicht
  fälschlich befreit.
- **AC-4:** Given ein Symlink außerhalb des Projekts, der auf eine Datei INNERHALB zeigt, When
  geprüft, Then weiterhin Exit 2 — der Fix folgt dem Link, statt ihn als Bypass zu akzeptieren.
- **AC-5:** Given eine Orchestrator-Datei (`.claude/settings.json`) außerhalb von Projekt UND
  `~/.claude/`, When geprüft, Then weiterhin Exit 2 — Schritt 1b hat Vorrang vor der neuen Prüfung.
- **AC-6:** Given eine Protected-State-Datei (`.claude/workflows/…`) außerhalb des Projekts, When
  geprüft, Then weiterhin Exit 2 — Schritt 1 hat Vorrang vor der neuen Prüfung.
- **AC-7:** Given die bestehende `~/.claude/`-Ausnahme (#48), When unverändert geprüft, Then
  weiterhin Exit 0 — keine Regression durch die neue Prüfung.

## Test Plan

`tests/test_edit_gate_outside_repo_80.py`, 8 Tests (Subprozess, echte Git-Repos, echter
`git worktree add`, echte Symlinks — Stilvorlage: `test_edit_gate_orchestrator_files.py`,
`test_loc_gate_worktree_root_96.py`):

- `test_file_far_outside_project_is_allowed` (AC-1)
- `test_file_inside_project_without_workflow_still_blocked` (AC-2, Gegenprobe)
- `test_worktree_outside_root_is_not_exempted` + `test_relative_path_inside_worktree_is_not_exempted` (AC-3)
- `test_symlink_from_outside_to_inside_target_is_not_exempted` (AC-4)
- `test_orchestrator_file_outside_project_still_blocked` (AC-5)
- `test_protected_state_file_outside_project_still_blocked` (AC-6)
- `test_home_claude_settings_still_exempted` (AC-7)

Nachweis:

- Ausgangsstand (main nach #89): 1109 passed, 4 skipped
- RED: 1 von 8 Tests rot vor dem Fix (der gemessene Vorfall selbst; die 7 „bleibt wie bisher"-
  Kontrollen bestanden schon vorher, weil sie unverändertes Verhalten prüfen)
- GREEN: 1117 passed, 4 skipped (8 neue, keine bestehenden verändert)

**Gegenprobe (Mutation).** Vier gezielte Verfälschungen, jede wurde rot: `_is_outside_project()`
liefert immer `False` (1 Test rot) · Worktree-Wurzel aus der Prüfung entfernt, nur `_root` geprüft
(2 Tests rot — bestätigt, dass eine reine `_root`-Prüfung jede Worktree-Sitzung ungeschützt
gelassen hätte) · Symlink-Auflösung durch reines `.absolute()` ersetzt (1 Test rot — bestätigt den
im Issue geforderten Symlink-Schutz) · neue Prüfung vor Schritt 1/1b statt danach eingefügt (2 Tests
rot — bestätigt, dass Protected-State/Orchestrator-Vorrang tatsächlich von der Reihenfolge abhängt,
nicht nur vom Vorhandensein der Checks). Arbeitsbaum nach jeder Mutation nachweislich sauber
wiederhergestellt (`diff` gegen Schnappschuss vor der ersten Mutation).

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Additive Prüfung vor bestehender Logik, kein neuer Mechanismus, keine Breaking
  Change für Pfade innerhalb des Projekts. PATCH-Bump (3.30.2 → 3.30.3) nach Repo-Konvention —
  behebt einen Fehlalarm, führt keine neue Fähigkeit für innerhalb liegende Pfade ein.
