---
entity_id: feat-470-spec-ampel
type: feature
created: 2026-10-28
updated: 2026-10-28
status: draft
version: "1.0"
workflow: feat-470-spec-ampel
tags: [autonomie, approvals, po-briefing, ampel]
---

# Spec-Ampel: automatische Spec-Freigabe im Auto-Modus (Issue #470)

## Approval

- [ ] Approved

## Purpose

Teil B von #468: Im Auto-Modus (`autonomy.mode: auto`) gibt die Ampel im unabhaengig erstellten PO-Briefing die Spec frei. Gruen heisst automatische Freigabe (Phase 3 nach 4, protokolliert in `approvals`), rot heisst der PO entscheidet wie bisher per `approved`. Damit muss der PO nur noch Specs anfassen, bei denen der Briefer ein Problem sieht.

## Source

- **File:** `core/hooks/workflow.py`
- **Identifier:** `autonomy_mode`, `parse_ampel`, `_apply_spec_approval`, `cmd_auto_approve`, `cmd_set_briefing`, `_check_po_briefing`, `next_step`, `status_note`, `COMMANDS`

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| #469 `autonomy_mode()`, `record_approval()`, `approvals` | function | Schalter und Freigabe-Protokoll, Grundlage dieser Aenderung |
| `core/hooks/config_loader.py` | module | `find_config_file(find_project_root())` liefert die wirksame Config-Datei (Hauptordner) |
| `core/hooks/workflow.py` | module | `_check_adr`, `_check_po_briefing`, `record_transition`, `_read_active`, `_save_active`, `check_briefing_content` |
| `core/hooks/phase_listener.py` | module | Referenz-Ablauf der menschlichen Freigabe (Zeilen 513-575); bleibt unveraendert |
| `core/hooks/herdr_bridge.py` | module | `build_report` meldet `next=auto` fuer den Auto-Schritt |
| `core/hooks/footer_gate.py` | module | Stop-Hook; muss bei Freitext-Schritt weiter Exit 0 liefern |
| `core/agents/po-briefer.md` | agent | Erzeugt den neuen Pflichtabschnitt `## Ampel` |
| `core/commands/30-write-spec.md`, `core/commands/00-intake.md` | command | Verzweigen auf `AUTO_APPROVE` bzw. verlangen Briefing im Fast Track |
| `scripts/sync_skills.py`, `skills/*/SKILL.md` | script/generated | Skills muessen nach Command-Aenderung synchron sein |
| `scripts/ci_spec_gate.py` | module | Ruft `check_briefing_content`; `## Ampel` darf es nicht kippen |
| `docs/context/feat-468-autonomie-modus.md` | doc | Gesamtanalyse und Gate-Inventar zu #468 |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| core/hooks/workflow.py | MODIFY | `autonomy_mode()` nur aus wirksamer Config; `parse_ampel`; `_apply_spec_approval`; `cmd_auto_approve` + `COMMANDS`-Eintrag; `cmd_set_briefing` speichert `ampel` und `briefing_sha256`; `_check_po_briefing` ohne Fast-Track-Ausnahme im Auto-Modus; `next_step` Auto-Schritt; `status_note` ohne ❗Du-Pflicht im Auto-Fall |
| core/hooks/herdr_bridge.py | MODIFY | `build_report`: Schritt "Auto-..." ergibt `next=auto` |
| core/agents/po-briefer.md | MODIFY | Pflichtabschnitt `## Ampel` mit Regeln, Regel "im Zweifel rot" |
| core/commands/30-write-spec.md | MODIFY | Nach Step 4 `auto-approve`; Verzweigung `AUTO_APPROVE=done` / `human` |
| core/commands/00-intake.md | MODIFY | Fast Track im Auto-Modus mit Briefing |
| skills/30-write-spec/SKILL.md, skills/00-intake/SKILL.md | MODIFY | Regeneriert via `python3 scripts/sync_skills.py` |
| tests/test_spec_ampel_470.py | CREATE | Tests zu allen Acceptance Criteria |
| CHANGELOG.md | MODIFY | Eintrag unter [Unreleased] |

### Estimated Changes

- Files: 1 neu, 8 geaendert (ueber dem 5-Dateien-Richtwert, aber ein zusammenhaengender Schnitt: Skills sind generiert)
- LoC: +130 Produktion / +380 Test

## Implementation Details

