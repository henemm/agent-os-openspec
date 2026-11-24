---
entity_id: fix-435-symlink-parent
type: bugfix
created: 2026-11-24
updated: 2026-11-24
status: draft
workflow: fix-435-symlink-parent
version: "1.0"
tags: [bash-gate, worktree, schreibschutz, hauptordner, symlink, fehlalarm]
test_targets: ["tests/test_bash_gate_symlink_parent_435.py"]
---

# bash_gate 1c: Symlink im eigenen Worktree nicht als Haupt-Ordner-Schreibzugriff werten — #435

## Approval

- [ ] Approved

## GitHub Issue

- **Issue:** #435 (Epic #429). Folge aus #417 (Adversary-Befund F001). Grundlage ist die Spec `docs/specs/fix-417-bash-main-write.md`, Punkt 3 („resolve() damit Symlinks erfasst sind“). Die Prüfung 1b (wirksame Config, `_writes_effective_config`) ist **nicht** Teil dieser Spec und bleibt unverändert.

## Purpose

Prüfung 1c blockt Bash-Schreibzugriffe einer Worktree-Sitzung auf den Haupt-Ordner. Dazu löst sie jedes Schreibziel per `Path.resolve()` vollständig auf. Liegt im eigenen Worktree ein Symlink, der in den Haupt-Ordner zeigt (typisch `node_modules`), landet auch `rm node_modules` oder `mv node_modules x` im Haupt-Ordner und wird fälschlich blockiert; der Ausweg war bisher nur „override“. Die Spec lässt Befehle, die den Link **selbst** bearbeiten, frei (nur der Elternpfad wird aufgelöst, der letzte Bestandteil bleibt roh) und lässt jede Form, die **durch** den Link schreibt, weiter blocken. Schutz vor Versehen, kein Sandbox-Ersatz; rein regelbasiert, ohne Modell, ohne neuen Hook.

## Source

- **File:** `core/hooks/bash_gate.py` — `_writes_main_repo` (~Z.1266), `_lexical_path` (~Z.630), `_dir_removal_targets` (~Z.610), `_CONFIG_WRITERS` (~Z.552), `_segment_write_targets` (~Z.592), Aufrufer Abschnitt 1c (~Z.1900)
- **Identifier:** `_writes_main_repo` (geändert), `_link_acting_targets` (neu)
- **Vorbild:** #473 F002 (`_lexical_path` für die Config-Sperre 1b: `realpath(dirname)` plus roher Basename)
- **Analyse:** `docs/context/fix-435-symlink-parent.md`
- **Ursprungsanfrage:** GitHub-Issue #435

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `core/hooks/bash_gate.py` | Modul | Kern-Gate Bash; Ort der Änderung; läuft bei jedem Bash-Aufruf |
| `_segment_write_targets`, `_split_redirects`, `_command_args`, `_positional`, `_cd_bases` | Funktionen im Gate | liefern Segmente, Basis, Ziele und Umleitungen; unverändert |
| `_dir_removal_targets`, `_lexical_path` | Funktionen im Gate | Quellen von `rm`/`mv`/`git rm\|mv\|checkout\|restore` und lexikalischer Pfad; werden wiederverwendet |
| `core/hooks/override_token.py` (über `_any_override_token`) | Modul | Ausweg des Schutzes; unverändert |
| `tests/test_bash_gate_main_write_417.py` | Test | Vorlage für `_worktree_sandbox` und `_expect`; wird nicht verändert |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| `core/hooks/bash_gate.py` | MODIFY | Neue Hilfsfunktion `_link_acting_targets(seg)`; `_writes_main_repo` prüft diese Tokens lexikalisch, alle übrigen wie bisher per `resolve()` |
| `tests/test_bash_gate_symlink_parent_435.py` | CREATE | Subprozess-Tests gegen das echte Gate: Fehlalarm weg, Durchschreib-Fälle blocken weiter |
| `CHANGELOG.md` | MODIFY | Eintrag `[4.20.3]` samt Known Limitations |
| `.claude-plugin/plugin.json`, `CLAUDE.md` (Kopfzeile), `README.md` (Kopfzeile), `skills/*/SKILL.md` und `.claude/commands/*.md` (Befehls-Marker `agent-os-openspec 4.20.x`) | MODIFY | Patch-Version 4.20.3; Skills über `python3 scripts/sync_skills.py`, nie von Hand |

