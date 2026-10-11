# Context: fix-422-state-files-source-check

## Request Summary
Folgeticket aus #416: Alle übrigen Zustandsdateien der Gate-Kette werden nur gelesen, wenn sie
nachweislich eine eigene, normale Datei sind (kein Symlink in der Kette, `S_ISREG`, `st_nlink == 1`).
Fund → keine Freigabe, Sperren bleiben wirksam. In-place-Schreiber werden atomar.
PO-Entscheid im Intake (2026-10-11): ein Ticket, trotz geschätzt ~500 Zeilen.

## Related Files — Leser und Schreiber je Zustandsdatei

| Datei (unter `.claude/`) | Leser | Schreiber | Wirkung des Inhalts |
|---|---|---|---|
| `user_override_token.json` | `override_token.py:33` `_load_tokens` (alle Hooks über `has_valid_token`), `phase_listener.py:381` (Import-Fallback) | `override_token.py:56` `_save_tokens` (`open(...,"w")`, schreibt durch Symlink), `phase_listener.py:394` `write_text`; `remove_all_tokens` unlinkt | **freigebend** (Override für edit_gate, bash_gate, Worktree-Guard `_has_override_token`, Config-Sperre) |
| `stop_lock.json` (worktree-lokal oder Root) | `edit_gate.py:356` `_is_stop_locked`, `bash_gate.py:188` (identische Kopie) | `phase_listener.py:432` `_set_stop_lock` (`write_text`) | **sperrend** (`enabled: true` blockt alles); fehlend/kaputt → heute *nicht* gesperrt |
| `pending_validation_<wf>.json` | `hook_utils.py:1525` `read_pending_validation_lock` (→ `post_implementation_gate.py:156`, `phase_listener.py:615`) | `post_implementation_gate.py:75` `_write_lock` (`write_text`); unlink in `_clear_lock` und bei fremder Instanz | **sperrend, aber mit Freigabeanteil**: `created` in der Zukunft hält das Batch-Fenster dauerhaft offen; `created` bestimmt, welcher Freigabe-Vermerk passt |
| `user_approved_validation_<wf>` (Text) | `post_implementation_gate.py:169` `read_text().strip()` | `phase_listener.py:619` `write_text(str(created))` | **freigebend** (passt Inhalt zu `lock.created` → Lock gelöscht, Edit erlaubt) |
| `footer_gate_state.json` (worktree-lokal) | `footer_gate.py:87` `_read_state` | `footer_gate.py:115` `_remember` (`write_text`) | **lockernd**: `last_turn_id`/`last_block_at` schalten das Gate für einen Turn bzw. 120 s ab (Zukunftszeit ist seit früher abgefangen) |
| `session-locks/*.json` | `session_singleton_guard.py:167` `_read_entries`, `:553` Heartbeat, `:621` Register, `:729` Claim; `workflow.py:2117` `_read_session_entries` (Anzeige) | `session_singleton_guard.py:535/595/634/810` (`write_text`, schreibt durch Symlink in fremde Datei); `_reap_dead` unlinkt | **nur Auskunft/Register**: gewährt kein Gate (Worktree-Pflicht hängt an cwd + Override-Token). Risiko liegt beim Schreiben durch einen Verweis |
| `active_workflow` (Text) | `hook_utils.py:1587/1613` `resolve_active_workflow` | `workflow.py` start/switch | **wählt nur den Namen**; der State wird danach über `read_state_json` geprüft. Ein Verweis auf das Marker-File einer anderen Sitzung kann deren Workflow wählen (vgl. #58) |
| `settings.local.json` | `hook_utils.py:1597/1621`, `workflow.py:471/513` | `workflow.py` (setzt `env.OPENSPEC_ACTIVE_WORKFLOW`) | wie oben, nur Namenswahl; zusätzlich Claude-Code-Einstellungsdatei (nicht nur unser State) |
| `workflow_state.json` (Alt-v2) | `migrate_state.py:33` | `migrate_state.py` (`write_text`) | einmalige Migration v2→v3; weiter in `setup.py:1555`, `80-workflow.md:227`, `migrate_to_plugin.py:54` genannt |

## Existing Patterns
- **#416-Leser** `hook_utils.read_state_json(path, root)` (`hook_utils.py:1471`): `_open_state_fd` läuft per
  `dir_fd` + `O_NOFOLLOW` ab Projektwurzel Glied für Glied, dann `fstat`: `S_ISREG`, `st_nlink == 1`.
  Fund → `UnsafeStateError` (erbt bewusst nicht von `OSError`/`ValueError`, damit fail-open-Leser ihn
  nicht verschlucken). Liest und parst JSON — für Textdateien (Approval-Marker, `active_workflow`)
  fehlt eine Variante.
- **Worktree-Pfade:** `_state_walk_start` prüft ab `root`; Stop-Lock und Footer-State liegen unter dem
  Worktree-Root (`_find_worktree_root()`), also muss `root` dort der Worktree sein, nicht `find_project_root()`.
- **Atomar schreiben:** `hook_utils.atomic_write_json` (`hook_utils.py:1499`, tempfile + `os.replace`)
  — neuer Inode, bricht harte Verweise, ersetzt Symlink am Ziel. Text-Variante fehlt.
- **Fehlerbehandlung je Hook bei Fund** (aus #416): edit_gate/bash_gate `block(...)`;
  post_implementation_gate fail-open mit Warnung (edit_gate blockt); footer_gate fängt
  `UnsafeStateError` (`footer_gate.py:161`); session_singleton_guard fängt ihn (`:329`).
- **Tests aus #416:** `tests/test_state_reader_source_416.py` (608 Zeilen) — parametrisiert über
  `RICHTUNGEN = ["hard", "symlink_file", "symlink_dir", "claude_symlink"]`, Hooks als echte
  Subprozesse in einer Wegwerf-Sandbox. Parametrisierung hält die Testzeilen je Datei klein.

## Dependencies
- Upstream: `hook_utils.find_project_root`, `_find_worktree_root`, `_open_state_fd`, `UnsafeStateError`,
  `atomic_write_json`, `config_loader`.
- Downstream: Jeder Hook, der `has_valid_token` aufruft (edit_gate, bash_gate, session_singleton_guard,
  worktree_write_guard u. a.); post_implementation_gate und phase_listener (Freigabe-Kette #134);
  footer_gate (jeder Turn-Ende in jedem Projekt, fail-open ist dort tragende Anforderung);
  `workflow.py sessions`.

## Existing Specs
- `docs/specs/fix-416-state-reader-source-check.md` — Vorbild, Abschnitt „Bewusst nicht im Scope“ benennt genau diese Dateien.
- `docs/context/fix-416-state-reader-source-check.md` — Abschnitt „Weitere Zustandsdateien“ (Zeilennummern inzwischen verschoben, s. Tabelle oben).

## Risks & Considerations
1. **Richtung je Datei:** Fund im Override-Token/Approval-Marker → wie „nicht vorhanden“ (keine Freigabe).
   Fund im Stop-Lock → *gesperrt* (heute: fehlend/kaputt = offen; ein Verweis darf das nicht erben).
   Fund im Pending-Lock → nicht als offenes Batch-Fenster werten (Zukunfts-`created`), sondern blocken.
   Footer-State → wie leer (Gate prüft). Session-Locks → Eintrag ignorieren, nie durchschreiben.
2. **Schreiben durch Verweise:** `write_text`/`open("w")` folgen Symlinks und schreiben in fremde Dateien
   (Session-Heartbeat bei *jedem* Tool-Aufruf). Atomar schreiben ersetzt den Verweis statt das Ziel zu ändern.
3. **Unlink-Pfade** (`_clear_lock`, `_reap_dead`, `remove_all_tokens`) löschen nur den Verweis, nie das Ziel — unkritisch, aber in Tests absichern.
4. **Footer-Gate und Session-Guard laufen bei jedem Turn/Tool in jedem Projekt** — keine neuen Ausnahmen, die nach außen werfen.
5. **Stop-Lock-Leser sind doppelt** (edit_gate/bash_gate identisch) — Kandidat für eine gemeinsame Funktion in hook_utils (spart Zeilen, erfüllt Teil 2).
6. **`active_workflow`/`settings.local.json`:** prüfen, ob die Namenswahl allein ausnutzbar ist (Verweis auf Marker einer Parallelsitzung → fremder Workflow, dessen State echt ist). `settings.local.json` gehört auch Claude Code; ein Symlink dort kann legitim sein (Dotfiles) — strenge Prüfung könnte Nutzer brechen.
7. **`migrate_state.py`:** v2→v3-Werkzeug, manuell aufgerufen, kein Gate. Kandidat für „nicht prüfen, dokumentieren“ oder Entfernen (Entfernen = Breaking für Doku in setup.py/80-workflow).
8. **Known Limitations aus #416 bleiben:** Wer schreiben darf, kann den Verweis auch löschen und eine echte Datei mit gefälschtem Inhalt anlegen; direktes Schreiben ohne Link wird nicht erkannt.
9. **Umfang:** ~9 Hook-Dateien + 1 Testdatei; Schätzung ~200 Code / ~300 Tests (Subprozess-Tests ~25 Zeilen, parametrisiert günstiger). PO hat ein Ticket bestätigt.

## Analysis

### Type
Bug (Sicherheitslücke, Folge aus #416)

### Reproduktion (2026-10-11, Wegwerf-Sandbox, echte Funktionen)
Skript im Scratchpad (`repro422.py`; Projekt per `CLAUDE_PROJECT_DIR`, `git init`):
- a) Token-Datei als Symlink auf fremde Datei mit gültigem Token → `override_token.has_valid_token('wf')` = **True**
- b) dasselbe als harter Verweis (`st_nlink=2`) → **True**
- c) `override_token._save_tokens` bei Symlink → **fremde Zieldatei überschrieben**
- d) `stop_lock.json` als hängender Symlink → `edit_gate._is_stop_locked()` = **False** (nicht gesperrt)

