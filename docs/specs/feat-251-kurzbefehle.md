---
entity_id: feat-251-kurzbefehle
type: module
created: 2026-10-03
updated: 2026-10-03
status: draft
version: "1.0"
tags: [kurz-befehle, alias, marker, setup, "#251", "#238", "#244", "#242"]
---

# Kurz-Befehle: Marker hinter das Frontmatter und Entfernen-Werkzeug (#251, fasst #238 und #244)

## Approval

- [ ] Approved

## Purpose

Die Kurz-Befehle (`/50-implement` statt `/agent-os-openspec:50-implement`) sind selbst erzeugte Weiterleitungs-
und Vollkopie-Dateien in `.claude/commands/`. Zwei Mängel sind reproduziert bzw. belegt: Der Marker
`<!-- openspec-alias: ... -->` steht vor dem Frontmatter, das dadurch nicht geparst wird. In der Befehlsauswahl
steht für jeden Kurz-Befehl der Marker statt der Beschreibung (#238, am 2026-10-03 mit Claude Code 2.1.285
reproduziert). Und es gibt keinen Weg, markierte Kurz-Befehle in einem Bereich wieder zu entfernen, ohne Dateien
von Hand zu löschen (#244).

Diese Änderung behebt beides mit reiner Textoperation: Der Marker wandert als erste Zeile hinter das Frontmatter,
`is_alias_file` erkennt alte und neue Position, und `setup.py --remove-aliases` löscht ausschließlich markierte
Dateien. Der dritte Strang des Sammel-Vorgangs (#242, „Unknown command" im Worktree) wurde nicht reproduziert und
ist bewusst nicht Teil dieser Änderung (siehe Known Limitations).

## Source

- **File:** `core/hooks/alias_sync.py`, `setup.py`
- **Identifier:** `alias_sync.ALIAS_MARKER`, `alias_sync.alias_content`, `alias_sync.is_alias_file`,
  `alias_sync.find_stale_aliases`, `alias_sync.find_aliases` (neu), `setup.refresh_command_aliases`,
  `setup.remove_command_aliases` (neu), Argument `--remove-aliases`

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `alias_sync.alias_content` | Funktion | einzige Quelle des Soll-Inhalts; ändert die Marker-Position, damit gelten Bestandskopien automatisch als veraltet |
| `alias_sync.find_stale_aliases` | Funktion | erkennt veraltete Kopien per `actual != expected`; bleibt unverändert, profitiert von der Erkennung beider Positionen |
| `alias_sync.find_removed_aliases` | Funktion | Vorbild für das Entfernen (nur markierte Dateien); bleibt unverändert |
| `setup.generate_command_aliases`, `setup.refresh_command_aliases` | Funktionen | nutzen `alias_content` und `is_alias_file`; `--refresh-aliases` hebt Altformate auf das neue Format |
| `session_banner.py` | Hook | importiert `find_stale_aliases`; meldet Altformat künftig als veraltet |
| `migrate_to_plugin.py` | Skript | erkennt den Marker per Teilstring (`openspec-alias:`) an beliebiger Stelle, bleibt kompatibel und löscht keine projekteigenen Befehle (#24/#160) |
| `skills/*/SKILL.md` | Dateien | Soll-Inhalt der Vollkopien; ihr Frontmatter bleibt unverändert |
| `tests/test_repo_own_aliases_147.py` | Test | prüft `find_stale_aliases(...) == []` für die versionierten Kopien in `.claude/commands/` und ersetzt damit ein `--check` im Release |

## Scope

- **Affected Files (handgeschrieben):** `core/hooks/alias_sync.py`, `setup.py`,
  `tests/test_alias_marker_position_251.py` (neu), `tests/test_alias_remove_251.py` (neu)
- **Regeneriert (rein mechanisch, zählt nicht als handgeschrieben):** die 15 versionierten Kopien in
  `.claude/commands/` per `setup.py <repo> --refresh-aliases`; die Marker-Zeile wandert hinter das Frontmatter
- **Estimated Changes:** ca. +120/−10 LoC (ohne regenerierte Kopien)
- **Nicht enthalten:** globale Ablage der Kurz-Befehle, Änderung von `expected_footer_command`
  (`core/hooks/workflow.py`), Aufräumen vorhandener Kopien auf diesem Rechner, Versions-Bump
  (Fix-/Feature-PRs schreiben nur unter `[Unreleased]` im Changelog)

## Implementation Details

1. **`alias_sync.alias_content(name, skill_text)`** setzt `ALIAS_MARKER` als erste Body-Zeile direkt nach dem
   schließenden `---` des Frontmatters:
   - Weiterleitung: `---`, `description: Kurz-Alias für /agent-os-openspec:<name>`, `---`, dann der Marker, dann
     eine Leerzeile und `/agent-os-openspec:<name> $ARGUMENTS`.
   - Vollkopie (`disable-model-invocation: true`): der Marker wird hinter das Frontmatter des `SKILL.md` eingefügt,
     der übrige Inhalt (inklusive Versions-Marker am Ende) bleibt byte-gleich. Das Frontmatter beginnt damit in
     Zeile 1 und ist parsbar; `description` ist die echte Beschreibung.
2. **`alias_sync.is_alias_file(text)`** erkennt beide Positionen: alt (Zeile 1 beginnt mit `<!-- openspec-alias:`)
   und neu (die erste Zeile direkt nach dem schließenden `---` des Frontmatters beginnt mit dem Präfix). Nur ein
   am Dateianfang stehendes, geschlossenes Frontmatter zählt; ein Marker an beliebiger anderer Stelle gilt nicht.
3. **`alias_sync.find_aliases(commands_dir)`** (neu) liefert alle Dateien `*.md` in `commands_dir`, für die
   `is_alias_file` wahr ist, sortiert; existiert das Verzeichnis nicht, ist das Ergebnis leer.
4. **`setup.remove_command_aliases(scope_path)`** (neu): löscht jede Datei aus `find_aliases(<scope>/.claude/commands)`
   und gibt je Datei `Removed: <name>.md` aus. Projekteigene (unmarkierte) Dateien werden nie gelöscht, aber
   namentlich als `Kept: <name>.md` gemeldet. Schlusszeile: `Command aliases: N removed, M kept.` Ohne markierte
   Dateien oder ohne Verzeichnis: keine Löschung, Meldung `0 removed`, kein Fehler, Exit-Code 0.
5. **Argument-Parser:** `--remove-aliases` (nur Entfernen, legt nie etwas an) und `--global` (Bereich ist das
   Home-Verzeichnis statt `project_path`). Ohne `--global` gilt der angegebene Projektordner, wie bei
   `--refresh-aliases`.
6. **Regenerierung:** `setup.py <repo> --refresh-aliases` hebt die 15 versionierten Kopien auf das neue Format.
   Eine Migration entfällt, weil Altformat-Dateien als markiert erkannt und als veraltet (`actual != expected`)
   gemeldet werden.

## Expected Behavior

- **Input:** `alias_content(name, skill_text)`; Textdateien in `<scope>/.claude/commands/`; Aufrufe
  `setup.py <pfad> --refresh-aliases` bzw. `--remove-aliases [--global]`.
- **Output:** Generierte Dateien haben ein parsbares Frontmatter mit echter `description`, der Marker steht in der
  ersten Zeile danach. Altformat-Dateien gelten weiter als generiert, werden als veraltet gemeldet und von
  `--refresh-aliases` aktualisiert. `--remove-aliases` löscht genau die markierten Dateien und nennt gelöschte und
  behaltene.
- **Side effects:** `--remove-aliases` ist eine löschende Operation, begrenzt auf markierte Dateien in
  `.claude/commands/` des gewählten Bereichs. `session_banner.py` meldet Bestandskopien mit altem Marker einmalig
  als veraltet, bis sie per `--refresh-aliases` angehoben sind. Keine neuen Berechtigungen, keine AppStorage-Keys.

## Known Limitations

Vier bewusste Abweichungen vom Definition-of-Done des Issues #251:

- **(a) #242 „Unknown command im Worktree" ist nicht Teil der Änderung.** Der Fehler wurde am 2026-10-03 mit
  Claude Code 2.1.285 nicht reproduziert: Wegwerf-Projekt mit gitignorierter Kurz-Befehl-Datei, `claude -p
  "/probe50"` aus dem Hauptordner, aus einem Worktree unter `.claude/worktrees/` und aus einem Worktree außerhalb
  des Projektordners — alle drei fanden den Befehl. Die im Issue behauptete Ursache trägt in dieser Version nicht.
  Nach der Regel „Reproduktion zuerst" wird dafür nichts gebaut; deshalb entfällt auch die globale Ablage, und die
  Empfehlung des Issues „alle 16 global" wird gekippt. Nicht ausgeschlossen bleibt, dass der Fehler nur auftritt,
  wenn ein Worktree erst mitten in der Sitzung betreten wird oder in einer älteren Version. Tritt er reproduzierbar
  auf, kommt ein eigenes Ticket. Das DoD-Kriterium „`/50-implement` funktioniert in einer Worktree-Sitzung" ist
  damit nicht neu belegt; im Repo selbst sind die 15 Kopien versioniert, ein Worktree trägt sie ohnehin mit.
- **(b) #244 „doppelte Einträge":** Das Entfernen-Werkzeug beseitigt die Handarbeit. Weil es keine globale Ablage
  gibt, entsteht die Doppelung nicht neu. Das Aufräumen vorhandener globaler und Projekt-Kopien auf diesem Rechner
  ist ein einmaliger Datenschritt und kein Repo-Code; er folgt nach der Auslieferung mit dem neuen Werkzeug. Das
  DoD-Kriterium „jeder der 16 Namen genau einmal in der Auswahl" ist damit eine Folge dieses Datenschritts, kein
  Testergebnis dieser Änderung.
- **(c) Fußzeilen-Kriterium „nennt nie einen Befehl, den es nicht gibt"** (`expected_footer_command` in
  `core/hooks/workflow.py`) ist nicht umgesetzt. Ohne reproduzierten Fehler und ohne zuverlässige
  Auflösbarkeits-Prüfung (ob Claude Code einen Kurz-Befehl in der laufenden Umgebung auflöst, ist von außen nicht
  ermittelbar) ist es nicht seriös automatisch prüfbar. Verweis: #235 bzw. ein eigenes Folgeticket.
- **(d) Kein Prüfmodus `--check` und kein Aufruf in `release_check.py`.** Der Zusatzbefund aus #88 im Issue
  verlangt einen Prüfmodus nach Vorbild von `sync_skills.py`, der Drift zwischen `core/commands/` und den
  Kurz-Befehlen im Release meldet. Er wird nicht gebaut: `tests/test_repo_own_aliases_147.py` prüft
  `find_stale_aliases(...) == []` für die versionierten Kopien bereits und läuft im Release-Testlauf. Ein zweiter
  Prüfweg würde dieselbe Aussage doppeln. Reicht dem PO der Test nicht, ist `--check` ein eigenes Folgeticket.
- Ebenso nicht umgesetzt: das Zielbild „Vollkopien abschaffen" aus dem Issue-Kommentar (die sechs Befehle global
  statt projektlokal); es hängt an der globalen Ablage, siehe (a). Die Drift der Vollkopien wird durch
  Neuerzeugen und den bestehenden Test beherrscht, nicht beseitigt.

Weitere Grenzen:

- Mit `--remove-aliases` entfernte Kurz-Befehle kehren erst mit `--command-aliases` zurück.
- Eine projekteigene Datei, die selbst den Marker trägt, gilt als generiert; das ist unverändert zum Stand vor
  dieser Änderung.

## Alternativen (und was sie kippen würden)

1. **Fußzeile nennt die Langform `/agent-os-openspec:50-implement`:** braucht weder Marker noch
   Entfernen-Werkzeug und ist überall auflösbar. Verworfen, weil der PO am 2026-09-26 ausdrücklich „einheitlich"
   mit Kurz-Befehlen wollte; gekippt würde die Entscheidung, dass die Fußzeile den Kurz-Namen nennt.
2. **Marker als Frontmatter-Feld:** sauber, aber das Verhalten von Claude Code bei nicht dokumentierten
   Zusatzfeldern ist nicht belegt (unterstützt sind `name`, `description`, `disable-model-invocation`,
   `user-invocable`, `allowed-tools`, `context`, `argument-hint`, `model`). Verworfen zugunsten der Body-Zeile.
3. **Alle 16 global ablegen (Empfehlung im Issue):** gekippt, siehe Known Limitations (a); kippt zugleich die
   Empfehlung „pro Projekt statt global" aus #87 nur insofern, als gar nichts global angelegt wird.

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] Die Befehlsauswahl zeigt für `/50-implement` und die übrigen Kurz-Befehle einen Beschreibungstext statt des
      Markers; belegt durch den Frontmatter-Parsetest für Weiterleitungen und Vollkopien
