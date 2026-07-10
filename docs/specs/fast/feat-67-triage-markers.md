# Mini-Spec: Intake-Agenten triage-bewusst machen (#67)

## Was ändert sich
- `core/agents/bug-intake.md` (Step 6, `gh issue create --body`, ~Zeile 104): Body bekommt eine erste Zeile `[triage:x]` + eine kurze Anleitung im Template, welcher Marker passt: `[triage:a]` bei nutzersichtbarem Fehlverhalten, `[triage:b]` bei Datenverlust-/Sicherheitsrisiko, `[triage:po]` wenn die Aufnahme direkt vom PO angestoßen wurde.
- `core/agents/bug-investigator.md` (`gh issue create --body`, ~Zeile 42): gleiche Ergänzung — Marker-Wahl richtet sich nach der gefundenen Root Cause (`[triage:a]`/`[triage:b]`) bzw. `[triage:po]` falls der PO die Analyse beauftragt hat.
- `core/agents/feature-planner.md` (`gh issue create --body`, ~Zeile 58): gleiche Ergänzung — Standardfall hier ist `[triage:po]` (Feature-Planung wird i.d.R. vom PO angestoßen), mit Hinweis, `[triage:a]`/`[triage:c]` zu nutzen falls das Feature aus einem konkreten Nutzerproblem bzw. einem fälschlich blockierenden Gate abgeleitet ist.

Die Agenten wählen den Marker selbst aus der jeweiligen Situation (kein hartcodierter Marker pro Template).

## Was darf sich nicht ändern
- Keine Logik-Änderung an Hooks (`bash_gate.py` etc.) — reine Doku-/Template-Änderung in den drei Agent-Dateien
- Keine Hardcodierung von Repo- oder Issue-Nummern (Nicht-Ziel aus #67)
- Bestehende Body-Struktur (Symptom / Root Cause / Aufwand etc.) bleibt inhaltlich erhalten, der Marker wird nur ergänzt

## Manuelle Test-Schritte
1. `grep -n "gh issue create" -A 5 core/agents/bug-intake.md core/agents/bug-investigator.md core/agents/feature-planner.md` — alle drei Treffer zeigen jetzt eine `[triage:x]`-Zeile mit Auswahl-Hinweis im Body-Template
2. Lesbarkeitscheck: Ein Mensch, der die Templates zum ersten Mal liest, versteht ohne Zusatzkontext, welchen Marker er in welcher Situation wählt

## Inline-Test (wird während Implementierung geschrieben)
- [ ] Grep-Assertion: alle 3 `gh issue create`-Blöcke in `core/agents/*.md` enthalten `[triage:` im Body-Template (Skript-Check, kein Unit-Test-Framework nötig, da reine Markdown-Templates ohne ausführbaren Code)
