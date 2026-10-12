---
entity_id: fix-417-bash-main-write
type: bugfix
created: 2026-10-12
updated: 2026-10-12
status: draft
workflow: fix-417-bash-main-write
version: "1.0"
tags: [bash-gate, worktree, schreibschutz, hauptordner, split-brain]
test_targets: ["tests/test_bash_gate_main_write_417.py"]
---

# bash_gate: Worktree-Sitzung darf per Bash nicht in den Haupt-Ordner schreiben — #417

## Approval

- [ ] Approved

## GitHub Issue

- **Issue:** #417 (Epic #429, Meilenstein 3.41). Folge zu #410 und #418 (Config-Sperre als Spezialfall). Die Prüfung an der Quelle gegen vorsätzliche Umgehung (`python -c`, `sh -c` mit Variablen) ist Ticket #416 und **nicht** Teil dieser Spec.

## Purpose

Eine Sitzung, die in einem Worktree (Haupt-Ordner plus `.claude/worktrees/<name>`) arbeitet, darf per Edit/Write nicht ins Hauptrepo schreiben; das stellt `worktree_write_guard.py` sicher. Per Bash gibt es diesen Wächter nicht: Umleitungen, `cp`, `mv`, `sed -i` oder `tee` treffen den Haupt-Ordner ungehindert und erzeugen genau den Split-Brain-Zustand, den die Worktree-Pflicht verhindern soll. Die Spec ergänzt im Kern-Gate `bash_gate.py` eine Prüfung auf echte Schreibziele, die unter dem Haupt-Ordner, aber nicht im eigenen Worktree liegen. Schutz vor Versehen, kein Sandbox-Ersatz. Rein regelbasiert, ohne Modell, ohne neuen Subprozess, ohne neuen Hook.

## Source

- **File:** `core/hooks/bash_gate.py` — vorhandene Schreibziel-Erkennung `_split_redirects` (~Z.365), `_command_args` (~Z.390), `_CONFIG_WRITERS` (~Z.500), `_config_write_targets` (~Z.512), `_cd_bases` (~Z.526), `_writes_effective_config` (~Z.539); Andockpunkt Prüfung 1b im Hauptablauf (~Z.1140)
- **Identifier:** `_writes_main_repo` (neu), Hauptablauf-Prüfung 1c
- **Referenzverhalten:** `core/hooks/worktree_write_guard.py` (Regex `^(?P<main>.*)/\.claude/worktrees/(?P<name>[^/]+)`, Haupt-Ordner gesperrt, eigener Worktree frei, fail-open)
- **Analyse:** `docs/context/fix-417-bash-main-write.md`
- **Ursprungsanfrage:** GitHub-Issue #417

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `core/hooks/bash_gate.py` | Modul | Kern-Gate Bash; Ort der Änderung; läuft bei jedem Bash-Aufruf in jedem Konsumentenprojekt |
| `core/hooks/hook_utils.py` (`_git_segments`, `find_worktree_root`, `find_main_repo_from_worktree`) | Modul | Zerlegung in Segmente; Erkennung von Worktree und Haupt-Ordner; unverändert |
| `core/hooks/override_token.py` (über `_any_override_token`) | Modul | Ausweg des Schutzes; unverändert |
| `core/hooks/worktree_write_guard.py` | Modul | Referenzverhalten für Edit/Write; unverändert, keine geteilte Importkette (bewusste Parallelkopie des Regex) |
| `tests/test_bash_gate_config_lock_418.py` | Test | Vorlage für `_worktree_sandbox` und `_expect` (echtes Gate als Subprozess, echter Worktree); wird als Muster genutzt, nicht verändert |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| `core/hooks/bash_gate.py` | MODIFY | Die Zielerkennung aus `_config_write_targets` wird als Hilfsfunktion „Schreibziele je Segment mit cd-Basis“ herausgezogen und von 1b und der neuen Funktion `_writes_main_repo(segments, cwd)` gemeinsam genutzt; neuer Block 1c neben 1b |
| `tests/test_bash_gate_main_write_417.py` | CREATE | Subprozess-Tests gegen das echte Gate, je Schreibweise und je Ausnahme ein Fall |
| `CHANGELOG.md` | MODIFY | Eintrag unter `[Unreleased]`, kein Versions-Bump |