**Schalter nur aus wirksamer Config.** `autonomy_mode()` liest nicht mehr `config_loader.load_config()` (das `settings.local.json` einmischt), sondern laedt die wirksame Datei `config_loader.find_config_file(find_project_root())` direkt als YAML, ohne Local-Overrides. Grund: `settings.local.json` ist nicht schreibgeschuetzt, die wirksame Config schon (`bash_gate.py::_writes_effective_config`, Ausweg nur Override-Token). Bleibt fail-closed: nur exakt `"auto"` ergibt `"auto"`, jede Ausnahme und jeder andere Wert ergibt `"manual"`. Ein `autonomy: mode: auto` in `settings.local.json` bleibt wirkungslos.

**Ampel-Parser.** `parse_ampel(text) -> "green" | "red"`. Gruen nur, wenn das Briefing genau einen Abschnitt `## Ampel` hat, dieser genau eine Zeile `Ampel: <wert>` enthaelt und `<wert>` (case-insensitiv, getrimmt) `gruen`, `grün` oder `green` ist. Alles andere ergibt `red`: `rot`, fehlender Abschnitt, doppelter Abschnitt, zwei `Ampel:`-Zeilen, mehrere Zeilen im Abschnitt, unklarer Text. Wirft nie.

**Briefer.** `po-briefer.md` bekommt den Pflichtabschnitt `## Ampel` mit genau einer Zeile `Ampel: gruen` oder `Ampel: rot` (hinter "Freigabe-Frage"). Regeln: rot bei Abweichung vom Ticket, Scope-Frage, offener Entscheidung, Acceptance Criterion ohne Test, vagem AC oder Zweifel; gruen nur, wenn "Kritische Anmerkungen" keine offene Entscheidung des PO verlangt. Im Zweifel rot.

**Registrierung.** `cmd_set_briefing` speichert in `data["po_briefing"]` zusaetzlich `ampel` (Ergebnis von `parse_ampel` auf dem gelesenen Briefing) und `briefing_sha256` (SHA-256 des gelesenen Briefing-Texts, vor dem Frontmatter-Stempel berechnet und nach dem Stempeln auf den gestempelten Text aktualisiert, sodass spaetere Pruefung gegen die Datei auf Platte stimmt).

**Gemeinsamer Freigabe-Helfer.** `_apply_spec_approval(data, trigger) -> list` setzt `spec_approved=True`, ruft `record_transition(data, "phase4_approved", trigger)` und setzt `current_phase="phase4_approved"`. Der Auto-Pfad nutzt ihn mit `trigger="auto"`. `phase_listener.py` bleibt unveraendert und behaelt seinen eigenen Ablauf (Trigger `"approval"`); ein Drift-Test stellt sicher, dass beide Pfade dieselben State-Felder setzen.

**CLI `auto-approve`.** `cmd_auto_approve` druckt auf stdout `AUTO_APPROVE=done|human` und `REASON=<kurz>`, endet immer mit Exit 0 und ist fail-closed (jede Ausnahme ergibt `human`). Reihenfolge, erste Verfehlung ergibt `human` ohne State-Aenderung: (1) `autonomy_mode() == "auto"`; (2) Phase `phase3_spec`, `spec_file` gesetzt, `spec_approved` noch nicht gesetzt (sonst idempotent `human`, kein zweiter `approvals`-Eintrag); (3) `_check_adr` ok; (4) `_check_po_briefing` ok (Briefing vorhanden, vollstaendig, zur aktuellen Spec passend); (5) Briefing-Datei frisch lesen, SHA-256 gleich dem registrierten `briefing_sha256` (sonst Briefing nach Registrierung geaendert); (6) `parse_ampel` der frisch gelesenen Datei ist `green`; dann `_apply_spec_approval(data, "auto")`, `record_approval(data, "spec", "auto", <Grund>, evidence={briefing, briefing_sha256, spec_sha256, ampel})`, `_save_active`, Ausgabe `AUTO_APPROVE=done`.

**Fast Track im Auto-Modus.** `_check_po_briefing` ignoriert `skip_fast_track` und die Fast-Track-Ausnahme, wenn `autonomy_mode() == "auto"`: das Briefing (mit Ampel) ist Pflicht. Der manual-Modus bleibt unveraendert. `00-intake.md` beschreibt das.

