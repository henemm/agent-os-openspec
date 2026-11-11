# Context: fix-563-foreign-repo-commit

## Request Summary
Issue #563: Die Workflow-Commit-Gates in `bash_gate.py` (Schritt 5) blocken auch einen
`git commit`, der in einem **fremden** Repository entsteht (`cd /anderes/repo && git commit`,
`git -C /anderes/repo commit`), weil sie nur am aktiven Workflow des Sitzungsprojekts hängen.
Soll: Commit-Gates nur für Commits im Repo des aktiven Workflows (Hauptrepo + seine Worktrees);
Secrets- und Stop-Lock-Prüfung gelten weiter überall.

## Related Files
| File | Relevance |
|------|-----------|
| `core/hooks/bash_gate.py` `main()` Schritt 5 (~Z. 2057) | Einstieg `if workflow_enforced and _creates_commit(command)` — hier fehlt die Zielrepo-Prüfung |
| `core/hooks/bash_gate.py` `_creates_commit` (~Z. 1476) | erkennt `git commit` und `git merge --continue` |
| `core/hooks/bash_gate.py` `_cd_bases` / `_segment_write_targets` (~Z. 575) | bestehendes Muster: Basis über `cd`/`pushd`/`popd` nachführen (#418) |
| `core/hooks/bash_gate.py` `_measurement_root` (~Z. 176) | Arbeitsbaum der Sitzung (Worktree oder Hauptrepo) |
| `core/hooks/hook_utils.py` `_git_segments`, `_git_subcommand_after`, `_git_subcommands_in_segment`, `_git_nested_subcommands`, `_GIT_OPTS_WITH_VALUE`, `_ENV_ASSIGN_RE`, `_GIT_COMMAND_PREFIXES`, `_looks_like_git` | Tokenisierung und git-Aufruferkennung (#1431, #281, #297) |
| `core/hooks/adversary_dialog.py` `run_git`, `git_toplevel` | git-Aufrufe mit probe/fail-closed |
| `tests/test_bash_gate_worktree_commit_155.py` | Testmuster: echte Repos + Worktree, Hook als Subprozess |

## Existing Patterns
- Hook-Tests laufen als Subprozess gegen echte temporäre Git-Repos (kein Mocking).
- Unauflösbare Ziele (`$VAR`, Glob, Backtick, `cd -`) werden beim Schutz konservativ behandelt.
- `git_subcommands` erkennt `-C`, `--git-dir`, Env-Aliase und verschachtelte Shells.

## Dependencies
- Upstream: `hook_utils` Lexer, `git rev-parse --git-common-dir` (git ≥ 2.31 für `--path-format=absolute`; Container: 2.43).
- Downstream: Jeder Commit aus jeder Sitzung jedes Konsumenten-Projekts läuft durch Schritt 5.

## Existing Specs
- `docs/specs/bash-gate-false-positive-fix.md` (Erkennungslogik), #259 Abdeckung, #253 Dialog-Nachweis.

## Risks & Considerations
- **Umgehungsrisiko:** Erkennung „fremdes Repo" darf nie für das eigene Repo greifen — Worktrees teilen das
  `git-common-dir` mit dem Hauptrepo, Vergleich daher über `--git-common-dir`, nicht Toplevel.
- Unsicherheit (verschachtelte Shell, `--git-dir`/`--work-tree`, `GIT_DIR=`-Präfix, nicht auflösbares `cd`,
  nicht existierendes Ziel, nicht zerlegbares Kommando, Env-Alias statt `git`) → Gates greifen (fail-closed).
- Mehrere Commits in einem Befehl: Gates entfallen nur, wenn **jeder** Commit fremd ist.
- Persistentes `cd` der Bash-Sitzung: Hook-cwd = Sitzungs-cwd; liegt es in einem fremden Repo, ist ein
  nackter `git commit` ebenfalls fremd.
- Secrets (Schritt 4), Stop-Lock (1) und Schutzschritte 1b–1e bleiben unberührt.

## Analysis

### Type
Bug (reproduziert 2026-11-10: Projekt in phase6 ohne Verdict; `cd <fremd> && git commit` und
`git -C <fremd> commit` → Exit 2 „Adversary verdict missing"; Ursache `core/hooks/bash_gate.py`
Schritt 5, Bedingung `workflow_enforced and _creates_commit(command)` ohne Zielrepo-Prüfung).

### Affected Files (with changes)
| File | Change Type | Description |
|------|-------------|-------------|
| core/hooks/bash_gate.py | MODIFY | neue Funktion `_commit_in_foreign_repo(command, cwd)`; Schritt 5 überspringt Gates, wenn sie True liefert |
| tests/test_bash_gate_foreign_repo_563.py | CREATE | echte Repos + Worktree, Hook als Subprozess |
| CHANGELOG.md | MODIFY | `[Unreleased]` Fixed |

### Scope Assessment
- Files: 3
- Estimated LoC: +70 Code / +150 Test
- Risk Level: HIGH (Commit-Gate, Umgehungsgefahr)

### Technical Approach
`_commit_in_foreign_repo` liefert nur dann True, wenn sicher bestimmbar ist, dass JEDER
Commit-Aufruf des Befehls in einem Repo mit anderem `git rev-parse --git-common-dir` als das
Sitzungsprojekt (`_root`) entsteht. Ablauf:
1. `_git_segments` zerlegen; None → False.
2. Basis = cwd; `cd`/`pushd` mit literalem Ziel führt die Basis nach; nicht auflösbar
   (`$`, Backtick, Glob, `cd -`, `cd` ohne Ziel, `popd`) → Basis unbekannt.
3. Je Segment: enthält es eine verschachtelte Shell/`eval` mit Commit → False. Enthält es
   (`_git_subcommands_in_segment`) `commit` oder `merge` (bei `_creates_commit`) → Segment muss
   direkt mit `git` beginnen (keine Env-Präfixe wie `GIT_DIR=`, keine Wrapper) und darf nur
   `-C <pfad>`, `-c k=v`, `--no-pager` u. ä. tragen; `--git-dir`, `--work-tree`, `--namespace`,
   `--super-prefix`, `--config-env` → False. Zielverzeichnis = Basis + alle `-C` (kumulativ).
4. Ziel muss existieren und `git rev-parse --git-common-dir` liefern; sonst False.
5. Vergleich (realpath) mit common-dir von `_root`; gleich → False.
6. Kein einziger Commit-Aufruf gefunden (z. B. Fall-3-Erkennung per Teilstring) → False.
Fail-closed: jede Ausnahme → False (Gates laufen wie bisher).

### Dependencies
`hook_utils` (`_git_segments`, `_git_subcommands_in_segment`, `_git_nested_subcommands`,
`_looks_like_git`, `_command_env_aliases`), `subprocess` git.

### Open Questions
- keine (Soll im Issue eindeutig; Submodul des eigenen Repos zählt als fremdes Repo — eigener
  common-dir; der Zeiger-Commit im eigenen Repo bleibt gegated → Known Limitation).
