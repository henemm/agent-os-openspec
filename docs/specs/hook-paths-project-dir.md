---
entity_id: hook_paths_project_dir
type: module
created: 2026-09-21
updated: 2026-09-21
status: draft
version: "1.0"
tags: [hooks, setup, migration]
test_targets: [tests/test_hook_paths_project_dir_165.py]
---

# Hook-Pfade über ${CLAUDE_PROJECT_DIR} statt cwd-relativ

## Approval

- [ ] Approved

## GitHub Issue

- **Issue:** #165

## Purpose

Hook-Kommandos in `.claude/settings.json` dürfen nicht mehr vom aktuellen
Arbeitsverzeichnis abhängen. Sie werden über `${CLAUDE_PROJECT_DIR}` verankert,
damit ein Hook auch dann startet, wenn die Sitzung in einem Unterordner steht.

## Source

- **File:** `setup.py` — `generate_settings_json()`
- **File:** `migrate_to_plugin.py` — `_patch_settings()` + `migrate()`

## Scope

- **Affected Files:** `setup.py`, `migrate_to_plugin.py`,
  `tests/test_hook_paths_project_dir_165.py` (neu), `CHANGELOG.md`
- **Estimated Changes:** ~120 LoC

## Implementation Details

### 1. `setup.py` — Erzeugung (Kopier-Modus)

Statt eines eingebackenen absoluten Pfads:

```
vorher:  python3 /Users/hem/Developer/X/.claude/hooks/edit_gate.py
nachher: python3 "${CLAUDE_PROJECT_DIR}/.claude/hooks/edit_gate.py"
```

`collect_hooks()` prüft weiterhin die Existenz der Datei auf der Platte,
liefert aber den Platzhalter-Pfad zurück. Die Anführungszeichen sind Pflicht:
Projektordner mit Leerzeichen (`Meditationstimer iOS`) brechen sonst.

### 2. `migrate_to_plugin.py` — Reparatur (Bestandsprojekte)

Neuer Schritt neben dem bestehenden Entfernen von Plugin-Hooks:
Jedes verbleibende Hook-Kommando, das eine Datei unter `.claude/hooks/`
referenziert (projekteigene Hooks wie `session_start.py`), wird auf die
Platzhalter-Form umgeschrieben — relativer wie absoluter Pfad, Zusatzargumente
bleiben erhalten. Bereits platzhalter-basierte Kommandos bleiben unverändert
(idempotent).

Zusätzlich wird `settings.local.json` mitverarbeitet, sofern sie einen
`hooks`-Abschnitt hat. Der `permissions`-Abschnitt wird nicht angefasst.

## Expected Behavior

- **`setup.py` erzeugt keine cwd-relativen Hook-Kommandos:** Jedes erzeugte
  Kommando in `settings.json` enthält `${CLAUDE_PROJECT_DIR}`.
- **`setup.py` erzeugt keine eingebackenen absoluten Projektpfade** mehr in
  Hook-Kommandos.
- **Pfade mit Leerzeichen funktionieren:** Der Platzhalter steht in
  doppelten Anführungszeichen.
- **`migrate_to_plugin.py` repariert projekteigene Hooks:** Ein Eintrag
  `python3 .claude/hooks/session_start.py` wird zu
  `python3 "${CLAUDE_PROJECT_DIR}/.claude/hooks/session_start.py"`.
- **Zusatzargumente überleben:** `qa_gate.py --hook-mode` behält `--hook-mode`.
- **Idempotenz:** Ein zweiter Lauf ändert nichts mehr.
- **`settings.local.json` wird mitgenommen**, falls dort Hooks registriert sind.
- **Plugin-Hooks bleiben entfernt** — das bestehende Verhalten ändert sich nicht.

## Error Handling

- Fehlt `settings.local.json` oder hat sie keinen `hooks`-Abschnitt: kein Fehler,
  Schritt wird übersprungen.
- Unlesbares JSON in `settings.local.json`: Warnung, `settings.json` wird
  trotzdem migriert.

## Out of Scope

- `hooks/hooks.json` (Plugin-Modus) — nutzt bereits `${CLAUDE_PLUGIN_ROOT}`.
- Reparatur der Bestandsprojekte selbst (separater Betriebsschritt nach dem Fix).