**Naechster Schritt.** `next_step`: Phase `phase3_spec` mit `spec_file`, Modus `auto` und `po_briefing.ampel == "green"` ergibt "Auto-Freigabe der Spec (workflow.py auto-approve)"; in allen anderen Faellen bleibt "Freigabe der Spec (Stichwort: approved)". `status_note` nennt im Auto-Fall keine ❗Du-Pflicht fuer diesen Schritt. Der Schritt beginnt nicht mit `/`, daher ist er Freitext: `expected_footer_command` reicht ihn durch und `footer_gate.py` bleibt bei Freitext fail-open (Exit 0). `herdr_bridge.build_report` setzt `next=auto`, wenn der Schritt mit "Auto-" beginnt, sonst wie bisher `approved`.

**Commands.** `30-write-spec.md` ruft nach Step 4 `workflow.py auto-approve`. Bei `AUTO_APPROVE=done` gibt der Orchestrator das Briefing als Info aus (mit Hinweis "automatisch freigegeben") und startet `/40-tdd-red` selbst; bei `human` gilt die bisherige Freigabe-Ausgabe samt ❗Du-Zeile `approved`. Skills werden mit `python3 scripts/sync_skills.py` regeneriert, nie direkt editiert.

**CI-Neutralitaet.** `check_briefing_content` ignoriert unbekannte Abschnitte; `## Ampel` kippt weder das lokale Gate noch `scripts/ci_spec_gate.py`.

## Expected Behavior

- **Input:** Modus `auto` in der wirksamen Config; registriertes Briefing mit `## Ampel`; Aufruf `workflow.py auto-approve`
- **Output:** `AUTO_APPROVE=done` + `REASON=...` (Spec freigegeben, Phase `phase4_approved`) bzw. `AUTO_APPROVE=human` + `REASON=...` (PO entscheidet wie bisher)
- **Side effects:** Bei `done`: `spec_approved=True`, `phase_transitions`-Eintrag mit `trigger "auto"`, `approvals`-Eintrag `gate=spec`, `by=auto` mit Evidence. Bei `human`: State unveraendert.

## Known Limitations

- Die Urheberschaft des Briefings wird nicht erzwungen: Ein Agent koennte ein gruenes Briefing selbst schreiben ("Fake-Gruen"). Mitigation: Hash-Bindung (`briefing_sha256`, `spec_sha256`), Audit-Eintrag in `approvals`, Auflistung automatischer Freigaben in der Abschlussmeldung (#472) und die CI-Pruefung des Briefings im Pull Request.
- Bestehende Briefings ohne `## Ampel` gelten im Auto-Modus als rot (PO entscheidet); im manual-Modus ist die Ampel ohne Wirkung.
- Gelesen wird die wirksame Config des Hauptordners; eine Worktree-lokale Abweichung wirkt nicht.
- Der Listener-Pfad (`approved`) bleibt vollstaendig erhalten und wird nicht durch die Ampel eingeschraenkt.

## Definition of Done

Fertig ist diese Aenderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] Im Auto-Modus mit gruenem, aktuellem Briefing fuehrt `workflow.py auto-approve` die Spec nach `phase4_approved` und `status` zeigt die automatische Freigabe; bei roter Ampel, manual-Modus oder geaendertem Briefing bleibt die Spec in `phase3_spec` und `approved` funktioniert weiter
- [ ] Ein `auto` aus `settings.local.json` schaltet den Auto-Modus nicht ein
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf gruen)

## Acceptance Criteria

- **AC-1:** Given `settings.local.json` setzt `autonomy.mode: auto`, die wirksame `config.yaml`/`openspec.yaml` nicht / When `autonomy_mode()` aufgerufen wird / Then liefert sie `"manual"`; steht `auto` in der wirksamen Config, liefert sie `"auto"`; bei kaputter oder fehlender Config `"manual"` ohne Ausnahme
  - Test: tests/test_spec_ampel_470.py::test_autonomy_mode_ignores_settings_local

- **AC-2:** Given ein Briefing mit genau einem Abschnitt `## Ampel` und der Zeile `Ampel: gruen`, `Ampel: grün` oder `Ampel: green` / When `parse_ampel(text)` aufgerufen wird / Then liefert sie `"green"`
  - Test: tests/test_spec_ampel_470.py::test_parse_ampel_green_variants

- **AC-3:** Given ein Briefing mit `Ampel: rot`, ohne Abschnitt, mit doppelter `Ampel:`-Zeile, mit zwei `## Ampel`-Abschnitten, mit mehreren Zeilen im Abschnitt oder mit unklarem Text / When `parse_ampel(text)` aufgerufen wird / Then liefert sie jeweils `"red"`
  - Test: tests/test_spec_ampel_470.py::test_parse_ampel_everything_else_is_red

