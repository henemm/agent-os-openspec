# Context: fix-350-remove-aliases-robust

## Request Summary
#350 (Folge der Gegenprüfung von #251): `setup.py --remove-aliases` soll auch bei unerwarteten
Dateien in `.claude/commands/` benutzbar bleiben. Drei Teile: F001 unlesbare Dateien (MEDIUM),
F002 Kept-Liste und `--global`-Warnung (LOW), F003 Frontmatter-Erkennung bei CRLF/Leerzeichen (LOW).
Quelle der Befunde: `docs/artifacts/feat-251-kurzbefehle/adversary-dialog.md`.

## Related Files
| Datei | Relevanz |
|-------|----------|
| `core/hooks/alias_sync.py:94` `find_aliases` | F001: `p.read_text()` ohne Fehlerbehandlung, `UnicodeDecodeError` bricht den Lauf |
| `core/hooks/alias_sync.py:43` `_frontmatter_close` | F003: verlangt `lines[0] == "---"` und `"---"` exakt, CRLF/Leerzeichen fallen auf die Altposition |
| `core/hooks/alias_sync.py:53` `alias_content` | F003: nutzt `_frontmatter_close` beim Einsetzen des Markers |
| `core/hooks/alias_sync.py:163/166/192` | GLEICHER Defekt wie F001 in `find_stale_aliases` und `find_removed_aliases` (ungeschütztes `read_text`), nicht im Ticket genannt |
| `setup.py:1123` `remove_command_aliases` | F001/F002: Kept-Liste per `glob("*.md")` ohne `is_file`, keine Behandlung unlesbarer Dateien |
| `setup.py:1268` | F002: `--global` ohne `--remove-aliases` wird stillschweigend ignoriert |
| `migrate_to_plugin.py:506-510` | Vorbild: `try: read_text() except Exception: continue` — unlesbar heißt nicht löschbar |
| `tests/test_alias_remove_251.py` | Bestehende Tests, Muster: `setup.py` als echter Prozess mit Test-Home (`_run_setup`) |

## Existing Patterns
- Unlesbare Datei = nie löschen, still überspringen (`migrate_to_plugin.py`).
- CLI-Tests starten `setup.py` per `subprocess` mit eigenem HOME, nie das echte `~/.claude/commands/`.
- Meldungsformat: `Removed: x.md`, `Kept: x.md`, Schlusszeile `Command aliases: N removed, M kept.`

## Dependencies
- Upstream: `alias_sync.is_alias_file`, `ALIAS_MARKER`, `pathlib`.
- Downstream: `find_aliases` hat nur einen Aufrufer (`remove_command_aliases`). `find_stale_aliases`
  und `find_removed_aliases` werden vom Refresh-Modus genutzt (und ggf. vom Session-Banner, in
  `/20-analyse` zu klären — ein Absturz dort wäre ein Hook-Problem, kein Werkzeug-Problem).

## Existing Specs
- `docs/specs/feat-251-kurzbefehle.md` (Verhalten von `--remove-aliases`, AC der Vorarbeit)
- `docs/context/feat-251-kurzbefehle.md`

## Risks & Considerations
- `core/hooks/alias_sync.py` ist Hook-Verzeichnis: Gegenprüfung mit hohem Risiko (mind. 2 Runden).
- Offene Entscheidung für die Analyse: F001 nur in `find_aliases` beheben (Ticket-Wortlaut) oder
  über einen gemeinsamen Lese-Helfer auch in `find_stale_aliases`/`find_removed_aliases`.
  Alternative: nur Ticket-Umfang, die beiden anderen als Hinweis im Ticket vermerken.
- Scoping: 3 Dateien (`alias_sync.py`, `setup.py`, Testdatei), erwartet 40–60 LoC.
- F002 `Kept`: nur `is_file()`-Einträge; hängender Symlink ist `is_file() == False`, daher entfällt er.
- Unlesbare Datei soll als `Kept` erscheinen, nicht verschwinden (sonst Zählung unvollständig).

## Analysis

### Type
Bugfix (Robustheit eines Werkzeugs), Folgearbeit aus #251. Keine sichtbare UI → keine Entwurfs-Vorschau nötig (nur Konsolenmeldungen).

### Root Cause (am Code belegt)
- F001: `alias_sync.py:94` `find_aliases` ruft `p.read_text()` ungeschützt; eine nicht UTF-8-lesbare oder nicht lesbare `.md` wirft `UnicodeDecodeError`/`OSError`, der ganze Lauf bricht ab, nichts wird entfernt.
  Derselbe Defekt in `find_stale_aliases` (Z.163) und `find_removed_aliases` (Z.192). Dort ist er schlimmer: `session_banner.py:153/178` fängt die Ausnahme per `except Exception: continue` und verwirft damit die Warnung für den GANZEN Scope, sobald eine einzelne Datei kaputt ist. `setup.py --refresh-aliases` (Z.1105/1113) stürzt ab.
