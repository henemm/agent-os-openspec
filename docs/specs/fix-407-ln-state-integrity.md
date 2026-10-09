---
entity_id: fix-407-ln-state-integrity
type: bugfix
created: 2026-10-09
updated: 2026-10-09
status: draft
version: "1.0"
tags: [bash-gate, state-integrity, ln, hardlink, symlink, ordner-operationen]
test_targets: ["tests/test_bash_gate_ln_state_407.py"]
---

# bash_gate: Verweise (ln/link) und Ordner-Operationen auf Zustandsdateien — #407

## Approval

- [ ] Approved

## GitHub Issue

- **Issue:** #407. Glob-Lücke, `config.yaml`-Schutz und die `st_nlink`-Prüfung an der Quelle sind **nicht** Teil dieser Spec, sondern gebündelt in #410.

## Purpose

`bash_gate.py` Prüfung 3b (State-Integrity) schützt Workflow-State, Override-Token, Settings und Hook-Dateien vor Schreibzugriffen per Bash, erkennt aber nur eine feste Liste von Schreibbefehlen. `ln`/`link` stehen nicht darauf: Ein Verweis auf eine geschützte Datei an einem unverdächtigen Pfad (`ln .claude/workflows/<wf>.json docs/x/notes.txt`, danach `echo '{…VERIFIED…}' > docs/x/notes.txt`) umgeht den Schutz vollständig. Außerdem verlangen die Schutzmuster einen Dateinamen, sodass Operationen auf den ganzen Ordner (`ln -s .claude/workflows docs/w`, `mv .claude/workflows docs/w`, `cp -r`, `rsync`) nie greifen. Die Spec schließt beides mit Regeln, ohne Modell, ohne neuen Subprozess, ohne Abhängigkeit.

## Source

