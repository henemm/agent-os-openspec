# Kontext + Analyse: fix-497-autoclear-grenze-beim-phasenwechsel (Issue #497)

## Request Summary
PO (nach 5 Fehlversuchen bei Auto-/clear): verbleibendes Risiko von #495 beseitigen und echt testen.
1. Grenz-Vermerk darf nicht mehr davon abhaengen, dass Claude zusaetzlich `workflow.py autoclear` aufruft → beim erzwungenen Phasenwechsel automatisch schreiben.
2. Echter E2E mit echter Phase (echter Befehl aus diesem Plugin) und grossem Modell.
3. Restfaelle aus #497: (a) zweimal falsche Fusszeile → Vermerk bleibt stehen (footer_gate.py ~Z. 227 endet vor maybe_auto_clear); (b) `at` ohne Zeitzone (workflow.py `_record_auto_clear_boundary`).

## Grenzen (Ende eines Phasenbefehls, Folgebefehl kommt im neuen Kontext)
| Uebergang | Gesetzt in | Folgebefehl |
|---|---|---|
| phase1_context → phase2_analyse | 10-context Ende | /20-analyse #N |
| phase2_analyse → phase3_spec | 20-analyse Ende | /30-write-spec #N |
| phase3_spec → phase4_approved | Freigabe (phase_listener "approved" bzw. `auto-approve` → `_apply_spec_approval`) | /40-tdd-red #N |
| phase5_tdd_red → phase6_implement | 40-tdd-red Ende | /50-implement #N |
| phase6b_adversary → phase7_validate | 50-implement nach VERIFIED | /60-validate #N |

KEINE Grenzen: phase4→phase5 (Anfang 40), phase6→phase6b (mitten in 50), phase6b→phase6 (BROKEN-Fix-Schleife), Ruecksprünge, phase7→phase8.

## Related Files
- core/hooks/workflow.py — `record_transition` (~Z. 996, gemeinsamer Pfad aller Phasenwechsel inkl. `cmd_phase` ~Z. 2005 und `_apply_spec_approval` ~Z. 3081), `_record_auto_clear_boundary` (~Z. 3054), `expected_footer_command`, `next_step`, `NEXT_STEP`
- core/hooks/phase_listener.py — Freigabe-Pfad "approved"
- core/hooks/herdr_bridge.py — `maybe_auto_clear`, `_consume_boundary`, `auto_clear_enabled`, `_pane`
- core/hooks/footer_gate.py — `main` (stop_hook_active-Ausgang ~Z. 227)
- scripts/e2e_auto_clear.sh — echter E2E (Herdr 0.9.5 headless + Claude TUI + Plugin), Szenarien A–D
- tests/test_autoclear_boundary_495.py, tests/test_herdr_auto_clear_467.py

## Loesungsrichtung
- In `record_transition` (oder direkt danach an allen Aufrufstellen): ist (alt, neu) eine Grenze laut Tabelle und Auto-/clear aktiv (`herdr_bridge._pane()` + `auto_clear_enabled()`), dann `auto_clear_boundary = {phase: neu, command: Folgebefehl #N, at: tz-aware ISO}` in `data` setzen (wird mit dem State gespeichert). Fail-open.
- `workflow.py autoclear` bleibt (zweite, gleichwertige Quelle).
- footer_gate: auf dem `stop_hook_active`-Ausgang einen vorhandenen Vermerk verwerfen (#497a).
- `at` mit Zeitzone schreiben (#497b); Leser akzeptiert beides.
- E2E: Szenario E — echter Befehl `/agent-os-openspec:10-context` (bzw. Alias) in einem kleinen Wegwerf-Projekt mit Issue-Nummer, grosses Modell (`E2E_MODEL`, z. B. opus), Rechte fuer das Wegwerf-Projekt per `--dangerously-skip-permissions` (isolierter Container, Wegwerf-Ordner). Erwartung: Phase wechselt auf phase2_analyse, Herdr tippt `/clear` und `/20-analyse #N`, der echte Folgebefehl startet. Szenario A ohne `autoclear`-Aufruf: nur `workflow.py phase` → Vermerk entsteht trotzdem.

## Risks
- Fehl-Ausloesung, wenn ein Grenz-Phasenwechsel ausserhalb des Befehlsendes passiert (z. B. manuell) → Einmal-Signal + 15-min-Fenster + Fusszeile muessen passen.
- Kosten/Dauer des echten E2E mit grossem Modell (einige Minuten, einstellige Euro-Cent bis wenige Dollar) → als optionales Szenario per `ONLY=E`.
