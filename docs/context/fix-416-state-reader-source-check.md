# Context: fix-416-state-reader-source-check

## Request Summary
Issue #416 (ausgegliedert aus #410, Teil 3): Workflow-State soll nur gelesen werden, wenn er nachweislich
eine eigene, normale Datei ist (`S_ISREG`, `st_nlink == 1`, kein Symlink in der Pfadkette). Eine gemeinsame
Lesefunktion in `hook_utils`, alle Leser darauf umstellen, bei Fund blocken mit klarer Meldung statt still
ignorieren. Damit schließt sich F004 aus #410 (Textprüfung in `bash_gate` 3b kann Verweise über
`xargs ln`, `find -exec ln`, `python3 -c 'os.link(...)'`, `tar -C`, `cd .claude && ln -s` nicht vollständig
erfassen).

## Bedrohungsmodell (aus #407/#410)
1. **Harter Verweis von außen:** `ln .claude/workflows/<wf>.json docs/x.txt`, dann `echo '{…VERIFIED…}' > docs/x.txt`
   → State gefälscht, ohne dass ein Befehl den State-Pfad als Schreibziel nennt.
2. **Weicher Verweis auf den State:** `.claude/workflows/<wf>.json` (oder der ganze Ordner `.claude/workflows`)
   wird durch einen Symlink auf eine frei schreibbare Datei ersetzt.
