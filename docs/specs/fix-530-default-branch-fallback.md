---
entity_id: fix-530-default-branch-fallback
type: bugfix
created: 2026-11-06
updated: 2026-11-06
status: draft
version: "1.0"
workflow: fix-530-default-branch-fallback
tags: [autonomy, auto-mode, validate, auto-ship, default-branch, po-no-git]
---

# Auto-Modus: Default-Branch ohne origin/HEAD ermitteln, Namenskonflikt, Punkt-Verweise (Issue #530)

## Approval

- [ ] Approved

## Purpose

Im Auto-Modus von `/60-validate` ermitteln Punkt 2 und 3 den Default-Branch des Remotes nur über `git symbolic-ref --short refs/remotes/origin/HEAD`. Fehlt `origin/HEAD` lokal (etwa nach `git init` plus `git remote add`), schlägt das fehl, es wird nicht gepusht, und bei `AUTO_SHIP=on` wird nichts ausgeliefert (Adversary-Fund F003 aus #528, der wichtigste). Künftig fragt Claude als zweiten Weg `git ls-remote --symref origin HEAD` ab; scheitert auch das, meldet Claude bei `AUTO_SHIP=on` das Problem in Alltagssprache und gibt dem PO nie einen Git-Auftrag. Dazu: der Namenskonflikt beim neuen Feature-Branch nennt ausdrücklich „lokal oder auf dem Remote“ (F001), und ein Test bindet jeden Verweis „Punkt N“ im Auto-Modus-Abschnitt an den Titel des Listenpunkts N (F002), damit eine spätere Umnummerierung nicht still falsche Verweise hinterlässt.

## Source

- **File:** `core/commands/60-validate.md`, `tests/test_default_branch_fallback_530.py`
- **Identifier:** Abschnitt „Auto-Modus prüfen“, Listenpunkte 2 und 3; neue Testklassen für Fallback, Namenskonflikt und Verweise

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `core/commands/60-validate.md` (#472, #489, #525, #528) | command | Auto-Modus-Liste; Punkte 1, 4, 5, 6 und der Wortlaut von on-/off-Text bleiben unverändert |
| `tests/test_ship_default_branch_528.py` | tests | Vorbild für Abschnitts- und Listenpunkt-Parser (`_section`, `_items`, `_title`); bleibt grün |
| `tests/test_autonomy_kette_472.py`, `tests/test_kette_auto_clear_489.py` | tests | 4000-Zeichen-Fenster ab erstem `AUTONOMY=auto`; müssen grün bleiben (siehe Known Limitations) |
| `tests/test_auto_ship_525.py` | tests | Text-Tests zu on-/off-Absatz; bleiben grün |
| `scripts/sync_skills.py` | script | erzeugt `skills/60-validate/SKILL.md` aus dem Command; Drift blockt Release |
| `docs/context/fix-530-default-branch-fallback.md` | doc | Kontext, Analyse und Design |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| core/commands/60-validate.md | MODIFY | Punkt 3: Ermittlung des Default-Branchs mit Fallback `git ls-remote --symref origin HEAD` und Meldeweg je `AUTO_SHIP`; Punkt 2: Verweis auf diese Ermittlung statt Befehlswiederholung, Namenskonflikt „lokal oder auf dem Remote“ |
| skills/60-validate/SKILL.md | MODIFY | generiert per `python3 scripts/sync_skills.py` |
| tests/test_default_branch_fallback_530.py | CREATE | Text-Tests zu allen AC, inklusive Verweis-Test und Mutationsprobe |
| CHANGELOG.md | MODIFY | Eintrag unter [Unreleased], nennt #530 |

### Estimated Changes

- Files: 1 neu, 3 geändert (davon 1 generiert)
- LoC: +8/−3 Command-Text, +130 Test
- Risk Level: LOW (nur Anweisungstext und Tests, kein Python-Code in Hooks)

## Implementation Details

**`core/commands/60-validate.md`**, Abschnitt „Auto-Modus prüfen“, nur Punkt 2 und 3:

- **Punkt 3 („Den Feature-Branch pushen“)** beschreibt die Ermittlung des Default-Branchs einmal und vollständig: zuerst `git symbolic-ref --short refs/remotes/origin/HEAD` (z. B. `origin/main` wird zu `main`); schlägt das fehl, danach `git ls-remote --symref origin HEAD` und die Zeile `ref: refs/heads/<name>` auswerten. Schlagen beide fehl: bei `AUTO_SHIP=off` wie bisher nicht pushen und in der Abschlussmeldung melden; bei `AUTO_SHIP=on` ebenfalls nicht pushen und das Problem in Alltagssprache melden (etwa „Der Server war nicht erreichbar, ausgeliefert wird später“), nie als Git-Auftrag an den PO. Der Satz „nicht gepusht“ bleibt im Text.
- **Punkt 2 („Committen ohne Rückfrage“)** wiederholt den `symbolic-ref`-Befehl nicht mehr, sondern verweist für den Default-Branch auf die Ermittlung in Punkt 3. Der Namenskonflikt lautet: „Existiert der Name schon lokal oder auf dem Remote, wird `-2`, `-3` und so weiter angehängt.“ Der Rest (Feature-Branch vor dem Commit, kein `reset`, kein `--force`) bleibt im Wortlaut.
- Der Text bleibt knapp: Punkt 2 wird durch den Verweis kürzer, Punkt 3 wächst um wenige Zeilen. Ziel ist, dass der Deploy-Satz aus Punkt 4 im 4000-Zeichen-Fenster der Tests aus #472/#489 bleibt.

**`tests/test_default_branch_fallback_530.py`**: Text-Tests nach dem Muster aus `tests/test_ship_default_branch_528.py` (Abschnitt `### Auto-Modus prüfen` bis `## On Failure`, Whitespace normalisiert, Listenpunkte über `^\d+\.\s` samt eingerückten Folgezeilen, Titel aus dem ersten `**...**`), parametrisiert über `core/commands/60-validate.md` und `skills/60-validate/SKILL.md` (der Skill schreibt `$WF` statt `python3 .claude/hooks/workflow.py`; der Test nutzt für Aufrufe `(?:workflow\.py|\$WF)`).

**Verweis-Test:** Im Auto-Modus-Abschnitt werden per Regex `Punkt (\d)(?: und (\d))?` alle Verweise gesammelt. Jede genannte Nummer muss einen existierenden Listenpunkt haben. Zusätzlich hält der Test die erwartete Zuordnung fest: „Nach Punkt 2 und 3“ führt auf die Titel „Committen“ und „pushen“; „Verbot aus Punkt 3“ auf „pushen“; „siehe Punkt 5“ (Abschlussvorlage, 2 Stellen) auf „Ausliefern“; „hängt Punkt 2 ab“ in Punkt 1 auf „Committen“. Eine Mutationsprobe verschiebt in einer Kopie des Textes einen Verweis auf eine falsche Nummer und erwartet, dass die Prüffunktion dafür rot meldet.

**`skills/60-validate/SKILL.md`** wird nicht von Hand editiert, sondern per `python3 scripts/sync_skills.py` neu erzeugt.

## Expected Behavior

- **Input:** Abschluss einer Validierung (`phase8_complete`) im Auto-Modus mit `AUTO_SHIP=on` in einem Repo, in dem `refs/remotes/origin/HEAD` lokal fehlt, der Remote aber erreichbar ist
- **Output:** Claude ermittelt den Default-Branch über `git ls-remote --symref origin HEAD`, pusht den Feature-Branch und liefert normal aus; ist der Remote nicht erreichbar, steht in der Abschlussmeldung in Alltagssprache, dass nicht ausgeliefert werden konnte, ohne Git-Auftrag an den PO
- **Side effects:** keine neuen Zustände oder Dateien; nur ein zusätzlicher lesender Netzaufruf (`ls-remote`) im Fehlerfall des ersten Wegs

## Known Limitations

- `git ls-remote` braucht Netz und Zugang zum Remote; ohne beides schlägt auch der Fallback fehl und es wird (bei `on` mit Meldung in Alltagssprache) nicht gepusht und nicht ausgeliefert.
- Der Verweis-Test kennt nur die heute vorhandenen Verweisformen („Punkt N“ und „Punkt N und M“); eine neue Schreibweise (etwa „Punkte 2 bis 3“) wird nicht erfasst.
- Die erwartete Zuordnung Verweis zu Titel ist im Test festgehalten; ändert sich ein Listenpunkt-Titel absichtlich, muss der Test mitgezogen werden.
- Die Regel steht im Command-Text und wird von Claude befolgt, nicht von einem Hook erzwungen; ein Test belegt den Text, nicht das Verhalten im Lauf.
- Randbedingung Fenster #472: `test_validate_auto_never_deploys` sucht „löst nie ein Deploy aus“ in 4000 Zeichen ab dem ersten `AUTONOMY=auto`. Gemessener heutiger Abstand: 2081 Zeichen (Stand vor dieser Änderung). Der neue Text darf den Abstand nur so weit vergrößern, dass er unter 4000 bleibt; der Test aus #472 prüft das ohnehin und bleibt unverändert.
- Ein Remote, dessen `HEAD` auf keinen Branch zeigt (leeres Repo, Remote ohne Default-Branch), liefert keine `ref:`-Zeile und zählt als Fehlschlag beider Wege.

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] Die Anleitung nennt für den Default-Branch den Fallback `git ls-remote --symref origin HEAD` und den Meldeweg in Alltagssprache ohne Git-Auftrag an den PO
- [ ] Der Namenskonflikt beim Feature-Branch nennt ausdrücklich lokal und Remote
- [ ] Ein Test prüft jeden Verweis „Punkt N“ im Auto-Modus-Abschnitt gegen den Titel des Listenpunkts N
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf `pytest tests/` grün, Tests aus #472/#489/#525/#528 und Skill-Drift-Test grün)

## Acceptance Criteria

Testaufbau: Command-Text-Tests lesen `core/commands/60-validate.md` und `skills/60-validate/SKILL.md` als Datei, begrenzen auf den Abschnitt „Auto-Modus prüfen“ bis „## On Failure“ und suchen im Fliesstext (Whitespace normalisiert). Kein Mock.

- **AC-1:** Given der Auto-Modus-Abschnitt / When gelesen / Then nennt der Listenpunkt „pushen“ erst `git symbolic-ref --short refs/remotes/origin/HEAD` und, wenn das fehlschlägt, als zweiten Weg `git ls-remote --symref origin HEAD` mit der Zeile `ref: refs/heads/`
  - Test: tests/test_default_branch_fallback_530.py::TestFallback::test_ls_remote_fallback_after_symbolic_ref

- **AC-2:** Given der Listenpunkt „pushen“ / When gelesen / Then steht dort für den Fall, dass beide Wege scheitern: bei `AUTO_SHIP=on` nicht pushen und in Alltagssprache melden, nie ein Git-Auftrag an den PO; bei `AUTO_SHIP=off` wie bisher nicht pushen und in der Abschlussmeldung melden
  - Test: tests/test_default_branch_fallback_530.py::TestFallback::test_both_fail_reports_plainly_on_and_as_before_off

- **AC-3:** Given der Listenpunkt „Committen“ / When gelesen / Then verweist er für den Default-Branch auf die Ermittlung in Punkt 3 und wiederholt den `symbolic-ref`-Befehl nicht
  - Test: tests/test_default_branch_fallback_530.py::TestFallback::test_commit_point_refers_to_determination_in_push_point

- **AC-4:** Given der Listenpunkt „Committen“ / When gelesen / Then lautet der Namenskonflikt „lokal oder auf dem Remote“ mit Suffix `-2`, `-3`
  - Test: tests/test_default_branch_fallback_530.py::TestNameConflict::test_conflict_local_or_remote_gets_suffix

- **AC-5:** Given der Abschnitt / When gelesen / Then zeigt jeder Verweis „Punkt N“ (auch „Punkt N und M“) auf einen existierenden Listenpunkt, und die festgehaltene Zuordnung stimmt mit dem fett gesetzten Titel überein (Nach Punkt 2 und 3 = Committen und pushen; Verbot aus Punkt 3 = pushen; siehe Punkt 5 = Ausliefern; hängt Punkt 2 ab = Committen)
  - Test: tests/test_default_branch_fallback_530.py::TestPointReferences::test_every_reference_matches_item_title

- **AC-6:** Given eine Kopie des Abschnitts, in der ein Verweis auf eine falsche Nummer geändert wurde / When die Verweis-Prüffunktion läuft / Then meldet sie einen Fehler (Mutationsprobe); der unveränderte Text meldet keinen
  - Test: tests/test_default_branch_fallback_530.py::TestPointReferences::test_wrong_reference_is_detected

- **AC-7:** Given `core/commands/60-validate.md` / When der Abstand vom ersten `AUTONOMY=auto` bis „löst nie ein Deploy aus“ gemessen wird / Then liegt er unter 4000 Zeichen, und die on-/off-Texte aus #525/#528 sind weiter vorhanden
  - Test: tests/test_default_branch_fallback_530.py::TestWindow::test_deploy_sentence_within_4000_chars

- **AC-8:** Given `skills/60-validate/SKILL.md` und `core/commands/60-validate.md` / When `scripts/sync_skills.py --check` läuft / Then endet es mit Exit 0, der Skill ist synchron
  - Test: tests/test_default_branch_fallback_530.py::test_skills_in_sync

- **AC-9:** Given `CHANGELOG.md` / When gelesen / Then steht ab `## [Unreleased]` (unter `[Unreleased]` oder in einem beliebigen Versionsabschnitt, release-fest) ein Eintrag, der `#530` nennt
  - Test: tests/test_default_branch_fallback_530.py::test_changelog_mentions_530

## Test Plan

Automatische Tests (jeweils an eine AC oben gebunden):

- `pytest tests/test_default_branch_fallback_530.py`
- `pytest tests/test_ship_default_branch_528.py tests/test_auto_ship_525.py tests/test_autonomy_kette_472.py tests/test_kette_auto_clear_489.py tests/test_autonomy_schalter_469.py` (bestehende Text- und Fenster-Tests bleiben grün)
- Regressionslauf: `pytest tests/`
- `python3 scripts/sync_skills.py --check`

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Die Änderung ergänzt nur Anweisungstext in `60-validate.md` und einen Text-Test; kein neuer State, kein neues Gate, kein Hook, per Rückbau des Textes reversibel. `git ls-remote --symref origin HEAD` ist ein rein lesender Aufruf, der ohne lokales `origin/HEAD` auskommt und überall verfügbar ist, wo Git läuft. Verworfen: (a) `git remote set-head origin --auto` — ändert die lokale Konfiguration des Projekts (schreibt `refs/remotes/origin/HEAD`) und braucht ebenfalls Netz, bringt also keinen Vorteil gegenüber dem lesenden `ls-remote`; (b) `gh repo view --json defaultBranchRef` — setzt die GitHub-CLI und eine Anmeldung voraus, nicht überall installiert; (c) den Default-Branch aus Namen wie `main` oder `master` raten — falsch bei abweichenden Default-Branches und gefährlich beim Push-Verbot; (d) bei fehlendem `origin/HEAD` den PO bitten, es zu setzen — wäre ein Git-Auftrag an den PO und widerspricht #525.

## Changelog

- 2026-11-06: Initial spec created
