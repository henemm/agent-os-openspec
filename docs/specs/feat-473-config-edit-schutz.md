---
entity_id: feat-473-config-edit-schutz
type: feature
created: 2026-10-28
updated: 2026-10-28
status: draft
version: "1.0"
workflow: feat-473-config-edit-schutz
tags: [config, gate, edit-gate, bash-gate, autonomie]
---

# Config-Edit-Schutz: Edit/Write/MultiEdit und neue vorrangige Config (Issue #473)

## Approval

- [ ] Approved

## Purpose

Die wirksame Gate-Config (Kill-Switches, `autonomy.mode`) ist heute nur gegen Bash-Schreibzugriffe geschuetzt (`bash_gate._writes_effective_config`, #410/#418); ueber Edit/Write/MultiEdit laesst sie sich ohne Hindernis aendern, und auch eine neu angelegte, vorrangige Config-Datei (z. B. `openspec.yaml` neben einer wirksamen `.claude/openspec.yaml`) uebersteuert die bisherige still. Im Auto-Modus (#470) koennte ein Agent so `autonomy.mode: auto` selbst setzen (Adversary-Fund F011 aus #470). Diese Aenderung schliesst beide Luecken ueber eine gemeinsame Pfadmenge fuer `edit_gate.py` und `bash_gate.py` und muss vor der Nutzung des Auto-Modus gelten.

## Source

- **File:** `core/hooks/config_loader.py`
- **Identifier:** `protected_config_paths`, `is_plugin_config_text`, `edit_gate.main` (neuer Schritt 0a), `edit_gate._config_edit_hit`, `bash_gate._writes_effective_config`

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `core/hooks/config_loader.py` | module | `CONFIG_NAMES`, `_find_config_file`/`find_config_file`, `is_plugin_config`, `_is_root_app_config` (#372): Quelle der Suchreihenfolge; hier entsteht der neue Helfer |
| `core/hooks/hook_utils.py` | module | `find_project_root()` (vertrauenswuerdige Wurzel, im Worktree das Haupt-Repo), `get_tool_input`, `block`, `framework_disabled` |
| `core/hooks/edit_gate.py` | module | Kern-Gate Edit/Write/MultiEdit; `_apply_spec_edit`/`_spec_edit_variants` (Simulation des neuen Inhalts, #439) und `_has_override_token` werden wiederverwendet |
| `core/hooks/bash_gate.py` | module | `_writes_effective_config`, `_segment_write_targets`, Schritt 1b (Override-Token-Ausweg) |
| `core/hooks/override_token.py` | module | `has_valid_token` als einziger Ausweg |
| `tests/test_bash_gate_config_lock_418.py`, `tests/test_bash_gate_state_integrity_410.py` | test | Bestehende Config-Lock-Tests muessen gruen bleiben; Sandbox-Helfer (`_sandbox_ohne_workflow`, `_worktree_sandbox`, `PLUGIN_CONFIG`) werden wiederverwendet |
| `docs/context/feat-473-config-edit-schutz.md` | doc | Kontext und Analyse zu #473 |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| core/hooks/config_loader.py | MODIFY | Neu: `protected_config_paths(root, new_content=None)` und `is_plugin_config_text(text)`; `is_plugin_config` delegiert an letzteres |
| core/hooks/edit_gate.py | MODIFY | Neuer Schritt 0a (vor dem `framework_disabled`-Schnellweg): Ziel gegen die geschuetzte Pfadmenge pruefen, Ausweg Override-Token; Inhalts-Simulation fuer Root-`config.yaml` ohne Plugin-Block |
| core/hooks/bash_gate.py | MODIFY | `_writes_effective_config` vergleicht gegen `protected_config_paths(find_project_root())` statt nur gegen die wirksame Datei; Meldung 1b um das Anlegen erweitert |
| tests/test_config_edit_schutz_473.py | CREATE | Tests zu allen Acceptance Criteria (Gate als Subprozess) |
| CHANGELOG.md | MODIFY | Eintrag unter [Unreleased] |

### Estimated Changes

- Files: 1 neu, 4 geaendert
- LoC: +90 Produktion / +300 Test

## Implementation Details

**Ort des Helfers.** `protected_config_paths` liegt in `config_loader.py`, nicht in `hook_utils.py`: `config_loader` besitzt `CONFIG_NAMES`, die Suchreihenfolge und die #372-Erkennung, und importiert bereits aus `hook_utils`; ein Helfer in `hook_utils` brauchte einen Rueck-Import (Zyklus) oder eine Parallelkopie der Reihenfolge, die beim naechsten Config-Namen driftet. `bash_gate` importiert `find_config_file` schon heute von dort; `edit_gate` zieht den Import lokal im Schritt (wie `bash_gate`), damit ein Importfehler nur diesen Schritt trifft.

**Pfadmenge.** `protected_config_paths(root, new_content=None) -> list[Path]` liefert unter `root` (immer `hook_utils.find_project_root()`, im Worktree das Haupt-Repo) die absoluten, nicht aufgeloesten Kandidatenpfade in Suchreihenfolge (je Name erst `root/<name>`, dann `root/.claude/<name>`; 6 Kandidaten). Aufgenommen werden:

1. die wirksame Datei (`find_config_file(root)`), falls vorhanden;
2. jeder Kandidat, der in der Suchreihenfolge VOR der wirksamen Datei steht (Anlegen wuerde ihn wirksam machen), bzw. alle 6, wenn keine wirksame Datei existiert;
3. Nachrangige Kandidaten (hinter der wirksamen Datei) bleiben frei: sie sind wirkungslos.

**Ausnahme #372.** Der Kandidat `root/config.yaml` (nur dieser, nicht `.claude/config.yaml`) gehoert der App, solange er keinen Plugin-Block hat. Er wird nur aufgenommen, wenn er bereits ein Plugin-Block-Config ist (dann ist er ohnehin wirksam oder vorrangig) oder wenn `new_content` ein String mit Plugin-Block ist (`is_plugin_config_text`, gleiche Schluesselmenge `PLUGIN_CONFIG_KEYS` wie `is_plugin_config`; gemeinsame Funktion, kein zweiter Parser). `new_content=None` heisst "Inhalt unbekannt" und nimmt die App-Config nicht auf. Der Helfer wirft nie nach aussen (Fehler: leere Liste, siehe Fail-open).

**Vergleich.** Ein Ziel trifft, wenn (a) `normpath(abspath(ziel))` einem Kandidaten entspricht, oder (b) `Path(ziel).resolve()` dem aufgeloesten Kandidaten entspricht (Symlink auf die Datei, `..`, Symlink-Ordner, relativer Pfad gegen `Path.cwd()`), oder (c) beide Dateien existieren und `os.path.samefile` wahr ist (Hardlink). Eine Worktree-Kopie hat einen anderen Pfad und andere Inode und trifft nie (Konsistenz mit #410). Ein Ziel ausserhalb des Projekts trifft keinen Kandidaten und bleibt von diesem Schritt unberuehrt.

**edit_gate.** Neuer Schritt 0a in `main()`: `tool_input` und `file_path` werden vor dem `framework_disabled()`-Schnellweg gelesen (Muell-Payload wie bisher: kein String/leer → `allow()`), dann `_config_edit_hit(file_path, tool_input)`. Dieser ermittelt `new_content` (Write: `content`; Edit/MultiEdit: nur fuer die bestehende Root-`config.yaml` ohne Plugin-Block per `_spec_edit_variants` auf dem Dateiinhalt simuliert, jede Variante zaehlt; Simulation scheitert → Edit schlaegt ohnehin fehl → kein Treffer), ruft `protected_config_paths(_root, new_content)` und vergleicht. Bei Treffer: `_has_override_token("__infra__") or _has_override_token()` → weiter, sonst `block(...)` (Exit 2) mit Meldung analog bash_gate 1b ("Schreibzugriff auf die wirksame Gate-Config", Hinweis auf Worktree-Kopie, "User tippt 'override'"). Der Schritt steht VOR 1c ("ausserhalb Projekt"), 2/2b (always-allowed) und 3 ("kein Code"), sonst winkt "`.yaml` ist kein Code" die Datei durch.

**framework_disabled.** Der Schutz gilt auch bei `framework_disabled()` (Config `framework.enabled: false` oder `OPENSPEC_FRAMEWORK=off`) und ohne aktiven Workflow, konsistent mit bash_gate 1b ("Schutz, kein Workflow-Zwang"): wer die Kill-Switches setzt, soll sie nicht ueber den Edit-Weg ohne User-Freigabe aendern koennen. Ausweg ist der Override-Token. Konsequenz: In Projekten mit abgeschaltetem Framework braucht das Anlegen/Aendern der Gate-Config ebenfalls "override".

**bash_gate.** `_writes_effective_config` ersetzt die Einzelpruefung `== effective` durch dieselbe Treffer-Funktion gegen `protected_config_paths(find_project_root())` (ohne `new_content`, Shell-Inhalt ist nicht zuverlaessig lesbar). Damit blockt `echo … > openspec.yaml`, wenn `.claude/openspec.yaml` wirksam ist, und jedes Anlegen eines Kandidaten, wenn gar keine Config wirksam ist; das bisherige `found is None → False` entfaellt. Die #418-Zielerkennung (`_segment_write_targets`, `cd`-Nachfuehrung) bleibt unveraendert. Override-Ausweg und Meldung bleiben (Text um "oder Anlegen einer vorrangigen Config" ergaenzt; die #418-Tests pruefen nur Exit-Code und `override`).

**Fail-open.** Jede Ausnahme in der Pfadermittlung (`find_project_root`, `find_config_file`, `resolve`, Import) ergibt in beiden Gates "kein Treffer": der Config-Schritt wird uebersprungen, die uebrigen Gates laufen unveraendert weiter. Ein Fehler darf nie alle Edits blocken (Konsistenz mit #410/bash_gate).

**Nicht betroffen.** `.claude/settings.local.json` bleibt frei (`load_config` liest sie als Override-Quelle, sie ist aber seit #470 im Auto-Pfad wirkungslos und kein Config-Kandidat). Keine Aenderung an `hooks/hooks.json` (Matcher `Edit|Write|MultiEdit` und `Bash` bestehen).

## Expected Behavior

- **Input:** Edit/Write/MultiEdit-Aufruf mit `file_path` bzw. Bash-Befehl mit Schreibziel; Projekt mit oder ohne wirksame Config; ggf. Override-Token
- **Output:** Exit 0 (frei) oder Exit 2 mit Meldung inkl. Override-Hinweis auf stderr
- **Side effects:** Keine. Der Override-Token wird wie bei den bestehenden Schritten (Infrastruktur, bash_gate 1b) geprueft, nicht anders verbraucht.

## Known Limitations

- **Inline-Code per Bash.** `bash_gate` erkennt fuer die Config-Sperre nur Shell-Umleitungen und die Befehle in `_CONFIG_WRITERS` (`cp`, `install`, `ln`, `mv`, `rm`, `unlink`, `tee`, `truncate`, `touch`, `sed -i`, `perl -i`, `git`, `dd of=`, `yq -i`). Schreiben per `python3 -c`, `ruby`, `node`, `awk -i inplace`, `rsync`, `tar -x`, `patch` oder Skriptdatei bleibt fuer die Config unerkannt; die Inline-Code-Erkennung (`_INLINE_WRITE_RE`) gilt nur fuer den Simulator-Beleg (#447/#452). Das ist Bestand seit #410/#418 und wird hier nicht geschlossen.
- **Fremde Schreibwege.** Schreibende Nicht-Datei-Tools (z. B. MCP-Server, die Dateien schreiben) laufen nicht durch `edit_gate`/`bash_gate`.
- **Bash und Root-`config.yaml`.** Bash kennt den Dateiinhalt nicht: Eine Root-`config.yaml` ohne Plugin-Block bleibt per Bash frei, auch wenn der Befehl einen Plugin-Block hineinschreibt (nur relevant, wenn dadurch eine bisher uebergangene App-Config wirksam wuerde). Edit/Write pruefen den Inhalt.
- **Editor-Simulation.** Bei Edit/MultiEdit auf eine App-`config.yaml` wird der neue Inhalt wie in #439 per `str.replace` simuliert; weicht Claude Codes tatsaechliche Anwendung davon ab, gilt die best-effort-Variantenliste (`_spec_edit_variants`).
- **Gross-/Kleinschreibung.** Auf case-insensitiven Dateisystemen (macOS) loest `resolve()` einen abweichend geschriebenen, noch nicht existierenden Namen (`OpenSpec.yaml`) nicht auf den Kandidaten auf; existierende Dateien treffen ueber `samefile`.
- **Framework-Repo selbst.** Das Framework editiert `config.yaml` als Template: im Haupt-Ordner nur mit "override" (wie per Bash heute), in der Worktree-Kopie frei.
- **framework_disabled.** Der Schutz gilt dort weiter (siehe oben); wer das nicht will, setzt die Datei in einer Worktree-Kopie und merged.
- **Shell-Indirektion und Variablen-Pfade (Adversary F003).** `bash -c '...'`, `sh -c '...'`, `eval '...'` sowie Ziele mit Variablen-Expansion (`$PWD/openspec.yaml`, `$HOME/...`, `${X}/...`), Backticks, `$(...)` und Globs (`rm -rf .clau*`) werden von `_segment_write_targets` nicht aufgeloest und bleiben fuer die Config-Sperre unerkannt (Exit 0). Gleiche Klasse wie "Inline-Code per Bash"; nicht in diesem Issue geschlossen.
- **Varianten-Deckel (Adversary F001).** `_spec_edit_variants` dedupliziert und deckelt die simulierten Fassungen bei `_SPEC_VARIANT_CAP` (64). Darueber gilt fail-closed: im Config-Schritt als Treffer (Exit 2, Ausweg "override"), im Spec-Freeze (#439) als "nicht sicher berechenbar" (Block). Ob der Deckel greift, haengt vom Dateiaufbau ab, nicht von einer festen Edit-Zahl: Wachsen die Varianten exponentiell (jede `\n`-Variante eines Loesch-Edits mit leerem `new_string` ergibt eine neue, verschiedene Fassung), ist er schon ab 7 Loesch-Edits erreicht; wachsen sie linear (gleichfoermige Zeilen, Fassungen fallen per Dedup zusammen), bleiben auch 60 eindeutige Loesch-Edits darunter. Ein betroffener MultiEdit muss aufgeteilt oder als Write ausgefuehrt werden.
- **Groessen-/Mengengrenzen und Zeitbudget (Adversary Runde 2, F001).** Der Deckel begrenzte nur die Anzahl der Fassungen, nicht die Laufzeit (Fassungen x Edits x Dateigroesse); ein Hook-Timeout (10 s) blockiert nicht und waere ein Durchlass. Deshalb wird im Config-Schritt fuer die App-`config.yaml` nicht simuliert, sondern fail-closed geblockt (Exit 2, Grund in der Meldung, Ausweg "override"), wenn die bestehende Datei groesser als 256 KiB ist, ein MultiEdit mehr als 20 Edits enthaelt, ein Write-`content` oder eine simulierte Fassung groesser als 256 KiB ist (256 KiB = Probe-Grenze von `is_plugin_config_text`). Zusaetzlich gilt ein Gesamt-Zeitbudget von 3 s (`time.monotonic`) fuer Simulation und Plugin-Block-Pruefung; Ueberschreitung zaehlt als Treffer, im Spec-Freeze (#439) als "nicht sicher berechenbar" (Block). Folge: legitime grosse App-Configs oder grosse MultiEdits darauf brauchen "override" oder kleinere Schritte; auf langsamen Rechnern kann das Budget bei Dateien nahe 256 KiB schon bei wenigen Fassungen greifen (fail-closed). Ein einzelner `str.replace` bzw. YAML-Parse wird nicht unterbrochen; die Groessengrenzen halten ihn kurz.
- **Weitere Loesch-Wege per Bash (Adversary Runde 2, F004).** `git clean -fdx`, `git stash -u`, `find … -delete`, `rm -rf .claude/*` (Glob), `shred` und `tar --remove-files` entfernen bzw. verschieben die geschuetzte Config, ohne von `bash_gate` erkannt zu werden (Exit 0). Gleiche Klasse wie "Inline-Code per Bash" und "Shell-Indirektion"; nicht in diesem Issue geschlossen.
- **Fehlalarm bei Index-Befehlen (Adversary Runde 2, F005).** `git rm --cached -r .claude` und `git restore --staged .claude` aendern nur den Index, nicht die Datei, werden aber wie Loeschen/Wiederherstellen des Ordners geblockt. Ausweg: "override".
- **Ordner mit der Config per Bash (Adversary F002).** `mv`, `rm` und `git rm|mv|checkout|restore` auf einen Ordner innerhalb der Projektwurzel, der eine vorhandene geschuetzte Config enthaelt (`rm -rf .claude`, `mv .claude x`), blocken. Die Projektwurzel selbst bleibt frei (`rm -rf <projekt>`, `git checkout .` sind kein gezielter Kill-Switch-Umweg und wuerden alltaegliche Befehle treffen). Andere Werkzeuge auf den Ordner (`rsync --delete`, `find -delete`, `chmod 000 .claude`) bleiben unerkannt.

## Definition of Done

Fertig ist diese Aenderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] Ein Edit/Write auf die wirksame Config wird im echten Gate mit Exit 2 und dem Hinweis "override" abgelehnt; mit Override-Token geht er durch
- [ ] Das Anlegen einer vorrangigen Config-Datei (per Write oder per `echo … > openspec.yaml`) wird abgelehnt, das Anlegen einer wirkungslosen nachrangigen Datei und die Bearbeitung einer App-`config.yaml` (#372) bleiben frei
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf gruen, insbesondere `test_bash_gate_config_lock_418.py`)

## Acceptance Criteria

- **AC-1:** Given ein Projekt mit wirksamer `root/openspec.yaml` bzw. `root/.claude/openspec.yaml` bzw. Root-`config.yaml` mit Plugin-Block (je eigene Sandbox) / When Write, Edit oder MultiEdit auf diese Datei laeuft / Then endet `edit_gate` mit Exit 2 und die Meldung enthaelt `override`
  - Test: tests/test_config_edit_schutz_473.py::test_edit_write_multiedit_on_effective_config_blocked

- **AC-2:** Given eine wirksame `root/.claude/openspec.yaml` / When Write `root/openspec.yaml` (vorrangig, noch nicht vorhanden) anlegen will / Then Exit 2 mit `override`; ein Write auf `root/.openspec.yaml` oder `root/.claude/.openspec.yaml` (nachrangig, wirkungslos) endet mit Exit 0
  - Test: tests/test_config_edit_schutz_473.py::test_create_higher_priority_blocked_lower_priority_free

- **AC-3:** Given ein Projekt ohne jede wirksame Config / When Write einen der Kandidaten `openspec.yaml`, `.claude/openspec.yaml`, `.claude/config.yaml`, `.openspec.yaml` oder `.claude/.openspec.yaml` anlegen will / Then Exit 2 fuer jeden; Write auf Root-`config.yaml` ohne Plugin-Block bleibt Exit 0, mit Plugin-Block im Inhalt Exit 2
  - Test: tests/test_config_edit_schutz_473.py::test_no_effective_config_creation_of_any_candidate_blocked

- **AC-4:** Given eine App-`config.yaml` im Root ohne Plugin-Block (#372) neben einer wirksamen `.claude/openspec.yaml` / When Edit oder MultiEdit auf die App-`config.yaml` laeuft, der keinen Plugin-Block einfuegt / Then Exit 0
  - Test: tests/test_config_edit_schutz_473.py::test_app_config_edit_without_plugin_block_free

- **AC-5:** Given dieselbe App-`config.yaml` / When Write oder Edit/MultiEdit einen Plugin-Block (z. B. `autonomy:` oder `framework:`) einfuegt / Then Exit 2 mit `override`
  - Test: tests/test_config_edit_schutz_473.py::test_app_config_edit_inserting_plugin_block_blocked

- **AC-6:** Given eine wirksame Config / When das Ziel als relativer Pfad (cwd = Projekt), mit `..`-Umweg, ueber einen Symlink auf die wirksame Datei oder einen Hardlink angegeben wird / Then Exit 2 in allen Faellen
  - Test: tests/test_config_edit_schutz_473.py::test_path_tricks_relative_dotdot_symlink_hardlink_blocked

- **AC-7:** Given eine Worktree-Sitzung, deren Worktree eine eigene Kopie `openspec.yaml` enthaelt / When Edit/Write auf die Worktree-Kopie laeuft / Then Exit 0, waehrend dasselbe auf die wirksame Datei im Haupt-Ordner Exit 2 ergibt
  - Test: tests/test_config_edit_schutz_473.py::test_worktree_copy_free_main_repo_blocked

- **AC-8:** Given eine Datei ausserhalb des Projekts (z. B. `/tmp/.../openspec.yaml` oder `~/.claude/...`) / When Write darauf laeuft / Then verhaelt sich `edit_gate` wie vor dieser Aenderung (Exit 0 bei Pfad ausserhalb, keine Config-Meldung)
  - Test: tests/test_config_edit_schutz_473.py::test_outside_project_unchanged

- **AC-9:** Given ein gueltiger Override-Token / When Edit/Write auf die wirksame Config oder das Anlegen einer vorrangigen Config laeuft / Then Exit 0
  - Test: tests/test_config_edit_schutz_473.py::test_override_token_allows_config_edit

- **AC-10:** Given `framework_disabled()` (Config `framework.enabled: false` bzw. `OPENSPEC_FRAMEWORK=off`) und kein aktiver Workflow / When Edit/Write auf die wirksame Config laeuft / Then Exit 2 (Schutz gilt wie bei bash_gate 1b), mit Override-Token Exit 0, und ein Edit auf eine beliebige andere Datei bleibt Exit 0
  - Test: tests/test_config_edit_schutz_473.py::test_framework_disabled_still_protects_config

- **AC-11:** Given ein Projekt mit wirksamer `.claude/openspec.yaml` bzw. ohne wirksame Config / When `bash_gate` den Befehl `echo x > openspec.yaml` (Anlegen der vorrangigen Datei) bzw. `echo x > .claude/openspec.yaml` ausfuehrt / Then Exit 2 mit `override`; derselbe Befehl auf eine nachrangige Datei (`echo x > .openspec.yaml` bei wirksamer `openspec.yaml`) Exit 0
  - Test: tests/test_config_edit_schutz_473.py::test_bash_creating_higher_priority_config_blocked

- **AC-12:** Given die bestehenden Tests zur Config-Sperre / When `pytest tests/test_bash_gate_config_lock_418.py tests/test_bash_gate_state_integrity_410.py` laeuft / Then bleiben sie gruen (Lese-Quellen, Langformen, cd-Nachfuehrung, Worktree-Kopie, Override unveraendert)
  - Test: tests/test_config_edit_schutz_473.py::test_existing_bash_config_lock_suites_still_green

- **AC-13:** Given `.claude/settings.local.json` / When Write oder Edit darauf laeuft / Then Exit 0 durch den Config-Schritt (kein Treffer in `protected_config_paths`)
  - Test: tests/test_config_edit_schutz_473.py::test_settings_local_json_stays_free

- **AC-14:** Given eine Ausnahme in der Pfadermittlung (`find_config_file` bzw. `protected_config_paths` wirft, per Monkeypatch/Env-Praeparierung im Subprozess) / When Edit/Write auf eine beliebige Datei laeuft / Then ueberspringt der Config-Schritt (kein Totalblock) und das Gate entscheidet wie bisher; `protected_config_paths` selbst wirft nie
  - Test: tests/test_config_edit_schutz_473.py::test_path_resolution_error_fails_open

- **AC-15:** Given `protected_config_paths(root, new_content)` direkt aufgerufen / When wirksame Datei, Anlegen-Kandidaten, App-Config mit und ohne Plugin-Block im `new_content` sowie `new_content=None` durchgespielt werden / Then liefert sie genau die in "Implementation Details" beschriebene Menge in Suchreihenfolge (nachrangige Kandidaten fehlen)
  - Test: tests/test_config_edit_schutz_473.py::test_protected_config_paths_set

- **AC-16:** Given die bestehende Testsuite / When `pytest tests/` laeuft / Then bleiben alle vor dieser Aenderung gruenen Tests gruen
  - Test: tests/test_config_edit_schutz_473.py::test_existing_edit_gate_suites_still_green

## Test Plan

Automatische Tests (jeweils an eine AC oben gebunden); `edit_gate.py` und `bash_gate.py` laufen als Subprozess in temporaeren Sandboxes (Helfer aus `test_bash_gate_state_integrity_410.py`), Eingabe ueber den JSON-Payload (`tool_name`, `tool_input`):

- `pytest tests/test_config_edit_schutz_473.py`
- Config-Lock-Regression: `pytest tests/test_bash_gate_config_lock_418.py tests/test_bash_gate_state_integrity_410.py`
- Edit-Gate-Regression: `pytest tests/ -k "edit_gate"`
- Gesamtlauf: `pytest tests/`
- Syntaxpruefung: `python3 -m py_compile core/hooks/config_loader.py core/hooks/edit_gate.py core/hooks/bash_gate.py`

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Die Aenderung wendet das bestehende Schutzmuster aus #410/#418 (Schreibschutz der wirksamen Config mit Override-Token als einzigem Ausweg) auf den bisher offenen Edit-Weg und auf das Anlegen vorrangiger Dateien an, ohne neue Konzepte, ohne neuen Hook, ohne Config-Schluessel und ohne Migrationspfad. Der gemeinsame Helfer liegt dort, wo die Suchreihenfolge schon definiert ist; die Entscheidung "Schutz gilt auch bei framework_disabled" folgt dem bash_gate-Vorbild und ist hier dokumentiert, eine eigene ADR braucht es dafuer nicht.

## Changelog

- 2026-10-28: Initial spec created