### Recherche
- `os.replace(tmp, ziel)` ersetzt einen Symlink am Ziel durch eine normale Datei und bricht harte
  Verweise (neuer Inode) — gewollt, so wird nie in fremde Dateien geschrieben.
- Aber: `atomic_write_json` legt das tempfile in `path.parent`; ist `.claude` (oder ein Ordner bis zur
  Wurzel) ein Symlink, landet die Datei am Verweisziel. Der Schreiber muss die Ordnerkette genauso
  prüfen wie der Leser (dir_fd + `O_NOFOLLOW`), vgl. CWE-59.
- Quellen: code.activestate.com/recipes/579097, db.gcve.eu/cwe/CWE-59.

### Affected Files (with changes)
| File | Change Type | Description |
|------|-------------|-------------|
| core/hooks/hook_utils.py | MODIFY | `_read_state_bytes` (Kern aus `read_state_json`), `read_state_text`, sicherer Schreiber `atomic_write_text` / `atomic_write_json(..., root=)` mit dir_fd-Walk der Ordnerkette, gemeinsamer `is_stop_locked`; `read_pending_validation_lock` über den Kern |
| core/hooks/override_token.py | MODIFY | `_load_tokens` über Kern, Fund → `{}`; `_save_tokens` atomar mit `root` |
| core/hooks/edit_gate.py | MODIFY | Stop-Lock-Kopie durch `hook_utils.is_stop_locked` ersetzen |
| core/hooks/bash_gate.py | MODIFY | dito |
| core/hooks/phase_listener.py | MODIFY | Stop-Lock-, Freigabevermerk- und Token-Fallback-Schreiber atomar; Fund beim Schreiben → nicht schreiben, warnen |
| core/hooks/post_implementation_gate.py | MODIFY | Freigabevermerk über `read_state_text` (Fund → kein Vermerk); `_read_lock` (Z. 152, heute ungeschützt) Fund → `block`; `_write_lock` atomar |
| core/hooks/footer_gate.py | MODIFY | `_read_state` Fund → `{}` + Log; `_remember` atomar |
| core/hooks/session_singleton_guard.py | MODIFY | `_read_entries` Fund → Eintrag überspringen; Heartbeat/Register/Claim atomar mit `root` |
| core/hooks/workflow.py | MODIFY | `_read_session_entries` über Kern (Anzeige) |
| tests/test_state_files_source_422.py | CREATE | parametrisiert über `RICHTUNGEN` aus #416, je Datei und Richtung; Schreiber-Tests (Ziel unverändert, Ordnerkette), Unlink-Pfade |
| CHANGELOG.md, CLAUDE.md | MODIFY | [Unreleased]; hook_utils-Zeile um die neuen Funktionen |

