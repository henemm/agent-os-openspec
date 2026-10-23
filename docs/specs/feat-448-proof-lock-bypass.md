---
entity_id: feat-448-proof-lock-bypass
type: feature
created: 2026-10-23
updated: 2026-10-23
status: draft
workflow: feat-448-proof-lock-bypass
version: "1.0"
tags: [bash-gate, edit-gate, evidence-gate, beleg-sperre, symlink, haertung]
test_targets: ["tests/test_proof_lock_448.py", "tests/test_evidence_gate_447.py"]
---

# Abdichtung der Beleg-Schreibsperre (Simulator-Beleg) — #448

## Approval

- [ ] Approved

## GitHub Issue

- **Issue:** #448 (Folgebefund F001/F002 aus dem Adversary-Dialog zu #447). Dieselbe Lücke in den Sperren 1b (Config) und 1c (Hauptordner) ist **nicht** Teil dieser Spec, sondern Folge-Issue #452.

## Purpose

Das Evidence-Gate (#447) verlangt vor `phase8_complete` einen maschinell erzeugten Simulator-Beleg (`docs/artifacts/<wf>/simulator-run.txt` und alles unter `docs/artifacts/<wf>/simulator-run/`). Damit Claude diesen Beleg nicht von Hand schreibt, sperren `bash_gate.py` (Prüfung 1d) und `edit_gate.py` den Schreibzugriff. Diese Sperre lässt sich heute mit trivialen Einzeilern umgehen: 27 von 28 gemessenen Angriffsformen kommen durch (verschachtelte Shells, Variablen, Inline-Interpreter, weitere Schreibbefehle wie `curl -o` oder `rsync`, Befehlspräfixe, Hardlinks, Symlink-Ordner). Die Spec dichtet diese Formen ab, ohne lesende Zugriffe, Erwähnungen in Doku und den echten Erzeuger-Aufruf zu blockieren. Rein regelbasiert, ohne Modell, ohne neue Abhängigkeit. Ziel ist „kein trivialer Einzeiler mehr“, nicht Vollständigkeit (siehe Known Limitations).

## Source

- **File:** `core/hooks/bash_gate.py` — `PROOF_FILE_PATTERNS`, `_writes_proof_file`, `_into_dir_targets`, `_config_write_targets`/`_CONFIG_WRITERS` (nur lesend verwendet), Aufruf Prüfung 1d (nur bei `workflow_enforced`, vor dem Git-Schnellweg); `core/hooks/edit_gate.py` — `PROOF_FILE_RE` und die Beleg-Prüfung auf `os.path.normpath(file_path)`
- **Analyse:** `docs/context/feat-448-proof-lock-bypass.md` (Probe-Matrix, Technical Approach Punkte 1 bis 8, Befunde dagegen)
- **Ursprungs-Spec:** `docs/specs/feat-447-evidence-gate.md` (AC-27 bis AC-29, Known Limitation 3) — bleibt unberührt (freigegeben, Spec-Freeze)
- **Stilvorbilder:** `docs/specs/fix-418-config-lock-precision.md`, `docs/specs/fix-417-bash-main-write.md`

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `core/hooks/bash_gate.py` | Modul | Kern-Gate Bash, Prüfung 1d; läuft bei jedem Bash-Aufruf in jedem Konsumentenprojekt |
| `core/hooks/edit_gate.py` | Modul | Kern-Gate Edit/Write, Beleg-Prüfung (Schritt 1) |
| `core/hooks/hook_utils.py` (`_git_lex`, `_git_segments`, `git_subcommands`, `strip_heredoc_bodies`) | Modul | Zerlegung in Segmente; `git_subcommands` ist das Vorbild für die rekursive Zerlegung verschachtelter Shells; unverändert |
| `_split_redirects`, `_command_args`, `_positional`, `_copy_targets`, `_into_dir_targets`, `_cd_bases` | Funktionen | Zielerkennung und `cd`-Nachführung; unverändert wiederverwendet |
| `_CONFIG_WRITERS`, `_config_write_targets` | Tabelle/Funktion | Werden auch von 1b (`_writes_effective_config`) und 1c (`_writes_main_repo`) genutzt; **bleiben unverändert** |
| `tests/test_evidence_gate_447.py` (`_sandbox`, `_bash_gate`, `_edit_gate`) | Testhilfen | Wiederverwendung für die neuen Tests; AC-29 ist Regressionsgrenze |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| `core/hooks/bash_gate.py` | MODIFY | `_writes_proof_file` erweitern: rekursive Zerlegung, Variablen, Inline-Interpreter, eigene Zusatz-Schreiber-Tabelle, Präfixe, Vorfahr-/Link-Regel, `resolve()`-Prüfung; Fehlermeldung nennt die Vorfahr-Regel |
| `core/hooks/edit_gate.py` | MODIFY | Beleg-Prüfung zusätzlich auf aufgelösten Pfad (normpath ODER resolved) |
| `tests/test_proof_lock_448.py` | CREATE | Probe-Matrix als parametrisierte Tests (Angriff → Exit 2, Negativkontrolle → Exit 0) |
| `docs/specs/feat-448-proof-lock-bypass.md` | CREATE | Diese Spec |
| `CHANGELOG.md` | MODIFY | Eintrag unter [Unreleased] (Teil des Scopes) |

### Estimated Changes

- Files: 5
- LoC: bash_gate +90 bis +120, edit_gate +10, Tests +130

### Out of Scope

- Erweiterung der Sperren 1b (Config) und 1c (Hauptordner) um dieselben Formen: Folge-Issue #452. `_CONFIG_WRITERS` bleibt unverändert, damit deren Fehlalarm-Grenzen (#417/#418) nicht still verschoben werden.
- Ein Override-Ausweg für die Beleg-Sperre: bewusst keiner (hat sie heute auch nicht).
- Änderungen an `docs/specs/feat-447-evidence-gate.md`.
- Erkennung von Schreibzugriffen, die in Skriptdateien stecken (siehe Known Limitations).

## Implementation Details

Alles in Hilfsfunktionen rund um `_writes_proof_file`; jede Ausnahme führt zu „kein Treffer“ (fail-open, wie 1b/1c). Reihenfolge der Erkennung je Segment:

1. **Präfixe überspringen** (nur in 1d): `timeout N`, `nohup`, `nice [-n N]`, `stdbuf …`, `time`, `exec` vor dem Kommandowort; ebenso `sudo`-Form und Pfad-Kommandos (`/bin/sh`).
2. **Verschachtelte Shells:** Kommandowort `bash|sh|zsh|dash|ksh` (auch mit Pfad) mit Flag-Bündel, das `c` enthält (`-c`, `-lc`, `-ec`), sowie `eval …`: Nutzlast erneut mit `_git_segments` zerlegen und dieselbe Prüfung rekursiv anwenden, `cd`-Basen werden übernommen. Tiefenlimit 3. Bei Tiefe > 3 oder Parse-Fehler: Rückfall auf „Beleg-Pfad erwähnt + Schreibindikator“ statt stillem Durchlassen.
3. **Variablen:** Zuweisungen im selben Befehl (`X=…` als eigenes Segment, `export X=…`) einsammeln, `$X`/`${X}` in Zielen ersetzen. Nicht auflösbare Variablen gelten weiter als „kein Treffer“ (kein „Erwähnung + unbekanntes Ziel → Block“, das träfe `echo "PROOF" > "$LOG"`).
4. **Inline-Interpreter:** `python|python3|node|perl|ruby` mit `-c`/`-e` sowie `-`/ohne Skriptargument bei Heredoc- oder Pipe-Eingabe (Heredoc-Rumpf aus dem Rohtext lesen). Block nur, wenn der Code das Beleg-Muster erwähnt UND einen **eigenen, engen Schreibindikator** enthält (`open(…, 'w'|'a'|'x'|'+')`, `write_text`, `write_bytes`, `writeFile`/`writeFileSync`, `appendFile`, `createWriteStream`, `shutil.copy*/move`, `os.rename/replace/remove/unlink/symlink/link`, `.touch(`, `.unlink(`, `.rename(`, `.symlink_to(`, Perl `open(… ">…")`). Aufrufe mit Skriptdatei zählen nicht.
5. **Zusatz-Schreiber (eigene Tabelle, nur für 1d):** `rsync` (letztes Positionsargument), `curl -o/--output`, `wget -O/--output-document`, `patch` (Datei-Argument und `-o`), `ed`/`ex` (Datei-Argument), `tar -C DIR` und `unzip -d DIR` als Ordnerziel (Treffer, wenn DIR im Beleg-Bereich `docs/artifacts/<x>` oder darunter liegt).
6. **Vorfahr- und Link-Regel:** `mv`, `ln` (hart und `-s`), `cp -l/-s/-al`, `rsync`, deren Quelle **oder** Ziel `docs/artifacts/<x>` selbst, `docs/artifacts` oder ein Beleg-Pfad ist, zählt als Zugriff auf den Beleg. Deckt Hardlink, Symlink im selben Befehl und Umbenennen-Schreiben-Zurückbenennen ab.
7. **Symlink-Auflösung im Bash-Gate:** Jedes Ziel wird zusätzlich mit `Path.resolve()` (in `try` gekapselt) geprüft; Treffer, wenn normalisierter **oder** aufgelöster Pfad das Muster trifft.
8. **Symlink-Auflösung im Edit-Gate:** gleiche Regel für `file_path`, relativ und absolut (Muster vorhanden: die Berechnung `Path(file_path).expanduser().resolve()` direkt unter der Beleg-Prüfung).

Die Fehlermeldung bei Treffer nennt zusätzlich die Vorfahr-Regel („auch Umbenennen, Verlinken oder Kopieren des Ordners `docs/artifacts/<wf>` zählt als Zugriff auf den Beleg“).

## Expected Behavior

- **Input:** Ein Bash-Befehl bzw. ein Edit/Write-Aufruf in einem Projekt mit erzwungenem Workflow (1d) bzw. beliebigem Zielpfad (Edit-Gate).
- **Output:** Exit 2 mit Begründung, wenn der Aufruf den Beleg schreiben, verlinken oder sein Vorfahrverzeichnis umbenennen würde; sonst Exit 0 wie bisher.
- **Side effects:** Keine. Lesezugriffe, Erwähnungen in Doku/Echo-Text, der Erzeuger-Aufruf und alle Befehle ohne Bezug zum Beleg bleiben frei. Sperren 1b/1c verhalten sich unverändert.

## Known Limitations

- **Skriptdateien, die intern schreiben** (`python3 x.py`, `bash x.sh`) sind unsichtbar: der Hook sieht nur die Befehlszeile, nicht den Dateiinhalt.
- **`xargs`, `find -exec`** reichen Pfade indirekt weiter; nicht erkannt.
- **Base64-kodierte oder zusammengesetzte Pfade** (`"docs/arti""facts"`-artige Konstruktion zur Laufzeit, `$(printf …)`) werden nicht aufgelöst.
- **Umbenennen von `docs/` oder des Projektordners** selbst: die Vorfahr-Regel endet bei `docs/artifacts`.
- **Variablen aus früheren Bash-Aufrufen** sind irrelevant: Shell-Zustand überlebt keinen Aufruf; nur Zuweisungen im selben Befehl werden aufgelöst.
- **Schutz nur über die Hooks** (Known Limitation 3 aus #447 bleibt): ein Prozess außerhalb von Claude Code ist nicht gesperrt.
- **Tiefe > 3** verschachtelter Shells fällt auf die gröbere Erwähnungs-Prüfung zurück; sie kann dort in seltenen Fällen fälschlich blocken oder (ohne Schreibindikator) durchlassen.
- **Vorfahr-Regel** trifft seltene legitime Befehle (z.B. `mv docs/artifacts/<wf> …` zum Aufräumen); bewusst in Kauf genommen, in der Fehlermeldung benannt, kein Override.
- **Defensive Tiefe:** Das Evidence-Gate prüft den Beleg ohnehin gegen `run.xcresult`; ein gefälschter Beleg braucht ein passendes Ergebnisbündel. Deshalb Einstufung MEDIUM, nicht HIGH.

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] Alle 28 Angriffsformen der Probe-Matrix (27 heute offene plus `bash <<EOF … > PROOF`, das heute nur zufällig blockt; verschachtelte Shells, Variablen, Inline-Interpreter, Zusatz-Schreiber, Präfixe, Hardlink, Vorfahr-/Link-Regel, Symlink in Bash- und Edit-Gate) werden mit Exit 2 blockiert, und die Meldung benennt die Vorfahr-Regel
- [ ] Alle 10 Negativkontrollen (u.a. Erzeuger-Aufruf `sim_proof.py`, `echo "PROOF" > "$LOG"`) bleiben frei; kein neuer Fehlalarm in `tests/test_evidence_gate_447.py` (AC-29)
- [ ] `CHANGELOG.md` enthält den Eintrag unter [Unreleased]
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf grün, insbesondere Sperren 1b/1c)

