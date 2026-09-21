# Mini-Spec: Session-Banner empfiehlt keinen schädlichen Reparatur-Befehl mehr (#163)

## Problem

`session_banner.py` meldet Alias-Kopien als „veraltet" und druckt einen Reparatur-Befehl. Zwei Fehler:

1. `find_stale_aliases()` vergleicht nur Inhalte auf Gleichheit, nicht Versionen. Eine Kopie mit
   *neuerem* Marker als die Session gilt ebenfalls als „veraltet" — der Befehl würde sie durch
   ältere Dateien ersetzen (Downgrade).
2. Der Befehl zeigt auf `CLAUDE_PLUGIN_ROOT` (die beim Session-Start eingefrorene Version) und für
   den Scope `~` auf den globalen Lauf, vor dem `setup.py` selbst warnt (#87: User-Scope
   überschattet projekteigene Befehle). Real passiert am 2026-09-21: globales `70-deploy.md`
   angelegt, das `gregor_zwanzig/.claude/commands/70-deploy.md` überschattete.

## Was ändert sich

- `core/hooks/alias_sync.py`: liest die Version aus der `⚙ /<name> · agent-os-openspec <x.y.z>`-Zeile
  einer Alias-Kopie und vergleicht numerisch (nicht als String). Neue Funktion für „Kopie ist
  beweisbar neuer als die geladene Version".
- `core/hooks/session_banner.py`:
  - Kopien, die beweisbar **neuer** sind als die geladene Version, werden nicht gemeldet.
  - Kein Marker / nicht lesbare Version → wird gemeldet wie bisher (nur „beweisbar neuer" unterdrückt).
  - Reparatur-Pfad kommt aus der **installierten** Version (`installed_plugins.json`, Eintrag
    `agent-os-openspec@…`, bevorzugt `scope: user`; Version aus deren `plugin.json`).
    Lässt sich das nicht auflösen: **kein** `setup.py`-Pfad in der Meldung — nie der Session-Pfad.
  - Scope `~`: kein Befehl, sondern Verweis auf den Pro-Projekt-Lauf
    (`python3 <installiert>/setup.py <projekt> --command-aliases`).
- `tests/test_session_banner.py`: zwei bestehende Tests prüfen genau die fehlerhaften Strings und
  werden umgeschrieben; neue Tests für die drei Fälle aus dem Issue + Fallback.
- `CHANGELOG.md` (`[Unreleased]`), Version 3.26.3 (`plugin.json`, `setup.py`, `CLAUDE.md`),
  `sync_skills.py` neu laufen lassen (Marker trägt die Version).

## Was darf sich nicht ändern

- Der Banner blockiert nie den Session-Start: jede Exception → still, Exit 0.
- Erste Zeile `agent-os-openspec <Version> aktiv` bleibt unverändert.
- Projekteigene Befehle ohne Marker bleiben tabu (nie gemeldet).
- `setup.py` und `find_stale_aliases`-Semantik für Aufrufer außerhalb des Banners bleiben gleich.

## Wo ich für dich entschieden habe

- **Nur bei Beweis unterdrücken:** Eine Kopie ohne lesbare Version (z. B. reiner Redirect, oder
  Vollkopie einer Vorversion ohne Marker) wird weiter gemeldet. Lieber eine Meldung zu viel als
  ein still liegengebliebener Reparaturfall.
- **Vergleich gegen die geladene Version**, nicht gegen die installierte — so steht es im Issue.
- **Kein Pfad statt falscher Pfad:** Ist die installierte Version nicht auffindbar, nennt der Banner
  die Abweichung ohne Befehl.

## Offene Frage an dich (PO) — nicht Teil dieses Fixes

Eine veraltete **globale** Kopie überschattet (#87) projekteigene Befehle und wird von einem
Pro-Projekt-Lauf **nicht** repariert. Die ehrliche Abhilfe wäre, sie zu **löschen**. Das Issue
verlangt nur den Verweis auf den Pro-Projekt-Lauf; das setze ich um. Soll der Banner für `~`
stattdessen zum Entfernen der globalen Kopien raten? → Falls ja, eigenes Issue.

## Acceptance Criteria

- **AC-1:** Given eine Session auf älterer Version und eine Alias-Datei mit neuerem Marker, When der
  Banner läuft, Then erscheint keine „Veraltete Befehls-Kopien"-Meldung für diese Datei.
- **AC-2:** Given eine Alias-Datei mit älterem Marker, When der Banner läuft, Then wird sie gemeldet
  und der genannte `setup.py`-Pfad liegt in der installierten Version, nicht im Session-Root.
- **AC-3:** Given eine veraltete Kopie im Scope `~`, When der Banner läuft, Then nennt er den
  Pro-Projekt-Lauf und nie `setup.py ~ --command-aliases`.
- **AC-4:** Given die installierte Version ist nicht auflösbar (`installed_plugins.json` fehlt/defekt),
  When der Banner läuft, Then enthält die Meldung keinen `setup.py`-Pfad.
- **AC-5:** Given Versionen wie `3.9.0` vs. `3.25.0`, When verglichen wird, Then entscheidet der
  numerische Vergleich (3.25.0 ist neuer).

## Manuelle Test-Schritte

1. Banner gegen die echte Umgebung ausführen (`CLAUDE_PLUGIN_ROOT` auf eine ältere Version setzen,
   z. B. 3.24.0): keine Meldung für Kopien mit 3.25.0/3.26.x-Marker.
2. Eine Kopie im Fake-HOME auf älteren Marker setzen: Meldung nennt Pfad der installierten Version.

## Test Plan

- `tests/test_session_banner.py`: bestehende Tests `test_full_copy_for_now_invocable_skill_is_stale`
  und `test_outdated_full_copy_in_project_is_stale` umschreiben; neu: neuere Kopie (AC-1), ältere
  Kopie + installierter Pfad per Fake-`installed_plugins.json` (AC-2), Scope `~` (AC-3), Fallback
  ohne `installed_plugins.json` (AC-4), Versionsvergleich `3.9.0` < `3.25.0` (AC-5).
- Volle Suite (`python3 -m pytest tests/`) + `scripts/sync_skills.py --check`.
