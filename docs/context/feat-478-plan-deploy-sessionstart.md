# Context: feat-478-plan-deploy-sessionstart

## Request Summary
Folge zu #476 nach PO-Abnahme in echtem Herdr: (1) Nach `phase8_complete` zeigt der Plan alles ✔ und „abgeschlossen“, die Sitzung verlangt aber noch `/70-deploy #N`. (2) Der Plan-Bereich soll auch beim Start von Claude Code aufgehen, wenn ein Workflow läuft.

## PO-Entscheidungen
- Eigener Schritt **Deploy** unter „8 Fertig“: `▶ Deploy  (offen)` + `Nächster: /70-deploy #N`, solange Phase 8 und nicht archiviert
- Deploy-Signal: nur `deploy:`-Config mit `command` + `verify` (= `workflow.py deploy-config` → `DEPLOY_CONFIGURED=yes`); die Datei `70-deploy.md` liegt in jedem Projekt als Vorlage und zählt nicht
- Auto-Öffnen beim SessionStart: ja

## Related Files
| File | Relevance |
|------|-----------|
| `core/hooks/workflow.py` | `render_plan` (#476), `_plan_active`/`_plan_watch`/`cmd_plan`, `_deploy_steps` + `cmd_deploy_config` (#81), `next_step`/`NEXT_STEP` (Phase 8 → None, bleibt so: footer_gate/status_note unberührt) |
| `core/hooks/session_banner.py` | SessionStart-Hook; `main()` ruft schon `herdr_bridge.report_active()` fail-open |
| `core/hooks/herdr_bridge.py` | `open_plan_pane(force)` spawnt detacht; Runner prüft per `pane get`, ob der Pane schon offen ist → kein Duplikat |
| `tests/test_herdr_plan_pane_476.py` | Stub-Binary-Muster, Projekt-Setup |

## Analysis
### Affected Files
| File | Change Type | Description |
|------|-------------|-------------|
| core/hooks/workflow.py | MODIFY | `deploy_configured()`, `render_plan(..., deploy=False)`, `plan`/`--watch` reichen das Signal durch |
| core/hooks/herdr_bridge.py | MODIFY | `open_plan_pane_for_active()`: nur bei aktivem Workflow |
| core/hooks/session_banner.py | MODIFY | Aufruf nach `report_active()`, fail-open |
| tests/test_herdr_plan_deploy_sessionstart_478.py | CREATE | Renderer, CLI mit Deploy-Config, SessionStart mit Stub |
| CHANGELOG.md | MODIFY | [Unreleased] |

### Scope / Risiko
- ~+50 LoC Prod, ~+200 Test; Risk MEDIUM (SessionStart läuft in jedem Projekt; fail-open, nur Spawn)
- `next_step` bleibt unverändert, damit footer_gate in Phase 8 nichts Neues verlangt
