# Context: fix-555-nacharbeit-endzustand

## Request Summary
Issue #555 sammelt die LOW-Funde der Adversary-Dialoge zu #550 (PR #554) und #551 (PR #556). Dazu kommt eine Beobachtung, die den Kern des PO-Wunsches aus #550 trifft: Im Auto-Modus mit autarkem Auftrag zeigt die Fußzeile `❗ Du: /50-implement #N`, obwohl Claude den Schritt selbst ausführt. Das ist eine erfundene PO-Aufgabe; #550 verbietet genau das („keine erfundenen PO-Aufgaben“).

## Related Files
| File | Relevance |
|------|-----------|
| core/hooks/workflow.py:400 / :3658 | `_one_line` doppelt definiert; die spätere (ohne `rstrip(".")`) überschreibt die erste → `waiting "CI."` ergibt „CI.. Du musst …“ (Fund 1) |
| core/hooks/workflow.py:426 | `deploy_note` geht ungeprüft in `_one_line`; ein Nicht-String erscheint als Python-Repr (Fund 3) |
| core/hooks/workflow.py:435-445 | `_end_state_open`: Phasen < 8 immer ❗ für Slash-Schritte (Fund 6) |
| core/hooks/workflow.py:458-500 | `_end_state_queue`, `end_state`: filtert die eigene Nummer bei `queue_next` nicht selbst (Fund 8) |
| core/hooks/workflow.py:502-518 | `queue_end_args`: einzige Quelle für Auftrags-Argumente von `endstate` und Plan |
| core/hooks/workflow.py:3264 | `cmd_waiting` stößt kein Seitenleisten-Update an (Fund 2) |
| core/hooks/herdr_bridge.py:217 | `build_report` ruft `end_state(data)` ohne Auftrags-Argumente → Seitenleiste kennt den Auftrag nicht |
| core/commands/60-validate.md:429-432, 70-deploy.md:124-127 | Kette greift bei jedem `ENDSTATE=waiting` mit `NEXT=M`, auch bei CI-Warten (Fund 7) |
| core/commands/70-deploy.md:122 | „Ohne Workflow bzw. Issue-Nummer entfällt der Aufruf“ — `endstate <name>` geht auch ohne Nummer (Fund 4) |
| config.yaml:207-208 | Kommentar nennt noch „Deploy (nicht eingerichtet)“ (Fund 5); Block `auftrag:` fehlt (Fund 10). Schreiben auf die wirksame Gate-Config blockt `bash_gate`/`edit_gate` außerhalb eines Worktrees |

## Existing Patterns
- Eine Quelle, viele Anzeiger (#234, #550): `end_state` ist rein, die Aufrufer liefern Config-/Auftragslage über `queue_end_args`.
- Autonomie: `autonomy_mode()` (workflow.py:1146) liefert `auto`/`manual`.
- Seitenleiste: `_herdr("report")`-Aufrufe nach Zustandsänderungen (Muster in `record_transition`).

## Dependencies
- Upstream: `next_step`, `expected_footer_command`, `read_auftrag`, `auftrag_open_issues`, `autonomy_mode`.
- Downstream: `cmd_endstate`, `render_plan`/`cmd_plan`/`_plan_watch`, `herdr_bridge.build_report`, `status_note` (Wortlaut-Regel), `footer_gate` (prüft nur ❗-Zeilen, fail-open ohne ❗).

## Existing Specs
- docs/specs/fix-550-endzustand.md, docs/specs/feat-551-auftragsliste.md

## Risks & Considerations
- Fund 6 ändert Endzeilen in Phasen < 8 → Plan, `endstate` und Seitenleiste müssen weiterhin dieselbe Zeile liefern.
- `footer_gate` blockt nicht, wenn keine ❗-Zeile vorliegt (AC-11 aus #550); eine ⏳-Zeile ist dort fail-open.
- config.yaml: nur über einen Worktree schreibbar (Hook-Vorgabe „Änderungen gehören in die Worktree-Kopie“).

## Analysis

### Type
Bugfix (Nacharbeit)

### Technical Approach (Tech-Lead-Entscheidung)
1. **Fund 1:** Die zweite `_one_line` (workflow.py:3658, Auskunft `observable-surface`) wird in `_flat_line` umbenannt, die Aufrufer dort angepasst. Damit gilt `_one_line` mit `rstrip(".")` für die Endzeilen; `waiting "CI."` ergibt „CI. Du musst …“ ohne Doppelpunkt.
2. **Fund 2:** `cmd_waiting` ruft nach dem Schreiben `_herdr("report")` (fail-open).
3. **Fund 3:** `deploy_note` zählt nur als String; alles andere wird ignoriert.
4. **Fund 4:** 70-deploy.md: `endstate` mit Workflow-Name, wenn keine Issue-Nummer da ist; nur ohne Workflow entfällt der Aufruf.
5. **Fund 5 + 10:** config.yaml: Kommentar auf das Verhalten nach #550 bringen („Projekt ohne Deploy: der Plan endet mit ✅“) und kommentierten Block `auftrag:` / `enabled: true` ergänzen. Schreiben im Git-Worktree der Sitzung (Hook-Vorgabe).
6. **Fund 6 (Kern):** `end_state(..., self_driven=False)`: Ist `self_driven` wahr und der Schritt in Phasen < 8 ein Slash-Befehl, liefert `end_state` `waiting` mit `⏳ Läuft noch: Claude führt <Befehl> selbst aus. Du musst nichts tun, ich melde mich.` und `cmd` = Befehl. `self_driven` = Autonomie `auto` UND offener autarker Auftrag; berechnet in `queue_end_args` (dort umbenannt bzw. erweitert, gemeinsame Quelle). Freigabe-Wörter und Stopps (AMBIGUOUS, BROKEN, Override …) bleiben ❗. Ohne autarken Auftrag oder bei `manual` bleibt alles wie in #550.
7. **Seitenleiste:** `herdr_bridge.build_report` nutzt dieselben Argumente (`queue_end_args`) wie `endstate` und Plan.
8. **Fund 7:** 60-validate.md/70-deploy.md: Kette nur, wenn `FOOTER` „aus deinem Auftrag“ enthält.
9. **Fund 8:** `end_state` ignoriert `queue_next`, wenn es die eigene Issue-Nummer des Workflows ist.
10. **Fund 9:** bewusst nicht umgesetzt (Spec #551 legt stille Normalisierung fest; kein Nutzen für den PO).

### Affected Files (with changes)
| File | Change Type | Description |
|------|-------------|-------------|
| core/hooks/workflow.py | MODIFY | Funde 1, 2, 3, 6, 8; `queue_end_args` liefert `self_driven` |
| core/hooks/herdr_bridge.py | MODIFY | `build_report` mit `queue_end_args` |
| core/commands/60-validate.md, 70-deploy.md | MODIFY | Funde 4, 7 |
| config.yaml | MODIFY | Funde 5, 10 (über Worktree) |
| tests/test_nacharbeit_555.py | CREATE | Regressionstests |
| skills/*, .claude/commands/* | REGENERATE | sync_skills / --command-aliases |
| CHANGELOG.md | MODIFY | [Unreleased] |

### Scope Assessment
- Files: ~6 (+ regeneriert)
- Estimated LoC: +80/-20 Produktion, +150 Test
- Risk Level: MEDIUM

### Open Questions
- keine (Fund 6 folgt der PO-Vorgabe aus #550: „keine erfundenen PO-Aufgaben“, Zustand 2 = „du musst nichts tun“)
