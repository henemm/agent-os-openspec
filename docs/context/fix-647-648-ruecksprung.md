# Context: fix-647-648-ruecksprung

## Request Summary
Nach einem Rücksprung auf Analyse oder Spec (#647: phase4_approved → phase3_spec, #648: phase6_implement → phase2_analyse) bleiben altes PO-Briefing und `spec_file` stehen. `next_step()` meldet dann die (Auto-)Freigabe statt `/30-write-spec`. Herdr bleibt stehen, und `auto-approve` könnte eine widerlegte Spec erneut freigeben. Dazu kommt ein Nebenbefund: `endstate <N>` löst auf einen abgeschlossenen Vorgänger derselben Nummer auf statt auf den aktiven Workflow. Teil von Epic #649 (Schnitt 2).

## Related Files
| File | Relevance |
|------|-----------|
| core/hooks/workflow.py `_reset_approvals_on_backstep` (~3621) | Setzt bei Rücksprung `spec_approved`/`green_approved`/Deploy-Felder zurück, aber **nicht** `po_briefing` → Kern des Fehlers |
| core/hooks/workflow.py `cmd_phase` (~3645) | Ruft den Reset vor `record_transition` auf; einziger Weg für Phasenwechsel per CLI |
| core/hooks/workflow.py `next_step` (~285) | phase3_spec + `spec_file` → immer Freigabe-Schritt (`AUTO_APPROVAL_STEP` bzw. `APPROVAL_STEP`), nie `/30-write-spec` |
| core/hooks/workflow.py `_auto_approval_pending` (~187) | Grün + Auto-Modus + Briefing-Datei mit passendem Hash → Auto-Freigabe |
| core/hooks/workflow.py `_check_po_briefing` (~2744) | Bestimmt, ob ein Briefing Pflicht ist (Kill-Switch, Fast Track/`skip_fast_track`, Auto-Modus) — wiederverwendbar für „Briefing fehlt → Spec-Schritt“ |
| core/hooks/workflow.py `cmd_auto_approve` (~5100) | Gibt frei, wenn Briefing grün und aktuell. Nach Rücksprung prüft es nur Hashes → würde alte Spec freigeben |
| core/hooks/workflow.py `_deploy_status_target` (~4385) / `_status_target` / `cmd_endstate` | Auflösung `endstate <N>`: laufende Treffer alphabetisch sortiert, aktiver Workflow nicht bevorzugt |
| core/hooks/herdr_bridge.py `maybe_auto_clear` | Konsument von `expected_footer_command` (skip bei Freitext-Schritt) |
| core/hooks/footer_gate.py | Prüft ❗Du-Zeile gegen `next_step()` |
| tests/test_rueckspruung_405.py | Bestehende Tests zum Rücksprung-Reset (#405) — Erweiterungsort |
| tests/test_spec_ampel_470.py | Auto-Freigabe/Ampel-Tests |
| tests/test_endzustand_550.py | endstate-Tests |

## Existing Patterns
- Rücksprung-Reset zentral in `_reset_approvals_on_backstep` (#405, #561): Freigaben, die das Ziel noch nicht hat, werden entwertet; Belege (`phase_transitions`, `phase_log`, `approvals`) bleiben.
- Briefing-Bindung per `spec_sha256`/`briefing_sha256` (`set-briefing`, #470 F005).
- `next_step()` ist die eine Quelle für Fußzeile, Plan, Herdr-Report und footer_gate (#234, #550).

## Dependencies
- Upstream: `PHASES`, `autonomy_mode()`, `load_config`, Briefing-Leser.
- Downstream: footer_gate, herdr_bridge (`next=`), `end_state`/`endstate`, `status_note`, phase_listener (Freigabe-Phrase), `auto-approve`, ci_spec_gate (liest nur committete Briefings, nicht betroffen).

## Existing Specs
- `docs/specs/feat-470-spec-ampel.md` (Auto-Freigabe)
- `docs/specs/fix-550-endzustand.md` (endstate)
- Spec zu #405 (Rücksprung-Reset), sofern vorhanden

## Risks & Considerations
- **Freigabe-Gate ist kritischer Pfad:** Ein Fehler hier gibt entweder eine überholte Spec frei oder blockiert jede Freigabe.
- Das Briefing nur zu verwerfen reicht nicht (#647 Punkt 4): Ohne Briefing meldet `next_step` dann `approved` statt `/30-write-spec`. In phase3_spec mit Spec, aber ohne gültiges Pflicht-Briefing, ist der offene Schritt das Fertigstellen der Spec (`/30-write-spec`).
- Ausnahmen, in denen kein Briefing Pflicht ist (Kill-Switch, Fast Track manuell): Dort muss `approved` bleiben.
- Belege nicht löschen: Das alte Briefing kommt als überholt in eine Historie, statt zu verschwinden (Prinzip „nichts still löschen“).
- Normaler Ablauf in `/30-write-spec`: `spec_file` wird vor `set-briefing` gesetzt. In dieser Lücke ist `/30-write-spec` als nächster Schritt korrekt, weil die Phase dann noch nicht fertig ist.
- `endstate <N>`: Vorgänger in phase8_complete, aber noch nicht archiviert, liegt neben dem aktiven Workflow. Aktiven bevorzugen, dann nicht abgeschlossene, dann den jüngsten.
- Herdr-Auto-/clear wird mit Epic #649 zurückgebaut. Der Fix muss trotzdem für `next_step` allgemein stimmen (Cloud, Footer, Plan).
