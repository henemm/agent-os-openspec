---
entity_id: fix-400-alias-robust
type: bugfix
created: 2026-10-08
updated: 2026-10-08
status: draft
version: "1.0"
tags: [alias-sync, refresh-aliases, start-hinweis, symlink, robustheit, kurzbefehle]
test_targets: ["tests/test_alias_sync_robust_400.py"]
---

# Kurzbefehl-Wartung: Symlinks und schreibgeschützte Dateien (#400)

## Approval

- [ ] Approved

## GitHub Issue

- **Issue:** #400 (Folge der Gegenprüfung von #399). Befunde F001 und F002 aus `docs/artifacts/fix-399-start-wartung/adversary-dialog.md`.

## Purpose

Seit #399 erneuert der Start-Hinweis veraltete Kurzbefehl-Kopien in `~/.claude/commands/` selbst und löscht Aliase entfernter Befehle — unbeaufsichtigt bei jedem Sitzungsstart. `alias_sync.refresh_aliases` hat dabei zwei belegte Lücken:

1. **Symlinks (F001):** `find_stale_aliases` und `find_removed_aliases` nehmen Symlinks auf, weil `is_file()` ihnen folgt. `Path.write_text` folgt ihnen ebenfalls und überschreibt das Ziel — auch eine Datei weit außerhalb von `~/.claude/commands/` (z. B. in einem Dotfiles-Repo). Die Wartung verlässt damit ihren Schreibbereich.
2. **Einzelne schreibgeschützte Datei (F002):** Die Schleife hat kein `try/except` pro Datei. Ein `PermissionError` bei einer 0444-Kopie bricht den ganzen Lauf ab. Der Aufrufer `refresh_home_aliases` fängt alles mit `except Exception: return []`, sodass nicht einmal die bereits erneuerten Dateien als Zeile erscheinen — der Nutzer erfährt nichts, und der Fehler wiederholt sich bei jedem Start.

Es ist eine Verschlechterung, kein Altfehler: Vor #399 lief die Wartung nur auf Handbefehl, seit #399 läuft sie bei jedem Start. Diese Spec hält die Wartung in ihrem Schreibbereich (Symlinks werden nie beschrieben und nie gelöscht) und macht sie gegen einzelne Problemdateien robust: Was nicht angefasst werden kann, wird übersprungen und sichtbar gemeldet, der Rest läuft weiter.

## Source

