---
entity_id: fix-485-ampel-kalibrierung
type: feature
created: 2026-10-29
updated: 2026-10-29
status: draft
version: "1.0"
workflow: fix-485-ampel-kalibrierung
tags: [po-briefer, ampel, autonomy, approval]
---

# Ampel neu kalibrieren; keine Freigabe per Auswahldialog (Issue #485)

## Approval

- [ ] Approved

## Purpose

Im Auto-Modus soll die Spec-Freigabe nur noch dann beim PO landen, wenn wirklich eine Entscheidung offen ist, die nur er treffen kann. Heute stuft der `po-briefer` praktisch jede Spec rot ein („sonstiger Zweifel“, „Im Zweifel rot“, Pflicht zur Freigabe-Frage). Die Regeln werden so gefasst, dass bereits getroffene PO-Entscheidungen, dokumentierte Einschraenkungen und eine noetige manuelle Abnahme die Ampel nicht mehr rot machen. Ausserdem erfragt Claude eine Spec-Freigabe nie mehr per Auswahldialog, weil eine Dialog-Antwort vom Freigabe-Hook nicht gesehen wird.

## Source

- **File:** `core/agents/po-briefer.md`, `core/commands/30-write-spec.md` (+ generiert `skills/30-write-spec/SKILL.md`)
- **Identifier:** Abschnitt `## Ampel` und Briefing-Vorlage (Freigabe-Frage) im po-briefer; Freigabe-Ausgabe in 30-write-spec

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `core/agents/po-briefer.md` (#470) | agent | erzeugt Briefing + Ampel |
| `core/hooks/workflow.py` | module | `parse_ampel`, `check_briefing_content` (Freigabe-Frage optional, Wortgrenze 120) — unveraendert |
| `core/commands/30-write-spec.md` | command | Step 3b/4b, Freigabe-Ausgabe |
| `scripts/sync_skills.py` | script | erzeugt `skills/` aus `core/commands/` |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| core/agents/po-briefer.md | MODIFY | Ampel-Regeln neu: abschliessende Rot-Liste, ausdrueckliche Nicht-Rot-Liste, „Im Zweifel rot“ entfaellt; Freigabe-Frage bei gruen „Keine – Ampel gruen.“ |
| core/commands/30-write-spec.md | MODIFY | Regel: Spec-Freigabe nie per Auswahldialog erfragen; Dialog-Antwort zaehlt nicht |
| skills/30-write-spec/SKILL.md | MODIFY | per `sync_skills.py` neu erzeugt |
| tests/test_ampel_kalibrierung_485.py | CREATE | Textvertraege fuer po-briefer und 30-write-spec |
| CHANGELOG.md | MODIFY | Eintrag unter [Unreleased] |

### Estimated Changes

- Files: 1 neu, 4 geaendert
- LoC: +40 Anweisungstext / +60 Test
- Risk Level: LOW (nur Anweisungstext; Gate-Logik unveraendert)

## Implementation Details

**Ampel im po-briefer (ersetzt die bisherigen Stichpunkte unter `## Ampel`):**

- **rot nur bei** (abschliessend):
  1. Abweichung vom Ticket (anders geloest, weggelassen, zusaetzlich eingebaut), die der PO weder in der Ursprungsanfrage noch in den dort genannten PO-Entscheidungen bereits entschieden hat;
  2. Acceptance Criterion ohne Test oder mit vager Formulierung („korrekt“, „sinnvoll“, „schnell“);
  3. eine offene Entscheidung, die nur der PO treffen kann und die noch nicht getroffen ist.
- **nicht rot** (ausdruecklich): dokumentierte Known Limitations; Pruefung nur durch manuelle Abnahme moeglich; Risiken, die die Spec selbst behandelt oder benennt; vom PO bereits getroffene Entscheidungen; Umsetzungsdetails, die der PO nicht beurteilen muss.
- Kritische Anmerkungen duerfen auch bei gruen stehen (Information, keine Entscheidung).
- Der Satz „Im Zweifel rot“ und die Formulierung „sonstiger Zweifel“ entfallen. Stattdessen: „Unsicher? Pruefe, ob der Punkt unter die drei Rot-Gruende faellt. Wenn nicht: gruen.“
- Vorlage `## Freigabe-Frage`: bei gruen genau „Keine – Ampel gruen.“, bei rot eine Entscheidungsfrage zum Rot-Grund.

**30-write-spec:** Im Abschnitt „Freigabe-Ausgabe an den User“ ein Absatz: Die Spec-Freigabe wird nie per Auswahldialog (AskUserQuestion) erfragt, sondern immer mit der ❗Du-Zeile `approved`; der Freigabe-Hook sieht nur getippte Nachrichten. Hat der PO im Dialog bereits freigegeben, bittet Claude in genau einer Zeile um das Stichwort.

## Expected Behavior

- **Input:** Spec ohne offene PO-Entscheidung, mit Known Limitations und manueller Abnahme
- **Output:** Briefing mit `Ampel: gruen`; im Auto-Modus automatische Freigabe
- **Side effects:** keine

## Known Limitations

- Die Ampel bleibt eine Einschaetzung eines Modells; die Tests pruefen nur den Anweisungstext, nicht das Urteil im Einzelfall.
- Eine im Auswahldialog gegebene Freigabe zaehlt weiterhin nicht; die Regel verhindert nur, dass Claude danach fragt.

## Definition of Done

Fertig ist diese Aenderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] Im Auto-Modus laufen Specs ohne offene Entscheidung ohne `approved` durch (manuelle Abnahme durch den PO)
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf gruen, insbesondere #470/PO-Briefing-Tests)

