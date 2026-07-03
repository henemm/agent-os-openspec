# Mini-Spec: feat-33-plugin-path-resolution (Stufe 1 von Issue #33)

## Problem
Alle 16 Plugin-Skills nutzen dasselbe Setup-Snippet:
```bash
_H="${CLAUDE_PLUGIN_ROOT:+${CLAUDE_PLUGIN_ROOT}/core/hooks}"; _H="${_H:-.claude/hooks}"
```
`CLAUDE_PLUGIN_ROOT` ist nur in Harness-Hook-Subprozessen gesetzt, NIE in manuellen
Bash-Aufrufen der Skills → der Fallback `.claude/hooks` greift in Consumer-Projekten
immer und trifft dort eingefrorene Legacy-Kopien, die nie Plugin-Updates bekommen
(strukturelle Doppelentwicklung; zweimal real passiert: #960, #29).

## Was ändert sich
Das Setup-Snippet in **allen 16 `skills/*/SKILL.md`** wird um eine mittlere
Auflösungsstufe erweitert. Neue Prioritätskette:

1. `CLAUDE_PLUGIN_ROOT` (wie bisher, wenn gesetzt)
2. **NEU:** `~/.claude/plugins/installed_plugins.json` lesen (python3-Einzeiler):
   ersten Eintrag für Plugin-Key `agent-os-openspec@*` nehmen (user-scope bevorzugt),
   dessen `installPath` + `/core/hooks` verwenden — aber nur, wenn das Verzeichnis
   tatsächlich existiert (`[ -d ]`-Guard gegen stale JSON)
3. `.claude/hooks` (Fallback wie bisher — Projekte ohne Plugin/Legacy-Installs
   funktionieren unverändert)

Das Snippet bleibt in allen 16 Skills identisch (ein Block, kopiert). Fehler beim
JSON-Lesen (Datei fehlt, kaputt, kein Eintrag) werden verschluckt (`2>/dev/null`,
leerer String) → Kette fällt sauber auf Stufe 3 durch.

**Nicht geändert:** `core/commands/*.md` (Legacy-Verteilweg via setup.py — dort ist
`.claude/hooks` die korrekte, gewollte Quelle).

Zusätzlich: `CHANGELOG.md`-Eintrag, Version 3.6.2 → 3.7.0 (MINOR, neues Verhalten).

## Was darf sich nicht ändern
- Harness-Hook-Kontext (CLAUDE_PLUGIN_ROOT gesetzt): identisches Verhalten wie bisher.
- Projekt ohne installiertes Plugin und ohne installed_plugins.json: identischer
  Fallback auf `.claude/hooks` wie bisher.
- Kein Glob auf den Cache-Ordner (Versionsnummer im Pfad!) — ausschließlich die
  JSON ist autoritativ.

## Manuelle Test-Schritte
1. In einem Consumer-Projekt (gregor_zwanzig) ohne CLAUDE_PLUGIN_ROOT das Snippet
   ausführen → `_H` zeigt auf `~/.claude/plugins/cache/.../3.7.0/core/hooks`
   (aktuelle Plugin-Version), nicht auf `.claude/hooks`.
2. Mit gesetztem CLAUDE_PLUGIN_ROOT → dieser gewinnt.
3. Mit HOME ohne installed_plugins.json → `.claude/hooks` wie bisher.

## Inline-Tests (werden während Implementierung geschrieben)
- [ ] Neues `tests/test_skill_path_resolution.py`: extrahiert das Snippet aus einer
      SKILL.md und führt es via `bash -c` mit präpariertem Fake-HOME aus —
      (a) JSON vorhanden + Verzeichnis existiert → installPath gewinnt,
      (b) CLAUDE_PLUGIN_ROOT gesetzt → gewinnt über JSON,
      (c) kein JSON → `.claude/hooks`-Fallback,
      (d) JSON zeigt auf nicht-existentes Verzeichnis → Fallback,
      (e) alle 16 Skills enthalten das identische neue Snippet (Konsistenz-Check).

## Folgestufen (separate Workflows, NICHT hier)
- Stufe 2 (#33c): `migrate_to_plugin.py` — `CORE_HOOKS` um 6 fehlende Framework-
  Dateien ergänzen; `hook_utils.py`/`config_loader.py` nicht blind löschen
  (projekteigene Hooks in gregor importieren sie — Shim oder Import-Umbau nötig).
- Stufe 3 (#33a): Legacy-Kopien in gregor_zwanzig tatsächlich entfernen — erst
  nachdem Stufe 1+2 deployed sind.
