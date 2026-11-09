---
entity_id: fix-555-nacharbeit-endzustand
type: bugfix
created: 2026-11-09
updated: 2026-11-09
status: draft
version: "1.0"
workflow: fix-555-nacharbeit-endzustand
tags: [workflow, footer, plan, herdr, auftrag]
---

# Nacharbeit zu den Endzuständen und zur Auftragsliste (Issue #555, zu #550/#551)

## Approval

- [ ] Approved

## Purpose

Die Adversary-Dialoge zu #550 und #551 haben mehrere kleine Fehler hinterlassen; der wichtigste trifft den Kern des PO-Wunschs aus #550: Im Auto-Modus mit autarkem Auftrag zeigt die Fußzeile `❗ Du: /50-implement #N`, obwohl Claude den Schritt selbst ausführt. Das ist eine erfundene PO-Aufgabe. Diese Änderung stellt die drei Endzustände wieder eindeutig her und räumt die kleineren Funde (doppelter Punkt, fehlendes Seitenleisten-Update, Wortlaut in Befehlstexten und Config) auf.

## Source

- **File:** `core/hooks/workflow.py`, `core/hooks/herdr_bridge.py`, `core/commands/60-validate.md`, `core/commands/70-deploy.md`, `config.yaml`
- **Identifier:** `end_state`, `_end_state_open`, `_end_state_final`, `queue_end_args`, `cmd_waiting`, zweite `_one_line` (Auskunft `observable-surface`), `herdr_bridge.build_report`

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `workflow.end_state`, `_end_state_open`, `_end_state_queue` (~400-500) | function | Einzelquelle der Endzeile (#550/#551); bekommt `self_driven` und die Selbst-Nummer-Filterung |
| `workflow.queue_end_args` (~502) | function | gemeinsame Quelle der Auftrags-Argumente für `endstate`, Plan und (neu) Seitenleiste |
| `workflow.autonomy_mode` (~1146), `read_auftrag`, `auftrag_open_issues`, `auftrag_autark_open` | function | Auto-Modus und offener autarker Auftrag |
| `workflow.cmd_waiting` (~3264), `_herdr` | function | setzt `waiting_on`; soll die Seitenleiste anstoßen (fail-open) |
| `workflow.cmd_observable_surface` (~3650) | function | nutzt die zweite `_one_line` (Namenskollision) |
| `herdr_bridge.build_report` (~186-225) | function | Seitenleisten-Token `state`/`next` |
| `core/hooks/footer_gate.py` | hook | prüft nur ❗-Zeilen, bleibt unverändert |
| `docs/specs/fix-550-endzustand.md`, `docs/specs/feat-551-auftragsliste.md` | spec | Grundlage; diese Spec ändert nur die hier genannten Punkte |
| `scripts/sync_skills.py`, `setup.py --command-aliases` | tool | Skills und Kurzbefehle neu erzeugen |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| core/hooks/workflow.py | MODIFY | zweite `_one_line` → `_flat_line`; `cmd_waiting` ruft `_herdr("report")`; `deploy_note` nur als String; `end_state(..., self_driven=False)`; `queue_end_args` liefert `self_driven`; `end_state` ignoriert `queue_next` gleich eigener Nummer |
| core/hooks/herdr_bridge.py | MODIFY | `build_report` ruft `end_state(data, **queue_end_args(data))` |
| core/commands/60-validate.md | MODIFY | Kette nur bei „aus deinem Auftrag“ in `FOOTER` |
| core/commands/70-deploy.md | MODIFY | Kette wie oben; `endstate <name>` statt „entfällt ohne Issue-Nummer“ |
| config.yaml | MODIFY | Kommentar „Deploy (nicht eingerichtet)“ ersetzen; Block `auftrag:` mit `enabled: true` (Schreiben im Git-Worktree der Sitzung) |
| tests/test_nacharbeit_555.py | CREATE | Regressionstests zu allen AC |
| skills/*/SKILL.md, .claude/commands/* | REGENERATE | `python3 scripts/sync_skills.py`, `setup.py --command-aliases` |
| CHANGELOG.md | MODIFY | Eintrag unter [Unreleased], kein Versions-Bump |

Nicht umgesetzt (Fund 9): stille Normalisierung der Auftragsnummern bleibt, wie in Spec #551 festgelegt; kein Nutzen für den PO.

### Estimated Changes

- Files: 1 neu (+ regenerierte Skills), 6 geändert
- LoC: ca. +80/-20 Produktion, +150 Test
- Risk Level: MEDIUM (Kern-Hook `workflow.py`, Endzeilen in Phasen < 8 ändern sich; reine Anzeige ohne Gate-Wirkung)

## Implementation Details

1. **Doppelter Punkt (Fund 1).** Die spätere `_one_line` (Auskunft `observable-surface`, ohne `rstrip(".")`) überschreibt die erste. Sie wird in `_flat_line` umbenannt, ihre Aufrufer in `cmd_observable_surface` angepasst. Damit gilt für die Endzeilen wieder `_one_line` mit `rstrip(".")`: `waiting "CI."` ergibt „CI. Du musst …“ ohne Doppelpunkt-Folge „..“. Die Auskunft behält ihr Verhalten.
2. **Seitenleiste bei `waiting` (Fund 2).** `cmd_waiting` ruft nach dem Schreiben (gesetzt und `--clear`) `_herdr("report")`, fail-open wie in `record_transition`.
3. **`deploy_note` (Fund 3).** Nur ein `str` zählt; jeder andere Typ wird ignoriert, es erscheint kein Python-Repr.
4. **`end_state(data, ..., self_driven=False)` (Fund 6, Kern).** Ist `self_driven` wahr und der Schritt in Phasen < 8 ein Slash-Befehl, liefert `_end_state_open` `waiting` mit `⏳ Läuft noch: Claude führt <Befehl> selbst aus. Du musst nichts tun, ich melde mich.` und `cmd` = Befehl. Freigabe-Wörter (`approved` u. Ä.) und Stopps (AMBIGUOUS, BROKEN, Override …) bleiben ❗, ebenso Phase 8/archiviert (dort gilt die bestehende Tabelle aus #550/#551). Ohne autarken Auftrag oder bei `manual` bleibt alles wie in #550.
5. **`queue_end_args`** liefert zusätzlich `self_driven` = `autonomy_mode() == "auto"` UND `auftrag_autark_open()`; Fehler und Kill-Switch `auftrag.enabled: false` ergeben `False`. Es bleibt die einzige Quelle: `cmd_endstate`, `render_plan`/`cmd_plan`/`_plan_watch` und `herdr_bridge.build_report` übergeben `**queue_end_args(data)`; damit sind Plan-Schlusszeile, `endstate`-FOOTER und Seitenleisten-Token-Art auch mit Auftrag und `self_driven` gleich.
6. **Eigene Nummer in `queue_next` (Fund 8).** `end_state` ignoriert `queue_next`, wenn es der `workflow_issue_number` des Workflows entspricht (Verteidigung zusätzlich zur Filterung in `queue_end_args`), damit ein Aufrufer ohne Filter kein „startet #N“ für das eigene, fertige Issue erzeugt.
7. **Befehlstexte (Funde 4, 7).** `60-validate.md` und `70-deploy.md`: die Kette (`/00-intake #M` ohne Halt) greift nur, wenn der Wert hinter `FOOTER=` „aus deinem Auftrag“ enthält (nicht bei `waiting` wegen CI oder Deploy). `70-deploy.md` ruft `endstate <name>` auf, wenn keine Issue-Nummer vorliegt; nur ohne Workflow entfällt der Aufruf. Danach `python3 scripts/sync_skills.py` und `setup.py --command-aliases`.
8. **config.yaml (Funde 5, 10).** Der Kommentar zu `enabled: false` nennt das Verhalten nach #550 („Projekt ohne Deploy: der Plan endet mit ✅“) statt „Deploy (nicht eingerichtet)“; ein Block `auftrag:` mit `enabled: true` und Kurzkommentar kommt dazu. `auftrag` ist bereits in `PLUGIN_CONFIG_KEYS` eingeordnet. Schreiben nur im Worktree (Hook-Vorgabe zur wirksamen Gate-Config).
9. **footer_gate (Fund 9 aus Sicht Hook).** Keine Codeänderung: eine `⏳ Läuft noch: Claude führt … selbst aus`-Zeile enthält keine ❗-Zeile und wird fail-open durchgelassen; ein Test sichert das.

## Expected Behavior

- **Input:** Workflow-State in Phasen 1-8 oder archiviert, Autonomie `auto`/`manual`, Auftragsdatei `.claude/auftrag.json`, Aufrufe `workflow.py waiting`, `endstate`, `plan`, Seitenleisten-Update
- **Output:** genau eine der drei Endzeilen; im Auto-Modus mit offenem autarkem Auftrag zeigen Phasen < 8 mit Slash-Schritt `⏳ Läuft noch: Claude führt <Befehl> selbst aus. …`, sonst unverändert `❗ Du: …`; Chat, Plan und Seitenleiste zeigen dieselbe Art
- **Side effects:** `waiting` stößt ein Seitenleisten-Update an; kein neues State-Feld, keine neue Gate-Wirkung

## Known Limitations

- `self_driven` beschreibt die Zusage „Claude führt den Schritt aus“; ob Claude es tut, erzwingt kein Hook (wie bei allen ⏳-Zeilen).
- Freigabe-Wort-Schritte bleiben ❗ auch im Auto-Modus; die Auto-Freigabe ist ein eigener Fall (`AUTO_APPROVAL_STEP`, #550).
- Ein `str`-`deploy_note` bleibt erlaubt; ein Nicht-String geht verloren (bewusst, kein Nutzen als Repr).
- config.yaml-Änderung ist nur über den Worktree möglich; Konsumenten-Projekte bekommen sie über `setup.py --update`.

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] Im Auto-Modus mit offenem autarkem Auftrag erscheint für Schritte, die Claude selbst ausführt, keine ❗-Zeile mehr
- [ ] Plan, `endstate` und Seitenleiste zeigen auch mit Auftrag dieselbe Endzeile
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf grün, `skills/` ohne Drift)

## Acceptance Criteria

- **AC-1:** Given `workflow.py waiting "CI."` / When die Endzeile gebildet wird / Then lautet sie `⏳ Läuft noch: CI. Du musst nichts tun, ich melde mich.` ohne doppelten Punkt, und die Auskunft `observable-surface` liefert unverändert genau ihre fünf Zeilen
  - Test: tests/test_nacharbeit_555.py::test_waiting_trailing_dot_and_observable_surface_unchanged

- **AC-2:** Given ein aktiver Workflow und ein Stub für `_herdr` / When `cmd_waiting` mit Text bzw. mit `--clear` läuft / Then wird `_herdr("report")` aufgerufen; wirft der Stub, bleibt `cmd_waiting` fehlerfrei (fail-open)
  - Test: tests/test_nacharbeit_555.py::test_cmd_waiting_triggers_sidebar_report

- **AC-3:** Given `deploy_status="failed"` und ein `deploy_note`, das kein String ist (Liste, Zahl, dict) / When `end_state` läuft / Then enthält die Zeile keinen Python-Repr (kein `[`, `{`, kein `()`-Zusatz) und lautet `… Deploy fehlgeschlagen, bitte neu anstoßen`
  - Test: tests/test_nacharbeit_555.py::test_non_string_deploy_note_ignored

- **AC-4:** Given Auto-Modus und ein offener autarker Auftrag (`self_driven=True`) / When `end_state` für Phasen < 8 mit Slash-Schritt läuft / Then ist die Art `waiting`, `cmd` der Befehl und die Zeile `⏳ Läuft noch: Claude führt <Befehl> selbst aus. Du musst nichts tun, ich melde mich.`; ohne autarken Auftrag oder bei `manual` bleibt es `❗ Du: <Befehl> — …`; Schritte mit Freigabe-Wort bleiben auch mit `self_driven` ❗
  - Test: tests/test_nacharbeit_555.py::test_self_driven_open_step_is_waiting

- **AC-5:** Given Auftrag und `self_driven` in einer Phase < 8 / When Plan (`render_plan`), `workflow.py endstate` und `herdr_bridge.build_report` laufen / Then sind Plan-Schlusszeile und `FOOTER` identisch, und das Seitenleisten-Token `state` entspricht derselben Art (herdr nutzt `queue_end_args`)
  - Test: tests/test_nacharbeit_555.py::test_plan_endstate_sidebar_agree_with_self_driven

- **AC-6:** Given ein fertiger Workflow `#555` / When `end_state(..., queue_next=555)` (eigene Nummer) läuft / Then entsteht keine Zeile „Claude startet #555 …“ bzw. `/00-intake #555`, sondern `✅ Erledigt`; mit `queue_next=556` bleibt die Auftragszeile
  - Test: tests/test_nacharbeit_555.py::test_end_state_ignores_own_issue_in_queue_next

- **AC-7:** Given `core/commands/60-validate.md`, `core/commands/70-deploy.md` und die generierten Skills / When gelesen / Then bindet jede Kette an „aus deinem Auftrag“ in `FOOTER`, `70-deploy.md` nennt `endstate <name>` statt „entfällt ohne Issue-Nummer“, und `python3 scripts/sync_skills.py --check` meldet keine Drift
  - Test: tests/test_nacharbeit_555.py::test_command_texts_chain_only_on_auftrag_and_skills_synced

- **AC-8:** Given die Template-`config.yaml` / When gelesen und per `config_loader` geprüft / Then enthält sie einen Block `auftrag:` mit `enabled: true`, den Text „Deploy (nicht eingerichtet)“ nicht mehr, und `test_ac7_template_keys_classified` sowie `is_plugin_config` bleiben grün
  - Test: tests/test_nacharbeit_555.py::test_config_has_auftrag_block_and_no_stale_deploy_text

- **AC-9:** Given eine Fußzeile mit `⏳ Läuft noch: Claude führt /50-implement #555 selbst aus. Du musst nichts tun, ich melde mich.` ohne ❗-Zeile / When `footer_gate` läuft / Then wird nicht geblockt (Exit 0)
  - Test: tests/test_nacharbeit_555.py::test_footer_gate_accepts_self_driven_waiting_line

## Test Plan

Automatische Tests (jeweils an eine AC oben gebunden, alle ohne Netzwerk, `_herdr` und Auftragsdatei per Stub/`tmp_path`):
- `pytest tests/test_nacharbeit_555.py` (RED zuerst, dann GREEN)
- Bestandstests zu #550/#551: `pytest tests/test_endzustand_550.py tests/test_auftrag_551.py tests/test_footer_gate_234.py tests/test_app_config_yaml_372.py tests/test_skills_sync.py`
- Regressionslauf: `pytest tests/`
- `python3 -m py_compile core/hooks/workflow.py core/hooks/herdr_bridge.py`
- `python3 scripts/sync_skills.py --check`

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Nacharbeit im bestehenden Muster „eine Quelle, viele Anzeiger“ (#234, #550): `end_state()` bleibt rein, die Aufrufer liefern Auftrags- und Autonomie-Lage über die gemeinsame `queue_end_args`. Der neue Parameter `self_driven` setzt nur die PO-Vorgabe aus #550 („keine erfundenen PO-Aufgaben“) konsequent um. Keine Gate-Wirkung, rein additiv, reversibel durch Zurücksetzen der Anzeiger.

## Changelog

- 2026-11-09: Initial spec created
