---
entity_id: fix-528-ship-default-branch
type: bugfix
created: 2026-11-06
updated: 2026-11-06
status: draft
version: "1.0"
workflow: fix-528-ship-default-branch
tags: [autonomy, auto-mode, validate, auto-ship, default-branch, po-no-git]
---

# Auto-Modus: Ausliefer-Pfad bei Checkout auf dem Default-Branch (Issue #528)

## Approval

- [ ] Approved

## Purpose

Seit #525 liefert Claude im Auto-Modus bei `AUTO_SHIP=on` selbst aus (PR, CI, Merge) und gibt dem PO nie einen Git-Auftrag. Eine Lücke bleibt: Steht der Checkout direkt auf `main`, `master`, dem Default-Branch des Remotes oder einem detached `HEAD`, sagt Punkt 2 des Auto-Modus „nur committen und der PO in der Abschlussmeldung darauf hingewiesen“. Dann gibt es keinen Branch für einen PR, und der Hinweis wäre ein Git-Auftrag an den PO, was #525 widerspricht (Adversary-Fund F003). Künftig legt Claude bei `AUTO_SHIP=on` vor dem Commit einen Feature-Branch mit dem Workflow-Namen an und liefert normal aus. Dazu: die Text-Tests zu AC-9/AC-10 aus #525 prüfen zu weite Fenster (F002), und der Ausliefer-Block hängt formal unter dem Deploy-Punkt (Layout).

## Source