**Nicht ändern:** `_writes_effective_config` und `_removes_config_dir` (1b), `worktree_write_guard.py`, `hook_utils.py`, `hooks/hooks.json`.

### Estimated Changes

- Files: 1 Code-Datei, 1 Testdatei, dazu Changelog und Versionsstellen
- LoC: ca. +40/-3 im Gate, ca. +150 in den Tests
- Alle Funktionen bleiben unter 50 Zeilen.

## Implementation Details

**1. Link-Rollen je Segment.** `_link_acting_targets(seg)` liefert die Tokens eines Segments, die den Link selbst bearbeiten:

- `rm`, `unlink`: alle Positionsargumente.
- `mv` und `git rm|mv|checkout|restore`: die Quellen (über `_dir_removal_targets`); das Ziel von `mv` nur mit `-T` bzw. `--no-target-directory`.
- `touch`: nur mit `-h` bzw. `--no-dereference` (auch in kombinierten Kurzflags).
- `ln`: das Ziel nur mit `-n`, `-T`, `--no-dereference` oder `--no-target-directory` (auch in `-sfn`, `-sfT`).

**2. Lexikalisch nur unter drei Bedingungen.** Ein Token wird mit `_lexical_path(basis, token)` (Elternordner aufgelöst, letzter Bestandteil roh) geprüft, wenn (a) es in der Link-Liste steht, (b) dasselbe Token im selben Segment nicht zugleich Umleitungsziel oder ein sonstiges folgendes Schreibziel ist und (c) sein letzter Bestandteil ein normaler Name ist (kein abschließendes `/`, nicht `.`, nicht `..`). Erfüllt es eine Bedingung nicht, gilt der bisherige Weg `(basis / expanduser(token)).resolve()`.

**3. Sicherheitsrichtung bleibt „aufgelöst“.** Alles, was nicht ausdrücklich als Link-Rolle erkannt ist (Umleitungen, `cp`, `install`, `tee`, `truncate`, `dd of=`, `sed -i`, `perl -i`, `touch` ohne `-h`, `mv`-Ziel ohne `-T`, `ln` ohne `-n`/`-T`, unbekannte oder neue Befehle in `_CONFIG_WRITERS`), bleibt aufgelöst und blockt weiter. Ein Pfad, dessen Elternteil der Link ist (`L/a`), wird durch `realpath(dirname)` ohnehin aufgelöst und blockt.

**4. Blockbedingung unverändert.** Der (lexikalische oder aufgelöste) Pfad blockt, wenn er unter dem Haupt-Ordner und nicht unter dem eigenen Worktree liegt. Ein Link, der selbst im Haupt-Ordner liegt, hat einen lexikalischen Pfad im Haupt-Ordner und blockt daher auch bei `rm`.

**5. Basis-Nachführung.** Die Basis folgt weiter `_cd_bases`; `cd node_modules/..` oder `cd sub && rm ../L` im Worktree-Unterordner führt zum selben lexikalischen Ergebnis wie vom Worktree-Wurzelordner.

**6. Meldung, Override, Fail-open.** Abschnitt 1c, Block-Meldung (1c-Text mit Hinweis auf „override“), Override-Token und Fail-open bei `$`, Backtick, Glob, offener Quote oder Exception bleiben unverändert.

## Expected Behavior

- **Input:** Ein Bash-Befehl durch `bash_gate.py`, cwd im Worktree `W`; `L` ist ein Symlink in `W`, der auf einen Ordner (oder eine Datei) im Haupt-Ordner `H` zeigt.
- **Output:** Befehle, die `L` selbst entfernen, umbenennen oder ersetzen, enden mit Exit 0. Befehle, die durch `L` hindurch schreiben, enden weiter mit Exit 2 und der 1c-Meldung.
- **Side effects:** Keine neuen Subprozesse, Abhängigkeiten oder Config-Keys.

