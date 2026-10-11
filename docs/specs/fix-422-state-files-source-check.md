---
entity_id: fix-422-state-files-source-check
type: bugfix
created: 2026-10-11
updated: 2026-10-11
status: draft
workflow: fix-422-state-files-source-check
version: "1.0"
tags: [state-integrity, hook-utils, symlink, hardlink, override-token, stop-lock, fail-open]
test_targets: ["tests/test_state_files_source_422.py"]
---

# Weitere Zustandsdateien an der Quelle prüfen: Token, Sperren, Marker, Session-Locks — #422

## Approval

- [ ] Approved

## GitHub Issue

- **Issue:** #422 (Folge aus #416, dort unter „Bewusst nicht im Scope“ benannt). Die Config-Sperre (#418) und der allgemeine Bash-Schreibzugriff aufs Hauptrepo (#417) sind nicht Teil dieser Spec.

## Purpose

#416 hat den Workflow-State an der Quelle abgesichert: Er wird nur gelesen, wenn er eine eigene, normale Datei ist. Die übrigen Zustandsdateien der Gate-Kette lesen und schreiben weiterhin ungeprüft. Reproduziert (2026-10-11, Wegwerf-Sandbox, echte Funktionen): Eine Token-Datei als Symlink oder harter Verweis auf eine fremde Datei mit gültigem Token lässt `override_token.has_valid_token` den Wert `True` liefern, also eine Freigabe aus gefälschtem Inhalt. `override_token._save_tokens` schreibt durch einen Symlink hindurch in die fremde Zieldatei. Ein hängender Symlink als `stop_lock.json` ergibt `edit_gate._is_stop_locked() == False`: die Sperre fällt weg, weil „kaputt“ heute „nicht gesperrt“ heißt.

Diese Spec überträgt die #416-Prüfung auf alle übrigen Zustandsdateien: Lesen nur, wenn die Datei nachweislich eine eigene, normale Datei ist (kein Symlink in der Kette ab Wurzel, `S_ISREG`, `st_nlink == 1`). Bei Fund gilt je Datei die sichere Richtung: freigebende Dateien geben nichts frei, sperrende Sperren bleiben wirksam. Die Schreiber werden atomar (neuer Inode, auch die Ordnerkette wird geprüft), damit nie durch einen Verweis in fremde Dateien geschrieben wird. Rein regelbasiert (Dateisystem-Metadaten), ohne Modell, ohne neue Abhängigkeit.

## Source