## Acceptance Criteria

- **AC-1:** Given ein Workflow mit erzwungener Sperre / When ein Befehl den Beleg in einer verschachtelten Shell schreibt (`bash -c '… > PROOF'`, `sh -c`, `bash -lc`, `sudo bash -c`, `/bin/sh -c`, `eval '…'`; auch mit `cd` in der Nutzlast) / Then beendet sich das Bash-Gate mit Exit 2
  - Test: `tests/test_proof_lock_448.py::test_nested_shell_and_eval_blocked`
- **AC-2:** Given eine Variablenzuweisung im selben Befehl / When `X=PROOF; echo x > $X` oder `export X=PROOF; echo x > "$X"` (auch `${X}`) ausgeführt wird / Then Exit 2
  - Test: `tests/test_proof_lock_448.py::test_variable_in_same_command_blocked`
- **AC-3:** Given ein Inline-Interpreter-Aufruf mit engem Schreibindikator / When `python3 -c "open(PROOF,'w')…"`, `python3 - <<EOF`, `echo "…" | python3`, `node -e "…writeFileSync…"` oder `perl -e 'open(F,">PROOF")'` den Beleg-Pfad enthält / Then Exit 2; die Heredoc-Form `bash <<EOF … > PROOF EOF` bleibt ebenfalls Exit 2
  - Test: `tests/test_proof_lock_448.py::test_inline_interpreter_with_write_indicator_blocked`
