---
entity_id: fix-598-autoclear-kontextschnitt
type: bugfix
created: 2026-11-25
updated: 2026-11-25
status: draft
workflow: fix-598-autoclear-kontextschnitt
version: "1.0"
tags: [herdr, auto-clear, kontext-haushalt, stop-hook]
test_targets: ["tests/test_autoclear_kontextschnitt_598.py"]
---

# Auto-/clear greift auch beim Kontext-Schnitt mitten in der Phase — #598

## Approval

- [ ] Approved

## GitHub Issue

- **Issue:** #598. Überbrückung bis Epic #649 (Auto-/clear wird dort ganz zurückgebaut); bewusst klein gehalten.

## Purpose

Endet eine Sitzung im Herdr-Pane mit Auto-/clear mitten in einer Phase, weil die Kontext-Schwelle erreicht ist (`workflow.py context` → `CONTEXT_CUT=on`), nennt die Fußzeile `❗ Du: /clear, dann /50-implement #N`, aber Auto-/clear startet nicht: der Stop-Hook verlangt den Grenz-Vermerk `auto_clear_boundary`, und den setzen nur Phasenwechsel aus `AUTO_CLEAR_BOUNDARIES` oder `workflow.py autoclear`. Letzteres ruft das Modell beim Kontext-Schnitt nicht auf. Belegt in henemm-infra #515 (`phase6_implement`, zweimal am 25.11.2026: 151128 bzw. 149699 Token bei Grundlast ~69k, wirksame Schwelle ~144k; Log `skip: keine Grenze vermerkt`). Die Grenze wird jetzt mechanisch im Stop-Hook erkannt statt vom Modell.

## Source

