---
entity_id: fix-557-kontext-grundlast
type: bugfix
created: 2026-11-09
updated: 2026-11-09
status: draft
version: "1.0"
workflow: fix-557-kontext-grundlast
tags: [kontext, token, hooks, workflow, cloud]
---

# Kontext-Schwelle relativ zum Grundkontext (Issue #557)

## Approval

- [ ] Approved

## Purpose

In Cloud-Sitzungen liegt der Grundkontext (System-Prompt, Tool-Schemas, CLAUDE.md, MCP) direkt nach `/clear` schon bei etwa 100k Token. Die feste Schwelle `context_budget.clear_threshold_tokens` (100k) steht dort dauerhaft auf `CONTEXT_CUT=on`, und jede Phase hält für ein nutzloses `/clear` an. Diese Änderung misst die Schwelle relativ zum Grundkontext der Sitzung: Wachstum seit dem ersten Messwert zählt, nicht die absolute Größe. Lokal (Grundlast ca. 25k) bleibt praktisch alles beim Alten.

## Source

- **File:** `core/hooks/hook_utils.py`, `core/hooks/post_bash.py`, `core/hooks/workflow.py`
- **Identifier:** `record_context_usage`, `context_budget_settings`, `effective_context_threshold` (neu), `context_bucket`, `context_cut_note`, `post_bash._track_context`, `workflow.cmd_context`

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `hook_utils.record_context_usage` (~2584) | function | schreibt die Messung je Sitzung; bekommt das Feld `baseline_tokens` |
| `hook_utils.context_budget_settings` (~2509) | function | liefert `threshold`; neu `growth` aus `context_budget.growth_tokens` (Default 75000 im Code) |
| `hook_utils.context_bucket`, `context_cut_note` (~2638, ~2652) | function | Stufen und Hinweistext, bekommen die wirksame Schwelle |
| `post_bash._track_context` (~151) | function | misst, setzt Baseline, gibt Stufen-Hinweise aus |
| `workflow.cmd_context` (~3886) | function | Auskunft `CONTEXT_TOKENS`/`CONTEXT_CUT`, neu `CONTEXT_THRESHOLD` |
| `workflow.cmd_autoclear` (~3746) | function | nutzt die Schwelle nicht; bleibt unverändert |
| `workflow.auftrag_autark_open` (#551) | function | Autark-Vorrang bleibt unverändert |
| `docs/specs/feat-kontext-haushalt.md`, `docs/specs/feat-551-auftragsliste.md` | spec | Grundlage |
| `scripts/sync_skills.py` | tool | Skills nach Textänderung neu erzeugen |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| core/hooks/hook_utils.py | MODIFY | `baseline_tokens` in `record_context_usage` (Erstwert, Reset bei Abfall um mehr als 30 %, dabei `announced_bucket` auf 0); `growth` in `context_budget_settings`; neue `effective_context_threshold` |
| core/hooks/post_bash.py | MODIFY | `_track_context`: Stufen und Hinweis relativ zur wirksamen Schwelle |
| core/hooks/workflow.py | MODIFY | `cmd_context`: wirksame Schwelle, neue Zeile `CONTEXT_THRESHOLD=` |
| tests/test_kontext_grundlast_557.py | CREATE | Regressionstests zu allen AC |
| tests/test_kontext_haushalt.py | MODIFY | Stufentest: erster Messwert unter der Schwelle (sonst wird er Baseline) |
| README.md, core/commands/10-context.md bis 50-implement.md | MODIFY | Doku/Wortlaut „wirksame Schwelle“; Skills per `sync_skills.py` neu |
| CHANGELOG.md | MODIFY | Eintrag unter [Unreleased], kein Versions-Bump |

Nicht geändert: Repo-`config.yaml` (Config-Schutz; Default im Code, Doku in README/Spec), `cmd_autoclear`, `herdr_bridge.py`.

### Estimated Changes

- Files: 1 neu, 4 Produktions-/Testdateien geändert, Doku
- LoC: ca. +50/-10 Produktion, +130 Test
- Risk Level: LOW-MEDIUM (Kern-Hooks, reine Auskunft ohne Gate-Wirkung)

## Implementation Details

1. **Baseline (`record_context_usage`).** Die Messdatei bekommt `baseline_tokens`. Fehlt es in der vorigen Messung (neue Sitzung oder alte Datei), ist der aktuelle Wert die Baseline. Liegt der neue Wert mehr als 30 % unter dem vorigen (`tokens < 0.7 * previous_tokens`, Zeichen für `/clear` oder `/compact`), wird `baseline_tokens` auf den neuen Wert gesetzt und `announced_bucket` auf 0 zurückgesetzt. Sonst bleibt die Baseline erhalten.
2. **Wachstumsbudget (`context_budget_settings`).** Neuer Schlüssel `context_budget.growth_tokens` (int >= 1000, sonst Default `CONTEXT_BUDGET_DEFAULT_GROWTH = 75000`); Rückgabe um `growth` ergänzt, `threshold` bleibt der Basiswert.
3. **Wirksame Schwelle (`effective_context_threshold`).** `max(threshold, baseline_tokens + growth)`; ist die Baseline None oder kein int (alte Datei), gilt nur `threshold`.
4. **post_bash.** `_track_context` aktualisiert zuerst Messung und Baseline, bildet dann `context_bucket(tokens, wirksam)` und `context_cut_note(tokens, wirksam, ...)`; Hinweis einmal je Stufe, danach je 50k über der wirksamen Schwelle.
5. **`workflow.py context`.** `CONTEXT_CUT=on`, wenn `context_budget` an und `tokens >= wirksame Schwelle`; neue Zeile `CONTEXT_THRESHOLD=<wirksam>` (nach `CONTEXT_CUT`). Autark (#551, `CONTEXT_REASON=AUTARK`) bleibt vorrangig `off`. Kill-Switch `context_budget.enabled: false` unverändert.
6. **Doku.** README-Abschnitt Kontext-Haushalt, Befehlstexte (kein festes „Default 100.000“ mehr), CHANGELOG; danach `python3 scripts/sync_skills.py`.

## Expected Behavior

- **Input:** Messdatei `.claude/context_usage/<session>.json`, `context_budget`-Config, Aufrufe `post_bash.py` und `workflow.py context`
- **Output:** `CONTEXT_CUT=on` erst, wenn der Kontext die wirksame Schwelle `max(100000, Baseline + 75000)` erreicht; `CONTEXT_THRESHOLD=<wirksam>` nennt sie
- **Side effects:** Feld `baseline_tokens` in der Messdatei; kein neues Gate, keine Config-Änderung im Repo

## Known Limitations

- Der erste Messwert gilt als Grundkontext; startet die Messung erst spät (Resume mit großem Kontext), liegt die Baseline höher und die Schwelle später. Der nächste `/clear`/`/compact` (Abfall über 30 %) korrigiert das.
- Ein `/compact`, das weniger als 30 % einspart, setzt die Baseline nicht zurück.
- Reine Anzeige: ob Claude bei `on` anhält, erzwingt kein Hook.

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] Eine Cloud-Sitzung mit 100k Grundkontext meldet `CONTEXT_CUT=off`, bis der Kontext um das Wachstumsbudget gewachsen ist
- [ ] Lokale Sitzungen (ca. 25k Grundlast) behalten die Schwelle 100k
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf grün, `skills/` ohne Drift)

