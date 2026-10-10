---
entity_id: fix-418-config-lock-precision
type: bugfix
created: 2026-10-10
updated: 2026-10-10
status: draft
workflow: fix-418-config-lock-precision
version: "1.0"
tags: [bash-gate, config-lock, schreibziele, cd-kontext, fehlalarm]
test_targets: ["tests/test_bash_gate_config_lock_418.py"]
---

# bash_gate: Config-Sperre trifft nur Schreibziele, Langformen und cd im Befehl — #418

## Approval

- [ ] Approved

## GitHub Issue

- **Issue:** #418 (Folge zu #410, Befunde F001 bis F003 aus der Gegenprüfung). Die Prüfung an der Quelle (vorsätzliche Umgehung per `bash -c`, Variablen, Globs) ist **nicht** Teil dieser Spec, sondern Ticket #416. Allgemeiner Bash-Schreibzugriff aufs Hauptrepo ist #417 und ebenfalls außerhalb.

## Purpose

Die Config-Sperre (Prüfung 1b in `core/hooks/bash_gate.py`, Funktion `_writes_effective_config`) schützt die wirksame Gate-Konfiguration, aus der alle Kill-Switches gelesen werden, vor Schreibzugriffen per Bash. Sie prüft heute zwei voneinander unabhängige Dinge: „irgendein Schreib-Indikator im Segment“ und „irgendein Argument zeigt auf die Config“. Daraus folgen drei Fehler: (A) Lesende Befehle mit Umleitung oder Kopierziel blocken zu Unrecht, weil die Lese-**Quelle** auf die Config zeigt (`cat openspec.yaml > copy`, `cp openspec.yaml backup.yaml`). (B) Mehrere versehentlich auslösbare Schreibformen rutschen durch (`sed --in-place`, `sed -ni`, `perl -pi`, `>|`, `git checkout/restore`, `ln -sf`). (C) Ein `cd` im selben Befehl wird ignoriert: Die Auflösung nutzt immer `Path.cwd()`. Die Spec ersetzt die Rate-Logik durch eine Prüfung der tatsächlichen **Schreibziele**, mit nachgeführtem Arbeitsverzeichnis. Rein regelbasiert, ohne Modell, ohne neuen Subprozess, ohne neue Abhängigkeit.

## Source

- **File:** `core/hooks/bash_gate.py` — `_writes_effective_config` (~Z.378-407), Aufruf Prüfung 1b im Hauptablauf (~Z.973-981), Vorlage für die `cd`-Nachführung: `_cd_into_claude` / `_cd_context_protected` / `_dir_token_in_cd_context`
- **Analyse:** `docs/context/fix-418-config-lock-precision.md`, Abschnitte „Reproduktion“, „Root Cause“, „Lexer-Befund“, „Recherche“, „Technical Approach“, „Alternativen“, „Known Limitations“
- **Ursprungsanfrage:** GitHub-Issue #418
- **Befunde:** `docs/artifacts/fix-410-state-integrity-gaps/adversary-dialog.md` (F001 bis F003)

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `core/hooks/bash_gate.py` | Modul | Kern-Gate Bash, Prüfung 1b; läuft bei jedem Bash-Aufruf in jedem Konsumentenprojekt, auch ohne Workflow, vor dem Git-Schnellweg |
| `core/hooks/hook_utils.py` (`_git_segments`, `_git_lex`, `SECRETS_FREETEXT_FLAGS`, `find_project_root`) | Modul | Zerlegung in trennerfreie Segmente; Umleitungsoperatoren (`>`, `>>`, `>\|`, `&>`, `>&`) sind eigene Token, das Ziel ist das nächste Token; unverändert |
| `core/hooks/config_loader.py` (`find_config_file`) | Modul | Liefert die tatsächlich geladene Config-Datei; im Worktree die Datei im Hauptordner; unverändert |
| `core/hooks/override_token.py` (`has_valid_token`, über `_any_override_token`) | Modul | Ausweg der Config-Sperre; unverändert |
| `tests/test_bash_gate_state_integrity_410.py` | Test | Quelle der Sandbox-Helfer (Subprozess gegen echtes Gate, mit/ohne Workflow, echter Worktree, Override-Token); wird importiert, nicht verändert; AC-4 bis AC-7 aus #410 müssen grün bleiben |
| `docs/specs/fix-410-state-integrity-gaps.md` | Spec | Direkter Vorgänger; Known Limitations verweisen auf diese Folgearbeit |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| `core/hooks/bash_gate.py` | MODIFY | Neue 1b-eigene Zielextraktion `_config_write_targets(seg) -> list[str]` (mit kleinen Hilfsfunktionen je Kommandogruppe); `_writes_effective_config` vergleicht nur noch diese Schreibziele und führt die Basis über `cd`/`pushd`-Segmente nach |
| `tests/test_bash_gate_config_lock_418.py` | CREATE | Subprozess-Tests gegen das echte Gate: A frei, B blockt, C blockt, C-Spiegelbild frei, Gegenprobe, Worktree-Kopie, Override, fail-open |
| `CHANGELOG.md` | MODIFY | Eintrag unter `[Unreleased]`, **kein** Versions-Bump |

