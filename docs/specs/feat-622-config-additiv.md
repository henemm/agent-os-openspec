---
entity_id: feat-622-config-additiv
type: feature
created: 2026-11-21
updated: 2026-11-21
status: draft
version: "1.0"
workflow: feat-622-config-additiv
tags: [gate, config-schutz, autark, issue-622]
---

# Anzeige-Abschnitte der wirksamen Config ohne Override ändern; Planungshinweis für autarke Aufträge

## Approval

- [ ] Approved

## Purpose

Issue #622 („Autarker Auftrag darf nie auf ein PO-„override“ hinauslaufen (Config-Schutz und Planung)“): Ein autarker Auftrag läuft bis zum Ende ohne override, solange keine echte Schutzfunktion gelockert wird. Anlass war #620, wo ein neuer Anzeige-Abschnitt `time_estimate` in der wirksamen `config.yaml` den Config-Schutz (#473) auslöste, obwohl er kein Gate berührt. Diese Änderung lässt reine Anzeige-Abschnitte ohne Override zu und weist die Planung an, Gate-Config-Änderungen bei autarken Aufträgen zu vermeiden.

**Bewusste Präzisierung gegenüber dem Issue:** Das Issue sagt „neuer, gate-fremder Abschnitt“. „Gate-fremd“ wird hier nicht als „beliebiger neuer Abschnitt“ umgesetzt, sondern als feste Liste `DISPLAY_ONLY_CONFIG_KEYS = ("next_suggestion", "time_estimate")`. Grund: Ein beliebiger neuer Abschnitt (etwa `adversary_coverage_gate: {enabled: false}`) könnte ein Gate abschalten; ob ein Schlüssel „gate-fremd“ ist, lässt sich nicht aus dem Namen erraten. `herdr`, `autonomy`, `auftrag` und `context_budget` stehen zwar in `PLUGIN_CONFIG_KEYS`, wirken aber auf Abläufe (Auto-/clear, Autonomie, Auto-Kette, Kontext-Schnitt) und gehören deshalb nicht in die Liste.

## Source

