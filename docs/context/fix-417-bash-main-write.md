# Context: fix-417-bash-main-write

## Request Summary
Eine Worktree-Sitzung darf per Bash nicht in den Haupt-Ordner schreiben, genauso wenig wie per Edit/Write (Issue #417, Epic #429, Meilenstein 3.41).

## Befund (belegt)
- `core/hooks/worktree_write_guard.py:48` liest nur `tool_input.file_path`; er ist nur für Edit|Write|MultiEdit registriert (`hooks/hooks.json:40`). Bash hat dort keinen Wächter.
- `core/hooks/bash_gate.py:1140` ruft `_writes_effective_config` auf. Das prüft Schreibziele nur gegen die EINE wirksame Config-Datei (`bash_gate.py:539`, aus #410/#418).
- `core/hooks/secret_egress_guard.py:381` (`_is_outside_safe_zone`) rechnet den Haupt-Ordner zur Sicherheitszone, weil `find_project_root()` Worktrees bewusst auf den Haupt-Ordner auflöst (`hook_utils.py:1371`). Umleitungen in den Haupt-Ordner fallen dadurch durch.

## Related Files
| File | Relevanz |
|------|----------|
| `core/hooks/bash_gate.py` | Kern-Gate Bash; enthält schon die Schreibziel-Erkennung (`_split_redirects`, `_command_args`, `_CONFIG_WRITERS` für cp/mv/tee/sed -i/perl -i/dd/touch/truncate/rm/ln/yq/git, `_cd_bases` für cd/pushd). Ort der Änderung. |
| `core/hooks/worktree_write_guard.py` | Referenzverhalten für Edit/Write: Main-Repo gesperrt, eigener Worktree frei, fail-open bei Fehler. Pfad-Regex `.claude/worktrees/<name>`. |
| `core/hooks/secret_egress_guard.py` | Eigene Umleitungs-Erkennung (`_shell_write_targets`), aber mit Sicherheitszone = Projekt inkl. Haupt-Ordner. Nicht der richtige Ort. |
| `core/hooks/hook_utils.py` | `find_worktree_root()` (Worktree selbst) vs. `find_project_root()` (Haupt-Ordner); `find_main_repo_from_worktree`. |
| `tests/test_bash_gate_config_lock_418.py`, `tests/test_bash_gate_state_integrity_410.py` | Muster: echtes Gate als Subprozess, `_worktree_sandbox` (Haupt-Ordner + echter Worktree), `_expect`/`_assert_blocked`. Neue Tests hier andocken. |

## Existing Patterns
- Hook-Entwicklung (CLAUDE.md): Phase-/Commit-/Schreib-Checks gehören in die 4 Kern-Gates, kein neuer Hook ohne eigenes Event. Bash-Schreibschutz gehört also in `bash_gate.py`, nicht in eine neue Datei.
- Kein geteilter Import zwischen den Guards (bewusste Parallel-Kopien, siehe `_strip_trailing_shell_noise`).
- Ausweg bei Schutz-Blöcken: Override-Token ("override"), `_any_override_token()`.
- Schreibziele werden gegen eine mit `cd` nachgeführte Basis aufgelöst (`_cd_bases`); nicht auflösbar heißt: kein neuer Block-Grund (fail-open).

## Dependencies / Dependents
- Upstream: `_git_segments`, `_split_redirects`, `_config_write_targets`, `find_worktree_root`, `find_main_repo_from_worktree`.
- Downstream: jeder Bash-Aufruf in jedem Konsumenten-Projekt. Ein Fehlalarm blockiert legitime Arbeit.

## Offene Punkte für die Analyse
- Ausnahmen: `workflow.py`-Aufrufe schreiben `.claude/workflows/` im Haupt-Ordner aus Python heraus (kein Umleitungsziel, sollte also nicht betroffen sein). Prüfen: `git`-Befehle (Commits schreiben in `<main>/.git/worktrees/...`), `gh`, `claude`-Hilfsskripte mit absoluten Haupt-Ordner-Pfaden als Argument.
- Nur lesende Befehle (`cat <main>/x`, `cp <main>/x ./`) müssen frei bleiben; nur echte Schreibziele zählen.
- Außerhalb von Worktrees (normaler Haupt-Ordner-Betrieb) darf sich nichts ändern.
- Pfad-Tricks: `../../..`, `~`, Symlinks; nicht auflösbar → fail-open wie bisher.
- Kill-Switch/Override: Override-Token wie bei #410 als Ausweg.

## Risks & Considerations
- Gate-Code, hohes Risiko: Adversary mit mindestens 2 Runden.
- Scope-Grenze: Dies ist ein Schutz vor Versehen und gedankenlosem Umgehen, kein Sandbox-Ersatz (Bash-Text-Erkennung bleibt umgehbar, z. B. über `python -c`); das gehört in die Spec als ausdrückliche Nicht-Ziel-Aussage.

## Analysis

### Type
Bug (Sicherheits-Schutzlücke, Gate-Code)

### Befund bestätigt
Die Erkennung echter Schreibziele existiert bereits (`bash_gate.py`: `_split_redirects` :365, `_command_args` :390, `_CONFIG_WRITERS` :500, `_config_write_targets` :512, `_cd_bases` :526) und wird in `_writes_effective_config` (:539) nur gegen EINE Datei verglichen. Der Block in Schritt 1b (:1140) ist der Andockpunkt. Die Worktree-Erkennung des Edit/Write-Wächters (`_WORKTREE_RE`, `worktree_write_guard.py:19`) lässt sich als cwd-Regex übernehmen.

### Affected Files (with changes)
| File | Change Type | Description |
|------|-------------|-------------|
| core/hooks/bash_gate.py | MODIFY | Hilfsfunktion „Schreibziele je Segment mit cd-Basis“ herausziehen; neue `_writes_main_repo(segments, cwd)`; neuer Block 1c neben 1b mit Override-Ausweg |
| tests/test_bash_gate_main_write_417.py | CREATE | Echtes Gate als Subprozess, `_worktree_sandbox` wie in den #418-Tests; je Schreibweise ein Test |
| CHANGELOG.md | MODIFY | Eintrag unter [Unreleased] |
| docs/specs/... | CREATE | Spec (Phase 3) |

### Technical Approach
1. Nur aktiv, wenn cwd in einem Pfad der Form main/.claude/worktrees/NAME liegt (sonst unverändert; kein Effekt im Haupt-Ordner-Betrieb).
2. Ziele wie in #418: Umleitung, cp/mv/install/ln, tee, sed -i, perl -i, dd of=, touch, truncate, rm, yq -i, git checkout/restore/rm/mv. Lese-Quellen zählen nie. Auflösung gegen cd-Basen, `~` und `..`, per resolve() (Symlinks).
3. Blockiert, wenn das aufgelöste Ziel unter dem Haupt-Ordner liegt, aber NICHT unter dem eigenen Worktree (der liegt physisch im Haupt-Ordner!). Fremde Worktrees bleiben gesperrt, wie beim Write-Wächter.
4. Nicht auflösbar / Fehler: fail-open. Ausweg: Override-Token (`_any_override_token`).
5. Kein neuer Hook, keine neue Datei (Hook-Konvention). Die #410-Config-Sperre bleibt als Spezialfall mit gezielterer Meldung bestehen.

### Beantwortete Fragen aus dem Issue
- workflow.py-Aufruf: kein Umleitungsziel/Writer-Befehl, also nicht betroffen. Im Test abdecken.
- git commit / gh: Ziele sind keine Argument-Tokens, also frei. git checkout|restore|rm|mv mit Pfad in den Haupt-Ordner wird geblockt (gewollt).
- Lesen (cat main/x, cp main/x ./) bleibt frei: nur Ziele zählen.
- Direktes Schreiben nach .claude/workflows/ ist ohnehin durch State-Integrity geschützt; keine Sonderausnahme nötig.

### Scope Assessment
- Files: 2 Code/Test (+ Spec, Changelog)
- Estimated LoC: +60/-15 Gate, +150 Tests
- Risk Level: HIGH (Kern-Gate, jeder Bash-Aufruf in jedem Konsumenten-Projekt; Fehlalarm blockiert Arbeit). Adversary mind. 2 Runden.

### Dependencies
Upstream: `_git_segments`, `_config_write_targets`, `_cd_bases`, `_any_override_token`. Downstream: alle Worktree-Sitzungen.

### Nicht-Ziele
Kein Sandbox-Ersatz: `python -c`, `sh -c` mit Variablen und Skripte, die selbst schreiben, bleiben unerkannt. Schutz vor Versehen, nicht vor Absicht.

### Open Questions
- [ ] Hängt die Sperre am Projekt-Schalter `framework_disabled()`? Empfehlung: nein, wie 1b immer aktiv (Schutz, kein Workflow-Zwang).
- [ ] Testfall Worktree-Pfad mit Leerzeichen abdecken (Regex `[^/]+`).
