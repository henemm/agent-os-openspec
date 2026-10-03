---
entity_id: feat-250-teil-a1-intake-einziger-eingang
type: module
created: 2026-10-03
updated: 2026-10-03
status: draft
version: "1.0"
tags: [intake, bug, anweisungstext, "#250"]
---

# /00-intake wird der einzige Eingang — auch für Bugs (#250, Teil A, Stufe A1)

## Approval

- [ ] Approved

## Purpose

Heute gibt es zwei Eingänge: `/00-intake` (Score, zwei Stufen) und `/00-bug` (Analyse, danach
optional ein Bug-Schnellweg `--type bug` ohne Spec, ohne TDD-Rot, ohne Gegenprüfung, mit „Manuell
testen"). Der Schnellweg spart nur Nachweise, nicht Zeit (Archiv: Typ `bug` Median 91 min,
`feature-fast` Median 20 min). Diese Änderung führt den Bug-Inhalt in `/00-intake` zusammen, damit jede
Aufgabe — Bug oder Feature — denselben Weg und dieselben Nachweise bekommt.

## Source

- **File:** `core/commands/00-intake.md`, `core/commands/00-bug.md`
- **Identifier:** Befehlstext (Anweisung an Claude, kein Hook-Code)

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `scripts/sync_skills.py` | Script | erzeugt `skills/00-intake/SKILL.md` und `skills/00-bug/SKILL.md` aus `core/commands/` |
| `core/commands/20-analyse.md` Step 2b | Befehl | enthält die ausführliche Bug-Analyse (`bug-intake`); der Intake verweist darauf, kopiert sie nicht |
| `tests/test_skills_sync.py` | Test | verlangt, dass jede Befehlsdatei klassifiziert ist → `00-bug.md` bleibt bestehen |
| `tests/test_intake_two_tracks_254.py` | Test | Vorbild für String-Präsenz-Tests; darf nicht rot werden (genau zwei `--type`-Startblöcke in `00-intake.md`) |

## Scope

- **Affected Files:** `core/commands/00-intake.md`, `core/commands/00-bug.md`,
  `skills/00-intake/SKILL.md` und `skills/00-bug/SKILL.md` (generiert), `tests/test_intake_bugs_250a1.py` (neu),
  `tests/test_skill_path_resolution.py`, `README.md`, `CLAUDE.md`, `setup.py`, `docs/WORKFLOW_GUIDE.md`,
  `CHANGELOG.md`
- **Estimated Changes:** ca. +70 / −85 LoC; 6 der 11 Dateien sind Einzeiler in Tabellen oder generiert.
  Kein Hook-Code, kein State-Format, kein Typ `bug` entfernt (das ist A2, eigenes Ticket).

## Implementation Details

1. **`00-intake.md`** bekommt einen Abschnitt „Bugs" **vor** dem Scoring (nach „Aufgabe verstehen"):
   - Bei einem Fehlerbericht zuerst Duplikatsuche (`gh issue list --label bug` / `--search`); Duplikat →
     bestehendes Issue verwenden.
   - Fehler **nachstellen** und die Ursache mit `file:line` belegen. Die ausführliche Vorgehensweise steht
     in `/20-analyse` Step 2b; der Intake verweist darauf und kopiert sie nicht.
   - Das Ergebnis speist das Scoring: Ursache bekannt und ≤3 Dateien → Unsicherheit **Low**; Ursache
     unklar → Unsicherheit mindestens Medium.
   - STOP-Bedingungen: Ursache unklar, nicht reproduzierbar, mehrere mögliche Ursachen, Fix > 5 Dateien.
   - Es gibt keinen eigenen Bug-Typ und keinen „Manuell testen"-Schritt: der Nachweis ist ein Test, der den
     Fehler vorher rot zeigt. Danach gilt dieselbe Wahl `feature-fast` / `feature` wie für alles andere.
2. **`00-bug.md`** wird ein Hinweis von höchstens 15 Zeilen: „Bugs laufen über `/00-intake`", mit
   Verweis auf den Abschnitt „Bugs". Der Fast-Track-Block mit `--type bug` und „Manuell testen"
   entfällt vollständig. Der Text enthält weder `workflow.py` noch `--type bug`.
3. **Generierte Skills:** `python3 scripts/sync_skills.py`, nie von Hand. Weil `00-bug` kein `workflow.py`
   mehr aufruft, verliert `skills/00-bug/SKILL.md` den Hook-Setup-Snippet (15 → 14 Skills mit Snippet).
4. **`tests/test_skill_path_resolution.py`:** Zähler 15 → 14 (Test e) und die Liste der Skills ohne Snippet
   `["01-feature"]` → `["00-bug", "01-feature"]` (Test e2); Kommentar entsprechend.
5. **Doku-Einzeiler:** `README.md`, `CLAUDE.md`, `setup.py`, `docs/WORKFLOW_GUIDE.md` — Zeile „Bug-Analyse"
   wird zu „Hinweis auf `/00-intake`". `CHANGELOG.md` unter `[Unreleased]`.

## Expected Behavior

- **Input:** Ein Fehlerbericht ruft `/00-intake` (oder die Gewohnheit `/00-bug`).
- **Output:** `/00-intake` fordert Duplikatsuche, Nachstellen und Ursachenbeleg, bewertet danach mit dem
  normalen Score und führt in `feature-fast` oder `feature`. `/00-bug` verweist nur noch dorthin.
- **Side effects:** `workflow.py start --type bug` wird von keinem Befehl mehr aufgerufen. Die Hooks
  akzeptieren den Typ weiterhin (Altbestand im Archiv bleibt lesbar) bis A2.