- **File:** `core/hooks/edit_gate.py`, `core/hooks/config_loader.py`
- **Identifier:** `edit_gate._config_edit_hit` (Prüfung 0a), `config_loader.DISPLAY_ONLY_CONFIG_KEYS`, `config_loader.display_only_change`

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `config_loader.find_config_file` | function | bestimmt die wirksame Config; Ausnahme gilt nur für genau diese Datei |
| `config_loader.protected_config_paths` | function | Pfadmenge des Config-Schutzes (#473), bleibt unverändert |
| `config_loader.is_plugin_config_text` | function | Erkennung des Plugin-Blocks, bleibt unverändert |
| `edit_gate._simulate_spec_write` | function | liefert alte und neue Fassung(en) für Write/Edit/MultiEdit, fail-closed bei Zweifel |
| `override_token` | module | Ausweg für alle weiterhin geschützten Änderungen |
| `bash_gate._writes_effective_config` | function | Bash-Schutz, bleibt unverändert |
| PyYAML | library | YAML lesen; strenger Loader erkennt doppelte Schlüssel |
| `scripts/sync_skills.py` | script | erzeugt `skills/*/SKILL.md` aus den Befehlstexten |
| `tests/test_config_edit_schutz_473.py` | test | Muster für Hilfsfunktionen; bleibt grün |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| `core/hooks/config_loader.py` | MODIFY | `DISPLAY_ONLY_CONFIG_KEYS` und pure Funktion `display_only_change(old_text, new_text) -> bool` mit strengem YAML-Loader |
| `core/hooks/edit_gate.py` | MODIFY | Prüfung 0a: Treffer auf die wirksame Config entfällt, wenn jede neue Fassung nur Anzeige-Abschnitte ändert |
| `core/commands/00-intake.md` | MODIFY | Planungshinweis für autarke Aufträge |
| `core/commands/30-write-spec.md` | MODIFY | gleicher Planungshinweis bei der Spec-Erstellung |
| `skills/00-intake/SKILL.md` | MODIFY | Generat (`python3 scripts/sync_skills.py`), nie von Hand |
| `skills/30-write-spec/SKILL.md` | MODIFY | Generat (`python3 scripts/sync_skills.py`), nie von Hand |
| `tests/test_config_additiv_622.py` | CREATE | alle Tests dieser Spec |
| `CHANGELOG.md` | MODIFY | Eintrag unter `[Unreleased]` |

### Estimated Changes

- Files: 8 (4 Quelldateien, 2 Generate, Tests, CHANGELOG)
- LoC: +90 Produktiv/Text, +150 Tests, -0

Der Schnitt liegt über der Faustregel von 4–5 Dateien, weil zwei Dateien reine Generate sind; handgeschrieben sind 4 Quelldateien plus Tests.

## Implementation Details

Regel: Ein Edit/Write/MultiEdit auf die **wirksame** Config (Datei existiert und ist `find_config_file(root)`) löst keinen Treffer aus, wenn alle folgenden Punkte gelten:

1. Alte und jede neue Fassung sind als YAML-Mapping lesbar, und zwar mit einem strengen Loader, der doppelte Schlüssel (auch verschachtelt) ablehnt.
2. Jeder Top-Level-Schlüssel außerhalb von `DISPLAY_ONLY_CONFIG_KEYS` ist in alter und neuer Fassung vorhanden und hat einen gleichen Wert.
3. Schlüssel aus `DISPLAY_ONLY_CONFIG_KEYS` dürfen dazukommen, sich ändern oder wegfallen. Kommentare und Formatierung zählen nicht.

`display_only_change` ist pur (nur Texte rein, Wahrheitswert raus) und gibt bei jedem Fehler `False` zurück. Das heißt: Zweifel führt wie bisher zum Treffer (fail-closed).

`edit_gate.py` ruft die Funktion in Prüfung 0a erst auf, nachdem die bestehende Trefferlogik die wirksame Config erkannt hat, und nur für Edit/Write/MultiEdit. Die Fassungen kommen aus `_simulate_spec_write`; liefert diese nichts (Größe, Anzahl Edits, Zeitlimit, nicht anwendbarer Edit), bleibt es beim Treffer.

Unverändert geschützt bleiben: Bash-Schreibzugriffe (kein prüfbarer Inhalt), `~/.claude/settings*.json`, jede nicht wirksame Config-Datei und das Anlegen einer vorrangigen Config. Der Override-Token wirkt wie bisher.

Planungshinweis (Wortlaut sinngemäß in beiden Befehlstexten): Bei einem autarken Auftrag keine Schritte einplanen, die eine menschliche Sperre (Override) brauchen. Änderungen an der wirksamen Gate-Config vermeiden, wenn eingebaute Standardwerte oder ein anderer Weg genügen; reine Anzeige-Abschnitte (`next_suggestion`, `time_estimate`) sind davon ausgenommen.

**Alternativen (verworfen):**

- „Jeder neue Top-Level-Schlüssel ist erlaubt“: ein neu eingefügter `adversary_coverage_gate: {enabled: false}` schaltete ein Gate ab.
- Override für autarke Aufträge automatisch ausstellen: hebelt den Schutz vollständig aus.

## Expected Behavior

- **Input:** Write, Edit oder MultiEdit auf die wirksame `config.yaml` im Projekt.
- **Output:** Nur Anzeige-Abschnitte betroffen: erlaubt ohne Token. Sonst: blockiert wie bisher, Ausweg „override“.
- **Side effects:** keine; die Funktion `display_only_change` ist pur. Befehlstexte und Generate tragen den Planungshinweis.

## Known Limitations

- Die Liste `DISPLAY_ONLY_CONFIG_KEYS` ist fest; ein weiterer Anzeige-Abschnitt braucht eine Codeänderung samt Test.
- Bash-Schreibzugriffe auf die Config bleiben geschützt, auch wenn sie nur einen Anzeige-Abschnitt ändern; Inhalt ist dort nicht prüfbar.
- In Cloud-Sitzungen (Arbeit im Haupt-Checkout) bleibt jede andere Config-Änderung override-pflichtig; der Planungshinweis soll sie vermeiden, kann sie nicht ausschließen.
- Ein Ändern innerhalb eines Anzeige-Abschnitts wird nicht inhaltlich bewertet; die Liste enthält nur Abschnitte, die keinen Ablauf steuern.

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] Ein autarker Auftrag kann einen Anzeige-Abschnitt (`time_estimate`, `next_suggestion`) in der wirksamen Config ergänzen, ändern oder entfernen, ohne dass jemand „override“ tippen muss
- [ ] Wer einen Gate-Schalter ändert, entfernt oder einschmuggelt, braucht weiterhin „override“
- [ ] `/00-intake` und `/30-write-spec` (samt `skills/`) enthalten den Planungshinweis, `scripts/sync_skills.py` meldet keine Drift
- [ ] `CHANGELOG.md` trägt den Eintrag unter `[Unreleased]`
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf grün, insbesondere #473, #481, #372, #418)

## Acceptance Criteria

- **AC-1:** Given die wirksame `config.yaml` mit Plugin-Block und ohne Override-Token / When ein Write einen neuen Abschnitt `time_estimate` hinzufügt und alle anderen Schlüssel gleich lässt / Then lässt `edit_gate.py` den Schreibzugriff ohne Token zu
  - Test: tests/test_config_additiv_622.py::test_write_neuer_anzeige_abschnitt_erlaubt
- **AC-2:** Given die wirksame `config.yaml` mit Abschnitten `time_estimate` und `next_suggestion` / When ein Edit den Wert in einem dieser Abschnitte ändert oder ein MultiEdit einen davon entfernt / Then wird der Zugriff ohne Token zugelassen
  - Test: tests/test_config_additiv_622.py::test_edit_und_multiedit_aendern_entfernen_anzeige_abschnitt_erlaubt
- **AC-3:** Given die wirksame `config.yaml` / When ein Edit einen bestehenden Gate-Schlüssel ändert (etwa `adversary_coverage_gate.enabled` von true auf false) / Then blockiert `edit_gate.py` weiterhin und nennt „override“ als Ausweg
  - Test: tests/test_config_additiv_622.py::test_gate_schluessel_aendern_blockiert
