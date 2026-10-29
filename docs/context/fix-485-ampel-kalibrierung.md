# Context: fix-485-ampel-kalibrierung

## Request Summary
PO, Auto-Modus aktiv: „irgendwie zeigt die aber immer "rot"!“ — der po-briefer stuft jede Spec rot ein, damit landet jede Freigabe beim PO. Zusätzlich gab der PO eine Freigabe im Auswahldialog, die nicht zählte (nur getippte Stichwörter wirken).

## Related Files
| File | Relevance |
|------|-----------|
| `core/agents/po-briefer.md` | Abschnitt `## Ampel`: „sonstiger Zweifel → rot“, „Im Zweifel rot“; Pflicht-Freigabe-Frage |
| `core/commands/30-write-spec.md` | Step 4b Auto-Freigabe, Freigabe-Ausgabe; erfragt Freigabe nicht ausdrücklich per Dialog, verbietet es aber auch nicht |
| `core/hooks/workflow.py` | `parse_ampel`, `check_briefing_content` (Freigabe-Frage-Pflicht, Wortgrenzen) |
| `tests/test_spec_ampel_470.py`, `tests/test_po_briefing_gate.py` | Verträge Ampel/Briefing |
| `skills/30-write-spec/SKILL.md` | generiert aus core/commands |

## Analysis
- Reine Anweisungsänderung (Agent-/Command-Text) + ggf. Gate-Toleranz für „Freigabe-Frage: Keine …“ bei grün (prüfen, ob `check_briefing_content` eine Frage erzwingt).
- Dialog-Freigabe: kein neuer Hook (Sicherheitsfläche); stattdessen Regel in 30-write-spec/00-intake: Freigabe nie per Auswahldialog erfragen, immer als Stichwort-Zeile; nimmt der PO im Dialog trotzdem frei, bittet Claude um das Stichwort in einer Zeile.
- Risiko LOW–MEDIUM (Freigabe-Schwelle sinkt; Rot-Gründe für echte Abweichungen bleiben).