- [ ] Eine Datei mit altem Marker wird weiterhin als generiert erkannt und per `--refresh-aliases` angehoben
- [ ] Markierte Kurz-Befehle lassen sich in einem Bereich ohne Handarbeit entfernen, projekteigene bleiben
      stehen
- [ ] Die 15 versionierten Kopien tragen den Marker in neuer Position (`test_repo_own_aliases_147` grün)
- [ ] Die Abweichungen (a) bis (d) vom Ticket-DoD sind in der Auslieferung benannt
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf grün)

## Acceptance Criteria

- **AC-1:** Given eine mit `alias_content` erzeugte Weiterleitung / When ihr Frontmatter geparst wird / Then
  beginnt die Datei mit `---`, `description` ist der echte Text `Kurz-Alias für /agent-os-openspec:<name>` und
  die erste Zeile nach dem Frontmatter ist der Marker
  - Test: `tests/test_alias_marker_position_251.py::test_redirect_frontmatter_parses_and_marker_follows_it`
- **AC-2:** Given eine mit `alias_content` erzeugte Vollkopie (`disable-model-invocation: true`) / When ihr
  Frontmatter geparst wird / Then ist `description` die echte Beschreibung aus dem `SKILL.md`, der Marker steht
  direkt nach dem Frontmatter, und der Rest des Skill-Inhalts ist unverändert
  - Test: `tests/test_alias_marker_position_251.py::test_full_copy_frontmatter_parses_and_marker_follows_it`