- F002: `setup.py:1139` Kept-Liste per `glob("*.md")` ohne `is_file()` → Verzeichnisse `x.md` und hängende Symlinks erscheinen als Kept. `setup.py:1268`: `--global` ohne `--remove-aliases` wird stillschweigend ignoriert.
- F003: `_frontmatter_close` (Z.43) vergleicht Zeilen exakt mit `"---"`. `alias_content` zerlegt mit `split("\n")`, bei CRLF steht dort `"---\r"` → keine Erkennung, Marker landet auf Altposition. Leerzeichen hinter `---` genauso. `is_alias_file` nutzt `splitlines()` (CRLF ok), scheitert aber an Leerzeichen.

### Affected Files (with changes)
| File | Change Type | Description |
|------|-------------|-------------|
| core/hooks/alias_sync.py | MODIFY | Lese-Helfer `_read_or_none` (fängt OSError/UnicodeDecodeError → None), in allen drei `find_*` benutzt; `_frontmatter_close` vergleicht mit `rstrip()` |
| setup.py | MODIFY | Kept-Liste nur `is_file()`; Warnung auf stderr bei `--global` ohne `--remove-aliases` |
| tests/test_alias_robust_350.py | CREATE | je Teil ein Test (F001 inkl. Banner/Refresh-Pfad, F002 beide Fälle, F003 CRLF + Leerzeichen) |
| CHANGELOG.md | MODIFY | Eintrag unter [Unreleased] |

### Scope Assessment
- Files: 4 (davon 1 neu, 1 Doku)
- Estimated LoC: +~90 / -~6 (davon ~55 Tests)
- Risk Level: MEDIUM — `core/hooks/alias_sync.py` ist Hook-Verzeichnis (Gegenprüfung mind. 2 Runden), aber rein defensiv: Verhalten für lesbare Dateien bleibt gleich.

### Technical Approach (Empfehlung)
Regelweg, kein Modell nötig (trivial deterministisch). Gemeinsamer Lese-Helfer in `alias_sync.py`, in allen drei `find_*` verwendet. Unlesbare Datei = nie löschen, still überspringen (Vorbild `migrate_to_plugin.py:506`). Sie erscheint automatisch als `Kept`, weil sie eine Datei ist und nicht in `aliases` steckt — kein Sonderzweig in `setup.py` nötig. `_frontmatter_close`: `lines[0].rstrip() == "---"` und Suche des Schlusszeichens per Schleife mit `rstrip()`. Warnung: eine Zeile auf stderr, Exit-Code bleibt 0 (Warnung, kein Fehler — ein Abbruch würde bestehende Aufrufe brechen).

### Alternativen (bewusst geprüft)
1. Nur `find_aliases` fixen (Ticket-Wortlaut), die anderen zwei als Hinweis vermerken: kleiner (~10 LoC weniger), lässt aber den Banner-Defekt (ein kaputtes File blendet alle Warnungen des Scopes aus) und den `--refresh-aliases`-Absturz stehen. Verworfen: gleiche Ursache, gleiche Zeile, gleiche Testdatei.
2. `read_text(errors="replace")` statt Fangen: keine Ausnahme bei Kodierung, aber `PermissionError`/`OSError` bleibt ungefangen, und eine Fremddatei mit Marker würde gelöscht. Verworfen.
3. `--global` ohne `--remove-aliases` als harter Fehler (Exit 2) statt Warnung: sauberer, bricht aber Skripte, die das Flag bisher folgenlos mitgaben. Warnung gewählt; kein ADR betroffen.
4. Gar nichts tun / Ticket schließen: F003 ist im Repo nicht betroffen (alle Skills LF), F002 kosmetisch. Nur F001 hat echten Nutzerschaden; F002/F003 sind aber mit je 2–4 Zeilen billig und im Ticket zugesagt.

### Dependencies
`find_aliases` → nur `remove_command_aliases`. `find_stale_aliases` → `setup.py:1105`, `session_banner.py:153`. `find_removed_aliases` → `setup.py:1113`, `session_banner.py:178`. Bestehende Tests (`test_alias_remove_251`, `test_alias_marker_position_251`, `test_session_banner`, `test_bug_typ_entfernt_333`, `test_setup_alias_sync_150`) müssen grün bleiben.

### Open Questions
- [x] F001 nur `find_aliases` oder alle drei? → alle drei (Empfehlung oben, Henning kann Alternative 1 wählen).
- [ ] Keine PO-Frage offen.
