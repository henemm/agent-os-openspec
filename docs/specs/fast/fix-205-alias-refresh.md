# Mini-Spec: Sicherer Refresh für veraltete Befehls-Kopien (#205)

## Problem

Der Session-Banner meldet veraltete Vollkopien in `~/.claude/commands/` und rät zum Pro-Projekt-Lauf
`setup.py <projekt> --command-aliases`. Der repariert nichts: der User-Scope gewinnt gegen den
Projekt-Scope (#87), die alte globale Kopie bleibt aktiv. Der globale Lauf wiederum legt für jeden
Skill eine Datei an (auch `70-deploy.md`) und überschattet projekteigene Befehle. Es gibt also keinen
sicheren, im Banner genannten Weg — und jedes Plugin-Update macht die Kopien erneut alt.

## Was ändert sich

- `setup.py`: neues Flag `--refresh-aliases` (Funktion `refresh_command_aliases`). Es erneuert nur
  Dateien, die schon existieren, den Framework-Marker tragen und vom Soll abweichen
  (`alias_sync.find_stale_aliases`, mit `loaded_version=FRAMEWORK_VERSION`). Es legt **nie** eine
  Datei an und kann deshalb nichts überschatten — auch für `~` sicher.
- `core/hooks/session_banner.py`: `_repair_hint` nennt für beide Scopes
  `python3 <installiert>/setup.py <scope> --refresh-aliases` (für `~` also `setup.py ~ --refresh-aliases`,
  nicht mehr den Pro-Projekt-Lauf).
- `tests/test_setup_command_aliases.py`: Tests für den Refresh-Modus.
- `tests/test_session_banner.py`: erwartete Hinweistexte an den neuen Befehl anpassen.
- `CHANGELOG.md` unter `[Unreleased]`. Keine Versionserhöhung: der Release-Schnitt gehört zu
  Epic #198 (Ziel 3.28.0) und #204.

## Was darf sich nicht ändern

- `--command-aliases` (Anlegen/Aktualisieren) verhält sich unverändert.
- Projekteigene, unmarkierte Befehle werden nie angefasst.
- Kopien mit beweisbar neuerem Marker werden nie herabgestuft.
- Der Banner blockiert nie den Session-Start; Fallback ohne auffindbare Installation bleibt
  „kein `setup.py`-Pfad“.

## Wo ich für dich entschieden habe

- **Update-only statt „globale Kopien löschen“:** Löschen würde `/50-implement` & Co. in Projekten
  ohne eigene Kopie entfernen (der Skill-Aufruf scheitert dort am Skill-Tool-Gate). Refresh
  bewahrt die Befehle und ist nach jedem Plugin-Update ein einziger sicherer Befehl.
- **Auch der Projekt-Scope bekommt den Refresh-Befehl:** gleiche Wirkung, aber ohne Anlegen neuer
  Dateien — sicherer als der bisherige `--command-aliases`-Lauf.

## Acceptance Criteria

- **AC-1:** Given eine veraltete markierte Kopie im Scope, When `--refresh-aliases` läuft, Then ist
  sie danach identisch zum Soll-Inhalt.
- **AC-2:** Given ein Skill ohne vorhandene Datei im Scope, When `--refresh-aliases` läuft, Then wird
  keine Datei angelegt.
- **AC-3:** Given eine unmarkierte Datei oder eine Kopie mit neuerem Marker, When `--refresh-aliases`
  läuft, Then bleibt sie byte-identisch.
- **AC-4:** Given eine veraltete Kopie im Scope `~`, When der Banner läuft, Then nennt er
  `setup.py ~ --refresh-aliases`.

## Manuelle Test-Schritte

1. Fake-HOME mit veralteter `50-implement.md` und ohne `70-deploy.md`: Refresh ausführen — erstere
   erneuert, `70-deploy.md` bleibt fern.
2. Banner danach: keine Warnzeile mehr.

## Test Plan

- `tests/test_setup_command_aliases.py`: vier neue Tests (AC-1 bis AC-3, plus Idempotenz).
- `tests/test_session_banner.py`: bestehende Hinweis-Asserts anpassen (AC-4).
- Volle Suite `python3 -m pytest tests/` + `python3 scripts/sync_skills.py --check`.
