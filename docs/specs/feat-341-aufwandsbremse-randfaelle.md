---
entity_id: feat-341-aufwandsbremse-randfaelle
type: module
created: 2026-10-03
updated: 2026-10-03
status: draft
version: "1.0"
tags: [aufwandsbremse, effort-budget, loc, phase-listener, "#341", "#250"]
---

# Aufwandsbremse: Randfälle bei Abschluss-Zeilenzählung und Überschreitungs-Rückfrage (#341)

## Approval

- [ ] Approved

## Purpose

Folgearbeit aus der Prüfung von #250 Teil B (PR #340). Gemeinsames Ziel: Die Abschluss-Zeilenzählung
(`loc_delta_final`) und die Budget-Rückfrage an den PO stimmen auch in Randfällen. Heute zählt die
Messung nach einem Rebase Zeilen aus main mit (reproduziert: 10 Feature-Zeilen ergeben 110), ordnet
Umlaut-Pfade falsch zu (`tests/Prüfung_test.py` zählt als Produktivcode) und liest Umbenennungen als
Doppelpfad. Außerdem wird eine Budget-Überschreitung, die beim Betreten von `phase4_approved` entsteht,
protokolliert, aber nie als Rückfrage ausgegeben, weil `phase_listener.py` die Rückgabe von
`record_transition` verwirft. Alles ist reine Git-Mechanik und Textausgabe; ein Modell ist nicht nötig.

## Source

- **File:** `core/hooks/workflow.py`, `core/hooks/phase_listener.py`
- **Identifier:** `workflow._final_loc`, `workflow._print_budget_question`, `workflow.record_transition`,
  Freigabe-Zweig in `phase_listener.main` (Aufruf `record_transition(wf_data, "phase4_approved", "approval")`)

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `adversary_dialog._phase8_base(data, top)` | Funktion | löst die Messbasis bereits korrekt auf (`base_commit`, sonst `merge-base(origin/main, HEAD)`); wird wiederverwendet statt zweiter Basislogik |
| `workflow.record_transition` | Funktion | liefert neue Überschreitungen als Liste; Rückgabe wird im Listener ausgewertet |
| `phase_listener._notify` / `_finish` | Funktionen | Ausgabepfad des Listeners; `_finish(note)` reicht `additionalContext` an Claude durch |
| `config_loader.get_scope_loc_config`, `get_scope_test_loc_config` | Funktionen | Ausschlüsse und Test-Muster der Zählung, unverändert |
| `docs/specs/feat-250-teil-b-aufwandsbremse.md` | Spec | eingefroren, wird nicht angefasst; AC-6 wird hier geklärt |
| `docs/context/feat-341-aufwandsbremse-randfaelle.md` | Analyse | Reproduktion, Root Cause, Recherche zu `git diff --numstat -z` |

## Scope

- **Affected Files:** `core/hooks/workflow.py`, `core/hooks/phase_listener.py`,
  `tests/test_effort_budget_250b.py`, `CHANGELOG.md`
- **Estimated Changes:** ca. +60/-15 LoC einschließlich Tests (Parser ca. 20, Basis ca. 8, Listener ca. 10).
  2 Logik-Dateien.
- **Nicht enthalten:** Änderungen an der Spec `feat-250-teil-b-aufwandsbremse.md`, an Budgetwerten,
  an `effort_budget_exceeded` oder an der 15-Minuten-Bremse.

## Implementation Details

1. **Basis von `_final_loc`:** `adversary_dialog._phase8_base(data, top)` statt `base_commit` direkt.
   Bewusst **nicht** `git merge-base <base_commit> HEAD` wie im Issue-Text: Nach einem Rebase bleibt der
   alte `base_commit` Vorfahre von HEAD, der merge-base wäre er selbst, und die neuen main-Zeilen
   zählten weiter mit. `_phase8_base` nimmt den jüngeren gültigen Vorfahren (gegen `origin/main`).
   Liefert die Auflösung einen Fehler oder `None`, bleibt das Ergebnis `None`: Messfehler blockieren den
   Abschluss nie.
2. **Parser:** `git diff <base> --numstat -z`; die Ausgabe wird an NUL zerlegt. Ein Eintrag hat die Form
   `added\tdeleted\tpfad`. Ist das dritte Feld leer, ist es eine Umbenennung: die zwei folgenden
   NUL-Tokens sind Vorher- und Nachher-Pfad, gezählt wird der **Nachher-Pfad** (Produktiv/Test nach
   dessen Muster). Die Rename-Erkennung von Git bleibt an, die Zeilen sind nur die tatsächlich
   geänderten. Binärdateien (`-\t-`) zählen 0. Mit `-z` werden Pfade verbatim ausgegeben (keine
   Oktal-Escapes), Umlaut-Pfade treffen also die Testmuster.
