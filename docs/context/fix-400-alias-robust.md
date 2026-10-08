# Context: fix-400-alias-robust

## Request Summary
Issue #400: Die automatische Kurzbefehl-Wartung (`alias_sync.refresh_aliases`, beim Start und per `setup.py --refresh-aliases`) soll in ihrem Schreibbereich bleiben (Symlinks) und sich von einer einzelnen Datei nicht stoppen lassen (0444).

## Related Files
| File | Relevance |
|------|-----------|
| core/hooks/alias_sync.py:215-235 | `refresh_aliases`: `write_text` (Z. 230) folgt Symlinks; `unlink` (Z. 234); kein try/except pro Datei, Schleife bricht beim ersten Fehler ab |
| core/hooks/alias_sync.py:153-194 | `find_stale_aliases`: nimmt Symlinks auf (`is_file()` folgt ihnen) |
| core/hooks/alias_sync.py:197-212 | `find_removed_aliases`: gleiches Verhalten |
| core/hooks/alias_sync.py:53-58 | `_read_or_none`: bestehendes Muster fuer fehlertolerantes Lesen (#350) |
| core/hooks/session_banner.py:150-167 | `refresh_home_aliases`: faengt alles mit `except Exception: return []` — bei Fehler Zeile weg, auch fuer bereits erneuerte Dateien |
| setup.py:1275-1300 | `--refresh-aliases`: gibt Refreshed/Removed aus, kennt keine uebersprungenen Dateien |
| tests/test_session_banner.py | bestehende Tests zu `refresh_home_aliases` (#399) |

## Existing Patterns
- #350: Lesefehler werden zu `None` und die Datei still uebergangen.
- Rueckgabe von `refresh_aliases` ist ein Tupel `(erneuert, geloescht)`; zwei Aufrufer (setup.py, session_banner.py).

## Dependencies
- Upstream: nur `pathlib`.
- Downstream: Start-Hinweis jeder Sitzung, `setup.py --refresh-aliases`.

## Existing Specs
- Keine eigene Spec; Herkunft #399 (`docs/artifacts/fix-399-start-wartung/adversary-dialog.md`, F001/F002).

## Entscheidungsvorschlag (fuer /20-analyse)
- Symlink-Weg A (ueberspringen) ist einfacher und braucht keine Pfadlogik. Weg B (aufloesen, nur schreiben wenn Ziel unter `commands_dir`) erhaelt Dotfiles-Setups, die auf Framework-Kopie zeigen, aber ein Ziel im selben Ordner ist selten der Fall; Ziel ausserhalb waere ohnehin uebersprungen. Empfehlung: A.
- Rueckgabe erweitern um dritte Liste `skipped` (Namen), beide Aufrufer anpassen — Rueckgabe-Aenderung betrifft Tests, die zweistellig entpacken.

## Risks & Considerations
- Rueckgabe-Signatur aendern bricht bestehende Entpackungen (`refreshed, removed = ...`) in Tests; Alternative: Ergebnisobjekt oder zweiter Parameter `skipped: list | None` (abwaertskompatibel).
- Symlink-Pruefung muss `is_symlink()` vor Schreiben UND vor `unlink` machen (unlink auf Symlink loescht nur den Link, harmlos, aber Konsistenz).
- Start-Hinweis soll weiterhin eine Zeile liefern; Zaehlung "(N)" nur erfolgreiche.
- Aenderungen am Hook-Code `core/hooks/` benoetigen laut Projekt-CLAUDE.md in phase6 keinen Override mehr (#322).

## Analysis

### Type
Bug (Randfaelle aus der Gegenpruefung zu #399, beide nachgestellt: Adversary-Protokoll F001/F002). Eine Verschlechterung, kein Altfehler: vor #399 lief die Wartung nur auf Handbefehl, seit #399 laeuft sie unbeaufsichtigt bei jedem Start.

### Root Cause
`alias_sync.refresh_aliases` (Z. 215-235):
1. `Path.write_text` folgt Symlinks; `find_stale_aliases`/`find_removed_aliases` nehmen Symlinks auf, weil `is_file()` ihnen folgt. Die Schleife prueft nie `is_symlink()`.
2. Schleife ohne try/except pro Datei: ein `PermissionError` (0444) bricht ab; der Aufrufer `refresh_home_aliases` faengt alles mit `except Exception: return []`, daher keine Zeile, auch nicht fuer schon erneuerte Dateien.

### Affected Files (with changes)
| File | Change Type | Description |
|------|-------------|-------------|
| core/hooks/alias_sync.py | MODIFY | Symlink -> `skipped`; `OSError` pro Datei (Lesen SKILL.md, Schreiben, unlink) -> `skipped`, Schleife laeuft weiter; neuer optionaler Parameter `skipped: list \| None = None` |
| core/hooks/session_banner.py | MODIFY (klein) | `skipped`-Liste mitgeben; Zeile "Kurzbefehle aktualisiert (N)" zaehlt nur Erfolge; optional Zusatz "M uebersprungen" |
| setup.py | MODIFY | `refresh_command_aliases` meldet `  Skipped: <name> (<Grund>)` und Zaehler in der Schlusszeile |
| tests/test_alias_sync_robust_400.py | CREATE | Symlink-Test, 0444-Test mit weiterer veralteter Kopie + entferntem Alias, CLI-Ausgabe |
| CHANGELOG.md | MODIFY | Eintrag unter [Unreleased] |

### Scope Assessment
- Files: 4 Code/Test + CHANGELOG
- Estimated LoC: +~45 Code, +~70 Tests
- Risk Level: LOW (isolierte Funktion, zwei Aufrufer, Rueckgabe-Tupel bleibt unveraendert)

### Technical Approach (Empfehlung)
- **Symlinks: ueberspringen (Weg A)**, in der Schleife von `refresh_aliases` (nicht in `find_*`), damit der Name in `skipped` landet und sichtbar wird. Gilt auch fuer die Loeschschleife.
- **Fehler pro Datei:** `try/except OSError` um Lesen, Schreiben, `unlink`; Name + Kurzgrund nach `skipped`, weiter mit der naechsten.
- **Signatur abwaertskompatibel:** Rueckgabe bleibt `(erneuert, geloescht)`, `skipped` als optionaler Out-Parameter. Kein bestehender Aufrufer/Test bricht (in tests/ gibt es keinen direkten Entpack-Aufruf; `test_bug_typ_entfernt_333.py` geht ueber die CLI).
- `refresh_home_aliases` bleibt mit seinem aeusseren `except`, wird dadurch aber nur noch von echten Ausnahmen ausserhalb der Dateischleife getroffen.

### Alternativen
- **Weg B (Symlink aufloesen, nur schreiben wenn Ziel unter `commands_dir`):** erhaelt Dotfiles-Setups, aber ein Ziel im selben Ordner ist praktisch nie der Fall; ausserhalb wird ohnehin uebersprungen. Mehr Pfadlogik ohne realen Gewinn. Kippt keine ADR.
- **0444 heilen statt ueberspringen (temp-Datei + `os.replace`):** erneuert auch schreibgeschuetzte Kopien, uebergeht aber eine bewusste Schutzentscheidung des Nutzers in einem unbeaufsichtigten Lauf. Nicht empfohlen; die Datei wird gemeldet, nicht veraendert.
- **Ergebnisobjekt statt Tupel:** sauberer, bricht aber beide Aufrufer. Nicht noetig.

### Dependencies
Nur `pathlib`/`os`. Downstream: Start-Hinweis jeder Sitzung, `setup.py --refresh-aliases`.

### Open Questions
- [ ] Keine, die PO-Input braucht. Entscheidung Weg A und Signatur sind technisch und liegen bei Claude.