- **File:** `core/hooks/bash_gate.py` — `PROTECTED_FILE_PATTERNS` (~Z.56), `WRITE_INDICATORS` (~Z.100), `_has_write_indicator`, `_protected_outside_whitelist` / `_references_protected` (~Z.243-345), Prüfung 3b im Hauptablauf (~Z.947)
- **Analyse:** `docs/context/fix-407-ln-state-integrity.md`, Abschnitt „Analysis“ (Reproduktion am echten Gate, Ursachen, Weg B, Alternativen)

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `core/hooks/bash_gate.py` | Modul | Kern-Gate Bash, Prüfung 3b; läuft bei jedem Bash-Aufruf in jedem Konsumentenprojekt |
| `core/hooks/hook_utils.py` (`_git_segments`, `_git_lex`, Freitext-Flags) | Modul | Zerlegung in Segmente/Token, Freitext-Ausnahme (#53/#64); unverändert |
| `_cd_into_claude` in `bash_gate.py` | Funktion | Vorbild: behandelt `.claude` und `.claude/workflows` bereits als Zustandsordner, `.claude/worktrees/…` und `.claude/hooks` bewusst nicht |
| `tests/test_bash_gate_erkennung_299.py`, `…_teil_b.py`, `…_teil_c.py` | Test | Sandbox-Muster (`_sandbox`/`_expect`: Subprozess gegen echtes Gate, Wegwerf-Repo, Workflow aktiv) |
| `tests/test_bash_gate_false_positives.py`, `tests/test_bash_gate_freetext_fixes_64_75.py`, `tests/test_bash_gate_env_aliase_324.py` | Test | Regressionsschutz gegen Über-Blockierung und Freitext |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| `core/hooks/bash_gate.py` | MODIFY | `ln`, `link`, `install`, `rsync` als Kommandowort erkannt; neue Liste `PROTECTED_DIR_TOKEN_PATTERNS` (Ordner `.claude`, `.claude/workflows`), wirksam in 3b im Token-Pfad und im Roh-Scan-Fallback |
| `tests/test_bash_gate_ln_state_407.py` | CREATE | Subprozess-Tests gegen das echte Gate, beide Fehlerrichtungen |
| `CHANGELOG.md` | MODIFY | Eintrag unter `[Unreleased]` |

### Estimated Changes

- Files: 3
- LoC: ca. +190/-2 (Gate ca. 30, Tests ca. 150, Changelog ca. 5). Spec/Kontext/Briefing zählen im LoC-Gate zusätzlich (#294). Mit laufendem Workflow ab phase6 entfällt der Override für `core/hooks/` (#322).

## Implementation Details

**1. Kommandowort statt `\bln\b`.** Belegt (2026-10-09): `re.search(r'\bln\b', 'ls -ln docs/x.txt')` liefert `True`, weil `-` ein Nicht-Wortzeichen ist. Ein Wortgrenzen-Regex würde `ls -ln <state>` fälschlich blocken. Deshalb werden `ln`, `link`, `install` und `rsync` als **Kommandowort** erkannt: am Segmentanfang oder nach `;`, `&&`, `||`, `|`, `(` sowie nach Präfixen wie `sudo`/`env`, niemals mit führendem `-`. So trifft `install` auch nicht `pip install x` oder `npm install`. Die vier Wörter gelten wie die übrigen Indikatoren nur zusammen mit einem geschützten Pfad im selben Befehl.

**2. Ordner-Muster.** Die Datei-Muster in `PROTECTED_FILE_PATTERNS` verlangen `…/<name>.json`; ein Ordner-Token passt nie. Neue Liste `PROTECTED_DIR_TOKEN_PATTERNS` für die Token `.claude` und `.claude/workflows` (optional `./`, beliebiger Präfixpfad, optionaler abschließender Slash). Muster mit Lookahead statt `$`, etwa `(?<![\w.-])(?:\./)?(?:[^\s'"]*/)?\.claude(?:/workflows)?/*(?=[\s"';&|)]|$)`, damit es pro Token (`re.search`, `_matches_file_token`) und im Roh-Scan-Fallback (`sh -c`, `eval`, shlex-Fehler: ganzer String) gleich wirkt. Es wird nur in 3b über `_protected_outside_whitelist` / `_references_protected` herangezogen. **Nicht erfasst** bleiben `.claude/worktrees/…` (sonst blockt jede Worktree-Arbeit, z. B. `node_modules`-Verweise) und `.claude/hooks` als Ordner (konsistent mit `_cd_into_claude`); einzelne `.py` unter `.claude/hooks` sind weiter über `PROTECTED_FILE_PATTERNS` geschützt.

**3. Unberührt:** `_redirects_to_protected` (eigene Liste), Secrets-Pfade, `_cd_context_protected`, Freitext-Flag-Ausnahme (Inhalte von `-m`/`--body` zählen nicht).

**Abweichung vom Issue-Wortlaut (offen benannt):** Das Issue verlangt „`ln` mit geschütztem Pfad als Schreibzugriff werten“. Diese Spec geht darüber hinaus (Ordner-Muster, `mv`/`cp -r`/`rsync`/`install` auf Zustandsordner). Begründung: Ziel des Issues ist, dass sich keine geschützte Datei über einen zweiten Namen beschreiben lässt. Der Wortlaut allein (Alternative A) lässt den Ordner-Verweis `ln -s .claude/workflows docs/w` mit anschließendem `echo x > docs/w/<wf>.json` offen (reproduziert, beide Exit 0) und damit dasselbe Loch in anderer Form. Es zählt das Ziel, nicht der Wortlaut.

**Alternativen (Regelweg vorn; Details in der Analyse):**

- **Gewählt, Weg B:** Kommandowort-Erkennung plus Ordner-Muster im bestehenden Gate. Kein Modell nötig: Token- und Regelprüfung ist deterministisch, die Nulllinie ist die Regel.
- **A (nur `ln`/`link`, Issue-Wortlaut):** 2 Zeilen, erfüllt die DoD des Issues wörtlich, lässt aber Ordner-Verweise sowie `mv`/`cp -r`/`rsync` auf den ganzen Ordner offen. Verworfen, weil es das Ziel verfehlt.
- **C (`st_nlink`-/Symlink-Prüfung beim Lesen des Zustands):** wirkt unabhängig von der Befehlsform (auch `python -c "os.link(…)"`), braucht aber Änderungen in mindestens 8 Leser-Dateien (sprengt die Scoping-Limits), schützt nur Workflow-JSON (nicht `settings.json`/Token/Hooks), und Ordner-Symlinks erzeugen kein `st_nlink > 1`. Verworfen als Ersatz; als Ergänzung in #410 geführt.

## Expected Behavior

- **Input:** Ein Bash-Befehl durch `bash_gate.py`, Projekt mit aktivem Workflow.
- **Output:** Verweise und Ordner-Operationen mit einem Zustandspfad enden mit Exit 2 und der bestehenden 3b-Meldung „Direct state file manipulation“. Lesende und unbeteiligte Befehle laufen mit Exit 0.
- **Side effects:** Keine neuen Subprozesse, keine neuen Abhängigkeiten. Ohne aktiven Workflow bleibt das Verhalten unverändert.

| Befehl | Heute | Soll |
|--------|-------|------|
| `ln`, `ln -f`, `ln -s`, `link` mit `.claude/workflows/<wf>.json` als Quelle | 0 | 2 |
| `ln docs/x/notes.txt .claude/workflows/<wf>.json` (State als Ziel) | 0 | 2 |
| `ln .claude/user_override_token.json …`, `ln .claude/settings.json …` | 0 | 2 |
| `ln -s ../core/hooks/x.py .claude/hooks/x.py` | 0 | 2 |
| `ln -s .claude/workflows docs/w`, `ln -s .claude docs/c` | 0 | 2 |
| `mv .claude/workflows docs/w`, `cp -r` in beide Richtungen, `rsync -a docs/w/ .claude/workflows/`, `install docs/x .claude/workflows/<wf>.json` | 0 | 2 |
| `ls -ln <state>`, `cat <state>`, `ln -s docs/a docs/b`, `ln -s … .claude/worktrees/x/node_modules`, `pip install x`, `npm install` | 0 | 0 |
| `git commit -m "… ln .claude/workflows …"` (Freitext) | 0 | 0 |

## Known Limitations

- **Restrisiko (bewusst akzeptiert):** `cp -r ~/.claude backup` oder `rsync ~/.claude/ x` blockt bei aktivem Workflow, weil das Home-Verzeichnis `~/.claude` textlich nicht vom Projekt-`.claude` unterscheidbar ist. Selten, nur im Workflow, mit klarer Meldung.
- `.claude/hooks` als Ordner bleibt offen (konsistent mit `_cd_into_claude`); einzelne `.py`-Dateien sind geschützt.
- Bedrohungsmodell unverändert: verhindert wird das versehentliche Umgehen. Vorsätzliche Verschleierung (`python -c "os.link(…)"`, Variablen im Pfad, Wrapper-Skripte) bleibt Known Limitation; Gegenmaßnahme dafür ist die `st_nlink`-Prüfung an der Quelle in #410.
- Glob-Argumente (`ln .claude/workflows/fix* docs/x/`) und das ungeschützte `.claude/config.yaml` bleiben offen — Out of Scope, siehe #410.
- Verteilung: wirkt in Konsumenten-Projekten erst nach dem Plugin-Update.

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] `ln .claude/workflows/<wf>.json <beliebig>` (und die Varianten `-f`, `-s`, `link`, Ziel-Richtung, Ordner-Verweis) wird am echten Gate mit Exit 2 abgewiesen, die Kontrollfälle laufen weiter mit Exit 0
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf grün, insbesondere False-Positive-, Freitext- und #299-Tests)

## Acceptance Criteria

- **AC-1:** Given ein aktiver Workflow / When `ln`, `ln -f`, `ln -s` oder `link` eine State-Datei `.claude/workflows/<wf>.json` als Quelle erhält / Then blockt das Gate mit Exit 2
  - Test: `tests/test_bash_gate_ln_state_407.py::test_ln_mit_state_datei_als_quelle_blockt`
- **AC-2:** Given ein aktiver Workflow / When `ln` eine State-Datei als Ziel erhält (`ln docs/x/notes.txt .claude/workflows/<wf>.json`) / Then blockt das Gate mit Exit 2
  - Test: `tests/test_bash_gate_ln_state_407.py::test_ln_mit_state_datei_als_ziel_blockt`
- **AC-3:** Given ein aktiver Workflow / When `ln` `.claude/user_override_token.json`, `.claude/settings.json` oder `ln -s ../core/hooks/x.py .claude/hooks/x.py` verwendet / Then blockt das Gate mit Exit 2
  - Test: `tests/test_bash_gate_ln_state_407.py::test_ln_mit_token_settings_und_hook_datei_blockt`
- **AC-4:** Given ein aktiver Workflow / When ein Ordner-Verweis auf den Zustandsordner angelegt wird (`ln -s .claude/workflows docs/w`, `ln -s .claude docs/c`, auch mit `./`, absolutem Pfad und abschließendem Slash) / Then blockt das Gate mit Exit 2
  - Test: `tests/test_bash_gate_ln_state_407.py::test_ordner_verweis_auf_zustandsordner_blockt`
- **AC-5:** Given ein aktiver Workflow / When `mv .claude/workflows docs/w`, `cp -r .claude/workflows docs/w`, `cp -r docs/w .claude/workflows`, `rsync -a docs/w/ .claude/workflows/` oder `install docs/x .claude/workflows/<wf>.json` läuft / Then blockt das Gate mit Exit 2
  - Test: `tests/test_bash_gate_ln_state_407.py::test_ordner_operationen_mv_cp_rsync_install_blocken`
- **AC-6:** Given ein aktiver Workflow / When der Befehl nur über `sh -c`/`eval` oder bei nicht zerlegbarem Text (Roh-Scan-Fallback) ein Ordner- oder State-Muster samt `ln` enthält / Then blockt das Gate ebenfalls mit Exit 2
  - Test: `tests/test_bash_gate_ln_state_407.py::test_roh_scan_fallback_erkennt_ordner_muster`
- **AC-7:** Given ein aktiver Workflow / When `ls -ln <state>`, `cat <state>`, `ln -s docs/a docs/b`, `ln -s … .claude/worktrees/x/node_modules`, `pip install x` oder `npm install` läuft / Then lässt das Gate sie mit Exit 0 durch
  - Test: `tests/test_bash_gate_ln_state_407.py::test_harmlose_kontrollfaelle_bleiben_frei`
- **AC-8:** Given ein aktiver Workflow / When Freitext in `-m`/`--body` die Zeichenfolge „ln .claude/workflows“ enthält / Then lässt das Gate den Befehl mit Exit 0 durch (Freitext-Ausnahme)
  - Test: `tests/test_bash_gate_ln_state_407.py::test_freitext_mit_ln_und_zustandspfad_bleibt_frei`
- **AC-9:** Given kein aktiver Workflow / When dieselben Verweis- und Ordner-Befehle laufen / Then bleibt das Verhalten unverändert (Exit 0)
  - Test: `tests/test_bash_gate_ln_state_407.py::test_ohne_aktiven_workflow_unveraendert`
- **AC-10:** Given der bestehende Testbestand / When die Regressionstests laufen / Then bleiben sie grün
  - Test: `tests/test_bash_gate_false_positives.py`, `tests/test_bash_gate_freetext_fixes_64_75.py`, `tests/test_bash_gate_erkennung_299.py`, `tests/test_bash_gate_erkennung_299_teil_b.py`, `tests/test_bash_gate_erkennung_299_teil_c.py`, `tests/test_bash_gate_env_aliase_324.py` (unverändert, Lauf grün)

> Die Test-Zuordnung wird **bei der Spec-Erstellung** eingetragen, nicht nachträglich:
> Nach der Freigabe ist diese Datei eingefroren (#230) — jede Änderung verschiebt den
> PO-Briefing-Hash und blockt den Workflow-Abschluss. Stimmt der Testname später nicht
> mehr, gehört die Korrektur in die TDD-RED-Artefakte (`workflow.py add-artifact`),
> nicht in diese Datei.

## Test Plan

Automatische Tests (jeweils an eine AC oben gebunden):

- `pytest tests/test_bash_gate_ln_state_407.py` (AC-1 bis AC-9). Jeder Test: GIVEN Wegwerf-Repo mit aktivem Workflow in phase6, WHEN der Befehl als Subprozess durch das echte `core/hooks/bash_gate.py` läuft, THEN Exit 2 (blockende Fälle) bzw. Exit 0 (Kontrollfälle). Beide Fehlerrichtungen, Abweichungen werden gesammelt gemeldet.
- Regressionslauf: `pytest tests/test_bash_gate_false_positives.py tests/test_bash_gate_freetext_fixes_64_75.py tests/test_bash_gate_erkennung_299.py tests/test_bash_gate_erkennung_299_teil_b.py tests/test_bash_gate_erkennung_299_teil_c.py tests/test_bash_gate_env_aliase_324.py` (AC-10), danach die Vollsuite.

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Erweitert die Erkennung von Prüfung 3b innerhalb der bestehenden Entscheidung „Gate prüft Befehlstext per Regeln“ (Struktur aus #299); kein neues Muster, keine neue Abhängigkeit. Die Alternative „`st_nlink` beim Lesen“ (C) würde das Prinzip „Prüfung an der Quelle“ einführen und ist bewusst nach #410 verschoben; keine bestehende ADR wird gekippt.

## Changelog

- 2026-10-09: Initial spec created (#407)
