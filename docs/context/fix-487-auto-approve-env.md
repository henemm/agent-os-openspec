# Context: fix-487-auto-approve-env

## Request Summary
PO: grünes Briefing, `workflow.py autonomy` = `auto` (über `OPENSPEC_AUTONOMY`, #481), trotzdem verlangt die Sitzung `approved`.

## Related Files
| File | Relevance |
|------|-----------|
| `core/hooks/workflow.py` | `_auto_approve_decision()` (Z. ~2905) liest `trusted_config()["autonomy"]["mode"]` direkt statt `autonomy_mode()` → Env-Schalter wirkungslos |
| `tests/test_spec_ampel_470.py` | bestehende auto-approve-Tests |
| `tests/test_autonomy_global_481.py` | Env-Schalter-Tests (decken auto-approve nicht ab) |

## Analysis
- Fix: Modusprüfung über `autonomy_mode()`; `trusted_config()` bleibt Quelle für Gate-Einstellungen (ADR/Briefing).
- Tests: Ende-zu-Ende `auto-approve` mit Env-Schalter; Architekturtest: `autonomy`-`mode` wird nur in `autonomy_mode()` gelesen.
- Risk LOW (zwei Zeilen, Verhalten nur bei gesetztem Env-Schalter anders).
