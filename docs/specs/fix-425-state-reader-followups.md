---
entity_id: fix-425-state-reader-followups
type: bugfix
created: 2026-10-11
updated: 2026-10-11
status: draft
workflow: fix-425-state-reader-followups
version: "1.0"
tags: [state-integrity, hook-utils, hardlink, atomic-write, override-token, follow-up]
test_targets: ["tests/test_state_followups_425.py"]
---

# Folgebefunde aus #422: Fehlalarm beim Ersetzen, lange Zielnamen, unsichtbarer Token-Fehler — #425

## Approval

- [ ] Approved

## GitHub Issue

- **Issue:** #425 (Nebenbefunde F001–F003 der Gegenprüfung zu #422). Die Dateien selbst und die Verweis-Richtungen sind in #416 und #422 geregelt und nicht Teil dieser Spec.

## Purpose

Die Gegenprüfung zu #422 hat drei Nebenbefunde hinterlassen. Alle drei sind am Stand `bff54d5` nachgestellt bzw. im Code belegt (2026-10-11, Scratchpad `repro425.py`).

- **F001 — Fehlalarm beim gleichzeitigen Ersetzen.** `_read_state_bytes` meldet jeden Wert `st_nlink != 1` als harten Verweis. Ersetzt ein Schreiber die Datei per `os.replace`, nachdem der Leser sie geöffnet hat, hat der geöffnete Inode keinen Namen mehr und meldet `st_nlink == 0`. Das ist kein Verweis, wird aber als einer behandelt. Messung: 1 Leser gegen 4 Schreiber (`atomic_write_json`) ergab **132 von 500** Lesezugriffen mit `UnsafeStateError` bei einer ganz normalen Datei. Folge: Gates sperren zufällig (fail-closed, aber ein Fehlalarm, der Arbeit blockiert).
- **F002 — Lange Zielnamen.** `_atomic_write_at` baut den tempfile-Namen als `.<ziel>.<16 hex>.tmp`, also Zielname plus 22 Zeichen. Ab 234 Zeichen im Ziel überschreitet das `NAME_MAX` (255): `OSError 63 File name too long` aus `atomic_write_text` (nachgestellt mit 240 Zeichen).
- **F003 — Unsichtbarer Token-Fehler.** `override_token._save_tokens` fängt `UnsafeStateError` und schreibt nur auf stderr. `phase_listener` meldet danach trotzdem „Override token created“. Der Nutzer glaubt an eine Freigabe, die nie geschrieben wurde.

Die Lösung bleibt regelbasiert (Dateisystem-Metadaten), ohne Modell, ohne neue Abhängigkeit. Ohne Modell geht es hier trivial, weil es um `fstat`-Werte, Namenslängen und Rückgabewege geht.

## Source

