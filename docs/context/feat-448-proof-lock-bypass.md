# Context: feat-448-proof-lock-bypass

## Request Summary
Issue #448 (Folgebefund aus dem Adversary-Dialog zu #447). Die Schreibsperre für den Simulator-Beleg
(`docs/artifacts/<wf>/simulator-run.txt` und `docs/artifacts/<wf>/simulator-run/`) lässt sich umgehen.
- **F001:** Bash-Schreibzugriffe, die die Zielerkennung nicht kennt:
  - `bash -c`/`sh -c`/`eval`
  - Variablen (`X=…; echo x > $X`)
  - Interpreter (`python3 -c "open(…,'w')"`)
  - rsync, curl -o, wget -O, patch, ed, tar -C, unzip -d
- **F002:** Ein Symlink-Ordner (`ln -s docs/artifacts/<wf> lnk`, danach Write/Umleitung auf
  `lnk/simulator-run.txt`) umgeht das Muster, weil nur der normalisierte, nicht der aufgelöste Pfad
  geprüft wird.

## Related Files
| File | Relevance |
|------|-----------|
| `core/hooks/bash_gate.py` | `PROOF_FILE_PATTERNS` (Z. ~70), `_writes_proof_file` (Z. ~619), `_into_dir_targets` (Z. ~600), Aufruf Prüfung 1d (Z. ~1261, nur bei `workflow_enforced`, vor dem Git-Schnellweg). Zielerkennung über `_config_write_targets` + `_CONFIG_WRITERS` (Z. ~514): cp/install/ln/mv/rm/unlink/tee/truncate/touch/sed/perl/git/dd/yq plus Umleitungen (`_split_redirects`). |
| `core/hooks/edit_gate.py` | `PROOF_FILE_RE` (Z. 52), Prüfung Z. ~663 auf `os.path.normpath(file_path)`, ohne `resolve()`. Direkt darunter (1b) wird `Path(file_path).expanduser().resolve()` bereits berechnet (Muster vorhanden). |
| `core/hooks/hook_utils.py` | `_git_lex`/`_git_segments` (Z. 433/517), Segmentzerlegung; `git_subcommands(command, depth)` (Z. 531) zerlegt verschachtelte Shells (`bash -c "…"`) rekursiv. Das ist das Vorbild für F001. |
| `tests/test_evidence_gate_447.py` | AC-27/28/29 mit Helfern `_sandbox`, `_edit_gate`, `_bash_gate` (Z. 526–600). AC-29 (enge Sperre) ist die Regressionsgrenze: Erwähnung in Doku, Lesen, Erzeuger-Aufruf (`python3 scripts/sim_proof.py … docs/artifacts/<wf>/simulator-run/run.xcresult …`) müssen frei bleiben. |
| `docs/specs/feat-447-evidence-gate.md` | Ursprungs-Spec, Known Limitation 3 („Sperre wirkt nur über die Hooks“). |
| `docs/specs/fix-418-config-lock-precision.md`, `fix-417-bash-main-write.md` | Vorbilder: Zielerkennung nur für echte Schreibziele, `cd`-Nachführung, fail-open bei Fehlern. |