## Known Limitations

- Die Hooks kennen den Typ `bug` weiter (`edit_gate`, `bash_gate`, `workflow`, `adversary_dialog`);
  Entfernung ist A2.
- Die Wirkung ist eine Anweisung an Claude; sie wird durch Text-Tests belegt, nicht durch einen Hook erzwungen.
- `docs/specs/bug-fix-fast-track.md` beschreibt den überholten Schnellweg; sie bleibt als Historie unverändert.

## Alternativen (und was sie kippen würden)

1. **`/00-bug` ganz löschen:** sauberster Einstieg, bricht aber Kurz-Alias, Wiedereinstiegs-Test und
   Gewohnheit. Nicht jetzt; möglich nach A2.
2. **Bug-Analyse nur in `/20-analyse` Step 2b belassen:** kein Textduplikat, aber der Intake bewertet ohne
   Ursachenkenntnis — genau die Fehleinstufung, die A1 beheben soll. Gewählt wird die kurze Fassung im Intake
   mit Verweis auf Step 2b.
3. **Bug-Schnellweg behalten, aber mit Gegenprüfung:** würde die Entscheidung aus
   `docs/specs/bug-fix-fast-track.md` erhalten. Verworfen: der Weg ist im Archiv nicht schneller, und die
   dritte Stufe wurde mit #254 gerade entfernt.

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] Wer `/00-intake` mit einem Fehlerbericht aufruft, wird zur Duplikatsuche, zum Nachstellen und zum
      Ursachenbeleg geführt, bevor bewertet wird; `/00-bug` verweist nur noch dorthin
- [ ] Kein Befehlstext nennt mehr einen Bug-Schnellweg oder „Manuell testen"
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf grün)

## Acceptance Criteria

- **AC-1:** Given `core/commands/00-intake.md` / When der Text gelesen wird / Then enthält er einen
  Abschnitt „Bugs", der Duplikatsuche (`gh issue list`), Nachstellen, Ursachenbeleg (`file:line`),
  STOP-Bedingungen und den Verweis auf `/20-analyse` Step 2b nennt, und dieser Abschnitt steht vor
  „### 2. Score präsentieren"
  - Test: `tests/test_intake_bugs_250a1.py::test_intake_has_bug_section_before_scoring`
- **AC-2:** Given der Intake-Text / When das Scoring beschrieben wird / Then gilt „Ursache bekannt, ≤3 Dateien"
  als Unsicherheit Low
  - Test: `tests/test_intake_bugs_250a1.py::test_known_cause_means_low_uncertainty`
- **AC-3:** Given `00-intake.md` / When die Startblöcke gezählt werden / Then bleiben es genau zwei
  (`feature`, `feature-fast`), und kein `--type bug` kommt vor
  - Test: `tests/test_intake_bugs_250a1.py::test_no_bug_type_and_two_start_blocks`
- **AC-4:** Given `core/commands/00-bug.md` / When der Text gelesen wird / Then verweist er auf `/00-intake`,
  hat höchstens 15 Zeilen und enthält weder `--type bug`, `workflow.py` noch „Manuell testen"
  - Test: `tests/test_intake_bugs_250a1.py::test_00_bug_is_only_a_pointer`
- **AC-5:** Given alle Befehls- und Skill-Dateien / When nach „Manuell testen" und `--type bug` gesucht wird
  / Then kommt keines von beiden in `core/commands/` oder `skills/` vor
  - Test: `tests/test_intake_bugs_250a1.py::test_no_bug_fast_track_left_in_commands_or_skills`
- **AC-6:** Given die generierten Skills / When `sync_skills.py --check` läuft / Then gibt es keinen Drift
  - Test: `tests/test_intake_bugs_250a1.py::test_generated_skills_are_in_sync`
- **AC-7:** Given `skills/` / When Skills mit Hook-Setup-Snippet gezählt werden / Then sind es 14, und genau
  `00-bug` und `01-feature` haben keinen
  - Test: `tests/test_skill_path_resolution.py::test_e_all_skills_share_identical_snippet` und
    `::test_e2_non_hook_skills_have_no_snippet`
- **AC-8:** Given README, CLAUDE.md, setup.py und WORKFLOW_GUIDE / When `/00-bug` beschrieben wird / Then
  nicht mehr als „Bug-Analyse"-Einstieg, sondern als Hinweis auf `/00-intake`
  - Test: `tests/test_intake_bugs_250a1.py::test_docs_describe_00_bug_as_pointer`

> Die Test-Zuordnung wird **bei der Spec-Erstellung** eingetragen, nicht nachträglich:
> Nach der Freigabe ist diese Datei eingefroren (#230) — jede Änderung verschiebt den
> PO-Briefing-Hash und blockt den Workflow-Abschluss. Stimmt der Testname später nicht
> mehr, gehört die Korrektur in die TDD-RED-Artefakte (`workflow.py add-artifact`),
> nicht in diese Datei.

## Test Plan

Automatische Tests (jeweils an eine AC oben gebunden):
- `pytest tests/test_intake_bugs_250a1.py` (AC-1 bis AC-6, AC-8)
- `pytest tests/test_skill_path_resolution.py` (AC-7)
- Regression: `pytest tests/test_intake_two_tracks_254.py tests/test_skills_sync.py tests/test_wakeup_blocks.py`

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Reiner Anweisungstext ohne neue Struktur. Er kippt die Entscheidung aus
  `docs/specs/bug-fix-fast-track.md` (eigener Bug-Schnellweg); die Hooks bleiben bis A2 unverändert.

## Changelog

- 2026-10-03: Initial spec created
