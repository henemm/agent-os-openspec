---
entity_id: fix-675-context-fresh
type: bugfix
created: 2026-11-25
updated: 2026-11-25
status: draft
version: "1.0"
workflow: fix-675-context-fresh
tags: [kontext, token, workflow]
---

# `workflow.py context` misst frische Sitzungen selbst (Issue #675)

## Approval

- [ ] Approved

## Purpose

Direkt nach dem Start einer Sitzung meldet `workflow.py context` `CONTEXT_TOKENS=unknown`, weil `post_bash.py` noch keine Messung für diese Sitzung geschrieben hat. Künftig liest `context` dann das Transcript der laufenden Sitzung selbst, mit derselben Rechnung wie `post_bash.py`, und meldet eine Zahl; `unknown` nur noch, wenn weder Messung noch Transcript auffindbar ist.

## Source

- **File:** `core/hooks/workflow.py`, `core/hooks/hook_utils.py`
- **Identifier:** `workflow.cmd_context`, `hook_utils.session_transcript_path` (neu)

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `hook_utils.context_tokens_from_transcript` | Funktion (unverändert) | Rechnung input + cache_creation + cache_read der letzten Hauptsitzungs-Antwort |
| `hook_utils.read_context_usage` | Funktion (unverändert) | Messdatei der Sitzung bzw. jüngste Messung |
| `CLAUDE_CODE_SESSION_ID`, `CLAUDE_CONFIG_DIR`, `HOME` | Umgebung | Sitzungs-Id und Ort der Transcripts |

## Scope

- **Affected Files:** `core/hooks/hook_utils.py`, `core/hooks/workflow.py`, `tests/test_context_fresh_675.py` (neu), `CHANGELOG.md`, `.claude-plugin/plugin.json`
- **Estimated Changes:** ~30 LoC Code, ~100 LoC Test

## Implementation Details

```
hook_utils.session_transcript_path(session_id=None) -> Path | None
  sid = session_id or env CLAUDE_CODE_SESSION_ID; leer oder nicht [A-Za-z0-9_.-]{1,128} -> None
  base = env CLAUDE_CONFIG_DIR (falls gesetzt) sonst ~/.claude
  Kandidaten = base/projects/*/<sid>.jsonl (nur Dateien); jüngste nach mtime, sonst None
  wirft nie

workflow.cmd_context, Reihenfolge der Quellen:
  1. read_context_usage(None, root, fallback_newest=False)  # eigene Messdatei
  2. sonst: tokens = context_tokens_from_transcript(session_transcript_path())  # eigenes Transcript
  3. sonst: read_context_usage(None, root)                   # bisheriger Fallback (jüngste Messung)
  Baseline nur aus einer Messdatei (1 oder 3); aus dem Transcript keine Baseline.
  Ausgabeformat, CUT/STOP/AUTARK-Logik und Exit 0 unverändert; context schreibt nichts.
```

## Expected Behavior

- **Input:** Aufruf `workflow.py context` in einer Sitzung.
- **Output:** `CONTEXT_TOKENS=<n>`, sobald Messdatei oder Transcript der Sitzung vorliegt; übrige Zeilen wie bisher.
- **Side effects:** keine (keine Datei wird geschrieben).

## Acceptance Criteria

- **AC-1:** Frische Sitzung ohne eigene Messdatei, mit Transcript unter `<config>/projects/<slug>/<sid>.jsonl` → `CONTEXT_TOKENS=<Summe input+cache_creation+cache_read der letzten Hauptsitzungs-Antwort>`.
- **AC-2:** Eigene Messdatei vorhanden → ihr Wert gilt, auch wenn ein Transcript mit anderem Wert existiert.
- **AC-3:** Jüngere Messdatei einer fremden Sitzung verdrängt das eigene Transcript nicht.
- **AC-4:** Weder Messdatei noch Transcript → `CONTEXT_TOKENS=unknown` (bzw. bisheriger Fallback auf jüngste Messung bleibt).
- **AC-5:** `CLAUDE_CONFIG_DIR` wird statt `~/.claude` benutzt, wenn gesetzt.
- **AC-6:** Ungültige Sitzungs-Id (z. B. `../x`) → kein Transcript-Zugriff, keine Ausnahme.
- **AC-7:** `context` schreibt keine Messdatei; Ausgabe-Reihenfolge und `CONTEXT_STOP` als letzte Zeile unverändert (bestehende Tests #658/#662 grün).

## Test Plan

Automatische Tests (je an eine AC gebunden, ohne Netzwerk; tmp-Projekt mit kopierten Hooks, eigenes `HOME`, `CLAUDE_CONFIG_DIR` und `CLAUDE_CODE_SESSION_ID` je Szenario explizit gesetzt):

- `pytest tests/test_context_fresh_675.py` (RED zuerst, dann GREEN)
- Bestandstests: `pytest tests/test_context_stop_658.py tests/test_auto_chain_flat_662.py`
- Regressionslauf: `pytest tests/`
- `python3 -m py_compile core/hooks/hook_utils.py core/hooks/workflow.py`

## Known Limitations

- Aus dem Transcript gibt es keinen Grundkontext (Baseline); die wirksame Schwelle ist dann `clear_threshold_tokens`, wie heute bei fehlender Baseline.
- Ohne `CLAUDE_CODE_SESSION_ID` wird kein Transcript gesucht (kein Raten zwischen Sitzungen).

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion oben ist durch einen automatischen Test belegt
- [ ] `workflow.py context` meldet in einer frischen Sitzung eine Zahl statt `unknown`
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf grün); kein Gate-Verhalten geändert
- [ ] CHANGELOG und Version erhöht
