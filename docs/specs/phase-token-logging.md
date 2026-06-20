---
entity_id: phase_token_logging
type: feature
created: 2026-06-20
updated: 2026-06-20
status: draft
version: "1.0"
tags: [workflow, observability, token-efficiency]
test_targets:
  - core/hooks/phase_listener.py
  - core/hooks/workflow.py
---

# Phase-Token-Logging

## Approval

- [ ] Approved

## GitHub Issue

- **Issue:** (noch nicht erstellt)

## Purpose

Jeden Phasenwechsel mit einem ISO-Timestamp im Workflow-JSON protokollieren.
Zeit pro Phase ist ein verlässlicher Proxy für Token-Verbrauch (mehr Tokens →
längere Phase). `workflow.py phase-log` zeigt eine Zusammenfassung, mit der
erkennbar wird welche Phasen unverhältnismäßig viel kosten.

Claude Code selbst zeigt keinen Per-Phase-Token-Verbrauch — dieses Feature
schließt die Lücke ohne API-Zugriff oder externe Infrastruktur zu benötigen.

## Abhängigkeiten

| Komponente | Typ | Abhängigkeit |
|-----------|-----|-------------|
| `phase_listener.py` | Hook | Schreibt `phase_log` bei jedem Phasenwechsel |
| `workflow.py` | CLI | Neuer Subcommand `phase-log` |

## Implementierungsdetails

### 1. Datenstruktur im Workflow-JSON

`phase_log` wird als Array in die Workflow-JSON geschrieben. Jeder Eintrag
repräsentiert eine Phase-Transition:

```json
{
  "name": "FEAT-007",
  "current_phase": "phase6_implement",
  "phase_log": [
    {
      "phase": "phase1_context",
      "entered_at": "2026-06-20T09:00:00",
      "exited_at": "2026-06-20T09:14:32",
      "duration_min": 14.5
    },
    {
      "phase": "phase2_analyse",
      "entered_at": "2026-06-20T09:14:32",
      "exited_at": "2026-06-20T09:28:10",
      "duration_min": 13.6
    },
    {
      "phase": "phase6_implement",
      "entered_at": "2026-06-20T09:28:10",
      "exited_at": null,
      "duration_min": null
    }
  ]
}
```

`duration_min` wird beim Verlassen einer Phase berechnet (= `exited_at - entered_at`).
`exited_at` und `duration_min` bleiben `null` für die aktive Phase.

### 2. `phase_listener.py` — `_log_phase_transition()`

Neue Hilfsfunktion, die bei jedem `wf_data["current_phase"] = new_phase` aufgerufen wird:

```python
def _log_phase_transition(wf_data: dict, new_phase: str) -> None:
    now = datetime.now().isoformat()
    log = wf_data.setdefault("phase_log", [])

    # Letzte Phase abschließen
    if log:
        last = log[-1]
        if last.get("exited_at") is None:
            last["exited_at"] = now
            try:
                entered = datetime.fromisoformat(last["entered_at"])
                exited = datetime.fromisoformat(now)
                last["duration_min"] = round((exited - entered).total_seconds() / 60, 1)
            except (ValueError, KeyError):
                pass

    # Neue Phase eintragen
    log.append({"phase": new_phase, "entered_at": now, "exited_at": None, "duration_min": None})
```

Die Funktion wird bei jeder Stelle aufgerufen wo bisher `wf_data["current_phase"] = ...`
steht. (Aktuell: `_handle_approval`, `_handle_green`.)

### 3. `workflow.py phase` — Logging bei CLI-gesteuerten Übergängen

`workflow.py phase <phase_name>` ruft ebenfalls `_log_phase_transition()` auf,
damit auch manuell gesetzte Phasen (z.B. `/80-workflow` → `phase phase6_implement`)
im Log landen.

### 4. `workflow.py phase-log` — Lesbare Ausgabe

Neuer Subcommand, Ausgabe auf stdout:

