# Context: feat-622-config-additiv

## Request Summary
Ein autarker Auftrag darf nicht an einem PO-„override“ hängen bleiben (Anlass #620: neuer
Anzeige-Abschnitt `time_estimate` in der wirksamen `config.yaml`). Harmlose Config-Änderungen
sollen ohne Override gehen, echte Schutzschalter bleiben geschützt; die Planung soll solche
Sperren bei autarken Aufträgen meiden.

## Related Files
| File | Relevance |
|------|-----------|
| `core/hooks/edit_gate.py` 0a: `_config_edit_hit` (~643-693), Aufruf in `main` (~930-947) | blockt Edit/Write auf die wirksame Config ohne Token; hier kommt die Ausnahme hinein |
| `core/hooks/edit_gate.py` `_simulate_spec_write` (~459-487), `_CONFIG_MAX_BYTES`, `_CONFIG_MAX_EDITS`, `_sim_deadline` | liefert (alt, [neue Fassungen]) für Write/Edit/MultiEdit, fail-closed bei Zweifel |
| `core/hooks/config_loader.py` `PLUGIN_CONFIG_KEYS` (40-51), `protected_config_paths` (175), `find_config_file`, `is_plugin_config_text` | Pfadmenge und Plugin-Erkennung; Ort für die Liste reiner Anzeige-Abschnitte |
| `core/hooks/bash_gate.py` 1b (`_writes_effective_config` 665-694, Block 1871-1881) | Bash-Schreibzugriffe ohne prüfbaren Inhalt → bleibt unverändert geschützt |
| `core/commands/00-intake.md` 1a (74-97) | erwähnt den autarken Auftrag; Ort für den Planungshinweis |
| `core/commands/30-write-spec.md` | kein Autark-Bezug; Hinweis vor/bei der Spec-Erstellung |
| `tests/test_config_edit_schutz_473.py` | Muster: `_proj`, `_gate` (Subprozess mit JSON), `_write`/`_edit`/`_multi`, Token-Helfer |

## Existing Patterns
- Config-Schutz #473: Pfadmenge `protected_config_paths`, Inhaltsprüfung nur für die Root-`config.yaml` (#372), fail-closed bei nicht prüfbarer Simulation, Ausweg nur Override.
- Worktree-Kopie der Config ist frei (wirkt erst nach Merge); Cloud-Sitzungen arbeiten aber im Haupt-Checkout → dort trifft der Schutz jede Config-Änderung.
- Duplikat-Schlüssel-Abwehr nur für JSON (`_no_duplicate_keys`, edit_gate ~494-500); PyYAML `safe_load` nimmt still den letzten Wert.

## Dependencies
- Upstream: `config_loader`, PyYAML, `_simulate_spec_write`, `override_token`.
- Downstream: alle Gates, die die wirksame Config lesen; Tests #473/#481/#372/#418.

## Risks & Considerations
- `herdr`, `autonomy`, `auftrag`, `context_budget` stehen in `PLUGIN_CONFIG_KEYS`, wirken aber auf Abläufe (Auto-/clear, Autonomie, Auto-Kette, Kontext-Schnitt) → nicht auf die Anzeige-Liste.
- Eine App-`config.yaml` ohne Plugin-Block würde durch einen Anzeige-Schlüssel zur wirksamen Config und verdrängte eine nachrangige → Ausnahme nur für die bereits wirksame Datei.
- Doppelte YAML-Schlüssel könnten einen Schutzschalter verdecken → strenger Loader.
- Bash bleibt geschützt (kein Inhalt prüfbar).

## Analysis

### Type
Feature (Gate-Lockerung mit enger Grenze + Befehlstext)

### Affected Files (with changes)
| File | Change Type | Description |
|------|-------------|-------------|
| `core/hooks/config_loader.py` | MODIFY | `DISPLAY_ONLY_CONFIG_KEYS = ("next_suggestion", "time_estimate")`, pure `display_only_change(old_text, new_text) -> bool` (strenger YAML-Loader ohne Duplikate) |
| `core/hooks/edit_gate.py` | MODIFY | 0a: Treffer auf die wirksame Config, deren alle Fassungen nur Anzeige-Abschnitte ändern → kein Treffer |
| `core/commands/00-intake.md`, `core/commands/30-write-spec.md` | MODIFY | Planungshinweis für autarke Aufträge |
| `skills/00-intake/SKILL.md`, `skills/30-write-spec/SKILL.md` | MODIFY | Generat (`scripts/sync_skills.py`) |
| `tests/test_config_additiv_622.py` | CREATE | Tests |
| `CHANGELOG.md` | MODIFY | `[Unreleased]` |

### Scope Assessment
- Files: 4 Quelldateien + 2 Generate + Tests + CHANGELOG
- Estimated LoC: +90 Produktiv/Text, +150 Tests
- Risk Level: HIGH (Gate-Code)

### Technical Approach
- Regel: Ein Edit/Write auf die **wirksame** Config (Datei existiert, ist `find_config_file(root)`) braucht kein Override, wenn alte und jede neue Fassung als YAML-Mapping ohne doppelte Schlüssel lesbar sind und jeder Top-Level-Schlüssel außerhalb von `DISPLAY_ONLY_CONFIG_KEYS` in beiden Fassungen gleich vorhanden und gleich im Wert ist. Anzeige-Abschnitte dürfen dazukommen, sich ändern oder wegfallen; Kommentare zählen nicht.
- Alles andere bleibt wie bisher (Treffer → Override), ebenso Anlegen vorrangiger Configs, Bash-Schreibzugriffe und `~/.claude/settings*.json`. Jeder Fehler/Zweifel → wie bisher Treffer (fail-closed).
- Planungshinweis: Bei autarkem Auftrag keine Schritte einplanen, die eine menschliche Sperre (Override) brauchen, wenn eingebaute Standardwerte oder ein anderer Weg genügen.

### Alternativen
- Allgemein „neue Top-Level-Schlüssel erlaubt“ → verworfen: ein neu eingefügter `adversary_coverage_gate: {enabled: false}` schaltete ein Gate ab.
- Override für autarke Aufträge automatisch ausstellen → verworfen: hebelt den Schutz vollständig aus.

### Open Questions
- keine
