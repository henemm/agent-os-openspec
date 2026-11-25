---
entity_id: fix-665-config-kommentare
type: bugfix
created: 2026-11-25
updated: 2026-11-25
status: draft
version: "1.0"
workflow: fix-665-config-kommentare
tags: [config, kommentare, herdr, kontext, epic-649]
---

# config.yaml: veraltete Kommentare zu herdr.auto_clear und CONTEXT_CUT (Issue #665)

## Approval

- [ ] Approved

## Purpose

Die Kommentare in `config.yaml` beschreiben zwei Dinge falsch: Auto-/clear per Herdr (`herdr.auto_clear`, `OPENSPEC_HERDR_AUTO_CLEAR`) gilt dort noch als wirksam, obwohl #663 es entfernt hat; und der Abschnitt `context_budget` sagt, bei `CONTEXT_CUT=on` hielten die Phasen-Befehle an und der PO oder Herdr tippe `/clear`. Seit #658/#662 hält die Kette nur bei `CONTEXT_STOP=on` (Modus `manual`), und Herdr tippt nichts. Wer die Config liest, wird in die Irre geführt.

## Source

- Issue #665 (Folge von #658, #662, #663)
- `config.yaml` Abschnitte `context_budget` und `herdr`
- `core/hooks/herdr_bridge.py` Modul-Docstring (Stand nach #663: Schlüssel werden nicht mehr gelesen)

## Dependencies

- `core/hooks/config_loader.py::display_only_change` — reine Kommentaränderungen ändern die geladene Config nicht und brauchen deshalb keinen Override (#622)

## Scope

### Affected Files

| Datei | Änderung |
|---|---|
| `config.yaml` | Nur Kommentare in `context_budget` und `herdr` |
| `tests/test_config_kommentare_665.py` | Neu: pinnt die neuen Kommentare und die unveränderten Werte |
| `CHANGELOG.md`, `.claude-plugin/plugin.json`, `CLAUDE.md`, `README.md` | Version 4.25.1 |

### Estimated Changes

ca. 30 Zeilen Kommentar, ca. 60 Zeilen Test.

## Implementation Details

- `context_budget`-Kommentar: `CONTEXT_CUT=on` ist nur der Messfakt; angehalten wird bei `CONTEXT_STOP=on` (nur Modus `manual`); im Auto-Modus läuft die Kette weiter; Herdr tippt nichts.
- `herdr`-Kommentar zu `auto_clear`: wirkungslos seit #663 (4.24.0), wird von keinem Code gelesen, ebenso `OPENSPEC_HERDR_AUTO_CLEAR`; Werte bleiben nur stehen, weil das Streichen eines Schlüssels die wirksame Gate-Config ändert (Override-Pflicht, #622). Die Inline-Kommentare der Unterschlüssel werden auf „wirkungslos“ gekürzt.
- Die geladenen Werte (YAML-Daten) bleiben exakt gleich.

## Expected Behavior

- Nach der Änderung liefert `yaml.safe_load(config.yaml)` dasselbe Ergebnis wie vorher.
- Kein Kommentar in `config.yaml` beschreibt Auto-/clear als wirksam oder `CONTEXT_CUT=on` als Haltesignal.

## Known Limitations

- Der Schlüssel `herdr.auto_clear` bleibt als toter Eintrag stehen; Entfernen erst bei einem ohnehin nötigen Eingriff in die Gate-Config.

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] Die geladene Config ist unverändert (`display_only_change` gegen `origin/main` wahr)
- [ ] Regressionslauf `pytest tests/` grün, CHANGELOG und Version 4.25.1 veröffentlicht

## Acceptance Criteria

- **AC-1:** Given `config.yaml` vor und nach der Änderung / When beide mit `yaml.safe_load` geladen werden / Then sind die Daten gleich, insbesondere `context_budget` und `herdr`
  - Test: tests/test_config_kommentare_665.py::test_loaded_config_unchanged

- **AC-2:** Given die Kommentare des Abschnitts `context_budget` / When sie gelesen werden / Then nennen sie `CONTEXT_STOP=on` als Haltesignal und enthalten nicht mehr „(oder Herdr) tippt /clear“
  - Test: tests/test_config_kommentare_665.py::test_context_budget_comment_names_context_stop

- **AC-3:** Given die Kommentare des Abschnitts `herdr` / When sie gelesen werden / Then markieren sie `auto_clear` und `OPENSPEC_HERDR_AUTO_CLEAR` als wirkungslos (#663) und enthalten keine Beschreibung mehr, dass ein Runner `/clear` tippt
  - Test: tests/test_config_kommentare_665.py::test_herdr_comment_marks_auto_clear_dead

## Test Plan

- GIVEN Config-Text von `origin/main` (Fixture-Kopie der Werte) WHEN geladen THEN gleiche Werte (AC-1)
- GIVEN Kommentarblock vor `context_budget:` WHEN gelesen THEN `CONTEXT_STOP=on`, kein „tippt /clear“ (AC-2)
- GIVEN Kommentare im Abschnitt `herdr` WHEN gelesen THEN „wirkungslos“ und „#663“, kein „tippt ein detachter Runner“ (AC-3)

Läufe: `pytest tests/test_config_kommentare_665.py`, Regressionslauf `pytest tests/`.

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Reine Doku-Korrektur in Kommentaren; die wirksamen Werte bleiben gleich, deshalb kein Override und keine Migration für Konsumenten.
- **Alternative A, Schlüssel `herdr.auto_clear` streichen:** verworfen für diesen autarken Auftrag, weil es die wirksame Gate-Config ändert und einen Override (menschlichen Halt) braucht (#622); der Nutzen (ein toter Block weniger) rechtfertigt den Halt nicht.

## Changelog

- 2026-11-25: Initial spec created
