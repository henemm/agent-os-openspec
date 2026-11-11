---
entity_id: fix-563-foreign-repo-commit
type: bugfix
created: 2026-11-10
updated: 2026-11-10
status: draft
version: "1.0"
workflow: fix-563-foreign-repo-commit
issue: 563
tags: [bash-gate, commit-gates, foreign-repo, fail-closed, high-risk]
---

# Commit-Gates nur für Commits im Repo des aktiven Workflows (Issue #563)

## Approval

- [ ] Approved

## Purpose

Die Workflow-Commit-Gates in `bash_gate.py` (Schritt 5: Pflichtdateien, Rebase-Pflicht, Adversary-Verdict samt Dialog-Nachweis und Abdeckung, E2E-Scope) hängen am aktiven Workflow des Sitzungsprojekts. Sie blocken deshalb auch einen `git commit`, der in einem ganz anderen Repository entsteht (`cd /anderes/repo && git commit`, `git -C /anderes/repo commit`). Dieses Repo hat mit dem Workflow nichts zu tun. Die Änderung lässt Schritt 5 nur dann entfallen, wenn sicher feststeht, dass jeder Commit des Befehls in einem Repo mit anderem `git-common-dir` entsteht; in jedem Zweifel greifen die Gates wie bisher.

## Source