## Acceptance Criteria

- **AC-1:** Given eine neue Sitzung ohne Messdatei / When `post_bash.py` den ersten Messwert (z. B. 100.000) verarbeitet / Then enthält `.claude/context_usage/<session>.json` `baseline_tokens` = 100000, und spätere Messwerte im Bereich ab 70 % des vorigen lassen die Baseline unverändert
  - Test: tests/test_kontext_grundlast_557.py::test_first_measurement_sets_baseline

- **AC-2:** Given eine Sitzung mit Messwert 180.000 und Baseline 100.000 / When der nächste Messwert mehr als 30 % tiefer liegt (z. B. 40.000) / Then wird `baseline_tokens` = 40000 und `announced_bucket` = 0; ein Rückgang um höchstens 30 % (z. B. 180.000 auf 130.000) setzt die Baseline nicht zurück
  - Test: tests/test_kontext_grundlast_557.py::test_baseline_resets_on_drop_over_30_percent

- **AC-3:** Given `context_budget` mit Default-Werten / When die wirksame Schwelle berechnet wird / Then gilt `max(clear_threshold_tokens, baseline_tokens + growth_tokens)` mit `growth_tokens` = 75000 als Default im Code; ein gültiger Config-Wert `growth_tokens` (int >= 1000) überschreibt ihn, ein ungültiger (Text, Zahl unter 1000) fällt auf 75000 zurück
  - Test: tests/test_kontext_grundlast_557.py::test_effective_threshold_formula_default_and_override