**Nicht ändern:** `worktree_write_guard.py`, `secret_egress_guard.py` (eigene Umleitungs-Erkennung mit Sicherheitszone inklusive Haupt-Ordner, bleibt), `hook_utils.py`, `hooks/hooks.json`. Kein neuer Hook, keine neue Datei im Hook-Verzeichnis.

### Estimated Changes

- Files: 3
- LoC: ca. +60/-15 im Gate, ca. +150 in den Tests, Changelog ca. +5
- Alle Funktionen bleiben unter 50 Zeilen.

## Implementation Details

**1. Aktivierung nur in Worktrees.** `_writes_main_repo` ermittelt aus `cwd` per Regex `^(?P<main>.*)/\.claude/worktrees/(?P<name>[^/]+)` den Haupt-Ordner und den eigenen Worktree. Passt der Regex nicht (normaler Haupt-Ordner-Betrieb, anderes Projekt), liefert die Funktion `False`; für diese Sitzungen ändert sich nichts. `[^/]+` erlaubt Leerzeichen im Namen.

**2. Schreibziele wiederverwenden.** Die Zielerkennung aus #418 (Umleitung `>`, `>>`, `>|`, `&>`; `cp`/`mv`/`install`/`ln`; `tee`; `sed -i`; `perl -i`; `dd of=`; `touch`; `truncate`; `rm`/`unlink`; `yq -i`; `git checkout|restore|rm|mv`) wird als Hilfsfunktion je Segment herausgezogen, die Zielliste je Segment und `cd`-Basis liefert. 1b und 1c nutzen dieselbe Funktion; 1b behält sein Verhalten.

**3. Basis nachführen und auflösen.** Die Basis startet bei `cwd` und wird über `_cd_bases` (`cd`, `pushd`, `popd`) nachgeführt. Jedes Ziel wird mit `(basis / expanduser(ziel)).resolve()` aufgelöst, damit `~`, `..` und Symlinks erfasst sind.

**4. Blockbedingung.** Ein aufgelöstes Ziel blockt, wenn es unter dem Haupt-Ordner liegt **und nicht** unter dem eigenen Worktree. Der eigene Worktree liegt physisch im Haupt-Ordner und muss ausgenommen sein; fremde Worktrees (unter `.claude/worktrees/` mit anderem Namen) bleiben gesperrt, wie beim Write-Wächter.

**5. Neuer Block 1c.** Direkt nach 1b: Trifft `_writes_main_repo(_git_segments(scan_cmd) or [], Path.cwd())` und gibt es keinen Override-Token (`_any_override_token()`), endet das Gate mit Exit 2 und einer Meldung, die Worktree-Pflicht, Ziel und den Ausweg „override“ nennt. 1b läuft vor 1c: Schreibzugriffe auf die wirksame Config behalten ihre gezieltere Meldung aus #410.