- **Analyse:** `docs/context/fix-422-state-files-source-check.md` (Abschnitte „Related Files“, „Analysis“, „Verhalten bei Fund je Datei“, „Alternativen“, „Known Limitations“)
- **Ursprungsanfrage:** GitHub-Issue #422
- **Vorbild:** `docs/specs/fix-416-state-reader-source-check.md` und `core/hooks/hook_utils.py` (`read_state_json`, `_open_state_fd`, `UnsafeStateError`, `atomic_write_json`)
- **Recherche:** `os.replace(tmp, ziel)` ersetzt einen Symlink am Ziel und bricht harte Verweise (neuer Inode). Das tempfile liegt aber im Elternordner des Ziels: Ist ein Ordner der Kette ein Symlink, landet die Datei am Verweisziel, der Schreiber muss die Kette deshalb wie der Leser per `dir_fd` + `O_NOFOLLOW` prüfen (CWE-59; CERT POS01-C, POS35-C).
- **Leser und Schreiber je Datei:** `override_token.py`, `phase_listener.py`, `edit_gate.py`, `bash_gate.py`, `post_implementation_gate.py`, `footer_gate.py`, `session_singleton_guard.py`, `workflow.py`, `hook_utils.py`

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `core/hooks/hook_utils.py` (`_open_state_fd`, `_state_walk_start`, `UnsafeStateError`, `atomic_write_json`, `find_project_root`, `_find_worktree_root`) | Modul | Heimat des gemeinsamen Leserkerns und des sicheren Schreibers; Vorarbeit aus #416 |
| `core/hooks/override_token.py` | Modul | `has_valid_token` wird von edit_gate, bash_gate, session_singleton_guard, worktree_write_guard u. a. aufgerufen; der Fund wird im Leser selbst abgefangen |
| `core/hooks/edit_gate.py`, `core/hooks/bash_gate.py` | Modul | Haben identische Stop-Lock-Kopien; werden auf eine gemeinsame Funktion `hook_utils.is_stop_locked` umgestellt |
| `core/hooks/post_implementation_gate.py`, `core/hooks/phase_listener.py` | Modul | Freigabe-Kette #134 (Pending-Lock, Freigabevermerk) |
| `core/hooks/footer_gate.py` | Modul | Läuft bei jedem Turn-Ende in jedem Konsumentenprojekt; fail-open ist tragende Anforderung |
| `core/hooks/session_singleton_guard.py`, `core/hooks/workflow.py` | Modul | Session-Register (Heartbeat bei jedem Tool-Aufruf) und Anzeige `workflow.py sessions` |
| `tests/test_state_reader_source_416.py` | Test | Quelle von `RICHTUNGEN = ["hard", "symlink_file", "symlink_dir", "claude_symlink"]` und der Sandbox-Hilfen; bleibt grün |
| `docs/specs/fix-416-state-reader-source-check.md` | Spec | Vorbild; dort benannte Known Limitations gelten weiter |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| `core/hooks/hook_utils.py` | MODIFY | `_read_state_bytes` (Kern aus `read_state_json`), `read_state_text`, sicherer Schreiber `atomic_write_text` und `atomic_write_json(..., root=)` mit `dir_fd`-Walk der Ordnerkette, gemeinsame `is_stop_locked`; `read_pending_validation_lock` über den Kern; `resolve_active_workflow` liest `active_workflow` über `read_state_text` |
| `core/hooks/override_token.py` | MODIFY | `_load_tokens` über den Kern, Fund ergibt `{}`; `_save_tokens` atomar mit `root` |
| `core/hooks/edit_gate.py` | MODIFY | Stop-Lock-Kopie durch `hook_utils.is_stop_locked` ersetzen |
| `core/hooks/bash_gate.py` | MODIFY | dito |
| `core/hooks/phase_listener.py` | MODIFY | Schreiber für Stop-Lock, Freigabevermerk und Token-Fallback atomar; Fund beim Schreiben: nicht schreiben, warnen |
| `core/hooks/post_implementation_gate.py` | MODIFY | Freigabevermerk über `read_state_text` (Fund ergibt keinen Vermerk); `_read_lock` fängt den Fund explizit und blockt; `_write_lock` atomar |
| `core/hooks/footer_gate.py` | MODIFY | `_read_state` bei Fund wie leer plus Log; `_remember` atomar |
| `core/hooks/session_singleton_guard.py` | MODIFY | `_read_entries` überspringt den Eintrag; Heartbeat, Register und Claim atomar mit `root` |
| `core/hooks/workflow.py` | MODIFY | `_read_session_entries` über den Kern (Anzeige) |
| `tests/test_state_files_source_422.py` | CREATE | Parametrisiert über `RICHTUNGEN` aus #416, je Datei und Richtung; Schreiber-Tests, Unlink-Pfade; Hooks als echte Subprozesse in Wegwerf-Sandbox |
| `CHANGELOG.md`, `CLAUDE.md` | MODIFY | Eintrag unter `[Unreleased]`, **kein** Versions-Bump; die `hook_utils`-Zeile in `CLAUDE.md` nennt die neuen Funktionen |

### Estimated Changes

