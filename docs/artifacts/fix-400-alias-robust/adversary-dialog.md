# Adversary Dialog — fix-400-alias-robust
Spec: docs/specs/fix-400-alias-robust.md
Datum: 2026-10-08 11:56

## Checkliste
- [x] **Input:** Start-Hinweis (`refresh_home_aliases`) bzw. `setup.py --refresh-aliases` mit einem Kurzbefehl-Ordner, der neben normalen veralteten Kopien Symlinks oder schreibgeschützte Dateien enthält.
Status: CONFIRMED
Code reference: core/hooks/alias_sync.py:227
Evidence: Beide Aufrufer (`session_banner.py:160`, `setup.py:1293`) reichen `skipped` an `refresh_aliases` durch; Probeskript mit Symlink, 0444-Datei und 0555-Ordner liefert Meldungen statt Abbruch.
- [x] **Output:** Normale veraltete Kopien werden erneuert, Aliase entfernter Befehle gelöscht. Symlinks und nicht beschreibbare Dateien bleiben unverändert und werden als übersprungen gemeldet (Start-Hinweis: Zusatz bzw. eigene Zeile; CLI: `Skipped:`-Zeilen). Ein Problemfall stoppt die übrigen nie.
Status: CONFIRMED
Code reference: core/hooks/alias_sync.py:244
Evidence: Normale Kopie wird erneuert, entfernter Alias gelöscht, Symlink/0444/0555 bleiben byte-/rechtegleich und stehen in `skipped`.
- [x] **Side effects:** Keine neuen Dateien, keine Rechteänderungen, keine neuen Abhängigkeiten. Neu sind nur die Meldungen über Übersprungenes.
Status: CONFIRMED
Code reference: core/hooks/alias_sync.py:248
Evidence: Im Diff keine chmod-, Neuanlage- oder Import-Aufrufe; 0444-Rechte nach dem Lauf unverändert (`0o100444`).
- [x] **AC-1:** Given ein veralteter markierter Alias im Befehlsordner, der ein Symlink auf eine Datei außerhalb des Ordners ist / When `refresh_aliases` läuft / Then wird die Zieldatei nicht verändert (Inhalt identisch), der Symlink bleibt Symlink, der Name steht mit dem Grund `Symlink` in `skipped` und nicht in der Liste der erneuerten
Status: CONFIRMED
Code reference: core/hooks/alias_sync.py:248
Evidence: Ziel `ext/x.md` byte-gleich, `10-context: Symlink` in skipped, nicht in refreshed. Test `test_symlink_wird_nicht_beschrieben` PASSED.
- [x] **AC-2:** Given der Alias eines entfernten Befehls (z. B. `00-bug.md`, markiert), der ein Symlink ist / When `refresh_aliases` läuft / Then wird der Symlink nicht gelöscht, das Ziel bleibt unverändert, der Name steht in `skipped` und nicht in der Liste der gelöschten
Status: CONFIRMED
Code reference: core/hooks/alias_sync.py:264
Evidence: Symlink `00-bug.md` bleibt, Ziel unverändert, `00-bug: Symlink` (path.stem) in skipped. Test `test_symlink_als_entfernter_alias_wird_nicht_geloescht` PASSED.
- [x] **AC-3:** Given eine veraltete markierte Kopie mit Rechten 0444 (als Nicht-root), dazu eine weitere veraltete Kopie und ein Alias eines entfernten Befehls / When `refresh_aliases` läuft / Then bricht der Lauf nicht ab: die weitere Kopie ist erneuert, der entfernte Alias gelöscht, die 0444-Datei ist unverändert und steht mit Grund in `skipped`
Status: CONFIRMED
Code reference: core/hooks/alias_sync.py:258
Evidence: 0444-Kopie unverändert mit `10-alpha: schreibgeschützt`; weitere Kopie erneuert, `00-bug` gelöscht; auch bei 0555-Ordner läuft die Schleife weiter. Test `test_schreibgeschuetzte_datei_bricht_schleife_nicht_ab` PASSED.
- [x] **AC-4:** Given ein Aufruf von `refresh_aliases` ohne `skipped`-Parameter / When er läuft / Then liefert er weiterhin ein Zweier-Tupel `(erneuert, gelöscht)` mit unverändertem Inhalt für normale Dateien, und mit übergebener Liste wird diese gefüllt
Status: CONFIRMED
Code reference: core/hooks/alias_sync.py:215
Evidence: `skipped=None` wird von `_skip` abgefangen, Rückgabe bleibt Zweier-Tupel; Aufrufer-Grep: nur session_banner.py, setup.py und Tests. Test `test_rueckgabe_tupel_und_optionaler_skipped_parameter` PASSED.
- [x] **AC-5:** Given ein Home mit einer erneuerbaren Kopie und einer Problemdatei (Symlink bzw. 0444) / When `refresh_home_aliases` läuft / Then steht genau eine Zeile `Kurzbefehle aktualisiert (1) · 1 übersprungen` (Zählung nur Erfolge); bei ausschließlich Übersprungenen steht `Kurzbefehle: 1 übersprungen`; die erneuerte Datei ist auch bei Problemdatei erneuert
Status: CONFIRMED
Code reference: core/hooks/session_banner.py:167
Evidence: Wortlaut exakt `Kurzbefehle aktualisiert (N) · M übersprungen` bzw. `Kurzbefehle: M übersprungen`; Zählung nur Erfolge. Test `test_start_hinweis_zaehlt_erfolge_und_nennt_uebersprungene` PASSED.
- [x] **AC-6:** Given `setup.py --refresh-aliases` mit einem übersprungenen Eintrag (Symlink) und einer erneuerbaren Kopie / When der Aufruf als echter Prozess mit Test-Home läuft / Then endet er mit Exit 0, die Ausgabe enthält `  Skipped: ` mit dem Namen und dem Grund, `  Refreshed: ` für die erneuerte Kopie, und die Schlusszeile nennt `1 skipped`; ohne übersprungene Einträge bleibt die Schlusszeile `Command aliases: N refreshed, M removed, none created.`
Status: CONFIRMED
Code reference: setup.py:1301
Evidence: `  Skipped: <Eintrag>` je Eintrag, Schlusszeile mit `, K skipped.` nur bei K>0, sonst wortgleich wie bisher; echter Prozess mit Test-Home, Exit 0. Test `test_refresh_aliases_cli_meldet_uebersprungene` PASSED.
- [x] **AC-7:** Given der bestehende Testbestand / When die Regressionstests laufen / Then bleiben sie grün
Status: CONFIRMED
Code reference: core/hooks/session_banner.py:150
Evidence: Regressionsdateien 251, 150, 333, 350, session_banner, setup_command_aliases: 66 passed, 0 failed.