**6. Unabhängig vom Projekt-Schalter.** Block 1c gilt wie 1b auch ohne aktiven Workflow und auch bei `framework_disabled()`. Begründung: Es ist Schutz vor Split-Brain, kein Workflow-Zwang (das Gate trennt Workflow-Zwang und Schutz seit #132). Das beantwortet die offene Frage aus der Analyse.

**7. Fail-open.** Lässt sich der Befehl nicht zerlegen (`_git_segments` liefert `None`), ist ein Ziel nicht auflösbar (`$VAR`, Glob, Backtick, `cd $X`) oder wirft die Auflösung eine Exception, ist das Ergebnis „kein Treffer“.

**8. Unberührt.** Lesen (die Quelle zählt nie), `workflow.py`-Aufrufe (schreiben aus Python heraus, kein Umleitungsziel), `git commit`, `git add`, `gh` (keine Pfadziele), Prüfungen 3a/3b, Secrets-Pfade.

## Expected Behavior

- **Input:** Ein Bash-Befehl durch `bash_gate.py`, Arbeitsverzeichnis im Worktree.
- **Output:** Schreibt der Befehl (Umleitung, Kopier-, Verschiebe-, In-Place-Form, `tee`, `touch`, `rm`, `git checkout|restore|rm|mv` und weitere) in den Haupt-Ordner außerhalb des eigenen Worktrees, endet er mit Exit 2 und einer Meldung mit Hinweis auf „override“. Alles andere endet wie bisher.
- **Side effects:** Keine neuen Subprozesse, keine neuen Abhängigkeiten, keine neuen Config-Keys.

`H` steht für den Haupt-Ordner, `W` für den eigenen Worktree, cwd ist `W`.

| Befehl | Heute | Soll |
|--------|-------|------|
| Umleitung `>` oder `>>` auf eine Datei in `H` | 0 | 2 |
| `cp f H/a.txt`, `mv f H/a.txt`, `cat f \| tee H/a.txt` | 0 | 2 |
| `sed -i s/a/b/ ../../../a.txt` (löst auf `H/a.txt`) | 0 | 2 |
| `cd ../../.. && echo x > a.txt` (Ziel über cd-Basis) | 0 | 2 |
| Tilde-Pfad, der auf `H` auflöst | 0 | 2 |
| Pfad mit Leerzeichen in `H` | 0 | 2 |
| Ziel in einem fremden Worktree unter `H` | 0 | 2 |
| Schreiben nach `W` (relativ oder absolut) | 0 | 0 |
| `cat H/a.txt`, `cp H/a.txt ./` (nur Lesen) | 0 | 0 |
| `workflow.py`-Aufruf, `git commit -m x`, `gh pr view` | 0 | 0 |
| Ziel mit `$VAR`, nicht zerlegbarer Befehl (offene Quote) | 0 | 0 (fail-open) |
| Schreibbefehl nach `H` mit gültigem Override-Token | 0 | 0 |
| Schreibbefehl nach `H` ohne Workflow bzw. bei `framework_disabled()` | 0 | 2 |
| `sed -i` auf die wirksame Config in `H` | 2 | 2 (Meldung aus 1b) |
| Befehle mit cwd im Haupt-Ordner selbst | unverändert | unverändert |

## Known Limitations

- **Kein Sandbox-Ersatz:** `python -c`, `sh -c`/`bash -c` mit Variablen, `eval`, Backticks und Skripte, die selbst schreiben, bleiben unerkannt. Vorsätzliche Umgehung gehört zu #416. Diese Spec schützt nur vor versehentlichen und gedankenlosen Schreibzugriffen.
- Nicht abgedeckt wie in #418: `patch`, `ex -s`/`vim -c`, `git apply` (Ziel steht nur im Diff).
- `cd` in Subshells und `||`-Zweigen wird linear nachgeführt, nicht zweiggenau; bei nicht auflösbarem `cd` bleibt zusätzlich `cwd` als Basis im Spiel.
- Fehlalarm-Richtung: Wer legitim in den Haupt-Ordner schreiben will (z. B. Sync nach dem Merge), tippt „override“ oder arbeitet in einer Haupt-Ordner-Sitzung.
- Verteilung: wirkt in Konsumentenprojekten erst nach dem Plugin-Update.

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test am echten Gate-Subprozess belegt
- [ ] In einer Worktree-Sitzung endet ein Befehl, der in den Haupt-Ordner schreibt (Umleitung, `cp`, `mv`, `sed -i`, `tee`, auch über `cd`, Tilde-Pfad oder Pfade mit Leerzeichen), mit Exit 2 und einer Meldung mit Hinweis auf „override“
- [ ] Im eigenen Worktree schreiben, Dateien des Haupt-Ordners lesen, `workflow.py`, `git commit` und `gh` laufen weiterhin ohne Blockade
- [ ] Der Haupt-Ordner-Betrieb ist unverändert, ein nicht auflösbares Ziel führt nicht zu einem Block, und „override“ gibt den Schreibzugriff frei
- [ ] Known Limitations (kein Sandbox-Ersatz, #416) stehen in Spec und CHANGELOG-Eintrag
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (`tests/test_bash_gate*` und Vollsuite grün)

## Acceptance Criteria

- **AC-1:** Given eine Worktree-Sitzung / When ein Befehl per Umleitung (`>`, `>>`) in eine Datei im Haupt-Ordner schreibt / Then endet das Gate mit Exit 2 und nennt „override“ in der Meldung
  - Test: `tests/test_bash_gate_main_write_417.py::test_umleitung_in_hauptordner_blockt`
- **AC-2:** Given eine Worktree-Sitzung / When `cp f` oder `mv f` mit Ziel im Haupt-Ordner läuft / Then endet das Gate mit Exit 2
  - Test: `tests/test_bash_gate_main_write_417.py::test_cp_und_mv_in_hauptordner_blocken`
- **AC-3:** Given eine Worktree-Sitzung / When `sed -i` mit relativem Pfad `../../../a.txt` (löst auf den Haupt-Ordner) läuft / Then endet das Gate mit Exit 2
  - Test: `tests/test_bash_gate_main_write_417.py::test_sed_inplace_mit_relativem_pfad_blockt`
- **AC-4:** Given eine Worktree-Sitzung / When `cat f | tee` mit Ziel im Haupt-Ordner läuft / Then endet das Gate mit Exit 2
  - Test: `tests/test_bash_gate_main_write_417.py::test_tee_in_hauptordner_blockt`
- **AC-5:** Given eine Worktree-Sitzung / When `cd ../../.. && echo x > a.txt` läuft (das Ziel liegt über die cd-Basis im Haupt-Ordner) / Then endet das Gate mit Exit 2
  - Test: `tests/test_bash_gate_main_write_417.py::test_ziel_ueber_cd_basis_blockt`
- **AC-6:** Given eine Worktree-Sitzung / When das Ziel als Tilde-Pfad angegeben ist, der auf den Haupt-Ordner auflöst / Then endet das Gate mit Exit 2
  - Test: `tests/test_bash_gate_main_write_417.py::test_tilde_pfad_blockt`
- **AC-7:** Given ein Haupt-Ordner mit Leerzeichen im Pfad und eine Worktree-Sitzung darin / When ein Befehl in den Haupt-Ordner schreibt / Then endet das Gate mit Exit 2 (Regex `[^/]+` greift)
  - Test: `tests/test_bash_gate_main_write_417.py::test_pfad_mit_leerzeichen_blockt`
- **AC-8:** Given eine Worktree-Sitzung und ein fremder Worktree im selben Haupt-Ordner / When ein Befehl in den fremden Worktree schreibt / Then endet das Gate mit Exit 2
  - Test: `tests/test_bash_gate_main_write_417.py::test_fremder_worktree_blockt`
- **AC-9:** Given eine Worktree-Sitzung / When ein Befehl in den eigenen Worktree schreibt (relativer oder absoluter Pfad) / Then bleibt das Gate bei Exit 0
  - Test: `tests/test_bash_gate_main_write_417.py::test_eigener_worktree_bleibt_frei`
- **AC-10:** Given eine Worktree-Sitzung / When Haupt-Ordner-Dateien nur gelesen werden (`cat <haupt>/a.txt`, `cp <haupt>/a.txt ./`) / Then bleibt das Gate bei Exit 0
  - Test: `tests/test_bash_gate_main_write_417.py::test_lesen_aus_hauptordner_bleibt_frei`
- **AC-11:** Given eine Worktree-Sitzung / When ein `workflow.py`-Aufruf oder `git commit` läuft / Then bleibt das Gate bei Exit 0
  - Test: `tests/test_bash_gate_main_write_417.py::test_workflow_py_und_git_commit_bleiben_frei`
- **AC-12:** Given eine Sitzung im Haupt-Ordner selbst / When ein Befehl dort schreibt / Then verhält sich das Gate unverändert (Exit 0)
  - Test: `tests/test_bash_gate_main_write_417.py::test_hauptordner_sitzung_unveraendert`
- **AC-13:** Given eine Worktree-Sitzung / When das Ziel nicht auflösbar ist (Variable im Zielpfad) oder der Befehl nicht zerlegbar ist (offene Quote) / Then stürzt das Gate nicht ab und bleibt bei Exit 0 (fail-open)
  - Test: `tests/test_bash_gate_main_write_417.py::test_nicht_aufloesbares_ziel_ist_fail_open`
- **AC-14:** Given eine Worktree-Sitzung und ein gültiger Override-Token / When ein Befehl in den Haupt-Ordner schreibt / Then lässt das Gate ihn mit Exit 0 durch
  - Test: `tests/test_bash_gate_main_write_417.py::test_override_token_laesst_durch`
- **AC-15:** Given eine Worktree-Sitzung ohne aktiven Workflow bzw. mit `framework_disabled()` / When ein Befehl in den Haupt-Ordner schreibt / Then endet das Gate mit Exit 2 (Schutz, kein Workflow-Zwang)
  - Test: `tests/test_bash_gate_main_write_417.py::test_block_ohne_workflow_und_bei_framework_disabled`
- **AC-16:** Given eine Worktree-Sitzung / When `sed -i` die wirksame Gate-Config im Haupt-Ordner trifft / Then bleibt der Block aus #410 mit seiner gezielteren Config-Meldung bestehen
  - Test: `tests/test_bash_gate_main_write_417.py::test_config_sperre_410_bleibt_mit_eigener_meldung`
- **AC-17:** Given der bestehende Testbestand / When `tests/test_bash_gate_config_lock_418.py`, `tests/test_bash_gate_state_integrity_410.py` und das Regressionsnetz `tests/test_bash_gate*` laufen / Then bleiben sie grün
  - Test: `tests/test_bash_gate_config_lock_418.py`, `tests/test_bash_gate_state_integrity_410.py` (unverändert, Lauf grün)

> Die Test-Zuordnung wird **bei der Spec-Erstellung** eingetragen, nicht nachträglich:
> Nach der Freigabe ist diese Datei eingefroren (#230) — jede Änderung verschiebt den
> PO-Briefing-Hash und blockt den Workflow-Abschluss. Stimmt der Testname später nicht
> mehr, gehört die Korrektur in die TDD-RED-Artefakte (`workflow.py add-artifact`),
> nicht in diese Datei.

## Test Plan

Automatische Tests (jeweils an eine AC oben gebunden):

- `pytest tests/test_bash_gate_main_write_417.py` — Subprozess-Tests gegen das echte `core/hooks/bash_gate.py`; Sandbox mit Haupt-Ordner und echtem Worktree (`git worktree add`) nach dem Muster `_worktree_sandbox`/`_expect` aus `tests/test_bash_gate_config_lock_418.py`; zusätzlich ein zweiter Worktree (fremd), ein Haupt-Ordner mit Leerzeichen im Pfad und ein Override-Token. Die RED-Läufe zeigen vor der Implementierung Exit 0 statt Exit 2 und werden als Artefakte registriert.
- Regression: `pytest tests/test_bash_gate*` (insbesondere #410 und #418), danach die Vollsuite.

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Die Änderung folgt der bestehenden Entscheidung „Gate prüft den Befehlstext vor dem Ausführen per Regeln, Ausweg ist der Override-Token“ (#299, #407, #410, #418) und der Hook-Konvention, Schreibschutz-Checks in die Kern-Gates zu legen statt in neue Hooks. Sie nutzt vorhandene Zielerkennung weiter und führt kein neues Muster, keine neue Abhängigkeit und keinen neuen Hook ein; keine bestehende Entscheidung wird gekippt. Verworfen: Erkennung in `secret_egress_guard.py` (dessen Sicherheitszone schließt den Haupt-Ordner bewusst ein) und ein eigener Bash-Wächter neben `worktree_write_guard.py` (kein eigenes Event nötig).

## Changelog

- 2026-10-12: Initial spec created (#417)
