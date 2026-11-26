---
entity_id: fix-653-target-dir-flag
type: bugfix
created: 2026-11-26
updated: 2026-11-26
status: draft
workflow: fix-653-target-dir-flag
version: "1.0"
tags: [bash-gate, schreibziel, zielordner-flag, hauptordner, config-sperre, getopt]
test_targets: ["tests/test_bash_gate_target_dir_653.py"]
---

# bash_gate: Zielordner-Flag (-t / --target-directory) in allen Schreibweisen erkennen — #653

## Approval

- [ ] Approved

## GitHub Issue

- **Issue:** #653 „Schreibziel-Erkennung: Zielordner-Flag (-t/--target-directory) in Varianten übersehen (cp/mv/ln/install)“. Teil des Epics #429. Folge aus #435 (Adversary-Befund F001). Grundlage: `docs/specs/fix-417-bash-main-write.md` (Prüfung 1c) und `docs/specs/fix-435-symlink-parent.md`.
- **Analyse:** `docs/context/fix-653-target-dir-flag.md`

## Purpose

Das Gate erkennt Schreibziele von `cp`, `install`, `ln` und `mv` für die Prüfung 1b (wirksame Gate-Config als Ziel) und 1c (Haupt-Ordner aus einer Worktree-Sitzung) bisher nur in den Formen `-t DIR` und `--target-directory=DIR`. Gültige Varianten wie `cp -vt DIR x`, `cp -tDIR x`, `ln -sft DIR x` oder `cp --target-dir=DIR x` liefern nur die Quelle `x` als Ziel; der Schreibzugriff nach `DIR/x` bleibt unbemerkt und die Sperre lässt sich versehentlich umgehen. Die Spec ersetzt die grobe Erkennung durch einen gemeinsamen getopt-Zerleger, sodass jede gültige Schreibweise `DIR/<basename>` je Quelle als Schreibziel liefert. Schutz vor Versehen, kein Sandbox-Ersatz; rein regelbasiert, ohne Modell, ohne neuen Hook.

## Source

