# Kontext: Hook-Kommandos mit cwd-relativem Pfad (Issue #165)

## Auslöser

Henning meldet aus `Meditationstimer`, dass jede Nutzer-Nachricht abbricht:

```
UserPromptSubmit operation blocked by hook: [python3 .claude/hooks/phase_listener.py]:
can't open file '/Users/hem/Developer/Meditationstimer/Meditationstimer/Meditationstimer iOS/Media/.claude/hooks/phase_listener.py':
[Errno 2] No such file or directory
```

## Recherche (zuerst, vor jeder Analyse)

Quelle: https://code.claude.com/docs/en/hooks

- Hook-Kommandos laufen im **aktuellen Arbeitsverzeichnis** der Sitzung —
  nicht im Projekt-Root.
- Für Pfad-Referenzen ist `${CLAUDE_PROJECT_DIR}` vorgesehen: „the project root
  where the session started".
- Dokumentiertes Beispiel:
  `"command": "${CLAUDE_PROJECT_DIR}/.claude/hooks/check-style.sh"`

## Reproduktion (verifiziert, identische Fehlermeldung)

```
cd "/Users/hem/Developer/Meditationstimer/Meditationstimer/Meditationstimer iOS/Media"
python3 .claude/hooks/phase_listener.py
→ can't open file '.../Media/.claude/hooks/phase_listener.py': [Errno 2] No such file or directory
```

Die Hook-Datei existiert — unter `<projekt-root>/.claude/hooks/phase_listener.py`.
Nur die Auflösung des relativen Pfads schlägt fehl.

## Ist-Zustand im Framework

| Ort | Zustand |
|-----|---------|
| `hooks/hooks.json` (Plugin-Modus) | `${CLAUDE_PLUGIN_ROOT}/...` — korrekt, nicht betroffen |
| `setup.py` → `generate_settings_json_plugin_mode()` | übernimmt `hooks.json` — korrekt |
| `setup.py` → `generate_settings_json()` (Kopier-Modus) | schreibt `python3 <absoluter Pfad>` (`Path(...).resolve()`, Zeile 1057). Läuft heute, bricht aber beim Verschieben/Umbenennen des Projekts |
| `migrate_to_plugin.py` | entfernt Plugin-Hooks aus `settings.json`; **projekteigene** Hooks behalten ihren relativen Pfad |
| `migrate_to_plugin.py` | verarbeitet `settings.local.json` gar nicht |

Die relativen Pfade in den Bestandsprojekten stammen aus einer älteren
`setup.py`-Fassung, die den übergebenen Projektpfad nicht auflöste
(`setup.py .` → `.claude/hooks/...`).

## Betroffene Bestandsprojekte (Scan über ~/Developer)

| Projekt | Relative Hook-Einträge |
|---------|------------------------|
| `Meditationstimer/Meditationstimer` | 4 Kern-Hooks + `session_start.py` (projekteigen) |
| `my-daily-sprints` | 7 Hooks |
| `gregor-zwanzig` | 10+ Hooks (überwiegend projekteigene Alt-Hooks) |

## Abgrenzung

Der Fehler ist **kein** Workflow-/Gate-Problem. Kein Hook hat inhaltlich
blockiert — der Interpreter fand die Datei nicht. Die Meldung
„operation blocked by hook" ist nur die Verpackung des Startfehlers.
