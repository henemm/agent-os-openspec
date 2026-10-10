---
entity_id: fix-410-state-integrity-gaps
type: bugfix
created: 2026-10-09
updated: 2026-10-09
status: draft
workflow: fix-410-state-integrity-gaps
version: "1.0"
tags: [bash-gate, state-integrity, glob, config, override, cd-kontext]
test_targets: ["tests/test_bash_gate_state_integrity_410.py"]
---

# bash_gate: Restlücken in Prüfung 3b und Schutz der wirksamen Gate-Config — #410

## Approval

- [ ] Approved

## GitHub Issue

- **Issue:** #410 (inkl. Kommentar „Teil 4“). Die Prüfung an der Quelle (`st_nlink`/Symlink beim Lesen des Zustands, „Teil 3“) ist **nicht** Teil dieser Spec, sondern eigenes Ticket #416. Allgemeiner Bash-Schreibzugriff aufs Hauptrepo ist #417 und ebenfalls außerhalb.

## Purpose

Prüfung 3b in `core/hooks/bash_gate.py` schützt Workflow-State, Override-Token, Settings und Hook-Dateien vor Schreibzugriffen per Bash, hat aber nach #407 noch Lücken, die sich **versehentlich** auslösen lassen: ein Glob ohne `.json` (`cp .claude/workflows/fix* docs/x/`), Ordner-Token mit `/.`, `/..` oder `//` (`rsync -a docs/w/ .claude/workflows/.`, `ln -s .claude//workflows d`) und Ordner-Verweise nach `cd .claude` (`cd .claude && ln -s workflows ../w`). Zusätzlich ist die **wirksame** Gate-Konfiguration (die Datei, aus der alle Kill-Switches gelesen werden) per Bash frei beschreibbar: Eine Worktree-Sitzung kann mit `sed -i … <Hauptordner>/config.yaml` jeden Schalter umlegen, ohne dass ein Wächter anschlägt (am echten Gate belegt, alle drei Wächter Exit 0). Die Spec schließt beides mit Regeln, ohne Modell, ohne neuen Subprozess, ohne neue Abhängigkeit.

## Source

