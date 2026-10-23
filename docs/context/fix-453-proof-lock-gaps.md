# Context: fix-453-proof-lock-gaps

## Request Summary
Issue #453: Restlücken der Beleg-Schreibsperre (Prüfung 1d in `bash_gate.py`) aus dem
Adversary-Dialog und der Validierung zu #448 schließen — sechs Umgehungen (F001–F003, F005–F007)
und ein Fehlalarm (F004). Alle LOW; das Evidence-Gate prüft den Beleg zusätzlich gegen `run.xcresult`.

### Befunde (aus dem Issue + Kommentar)
| ID | Art | Beispiel | Ursache im Code |
|----|-----|----------|-----------------|
| F001 | Umgehung | `python3 -W ignore -c "open(P,'w')"` | `_inline_code`: erstes Nicht-Flag-Token gilt als Skriptdatei; `-W`/`-X`/`-m` u.ä. nehmen einen Wert |
| F002 | Umgehung | `doas`, `busybox`, `flock`, `ionice`, `setsid`, `taskset`, `chronic`, `builtin`, `xargs` vor `tee` | `_PROOF_PREFIXES` geschlossene Liste |
| F003 | Umgehung | Globs/Brace im Ziel, `cp -t ORDNER QUELLE`, `rm -rf ART`, `chmod`/`shred`/`mkdir`, `git mv ART t`, `curl -oDATEI` | Glob/Brace nicht expandiert; Vorfahr-Regel nur `mv/ln/cp -l/-s/rsync`; `_opt_values` kennt kein angehängtes `-oX`; `shred`/`chmod`/`mkdir` in keiner Tabelle |
| F004 | Fehlalarm | Inline-Skript liest Beleg, schreibt woanders → Block | Regel „Erwähnung + Schreibindikator“ irgendwo im Code, nicht ans Beleg-Argument gebunden |
| F005 | Umgehung | `X=PROOF tee $X <<< x` (Zuweisung als Präfix im selben Segment) | `_proof_text_hit` sammelt Zuweisungen nur aus reinen Zuweisungs-Segmenten/`export` |
| F006 | Umgehung | `python3 -c "import os; os.system('echo x > PROOF')"`, `subprocess` | `_INLINE_WRITE_RE` kennt keine Shell-Aufrufe |
| F007 | Umgehung | `tar -cf PROOF …` | `_tar_dir` nur Entpacken mit `-C`; `-f`-Archivziel beim Packen nicht als Schreibziel |

