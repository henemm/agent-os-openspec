# Context: fix-418-config-lock-precision

## Request Summary
Die Config-Sperre aus #410 (`bash_gate.py` Prüfung 1b, `_writes_effective_config`) soll nur echte Schreibzugriffe auf die wirksame Gate-Config treffen: lesende Befehle mit Umleitung/Kopierziel frei (Teil A), versehentlich auslösbare Langformen blocken (Teil B), `cd` im selben Befehl nachführen (Teil C).

## Related Files
| File | Relevance |
|------|-----------|
| `core/hooks/bash_gate.py` (`_writes_effective_config`, ca. Z. 378–407) | Kern der Änderung. Heute: Segment hat irgendeinen Schreib-Indikator UND irgendein Nicht-Flag-Token löst auf die Config auf → Block. Ursache von Teil A. |
| `core/hooks/bash_gate.py` (Aufruf Prüfung 1b, ca. Z. 973–981) | `_writes_effective_config(_git_segments(scan_cmd) or [], Path.cwd())`, gilt ohne Workflow, vor dem Git-Schnellweg, Ausweg nur Override-Token. |
| `core/hooks/bash_gate.py` (`WRITE_INDICATORS`, `_has_write_indicator`, `_has_real_redirect`) | Gemeinsamer Schreib-Indikator, wird auch von Prüfung 3b (State-Integrity) benutzt → nicht für #418 verändern, sonst Seiteneffekt auf 3b. `sed\s+-i` trifft `--in-place`/`-ni` nicht, `perl -pi`, `>|`, `git checkout/restore`, `ln` fehlen. |
| `core/hooks/bash_gate.py` (`_cd_into_claude`, `_cd_context_protected`, `_dir_token_in_cd_context`) | Bestehendes Muster für cd-Nachführung über Segmente (nur `.claude`-Kontext, kein Pfad-Tracking). Vorlage für Teil C. |
| `core/hooks/hook_utils.py` (`_git_lex`, `_git_segments`, `_is_git_redirect`) | Lexer: Trenner als eigene Token, Umleitungen (`>`, `>>`, `>|`, `&>`) als eigene Token; Segmente ohne Trenner. Grundlage für Zielerkennung. |
| `core/hooks/secret_egress_guard.py` (`_shell_write_targets`, Z. 326) | Existierende Ziel-Extraktion (Umleitung + `tee`), bewusst parallele Kopie statt Import. Kandidat für Wiederverwendung / gemeinsamen Helfer mit #417. |
| `tests/test_bash_gate_state_integrity_410.py` | Muster: echtes Gate als Subprozess, Sandbox mit/ohne Workflow, echter Worktree (`_worktree_sandbox`), Override-Token, Abweichungen sammeln. AC-4 bis AC-7 dürfen nicht kippen. |
| `docs/specs/fix-410-state-integrity-gaps.md` | Known Limitations nennen F001/F002 als Folgearbeit; Abgrenzung zu #416 (Quelle) und #417 (Hauptordner allgemein). |
| `docs/artifacts/fix-410-state-integrity-gaps/adversary-dialog.md` | Befunde F001–F003 mit den Beispielbefehlen. |

## Existing Patterns
- Subprozess-Tests gegen das echte Gate, je Fehlerrichtung, Abweichungen gesammelt.
- Fail-open bei nicht zerlegbarem Befehl (`_git_segments` → None → `[]`).
- Freitext-Flags (`-m`, `--body`, …) werden übersprungen (`SECRETS_FREETEXT_FLAGS`).
- cd-Kontext wird segmentweise über `in_claude`-Flag nachgeführt.
- Textprüfung härtet nur versehentliche Schreibweisen; vorsätzliche Umgehung → #416.

## Dependencies
- Upstream: `config_loader.find_config_file(find_project_root())` (wirksame Config; im Worktree die Datei im Hauptordner), `override_token`, `hook_utils`-Lexer.
- Downstream: jeder Bash-Aufruf in allen Konsumenten-Projekten (Prüfung 1b läuft immer, auch ohne Workflow).

## Existing Specs
- `docs/specs/fix-410-state-integrity-gaps.md` (AC-4 bis AC-7 Config-Schutz)
- `docs/specs/fix-407-ln-state-integrity.md` (Verweisbefehle, `_LINK_COMMAND_RE`)