## Acceptance Criteria

- **AC-1:** Given `core/agents/po-briefer.md` / When der Abschnitt zur Ampel gelesen wird / Then enthaelt er die drei Rot-Gruende (Ticket-Abweichung ohne PO-Entscheidung, AC ohne Test/vage, offene PO-Entscheidung) und nicht mehr die Formulierungen „Im Zweifel rot“ und „sonstigem Zweifel“
  - Test: tests/test_ampel_kalibrierung_485.py::test_po_briefer_red_reasons_closed_list

- **AC-2:** Given `core/agents/po-briefer.md` / When der Abschnitt gelesen wird / Then nennt er ausdruecklich als nicht rot: Known Limitations, manuelle Abnahme, bereits getroffene PO-Entscheidungen
  - Test: tests/test_ampel_kalibrierung_485.py::test_po_briefer_not_red_list

- **AC-3:** Given ein Briefing mit allen Pflichtabschnitten, `## Freigabe-Frage` = „Keine – Ampel gruen.“ und `Ampel: gruen` / When `workflow.check_briefing_content` und `workflow.parse_ampel` laufen / Then gilt das Briefing als vollstaendig und die Ampel als gruen
  - Test: tests/test_ampel_kalibrierung_485.py::test_green_briefing_without_question_passes_gate

- **AC-4:** Given `core/commands/30-write-spec.md` und `skills/30-write-spec/SKILL.md` / When gelesen / Then steht dort, dass die Spec-Freigabe nicht per Auswahldialog (AskUserQuestion) erfragt wird
  - Test: tests/test_ampel_kalibrierung_485.py::test_write_spec_forbids_dialog_approval

## Test Plan

Textvertraege per Dateilesen; Gate-Pruefung per Import von `workflow.check_briefing_content`/`parse_ampel`.

- `pytest tests/test_ampel_kalibrierung_485.py`
- Regressionslauf: `pytest tests/`
- `python3 scripts/sync_skills.py --check` (falls vorhanden) bzw. Release-Check auf Skill-Drift

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Anpassung von Anweisungstexten an das beobachtete Verhalten; keine Aenderung an Gates, State oder Hooks. Reversibel durch Zuruecksetzen der Texte.

## Changelog

- 2026-10-29: Initial spec created