## Dialog

### Runde 1
**Adversary:** Ich greife die Schreib- und Löschpfade an: hängender Symlink, Symlink auf Verzeichnis, Symlink-Schleife, `commands_dir` als Symlink, Ordner 0555 beim `unlink`, 0444-Datei, kaputtes UTF-8 in SKILL.md zwischen `find_stale_aliases` und Lesen, Tupel-Rückgabe für andere Aufrufer, Doppelzählung in `skipped`, Wortlaut der Start-Hinweis-Zeilen. Tests: 55 passed. Die Kernfunktion hält (AC-1 bis AC-7), aber die Spec wird an zwei Stellen im Wortlaut verfehlt: Der Grund bei Schreibschutz ist `Permission denied` statt `schreibgeschützt`, der entfernte Alias heißt `00-bug.md` statt `00-bug`, und ein `UnicodeDecodeError` ist kein `OSError`. Fragen: Warum fehlen die Kurzgründe? Soll der Name `00-bug` oder `00-bug.md` heißen? Bleibt `UnicodeDecodeError` bewusst unbehandelt?
**Implementierer:** Die Kurzgründe fehlten, weil der Entwicklerauftrag sie nicht nannte, nicht aus Absicht. Behoben in `alias_sync.py`: `_reason(exc)` bildet `PermissionError` auf `schreibgeschützt` und jeden anderen Fehler auf `Fehler (<Fehlername>)` ab; Lesen der SKILL.md und Schreiben sind getrennt gefasst, ein Lesefehler (OSError oder UnicodeDecodeError) meldet `Skill nicht lesbar`; die Löschschleife meldet `path.stem`, `removed` behält `path.name`. Tests geschärft (`00-bug: Symlink`, `10-alpha: schreibgeschützt`, neuer Test für unlesbaren Skill-Text).

