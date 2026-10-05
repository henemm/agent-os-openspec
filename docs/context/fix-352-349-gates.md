# Context: fix-352-349-gates

## Request Summary
Zwei fälschlich blockierende Gates in einem Bündel beheben: #352 (`bash_gate` 5b blockt den
abschließenden Merge-Commit) und #349 (`tdd_enforcement` erkennt spec-Reporter-Summary `ℹ todo 0` nicht).

## Related Files
| File | Relevanz |
|------|----------|
| `core/hooks/bash_gate.py` (Abschnitt 5b, ca. Z. 863–884) | `rev-list --count HEAD..origin/main`; blockt jedes `git commit` bei > 0, Meldung rät zu `rebase --autostash` |
| `core/hooks/tdd_enforcement.py` Z. 87 (`_TAP_SUMMARY_RE`), Z. 140 (`_iter_frame_lines`) | filtert nur `^#\s*(tests\|…\|todo\|…)`; spec-Reporter-Form `ℹ todo 0` rutscht in die Platzhaltersuche (`\bTODO\b`, IGNORECASE) |
| `core/hooks/qa_gate.py` Z. 161 | erkennt `(ℹ\|#)` bereits → #349 betrifft qa_gate NICHT (Vermutung im Issue widerlegt) |
| `tests/test_bash_gate_erkennung_299.py` Z. 334–410 | Helfer `_origin_mit_klon`, `_gate`, `_git`; AC-17/18/19 sichern bestehendes 5b-Verhalten (Autostash-Rat, Messung im Arbeitsbaum, kein Block ohne Rückstand) |
| `tests/test_gate_fixes_26_38_34.py` | weitere 5b-Tests (cwd-Auflösung) |
| `tests/test_tdd_enforcement_*` (3 Dateien) | Muster für Tests des Platzhalterfilters |

## Existing Patterns
- 5b: fetch, dann `rev-list --count`; Netzfehler → stiller Skip (fail-open).
- Platzhalterfilter: Zeilenfilter vor `_PLACEHOLDER_RE`; Fehler-Evidenz (`_FAILURE_RE`) läuft auf Originalinhalt.

## Dependencies / Dependents
- Upstream: git (`MERGE_HEAD`, `rev-list`), `config`, `_read_active_workflow`.
- Downstream: alle Konsumenten-Projekte (Commit- und Edit-Pfad).

## Existing Specs
- Spec zu #284 (Autostash-Rat) und #73/#89/#262 (Platzhalterfilter) — Verhalten bleibt für den Nicht-Merge-Fall erhalten.

## Risks & Considerations
- #352: Rückstand bei laufendem Merge gegen `MERGE_HEAD` messen. Gate darf nicht fail-closed werden, wenn `rev-parse` scheitert → dann alter Pfad (HEAD).
- Merge, der Rückstand NICHT beseitigt (`MERGE_HEAD..origin/main` > 0) bleibt geblockt, Meldung ohne `--autostash`-Rat (Merge-Variante).
- Inkonsistenz `git merge --continue` (Gate erkennt nur `commit`): bewusst nicht Teil dieses Bündels; als Befund in der Spec notieren, kein Scope-Zuwachs.
- #349: Regex um `ℹ` erweitern, Test mit echter spec-Reporter-Ausgabe (aus `node --test --test-reporter=spec` erzeugen, nicht von Hand tippen).
- Alternative zu #352: 5b bei gesetztem MERGE_HEAD ganz überspringen (einfacher, lässt aber unvollständigen Merge durch) → verworfen.

## Analysis

### Type
Bugfix (2 fälschlich blockierende Gates, ein Ziel: "Gate blockt nur echte Verstöße").

### Reproduktion (2026-10-05, eigene Läufe)
- **#349:** `node --test --test-reporter=spec` (Node, echter Lauf mit einem roten Test) erzeugt `ℹ todo 0`.
  `tdd_enforcement._find_placeholder(<Ausgabe>)` → `(8, 'ℹ todo 0')`; dieselbe Ausgabe mit `ℹ`→`#` → `None`.
  Root Cause: `_TAP_SUMMARY_RE` (Z. 87) kennt nur `^#`; `_PLACEHOLDER_RE` trifft `todo` per IGNORECASE.
