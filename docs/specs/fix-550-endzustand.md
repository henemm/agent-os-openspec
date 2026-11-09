---
entity_id: fix-550-endzustand
type: module
created: 2026-11-09
updated: 2026-11-09
status: draft
version: "1.0"
workflow: fix-550-endzustand
tags: [workflow, footer, plan, herdr, deploy]
---

# Genau drei eindeutige Endzustände (Issue #550, umfasst #547)

## Approval

- [ ] Approved

## Purpose

Jede Meldung, die ein Arbeitspaket beendet, sowie die Plan-Ansicht und die Seitenleiste zeigen heute den Abschluss aus drei getrennten Texten und widersprechen sich (#547: „Nächster: /70-deploy" obwohl Deploy läuft oder gar nicht eingerichtet ist; „fachliche Abnahme" als erfundene PO-Aufgabe). Künftig entscheidet eine einzige reine Funktion `end_state()`, und alle Anzeiger (Chat-Fußzeile, Plan, Seitenleiste) zeigen genau eine von drei festen Formen.

## Source

- **File:** `core/hooks/workflow.py`, `scripts/sync_skills.py`, `core/hooks/herdr_bridge.py`, `core/commands/60-validate.md`, `core/commands/70-deploy.md`, `core/commands/30-write-spec.md`
- **Identifier:** neu `end_state`, `_plan_deploy_mode`, `NEXT_WHY`, `cmd_endstate`; geändert `render_plan` (~354-427), `status_note` (~429-481), `marker_block` (~77), `build_report` (~186)

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `workflow.next_step` (~277), `expected_footer_command` (~312) | function | liefert den Pflicht-Befehl für Phasen vor 8; bleibt unverändert |
| `workflow.deploy_mode` (~2998), `DEPLOY_STATUS_VALUES`, `cmd_deploy_status` (~3039) | function | Deploy-Modus aus der Config bzw. Marker `deploy_status` im State |
| `workflow._deploy_status_target` (~3018) | function | Suche aktiv, dann Archiv (Muster für `endstate`) |
| `workflow.cmd_deploy_config` (~3069), `deploy.autonomous` | function/config | Quelle für `autonomous` |
| `workflow.cmd_complete` (~2800) | function | archiviert den Workflow; der Abschluss-Turn läuft danach |
| `core/hooks/footer_gate.py` | hook | bleibt unverändert (siehe Known Limitations) |
| `docs/specs/feat-510-plan-deploy-status.md` | spec | wird in Teilen abgelöst (siehe Scope) |
| `tests/test_plan_deploy_status_510.py`, `test_herdr_plan_deploy_sessionstart_478.py`, `test_herdr_plan_pane_476.py`, `test_plan_issue_titel_490.py`, `test_status_note_325.py`, `test_herdr_sidebar_466.py`, `test_skills_sync.py`, `test_footer_gate_234.py` | tests | Wortlaut-Pins werden bewusst umgestellt, nicht gelöscht |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| core/hooks/workflow.py | MODIFY | `end_state()`, `_plan_deploy_mode`, `NEXT_WHY`, `cmd_endstate` + CLI-Eintrag `endstate`, `cmd_waiting` + CLI-Eintrag `waiting` (State-Feld `waiting_on`), Phasenwechsel leert `waiting_on`, `render_plan`-Schluss, `status_note`-Regeltext |
| scripts/sync_skills.py | MODIFY | `marker_block`: drei Formen, „ℹ️ Nichts zu tun" entfällt |
| core/commands/60-validate.md | MODIFY | Vorlage „Offen beim PO: [fachliche Abnahme][, Deploy]" (~397, ~408) entfernen; Abschluss ruft `workflow.py endstate` auf |
| core/commands/70-deploy.md | MODIFY | endet mit `workflow.py endstate`; Hinweis, dass `DEPLOY_CONFIGURED=no` nur noch manuell erreicht wird |
| core/commands/30-write-spec.md | MODIFY | Verweis auf „ℹ️ Nichts-zu-tun" (~201) anpassen |
| core/hooks/herdr_bridge.py | MODIFY | `build_report`: neues Token `state` (erledigt/läuft/du) für Phasen 1-7 |
| skills/*/SKILL.md, .claude/commands/* | REGENERATE | `python3 scripts/sync_skills.py` |
| tests/test_endzustand_550.py | CREATE | Regressionstests zu allen AC |
| tests/test_plan_deploy_status_510.py, test_herdr_plan_deploy_sessionstart_478.py, test_herdr_plan_pane_476.py, test_plan_issue_titel_490.py, test_status_note_325.py, test_herdr_sidebar_466.py, test_skills_sync.py, ggf. test_footer_gate_234.py | MODIFY | alte Wortlaute („abgeschlossen", „Nächster: /70-deploy", „ℹ️ Nichts zu tun", Token-Menge) umstellen |
| CHANGELOG.md | MODIFY | Eintrag unter [Unreleased], kein Versions-Bump |
| docs/specs/feat-510-plan-deploy-status.md | MODIFY | nur ein Hinweis auf Ablösung (Frontmatter-/Änderungsprotokoll-Zeile) |

**Ablösung von #510:** Diese Spec löst AC-1, AC-2, AC-3, AC-4 und AC-7 aus `feat-510-plan-deploy-status.md` ab (dort war „Nächster: /70-deploy" auch bei `running`, `failed`, `unconfigured` festgelegt, und „nicht eingerichtet" wurde angezeigt). AC-5, AC-6, AC-8 (frühe Phasen: Deploy-Zeile `○`) und AC-9 gelten weiter. Ebenso abgelöst: die „nicht eingerichtet"-Vorgaben aus #478.

Nicht Teil: `footer_gate.py`, `maybe_auto_clear`, das Kontext-Haushalt-Thema (`CONTEXT_CUT` dauerhaft `on` in Cloud-Sitzungen, eigenes Issue).

### Estimated Changes

- Files: 1 neu (+ regenerierte Skills), ca. 12 geändert
- LoC: ca. +180/-90 Produktion, +200 Test
- Risk Level: MEDIUM (Kern-Hook `workflow.py` betroffen, viele Wortlaut-Pins in Tests; aber reine Anzeige ohne Gate-Wirkung)

## Implementation Details

**Drei Endzustände, fester Wortlaut.** Kein vierter Zustand. „ℹ️ Nichts zu tun" entfällt ersatzlos (wird zu ⏳); die Vorgabe „fachliche Abnahme" entfällt ersatzlos.

```
✅ Erledigt: <was>. Du kannst /clear ausführen und das nächste Issue starten.
⏳ Läuft noch: <worauf gewartet wird>. Du musst nichts tun, ich melde mich.
❗ Du: <konkreter Schritt> — <warum>
```

**`end_state(data, archived=False, deploy="off", autonomous=False) -> dict`.** Reine Funktion (kein Config-Zugriff, kein I/O). Rückgabe `{"kind": "done"|"waiting"|"you", "line": <ganze Zeile>, "cmd": <Slash-Befehl oder None>}`. Deploy-Modus und `autonomous` liefern die Aufrufer aus der Config.

**`_plan_deploy_mode(deploy)`.** Normalisiert `True`/`"configured"` → `"configured"`, alles andere inkl. `False`, `"off"` und `"unconfigured"` → `"off"`. Damit gilt ein Projekt ohne `deploy:`-Block als „ohne Deploy" (PO-Vorgabe #550). Wer Deploy braucht, beschreibt `deploy:` (`command` und `verify`). `deploy_mode()` selbst und `deploy.enabled: false` bleiben unverändert; `render_plan` und `endstate` gehen beide über `_plan_deploy_mode`, damit Plan und Chat nie auseinanderlaufen.

**Tabelle Phase 8 bzw. archiviert** (`deploy_status` aus `data`):

| Modus / Lage | Ergebnis |
|---|---|
| off, unconfigured, `status == "abandoned"` oder `no_build_reason` gesetzt | done |
| configured, `deploy_status` leer, autonomous | waiting („Claude deployt") |
| configured, `deploy_status` leer, nicht autonomous | you, `/70-deploy #N` |
| configured, `running` | waiting („Deploy läuft") |
| configured, `done` | done |
| configured, `failed` (auch bei autonomous) | you, `/70-deploy #N — Deploy fehlgeschlagen …` (Grund aus `deploy_note`, falls vorhanden) |

Begründung `failed` immer ❗: „Claude kümmert sich" ohne zugesicherten Folgeschritt wäre unehrlich (autonomous erlaubt nur das Anstoßen von `/70-deploy` ohne Halt, keine Fehlerbehebung). Ohne Issue-Nummer lautet der Befehl `/70-deploy`.

**Phasen < 8.** `next_step(data)` liefert den Befehl; der Warum-Text kommt aus der neuen Tabelle `NEXT_WHY` (ein Satz je Phase bzw. je Befehl, z. B. Freigabe-Wort „approved" → „die Spec wartet auf deine Freigabe"). Zeile: `❗ Du: <Befehl> — <warum>`. Läuft der Schritt automatisch (`AUTO_APPROVAL_STEP`, Auto-Freigabe, kein Slash-Befehl) → waiting mit Text „Auto-Freigabe der Spec läuft". Freigabe-Wörter und Slash-Befehle für den PO → you. `footer_gate` prüft weiterhin nur den Befehl; der Text nach „—" ist Freitext.

**Warten auf CI, Hintergrund-Agent oder Server (`waiting_on`).** Das Ticket verlangt Zustand 2 auch, während CI, ein Hintergrund-Agent oder ein Server läuft. Diese Lage kennt nur Claude selbst; damit Chat und Seitenleiste sie trotzdem aus derselben Quelle zeigen, bekommt der Workflow-State ein Feld `waiting_on` (Text, worauf gewartet wird). Gesetzt mit `workflow.py waiting "<worauf>"`, gelöscht mit `workflow.py waiting --clear`; Ziel wie bei `deploy-status` (aktiver Workflow zuerst, sonst Archiv per `#N`). Jeder Phasenwechsel (`workflow.py phase …`) leert das Feld automatisch, damit kein veralteter Wartezustand stehen bleibt. Ist `waiting_on` gesetzt, liefert `end_state` in jeder Phase vorrangig `waiting` mit der Zeile `⏳ Läuft noch: <waiting_on>. Du musst nichts tun, ich melde mich.` (Ausnahme: `deploy_status == "failed"` bleibt ❗, weil ein Fehlschlag eine Handlung verlangt). Der Fußzeilen-Regeltext (`marker_block`, `status_note`) schreibt vor: Wer einen Turn beendet, während er auf CI/Agent/Server wartet, setzt vorher `workflow.py waiting "<worauf>"` und gibt die ⏳-Zeile aus; wenn das Ergebnis da ist, `waiting --clear`.

**CLI `workflow.py endstate [#N|name]`.** Sucht den aktiven Workflow (Namens-Auflösung wie sonst), sonst per `_deploy_status_target`-Muster im Archiv (der Abschluss-Turn läuft nach `complete`, der Workflow ist dann archiviert). Liest `deploy_mode` und `autonomous` aus der Config, ruft `end_state(..., archived=<gefunden im Archiv>)` und gibt zwei Zeilen aus: `ENDSTATE=<kind>` und `FOOTER=<line>`. Kein Treffer: Meldung auf stderr, Exit 1. Batch-fähig (`batch ... -- endstate`).

**`render_plan`.** Schlusszeile = `end_state(...)["line"]` (ersetzt „Nächster: …" und „abgeschlossen"). Deploy-Zeile nur bei Modus `configured`; bei `off`/`unconfigured`/`running` kein „Nächster: /70-deploy". Lange Zeilen werden umbrochen (Emoji+Art / Rest) statt hart gekürzt.

**Fußzeilen-Regeltext.** `scripts/sync_skills.py::marker_block` und `status_note` in `workflow.py` beschreiben nur noch die drei Formen; danach `python3 scripts/sync_skills.py`.

**Befehlsdateien.** `60-validate.md`: Vorlage „Offen beim PO" entfällt; der Abschluss ruft `workflow.py endstate` auf und gibt `FOOTER` wörtlich als letzte Zeile aus. `70-deploy.md`: endet ebenso mit `endstate`. `30-write-spec.md`: Verweis auf „ℹ️ Nichts-zu-tun" entfällt bzw. nennt ⏳.

**Seitenleiste.** `herdr_bridge.build_report` ergänzt Token `state` (`erledigt`/`läuft`/`du`) für Phasen 1-7, abgeleitet aus `end_state`; Phase 8 leert die Leiste weiter (`clear()` über `TOKEN_NAMES`).

## Expected Behavior

- **Input:** Workflow-State (aktiv oder archiviert), Config (`deploy_mode`, `deploy.autonomous`); Aufrufe `workflow.py endstate [#N]`, `workflow.py plan`, Seitenleisten-Update
- **Output:** genau eine Zeile `✅ Erledigt: …`, `⏳ Läuft noch: …` oder `❗ Du: … — …`; im Chat (FOOTER), im Plan-Schluss und im Seitenleisten-Token identisch abgeleitet
- **Side effects:** ein neues State-Feld `waiting_on` (nur per `workflow.py waiting` gesetzt, bei Phasenwechsel geleert); `herdr_bridge` meldet ein zusätzliches Token

## Known Limitations

- `footer_gate.py` bleibt unverändert: `cmd_complete` archiviert den Workflow, danach löst das Gate keinen Namen mehr auf und steigt fail-open aus; eine Phase-8-Prüfung wäre toter Code. Ersatz ist die Absicherung per Test, dass `60-validate.md` und `70-deploy.md` `workflow.py endstate` enthalten.
- Projekte ohne `deploy:`-Block bekommen kein Deploy-Ende mehr; `/70-deploy` mit `DEPLOY_CONFIGURED=no` wird nur noch manuell aufgerufen.
- ⏳/✅-Zeilen enthalten keinen Slash-Befehl und lösen daher keinen Auto-/clear aus; das ist am Abschluss gewollt (Wechsel bleibt manuell).
- Ob eine Meldung die Zeile tatsächlich wörtlich ausgibt, erzwingt kein Hook, sondern nur der Befehlstext.
- `waiting_on` setzt Claude selbst nach Regeltext; vergisst er es, zeigt die Seitenleiste den Pflicht-Schritt statt ⏳. `scripts/ship.py` wartet synchron innerhalb eines Turns auf CI und braucht das Feld daher nicht.

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] Der Abschluss eines Workflows (mit und ohne Deploy) endet im Chat, im Plan und in der Seitenleiste in genau einem der drei Endzustände; „fachliche Abnahme" und „ℹ️ Nichts zu tun" kommen nirgends mehr vor
- [ ] Bei laufendem oder nicht eingerichtetem Deploy steht nirgends „Nächster: /70-deploy"
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf grün, umgestellte Tests nicht gelöscht)

## Acceptance Criteria

- **AC-1:** Given die Befehlsdateien `core/commands/*.md` und die generierten `skills/*/SKILL.md` / When sie durchsucht werden / Then kommt der Text „fachliche Abnahme" in keiner Datei vor
  - Test: tests/test_endzustand_550.py::test_no_fachliche_abnahme

- **AC-2:** Given Workflows in Phase 8 mit den Fällen off, unconfigured, configured ohne Marker (autonomous true und false), running, done und failed / When `render_plan` läuft / Then ist die Schlusszeile genau eine der drei Formen (Regex `^(✅ Erledigt|⏳ Läuft noch|❗ Du):`) mit der Art done, done, waiting bzw. you, waiting, done, you
  - Test: tests/test_endzustand_550.py::test_render_plan_tail_is_one_of_three

- **AC-3:** Given ein archivierter Workflow ohne Deploy (off oder unconfigured) / When `render_plan` mit `archived=True` läuft / Then zeigt der Plan `✅ Erledigt`, keine Deploy-Zeile und kein „Nächster: /70-deploy"
  - Test: tests/test_endzustand_550.py::test_archived_without_deploy_is_done

- **AC-4:** Given configured, `deploy_status="failed"` und `autonomous=True` / When `end_state` läuft / Then ist die Art `you` und die Zeile beginnt mit `❗ Du: /70-deploy #N — Deploy fehlgeschlagen`
  - Test: tests/test_endzustand_550.py::test_failed_autonomous_is_you

- **AC-5:** Given derselbe Workflow / When `workflow.py endstate` (Chat) und `render_plan` (Plan) laufen / Then liefern beide dieselbe Zeile (FOOTER-Wert gleich Schlusszeile)
  - Test: tests/test_endzustand_550.py::test_endstate_cli_matches_plan

- **AC-6:** Given ein archivierter Workflow `fix-550-x` ohne aktiven Workflow / When `workflow.py endstate #550` läuft / Then Exit 0 mit `ENDSTATE=` und `FOOTER=`; bei unbekannter Nummer Exit 1
  - Test: tests/test_endzustand_550.py::test_endstate_finds_archived

- **AC-7:** Given `marker_block` und der Regeltext von `status_note` / When sie gelesen werden / Then enthalten sie die drei Formen (`✅ Erledigt`, `⏳ Läuft noch`, `❗ Du`) und nicht mehr „ℹ️ Nichts zu tun"
  - Test: tests/test_endzustand_550.py::test_rule_text_has_three_forms

- **AC-8:** Given `core/commands/60-validate.md` und `core/commands/70-deploy.md` / When gelesen / Then enthält jede `workflow.py endstate` und keine Vorlage „Offen beim PO"
  - Test: tests/test_endzustand_550.py::test_commands_call_endstate

- **AC-9:** Given Workflows in den Phasen 1-7 und Phase 8 / When `herdr_bridge.build_report` läuft / Then enthält der Bericht Token `state` passend zu `end_state` (erledigt/läuft/du) für Phasen 1-7, und Phase 8 leert die Leiste weiterhin
  - Test: tests/test_endzustand_550.py::test_herdr_state_token

- **AC-10:** Given ein Workflow in einer Phase vor 8 (z. B. `phase3_spec`) / When `end_state` läuft / Then enthält die ❗-Zeile den Befehl aus `next_step` gefolgt von „ — " und dem Warum-Text aus `NEXT_WHY`; bei Auto-Freigabe ist die Art `waiting`
  - Test: tests/test_endzustand_550.py::test_early_phase_you_line_has_command_and_why

- **AC-11:** Given Fußzeilen mit ✅- oder ⏳-Zeile (ohne Slash-Befehl) / When `footer_gate` läuft / Then wird nicht geblockt (fail-open, Exit 0)
  - Test: tests/test_endzustand_550.py::test_footer_gate_accepts_done_and_waiting

- **AC-12:** Given ein Workflow (Phase vor 8 oder archiviert ohne Deploy) mit `workflow.py waiting "CI von PR 12"` / When `end_state`, `workflow.py endstate` und `herdr_bridge.build_report` laufen / Then ist die Art `waiting`, die Zeile lautet `⏳ Läuft noch: CI von PR 12. Du musst nichts tun, ich melde mich.`, das Token `state` ist `läuft`; nach `waiting --clear` oder einem Phasenwechsel gilt wieder der vorherige Zustand
  - Test: tests/test_endzustand_550.py::test_waiting_on_ci_or_agent_gives_waiting_everywhere

## Test Plan

Automatische Tests (jeweils an eine AC oben gebunden):
- `pytest tests/test_endzustand_550.py` (RED zuerst, dann GREEN)
- umgestellte Bestandstests: `pytest tests/test_plan_deploy_status_510.py tests/test_herdr_plan_deploy_sessionstart_478.py tests/test_herdr_plan_pane_476.py tests/test_plan_issue_titel_490.py tests/test_status_note_325.py tests/test_herdr_sidebar_466.py tests/test_skills_sync.py tests/test_footer_gate_234.py`
- Regressionslauf: `pytest tests/`
- `python3 -m py_compile core/hooks/workflow.py core/hooks/herdr_bridge.py scripts/sync_skills.py`
- `python3 scripts/sync_skills.py --check` (keine Drift in `skills/`)

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Anzeige-Konsolidierung auf das bestehende Muster „eine Quelle, viele Anzeiger" (#234: `expected_footer_command` als dünne Hülle für Hook-Hinweis, Gate und Plan). `end_state()` ist die neue Einzelquelle für den Abschluss; Chat, Plan und Seitenleiste lesen sie nur. Keine Gate-Wirkung, keine neue Architektur, reversibel durch Zurücksetzen der Anzeiger.

## Changelog

- 2026-11-09: Initial spec created
- 2026-11-09: `waiting_on` ergänzt (Zustand 2 auch für CI/Hintergrund-Agent/Server, Befund PO-Briefing)