- **AC-4:** Given ein Workflow in `phase3_spec` mit gueltigem Briefing mit gruener Ampel / When `workflow.py set-briefing <pfad>` laeuft / Then enthaelt `po_briefing` zusaetzlich `ampel="green"` und `briefing_sha256` passend zum Briefing auf der Platte; bei roter Ampel `ampel="red"`
  - Test: tests/test_spec_ampel_470.py::test_set_briefing_stores_ampel_and_hash

- **AC-5:** Given Modus `auto`, `phase3_spec`, ADR ok, Briefing aktuell, Ampel gruen / When `workflow.py auto-approve` laeuft / Then steht auf stdout `AUTO_APPROVE=done`, der Exit-Code ist 0, `current_phase` ist `phase4_approved`, `spec_approved` ist `true` und `phase_transitions` enthaelt `phase3_spec` nach `phase4_approved` mit `trigger "auto"`
  - Test: tests/test_spec_ampel_470.py::test_auto_approve_happy_path_sets_state

- **AC-6:** Given der Happy Path aus AC-5 / When `auto-approve` fertig ist / Then enthaelt `approvals` genau einen Eintrag mit `gate="spec"`, `by="auto"`, `mode="auto"` und Evidence mit `briefing`, `briefing_sha256`, `spec_sha256` und `ampel`
  - Test: tests/test_spec_ampel_470.py::test_auto_approve_records_approval_with_evidence

- **AC-7:** Given Modus `manual` / When `auto-approve` laeuft / Then steht auf stdout `AUTO_APPROVE=human`, der Exit-Code ist 0 und der State ist byte-identisch unveraendert
  - Test: tests/test_spec_ampel_470.py::test_auto_approve_manual_mode_is_human

- **AC-8:** Given Modus `auto` und Ampel rot bzw. Abschnitt `## Ampel` fehlt / When `auto-approve` laeuft / Then `AUTO_APPROVE=human`, Exit 0, State unveraendert
  - Test: tests/test_spec_ampel_470.py::test_auto_approve_red_or_missing_ampel_is_human

- **AC-9:** Given Modus `auto`, gruene Ampel registriert, aber die Briefing-Datei wurde nach `set-briefing` geaendert (Hash weicht ab, z. B. rot auf gruen gedreht) / When `auto-approve` laeuft / Then `AUTO_APPROVE=human`, Exit 0, State unveraendert
  - Test: tests/test_spec_ampel_470.py::test_auto_approve_briefing_changed_after_registration_is_human

- **AC-10:** Given Modus `auto`, gruene Ampel, aber die Spec wurde nach `set-briefing` geaendert / When `auto-approve` laeuft / Then `AUTO_APPROVE=human`, Exit 0, State unveraendert
  - Test: tests/test_spec_ampel_470.py::test_auto_approve_spec_changed_after_briefing_is_human

- **AC-11:** Given Modus `auto`, gruene Ampel, aber die ADR-Sektion der Spec ist nicht ausgefuellt / When `auto-approve` laeuft / Then `AUTO_APPROVE=human`, Exit 0, State unveraendert
  - Test: tests/test_spec_ampel_470.py::test_auto_approve_adr_missing_is_human

- **AC-12:** Given Modus `auto` und gruene Ampel, aber der Workflow steht nicht in `phase3_spec` / When `auto-approve` laeuft / Then `AUTO_APPROVE=human`, Exit 0, State unveraendert
  - Test: tests/test_spec_ampel_470.py::test_auto_approve_wrong_phase_is_human

- **AC-13:** Given eine bereits freigegebene Spec (`spec_approved=true`) im Auto-Modus / When `auto-approve` ein zweites Mal laeuft / Then `AUTO_APPROVE=human`, Exit 0 und `approvals` enthaelt weiterhin nur den einen bisherigen Eintrag
  - Test: tests/test_spec_ampel_470.py::test_auto_approve_is_idempotent

- **AC-14:** Given ein Fast-Track-Workflow (`feature-fast`) ohne Briefing, auch mit `po_briefing_gate.skip_fast_track: true` / When im Auto-Modus `_check_po_briefing` geprueft wird / Then meldet es das fehlende Briefing; im manual-Modus bleibt die Ausnahme (kein Fehler) unveraendert
  - Test: tests/test_spec_ampel_470.py::test_fast_track_requires_briefing_in_auto_mode

