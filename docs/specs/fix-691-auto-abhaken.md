---
entity_id: fix-691-auto-abhaken
type: bugfix
created: 2026-11-26
updated: 2026-11-26
status: draft
version: "1.0"
workflow: fix-691-auto-abhaken
tags: [workflow, ship-status, auftrag, archiv, auto-modus]
---

# Auto-Modus: ausgeliefertes Issue wird abgehakt und der Workflow archiviert (Issue #691)

## Approval

- [ ] Approved

## Purpose

Im Auto-Modus liefert `/60-validate` selbst bis `main` aus (`scripts/ship.py --merge`, danach `workflow.py ship-status done`), ruft aber nie `workflow.py finish` auf. Der Workflow bleibt in `phase8_complete` aktiv, das Issue steht im Auftrag weiter als offen und `queue` schlägt es erneut als nächstes vor. Künftig schließt `ship-status done|skipped` den Workflow mechanisch ab (Archiv, Log, Abhaken im Auftrag), ohne dass jemand an `finish` denken muss.

## Source

- **File:** `core/hooks/workflow.py`, `core/commands/60-validate.md`, `skills/60-validate/SKILL.md` (generiert), `CHANGELOG.md`
- **Identifier:** neu `_finalize_archive(data, name)` (Abschluss-Teil aus `cmd_complete` herausgelöst); geändert `cmd_ship_status` (`done`/`skipped`-Zweig) und `cmd_complete` (nutzt den Helfer)

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `workflow.cmd_complete` | function | bisher einziger Ort für Archivierung und Abhaken (#551); nutzt künftig denselben Helfer |
| `workflow.cmd_write_log` | function | schreibt das Execution-Log `.claude/workflows/_log/<datum>_<name>.yaml` (für `/90-retro`) |
| `workflow.cmd_ship_status`, `_ship_fallback_target`, `_status_target`, `_claim_release` | function | Zielauflösung (aktiv, Archiv, `<nr\|name>`) und Statusschreiben |
| `workflow._archive_dir`, `_workflow_file`, `_persist_env`, `_herdr` | function | Archivieren, Arbeitsdatei löschen, Aktiv-Zeiger, Seitenleiste |
| `hook_utils.auftrag_mark_done` | function | Abhaken im Auftrag; wirft nie, `False` ohne Auftrag/Nummer |
| `scripts/ship.py` | script | ruft nach erfolgreichem Merge `ship-status done "PR N gemergt"` (unverändert) |
| `scripts/sync_skills.py` | script | erzeugt `skills/60-validate/SKILL.md` aus `core/commands/60-validate.md` |
| `docs/specs/feat-551-auftragsliste.md`, `feat-525-auto-ship.md`, `feat-612-plan-kopf-auslieferung.md` | spec | Vorgänger zu Auftrag, Auto-Auslieferung und `ship-status` |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| core/hooks/workflow.py | MODIFY | Helfer `_finalize_archive`; `cmd_ship_status` ruft ihn bei `done`/`skipped` fail-open; `cmd_complete` nutzt ihn ohne Verhaltensänderung |
| tests/test_ship_status_finalize_691.py | CREATE | Subprozess-Tests mit `cwd=tmp_path` (Muster `tests/test_auftrag_551.py`) |
| core/commands/60-validate.md | MODIFY | Ein Satz in Step 4: `ship-status done` schließt den Workflow ab, `finish` danach nicht nötig |
| skills/60-validate/SKILL.md | REGENERATE | `python3 scripts/sync_skills.py` (nie von Hand) |
| CHANGELOG.md | MODIFY | Eintrag unter [Unreleased] |

### Estimated Changes

- Files: 5 (davon 1 generiert)
- LoC: ca. +60 bis +90 Produktivcode in `workflow.py`, ca. +150 Tests
- Nicht Teil: `config.yaml` (keine neue Einstellung), `scripts/ship.py`, Verhalten von `running`/`failed`. Hohes Adversary-Risiko, weil `workflow.py` ein Kern-Hook ist.

## Implementation Details

Kopplung an „Phase 8 und ausgeliefert“ statt an einen zusätzlichen Befehl im Anweisungstext. `ship.py` setzt `ship-status done` mechanisch nach dem Merge, der Abschluss greift also ohne Zutun von Claude.

Beim Status `done` oder `skipped` (nach dem Setzen von `ship_status` und `_claim_release`, alles in try/except):

1. Ziel nicht archiviert (Datei in `.claude/workflows/`) und `current_phase == phase8_complete`: Execution-Log schreiben, falls kein `_log/*_<name>.yaml` existiert; dann wie `complete` archivieren (Datei ins Archiv, Arbeitsdatei löschen). `_persist_env(None)` und `_herdr("clear")` nur, wenn das Ziel der aktive Workflow der Sitzung ist; der Aktiv-Zeiger einer fremden Sitzung bleibt unberührt. Danach `auftrag_mark_done` für die Issue-Nummer des Ziels und zusätzliche Ausgabezeile `ARCHIVED=<name>`.
2. Ziel bereits im Archiv (`complete` lief vorher): nur `auftrag_mark_done` (idempotent, kein zweites Archivieren).
3. Ziel nicht in Phase 8 (z. B. Hand-Aufruf in Phase 6): nur Status wie bisher, kein Archiv, kein Abhaken.
4. Fehler im Abschluss ändern weder die Ausgabe `SHIP_STATUS=<status>` noch den Exit-Code.

`cmd_complete` ruft denselben Helfer für Archivierung und Aufräumen auf; sein sichtbares Verhalten bleibt gleich. `running` und `failed` bleiben unverändert (kein Abschluss).

Verworfen: nur Anweisungstext („nach Merge `write-log` und `finish`“) — genau das Vergessen ist der Befund. Abhaken schon bei `phase phase8_complete` — das Issue gälte als erledigt, bevor ausgeliefert ist (CI rot).

## Expected Behavior

- **Input:** `workflow.py ship-status done|skipped [Notiz]` (auch mit `<nr|name>`) gegen einen Workflow in `phase8_complete`
- **Output:** wie bisher `SHIP_STATUS=<status>`, zusätzlich `ARCHIVED=<name>` bei erfolgter Archivierung; Exit-Code unverändert
- **Side effects:** Workflow liegt im Archiv, Log vorhanden, Arbeitsdatei weg, Auftrag hakt das Issue ab (`done`); `queue` schlägt es nicht mehr vor

## Known Limitations

- Ein von Hand zu früh gesetztes `ship-status done` (Phase < 8) schließt nichts ab; der Abschluss kommt dann über `finish` wie bisher.
- Ohne Auftragsdatei oder Issue-Nummer ist das Abhaken ein stiller No-op (wie in `cmd_complete`).

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] Nach einer Auto-Auslieferung (`ship.py --merge`) ist der Workflow archiviert und das Issue im Auftrag als erledigt markiert; `queue` schlägt es nicht mehr als nächstes vor
- [ ] Ein von Hand zu früh gesetztes `ship-status done` archiviert und hakt nichts ab
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf grün)

