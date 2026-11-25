---
entity_id: fix-668-handoff-idempotent
type: bugfix
created: 2026-11-25
updated: 2026-11-25
status: draft
version: "1.0"
workflow: fix-668-handoff-idempotent
tags: [auftrag, workflow, herdr, cloud, epic-649]
---

# Übergabe an frische Sitzung idempotent (Issue #668, Epic #649)

## Approval

- [ ] Approved

## Purpose

Die Übergabe des nächsten Auftrags-Issues an eine frische Sitzung (#667) darf nie zwei Sitzungen für dasselbe Issue starten. Heute kann das passieren: Nach einer Cloud-Übergabe (`handoff --mark cloud`) meldet ein erneuter `handoff`-Aufruf weiter `HANDOFF=cloud` ohne Hinweis auf die schon erfolgte Übergabe, und im Herdr-Weg führt ein Fehler beim Vermerken nach erfolgreichem Start zu `STARTED=no` und damit zum Rückfall auf den Selbstaufruf. Zusätzlich wird der Vermerk ohne Sperre über einen veralteten Lesestand geschrieben.

## Source

- **File:** `core/hooks/workflow.py`, `core/commands/60-validate.md`, `core/commands/70-deploy.md`, `core/commands/80-workflow.md`
- **Identifier:** `workflow.cmd_handoff`, `workflow._handoff_mark`

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `hook_utils.read_auftrag` / `write_auftrag` / `auftrag_path` / `auftrag_owner_key` | Funktion | Auftrag frisch lesen und schreiben, Pfad für die Sperre |
| `herdr_bridge._pp_flock` | Funktion | Exklusive Datei-Sperre (max ~2 s, fail-open) |
| `herdr_bridge.start_session` | Funktion | Herdr-Start (unverändert) |
| `tests/test_handoff_667.py` | Test | Bestandsverhalten #667 |

## Scope

### Affected Files

| Datei | Änderung |
|-------|----------|
| `core/hooks/workflow.py` | `cmd_handoff`: `HANDOFF_DONE=`, `MARKED=`, `WARN=`; `_handoff_mark` unter Sperre mit Neulesen |
| `core/commands/60-validate.md`, `core/commands/70-deploy.md` | Kettenabsatz: bei `HANDOFF_DONE=` keine weitere Sitzung |
| `core/commands/80-workflow.md` | Doku der neuen Zeilen |
| `skills/*/SKILL.md` | generiert (`scripts/sync_skills.py`) |
| `tests/test_handoff_668.py` | neue Tests |
| `CHANGELOG.md`, `.claude-plugin/plugin.json` | Version |

### Estimated Changes

- ca. 40 LoC Python, ca. 10 Zeilen Befehlstext, ca. 150 LoC Tests

## Implementation Details

- Vermerk-Prüfung: `done = auftrag.get("handoff")` aus dem beim Aufruf gelesenen Auftrag. Ist der Weg ≠ `none` und `done["issue"] == NEXT`, folgt nach `NEXT=` (bzw. nach `REPO_URL=` im Cloud-Weg) die Zeile `HANDOFF_DONE=<mode des Vermerks>`. Die übrigen Zeilen und der Startauftrag bleiben (Rückwärtskompatibilität).
- `--mark <weg>`: Zeile `MARKED=yes|no` (no: Weg `none` oder Schreibfehler, dann zusätzlich `WARN=<kurz>` bei Fehler).
- `_handoff_mark(root, number, mode)`: Sperre `herdr_bridge._pp_flock(auftrag_path(root, auftrag_owner_key()))`, dann `read_auftrag(root)` neu, Feld `handoff` setzen, `write_auftrag`; Sperre im `finally` freigeben. Ohne Sperre (Timeout) fail-open weiter. Kein Auftrag mehr → Exception (zählt als Fehlschlag).
- `--start` herdr: `start_session` ok → `STARTED=yes`; der Vermerk läuft in eigenem try; Fehlschlag → zusätzlich `WARN=Vermerk fehlgeschlagen (<Exception-Typ>)`, `STARTED` bleibt `yes`.
- Zeilenreihenfolge: `HANDOFF`, `NEXT`, [`REPO_URL`], [`HANDOFF_DONE`], [`MARKED`], [`STARTED`], [`REASON` | `WARN`], dann ggf. `PROMPT_BEGIN … PROMPT_END`.
- Befehlstexte 60-validate/70-deploy: vor der Wegverzweigung: „Steht `HANDOFF_DONE=` in der Ausgabe, ist #M schon übergeben: ⏳-Zeile ausgeben, Turn beenden, weder `create_session` noch `--start` noch Selbstaufruf.“

## Expected Behavior

- **Input:** Auftrag mit optionalem Feld `handoff`, Argumente `--start` / `--mark <weg>`, Umgebung wie #667
- **Output:** wie #667, zusätzlich `HANDOFF_DONE=<weg>` bei bestehendem Vermerk für `NEXT`, `MARKED=yes|no` bei `--mark`, `WARN=` bei gescheitertem Vermerk
- **Side effects:** Vermerk wird unter Sperre auf den frisch gelesenen Auftrag geschrieben; parallel geänderte Felder (z. B. abgehakte Issues) bleiben erhalten

## Known Limitations

- Die Sperre ist fail-open (nach ~2 s ohne Sperre weiter) wie alle Sperren über `_pp_flock`; andere Schreiber des Auftrags (`queue`, `complete`) nehmen die Sperre nicht, das Neulesen verkleinert das Zeitfenster nur.
- Ob Claude den Befehlstext befolgt, erzwingt kein Hook.

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] Ein zweiter `handoff`-Aufruf nach Cloud- oder Herdr-Übergabe meldet `HANDOFF_DONE=` und die Befehlstexte starten dann keine weitere Sitzung
- [ ] Ein gescheiterter Vermerk nach erfolgreichem Herdr-Start meldet `STARTED=yes` mit `WARN=`
- [ ] Keine bestehende Funktion ist kaputtgegangen (`pytest tests/` grün, `skills/` ohne Drift), CHANGELOG und Version veröffentlicht