- **File:** `core/hooks/herdr_bridge.py` — `maybe_auto_clear` (Grenz-Prüfung), neu `_context_cut_active`, `_record_context_cut_boundary`
- **File:** `core/hooks/workflow.py` — `_record_auto_clear_boundary(name=None)` gibt den geschriebenen Vermerk zurück und schreibt mit `name` genau diesen Workflow
- **Vorbild:** `cmd_context` (Bedingung für `CONTEXT_CUT=on`, #557, #551)

## Dependencies

- `hook_utils.context_budget_settings`, `effective_context_threshold`, `read_context_usage(..., fallback_newest=False)`, `auftrag_autark_open`
- Stop-Hook `footer_gate.py` ruft `maybe_auto_clear` unverändert nur auf dem Pfad „Fußzeile korrekt“

## Scope

### Affected Files

- `core/hooks/herdr_bridge.py`
- `core/hooks/workflow.py`
- `tests/test_autoclear_kontextschnitt_598.py` (neu)

### Estimated Changes

Rund 80 Zeilen Code, ein neuer Testfile.

## Implementation Details

In `maybe_auto_clear` gilt nach allen bisherigen Vorprüfungen (Slash-Befehl, kein `/clear`, nicht `MANUAL_COMMANDS`, Fußzeile nennt den erwarteten Befehl):

1. Kein Vermerk und kein Kontext-Schnitt → wie bisher `skip: keine Grenze vermerkt`.
2. Klartext-Vorprüfung (#597) wie bisher; bei Treffer Skip ohne Schreiben.
3. Kein Vermerk, aber Kontext-Schnitt aktiv: Negativ-Marker → `skip: Negativmarker` ohne Schreiben; sonst `workflow._record_auto_clear_boundary(name)` für den übergebenen Workflow (aktuelle Phase, `expected_footer_command`, frischer Zeitstempel) und den Vermerk in `data` spiegeln.
4. Danach der normale Pfad unverändert (Match, Frische, Spawn mit `boundary_at`, Runner nimmt den Vermerk vor dem Tippen).

Kontext-Schnitt aktiv = `context_budget` eingeschaltet, Messung genau der stoppenden Sitzung (`session_id` aus dem Payload, ohne Rückgriff auf die jüngste fremde Messung) ≥ `effective_context_threshold`, kein autarker Auftrag offen. Fail-open: jede Ausnahme = nicht aktiv.

## Expected Behavior

- **Input:** Stop-Payload mit `session_id`, `last_assistant_message`; Workflow-State ohne Vermerk; Messdatei `.claude/context_usage/<session_id>.json`.
- **Output:** Bei aktivem Kontext-Schnitt und passender Fußzeile wird der Runner gestartet und tippt `/clear` und den Folgebefehl; sonst kein Spawn und kein Vermerk.
- **Side effects:** Vermerk `auto_clear_boundary` im Workflow-State (wie `workflow.py autoclear`); Skip-Gründe im bestehenden Log.

## Known Limitations

- Ohne Messdatei der Sitzung (z. B. `context_budget` erst nachträglich eingeschaltet, noch kein Bash-Aufruf seit Start) bleibt es beim Modell-Aufruf von `workflow.py autoclear`.
- Liegt die Messung noch knapp unter der Schwelle, die Sitzung bricht aber trotzdem ab, greift Auto-/clear nicht (die Fußzeile allein ist kein Auslöser).
- Der Rückbau von Auto-/clear (Epic #649) ersetzt diese Brücke.

## Definition of Done

- Mitten in einer Phase startet Auto-/clear beim Kontext-Schnitt ohne Modell-Aufruf, wenn die Fußzeile den erwarteten Befehl nennt.
- Alle bestehenden Schutzregeln (Fußzeile, `MANUAL_COMMANDS`, `/clear`, Klartext, Negativ-Marker, Runner-Aktivitätsprüfung, autarker Auftrag) gelten unverändert.
- Neue Tests und die Gesamtsuite grün; Version 4.21.1 ausgeliefert und auf dem Server installiert.

## Acceptance Criteria

- **AC-1:** Given kein Grenz-Vermerk und die Messung der Sitzung über der wirksamen Schwelle / When die Antwort mit `❗ Du: /clear, dann /50-implement #N` endet / Then startet der Runner, der Vermerk für Phase und Befehl steht im State und ist nach dem Tippen verbraucht
  - Test: `tests/test_autoclear_kontextschnitt_598.py::test_context_cut_without_boundary_spawns_runner`, `::test_context_cut_records_boundary_before_spawn`
- **AC-2:** Given kein Vermerk und die Messung unter der Schwelle, fehlend oder nur für eine andere Sitzung vorhanden / When der Stop-Hook läuft / Then `skip: keine Grenze vermerkt`, kein Spawn, kein Vermerk
  - Test: `::test_below_threshold_keeps_old_behaviour`, `::test_other_sessions_measurement_does_not_count`
- **AC-3:** Given Kontext über der Schwelle / When die Fußzeile den erwarteten Befehl nicht nennt („Client secret kopieren“, „⏳ Läuft noch“) / Then kein Spawn und kein Vermerk
  - Test: `::test_footer_without_command_never_triggers`
- **AC-4:** Given Kontext über der Schwelle und ein offener autarker Auftrag / When der Stop-Hook läuft / Then kein Spawn und kein Vermerk
  - Test: `::test_autark_auftrag_blocks`
- **AC-5:** Given Kontext über der Schwelle und `context_budget.enabled: false` / When der Stop-Hook läuft / Then kein Spawn und kein Vermerk
  - Test: `::test_context_budget_disabled_blocks`
- **AC-6:** Given Kontext über der Schwelle / When die Klartext-Prüfung die Antwort zurückweist oder der Negativ-Marker steht / Then der passende Skip-Grund im Log und kein Vermerk im State
  - Test: `::test_klartext_hit_writes_no_boundary`, `::test_negative_marker_writes_no_boundary`

## Test Plan

- `pytest tests/test_autoclear_kontextschnitt_598.py` — Subprozess-Tests gegen das echte `footer_gate.py` mit Stub-Herdr, Scaffold `Case` aus `tests/test_autoclear_retry_597.py`, Messdatei und `context_budget`-Config je Fall. RED vor der Änderung: AC-1 und AC-6 rot (`skip: keine Grenze vermerkt`).
- Regression: alle Auto-/clear-Tests (#467, #480, #489, #495, #497, #506, #597), danach die Vollsuite.

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Nutzt die bestehende Grenz-Mechanik (#495/#597) unverändert und nur eine zusätzliche Quelle für den Vermerk; dieselbe Bedingung wie `workflow.py context`. Kein neuer Hook, keine neue Abhängigkeit.
- **Verworfene Alternativen:**
  - *Befehlstexte verpflichten das Modell, `workflow.py autoclear` beim Kontext-Schnitt aufzurufen:* hängt weiter am Modell, genau das ist der Befund.
  - *Fußzeile `/clear, dann …` allein als Auslöser:* ohne Messung nicht prüfbar, öffnet Fehlauslösungen.

## Changelog

- 2026-11-25: Initial spec created (#598)
- Release-Hinweis: CHANGELOG `[4.21.1]`