- Files: 12 (davon 9 Hook-Dateien, 1 Test, 2 Doku). Das liegt über der Grenze von 4-5 Dateien.
- LoC: Code ca. +160/-40, Tests ca. +300, in Summe ca. 500 bei einer Grenze von ±250.
- **Überschreitung ist vom PO bestätigt:** Henning hat am 2026-10-11 im Intake ein Ticket trotz der Überschreitung entschieden (gemeinsames Ziel „jede Zustandsdatei prüft an der Quelle“; eine Teilung ließe Dateien ungeprüft). Die Teilung erfolgt stattdessen als Commit-Zwischenstände (siehe Implementation Details Punkt 7). Spec, Analyse-Kontext und PO-Briefing zählen im LoC-Gate zusätzlich als Code (#294, Fehlalarm).
- Alle Funktionen bleiben unter 50 Zeilen.
- Risiko hoch: Kern-Gates; `footer_gate` und `session_singleton_guard` laufen bei jedem Turn bzw. Tool-Aufruf in jedem Konsumentenprojekt. Ein Fehlalarm sperrt Arbeit, ein Durchschlagen nach außen gibt frei. Deshalb Gegenproben im Normalfall (AC-2, AC-18).

## Implementation Details

**1. Gemeinsamer Leserkern.** `_read_state_bytes(path, root)` ist der Kern aus `read_state_json` (#416): `dir_fd`-Walk ab `root` mit `O_NOFOLLOW|O_DIRECTORY` je Ordnerglied, Datei mit `O_RDONLY|O_NOFOLLOW|O_NONBLOCK`, `fstat` mit `S_ISREG` und `st_nlink == 1`, Lesen über denselben Deskriptor. `read_state_json` parst die Bytes weiter als JSON; neu ist `read_state_text` für Textdateien (Freigabevermerk, `active_workflow`). Fund ergibt `UnsafeStateError` (erbt weiter nur von `Exception`, nicht von `OSError`/`ValueError`). Fehlende Datei (`FileNotFoundError`) und kaputtes JSON verhalten sich wie heute.

**2. Richtung bei Fund je Datei (Tech-Lead-Entscheidung).** Freigebende Dateien fangen den Fund im Leser selbst, damit der sichere Default nicht von breiten `except Exception` der Aufrufer abhängt (z. B. `bash_gate`, `hook_utils`, `session_singleton_guard`, `workflow`). Sperrende Dateien werten den Fund als Sperre.

| Datei (unter `.claude/`) | Fund bedeutet | root |
|---|---|---|
| `user_override_token.json` | wie nicht vorhanden: keine Freigabe; im Leser abgefangen, nie propagiert | Projektwurzel |
| `user_approved_validation_<wf>` (Freigabevermerk) | wie nicht vorhanden | Projektwurzel |
| `stop_lock.json` | **gesperrt**; Meldung nennt den Verweis und dass Entfernen ihn löst | Worktree-Root, sonst Projektwurzel |
| `pending_validation_<wf>.json` | **blocken**: explizit fangen, denn eine unbehandelte Ausnahme ist Exit 1 und Claude Code lässt dabei durch | Projektwurzel |
| `footer_gate_state.json` | wie leer (Gate prüft), Log | Worktree-Root |
| `session-locks/*.json` | lesen: Eintrag überspringen; schreiben: nicht durchschreiben | Projektwurzel |
| `active_workflow` | wie nicht vorhanden, Fallback `settings.local.json`; Log | Worktree-Root bzw. Projektwurzel |

Stop-Lock und Footer-State liegen unter dem Worktree-Root; dort muss `root` der Worktree sein, nicht `find_project_root()`.

**3. Sicherer Schreiber.** `atomic_write_text` und `atomic_write_json(path, data, root=...)` schreiben ein tempfile und ersetzen per `os.replace`. Mit `root` läuft die Ordnerkette per `dir_fd` + `O_NOFOLLOW` (das tempfile entsteht über den geprüften Ordner-Deskriptor, nie in einem Symlink-Ziel); ist ein Ordner der Kette ein Verweis, wird nichts geschrieben und `UnsafeStateError` geworfen. Ein Symlink oder harter Verweis am Ziel wird ersetzt, das Verweisziel nie verändert. **Schreiber ohne `root` behalten das alte Verhalten** für Fremdaufrufer. Aufrufer fangen den Fund beim Schreiben: nicht schreiben, warnen.

**4. Pending-Lock.** `read_pending_validation_lock` liest über den Kern. `post_implementation_gate._read_lock` fängt den Fund ausdrücklich und ruft `block(...)`; ein `created` aus einem Verweis darf weder das Batch-Fenster offen halten noch einen Vermerk passend machen.

**5. Gemeinsame Stop-Lock-Funktion.** `hook_utils.is_stop_locked(root)` ersetzt die zwei Kopien in `edit_gate` und `bash_gate` (spart Zeilen, ein Regelwerk). Normale Datei mit `enabled: true` sperrt wie heute; fehlende oder kaputte Datei bleibt „nicht gesperrt“ wie heute; nur der Fund (Verweis) ist „gesperrt“.

**6. Fail-open bleibt tragend.** `footer_gate` und `session_singleton_guard` fangen `UnsafeStateError` an jeder neuen Stelle selbst; kein neuer Pfad lässt eine Ausnahme nach außen. Unlink-Pfade (`_clear_lock`, `_reap_dead`, `remove_all_tokens`) bleiben unverändert: `unlink` entfernt nur den Verweis, nie das Ziel.

**7. Commit-Zwischenstände** (jeder compiliert, Tests des jeweiligen Stands grün): (1) Kern + Token + Stop-Lock + Schreiber in `hook_utils`, (2) Freigabe-Kette (Pending-Lock, Freigabevermerk, `phase_listener`), (3) Footer-State + Session-Locks + `active_workflow`.

## Expected Behavior

- **Input:** Jeder Lese- oder Schreibzugriff auf Override-Token, Freigabevermerk, Stop-Lock, Pending-Lock, Footer-State, Session-Locks und `active_workflow` durch die genannten Hooks.
- **Output:** Normale eigene Datei: Verhalten wie heute. Verweis hart oder weich (Datei, ein Ordner der Kette oder `.claude`): Der Zugriff verhält sich gemäß Tabelle in Implementation Details Punkt 2, mit Meldung bzw. Log, die Pfad und Grund nennen. Kein Gate gewährt dadurch eine Freigabe, keine Sperre wird dadurch aufgehoben, und kein Schreiber verändert ein Verweisziel.
- **Side effects:** Keine neuen Subprozesse, keine neuen Abhängigkeiten, keine geänderten Config-Keys, kein neues State-Format, keine geänderten Dateipfade. Beim Fund wird nichts zurückgeschrieben und nichts kopiert.

## Known Limitations

Gelten aus #416 unverändert weiter und werden hier ausdrücklich benannt:

- **Link anlegen, schreiben, Link löschen:** Wer `.claude/` beschreiben darf, kann den Verweis wieder löschen und eine echte Datei mit gefälschtem Inhalt anlegen (`st_nlink == 1`); die Fälschung ist beim Lesen nicht erkennbar. Eine Inhaltsbindung (HMAC) würde das schließen, der Schlüssel läge aber wieder als Datei im selben Benutzerkonto.
- **Direktes Schreiben ohne Link** (zusammengesetzter Pfad, z. B. per `python3 -c`) wird nicht erkannt; das bleibt Sache der Textprüfung (#407/#410) und der Config-Sperre (#418).
- **Symlink von außen auf den Ordner** ist beim Lesen über den echten Pfad nicht erkennbar (Ziel ist eine normale Datei mit `st_nlink == 1`).
- **`settings.local.json` ungeprüft** (siehe nächster Abschnitt).
- **Fehlalarmquellen (selten):** `cp -l`/`rsync --link-dest`, `.claude` als Dotfile-Symlink. Die Meldung nennt den Bereinigungsweg.
- Windows: `dir_fd`/`O_NOFOLLOW` wie in #416 (das Framework läuft auf macOS/Linux).
- Verteilung: wirkt in Konsumentenprojekten erst nach dem Plugin-Update.

## Bewusst nicht im Scope

- **`settings.local.json`:** Die Datei gehört Claude Code; Dotfile-Symlinks sind dort legitim, eine strenge Prüfung könnte Nutzer aussperren. Sie wählt nur einen Workflow-Namen, dessen State danach über `read_state_json` (#416) geprüft wird. Bleibt Known Limitation.
- **`migrate_state.py`:** Manuell aufgerufenes Einmalwerkzeug (v2 nach v3) ohne Gate-Wirkung; Entfernen wäre ein Breaking Change für die Doku in `setup.py` und `80-workflow.md`. Wird nicht geprüft, nur hier dokumentiert.
- Der Leser `workflow_state.json` (Alt-v2) und alle Pfade außerhalb der oben genannten Zustandsdateien.

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Für jede genannte Datei ist Verweis (hart und weich) je Richtung aus `RICHTUNGEN` durch einen automatischen Test belegt: kein Gate gewährt dadurch eine Freigabe oder hebt eine Sperre auf
- [ ] Normale Dateien verhalten sich unverändert; die Vollsuite ist grün
- [ ] Die Known Limitations aus #416 (Link anlegen, schreiben, löschen; direktes Schreiben ohne Link) gelten weiter und sind in Spec und CHANGELOG-Eintrag benannt
- [ ] `settings.local.json` und `migrate_state.py` sind als bewusst ungeprüft mit Begründung dokumentiert
- [ ] `CHANGELOG.md` (unter `[Unreleased]`) und die `hook_utils`-Zeile in `CLAUDE.md` sind aktualisiert

## Acceptance Criteria

Alle Tests laufen über `RICHTUNGEN = ["hard", "symlink_file", "symlink_dir", "claude_symlink"]` aus `tests/test_state_reader_source_416.py`; Hooks laufen als echte Subprozesse in einer Wegwerf-Sandbox. Testdatei: `tests/test_state_files_source_422.py`.

- **AC-1:** Given jede der vier Richtungen für eine Zustandsdatei / When `read_state_text` bzw. der Leserkern sie liest / Then wirft er `UnsafeStateError` mit Pfad und Grund; `read_state_json` aus #416 verhält sich unverändert
  - Test: `tests/test_state_files_source_422.py::test_kern_wirft_unsafe_state_error_je_richtung`
- **AC-2:** Given eine normale eigene Datei, eine fehlende Datei, kaputter Inhalt und eine Wurzel hinter einem Symlink-Elternordner / When der Kern bzw. jeder umgestellte Leser sie liest / Then liefern sie den Inhalt, `FileNotFoundError` bzw. das heutige Verhalten wie vor der Änderung, ohne `UnsafeStateError` und ohne Fehlalarm
  - Test: `tests/test_state_files_source_422.py::test_normalfall_fehlend_kaputt_und_wurzel_hinter_symlink_wie_heute`
- **AC-3:** Given `user_override_token.json` mit gültigem Token als Verweis (alle vier Richtungen) / When `override_token.has_valid_token`, `edit_gate` und `bash_gate` (als Subprozess), die Worktree-Prüfung und der Import-Fallback in `phase_listener` den Token auswerten / Then liefert `has_valid_token` `False`, und kein Gate gewährt dadurch eine Freigabe (Code-Edit bleibt blockiert, Exit 2); der Fund wird im Leser abgefangen und nie propagiert
  - Test: `tests/test_state_files_source_422.py::test_override_token_verweis_gibt_nichts_frei`
- **AC-4:** Given `user_approved_validation_<wf>` (Freigabevermerk) als Verweis mit zum Pending-Lock passendem Inhalt (alle vier Richtungen) / When `post_implementation_gate` läuft / Then gilt der Vermerk als nicht vorhanden: der Lock wird nicht gelöscht, der Edit nicht erlaubt (Exit 2)
  - Test: `tests/test_state_files_source_422.py::test_freigabevermerk_verweis_gilt_als_nicht_vorhanden`
- **AC-5:** Given `stop_lock.json` als Verweis, auch hängend und auch mit `enabled: false` im Ziel (alle vier Richtungen) / When `edit_gate` und `bash_gate` als Subprozess laufen / Then sind sie gesperrt (Exit 2), die Meldung nennt den Verweis und dass Entfernen ihn löst; beide nutzen dieselbe Funktion `hook_utils.is_stop_locked`, und die Kopien in den Gates sind entfernt
  - Test: `tests/test_state_files_source_422.py::test_stop_lock_verweis_sperrt_edit_und_bash_gate`
- **AC-6:** Given `pending_validation_<wf>.json` als Verweis, auch mit `created` in der Zukunft (alle vier Richtungen) / When `post_implementation_gate` und `phase_listener` laufen / Then blockt `post_implementation_gate` ausdrücklich per `block()` (Exit 2, nie Exit 1 durch unbehandelte Ausnahme), das Batch-Fenster bleibt nicht offen, und `phase_listener` schreibt keinen Freigabevermerk
  - Test: `tests/test_state_files_source_422.py::test_pending_lock_verweis_blockt_explizit_nie_exit_1`
- **AC-7:** Given `footer_gate_state.json` als Verweis mit Inhalt, der das Gate abschalten würde (`last_turn_id` des aktuellen Turns bzw. frisches `last_block_at`) (alle vier Richtungen) / When `footer_gate` als Subprozess läuft / Then wird der Verweis wie ein leerer State behandelt (das Gate prüft die Fußzeile), ein Log nennt den Fund, und der Hook endet nie mit einer Ausnahme nach außen (fail-open)
  - Test: `tests/test_state_files_source_422.py::test_footer_state_verweis_wie_leer_mit_log`
- **AC-8:** Given Session-Locks (`session-locks/*.json`), von denen ein Eintrag ein Verweis ist (alle vier Richtungen) / When `session_singleton_guard._read_entries` und `workflow.py sessions` lesen / Then wird der Eintrag übersprungen (taucht nicht in der Anzeige auf), die übrigen Einträge werden normal gelesen, und es entsteht keine Ausnahme nach außen
  - Test: `tests/test_state_files_source_422.py::test_session_locks_verweis_eintrag_wird_uebersprungen`
- **AC-9:** Given der eigene Session-Lock oder `active_workflow` ist ein Verweis auf eine fremde Datei (alle vier Richtungen) / When `session_singleton_guard` Heartbeat, Register oder Claim schreibt / Then bleibt die fremde Zieldatei byte-gleich, nichts wird durchgeschrieben, und der Hook endet unverändert fail-open ohne neue Ausnahme
  - Test: `tests/test_state_files_source_422.py::test_session_guard_schreibt_nie_durch_verweis`
- **AC-10:** Given `active_workflow` als Verweis (alle vier Richtungen), und `settings.local.json` mit anderem Namen / When `resolve_active_workflow` den Namen bestimmt / Then gilt der Marker als nicht vorhanden, der Fallback `settings.local.json` greift, ein Log nennt den Fund, und der Name aus dem Verweis wird nie übernommen
  - Test: `tests/test_state_files_source_422.py::test_active_workflow_verweis_wie_nicht_vorhanden_mit_fallback`
- **AC-11:** Given Override-Token, Stop-Lock, Pending-Lock, Freigabevermerk und Footer-State als Verweis auf eine fremde Datei (alle vier Richtungen) / When `override_token._save_tokens`, `phase_listener._set_stop_lock`, der Schreiber des Freigabevermerks, der Token-Fallback, `post_implementation_gate._write_lock` und `footer_gate._remember` schreiben / Then ändert sich das Verweisziel nie (byte-gleich); am Ziel entsteht eine neue normale Datei bzw. bei Fund in der Ordnerkette wird gar nicht geschrieben, mit Warnung
  - Test: `tests/test_state_files_source_422.py::test_schreiber_veraendern_verweisziel_nie`
- **AC-12:** Given `.claude` oder ein Ordner der Kette (z. B. `session-locks`) ist ein Symlink / When ein atomarer Schreiber mit `root` schreibt / Then wird kein tempfile am Verweisziel angelegt, nichts geschrieben und `UnsafeStateError` gemeldet; die Ordnerkette wird also wie beim Lesen geprüft, nicht nur das letzte Glied
  - Test: `tests/test_state_files_source_422.py::test_atomarer_schreiber_prueft_ordnerkette`
- **AC-13:** Given Schreiber ohne `root` (Fremdaufrufer von `atomic_write_json`) / When sie aufgerufen werden / Then behalten sie das bisherige Verhalten (tempfile im Elternordner, `os.replace`, kein Walk)
  - Test: `tests/test_state_files_source_422.py::test_schreiber_ohne_root_behalten_altes_verhalten`
- **AC-14:** Given Verweise auf die Zustandsdateien und die Unlink-Pfade `post_implementation_gate._clear_lock`, `session_singleton_guard._reap_dead` und `override_token.remove_all_tokens` / When sie laufen / Then wird nur der Verweis entfernt und das Verweisziel bleibt unverändert; je Pfad ein Test
  - Test: `tests/test_state_files_source_422.py::test_clear_lock_loescht_nur_den_verweis`, `::test_reap_dead_loescht_nur_den_verweis`, `::test_remove_all_tokens_loescht_nur_den_verweis`
- **AC-15:** Given jeder Fund-Pfad in `footer_gate` und `session_singleton_guard` / When die Hooks als Subprozess laufen / Then endet keiner mit einer unbehandelten Ausnahme (kein Exit 1, kein Traceback nach außen); fail-open bleibt wie vor der Änderung
  - Test: `tests/test_state_files_source_422.py::test_footer_gate_und_session_guard_werfen_nie_nach_aussen`
- **AC-16:** Given normale eigene Zustandsdateien in allen sieben Fällen / When die Hooks lesen und schreiben / Then bleibt das Verhalten unverändert (Token gewährt Freigabe, Stop-Lock sperrt bei `enabled: true`, Pending-Lock und passender Vermerk lösen die Sperre, Footer-State schaltet das Gate ab, Session-Locks erscheinen in der Anzeige, `active_workflow` wählt den Namen), und die geschriebene Datei ist wieder eine normale Datei mit `st_nlink == 1`
  - Test: `tests/test_state_files_source_422.py::test_normale_dateien_verhalten_unveraendert`
- **AC-17:** Given der bestehende Testbestand / When die Vollsuite einschließlich `tests/test_state_reader_source_416.py` und `tests/test_bash_gate*` läuft / Then bleibt sie grün
  - Test: Vollsuite (unverändert, Lauf grün)
- **AC-18:** Given `CHANGELOG.md` und `CLAUDE.md` / When sie gelesen werden / Then nennt der `[Unreleased]`-Eintrag die Known Limitations aus #416 (Link anlegen, schreiben, löschen; direktes Schreiben ohne Link) und `settings.local.json` als ungeprüft, `CLAUDE.md` nennt die neuen `hook_utils`-Funktionen, und es gibt keinen Versions-Bump
  - Test: `tests/test_state_files_source_422.py::test_changelog_und_claude_md_nennen_limitations_und_funktionen`

> Die Test-Zuordnung wird **bei der Spec-Erstellung** eingetragen, nicht nachträglich:
> Nach der Freigabe ist diese Datei eingefroren (#230) — jede Änderung verschiebt den
> PO-Briefing-Hash und blockt den Workflow-Abschluss. Stimmt der Testname später nicht
> mehr, gehört die Korrektur in die TDD-RED-Artefakte (`workflow.py add-artifact`),
> nicht in diese Datei.

## Test Plan

### Automated Tests (TDD RED)

Datei: `tests/test_state_files_source_422.py`, parametrisiert je Datei × Richtung (`RICHTUNGEN` aus `tests/test_state_reader_source_416.py`) plus Normalfall. Hooks als echte Subprozesse in einer Wegwerf-Sandbox mit echtem Projektaufbau; die Parametrisierung hält die Testzeilen je Datei klein. Abweichungen werden gesammelt und am Ende gemeinsam gemeldet.

- [ ] Test 1 (AC-1, AC-2): GIVEN Verweise in vier Richtungen bzw. normale, fehlende, kaputte Datei und Wurzel hinter Symlink, WHEN der Kern liest, THEN `UnsafeStateError` bzw. Verhalten wie heute (Normalfall muss vor und nach der Implementierung grün sein)
- [ ] Test 2 (AC-3, AC-4): GIVEN Token bzw. Freigabevermerk als Verweis mit freigebendem Inhalt, WHEN `has_valid_token`, `edit_gate`, `bash_gate`, `post_implementation_gate` laufen, THEN keine Freigabe (RED: heute `True` bzw. Edit erlaubt)
- [ ] Test 3 (AC-5, AC-6): GIVEN Stop-Lock bzw. Pending-Lock als Verweis, WHEN `edit_gate`, `bash_gate`, `post_implementation_gate` laufen, THEN Exit 2 mit Meldung, nie Exit 1 (RED: heute nicht gesperrt bzw. unbehandelte Ausnahme)
- [ ] Test 4 (AC-7, AC-8, AC-10, AC-15): GIVEN Footer-State, Session-Lock bzw. `active_workflow` als Verweis, WHEN `footer_gate`, `session_singleton_guard`, `workflow.py sessions` und `resolve_active_workflow` laufen, THEN wie leer, übersprungen bzw. nicht vorhanden, mit Log und ohne Ausnahme nach außen
- [ ] Test 5 (AC-9, AC-11, AC-12, AC-13): GIVEN Verweise auf fremde Dateien, Symlink-Ordner in der Kette und Aufrufe ohne `root`, WHEN die Schreiber schreiben, THEN Verweisziel byte-gleich, kein tempfile am Verweisziel, altes Verhalten ohne `root` (RED: heute schreibt `open(..., "w")` durch den Symlink)
- [ ] Test 6 (AC-14): GIVEN Verweise, WHEN `_clear_lock`, `_reap_dead`, `remove_all_tokens` laufen, THEN nur der Verweis ist entfernt, das Ziel bleibt
- [ ] Test 7 (AC-16, AC-17, AC-18): GIVEN normale Dateien, der bestehende Bestand und die Doku, WHEN Tests und Prüfungen laufen, THEN Verhalten unverändert, Vollsuite grün, CHANGELOG/CLAUDE.md wie spezifiziert

Die RED-Läufe müssen vor der Implementierung an allen vier Verweisrichtungen die Abweichung zeigen und werden als Artefakte registriert.

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Die Änderung überträgt die Entscheidung aus #416 („Prüfung an der Quelle per `dir_fd`-Walk in einer gemeinsamen Funktion“) auf die übrigen Zustandsdateien und kippt keine bestehende ADR. Kein neues Format, keine neue Abhängigkeit, keine Migration.

**Entscheidung:** Ein gemeinsamer Leserkern und ein gemeinsamer sicherer Schreiber in `hook_utils`, kein zweites Regelwerk; die Richtung bei Fund richtet sich nach der Wirkung der Datei (freigebend: keine Freigabe; sperrend: gesperrt). Regelweg zuerst: Dateisystem-Metadaten (`fstat`, `O_NOFOLLOW`) sind deterministisch, „ohne Modell geht es nicht“ stellt sich nicht.

**Alternativen (bewertet, nicht gewählt):**

- **A — Alle Zustandsdateien nach `.claude/state/` mit einer Ordnerprüfung:** löst harte Verweise nicht, und die Pfad-Migration in laufenden Sitzungen wäre ein Breaking Change. Verworfen.
- **B — Inhalt per HMAC an ein Sitzungsgeheimnis binden:** fängt auch gefälschte echte Dateien (Known Limitation aus #416), aber der Schlüssel läge wieder als Datei im selben Benutzerkonto; hohe Komplexität, neues Format. Würde die Entscheidung „präventiv prüfen, Ausweg Override“ aus #407/#410 ergänzen statt ersetzen. Verworfen.
- **C — Nur freigebende Dateien prüfen:** kleinster Umfang, lässt aber die Stop-Lock-Lücke (hängender Symlink hebt die Sperre auf) und das Durchschreiben der Session-Locks offen. Verworfen.
- **D — Drei Tickets statt einem:** PO hat ein Ticket entschieden; die Schnitte werden zu Commit-Zwischenständen. Verworfen.

## Changelog

- 2026-10-11: Initial spec created (#422)