3. **Rückfrage bei Freigabe:** Der Text aus `_print_budget_question` wird als wiederverwendbare Funktion
   bereitgestellt (z. B. `format_budget_question(exceeded) -> str`); `_print_budget_question` ruft sie
   auf, die Ausgabe in `cmd_phase` bleibt identisch. `phase_listener.py` wertet die Rückgabe von
   `record_transition` aus; bei nicht leerer Liste geht der Text mit `RÜCKFRAGE AN DEN PO` als
   Anweisung an Claude über den Kontext-Pfad des Listeners (`_finish(note)` → `additionalContext`),
   nicht nur über stderr/`systemMessage`. Der Zustandswechsel nach `phase4_approved` bleibt vom
   Ergebnis unberührt; der bestehende `try/except` um den Aufruf deckt auch Fehler der Ausgabe ab.
4. **Klärung AC-6:** siehe nächsten Abschnitt; keine Codeänderung, das Verhalten ist bereits so
   umgesetzt und getestet.

## Klärung zu AC-6 aus #250 B

Die eingefrorene Spec `feat-250-teil-b-aufwandsbremse.md` formuliert AC-6 mit „ein **drittes** Mal
betritt (Grenze 2)". Das ist missverständlich. PO-Entscheidung vom 2026-10-03: **Die Rückfrage kommt
erst beim vierten Betreten einer Phase.** Gezählt wird `phase_reentries` = Betreten minus 1; gemeldet
wird, wenn der Wert die Grenze **überschreitet** (Wert > Grenze). Bei Grenze 2 ist das dritte Betreten
(Wert 2) genau auf der Grenze und still, das vierte Betreten (Wert 3) löst die Rückfrage aus. Die alte
Spec wird nicht geändert (das würde ihr Briefing und das CI-Spec-Gate entwerten); diese Klärung gilt
als maßgebliche Lesart.

## Expected Behavior

- **Input:** Abschluss (`write-log`/`finish`) nach Rebase, Umbenennung oder Umlaut-Pfad; Freigabe
  (`approved`) mit überschrittenem Budget.
- **Output:** `loc_delta_final`/`loc_delta_test_final` zählen nur die Zeilen des Workflows, Umbenennungen
  nach dem Nachher-Pfad, Umlaut-Pfade nach Testmuster. Bei Freigabe mit Überschreitung steht
  `RÜCKFRAGE AN DEN PO` im Kontext von Claude; ohne Überschreitung keine zusätzliche Ausgabe.
- **Side effects:** keine; die Freigabe und der Abschluss werden nie verweigert.

## Known Limitations

- Alternative zu Teil 2: `--no-renames` (Issue-Vorschlag) ist einfacher, zählt aber eine reine
  Verschiebung einer Datei als vollen Neucode und reizt das Budget grundlos aus. Gewählt ist darum die
  Rename-Erkennung mit `-z`. Folge: Bei Umbenennung mit Kategoriewechsel (Produktiv → Test) zählen die
  geänderten Zeilen komplett zum Nachher-Pfad; die entfallenen Vorher-Zeilen werden nicht abgezogen.
- Die Rückfrage bei Freigabe ist wie in Teil B eine Anweisung an Claude, kein erzwungener Halt; belegt
  wird die Ausgabe, nicht die Befolgung.
- Ist weder `base_commit` noch `origin/main` auflösbar, bleibt `loc_delta_final` leer (wie bisher).

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt; je Teil war der Test
      vorher rot und ist nachher grün
- [ ] Nach einem Rebase zeigt `loc_delta_final` nur die eigenen Zeilen, Umbenennungen und Umlaut-Pfade
      werden richtig zugeordnet
- [ ] Wird bei der Freigabe das Budget überschritten, wird der PO gefragt; ohne Überschreitung bleibt es
      still, und die Freigabe gelingt in jedem Fall
- [ ] Die Lesart „vierte Betreten" von AC-6 steht schriftlich fest und ist durch einen Test belegt
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Vollsuite grün)

## Acceptance Criteria

- **AC-1:** Given ein Feature-Branch mit 10 Zeilen Produktivcode und 100 neuen Zeilen auf main, Feature
  auf main rebased / When `_final_loc` misst / Then ergibt sich (10, 0) statt (110, 0)
  - Test: `tests/test_effort_budget_250b.py::test_final_loc_ignores_main_lines_after_rebase`
