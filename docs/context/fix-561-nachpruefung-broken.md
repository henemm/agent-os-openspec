# Context: fix-561-nachpruefung-broken

## Request Summary
Ein fachlicher Befund bei der Nachprüfung nach Phase 8 (Staging/verify: eine AC ist nicht erfüllt) soll den BROKEN-Pfad nehmen (Rücksprung nach `phase6_implement`, Fix, Adversary, Validierung, erneut ausliefern) statt eines Korrektur-PRs am Workflow vorbei. Ein Rücksprung vor Phase 8 muss den alten Deploy-Zustand verwerfen, damit Plan, Seitenleiste und Endzustand-Zeile nach dem erneuten Durchlauf den neuen Deploy zeigen.

## Related Files
| File | Relevance |
|------|-----------|
| core/hooks/workflow.py | `_reset_approvals_on_backstep` (~2547) setzt bei Rücksprung nur Freigaben zurück; `cmd_phase` ruft sie; `cmd_deploy_status` (~3241) schreibt `deploy_status`/`deploy_at`, kein `deploy_note`; `_end_state_final` (~409) liest `deploy_note` (wird nirgends geschrieben); `_plan_deploy_line` (~601) |
| core/commands/70-deploy.md | Step 3/4: nur technischer Fehlschlag (`deploy-status failed` → Rollback vorschlagen), kein fachlicher Befund |
| core/commands/60-validate.md | Step 2b + Punkt 5: BROKEN-Pfad bei Code-Fix (#259) und roter CI; nichts zur Nachprüfung nach Phase 8 |
| skills/60-validate/SKILL.md, skills/70-deploy/SKILL.md | generiert per `scripts/sync_skills.py` |
| tests/test_rueckspruung_405.py | bestehende Tests zum Rücksprung (Freigaben) |
| tests/test_plan_deploy_status_510.py, tests/test_endzustand_550.py, tests/test_nacharbeit_555.py | Plan-/Endzustand-Tests zu `deploy_status`/`deploy_note` |

## Existing Patterns
- Rücksprung-Nebenwirkungen zentral in `_reset_approvals_on_backstep(data, current, target)` (#405), aufgerufen nur aus `cmd_phase`.
- `waiting_on` wird bei jedem Phasenwechsel geleert (#550) — gleiches Muster „Phasenwechsel verwirft Anzeige-Zustand“.
- BROKEN-Pfad-Formulierung aus `/60-validate` (#259): zurück zu `phase6_implement`, `/50-implement`, eine Adversary-Runde aus demselben Kontingent.

## Dependencies
- Upstream: `PHASES`, `_validate_transition` (erlaubt Rückwärtswechsel aus `phase8_complete`, solange nicht archiviert).
- Downstream: `render_plan`/`_plan_lines`, `end_state`, `herdr_bridge` (Seitenleiste), `/70-deploy`, `/60-validate`.

## Existing Specs
- `docs/specs/feat-510-plan-deploy-status.md` — `deploy_status`-Feld und Plan-Zeile
- `docs/specs/fix-550-endzustand.md` — Endzustand bei `failed` (Grund aus `deploy_note`)
- `docs/specs/fix-555-nacharbeit-endzustand.md` — `deploy_note` nur als String

## Risks & Considerations
- Archivierung passiert erst über `complete`/`finish`/`/99-reset`; nach `phase phase8_complete` liegt der Workflow noch unter `.claude/workflows/` → Rücksprung ist der Normalfall. Archiviert: neuer Workflow mit derselben Issue-Nummer.
- `deploy_note` wird von keinem Befehl geschrieben — „`deploy-status failed` mit Grund“ (Issue-Soll 1) braucht ein optionales `--note`.
- Nach gemergtem Erst-PR: `base_commit` liegt vor dem Merge, die Abdeckungsprüfung verlangt daher alle Dateien seit Basis — strenger, nicht schwächer; kein Handlungsbedarf.
- `workflow.py` ist Kern-Infrastruktur → hohes Adversary-Risiko (2 Runden).

## Analysis

### Type
Bug (fehlende Anweisung + Altzustand beim Rücksprung)

### Reproduktion
`_reset_approvals_on_backstep(d, "phase8_complete", "phase6_implement")` mit `deploy_status=failed`, danach wieder `phase8_complete`: Plan zeigt `✘ Deploy  (fehlgeschlagen)` und Endzeile `❗ Du: /70-deploy #561 — Deploy fehlgeschlagen (…)` statt `▶ Deploy  (offen)`. Ursache: `core/hooks/workflow.py:2547` setzt nur `spec_approved`/`green_approved` zurück.

### Affected Files (with changes)
| File | Change Type | Description |
|------|-------------|-------------|
| core/hooks/workflow.py | MODIFY | Rücksprung vor `phase8_complete` entfernt `deploy_status`, `deploy_at`, `deploy_note`; `deploy-status … --note <Grund>` schreibt `deploy_note` (bei running/done wird es entfernt) |
| core/commands/70-deploy.md | MODIFY | Step 4: technischer vs. fachlicher Befund; fachlich = BROKEN-Pfad; archivierter Workflow → neuer Workflow mit derselben Issue-Nummer |
| core/commands/60-validate.md | MODIFY | Nachprüfung nach Phase 8 (Staging/live) als BROKEN-Pfad, Verweis auf `/70-deploy` |
| skills/60-validate/SKILL.md, skills/70-deploy/SKILL.md | MODIFY | per `scripts/sync_skills.py` |
| tests/test_nachpruefung_broken_561.py | CREATE | Plan/Endzustand nach Rücksprung, `--note`, Anweisungstexte |
| CHANGELOG.md | MODIFY | `[Unreleased]` |

### Scope Assessment
- Files: 6 (davon 2 generiert)
- Estimated LoC: +~140/-~5 (Code ~25)
- Risk Level: MEDIUM (Kern-State-CLI, aber nur Anzeige-Felder ohne Gate-Wirkung)

### Technical Approach
Rücksprung-Nebenwirkung in `_reset_approvals_on_backstep` ergänzen (gleiche Stelle wie #405): Ziel vor `phase8_complete` → `deploy_status`, `deploy_at`, `deploy_note` per `pop` entfernen. `cmd_deploy_status` um optionales `--note <text>` erweitern (Reihenfolge der übrigen Argumente unverändert); `running`/`done` entfernen eine alte Notiz. Anweisungstexte: fachlicher Befund = BROKEN-Pfad mit fester Schrittfolge, kein Korrektur-PR am Workflow vorbei.

### Dependencies
Plan (`render_plan`), `end_state`, `herdr_bridge` lesen die Felder nur; keine Gate-Wirkung.

### Open Questions
- keine (technische Entscheidungen liegen beim Tech Lead)