### Verhalten bei Fund je Datei (Tech-Lead-Entscheidung)
| Datei | Fund bedeutet | root |
|---|---|---|
| Override-Token | wie nicht vorhanden (keine Freigabe); im Leser abgefangen, nie propagiert | Projektwurzel |
| Freigabevermerk (Validation) | wie nicht vorhanden | Projektwurzel |
| Stop-Lock | **gesperrt**; Meldung nennt den Verweis und dass Entfernen ihn löst | Worktree-Root, sonst Projektwurzel |
| Pending-Lock | **blocken** — explizit fangen: heute ungeschützter Aufruf Z. 152, unbehandelte Ausnahme = Exit 1 = Claude Code lässt durch | Projektwurzel |
| Footer-State | wie leer (Gate prüft), Log | Worktree-Root |
| Session-Locks lesen / schreiben | Eintrag überspringen / nicht durchschreiben | Projektwurzel |
| `active_workflow` | wie nicht vorhanden → Fallback `settings.local.json`; Log | Worktree-Root bzw. Projektwurzel |
| `settings.local.json` | **nicht geprüft** — gehört Claude Code, Dotfile-Symlinks legitim; wählt nur einen Namen, dessen State `read_state_json` prüft → Known Limitation | – |
| `migrate_state.py` | **nicht geprüft** — manuelles Einmal-Werkzeug ohne Gate-Wirkung → dokumentieren | – |

