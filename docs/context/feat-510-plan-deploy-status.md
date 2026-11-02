# Kontext: feat-510-plan-deploy-status (Issue #510)

## Anfrage (PO, 2026-11-02)

„Eine Erweiterung am Workflow Sidepane: Aktuell ist der Schritt des Deploys nicht richtig abgedeckt. Es sieht immer schon fertig aus, bevor die Software wirklich deployt ist.“

Rückfrage beantwortet: alle drei Symptome treten auf (✔ Deploy nach Archiv, kein Deploy-Schritt ohne Config, „✔ 8 Fertig“ zu früh). Deploy gilt als erledigt nach erfolgreichem verify in `/70-deploy`.

## Befund

- `core/hooks/workflow.py::render_plan` (#478): `archived=True` → `✔ Deploy` + `abgeschlossen`, unabhängig davon, ob deployt wurde. `cmd_complete` (`finish`) archiviert ohne Deploy-Bezug.
- `deploy_configured()` falsch → kein Deploy-Schritt, Phase 8 = `abgeschlossen`.
- `done_all` in Phase 8 setzt alle Schritte inkl. „8 Fertig“ auf ✔.
- `/70-deploy` schreibt keinerlei State; der Plan kann den Deploy-Erfolg nicht kennen.
- `_plan_watch` rendert nach Archivierung die Archivdatei weiter (`archived=True`) und liest sie je Runde neu.
