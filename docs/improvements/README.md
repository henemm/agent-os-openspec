# Improvement Tracking

Dieses Verzeichnis trackt Improvements aus anderen Projekten.

## Workflow

1. **Du sagst**: "Schau in Projekt X" (GitHub-URL oder lokaler Pfad)
2. **Ich analysiere**: Hooks, Commands, Workflows, Standards
3. **Ich schlage vor**: Was könnte generalisiert werden?
4. **Du entscheidest**: Ja/Nein/Anpassen
5. **Ich integriere**: Ins Meta-Projekt übernehmen

## Analysierte Projekte

| Projekt | Analysiert | Beschreibung | Issues gefunden | Status |
|---------|------------|--------------|-----------------|--------|
| FocusBlox | 2026-05-09 | iOS/macOS SwiftUI, 711 commits, 37+ Workflow-Zyklen | [#3](https://github.com/henemm/agent-os-openspec/issues/3) | Umgesetzt in v3.1 |
| Meditationstimer | 2026-05-09 | iOS/watchOS SwiftUI, Workflow v6, Adversary System | [#4](https://github.com/henemm/agent-os-openspec/issues/4) | Umgesetzt in v3.1 |
| gregor_zwanzig | 2026-05-09 | Python-Service, 170 Commits, externes Validator-System | [#5](https://github.com/henemm/agent-os-openspec/issues/5) | Umgesetzt in v3.1 |

## Umgesetzte Improvements (v3.1)

Aus den 3 Projekten destilliert und als Spec-Proposal [#6](https://github.com/henemm/agent-os-openspec/issues/6) dokumentiert.
Alle 5 Gaps wurden in Core implementiert:

| Gap | Häufigkeit | Umsetzung |
|-----|-----------|-----------|
| Kein Execution Log | 3/3 | `workflow.py write-log`, `_log/` Verzeichnis, `complete` blockiert ohne Log |
| Keine testbaren Acceptance Criteria | 3/3 | `edit_gate.py` prüft `## Acceptance Criteria` + `AC-N` vor phase6-Edits, Spec-Template aktualisiert |
| Scope: nur File-Count, kein LoC | 2/3 | `edit_gate.py` prüft `git diff HEAD --numstat`, Standard-Limit 250 LoC |
| Adversary liest Spec, nicht Code | 2/3 | `implementation-validator.md` fordert `Code reference: file:line` pro Finding; AMBIGUOUS blockiert Commit |
| Kein Phase-Transition Audit Trail | 2/3 | `workflow.py phase` loggt from/to/at/trigger; Fix-Loop-Counter |

## Proposals

Siehe [GitHub Issues mit Label `spec-proposal`](https://github.com/henemm/agent-os-openspec/issues?q=label%3Aspec-proposal)
für detaillierte Verbesserungsvorschläge mit Evidence und Open Questions.