- **AC-15:** Given Modus `auto`, `phase3_spec`, Spec vorhanden und `po_briefing.ampel="green"` / When `next_step` gebildet wird / Then lautet der Schritt "Auto-Freigabe der Spec (workflow.py auto-approve)"; bei roter Ampel, ohne Ampel oder im manual-Modus bleibt er "Freigabe der Spec (Stichwort: approved)"; `status_note` fordert im Auto-Fall keine ❗Du-Zeile fuer diesen Schritt
  - Test: tests/test_spec_ampel_470.py::test_next_step_auto_only_with_green_ampel

- **AC-16:** Given der Auto-Schritt als erwarteter Freitext / When `footer_gate.py` ein Turn-Ende mit beliebiger Freitext-Fusszeile prueft / Then endet es mit Exit 0
  - Test: tests/test_spec_ampel_470.py::test_footer_gate_exit_zero_on_auto_step

- **AC-17:** Given der Auto-Schritt im State / When `herdr_bridge.build_report` laeuft / Then ist `tokens.next` gleich `auto`; beim bisherigen Freigabe-Schritt weiter `approved`
  - Test: tests/test_spec_ampel_470.py::test_herdr_report_next_auto

- **AC-18:** Given `core/agents/po-briefer.md` / When sie gelesen wird / Then enthaelt sie den Pflichtabschnitt `## Ampel` samt Regeln (rot bei Abweichung, Scope-Frage, offener Entscheidung, AC ohne Test, vagem AC, im Zweifel rot)
  - Test: tests/test_spec_ampel_470.py::test_po_briefer_defines_ampel_section

- **AC-19:** Given `core/commands/30-write-spec.md` und `core/commands/00-intake.md` / When sie gelesen werden / Then verzweigt `30-write-spec.md` auf `AUTO_APPROVE=done` bzw. `human`, und `00-intake.md` verlangt im Auto-Modus fuer den Fast Track ein Briefing; die generierten `skills/*/SKILL.md` sind synchron (`sync_skills.py` erzeugt keine Aenderung)
  - Test: tests/test_spec_ampel_470.py::test_commands_branch_on_auto_approve_and_skills_in_sync

- **AC-20:** Given ein Briefing mit zusaetzlichem Abschnitt `## Ampel` / When `workflow.check_briefing_content` (das CI-Gate) es prueft / Then wird es akzeptiert (kein Fehler)
  - Test: tests/test_spec_ampel_470.py::test_check_briefing_content_accepts_ampel_section

- **AC-21:** Given Modus `auto`, rote Ampel, Spec in `phase3_spec` / When der Listener die Nachricht `approved` verarbeitet / Then wird die Spec weiterhin freigegeben (`phase4_approved`, `phase_transitions` mit `trigger "approval"`)
  - Test: tests/test_spec_ampel_470.py::test_listener_approved_still_works_in_auto_mode_with_red_ampel

- **AC-22:** Given eine Freigabe ueber den Listener und eine ueber `auto-approve` auf gleichem Ausgangsstate / When beide Zustaende verglichen werden / Then sind `spec_approved`, `current_phase` und die Form des `phase_transitions`-Eintrags (`from`, `to`) identisch; allein `trigger` und der `approvals`-Eintrag unterscheiden sich
  - Test: tests/test_spec_ampel_470.py::test_listener_and_auto_paths_set_same_state_fields

## Test Plan

Automatische Tests (jeweils an eine AC oben gebunden); Config-Varianten per temporaerer `config.yaml` bzw. `settings.local.json` in einem Temp-Projekt, CLI-Tests als Subprozess mit `OPENSPEC_ACTIVE_WORKFLOW`:

- `pytest tests/test_spec_ampel_470.py`
- Regressionslauf: `pytest tests/` (insbesondere `tests/test_autonomy_schalter_469.py`, Briefing-Gate-, Listener- und footer_gate-Tests)
- Skill-Drift: `python3 scripts/sync_skills.py --check` bzw. Lauf ohne Diff
- Syntaxpruefung: `python3 -m py_compile core/hooks/workflow.py core/hooks/herdr_bridge.py`

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Es existiert kein Verzeichnis `docs/adr` und keine erkennbare ADR-Nummerierung im Repository. Die Weichenstellung (Freigabe-Prinzip im Auto-Modus per Ampel) ist als PO-Entscheidung in #468 und `docs/context/feat-468-autonomie-modus.md` dokumentiert; die Aenderung ist hinter dem Schalter `autonomy.mode` (Default `manual`) abschaltbar, der menschliche Freigabepfad bleibt unveraendert erhalten.

## Changelog

- 2026-10-28: Initial spec created