Finding:
  ID: F001
  Severity: MEDIUM
  Category: spec_violation
  Code reference: core/hooks/alias_sync.py:220
  Description: Der Grund bei Schreibschutz war der englische, OS-abhängige Text `Permission denied` statt des in der Spec genannten Kurzgrunds `schreibgeschützt`.
  Spec requirement: Implementation Details, Fehler pro Datei: `schreibgeschützt` für PermissionError, sonst `Fehler (<Fehlername>)`, `Skill nicht lesbar`
  Conflict: CLI zeigte `Skipped: 10-context: Permission denied`; der Test prüfte den Grund nicht.
  Remediation: `_reason(exc)` und Grund im Test festschreiben (umgesetzt).

Finding:
  ID: F002
  Severity: LOW
  Category: spec_violation
  Code reference: core/hooks/alias_sync.py:264
  Description: Der Name des entfernten Alias trug die Endung `.md` (`00-bug.md: Symlink`), die Erneuerungsschleife meldet ohne Endung.
  Spec requirement: Tabelle Expected Behavior: `skipped: 00-bug: Symlink`
  Conflict: Uneinheitliches Format.
  Remediation: `path.stem` melden (umgesetzt).

Finding:
  ID: F003
  Severity: LOW
  Category: edge_case
  Code reference: core/hooks/alias_sync.py:253
  Description: Ein `UnicodeDecodeError` beim Lesen der SKILL.md ist kein `OSError`; wird die Datei zwischen Suche und Lesen kaputt, brach der Lauf ab.
  Spec requirement: Fehler pro Datei: ein nicht lesbarer Skill-Text wird als `Skill nicht lesbar` gemeldet
  Conflict: Race-Fall brach die Schleife ab.
  Remediation: `except (OSError, UnicodeDecodeError)` (umgesetzt).

### Runde 2
**Adversary:** Probeskript erneut gelaufen: Symlink-Ziel byte-gleich, `10-context: Symlink`; Ordner 0555: `20-analyse` erneuert, `00-bug: schreibgeschützt`; Datei 0444: Rechte `0o100444`, `10-context: schreibgeschützt`; kaputtes UTF-8 in SKILL.md: kein Abbruch, `10-context: Skill nicht lesbar`; hängender Symlink, Symlink auf Verzeichnis und Schleife werden nie angefasst. Handler-Reihenfolge: Lesen und Schreiben getrennt, `PermissionError` wird in `_reason` vor dem generischen Fall geprüft; `FileNotFoundError` im Race wird zu `Fehler (FileNotFoundError)`. Tests: 66 passed. F001 bis F003 sind behoben, keine offenen Findings. Hinweis (nicht blockierend): Der generische `Fehler (...)`-Zweig ist nicht durch einen eigenen Test gepinnt.
**Implementierer:** Bestätigt; der generische Zweig ist ein Einzeiler im selben Helfer und wird über die Probeläufe belegt. Kein weiterer Fix nötig.

## Herkunft der Vorbedingungen

kein Sprachprofil konfiguriert (`precondition_origins.default_lang`)

## Verdict

Alle 10 Punkte (Input, Output, Side effects, AC-1 bis AC-7) sind CONFIRMED. Die Befunde F001 bis F003 aus Runde 1 sind im Code behoben und in Runde 2 bestätigt.

Tests: 66 passed, 0 failed, 0 übersprungen
Edge cases: Alle geprüft, nichts gebrochen
Regressions: None found
Checklist: 10/10 points proven

VERDICT: VERIFIED

## Geprüfte Dateien

- sha256:adfb53e8de9f830e9bcfbecebfc93f9faf2701fda4f26685d9807966d6c3e096  core/hooks/alias_sync.py
- sha256:887f1c17eecc824b005d6028526a0e697b019d231680036f69549d4c474f8c33  core/hooks/session_banner.py
- sha256:d0798571ba851cb7a1cbd6ba41ebab43a1de5a6b98e56d9077b74620ef6a0b27  setup.py

## Prüfbasis

- base: 0e9501f5c2f9baf5e22de52d43af85b9a1abf368
- blob:4565fcc56d7c3dcd7fb96e51bd8ae2fc490bd9b3  core/hooks/alias_sync.py
- blob:6929c83fb6dd475d555c7337f1fc63a662100f76  core/hooks/session_banner.py
- blob:deed6c44dc1232f3b4d87507287db5b2fd0ce869  setup.py