- **File:** `core/hooks/bash_gate.py`
- **Identifier:** neue Funktion `_commit_in_foreign_repo(command, cwd)`; Aufrufstelle in `main()`, Schritt 5 (`if workflow_enforced and _creates_commit(command)`, ca. Z. 2058)

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `hook_utils._git_segments` | function | zerlegt den Befehl in Segmente (None bei nicht zerlegbar) |
| `hook_utils._git_subcommands_in_segment`, `_git_nested_subcommands` | function | erkennen git-Unterbefehle im Segment bzw. in verschachtelten Shells/`eval` |
| `hook_utils._looks_like_git`, `_command_env_aliases`, `_ENV_ASSIGN_RE` | function/const | erkennen git-Aufrufe, Env-Aliase und Env-Präfixe (`GIT_DIR=…`) |
| `bash_gate._creates_commit` | function | erkennt `git commit` und `git merge --continue` |
| `bash_gate._cd_bases` | function | Muster für das Nachführen der Basis über `cd`/`pushd`/`popd` (#418) |
| `git rev-parse --git-common-dir` | external | gemeinsames Git-Verzeichnis von Hauptrepo und allen Worktrees |
| `tests/test_bash_gate_worktree_commit_155.py` | test helper | Muster: echte Repos und Worktree, Hook als Subprozess |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| core/hooks/bash_gate.py | MODIFY | neue Funktion `_commit_in_foreign_repo(command, cwd)`; Schritt 5 in `main()` wird übersprungen, wenn sie True liefert |
| tests/test_bash_gate_foreign_repo_563.py | CREATE | echte temporäre Repos und Worktree, Hook als Subprozess |
| CHANGELOG.md | MODIFY | `[Unreleased]` → Fixed mit `#563` |

### Estimated Changes

- Files: 3
- LoC: +~70 Produktion, +~150 Test
- Risk Level: HIGH (Commit-Gate, Umgehungsgefahr: eine falsche „fremd“-Entscheidung öffnet das Gate für das eigene Repo)

## Implementation Details

**Ursache.** Schritt 5 in `main()` prüft nur `workflow_enforced and _creates_commit(command)`. Wohin der Commit geht, wird nicht untersucht; das Sitzungsprojekt und sein aktiver Workflow gelten für jeden Commit der Sitzung.

**Änderung.** Schritt 5 wird zu `if workflow_enforced and _creates_commit(command) and not _commit_in_foreign_repo(command, Path.cwd())`. Die Gates 5a bis 5d fallen also gemeinsam weg oder gelten gemeinsam. Alles andere bleibt: Stop-Lock (1), Schutzschritte 1b bis 1e, Marker- und State-Schutz (3a/3b), Secrets und Credentials (4/4b) laufen vor Schritt 5 und sind von der Änderung nicht berührt.

**`_commit_in_foreign_repo` liefert nur dann True, wenn bewiesen ist, dass JEDER Commit-Aufruf des Befehls in einem fremden Repo entsteht.** „Eigenes Repo“ heißt: gleiches `git rev-parse --git-common-dir` (per `realpath` verglichen) wie das Sitzungsprojekt `_root`. Hauptrepo und alle seine Worktrees teilen das common-dir und zählen damit als eigen. Ablauf:

1. Befehl mit `_git_segments` zerlegen; `None` → False.
2. Basisverzeichnis = Hook-cwd. `cd`/`pushd` mit literalem Ziel führt die Basis nach (Muster `_cd_bases`). Nicht literal (`$`, Backtick, Glob, `cd -`, `cd` ohne Ziel, `popd`) → Basis unbekannt.
3. Je Segment: Enthält es eine verschachtelte Shell oder `eval` mit Commit → False. Enthält es einen Commit-Aufruf (`commit`, oder `merge`, wenn `_creates_commit` greift), muss das Segment direkt mit `git` beginnen: kein Env-Präfix wie `GIT_DIR=…`, kein Wrapper wie `xargs`/`timeout`, kein Env-Alias. Erlaubt sind nur harmlose globale Optionen (`-C <pfad>`, `-c k=v`, `--no-pager` u. ä.). `--git-dir`, `--work-tree`, `--namespace`, `--super-prefix`, `--config-env` am Aufruf → False. Zielverzeichnis = Basis plus alle `-C`-Pfade kumulativ (relativ zum jeweils vorigen).
4. Ziel muss existieren und für `git rev-parse --git-common-dir` ein Ergebnis liefern; sonst False.
5. common-dir des Ziels (realpath) gleich dem common-dir von `_root` → False (eigenes Repo).
6. Wurde kein einziger Commit-Aufruf erkannt (etwa Teilstring-Fallback der Commit-Erkennung) → False.
7. Jede Ausnahme in der Funktion → False.

True ergibt sich nur, wenn mindestens ein Commit-Aufruf erkannt wurde und alle erkannten Aufrufe Schritt 3 bis 5 mit „fremd“ bestehen. Ein gemischter Befehl (eigenes Repo und fremdes Repo) ist damit gegated.

**Fail-closed ist die tragende Eigenschaft.** Die Funktion kennt nur einen Weg zu True. Alles Unklare, Unlesbare oder Unerwartete endet in False, also im heutigen Verhalten. Die Änderung kann dadurch nie mehr blocken als bisher; sie kann nur in klar belegten Fällen weniger blocken.

**Tests.** Hook als Subprozess gegen echte temporäre Git-Repos (Muster `tests/test_bash_gate_worktree_commit_155.py`): Sitzungsrepo mit Workflow-State `phase6_implement`, `workflow_type: feature`, ohne Verdict; ein zweites, unabhängiges Repo als „fremd“; ein Worktree des Sitzungsrepos. Die Env-Variablen `CLAUDE_PROJECT_DIR` und `OPENSPEC_ACTIVE_WORKFLOW` werden aus der Subprozess-Umgebung entfernt. Kein Mock von Shell oder git.

## Expected Behavior

- **Input:** Ein `git commit`-Befehl (oder `git merge --continue`) in einer Bash-Hook-Eingabe, während ein Workflow ab phase6 ohne Adversary-Verdict aktiv ist.
- **Output:** Entsteht jeder Commit des Befehls sicher in einem Repo mit anderem `git-common-dir`, endet der Hook mit Exit 0 (Schritt 5 entfällt). In allen anderen Fällen gelten die Gates unverändert (Exit 2 mit der bisherigen Meldung).
- **Side effects:** Keine. Stop-Lock, Secrets-Prüfung, Marker- und State-Schutz wirken in jedem Fall wie bisher, auch beim Commit in ein fremdes Repo.

## Known Limitations

- Ein Submodul des eigenen Repos hat ein eigenes `git-common-dir` und zählt als fremd; ein Commit darin ist also nicht gegated. Der Zeiger-Commit im eigenen Repo (der Commit im Hauptrepo, der den neuen Submodul-Stand festschreibt) bleibt gegated.
- Ein `cd` in ein per Symlink erreichbares Verzeichnis wird über `realpath` aufgelöst; maßgeblich ist das echte Zielrepo.
- Commits über Wrapper oder Env-Präfix in fremde Repos (`GIT_DIR=… git commit`, `xargs git commit`, `timeout 5 git commit`, `bash -c "cd fremd && git commit"`) bleiben konservativ geblockt. Ausweg: den Commit-Befehl direkt schreiben (`git -C <fremd> commit` bzw. `cd <fremd> && git commit`).
- `git rev-parse --git-common-dir` verlangt ein Repo; ein Zielverzeichnis ohne Git-Repo gilt als nicht belegt und bleibt gegated.

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test in `tests/test_bash_gate_foreign_repo_563.py` belegt
- [ ] `cd <fremd> && git commit` und `git -C <fremd> commit` werden bei Workflow in phase6 ohne Verdict nicht mehr geblockt (AC-1, AC-2, AC-8)
- [ ] Commits im eigenen Repo, in dessen Worktrees und gemischte Befehle bleiben gegated (AC-3, AC-4, AC-5)
- [ ] Alle unsicheren Formen bleiben gegated (fail-closed, AC-6)
- [ ] Stop-Lock und Secrets-Prüfung gelten weiter auch beim Commit in ein fremdes Repo (AC-7)
- [ ] CHANGELOG `[Unreleased]` → Fixed nennt `#563`
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf `pytest tests/` grün, insbesondere `test_bash_gate_worktree_commit_155.py` und die Adversary-Gate-Tests)
- [ ] Mindestens zwei Adversary-Runden (Risiko HOCH), Verdict VERIFIED mit gültigem Dialog-Nachweis

