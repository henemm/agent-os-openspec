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