- **AC-4:** Given die eigene Zusatz-Schreiber-Tabelle / When `rsync … PROOF`, `curl -o PROOF`, `wget -O PROOF`, `patch PROOF`, `ed PROOF`, `tar -xf a -C ART` oder `unzip a -d ART` auf den Beleg bzw. den Beleg-Ordner zielt / Then Exit 2
  - Test: `tests/test_proof_lock_448.py::test_additional_writers_blocked`
- **AC-5:** Given ein Schreibbefehl mit Präfix / When `… | timeout 5 tee PROOF`, `… | nohup tee PROOF`, `nice -n 5`, `stdbuf -oL`, `time` oder `exec` vor dem Kommandowort steht / Then Exit 2
  - Test: `tests/test_proof_lock_448.py::test_command_prefixes_blocked`
- **AC-6:** Given der Beleg als Quelle eines harten Links / When `cp -l PROOF hl` oder `ln PROOF hl` ausgeführt wird / Then Exit 2
  - Test: `tests/test_proof_lock_448.py::test_hardlink_on_proof_blocked`
- **AC-7:** Given die Vorfahr-/Link-Regel / When `mv`, `ln` (hart und `-s`), `cp -l/-s/-al` oder `rsync` den Ordner `docs/artifacts/<wf>`, `docs/artifacts` oder einen Beleg-Pfad als Quelle oder Ziel hat, auch kombiniert (`ln -s ART l2 && echo x > l2/simulator-run.txt`, `mv ART t && echo x > t/simulator-run.txt && mv t ART`) / Then Exit 2
  - Test: `tests/test_proof_lock_448.py::test_ancestor_and_link_rule_blocked`