## Acceptance Criteria

Testaufbau: echte Repos in `tmp_path`, Hook als Subprozess, Workflow-State `phase6_implement` mit `workflow_type: feature` ohne Verdict, Env `CLAUDE_PROJECT_DIR` und `OPENSPEC_ACTIVE_WORKFLOW` entfernt.

- **AC-1:** Given ein Sitzungsrepo mit Workflow in phase6 ohne Verdict und ein unabhängiges fremdes Repo / When der Befehl `cd <fremd> && git commit -m x` geprüft wird / Then endet der Hook mit Exit 0
  - Test: tests/test_bash_gate_foreign_repo_563.py::test_cd_into_foreign_repo_then_commit_is_allowed

- **AC-2:** Given dieselbe Ausgangslage / When `git -C <fremd> commit -m x` geprüft wird / Then endet der Hook mit Exit 0
  - Test: tests/test_bash_gate_foreign_repo_563.py::test_git_dash_c_foreign_repo_commit_is_allowed

- **AC-3:** Given dieselbe Ausgangslage, Hook-cwd im Sitzungsrepo / When ein nackter `git commit -m x` geprüft wird / Then endet der Hook weiter mit Exit 2 (Adversary-Verdict fehlt)
  - Test: tests/test_bash_gate_foreign_repo_563.py::test_bare_commit_in_own_repo_stays_blocked

- **AC-4:** Given Sitzungsrepo mit einem Worktree (gleiches `git-common-dir`) / When `git -C <eigener Worktree> commit -m x` geprüft wird, und aus einer Worktree-Sitzung `cd <Hauptrepo> && git commit -m x` / Then endet der Hook jeweils weiter mit Exit 2
  - Test: tests/test_bash_gate_foreign_repo_563.py::test_commit_in_own_worktree_or_main_repo_stays_blocked

- **AC-5:** Given dieselbe Ausgangslage / When ein gemischter Befehl wie `git commit -m x && git -C <fremd> commit -m y` (und in umgekehrter Reihenfolge) geprüft wird / Then endet der Hook mit Exit 2, weil nicht jeder Commit fremd ist
  - Test: tests/test_bash_gate_foreign_repo_563.py::test_mixed_own_and_foreign_commit_stays_blocked