- **AC-4:** Given die wirksame `config.yaml` / When ein Write einen bestehenden Gate-Abschnitt entfernt oder einen neuen Abschnitt außerhalb der Anzeige-Liste einfügt (etwa `adversary_coverage_gate: {enabled: false}`) / Then wird weiterhin blockiert
  - Test: tests/test_config_additiv_622.py::test_gate_schluessel_entfernen_oder_neu_einfuegen_blockiert
- **AC-5:** Given die wirksame `config.yaml` / When die neue Fassung Anzeige-Abschnitte ändert, aber einen Schlüssel doppelt enthält oder als YAML unlesbar ist / Then wird weiterhin blockiert (fail-closed)
  - Test: tests/test_config_additiv_622.py::test_doppelte_schluessel_und_unlesbares_yaml_blockiert
- **AC-6:** Given eine App-`config.yaml` ohne Plugin-Block, die nicht die wirksame Config ist, oder keine vorhandene wirksame Config / When ein Write einen Anzeige-Abschnitt dort hinzufügt oder eine vorrangige Config neu anlegt / Then wird weiterhin blockiert
  - Test: tests/test_config_additiv_622.py::test_app_config_ohne_plugin_block_und_anlegen_vorrangiger_config_blockiert
- **AC-7:** Given die wirksame `config.yaml` / When ein Bash-Aufruf einen Anzeige-Abschnitt per Schreibumleitung hinzufügt / Then blockiert `bash_gate.py` unverändert ohne Token
  - Test: tests/test_config_additiv_622.py::test_bash_schreibzugriff_bleibt_blockiert
- **AC-8:** Given ein gültiger Override-Token und die wirksame `config.yaml` / When ein Gate-Schlüssel geändert wird / Then wird der Zugriff wie bisher zugelassen
  - Test: tests/test_config_additiv_622.py::test_override_wirkt_weiter
- **AC-9:** Given die Befehlstexte `00-intake` und `30-write-spec` samt den erzeugten `skills/` / When ein autarker Auftrag geplant wird / Then enthalten beide Texte den Hinweis, keine Schritte einzuplanen, die einen Override brauchen, und die Skills stimmen mit den Quellen überein (kein Sync-Drift)
  - Test: tests/test_config_additiv_622.py::test_planungshinweis_in_befehlstexten_und_skills_ohne_drift

## Test Plan

Automatische Tests in `tests/test_config_additiv_622.py` (Subprozess-Aufruf des Gates mit JSON, Muster aus `tests/test_config_edit_schutz_473.py`), jeweils an eine AC gebunden:

### Automated Tests (TDD RED)

- [ ] GIVEN wirksame Config WHEN Write fügt `time_estimate` hinzu THEN erlaubt (AC-1)
- [ ] GIVEN Config mit Anzeige-Abschnitten WHEN Edit ändert bzw. MultiEdit entfernt einen THEN erlaubt (AC-2)
- [ ] GIVEN Gate-Schlüssel WHEN Edit ändert `enabled` THEN blockiert (AC-3)
- [ ] GIVEN Gate-Abschnitt WHEN Write entfernt ihn oder fügt neuen Nicht-Anzeige-Abschnitt ein THEN blockiert (AC-4)
- [ ] GIVEN Anzeige-Änderung WHEN doppelter Schlüssel oder kaputtes YAML THEN blockiert (AC-5)
- [ ] GIVEN App-Config ohne Plugin-Block bzw. fehlende wirksame Config WHEN Anzeige-Abschnitt oder vorrangige Config angelegt THEN blockiert (AC-6)
- [ ] GIVEN wirksame Config WHEN Bash schreibt Anzeige-Abschnitt THEN blockiert (AC-7)
- [ ] GIVEN Override-Token WHEN Gate-Schlüssel geändert THEN erlaubt (AC-8)
- [ ] GIVEN Befehlstexte und Skills WHEN gelesen und `sync_skills.py --check` läuft THEN Hinweis vorhanden, kein Drift (AC-9)
- [ ] Unit: `display_only_change` ist pur und gibt bei jedem Fehler `False` zurück

Ablauf: Tests zuerst schreiben, im venv mit `pytest` ausführen, Ausgabe nach `docs/artifacts/622-red.log` schreiben und als RED-Artefakt registrieren (`workflow.py add-artifact test_output docs/artifacts/622-red.log "..." phase5_tdd_red`, danach `mark-red`). Erst dann Implementierung bis GRÜN. Zusätzlich Regressionslauf: `pytest tests/test_config_edit_schutz_473.py` und die Tests zu #481, #372, #418.

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Es ist eine enge Lockerung innerhalb des bestehenden Config-Schutzes (#473) mit fester Liste und fail-closed-Verhalten; es entsteht keine neue Entscheidungsfläche. Die verworfenen Alternativen (jeder neue Schlüssel erlaubt, automatischer Override) sind oben begründet und widersprechen dem Schutzziel, daher kein ADR nötig.

## Changelog

- 2026-11-21: Initial spec created (Issue #622)