- **AC-8:** Given ein bestehender Symlink `lnk → docs/artifacts/<wf>` / When das Bash-Gate `echo x > lnk/simulator-run.txt` sieht / Then Exit 2 (aufgelöster Pfad trifft das Muster)
  - Test: `tests/test_proof_lock_448.py::test_bash_symlink_resolution_blocked`
- **AC-9:** Given derselbe bestehende Symlink `lnk` / When das Edit-Gate ein Write auf `lnk/simulator-run.txt` erhält, sowohl relativ als auch absolut / Then Exit 2; die Prüfung trifft bei normpath ODER aufgelöstem Pfad (ein Projekt, in dem `docs/artifacts` selbst ein Symlink ist, verliert den Schutz nicht)
  - Test: `tests/test_proof_lock_448.py::test_edit_gate_symlink_resolution_blocked`
- **AC-10:** Given die Negativkontrolle „Inline-Python liest nur“ / When `python3 -c "print(open(PROOF).read())"` ausgeführt wird / Then Exit 0
  - Test: `tests/test_proof_lock_448.py::test_negative_python_read_free`
- **AC-11:** Given die Negativkontrolle „verschachtelte Shell liest nur“ / When `bash -c 'cat PROOF'` ausgeführt wird / Then Exit 0
  - Test: `tests/test_proof_lock_448.py::test_negative_bash_c_cat_free`