- **AC-3:** Given eine Datei mit dem alten Marker in Zeile 1 / When `is_alias_file` und `find_stale_aliases`
  laufen / Then gilt sie als generiert und wird als veraltet gemeldet
  - Test: `tests/test_alias_marker_position_251.py::test_old_marker_in_line_one_still_recognized_and_stale`
- **AC-4:** Given eine Datei mit altem Marker im Projekt / When `setup.py --refresh-aliases` läuft / Then hat sie
  danach den Inhalt von `alias_content` (neue Position) und ist nicht mehr veraltet
  - Test: `tests/test_alias_marker_position_251.py::test_refresh_lifts_old_format_to_new_position`
- **AC-5:** Given eine unmarkierte projekteigene Datei, auch mit Marker-Text mitten im Inhalt / When
  `is_alias_file`, `--refresh-aliases` und `--remove-aliases` laufen / Then ist `is_alias_file` falsch und die
  Datei bleibt byte-gleich unverändert
  - Test: `tests/test_alias_remove_251.py::test_unmarked_file_untouched_by_detection_refresh_and_remove`
- **AC-6:** Given ein Bereich mit markierten und unmarkierten Dateien / When `setup.py <pfad> --remove-aliases`
  läuft / Then sind alle markierten Dateien gelöscht und die Ausgabe nennt gelöschte (`Removed:`) und behaltene
  (`Kept:`) Dateien namentlich
  - Test: `tests/test_alias_remove_251.py::test_remove_deletes_marked_and_reports_removed_and_kept`