- **File:** `core/hooks/bash_gate.py` — `_copy_targets`, `_into_dir_targets`, `_dir_removal_targets`, `_CONFIG_WRITERS`, `_config_write_targets`, `_segment_write_targets`, `_target_dir_values`/`_mv_dir_targets` (#435)
- **Identifier:** `_target_dir_split` (neu), genutzt von `_copy_targets`, `_into_dir_targets`, `_dir_removal_targets`
- **Unverändert:** `_cp_target_dir` (#453, Beleg-Schutz 1d) mit eigenem Parser
- **Ursprungsanfrage:** GitHub-Issue #653

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `core/hooks/bash_gate.py` | Modul | Kern-Gate Bash; Ort der Änderung; läuft bei jedem Bash-Aufruf |
| `_CONFIG_WRITERS`, `_config_write_targets`, `_segment_write_targets` | Funktionen im Gate | gemeinsame Basis für 1b, 1c und 1d; rufen `_copy_targets` auf; Aufrufschnittstelle unverändert |
| `_writes_main_repo`, `_writes_effective_config` | Funktionen im Gate | Prüfungen 1c und 1b; unverändert, profitieren von den neuen Zielen |
| `_cp_target_dir` | Funktion im Gate | Parser des Beleg-Schutzes (#453); bleibt unverändert |
| `core/hooks/override_token.py` (über `_any_override_token`) | Modul | Ausweg des Schutzes; unverändert |
| `tests/test_bash_gate_main_write_417.py`, `tests/test_bash_gate_config_lock_418.py` | Tests | Vorlage für `_worktree_sandbox`, `_expect`, `OVERRIDE_HINT`; werden nicht verändert |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| `core/hooks/bash_gate.py` | MODIFY | Neuer Zerleger `_target_dir_split(cmd, args)`; `_copy_targets`, `_into_dir_targets`, `_dir_removal_targets` nutzen ihn |
| `tests/test_bash_gate_target_dir_653.py` | CREATE | Subprozess-Tests gegen das echte Gate, je Schreibweise für 1c und 1b, dazu Negativ- und Grenzfälle |
| `CHANGELOG.md` | MODIFY | Eintrag `[4.26.5]` samt Known Limitations |
| `.claude-plugin/plugin.json`, `CLAUDE.md` (Kopfzeile), `README.md` (Kopfzeile), `skills/*/SKILL.md` und `.claude/commands/*.md` (Marker) | MODIFY | Patch-Version 4.26.5; Skills über `python3 scripts/sync_skills.py`, nie von Hand |

**Nicht ändern:** `_cp_target_dir` (1d), `_writes_effective_config`, `_writes_main_repo` (Logik), `worktree_write_guard.py`, `hook_utils.py`, `hooks/hooks.json`.

### Estimated Changes

- Files: 1 Code-Datei, 1 Testdatei, dazu Changelog und Versionsstellen
- LoC: ca. +70/-25 im Gate, ca. +220 in den Tests
- Jede neue oder geänderte Funktion bleibt unter 50 Zeilen.

## Implementation Details

**1. Zerleger.** `_target_dir_split(cmd, args)` liefert `(zielordner_liste, positionale)` für `cmd` in `cp`, `mv`, `ln`, `install` nach GNU-getopt-Regeln:

- **Kurzoptionen** stehen einzeln oder in Gruppen (`-vt`, `-sft`, `-Dt`). Innerhalb einer Gruppe nimmt der erste Wertbuchstabe den Rest des Tokens als Wert (`-tDIR`, `-S.bak`); steht nichts dahinter, ist das nächste Token der Wert. Wertbuchstaben: `cp`, `mv`, `ln`: `S`, `t`; `install`: `g`, `m`, `o`, `S`, `t`. Nur ein Wertbuchstabe `t` liefert einen Zielordner, die anderen verbrauchen ihren Wert, ohne ihn als Ziel zu zählen.
- **Langoptionen:** `--target-directory` in jeder eindeutigen Abkürzung ab `--t` (`--t`, `--target`, `--target-dir`, …) mit `=` oder als Folgetoken. Die Langoptionen mit Wert `--suffix`, `--mode`, `--owner`, `--group`, `--strip-program`, `--no-preserve`, `--sparse` verbrauchen ihren Wert (mit `=` oder Folgetoken), ohne Zielordner zu sein. Jede andere Langoption gilt als wertlos.
- **`--`** beendet die Optionen; alles danach ist positional.
- **Permutation:** Optionen dürfen an jeder Stelle stehen (GNU-Standard), auch hinter den Quellen.
- **Mehrere Zielordner:** alle zählen (fail-closed).

**2. Nutzung.** `_copy_targets` (für `cp`/`install`/`ln` über `_CONFIG_WRITERS`, bei `mv` zusätzlich zu den Positionsargumenten) liefert mit Zielordnern `DIR/<basename>` je Quelle, sonst wie bisher das letzte Positionsargument. `_into_dir_targets` und `_dir_removal_targets` (für `mv`) entscheiden über „Zielordner-Modus“ anhand desselben Zerlegers statt per exaktem `"-t" in args`. Die Regel „Link-Rolle entfällt im Zielordner-Modus“ aus #435 bleibt bestehen, gilt aber jetzt für alle Schreibweisen.

**3. Sicherheitsrichtung.** Im Zweifel mehr Ziele, nie weniger: Ein Token, das nicht sicher als Wert einer bekannten Option erkannt wird, bleibt positional. Fehlalarme sind akzeptiert, ein verschlucktes Ziel nicht.

**4. Unverändert.** Blockbedingung, Meldungen (1b-Config-Text, 1c-Text mit Hinweis auf „override“), Override-Token und Fail-open bei `$`, Backtick, Glob, offener Quote oder Exception bleiben wie bisher.

## Expected Behavior

- **Input:** Ein Bash-Befehl durch `bash_gate.py` mit einem Zielordner-Flag in beliebiger gültiger Schreibweise bei `cp`, `install`, `ln` oder `mv`.
- **Output:** Zeigt `DIR/<basename>` in den Haupt-Ordner (Worktree-Sitzung, Prüfung 1c) oder auf die wirksame Gate-Config (1b), endet das Gate mit Exit 2 und der jeweiligen Meldung; liegt es im eigenen Worktree, mit Exit 0.
- **Side effects:** Keine neuen Subprozesse, Abhängigkeiten oder Config-Keys.

| Befehl (Zielordner `H` = Haupt-Ordner bzw. Ordner mit Config) | Heute | Soll |
|--------|-------|------|
| `cp --target-directory H x`, `cp --target-dir=H x`, `cp -vt H x`, `cp -tH x` | 0 | 2 |
| `ln -sft H x`, `ln --target-directory H x` | 0 | 2 |
| `install -Dt H x`, `install -m 644 --target-directory=H x` | 0 | 2 |
| `mv -tH x`, `mv --target-dir=H x`, `mv -vt H x` | teils 0 | 2 |
| dieselben Formen mit Zielordner im eigenen Worktree | 0 | 0 |
| `cp -S .t x y` (Wert von `-S` ist kein Ziel; Ziel ist `y`) | Ziel `y` | Ziel `y` |
| `cp -t H x`, `cp --target-directory=H x` (exakte Formen) | 2 | 2 |

## Known Limitations

- **Kein Sandbox-Ersatz:** `python -c`, `sh -c` mit Variablen, `eval`, Backticks und Skripte, die selbst schreiben, bleiben unerkannt (Ticket #416); wie in den Specs zu #417 und #435.
- **Abkürzungen anderer Lang-Wertoptionen:** Eine abgekürzte Lang-Wertoption außer `--target-directory` (etwa `--suf` für `--suffix`) wird als wertlos behandelt; ihr Folgetoken zählt dann als Positionsargument und kann als Ziel gewertet werden. Folge ist höchstens ein Fehlalarm, nie ein verschlucktes Ziel. Ausweg: volle Option oder „override“.
- **`POSIXLY_CORRECT`:** Die Umgebungsvariable (Optionen nur vor den Operanden) wird nicht berücksichtigt; es gilt immer die GNU-Permutation.
- **BSD/macOS:** Dort abweichende Optionssätze (etwa kein `--target-directory`) werden nicht gesondert behandelt.
- **Beleg-Schutz 1d (#453)** behält seinen eigenen Parser `_cp_target_dir`.
- Verteilung: wirkt in Konsumentenprojekten erst nach dem Plugin-Update.

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test am echten Gate-Subprozess belegt
- [ ] Eine Worktree-Sitzung, die mit `cp`, `install`, `ln` oder `mv` über irgendeine gültige Schreibweise des Zielordner-Flags in den Haupt-Ordner oder auf die wirksame Gate-Config schreibt, wird genauso blockiert wie bei der exakten Form `-t DIR`
- [ ] Zielordner im eigenen Worktree und Werte von `-S`/`--suffix`/`-m` führen zu keinem Fehlalarm
- [ ] CHANGELOG-Eintrag `[4.26.5]` mit Known Limitations; Version 4.26.5 an allen Stellen (plugin.json, CLAUDE.md, README.md, Skills und Marker per `sync_skills.py`)
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Tests 417, 418, 435, 447, 448, 453 und Vollsuite grün)

## Acceptance Criteria

- **AC-1:** Given eine Worktree-Sitzung und der Haupt-Ordner als Zielordner / When `cp --target-directory H x` (getrennter Wert), `cp --target-dir=H x` (abgekürzt, mit `=`) oder `cp -vt H x` (Kurzflag-Gruppe) läuft / Then endet das Gate mit Exit 2 und der 1c-Meldung mit Hinweis auf „override“
  - Test: `tests/test_bash_gate_target_dir_653.py::test_cp_varianten_in_hauptordner_blocken`
- **AC-2:** Given eine Worktree-Sitzung und der Haupt-Ordner als Zielordner / When `cp -tH x` (Wert direkt angehängt) läuft / Then endet das Gate mit Exit 2
  - Test: `tests/test_bash_gate_target_dir_653.py::test_cp_angehaengter_wert_blockt`
- **AC-3:** Given eine Worktree-Sitzung und der Haupt-Ordner als Zielordner / When `ln -sft H x` oder `ln --target-directory H x` läuft / Then endet das Gate mit Exit 2
  - Test: `tests/test_bash_gate_target_dir_653.py::test_ln_varianten_in_hauptordner_blocken`
- **AC-4:** Given eine Worktree-Sitzung und der Haupt-Ordner als Zielordner / When `install -Dt H x` oder `install -m 644 --target-directory=H x` läuft / Then endet das Gate mit Exit 2 (der Wert von `-m` wird nicht als Zielordner gelesen, das Zielordner-Flag trotzdem erkannt)
  - Test: `tests/test_bash_gate_target_dir_653.py::test_install_varianten_in_hauptordner_blocken`
- **AC-5:** Given eine Worktree-Sitzung und der Haupt-Ordner als Zielordner / When `mv -tH x`, `mv --target-dir=H x` oder `mv -vt H x` läuft / Then endet das Gate mit Exit 2
  - Test: `tests/test_bash_gate_target_dir_653.py::test_mv_varianten_in_hauptordner_blocken`
- **AC-6:** Given die wirksame Gate-Config `openspec.yaml` liegt im Ordner `D` / When `cp --target-directory D x`, `cp --target-dir=D x`, `cp -vt D x`, `cp -tD x`, `ln -sft D x`, `install -Dt D x`, `install -m 644 --target-directory=D x` oder `mv -vt D x` mit `x` = `openspec.yaml` läuft / Then endet das Gate mit Exit 2 und der Config-Meldung der Prüfung 1b
  - Test: `tests/test_bash_gate_target_dir_653.py::test_config_als_ziel_ueber_alle_schreibweisen_blockt_1b`
- **AC-7:** Given eine Worktree-Sitzung / When dieselben Befehle ihren Zielordner im eigenen Worktree haben (z. B. `cp -vt wt/sub x`, `mv --target-dir=wt/sub x`, `install -Dt wt/sub x`) / Then bleibt das Gate bei Exit 0
  - Test: `tests/test_bash_gate_target_dir_653.py::test_zielordner_im_eigenen_worktree_bleibt_frei`
- **AC-8:** Given eine Worktree-Sitzung / When `cp -S .t x y`, `cp --suffix .t x y` oder `install -m 644 x y` mit `y` im eigenen Worktree läuft, wobei der Wert einer Wertoption wie ein Pfad im Haupt-Ordner aussieht / Then wird der Wert nicht als Zielordner gelesen, das Ziel ist `y`, und das Gate bleibt bei Exit 0
  - Test: `tests/test_bash_gate_target_dir_653.py::test_wert_von_S_suffix_und_m_ist_kein_zielordner`
- **AC-9:** Given eine Worktree-Sitzung / When das Zielordner-Flag hinter den Quellen steht (`cp x -t H`), `--` die Optionen beendet (`cp -t H -- x`) oder zwei Zielordner angegeben sind (`cp -t wt/sub -t H x`) / Then endet das Gate mit Exit 2 (Permutation, `--` und mehrere Zielordner werden erfasst)
  - Test: `tests/test_bash_gate_target_dir_653.py::test_permutation_doppelstrich_und_mehrere_zielordner`
- **AC-10:** Given eine Worktree-Sitzung, ein fremder Worktree im selben Haupt-Ordner, eine Sitzung im Haupt-Ordner selbst, ein gültiger Override-Token und ein nicht auflösbares Ziel (Variable, Glob, offene Quote) / When ein Befehl mit Zielordner-Flag läuft / Then bleibt der fremde Worktree gesperrt (Exit 2), die Haupt-Ordner-Sitzung, der Override (Exit 0) und das Fail-open unverändert
  - Test: `tests/test_bash_gate_target_dir_653.py::test_fremder_worktree_override_und_fail_open_unveraendert`
- **AC-11:** Given der bestehende Testbestand / When `tests/test_bash_gate_main_write_417.py`, `tests/test_bash_gate_config_lock_418.py`, `tests/test_bash_gate_symlink_parent_435.py`, `tests/test_proof_lock_453.py` und das übrige Regressionsnetz `tests/test_bash_gate*` (inklusive 447 und 448) laufen / Then bleiben sie grün
  - Test: die genannten Dateien, unverändert (Lauf grün)

> Die Test-Zuordnung wird **bei der Spec-Erstellung** eingetragen, nicht nachträglich:
> Nach der Freigabe ist diese Datei eingefroren (#230) — jede Änderung verschiebt den
> PO-Briefing-Hash und blockt den Workflow-Abschluss. Stimmt der Testname später nicht
> mehr, gehört die Korrektur in die TDD-RED-Artefakte (`workflow.py add-artifact`),
> nicht in diese Datei.

## Test Plan

Automatische Tests (jeweils an eine AC oben gebunden):

- `pytest tests/test_bash_gate_target_dir_653.py` — Subprozess-Tests gegen das echte `core/hooks/bash_gate.py`. Sandbox nach dem Muster `_worktree_sandbox`/`_expect` aus `tests/test_bash_gate_main_write_417.py`: Haupt-Ordner `main`, Worktree unter `main/.claude/worktrees/wt` mit Unterordner `sub`, fremder Worktree, Ordner mit `openspec.yaml` für 1b, Override-Token. Die RED-Läufe zeigen vor der Implementierung Exit 0 statt Exit 2 für die Varianten (AC-1 bis AC-6, AC-9) und werden als Artefakte registriert; die Frei-Fälle (AC-7, AC-8) und AC-10 sind schon vor der Änderung grün und sichern, dass der neue Zerleger keine Fehlalarme und keine Lücke öffnet.
- Regression: `pytest tests/test_bash_gate*` (insbesondere 417, 418, 435, 447, 448, 453), danach die Vollsuite.

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Die Änderung folgt der bestehenden Entscheidung „Gate prüft den Befehlstext vor dem Ausführen per Regeln, Ausweg ist der Override-Token“ (#299, #407, #417, #418, #435). Ein gemeinsamer Optionen-Zerleger ersetzt mehrere grobe Einzelerkennungen, ohne neues Muster, neue Abhängigkeit oder neuen Hook; keine bestehende Entscheidung wird gekippt. Die Sicherheitsrichtung bleibt „im Zweifel mehr Ziele“.
- **Verworfene Alternativen:**
  - *Weitere Sonderfälle in die bestehenden Erkennungen einbauen (je Schreibweise ein Muster):* bleibt lückenhaft und an drei Stellen doppelt gepflegt.
  - *`_cp_target_dir` (#453) wiederverwenden:* der Parser ist auf den Beleg-Schutz zugeschnitten und kennt weder `mv` noch `install`; Mitnutzung würde 1d riskieren.
  - *Externes `getopt`/`shlex`-Programm aufrufen:* neuer Subprozess bei jedem Bash-Aufruf, widerspricht dem Fail-open-Rahmen des Gates.

## Changelog

- 2026-11-26: Initial spec created (#653)
- Release-Hinweis: CHANGELOG `[4.26.5]` — „bash_gate: Zielordner-Flag von cp/install/ln/mv wird in allen gültigen Schreibweisen (-vt, -tDIR, --target-dir, mit = oder getrenntem Wert) als Schreibziel erkannt; Prüfungen 1b und 1c blocken damit wie bei der exakten Form (#653)“
