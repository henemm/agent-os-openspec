# Context: feat-345-qa-gate-selbst-ausfuehren

## Request Summary
Issue #345 (aus der Analyse zu #313/#327, dort Alternative B): `qa_gate.py` soll den Testbefehl selbst ausfuehren (`--run <Befehl>`) und den echten Exit-Code werten, statt eine Textdatei je Runner per Regex zu parsen. Ziel: Schluss mit "Could not determine test result" und mit der Faelschbarkeit (angehaengte Summary-Zeile, fix-2375 in #327). DoD laut Ticket: **erst Entwurf mit Migrationspfad und Entscheidung, ob der Datei-Modus bleibt (ADR), danach Umsetzung.**

## Related Files
| File | Relevance |
|------|-----------|
| core/hooks/qa_gate.py (566 Z.) | Kern. `validate_test_output` (Z. 347-446): Alter <= 30 min, Groesse >= 100 B, dann Kaskade unittest/node -> Executed (xcodebuild) -> Swift Testing -> pytest-Summary -> go -> cargo -> generische Marker -> "Could not determine". `main` (Z. 449-562): Argumente per Hand geparst, Verdict via `workflow.py set-field`, `--checklist` ruft `adversary_dialog.validate_dialog_artifact_ex` |
| core/hooks/post_bash.py:70-107 | `_detect_test_output`: zweite, unabhaengige Text-Erkennung (Runner-Liste im Befehl, Pass-/Fail-Regex) -> nur Hinweis `last_test_run`, kein Verdict (#253) |
| core/hooks/tdd_enforcement.py:200-290 | RED-Artefakte (`test_output`) werden inhaltlich geprueft (Platzhalter-Regex), unabhaengig von qa_gate |
| core/hooks/bash_gate.py:109-111 | `qa_gate.py` steht auf der WHITELIST_COMMANDS (Schreib-Indikator-Pruefung) — ein `--run` mit beliebigem Befehl wuerde ueber diese Whitelist laufen |
| core/hooks/adversary_dialog.py | `validate_dialog_artifact_ex`, `dialog_verdict` — von qa_gate genutzt, Verdict-Semantik VERIFIED/BROKEN/AMBIGUOUS |
| core/commands/50-implement.md:106, 284-294 | Developer-Agent schreibt `[test_command] > test-green-output.txt`; Step 8d ruft `qa_gate.py <datei> --checklist ...` |
| core/commands/60-validate.md:46-101 | `test_command` "aus openspec.yaml" — Feld existiert dort nicht (config.yaml `pre_commit` kennt nur `required_staged_files`) |
| core/commands/80-workflow.md:219-221 | Dokumentierte qa_gate-Aufrufe (Datei-Modus) |
| core/agents/implementation-validator.md:42-51, 203-218 | "test command ... in openspec.yaml under pre_commit.test_command" — verweist auf ein nicht existierendes Feld; Agent speichert Ausgabe fuer qa_gate |
| core/agents/developer-agent.md:27-57 | `test_command` als Eingabe, Ausgabe in Datei umleiten |
| config.yaml:218-221 | `pre_commit:` ohne `test_command` |
| skills/*/SKILL.md | generiert aus core/commands (sync_skills.py) — jede Befehlsaenderung zieht Skills nach |
| CLAUDE.md:51, 221, 434 | Beschreibt qa_gate als "Test-Output validieren" |

## Existing Patterns
- **"Datei rein, Urteil raus":** Jeder Testlauf erzeugt eine Datei unter `docs/artifacts/<wf>/`, die als Artefakt registriert, gestempelt, committet und spaeter (Phase 8, Commit-Gate) wieder herangezogen wird. Das Artefakt ist Nachweis fuer Mensch und CI, nicht nur fuer das Gate.
- **Fehlerrichtung:** Jede rote Evidenz gewinnt gegen gruen; 0 passed + skipped ist nicht gruen (#275, `_not_passed_skipped`).
- **Freshness statt Herkunft:** Die Datei darf hoechstens 30 min alt sein — der einzige Schutz gegen alte Laeufe; gegen eine handgeschriebene/ergaenzte Datei schuetzt nichts (genau die Faelschbarkeit aus #327).
- **Zustand statt Text (#299/#325):** Die Framework-Richtung geht bei Gates weg von Textmustern hin zu pruefbarem Zustand — #345 ist dieselbe Bewegung fuer Testergebnisse.
- **Kill-Switches** in `config.yaml` (`<gate>.enabled: false`) fuer neue Gates.

## Dependencies
- Upstream: `hook_utils` (setup_path, strip_ansi), `workflow.py` (status, set-field), `adversary_dialog`.
- Downstream: `/50-implement` (Step 4, 8d), `/60-validate`, `/80-workflow`-Doku, `implementation-validator`- und `developer-agent`-Briefings, Konsumenten-Projekte (iOS/xcodebuild, Home Assistant, node, go, cargo), Commit-Gate und Phase-8-Uebergang (lesen `adversary_verdict`).
- Testbestand: 6 Testdateien, ~108 Tests rund um die Parser (`test_qa_gate*.py`, `test_testausgabe_erkennung_275.py`, `test_gate_parser_fixes_73_76_79.py`, `test_verdict_pipeline_77.py`).

## Existing Specs
- docs/specs/fix-313-327-qa-gate-testausgabe.md — unittest/node per Regex (Weg A gewaehlt, B = dieses Issue)
- docs/specs/fix-275-testausgabe-erkennung.md — skipped/ANSI
- docs/specs/fix-71-qa-gate-zero-failed.md, docs/specs/qa-gate-path-resolution.md
- docs/specs/fix-253-adversary-evidence-gate.md — Verdict nur mit gestempeltem Dialog
- Kontext-Voranalyse: docs/context/fix-313-327-qa-gate-testausgabe.md, Abschnitt "Alternativen" (B)

## Risks & Considerations
- **Prinzip-Bruch / ADR noetig:** Das Ticket verlangt zuerst eine Entscheidung (Datei-Modus behalten, ersetzen, oder beides). Spec-Ergebnis kann ein Entwurf + ADR sein, Umsetzung als Folge.
- **Befehlsausfuehrung im Gate:** beliebiger Befehl -> Laufzeit (xcodebuild-Suiten: viele Minuten; Hook-/Tool-Timeouts), Umgebung (venv, Simulator), Secrets-/Egress-Guards, `bash_gate`-Whitelist fuer `qa_gate.py` wird zum Freibrief, wenn `--run` beliebige Befehle ausfuehrt.
- **Exit-Code ist nicht immer die Wahrheit:** `xcodebuild | xcbeautify` ohne `pipefail` liefert den Exit-Code des Formatters; `pytest` gibt 5 bei "no tests collected"; "0 passed + skipped" hat Exit 0 — die Skipped-Regel (#275) braeuchte weiterhin Text. Muss in der Analyse recherchiert werden.
- **Artefakt-Kette:** Wenn das Gate selbst ausfuehrt, muss es die Ausgabe trotzdem als Datei ablegen (Nachweis fuer Commit, CI, Mensch) und die Datei an den gemessenen Lauf binden (Hash/Exit-Code im Artefakt), sonst bleibt die Faelschbarkeit beim Wiederverwenden.
- **Woher kommt der Befehl?** `test_command` ist in `/60-validate` und im Validator-Agenten referenziert, existiert aber in keiner Config — ein Konfigurationsfeld waere neu (Migrationspfad fuer Konsumenten).
- **Zweite Erkennung in post_bash.py** bleibt Text-basiert; ob sie mitwandert, ist zu entscheiden (Scope).
- **Scope-Limit (4-5 Dateien, ±250 LoC):** volle Umsetzung inkl. Befehls-/Agenten-Doku und Skills-Sync sprengt es wahrscheinlich -> Teilung in Entwurf/ADR + Umsetzungsscheiben pruefen.
- **Offene Recherchefrage:** Was liefert der PostToolUse-Bash-Payload von Claude Code (Exit-Code-Feld?) — waere eine Alternative ohne Selbstausfuehrung (Hook liest den echten Exit-Code des Laufs, den Claude ohnehin startet).