- **AC-2:** Given eine Umbenennung `core/hooks/old.py` nach `tests/test_new.py` mit 5 geänderten Zeilen /
  When `_final_loc` misst / Then zählen die 5 Zeilen als Testzeilen des Nachher-Pfads (0, 5), der
  Doppelpfad stört nicht
  - Test: `tests/test_effort_budget_250b.py::test_final_loc_follows_rename_to_new_path`
- **AC-3:** Given eine neue Datei `tests/Prüfung_test.py` mit 7 Zeilen / When `_final_loc` misst / Then
  zählt sie als Test (0, 7) statt als Produktivcode (7, 0)
  - Test: `tests/test_effort_budget_250b.py::test_final_loc_matches_umlaut_path_as_test`
- **AC-4:** Given ein Workflow in `phase3_spec`, dessen Betreten von `phase4_approved` das Budget
  überschreitet / When der echte Listener (Subprozess) den Prompt `approved` erhält / Then enthält seine
  Ausgabe `RÜCKFRAGE AN DEN PO` im Kontext für Claude (`additionalContext`) und die Freigabe ist wirksam
  - Test: `tests/test_effort_budget_250b.py::test_approval_prints_budget_question`
- **AC-5:** Given dieselbe Freigabe innerhalb des Budgets, sowie eine Freigabe, bei der die Ausgabe der
  Rückfrage einen Fehler wirft / When der Listener `approved` verarbeitet / Then ist im ersten Fall keine
  Rückfrage zu sehen, und in beiden Fällen steht `spec_approved` auf wahr und `current_phase` auf
  `phase4_approved`
  - Test: `tests/test_effort_budget_250b.py::test_approval_within_budget_silent_and_never_blocked`
- **AC-6:** Given ein `feature`-Workflow (Grenze 2) / When er eine Phase zum dritten Mal betritt / Then
  bleibt es still (Wert 2 liegt auf der Grenze), erst beim vierten Betreten (Wert 3 > Grenze) kommt die
  Rückfrage, und ein gleicher Stand wird nicht erneut gemeldet (Klärung zu AC-6 aus #250 B, PO-Entscheidung
  2026-10-03)
  - Test: `tests/test_effort_budget_250b.py::test_reentries_counted_and_not_repeated`
- **AC-7:** Given ein Messfehler (unbekannter `base_commit` bzw. nicht auflösbare Basis) / When `_final_loc`
  misst und `finish` läuft / Then liefert `_final_loc` `None` und der Abschluss gelingt ohne
  `loc_delta_final`
  - Test: `tests/test_effort_budget_250b.py::test_final_loc_error_still_returns_none`

> Die Test-Zuordnung wird **bei der Spec-Erstellung** eingetragen, nicht nachträglich: Nach der
> Freigabe ist diese Datei eingefroren (#230). Stimmt ein Testname später nicht mehr, gehört die
> Korrektur in die TDD-RED-Artefakte (`workflow.py add-artifact`), nicht in diese Datei.

## Test Plan

Automatische Tests (jeweils an eine AC oben gebunden):
- `pytest tests/test_effort_budget_250b.py` (AC-1 bis AC-7). AC-1 bis AC-3 und AC-7 bauen echte Git-Repos
  in `tmp_path` (Helfer `_git`, `_project`, `_py`), AC-1 mit echtem `git rebase`, AC-2 mit echter
  Umbenennung. AC-4/AC-5 starten den echten Listener per Subprozess (Muster wie
  `tests/test_adr_gate.py::_run_phase_listener`). AC-6 bleibt der bestehende Test, der das Verhalten
  bereits belegt (drittes Betreten still, viertes meldet `phase_reentries` 3 gegen 2).
- Vollsuite: `pytest tests/` (Hinweis: venv mit pytest und pyyaml, sonst stiller Leerlauf).

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Die Änderung kippt keine bestehende ADR. Sie nimmt den Regelweg statt eines Modells
  (reine Git-Mechanik und Text) und verwendet `_phase8_base` weiter, statt eine zweite Basislogik
  daneben zu stellen, die bei Rebase-Sonderfällen auseinanderlaufen könnte. Alternative: `git merge-base
  <base_commit> HEAD` (Issue-Text) ist einfacher, bleibt aber nach Rebase falsch; `--no-renames` ist
  einfacher als die Rename-Behandlung, überzählt aber Verschiebungen; und die Rückfrage könnte bei der
  Freigabe ganz entfallen und erst beim nächsten `workflow.py phase` erscheinen, ließe die Überschreitung
  dann aber bis dahin unsichtbar.

## Changelog

- 2026-10-03: Initial spec created
