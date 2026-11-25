# Context: fix-675-context-fresh

## Request Summary
`workflow.py context` meldet direkt nach Sitzungsstart `CONTEXT_TOKENS=unknown`, weil `post_bash.py` noch keine Messung (`context_usage/<sid>.json`) geschrieben hat. Ziel: fehlt die Messung, liest `context` das Transcript der laufenden Sitzung selbst (gleiche Rechnung wie `post_bash.py`).

## Related Files
| File | Relevance |
|------|-----------|
| core/hooks/workflow.py `cmd_context` (~5372) | Ausgabe `CONTEXT_TOKENS=`; liest nur `read_context_usage` |
| core/hooks/hook_utils.py `context_tokens_from_transcript` (~2664) | Rechnung input + cache_creation + cache_read der letzten Hauptsitzungs-Antwort |
| core/hooks/hook_utils.py `read_context_usage` (~2750) | eigene Messdatei, sonst juengste Datei (<= CONTEXT_USAGE_MAX_AGE_S) |
| core/hooks/post_bash.py `_track_context` (~150) | schreibt Messung aus `transcript_path` des Hook-Payloads |
| tests/test_context_stop_658.py | Muster fuer isolierte tmp-Projekte + `workflow.py context` |

## Existing Patterns
- Transcript-Fundort von Claude Code: `<CLAUDE_CONFIG_DIR|~/.claude>/projects/<projekt-slug>/<session_id>.jsonl` (in dieser Cloud-Sitzung bestaetigt: `~/.claude/projects/-home-user-agent-os-openspec/<sid>.jsonl`). Sitzungs-Id aus `CLAUDE_CODE_SESSION_ID`.
- Hooks sind fail-open; `context` ist Auskunft, kein Gate, Exit immer 0.

## Dependencies
- Upstream: `context_tokens_from_transcript`, `CLAUDE_CODE_SESSION_ID`, HOME/`CLAUDE_CONFIG_DIR`.
- Downstream: Phasen-Befehle lesen `CONTEXT_TOKENS`/`CONTEXT_STOP` (Kette fortsetzen oder Checkpoint); `handoff_prompt` laesst die Folgesitzung den Wert melden.

## Existing Specs
- docs/specs/fix-658-context-stop-auto.md, docs/specs/feat-662-kette-flach.md (Ausgabeformat von `context`).

## Risks & Considerations
- Reihenfolge: eigene Messdatei > eigenes Transcript > juengste fremde Messung (bisheriger Fallback). Sonst meldet eine frische Sitzung u. U. den Wert einer anderen Sitzung.
- Ohne Messdatei keine Baseline -> wirksame Schwelle = `clear_threshold_tokens` (wie heute bei fehlender Baseline). `context` schreibt nichts (Auskunft bleibt seiteneffektfrei).
- Sitzungs-Id gegen Pfad-Traversal pruefen (gleiche Regex wie `_context_usage_file`).
- Gate-Verhalten (post_bash-Hinweise, CONTEXT_STOP-Regeln) unveraendert.

## Analysis

### Type
Bug (Auskunft unvollstaendig), klein.

### Affected Files (with changes)
| File | Change Type | Description |
|------|-------------|-------------|
| core/hooks/hook_utils.py | MODIFY | neu `session_transcript_path(session_id)`: sucht `<CLAUDE_CONFIG_DIR oder ~/.claude>/projects/*/<sid>.jsonl` (sid per Regex geprueft), juengste Datei |
| core/hooks/workflow.py | MODIFY | `cmd_context`: eigene Messdatei (`fallback_newest=False`) > eigenes Transcript (`context_tokens_from_transcript`) > bisheriger Fallback juengste Messung |
| tests/test_context_fresh_675.py | CREATE | frische Sitzung ohne Messdatei mit Transcript -> Zahl; ohne Transcript -> wie bisher; eigene Messdatei hat Vorrang; fremde juengere Messung verdraengt eigenes Transcript nicht |
| CHANGELOG.md, plugin.json | MODIFY | 4.25.4 |

### Scope Assessment
- Files: 3 Code/Test + 2 Release
- Estimated LoC: +~30 Code, +~90 Test
- Risk Level: LOW (Auskunftsbefehl; einziger anderer Aufrufer von `read_context_usage` ist `record_context_usage` mit `fallback_newest=False`, unveraendert)

### Technical Approach
Nur lesen, nichts schreiben. Aus dem Transcript gibt es keine Baseline -> Schwelle wie bisher ohne Baseline. Ohne `CLAUDE_CODE_SESSION_ID` entfaellt der Transcript-Schritt (kein Raten).

### Dependencies
`read_context_usage`, `context_tokens_from_transcript` (unveraendert).

### Open Questions
- keine
