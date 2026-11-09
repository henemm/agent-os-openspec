# Context: fix-550-endzustand

## Request Summary
Jede Nachricht, die ein Arbeitspaket beendet, und die Plan-Ansicht/Seitenleiste zeigen genau einen
von drei festen Endzuständen (Erledigt / Läuft noch / Du bist dran), aus derselben Quelle. Die
erfundene „fachliche Abnahme“ entfällt; „Nächster: /70-deploy“ bei fehlendem/laufendem Deploy
(#547) verschwindet.

## Related Files
| File | Relevance |
|------|-----------|
| core/hooks/workflow.py:277 `next_step` | Pflicht-Schritt aus State; None ab Phase 8 |
| core/hooks/workflow.py:312 `expected_footer_command` | Hülle für footer_gate, render_plan, herdr |
| core/hooks/workflow.py:354-427 `render_plan` | Plan-Pane; Deploy-Zweig :396-414 setzt `deploy_pending` für alles ausser `done` → „Nächster: /70-deploy“ (Ursache #547) |
| core/hooks/workflow.py:429-476 `status_note` | Hook-Hinweis je Prompt; Regeltext „niemals ‚nichts zu tun‘“ :474-481; None ab Phase 8 |
| core/hooks/workflow.py:2998 `deploy_mode` | configured / unconfigured / off; ohne `deploy:`-Block → unconfigured |
| core/hooks/workflow.py:3039 `cmd_deploy_status`, :3015 `DEPLOY_STATUS_VALUES` | running/done/failed in `data["deploy_status"]` |
| core/hooks/workflow.py:3069 `cmd_deploy_config` | `autonomous: true/false` aus `deploy.autonomous` |
| core/hooks/workflow.py:2195-2220 Plan-Watch, :2254 CLI `plan` | Aufrufer von render_plan + deploy_mode (auch archivierte Workflows) |
| core/hooks/footer_gate.py | Stop-Hook; prüft nur Slash-Befehle der letzten ❗Du-Zeile gegen `expected_footer_command`; Freitext/None → fail-open |
| core/hooks/herdr_bridge.py:186 `build_report` | Seitenleisten-Tokens workflow/issue/phase/step/next; Phase 8 → None (Leiste wird geleert) |
| scripts/sync_skills.py:77 `marker_block` | EINZIGE Quelle des Fußzeilen-Regeltexts in skills/*/SKILL.md (+ .claude/commands Kopien) |
| core/commands/60-validate.md:397, :408 | Vorlage `**Offen beim PO:** [fachliche Abnahme][, Deploy]` |
| core/commands/70-deploy.md:48-88 | `DEPLOY_CONFIGURED=no` → Rückfragen; `deploy-status running/done/failed` |

## Existing Patterns
- Eine Quelle, viele Anzeiger: `expected_footer_command` als dünne Hülle (#234), damit Hook-Hinweis, Gate und Plan nie auseinanderlaufen.
- Regeltext der Fußzeile zentral in `sync_skills.marker_block`, Skills generiert; Drift-Test `tests/test_skills_sync.py`.
- Fail-open in allen Stop-/Anzeige-Hooks.
- Deploy-Zustand pro Workflow im State (`deploy_status`, #510), Modus aus Config (`deploy_mode`).

## Dependencies
- Upstream: `_deploy_block`, `_deploy_is_configured`, `workflow_issue_number`, `autonomy_mode`, `auto_ship_enabled`.
- Downstream: phase_listener (`status_note`), footer_gate, herdr_bridge (`build_report`, `maybe_auto_clear`), Plan-Pane, alle generierten Skills.

## Existing Specs
- docs/specs/feat-510-plan-deploy-status.md — AC-1..AC-4 legen heute genau das widersprüchliche Verhalten fest („Nächster: /70-deploy“ auch bei running/failed/unconfigured) → werden durch diese Spec abgelöst.
- docs/specs/feat-478-plan-deploy-sessionstart.md, feat-476-herdr-plan-pane.md, feat-466-herdr-sidebar.md, feat-467-herdr-auto-clear.md.
- Fußzeile: #234 (footer_gate), #325 (status_note), #470 (Auto-Freigabe).

## Tests (betroffen)
- tests/test_plan_deploy_status_510.py (9), test_herdr_plan_deploy_sessionstart_478.py (9), test_herdr_plan_pane_476.py (14), test_plan_issue_titel_490.py (6)
- tests/test_footer_gate_234.py (22), test_status_note_325.py, test_spec_ampel_470.py, test_skills_sync.py, test_herdr_sidebar_466.py

## Risks & Considerations
- footer_gate läuft bei jedem Turn-Ende in jedem Projekt: neue Erkennung muss fail-open bleiben.
- Herdr wertet eine ❗-Fußzeile als „blocked“ (#505) — die neue ⏳/✅-Form darf Auto-/clear nicht verschlechtern.
- `unconfigured` ist mehrdeutig (gar kein Deploy vs. nicht beschrieben). #550 (jüngere PO-Vorgabe) verlangt: Projekt ohne Deploy → Ende „Erledigt“, kein Deploy-Schritt. Wer Deploy braucht, beschreibt `deploy:`.
- Viele bestehende Tests prüfen alte Wortlaute („abgeschlossen“, „Nächster: /70-deploy“, „ℹ️ Nichts zu tun“) → bewusst anpassen, nicht löschen.
- Nebenbefund Kontext-Haushalt: In Cloud-Sitzungen liegt schon der Grundkontext direkt nach `/clear` bei ~100k (Schwelle 100k) → `CONTEXT_CUT=on` dauerhaft, `/clear` hilft nicht. Separat als Issue erfassen, nicht Teil von #550.

## Analysis

### Type (Bug)
Bug/Konsistenzfehler: Plan-Pane, Fußzeile und Abschlussnachricht leiten den Endzustand aus drei getrennten Texten ab und widersprechen sich (#547: „Nächster: /70-deploy“ obwohl Deploy läuft oder gar nicht eingerichtet; „fachliche Abnahme“ als erfundene PO-Aufgabe).

### Affected Files (with changes)
| File | Change Type | Description |
|------|-------------|-------------|
| core/hooks/workflow.py | edit | `end_state()` (pure), `cmd_endstate` + CLI-Eintrag, `render_plan`-Tail ersetzt, `_plan_deploy_mode` (unconfigured = aus), `status_note`-Regeltext |
| scripts/sync_skills.py | edit | `marker_block` (:77-101): drei Formen, „ℹ️ Nichts zu tun“ raus |
| core/commands/60-validate.md | edit | :397/:408 „Offen beim PO“-Vorlage weg; Ende: `endstate` aufrufen, FOOTER wörtlich |
| core/commands/70-deploy.md | edit | Ende ruft `endstate` auf; `deploy-status` bleibt |
| core/commands/30-write-spec.md | edit | :201 Verweis auf „ℹ️ Nichts-zu-tun“ anpassen |
| core/hooks/herdr_bridge.py | edit (minimal) | Token `state` für Phasen 1-7 (Phase 8 bleibt Clear) |
| skills/*/SKILL.md, .claude/commands/* | regeneriert | `python3 scripts/sync_skills.py` |
| core/hooks/footer_gate.py | KEINE Änderung | siehe Befund 1 |
| tests/test_endzustand_550.py | neu | Regression (s. u.) |
| tests/test_plan_deploy_status_510.py, test_herdr_plan_deploy_sessionstart_478.py, test_herdr_plan_pane_476.py, test_plan_issue_titel_490.py, test_status_note_325.py, test_herdr_sidebar_466.py, test_skills_sync.py | anpassen | alte Wortlaute / Token-Menge bewusst umstellen |
| CHANGELOG.md, docs/specs/feat-510-plan-deploy-status.md | edit | [Unreleased]; 510-AC als abgelöst vermerken |

### Scope Assessment
~12 Dateien, ca. +180/-90 LoC Code, +200 LoC Tests (ohne generierte Skills). Risiko mittel: Wortlaut-Pins in ~60 Tests, ein Kern-Hook (workflow.py) betroffen, aber alles Anzeige ohne Gate-Wirkung.

### Technical Approach
- **A behalten, Signatur ändern:** `end_state(data, archived=False, deploy="off", autonomous=False) -> dict(kind, line, cmd)`. Pure: Deploy-Modus und `autonomous` kommen als Parameter (Aufrufer lesen Config), nicht per `_deploy_block()` im Inneren (Archiv-Workflows, Tests). `deploy` wird über `_plan_deploy_mode` normalisiert; "unconfigured" ⇒ "off" (PO-Vorgabe #550; Folge: `/70-deploy` mit `DEPLOY_CONFIGURED=no` wird nur noch manuell erreicht, in 70-deploy.md und CHANGELOG nennen). Tabelle: aus/abandoned/no_build_reason → done; configured+nicht done: autonomous → waiting („Claude deployt“ bzw. bei failed „Claude kümmert sich“), sonst you `/70-deploy #N` (failed: Warum = „Deploy fehlgeschlagen, erneut starten“); running → waiting; done → done. Phasen < 8: `next_step` + Warum-Text aus neuer Tabelle `NEXT_WHY` (das `<warum>` fehlt heute komplett); Auto-Freigabe-Schritt → waiting.
- **B behalten:** `workflow.py endstate [#N|name]` mit `_deploy_status_target` (aktiv zuerst, dann Archiv); Ausgabe `ENDSTATE=`/`FOOTER=`; Config-Lesen (deploy_mode, autonomous) im CLI-Wrapper. Wichtig: Der Abschluss-Turn läuft NACH `complete` (Workflow archiviert), daher ist die Archiv-Suche tragend. Zusätzlich `batch`-fähig lassen.
- **C behalten:** render_plan-Tail = `end_state(...)["line"]`; Deploy-Zeile nur bei mode configured. Plan-Zeilen werden dadurch lang → Breitenkürzung (`width`) greift schon; Zeile besser auf zwei Zeilen (Emoji+Art / Rest) umbrechen, nicht hart kürzen.
- **D behalten:** marker_block + status_note einheitlich auf drei Formen; „ℹ️ Nichts zu tun“ ersatzlos auf „⏳ Läuft noch“. Bei Phase 8: `status_note` bleibt None (Archiv), Regel steht im Skill-Text: „Ende = `endstate`-FOOTER wörtlich“.
- **E fallen lassen** (Begründung Befund 1). Stattdessen Absicherung per Test, dass 60-validate.md/70-deploy.md den `endstate`-Aufruf enthalten und keine eigene ❗-Vorlage für das Ende.
- **F minimal:** nur Token `state` (erledigt/läuft/du) für Phasen 1-7, abgeleitet aus `end_state`; Phase 8 bleibt `clear()` (Workflow ist archiviert, nichts zu melden; Plan-Pane zeigt Archiv-Endzustand). Kein Eingriff in `maybe_auto_clear` (löst nur bei Slash-Befehl-Fußzeile aus; ⏳/✅-Zeilen enthalten keinen → kein Auto-/clear, und das ist am Ende korrekt, weil `/99-reset`/Abschluss manuell bleibt).
- **Tests (neu):** (1) kein „fachliche Abnahme“ in core/commands/*.md, skills/*/SKILL.md; (2) `render_plan` für off/open/running/done/failed × autonomous ⇒ Tail ist genau eine der drei Formen (Regex `^(✅ Erledigt|⏳ Läuft noch|❗ Du):`); (3) Chat-Zustand (`cmd_endstate`-Ausgabe) == Plan-Zustand; (4) kein „Nächster: /70-deploy“ bei running/off/unconfigured.

### Befunde gegen den Plan
1. **E ist toter Code:** `cmd_complete` (workflow.py:2800-2829) archiviert, löscht die Workflow-Datei und setzt `_persist_env(None)`. footer_gate löst den Namen über `resolve_active_workflow()` → danach `source=="none"` bzw. keine Datei → `_expected_command` liefert (None, None), `main()` beendet fail-open (footer_gate.py:259-261). Ein „aktiver Workflow in phase8_complete“ existiert praktisch nie; auch `_expected_command` verlangt Slash-Befehl (:171). E wäre nur mit neuer Archiv-Suche ohne Namen möglich — fragil, widerspricht fail-open. Verwerfen.
2. **Phase-8-Verzweigung in A greift nur für archivierte/Plan-Fälle:** `status_note` liefert ab phase8 None (:445-446), `next_step` None. Die Quelle für den Abschluss-Turn ist also zwingend das CLI `endstate` auf dem Archiv (B), nicht der Hook-Hinweis.
3. **`unconfigured` ⇒ off verändert #478/#510:** Heute zeigt der Plan bei fehlendem `deploy:` bewusst „nicht eingerichtet“ (workflow.py:410-411, AC aus feat-510). Das ist gewollt abgelöst; aber `deploy_mode()` (:2998) und `render_plan` müssen konsistent bleiben, sonst zeigt `plan` etwas anderes als `endstate` — beide über dieselbe `_plan_deploy_mode`-Normalisierung führen. `deploy.enabled: false` ("off") bleibt unverändert.
4. **`<warum>` fehlt in der Datenbasis:** `NEXT_STEP`/`next_step` liefern nur den Befehl. Ohne Warum-Tabelle ist die Form 3 nicht erfüllbar; Gate-Prüfung bleibt nur auf den Befehl (footer_gate.py:132-153), Freitext nach „—“ unkritisch.
5. **herdr:** Test `test_herdr_sidebar_466.py:35,165,236,514` pinnt genau fünf Tokens; Token `state` erfordert bewusstes Update, `clear()` räumt über `TOKEN_NAMES` (herdr_bridge.py:231,249) automatisch mit. #505 (❗ ⇒ „blocked“) wird nicht verschlechtert, da ⏳/✅ kein ❗ tragen — gewünschte Wirkung: Sidebar zeigt „fertig/läuft“ statt blocked.
6. **Autonomous-Fall failed:** `autonomous: true` heißt „/60-validate darf /70-deploy ohne Halt anstoßen“ (config.yaml:206), nicht „Claude repariert Fehler“. Zustand 2 bei failed ist nur ehrlich, wenn 70-deploy.md dann tatsächlich selbst weiterarbeitet; sonst Lüge („Du musst nichts tun“). 70-deploy.md muss bei autonomous+failed einen Retry/Diagnose-Schritt vorschreiben (Entscheidung: ja, einmaliger Retry, danach `deploy-status failed` + Zustand 3 mit Grund — Zustand 2 gilt nur für den ersten Fehlschlag; `end_state` kennt dafür kein Zählerfeld, daher: autonomous+failed ⇒ **Zustand 3** „Du: /70-deploy #N — Deploy fehlgeschlagen, <Grund aus deploy_note>“). Das weicht vom Issue-Text ab (dort State 2); Begründung: ein autonomer Agent, der schon gescheitert ist, hat keinen weiteren zugesicherten Schritt.
7. **Kontext-Nebenbefund (Zeile 50)** bleibt außerhalb.

### Dependencies / Reihenfolge
1. `end_state` + `_plan_deploy_mode` + `NEXT_WHY` + Unit-Tests (RED zuerst) → 2. `render_plan`/`cmd_endstate`/CLI → 3. `marker_block`/`status_note` + 60-validate/70-deploy/30-write-spec, dann `sync_skills.py` → 4. herdr-Token → 5. Altest-Tests umstellen, CHANGELOG, 510-Spec-Hinweis. Kein Release-Bump.

### Open Questions
Keine Produktfragen. Technische Entscheidungen oben getroffen: E verworfen, F minimal, autonomous+failed ⇒ Zustand 3 (Abweichung von der Issue-Skizze; bei PO-Widerspruch trivial umstellbar).

### Entscheidungen Tech Lead (nach Bewertung)
- A–D übernommen wie in „Technical Approach“; E (footer_gate-Prüfung in Phase 8) verworfen, weil `cmd_complete` den Workflow archiviert und das Gate dann fail-open aussteigt — Ersatz: Tests, dass 60-validate.md/70-deploy.md mit `workflow.py endstate` enden.
- F minimal: Token `state` für Phasen 1–7, Phase 8 leert die Leiste weiter (Plan-Pane zeigt den Endzustand).
- Deploy fehlgeschlagen → immer Zustand 3 mit klarem Schritt (`❗ Du: /70-deploy #N — Deploy fehlgeschlagen …`), auch bei `autonomous: true`: „Claude kümmert sich“ ohne zugesicherten Folgeschritt wäre unehrlich. Deckt die Issue-Formulierung „bzw. klarer Schritt“ ab.
- `unconfigured` = kein Deploy (wie `off`); löst #510 AC-1..AC-4/AC-7 und #478-Vorgaben ab, Tests werden umgestellt.
- Keine Produktfrage an den PO offen.