- **#352:** Wegwerf-Repo mit Rückstand, `git merge --no-commit --no-ff origin/main` (MERGE_HEAD gesetzt):
  `HEAD..origin/main`=1, `MERGE_HEAD..origin/main`=0, Gate auf `git commit -m x` → rc 2,
  „1 Commit(s) hinter origin/main … git rebase --autostash origin/main". Root Cause: 5b misst gegen HEAD (Vor-Merge-Stand).
- **qa_gate (Vermutung im Issue #349) widerlegt:** `qa_gate.py` Z. 161 erkennt `(ℹ|#)` bereits.

### Affected Files (with changes)
| File | Change Type | Description |
|------|-------------|-------------|
| core/hooks/bash_gate.py | MODIFY | 5b: bei `MERGE_HEAD` gegen `MERGE_HEAD..origin/main` messen; Meldung ohne --autostash-Rat in der Merge-Variante |
| core/hooks/tdd_enforcement.py | MODIFY | `_TAP_SUMMARY_RE` um `ℹ`-Form erweitern |
| tests/test_bash_gate_merge_head_352.py | CREATE | Merge fertig → durch; Merge unvollständig → blockt; ohne Merge unverändert (AC-17/18/19 bleiben grün) |
| tests/test_tdd_enforcement_spec_reporter_349.py | CREATE | Fixture aus echtem spec-Reporter-Lauf (roter Test) |
| CHANGELOG.md | MODIFY | [Unreleased], kein Versions-Bump |

### Scope Assessment
- Files: 5 (2 Code, 2 Tests, Changelog)
- Estimated LoC: +~140/-~5 (Code ~+25, Tests ~+110)
- Risk Level: LOW — beide Änderungen lockern ein Gate nur im eng definierten Fall; Nicht-Merge-Pfad bleibt Byte-identisch.

### Technical Approach (Regelweg, kein Modell nötig)
1. **#352:** In 5b vor `rev-list`: `git rev-parse -q --verify MERGE_HEAD` (cwd wie bisher). rc 0 → Basis = `MERGE_HEAD`, sonst `HEAD`.
   Schlägt `rev-parse` anders als „nicht vorhanden" fehl (Timeout/OSError) → alter Pfad (fail-open bleibt).
   Bei Basis=MERGE_HEAD und Rest > 0: Meldung „Merge bringt origin/main nicht vollständig herein — erst `git fetch origin && git merge origin/main`", ohne `--autostash`.
2. **#349:** Regex `^[#ℹ]\s*(tests|suites|…)\b.*$`. Test-Fixture aus echtem Lauf (nicht von Hand getippt); zusätzlich Gegenprobe: echtes TODO im Rahmen blockt weiterhin.

### Alternativen (bewusst verworfen)
- #352 (a): 5b bei MERGE_HEAD komplett überspringen — einfacher, lässt aber unvollständigen Merge durch.
- #352 (b): Rückstandsprüfung ganz streichen und der CI überlassen — kippt die Entscheidung hinter #284/5b (Rebase-Pflicht); CI-Spec-Gate fängt Rückstand nicht.
- #349 (a): Summary-Block generisch erkennen (Zeilen vor `duration_ms`) — fragil gegenüber Reporter-Versionen.
- #349 (b): RED-Artefakte nur im TAP-Reporter zulassen — schiebt den Aufwand auf Nutzer, kein Gewinn.

### Befunde ohne Scope-Zuwachs
- `git merge --continue` wird vom Gate nicht erfasst (nur Subcommand `commit`) → Gate inkonsistent. Folgearbeit: eigenes Issue anlegen, falls noch keines existiert (zuerst suchen).

### Dependencies
git (`rev-parse`, `rev-list`), `hook_utils`, bestehende Testhelfer `_origin_mit_klon/_gate/_git` aus tests/test_bash_gate_erkennung_299.py (Import).

### Open Questions
- [ ] Keine PO-Entscheidung nötig (rein technisch).