- **AC-7:** Given ein Bereich ohne markierte Dateien oder ohne `.claude/commands/` / When `--remove-aliases`
  läuft / Then ist es ein No-op: nichts wird gelöscht, die Ausgabe meldet `0 removed`, Exit-Code 0
  - Test: `tests/test_alias_remove_251.py::test_remove_without_marked_files_is_noop`
- **AC-8:** Given `--remove-aliases --global` und ein gesetztes Home-Verzeichnis (Test-Home) / When es läuft /
  Then wirkt es auf `<home>/.claude/commands/` und nicht auf den Projektordner
  - Test: `tests/test_alias_remove_251.py::test_remove_global_targets_home_commands_dir`
- **AC-9:** Given `migrate_to_plugin.py` und ein Projekt mit projekteigenen Befehlen / When die Migration läuft /
  Then werden projekteigene Befehle weiterhin nicht gelöscht (bestehende Tests bleiben grün)
  - Test: `tests/test_alias_remove_251.py::test_migrate_to_plugin_keeps_project_commands_with_new_marker_files`
- **AC-10:** Given die 15 versionierten Kopien in `.claude/commands/` / When `find_stale_aliases` und die
  Marker-Position geprüft werden / Then ist die Liste der veralteten leer und jede Kopie trägt den Marker in der
  neuen Position
  - Test: `tests/test_alias_marker_position_251.py::test_repo_copies_carry_marker_in_new_position`
    (zusätzlich bleibt `tests/test_repo_own_aliases_147.py` grün)