- **AC-12:** Given die Negativkontrolle „Skriptdatei mit Beleg-Pfad als Argument“ / When `bash scripts/x.sh PROOF` ausgeführt wird / Then Exit 0
  - Test: `tests/test_proof_lock_448.py::test_negative_script_with_proof_argument_free`
- **AC-13:** Given die Negativkontrolle „Beleg-Pfad nur im Echo-Text, Ziel unbekannte Variable“ / When `echo "PROOF" > "$LOG"` ausgeführt wird / Then Exit 0
  - Test: `tests/test_proof_lock_448.py::test_negative_echo_proof_text_to_variable_free`
- **AC-14:** Given Negativkontrollen für die Zusatz-Schreiber mit unbeteiligtem Ziel / When `curl -o /tmp/x URL` bzw. `tar -xf a -C /tmp` ausgeführt wird / Then Exit 0
  - Test: `tests/test_proof_lock_448.py::test_negative_curl_tar_other_target_free`
- **AC-15:** Given der echte Erzeuger-Aufruf / When `python3 scripts/sim_proof.py <wf> <testklasse> docs/artifacts/<wf>/simulator-run/run.xcresult <endzeile> <befehl> <exit>` bzw. `scripts/sim.sh test-proof …` ausgeführt wird / Then Exit 0 (das Bündel-Argument liegt selbst unter dem gesperrten Ordner; Skriptdatei-Aufrufe zählen nicht als Inline-Interpreter)
  - Test: `tests/test_proof_lock_448.py::test_negative_generator_call_free`
- **AC-16:** Given Doku-Erwähnung und Nachbardatei / When ein Befehl den Beleg-Pfad nur in Text erwähnt (z.B. `echo "siehe docs/artifacts/<wf>/simulator-run.txt" >> README.md`) oder `docs/artifacts/<wf>/other.txt` schreibt / Then Exit 0
  - Test: `tests/test_proof_lock_448.py::test_negative_doc_mention_and_sibling_file_free`
- **AC-17:** Given die bestehende Prüfung aus #447 / When `tests/test_evidence_gate_447.py` (insbesondere AC-27 bis AC-29) läuft / Then bleibt sie unverändert grün
  - Test: `tests/test_evidence_gate_447.py::test_ac29_write_protection_is_narrow` (Regressionslauf der gesamten Datei)
- **AC-18:** Given die Sperren 1b (`_writes_effective_config`) und 1c (`_writes_main_repo`) / When Befehle mit den neuen Zusatz-Schreibern (`curl -o`, `wget -O`, `rsync`, `tar -C`, `unzip -d`, `patch`) gegen Config bzw. Hauptordner laufen / Then verhalten sich 1b/1c unverändert (`_CONFIG_WRITERS` unverändert, keine neue Blockade); die bestehenden Tests zu #417/#418 bleiben grün
  - Test: `tests/test_proof_lock_448.py::test_config_and_main_repo_locks_unchanged`
- **AC-19:** Given Ausnahmen oder Parse-Fehler / When die Beleg-Erkennung intern eine Ausnahme wirft (z.B. `resolve()` schlägt fehl, kaputte Quotes in nicht-verschachteltem Befehl) / Then fail-open (Exit 0) wie 1b/1c
  - Test: `tests/test_proof_lock_448.py::test_fail_open_on_exception`
