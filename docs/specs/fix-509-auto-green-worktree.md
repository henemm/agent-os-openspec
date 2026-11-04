---
entity_id: fix-509-auto-green-worktree
type: bugfix
created: 2026-11-04
updated: 2026-11-04
status: draft
version: "1.0"
workflow: fix-509-auto-green-worktree
tags: [workflow, auto-green, worktree, artifacts, security]
---

# auto-green findet das GREEN-Artefakt im Worktree (Issue #509)

## Approval

- [ ] Approved

## Purpose

`workflow.py auto-green` sucht das registrierte GREEN-Artefakt nur unter dem Hauptrepo-Root. In einer Worktree-Sitzung liegt die Datei aber im Worktree, weil `docs/artifacts/` gitignored ist und nicht geteilt wird. Die automatische GREEN-Freigabe (#471) antwortet deshalb in Worktrees immer `AUTO_GREEN=human` mit „GREEN-Artefakt fehlt, ist keine regulaere Datei oder liegt ausserhalb des Projekts“, und jede Sitzung fällt auf die manuelle Freigabe zurück. Künftig löst `_green_artifact_file` einen relativen Pfad zuerst gegen den Worktree auf, wie es Spec und Briefing im selben Modul schon tun, und prüft die Grenze gegen genau diese Wurzel. Der Schutz aus #471 (kein Symlink, nichts außerhalb, nur reguläre Datei) bleibt unverändert.

## Source

- **File:** `core/hooks/workflow.py`
- **Identifier:** `workflow._green_artifact_file` (geändert); genutzt, unverändert: `workflow._worktree_first_root`, `workflow._worktree_root_if_any`, `workflow._auto_green_decision`, `hook_utils.find_project_root`

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `workflow._worktree_first_root` (#470) | function | eine Quelle für „Worktree vor Hauptrepo“; schon für Spec und Briefing im Einsatz |
| `workflow._auto_green_decision` (#471) | function | einziger Aufrufer; Prüfkette und Meldungen bleiben |
| `qa_gate.validate_test_output` (#471) | function | bewertet die Datei danach mit `trusted=False` (30 min, 100 Byte) |
| `tdd_enforcement._resolve_artifact_path` (#1478 Teil 1) | function | Vorbild des Fallbacks; wird nicht geändert |
| `docs/specs/feat-471-auto-green.md` | spec | ursprüngliche Sicherheitsanforderungen an das GREEN-Artefakt |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| core/hooks/workflow.py | MODIFY | `_green_artifact_file`: relative Pfade über `_worktree_first_root(rel)`, Grenze gegen diese Wurzel; absolute Pfade innerhalb Worktree- oder Projekt-Root |
| tests/test_auto_green_worktree_509.py | CREATE | Worktree-Fälle, Rückfall aufs Hauptrepo, Negativfälle, Hauptrepo-Sitzung unverändert |
| CHANGELOG.md | MODIFY | Eintrag unter [Unreleased] |

### Estimated Changes

- Files: 1 neu, 2 geändert
- LoC: +15/−5 Produktion / +250 Test
- Risk Level: MEDIUM (Freigabepfad: die Prüfung bekommt eine zweite zulässige Wurzel, den eigenen Worktree; Symlink-, Ausbruch- und Gerät-Schutz bleiben gleich, die Hauptrepo-Sitzung ändert sich nicht)

## Implementation Details

**`_green_artifact_file(rel) -> Path | None`** (heute `workflow.py:3464–3482`). Die Datei wird vor allen Prüfungen nicht gelesen. Ablauf:

1. **Relativer Pfad:** `root = _worktree_first_root(rel)`. Das ist der Worktree-Root, wenn die Sitzung in einem Worktree läuft und `root / rel` dort existiert, sonst `find_project_root()`. `candidate = root / rel`. Zulässige Wurzeln: nur `root`.
2. **Absoluter Pfad:** `candidate = Path(rel)`. Zulässige Wurzeln: `_worktree_root_if_any()` (falls nicht `None`) und `find_project_root()`.
3. `os.lstat(candidate)` muss eine reguläre Datei melden (`S_ISREG`). Symlink, Ordner, FIFO, Gerät → `None`.
4. `resolved = candidate.resolve(strict=True)` muss innerhalb mindestens einer zulässigen Wurzel liegen (`is_relative_to` gegen die aufgelöste Wurzel). Sonst `None`.
5. `OSError`, `ValueError`, `RuntimeError` → `None`. Rückgabe sonst `resolved`.

Keine neue Worktree-Erkennung: Beide Wurzeln kommen aus den vorhandenen Funktionen `_worktree_first_root` und `_worktree_root_if_any` im selben Modul.

**Aufrufer unverändert.** `_auto_green_decision` behält Reihenfolge, Meldungen und Evidence (`{"artifact": <registrierter Pfad>}`). Stop-Lock und State bleiben am Hauptrepo (`find_project_root()`), weil sie geteilt sind. Docstring von `_green_artifact_file` nennt künftig „Worktree vor Hauptrepo (#509)“.

**Warum relativ nur eine Wurzel.** Ein relativer Pfad gilt für den Arbeitsbaum, in dem die Datei gefunden wurde. Ein `..`, das aus dem Worktree herausführt, wird abgelehnt, auch wenn das Ziel im Hauptrepo liegt. So kann ein Worktree unter `.claude/worktrees/<n>/` nicht per `..` auf Dateien eines anderen Arbeitsbaums zeigen.

## Expected Behavior

- **Input:** registrierter Pfad des jüngsten `test_output`-Artefakts der Phase `phase6_implement`, Sitzung im Hauptrepo oder in einem Worktree
- **Output:** In einer Worktree-Sitzung wird eine reguläre, grüne, frische Datei im Worktree gefunden → `AUTO_GREEN=done`. Symlink, Ausbruch, Nicht-Datei → weiterhin `AUTO_GREEN=human` mit der bisherigen Meldung.
- **Side effects:** keine neuen; bei `done` wie bisher `green_approved` und ein `approvals`-Eintrag, bei `human` bleibt der State byte-identisch

## Known Limitations

- Fehlt die Datei im Worktree, gilt wie bisher das Hauptrepo. Eine alte Datei am selben Pfad im Hauptrepo kann dann gewertet werden. Die Altersgrenze von 30 Minuten in `validate_test_output(trusted=False)` fängt das in der Regel ab.
- `_worktree_first_root` prüft mit `exists()`, das Symlinks folgt. Ein kaputter Symlink im Worktree führt deshalb zum Hauptrepo-Pfad. Das öffnet nichts: Auch dort muss eine reguläre Datei innerhalb des Projekts liegen.
- Die Worktree-Erkennung geht vom Arbeitsordner (`cwd`) aus, wie bei Spec und Briefing. Steht `cwd` im Hauptrepo, gilt das Hauptrepo.
- Das Worktree-zuerst-Muster gibt es weiterhin dreimal (`workflow._worktree_first_root`, `tdd_enforcement._resolve_artifact_path`, `adversary_dialog._resolve_artifact_path`), dazu zwei gleiche Worktree-Erkennungen (`workflow._worktree_root_if_any`, `hook_utils._find_worktree_root`). Sie in `hook_utils.py` zusammenzuführen ändert zwei weitere Gates und gehört in ein Folge-Issue.
- Harte Verweise (`st_nlink > 1`) werden wie bisher nicht abgelehnt (#471 hat das nicht verlangt).

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] Der im Kontext nachgestellte Fall (GREEN-Log nur im Worktree) liefert `AUTO_GREEN=done` (Test)
- [ ] `tests/test_auto_green_471.py` bleibt unverändert grün
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf `pytest tests/` grün)

## Acceptance Criteria

Testaufbau für alle Worktree-Fälle: echtes `tmp_path`, Hauptrepo mit `.git`-Ordner, State unter `<main>/.claude/workflows/`, Worktree mit `.git`-Datei (`gitdir: <main>/.git/worktrees/<n>`) und worktree-lokalem `.claude/active_workflow`, `cwd` und `CLAUDE_PROJECT_DIR` = Worktree, Auto-Modus in `<main>/openspec.yaml`, Workflow in `phase6_implement` mit `red_test_done: true`, GREEN-Log mit „3 passed“ unter `docs/artifacts/<wf>/green.log`. Kein Mock der Pfadauflösung (außer AC-11).

- **AC-1:** Given ein Worktree unter `<main>/.claude/worktrees/wt` und das GREEN-Log nur im Worktree, relativ registriert / When `workflow.py auto-green` läuft / Then `AUTO_GREEN=done`, `green_approved` ist `true` und der neue `approvals`-Eintrag hat `evidence == {"artifact": "docs/artifacts/<wf>/green.log"}`
  - Test: tests/test_auto_green_worktree_509.py::test_relative_artifact_only_in_worktree_gives_done

- **AC-2:** Given ein Worktree außerhalb des Hauptrepos (Geschwister-Ordner von `<main>`) und das GREEN-Log nur im Worktree, relativ registriert / When `workflow.py auto-green` läuft / Then `AUTO_GREEN=done`
  - Test: tests/test_auto_green_worktree_509.py::test_worktree_outside_main_repo_gives_done

- **AC-3:** Given derselbe relative Pfad im Worktree mit „1 failed“ und FAILED-Zeile und im Hauptrepo mit „3 passed“ / When `workflow.py auto-green` in der Worktree-Sitzung läuft / Then `AUTO_GREEN=human` mit Grund „nicht gruen“ bzw. „FAILED/ERROR-Zeile“ und der State bleibt byte-identisch (die Worktree-Datei gewinnt)
  - Test: tests/test_auto_green_worktree_509.py::test_worktree_copy_wins_over_main_repo

- **AC-4:** Given eine Worktree-Sitzung und das GREEN-Log nur im Hauptrepo am relativen Pfad / When `workflow.py auto-green` läuft / Then `AUTO_GREEN=done` (Rückfall aufs Hauptrepo wie bisher)
  - Test: tests/test_auto_green_worktree_509.py::test_falls_back_to_main_repo_when_absent_in_worktree

- **AC-5:** Given im Worktree ist der registrierte Pfad ein Symlink, einmal auf ein grünes Log im Worktree, einmal auf ein grünes Log außerhalb von Worktree und Hauptrepo / When `workflow.py auto-green` läuft / Then jeweils `AUTO_GREEN=human` mit dem Grund „GREEN-Artefakt fehlt, ist keine regulaere Datei oder liegt ausserhalb des Projekts“, `qa_gate.validate_test_output` wird nicht aufgerufen und der State bleibt byte-identisch
  - Test: tests/test_auto_green_worktree_509.py::test_symlink_in_worktree_gives_human

- **AC-6:** Given eine Worktree-Sitzung und (a) ein relativer Pfad mit `..`, der aus dem Worktree in einen Ordner außerhalb von Worktree und Hauptrepo führt, (b) ein relativer Pfad mit `..`, der aus dem Worktree unter `.claude/worktrees/wt` auf ein grünes Log im Hauptrepo führt, (c) ein absoluter Pfad außerhalb von Worktree und Hauptrepo / When `workflow.py auto-green` läuft / Then jeweils `AUTO_GREEN=human` mit dem Grund aus AC-5 und State byte-identisch
  - Test: tests/test_auto_green_worktree_509.py::test_path_outside_worktree_gives_human

- **AC-7:** Given im Worktree ist der registrierte Pfad ein Ordner bzw. ein FIFO / When `workflow.py auto-green` läuft / Then jeweils `AUTO_GREEN=human` mit dem Grund aus AC-5, ohne zu blockieren (Subprozess endet vor dem Timeout) und State byte-identisch
  - Test: tests/test_auto_green_worktree_509.py::test_non_regular_file_in_worktree_gives_human

- **AC-8:** Given eine Worktree-Sitzung mit Worktree außerhalb des Hauptrepos und (a) das GREEN-Log im Worktree, absolut registriert, (b) das GREEN-Log im Hauptrepo, absolut registriert / When `workflow.py auto-green` läuft / Then jeweils `AUTO_GREEN=done`
  - Test: tests/test_auto_green_worktree_509.py::test_absolute_paths_inside_worktree_or_project_give_done

- **AC-9:** Given eine Hauptrepo-Sitzung ohne Worktree (`cwd` = Hauptrepo) und (a) das GREEN-Log relativ im Hauptrepo, (b) das GREEN-Log nur unter `<main>/.claude/worktrees/wt/<relativer Pfad>` / When `workflow.py auto-green` läuft / Then (a) `AUTO_GREEN=done`, (b) `AUTO_GREEN=human` mit dem Grund aus AC-5 (die Hauptrepo-Sitzung sucht nicht in Worktrees)
  - Test: tests/test_auto_green_worktree_509.py::test_main_repo_session_unchanged

- **AC-10:** Given eine Worktree-Sitzung mit gültigem GREEN-Log im Worktree und aktivem Stop-Lock in `<main>/.claude/stop_lock.json` / When `workflow.py auto-green` läuft / Then `AUTO_GREEN=human` mit Grund „Stop-Lock aktiv“ und State byte-identisch (geteilter State bleibt am Hauptrepo)
  - Test: tests/test_auto_green_worktree_509.py::test_stop_lock_from_main_repo_applies_in_worktree

- **AC-11:** Given `workflow._worktree_first_root` ist per `monkeypatch` auf eine Funktion gesetzt, die einen Ordner `X` liefert, und unter `X/<rel>` liegt eine reguläre Datei, unter `find_project_root()/<rel>` nicht / When `workflow._green_artifact_file(rel)` läuft / Then ist das Ergebnis `(X / rel).resolve()` (die Auflösung läuft über die eine vorhandene Funktion, keine Kopie)
  - Test: tests/test_auto_green_worktree_509.py::test_green_artifact_file_uses_worktree_first_root

- **AC-12:** Given `CHANGELOG.md` / When gelesen / Then steht unter `[Unreleased]` ein Eintrag, der `#509` nennt
  - Test: tests/test_auto_green_worktree_509.py::test_changelog_mentions_509

## Test Plan

- `pytest tests/test_auto_green_worktree_509.py`
- `pytest tests/test_auto_green_471.py tests/test_tdd_enforcement_worktree_artifact_path_1478.py`
- Regressionslauf: `pytest tests/`
- `python3 -m py_compile core/hooks/workflow.py`

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Fehlerkorrektur in einer Funktion: Sie übernimmt die Wurzelwahl, die dasselbe Modul für Spec und Briefing schon nutzt (`_worktree_first_root`). Keine neue Gate-Wirkung, kein neues State-Feld, reversibel durch Rückbau der Funktion. Verworfen: (a) Logik aus `tdd_enforcement` kopieren (dritte Kopie), (b) jetzt alle drei Kopien in `hook_utils.py` zusammenführen (ändert zwei weitere Gates; eigenes Folge-Issue).

## Changelog

- 2026-11-04: Initial spec created
