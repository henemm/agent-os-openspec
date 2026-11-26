---
entity_id: docs-674-commands-slim
type: refactor
created: 2026-11-26
updated: 2026-11-26
status: draft
version: "1.0"
workflow: docs-674-commands-slim
tags: [token, befehle, docs, epic-649]
---

# Befehlstexte verschlanken, Schnitt 1 (Issue #674)

## Approval

- [ ] Approved

## Purpose

Der Befehlstext einer Phase wird bei jedem Aufruf vollständig geladen. Schnitt 1 kürzt die beiden größten Befehle, `60-validate.md` (27 481 Bytes) und `50-implement.md` (21 324 Bytes). Begründungen, Historie und Sonderfall-Erläuterungen wandern wörtlich nach `docs/befehle/50-implement.md` bzw. `docs/befehle/60-validate.md`. Das Gesamtziel von −40 % über alle Befehlstexte wird mit #677 und #678 erreicht, weil die Umfangsgrenze (250 Zeilen je Workflow) nicht mehr in einem Schnitt zulässt. #679 übernimmt den Marker-Block und die Hook-Hinweise.

## Source

- **File:** `core/commands/50-implement.md`, `core/commands/60-validate.md`, neu `docs/befehle/50-implement.md`, `docs/befehle/60-validate.md`
- **Identifier:** Abschnitte der beiden Befehlstexte

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `scripts/sync_skills.py` | script | erzeugt `skills/*/SKILL.md` aus `core/commands`; `--check` weist Drift nach |
| `scripts/release_check.py` | script | prüft Skill-Drift und Versionsstände |
| Pin-Tests (u. a. `test_foreground_checkers_83`, `test_cloud_agents_577`, `test_auto_green_471`, `test_context_stop_658`, `test_adversary_protokoll_format_278`, `test_precondition_section_gate`, `test_nachpruefung_broken_561`, `test_auto_ship_525/528/530`, `test_autonomy_kette_472`, `test_endzustand_550`, `test_skills_sync`) | test | pinnen Wortlaute in 50/60; müssen unverändert grün bleiben |
| `docs/architektur.md`, `docs/arbeitsweise.md` | doc | enthalten Adversary-, Gate- und Kontext-Haushalt-Wissen; Dubletten können entfallen bzw. verweisen |
| `core/hooks/hook_utils.py` | hook | stuft `core/commands/*.md` als niedriges Adversary-Risiko ein; bleibt unberührt |
| `tests/test_claude_md_slim_580.py` | test | Vorbild für den Größenwächter |
| Epic #649, Folge-Issues #677, #678, #679 | issue | Restschnitt, Gesamtziel, Marker-Block |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| core/commands/50-implement.md | MODIFY | auf höchstens 15 360 Bytes kürzen, Verweis-Satz auf `docs/befehle/50-implement.md` |
| core/commands/60-validate.md | MODIFY | auf höchstens 20 480 Bytes kürzen, Verweis-Satz auf `docs/befehle/60-validate.md`; Abschnitt „Auto-Modus prüfen“ unverändert |
| docs/befehle/50-implement.md | CREATE | verschobene Begründungen und Sonderfälle, wörtlich |
| docs/befehle/60-validate.md | CREATE | verschobene Begründungen und Sonderfälle, wörtlich |
| tests/test_commands_slim_674.py | CREATE | Größenwächter mit Budget-Tabelle, Verweis- und Drift-Prüfung |
| skills/50-implement/SKILL.md, skills/60-validate/SKILL.md | MODIFY | per `sync_skills.py` regeneriert |
| CHANGELOG.md, .claude-plugin/plugin.json, CLAUDE.md, README.md, Versionsmarker | MODIFY | Version 4.25.5 (Marker per sync) |

### Estimated Changes

- Files: 2 Befehle, 2 neue Doku, 1 neuer Test, 2 Generate, Versionsdateien
- LoC: Befehle ca. -150/+40, Doku ca. +170, Test ca. +60 (unter 250 Produktivzeilen)
- Risk Level: LOW (nur Anweisungstext, Doku, Tests; kein Hook-Code)

## Implementation Details