- **AC-20:** Given verschachtelte Shells über der Tiefe 3 oder mit Parse-Fehler in der Nutzlast / When die Nutzlast Beleg-Pfad und Schreibindikator enthält / Then Rückfall auf die Erwähnungs-Prüfung: Exit 2; ohne Schreibindikator Exit 0 (einzige Ausnahme von fail-open)
  - Test: `tests/test_proof_lock_448.py::test_depth_and_parse_error_fallback`
- **AC-21:** Given ein blockierter Zugriff / When das Bash-Gate die Fehlermeldung ausgibt / Then benennt sie die Vorfahr-Regel (Umbenennen, Verlinken, Kopieren von `docs/artifacts/<wf>` zählt als Zugriff)
  - Test: `tests/test_proof_lock_448.py::test_error_message_names_ancestor_rule`

> Die Test-Zuordnung steht bei der Spec-Erstellung fest (Spec-Freeze #230). Weicht ein Testname später ab, wird das in den TDD-RED-Artefakten (`workflow.py add-artifact`) korrigiert, nicht in dieser Datei. AC-17 verweist auf den vorhandenen AC-29-Test aus #447.

## Test Plan

Automatische Tests (jeweils an eine AC oben gebunden):

- `pytest tests/test_proof_lock_448.py` — neue Datei, parametrisiert über die Probe-Matrix aus `docs/context/feat-448-proof-lock-bypass.md` (Angriff → Exit 2, Negativkontrolle → Exit 0), Helfer `_sandbox`/`_bash_gate`/`_edit_gate` aus `tests/test_evidence_gate_447.py` (AC-1 bis AC-16, AC-18 bis AC-21).
- Symlink-Fälle legen den Link in der Sandbox real an (`os.symlink`), kein Mocking von `resolve()`.
- `pytest tests/test_evidence_gate_447.py` — bestehende Tests bleiben grün (AC-17).
- `pytest tests/` — Regressionslauf, insbesondere die Tests zu 1b/1c (#417/#418).
- RED zuerst: Alle Angriffsformen der Matrix scheitern vor der Implementierung (Exit 0 statt 2); die 10 Negativkontrollen sind schon vorher grün.

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Drei Entscheidungen, jeweils gegen Alternativen abgewogen.

**1. Eigene Zusatz-Schreiber-Tabelle statt Erweiterung von `_CONFIG_WRITERS`.** `_CONFIG_WRITERS` speist auch 1b und 1c, die eigene Fehlalarm-Grenzen haben (#417/#418). Eine gemeinsame Erweiterung würde dort still verschärfen, mit neuen möglichen Fehlalarmen in jedem Konsumentenprojekt, und gehört nicht zum Auftrag. Verworfen: gemeinsame Erweiterung (mehr Schutz, aber ungeprüftes Risiko). Die gleiche Lücke in 1b/1c wird als #452 getrennt bearbeitet.

**2. Treffer bei normpath ODER aufgelöstem Pfad, nie nur einer.** Nur `resolve()` würde den Schutz verlieren, wenn in einem Konsumentenprojekt `docs/artifacts` selbst ein Symlink ist (aufgelöster Pfad enthält das Muster dann nicht mehr). Nur `normpath` ist die heutige Lücke F002. Verworfen: ausschließlich aufgelöst (regressiv bei Symlink-`docs/artifacts`), ausschließlich normalisiert (Status quo).

**3. Eigener enger Schreibindikator für Inline-Interpreter statt der vorhandenen `WRITE_INDICATORS`.** `WRITE_INDICATORS` enthält u.a. `open\(` und träfe damit auch reines Lesen (`print(open(PROOF).read())`), das als Negativkontrolle frei bleiben muss. Verworfen: Wiederverwendung der breiten Liste (Fehlalarme); „Beleg erwähnt + nicht auflösbares Ziel → Block“ (träfe `echo "PROOF" > "$LOG"`); Roh-Scan auf Erwähnung allein (träfe Doku und Erzeuger-Aufruf).

Weitere verworfene Alternative: vollständige Interpretation von Skriptdateien oder Sandbox-Ausführung — unverhältnismäßig für einen Hook, der bei jedem Befehl läuft; die Grenze steht in den Known Limitations.

## Changelog

- 2026-10-23: Initial spec created