## Acceptance Criteria

- **AC-1:** Given ein aktiver Workflow in `phase8_complete` mit Issue-Nummer im Auftrag (`open`) / When `ship-status done` läuft / Then liegt der Workflow im Archiv, die Arbeitsdatei in `.claude/workflows/` ist weg und das Issue steht im Auftrag auf `done`
  - Test: tests/test_ship_status_finalize_691.py::test_done_in_phase8_archives_and_marks_done
- **AC-2:** Given derselbe Fall ohne vorhandenes Execution-Log / When `ship-status done` läuft / Then existiert danach `_log/*_<name>.yaml`; existierte bereits ein Log, wird es nicht überschrieben
  - Test: tests/test_ship_status_finalize_691.py::test_log_written_if_missing_and_kept_if_present
- **AC-3:** Given ein aktiver Workflow in `phase8_complete` / When `ship-status done` oder `ship-status skipped` läuft / Then enthält die Ausgabe `SHIP_STATUS=<status>` und eine Zeile `ARCHIVED=<name>`, Exit-Code 0
  - Test: tests/test_ship_status_finalize_691.py::test_output_lines_and_exit_code
- **AC-4:** Given ein Workflow in `phase6_implement` / When `ship-status done` läuft / Then wird nur der Status gesetzt: nicht archiviert, nicht abgehakt, keine `ARCHIVED=`-Zeile
  - Test: tests/test_ship_status_finalize_691.py::test_done_before_phase8_only_sets_status
- **AC-5:** Given ein bereits per `finish` archivierter und abgehakter Workflow / When `ship-status done` (Archiv-Ziel) läuft / Then bleibt das Issue `done`, nichts wird doppelt archiviert und es gibt keinen Fehler; war es noch `open`, wird es jetzt abgehakt
  - Test: tests/test_ship_status_finalize_691.py::test_archived_target_idempotent_marking