- **File:** `core/commands/60-validate.md`, `tests/test_auto_ship_525.py`
- **Identifier:** Abschnitt „Auto-Modus prüfen“ (Punkte 1 bis 4 neu geordnet); `_on_windows` in `tests/test_auto_ship_525.py` (Fenster enger)

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `workflow.py auto-ship` (#525) | command | liefert `AUTO_SHIP=on\|off`; Aufruf und Schalter-Doku bleiben inhaltlich unverändert |
| `core/commands/60-validate.md` (#472, #489, #525) | command | Auto-Modus-Liste; der bisherige on-Text und der off-Text (4.5.4) bleiben im Wortlaut |
| `tests/test_autonomy_kette_472.py`, `tests/test_kette_auto_clear_489.py` | tests | Fenster-Tests ab `AUTONOMY=auto`; müssen grün bleiben (Deploy-Satz bleibt im Fenster) |
| `scripts/sync_skills.py` | script | erzeugt `skills/60-validate/SKILL.md` aus dem Command; Drift blockt Release |
| `docs/context/fix-528-ship-default-branch.md` | doc | Kontext und festgelegtes Design |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| core/commands/60-validate.md | MODIFY | Auto-Modus-Liste neu geordnet: `auto-ship` prüfen, Committen (bei on auf Default-Branch/detached `HEAD`: vorher Feature-Branch anlegen), Pushen, Ausliefern, Deploy, Freigaben auflisten |
| skills/60-validate/SKILL.md | MODIFY | generiert per `python3 scripts/sync_skills.py` |
| tests/test_auto_ship_525.py | MODIFY | `_on_windows` endet am off-Marker statt nach 4000 Zeichen; Testnamen und Aussagen bleiben |
| tests/test_ship_default_branch_528.py | CREATE | Command-Text-Tests zu allen AC |
| CHANGELOG.md | MODIFY | Eintrag unter [Unreleased], nennt #528 |

### Estimated Changes

- Files: 1 neu, 4 geändert (davon 1 generiert)
- LoC: +20/−10 Command-Text, +10 Test (525), +130 Test (neu)
- Risk Level: LOW (nur Anweisungstext und Tests, kein Python-Code in Hooks)

## Implementation Details

**`core/commands/60-validate.md`**, Abschnitt „Auto-Modus prüfen“. Neue Reihenfolge der Liste:

1. **`auto-ship` prüfen** als eigener erster Punkt: Aufruf `python3 .claude/hooks/workflow.py auto-ship`, nur die ausdrücklich gelesene Zeile `AUTO_SHIP=on` schaltet um, sonst `off`, Schalter `autonomy.ship: false` dokumentiert. Inhaltlich unverändert aus #525, nur aus dem Deploy-Punkt herausgelöst.
2. **Committen ohne Rückfrage** (bisher Punkt 1). Neu bei `AUTO_SHIP=on`: Steht der Checkout auf `main`, `master`, dem Default-Branch des Remotes (`git symbolic-ref --short refs/remotes/origin/HEAD`) oder einem detached `HEAD`, wird VOR dem Commit ein Feature-Branch mit dem Workflow-Namen angelegt (`git switch -c <workflow-name>`). Existiert der Name schon, wird `-2`, `-3` und so weiter angehängt. Der lokale Default-Branch wird nie zurückgesetzt (kein `reset`, kein `--force`). Bei `AUTO_SHIP=off` gilt der bisherige Text unverändert.
3. **Den Feature-Branch pushen** (bisher Punkt 2). Das Verbot, `main`, `master` oder den Default-Branch zu pushen, bleibt. Der Satz „nur committet und der PO in der Abschlussmeldung darauf hingewiesen“ gilt ausdrücklich nur für `AUTO_SHIP=off`.
4. **Ausliefern** als eigener Punkt: der bisherige on-Text aus #525 im Wortlaut (PR, CI, Merge, rote CI, Schutzregeln, kein Git-Auftrag an den PO), danach der off-Fall (`**Bei \`AUTO_SHIP=off\`**`, Git-Policy des Projekts, 4.5.4) im Wortlaut. Die Abschlussmeldung bei `on` nennt dem PO keinen Git-Schritt, auch nicht für den neu angelegten Branch.
5. **Deploy bleibt beim PO** als eigener Punkt mit nur dem Deploy-Satz (`deploy.autonomous` getrennt, kein `/70-deploy` aus dem Auto-Modus). Kein Ausliefer- oder `auto-ship`-Text mehr darin.
6. **Automatische Freigaben auflisten** (unverändert).

Der Verweis „siehe Punkt 3“ in der Abschlussvorlage wird auf die neue Nummer des Ausliefer-Punkts angepasst. Die Fenster-Tests aus #472/#489 bleiben grün, weil der Deploy-Satz im Wortlaut erhalten bleibt.

**`tests/test_auto_ship_525.py`**: `_on_windows` schneidet jedes Fenster ab `AUTO_SHIP=on` am nächsten off-Marker (`**Bei \`AUTO_SHIP=off\`**`) ab, falls dahinter, und nutzt sonst weiter die Breite. Damit werden AC-9/AC-10 nur vom on-Absatz erfüllt (Fund F002).

**`tests/test_ship_default_branch_528.py`**: Command-Text-Tests nach Muster von `TestCommandText` aus #525 (`_flat`, abschnittsgenaue Suche) für `core/commands/60-validate.md` und `skills/60-validate/SKILL.md`.

**`skills/60-validate/SKILL.md`** wird nicht von Hand editiert, sondern per `python3 scripts/sync_skills.py` neu erzeugt.

## Expected Behavior

- **Input:** Abschluss einer Validierung (`phase8_complete`) im Auto-Modus mit `AUTO_SHIP=on`, Checkout auf `main`, dem Default-Branch oder einem detached `HEAD`
- **Output:** Claude legt vor dem Commit den Branch `<workflow-name>` an, committet, pusht, erstellt den PR, wartet auf CI und mergt; die Abschlussmeldung nennt dem PO keinen Git-Schritt
- **Side effects:** neuer lokaler und entfernter Feature-Branch, PR und Merge; der lokale Default-Branch wird nicht verändert

## Known Limitations

- Commits, die schon vorher lokal auf dem Default-Branch liegen, wandern in den neuen Feature-Branch und damit in den PR.
- Der lokale Default-Branch bleibt dahinter bzw. daneben stehen und divergiert nach einem Squash-Merge vom Remote; er wird bewusst nicht zurückgesetzt.
- Die Regel steht im Command-Text und wird von Claude befolgt, nicht von einem Hook erzwungen; ein Test belegt den Text, nicht das Verhalten im Lauf.
- Bei `AUTO_SHIP=off` bleibt der Default-Branch-Fall wie bisher: nur committen und PO-Hinweis.
- Die Namenssuffixe `-2`, `-3` prüft Claude selbst anhand vorhandener lokaler und entfernter Branches; ein Hook kontrolliert das nicht.

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] Bei `AUTO_SHIP=on` und Checkout auf dem Default-Branch oder detached `HEAD` beschreibt `/60-validate` den Feature-Branch vor dem Commit, ohne Git-Auftrag an den PO
- [ ] Der lokale Default-Branch wird nie zurückgesetzt und nie mit `--force` angefasst
- [ ] Die Text-Tests zu AC-9/AC-10 aus #525 prüfen nur den on-Absatz
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf `pytest tests/` grün, Skill-Drift-Test grün)

## Acceptance Criteria

Testaufbau: Command-Text-Tests lesen `core/commands/60-validate.md` und `skills/60-validate/SKILL.md` als Datei, begrenzen auf den Abschnitt „Auto-Modus prüfen“ bis „## On Failure“ und suchen im Fliesstext (Whitespace normalisiert). Kein Mock.

- **AC-1:** Given der Abschnitt „Auto-Modus prüfen“ in `core/commands/60-validate.md` / When gelesen / Then steht der Aufruf `workflow.py auto-ship` vor dem Punkt „Committen“ und ist ein eigener Listenpunkt
  - Test: tests/test_ship_default_branch_528.py::TestOrder::test_auto_ship_check_precedes_commit_point

