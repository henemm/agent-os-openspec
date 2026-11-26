---
entity_id: docs-679-marker-slim
type: refactor
created: 2026-11-26
updated: 2026-11-26
status: draft
version: "1.0"
workflow: docs-679-marker-slim
tags: [token, marker-block, hook-hinweis, epic-649]
---

# Versions-Marker-Block und Hook-Hinweis verschlanken (Issue #679)

## Approval

- [ ] Approved

## Purpose

Der Versions-Marker-Block hängt an jedem der 15 generierten Befehlstexte (heute 3 259 Bytes), und der Hook-Hinweis je Nutzer-Nachricht kostet heute 1 886 Bytes. Beide werden auf das Nötige gekürzt (Block höchstens 1 200, Hinweis höchstens 900 Bytes); die Begründungsprosa zieht wörtlich nach `docs/befehle/fusszeile.md`. Gate-Verhalten bleibt unverändert. Folgeschnitt von #674/#677/#678 im Epic #649.

## Source

- **File:** `scripts/sync_skills.py`, `core/hooks/workflow.py`
- **Identifier:** `marker_block(name, version)`; `END_STATE_RULE`, `_status_note_base`, `status_note`

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `core/hooks/alias_sync.py` (Zeilen 148-150) | hook | erkennt die Zeile, die mit `⚙ ` beginnt; diese Zeile bleibt wörtlich |
| `core/hooks/footer_gate.py`, `core/hooks/phase_listener.py` | hook | Gate-Verhalten, unverändert; `phase_listener.py` ruft `status_note` je Zug |
| `core/hooks/workflow.py` `auftrag_note_text` | function | Auftragssatz, bleibt unverändert |
| `tests/test_skills_sync.py` (62-136, 309-387) | test | pinnt Wortlaute des Blocks, bleibt unverändert grün |
| `tests/test_endzustand_550.py`, `tests/test_status_note_325.py`, `tests/test_spec_ampel_470.py` | test | pinnen Wortlaute des Hinweises und den Auto-Freigabe-Fall, unverändert grün |
| `tests/test_issue_number_513.py`, `tests/test_sitzungs_backlog_613_610.py`, `tests/test_auftrag_551.py` | test | Issue-Nummer und Auftragssatz im Hinweis |
| `docs/befehle/*.md` | doc | Muster für den Hintergrund-Ort (#674/#677/#678) |
| Epic #649, #674, #677, #678 | issue | Gesamtziel; Messung wie #580 |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| scripts/sync_skills.py | MODIFY | `marker_block` auf höchstens 1 200 Bytes, Verweis auf `docs/befehle/fusszeile.md` |
| core/hooks/workflow.py | MODIFY | `END_STATE_RULE` und `_status_note_base` auf höchstens 900 Bytes (Normalfall), Auto-Fall ebenfalls gekürzt |
| skills/*/SKILL.md | MODIFY | regeneriert per `python3 scripts/sync_skills.py` (15 Skills) |
| docs/befehle/fusszeile.md | CREATE | gestrichene Begründungen wörtlich, für Marker-Block und Hook-Hinweis |
| tests/test_marker_slim_679.py | CREATE | Größenwächter |
| CHANGELOG.md | MODIFY | Eintrag `[4.26.3]` |
| .claude-plugin/plugin.json | MODIFY | Version 4.26.3 (plus übliche Versionsmarker) |

### Estimated Changes

- Files: 2 Quelldateien, 1 neue Doku, 1 neuer Test, Generate, Versionsdateien
- LoC: Quelltext ca. −90/+40, Doku ca. +80, Test ca. +60
- Risk Level: HIGH (Hook-Code in `workflow.py`; zwei Adversary-Runden)

## Implementation Details

- **Marker-Block:** Es bleiben die Vorlage `❗ Du:` → `ℹ️ Status: Workflow \`<name>\` · Phase \`<x>\` von 8` → `⚙ /<name> · agent-os-openspec <version>` (⚙-Zeile wörtlich, am Zeilenanfang), die drei Formen ✅/⏳/❗ inkl. `‼️`, `workflow.py waiting`/`endstate`/`status`, „AM ENDE dieser Nachricht“, „Nächster Pflicht-Schritt“, die Verbotswörter vor phase8, die Regel zu frei formulierten Arbeitsstandsmeldungen und Übergabe-Blöcken sowie der Verweis auf `docs/befehle/fusszeile.md`. Die drei Begründungsabsätze (Turn-Beginn-Stand, Übergabe-Blöcke, Platzhalter) entfallen im Block und stehen wörtlich im Hintergrunddokument.
- **Hook-Hinweis:** Kopfzeile `[agent-os-openspec] AKTIVER WORKFLOW <name> · Phase N von 8 (<phase>) · Nächster Pflicht-Schritt: <schritt>` bleibt. `END_STATE_RULE` wird zur Kurzform der Drei-Formen-Regel mit `✅ Erledigt:`/`⏳ Läuft noch:`/`❗ Du:`, `workflow.py waiting`, „bei Bedarf“, „optional“, „fertig“, `phase8_complete`, `/clear`, Hinweis auf eigenen Phasenwechsel (neuer Stand gilt), Emoji-Zeilen nur wie vorgeschrieben. Auto-Freigabe-Fall (#470) bleibt ohne `❗`. Der Auftragssatz (`auftrag_note_text`) ändert sich nicht und zählt nicht zum 900-Bytes-Budget.
- **Hintergrund:** `docs/befehle/fusszeile.md` hat je einen Abschnitt für Marker-Block und Hook-Hinweis mit den gestrichenen Absätzen im Originalwortlaut.
- **Messung (vorher/nachher, Ergebnis als Kommentar an #649):** Byte-Werte beider Texte (Typfall `fix-1761-statusvermerk`, `phase7_validate`, Issue 1761) und zwei frische Cloud-Sitzungen (main gegen Branch, identischer Auftrag „Skill 90-retro laden, nichts ausführen“), Eingabe-Token des Modellaufrufs nach dem Skill-Laden.

Invarianten: kein Gate-Code (`footer_gate.py`, `phase_listener.py`, `expected_footer…`) geändert, keine Gate-Konfiguration, kein Override nötig, alle bestehenden Tests ohne Änderung ihrer Assertions grün.

## Expected Behavior

- **Input:** Aufruf eines Befehls (Skill-Laden) bzw. jede Nutzer-Nachricht bei aktivem Workflow
- **Output:** gleiche Fußzeilen-Pflichten aus kürzerem Text; Block höchstens 1 200 Bytes, Hinweis höchstens 900 Bytes
- **Side effects:** je Befehlsaufruf ca. −2 KB, je Zug mit aktivem Workflow ca. −1 KB; Hintergrund vollständig in `docs/befehle/fusszeile.md`

## Known Limitations

- Die Grundlast der ersten Anfrage ändert sich kaum (Skills sind beim Start nur als Beschreibung gelistet); die Wirkung zeigt sich je Befehlsaufruf und je Zug.
- `docs/befehle/` liegt im Plugin-Ordner und ist zur Ausführung nicht nötig.

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] Marker-Block höchstens 1,2 KB, Hook-Hinweis höchstens 900 Bytes, Messung vorher/nachher als Kommentar an #649
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf grün)
- [ ] CHANGELOG `[4.26.3]`, Version 4.26.3 überall, veröffentlicht

## Acceptance Criteria

- **AC-1:** Given `scripts/sync_skills.py` nach der Änderung / When `marker_block(name, version)` aufgerufen wird / Then ist das Ergebnis höchstens 1 200 Bytes (UTF-8) groß und enthält weiterhin alle Pflicht-Stichworte der bestehenden Tests: Vorlage `❗ Du:` vor `ℹ️ Status: Workflow \`<name>\` · Phase \`<x>\` von 8` vor `⚙ /<name> · agent-os-openspec <version>` (⚙-Zeile wörtlich, am Zeilenanfang), die drei Formen ✅/⏳/❗ inkl. `‼️`, `workflow.py waiting`/`endstate`/`status`, „AM ENDE dieser Nachricht“, „Nächster Pflicht-Schritt“, die Verbotswörter vor phase8, die Regel zu frei formulierten Arbeitsstandsmeldungen und Übergabe-Blöcken sowie der Verweis auf `docs/befehle/fusszeile.md`
  - Test: tests/test_marker_slim_679.py::test_marker_block_within_budget
  - Test: tests/test_skills_sync.py (bestehende Pin-Tests, unverändert)

- **AC-2:** Given das Repo nach der Änderung / When `docs/befehle/fusszeile.md` gelesen wird / Then existiert sie nach dem Muster `docs/befehle/*.md` und enthält die gestrichene Begründungsprosa wörtlich, getrennt für Marker-Block und Hook-Hinweis
  - Test: tests/test_marker_slim_679.py::test_fusszeile_doc_has_rationale

- **AC-3:** Given ein Workflow `fix-1761-statusvermerk` in `phase7_validate` mit Issue 1761 / When `workflow.status_note` den Normalfall ohne Auftragssatz liefert / Then ist der Hinweis höchstens 900 Bytes groß (heute 1 886) und enthält Kopfzeile `[agent-os-openspec] AKTIVER WORKFLOW <name> · Phase N von 8 (<phase>) · Nächster Pflicht-Schritt: <schritt>`, `✅ Erledigt:`, `⏳ Läuft noch:`, `❗ Du:`, `workflow.py waiting`, „bei Bedarf“, „optional“, „fertig“, `phase8_complete`, `/clear` und den Hinweis auf eigenen Phasenwechsel (neuer Stand gilt)
  - Test: tests/test_marker_slim_679.py::test_status_note_within_budget
  - Test: tests/test_status_note_325.py (bestehende Pins, unverändert)

- **AC-4:** Given der Auto-Freigabe-Fall (#470) und der Auftragssatz / When `status_note` aufgerufen wird / Then bleibt der Auto-Fall ohne `❗` und ist ebenfalls gekürzt, der manuelle Fall enthält `❗`, und `auftrag_note_text` ist unverändert
  - Test: tests/test_marker_slim_679.py::test_auto_note_without_du_and_shorter
  - Test: tests/test_spec_ampel_470.py, tests/test_auftrag_551.py (bestehend, unverändert)

- **AC-5:** Given die Änderung / When die Gesamtsuite läuft / Then sind `footer_gate.py`, `phase_listener.py` und die Erwartungswerte (`expected_footer…`) unverändert, und alle bestehenden Tests sind ohne Anpassung ihrer Assertions grün
  - Test: tests/ (Gesamtsuite), `git diff` ohne Änderung an `core/hooks/footer_gate.py` und `core/hooks/phase_listener.py`

- **AC-6:** Given `python3 scripts/sync_skills.py` wurde ausgeführt / When `skills/*/SKILL.md` gemessen wird / Then ist `skills/` insgesamt mindestens 30 000 Bytes (15 × 2 000) kleiner als vorher, und `sync_skills.py --check` meldet keine Drift
  - Test: tests/test_marker_slim_679.py::test_skills_shrunk_by_marker_cut
  - Test: tests/test_skills_sync.py (Drift-Prüfung)

- **AC-7:** Given der Größenwächter / When `pytest tests/test_marker_slim_679.py` läuft / Then prüft er Marker-Block höchstens 1 200 Bytes, Hinweis höchstens 900 Bytes und dass `docs/befehle/fusszeile.md` existiert und die Begründungen enthält
  - Test: tests/test_marker_slim_679.py

- **AC-8:** Given der Branch und `main` / When zwei frische Cloud-Sitzungen mit identischem Auftrag „Skill 90-retro laden, nichts ausführen“ laufen / Then liegen die Byte-Werte beider Texte vorher/nachher und die Eingabe-Token nach dem Skill-Laden als Kommentar an #649 vor
  - Test: Messung (manuell dokumentiert durch den Orchestrator, kein Produktcode); Byte-Anteil durch tests/test_marker_slim_679.py belegt

- **AC-9:** Given der Versions-Bump / When Versionsdateien und CHANGELOG geprüft werden / Then steht überall 4.26.3 und CHANGELOG hat einen `[4.26.3]`-Eintrag
  - Test: tests/ (Gesamtsuite; Versionsabgleich plugin.json/CHANGELOG/Marker über tests/test_skills_sync.py)

## Test Plan

### Automated Tests (TDD RED)

- [ ] Test 1: GIVEN der ungekürzte Marker-Block (3 259 Bytes) WHEN `pytest tests/test_marker_slim_679.py` läuft THEN scheitert `test_marker_block_within_budget` (RED)
- [ ] Test 2: GIVEN der ungekürzte Hinweis (1 886 Bytes) WHEN der Größenwächter läuft THEN scheitern `test_status_note_within_budget` und `test_fusszeile_doc_has_rationale` (RED)
- [ ] Test 3: GIVEN die gekürzten Texte und `docs/befehle/fusszeile.md` WHEN `pytest tests/` läuft THEN alles grün ohne `skip`/`xfail`, ohne geänderte Assertions bestehender Tests

Tests im venv mit `pytest` und `pyyaml`.

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Umverteilung von Anweisungstext wie #580/#674/#677/#678; keine neue Architektur, Gate-Verhalten unverändert.
- **Alternative A, Gate-Erwartung statt Text anpassen:** verworfen, Gate-Config ist tabu und Verhaltensrisiko.
- **Alternative B, gepinnte Wortlaute umschreiben und Tests lockern:** verworfen, Risiko für Gate-Verhalten.

## Changelog

- 2026-11-26: Erstfassung
