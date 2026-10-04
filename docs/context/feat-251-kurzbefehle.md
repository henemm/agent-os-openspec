# Context: feat-251-kurzbefehle

## Request Summary
#251 (fasst #242, #238, #244): Kurz-Befehle (`/50-implement`) sollen einheitlich funktionieren —
auch in Worktree-Sitzungen, mit echter Beschreibung, genau einmal in der Auswahl, und mit einem
Werkzeug zum Entfernen. Recherche steht vollständig im Issue; nichts davon ist bisher umgesetzt.

## Related Files
| File | Relevance |
|------|-----------|
| `core/hooks/alias_sync.py:21,43-60` | `ALIAS_MARKER` steht als erste Zeile VOR dem Frontmatter (#238); `is_alias_file` prüft nur Zeile 1 |
| `setup.py:1000-1110` | `generate_command_aliases`, `refresh_command_aliases`; kein Entfernen-Modus (#244); Argumente ab ~1198 |
| `core/hooks/alias_sync.py:134-153` | `REMOVED_SKILLS` + `find_removed_aliases`: Entfernen nur einer festen Liste, nur markierte Dateien |
| `migrate_to_plugin.py:460,510` | Erkennt Marker per Teilstring an beliebiger Stelle → kompatibel mit neuer Position |
| `core/hooks/workflow.py:194` | `expected_footer_command` erzeugt den Kurz-Namen bedingungslos (#242 zweiter Teil) |
| `tests/test_repo_own_aliases_147.py` | prüft schon `find_stale_aliases(...) == []` für `.claude/commands/` → deckt das gewünschte `--check` im Release ab |
| `tests/test_setup_alias_sync_150.py`, `test_setup_command_aliases.py`, `test_session_banner.py`, `test_migrate_*` | nutzen den Marker und müssen grün bleiben |

## Existing Patterns
- Soll-Inhalt einer Alias-Datei kommt ausschließlich aus `alias_content()`; Veraltet-Erkennung ist
  `actual != expected` für markierte Dateien. **Folge:** Ändert sich die Marker-Position, gelten alle
  Bestandskopien mit altem Marker automatisch als veraltet und werden von `--refresh-aliases` auf das
  neue Format gehoben. Eine Migration entfällt, solange `is_alias_file` BEIDE Positionen erkennt.
- Unmarkierte Dateien sind projekteigen und tabu (#24/#160).

## Dependencies / Dependents
- Upstream: `skills/*/SKILL.md` (Soll-Inhalt).
- Downstream: `session_banner.py`, `setup.py`, `migrate_to_plugin.py`.

## Existing Specs
Keine passende; `docs/specs/short-command-aliases.md` wird erwähnt (Mitigation #87).

## Risks & Considerations
- Der alte Marker darf nie unerkannt bleiben, sonst gelten Bestandskopien als projekteigen und
  frieren ein (Issue-Pflicht).
- Ein Entfernen-Modus ist eine löschende Operation: nur Dateien mit Marker, Test mit unmarkierter Datei.
- Globale Ablage: vor dem Anlegen Kollisionsprüfung über alle Projekte (Momentaufnahme im Issue vom
  2026-09-26, hier erneut messen). Das ist ein Daten-Schritt auf diesem Rechner, kein Repo-Code.
- `.claude/commands/` im Repo selbst ist versioniert (15 Dateien) und wird vom Test 147 überwacht.

## Analysis

### Alternative (Hennings Regel „in Alternativen denken")
**Fußzeile nennt die Langform** `/agent-os-openspec:50-implement`. Sie ist in jeder Umgebung
auflösbar (Plugin-Namensraum), braucht weder globale Ablage noch Marker noch Entfernen-Werkzeug und
erfüllt das letzte DoD-Kriterium trivial. Preis: mehr Tippen, und die Kurzform bleibt eine Bequemlichkeit.
Gekippt würde die Entscheidung aus #235-Umfeld, dass die Fußzeile den Kurz-Namen nennt. Der PO hat am
2026-09-26 ausdrücklich „einheitlich" mit Kurz-Befehlen gewollt → Kurzform bleibt Ziel, aber die
Fußzeile fällt auf die Langform zurück, wenn der Kurz-Befehl in der Umgebung nicht aufgelöst werden kann
(erstmal nicht erkennbar → Entscheidung in der Spec).

### Schnitt (lean, 4–5 Dateien)
1. `alias_sync.py`: Marker hinter das Frontmatter; `is_alias_file` erkennt Zeile 1 (alt) und die
   Zeile direkt nach dem Frontmatter (neu). Dazu `find_aliases` für das Entfernen.
2. `setup.py`: `--remove-aliases` entfernt nur markierte Dateien in `<scope>/.claude/commands/`.
3. Tests: Marker-Position (Frontmatter parsbar, Beschreibung bleibt), Rückwärtskompatibilität,
   Entfernen lässt unmarkierte Dateien stehen.
4. Daten-Schritt (nicht im PR): globale Ablage + Projekt-Kopien entfernen, nach erneuter Kollisionsprüfung.
5. Fußzeile (`expected_footer_command`): separat bewertet — nur wenn eine Auflösbarkeits-Prüfung
   zuverlässig machbar ist; sonst Langform-Rückfall oder eigenes Ticket.

### Reproduktion (2026-10-03, Claude Code 2.1.285)
- **#238 (Beschreibung = Marker): reproduziert.** In dieser Sitzung zeigt die Skill-Liste für jeden
  Kurz-Befehl als Beschreibung `<!-- openspec-alias: do-not-treat-as-legacy-duplicate -->`.
- **#242 („Unknown command" im Worktree): NICHT reproduziert.** Wegwerf-Projekt mit gitignorierter
  Kurz-Befehl-Datei, `claude -p "/probe50"`: Hauptordner → OK, Worktree unter `.claude/worktrees/` → OK,
  Worktree außerhalb des Projektordners → OK. Die im Issue behauptete Ursache („lädt `.claude/commands/`
  von dort nicht") trägt in dieser Version nicht. Nicht ausgeschlossen: Worktree wird erst *mitten in
  der Sitzung* betreten (Befehlsliste beim Start geladen) oder ältere Version. Ohne Reproduktion wird
  dafür nichts gebaut (Regel „Reproduktion zuerst").
- Folge: Der Programmpunkt „einmal global ablegen" ist unbegründet und entfällt aus dem Schnitt. Das ist
  zugleich die Alternative zur Issue-Empfehlung; gekippt wird die Empfehlung in #251 („alle 16 global").
- Im Repo selbst sind die 15 Kurz-Befehle versioniert, ein Worktree trägt sie daher ohnehin mit.

### Betroffene Dateien
| Datei | Änderung | Beschreibung |
|-------|----------|--------------|
| `core/hooks/alias_sync.py` | MODIFY | Marker hinter das Frontmatter; `is_alias_file` erkennt alt (Zeile 1) und neu; `find_aliases` |
| `setup.py` | MODIFY | `--remove-aliases [--global]`: löscht nur markierte Dateien |
| `tests/test_alias_marker_position_251.py` | CREATE | Frontmatter parsbar, Beschreibung echt, Altformat erkannt |
| `tests/test_alias_remove_251.py` | CREATE | Entfernen lässt unmarkierte Datei stehen |
| `.claude/commands/*` (15) | REGENERATE | per `--refresh-aliases`, rein mechanisch (Marker-Zeile verschoben) |

### Scope / Risiko
- 4 handgeschriebene Dateien, ca. +120/−10 LoC (ohne regenerierte Kopien). Risiko: **MITTEL** — falsche
  Marker-Erkennung würde Bestandskopien einfrieren (#24/#160), Entfernen ist eine löschende Operation.

### Technischer Ansatz
Marker als erste Body-Zeile nach dem Frontmatter (kleinster Eingriff, kein Verhalten mit unbekannten
Zusatzfeldern). Vollkopien: Marker nach dem schließenden `---` des SKILL.md-Frontmatters einfügen.
Regelweg komplett, kein Modell nötig (reine Textoperation).

### Offene Fragen
- [ ] Footer-Teil (`expected_footer_command` / DoD „nennt nie unbekannten Befehl"): ohne reproduzierten
      Fehler und ohne Auflösbarkeits-Prüfung nicht umsetzbar → in #235 behandeln? (Empfehlung: ja.)

`--check` im `release_check.py` entfällt: `test_repo_own_aliases_147.py` leistet das bereits und läuft
im Release-Testlauf.