## Existing Patterns
- **Zwei Philosophien im Bash-Gate:**
  - **„Erwähnung + Schreibindikator“** (3b, für State-Dateien; `_references_protected` + `_has_write_indicator`). Fängt `bash -c`, `python3 -c`, Variablen grob. Bei `sh -c`/`eval` fällt es auf einen Roh-Scan zurück. Erzeugt aber Fehlalarme bei bloßer Erwähnung.
  - **„Echte Schreibziele“** (1b/1c/1d, #417/#418/#447). Präzise, kennt aber nur die Befehle in `_CONFIG_WRITERS` und keine verschachtelten Shells.
- **Verschachtelte Shells:** `_has_real_redirect` und `_matches_file_token` fallen bei `(ba|z|da|k)?sh -c`/`eval` auf einen Roh-Scan zurück. `git_subcommands` zerlegt rekursiv mit Tiefenlimit.
- **Nicht auflösbare Ziele** (`$VAR`, Glob, Backtick) gelten in 1c als fail-open (`_writes_main_repo` überspringt sie).
- **Symlinks:** `edit_gate.py` nutzt an anderer Stelle `Path.resolve()` (Z. 123–138, 495). Die Beleg-Prüfung tut es nicht.

## Dependencies
- Upstream: `hook_utils._git_lex`/`_git_segments`, `_command_args`, `_split_redirects`, `_positional`, `_cd_bases`.
- Downstream:
  - `_CONFIG_WRITERS` und `_config_write_targets` werden auch von 1b (`_writes_effective_config`) und 1c (`_writes_main_repo`) genutzt. Neue Schreiber dort erweitern automatisch auch diese Sperren, mit mehr Schutz, aber auch neuen möglichen Fehlalarmen.
  - Jedes Konsumentenprojekt (Bash-Gate läuft bei jedem Befehl).

## Existing Specs
- `docs/specs/feat-447-evidence-gate.md`: Schreibsperre (AC-27–AC-29), Known Limitations 3.
- `docs/specs/fix-418-config-lock-precision.md`, `docs/specs/fix-417-bash-main-write.md`: Zielerkennungs-Präzision.

## Risks & Considerations
- **Fehlalarme sind das Hauptrisiko.** Das Bash-Gate läuft bei jedem Befehl in jedem Projekt. AC-29 (b) „Doku erwähnt Pfad“ und (d) Erzeuger-Aufruf müssen frei bleiben. Der Erzeuger übergibt einen Pfad unter `simulator-run/` als Argument.
- **Vollständigkeit ist unmöglich.** Ein Hook kann beliebigen Code (`python3 script.py`, das intern schreibt; `node -e`; Base64-kodierte Pfade) nie lückenlos erkennen. Die Spec muss die Grenze ehrlich benennen. Ziel ist: kein trivialer Einzeiler.
- **Wirkung auf 1b/1c:** Neue Einträge in `_CONFIG_WRITERS` (curl -o, wget -O, rsync, tar -C, unzip -d, patch) verschärfen auch den Config-Schutz und die Haupt-Ordner-Sperre. Das ist zu entscheiden: gemeinsam erweitern oder eigene Tabelle nur für den Beleg.
- **Symlink-Auflösung:**
  - `resolve()` auf einen noch nicht existierenden Zielpfad löst nur die existierenden Elternordner auf. Das genügt für den Fall `lnk/simulator-run.txt`.
  - Ein Symlink, der *in* das Projekt *auf* `docs/artifacts/<wf>` zeigt, muss treffen. Ein Pfad außerhalb des Projekts mit gleichem Muster trifft heute schon (Regex auf `normpath`).
- **Defensive Tiefe:** Das Evidence-Gate prüft das Ergebnisbündel neu. Ein gefälschter Beleg braucht ein passendes `run.xcresult`. Einstufung daher MEDIUM.

## Analysis

### Type
Feature (Härtung einer bestehenden Sperre; Folgebefund aus dem Adversary-Dialog zu #447)

### Ist-Zustand (Probe-Matrix, 2026-10-23, gegen `bash_gate.py`/`edit_gate.py` auf `main` 3.42.0)
Messung mit den Helfern `_sandbox`/`_bash_gate`/`_edit_gate` aus `tests/test_evidence_gate_447.py`
(Skript nur im Scratchpad, nicht im Repo). Exit 2 = blockiert, 0 = durchgelassen.

| Form | heute | Soll |
|------|-------|------|
| `bash -c '… > PROOF'`, `sh -c`, `bash -lc`, `sudo bash -c`, `/bin/sh -c`, `eval '…'` | 0 | 2 |
| `X=PROOF; echo x > $X`, `export X=PROOF; echo x > "$X"` | 0 | 2 |
| `python3 -c "open(PROOF,'w')…"`, `python3 - <<EOF`, `echo "…" \| python3`, `node -e "…writeFileSync…"`, `perl -e 'open(F,">PROOF")'` | 0 | 2 |
| `bash <<EOF … > PROOF EOF` | 2 (zufällig: Heredoc-Rumpf wird mitzerlegt) | 2 |
| `rsync … PROOF`, `curl -o PROOF`, `wget -O PROOF`, `patch PROOF`, `ed PROOF`, `tar -xf a -C ART`, `unzip a -d ART` | 0 | 2 |
| `… \| timeout 5 tee PROOF`, `… \| nohup tee PROOF` (Präfix nicht erkannt) | 0 | 2 |
| `cp -l PROOF hl`, `ln PROOF hl` (Hardlink auf den Beleg) | 0 | 2 |
| `ln -s ART l2 && echo x > l2/simulator-run.txt` (Link im selben Befehl) | 0 | 2 |
| `mv ART t && echo x > t/simulator-run.txt && mv t ART` (Vorfahr umbenannt) | 0 | 2 |
| Bash `echo x > lnk/simulator-run.txt` bei bestehendem Symlink `lnk → ART` | 0 | 2 |
| Write `lnk/simulator-run.txt` (relativ und absolut) bei bestehendem Symlink | 0 | 2 |
| **Negativkontrollen:** `python3 -c "print(open(PROOF).read())"`, `bash -c 'cat PROOF'`, `bash scripts/x.sh PROOF`, `echo "PROOF" > "$LOG"`, `curl -o /tmp/x URL`, `tar -xf a -C /tmp`, Erzeuger `python3 scripts/sim_proof.py … RUN/run.xcresult …`, `scripts/sim.sh test-proof …`, Doku-Erwähnung, `ART/other.txt` | 0 | 0 |

Ergebnis: 27 von 28 Angriffsformen kommen heute durch; alle 10 Negativkontrollen sind frei.
Die Matrix ist die RED-Liste für Phase 5 und die Fehlalarm-Grenze (zusätzlich zu AC-29 aus #447).

### Affected Files (with changes)
| File | Change Type | Description |
|------|-------------|-------------|
| `core/hooks/bash_gate.py` | MODIFY | `_writes_proof_file` erweitern: rekursive Zerlegung, Variablen, Inline-Interpreter, eigene Zusatz-Schreiber, Präfixe, Vorfahr-/Link-Regel, `resolve()`-Prüfung |
| `core/hooks/edit_gate.py` | MODIFY | Beleg-Prüfung zusätzlich auf aufgelösten Pfad (normpath ODER resolved) |
| `tests/test_proof_lock_448.py` | CREATE | Probe-Matrix als parametrisierte Tests (Angriff → 2, Negativ → 0) |
| `docs/specs/feat-448-proof-lock-bypass.md` | CREATE | Spec mit ACs + Known Limitations |
| `CHANGELOG.md` | MODIFY | Eintrag unter [Unreleased] |

`docs/specs/feat-447-evidence-gate.md` bleibt unberührt (freigegeben, Spec-Freeze); die neue Spec verweist darauf.

### Scope Assessment
- Files: 5 (2 Code, 1 Test, Spec, CHANGELOG)
- Estimated LoC: bash_gate +90–120, edit_gate +10, Tests +130
- Risk Level: MEDIUM — Bash-Gate läuft bei jedem Befehl in jedem Projekt (Fehlalarm-Risiko); Wirkung aber auf Beleg-Pfade beschränkt, und das Evidence-Gate prüft den Beleg ohnehin neu gegen `run.xcresult`.

### Technical Approach (Entscheidungen als Tech Lead)
1. **Nur Sperre 1d erweitern, nicht `_CONFIG_WRITERS`.** Zusatz-Schreiber in einer eigenen Tabelle, die nur `_writes_proof_file` nutzt. Grund: 1b/1c haben eigene Fehlalarm-Grenzen (#417/#418); eine stille Verschärfung dort ist nicht Teil dieses Auftrags. Gleiche Lücke dort → Folge-Issue **#452**.
2. **Verschachtelte Shells:** Segment mit Kommandowort `bash|sh|zsh|dash|ksh` (auch mit Pfad, nach Präfixen) und einem Flag-Bündel, das `c` enthält (`-c`, `-lc`, `-ec`), sowie `eval …`: Nutzlast neu mit `_git_segments` zerlegen und dieselbe Prüfung rekursiv anwenden, `cd`-Basen werden übernommen. Tiefenlimit 3; darüber oder bei Parse-Fehler Rückfall auf „Beleg-Pfad erwähnt + Schreibindikator“ statt stillem Durchlassen.
3. **Variablen:** Zuweisungen im selben Befehl (`X=…` als eigenes Segment, `export X=…`, `declare`/`local` nicht nötig) einsammeln und `$X`/`${X}` in Zielen ersetzen. Kein „Erwähnung + nicht auflösbares Ziel → Block“ (träfe `echo "PROOF" > "$LOG"`). Shell-Zustand überlebt keinen Bash-Aufruf, daher genügt der Befehl selbst.
4. **Inline-Interpreter:** Nur Inline-Code zählt — `python|python3|node|perl|ruby` mit `-c`/`-e`, mit `-` bzw. ohne Skript-Argument bei Heredoc/Pipe-Eingabe. Aufrufe mit Skriptdatei (Erzeuger `scripts/sim_proof.py`) bleiben frei. Block, wenn der Code das Beleg-Muster erwähnt UND einen **eigenen, engen** Schreibindikator enthält: `open(…, 'w'|'a'|'x'|'+')`, `write_text`, `write_bytes`, `writeFile`, `appendFile`, `createWriteStream`, `shutil.copy*/move`, `os.rename/replace/remove/unlink/symlink/link`, `.touch(`, `.unlink(`, `.rename(`, `.symlink_to(`, Perl `open(… ">…")`. Die vorhandene Liste `WRITE_INDICATORS` ist ungeeignet: `open\(` träfe auch reines Lesen (Negativkontrolle `py read`).
5. **Zusatz-Schreiber (nur 1d):** `rsync` (letztes Positionsargument), `curl -o/--output`, `wget -O/--output-document`, `patch` (Datei-Argument und `-o`), `ed`/`ex` (Datei-Argument), `tar -C DIR` und `unzip -d DIR` als Ordnerziel (Treffer, wenn DIR = `docs/artifacts/<x>` oder darunter im Beleg-Bereich).
6. **Präfixe:** `timeout N`, `nohup`, `nice [-n N]`, `stdbuf …`, `time`, `exec` vor dem Kommandowort überspringen (nur in der 1d-Erkennung).
7. **Vorfahr- und Link-Regel:** `mv`, `ln` (hart und `-s`), `cp -l/-s/-al`, `rsync`, deren Quelle **oder** Ziel `docs/artifacts/<x>` selbst, `docs/artifacts` oder einen Beleg-Pfad ist, zählen als Zugriff auf den Beleg. Deckt Hardlink, Symlink im selben Befehl und Umbenennen-Schreiben-Zurückbenennen ab.
8. **Symlink-Auflösung (F002), beide Gates:** Treffer, wenn normalisierter Pfad **oder** aufgelöster Pfad (`Path.resolve()`, in `try` gekapselt) das Muster trifft. Nie nur einer der beiden: in Konsumentenprojekten kann `docs/artifacts` selbst ein Symlink sein, der aufgelöste Pfad verlöre dann das Muster.

### Dependencies
- Upstream (wiederverwendet, unverändert): `hook_utils._git_segments`/`_git_lex`, `_split_redirects`, `_command_args`, `_positional`, `_copy_targets`, `_into_dir_targets`, `_cd_bases`, `strip_heredoc_bodies` (Achtung: Heredoc-Rumpf für Interpreter-Erkennung aus dem Rohtext `command` lesen, nicht aus `scan_cmd`, falls dort entfernt).
- Downstream: nur Prüfung 1d im Bash-Gate und Schritt 1 im Edit-Gate. 1b/1c unverändert.

### Befunde, die gegen den Plan sprechen
- **Vollständigkeit bleibt unerreichbar:** Skriptdateien, die intern schreiben (`python3 x.py`, `bash x.sh`), `xargs`, `find -exec`, Base64-/zusammengesetzte Pfade, Umbenennen von `docs` oder des Projektordners. Gehören als Known Limitations in die Spec. Zielniveau: kein trivialer Einzeiler.
- **Komplexität im Kern-Gate wächst** (+~100 LoC in `bash_gate.py`). Abfederung: alles in Hilfsfunktionen rund um `_writes_proof_file`, fail-open bei Ausnahmen wie 1b/1c.
- **Vorfahr-Regel (7)** kann seltene legitime Befehle treffen (`mv docs/artifacts/<wf> …` zum Aufräumen). Wird bewusst in Kauf genommen und in der Fehlermeldung benannt; Ausweg Override ist **nicht** vorgesehen (die Beleg-Sperre hat heute keinen).

### Open Questions
- Keine offenen PO-Fragen. Die Abgrenzung 1b/1c ist als Tech-Lead-Entscheidung getroffen und als #452 ausgelagert.