- **File:** `core/hooks/alias_sync.py` — `refresh_aliases`; `core/hooks/session_banner.py` — `refresh_home_aliases`; `setup.py` — `refresh_command_aliases`
- **Analyse:** `docs/context/fix-400-alias-robust.md` (Root Cause, Technical Approach, Alternativen)
- **Befunde:** `docs/artifacts/fix-399-start-wartung/adversary-dialog.md` (F001 Symlink, F002 0444)

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `core/hooks/alias_sync.py` | Modul | Kernlogik `refresh_aliases`; Hauptänderung |
| `core/hooks/session_banner.py` | Modul | Aufrufer `refresh_home_aliases`; Zeile im Start-Hinweis |
| `setup.py` | Modul | Aufrufer `refresh_command_aliases` (`--refresh-aliases`); CLI-Ausgabe |
| `_read_or_none` in `alias_sync.py` | Funktion | Muster für fehlertolerantes Lesen (#350); bleibt unverändert |
| `tests/test_session_banner.py` | Test | Bestehende Tests zu `refresh_home_aliases` (#399); Regressionsschutz |
| `tests/test_alias_remove_251.py` | Test | Muster (`setup.py` als echter Prozess mit Test-Home); Regressionsschutz |
| `tests/test_setup_alias_sync_150.py` | Test | Regressionsschutz für `--refresh-aliases` |
| `tests/test_bug_typ_entfernt_333.py` | Test | Regressionsschutz (Löschen von `00-bug` per CLI) |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| `core/hooks/alias_sync.py` | MODIFY | `refresh_aliases`: Symlinks in beiden Schleifen überspringen; `try/except OSError` pro Datei (Lesen SKILL.md, Schreiben, `unlink`); optionaler Out-Parameter `skipped` |
| `core/hooks/session_banner.py` | MODIFY | `refresh_home_aliases` gibt `skipped` mit; Zeile zählt nur Erfolge und nennt Übersprungene |
| `setup.py` | MODIFY | `refresh_command_aliases` druckt `  Skipped: <Eintrag>` und nennt die Zahl in der Schlusszeile, wenn K > 0 |
| `tests/test_alias_sync_robust_400.py` | CREATE | je AC ein Test; Symlink, 0444, Rückgabe-Kompatibilität, Start-Hinweis, CLI |
| `CHANGELOG.md` | MODIFY | Eintrag nur unter `[Unreleased]`, kein Versions-Bump |

### Estimated Changes

- Files: 5 (3 Produktiv, 1 Test, 1 Doku)
- LoC: ca. +115 (Produktivcode ca. 45, Tests ca. 70). Spec/Kontext/Briefing zählen im LoC-Gate zusätzlich (#294).
- Risiko: LOW — isolierte Funktion mit zwei Aufrufern, Rückgabe-Tupel bleibt unverändert, Verhalten für normale Dateien bleibt gleich. `core/hooks/` ist Infrastruktur, daher Gegenprüfung nach dem Adversary-Protokoll.

## Implementation Details

**Symlinks (F001).** In `refresh_aliases` wird in der Erneuerungsschleife **und** in der Löschschleife vor jedem Zugriff `path.is_symlink()` geprüft. Ein Symlink wird weder beschrieben noch gelöscht; sein Name landet als `"<name>: Symlink"` in `skipped`. Die Prüfung sitzt bewusst in der Schleife von `refresh_aliases`, nicht in `find_stale_aliases`/`find_removed_aliases`: Dort ginge der Name verloren, und die Funktionen werden auch vom Projekt-Scope-Hinweis (`project_alias_context`) benutzt, der Symlinks weiter als „veraltet“ melden soll.

**Fehler pro Datei (F002).** Lesen der `SKILL.md`, Schreiben der Kopie und `unlink` sind je in `try/except OSError` gefasst. Bei einem Fehler wird `"<name>: <Grund>"` nach `skipped` geschrieben und mit der nächsten Datei weitergemacht. Kurzgründe: `schreibgeschützt` für `PermissionError`, sonst `Fehler (<Fehlername>)`; ein nicht lesbarer Skill-Text wird als `Skill nicht lesbar` gemeldet. Die Schleife läuft immer zu Ende.

**Signatur.** `refresh_aliases(skills_dir, commands_dir, loaded_version, skipped: "list | None" = None)`. Die Rückgabe bleibt das Tupel `(erneuert, gelöscht)`. Übergibt der Aufrufer eine Liste, füllt die Funktion sie; ohne Liste verhält sich die Funktion wie bisher (abgesehen davon, dass sie nicht mehr abbricht). Kein bestehender Aufrufer und kein Test bricht.

**Start-Hinweis.** `refresh_home_aliases` legt `skipped = []` an und reicht sie durch. Die Zeile `Kurzbefehle aktualisiert (N)` zählt nur Erfolge (erneuert plus gelöscht). Gibt es Übersprungene (M > 0), steht dahinter ` · M übersprungen`. Gibt es nur Übersprungene und keine Erfolge, erscheint trotzdem eine Zeile: `Kurzbefehle: M übersprungen`. Ohne Erfolge und ohne Übersprungene bleibt die Rückgabe leer wie bisher. Das äußere `except Exception: return []` bleibt, trifft aber nur noch echte Ausnahmen außerhalb der Dateischleife.

**CLI.** `refresh_command_aliases` übergibt eine `skipped`-Liste und druckt je Eintrag `  Skipped: <Eintrag>` (z. B. `  Skipped: 10-context: Symlink`). Die Schlusszeile bleibt bei K == 0 wortgleich (`Command aliases: N refreshed, M removed, none created.`); bei K > 0 lautet sie `Command aliases: N refreshed, M removed, none created, K skipped.` Ein Grep über `tests/` zeigt: Der Wortlaut „none created“ wird in keinem Test geprüft, die Zeile bleibt für K == 0 trotzdem unverändert. Exit-Code bleibt 0.

**Ohne Modell geht es?** Ja — reine Dateiprüfung (`is_symlink`, `OSError`), die Nulllinie ist die Regel.

**Alternativen:**

- **A (gewählt): Symlinks überspringen, `OSError` pro Datei abfangen, `skipped` als optionaler Out-Parameter.** Einfachste Lösung, keine Pfadlogik, abwärtskompatibel, Problemdateien werden sichtbar statt still.
- **B: Symlink auflösen und nur schreiben, wenn das Ziel unter `commands_dir` liegt.** Würde Dotfiles-Setups erhalten, die auf eine Kopie im selben Ordner zeigen. Das ist praktisch nie der Fall; liegt das Ziel außerhalb, wird ohnehin übersprungen. Mehr Pfadlogik (`resolve`, Vergleich) ohne realen Gewinn. Verworfen.
- **C: 0444 heilen (temp-Datei im selben Ordner schreiben, mit `os.replace` austauschen).** Erneuert auch schreibgeschützte Kopien, übergeht aber eine bewusste Schutzentscheidung des Nutzers in einem unbeaufsichtigten Lauf und ändert Dateirechte. Verworfen; die Datei wird gemeldet, nicht verändert.
- **D: Ergebnisobjekt statt Tupel.** Sauberer, bricht aber beide Aufrufer und jede Entpackung `refreshed, removed = ...`. Nicht nötig. Verworfen.

## Expected Behavior

- **Input:** Start-Hinweis (`refresh_home_aliases`) bzw. `setup.py --refresh-aliases` mit einem Kurzbefehl-Ordner, der neben normalen veralteten Kopien Symlinks oder schreibgeschützte Dateien enthält.
- **Output:** Normale veraltete Kopien werden erneuert, Aliase entfernter Befehle gelöscht. Symlinks und nicht beschreibbare Dateien bleiben unverändert und werden als übersprungen gemeldet (Start-Hinweis: Zusatz bzw. eigene Zeile; CLI: `Skipped:`-Zeilen). Ein Problemfall stoppt die übrigen nie.
- **Side effects:** Keine neuen Dateien, keine Rechteänderungen, keine neuen Abhängigkeiten. Neu sind nur die Meldungen über Übersprungenes.

| Zustand eines Eintrags in `~/.claude/commands/` | Heute | Soll |
|---|---|---|
| Veralteter Alias `10-context.md` ist Symlink auf Datei außerhalb | Ziel wird überschrieben | unverändert, `skipped: 10-context: Symlink` |
| Alias entfernten Befehls (`00-bug.md`) ist Symlink | `unlink` löscht den Link | unverändert, `skipped: 00-bug: Symlink` |
| Veraltete Kopie ist 0444, weitere veraltete Kopie dahinter | `PermissionError`, Lauf bricht ab, keine Zeile | 0444-Datei in `skipped`, weitere Kopie erneuert, entfernter Alias gelöscht |
| Start-Hinweis, 1 erneuert + 1 übersprungen | keine Zeile | `Kurzbefehle aktualisiert (1) · 1 übersprungen` |
| Start-Hinweis, nur übersprungene | keine Zeile | `Kurzbefehle: 1 übersprungen` |
| `--refresh-aliases` mit übersprungenem Eintrag | Absturz bzw. Zeile fehlt | `  Skipped: <Eintrag>`, Schlusszeile nennt `K skipped`, Exit 0 |
| Alles normal | `... none created.` | unverändert |

## Known Limitations

- **Verteilung:** wirkt in Konsumenten-Projekten und im Nutzer-Home erst nach dem Plugin-Update.
- Setups, bei denen Kurzbefehle per Symlink aus einem Dotfiles-Repo kommen, werden nicht erneuert, sondern nur gemeldet. Der Nutzer pflegt das Ziel selbst.
- Eine schreibgeschützte Kopie bleibt veraltet und wird bei jedem Start erneut gemeldet, bis der Nutzer die Rechte ändert oder die Datei löscht.
- Läuft die Sitzung als `root`, ist 0444 keine Schranke; dann wird die Datei normal erneuert. Der zugehörige Test läuft deshalb nur als Nicht-root.

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] Ein Symlink wird weder beschrieben noch gelöscht, sein Ziel bleibt byte-gleich
- [ ] Eine einzelne schreibgeschützte Datei stoppt weder Erneuerung noch Löschen der übrigen
- [ ] Start-Hinweis und `--refresh-aliases` nennen Übersprungenes sichtbar
- [ ] Keine bestehende Funktion ist kaputtgegangen (Regressionslauf grün)
- [ ] `CHANGELOG.md` unter `[Unreleased]` ergänzt

## Acceptance Criteria

- **AC-1:** Given ein veralteter markierter Alias im Befehlsordner, der ein Symlink auf eine Datei außerhalb des Ordners ist / When `refresh_aliases` läuft / Then wird die Zieldatei nicht verändert (Inhalt identisch), der Symlink bleibt Symlink, der Name steht mit dem Grund `Symlink` in `skipped` und nicht in der Liste der erneuerten
  - Test: `tests/test_alias_sync_robust_400.py::test_symlink_wird_nicht_beschrieben`
- **AC-2:** Given der Alias eines entfernten Befehls (z. B. `00-bug.md`, markiert), der ein Symlink ist / When `refresh_aliases` läuft / Then wird der Symlink nicht gelöscht, das Ziel bleibt unverändert, der Name steht in `skipped` und nicht in der Liste der gelöschten
  - Test: `tests/test_alias_sync_robust_400.py::test_symlink_als_entfernter_alias_wird_nicht_geloescht`
- **AC-3:** Given eine veraltete markierte Kopie mit Rechten 0444 (als Nicht-root), dazu eine weitere veraltete Kopie und ein Alias eines entfernten Befehls / When `refresh_aliases` läuft / Then bricht der Lauf nicht ab: die weitere Kopie ist erneuert, der entfernte Alias gelöscht, die 0444-Datei ist unverändert und steht mit Grund in `skipped`
  - Test: `tests/test_alias_sync_robust_400.py::test_schreibgeschuetzte_datei_bricht_schleife_nicht_ab`
- **AC-4:** Given ein Aufruf von `refresh_aliases` ohne `skipped`-Parameter / When er läuft / Then liefert er weiterhin ein Zweier-Tupel `(erneuert, gelöscht)` mit unverändertem Inhalt für normale Dateien, und mit übergebener Liste wird diese gefüllt
  - Test: `tests/test_alias_sync_robust_400.py::test_rueckgabe_tupel_und_optionaler_skipped_parameter`
- **AC-5:** Given ein Home mit einer erneuerbaren Kopie und einer Problemdatei (Symlink bzw. 0444) / When `refresh_home_aliases` läuft / Then steht genau eine Zeile `Kurzbefehle aktualisiert (1) · 1 übersprungen` (Zählung nur Erfolge); bei ausschließlich Übersprungenen steht `Kurzbefehle: 1 übersprungen`; die erneuerte Datei ist auch bei Problemdatei erneuert
  - Test: `tests/test_alias_sync_robust_400.py::test_start_hinweis_zaehlt_erfolge_und_nennt_uebersprungene`
- **AC-6:** Given `setup.py --refresh-aliases` mit einem übersprungenen Eintrag (Symlink) und einer erneuerbaren Kopie / When der Aufruf als echter Prozess mit Test-Home läuft / Then endet er mit Exit 0, die Ausgabe enthält `  Skipped: ` mit dem Namen und dem Grund, `  Refreshed: ` für die erneuerte Kopie, und die Schlusszeile nennt `1 skipped`; ohne übersprungene Einträge bleibt die Schlusszeile `Command aliases: N refreshed, M removed, none created.`
  - Test: `tests/test_alias_sync_robust_400.py::test_refresh_aliases_cli_meldet_uebersprungene`
- **AC-7:** Given der bestehende Testbestand / When die Regressionstests laufen / Then bleiben sie grün
  - Test: `tests/test_session_banner.py`, `tests/test_alias_remove_251.py`, `tests/test_setup_alias_sync_150.py`, `tests/test_bug_typ_entfernt_333.py` (unverändert, Lauf grün)

> Die Test-Zuordnung wird **bei der Spec-Erstellung** eingetragen, nicht nachträglich:
> Nach der Freigabe ist diese Datei eingefroren (#230) — jede Änderung verschiebt den
> PO-Briefing-Hash und blockt den Workflow-Abschluss. Stimmt der Testname später nicht
> mehr, gehört die Korrektur in die TDD-RED-Artefakte (`workflow.py add-artifact`),
> nicht in diese Datei.

## Test Plan

Automatische Tests (jeweils an eine AC oben gebunden):
- `pytest tests/test_alias_sync_robust_400.py` (AC-1 bis AC-6; `alias_sync`-Funktionen und `refresh_home_aliases` direkt mit Test-Home, `setup.py` als echter Prozess nach dem Muster aus `tests/test_alias_remove_251.py`; Symlink per `os.symlink` auf eine Datei außerhalb des Befehlsordners, 0444 per `chmod(0o444)` auf die Alias-Datei selbst — `write_text` schlägt dann mit `PermissionError` fehl; der Test wird übersprungen, wenn er als root läuft; veraltete Kopie = Marker mit älterer Version bzw. abweichender Inhalt wie in den bestehenden Alias-Tests; beide Richtungen: Fremdes bleibt, Normales wird erneuert).
- RED-Nachweis: Vor der Implementierung schlagen AC-1, AC-2 (Ziel überschrieben bzw. Link gelöscht), AC-3 (`PermissionError` bricht ab), AC-4 (Parameter `skipped` unbekannt), AC-5 (keine bzw. falsche Zeile) und AC-6 (keine `Skipped:`-Zeile bzw. Absturz) fehl; der Teil von AC-4, der nur das Zweier-Tupel ohne Parameter prüft, ist bereits grün.
- Regressionslauf (AC-7): die vier genannten Dateien, danach die Vollsuite.

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Defensive Fehlerbehandlung und Eingrenzung des Schreibbereichs innerhalb der bestehenden Entscheidung aus #251/#399 (nur markierte Dateien anfassen, nie anlegen, nie herabstufen). Kein neues Muster, keine Abhängigkeit. Reflexion der Alternativen: (A) Symlinks überspringen plus `OSError` pro Datei — gewählt wegen Einfachheit und Abwärtskompatibilität; (B) Symlink auflösen — verworfen, mehr Pfadlogik ohne realen Gewinn; (C) 0444 heilen — verworfen, übergeht eine bewusste Schutzentscheidung in einem unbeaufsichtigten Lauf; (D) Ergebnisobjekt statt Tupel — verworfen, bricht beide Aufrufer. Keine frühere ADR wird gekippt.

## Changelog

- 2026-10-08: Initial spec created (#400, Folge von #399)