3. **Weicher Verweis von außen:** `ln -s .claude/workflows docs/w` — Schreiben über `docs/w/<wf>.json`.
   Lesen über den echten Pfad zeigt hier KEINEN Link (Ziel ist normale Datei, nlink 1) → an der Quelle nicht
   erkennbar. Bleibt Sache der Textprüfung (#407 deckt den Ordner-Fall ab).

## Leser-Liste (vollständig, Explore-Agent 2026-10-10)

### Workflow-JSON (`.claude/workflows/<name>.json`, `_archive/`)
| file:line | Funktion | Fehlerverhalten | Aufrufer |
|---|---|---|---|
| workflow.py:331 | `_read_workflow` (+ Alias `_read_workflow_file` :300) | raise | zentral |
| workflow.py:360 | `_read_active` | raise / exit 1 | CLI |
| workflow.py:410 | `read_active_workflow_fast` | raise | tdd_enforcement:252, post_implementation_gate:124 (dort `except → allow()`, fail-open), qa_gate (`write_qa_run_stamp`) |
| workflow.py:1800/1867/1909/1980/2088 | `cmd_list`/`cmd_find`/`cmd_retro_list`/`cmd_retro`/`cmd_cleanup_stale_locks` | raise (2088: pass) | CLI |
| edit_gate.py:158, 164 | `_read_active_workflow` (inkl. `_archive`) | `None` → fail-open | PreToolUse Edit |
| edit_gate.py:181 | `_find_workflow_for_file` (glob) | Datei übersprungen | PreToolUse Edit |
| edit_gate.py:256, 266 | `_find_workflow_by_spec_file` | übersprungen / `None` | PreToolUse Edit |
| edit_gate.py:502 | LoC-Delta (read-modify-write) | pass | PreToolUse Edit |
| bash_gate.py:738 | `_read_active_workflow` | `None` | PreToolUse Bash |
| bash_gate.py:848 | `_write_e2e_scope` (RMW) | pass | PreToolUse Bash |
| post_bash.py:137 | `_record_test_run` (RMW) | pass | PostToolUse Bash |
| phase_listener.py:350 | `_read_active_workflow` | `(None, None)` | UserPromptSubmit |
| footer_gate.py:154 | `_expected_command` | `None`, fail-open Pflicht | Stop |
| adversary_dialog.py:947/1017/1347 | Fast-Track-Check / Metriken / `required-files` | False / Warnung / exit 1 | CLI + Import |
| session_singleton_guard.py:324 | `_read_workflow_phase` | `None` | SessionStart / PreToolUse |
| migrate_state.py:33, 41 | Migration v2→v3 | raise | CLI (Altbestand) |

### Marker für den aktiven Namen
- hook_utils.py:1460/1485 `resolve_active_workflow` — `.claude/active_workflow` (Worktree/Root), OSError → pass
- hook_utils.py:1469/1493 — `settings.local.json` env-Section; workflow.py:480/522 (RMW)

### Weitere Zustandsdateien (nicht Kern von #416, aber gleiche Angriffsfläche)
Override-Token (`override_token.py:37`, `phase_listener.py:371`), Stop-Lock (`edit_gate.py:349`,
`bash_gate.py:197`), Pending-Validation-Lock (`hook_utils.py:1400`), Approval-Marker
(`post_implementation_gate.py:164`), Footer-State (`footer_gate.py:88`), Session-Locks
(`session_singleton_guard.py:173/547/615/723`, `workflow.py:2129`).

## Existing Patterns
- `qa_gate.py:541-546` (#345): `os.open(…, O_NOFOLLOW)` + `os.fstat` + `S_ISREG`/`st_nlink != 1` → Abbruch mit Meldung. Vorbild für die Prüfung, aber nur für das letzte Pfadglied (O_NOFOLLOW prüft keine Eltern-Ordner).
- Pfadwurzel uneinheitlich: edit_gate, bash_gate, post_bash, phase_listener nutzen modulweites `_root`, der Rest `find_project_root()`.
- Shared-Helfer heute: `hook_utils.resolve_active_workflow` (:1418), `_workflow_file_exists` (:1410), `pending_validation_lock_path` (:1390), `approval_marker_path` (:1405). **Kein** Helfer in hook_utils liest die Workflow-JSON; nur workflow.py (und darüber tdd_enforcement, post_implementation_gate, qa_gate) nutzt `_read_workflow`.
- Hook-Bootstrap über `hook_utils.block()` (Exit 2, stderr an Claude).

## Writers (relevant für die Lebensdauer eines Verweises)
- Atomar per tempfile + `os.rename` (neuer Inode, bricht harte Verweise und ersetzt einen Symlink durch eine normale Datei): workflow.py `_atomic_write` (:314), edit_gate.py:505, bash_gate.py:850, post_bash.py:120.
- **In-place per `write_text`** (folgt Symlinks, behält Inode, harter Verweis bleibt wirksam): phase_listener.py:358 `_save_workflow` (Workflow-JSON!), :380 Token, :419 Stop-Lock, :600 Approval-Marker; override_token.py:60; footer_gate.py:118; post_implementation_gate.py:77; session_singleton_guard.py:529/589/628/804; migrate_state.py:80.

## Dependencies
- Upstream: `os`, `stat`, `json`, `pathlib`; `hook_utils.find_project_root`, `resolve_active_workflow`.
- Downstream: alle vier Kern-Gates, tdd_enforcement, post_implementation_gate, footer_gate, session_singleton_guard, qa_gate, adversary_dialog, workflow.py-CLI. Läuft bei jedem Werkzeugaufruf in jedem Konsumentenprojekt.

## Existing Specs
- `docs/specs/fix-407-ln-state-integrity.md` — Textprüfung für `ln`/`link`/Ordner-Operationen.
- `docs/specs/fix-410-state-integrity-gaps.md:89` — Known Limitation F004, verweist auf #416.
- Adversary-Protokoll #410: `docs/artifacts/fix-410-state-integrity-gaps/adversary-dialog.md`.

## Recherche (2026-10-10)
- CERT POS01-C: Verweise beim Öffnen prüfen; Dateien mit `st_nlink > 1` verweigern, weil Original und Angreifer-Link ununterscheidbar sind. https://wiki.sei.cmu.edu/confluence/spaces/c/pages/87152372/POS01-C.+Check+for+the+existence+of+links+when+dealing+with+files
- CERT POS35-C: TOCTOU vermeiden — `lstat` vor, `fstat` nach dem Öffnen, `st_dev`/`st_ino` vergleichen; `O_NOFOLLOW` verhindert das Folgen nur im letzten Glied. https://wiki.sei.cmu.edu/confluence/spaces/c/pages/87152082/POS35-C.+Avoid+race+conditions+while+checking+for+the+existence+of+a+symbolic+link
- Grenze der nlink-Prüfung: Wird der Verweis nach dem Schreiben wieder gelöscht, fällt `st_nlink` auf 1 zurück — der gefälschte Inhalt bleibt unerkannt.

## Risks & Considerations
1. **Schutzlücke "Link anlegen, schreiben, Link löschen":** Die Leseprüfung erkennt nur Verweise, die zum Lesezeitpunkt noch existieren. `ln state docs/x; echo … > docs/x; rm docs/x` hinterlässt eine normale Datei mit nlink 1 und gefälschtem Inhalt. Ehrlich als Known Limitation benennen; echte Alternative wäre eine Inhaltsbindung (z. B. Prüfsumme pro Schreibvorgang außerhalb der Reichweite von Bash) oder atomares Schreiben durch alle Writer (bricht Links bei jedem Hook-Schreibvorgang).
2. **Unmittelbares Schreiben ohne Link ist ohnehin möglich:** `python3 -c "open('.claude/'+'workflows/x.json','w')…"` umgeht die Textprüfung ganz ohne Verweis. #416 schließt also nur die Link-Klasse, nicht "State fälschen per Bash" insgesamt.
3. **Fail-open vs. blocken:** footer_gate und post_implementation_gate müssen bei Fehlern durchlassen; "blocken mit Meldung" muss pro Leser entschieden werden (PreToolUse: Exit 2; Stop/UPS: Meldung ohne Sperre?).
4. **Blast Radius:** Lesefunktion läuft bei jedem Werkzeugaufruf. Fehlalarm (z. B. Backup-Tools, Time Machine, `cp -l`, Dateisysteme ohne nlink-Semantik, macOS-APFS-Klone) sperrt alle Projekte.
5. **phase_listener schreibt in-place** — ein Symlink anstelle der State-Datei wird beim nächsten Phasenwechsel beschrieben (Ziel außerhalb). Ggf. Writer auf `_atomic_write` umstellen.
6. **Umfang:** ~10 Leser-Dateien über dem Limit 4–5 Dateien; PO hat ein Ticket bestätigt (Intake 2026-10-10). Weitere Zustandsdateien (Token, Stop-Lock, Marker) nur einbeziehen, wenn das Ziel es verlangt — sonst eigenes Ticket.
7. **Eltern-Symlink:** `.claude/workflows` selbst als Symlink → O_NOFOLLOW greift nicht; Pfadkette ab Projektwurzel per `lstat` prüfen (Worktree-Pfade unter `.claude/worktrees/` beachten; Projektwurzel selbst kann legitim hinter einem Symlink liegen, z. B. `/tmp` → `/private/tmp` auf macOS).

## Analysis

### Type
Bug (Sicherheitslücke in der Gate-Kette)

### Reproduktion (2026-10-10, Wegwerf-Projekte im Scratchpad, Skript `repro416.sh`)
Drei Varianten, jeweils gefälschter Inhalt `phase7_validate` + `adversary_verdict: VERIFIED`:
- harter Verweis (`ln <state> docs/x.txt`, Schreiben in `docs/x.txt`)
- Symlink anstelle der State-Datei
- Symlink anstelle des Ordners `.claude/workflows`

Ergebnis in allen drei: `workflow.py status` → „Phase: Validation“, `read_active_workflow_fast()` → `VERIFIED`, keine Warnung.
Ursache: `workflow.py:330 _read_workflow` = `json.loads(path.read_text())`, alle übrigen Leser ebenfalls ungeprüft (Leser-Liste oben, vom Bug-Intake-Agenten bestätigt, kein weiterer Leser gefunden).

### Affected Files (with changes)
| File | Change Type | Description |
|------|-------------|-------------|
| core/hooks/hook_utils.py | MODIFY | `read_state_json(path, root)` + `UnsafeStateError(Exception)` (erbt NICHT von OSError/ValueError) + `atomic_write_json` |
| core/hooks/workflow.py | MODIFY | `_read_workflow`, `_read_active`, `read_active_workflow_fast` über gemeinsame Funktion; CLI exit 1 mit Meldung; `_atomic_write` delegiert an hook_utils |
| core/hooks/edit_gate.py | MODIFY | 5 Lesestellen (:158/164/181/256/266/502); unsicher → Code-Edit blocken, Always-Allowed unverändert |
| core/hooks/bash_gate.py | MODIFY | :738, :848 RMW; unsicher → nur state-abhängige Freigaben (Commit-Gate) verweigern, gewöhnliche Befehle laufen |
| core/hooks/post_bash.py | MODIFY | :137 RMW über sicheren Leser (sonst wird die Fälschung atomar „gewaschen“) |
| core/hooks/phase_listener.py | MODIFY | :350 Leser fail-open mit Warnung, kein Phasenwechsel/keine Freigabe; :358 `_save_workflow` atomar |
| core/hooks/footer_gate.py | MODIFY | :154 fail-open mit Warnung |
| core/hooks/adversary_dialog.py | MODIFY | :947 Fast-Track (gewährt Freigabe), :1017, :1347 |
| core/hooks/session_singleton_guard.py | MODIFY | :324 informativ, über gemeinsame Funktion, bei Fund `None` (DoD „jeder Leser“) |
| tests/test_state_reader_source_416.py | CREATE | je Leser: hart / Symlink-Datei / Symlink-Ordner / Normalfall, parametrisiert |
| docs/specs/fix-410-state-integrity-gaps.md | MODIFY | F004 aufgelöst, Verweis auf #416 |
| CHANGELOG.md | MODIFY | [Unreleased] |

tdd_enforcement und post_implementation_gate ziehen über `read_active_workflow_fast` automatisch mit (post_implementation_gate bleibt fail-open, Warnung).

### Scope Assessment
- Dateien: ~9 Code + 1 Test + 2 Doku
- Geschätzte LoC: Code ~+190/-40, Tests ~+230 → gesamt ~460 (Limit ±250)
- Risk Level: HIGH — läuft bei jedem Werkzeugaufruf in jedem Konsumentenprojekt; Fehlalarm sperrt Code-Edits

### Technical Approach (Empfehlung)
1. **Prüfung an der Quelle per dir_fd-Walk** (TOCTOU-frei, CERT POS01-C/POS35-C): `os.open(root, O_DIRECTORY)`, dann `.claude`, `workflows` (ggf. `_archive`) je mit `O_NOFOLLOW|O_DIRECTORY, dir_fd=`; Datei mit `O_RDONLY|O_NOFOLLOW|O_NONBLOCK`; `fstat` → `S_ISREG` und `st_nlink == 1`; Lesen über denselben fd. `ELOOP`/`ENOTDIR` → `UnsafeStateError(pfad, grund)`. Fehlende Datei / kaputtes JSON verhalten sich wie heute.
2. **Wurzel**: die Wurzel, die der Aufrufer schon nutzt (`_root` / `find_project_root()`), per `realpath` aufgelöst und vertrauenswürdig (deckt `/tmp`→`/private/tmp`). Geprüft wird ab `.claude` abwärts; auch `.claude` als Symlink wird abgelehnt.
3. **Verhalten bei Fund: „kein vertrauenswürdiger State = keine Freigabe“**, nicht „kein Workflow“ (None bedeutet heute teils fail-open → eigenes Signal nötig):
   - edit_gate, tdd_enforcement: Code-Edit blocken (Exit 2) mit Meldung (Pfad, Grund, nlink).
   - bash_gate: nur Commit-Gate/state-abhängige Freigaben verweigern; übrige Bash-Befehle laufen, damit der Zustand bereinigt werden kann (keine Aussperrung).
   - phase_listener, footer_gate, post_implementation_gate: fail-open mit Warnung, nie Exit 2; phase_listener schreibt keinen Phasenwechsel und keine Freigabe.
   - workflow.py-CLI: exit 1 mit Meldung.
4. **Keine Reparatur durch Kopieren** (würde die Fälschung legalisieren). Bereinigung: Verweis/State entfernen und Workflow frisch starten; die Meldung nennt den Pfad.
5. **Writer**: phase_listener `_save_workflow` atomar; RMW-Stellen (edit_gate :502, bash_gate :848, post_bash :137) zwingend über den sicheren Leser.

### Alternativen (bewertet)
- **A — nur zentrale Leser** (workflow.py + edit_gate + bash_gate, ~5 Dateien, im Limit): post_bash/adversary_dialog/RMW lesen weiter ungeprüft und schreiben die Fälschung atomar als echte Datei zurück → DoD „jeder Leser“ nicht erfüllt. Verworfen.
- **B — Inhaltsbindung per Prüfsumme/HMAC**: würde auch „Link löschen“ schließen, aber Schlüssel/Prüfsummen liegen in Reichweite derselben Bash → Scheinsicherheit, neues Format + Migration. Verworfen.
- **C — nur atomare Writer**: bricht Hardlinks beim nächsten Hook-Schreiben, aber die Fälschung wird vorher gelesen. Ergänzung (Teil 5), kein Ersatz.

### Known Limitations (für die Spec)
- „Link anlegen, schreiben, Link löschen“ → nlink wieder 1, Fälschung unerkennbar.
- Direktes Schreiben ohne Link (`python3 -c` mit zusammengesetztem Pfad) bleibt Sache der Textprüfung.
- Symlink von außen auf den Ordner (`ln -s .claude/workflows docs/w`) ist beim Lesen nicht erkennbar (#407 Textprüfung).
- Fehlalarmquellen (selten): `cp -l`/`rsync --link-dest` aus dem Live-Ordner, `.claude` als Dotfile-Symlink. APFS-Klone und Time Machine lösen nicht aus.

### Bewusst nicht im Scope (Folgeticket, gleiche Angriffsfläche)
migrate_state.py (Altbestand), Marker `active_workflow`/`settings.local.json` (wählen nur den Namen, State wird danach geprüft gelesen), Override-Token, Stop-Lock, Pending-Lock, Approval-Marker, Footer-State, Session-Locks.

### Open Questions
- [x] Scope ~460 LoC über ±250-Limit: PO hat am 2026-10-10 ein Ticket bestätigt (keine Teilung).
