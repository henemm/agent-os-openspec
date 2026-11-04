# Kontext: fix-513-issue-nummer (Issue #513)

## Anfrage (PO, 2026-11-04)

„Starte mit #513, möglichst autark. Ich bin PO, ich kenne mich mit Git nicht aus. Handle als mein Tech Lead, der nach Best-Practice-Regeln entscheidet.“

Damit hat der PO die technischen Entscheidungen, auch den Schnitt des Umfangs, an den Tech Lead (Claude) delegiert.

## Issue #513 in Kurzform

Fünf Ursachen, fünf Vorschläge:

1. **Issue-Nummer falsch aus dem Namen** (`i18n-a2-e2e-2681` → `18`): erste Ziffernfolge statt echter Nummer, in `workflow.py::issue_number` und `session_singleton_guard.py::_extract_issue_number` (zwei Kopien derselben Regel).
2. **Phase 5 zeigt auf sich selbst:** `/40-tdd-red` ruft nie `mark-red`; erst der Phasenwechsel ganz am Ende schaltet die Fußzeile auf `/50-implement`.
3. Kein Abgleich State ↔ Wirklichkeit (Tests schon grün, PR schon gemergt).
4. Fußzeilen-Gate ohne Ausweg bei veraltetem State.
5. `/40-tdd-red` kennt den Fall „Tests existieren schon und sind grün“ nicht.

## Entscheidung zum Umfang (Tech Lead, vom PO delegiert)

Dieser Workflow behebt **Teil 1 und Teil 2**: Beide sind klar umrissene Fehler mit kleinem Risiko und sofortigem Nutzen (falsche Nummer in Fußzeile, Auto-/clear, `find`, Sitzungsregister; Phase 5 ohne Fortschritt).

**Teil 3–5** (`reconcile`, `phase-skip`, `step_override` im Footer-Gate) sind neue Funktionen mit eigener Gate-Wirkung, also ein Eingriff in die Schutzlogik. Sie brauchen eine eigene Spec und eigene Gegenprüfung und kommen in ein Folge-Issue. Grund: kleine, einzeln prüfbare Änderungen; ein Fehler im neuen Ausweg würde sonst den einfachen Fix mitreißen.

## Befund im Code (Stand 4.5.0)

- `core/hooks/workflow.py:303` `issue_number(name)`: `re.search(r"\d+")`. Aufrufer: `expected_footer_command`, `render_plan`, `status_note`, `cmd_start` (Titel-Abruf), `_with_issue_title`, `_plan_fetch_missing`; außerdem `herdr_bridge.py:199`.
- `core/hooks/session_singleton_guard.py:337` `_extract_issue_number(name)`: identische Regel; genutzt im Sitzungsregister (`issue`-Feld) und in `_claim_holds`.
- `cmd_find` sucht schon per Muster `(^|[-_])N([-_]|$)` und findet `i18n-a2-e2e-2681` für `2681`; es kennt aber kein State-Feld.
- Der State hat kein Feld für die Issue-Nummer.
- `core/commands/40-tdd-red.md` erwähnt `mark-red` nicht. `next_step()` meldet in `phase5_tdd_red` erst `/50-implement`, wenn `red_test_done` gesetzt ist.
- Bestehende Spec-Namen (`docs/specs/`) als Stichprobe: Die neue Regel ändert das Ergebnis nur bei `release-4-0-0` (bisher `4`, künftig keine Nummer, beides keine Issue-Nummer).