- **AC-6:** Given dieselbe Ausgangslage / When eine unsichere Form geprüft wird (`GIT_DIR=<fremd>/.git git commit`, `git --git-dir=<fremd>/.git commit`, `git --work-tree=<fremd> commit`, `bash -c "cd <fremd> && git commit"`, `cd $X && git commit`, `cd <fremd> && xargs git commit`, `git -C <nicht existierend> commit`, `git -C <Verzeichnis ohne Repo> commit`, nicht zerlegbarer Befehl mit offenem Anführungszeichen) / Then endet der Hook jeweils mit Exit 2 (fail-closed)
  - Test: tests/test_bash_gate_foreign_repo_563.py::test_unsafe_forms_stay_blocked_fail_closed

- **AC-7:** Given Stop-Lock gesetzt bzw. ein Befehl, der ein Secret liest oder ausgibt / When der Commit in ein fremdes Repo geprüft wird (`git -C <fremd> commit`) / Then blockt der Hook weiter mit Exit 2 (Stop-Lock-Meldung bzw. Secrets-Prüfung), die Ausnahme gilt nur für Schritt 5
  - Test: tests/test_bash_gate_foreign_repo_563.py::test_stop_lock_and_secrets_still_block_in_foreign_repo

- **AC-8:** Given die Hook-cwd liegt selbst in einem fremden Repo (persistentes `cd` der Sitzung) / When ein nackter `git commit -m x` geprüft wird / Then endet der Hook mit Exit 0
  - Test: tests/test_bash_gate_foreign_repo_563.py::test_bare_commit_with_cwd_in_foreign_repo_is_allowed

## Test Plan

Automatische Tests (jeweils an eine AC oben gebunden, TDD RED vor der Implementierung):

- Test: GIVEN Workflow phase6 ohne Verdict WHEN `cd <fremd> && git commit` THEN Exit 0 (AC-1)
- Test: GIVEN dieselbe Lage WHEN `git -C <fremd> commit` THEN Exit 0 (AC-2)
- Test: GIVEN dieselbe Lage WHEN nackter `git commit` im Sitzungsrepo THEN Exit 2 (AC-3)
- Test: GIVEN Worktree des Sitzungsrepos WHEN `git -C <Worktree> commit` und `cd <Hauptrepo> && git commit` aus Worktree-Sitzung THEN Exit 2 (AC-4)
- Test: GIVEN gemischter Befehl eigen plus fremd, beide Reihenfolgen WHEN geprüft THEN Exit 2 (AC-5)
- Test: GIVEN Env-Präfix, `--git-dir`, `--work-tree`, verschachtelte Shell, `$`-Ziel, Wrapper, fehlendes Ziel, Nicht-Repo, offenes Anführungszeichen WHEN geprüft THEN jeweils Exit 2 (AC-6)
- Test: GIVEN Stop-Lock bzw. Secret-Zugriff WHEN `git -C <fremd> commit` THEN Exit 2 (AC-7)
- Test: GIVEN Hook-cwd in fremdem Repo WHEN nackter `git commit` THEN Exit 0 (AC-8)

Ausführung:

- Neue Datei: `pytest tests/test_bash_gate_foreign_repo_563.py`
- Betroffene bestehende Tests: `pytest tests/test_bash_gate_worktree_commit_155.py` und die Tests zu Adversary-Verdict, Dialog-Nachweis und Abdeckung (#253, #259)
- TDD RED: Die neue Testdatei muss vor der Implementierung fehlschlagen (AC-1, AC-2, AC-8 liefern heute Exit 2)
- Regressionslauf: `pytest tests/` (lokal im venv mit `pytest` und `pyyaml`)
- Risiko HOCH: mindestens zwei Adversary-Runden mit Fokus auf Umgehungsformen (Shell-Syntax, Quoting, Symlinks, Worktrees)

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Das Repo führt keine ADR-Sammlung, vergleichbare Gate-Fixes (#522, #562, #566) haben bewusst keine ADR eingetragen. Die Änderung führt keine neue Regel ein, sondern präzisiert den Geltungsbereich eines bestehenden Gates (Commit-Gates gelten für das Repo des Workflows). Die Wahl des `git-common-dir` als Vergleichsmaß (statt Toplevel) folgt zwingend daraus, dass Worktrees zum eigenen Repo gehören, und ist in Implementation Details begründet.

## Changelog

- 2026-11-10: Initial spec created