### Scope Assessment
- Files: ~9 Hook-Dateien + 1 Testdatei + Doku (über Limit 4–5; PO hat im Intake ein Ticket entschieden)
- Estimated LoC: Code ~+160/−40, Tests ~+300
- Risk Level: HIGH (Kern-Gates; footer_gate und session_guard laufen bei jedem Turn/Tool in jedem Projekt)

### Technical Approach
Wie #416, ausgedehnt: ein gemeinsamer Leserkern (`_read_state_bytes`) und ein gemeinsamer sicherer
Schreiber in `hook_utils`, kein zweites Regelwerk. Freigebende Dateien fangen den Fund im Leser selbst
(sicherer Default unabhängig von breiten `except Exception` der Aufrufer, z. B. `bash_gate.py:1117`,
`hook_utils.py:1759`, `session_singleton_guard.py:267`, `workflow.py:1386`). Sperrende Dateien werten
den Fund als Sperre. Unlink-Pfade bleiben (löschen nur den Verweis) und bekommen je einen Test.
Schreiber ohne `root` behalten das alte Verhalten für Fremdaufrufer.
Wichtig: In Hooks ist eine unbehandelte Ausnahme Exit 1 = nicht blockierend → jeder neue Fund-Pfad in
sperrenden Gates muss explizit `block()` erreichen. Commits in Zwischenständen: (1) Kern + Token +
Stop-Lock + Schreiber, (2) Freigabe-Kette, (3) Footer + Session-Locks + `active_workflow`.

### Alternativen (verworfen)
1. Alle Zustandsdateien nach `.claude/state/` mit einer Ordnerprüfung — löst harte Verweise nicht,
   Pfad-Migration in laufenden Sitzungen = Breaking Change.
2. Inhalt per HMAC an ein Sitzungsgeheimnis binden — fängt auch gefälschte echte Dateien (Limitation
   aus #416), aber der Schlüssel läge wieder als Datei im selben Benutzerkonto; hohe Komplexität.
3. Nur freigebende Dateien prüfen — kleinster Umfang, lässt aber die Stop-Lock-Lücke (d) und das
   Durchschreiben der Session-Locks offen.
4. Drei Tickets statt einem — PO hat ein Ticket entschieden; die Schnitte werden zu Commit-Zwischenständen.

### Dependencies
Upstream: `_open_state_fd`, `_state_walk_start`, `UnsafeStateError`, `find_project_root`,
`_find_worktree_root`. Downstream: alle Aufrufer von `has_valid_token`, Freigabe-Kette #134,
footer_gate, `workflow.py sessions`.

### Known Limitations (bleiben)
Wer `.claude/` beschreiben darf, kann den Verweis löschen und eine echte Datei mit gefälschtem Inhalt
anlegen; direktes Schreiben ohne Link wird nicht erkannt. `settings.local.json` ungeprüft.
Windows: dir_fd/O_NOFOLLOW wie in #416 (Framework läuft auf macOS/Linux).

### Open Questions
- keine PO-Fragen offen (Gate-Design ist Tech-Lead-Entscheidung, Ein-Ticket-Entscheid liegt vor)