- **File:** `core/hooks/bash_gate.py` — `PROTECTED_FILE_PATTERNS` (~Z.56), `PROTECTED_DIR_TOKEN_PATTERNS` (~Z.69), `_writes_state_dir` (~Z.280), `_redirects_to_protected` (~Z.296), `_cd_into_claude` / `_cd_context_protected` (~Z.322-354), `_has_write_indicator` (~Z.443), `_matches_file_token` (~Z.456), Prüfung 3b im Hauptablauf (~Z.980-992), `_any_override_token` (~Z.882)
- **Analyse:** `docs/context/fix-410-state-integrity-gaps.md`, Abschnitte „Reproduktion“ und „Analysis“ (Entscheidungen Tech Lead, nach Daten)

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `core/hooks/bash_gate.py` | Modul | Kern-Gate Bash, Prüfung 3b; läuft bei jedem Bash-Aufruf in jedem Konsumentenprojekt |
| `core/hooks/hook_utils.py` (`find_project_root`, `_git_segments`, `_git_lex`, Freitext-Flags) | Modul | Projektwurzel (worktree-transparent), Zerlegung in Segmente/Token, Freitext-Ausnahme (#53/#64); unverändert |
| `core/hooks/config_loader.py` (`find_config_file`) | Modul | Öffentliche Funktion; liefert die tatsächlich geladene Config-Datei (`openspec.yaml`, `config.yaml`, `.openspec.yaml`, je im Root oder unter `.claude/`; Root-`config.yaml` ohne Plugin-Block gehört der App und wird übergangen, #372) |
| `core/hooks/override_token.py` (`has_valid_token`) | Modul | Ausweg für die Config-Sperre; `bash_gate` nutzt es bereits in `_any_override_token()` fürs Dependency-Gate |
| `shlex` (Standardbibliothek) | Modul | Token-Zerlegung für die `cd`-Kontext-Erkennung |
| `tests/test_bash_gate_ln_state_407.py` | Test | Vorlage: Subprozess gegen echtes Gate, Wegwerf-Repo, Workflow aktiv, beide Fehlerrichtungen |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| `core/hooks/bash_gate.py` | MODIFY | Teil 1: Glob im letzten Pfadteil in `PROTECTED_FILE_PATTERNS`; F001/F002: `PROTECTED_DIR_TOKEN_PATTERNS` toleriert `/+` und `/.`/`/..`-Suffixe; F003: neue Funktion `_dir_token_in_cd_context`; Teil 2: neue Funktion `_writes_effective_config` samt Block mit override-Ausweg |
| `tests/test_bash_gate_state_integrity_410.py` | CREATE | Subprozess-Tests gegen das echte Gate, beide Fehlerrichtungen je Teil |
| `CHANGELOG.md` | MODIFY | Eintrag unter `[Unreleased]`, **kein** Versions-Bump |

### Estimated Changes

- Files: 3 (Grenze 4-5 eingehalten)
- LoC: ca. +200/-5 (Gate ca. 55, Tests ca. 140, Changelog ca. 5). Das liegt innerhalb von ±250. Spec/Kontext/Briefing zählen im LoC-Gate zusätzlich (#294). Mit laufendem Workflow ab phase6 entfällt der Override für `core/hooks/` (#322).
- Alle neuen Funktionen bleiben unter 50 Zeilen.

## Implementation Details

**1. Teil 1, Glob.** Das erste Muster in `PROTECTED_FILE_PATTERNS` verlangt heute `…/workflows/<name>.json`. Der letzte Pfadteil darf künftig statt `[^\s]*\.json` auch ein Glob sein: `[^\s/]*[*?[][^\s]*`. Bewusst **nicht** das naive `[^\s]*`, weil das jedes Token unter `.claude/workflows/` träfe, auch Lesebefehle ohne Schreib-Indikator-Schutz in Randfällen. Wie bisher blockt 3b nur Pfad-Token **und** Schreib-/Verweis-Indikator im selben Segment; `ls .claude/workflows/fix*` hat keinen Indikator und bleibt frei.

**2. F001/F002, Ordner-Token.** `PROTECTED_DIR_TOKEN_PATTERNS` wird zu `\.claude(?:/+workflows)?(?:/+\.{1,2})*/*` vor dem bestehenden Lookahead. Damit gelten `.claude/workflows/.`, `.claude/workflows/..`, `.claude//workflows` und Kombinationen als Zustandsordner. `.claude/worktrees/…` und `.claude/hooks` als Ordner bleiben unerfasst (wie in #407).

**3. F003, Ordner-Verweis nach `cd`.** Neue Funktion `_dir_token_in_cd_context(segmente)`: Steht vor dem aktuellen Segment ein `cd`/`pushd` auf `.claude` oder `.claude/workflows` (gleiche Erkennung wie `_cd_into_claude`), zählt im Folgesegment ein nacktes `workflows`- oder `.`-Token zusammen mit `_has_write_indicator(seg, links=True)` als Treffer. `cd .claude/worktrees/x && cp a b` und `cd .claude && ls workflows` bleiben frei (kein Indikator bzw. anderer Ordner).

**4. Teil 2, wirksame Config (Variante B).** Neue Funktion `_writes_effective_config(segmente, cwd)`: Nur wenn ein Segment einen Schreib-Indikator hat (lazy, geringe Kosten pro Bash-Aufruf), wird `find_config_file(find_project_root())` aufgelöst. Zeigt ein Datei-Token des Segments, gegen das cwd aufgelöst (`Path.resolve()`), auf genau diese Datei, blockt das Gate mit Exit 2 und einer Meldung, die „override“ als Ausweg nennt. Gilt **unabhängig vom aktiven Workflow**, weil Kill-Switches auch ohne Workflow wirken. Lesen (`cat`, `grep`) bleibt frei. `_any_override_token()` hebt die Sperre nur für die Config, nicht für den Workflow-State. Die Worktree-Kopie (`config.yaml` im Worktree, nicht die aufgelöste Datei im Hauptordner) bleibt frei: `config_loader` liest absichtlich aus dem Hauptordner, eine Änderung wirkt erst nach Merge (Review + CI). Edit/Write auf die Config ist durch `worktree_write_guard` bzw. die Worktree-Pflicht abgedeckt, `edit_gate.py` bleibt unverändert.

**5. Unberührt:** `_redirects_to_protected`, Secrets-Pfade, Freitext-Flag-Ausnahme (Inhalte von `-m`/`--body` zählen nicht), alle `workflow.py`-Aufrufe.

## Expected Behavior

- **Input:** Ein Bash-Befehl durch `bash_gate.py`.
- **Output:** Die unten genannten Schreibweisen enden mit Exit 2 und der bestehenden 3b-Meldung „Direct state file manipulation“ (Config: eigene Meldung mit Hinweis auf „override“). Lesende und unbeteiligte Befehle laufen mit Exit 0.
- **Side effects:** Keine neuen Subprozesse, keine neuen Abhängigkeiten. State-Befehle ohne aktiven Workflow bleiben unverändert; nur die Config-Sperre gilt auch ohne Workflow.

| Befehl (aktiver Workflow) | Heute | Soll |
|---------------------------|-------|------|
| `cp\|ln\|mv .claude/workflows/fix* docs/x/` | 0 | 2 |
| `echo x > <wirksame config>`, `sed -i s/a/b/ <wirksame config>` | 0 | 2 (0 mit override) |
| `cp -r docs/w/. .claude/workflows/.`, `rsync -a docs/w/ .claude/workflows/.` | 0 | 2 |
| `cd .claude && ln -s workflows ../w`, `pushd .claude; ln -s workflows ../w` | 0 | 2 |
| `ln -s .claude//workflows d` | 0 | 2 |
| `cp docs/a.json .claude/workflows/b.json` (Sanity) | 2 | 2 |
| `ls .claude/workflows/fix*`, `cat .claude/workflows/x.json`, `cd .claude && ls workflows`, `cd .claude/worktrees/x && cp a b`, `ls .claude && rm docs/x`, `cat config.yaml`, `grep enabled <main>/config.yaml`, `sed -i s/a/b/ config.yaml` (Worktree-Kopie) | 0 | 0 |

## Known Limitations

- **F004, Ordner/Verweis in getrennten Segmenten sowie `xargs`/`find`/`tar`** (`ls .claude/workflows | xargs ln -s`) bleiben offen. Das ist die Kehrseite der Fehlalarm-Vermeidung: Pfad und Schreibbefehl liegen nicht im selben Segment, eine Verknüpfung per Text würde massenhaft harmlose Pipelines blocken. Gegenmaßnahme ist die Prüfung an der Quelle, Ticket #416 — mit #416 aufgelöst (Prüfung an der Quelle, docs/specs/fix-416-state-reader-source-check.md).
- **Hinnehmbarer Fehlalarm:** `cat .claude/workflows/fix* > docs/x` (Glob **und** Umleitung) blockt, obwohl nur gelesen wird. Ausweg: `workflow.py status`.
- **Textprüfung ist grundsätzlich umgehbar.** Sperrlisten auf Shell-Befehlstext gelten als nicht vollständig machbar: CVE-2024-6091 (AutoGPT, `/bin/./whoami` umgeht eine Sperrliste, exakt die Klasse von F001), CVE-2026-32973 (Glob-Normalisierung), Studien Juni 2026 (69-98 % realer Sperrlisten lückenhaft). Quellen: https://opencve.alliance.unm.edu/cve/CVE-2024-6091, https://db.gcve.eu/vuln/CVE-2026-32973, https://codex.danielvaughan.com/2026/07/26/guardfall-shellsieve-denylist-fragility-coding-agents-codex-cli-os-level-sandbox-defence/. Deshalb wird der Text nur für **versehentlich** auslösbare Schreibweisen gehärtet; vorsätzliche Umgehung (`python -c "os.link(…)"`, Variablen im Pfad, Wrapper-Skripte) löst nur #416.
- Die Worktree-Kopie der Config ist bewusst frei; wer sie ändert, ändert nichts Wirksames vor dem Merge.
- Allgemeiner Bash-Schreibzugriff aufs Hauptrepo (nicht nur Config) bleibt offen, siehe #417.
- Verteilung: wirkt in Konsumenten-Projekten erst nach dem Plugin-Update. Im Framework-Repo braucht die Pflege der Live-Config (Root-`config.yaml` im Hauptordner) künftig „override“.

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test am echten Gate-Subprozess belegt
- [ ] Alle Reproduktionsbefehle aus der Analyse enden mit Exit 2 (Glob, wirksame Config, `/.`, `/..`, `//`, `cd`-Kontext) und alle Fehlalarm-Gegenproben mit Exit 0
- [ ] Die wirksame Config ist ohne aktiven Workflow gesperrt und per „override“ freigebbar; die Worktree-Kopie bleibt frei
- [ ] Known Limitations (F004, Glob-plus-Umleitung, Textumgehung) sind in der Spec und im CHANGELOG-Eintrag benannt, Verweis auf #416/#417
- [ ] Keine bestehende Funktion ist kaputtgegangen (Regressionsnetz und Vollsuite grün)

## Acceptance Criteria

- **AC-1:** Given ein aktiver Workflow / When `cp .claude/workflows/fix* docs/x/`, `ln .claude/workflows/fix* docs/x/` oder `mv .claude/workflows/fix* docs/x/` läuft / Then blockt das Gate mit Exit 2
  - Test: `tests/test_bash_gate_state_integrity_410.py::test_glob_ohne_json_blockt`
- **AC-2:** Given ein aktiver Workflow / When `ls .claude/workflows/fix*` oder `cat .claude/workflows/x.json` läuft / Then bleibt Exit 0; zugleich blockt `cp docs/a.json .claude/workflows/b.json` weiter mit Exit 2 (Sanity)
  - Test: `tests/test_bash_gate_state_integrity_410.py::test_glob_lesen_bleibt_frei_und_sanity_blockt`
- **AC-3:** Given ein aktiver Workflow / When `cat .claude/workflows/fix* > docs/x` läuft / Then blockt das Gate mit Exit 2 (hinnehmbarer, dokumentierter Fehlalarm; Ausweg `workflow.py status`)
  - Test: `tests/test_bash_gate_state_integrity_410.py::test_glob_mit_umleitung_ist_dokumentierter_fehlalarm`
- **AC-4:** Given eine Projektwurzel mit wirksamer Config (aufgelöst über `find_config_file(find_project_root())`) / When `echo x > <wirksame config>`, `sed -i s/a/b/ <wirksame config>` (auch `openspec.yaml`, relativer Pfad `../../config.yaml`, absoluter Pfad) läuft / Then blockt das Gate mit Exit 2 und nennt „override“ in der Meldung
  - Test: `tests/test_bash_gate_state_integrity_410.py::test_wirksame_config_schreiben_blockt`
- **AC-5:** Given kein aktiver Workflow / When derselbe Schreibbefehl auf die wirksame Config läuft / Then blockt das Gate mit Exit 2 (Config-Schutz ist workflow-unabhängig)
  - Test: `tests/test_bash_gate_state_integrity_410.py::test_config_schutz_ohne_aktiven_workflow`
- **AC-6:** Given ein gültiger Override-Token / When ein Schreibbefehl auf die wirksame Config läuft / Then lässt das Gate ihn mit Exit 0 durch; ein Schreibbefehl auf Workflow-State bleibt trotz Token bei Exit 2
  - Test: `tests/test_bash_gate_state_integrity_410.py::test_override_gibt_config_frei_aber_nicht_state`
- **AC-7:** Given eine Worktree-Sitzung / When `sed -i s/a/b/ config.yaml` die Worktree-Kopie trifft (nicht die aufgelöste Datei im Hauptordner), oder `cat config.yaml` und `grep enabled <main>/config.yaml` lesen, oder eine App-`config.yaml` im Root ohne Plugin-Block geschrieben wird / Then bleibt Exit 0
  - Test: `tests/test_bash_gate_state_integrity_410.py::test_worktree_kopie_lesen_und_app_config_bleiben_frei`
- **AC-8:** Given ein aktiver Workflow / When `cp -r docs/w/. .claude/workflows/.`, `rsync -a docs/w/ .claude/workflows/.` oder ein Ordner-Token mit `/..` läuft / Then blockt das Gate mit Exit 2 (F001)
  - Test: `tests/test_bash_gate_state_integrity_410.py::test_ordner_token_mit_punkt_und_punktpunkt_blockt`
- **AC-9:** Given ein aktiver Workflow / When `ln -s .claude//workflows d` läuft / Then blockt das Gate mit Exit 2 (F002)
  - Test: `tests/test_bash_gate_state_integrity_410.py::test_doppelter_slash_im_ordner_token_blockt`
- **AC-10:** Given ein aktiver Workflow / When `cd .claude && ln -s workflows ../w` oder `pushd .claude; ln -s workflows ../w` läuft / Then blockt das Gate mit Exit 2 (F003)
  - Test: `tests/test_bash_gate_state_integrity_410.py::test_ordner_verweis_nach_cd_blockt`
- **AC-11:** Given ein aktiver Workflow / When `cd .claude && ls workflows`, `cd .claude/worktrees/x && cp a b`, `ls .claude && rm docs/x` oder ein `workflow.py`-Aufruf läuft / Then bleibt Exit 0
  - Test: `tests/test_bash_gate_state_integrity_410.py::test_cd_kontext_gegenproben_bleiben_frei`
- **AC-12:** Given ein aktiver Workflow / When Freitext in `-m`/`--body` die Zeichenfolge „cp .claude/workflows/fix*“ enthält / Then bleibt Exit 0 (Freitext-Ausnahme)
  - Test: `tests/test_bash_gate_state_integrity_410.py::test_freitext_mit_glob_bleibt_frei`
- **AC-13:** Given kein aktiver Workflow / When die State-Befehle aus AC-1, AC-8, AC-9 und AC-10 laufen / Then bleibt Exit 0 (State-Schutz weiter nur im Workflow, #407 AC-9)
  - Test: `tests/test_bash_gate_state_integrity_410.py::test_state_befehle_ohne_workflow_unveraendert`
- **AC-14:** Given der bestehende Testbestand / When die Regressionstests laufen / Then bleiben sie grün
  - Test: `tests/test_bash_gate_ln_state_407.py`, `tests/test_bash_gate_false_positives.py`, `tests/test_bash_gate_erkennung_299.py`, `tests/test_bash_gate_erkennung_299_teil_b.py`, `tests/test_bash_gate_erkennung_299_teil_c.py`, `tests/test_bash_gate_freetext_fixes_64_75.py`, `tests/test_gate_fixes_26_38_34.py`, `tests/test_bash_gate_env_aliase_324.py` (unverändert, Lauf grün)

> Die Test-Zuordnung wird **bei der Spec-Erstellung** eingetragen, nicht nachträglich:
> Nach der Freigabe ist diese Datei eingefroren (#230) — jede Änderung verschiebt den
> PO-Briefing-Hash und blockt den Workflow-Abschluss. Stimmt der Testname später nicht
> mehr, gehört die Korrektur in die TDD-RED-Artefakte (`workflow.py add-artifact`),
> nicht in diese Datei.

## Test Plan

### Automated Tests (TDD RED)

- [ ] Test 1 (AC-1, AC-2, AC-3): GIVEN Wegwerf-Repo mit aktivem Workflow in phase6, WHEN `cp|ln|mv .claude/workflows/fix* docs/x/` als Subprozess durch das echte `core/hooks/bash_gate.py` läuft, THEN Exit 2; WHEN `ls`/`cat` auf `.claude/workflows/*` läuft, THEN Exit 0; WHEN `cat … fix* > docs/x` läuft, THEN Exit 2 (dokumentierter Fehlalarm)
- [ ] Test 2 (AC-4, AC-5, AC-6): GIVEN Wegwerf-Repo mit Config (Root `openspec.yaml` bzw. Plugin-`config.yaml`), WHEN `echo x >`/`sed -i` auf die per `find_config_file` aufgelöste Datei läuft (relativ, absolut), THEN Exit 2 mit/ohne aktiven Workflow; WHEN ein gültiger Override-Token liegt, THEN Exit 0 für die Config, weiter Exit 2 für Workflow-State
- [ ] Test 3 (AC-7): GIVEN Hauptordner plus echter Worktree (`git worktree add`), WHEN `sed -i` die Worktree-Kopie trifft, THEN Exit 0; WHEN `cat`/`grep` die wirksame Datei im Hauptordner liest, THEN Exit 0; WHEN eine App-`config.yaml` ohne Plugin-Block im Root geschrieben wird, THEN Exit 0
- [ ] Test 4 (AC-8, AC-9, AC-10): GIVEN aktiver Workflow, WHEN die Reproduktionsbefehle `cp -r docs/w/. .claude/workflows/.`, `rsync -a docs/w/ .claude/workflows/.`, `ln -s .claude//workflows d`, `cd .claude && ln -s workflows ../w`, `pushd .claude; ln -s workflows ../w` laufen, THEN Exit 2
- [ ] Test 5 (AC-11, AC-12, AC-13): GIVEN aktiver Workflow, WHEN `cd .claude && ls workflows`, `cd .claude/worktrees/x && cp a b`, `ls .claude && rm docs/x`, `workflow.py status` und Freitext in `git commit -m "cp .claude/workflows/fix*"` laufen, THEN Exit 0; GIVEN kein Workflow, WHEN die State-Befehle laufen, THEN Exit 0
- [ ] Test 6 (AC-14): GIVEN der bestehende Bestand, WHEN `pytest tests/test_bash_gate_ln_state_407.py tests/test_bash_gate_false_positives.py tests/test_bash_gate_erkennung_299.py tests/test_bash_gate_erkennung_299_teil_b.py tests/test_bash_gate_erkennung_299_teil_c.py tests/test_bash_gate_freetext_fixes_64_75.py tests/test_gate_fixes_26_38_34.py tests/test_bash_gate_env_aliase_324.py` läuft, THEN grün; danach die Vollsuite

Aufbau: Subprozess-Muster aus `tests/test_bash_gate_ln_state_407.py` (`_sandbox`/`_expect`, Abweichungen gesammelt gemeldet). Die RED-Läufe müssen vor der Implementierung an den Reproduktionsbefehlen Exit 0 statt 2 zeigen und werden als Artefakte registriert.

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Die Änderung erweitert die Erkennung von Prüfung 3b innerhalb der bestehenden Entscheidung „Gate prüft Befehlstext per Regeln“ (Struktur aus #299, fortgeführt in #407); kein neues Muster, keine neue Abhängigkeit. Neu ist nur, dass ein Pfad (die wirksame Config) workflow-unabhängig und mit `override` als Ausweg geschützt wird; das folgt dem Prinzip „Ein Prüfer, den der Geprüfte selbst abschalten kann, ist keiner“. Die Prüfung an der Quelle (#416) und der allgemeine Hauptrepo-Schutz (#417) bleiben bewusst getrennte Tickets; keine bestehende ADR wird gekippt.

**Alternativen für Teil 2 (Regelweg vorn, belegt am echten Gate):**

- **Gewählt, Variante B:** nur die wirksame Config (`find_config_file(find_project_root())`) schützen, Ausweg `override`, unabhängig vom Workflow, Worktree-Kopie frei, `edit_gate` unverändert. Trifft genau die Datei, die wirkt; minimale Reibung.
- **A (Config-Name pauschal sperren + override):** verworfen. Erzeugt Reibung bei legitimer Template-Pflege im Framework-Repo und schützt die Worktree-Kopie, die vor dem Merge gar nicht wirkt. Ein Namensmuster `config.yaml` träfe außerdem App-Configs (#372).
- **C (Config offen lassen):** verworfen. Durch Versuch widerlegt: Die wirksame Datei im Hauptordner ist aus einer Worktree-Sitzung per Bash beschreibbar (`singleton`, `egress`, `bash_gate` alle Exit 0).
- **D (Kill-Switch-Nutzung nur protokollieren, `gate-events.jsonl`):** verworfen als Ersatz, weil es erkennt, aber nicht verhindert. Kann später als Ergänzung kommen.
- **Für Teil 1/F001-F003:** Alternative „Textprüfung weiter ausbauen bis lückenlos“ wurde verworfen (siehe Recherche in Known Limitations); stattdessen Prüfung an der Quelle in #416.

## Changelog

- 2026-10-09: Initial spec created (#410)
