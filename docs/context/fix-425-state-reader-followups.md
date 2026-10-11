# Context: fix-425-state-reader-followups

## Request Summary
Drei Nebenbefunde der Gegenprüfung zu #422 beheben: Der Zustandsleser meldet bei
gleichzeitigem Ersetzen fälschlich einen harten Verweis (F001), der atomare Schreiber
scheitert an langen Zielnamen (F002), und ein Verweis-Fund beim Token-Schreiben ist für
den Nutzer unsichtbar (F003).

## Nachstellung (2026-10-11, Scratchpad `repro425.py`, Stand `bff54d5`)
- F001: 1 Leser + 4 Schreiber (`atomic_write_json`) → **132 von 500** Lesezugriffen
  werfen `UnsafeStateError` bei einer normalen Datei.
- F002: Ziel mit 240 Zeichen → `OSError 63 File name too long` aus `atomic_write_text`.
- F003: im Code belegt — `override_token._save_tokens` (Z. 64–69) schreibt nur auf stderr;
  `phase_listener` (Z. 483) meldet danach trotzdem „Override token created“.

## Related Files
| File | Relevance |
|------|-----------|
| `core/hooks/hook_utils.py:1500` `_read_state_bytes` | F001: `st_nlink != 1` → auch `nlink == 0` (Datei nach `os.fstat` bereits ersetzt/gelöscht) gilt als Verweis |
| `core/hooks/hook_utils.py:1557` `_atomic_write_at` | F002: `tmp = f".{name}.{16 hex}.tmp"` → +22 Zeichen auf den Zielnamen (NAME_MAX 255) |
| `core/hooks/hook_utils.py:1540` `_atomic_write_legacy` | Vergleich: `mkstemp(suffix=".tmp")` erzeugt kurze Namen — nicht betroffen |
| `core/hooks/override_token.py:64` `_save_tokens` | F003: fängt `UnsafeStateError`, druckt auf stderr, Aufrufer erfährt nichts |
| `core/hooks/override_token.py:105` `create_token` | einziger produktiver Aufrufer von `_save_tokens` neben `remove_token` |
| `core/hooks/phase_listener.py:376` `_create_override_token` | ruft `create_token`; Fallback-Zweig (ImportError) meldet bereits per `_notify` |
| `core/hooks/phase_listener.py:478–483` | meldet „Override token created“ bedingungslos |
| `core/hooks/phase_listener.py:144` `_notify` | Weg, auf dem Meldungen als `systemMessage` beim Nutzer ankommen |
| `tests/test_state_files_source_422.py` | Bestandstests #422 (Verweise, Schreiber, Normalfall) — müssen grün bleiben |
| `tests/test_state_reader_source_416.py` | Bestandstests #416 (Leserkern, harter Verweis nlink 2) — müssen grün bleiben |

## Existing Patterns
- Leser prüfen per dir_fd-Walk + `O_NOFOLLOW` + `fstat` auf demselben fd (kein TOCTOU).
- `UnsafeStateError` erbt bewusst nicht von `OSError`/`ValueError` (darf nicht verschluckt werden).
- Meldungen an den Nutzer im UserPromptSubmit-Hook laufen über `_notify` → `_finish` (JSON `systemMessage`).
- Tests nutzen `tmp_path` + parametrisierte Verweis-Richtungen (`richtung`).

## Dependencies
- Upstream: `os.open`/`os.fstat`/`os.replace` mit `dir_fd`; POSIX-Semantik: nach `rename`
  über eine offene Datei hat deren Inode `st_nlink == 0`.
- Downstream von `_read_state_bytes`: alle Kern-Gates (edit_gate, bash_gate, phase_listener,
  footer_gate, post_bash, post_implementation_gate, session_singleton_guard, workflow,
  adversary_dialog, override_token) über `read_state_json` / `read_state_text`.
- Downstream von `_atomic_write_at`: `atomic_write_json` / `atomic_write_text` mit `root`.
- Downstream von `_save_tokens`: `create_token`, `remove_token`.

## Existing Specs
- `docs/specs/fix-416-state-reader-source-check.md` — Leserkern
- `docs/specs/fix-422-state-files-source-check.md` — übrige Zustandsdateien, atomarer Schreiber
- Gegenprüfung mit F001–F003: `docs/artifacts/fix-422-state-files-source-check/adversary-dialog.md`

## Erste Analyse (kurz, Summe 3)
- F001: `nlink == 0` ist kein Verweis — die Datei hat dann gar keinen Namen mehr, ein
  Angreifer kann darüber nichts umlenken. Zwei Wege: (a) nur `nlink > 1` melden und den
  gelesenen (alten, konsistenten) Inhalt liefern; (b) bei `nlink == 0` einmal neu öffnen,
  damit der aktuelle Stand gelesen wird. (b) liefert frischere Daten, (a) ist einfacher;
  beide schließen den Fehlalarm. Entscheidung in der Spec.
- F002: kurzer fester Präfix statt Zielname, z. B. `.tmp.<16 hex>` (21 Zeichen, unabhängig
  vom Ziel). Aufräumen nach Fehlschlag bleibt wie heute.
- F003: `_save_tokens` gibt das Scheitern an den Aufrufer weiter (Exception oder Rückgabewert),
  `create_token` reicht es durch, `_create_override_token` meldet per `_notify` und die
  Erfolgsmeldung „Override token created“ entfällt in dem Fall.

## Risks & Considerations
- `_read_state_bytes` ist Kern aller Gates: Lockerung darf harte Verweise (`nlink >= 2`)
  nicht freigeben — #416/#422-Tests bleiben Pflicht.