- **Analyse:** `docs/context/fix-425-state-reader-followups.md` (Abschnitte „Nachstellung“, „Analysis“, „Technical Approach“, „Bewusst ausgenommen“)
- **Ursprungsanfrage:** GitHub-Issue #425
- **Gegenprüfungsquelle der Befunde:** `docs/artifacts/fix-422-state-files-source-check/adversary-dialog.md`
- **Vorbild:** `docs/specs/fix-422-state-files-source-check.md` und `docs/specs/fix-416-state-reader-source-check.md`
- **Recherche:** Eine offene Datei, deren Name per `rename`/`unlink` ersetzt wurde, meldet `st_nlink == 0` (ext4/xfs/APFS; ramfs/shmem teils 1, NFS uneinheitlich), siehe [LKML 2011](https://lkml.iu.edu/hypermail/linux/kernel/1103.0/01178.html) und [LWN](https://lwn.net/Articles/432429/). 0 bedeutet Inode ohne Namen, also kein Verweis; nur `> 1` ist ein zweiter Name. Unter macOS/APFS gilt `NAME_MAX` 255 Bytes je Pfadkomponente, Überschreiten ergibt `ENAMETOOLONG` ([Apple Forum](https://developer.apple.com/forums/thread/726970)).

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `core/hooks/hook_utils.py` (`_open_state_fd`, `_read_state_bytes`, `_atomic_write_at`, `_atomic_write_legacy`, `UnsafeStateError`) | Modul | Leserkern und sicherer Schreiber aus #416/#422; dort liegen F001 und F002 |
| `core/hooks/override_token.py` (`_save_tokens`, `create_token`, `remove_token`) | Modul | F003; `create_token` hat als produktiven Aufrufer nur `phase_listener`, `remove_token` keinen |
| `core/hooks/phase_listener.py` (`_create_override_token`, `_notify`) | Modul | F003; Meldungsweg zum Nutzer als `systemMessage` |
| `tests/test_state_files_source_422.py` | Test | Bestandstests (u. a. SCHREIBER-Test um Z. 655, `.tmp`-Test um Z. 771); müssen grün bleiben |
| `tests/test_state_reader_source_416.py` | Test | Bestandstests Leserkern inkl. harter Verweis mit `nlink == 2`; müssen grün bleiben |
| Downstream von `_read_state_bytes` | Kern-Gates | edit_gate, bash_gate, phase_listener, footer_gate, post_bash, post_implementation_gate, session_singleton_guard, workflow, adversary_dialog, override_token (über `read_state_json`/`read_state_text`) |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| `core/hooks/hook_utils.py` | MODIFY | F001: `_read_state_bytes` teilen in `_open_state_fd` (unverändert) und neue `_read_checked_fd(fd, path)`; Bedingung `st_nlink > 1`. F002: tmp-Name in `_atomic_write_at` zielunabhängig `.<16hex>.tmp` |
| `core/hooks/override_token.py` | MODIFY | F003: `_save_tokens` fängt `UnsafeStateError` nicht mehr; `create_token` und `remove_token` reichen durch |
| `core/hooks/phase_listener.py` | MODIFY | F003: `_create_override_token` fängt `UnsafeStateError`, meldet per `_notify`, gibt `bool` zurück; „Override token created“ nur bei Erfolg |
| `tests/test_state_followups_425.py` | CREATE | je Teil ein RED-Test plus Gegenproben (nlink 2 weiter Fund, nlink 1 unverändert, Normalfall Erfolgsmeldung) |
| `CHANGELOG.md` | MODIFY | Eintrag unter `[Unreleased]`, keine Versionsanhebung |

### Estimated Changes

- Files: 4 Code/Test plus CHANGELOG (liegt innerhalb der Grenze von 4-5 Dateien).
- LoC: ca. +170/-15 (Code ca. 50, Tests ca. 110, CHANGELOG ca. 6); innerhalb von ±250. Spec, Kontext und Briefing zählen im LoC-Gate zusätzlich als Code (#294, Fehlalarm).
- Alle Funktionen bleiben unter 50 Zeilen.
- Risiko mittel: `_read_state_bytes` ist Kern aller Gates; die Lockerung darf `nlink >= 2` nicht freigeben (Gegenproben AC-2, AC-3).

## Implementation Details

**1. F001: Öffnen und Prüfen trennen.** `_read_state_bytes(path, root)` ruft `_open_state_fd(path, root)` und übergibt den Deskriptor an die neue Funktion `_read_checked_fd(fd, path)` (schließt `fd` selbst). Diese macht `fstat`, prüft `S_ISREG`, liest die Bytes. Die Bedingung wird von `st_nlink != 1` zu `st_nlink > 1`: Nur ein zweiter Name ist ein harter Verweis und ergibt weiter `UnsafeStateError(path, "harter Verweis, Linkzahl N")`. Bei `st_nlink == 0` (Datei nach dem Öffnen ersetzt) wird der gelesene Inhalt des alten Inodes geliefert. Das ist konsistent, weil Schreiber ausschließlich per `os.replace` ersetzen; der Leser sieht dann den vollständigen Stand von kurz vor dem Ersetzen, nie einen halben. Gates sind ohnehin Momentaufnahmen. Der Split ist die Naht für den Test: `fd = _open_state_fd(...)`, `os.replace(neu, p)`, dann `_read_checked_fd(fd, p)`, ohne Testhaken im Produktivcode und ohne auf einen Wettlauf zu hoffen.

**2. F002: kurzer fester tmp-Name.** In `_atomic_write_at` wird `tmp = f".{name}.{os.urandom(8).hex()}.tmp"` zu `tmp = f".{os.urandom(8).hex()}.tmp"` (21 Zeichen, unabhängig vom Ziel). Das tempfile liegt weiter im geprüften Ordner-Deskriptor, wird weiter mit `O_CREAT|O_EXCL|O_NOFOLLOW` angelegt und endet weiter auf `.tmp` (Bestandstest). Das Aufräumen nach Fehlschlag bleibt wie heute. `_atomic_write_legacy` ist nicht betroffen (`mkstemp(suffix=".tmp")` erzeugt kurze Namen).

**3. F003: Fehler sichtbar machen.** `_save_tokens` ruft nur noch `atomic_write_json(..., root=find_project_root())`; der `try/except UnsafeStateError` samt stderr-Ausgabe entfällt, die Ausnahme läuft durch. `create_token` und `remove_token` reichen sie unverändert weiter (Docstring nennt es). Eine Ausnahme statt eines `bool`, weil ein Rückgabewert sich wieder still ignorieren ließe; `UnsafeStateError` erbt bewusst nicht von `OSError`/`ValueError` und wird nicht versehentlich verschluckt. `phase_listener._create_override_token` fängt `UnsafeStateError` aus `create_token`, meldet per `_notify("WARNUNG: Override-Token nicht geschrieben: ...")` und gibt `False` zurück, sonst `True`. Der Fallback-Zweig (ImportError) gibt `False` zurück, wo sein vorhandener `except UnsafeStateError` bereits per `_notify` warnt, und `True` nach erfolgreichem Schreiben. Der Aufrufer (um Z. 482) ruft die Erfolgsmeldung „Override token created for workflow: ...“ nur auf, wenn der Rückgabewert `True` ist.

**4. Reihenfolge der Umsetzung:** F002, F001, F003, CHANGELOG, Vollsuite, Adversary (Hook-Code, zwei Runden).

## Expected Behavior

- **Input:** Lesen einer Zustandsdatei, die zwischen Öffnen und `fstat` ersetzt wird; Schreiben einer Zustandsdatei mit langem Namen; „override“ des Nutzers bei unsicherem Token-Pfad.
- **Output:** Normale Datei, auch wenn sie gerade ersetzt wurde: der Inhalt wird geliefert, kein `UnsafeStateError`. Harter Verweis (`nlink >= 2`), Symlink in der Kette oder keine normale Datei: unverändert `UnsafeStateError`. Ziele bis 255 Zeichen sind schreib- und lesbar, ohne `.tmp`-Rest. Bei Verweis auf die Token-Datei oder ihre Ordnerkette erscheint beim Nutzer eine Warnung, und es gibt keine Erfolgsmeldung; im Normalfall erscheint die Erfolgsmeldung wie bisher.
- **Side effects:** Keine neuen Subprozesse, Abhängigkeiten, Config-Keys, State-Formate oder Dateipfade. Die Signaturen von `create_token`/`remove_token` bleiben; sie werfen jetzt `UnsafeStateError` (einziger produktiver Aufrufer ist `phase_listener`, der sie fängt). Der Name des tempfile ändert sich, das Format der Zieldatei nicht.

## Known Limitations

- **Ersetzen nach dem Öffnen liefert den Stand von davor.** Ein Gate kann einen Inhalt sehen, der einen Augenblick älter ist als der aktuelle Stand. Für Momentaufnahmen in Gates unschädlich, ein späterer Aufruf sieht den neuen Stand.
- **Ersetzter Inode nicht von gelöschter Datei unterscheidbar:** `nlink == 0` sagt nicht, ob jemand die Datei ersetzt oder gelöscht hat. Auch dann wird der alte, vollständig gelesene Inhalt geliefert; die Gegenseite (Link anlegen, schreiben, Link löschen) ist schon in #416/#422 als Known Limitation benannt und bleibt bestehen.
- **Dateisysteme mit `nlink == 1` nach dem Ersetzen (ramfs/shmem, teils NFS):** Diese Fälle waren auch vorher kein Fehlalarm und bleiben unverändert.
- **`core/hooks/qa_gate.py:544` bewusst ausgenommen:** Dort steht ebenfalls `st_nlink != 1`, aber auf einer frisch per `O_CREAT` geöffneten Artefaktdatei. Das ist ein Schreibpfad, fail-closed, ohne Wettlauf mit eigenen Schreibern, und nicht Teil von #425.
- Die Known Limitations aus #416/#422 (Link anlegen, schreiben, löschen; direktes Schreiben ohne Link; `settings.local.json` ungeprüft) gelten unverändert weiter.
- Verteilung: wirkt in Konsumentenprojekten erst nach dem Plugin-Update.

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] F001, F002 und F003 sind je durch einen vorher roten, danach grünen automatischen Test belegt (RED-Artefakte registriert)
- [ ] Harte Verweise (`nlink >= 2`) lösen weiter `UnsafeStateError` aus (gezielte Gegenprobe), Bestandstests aus #416 und #422 sind unverändert grün
- [ ] Die Vollsuite ist grün
- [ ] `core/hooks/qa_gate.py:544` ist als bewusst ausgenommen in Spec und CHANGELOG-Eintrag benannt
- [ ] `CHANGELOG.md` ist unter `[Unreleased]` aktualisiert, ohne Versionsanhebung
- [ ] Adversary-Dialog (zwei Runden, Hook-Code) hat VERIFIED mit gültigem Artefakt

## Acceptance Criteria

Testdatei: `tests/test_state_followups_425.py`. Die Bestandstests aus #416/#422 laufen unverändert mit.

- **AC-1:** Given eine normale Zustandsdatei, die nach dem Öffnen des Deskriptors per `os.replace` durch neuen Inhalt ersetzt wurde (`fstat(fd).st_nlink == 0`) / When `_read_checked_fd(fd, path)` sie liest / Then liefert sie den Inhalt des alten Inodes ohne `UnsafeStateError`; deterministisch, ohne Wettlauf (vor der Änderung rot)
  - Test: tests/test_state_followups_425.py::test_f001_nlink0_liefert_alten_inhalt
- **AC-2:** Given eine Datei mit einem zweiten harten Verweis (`os.link`, `st_nlink == 2`) / When `_read_checked_fd` bzw. `_read_state_bytes` sie liest / Then wird weiter `UnsafeStateError` mit „harter Verweis, Linkzahl 2“ geworfen (Gegenprobe, Lockerung gibt nichts frei)
  - Test: tests/test_state_followups_425.py::test_f001_nlink2_bleibt_unsafe_state_error
- **AC-3:** Given eine normale Datei mit `st_nlink == 1` und ein Verzeichnis statt Datei / When `_read_state_bytes` liest / Then liefert die Datei ihren Inhalt und das Verzeichnis wirft weiter `UnsafeStateError` („keine normale Datei“); `_read_state_bytes` bleibt die Summe aus `_open_state_fd` und `_read_checked_fd`
  - Test: tests/test_state_followups_425.py::test_f001_normaldatei_und_verzeichnis_wie_bisher
- **AC-4:** Given ein Ziel mit einem 255 Zeichen langen Dateinamen unter `.claude` / When `atomic_write_text` und `atomic_write_json` mit `root` schreiben und `read_state_text` bzw. `read_state_json` zurücklesen / Then gelingt beides ohne `OSError` und der Inhalt stimmt (vor der Änderung `OSError 63`)
  - Test: tests/test_state_followups_425.py::test_f002_ziel_mit_255_zeichen_ist_schreib_und_lesbar
- **AC-5:** Given erfolgreiche und fehlgeschlagene Schreibvorgänge (Ziel mit 255 Zeichen; Fehler beim Schreiben der Nutzlast) / When sie abgeschlossen sind / Then bleibt im Ordner kein `*.tmp`-Rest zurück, und der tmp-Name ist zielunabhängig (`.` plus 16 Hex-Zeichen plus `.tmp`, 21 Zeichen, endet auf `.tmp`)
  - Test: tests/test_state_followups_425.py::test_f002_kein_tmp_rest_und_tmp_name_zielunabhaengig
- **AC-6:** Given die Token-Datei oder ein Ordner ihrer Kette ist ein Verweis (Richtungen aus `RICHTUNGEN`) / When `override_token.create_token` aufgerufen wird / Then wirft es `UnsafeStateError` (nicht mehr nur eine stderr-Zeile), und das Verweisziel bleibt byte-gleich
  - Test: tests/test_state_followups_425.py::test_f003_create_token_wirft_bei_verweis
- **AC-7:** Given dieselbe Lage mit einem vorhandenen gültigen Token / When `override_token.remove_token` aufgerufen wird / Then reicht es `UnsafeStateError` ebenfalls durch und verändert das Verweisziel nicht
  - Test: tests/test_state_followups_425.py::test_f003_remove_token_wirft_bei_verweis
- **AC-8:** Given die Token-Datei ist ein Verweis / When `phase_listener` als echter Subprozess die Nutzer-Nachricht „override“ erhält / Then enthält die `systemMessage` eine Warnung („Override-Token nicht geschrieben“), enthält **nicht** „Override token created“, und der Hook endet ohne Traceback
  - Test: tests/test_state_followups_425.py::test_f003_phase_listener_override_mit_verweis_warnt_ohne_erfolgsmeldung
- **AC-9:** Given eine normale, schreibbare `.claude`-Struktur / When `phase_listener` „override“ erhält / Then enthält die `systemMessage` „Override token created for workflow: ...“, keine Warnung, und `has_valid_token` liefert `True` (Normalfall wie heute)
  - Test: tests/test_state_followups_425.py::test_f003_phase_listener_override_normalfall_meldet_erfolg
- **AC-10:** Given der Import-Fallback von `_create_override_token` (Import von `override_token` schlägt fehl) / When die Token-Datei ein Verweis ist bzw. normal ist / Then gibt `_create_override_token` im ersten Fall `False` zurück und warnt, im zweiten `True`; die Erfolgsmeldung erscheint nur im zweiten
  - Test: tests/test_state_followups_425.py::test_f003_import_fallback_erfolgsmeldung_nur_bei_erfolg
- **AC-11:** Given der bestehende Testbestand / When `tests/test_state_reader_source_416.py`, `tests/test_state_files_source_422.py` und die Vollsuite laufen / Then bleiben sie grün (u. a. `nlink == 2` bleibt Fund, tmp-Name endet auf `.tmp`, SCHREIBER-Test erlaubt weiter `UnsafeStateError`)
  - Test: tests/test_state_reader_source_416.py und tests/test_state_files_source_422.py (unverändert, Lauf grün)
- **AC-12:** Given `CHANGELOG.md` / When er gelesen wird / Then enthält `[Unreleased]` einen Eintrag zu #425 (F001–F003) mit dem Vermerk, dass `qa_gate.py:544` bewusst ausgenommen ist, und es gibt keine Versionsanhebung
  - Test: tests/test_state_followups_425.py::test_changelog_nennt_425_und_qa_gate_ausnahme
- **AC-13:** Given eine normale Zustandsdatei, die vier parallele Schreiber per `atomic_write_json` fortlaufend ersetzen (DoD des Issues: „Leser + paralleler Ersetzer ohne Fehlalarm“) / When ein Leser sie 500-mal über `read_state_json` liest / Then tritt kein einziger `UnsafeStateError` auf, und jeder gelesene Inhalt ist ein vollständiger Stand eines Schreibers (vor der Änderung rot: in der Nachstellung 132 von 500 Fehlalarmen; nach der Änderung deterministisch grün, weil `nlink == 0` nie mehr auslöst)
  - Test: tests/test_state_followups_425.py::test_f001_paralleler_ersetzer_ohne_fehlalarm

> Die Test-Zuordnung wird **bei der Spec-Erstellung** eingetragen, nicht nachträglich:
> Nach der Freigabe ist diese Datei eingefroren (#230) — jede Änderung verschiebt den
> PO-Briefing-Hash und blockt den Workflow-Abschluss. Stimmt der Testname später nicht
> mehr, gehört die Korrektur in die TDD-RED-Artefakte (`workflow.py add-artifact`),
> nicht in diese Datei.

## Test Plan

### Automated Tests (TDD RED)

Datei: `tests/test_state_followups_425.py`; Hilfen und `RICHTUNGEN` aus `tests/test_state_reader_source_416.py` bzw. `tests/test_state_files_source_422.py` wiederverwenden. Hooks als echte Subprozesse in einer Wegwerf-Sandbox.

- [ ] Test 1 (AC-1): GIVEN geöffneter fd, danach `os.replace`, WHEN `_read_checked_fd`, THEN alter Inhalt (RED vor Fix: `UnsafeStateError`; Split `_read_checked_fd` fehlt, RED zeigt zusätzlich die Naht)
- [ ] Test 2 (AC-2, AC-3): GIVEN `os.link` bzw. normale Datei bzw. Verzeichnis, WHEN gelesen, THEN `UnsafeStateError` bzw. Inhalt (müssen vor und nach der Änderung grün sein)
- [ ] Test 3 (AC-4, AC-5): GIVEN Ziel mit 255 Zeichen, WHEN geschrieben und gelesen, THEN gelingt, kein `.tmp`-Rest (RED: `OSError 63`)
- [ ] Test 4 (AC-6, AC-7): GIVEN Token-Datei bzw. Ordnerkette als Verweis, WHEN `create_token`/`remove_token`, THEN `UnsafeStateError`, Ziel byte-gleich (RED: wird still geschluckt)
- [ ] Test 5 (AC-8, AC-9, AC-10): GIVEN Verweis bzw. Normalfall, WHEN „override“ im Subprozess bzw. Fallback-Zweig, THEN Warnung ohne Erfolgsmeldung bzw. Erfolgsmeldung (RED: Erfolgsmeldung trotz Fehler)
- [ ] Test 1b (AC-13): GIVEN vier parallele Schreiber, WHEN 500 Lesezugriffe, THEN kein `UnsafeStateError` (RED vor Fix: Fehlalarme gezählt; ergänzt den deterministischen Test 1, ersetzt ihn nicht)
- [ ] Test 6 (AC-11, AC-12): GIVEN Bestand und CHANGELOG, WHEN Tests und Prüfung laufen, THEN grün

Die RED-Läufe werden als Artefakte registriert; der F001-Test muss deterministisch rot sein, nicht nebenläufig.

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Die Änderung korrigiert Randfälle der in #416/#422 getroffenen Entscheidung („Prüfung an der Quelle per `dir_fd`-Walk in einer gemeinsamen Funktion“) und kippt keine bestehende ADR. Kein neues Format, keine neue Abhängigkeit, keine Migration.

**Entscheidung:** F001 Weg (a): nur `nlink > 1` ist ein harter Verweis, bei `nlink == 0` wird der gelesene Inhalt des alten Inodes geliefert. F002 ein zielunabhängiger kurzer tmp-Name. F003 Exception durchreichen, Meldung beim Aufrufer. Regelweg zuerst: Dateisystem-Metadaten und Namenslängen sind deterministisch.

**Alternativen (bewertet):**

- **F001 (b) — bei `nlink == 0` einmal neu öffnen:** liefert den frischeren Stand, kostet aber ca. 20 Zeilen mehr (Zähler, Restfall beim zweiten Öffnen, der wieder `nlink == 0` melden kann). Nötig wäre das nur, wenn Gates nie einen Stand älter als das letzte Ersetzen sehen dürfen; Gates sind aber Momentaufnahmen, und der Schreiber ersetzt ausschließlich atomar, der alte Inhalt ist also immer vollständig und konsistent. Verworfen. Würde (b) später nötig, kippt das keine ADR, nur diese Entscheidung.
- **F001 (c) — Leser und Schreiber mit einem Sperrmechanismus (flock) koppeln:** schließt den Wettlauf ganz, brächte aber Sperren in jeden Gate-Pfad, mit Deadlock- und Hängergefahr in Hooks, die bei jedem Tool-Aufruf laufen. Verworfen.
- **F002 — tmp-Name weiter aus dem Zielnamen ableiten, aber kürzen (z. B. auf 200 Zeichen):** mehr Logik und Randfälle für denselben Nutzen. Der feste kurze Name braucht keine Fallunterscheidung. Verworfen.
- **F003 — `bool` zurückgeben statt Exception:** ließe sich wieder still ignorieren, genau der heutige Fehler. Verworfen. **Alternative:** Meldung schon in `_save_tokens` über stderr belassen und nur die Erfolgsmeldung unterdrücken: der Nutzer sieht stderr der Hooks nicht zuverlässig. Verworfen.
- **Nichts tun:** F001 bleibt ein zufälliger Fehlalarm unter Last, F003 eine Falschmeldung an den Nutzer. Verworfen.

## Changelog

- 2026-10-11: Initial spec created (#425)
