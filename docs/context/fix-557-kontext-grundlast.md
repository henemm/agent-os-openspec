# Context: Kontext-Schwelle relativ zum Grundkontext messen (Issue #557)

## Request Summary

In Cloud-Sitzungen liegt der Grundkontext (System-Prompt, Tool-Schemas, CLAUDE.md, MCP) direkt nach `/clear` schon bei ~100k Token. Die feste Schwelle `context_budget.clear_threshold_tokens` (100k) steht dort dauerhaft auf `CONTEXT_CUT=on`; jede Phase hält für ein nutzloses `/clear` an. #551 entschärft das nur bei autarkem Auftrag. Gewünscht: Schwelle relativ zum Grundkontext (Wachstum seit erstem Messpunkt bzw. nach `/clear`/`/compact`). Test: Cloud-Szenario mit 100k Grundkontext meldet erst nach messbarem Wachstum `on`.

## Related Files

| Datei:Zeile | Bedeutung |
|-------------|-----------|
| core/hooks/hook_utils.py:2499-2506 | Kommentarblock Kontext-Haushalt, Konstanten `CONTEXT_BUDGET_DEFAULT_THRESHOLD` (100k), `CONTEXT_BUDGET_REPEAT_EVERY` (50k) |
| core/hooks/hook_utils.py:2509-2530 | `context_budget_settings()` → `{"enabled","threshold"}`; nur int >= 1000 gilt, fail-open |
| core/hooks/hook_utils.py:2584-2604 | `record_context_usage()` schreibt `session_id/tokens/at/announced_bucket` (liest `previous` selbst) |
| core/hooks/hook_utils.py:2606-2635 | `read_context_usage()` (Sitzungs-Id, sonst jüngste Datei <= 12 h) |
| core/hooks/hook_utils.py:2638-2643 | `context_bucket(tokens, threshold)`: 0 unter Schwelle, danach +1 je 50k |
| core/hooks/hook_utils.py:2652-2684 | `context_cut_note(tokens, threshold, autark)` Hinweistext |
| core/hooks/post_bash.py:151-186 | `_track_context`: misst, Stufen-Hinweis einmal je Stufe, Autark-Wortlaut via `auftrag_autark_open` |
| core/hooks/workflow.py:3886-3916 | `cmd_context`: `CONTEXT_TOKENS`, `CONTEXT_CUT` (Vergleich Zeile 3905), `CONTEXT_REASON=AUTARK` |
| core/hooks/workflow.py:3746-3768 | `cmd_autoclear`: nutzt die Schwelle NICHT (nur Herdr-Pane, Auto-/clear, Autark) |
| config.yaml:331-333 | `context_budget: enabled / clear_threshold_tokens: 100000` (nicht ändern, Config-Schutz) |
| docs/specs/feat-kontext-haushalt.md | Ursprungs-Spec (#-Kontext-Haushalt) |
| tests/test_kontext_haushalt.py:99-186 | Bestandstests Bucket, Settings, post_bash-Stufen, `cmd_context` |

## Existing Patterns

- Eine Quelle, viele Anzeiger: `context_budget_settings()` liefert die Schwelle, `post_bash` und `cmd_context` konsumieren sie getrennt.
- Messdatei je Sitzung, atomar, fail-open; Lesen nur als eigene normale Datei (`read_state_json`, #416).
- Auskunft statt Gate: `cmd_context` Exit immer 0, Schlüssel=Wert-Zeilen (`CONTEXT_REASON=AUTARK` als Vorbild für Zusatzzeilen).
- Autark (#551) hat Vorrang vor `on`; Kill-Switch nur das Literal `false`.
- Tests laufen post_bash/workflow als Subprozess mit tmp-Projekt (`_project`, `_transcript`, `_payload`, `_run`).

## Dependencies

- `post_bash._track_context` und `workflow.cmd_context` hängen an `context_budget_settings`, `read_context_usage`, `context_bucket`, `context_cut_note`.
- `cmd_autoclear` und `herdr_bridge` lesen weder Kontextgröße noch Schwelle (Grep: kein `threshold` in `herdr_bridge.py`); `test_autoclear_*`/`test_kette_auto_clear_489.py` bleiben unberührt, solange `AUTO_CLEAR` unverändert bleibt.
- Die Phasen-Befehle (`core/commands/10..50-*.md`) fragen nur `CONTEXT_CUT`; Text nennt „Default 100.000 Token“ (leichte Doku-Anpassung, Skills per `sync_skills.py`).

## Existing Specs

- docs/specs/feat-kontext-haushalt.md (Schwelle, Stufen, `CONTEXT_CUT`)
- docs/specs/feat-551-auftragsliste.md (Autark-Vorrang)
- README.md:310 (Doku der Schwelle, zu ergänzen)

## Risks & Considerations

- Erster Messwert ist nicht zwingend der Grundkontext: wird die Messung erst spät (z. B. nach Resume mit großem Kontext) gestartet, ist die Baseline hoch und die Schwelle später. Akzeptiert (nur Anzeige), Reset greift beim nächsten `/clear`/`/compact`.
- Bestandstest `test_post_bash_announces_once_per_bucket` misst als ersten Wert 122.040: neu Baseline 122.040, Schwelle 197.040, kein Hinweis. Test muss (RED/GREEN) angepasst werden, z. B. erst 40.000 messen.
- Stufen müssen relativ zur wirksamen Schwelle laufen, sonst wiederholt sich der Hinweis falsch; `announced_bucket` bei Baseline-Reset auf 0 zurücksetzen.
- `record_context_usage` überschreibt die Datei komplett: `baseline_tokens` muss dort fortgeschrieben werden, sonst geht es verloren.
- Alte Datei ohne `baseline_tokens` → Baseline None → nur absolute Schwelle (rückwärtskompatibel).
- Fail-open bleibt: kein Fehler ändert Gate-Entscheidungen; Kill-Switch und Autark unverändert.

## Analysis

### Type

Bugfix (Anzeige-/Messlogik, kein Gate).

### Technical Approach

1. `record_context_usage` (hook_utils): neues Feld `baseline_tokens`. Fehlt es in `previous` → aktueller Messwert. Fällt `tokens` um mehr als 30 % unter `previous["tokens"]` (`tokens < 0.7 * previous_tokens`, Zeichen für `/clear`/`/compact`) → `baseline_tokens = tokens` und `announced_bucket = 0`. Sonst Baseline fortschreiben. Alte Datei (nur `tokens`) bekommt beim nächsten Schreiben den aktuellen Wert als Baseline.
2. `context_budget_settings`: zusätzlich `growth` aus `context_budget.growth_tokens` (int >= 1000, Default `CONTEXT_BUDGET_DEFAULT_GROWTH = 75_000` im Code); `threshold` bleibt der Basiswert.
3. Neue Funktion `effective_context_threshold(settings, baseline)` in hook_utils: `max(threshold, baseline + growth)`; `baseline` None oder kein int → `threshold`.
4. `post_bash._track_context`: Baseline aus der bereits geschriebenen/zu schreibenden Messung ermitteln (Reihenfolge: erst Baseline-Update, dann `context_bucket(tokens, effective)` und `context_cut_note(tokens, effective, ...)`); Stufen relativ zur wirksamen Schwelle (je +50k).
5. `workflow.cmd_context`: `usage["baseline_tokens"]` lesen, wirksame Schwelle bilden, `on` bei `tokens >= wirksam`; neue Zeile `CONTEXT_THRESHOLD=<wirksam>` (nach `CONTEXT_CUT`, vor `CONTEXT_REASON`). Autark (#551) erzwingt weiter `off`; Kill-Switch unverändert.
6. `cmd_autoclear`: unverändert (nutzt die Schwelle nicht).
7. Doku: README.md Abschnitt Kontext-Haushalt, Befehlstexte (Formulierung „Schwelle aus `context_budget`“ ohne feste Zahl), CHANGELOG `[Unreleased]`. Repo-`config.yaml` unverändert.

### Affected Files (with changes)

| Datei | Änderung |
|-------|----------|
| core/hooks/hook_utils.py | `baseline_tokens` in `record_context_usage`; `growth` in `context_budget_settings`; neue `effective_context_threshold`; Kommentarblock |
| core/hooks/post_bash.py | `_track_context` nutzt wirksame Schwelle und Baseline-Reset |
| core/hooks/workflow.py | `cmd_context` mit wirksamer Schwelle, `CONTEXT_THRESHOLD=` |
| tests/test_kontext_grundlast_557.py | NEU, Tests zu allen AC |
| tests/test_kontext_haushalt.py | Anpassung des Stufentests (erster Messwert) |
| README.md, core/commands/10..50-*.md, skills/*/SKILL.md | Doku/Wortlaut, Skills per `sync_skills.py` |
| CHANGELOG.md | Eintrag unter [Unreleased] |

### Scope Assessment

- Dateien: 1 neu, ca. 4 Produktions-/Testdateien + Doku
- LoC: ca. +50/-10 Produktion, +130 Test
- Risiko: LOW-MEDIUM (Kern-Hooks `post_bash.py`/`workflow.py`, reine Auskunft ohne Gate-Wirkung)

### Open Questions

Keine.