- **AC-4:** Given ein Cloud-Szenario mit Baseline 100.000 / When `workflow.py context` bei 100.000, 150.000 und 174.999 Token läuft / Then lautet `CONTEXT_CUT=off`, und bei 175.000 sowie 200.000 `CONTEXT_CUT=on`
  - Test: tests/test_kontext_grundlast_557.py::test_cloud_scenario_cut_on_only_after_growth

- **AC-5:** Given ein lokales Szenario mit Baseline 25.000 / When `workflow.py context` bei 99.999 und 100.000 Token läuft / Then lautet `CONTEXT_CUT` `off` bzw. `on` (Schwelle bleibt 100.000, da 25.000 + 75.000 nicht darüber liegt)
  - Test: tests/test_kontext_grundlast_557.py::test_local_scenario_threshold_stays_100k

- **AC-6:** Given eine Messdatei mit Baseline / When `workflow.py context` läuft / Then enthält die Ausgabe eine Zeile `CONTEXT_THRESHOLD=<wirksame Schwelle>` (z. B. `CONTEXT_THRESHOLD=175000` bei Baseline 100.000, `CONTEXT_THRESHOLD=100000` bei Baseline 25.000) neben `CONTEXT_TOKENS=` und `CONTEXT_CUT=`
  - Test: tests/test_kontext_grundlast_557.py::test_context_prints_effective_threshold_line

- **AC-7:** Given Baseline 100.000 (wirksame Schwelle 175.000) / When `post_bash.py` bei 120.000, 175.000, 180.000 und 225.000 Token läuft / Then erscheint der Hinweis `KONTEXT-SCHWELLE` (mit der wirksamen Schwelle im Text) erstmals bei 175.000, nicht erneut bei 180.000 und wieder bei 225.000 (je 50k über der wirksamen Schwelle)
  - Test: tests/test_kontext_grundlast_557.py::test_post_bash_buckets_relative_to_effective_threshold

- **AC-8:** Given eine Messdatei ohne `baseline_tokens` (alte Fassung) / When `workflow.py context` läuft / Then gilt nur die absolute Schwelle wie bisher (`CONTEXT_THRESHOLD=100000`, `on` ab 100.000), ohne Fehler
  - Test: tests/test_kontext_grundlast_557.py::test_old_usage_file_without_baseline_behaves_as_before

- **AC-9:** Given ein offener autarker Auftrag (#551) bzw. `context_budget.enabled: false` / When `workflow.py context` und `post_bash.py` über der wirksamen Schwelle laufen / Then bleibt es unverändert: Autark ergibt `CONTEXT_CUT=off` plus `CONTEXT_REASON=AUTARK` (Hinweis im Autark-Wortlaut), der Kill-Switch ergibt `off` ohne Hinweis und ohne Messdatei
  - Test: tests/test_kontext_grundlast_557.py::test_autark_and_kill_switch_unchanged

## Test Plan

Automatische Tests (jeweils an eine AC oben gebunden, ohne Netzwerk, Messdatei und Config per `tmp_path`, Transcripts als synthetische JSONL):
- `pytest tests/test_kontext_grundlast_557.py` (RED zuerst, dann GREEN)
- Bestandstests: `pytest tests/test_kontext_haushalt.py tests/test_kette_auto_clear_489.py tests/test_autoclear_boundary_495.py tests/test_autoclear_transition_497.py tests/test_autoclear_eigene_signale_506.py tests/test_auftrag_551.py`
- Regressionslauf: `pytest tests/`
- `python3 -m py_compile core/hooks/hook_utils.py core/hooks/post_bash.py core/hooks/workflow.py`
- `python3 scripts/sync_skills.py --check`

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Die absolute Schwelle ignoriert den Grundkontext, der in Cloud-Sitzungen bereits ~100k beträgt. Eine Schwelle relativ zum ersten Messwert (mit Reset bei `/clear`/`/compact`) misst, was die Sitzung selbst anhäuft, und lässt lokal die bewährten 100k bestehen (`max`). Alternativen: Cloud-Erkennung per Umgebungsvariable (fragil, deckt MCP-Größe nicht ab) oder dauerhaft höhere Schwelle (verliert den Spareffekt lokal). Default im Code statt in `config.yaml` (Config-Schutz); rein additiv, fail-open, ohne Gate-Wirkung, reversibel durch Entfernen des Feldes (Baseline None = altes Verhalten).

## Changelog

- 2026-11-09: Initial spec created
