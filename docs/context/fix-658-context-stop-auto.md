# Context: fix-658-context-stop-auto

## Request Summary
Issue #658: Im Auto-Modus (`AUTONOMY=auto`) ohne Herdr-Auto-/clear hält `CONTEXT_CUT=on` die Phasenkette an
(❗Du-Zeile `/<folge> #N`), obwohl niemand `/clear` + Folgebefehl tippt. Ziel: der Halt greift nur, wo `/clear`
automatisch kommt (Herdr, `AUTO_CLEAR=on`) oder im Modus `manual`. Regel an einer Stelle (`workflow.py context`
liefert `CONTEXT_STOP=on|off`), Befehlstexte lesen nur diese Zeile; Tests.

## Related Files
| File | Relevance |
|------|-----------|
| core/hooks/workflow.py:5463 `cmd_context` | Gibt `CONTEXT_TOKENS`, `CONTEXT_CUT`, `CONTEXT_REASON=AUTARK` bzw. `CONTEXT_THRESHOLD` aus; hier entsteht `CONTEXT_STOP` |
| core/hooks/workflow.py:2195 `autonomy_mode` | Quelle für auto/manual (Env `OPENSPEC_AUTONOMY` + Config) |
| core/hooks/workflow.py:5308 `cmd_autoclear` | Bedingung `AUTO_CLEAR=on`: `herdr_bridge._pane()` und `herdr_bridge.auto_clear_enabled()`, aus bei autarkem Auftrag |
| core/hooks/herdr_bridge.py:149 `_pane`, :425 `auto_clear_enabled`, :660 `_context_cut_active` | Herdr-Erkennung; `_context_cut_active` spiegelt die CUT-Bedingung für den Stop-Hook (#598) — muss unverändert bleiben (dort ist Herdr per Definition aktiv) |
| core/hooks/hook_utils.py:2797 `context_cut_note` | Hinweistext von `post_bash.py` ab der Schwelle; Normalfall sagt „Im Auto-Modus den nächsten Skill NICHT selbst aufrufen" — widerspricht dem Ziel ohne Herdr |
| core/hooks/post_bash.py:178 | Aufruf `context_cut_note(tokens, threshold, autark=…)` |
| core/commands/10-context.md:167, 20-analyse.md:202, 30-write-spec.md:251, 40-tdd-red.md:183, 50-implement.md:405 | Absatz „Vor dem Selbstaufruf zusätzlich `workflow.py context` … Bei `CONTEXT_CUT=on` … NICHT selbst aufrufen" |
| skills/*/SKILL.md, .claude/agents | Generat (`scripts/sync_skills.py`), nach Befehls-Änderung neu erzeugen |
| CLAUDE.md:305 (Kontext-Haushalt Regel 1), README.md:209/311, setup.py:1390, config.yaml:334 | Doku nennt `CONTEXT_CUT` als Halt-Signal |
| tests/test_kontext_haushalt.py, test_kontext_grundlast_557.py, test_auftrag_551.py, test_autoclear_kontextschnitt_598.py | Pinnen exakte Ausgabezeilen von `context` und den Befehlsabsatz (`test_phase_commands_stop_chain_at_context_cut`) |

## Existing Patterns
- Auskunfts-Kommandos (`autonomy`, `autoclear`, `auto-ship`, `context`): kein Gate, Exit immer 0, fail-open auf „off".
- Autark-Ausnahme (#551) ist schon zentral in `cmd_context`/`cmd_autoclear`/`context_cut_note` (Grund-Zeile `CONTEXT_REASON=AUTARK`, eigener Hinweis-Wortlaut) — Vorbild für die neue Ausnahme „auto ohne Herdr".
- Befehlstexte lesen Ein-Zeilen-Signale (`AUTONOMY=`, `AUTO_CLEAR=`) und handeln danach.

## Dependencies
- Upstream: `autonomy_mode`, `herdr_bridge._pane`/`auto_clear_enabled`, `auftrag_autark_open`, `context_budget_settings`, `effective_context_threshold`, `read_context_usage`.
- Downstream: Phasen-Befehle 10–50, `post_bash.py`-Hinweis, Tests mit exakten Zeilenlisten. `herdr_bridge._context_cut_active` nutzt eigene Kopie der CUT-Bedingung (nicht `cmd_context`).

## Existing Specs
- docs/specs/feat-kontext-haushalt.md (CONTEXT_CUT, AC-7 Befehlstexte)
- docs/specs/fix-557-kontext-grundlast.md (Schwelle relativ, CONTEXT_THRESHOLD)
- docs/specs/feat-551-auftragsliste.md (AUTARK-Ausnahme)
- docs/specs/fix-598-autoclear-kontextschnitt.md (Herdr-Stop am Kontextschnitt)

## Risks & Considerations
- Zusätzliche Ausgabezeile bricht Tests mit exakten Zeilenlisten → Tests gezielt anpassen, `CONTEXT_CUT` selbst unverändert lassen (Messfakt; Herdr nutzt dieselbe Bedingung).
- Tests laufen in einer Umgebung mit `OPENSPEC_AUTONOMY=auto` (Cloud): Test-Env muss Autonomie explizit setzen/entfernen.
- Ohne Herdr läuft die Kette im Auto-Modus mit großem Kontext weiter; Ausgleich = automatische Komprimierung von Claude Code + Teilagenten (Hinweis). Epic #649 löst das grundsätzlich.
- Rückwärtskompatibilität: Befehlstexte und `workflow.py` kommen gemeinsam aus dem Plugin; ein alter Befehlstext, der noch `CONTEXT_CUT` liest, verhält sich wie bisher.

## Analysis

### Type
Bug (Verhalten widerspricht der PO-Einstellung `AUTONOMY=auto`).

### Affected Files (with changes)
| File | Change Type | Description |
|------|-------------|-------------|
| core/hooks/hook_utils.py | MODIFY | Entscheidungs-Helfer „hält die Kette für `/clear`?" (Autonomie != auto ODER Herdr-Auto-Clear aktiv), `context_cut_note(..., stop=)` mit Wortlaut „weiterarbeiten" für auto ohne Auto-/clear |
| core/hooks/herdr_bridge.py | MODIFY | Helfer `auto_clear_active()` = `_pane() and auto_clear_enabled()` (eine Quelle für `cmd_autoclear` und die neue Regel) |
| core/hooks/workflow.py | MODIFY | `cmd_context`: neue Zeile `CONTEXT_STOP=on|off` (immer, letzte Zeile), bei CUT=on/STOP=off `CONTEXT_REASON=AUTO_NO_CLEAR`; `cmd_autoclear` nutzt den Helfer |
| core/hooks/post_bash.py | MODIFY | Hinweisvariante nach derselben Regel wählen |
| core/commands/10..50-*.md | MODIFY | Absatz liest `CONTEXT_STOP=on` statt `CONTEXT_CUT=on` |
| skills/*, .claude/agents | REGENERATE | `scripts/sync_skills.py` |
| tests/test_context_stop_658.py | CREATE | auto ohne Herdr → off; auto+Herdr-Auto-Clear → on; manual → on; autark → off; Hinweis-Wortlaut |
| tests/test_kontext_haushalt.py, test_kontext_grundlast_557.py, test_auftrag_551.py | MODIFY | exakte Zeilenlisten um `CONTEXT_STOP`; Absatz-Test auf `CONTEXT_STOP=on`; Env `OPENSPEC_AUTONOMY`/`HERDR_*` explizit |
| CLAUDE.md, README.md, setup.py, config.yaml, CHANGELOG.md, .claude-plugin/plugin.json | MODIFY | Doku, Version 4.22.1 |

### Scope Assessment
- Files: ~8 Code/Test + Generat + Doku
- Estimated LoC: +200/-30 (ohne Generat)
- Risk Level: MEDIUM (Hook-Code, alle Konsumenten; Verhalten nur im Fall auto ohne Herdr geändert)

### Technical Approach
`CONTEXT_CUT` bleibt Messfakt (Herdr-Stop-Hook #598 nutzt dieselbe Bedingung unverändert). Neue Entscheidung `CONTEXT_STOP = CUT=on UND (Autonomie != auto ODER Herdr-Auto-Clear aktiv)`. Autark (#551) setzt CUT schon auf off → STOP off. Fehler im Entscheidungs-Helfer → STOP=on (bisheriges Verhalten). Befehlstexte lesen nur `CONTEXT_STOP`. Der post_bash-Hinweis sagt im Fall auto ohne Auto-/clear: weiterarbeiten, Teilagenten nutzen, Claude Code komprimiert automatisch.

Alternative verworfen: `CONTEXT_CUT` selbst umdeuten — vermischt Messung und Entscheidung, bricht #598-Spiegelbedingung und Hinweis-Unterscheidung. Zweite Alternative: CUT-Absatz streichen, nur `AUTO_CLEAR` — verliert die vom Issue verlangte Ein-Zeilen-Regel und lässt den post_bash-Hinweis ohne Entscheidungsstelle.

### Dependencies
`workflow.autonomy_mode` (lazy import im Helfer), `herdr_bridge._pane`/`auto_clear_enabled`, `auftrag_autark_open`.

### Open Questions
- keine (Produktentscheidung steht im Issue)