Abschnittsweise Vorgehen in beiden Befehlen. Es bleiben der Ablauf, alle Agent-Aufrufe, `workflow.py`-Befehle, Ausgabe-Blöcke und jeder von bestehenden Tests gepinnte Wortlaut. Reine Begründungen, Historie (Issue-Verweise wie #58, #83, #183, #253, #259, #289, #577, #589, #610) und Sonderfall-Erläuterungen wandern wörtlich in die gleichnamigen Abschnitte von `docs/befehle/<befehl>.md`. Im Befehl steht dafür ein Satz: „Hintergrund: `docs/befehle/<befehl>.md` (Plugin-Ordner)“.

Bei 50-implement entfallen aus dem Befehl: Rollentabelle, Circuit-Breaker-Erläuterung, „200k ≈ 5×“ und die Begründungen der genannten Issues. Bei 60-validate entfallen: Phase-7-Absätze, #83-Begründung, „Warum spec_file_path“, Epic-Details und Erläuterungen zu Step 2 und 4. „Auto-Modus prüfen“ (rund 7 KB, weitgehend gepinnt) bleibt unverändert.

Größenwächter `tests/test_commands_slim_674.py`: eine Budget-Tabelle je Datei in `core/commands/`. 50-implement und 60-validate erhalten die neuen Budgets; jede andere Datei erhält die heutige Größe aufgerundet auf volle 512 Bytes. Das verhindert Wachstum und wird in #677 und #678 gesenkt. Ein Befehl ohne Tabelleneintrag lässt den Test scheitern.

Messung: Bytes und geschätzte Token (Bytes/3,5) der geladenen Skill-Texte vorher/nachher je Phase; `CONTEXT_TOKENS` dieser Sitzung wird in Epic #649 festgehalten.

Invarianten: kein Hook- und kein Gate-Code geändert, keine Änderung an der Gate-Konfiguration, kein Schritt braucht einen Override.

## Expected Behavior

- **Input:** Aufruf von `/50-implement` oder `/60-validate`
- **Output:** gleicher Ablauf und gleiche Pflichtschritte wie bisher, aus einem kürzeren Text (50-implement ≤ 15 360 Bytes, 60-validate ≤ 20 480 Bytes)
- **Side effects:** geringere Last beim Laden der beiden Phasen; Hintergrundwissen vollständig in `docs/befehle/`

## Known Limitations

- Ersparnis rund −30 % je Datei statt −40 %, weil viele Wortlaute von Tests gepinnt sind; das Gesamtziel erreichen #677 und #678.
- Die Wirkung tritt erst beim Laden der jeweiligen Phase ein.
- `docs/befehle/` liegt im Plugin-Ordner, nicht im Konsumentenprojekt; der Hintergrund ist zur Ausführung nicht nötig.

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] 50-implement.md ≤ 15 360 Bytes und 60-validate.md ≤ 20 480 Bytes, verschobener Text vollständig in `docs/befehle/`
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf grün, `skills/` ohne Drift)
- [ ] CHANGELOG `[4.25.5]`, Version 4.25.5 überall, veröffentlicht
- [ ] Messung vorher/nachher (Bytes, geschätzte Token je Phase) und `CONTEXT_TOKENS` in Epic #649 festgehalten

## Acceptance Criteria

- **AC-1:** Given das Repo nach der Änderung / When die Größe von `core/commands/50-implement.md` gemessen wird / Then beträgt sie höchstens 15 360 Bytes
  - Test: tests/test_commands_slim_674.py::test_implement_within_budget

- **AC-2:** Given das Repo nach der Änderung / When die Größe von `core/commands/60-validate.md` gemessen wird / Then beträgt sie höchstens 20 480 Bytes
  - Test: tests/test_commands_slim_674.py::test_validate_within_budget

- **AC-3:** Given alle Dateien in `core/commands/` / When die Budget-Tabelle des Tests geprüft wird / Then hat jeder Befehlstext ein Budget und hält es ein, und ein Befehl ohne Budget lässt den Test scheitern
  - Test: tests/test_commands_slim_674.py::test_every_command_has_budget

- **AC-4:** Given `50-implement.md` und `60-validate.md` / When nach dem Verweis gesucht wird / Then nennen sie ihre Datei `docs/befehle/<befehl>.md`, und diese existiert mit mindestens 3 `##`-Abschnitten
  - Test: tests/test_commands_slim_674.py::test_commands_link_background_docs

- **AC-5:** Given `skills/50-implement/SKILL.md` und `skills/60-validate/SKILL.md` / When `sync_skills.py --check` läuft und der Text geprüft wird / Then gibt es keine Drift, und beide Skills tragen den Verweis auf ihre `docs/befehle`-Datei ebenfalls
  - Test: tests/test_commands_slim_674.py::test_skills_carry_link

- **AC-6:** Given die bestehenden Pin-Tests auf Wortlaute in 50/60 / When die Gesamtsuite läuft / Then bleibt sie grün, ohne `skip`/`xfail`
  - Test: tests/ (Gesamtsuite)

## Test Plan

- `pytest tests/test_commands_slim_674.py` (RED zuerst, dann GREEN)
- Pin-Tests aus der Dependencies-Tabelle einzeln, danach Regressionslauf `pytest tests/` (im venv mit `pytest` und `pyyaml`)
- `python3 scripts/sync_skills.py --check`
- Messung: Bytes und geschätzte Token (Bytes/3,5) der geladenen Skill-Texte je Phase vorher/nachher; Ergebnis und `CONTEXT_TOKENS` dieser Sitzung als Kommentar an Epic #649

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Reine Umverteilung von Anweisungstext und Dokumentation; keine neue Entscheidungsfläche, Vorgehen wie bei #580.
- **Alternative A, Kürzen ohne Verschieben:** verworfen, das Wissen ginge verloren.
- **Alternative B, alles in einem PR:** verworfen, die Umfangsgrenze (250 Zeilen je Workflow) lässt das nicht zu.
- **Alternative C, Abschnitt „Auto-Modus prüfen“ umschreiben und Tests anpassen:** verworfen, Risiko für das Auslieferungsverhalten.

## Changelog

- 2026-11-26: Erstfassung
