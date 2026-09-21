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

## Definition of Done

- Kein von `setup.py` erzeugtes Hook-Kommando ist cwd-relativ oder enthält einen
  eingebackenen Projektpfad.
- `migrate_to_plugin.py` hinterlässt in `settings.json` und `settings.local.json`
  kein Hook-Kommando mit cwd-relativem Pfad.
- Der gemeldete Fall (`Meditationstimer`) startet seine Hooks wieder, nachgewiesen
  mit demselben Ablauf, der zuvor den Abbruch zeigte.
- Gesamte Testsuite grün, `scripts/sync_skills.py --check` ohne Drift.

## Acceptance Criteria

- **AC-1:** Given ein Projekt mit Leerzeichen im Ordnernamen / When `setup.py`
  die `settings.json` erzeugt / Then enthält jedes Hook-Kommando
  `"${CLAUDE_PROJECT_DIR}/.claude/hooks/<datei>.py"` in doppelten
  Anführungszeichen und keinen absoluten Projektpfad.
- **AC-2:** Given eine `settings.json` mit dem projekteigenen Eintrag
  `python3 .claude/hooks/session_start.py` / When `migrate_to_plugin.py --apply`
  läuft / Then steht dort
  `python3 "${CLAUDE_PROJECT_DIR}/.claude/hooks/session_start.py"`, während
  Plugin-Hooks weiterhin entfernt werden.
- **AC-3:** Given ein Hook-Kommando mit Env-Präfix und Zusatzargument / When es
  verankert wird / Then bleiben Präfix und Argument unverändert erhalten, und ein
  zweiter Lauf ändert nichts mehr (Idempotenz).
- **AC-4:** Given eine `settings.local.json` mit Hooks und einem
  `permissions`-Abschnitt / When die Migration läuft / Then sind die Hooks
  verankert und `permissions` ist unverändert; unlesbares JSON dort bricht die
  Migration der `settings.json` nicht ab.

## Test Plan

| Prüfung | Art | Ort |
|---------|-----|-----|
| AC-1 (Platzhalter, kein absoluter Pfad, gequotet) | automatisiert | `tests/test_hook_paths_project_dir_165.py` |
| AC-2 (projekteigener Hook verankert, Plugin-Hook entfernt) | automatisiert | ebenda |
| AC-3 (Präfix, Argumente, Idempotenz, absoluter Pfad) | automatisiert | ebenda |
| AC-4 (`settings.local.json`, `permissions`, kaputtes JSON) | automatisiert | ebenda |
| Defekt im Vorzustand belegt | Nachstellung | `git show HEAD:` beider Dateien, Ausführung gegen dieselben Fälle |
| Gemeldeter Fall läuft wieder | Nachstellung | Hook-Start aus dem Unterordner `Meditationstimer iOS/Media` |

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Begründung:** Die Änderung führt kein neues Konzept ein, sondern folgt der
  dokumentierten Vorgabe von Claude Code (`${CLAUDE_PROJECT_DIR}` für
  Hook-Pfade, https://code.claude.com/docs/en/hooks). Die geprüfte Alternative —
  jeden Hook den Projekt-Root selbst auflösen zu lassen — hilft nicht: Der
  Interpreter findet die Datei gar nicht erst, der Hook-Code läuft nie an.

## Error Handling

- Fehlt `settings.local.json` oder hat sie keinen `hooks`-Abschnitt: kein Fehler,
  Schritt wird übersprungen.
- Unlesbares JSON in `settings.local.json`: Warnung, `settings.json` wird
  trotzdem migriert.

## Out of Scope

- `hooks/hooks.json` (Plugin-Modus) — nutzt bereits `${CLAUDE_PLUGIN_ROOT}`.
- Reparatur der Bestandsprojekte selbst (separater Betriebsschritt nach dem Fix).
