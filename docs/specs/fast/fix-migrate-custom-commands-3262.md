# Fast Track: Migrationswerkzeug löscht keine projekteigenen Befehle mehr (3.26.2)

## Problem

`migrate_to_plugin.py::_find_removable_command_files` hält jede `.claude/commands/<name>.md` für
eine „legacy duplicate", sobald ein Plugin-Skill gleichen Namens existiert. Einzige
Schutzvorrichtung ist der `openspec-alias:`-Marker, den nur generierte Kurz-Aliase tragen. Der
Docstring verspricht ausdrücklich *„never touch project-specific custom commands"* — der Code hält
das nicht.

Gemessen am 2026-09-20 gegen `/home/hem/gregor_zwanzig`: Das Werkzeug meldete
`.claude/commands/70-deploy.md` als entfernbar. Diese Datei ist die vollständige
Produktions-Deploy-Prozedur des Projekts und sagt in ihrer zweiten Zeile selbst, dass sie das
generische Plugin-Template ersetzt. Ein `--apply` hätte sie gelöscht; `/70-deploy` wäre danach auf
Vercel/Heroku-Beispiele zurückgefallen, und aufgefallen wäre es beim nächsten Deploy.

`70-deploy` ist laut Framework-CLAUDE.md ausdrücklich ein **projektspezifisches Template, das
angepasst werden muss**. Eine angepasste Fassung ist also der vorgesehene Normalzustand — und
genau sie wurde zum Löschen vorgeschlagen.

## Scope

- `migrate_to_plugin.py::_find_removable_command_files` gibt zwei Listen zurück: nachweisliche
  Kopien und abweichende Dateien, die stehenbleiben
- `migrate_to_plugin.py::migrate` Abschnitt 6 berichtet beide getrennt; gelöscht wird nur die
  erste Liste
- Nicht enthalten: eine Ähnlichkeitsschwelle — siehe ADR
- Nicht enthalten: ein Flag zum Löschen der abweichenden Dateien. Wer sie los werden will, löscht
  sie selbst; das Werkzeug trifft diese Entscheidung nicht

## Definition of Done

`--apply` entfernt nur Dateien, die nachweislich inhaltsgleich zum ausgelieferten Skill sind. Jede
abweichende Datei bleibt erhalten und wird im Bericht mit Grund genannt, statt stillschweigend zu
verschwinden.

## Acceptance Criteria

- **AC-1:** Given eine projekteigene Fassung ohne Alias-Marker, When das Werkzeug läuft, Then steht
  sie nicht auf der Löschliste.
- **AC-2:** Given eine veraltete Framework-Kopie, die inhaltlich abweicht, When das Werkzeug läuft,
  Then steht sie ebenfalls nicht auf der Löschliste — ohne Beweis wird nicht gelöscht.
- **AC-3:** Given eine inhaltsgleiche Doppelung, When das Werkzeug läuft, Then wird sie weiterhin
  entfernt; der Zweck des Werkzeugs bleibt erhalten.
- **AC-4:** Given eine Kopie, die sich nur im Versions-Marker oder in Leerraum unterscheidet, When
  das Werkzeug läuft, Then gilt sie als Kopie und wird entfernt.
- **AC-5:** Given eine Datei mit `openspec-alias:`-Marker bzw. ohne gleichnamigen Skill bzw. nicht
  lesbar, When das Werkzeug läuft, Then bleibt sie unangetastet (Bestandsverhalten).
- **AC-6:** Given eine Datei bleibt wegen Abweichung stehen, When der Trockenlauf berichtet, Then
  nennt er Datei und Grund.
- **AC-7:** Given beide Fälle liegen gleichzeitig vor, When der Trockenlauf berichtet, Then stehen
  sie in getrennten Listen.

## Test Plan

- `tests/test_migrate_custom_commands_160.py`: 10 Tests (AC-1 bis AC-7), echte Projektordner auf
  `tmp_path`, echtes Plugin-Verzeichnis per `monkeypatch` auf `PLUGIN_ROOT`.
- RED vor dem Fix: 4 von 10 rot. Grün blieben die sechs Bestandsgarantien — der Fix darf sie nicht
  eintauschen.

## ADR

**Entscheidung:** Gelöscht wird nur bei **Inhaltsgleichheit** zum ausgelieferten Skill, nachdem
Alias-Kommentar, Versions-Marker und Leerraum normalisiert wurden. Kein Ähnlichkeitsmaß.

**Verworfene Alternative — Ähnlichkeitsschwelle (`difflib`):** an echten Daten gemessen
(Plugin 3.26.1):

| Fall | Ähnlichkeit |
|------|-------------|
| Alt-Kopien `/var/www/henemm` (Framework 3.3.0) | 0.221 – 0.640 |
| Echte Anpassung gregor `70-deploy` | 0.028 |

Eine Schwelle dazwischen wäre aus zwei Stichproben geraten. Für eine **löschende** Operation ist
das die falsche Art von Sicherheit: die Fehlerkosten sind asymmetrisch. Eine übersehene Doppelung
kostet einen doppelten Eintrag in der Befehlsliste; eine fälschlich gelöschte Datei kostet eine
Produktionsprozedur, und der Verlust fällt erst beim nächsten Deploy auf.

**Folge:** Das Werkzeug räumt weniger auf als bisher. Alte, abweichende Kopien bleiben liegen und
werden berichtet. Das ist beabsichtigt — das Werkzeug hört auf, an Stelle des Menschen zu
entscheiden, und verliert dafür seine Fähigkeit, unbemerkt Schaden anzurichten.
