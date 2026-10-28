# Context: feat-469-autonomie-schalter

## Request Summary
Teil A von #468: Schalter `autonomy.mode` und Freigabe-Protokoll `approvals`. Kein Verhaltenswechsel — Grundlage für B (#470), C (#471), D (#472).
Gesamtanalyse, Gate-Inventar und PO-Entscheidungen: `docs/context/feat-468-autonomie-modus.md`.

## Related Files
| File | Relevance |
|------|-----------|
| `config.yaml` | neuer Abschnitt `autonomy: mode: manual` |
| `core/hooks/config_loader.py:40` | `PLUGIN_CONFIG_KEYS` (+ `autonomy`) |
| `scripts/ci_spec_gate.py:95` | `_FALLBACK_PLUGIN_KEYS` — Kopie, Drift-Test `tests/test_app_config_yaml_372.py` |
| `core/hooks/workflow.py:560` | `_new_workflow` (+ `approvals: []`) |
| `core/hooks/workflow.py:1332` | `cmd_status` (Anzeige der Einträge) |
| `core/hooks/workflow.py:1433` | `_SET_FIELD_PROTECTED` (+ `approvals`) |
| `core/hooks/workflow.py:2305` | `cmd_observable_surface` — Vorbild für Statuszeilen-Ausgabe `KEY=wert`, Exit 0 |
| `core/hooks/workflow.py:2383` | `COMMANDS` (+ `autonomy`) |

## Analysis
- Modus nur über `config_loader.load_config()` (Haupt-Repo-Config + settings.local.json); nur Literal `"auto"` (getrimmt? nein — exakt) schaltet an, alles andere/Fehler → `manual`
- Hilfsfunktion `autonomy_mode() -> "auto"|"manual"` in `workflow.py` (B/C/D und post_implementation_gate importieren sie)
- `workflow.py autonomy` druckt `AUTONOMY=<mode>`, Exit 0 auch bei Fehler
- Hilfsfunktion `record_approval(data, gate, by, reason, evidence)` hängt an `approvals` an (mode = aktueller Modus, at = ISO-Zeit); wird erst von B/C genutzt, hier mit Tests
- `approvals` überlebt Rücksprünge (`_reset_approvals_on_backstep` unverändert), ist per `set-field` gesperrt
- `status` zeigt Anzahl bzw. Einträge
- Risiko gering; Tests nach Muster `tests/test_app_config_yaml_372.py`, Workflow-CLI-Tests als Subprozess