- **AC-2:** Given der Command-Text / When gelesen / Then verlangt er bei `AUTO_SHIP=on` und Checkout auf `main`, `master`, dem Default-Branch des Remotes oder einem detached `HEAD`, VOR dem Commit mit `git switch -c` einen Branch mit dem Workflow-Namen anzulegen
  - Test: tests/test_ship_default_branch_528.py::TestDefaultBranchPath::test_switch_branch_before_commit_with_workflow_name

- **AC-3:** Given der Command-Text / When gelesen / Then regelt er einen schon vorhandenen Branch-Namen über ein angehängtes Suffix (`-2`, `-3`)
  - Test: tests/test_ship_default_branch_528.py::TestDefaultBranchPath::test_name_conflict_gets_suffix

- **AC-4:** Given der Command-Text / When gelesen / Then steht dort, dass der lokale Default-Branch nie zurückgesetzt wird (kein `reset`) und nie `--force` genutzt wird
  - Test: tests/test_ship_default_branch_528.py::TestDefaultBranchPath::test_no_reset_and_no_force

- **AC-5:** Given der Command-Text / When gelesen / Then nennt die Abschlussmeldung im on-Fall dem PO keinen Git-Schritt, und der Satz „nur committet und der PO … darauf hingewiesen“ gilt ausdrücklich nur für `AUTO_SHIP=off`
  - Test: tests/test_ship_default_branch_528.py::TestDefaultBranchPath::test_no_git_task_for_po_and_hint_only_for_off

- **AC-6:** Given der Command-Text / When gelesen / Then enthält der Deploy-Punkt („Deploy bleibt beim PO“) weder `auto-ship` noch den Ausliefer-Text, der on-Text zu PR, CI und Merge steht in einem eigenen Punkt
  - Test: tests/test_ship_default_branch_528.py::TestOrder::test_deploy_point_has_no_ship_text

- **AC-7:** Given der Command-Text / When gelesen / Then bleiben der on-Text aus #525 (PR, CI, Merge, Schutzregeln) und der off-Text zur Git-Policy aus 4.5.4 im Wortlaut erhalten
  - Test: tests/test_ship_default_branch_528.py::TestOrder::test_on_and_off_text_kept_verbatim

- **AC-8:** Given ein Text, dessen Regeln (Schutzregeln, `--force`, Git-Schritt) nur im off-Absatz nach `**Bei \`AUTO_SHIP=off\`**` stehen / When er an die verengte Fensterfunktion `_on_windows` aus `tests/test_auto_ship_525.py` geht / Then werden diese Regeln in keinem Fenster gefunden; ein Text mit den Regeln im on-Absatz findet sie weiterhin (Mutationstest zu F002)
  - Test: tests/test_ship_default_branch_528.py::TestWindowNarrowing::test_rules_only_in_off_paragraph_not_found

- **AC-9:** Given `skills/60-validate/SKILL.md` und `core/commands/60-validate.md` / When `scripts/sync_skills.py --check` läuft / Then endet es mit Exit 0, der Skill ist synchron
  - Test: tests/test_ship_default_branch_528.py::test_skills_in_sync

- **AC-10:** Given `CHANGELOG.md` / When gelesen / Then steht ab `## [Unreleased]` (unter `[Unreleased]` oder in einem beliebigen Versionsabschnitt, release-fest) ein Eintrag, der `#528` nennt
  - Test: tests/test_ship_default_branch_528.py::test_changelog_mentions_528

## Test Plan

Automatische Tests (jeweils an eine AC oben gebunden):

- `pytest tests/test_ship_default_branch_528.py`
- `pytest tests/test_auto_ship_525.py tests/test_autonomy_kette_472.py tests/test_kette_auto_clear_489.py tests/test_autonomy_schalter_469.py` (bestehende Fenster- und Text-Tests bleiben grün)
- Regressionslauf: `pytest tests/`
- `python3 scripts/sync_skills.py --check`

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Die Änderung ergänzt nur Anweisungstext in `60-validate.md` und verengt Test-Fenster; kein neuer State, kein neues Gate, kein Hook, per Rückbau des Textes reversibel. Der Branch wird vor dem Commit abgezweigt, damit der Default-Branch lokal nie angefasst werden muss. Verworfen: (a) Branch erst nach dem Commit abzweigen und den lokalen `main` zurücksetzen — destruktiv, widerspricht dem Verbot von `reset` und kann Arbeit vernichten; (b) den PO-Hinweis lassen — er wäre ein Git-Auftrag an den PO und widerspricht #525; (c) direkt auf den Default-Branch pushen — verletzt die Schutzregeln und das Push-Verbot aus Punkt 2; (d) die Layout-Frage ungelöst lassen — der Ausliefer-Block unter dem Deploy-Punkt verleitet zu falscher Lesart („Deploy bleibt beim PO“ gilt nicht für Merge).

## Changelog

- 2026-11-06: Initial spec created
