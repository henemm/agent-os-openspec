# Fast Track: Update erhält lokale Anpassungen (#72)

## Problem

`setup.py --update` ersetzte jede Framework-Datei im Projekt, deren Inhalt von der Framework-Fassung
abwich. Das traf auch bewusst ergänzte Abschnitte in Projekt-Agenten (gregor_zwanzig, Update-Commit
d821e7c9: `user-story-planner.md`, `external-validator.md`). Modul-Dateien wurden beim Update sogar
ohne jeden Vergleich neu kopiert. Nichts davon wurde gemeldet.

## Scope

- `setup.py`: Manifest `.claude/framework_manifest.json` (Hash je geschriebener Datei); `sync_file` entscheidet zwischen neu, unverändert, aktualisieren, lokal geändert (`<name>.new` daneben) und Altinstallation (Sicherung unter `.claude/update-backups/`); `update_project`, `install_module` und die Erstinstallation nutzen es; Warnblock in der Update-Zusammenfassung
- `README.md`: Abschnitt „Updating an Existing Installation“ beschreibt das echte Verhalten
- Nicht enthalten: automatischer 3-Wege-Merge; Plugin-Modus (dort liefert `claude plugin update` die Dateien, Projektdateien werden nicht angefasst)

## Definition of Done

Der Fundfall (lokal ergänzter Abschnitt in einer Agent-Datei) ist durch einen Test belegt, der ohne die Änderung rot ist; die volle Suite bleibt grün.

## Acceptance Criteria

- **AC-1:** Given eine Erstinstallation, When sie abgeschlossen ist, Then enthält `.claude/framework_manifest.json` einen Hash für jede installierte Hook-, Befehls- und Agent-Datei.
- **AC-2:** Given eine seit dem letzten Framework-Schreiben lokal geänderte Agent-, Befehls- oder Modul-Datei und eine inzwischen geänderte Framework-Fassung, When `--update` läuft, Then bleibt sie unverändert, die Framework-Fassung liegt als `<name>.new` daneben und die Ausgabe nennt die Datei unter „LOKAL GEAENDERT“.
- **AC-3:** Given eine Datei, die dem zuletzt vom Framework geschriebenen Stand entspricht, When `--update` läuft, Then wird sie auf die neue Framework-Fassung aktualisiert.
- **AC-4:** Given eine Installation ohne Manifest und eine abweichende Datei, When `--update` läuft, Then wird sie überschrieben, die alte Fassung unter `.claude/update-backups/<zeit>/` gesichert und die Ausgabe meldet das.
- **AC-5:** Given `--update --force`, When eine Datei lokal geändert ist, Then wird sie trotzdem überschrieben und keine `.new`-Datei angelegt.
- **AC-6:** Given eine lokal geänderte Datei, When `--update` mehrfach läuft, Then bleibt die Anpassung erhalten; dieselbe Framework-Fassung wird nur einmal als `.new` angeboten und gemeldet (nach dem Zusammenführen keine erneute Warnung); stimmt die Datei später mit der Framework-Fassung überein, wird die `.new`-Datei entfernt.

## Test Plan

- `tests/test_setup_update_keeps_local_72.py` (AC-1 bis AC-6), bestehende `tests/test_setup_*`, volle Suite