**Nicht ändern:** `WRITE_INDICATORS`, `_has_write_indicator` und `_has_real_redirect` (werden von Prüfung 3a/3b mitbenutzt, eine Änderung hätte Seiteneffekte auf die State-Integrity-Prüfung), `core/hooks/hook_utils.py` (Lexer ist korrekt), `core/hooks/secret_egress_guard.py` (eigene Kopie von `_shell_write_targets` bleibt; ein gemeinsamer Helfer kommt frühestens mit #417).

### Estimated Changes

- Files: 3 (Grenze 4-5 eingehalten)
- LoC: ca. +245/-15 (Gate ca. +95/-15, Tests ca. +130, Changelog ca. +5, in Summe knapp unter der Grenze von ±250). Spec, Analyse-Kontext und PO-Briefing zählen im LoC-Gate zusätzlich als Code (#294, Fehlalarm); mit laufendem Workflow ab phase6 entfällt der Override für `core/hooks/` (#322).
- Alle Funktionen bleiben unter 50 Zeilen; die Zielextraktion wird dazu je Kommandogruppe in Hilfsfunktionen geteilt.
- Schnittreserve ist bereits gezogen: `patch`, `ex -s`/`vim -c` und `git apply` sind nicht abgedeckt (siehe Known Limitations). Droht die Umsetzung trotzdem über 250 LoC, wird zuerst der `pushd`-Zweig gestrichen, danach bei Henning mit konkreter Zahl nachgefragt.

## Implementation Details

**1. Zielbasierte Prüfung statt „Indikator plus irgendein Token“.** `_writes_effective_config` ruft für jedes Segment die neue Funktion `_config_write_targets(seg) -> list[str]` auf. Sie liefert nur die Tokens, die der Befehl **beschreibt** (oder entfernt, ersetzt, verlinkt). Nur diese werden gegen die Basis aufgelöst (`Path.resolve()`) und mit `find_config_file(find_project_root())` verglichen. Lese-Quellen zählen nie. `WRITE_INDICATORS` wird für 1b nicht mehr benutzt, bleibt aber unverändert für 3a/3b.

**2. Abgedeckte Schreibformen.** Vor dem Kommandowort werden die Präfixe `sudo`, `command`, `env` und `VAR=x` übersprungen. Tokens nach `SECRETS_FREETEXT_FLAGS` werden übersprungen (wie bisher). Ein leeres Token (`-i ''`) wird vor `resolve()` gefiltert, sonst träfe es die Basis selbst.

| Form | Ziel |
|------|------|
| Umleitung `>`, `>>`, `>\|`, `&>`, `>&` (bei jedem Kommando) | das Token nach dem Operator; ausgenommen reine fd-Ziffer, `-` und `/dev/null` |
| `cp`, `install`, `ln` | letztes Nicht-Flag-Argument; bei `-t DIR` bzw. `--target-directory=DIR` jeweils `DIR/<basename der Quelle>` |
| `mv` | alle Nicht-Flag-Argumente (die Quelle verschwindet ebenfalls) |
| `rm`, `unlink`, `truncate`, `touch`, `tee` | alle Nicht-Flag-Argumente |
| `sed` | nur In-Place: Kurzflag-Cluster mit `i` (`-i`, `-ni`, `-i.bak`, `-i ''`) oder `--in-place[=SUF]`; ohne `-e`/`-f` ist das erste Nicht-Flag-Token das Skript und wird übersprungen, danach alle Dateien |
| `perl` | nur mit `-i`-Cluster (`-pi`, `-i.bak`); das `-e`-Skript wird übersprungen, der Rest sind Dateien |
| `git checkout`, `git restore` | alle Pfadargumente (Branchnamen lösen nicht auf die Config auf und lösen damit nichts aus) |
| `dd` | `of=X` |
| `yq` | nur mit `-i`; alle Nicht-Flag-Token als Kandidaten |

**3. `cd`-Nachführung (Teil C).** Die Basis startet bei `Path.cwd()`. Ein Segment `cd <pfad>` oder `pushd <pfad>` setzt `base = (base / pfad).resolve()` (`~` per `expanduser`). Die Folgesegmente werden gegen die dann gültige Basis aufgelöst. Ist das Ziel nicht auflösbar (`cd $X`, `cd -`, `cd` ohne Argument, Glob oder Backtick), werden die Folgesegmente gegen die alte Basis **und** gegen `cwd` geprüft; das erzeugt keinen neuen Block-Grund über das heutige Verhalten hinaus. Das Muster der segmentweisen Nachführung folgt `_cd_context_protected`.

**4. Fail-open bleibt.** Lässt sich der Befehl nicht zerlegen (`_git_segments` liefert `None`), ist die Zielliste leer. Jede Exception in der Zielextraktion ergibt „kein Treffer“. Der Block-Text mit „override“ als Ausweg und die Geltung ohne aktiven Workflow bleiben unverändert (#410 AC-5, AC-6).

**5. Spiegelbild von Teil C.** Dieselbe Basis-Nachführung macht ein heutiges Fehlverhalten sichtbar: `cd docs && sed -i s/a/b/ openspec.yaml` beschreibt `docs/openspec.yaml`, nicht die wirksame Config, wird heute aber mit Exit 2 geblockt, weil das Token gegen `cwd` aufgelöst wird. Künftig ist dieser Befehl frei. Das ist nicht im Ticket genannt, folgt aber zwingend aus Teil C (siehe Kritische Hinweise).

**6. Unberührt:** Prüfung 3a/3b, `_redirects_to_protected`, Secrets-Pfade, Freitext-Ausnahme, alle `workflow.py`-Aufrufe, `edit_gate.py`.

## Expected Behavior

- **Input:** Ein Bash-Befehl durch `bash_gate.py`, mit oder ohne aktiven Workflow.
- **Output:** Befehle, die die wirksame Config beschreiben, ersetzen, entfernen oder verlinken, enden mit Exit 2 und der bestehenden Config-Meldung mit Hinweis auf „override“. Befehle, die sie nur lesen, enden mit Exit 0.
- **Side effects:** Keine neuen Subprozesse, keine neuen Abhängigkeiten, keine geänderten AppStorage-/Config-Keys. Prüfung 3a/3b verhält sich unverändert.

`cfg` steht für die wirksame Config, im Beispiel `openspec.yaml` im Projektstamm.

| Befehl | Heute | Soll |
|--------|-------|------|
| `git diff openspec.yaml > x.patch`, `grep a openspec.yaml > out.txt`, `cat openspec.yaml > copy`, `cp openspec.yaml backup.yaml`, `cp -t backup/ openspec.yaml` | 2 | 0 |
| `cat openspec.yaml \| tee copy` | 0 | 0 |
| `echo x > cfg`, `echo x >> cfg`, `sed -i s/a/b/ cfg`, `cp x cfg`, `mv x cfg`, `mv cfg old`, `cat x \| tee cfg`, `truncate -s0 cfg`, `rm cfg` (Gegenprobe) | 2 | 2 |
| `sed -i.bak s/a/b/ cfg` | 2 | 2 |
| `sed --in-place s/a/b/ cfg`, `sed -ni 's/a/b/p' cfg`, `sed -i '' s/a/b/ cfg` | 0 | 2 |
| `perl -pi -e 's/a/b/' cfg`, `perl -i.bak -pe 's/a/b/' cfg` | 0 | 2 |
| `echo x >\| cfg`, `echo x &> cfg` | 0 | 2 |
| `git checkout -- cfg`, `git restore cfg` | 0 | 2 |
| `ln -sf x cfg`, `install x cfg`, `dd if=x of=cfg`, `yq -i .a=1 cfg` | 0 | 2 |
| `cp x -t DIR` mit `DIR/<name>` = cfg (Zielverzeichnis-Form) | 0 | 2 |
| `ex -s cfg`, `patch cfg x.diff`, `git apply x.diff` | 0 | 0 (Known Limitation) |
| `cd docs && sed -i s/a/b/ ../openspec.yaml`, `cd docs; echo x > ../openspec.yaml` | 0 | 2 |
| Worktree: `cd ../../.. && sed -i s/a/b/ openspec.yaml` (trifft die Datei im Hauptordner) | 0 | 2 |
| `cd docs && sed -i s/a/b/ openspec.yaml` (trifft `docs/openspec.yaml`, Spiegelbild) | 2 | 0 |
| Worktree: `sed -i s/a/b/ openspec.yaml` auf die Worktree-Kopie | 0 | 0 |
| nicht zerlegbarer Befehl (offene Quote), `cd $X && sed -i s/a/b/ openspec.yaml` | 0 bzw. 2 | fail-open: erhält das heutige Verhalten, kein neuer Block |

## Known Limitations

- **Nicht abgedeckt, bewusst (Schnittreserve):** `patch cfg x.diff` und `patch < x.diff` (das Ziel steht nur im Diff bzw. selten und nicht versehentlich), `ex -s cfg` / `vim -c` mit Skript über stdin (selten, nicht versehentlich), `git apply x.diff` (Ziel steht nur im Diff). Diese Formen bleiben Exit 0 und fallen unter die Prüfung an der Quelle, Ticket #416.
- **`cd` in Subshells `( … )` und in `||`-Zweigen:** wird linear über die Segmente nachgeführt, nicht zweiggenau. Das kann in Randfällen die falsche Basis wählen; fail-open-seitig bleibt die alte Basis zusätzlich im Spiel, soweit das Ziel nicht auflösbar ist.
- **Variablen, Globs, `bash -c`, `eval`, `$(…)`, Backticks:** Textprüfung ist grundsätzlich umgehbar (Belege in `docs/specs/fix-410-state-integrity-gaps.md`, Known Limitations). Vorsätzliche Umgehung löst nur #416. Diese Spec härtet nur **versehentlich** auslösbare Schreibformen.
- **Hauptordner allgemein aus dem Worktree** (nicht nur die Config): bleibt offen, siehe #417. Die Basis-Nachführung hier ist so gebaut, dass #417 sie später wiederverwenden kann; ein gemeinsamer Helfer wird in diesem Ticket nicht gebaut.
- Die Worktree-Kopie der Config ist bewusst frei (wirkt erst nach dem Merge).
- Verteilung: wirkt in Konsumentenprojekten erst nach dem Plugin-Update.

## Kritische Hinweise

- **Abweichung vom Ticket, folgt aus Teil C:** Das Ticket nennt nur den Durchrutscher (`cd docs && sed -i … ../openspec.yaml` muss blocken). Dieselbe `cd`-Nachführung macht aber auch das Spiegelbild frei: `cd docs && sed -i s/a/b/ openspec.yaml` trifft `docs/openspec.yaml`, nicht die wirksame Config, und war bisher ein Fehlalarm (Exit 2). Das ist nicht im Ticket, aber die korrekte Folge; ein Teil C ohne Spiegelbild wäre ein halb umgesetzter Pfadvergleich (AC-9).
- **Fehlalarm-Richtung ist teuer:** Prüfung 1b läuft ohne Workflow in jedem Konsumentenprojekt vor dem Git-Schnellweg; der einzige Ausweg ist „override“. Deshalb gilt: im Zweifel nicht zerlegbar heißt frei (fail-open), und neue Formen kommen nur mit Gegenprobe-Test hinzu.
- **Sicherheitsgewinn ist begrenzt:** Textprüfung bleibt umgehbar; Teil B schließt nur die versehentlich auslösbaren Langformen.

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test am echten Gate-Subprozess belegt
- [ ] Alle Beispiele aus Teil A laufen mit Exit 0, alle abgedeckten Formen aus Teil B und Teil C mit Exit 2, das Spiegelbild von Teil C mit Exit 0
- [ ] Die Gegenprobe (echte Schreibzugriffe auf die Config) blockt weiterhin vollständig; die Worktree-Kopie bleibt frei; „override“ gibt die Config weiterhin frei
- [ ] Known Limitations (`patch`, `ex`/`vim -c`, `git apply`, Subshell-/`||`-Zweige, #416, #417) sind in der Spec und im CHANGELOG-Eintrag benannt
- [ ] `tests/test_bash_gate_state_integrity_410.py` und das Regressionsnetz `tests/test_bash_gate*` sind grün, ebenso die Vollsuite

## Acceptance Criteria

- **AC-1:** Given eine Projektwurzel mit wirksamer Config / When ein lesender Befehl mit Umleitung oder Kopierziel läuft (`git diff openspec.yaml > x.patch`, `grep a openspec.yaml > out.txt`, `cat openspec.yaml > copy`, `cp openspec.yaml backup.yaml`, `cp -t backup/ openspec.yaml`, `cat openspec.yaml | tee copy`) / Then bleibt das Gate bei Exit 0, weil die Config nur Lese-Quelle ist
  - Test: `tests/test_bash_gate_config_lock_418.py::test_teil_a_lesende_befehle_bleiben_frei`
- **AC-2:** Given eine Projektwurzel mit wirksamer Config / When `sed --in-place`, `sed -ni`, `sed -i ''`, `perl -pi -e` oder `perl -i.bak -pe` die Config trifft / Then blockt das Gate mit Exit 2 und nennt „override“ in der Meldung
  - Test: `tests/test_bash_gate_config_lock_418.py::test_teil_b_inplace_langformen_blocken`
- **AC-3:** Given eine Projektwurzel mit wirksamer Config / When `echo x >| cfg`, `echo x &> cfg`, `git checkout -- cfg`, `git restore cfg`, `ln -sf x cfg`, `install x cfg`, `dd if=x of=cfg`, `yq -i .a=1 cfg` oder `cp x -t DIR` (Ziel `DIR/<name>` = Config) läuft / Then blockt das Gate mit Exit 2
  - Test: `tests/test_bash_gate_config_lock_418.py::test_teil_b_umleitung_git_und_kopierformen_blocken`
- **AC-4:** Given eine Projektwurzel mit wirksamer Config / When `cd docs && sed -i s/a/b/ ../openspec.yaml` oder `cd docs; echo x > ../openspec.yaml` läuft, und in einer Worktree-Sitzung `cd ../../.. && sed -i s/a/b/ openspec.yaml` (Datei im Hauptordner) / Then blockt das Gate mit Exit 2
  - Test: `tests/test_bash_gate_config_lock_418.py::test_teil_c_cd_im_befehl_blockt`
- **AC-5:** Given eine Projektwurzel mit wirksamer Config / When `cd docs && sed -i s/a/b/ openspec.yaml` läuft (trifft `docs/openspec.yaml`, nicht die wirksame Config) / Then bleibt das Gate bei Exit 0 (Spiegelbild von Teil C)
  - Test: `tests/test_bash_gate_config_lock_418.py::test_teil_c_spiegelbild_bleibt_frei`
- **AC-6:** Given eine Projektwurzel mit wirksamer Config / When die Gegenprobe läuft (`echo x > cfg`, `echo x >> cfg`, `sed -i s/a/b/ cfg`, `sed -i.bak s/a/b/ cfg`, `cp x cfg`, `mv x cfg`, `mv cfg old`, `cat x | tee cfg`, `truncate -s0 cfg`, `rm cfg`) / Then blockt das Gate weiterhin jeden dieser Befehle mit Exit 2
  - Test: `tests/test_bash_gate_config_lock_418.py::test_gegenprobe_echte_schreibzugriffe_blocken_weiter`
- **AC-7:** Given eine Worktree-Sitzung / When `sed -i s/a/b/ openspec.yaml` die Worktree-Kopie trifft (nicht die aufgelöste Datei im Hauptordner) / Then bleibt das Gate bei Exit 0; und Given ein gültiger Override-Token / When ein Schreibbefehl auf die wirksame Config läuft / Then lässt das Gate ihn mit Exit 0 durch
  - Test: `tests/test_bash_gate_config_lock_418.py::test_worktree_kopie_frei_und_override_gibt_config_frei`
- **AC-8:** Given ein nicht zerlegbarer Befehl (offene Quote) oder ein nicht auflösbares `cd`-Ziel (`cd $X && sed -i s/a/b/ openspec.yaml`) / When das Gate läuft / Then stürzt es nicht ab, die Zielextraktion ist fail-open, und das Ergebnis entspricht dem heutigen Verhalten (kein neuer Block-Grund); die nicht abgedeckten Formen `ex -s cfg`, `patch cfg x.diff`, `git apply x.diff` bleiben Exit 0 (dokumentierte Known Limitation)
  - Test: `tests/test_bash_gate_config_lock_418.py::test_fail_open_und_dokumentierte_grenzen`
- **AC-9:** Given der bestehende Testbestand / When `tests/test_bash_gate_state_integrity_410.py` und das Regressionsnetz `tests/test_bash_gate*` laufen / Then bleiben sie grün (insbesondere `test_wirksame_config_schreiben_blockt`, `test_config_schutz_ohne_aktiven_workflow`, `test_override_gibt_config_frei_aber_nicht_state`, `test_worktree_kopie_lesen_und_app_config_bleiben_frei`)
  - Test: `tests/test_bash_gate_state_integrity_410.py`, `tests/test_bash_gate_ln_state_407.py`, `tests/test_bash_gate_false_positives.py`, `tests/test_bash_gate_erkennung_299.py`, `tests/test_bash_gate_erkennung_299_teil_b.py`, `tests/test_bash_gate_erkennung_299_teil_c.py`, `tests/test_bash_gate_freetext_fixes_64_75.py`, `tests/test_bash_gate_env_aliase_324.py` (unverändert, Lauf grün)

> Die Test-Zuordnung wird **bei der Spec-Erstellung** eingetragen, nicht nachträglich:
> Nach der Freigabe ist diese Datei eingefroren (#230) — jede Änderung verschiebt den
> PO-Briefing-Hash und blockt den Workflow-Abschluss. Stimmt der Testname später nicht
> mehr, gehört die Korrektur in die TDD-RED-Artefakte (`workflow.py add-artifact`),
> nicht in diese Datei.

## Test Plan

### Automated Tests (TDD RED)

- [ ] Test 1 (AC-1): GIVEN Wegwerf-Repo ohne Workflow mit `openspec.yaml` im Stamm, WHEN `git diff openspec.yaml > x.patch`, `grep a openspec.yaml > out.txt`, `cat openspec.yaml > copy`, `cp openspec.yaml backup.yaml`, `cp -t backup/ openspec.yaml` und `cat openspec.yaml | tee copy` als Subprozess durch das echte `core/hooks/bash_gate.py` laufen, THEN jeweils Exit 0 (RED: fünf der sechs enden heute mit Exit 2)
- [ ] Test 2 (AC-2): GIVEN dasselbe Repo, WHEN `sed --in-place`, `sed -ni`, `sed -i ''`, `perl -pi -e`, `perl -i.bak -pe` auf die Config laufen, THEN jeweils Exit 2 mit „override“ in der Meldung (RED: heute Exit 0)
- [ ] Test 3 (AC-3): GIVEN dasselbe Repo, WHEN `>|`, `&>`, `git checkout -- cfg`, `git restore cfg`, `ln -sf x cfg`, `install x cfg`, `dd of=cfg`, `yq -i` und `cp x -t DIR` (Ziel = Config) laufen, THEN jeweils Exit 2 (RED: heute Exit 0)
- [ ] Test 4 (AC-4, AC-5): GIVEN Repo mit Unterordner `docs/` und echter Worktree, WHEN `cd docs && sed -i … ../openspec.yaml`, `cd docs; echo x > ../openspec.yaml` und im Worktree `cd ../../.. && sed -i … openspec.yaml` laufen, THEN Exit 2; WHEN `cd docs && sed -i s/a/b/ openspec.yaml` läuft, THEN Exit 0 (RED: heute 0 bzw. 2, also genau umgekehrt)
- [ ] Test 5 (AC-6): GIVEN dasselbe Repo, WHEN die zehn Gegenprobe-Befehle laufen, THEN jeweils Exit 2 (muss vor und nach der Implementierung grün sein; schützt vor Verlust bestehender Treffer)
- [ ] Test 6 (AC-7): GIVEN echter Worktree plus Hauptordner mit Config, WHEN `sed -i` die Worktree-Kopie trifft, THEN Exit 0; GIVEN gültiger Override-Token, WHEN ein Schreibbefehl auf die wirksame Config läuft, THEN Exit 0
- [ ] Test 7 (AC-8): GIVEN dasselbe Repo, WHEN ein Befehl mit offener Quote, `cd $X && sed -i s/a/b/ openspec.yaml`, `ex -s cfg`, `patch cfg x.diff` und `git apply x.diff` laufen, THEN kein Absturz (Exit 0 bzw. 2 gemäß heutigem Verhalten, bei den dokumentierten Grenzen Exit 0)
- [ ] Test 8 (AC-9): GIVEN der bestehende Bestand, WHEN `pytest tests/test_bash_gate_state_integrity_410.py tests/test_bash_gate_ln_state_407.py tests/test_bash_gate_false_positives.py tests/test_bash_gate_erkennung_299.py tests/test_bash_gate_erkennung_299_teil_b.py tests/test_bash_gate_erkennung_299_teil_c.py tests/test_bash_gate_freetext_fixes_64_75.py tests/test_bash_gate_env_aliase_324.py` läuft, THEN grün; danach `tests/test_bash_gate*` und die Vollsuite

Aufbau: Subprozess-Tests gegen das echte Gate, Sandbox ohne Workflow, echter Worktree (`git worktree add`); die Sandbox-Helfer (`_worktree_sandbox` und Verwandte) werden aus `tests/test_bash_gate_state_integrity_410.py` importiert. Wenige parametrisierte Funktionen; Abweichungen werden gesammelt und am Ende gemeinsam gemeldet. Die RED-Läufe müssen vor der Implementierung an den Teil-A-, B- und C-Befehlen die Abweichung zeigen und werden als Artefakte registriert.

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Die Änderung präzisiert die Erkennung der Config-Sperre aus #410 innerhalb der bestehenden Entscheidung „Gate prüft Befehlstext vor dem Ausführen per Regeln, Ausweg ist der Override-Token“ (Struktur aus #299, #407, #410). Neu ist nur, dass statt „Indikator plus beliebigem Argument“ die tatsächlichen Schreibziele verglichen werden und die Basis über `cd` nachgeführt wird; kein neues Muster, keine neue Abhängigkeit, keine bestehende Entscheidung wird gekippt.

**Entscheidung: zielbasierte Textprüfung vor dem Ausführen.** Regelweg zuerst: Die Fehler A, B und C entstehen alle aus der Rate-Logik; eine deterministische Zielextraktion behebt sie, ohne Modell.

**Alternativen (bewertet, nicht gewählt):**

- **Prüfung an der Wirkung (PostToolUse, Hash oder mtime der Config):** präzise und unabhängig von der Schreibform, meldet aber erst **nach** dem Schreiben (Revert nötig), braucht einen neuen Hook samt State. Würde die #410-Entscheidung „präventiv blocken, Ausweg Override-Token“ kippen. Gehört thematisch zur Prüfung an der Quelle, #416.
- **Config per `chmod` schreibschützen:** formunabhängig, kippt aber die Entscheidung, dass Gates in Konsumentenprojekten keine Dateirechte verändern, und kollidiert mit legitimem Editieren durch den User.
- **Nur A und C jetzt, B als Folgeticket:** kleinerer Schnitt, aber B ist der eigentliche Sicherheitsgewinn und fällt in dieselbe Zielextraktion fast kostenlos mit an. Bleibt Rückfalloption, falls die LoC-Grenze gerissen würde; würde dann die Bündelungsregel „ein Ticket je gemeinsames Ziel“ (Folgearbeit bündeln) verletzen.
- **Alle Schreibformen lückenlos abdecken (`patch`, `ex`, `git apply`):** verworfen, weil sich Textprüfung grundsätzlich nicht lückenlos machen lässt (siehe Known Limitations der #410-Spec) und die Zusatzformen selten oder nicht versehentlich sind.

## Changelog

- 2026-10-10: Initial spec created (#418)