- **AC-6:** Given zwei Workflows, A aktiv in der Sitzung, B per `ship-status done <nr|name>` als Ziel in `phase8_complete` / When der Abschluss für B läuft / Then wird B archiviert, der Aktiv-Zeiger von A bleibt erhalten
  - Test: tests/test_ship_status_finalize_691.py::test_foreign_target_keeps_active_pointer
- **AC-7:** Given `ship-status running` oder `failed` auf einem Workflow in `phase8_complete` / When der Befehl läuft / Then bleibt der Workflow aktiv und das Issue offen
  - Test: tests/test_ship_status_finalize_691.py::test_running_and_failed_do_not_finalize
- **AC-8:** Given ein Fehler im Abschluss (z. B. nicht beschreibbares Archiv oder defekte Auftragsdatei) / When `ship-status done` läuft / Then bleibt `SHIP_STATUS=done` ausgegeben und der Exit-Code 0 (fail-open)
  - Test: tests/test_ship_status_finalize_691.py::test_failure_in_finalize_is_fail_open
- **AC-9:** Given ein Workflow in `phase8_complete` / When `finish`/`complete` läuft (ohne vorheriges `ship-status`) / Then verhält es sich wie bisher: Log-Pflicht, Archiv, Abhaken, Aktiv-Zeiger gelöscht
  - Test: tests/test_ship_status_finalize_691.py::test_complete_behaviour_unchanged
- **AC-10:** Given `core/commands/60-validate.md` / When `scripts/sync_skills.py` läuft / Then steht in Step 4 der Satz zum Abschluss durch `ship-status done` in Befehl und generiertem Skill (kein Drift)
  - Test: tests/test_ship_status_finalize_691.py::test_validate_doc_mentions_finalize_and_skill_in_sync

> Die Test-Zuordnung steht bewusst schon hier: Nach der Freigabe ist diese Datei eingefroren (#230).

## Test Plan

Automatische Tests in `tests/test_ship_status_finalize_691.py`, jeweils als Subprozess gegen `workflow.py` mit `cwd=tmp_path` (Muster `tests/test_auftrag_551.py`, `tests/test_auto_ship_525.py`; Workflow-JSON und Auftragsdatei im Temp-Projekt angelegt):

- Test: GIVEN Workflow in `phase8_complete` und offener Auftrag WHEN `ship-status done` THEN Archiv, Arbeitsdatei weg, Auftrag `done` (AC-1)
- Test: GIVEN kein bzw. vorhandenes Log WHEN `ship-status done` THEN Log neu geschrieben bzw. unverändert (AC-2)
- Test: GIVEN `done` und `skipped` WHEN ausgeführt THEN `SHIP_STATUS=` plus `ARCHIVED=<name>`, Exit 0 (AC-3)
- Test: GIVEN Workflow in Phase 6 WHEN `ship-status done` THEN nur Status (AC-4)
- Test: GIVEN bereits archiviertes Ziel WHEN `ship-status done` THEN idempotent, ggf. nachträglich abgehakt (AC-5)
- Test: GIVEN fremdes Ziel WHEN Abschluss THEN Aktiv-Zeiger der Sitzung bleibt (AC-6)
- Test: GIVEN `running`/`failed` WHEN ausgeführt THEN kein Abschluss (AC-7)
- Test: GIVEN kaputte Auftragsdatei oder Archiv-Fehler WHEN `ship-status done` THEN Ausgabe und Exit unverändert (AC-8)
- Test: GIVEN `complete` WHEN ausgeführt THEN altes Verhalten (AC-9)
- Test: GIVEN Befehlstext und Skill WHEN verglichen THEN Satz vorhanden, kein Drift (AC-10)

Lauf: `pytest tests/test_ship_status_finalize_691.py`, danach Regressionslauf `pytest tests/test_auftrag_551.py tests/test_auto_ship_525.py` und die übrige Suite.

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Fehlerbehebung innerhalb der bestehenden Architektur; ein vorhandener Abschluss-Teil wird in einen Helfer gezogen und an einer zweiten, mechanisch ausgelösten Stelle (`ship-status done|skipped`) verwendet. Keine neue Komponente, keine Config, keine Schnittstellenänderung außer der zusätzlichen Ausgabezeile `ARCHIVED=`.

## Changelog

- 2026-11-26: Initial spec created
