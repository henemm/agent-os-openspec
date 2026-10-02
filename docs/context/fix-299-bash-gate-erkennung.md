# Context: fix-299-bash-gate-erkennung

## Request Summary

Sammel-Issue #299 (Epic #200): `bash_gate.py` erkennt Commit, geschützte Pfade und Whitelist nur per
Text-Mustererkennung auf dem rohen Bash-String. Jeder neue Schreibweise-Fund (#281 Alias, #296
Whitelist-Abkürzung, #297 „reines git“ führt Code aus / Commit ohne `commit`, #298 `bash -lc`,
#304 Umleitung/Option vor dem Unterbefehl) ist dieselbe Wurzel. Dazu #284: Rebase-Pflicht verlangt
einen Zustand, den das vorherige Vormerken ausschließt. Henning will die Epics abschließen
(Memory `epics-zu-ende-bringen`), also eine strukturelle Lösung statt weiterer Einzelflicken.

## Related Files

| File | Relevance |
|------|-----------|
| `core/hooks/bash_gate.py` (813 Z.) | `main()` Z. 622–809: 1 Stop-Lock, 2 Git-Schnellpfad (`is_pure_git_command`), 3a Marker-Schutz, 3b State-Integrity + Whitelist-`allow()` (Z. 703–704, #296), 4/4b Secrets, 5 Commit-Gates (5a Pflichtdateien, 5b Rebase-Pflicht Z. 750–771 = #284, 5c Adversary-Verdict + `_require_dialog_evidence`, 5d E2E-Scope) |
| `core/hooks/hook_utils.py` | Git-Zerlegung: `_git_lex`, `_git_segments`, `_git_subcommand_after` (Z. 93, #304), `_GIT_OPTS_WITH_VALUE` (Z. 80), `_git_nested_subcommands` (Z. 144, nur `-c` direkt nach Shell-Binary = #298), `git_subcommands`, `is_git_subcommand`, `is_pure_git_command` |
| `core/hooks/adversary_dialog.py` | `check_dialog_evidence`, `required-files` — von 5c aufgerufen (#253/#259) |
| `core/hooks/workflow.py` | Übergang nach Phase 8 prüft Verdict + Abdeckung unabhängig vom Commit-Weg (gegen `base_commit`/merge-base) |
| `scripts/ci_spec_gate.py` + `.github/workflows/spec-gate.yml` | Serverseitiges Gate: sieht nur committete Dateien; Workflow-State (`.claude/workflows/`) ist gitignored |
| `tests/test_git_invocation_detection.py` | Sandbox-Muster (`_sandbox`, aktiver Workflow phase6 ohne Verdict) für Commit-Erkennung |
| `tests/test_bash_gate_*.py` (3 Dateien) | Falsch-Positive, Freitext (#64/#75), Worktree-Commit (#155) — Regressionsschutz |

## Vorarbeit, die existiert (wichtig)

- **PR #291 (Draft, Zweig `claude/friendly-galileo-7gssiz`)** — #281 Alias-Resolver, Full Process.
  Enthält Kontext (381 Z.), Spec (834 Z., 17 ACs), PO-Briefing, RED-Tests (798 Z.). Die
  Implementierung (neues `core/hooks/git_alias.py`) lag nur lokal in einer Cloud-Sitzung und ist
  **nicht gepusht**. Adversary: Runde 1 BROKEN (17 Funde), Runde 2 BROKEN (F018–F020 Umgehungen über
  verschleierte Befehlsformen, F024 Über-Erkennung bei Heredoc-Prosa). Danach Stillstand.
- Das ist der Beleg für die Kernthese von #299: Text-Parsing der Shell-Syntax ist nach oben offen.
  Selbst ein sorgfältig spezifizierter Resolver mit 17 ACs fand in zwei Runden kein Ende.

## Existing Patterns

- Tokenbasierte Git-Erkennung seit Issue #1431 (statt `startswith("git ")`).
- „Im Zweifel prüfen“ (Drei-Fälle-Regel in `hook_utils`) — nicht zerlegbare Befehle gelten konservativ.
- Gates prüfen den echten Zustand dort, wo er existiert: 5a/5c lesen `git diff --cached`,
  `adversary_dialog` hasht Dateien; Phase 8 misst gegen die Basis, unabhängig vom Commit-Weg.
- Fail-open bei Infrastrukturfehlern (kein Netz → 5b still übersprungen).

## Dependencies

- Upstream: `hook_utils` (Zerlegung), `adversary_dialog`, `override_token`, `config_loader`, git-CLI.
- Downstream: jedes Konsumenten-Projekt (Plugin- und Copy-Modus), alle Agenten-Commits.

## Existing Specs

- `docs/specs/fix-253-adversary-evidence-gate.md` — VERIFIED nur mit gestempeltem Dialog
- `docs/specs/fix-259-adversary-diff-binding.md` — Abdeckung der Änderungsmenge; Known Limitation „vorsätzlich manipuliertes git“
- PR #291: `docs/specs/fix-281-git-alias-commit-gate.md` (nicht auf main)

## Recherche (extern)

- Git `pre-commit`/`commit-msg` lassen sich per `--no-verify` überspringen; der
  `reference-transaction`-Hook läuft bei jeder Ref-Änderung (auch `merge`, `cherry-pick`, `am`,
  `update-ref`) und kann im Zustand `prepared` die Transaktion abbrechen — nicht per `--no-verify`
  umgehbar ([githooks(5)](https://kernel.org/pub/software/scm/git/docs/githooks.html),
  [Patch „refs: implement reference transaction hook“](https://code.googlesource.com/git/+/675415976704459edaf8fb39a176be2be0f403d8%5E%21/)).
  Neuere git-Versionen kennen eine interne Option zum Überspringen (`958fbc74e3 refs: allow skipping
  the reference-transaction hook`) — zu prüfen, ob sie von außen erreichbar ist.
- Praxisbericht zu Agenten, die Commit-Prüfungen umgehen: Regex-Hooks fangen die offensichtlichen
  Formen, ein PATH-Shim scheitert an `/usr/bin/git`, **CI ist der eigentliche Backstop**, weil der
  Agent ihn nicht lokal abschalten kann ([pydevtools: How to stop AI agents from bypassing pre-commit hooks](https://pydevtools.com/handbook/how-to/how-to-stop-ai-agents-from-bypassing-pre-commit-hooks/)).

## Lösungsrichtungen für /20-analyse (noch keine Entscheidung)

1. **Bedrohungsmodell klären (Regelweg vorn):** Das Gate schützt vor *versehentlichem* Überspringen
   durch Claude (Normalform `git commit`, `git -C … commit`, `bash -lc "git commit"`, Umleitung),
   nicht vor vorsätzlicher Verschleierung. Dann reicht eine robuste Normalform-Erkennung plus
   Schließen der Struktur-Lücken (#296 Whitelist nur für 3b, #298, #304), und Alias/Code-Ausführung
   (#281/#297) gehen als Known Limitation an den Backstop.
2. **Backstop am echten Ereignis:** Phase-8-Übergang prüft schon unabhängig vom Commit-Weg. Ergänzend
   CI: Adversary-Nachweis (gestempeltes `adversary-dialog.md`, committet) im PR prüfen — analog
   `ci_spec_gate.py`. Unumgehbar lokal, braucht keinen Shell-Parser.
3. **Git-Hook (`reference-transaction`/`pre-commit`) installiert durch das Plugin:** fängt jeden
   Commit-Weg inkl. Alias/merge/cherry-pick; braucht Installation pro Projekt, kollidiert mit
   husky/pre-commit, `core.hooksPath` per `-c` überschreibbar.
4. **Resolver aus PR #291 fertigstellen:** höchster Aufwand, zweimal BROKEN, nach oben offen.

## Risks & Considerations

- Kern-Gate für alle Konsumenten: Über-Blockierung stoppt jeden Commit, Unter-Blockierung öffnet #253/#259.
- #284 ist kein Erkennungsproblem, sondern Reihenfolge: 5b blockt bei vorgemerkten Dateien mit
  einem Rat (`git rebase`), der bei nicht leerem Index scheitert. Lösung muss den Index-Zustand
  berücksichtigen (z. B. `git rebase --autostash` nennen oder 5b nur bei überlappenden Dateien).
  Der zweite Befund in #284 (`sync-main` aus keiner Sitzung erreichbar) gehört zu #185/#169, nicht hierher.
- PR #291 muss am Ende geschlossen oder verwertet werden (Tests sind wiederverwendbar).
- Scoping-Limit ±250 LoC: Richtung 3 oder 4 sprengt es sicher; Richtung 1+2 voraussichtlich nicht.
- `core/hooks/` ist Infrastruktur: Implementierung braucht Override-Token.

## Analysis

### Type
Bug (Gate-Umgehungen), Sammel-Vorgang. Alle Fälle am echten `bash_gate.py` reproduziert (Wegwerf-Repo,
Workflow phase6 ohne Verdict; Skripte `repro299.py`, `repro299b.py`, `repro284.py` im Sitzungs-Scratchpad):

| Befehl | rc heute | Soll | Issue |
|---|---|---|---|
| `git commit -m x` / `git -C . commit` / `bash -c "git commit"` | 2 | 2 | Kontrolle |
| `git commit -m x -- .claude/workflows/<wf>.json` | 0 | 2 | #296 |
| `git add .claude/settings.json && git commit -m x` | 0 | 2 | #296 |
| `git status && sed -i … .claude/workflows/<wf>.json` | 0 | 2 | Nebenbefund (Whitelist „irgendein Segment“, `bash_gate.py:_whitelist_matches`) |
| `git add x && sed -i … .claude/workflows/<wf>.json` | 0 | 2 | dto. |
| `bash -lc` / `sh -ec` / `bash --login -c "git commit -m x"` | 0 | 2 | #298 |
| `git >/dev/null commit -m x`, `git --attr-source HEAD commit -m x` | 0 | 2 | #304 |
| `git 2>&1 commit -m x` (`is_git_subcommand` → False) | 0 | 2 | Nebenbefund (`&`-Umleitungen als Trenner) |
| `git status 2>&1` (`is_pure_git_command` → False, Über-Erkennung) | – | rein git | Nebenbefund |
| `git -c alias.ci=commit ci -m x` | 0 | 2 | #281 (Teil B) |
| `git merge`, `git cherry-pick`, `git -c core.pager='sh -c …' log` | 0 | s. Teil B | #297 (Teil B) |
| #284: Rückstand + vorgemerkte Datei → Gate rät `git rebase origin/main` → „index contains uncommitted changes“; `git rebase --autostash origin/main` gelingt, Vormerkung bleibt | | | #284 |

### Entscheidung Tech Lead: Schnitt in zwei Teile (Scope-Limit ±250 LoC)

Gesamt ca. 185 Prod + 320 Test LoC → über dem Limit. Deshalb:

- **Teil A = dieser Workflow:** #296 inkl. Whitelist-Nebenbefund, #298, #304 inkl. `&`-Umleitungen, #284.
  Reine Struktur-/Zerlegungs-Fixes, kein neuer Subprozess. Ca. 75 Prod + 170 Test.
- **Teil B = nächster Workflow unter #299:** #281 schlank (eine `git config --get-regexp '^alias\.'`-Abfrage,
  nur im Fast-Path-Fall, fail-open, Kette mit Tiefenlimit, `!`-Alias = nicht rein git) und #297
  (merge/cherry-pick/revert/am/pull zählen NICHT als Commit — merge ist der legitime Weg aus der
  Rebase-Pflicht, Phase 8 fängt Code ab; gefährliche `-c`-Schlüssel und Kommando-Argument-Unterbefehle
  nehmen den Status „rein git“). PR #291 wird dort geschlossen, RED-Tests ggf. verwertet.

### Bedrohungsmodell (gilt für A und B)
Das Gate verhindert, dass der Agent die Pflichtprüfung **versehentlich** umgeht (gängige
Schreibweisen). Vorsätzliche Verschleierung (Config im selben Befehl schreiben, Env-Variablen wie
`GIT_PAGER`, `eval`, `| bash`, Here-Strings) ist Known Limitation; Backstop ist der Phase-8-Übergang,
der Verdict und Abdeckung unabhängig vom Commit-Weg gegen die Basis prüft.

### Affected Files (Teil A)
| File | Change Type | Description |
|------|-------------|-------------|
| `core/hooks/bash_gate.py` | MODIFY | 3b: Whitelist-Treffer überspringt nur 3b, kein `allow()`; `_is_whitelisted` nur wenn JEDES Segment whitelisted (wirkt auch auf 4b); 5b-Meldung nennt `git rebase --autostash origin/main`; 5b-cwd prüfen (`measure_root` statt `os.getcwd()`, #155-Konsistenz) |
| `core/hooks/hook_utils.py` | MODIFY | `_git_nested_subcommands`: Shell-Optionen überspringen (Bündel mit `c`, `--login/--noprofile/--norc`, `-o/-O/--rcfile/--init-file <wert>`); Umleitungen samt Ziel und Ziffern-Präfix vor/nach `git` überspringen (`>`, `>>`, `<`, `N>`, `>&`, `&>`, `N>&M`), `&`-Umleitungen nicht als Trenner; `_GIT_OPTS_WITH_VALUE`: `--attr-source` ergänzen, `--exec-path` raus |
| `tests/test_bash_gate_erkennung_299.py` | CREATE | Tabelle oben als Subprozess-Tests (beide Fehlerrichtungen), #284 mit echtem Origin-Repo inkl. Index-Wiederherstellung |
| `CHANGELOG.md` | MODIFY | [Unreleased] |

### Scope Assessment
- Files: 4 · Estimated LoC: ca. +245/−15 · Risk Level: HIGH (Kern-Gate aller Konsumenten), abgefedert durch Regressionssuite (`test_git_invocation_detection.py`, `test_bash_gate_*`).

### Technical Approach
Regelweg, kein Modell: Ohne Modell geht es, weil Shell-Tokenisierung und Optionslisten deterministisch
sind. Alternativen bewertet und nicht gewählt:
- (a) Git-Hook `reference-transaction`/`pre-commit` per Plugin: deckt Commit-Wege unabhängig von der
  Schreibweise, aber nicht 3b/Marker (Bash-Text), braucht Installer pro Projekt, kollidiert mit husky,
  `-c core.hooksPath` überschreibt, Plugin-Modus ohne Installationspunkt. Später als Spike möglich.
- (b) CI-Gate für gestempeltes `adversary-dialog.md` analog `ci_spec_gate.py`: lokal nicht abschaltbar,
  ergänzt den Backstop; kein Ersatz für A. Wird in Teil B als Option bewertet.
- (c) Resolver aus PR #291 fortführen: zweimal BROKEN, nach oben offen — verworfen.

### Dependencies
`hook_utils`-Zerlegung wird von `bash_gate` (Fast-Path, 3a, 5), `adversary_dialog` (`_commit_change_set`) genutzt; Teil B baut auf der überarbeiteten `_git_subcommand_after` auf.

### Open Questions
- Keine PO-Fragen. Produktentscheidung #297 (merge zählt nicht als Commit) fällt in Teil B und wird dort in der Spec begründet.
