---
entity_id: feat-510-plan-deploy-status
type: feature
created: 2026-11-02
updated: 2026-11-02
status: draft
version: "1.0"
workflow: feat-510-plan-deploy-status
tags: [herdr, workflow, plan, deploy]
---

# Plan-Pane: Deploy erst abgehakt, wenn wirklich deployt (Issue #510)

## Approval

- [ ] Approved

## Purpose

Der Workflow-Plan (#476/#478) sieht fertig aus, bevor die Software deployt ist: Deploy wird mit der Archivierung abgehakt, egal ob `/70-deploy` lief; ohne `deploy:`-Config fehlt der Schritt ganz; und „✔ 8 Fertig“ suggeriert schon in Phase 8 einen Abschluss. Künftig gilt Deploy erst als erledigt, wenn `/70-deploy` die `verify`-Nachprüfung erfolgreich durchlaufen und das per Marker im Workflow-State vermerkt hat. Der Plan zeigt den echten Deploy-Zustand (offen / läuft / fehlgeschlagen / erledigt) und meldet „abgeschlossen“ erst danach.

## Source

- **File:** `core/hooks/workflow.py`, `core/commands/70-deploy.md`
- **Identifier:** `render_plan`, `deploy_configured`, neu `deploy_mode`, neu `cmd_deploy_status` (`workflow.py deploy-status`), `_plan_watch`, `cmd_plan`

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `core/hooks/workflow.py` (#476, #478, #81) | module | `render_plan`, `_deploy_block`, `_deploy_config_steps`, `_archive_dir`, `_workflows_dir`, `_read_workflow`, `_atomic_write`, `issue_number` |
| `core/commands/70-deploy.md` | command | ruft künftig `deploy-status running/done/failed` |
| `skills/70-deploy/SKILL.md` | generiert | per `scripts/sync_skills.py` (falls vorhanden) |
| `tests/test_herdr_plan_deploy_sessionstart_478.py` | test | bestehende Erwartungen zu #478 werden an das neue Verhalten angepasst |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| core/hooks/workflow.py | MODIFY | `deploy_mode()`, `render_plan(..., deploy=...)` mit Deploy-Zustand, CLI `deploy-status` |
| core/commands/70-deploy.md | MODIFY | Marker setzen: `running` vor Step 3, `done` nach erfolgreichem verify, `failed` bei Abbruch/verify-Fehler |
| skills/70-deploy/SKILL.md | MODIFY | regeneriert |
| config.yaml | MODIFY | Kommentar zu `deploy.enabled: false` |
| tests/test_plan_deploy_status_510.py | CREATE | Renderer, CLI `deploy-status`, CLI `plan` |
| tests/test_herdr_plan_deploy_sessionstart_478.py | MODIFY | AC-2/AC-3/AC-4 von #478 an neues Verhalten anpassen |
| CHANGELOG.md | MODIFY | Eintrag unter [Unreleased] |

### Estimated Changes

- Files: 1 neu, 6 geändert
- LoC: +90 Produktion / +200 Test
- Risk Level: LOW (rein anzeigend plus ein neues, rein schreibendes State-Feld; keine Gate-Logik)

## Implementation Details

**State-Feld.** `deploy_status` im Workflow-JSON: `"running" | "done" | "failed"`, dazu `deploy_at` (ISO-Zeitstempel). Fehlt das Feld, gilt Deploy als offen.

**CLI `workflow.py deploy-status <running|done|failed> [<issue-nr|name>]`.** Ohne zweites Argument: aktiver Workflow; ist keiner aktiv, Fehler. Mit Argument: zuerst laufende Workflows, dann `_archive/` per Issue-Nummer (gleiches Muster wie `find`) bzw. exakten Namen; der jüngste Treffer im Archiv gewinnt. Schreibt atomar (`_atomic_write`) in genau die gefundene Datei — auch ins Archiv, weil Deploy typischerweise nach `finish` läuft. Ausgabe `DEPLOY_STATUS=<wert> (<name>)`, Exit 0; unbekannter Wert oder kein Treffer → Meldung auf stderr, Exit 1.

**Deploy-Modus.** `deploy_mode() -> "configured" | "unconfigured" | "off"`: `off`, wenn `deploy.enabled` explizit `false` ist; `configured`, wenn `command` und `verify` gesetzt sind (Regel aus #478); sonst `unconfigured`. Jede Ausnahme → `unconfigured`. `deploy_configured()` bleibt unverändert erhalten.

**Renderer.** `render_plan(data, archived=False, width=None, deploy=False)` bleibt pure. `deploy` akzeptiert zusätzlich die Modus-Strings; `True` ≙ `"configured"`, `False`/`"off"` ≙ kein Deploy-Schritt (Ausgabe wie bisher). Der Deploy-Schritt entfällt außerdem bei `data["status"] == "abandoned"` oder gesetztem `no_build_reason`.

Mit Deploy-Schritt:

- Schritt „8 Fertig“ heißt dann „8 Code fertig“ (Fast Track und voller Plan).
- Deploy-Zeile, wenn Phase 8 erreicht oder archiviert:
  - `deploy_status == "done"`: `✔ Deploy`, letzte Zeile `abgeschlossen`
  - `"running"`: `▶ Deploy  (läuft)`, letzte Zeile `Nächster: /70-deploy #N`
  - `"failed"`: `✘ Deploy  (fehlgeschlagen)`, letzte Zeile `Nächster: /70-deploy #N`
  - sonst: `▶ Deploy  (offen)` bzw. bei Modus `unconfigured` `▶ Deploy  (nicht eingerichtet)`, letzte Zeile `Nächster: /70-deploy #N`
- frühere Phasen: `○ Deploy`, Rest unverändert.
- Ohne Issue-Nummer `Nächster: /70-deploy`.

Archivierung allein hakt Deploy nicht mehr ab.

**CLI `plan`/`plan --watch`.** übergeben `deploy=deploy_mode()` (in `--watch` je Runde neu). `--watch` zeigt den archivierten Workflow wie bisher weiter an und liest dessen `deploy_status` je Runde neu, sodass ein `deploy-status done` ins Archiv sichtbar wird.

**`/70-deploy`.** Vor Step 3 `workflow.py deploy-status running <N>`; nach erfolgreichem Step 4 `deploy-status done <N>`; bricht Step 3 ab oder schlägt verify fehl: `deploy-status failed <N>`. Ohne Issue-Nummer/Workflow (Deploy ohne Workflow) wird der Aufruf übersprungen. Bei `DEPLOY_CONFIGURED=no` kein Marker.

`next_step`/`expected_footer_command`/`status_note` bleiben unverändert (footer_gate unberührt).

## Expected Behavior

- **Input:** `workflow.py plan [--watch]` für einen Workflow in Phase 8 oder im Archiv; `workflow.py deploy-status <wert> [<nr>]`
- **Output:** Deploy-Zeile nach tatsächlichem Zustand; „abgeschlossen“ nur mit `deploy_status=done` (oder ohne Deploy-Schritt)
- **Side effects:** `deploy-status` schreibt `deploy_status`/`deploy_at` in die Workflow- bzw. Archivdatei

## Known Limitations

- Ob deployt ist, weiß der Plan nur über den Marker; wer am `/70-deploy` vorbei deployt, muss `deploy-status done` selbst setzen.
- Bereits archivierte Workflows ohne Marker erscheinen nach dem Update als „Deploy offen“, bis der Pane wechselt oder `deploy-status done` gesetzt wird.
- Projekte ohne Deploy sehen „nicht eingerichtet“, bis sie `deploy.enabled: false` setzen.

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] Im Plan-Pane bleibt Deploy nach `finish` offen und springt erst nach `/70-deploy` mit erfolgreichem verify auf ✔ (manuelle Abnahme durch den PO)
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf grün)

## Acceptance Criteria

- **AC-1:** Given ein Workflow #510 in `phase8_complete`, `deploy="configured"`, ohne `deploy_status` / When `render_plan` läuft / Then steht `✔ 8 Code fertig`, danach `▶ Deploy  (offen)`, letzte Zeile `Nächster: /70-deploy #510`, kein `abgeschlossen` und kein `8 Fertig`
  - Test: tests/test_plan_deploy_status_510.py::test_phase8_deploy_open

- **AC-2:** Given derselbe Workflow mit `archived=True` ohne `deploy_status` / When `render_plan` läuft / Then bleibt `▶ Deploy  (offen)` mit `Nächster: /70-deploy #510`; mit `deploy_status="done"` steht `✔ Deploy` und letzte Zeile `abgeschlossen`
  - Test: tests/test_plan_deploy_status_510.py::test_archived_needs_done_marker

- **AC-3:** Given Phase 8 bzw. Archiv mit `deploy_status="running"` bzw. `"failed"` / When `render_plan` läuft / Then `▶ Deploy  (läuft)` bzw. `✘ Deploy  (fehlgeschlagen)`, jeweils mit `Nächster: /70-deploy #510`
  - Test: tests/test_plan_deploy_status_510.py::test_running_and_failed

- **AC-4:** Given `deploy="unconfigured"` und Phase 8 / When `render_plan` läuft / Then `▶ Deploy  (nicht eingerichtet)` und `Nächster: /70-deploy #510`; Given `deploy="off"` oder `False` / Then keine Deploy-Zeile, `✔ 8 Fertig`, letzte Zeile `abgeschlossen`
  - Test: tests/test_plan_deploy_status_510.py::test_unconfigured_and_off

- **AC-5:** Given ein archivierter Workflow mit `status="abandoned"` bzw. mit `no_build_reason` und `deploy="configured"` / When `render_plan` läuft / Then keine Deploy-Zeile und letzte Zeile `abgeschlossen`
  - Test: tests/test_plan_deploy_status_510.py::test_abandoned_has_no_deploy

- **AC-6:** Given ein Projekt mit archiviertem Workflow `feat-510-x` / When `workflow.py deploy-status done 510` läuft / Then Exit 0, Ausgabe enthält `DEPLOY_STATUS=done`, die Archivdatei enthält `deploy_status: "done"` und `deploy_at`; Given ein aktiver Workflow / When `deploy-status running` ohne Nummer / Then steht der Wert in dessen Datei; Given Wert `xyz` oder unbekannte Nummer / Then Exit 1
  - Test: tests/test_plan_deploy_status_510.py::test_cli_deploy_status

- **AC-7:** Given ein Projekt ohne `deploy:`-Config bzw. mit `deploy: {enabled: false}` und aktivem Workflow in Phase 8 / When `workflow.py plan` läuft / Then `▶ Deploy  (nicht eingerichtet)` bzw. keine Deploy-Zeile
  - Test: tests/test_plan_deploy_status_510.py::test_cli_plan_deploy_mode

- **AC-8:** Given ein Workflow in Phase 5 und `deploy="configured"` / When `render_plan` läuft / Then letzte Schrittzeile `○ Deploy`, „8 Code fertig“ als `○`, `Nächster:` wie bisher aus `expected_footer_command`
  - Test: tests/test_plan_deploy_status_510.py::test_early_phase

- **AC-9:** Given `core/commands/70-deploy.md` / When gelesen / Then enthält er `deploy-status running`, `deploy-status done` und `deploy-status failed`, und `done` steht nach dem verify-Schritt
  - Test: tests/test_plan_deploy_status_510.py::test_deploy_command_sets_markers

## Test Plan

- `pytest tests/test_plan_deploy_status_510.py tests/test_herdr_plan_deploy_sessionstart_478.py`
- Regressionslauf: `pytest tests/`
- `python3 -m py_compile core/hooks/workflow.py`
- `python3 scripts/sync_skills.py --check` (falls vorhanden)

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Anzeige-Erweiterung von #478 plus ein neues, rein informatives State-Feld ohne Gate-Wirkung. Reversibel per `deploy.enabled: false` bzw. Entfernen des Feldes.

## Changelog

- 2026-11-02: Initial spec created