```
Workflow: FEAT-007
──────────────────────────────────────────────
Phase               Dauer     Status
phase1_context      14.5 min  ✓
phase2_analyse      13.6 min  ✓
phase3_spec         22.1 min  ✓
phase4_approved      2.0 min  ✓
phase5_tdd_red      18.3 min  ✓
phase6_implement    [aktiv]
──────────────────────────────────────────────
Gesamt (abgeschl.)  70.5 min
```

Längste Phase wird mit `▲` markiert (visueller Hotspot-Hinweis).

### 5. Kein Breaking Change

`phase_log` ist ein neues optionales Feld. Bestehende Workflows ohne `phase_log`
funktionieren unverändert — `phase-log` gibt dann eine Meldung aus:
"Kein Phase-Log vorhanden (Workflow vor v3.2 gestartet)."

## Expected Behavior

- **Input:** Normaler Workflow-Betrieb (keine Änderung am User-Flow)
- **Output:** `phase_log`-Array wächst bei jedem Phasenwechsel automatisch
- **Seiteneffekte:** Minimale JSON-Schreibzugriffe (< 1 KB pro Eintrag)
- **`workflow.py phase-log`:** Tabellarische Ausgabe der Zeiten pro Phase

## Error Handling

- Fehler beim Schreiben des Logs → Warning auf stderr, kein Block, Workflow läuft weiter
- Korruptes `phase_log` in JSON → wird ignoriert, neuer leerer Log gestartet
- `datetime`-Parse-Fehler → `duration_min` bleibt `null`, kein Crash

## Known Limitations

- Zeit ≠ Tokens (exakt). Korreliert stark aber nicht 1:1 — lange Pausen des Users
  (z.B. Mittagspause) verfälschen die Messung.
- Keine Unterscheidung zwischen Claude-Denkzeit und User-Antwortzeit.
- Für exakte Token-Zahlen wäre Anthropic-API-Zugriff mit `usage`-Response nötig
  (nicht ohne externe Infrastruktur realisierbar in diesem Framework).

## Acceptance Criteria

- **AC-1:** Given Workflow startet bei phase1 / When `_log_phase_transition()` aufgerufen / Then `phase_log[0]` enthält `phase: "phase1_context"`, `entered_at` (ISO-String), `exited_at: null`
- **AC-2:** Given Phase1 aktiv / When Übergang zu phase2 / Then `phase_log[0].exited_at` gesetzt, `duration_min` berechnet, `phase_log[1]` eingefügt
- **AC-3:** Given Workflow mit 3 abgeschlossenen Phasen / When `workflow.py phase-log` / Then tabellarische Ausgabe mit Dauer pro Phase + Gesamt
- **AC-4:** Given Workflow ohne `phase_log` (Altbestand) / When `workflow.py phase-log` / Then Hinweis "Kein Phase-Log vorhanden" statt Fehler
- **AC-5:** Given Schreibfehler beim Log-Update / When Phasenwechsel / Then Workflow läuft weiter, Warning auf stderr (kein Block)

## Test Plan

```bash
# AC-1 + AC-2: phase_log wird korrekt befüllt
python3 core/hooks/workflow.py start TEST-LOG
export OPENSPEC_ACTIVE_WORKFLOW=TEST-LOG
python3 core/hooks/workflow.py phase phase1_context
python3 core/hooks/workflow.py phase phase2_analyse
python3 -c "
import json
d = json.load(open('.claude/workflows/TEST-LOG.json'))
assert len(d['phase_log']) == 2
assert d['phase_log'][0]['exited_at'] is not None
assert d['phase_log'][0]['duration_min'] is not None
assert d['phase_log'][1]['exited_at'] is None
print('OK')
"

# AC-3: phase-log Ausgabe
python3 core/hooks/workflow.py phase-log
# → tabellarische Ausgabe erwartet

# AC-4: Altbestand ohne phase_log
python3 -c "
import json; f=open('.claude/workflows/TEST-LOG.json','r+')
d=json.load(f); del d['phase_log']; f.seek(0); json.dump(d,f); f.truncate()
"
python3 core/hooks/workflow.py phase-log
# → "Kein Phase-Log vorhanden" erwartet, kein Fehler
```

## Changelog

- 2026-06-20: Initial spec erstellt