## Acceptance Criteria

- **AC-1:** Given autarker Auftrag im Auto-Modus, Cloud-Env, und `handoff --mark cloud` lief bereits für NEXT=548 / When `workflow.py handoff` erneut läuft / Then enthält die Ausgabe `HANDOFF=cloud`, `NEXT=548`, `REPO_URL=…` und danach `HANDOFF_DONE=cloud`; ohne Vermerk oder mit Vermerk für eine andere Nummer fehlt `HANDOFF_DONE=`
  - Test: tests/test_handoff_668.py::test_handoff_done_after_mark_cloud

- **AC-2:** Given Herdr-Weg mit Fake-Binary und ein erfolgreicher `handoff --start` / When `workflow.py handoff` (ohne Argumente) erneut läuft / Then enthält die Ausgabe `HANDOFF_DONE=herdr`
  - Test: tests/test_handoff_668.py::test_handoff_done_after_herdr_start

- **AC-3:** Given `--mark cloud` bei Weg ≠ none bzw. bei Weg `none` / When der Befehl läuft / Then lautet die Zeile `MARKED=yes` bzw. `MARKED=no`, Exit 0
  - Test: tests/test_handoff_668.py::test_marked_line

- **AC-4:** Given ein Auftrag, der zwischen dem Lesen durch `handoff` und dem Schreiben des Vermerks extern geändert wurde (548 abgehakt per Datei) / When `_handoff_mark` schreibt / Then bleibt die externe Änderung erhalten und das Feld `handoff` ist gesetzt; während des Schreibens wird die Sperrdatei `<auftrag>.lock` exklusiv gehalten
  - Test: tests/test_handoff_668.py::test_mark_rereads_under_lock

- **AC-5:** Given Herdr-Weg, `start_session` erfolgreich, aber das Schreiben des Vermerks schlägt fehl / When `workflow.py handoff --start` läuft / Then lautet die Ausgabe `STARTED=yes` plus `WARN=` mit dem Wort „Vermerk“, kein `REASON=`, Exit 0
  - Test: tests/test_handoff_668.py::test_start_yes_when_mark_fails

- **AC-6:** Given die Befehlstexte `core/commands/60-validate.md` und `70-deploy.md` samt Skills / When ihr Kettenabsatz gelesen wird / Then nennen sie `HANDOFF_DONE=` mit der Anweisung, keine weitere Sitzung zu starten, `80-workflow.md` dokumentiert `HANDOFF_DONE`, `MARKED` und `WARN`; `sync_skills.py --check` ohne Drift
  - Test: tests/test_handoff_668.py::test_command_texts_handoff_done

## Test Plan

Subprozess-Tests nach dem Muster von `tests/test_handoff_667.py` (Helfer importiert), ohne Netz, mit explizit gesetztem Env.

- GIVEN Vermerk cloud WHEN `handoff` THEN `HANDOFF_DONE=cloud` (AC-1)
- GIVEN Herdr-Start erfolgt WHEN `handoff` THEN `HANDOFF_DONE=herdr` (AC-2)
- GIVEN `--mark` WHEN Weg cloud/none THEN `MARKED=yes/no` (AC-3)
- GIVEN In-Prozess-Aufruf mit veraltetem Auftrag WHEN `_handoff_mark` THEN externe Änderung erhalten, Sperre gehalten (AC-4)
- GIVEN schreibgeschützter Auftragsordner nach Start WHEN `--start` THEN `STARTED=yes`, `WARN=` (AC-5)
- GIVEN Befehlstexte WHEN gelesen THEN `HANDOFF_DONE` enthalten (AC-6)

Läufe: `pytest tests/test_handoff_668.py tests/test_handoff_667.py`, Regressionslauf `pytest tests/`, `python3 scripts/sync_skills.py --check`.

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Kleine Erweiterung der bestehenden Auskunfts-CLI `handoff` um eine Zeile; der Startauftrag bleibt ausgegeben, damit bestehende Leser nicht brechen. Die Sperre nutzt das vorhandene `_pp_flock`-Muster.
- **Alternative A, Startauftrag bei Vermerk weglassen:** verworfen, bricht Leser, die nur `PROMPT_BEGIN` erwarten; die Zeile `HANDOFF_DONE=` ist eindeutig genug.
- **Alternative B, `HANDOFF=done` als neuer Weg:** verworfen, ändert die Bedeutung von `HANDOFF=` für bestehende Befehlstexte.

## Changelog

- 2026-11-25: Initial spec created