| Befehl (cwd `W`, `L` zeigt nach `H`) | Heute | Soll |
|--------|-------|------|
| `rm L`, `rm -f L`, `rm -rf L`, `unlink L` | 2 | 0 |
| `mv L L.bak`, `mv -T x L` | 2 | 0 |
| `touch -h L`, `ln -sfn ziel L`, `ln -sfT ziel L` | 2 | 0 |
| `git rm L`, `git checkout -- L`, `git restore L` | 2 | 0 |
| dieselben Befehle nach `cd` in einen Unterordner von `W` | 2 | 0 |
| `echo x > L/a`, `echo x > L` (L zeigt auf Datei) | 2 | 2 |
| `cp x L`, `mv x L`, `ln -sf x L`, `touch L`, `tee L/a` | 2 | 2 |
| `rm -r L/`, `rm -rf L/.`, `rm L/a` | 2 | 2 |
| `rm L > L` (Link-Rolle und Umleitungsziel) | 2 | 2 |
| `rm L2` mit `L2` als Link im Haupt-Ordner `H` | 2 | 2 |
| Fremder Worktree als Ziel; Sitzung im Haupt-Ordner; Override; nicht auflösbares Ziel | unverändert | unverändert |

## Known Limitations

- **Kein Sandbox-Ersatz:** `python -c`, `sh -c` mit Variablen, `eval`, Backticks und Skripte, die selbst schreiben, bleiben unerkannt (Ticket #416); wie in der Spec zu #417.
- **Konservativ aufgelöst:** `sed -i`, `perl -i`, `truncate`, `dd of=` und unbekannte Schreibbefehle auf einen Link bleiben blockiert, auch wenn sie den Link nur ersetzen könnten (`sed -i` mit `--follow-symlinks` aus). Ausweg: „override“.
- **BSD/macOS:** `rm -r L/` löscht dort den Inhalt des Ziels, GNU verweigert. Der abschließende Schrägstrich bleibt deshalb auf beiden aufgelöst und blockiert.
- **Hängende Links:** Ein Link, dessen Ziel nicht existiert, wird bei `touch L` (ohne `-h`) als Zieldatei im Haupt-Ordner gewertet und blockiert, wie beabsichtigt.
- Die Prüfung 1b (wirksame Config) behält ihre eigene Link-Behandlung.
- Verteilung: wirkt in Konsumentenprojekten erst nach dem Plugin-Update.

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test am echten Gate-Subprozess belegt
- [ ] In einer Worktree-Sitzung lassen sich der eigene `node_modules`-Link (zeigt in den Haupt-Ordner) löschen, umbenennen und neu setzen, ohne „override“ tippen zu müssen
- [ ] Jede Befehlsform, die durch den Link in den Haupt-Ordner schreibt (Umleitung, `cp`, `mv` ohne `-T`, `tee`, `touch` ohne `-h`, `rm -r L/`, `rm L/a`), endet weiter mit Exit 2 und dem Hinweis auf „override“
- [ ] Fremder Worktree, Haupt-Ordner-Sitzung, nicht auflösbare Ziele, Override und Prüfung 1b verhalten sich unverändert
- [ ] CHANGELOG-Eintrag `[4.20.3]` mit Known Limitations; Version 4.20.3 an allen Stellen (plugin.json, CLAUDE.md, README.md, Skills und Befehls-Marker per `sync_skills.py`)
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (`tests/test_bash_gate*` und Vollsuite grün)

## Acceptance Criteria

- **AC-1:** Given eine Worktree-Sitzung mit einem Link L im eigenen Worktree, der in den Haupt-Ordner zeigt / When `rm L`, `rm -f L`, `rm -rf L` oder `unlink L` läuft / Then bleibt das Gate bei Exit 0
  - Test: `tests/test_bash_gate_symlink_parent_435.py::test_rm_und_unlink_auf_link_bleiben_frei`
- **AC-2:** Given eine Worktree-Sitzung mit Link L in den Haupt-Ordner / When `mv L L.bak` oder `mv -T x L` läuft / Then bleibt das Gate bei Exit 0
  - Test: `tests/test_bash_gate_symlink_parent_435.py::test_mv_von_und_mit_T_auf_link_bleibt_frei`
- **AC-3:** Given eine Worktree-Sitzung mit Link L in den Haupt-Ordner / When `touch -h L`, `ln -sfn <ziel> L` oder `ln -sfT <ziel> L` läuft / Then bleibt das Gate bei Exit 0
  - Test: `tests/test_bash_gate_symlink_parent_435.py::test_touch_h_und_ln_sfn_auf_link_bleiben_frei`
- **AC-4:** Given eine Worktree-Sitzung mit Link L in den Haupt-Ordner / When `git rm L`, `git checkout -- L` oder `git restore L` läuft / Then bleibt das Gate bei Exit 0
  - Test: `tests/test_bash_gate_symlink_parent_435.py::test_git_rm_checkout_restore_auf_link_bleiben_frei`
- **AC-5:** Given eine Worktree-Sitzung mit Link L / When dieselben freien Befehle nach `cd` in einen Unterordner des Worktrees mit relativem Pfad zum Link laufen / Then bleibt das Gate bei Exit 0 (Basis-Nachführung)
  - Test: `tests/test_bash_gate_symlink_parent_435.py::test_freie_befehle_nach_cd_in_unterordner_bleiben_frei`
- **AC-6:** Given eine Worktree-Sitzung mit Link L in den Haupt-Ordner / When eine Umleitung `> L/a` oder `> L` (L zeigt auf eine Datei) läuft / Then endet das Gate mit Exit 2 und der 1c-Meldung mit Hinweis auf „override“
  - Test: `tests/test_bash_gate_symlink_parent_435.py::test_umleitung_durch_link_blockt`
- **AC-7:** Given eine Worktree-Sitzung mit Link L in den Haupt-Ordner / When `cp x L`, `mv x L` (ohne `-T`), `ln -sf x L` (ohne `-n`/`-T`), `touch L` (ohne `-h`) oder `tee L/a` läuft / Then endet das Gate mit Exit 2
  - Test: `tests/test_bash_gate_symlink_parent_435.py::test_folgende_befehle_durch_link_blocken`
- **AC-8:** Given eine Worktree-Sitzung mit Link L in den Haupt-Ordner / When `rm -r L/` (abschließender Schrägstrich), `rm -rf L/.` oder `rm L/a` (Elternteil ist der Link) läuft / Then endet das Gate mit Exit 2
  - Test: `tests/test_bash_gate_symlink_parent_435.py::test_schraegstrich_punkt_und_unterpfad_blocken`
- **AC-9:** Given eine Worktree-Sitzung mit Link L in den Haupt-Ordner / When dasselbe Token zugleich Link-Rolle und Umleitungsziel ist (`rm L > L`) / Then endet das Gate mit Exit 2
  - Test: `tests/test_bash_gate_symlink_parent_435.py::test_link_rolle_plus_umleitungsziel_blockt`
- **AC-10:** Given ein Link, der selbst im Haupt-Ordner liegt (Pfad außerhalb des eigenen Worktrees) / When `rm` auf diesen Link läuft / Then endet das Gate mit Exit 2 (lexikalischer Pfad liegt im Haupt-Ordner)
  - Test: `tests/test_bash_gate_symlink_parent_435.py::test_link_im_hauptordner_blockt_bei_rm`
- **AC-11:** Given eine Worktree-Sitzung und ein fremder Worktree im selben Haupt-Ordner, außerdem eine Sitzung im Haupt-Ordner selbst / When ein Befehl in den fremden Worktree schreibt bzw. in der Haupt-Ordner-Sitzung ein Befehl auf einen Link läuft / Then bleibt der fremde Worktree gesperrt (Exit 2) und die Haupt-Ordner-Sitzung verhält sich unverändert
  - Test: `tests/test_bash_gate_symlink_parent_435.py::test_fremder_worktree_und_hauptordner_sitzung_unveraendert`
- **AC-12:** Given eine Worktree-Sitzung mit Link L / When das Ziel nicht auflösbar ist (Variable, Glob, offene Quote) oder ein gültiger Override-Token vorliegt / Then bleibt das Gate fail-open bzw. lässt den blockierten Befehl mit Exit 0 durch
  - Test: `tests/test_bash_gate_symlink_parent_435.py::test_fail_open_und_override_wirken_wie_bisher`
- **AC-13:** Given eine Worktree-Sitzung, deren wirksame Gate-Config im Haupt-Ordner liegt / When ein Schreibbefehl diese Config trifft / Then bleibt der Block 1b mit seiner eigenen Config-Meldung unverändert
  - Test: `tests/test_bash_gate_symlink_parent_435.py::test_config_sperre_1b_bleibt_unveraendert`
- **AC-14:** Given der bestehende Testbestand / When `tests/test_bash_gate_main_write_417.py` und das Regressionsnetz `tests/test_bash_gate*` laufen / Then bleiben sie grün
  - Test: `tests/test_bash_gate_main_write_417.py` (unverändert, Lauf grün)

> Die Test-Zuordnung wird **bei der Spec-Erstellung** eingetragen, nicht nachträglich:
> Nach der Freigabe ist diese Datei eingefroren (#230) — jede Änderung verschiebt den
> PO-Briefing-Hash und blockt den Workflow-Abschluss. Stimmt der Testname später nicht
> mehr, gehört die Korrektur in die TDD-RED-Artefakte (`workflow.py add-artifact`),
> nicht in diese Datei.

## Test Plan

Automatische Tests (jeweils an eine AC oben gebunden):

- `pytest tests/test_bash_gate_symlink_parent_435.py` — Subprozess-Tests gegen das echte `core/hooks/bash_gate.py`. Sandbox nach dem Muster `_worktree_sandbox`/`_expect` aus `tests/test_bash_gate_main_write_417.py`: Haupt-Ordner `main` mit `node_modules`, Worktree unter `main/.claude/worktrees/wt` mit echtem Symlink `wt/node_modules -> ../../../node_modules`; zusätzlich ein fremder Worktree, ein Unterordner im Worktree, ein Link im Haupt-Ordner und ein Override-Token. Die RED-Läufe zeigen vor der Implementierung Exit 2 statt Exit 0 für die freien Fälle (AC-1 bis AC-5) und werden als Artefakte registriert; die Block-Fälle (AC-6 bis AC-10) sind schon vor der Änderung grün und sichern, dass die Lockerung keine Lücke öffnet.
- Regression: `pytest tests/test_bash_gate*` (insbesondere #417, #418, #473), danach die Vollsuite.

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Die Änderung folgt der bestehenden Entscheidung „Gate prüft den Befehlstext vor dem Ausführen per Regeln, Ausweg ist der Override-Token“ (#299, #407, #417, #418) und übernimmt das Muster `_lexical_path` aus #473 F002 für 1c. Kein neues Muster, keine neue Abhängigkeit, kein neuer Hook; keine bestehende Entscheidung wird gekippt. Die Sicherheitsrichtung bleibt „im Zweifel aufgelöst“.
- **Verworfene Alternativen:**
  - *Alles lexikalisch prüfen und nur Link-Folgen gesondert erkennen:* kehrt die Sicherheitsrichtung um; ein neuer Befehl in `_CONFIG_WRITERS` wäre standardmäßig offen.
  - *Jeder Link im eigenen Worktree ist frei:* öffnet `echo > L/a`, `cp x L` und `touch L` in den Haupt-Ordner.
  - *Nur Doku/override belassen:* verfehlt das Ziel des Issues, der Fehlalarm träte bei jedem `node_modules`-Wechsel wieder auf.

## Changelog

- 2026-11-24: Initial spec created (#435)
- Release-Hinweis: CHANGELOG `[4.20.3]` — „bash_gate 1c: Befehle, die einen Symlink im eigenen Worktree selbst bearbeiten (rm, unlink, mv, touch -h, ln -sfn/-T, git rm/checkout/restore), werden nicht mehr als Schreibzugriff auf den Haupt-Ordner geblockt; Schreiben durch den Link blockt weiter (#435)“