> Die Test-Zuordnung wird **bei der Spec-Erstellung** eingetragen, nicht nachträglich: Nach der
> Freigabe ist diese Datei eingefroren (#230). Stimmt ein Testname später nicht mehr, gehört die
> Korrektur in die TDD-RED-Artefakte (`workflow.py add-artifact`), nicht in diese Datei.

## Test Plan

Automatische Tests (jeweils an eine AC oben gebunden):
- `pytest tests/test_alias_marker_position_251.py` (AC-1 bis AC-4, AC-10)
- `pytest tests/test_alias_remove_251.py` (AC-5 bis AC-9)
- Regression: `pytest tests/test_repo_own_aliases_147.py tests/test_setup_alias_sync_150.py
  tests/test_setup_command_aliases.py tests/test_session_banner.py` sowie `pytest tests/test_migrate_*.py` und
  die gesamte Suite

Nicht automatisch prüfbar: ob Claude Code die Beschreibung im Auswahlmenü tatsächlich anzeigt. Belegt ist
nur, dass das Frontmatter parsbar ist und `description` den echten Text liefert; die Anzeige folgt laut
Claude-Code-Dokumentation aus genau diesem Feld.

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Reine Textoperation und ein Werkzeug auf Dateiebene: Regelweg, kein Modell nötig. Die Änderung
  verschiebt eine Marker-Zeile und löscht ausschließlich markierte Dateien; sie ändert keine Architektur. Sie
  kippt die Empfehlung aus #251 („alle 16 global") und damit nur im Sinne, dass keine globale Ablage gebaut wird;
  die Entscheidung aus #87 (pro Projekt) bleibt unberührt.

## Changelog

- 2026-10-03: Initial spec created
