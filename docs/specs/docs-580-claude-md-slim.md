---
entity_id: docs-580-claude-md-slim
type: docs
created: 2026-11-25
updated: 2026-11-25
status: draft
version: "1.0"
workflow: docs-580-claude-md-slim
tags: [token, claude-md, docs, epic-649]
---

# CLAUDE.md verschlanken (Issue #580)

## Approval

- [ ] Approved

## Purpose

`CLAUDE.md` dieses Repos hat 39 904 Bytes (rund 10 000 Token) und wird bei jedem Hauptzug und jedem Teilagenten-Start mitgelesen. Der größte Teil ist Nachschlagewissen (Architektur-Baum, Hook-Architektur, Wichtige-Dateien-Tabelle, Phasen-Diagramm, Slash-Command-Liste, Session-Register, CI-Spec-Gate). Dieser Schnitt verschiebt das Nachschlagewissen wörtlich nach `docs/architektur.md` und lässt in `CLAUDE.md` nur, was in jedem Zug gelten muss. Ziel: `CLAUDE.md` ≤ 12 KB, Grundlast jeder Sitzung im Framework-Repo sinkt um rund 7 000 Token (Hebel für Epic #649, Punkt „Grundlast frischer Cloud-Sitzungen“).

## Source

- **File:** `CLAUDE.md`, neu `docs/architektur.md`
- **Identifier:** Abschnitte von `CLAUDE.md`

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `scripts/release_check.py::check_claude_md_version` | function | liest nur die Zeile `**Version**:`; bleibt in CLAUDE.md |
| `core/hooks/claude_md_protection.py` | hook | prüft `max_lines` (600) und verbotene Muster; eine Kürzung bleibt darunter, kein Block |
| `tests/test_state_files_source_422.py` | test | erwartet die `hook_utils.py`-Zeile der Datei-Tabelle; liest künftig CLAUDE.md + docs/architektur.md |
| `tests/test_cloud_agents_577.py` | test | erwartet `scripts/sync_cloud_agents.py` und `.claude/agents/`; liest künftig beide Dateien |
| `tests/test_agent_dispatch_drift_279.py` | test | Agenten-Namen und Modell-Tabelle; liest künftig beide Dateien |
| `tests/test_rueckbau_autoclear_663.py`, `test_readme_version_195.py`, `test_release_check_93.py` u. a. | test | Versionszeile und Abwesenheit von Auto-/clear-Texten; bleiben erfüllt |
| `docs/arbeitsweise.md` | doc | Volltext der Arbeitsweise; Verweis bleibt |
| Epic #649 | issue | Messung der Grundlast vorher/nachher wird dort festgehalten |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| CLAUDE.md | MODIFY | auf Kernregeln kürzen (≤ 12 288 Bytes), Verweis-Satz auf `docs/architektur.md` |
| docs/architektur.md | CREATE | verschobene Referenzabschnitte, wörtlich übernommen |
| tests/test_claude_md_slim_580.py | CREATE | Größenwächter und Pinn-Tests zu den ACs |
| tests/test_state_files_source_422.py, tests/test_cloud_agents_577.py, tests/test_agent_dispatch_drift_279.py | MODIFY | Referenzinhalt in CLAUDE.md + docs/architektur.md suchen |
| CHANGELOG.md, .claude-plugin/plugin.json, README.md, Versionsmarker | MODIFY | Version 4.25.2 |

### Estimated Changes

- Files: 2 Doku, 1 neuer Test, 3 Tests angepasst, Versionsdateien
- LoC: CLAUDE.md ca. -400, docs/architektur.md ca. +420, Tests ca. +80
- Risk Level: LOW (nur Anweisungstext, Doku, Tests; kein Hook-Code)

## Implementation Details

**Bleibt in CLAUDE.md** (gilt in jedem Zug): Titel, Meta-Satz, `**Version**:`-Zeile; „Rollen und Zusammenarbeit“ und „Arbeitsweise“ unverändert; Projektzweck; Orchestrator-Prinzip; Phasenfolge als kurze Liste; Kern der Workflow-Steuerung (`OPENSPEC_ACTIVE_WORKFLOW`, `workflow.py start`, Pflicht-Zeile im Agent-Brief); Kontext-Haushalt in Kurzform; harte Regeln (CHANGELOG/Version, Infrastruktur-Schutz `core/hooks`/`core/agents` mit Override, `skills/` generiert, Hook-Entwicklung in die Kern-Gates, Hook-Pfade nie cwd-relativ #165, Exit-Codes); Workflow-Isolation; Adversary-Limit; ein Verweis-Satz auf `docs/architektur.md`.

**Wandert wörtlich nach docs/architektur.md:** Architektur-Baum, 8-Phasen-Diagramm, Parallele Workflows (inkl. Namensauflösung, Symlink-Verbot, Migration v2), TDD mit echten Artefakten, Modell-Zuweisungsstrategie, Adversary System, PO-Briefing-Gate, CI-Spec-Gate, Stop Lock, Override Token, Kontext-Haushalt (Langfassung), Hook-Architektur, Session-Register, Verzeichnis-Konventionen, Hook-Entwicklungs-Beispiel, Improvement-Flow, Wichtige Dateien, Slash-Commands-Übersicht. Inhalt bleibt unverändert, nur Überschriftenebene und ein Einleitungssatz kommen hinzu.

**Tests:** Die drei Bestandstests, die Referenzinhalt suchen, lesen den Text von `CLAUDE.md` und `docs/architektur.md` zusammen. Kein `skip`/`xfail`. Bei der Umsetzung zusätzlich gefunden und mitgezogen: `tests/test_adversary_coverage_gate_259.py` (Fall `claude-md-hooks` sucht „### Hooks“ jetzt in `docs/architektur.md`) und `tests/test_adversary_risk_342.py` (`TEXT_FILES` nennt `docs/architektur.md`, weil die Rundenregel im Abschnitt Adversary System liegt).

## Expected Behavior

- **Input:** Sitzungsstart im Framework-Repo (CLAUDE.md wird geladen)
- **Output:** CLAUDE.md ≤ 12 288 Bytes mit allen in jedem Zug nötigen Regeln; Nachschlagewissen vollständig in `docs/architektur.md`
- **Side effects:** Grundlast jeder Sitzung und jedes Teilagenten-Starts im Framework-Repo sinkt; Konsumenten-Projekte sind nicht betroffen (ihre CLAUDE.md erzeugt `setup.py` separat)

## Known Limitations

- Wirkt nur in Sitzungen im Framework-Repo, nicht in Konsumenten-Projekten.
- Der größte Teil der Grundlast einer Cloud-Sitzung (Systemanweisung, Werkzeuglisten der Umgebung, Befehlstexte) liegt außerhalb dieses Repos; der Effekt beträgt daher rund 7 000 von rund 100 000 Token.
- `claude_md_protection.py` behält `max_lines: 600`; die engere Grenze (12 KB) sichert der Test, nicht der Hook.

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] CLAUDE.md ≤ 12 288 Bytes, alle verschobenen Abschnitte in `docs/architektur.md`
- [ ] Gesamtsuite grün, `skills/` und Cloud-Agents ohne Drift, kein `skip`/`xfail`
- [ ] CHANGELOG `[4.25.2]`, Version 4.25.2 überall, veröffentlicht
- [ ] Grundlast vorher/nachher (`workflow.py context` bzw. erster Modellaufruf nach Sitzungsstart) in Epic #649 festgehalten
- [ ] #579 geprüft und, falls durch #649/#667 überholt, mit Begründung geschlossen

## Acceptance Criteria

- **AC-1:** Given das Repo nach der Änderung / When die Größe von `CLAUDE.md` gemessen wird / Then beträgt sie höchstens 12 288 Bytes
  - Test: tests/test_claude_md_slim_580.py::test_claude_md_within_budget

- **AC-2:** Given `CLAUDE.md` / When nach dem Verweis gesucht wird / Then nennt sie `docs/architektur.md`, und diese Datei existiert
  - Test: tests/test_claude_md_slim_580.py::test_claude_md_links_architektur

- **AC-3:** Given `docs/architektur.md` / When ihre Überschriften geprüft werden / Then enthält sie die verschobenen Abschnitte Architektur, 8-Phasen-Workflow, Parallele Workflows, TDD mit ECHTEN Artefakten, Modell-Zuweisungsstrategie, Adversary System, PO-Briefing-Gate, CI-Spec-Gate, Stop Lock, Override Token, Hook-Architektur, Session-Register, Improvement-Flow, Wichtige Dateien, Slash-Commands Übersicht
  - Test: tests/test_claude_md_slim_580.py::test_architektur_has_moved_sections

- **AC-4:** Given `CLAUDE.md` / When die Kernregeln geprüft werden / Then enthält sie die Abschnitte Rollen und Zusammenarbeit, Arbeitsweise, Orchestrator-Prinzip, Workflow-Isolation, Adversary-Limit sowie die Regeln zu Hook-Pfaden (#165), zum Infrastruktur-Schutz von `core/hooks/` und `core/agents/` (Override) und zu generierten `skills/`, dazu die Zeile `**Version**:`
  - Test: tests/test_claude_md_slim_580.py::test_claude_md_keeps_core_rules

- **AC-5:** Given die Referenz-Prüfungen aus #422, #577 und #279 / When sie gegen CLAUDE.md und docs/architektur.md zusammen laufen / Then sind sie grün (Datei-Tabelle mit `hook_utils.py`-Funktionen, `scripts/sync_cloud_agents.py`, Modell-Tabelle)
  - Test: tests/test_claude_md_slim_580.py::test_reference_facts_still_documented

## Test Plan

- `pytest tests/test_claude_md_slim_580.py` (RED zuerst, dann GREEN)
- `pytest tests/test_state_files_source_422.py tests/test_cloud_agents_577.py tests/test_agent_dispatch_drift_279.py tests/test_rueckbau_autoclear_663.py tests/test_readme_version_195.py tests/test_release_check_93.py`
- Regressionslauf `pytest tests/`; `python3 scripts/sync_skills.py --check`; `python3 scripts/sync_cloud_agents.py --check`

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Reine Umverteilung von Dokumentation; keine neue Entscheidungsfläche. Ziel und Grenze (≤ 12 KB) stehen im Issue.
- **Alternative A, Referenzteile löschen statt verschieben:** verworfen, Nachschlagewissen ginge verloren bzw. stünde nur verstreut in Befehlstexten.
- **Alternative B, Größenwächter im Hook `claude_md_protection.py` (Bytes statt Zeilen):** verworfen, Hook-Code in allen Konsumenten für ein Repo-internes Ziel; ein Test im Repo genügt.
- **Alternative C, CLAUDE.md per `@import` aufteilen:** verworfen, importierte Dateien werden ebenfalls in jeden Zug geladen und sparen nichts.

## Changelog

- 2026-11-25: Erstfassung