- F001-Test ist nebenläufig → muss deterministisch rot sein (z. B. Datei nach dem Öffnen
  gezielt ersetzen statt auf Wettlauf zu hoffen).
- F003 ändert die Signatur-Semantik von `create_token`/`_save_tokens`; `remove_token`-Aufrufer
  (heute keine produktiven außerhalb `override_token.py`) dürfen nicht neu crashen.
- Hook-Code → Adversary mit 2 Runden; CHANGELOG `[Unreleased]`, keine Versionsanhebung.

## Analysis

### Type
Bug (drei fail-closed/kosmetische Nebenbefunde aus #422)

### Recherche (2026-10-11)
- `st_nlink` einer offenen, per `rename`/`unlink` ersetzten Datei: ext4/xfs/APFS melden 0,
  ramfs/shmem teils 1, NFS uneinheitlich ([LKML 2011](https://lkml.iu.edu/hypermail/linux/kernel/1103.0/01178.html),
  [LWN](https://lwn.net/Articles/432429/)). 0 = Inode ohne Namen → kein Verweis; nur `> 1` ist ein zweiter Name.
- macOS/APFS: NAME_MAX 255 Bytes je Pfadkomponente → ENAMETOOLONG
  ([Apple Forum](https://developer.apple.com/forums/thread/726970)).

### Affected Files (with changes)
| File | Change Type | Description |
|------|-------------|-------------|
| `core/hooks/hook_utils.py` | MODIFY | F001: `_read_state_bytes` teilen in `_open_state_fd` + neu `_read_checked_fd(fd, path)`; Bedingung `st_nlink > 1`. F002: tmp-Name `.<16hex>.tmp` (21 Zeichen, zielunabhängig, endet weiter auf `.tmp`) |
| `core/hooks/override_token.py` | MODIFY | F003: `_save_tokens` fängt `UnsafeStateError` nicht mehr; `create_token`/`remove_token` reichen durch |
| `core/hooks/phase_listener.py` | MODIFY | F003: `_create_override_token` fängt `UnsafeStateError`, meldet per `_notify`, gibt `bool` zurück; „Override token created“ nur bei Erfolg (auch Fallback-Zweig) |
| `tests/test_state_followups_425.py` | CREATE | je Teil ein RED-Test + Gegenproben (nlink 2 weiter Fund, nlink 1 ok) |
| `CHANGELOG.md` | MODIFY | `[Unreleased]`-Eintrag, keine Versionsanhebung |

### Scope Assessment
- Files: 4 Code/Test + CHANGELOG (+ Spec)
- Estimated LoC: ca. +170/-15 (Code ~50, Tests ~110, CHANGELOG ~6)
- Risk Level: MEDIUM — `_read_state_bytes` ist Kern aller Gates; Lockerung darf `nlink >= 2` nicht freigeben

### Technical Approach
- **F001 Weg (a), empfohlen:** nur `nlink > 1` als harten Verweis melden, bei 0 den gelesenen Inhalt
  des alten Inodes liefern. Konsistent, weil Schreiber nur per `os.replace` ersetzen — entspricht einem
  Lesen kurz vor dem Ersetzen. Gates sind ohnehin Momentaufnahmen.
  **Alternative (b):** bei `nlink == 0` einmal neu öffnen (frischerer Stand), ~20 Zeilen mehr, Zähler,
  Restfall beim zweiten Öffnen. Nur nötig, wenn Gates nie einen Stand älter als das letzte Ersetzen sehen dürfen.
- **F001-Test deterministisch:** `fd = _open_state_fd(p, root)` → `os.replace(neu, p)` → `assert fstat(fd).st_nlink == 0`
  → `_read_checked_fd(fd, p)` liefert alten Inhalt (vor Fix rot). Gegenprobe `os.link` → nlink 2 → `UnsafeStateError`.
  Naht durch normalen Split, kein Testhaken im Produktivcode.
- **F002:** Ziel mit 255 Zeichen schreiben + lesen, kein `.tmp`-Rest. Bestandstest
  `test_state_files_source_422.py:771` (`endswith(".tmp")`) bleibt grün.
- **F003:** Exception statt bool aus `_save_tokens` (bool ließe sich wieder still ignorieren; `UnsafeStateError`
  erbt bewusst nicht von `OSError`). Test: Verweis auf die Token-Datei bzw. Ordnerkette,
  `phase_listener` mit „override“ → Warnung als `systemMessage`, keine Erfolgsmeldung.
- Reihenfolge: F002 → F001 → F003 → CHANGELOG → Vollsuite → Adversary (2 Runden, Hook-Code).

### Dependencies
- Aufrufer `create_token`: nur `phase_listener.py:380`; `remove_token`: kein produktiver Aufrufer.
- `tests/test_state_files_source_422.py:655` (SCHREIBER) erlaubt `UnsafeStateError` ausdrücklich → bleibt grün.
- Bestandstests #416/#422 (`nlink == 2`) bleiben Pflicht.

### Bewusst ausgenommen
- `core/hooks/qa_gate.py:544` prüft ebenfalls `st_nlink != 1`, aber auf frisch per `O_CREAT` geöffneter
  Artefaktdatei (Schreiben, fail-closed, kein Wettlauf mit eigenen Schreibern). Nicht Teil von #425; in Spec vermerken.

### Open Questions
- keine (Weg (a) vs. (b) ist Tech-Lead-Entscheidung: (a))
