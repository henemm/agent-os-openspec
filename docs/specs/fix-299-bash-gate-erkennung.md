---
entity_id: fix-299-bash-gate-erkennung
type: bugfix
created: 2026-10-01
updated: 2026-10-01
status: draft
version: "1.0"
tags: [bash-gate, commit-gate, whitelist, git-erkennung, rebase-pflicht, umleitung, nested-shell, teil-a]
test_targets: ["tests/test_bash_gate_erkennung_299.py"]
---

# bash_gate: Erkennungslücken schließen — Teil A von #299 (#296, #298, #304, #284)

## Approval

- [ ] Approved

## GitHub Issue

- **Issue:** #299 (Sammel-Vorgang, Epic #200), Teil A. Enthält #296 (Whitelist-Abkürzung), #298 (`bash -lc`), #304 (Umleitung/Option vor dem Unterbefehl) und #284 (Rebase-Pflicht gegen Vormerkung), dazu zwei Nebenbefunde aus der Reproduktion (Whitelist „irgendein Segment“, `&`-Umleitungen als Trenner). Teil B (#281, #297) ist ausdrücklich NICHT Teil dieses Vorgangs (siehe Known Limitations).

## Purpose

`bash_gate.py` erkennt „das ist ein Commit“, „das fasst einen geschützten Pfad an“ und „das ist Whitelist“ per Zerlegung des rohen Bash-Strings. Fünf konkrete Schreibweisen umgehen dabei heute die Commit-Gates (5a–5d, also Pflichtdateien, Rebase-Pflicht, Adversary-Verdict, E2E-Scope) oder den Schutz der Workflow-Dateien, obwohl der Agent sie ganz normal und ohne Absicht benutzen kann: ein Whitelist-Treffer beendet das Gate vorzeitig (`git commit -m x -- .claude/workflows/<wf>.json` läuft durch), `bash -lc "git commit …"` wird nicht als Commit gesehen, und `git >/dev/null commit`, `git 2>&1 commit` oder `git --attr-source HEAD commit` ebenso wenig. Umgekehrt rät die Rebase-Pflicht bei vorgemerkten Dateien zu `git rebase origin/main`, was bei nicht leerem Index scheitert (#284). Diese Spec schließt genau diese Lücken mit Regeln (Tokenisierung, Optionslisten), ohne Modell und ohne neuen Subprozess.

## Source

- **File:** `core/hooks/bash_gate.py` — `main()` Schritt 3b (State-Integrity + Whitelist), 4b, 5b (Rebase-Pflicht); `_whitelist_matches`, `_is_whitelisted`, `_measurement_root`
- **File:** `core/hooks/hook_utils.py` — `_git_lex`, `_git_segments`, `_is_git_separator`, `_git_subcommand_after`, `_git_nested_subcommands`, `_GIT_OPTS_WITH_VALUE`, `is_git_subcommand`, `is_pure_git_command`, `git_head_subcommands`
- **Analyse:** `docs/context/fix-299-bash-gate-erkennung.md`, Abschnitt „Analysis“ (Reproduktionstabelle, Schnitt Teil A/B, Bedrohungsmodell)

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `core/hooks/hook_utils.py` | Modul | Zerlegung der Git-Aufrufe; wird von `bash_gate` (Schnellpfad, 3a, 5) und `adversary_dialog._commit_change_set` genutzt, jede Änderung wirkt auf alle |
| `core/hooks/bash_gate.py` | Modul | Kern-Gate Bash; Schritt 3b/4b/5b |
| `core/hooks/adversary_dialog.py` | Modul | Von 5c aufgerufen; wird nicht geändert, profitiert von besserer Commit-Erkennung |
| `docs/specs/fix-253-adversary-evidence-gate.md` | Spec (Vorläufer) | Der Nachweis, den die Commit-Erkennung schützen soll |
| `docs/specs/fix-259-adversary-diff-binding.md` | Spec (Vorläufer) | Abdeckungsprüfung; dort schon Known Limitation „vorsätzlich manipuliertes git“ |
| `tests/test_git_invocation_detection.py` | Test | Sandbox-Muster (aktiver Workflow phase6 ohne Verdict), Regressionsschutz der Zerlegung |
| `tests/test_bash_gate_false_positives.py`, `tests/test_bash_gate_freetext_fixes_64_75.py`, `tests/test_bash_gate_worktree_commit_155.py` | Test | Regressionsschutz Über-Blockierung, Freitext, Worktree-Messung |
| git CLI (2.54 lokal) | extern | `git --attr-source <tree-ish>` (eigenes Wert-Token), `--exec-path[=<path>]` (nur mit `=`) laut `git(1)` |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| `core/hooks/bash_gate.py` | MODIFY | 3b: Whitelist-Treffer überspringt nur den Block-Teil von 3b, kein `allow()` mehr; `_is_whitelisted` gilt nur, wenn JEDES Segment whitelisted ist; 5b-Meldung nennt `git rebase --autostash origin/main`; 5b misst mit `measure_root` statt `os.getcwd()` |
| `core/hooks/hook_utils.py` | MODIFY | `_git_nested_subcommands`: Shell-Optionen überspringen; Umleitungen vor/nach `git` samt Ziel überspringen, `&`-Umleitungen sind keine Trenner; `_GIT_OPTS_WITH_VALUE`: `--attr-source` ergänzen, `--exec-path` entfernen |
| `tests/test_bash_gate_erkennung_299.py` | CREATE | Subprozess-Tests je Zeile der Reproduktionstabelle, beide Fehlerrichtungen; #284 mit echtem Origin-Repo |
| `CHANGELOG.md` | MODIFY | `[Unreleased]` |

### Estimated Changes

- Files: 4
- LoC: ca. +245 / −15 (Produktivcode ca. 75, Tests ca. 170). `core/hooks/` ist Infrastruktur: Die Implementierung braucht den Override-Token.

## Implementation Details

**1. #296 Whitelist überspringt nur 3b (`bash_gate.py`).** In Schritt 3b ruft ein Whitelist-Treffer heute `allow()` auf und beendet das ganze Gate. Danach laufen weder Secrets (4/4b) noch Commit-Gates (5) — `git commit -m x -- .claude/workflows/<wf>.json` und `git add .claude/settings.json && git commit -m x` kommen durch, weil `git add`/`git commit` auf der Whitelist stehen und der Befehl einen geschützten Pfad nennt. Neu: Bei Whitelist-Treffer entfällt nur der Block-Teil von 3b (`_has_write_indicator` → „Direct state file manipulation“), der Ablauf geht weiter zu 4/4b und 5. Der Zweck der Whitelist („`workflow.py …` darf den State anfassen“) bleibt erhalten, weil dort nur 3b übersprungen wird.

**2. Whitelist gilt nur für den ganzen Befehl (`_is_whitelisted`).** Heute reicht, dass IRGENDEIN Whitelist-Eintrag IRGENDWO im Befehl vorkommt (`_whitelist_matches`). `git status && sed -i … .claude/workflows/<wf>.json` gilt dadurch als whitelisted. Neu: Der Befehl wird in Segmente zerlegt (`_git_segments`); `_is_whitelisted` ist nur wahr, wenn JEDES Segment mindestens einen Whitelist-Eintrag trifft. Nicht zerlegbare Befehle (kaputte Quotes) behalten das bisherige Teilstring-Verhalten (fail-open, damit niemand ausgesperrt wird). Das wirkt auch auf 4b (`not _is_whitelisted` → Credential-Prüfung): ein zusammengesetzter Befehl, dessen Segment nicht whitelisted ist, wird dort jetzt geprüft statt übersprungen.

**3. #298 verschachtelte Shells (`_git_nested_subcommands`).** Heute zählt nur `<shell> -c "…"` mit `-c` unmittelbar nach dem Shell-Binary. Neu: Nach dem Shell-Token werden Optionen übersprungen, bis ein Optionsbündel mit dem Buchstaben `c` kommt (`-c`, `-lc`, `-ec`, `-xc`, …) und danach das Kommando-Token folgt. Mit eigenem Wert-Token: `-o`, `-O`, `--rcfile`, `--init-file` (der Wert wird übersprungen, nicht als Kommando gelesen). Ohne Wert: `--login`, `--noprofile`, `--norc`, `--posix`, andere `--lange` Flags. Beispiele: `bash -lc "git commit"`, `sh -ec "git commit"`, `bash --login -c "git commit"`, `bash -o pipefail -c "git commit"`, `bash --rcfile x -c "git commit"`, `bash --noprofile --norc -c "git commit"`. Die Tiefenbegrenzung (`depth >= 2`) bleibt.

**4. #304 Umleitungen (`_git_lex`/`_is_git_separator`/`_git_subcommand_after`).** Der Lexer liefert Umleitungen als eigene Token: `>`, `>>`, `<`, `>&`, `&>`, `&>>`, dazu ein Ziffern-Präfix als eigenes Token (`2>&1` → `2`, `>&`, `1`). Zwei Fehler heute:
  - In `_git_subcommand_after` gilt eine Umleitung vor dem Unterbefehl als Unterbefehl bzw. ihr Ziel als Unterbefehl: `git >/dev/null commit` liefert `>` bzw. `/dev/null` statt `commit`.
  - `>&`, `&>`, `&>>` enthalten das Zeichen `&` und werden von `_is_git_separator` als Befehlstrenner gelesen, sodass `git 2>&1 commit` in zwei Segmente zerfällt (`git 2`, `1 commit`) und `git status 2>&1` kein reines git mehr ist (`is_pure_git_command` → False, Über-Erkennung im Schnellpfad).

  Neu: (a) Ein Token, das eine Umleitung ist (nur aus `<>&` bestehend, mit mindestens einem `<` oder `>`; `&>` und `&>>` eingeschlossen), ist kein Trenner. (b) Ein reines Ziffern-Token direkt VOR einer Umleitung und das Ziel direkt DANACH werden in `_git_subcommand_after` übersprungen; bei `N>&M` ist `M` das Ziel. Reihenfolge-Beispiele: `git >/dev/null commit`, `git 2>&1 commit`, `git &>/dev/null commit`, `git commit 2>&1`, `git status 2>&1`. Ein einzelnes `&` (Hintergrund) bleibt Trenner, ebenso `&&`, `|&` und `<(`/`>(`.

**5. #304 `_GIT_OPTS_WITH_VALUE`.** `--attr-source` kommt dazu (nimmt laut `git(1)` ein eigenes Wert-Token: `git --attr-source HEAD commit`). `--exec-path` wird entfernt: laut `git(1)` heißt es `--exec-path[=<path>]`, ein Wert gehört nur mit `=` dazu; ohne Wert gibt git den Pfad aus und beendet sich. Als Wert-Option würde `git --exec-path commit` den Unterbefehl `commit` verschlucken — und damit eine konservativ zu prüfende Form übersehen. (Belegt am Handbuch der lokal installierten git-Version 2.54.0.)

**6. #284 Rebase-Pflicht (`bash_gate.py`, Schritt 5b).** Der Rat `git fetch origin && git rebase origin/main` scheitert bei vorgemerkten Dateien mit „index contains uncommitted changes“, und genau vorgemerkt sind sie in einem Commit-Moment immer. Neu nennt die Meldung `git fetch origin && git rebase --autostash origin/main`. `--autostash` sichert die Vormerkung vor dem Rebase und stellt sie danach wieder her (am echten Repo reproduziert: der Befehl gelingt, die Datei bleibt vorgemerkt). Die Blockier-Entscheidung selbst (Branch hinter `origin/main`) bleibt unverändert. Zusätzlich misst 5b mit `cwd=measure_root` statt `os.getcwd()` (Fetch, `rev-list`), wie 5a/5c/5d seit #155. Das ist eine Angleichung an dieselbe Messwurzel; sie ändert das Ergebnis nur, wenn Aufrufverzeichnis und Arbeitsbaum auseinanderfallen. Ein beobachtbarer Fehler daraus ist nicht reproduziert, der Code-Befund (zwei verschiedene Wurzeln im selben Schritt) rechtfertigt die Angleichung.

**Alternativen (Regelweg vorn):**

- **Gewählt: Struktur-Fix in der bestehenden Zerlegung.** Ohne Modell geht es, weil Shell-Tokenisierung und Git-Optionslisten deterministisch sind. Die Nulllinie ist die Regel; ein Modell würde hier nur Latenz und Fehlerquote hinzufügen.
- **(a) Git-Hook `reference-transaction`/`pre-commit`, vom Plugin installiert:** deckt jeden Commit-Weg unabhängig von der Schreibweise (auch Alias, `merge`, `cherry-pick`), aber nicht den Bash-Text-Schutz (3a/3b), braucht eine Installation pro Projekt, kollidiert mit husky/`pre-commit`, und `-c core.hooksPath=…` überschreibt ihn; im Plugin-Modus gibt es keinen Installationspunkt. Später als eigener Spike möglich.
- **(b) CI-Gate für den gestempelten Adversary-Nachweis, analog `ci_spec_gate.py`:** lokal nicht abschaltbar, ergänzt den Backstop, ersetzt Teil A aber nicht (die Sperre soll vor dem Commit greifen, nicht erst im PR). Wird in Teil B als Option bewertet.
- **(c) Alias-Resolver aus PR #291 fertigstellen:** zweimal BROKEN, nach oben offen (verschleierte Befehlsformen) — verworfen; Teil B löst #281 schlanker.
- **(d) Echter Shell-Parser (z. B. `bashlex`):** neue Abhängigkeit, ohne Freigabe nicht erlaubt, und löst Alias/Config/Env-Umgehungen ebenfalls nicht.

Gekippt wird keine ADR; die Entscheidung „Regeltext-Zerlegung statt Parser/Resolver“ bleibt und wird nur lückenloser gemacht.

## Expected Behavior

- **Input:** Ein Bash-Befehl, der durch `bash_gate.py` läuft, in einem Projekt mit aktivem Workflow in phase6 ohne gültigen Adversary-Verdict.
- **Output:** Jede Commit-Schreibweise aus der Tabelle unten wird wie ein normaler `git commit` behandelt (Exit 2, Block durch 5c, Meldung zum fehlenden Verdict). Befehle ohne Commit und ohne Schreibzugriff auf geschützte Pfade laufen weiter wie bisher (Exit 0).
- **Side effects:** Keine neuen Subprozesse. Die 5b-Meldung nennt `--autostash`. Schnellpfad und Marker-Schutz bleiben unverändert, außer dass `git status 2>&1` jetzt als reines git gilt und `git 2>&1 commit` als Commit erkannt wird.

| Befehl | Heute | Soll | Issue |
|--------|-------|------|-------|
| `git commit -m x`, `git -C . commit -m x`, `bash -c "git commit -m x"` | blockiert | blockiert | Kontrolle |
| `git commit -m x -- .claude/workflows/<wf>.json` | durchgelassen | blockiert | #296 |
| `git add .claude/settings.json && git commit -m x` | durchgelassen | blockiert | #296 |
| `git status && sed -i … .claude/workflows/<wf>.json` | durchgelassen | blockiert | Nebenbefund Whitelist |
| `git add x && sed -i … .claude/workflows/<wf>.json` | durchgelassen | blockiert | Nebenbefund Whitelist |
| `bash -lc` / `sh -ec` / `bash --login -c "git commit -m x"` | durchgelassen | blockiert | #298 |
| `bash -o pipefail -c`, `bash --rcfile f -c`, `bash --noprofile --norc -c "git commit -m x"` | durchgelassen | blockiert | #298 |
| `git >/dev/null commit -m x`, `git --attr-source HEAD commit -m x` | durchgelassen | blockiert | #304 |
| `git 2>&1 commit -m x` | durchgelassen | blockiert | Nebenbefund `&`-Umleitung |
| `git status 2>&1` | nicht „rein git“ | rein git, erlaubt | Nebenbefund Über-Erkennung |
| `git status`, `git add x`, `workflow.py status` | erlaubt | erlaubt | Nicht über-blockieren |
| #284: hinter `origin/main`, Datei vorgemerkt | Rat scheitert | Rat nennt `--autostash`, gelingt | #284 |

## Known Limitations

- **Nicht in diesem Vorgang (Teil B von #299):** #281 (Alias: `git -c alias.ci=commit ci -m x`, auch Alias aus der Repo-Config) und #297 (`git merge`/`cherry-pick`/`revert`/`am`/`pull` als Commit-Weg ohne Wort `commit`; `git -c core.pager='sh -c …' log` führt Code aus). Sie bleiben vorerst unverändert und werden im nächsten Workflow unter #299 gelöst: schlanke Alias-Abfrage (`git config --get-regexp '^alias\.'`, fail-open, mit Tiefenlimit, `!`-Alias = nicht rein git) und die Produktentscheidung zu `merge` (legitimer Weg aus der Rebase-Pflicht; Phase 8 fängt Code ab). PR #291 wird dort geschlossen oder verwertet.
- **Bedrohungsmodell:** Das Gate verhindert, dass Claude die Pflichtprüfung **versehentlich** umgeht, also über gängige Schreibweisen. **Vorsätzliche** Verschleierung ist Known Limitation: Config im selben Befehl schreiben, Umgebungsvariablen wie `GIT_PAGER`/`GIT_EXTERNAL_DIFF`, `eval`, `| bash`, Here-Strings, selbstgebaute Wrapper-Skripte. Das gilt für A und B. Ein Text-Parser der Shell-Syntax ist nach oben offen — Beleg ist PR #291 (zwei Adversary-Runden BROKEN).
- **Backstop:** Der Übergang nach Phase 8 (`workflow.py`) prüft Verdict und Abdeckung unabhängig vom Commit-Weg gegen `base_commit` bzw. `merge-base(origin/main, HEAD)`. Wer das Gate vorsätzlich umgeht, scheitert spätestens dort. Ein serverseitiger Nachweis im PR (Alternative b) wäre der stärkere Backstop und wird in Teil B bewertet.
- **Konservative Über-Erkennung bleibt:** `git --exec-path commit` gilt als Commit-Aufruf (git selbst würde nur den Pfad ausgeben). Das ist die sichere Richtung.
- **Umleitungen nur als Token:** Eine Umleitung, die ohne Leerzeichen am Wort klebt und dabei das Wort verändert (`git2>&1`), ist ein anderes Wort und bleibt unerkannt; so auch in der Shell.
- **Verteilung:** wirkt in Konsumenten-Projekten erst nach dem Plugin-Update.

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] Ein Commit, der über `bash -lc`, `sh -ec`, `bash --login -c`, eine Umleitung vor dem Unterbefehl oder `--attr-source` geschrieben wird, wird genauso blockiert wie ein normaler `git commit` ohne Adversary-Nachweis
- [ ] Ein Commit, der einen Workflow-State-Pfad nennt, und ein zusammengesetzter Befehl mit Schreibzugriff auf den Workflow-State neben einem Whitelist-Befehl werden blockiert statt durchgelassen
- [ ] Normale, harmlose Befehle (`git status`, `git status 2>&1`, `git add x`, `workflow.py status`, `bash -c "git status"`) werden weiterhin NICHT blockiert
- [ ] Die Rebase-Pflicht-Meldung nennt einen Befehl, der bei vorgemerkten Dateien tatsächlich gelingt und die Vormerkung erhält
- [ ] Known Limitations nennt Teil B (#281, #297) und das Bedrohungsmodell; die Issues #296, #298, #304, #284 sind erledigt, #299 bleibt für Teil B offen
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf grün)

## Acceptance Criteria

Alle Tests laufen `core/hooks` des Worktrees per `subprocess` an (Wegwerf-Repo, aktiver Workflow phase6 ohne Verdict; Muster aus `tests/test_git_invocation_detection.py`), nicht die installierte Plugin-Fassung.

- **AC-1:** Given ein Workflow in phase6 ohne Verdict / When `git commit -m x`, `git -C . commit -m x` oder `bash -c "git commit -m x"` läuft / Then bleibt der Befehl blockiert (Exit 2, Meldung zum fehlenden Verdict) wie bisher.
  - Test: tests/test_bash_gate_erkennung_299.py::test_kontrolle_normale_commit_formen_bleiben_blockiert
- **AC-2:** Given dieselbe Lage / When `git commit -m x -- .claude/workflows/<wf>.json` läuft / Then wird der Befehl blockiert (Whitelist-Treffer überspringt 5 nicht mehr).
  - Test: tests/test_bash_gate_erkennung_299.py::test_whitelist_commit_mit_geschuetztem_pfad_wird_blockiert
- **AC-3:** Given dieselbe Lage / When `git add .claude/settings.json && git commit -m x` läuft / Then wird der Befehl blockiert.
  - Test: tests/test_bash_gate_erkennung_299.py::test_whitelist_add_geschuetzt_und_commit_wird_blockiert
- **AC-4:** Given ein Workflow in phase6 / When `git status && sed -i … .claude/workflows/<wf>.json` läuft / Then wird der Befehl blockiert („Direct state file manipulation“), weil das zweite Segment nicht whitelisted ist.
  - Test: tests/test_bash_gate_erkennung_299.py::test_whitelist_gilt_nicht_fuer_beliebiges_segment_status_sed
- **AC-5:** Given ein Workflow in phase6 / When `git add x && sed -i … .claude/workflows/<wf>.json` läuft / Then wird der Befehl blockiert.
  - Test: tests/test_bash_gate_erkennung_299.py::test_whitelist_gilt_nicht_fuer_beliebiges_segment_add_sed
- **AC-6:** Given ein Workflow in phase6 / When `python3 .claude/hooks/workflow.py status`, `git status`, `git add x` oder `git status && git add x` läuft (jeweils ohne Schreibzugriff auf geschützte Pfade und ohne Commit) / Then wird der Befehl durchgelassen (Exit 0): reine Whitelist-Befehle werden nicht über-blockiert.
  - Test: tests/test_bash_gate_erkennung_299.py::test_reine_whitelist_befehle_ohne_commit_bleiben_erlaubt
- **AC-7:** Given ein Workflow in phase6 / When ein Whitelist-Befehl einen geschützten Pfad nur nennt, ohne zu schreiben (`python3 .claude/hooks/workflow.py status`, `git add .claude/workflows/<wf>.json`) / Then wird er durchgelassen; Schritt 3b blockiert nur bei Schreibzugriff.
  - Test: tests/test_bash_gate_erkennung_299.py::test_whitelist_mit_geschuetztem_pfad_ohne_schreibzugriff_bleibt_erlaubt
- **AC-8:** Given ein Workflow in phase6 ohne Verdict / When `bash -lc "git commit -m x"`, `sh -ec "git commit -m x"` oder `bash --login -c "git commit -m x"` läuft / Then wird der Befehl wie ein Commit blockiert.
  - Test: tests/test_bash_gate_erkennung_299.py::test_nested_shell_optionsbuendel_mit_c_wird_als_commit_erkannt
- **AC-9:** Given dieselbe Lage / When `bash -o pipefail -c "git commit -m x"`, `bash -O extglob -c …`, `bash --rcfile f -c …`, `bash --init-file f -c …` oder `bash --noprofile --norc -c "git commit -m x"` läuft / Then wird der Befehl wie ein Commit blockiert; der Wert der Option wird nicht als Kommando gelesen.
  - Test: tests/test_bash_gate_erkennung_299.py::test_nested_shell_optionen_mit_wert_und_noprofile_werden_uebersprungen
- **AC-10:** Given ein Workflow in phase6 / When `bash -c "git status"`, `bash -lc "echo git commit"` oder `bash --login -c "ls"` läuft / Then wird der Befehl nicht blockiert: kein Commit im Inneren, keine Über-Erkennung.
  - Test: tests/test_bash_gate_erkennung_299.py::test_nested_shell_ohne_commit_im_inneren_bleibt_erlaubt
- **AC-11:** Given ein Workflow in phase6 ohne Verdict / When `git >/dev/null commit -m x`, `git >>log commit -m x` oder `git &>/dev/null commit -m x` läuft / Then wird der Befehl wie ein Commit blockiert; Umleitung samt Ziel wird übersprungen.
  - Test: tests/test_bash_gate_erkennung_299.py::test_umleitung_vor_unterbefehl_wird_uebersprungen
- **AC-12:** Given dieselbe Lage / When `git --attr-source HEAD commit -m x` läuft / Then wird der Befehl wie ein Commit blockiert (`--attr-source` nimmt ein eigenes Wert-Token).
  - Test: tests/test_bash_gate_erkennung_299.py::test_attr_source_option_mit_wert_wird_uebersprungen
- **AC-13:** Given dieselbe Lage / When `git 2>&1 commit -m x` läuft / Then wird der Befehl als Commit erkannt und blockiert; `2>&1` ist kein Befehlstrenner.
  - Test: tests/test_bash_gate_erkennung_299.py::test_und_umleitung_ist_kein_trenner_commit_erkannt
- **AC-14:** Given `hook_utils` / When `is_pure_git_command("git status 2>&1")`, `…("git status &>/dev/null")` und `…("git log >> out.txt")` geprüft werden / Then ist das Ergebnis True; für `git status 2>&1 && touch x` False. Ein einzelnes `&` (`git status & touch x`) bleibt Trenner, `git status | cat` und `git status && touch x` sind nicht rein git.
  - Test: tests/test_bash_gate_erkennung_299.py::test_git_status_mit_umleitung_ist_rein_git_und_trenner_bleiben
- **AC-15:** Given dieselbe Lage / When `git commit -m x 2>&1` (Umleitung hinter dem Unterbefehl) läuft / Then wird der Befehl blockiert (Kontrolle: Unterbefehl bleibt `commit`); When `git --exec-path commit -m x` läuft / Then wird er ebenfalls blockiert (`--exec-path` nimmt keinen Wert, `commit` bleibt Unterbefehl).
  - Test: tests/test_bash_gate_erkennung_299.py::test_umleitung_nach_unterbefehl_und_exec_path_ohne_wert
- **AC-16:** Given ein normaler Commit mit gültigem Adversary-Nachweis bzw. ein Commit außerhalb eines Workflows / When er mit einer der erweiterten Schreibweisen (Umleitung, `bash -lc`) läuft / Then verhält er sich wie ohne Umleitung/Shell-Hülle: erlaubt, wenn alle Gates erfüllt sind (Exit 0), kein Über-Blockieren.
  - Test: tests/test_bash_gate_erkennung_299.py::test_erweiterte_schreibweisen_mit_gueltigem_nachweis_nicht_ueberblockiert
- **AC-17:** Given ein Wegwerf-Repo mit echtem Origin-Repo, dessen `main` einen Commit weiter ist, ein Workflow in phase6 und eine vorgemerkte Datei / When `git commit -m x` läuft / Then blockiert 5b mit einer Meldung, die `git rebase --autostash origin/main` enthält.
  - Test: tests/test_bash_gate_erkennung_299.py::test_rebase_pflicht_meldung_nennt_autostash
- **AC-18:** Given dieselbe Lage / When der in der Meldung genannte Befehl `git fetch origin && git rebase --autostash origin/main` ausgeführt wird / Then gelingt er (Exit 0), der Branch steht nicht mehr hinter `origin/main`, und die Datei ist weiterhin vorgemerkt (`git diff --cached --name-only` unverändert); der Rat ohne `--autostash` (`git rebase origin/main`) scheitert in derselben Lage mit „index contains uncommitted changes“ (Kontrolle gegen eine nur behauptete Wirkung).
  - Test: tests/test_bash_gate_erkennung_299.py::test_autostash_rat_gelingt_bei_vorgemerkter_datei_und_erhaelt_vormerkung
- **AC-19:** Given dasselbe Wegwerf-Repo, aber der Hook läuft aus einem Unterverzeichnis des Arbeitsbaums / When `git commit -m x` läuft / Then blockiert 5b weiterhin (Rückstand erkannt, Messwurzel `measure_root`); und ist der Branch nicht hinter `origin/main`, blockiert 5b nicht (Kontrolle: kein Über-Blockieren).
  - Test: tests/test_bash_gate_erkennung_299.py::test_rebase_pflicht_misst_im_arbeitsbaum_und_blockiert_nicht_ohne_rueckstand
- **AC-20:** Given die bestehenden Testdateien zur Git-Erkennung und zum Bash-Gate / When sie nach der Änderung laufen / Then bleiben `tests/test_git_invocation_detection.py`, `tests/test_bash_gate_false_positives.py`, `tests/test_bash_gate_freetext_fixes_64_75.py` und `tests/test_bash_gate_worktree_commit_155.py` unverändert grün.
  - Test: tests/test_bash_gate_erkennung_299.py::test_bestehende_bash_gate_und_git_erkennungs_tests_bleiben_gruen

## Test Plan

Automatische Tests (jeweils an eine AC oben gebunden). Subprozess-Tests gegen `core/hooks` des Worktrees (nicht die installierte Fassung); Wegwerf-Repo mit `.git` als Verzeichnis, aktiver Workflow phase6 ohne Verdict, Muster aus `tests/test_git_invocation_detection.py`:

- `pytest tests/test_bash_gate_erkennung_299.py` — AC-1 bis AC-20. Beide Fehlerrichtungen je Fund: Block (Unter-Blockieren: AC-2 bis AC-5, AC-8, AC-9, AC-11 bis AC-13, AC-15) und Nicht-Blockieren (Über-Blockieren: AC-6, AC-7, AC-10, AC-14, AC-16, AC-19). #284 (AC-17 bis AC-19) mit echtem Origin-Repo im Wegwerf-Verzeichnis (zweites Repo als `origin`, ein zusätzlicher Commit dort, Datei vorgemerkt); der `--autostash`-Rat wird tatsächlich ausgeführt und die Vormerkung danach geprüft.
- RED-Beleg: Alle Block-Fälle sind heute durchgelassen (Exit 0, Reproduktionstabelle); die Tests müssen vor der Implementierung fehlschlagen.
- `pytest tests/test_git_invocation_detection.py tests/test_bash_gate_false_positives.py tests/test_bash_gate_freetext_fixes_64_75.py tests/test_bash_gate_worktree_commit_155.py` — Regressionsschutz (AC-20)
- `pytest tests` — Gesamtlauf (mit venv, das pytest UND pyyaml enthält)

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Struktur-Fix innerhalb der bestehenden Zerlegung des Bash-Strings in `hook_utils.py` und der bestehenden Gate-Reihenfolge in `bash_gate.py`: die Whitelist beendet das Gate nicht mehr vorzeitig, sie gilt nur für den ganzen Befehl, drei Zerlegungslücken werden geschlossen und eine Meldung wird korrigiert. Keine neue Komponente, Konfigurationsoption oder Schnittstelle, kein neuer Subprozess. Regelweg statt Modell: Shell-Tokenisierung und Optionslisten sind deterministisch und messbar. Die Alternativen stehen oben (Git-Hook `reference-transaction`/`pre-commit`: installationsabhängig, kollidiert mit husky, per `-c core.hooksPath` überschreibbar; CI-Gate für den Adversary-Nachweis: ergänzt den Backstop, ersetzt die lokale Sperre nicht; Alias-Resolver aus PR #291: zweimal BROKEN). Alle drei bleiben als spätere Ergänzung offen (Teil B bzw. eigener Spike) und würden ggf. die Entscheidung kippen, dass die Commit-Erkennung allein im Bash-Gate-Text liegt. Teil A kippt nichts davon.

## Changelog

- 2026-10-01: Initial spec created (Teil A von #299)