## Risks & Considerations
- **Fehlalarm-Richtung ist teuer:** Prüfung 1b greift ohne Workflow in jedem Projekt; jeder Fehlalarm blockiert normale Arbeit (Ausweg nur „override“).
- **Umbau von „irgendein Argument“ auf „nur Schreibziele“** darf AC-4 (`echo x > cfg`, `sed -i … cfg`, relativ/absolut/`../`, Worktree→Hauptordner) nicht verlieren.
- **Nicht an `WRITE_INDICATORS` drehen**: würde 3b (State-Integrity) mitverändern; Zielerkennung für 1b separat.
- `cp a cfg` vs. `cp cfg backup`: Ziel ist das letzte Nicht-Flag-Argument, außer bei `-t <dir>`.
- `sed`: In-Place-Erkennung über kombinierte Kurzflags (`-ni`, `-i.bak`, `-i ''`) und `--in-place[=SUF]`; Ziele sind alle Dateiargumente nach dem Skript (bzw. nach `-e`/`-f`).
- `git checkout -- <cfg>` / `git restore <cfg>`: Git-Schnellweg kommt erst nach 1b, also sieht 1b sie.
- Teil C überschneidet sich mit #417 (Hauptordner per Bash aus dem Worktree): gleiche Fähigkeit „wohin schreibt der Befehl, relativ zu welchem Verzeichnis“. Gemeinsamer Helfer möglich, #417 aber nicht in diesem Ticket lösen (Scope).
- Variablen, Globs, `bash -c` bleiben außerhalb (#416); fail-open bei nicht auflösbarem `cd`-Ziel (`cd $X`, `cd -`).
- LoC: Subprozess-Tests ~25 Zeilen je Testfunktion (Memory „LoC-Schätzung Subprozess-Tests“); ~15 Beispielbefehle in wenigen parametrisierten Funktionen bündeln.

## Analysis

### Type
Bug (Präzisierung der Prüfung 1b aus #410: Fehlalarm + Durchrutscher)

### Reproduktion (echtes Gate, Subprozess, Sandbox ohne Workflow, 2026-10-10)
Skript: Scratchpad `repro418.py` (importiert Helfer aus `tests/test_bash_gate_state_integrity_410.py`).

| Gruppe | Befehl | heute | soll |
|---|---|---|---|
| A | `git diff openspec.yaml > x.patch`, `grep a openspec.yaml > out.txt`, `cat openspec.yaml > copy`, `cp openspec.yaml backup.yaml`, `cp -t backup/ openspec.yaml` | 2 | 0 |
| A (bereits ok) | `cat openspec.yaml \| tee copy` | 0 | 0 |
| A-Gegenprobe | `echo x > cfg`, `echo x >> cfg`, `sed -i s/a/b/ cfg`, `cp x cfg`, `mv x cfg`, `mv cfg old`, `cat x \| tee cfg`, `truncate -s0 cfg`, `rm cfg` | 2 | 2 |
| B | `sed --in-place`, `sed -ni`, `perl -pi -e`, `echo x >\| cfg`, `git checkout -- cfg`, `git restore cfg`, `ln -sf x cfg`, `install x cfg`, `dd if=x of=cfg`, `yq -i .a=1 cfg`, `ex -s cfg`, `patch cfg x.diff`, `git apply x.diff` | 0 | 2 (siehe Known Limitations) |
| B (bereits ok) | `sed -i.bak s/a/b/ cfg` | 2 | 2 |
| C | `cd docs && sed -i … ../openspec.yaml`, `cd docs; echo x > ../openspec.yaml`, Worktree: `cd ../../.. && sed -i … openspec.yaml` | 0 | 2 |
| C-Spiegelbild (NEU, nicht im Ticket) | `cd docs && sed -i s/a/b/ openspec.yaml` (trifft `docs/openspec.yaml`) | 2 | 0 |
| Gegenprobe | Worktree-Kopie `sed -i … openspec.yaml` im Worktree | 0 | 0 |

### Root Cause
`_writes_effective_config` (bash_gate.py Z. 378–407) prüft zwei unabhängige Dinge pro Segment: (1) hat das Segment IRGENDEINEN Schreib-Indikator (`_has_write_indicator`), (2) löst IRGENDEIN Nicht-Flag-Token gegen `Path.cwd()` auf die Config auf. Daraus folgen alle drei Befunde:
- A: Auch die Lese-QUELLE (`cat cfg > copy`, `cp cfg backup`) erfüllt (2) → Fehlalarm.
- B: (1) kennt viele Schreibformen nicht (`WRITE_INDICATORS` hat `\bsed\s+-i`, kein `--in-place`/`-ni`, kein `perl -i`, kein `git checkout/restore`, kein `ln/install/dd/yq`; `_has_real_redirect` erkennt `>|` nicht, weil `^\d*>{1,2}(.*)$` das `|` als Ziel liest bzw. der Lexer `>|` als eigenes Token liefert).
- C: Basis ist immer `Path.cwd()`, `cd`-Segmente im selben Befehl werden nicht nachgeführt.
(Korrektur zum Bug-Intake-Bericht: Nicht der Operator `>` wird als Datei gelesen, sondern die Quelle.)

### Lexer-Befund (`hook_utils._git_segments`, belegt)
Umleitungsoperatoren sind eigene Token, Ziel = nächstes Token: `>`, `>>`, `>|`, `&>`, `>&`; `2>x` → `'2','>','x'`; `2>&1` → `'2','>&','1'`; `x>cfg` → `'x','>','cfg'`. `sed -i ''` → leeres Token `''`. Segmente sind trennerfrei (`cd docs && …` → zwei Segmente). Zielextraktion aus dem Segment ist damit zuverlässig möglich.

### Recherche (Quellen)
- `sed -i` ist nicht POSIX; GNU: `-i[SUFFIX]` / `--in-place[=SUFFIX]` (Suffix ohne Leerzeichen), BSD/macOS: Suffix Pflicht, `-i ''` für keins. Erkennung muss `-i`, `-i ''`, `-i.bak`, `--in-place[=…]` und Cluster (`-ni`) abdecken. https://blog.geeky-boy.com/2020/11/using-sed-in-place-gnu-vs-bsd.html, https://hackmd.io/@maelvls/bsd-vs-gnu-vs-busybox-incompat
- `>|` schreibt wie `>`, überschreibt auch bei `noclobber` → vollwertiges Schreibziel. https://www.gnu.org/s/bash/manual/html_node/Redirections.html

### Affected Files (with changes)
| File | Change Type | Description |
|------|-------------|-------------|
| `core/hooks/bash_gate.py` | MODIFY | Neue 1b-eigene Zielextraktion `_config_write_targets(seg)`; `_writes_effective_config` vergleicht nur noch Schreibziele, führt `cd`/`pushd`-Basis nach |
| `tests/test_bash_gate_config_lock_418.py` | CREATE | Subprozess-Tests gegen das echte Gate: A frei, B blockt, C blockt + Spiegelbild frei, Regressionsgegenprobe; Sandbox-Helfer aus `test_bash_gate_state_integrity_410.py` importieren |
| `CHANGELOG.md` | MODIFY | Eintrag unter [Unreleased] |
| `docs/specs/fix-418-config-lock-precision.md` | CREATE | Spec (Phase 3) |

Nicht ändern: `WRITE_INDICATORS`, `_has_write_indicator`, `_has_real_redirect` (von 3a/3b mitbenutzt → Seiteneffekt), `hook_utils.py` (Lexer korrekt), `secret_egress_guard.py` (eigene Kopie bleibt; gemeinsamer Helfer erst mit #417).

### Scope Assessment
- Files: 3 Code/Test + Spec (Spec/Kontext zählen im LoC-Gate mit, Memory „LoC-Gate zählt Workflow-Docs als Code“, #294)
- Estimated LoC: bash_gate.py +100/-15; Tests +130–150 (realistisch nach #410-Erfahrung: ~25 Zeilen je Subprozess-Testfunktion, 5 Funktionen + Helfer); CHANGELOG +5 → ca. 250–270, knapp an/über der 250-Grenze
- Schnittreserve, falls drüber: zuerst `dd`/`yq`/`patch`/`ex`-Zweige samt Testfällen streichen (~25 LoC), dann `pushd`.
- Risk Level: MEDIUM — Prüfung 1b läuft ohne Workflow in jedem Konsumenten-Projekt vor dem Git-Schnellweg; jeder neue Fehlalarm blockiert normale Arbeit (Ausweg nur „override“).

### Technical Approach (Empfehlung)
Zielbasierte Prüfung statt „Indikator + irgendein Token“:
1. `_config_write_targets(seg) -> list[str]`, nur für 1b:
   - Umleitung (jedes Kommando): Token nach `>`, `>>`, `>|`, `&>`, `>&` (außer Ziffer, `-`, `/dev/null`).
   - Kommandowort = erstes Token nach Präfixen (`sudo`, `command`, `env`, `VAR=x`):
     - `cp`, `install`, `ln`: letztes Nicht-Flag-Argument; bei `-t DIR` bzw. `--target-directory=DIR`: `DIR/<basename je Quelle>`.
     - `mv`: alle Nicht-Flag-Argumente (Quelle verschwindet auch).
     - `rm`, `unlink`, `truncate`, `touch`, `tee`: alle Nicht-Flag-Argumente.
     - `sed`: nur bei In-Place (Kurzflag-Cluster mit `i`, `--in-place[=…]`); ohne `-e`/`-f` ist das erste Nicht-Flag-Token das Skript, danach alle Dateien. Leeres Token (`-i ''`) ignorieren.
     - `perl`: nur mit `-i`-Cluster (`-pi`, `-i.bak`); Skript über `-e`, Rest Dateien.
     - `dd`: `of=X`. `yq`: nur mit `-i`, alle Nicht-Flag-Token als Kandidaten.
     - `git checkout`, `git restore`: alle Pfadargumente (nur Treffer auf die Config zählen, Branchnamen lösen nicht auf).
     - `patch`: Nicht-Flag-Token.
   - Tokens nach `SECRETS_FREETEXT_FLAGS` überspringen (wie bisher).
2. `cd`-Nachführung: `base = cwd`; Segment `cd <pfad>`/`pushd <pfad>` → `base = (base/pfad).resolve()` (`~` per `expanduser`). Nicht auflösbar (`cd $X`, `cd -`, `cd` ohne Argument, Glob/Backtick) → Folgesegmente gegen alte Basis UND `cwd` prüfen, kein neuer Block-Grund (erhält heutiges Verhalten).
3. Fail-open bleibt: nicht zerlegbar → `[]`, Exception → False. Leeres Token vor `resolve()` filtern (sonst trifft `''` die Basis).
4. Regel vor Modell: rein deterministisch, kein Modell beteiligt.

### Alternativen (bewertet, nicht empfohlen)
- **Prüfung an der Wirkung (PostToolUse, Hash/mtime der Config):** präzise, aber meldet erst nach dem Schreiben (Revert nötig), neuer Hook + State; kippt die #410-ADR „präventiv blocken, Ausweg Override-Token“. Gehört eher zu #416 (Prüfung an der Quelle).
- **Config per `chmod` schreibschützen:** kippt die Entscheidung, dass Gates keine Dateirechte in Konsumenten-Projekten verändern; kollidiert mit legitimem Editieren durch den User.
- **Nur A + C jetzt, B als Folgeticket:** kleinerer Schnitt, aber B ist der eigentliche Sicherheitsgewinn und fällt in dieselbe Zielextraktion fast kostenlos mit an. Bleibt Rückfalloption, falls die Schnittreserve nicht reicht.

### Known Limitations (für die Spec)
- `git apply x.diff`, `patch < x.diff` ohne Pfad: Ziel steht nur im Diff.
- `ex -s cfg` / `vim -c` mit stdin-Skript: selten, nicht versehentlich.
- `cd` in Subshells `( … )` und `||`-Zweigen: linear nachgeführt, nicht zweiggenau.
- Variablen, Globs, `bash -c`, `eval` → #416; Hauptordner allgemein aus dem Worktree → #417.

### Dependencies
- Upstream: `config_loader.find_config_file(find_project_root())`, `hook_utils._git_segments`, `SECRETS_FREETEXT_FLAGS`, `_any_override_token`.
- Downstream: jeder Bash-Aufruf in allen Konsumenten-Projekten (1b ohne Workflow, vor Git-Schnellweg).
- Bestehende Tests, die grün bleiben müssen: `tests/test_bash_gate_state_integrity_410.py` (AC-4 bis AC-7: `test_wirksame_config_schreiben_blockt`, `test_config_schutz_ohne_aktiven_workflow`, `test_override_gibt_config_frei_aber_nicht_state`, `test_worktree_kopie_lesen_und_app_config_bleiben_frei`), dazu das Regressionsnetz `tests/test_bash_gate*`.

### Open Questions
- Keine PO-Fragen. Scope-Grenze: Liegt die Schätzung beim Spec-Schreiben über 250 LoC, wird zuerst die Schnittreserve (dd/yq/patch) gezogen; reicht das nicht, Rückfrage an Henning mit konkreter Zahl.