## Related Files
| File | Relevance |
|------|-----------|
| `core/hooks/bash_gate.py` (~618–818) | Gesamte 1d-Härtung aus #448: `_PROOF_LINK_PATTERNS`, `_PROOF_AREA_PATTERNS`, `_PROOF_MENTION_RE`, `_INLINE_WRITE_RE`, `_PROOF_PREFIXES`, `_opt_values`, `_tar_dir`, `_PROOF_WRITERS`, `_PROOF_DIR_WRITERS`, `_skip_prefixes`, `_nested_payload`, `_inline_code`, `_link_paths`, `_proof_path_hit`, `_proof_fallback`, `_proof_segment_hit`, `_proof_text_hit`, `_writes_proof_file` — hier wird geändert |
| `core/hooks/bash_gate.py:70` | `PROOF_FILE_PATTERNS` (Beleg-Muster `docs/artifacts/<x>/simulator-run(.txt|/…)`) |
| `core/hooks/bash_gate.py:1436–1441` | Aufruf 1d: nur bei `workflow_enforced`, vor dem Git-Schnellweg, kein Override |
| `core/hooks/bash_gate.py:370–440, 514–560` | `_split_redirects`, `_command_args`, `_positional`, `_copy_targets`, `_CONFIG_WRITERS`, `_config_write_targets`, `_cd_bases` — wiederverwendet, `_CONFIG_WRITERS` darf sich NICHT ändern (1b/1c, #452) |
| `core/hooks/bash_gate.py:934` | `_has_write_indicator` (breite `WRITE_INDICATORS`), genutzt im Tiefen-Rückfall |
| `core/hooks/hook_utils.py:433/517` | `_git_lex`, `_git_segments` — Zerlegung, unverändert |
| `core/hooks/edit_gate.py:51` | Parallelkopie des Beleg-Musters; vermutlich unberührt (Issue betrifft nur Bash) |
| `tests/test_proof_lock_448.py` | Bestehende parametrisierte Matrix (Helfer `_root`, `_blocked`, `_free`, `_nest`); Vorbild für neue Tests |
| `tests/test_evidence_gate_447.py` | AC-29 „Sperre ist eng“ — Regressionsgrenze für Fehlalarme |
| `tests/test_bash_gate_config_lock_418.py`, `tests/test_bash_gate_main_write_417.py` | 1b/1c dürfen sich nicht verändern |

## Existing Patterns
- Eigene, nur für 1d geltende Tabellen (`_PROOF_WRITERS`, `_PROOF_DIR_WRITERS`, `_PROOF_PREFIXES`) statt `_CONFIG_WRITERS` zu erweitern (ADR 1 aus #448).
- Treffer bei normpath ODER `resolve()` (`_proof_path_hit`, ADR 2).
- Enger Schreibindikator für Inline-Code (`_INLINE_WRITE_RE`, ADR 3), reines Lesen bleibt frei.
- fail-open bei Ausnahmen (`_writes_proof_file` fängt alles); einzige Ausnahme: Tiefe > 3 / Parse-Fehler in Nutzlast → `_proof_fallback`.
- Tests: parametrisierte Angriffs-/Negativlisten mit `_blocked`/`_free`, Symlinks real angelegt.

## Dependencies
- Upstream: `hook_utils._git_segments`/`_git_lex`, `_split_redirects`, `_command_args`, `_positional`, `_copy_targets`, `_into_dir_targets`, `_config_write_targets`, `_cd_bases`, `_has_write_indicator`, `PROOF_FILE_PATTERNS`.
- Downstream: nur `main()` von `bash_gate.py` (Prüfung 1d). Läuft bei JEDEM Bash-Aufruf jedes Konsumentenprojekts mit `workflow_enforced` — unabhängig davon, ob `evidence_checks` aktiv ist.

## Existing Specs
- `docs/specs/feat-448-proof-lock-bypass.md` — Vorgänger (21 ACs, Known Limitations: Skriptdateien, `xargs`/`find -exec`, zusammengesetzte Pfade, Umbenennen von `docs/`, Tiefe > 3). Freigegeben → unverändert lassen.
- `docs/specs/feat-447-evidence-gate.md` — Ursprung (AC-27 bis AC-29), unverändert.
- Verwandt, NICHT im Scope: #452 (gleiche Lücken in 1b/1c).

## Risks & Considerations
- **Fehlalarme in allen Konsumentenprojekten:** neue Regeln wie `rm -rf docs/artifacts/<wf>`, `mkdir`, `chmod` oder Glob-Expansion können legitime Aufräum-Befehle treffen. Grenze in der Analyse festlegen (z. B. `rm`/`chmod` nur, wenn Ziel Beleg-Pfad oder dessen Vorfahr bis `docs/artifacts/<x>`; Glob nur gegen das Beleg-Muster per `fnmatch` statt Dateisystem-Expansion).
- **F004 lockern ohne neues Loch:** Bindung „Schreibindikator am Beleg-Argument“ ist schwer regelbasiert sauber; Alternative: Beleg-Erwähnung muss im selben Ausdruck wie der Schreibaufruf stehen (z. B. `open(<…PROOF…>, 'w')`), Variablen im Inline-Code machen das unscharf → Trade-off dokumentieren.
- **F002 `xargs`/`busybox`/`builtin`:** `xargs` ist in #448 als Known Limitation gelistet; hier nur die Form „Präfix vor Schreibbefehl“ (`xargs tee PROOF`), nicht indirekt weitergereichte Pfade.
- **F007:** `tar -cf` und `tar --file=`, gebündelte Flags (`czf`, `-cvf`), Reihenfolge des Werts nach `f` im Bündel beachten.
- **Spec-Freeze:** `feat-448`-Spec bleibt unangetastet; neue Spec `docs/specs/fix-453-proof-lock-gaps.md`.
- **Adversary-Risiko hoch** (Gate-Code) → mindestens 2 Dialog-Runden.
- Nach Abschluss: Known Limitations ehrlich fortschreiben; Rest-Risiko bleibt durch Evidence-Gate (`run.xcresult`) abgefedert.

## Analysis

### Type
Bug (Härtung) — Restlücken der Beleg-Schreibsperre 1d (`bash_gate.py`), Folge von #448.

### Ist-Stand per Probe (2026-10-23, echter `bash_gate.py`-Subprozess in `_root`-Sandbox)
Saatgut für Phase 5 (als `tests/test_proof_lock_453.py` übernehmen): Helfer `_root`/`_bash_gate` aus `test_proof_lock_448`/`test_evidence_gate_447`, zusätzlich `docs/artifacts/other-wf/` angelegt.
Abkürzungen: `P` = Beleg-Datei `ART/simulator-run.txt`, `ART` = `docs/artifacts/wf-447`, `RUN` = `ART/simulator-run`.

**Kommen heute DURCH (rc 0). Art F = Fälschen möglich, Z = nur Zerstören:**
| ID | Befehl | Art |
|----|--------|-----|
| F001 | `python3 -W ignore -c "open(P,'w')"`, `python3 -X utf8 -c …`, `node -r foo -e …`, `node --eval …`, **neu:** `node -p …` (`-p/--print` fehlt ganz) | F |
| F002 | `doas tee P`, `busybox tee P`, `flock /tmp/l tee P`, `flock /tmp/l -c 'echo x > P'`, `ionice -c 3 tee P`, `setsid tee P`, `taskset 1 tee P`, `chronic tee P`, `echo x \| xargs tee P` | F |
| F003a | `tee ART/simulator-run.t?t`, `tee ART/simulator-run.{txt,x}` (Glob `?`, Brace) | F |
| F003b | `cp -vt ART /tmp/simulator-run.txt`, `cp -tART …`, `cp --target-directory ART …` | F |
| F003c | `curl -oP https://x` (angehängter Wert) | F |
| F003d | `git mv ART t`, **neu:** `git mv fake-dir ART` | Z (Quelle) / F (Ziel) |
| F003e | **neu:** `cp -r /tmp/wf-447 docs/artifacts/`, `cp -r /tmp/fake/. ART/` (rekursive Kopie IN den Bereich) | F |
| F003f | `shred -u P`, `chmod 000 P` | Z |
| F003g | `rm -rf ART`, `rm -rf docs/artifacts`, `git rm -r ART`, `mkdir -p RUN/x` | Z |
| F005 | `X=P sh -c 'tee $X <<< x'`, `X=P python3 -c "import os; open(os.environ['X'],'w')"` | F |
| F006 | `python3 -c "import os; os.system('echo x > P')"`, `subprocess.run(['tee','P'])` | F |
| F007 | `tar -cf P …`, `tar czf P …`, `tar --file=P -c …` | F |

**Blocken heute schon (rc 2):** `builtin echo x > P` (Umleitung zählt unabhängig vom Kommandowort), `tee docs/artifacts/*/simulator-run.txt` (`*` trifft `[^/]+` literal), `cp -t ART /tmp/simulator-run.txt`, `cp -t RUN /tmp/x`, `cp -r /tmp/fake RUN`, `rsync -a /tmp/fake/ ART/`.

**F005 in der Issue-Form ist KEIN echter Angriff:** `X=P tee $X` — Bash expandiert `$X`, bevor die Präfix-Zuweisung wirkt (verifiziert: `X=a; X=b echo "[$X]"` → `[a]`). Echt ist nur der Weg über die Umgebung eines Kindprozesses (Nutzlast `sh -c`, Inline-Interpreter mit `environ`/`getenv`). Entscheidung: `X=P tee $X` bleibt frei (Bash-Semantik) und kommt als Negativfall in die Spec.

**Fehlalarm F004 bestätigt:** `python3 -c "d=open(P).read(); open('/tmp/out','w').write(d)"` → rc 2. Zusätzlich live erlebt: Ein Bash-Heredoc, das diese Analyse in die Kontextdatei schreiben sollte (Erwähnung des Beleg-Pfads im Text + `>>`), wurde geblockt — Rückfallregel „Erwähnung + Schreibindikator“ greift auch für Doku-Text.

**Negativkontrollen, heute frei, müssen frei bleiben (Pflicht-FREE-Liste):** `cat P`, `tar -cf /tmp/a.tar ART`, `rm -rf docs/artifacts/other-wf`, `mkdir -p ART`, `rm -f ART/shot.png`, `grep tee P`, `git add P`, `ls -la ART`, `python3 -c "print(open(P).read())"`, `echo P`, `git log -- P`, `tar -xf /tmp/a.tar -C /tmp/out`, `X=P tee $X <<< x`.

### Entscheidungsgrundlage: Evidence-Gate ist fail-closed
`evidence_gate._verify_xcresult_proof` lehnt fehlenden Beleg, fehlende/prüfsummenlose `summary.json` und fehlendes `run.xcresult` ab. Reines Zerstören (Z) führt nie zu einem falschen Phase-8-Durchlauf, nur zu einem Neu-Erzeugen. Fälschen (F) ist das eigentliche Risiko.

### Affected Files (with changes)
| File | Change Type | Description |
|------|-------------|-------------|
| `core/hooks/bash_gate.py` | MODIFY | nur 1d-Abschnitt (`_PROOF_*`, `_inline_code`, `_opt_values`, `_tar_dir`, `_link_paths`, `_skip_prefixes`, `_proof_segment_hit`, `_proof_text_hit`) + neue 1d-Helfer (Brace/Glob, Zielordner, Rekursiv-Kopie, Inline-Bindung) |
| `tests/test_proof_lock_453.py` | CREATE | Angriffs-/Negativmatrix aus obiger Probe |
| `docs/specs/fix-453-proof-lock-gaps.md` | CREATE | neue Spec; `feat-448`-Spec bleibt unverändert |
| `CHANGELOG.md` | MODIFY | `[Unreleased]` |
| `_CONFIG_WRITERS`, `_copy_targets`, `_git_write_targets`, `_command_args`, `_positional`, `hook_utils.*`, `edit_gate.py` | UNVERÄNDERT | geteilt mit 1b/1c (#452) bzw. nicht betroffen |

### Scope Assessment
- Files: 4 (davon 1 Produktivcode)
- Estimated LoC: Produktivcode ca. +120/-15 in `bash_gate.py`; Tests ca. +250
- Risk Level: **HIGH** — Gate-Code, läuft bei jedem Bash-Aufruf jedes Konsumentenprojekts mit `workflow_enforced` (unabhängig von `evidence_checks`); Fehlalarme treffen alle. Adversary: mind. 2 Runden.

### Technical Approach (Empfehlung je Befund)
1. **Fälschen schließen, Zerstören nicht (ADR-Kandidat 1).** F003g (`rm -rf ART`, `rm -rf docs/artifacts`, `git rm -r ART`, `mkdir -p RUN/x`) → Known Limitation „fail-closed per Evidence-Gate“. Grund: hohes Fehlalarm-Risiko bei legitimem Aufräumen/Anlegen (`rm -rf docs/artifacts/<wf>`, `mkdir -p docs/artifacts/<wf>`), kein Fälschungsgewinn. Ausnahme F003f: `shred` und `chmod`/`chown` nur auf den **exakten** Beleg-Pfad (`PROOF_FILE_PATTERNS`) — ohne Fehlalarm-Risiko, daher billig mitnehmen (`shred`: alle Positionsargumente; `chmod`/`chown`: Positionsargumente ab dem zweiten).
2. **F001 — Interpreter-Optionen mit Wert:** Tabelle je Interpreter (python `-W -X`; node `-r --require --input-type -C`; perl `-I -M -x` mit getrenntem Wert; ruby `-I -r -C`), Werte überspringen; Inline-Flags erweitern um node `--eval`, `-p`, `--print`. `-m MODUL` = kein Inline-Code (wie Skriptdatei). Offen für die Spec: ruby `-E` ist Encoding, kein Code (heute fälschlich als Code-Flag gelesen — harmlos, eher Über-Block).
3. **F002 — geschlossene Präfixliste erweitern (ADR-Kandidat 2):** `doas (-u -C)`, `busybox` (nächstes Wort ist das Applet), `flock` (Optionen `-w -E` mit Wert, danach Lock-Datei als Positionsargument; `-c CMD` → wie `sh -c` als Nutzlast rekursiv), `ionice (-c -n -p -t)`, `setsid`, `taskset` (Maske als Positionsargument; `-c LISTE`), `chronic`, `builtin`, `xargs (-a -d -E -I -L -n -P -s` und Langformen). **Kein** strukturelles „ab jedem Schreiber-Wort neu auswerten“: erzeugt Fehlalarme wie `grep tee P`. Rest (z. B. `su -c`, `runuser`, `script -c`, `unshare`, `chroot`, `watch`, `parallel`) → Known Limitation.
4. **F003a — Glob/Brace:** eigene 1d-Brace-Expansion (Komma-Listen, verschachtelt) und für Ziele mit `?`/`[` zusätzlich `glob.glob` gegen jede Basis (Bash-Semantik: Glob expandiert nur gegen Vorhandenes; ohne Treffer bleibt der Literal-Pfad, der den Beleg nicht trifft). Der bestehende Regex-Treffer für `*` bleibt.
5. **F003b — `cp`-Zielordner:** eigener 1d-Extraktor (`-t` im Bündel `-vt`, angehängt `-tDIR`, `--target-directory DIR`/`=DIR`) → `DIR/<basename>` je Quelle. `_copy_targets` bleibt unverändert (#452).
6. **F003c — `_opt_values`:** angehängter Wert bei Kurz-Flags (`-oDATEI`; Bündel `-sSoDATEI` nach getopt-Semantik: Rest nach dem Wert-Flag ist der Wert). Nur 1d.
7. **F003d — `git mv`:** Quellen UND Ziel gegen `_PROOF_LINK_PATTERNS` (Vorfahr-/Link-Regel wie `mv`), nur in `_link_paths`. `git rm` → Zerstörer, Known Limitation.
8. **F003e — rekursive Kopie IN den Bereich:** `cp -r/-R/-a` mit Ziel `docs/artifacts` oder `docs/artifacts/<x>`: blocken nur, wenn die Quelle auf der Platte einen Eintrag `simulator-run(.txt)` an der Stelle enthält, die im Ziel auf das Beleg-Muster fällt (Quelle `X` → `DEST/basename(X)/…`, Quelle `X/.` → `DEST/…`). Präzise, kein Fehlalarm für `cp -r screenshots/ ART/`. `rsync` ist schon abgedeckt.
9. **F004 + F006 gemeinsam (ADR-Kandidat 3):** Inline-Code wird pro Anweisung bewertet (Trennung an `;`/Zeilenumbruch): Block, wenn eine Anweisung eine Beleg-Erwähnung **und** einen Schreibindikator enthält. Einstufige Variablen-Verfolgung: Bezeichner, denen eine Erwähnung zugewiesen wird (`p = '…P…'`, `p = Path('…P…')`), zählen in späteren Anweisungen als Erwähnung. Schreibindikator erweitert um Shell-Aufrufe (F006): `os.system`, `os.popen`, `subprocess.*`, `os.exec*`/`spawn*`, node `child_process`/`execSync`/`spawnSync`, perl/ruby `system(`, `exec(`, Backticks, `qx`. Trade-off: mehrstufige Indirektion (`a=P; b=a; open(b,'w')`) und aus Teilstrings zusammengesetzte Erwähnung → Known Limitation (wie in #448 „zusammengesetzte Pfade“). Alternative „Shell-Strings herausziehen und rekursiv durch `_proof_text_hit`“ verworfen: deckt die Listenform `subprocess.run(['tee', P])` nicht ab und kostet mehr Code. Die Rückfallregel `_proof_fallback` (Tiefe > 3 / Parse-Fehler) bleibt unverändert grob.
10. **F005 — Präfix-Zuweisungen in die Kindumgebung:** Zuweisungen vor dem Kommandowort im selben Segment (`X=P cmd …`) bilden eine segmentlokale Umgebung, die (a) in die Nutzlast von `sh -c`/`eval`/`flock -c` substituiert wird und (b) für Inline-Code als Erwähnung zählt, wenn der Code die Umgebung liest (`environ`, `getenv`, `process.env`, `$ENV{`, `ENV[`). Gleiches für schon per `export`/Zuweisung bekannte Werte. Die Argumente desselben Kommandos (`X=P tee $X`) werden NICHT substituiert (Bash-Semantik).
11. **F007 — `tar` packen:** bei Modus `c`/`r`/`u`/`A` (Bündel ohne Strich `czf`, `-cvf`, `--create`/`--append`/`--update`) ist der Wert von `-f`/`--file`/`--file=` Schreibziel gegen `PROOF_FILE_PATTERNS`. Wert im Bündel: nächstes Token (getopt) bzw. bei altem Stil das erste folgende Argument. Entpacken (`-x -f`) liest nur.

### Dependencies
- Upstream unverändert: `hook_utils._git_segments`/`_git_lex`, `_split_redirects`, `_command_args`, `_positional`, `_copy_targets`, `_into_dir_targets`, `_config_write_targets`, `_cd_bases`, `_has_write_indicator`, `PROOF_FILE_PATTERNS`.
- Downstream: nur Prüfung 1d in `main()`. Regressionsgrenzen: `tests/test_proof_lock_448.py`, `tests/test_evidence_gate_447.py` (AC-29 „Sperre ist eng“), `tests/test_bash_gate_config_lock_418.py`, `tests/test_bash_gate_main_write_417.py`.

### Process Notes
- Bug-Intake-Agent übersprungen: Die Probe mit dem echten Gate ersetzt die Investigation (Ist-Stand je Befund belegt).
- Strategische Bewertung per Advisor-Review statt Plan-Agent; eingearbeitet: Fälscher/Zerstörer-Schnitt, F005-Bash-Semantik, F004/F006 gemeinsam, Listen statt Struktur, neue Proben (`git mv … ART`, `cp -r` in den Bereich, `node -p`).

### Open Questions
- Keine, die der PO entscheiden muss. Die drei ADR-Kandidaten (Zerstörer → Known Limitation; Präfixliste statt Struktur; Bindung pro Anweisung + einstufige Variablen-Verfolgung) kommen mit Begründung in die Spec und werden im PO-Briefing sichtbar.
- Für die Spec zu klären: Soll die Rückfallregel `_proof_fallback` (blockte live einen Doku-Heredoc) ebenfalls enger werden? Empfehlung: nein in diesem Issue — sie greift nur bei Tiefe > 3/Parse-Fehler bzw. Daten-Heredocs mit Interpreter; als Beobachtung in Known Limitations notieren.
