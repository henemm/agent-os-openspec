# Context: feat-341-aufwandsbremse-randfaelle

## Request Summary
Randfälle aus der Prüfung von #250 Teil B (PR #340) beheben: Abschluss-Zeilenzählung nach Rebase,
Umbenennungen und Sonderzeichen-Pfade in der Zählung, verworfene Budget-Rückfrage bei der Freigabe.

## Related Files
| File | Relevance |
|------|-----------|
| core/hooks/workflow.py:1098 `_final_loc` | misst `git diff <base_commit> --numstat` gegen den Arbeitsbaum; F002/F003 |
| core/hooks/workflow.py:621 `record_transition` | gibt neue Überschreitungen als Liste zurück |
| core/hooks/workflow.py:1298 `_print_budget_question` | Ausgabe "RÜCKFRAGE AN DEN PO" (nur `cmd_phase` ruft sie) |
| core/hooks/phase_listener.py:530 | ruft `record_transition(..., "phase4_approved", "approval")`, verwirft die Rückgabe; F004 |
| core/hooks/phase_listener.py:143 `_notify` | Ausgabepfad des Listeners (stderr + `_NOTICES`) |
| core/hooks/adversary_dialog.py:1102 `_phase8_base` | löst die Basis bereits korrekt auf (base_commit, sonst merge-base(origin/main, HEAD)) |
| tests/test_effort_budget_250b.py:332 | bestehender Test für `loc_delta_final` (ohne Rebase) |

## Existing Patterns
- Basis-Auflösung nach Rebase: `_phase8_base` nimmt den jüngeren gültigen Vorfahren von HEAD
  (base_commit nur, wenn er Vorfahre von HEAD ist).
- Listener-Meldungen laufen über `_notify`; Fehler im Protokollpfad werden toleriert (Freigabe darf nie scheitern).
- Tests bauen echte Git-Repos in `tmp_path` und rufen `workflow.py` per CLI (`_cli`, `_project`, `_git`).

## Dependencies
- Upstream: `config_loader.get_scope_loc_config`, `get_scope_test_loc_config`, `git`.
- Downstream: `cmd_complete` / `write-log` schreiben `loc_delta_final`, `loc_delta_test_final` ins Archiv.

## Wichtige Erkenntnis (korrigiert die Empfehlung aus der Prüfung)
Der Prüfer schlug `git merge-base <base_commit> HEAD` vor. Das reicht nicht: Nach einem Rebase ist der
alte `base_commit` ein Vorfahre von HEAD (alter main-Stand), der merge-base wäre er selbst, die neuen
main-Zeilen zählten weiter mit. Richtig ist die Basis gegen `origin/main` — also `_phase8_base` wiederverwenden
(oder dessen Logik), nicht neu erfinden.
Hinweis: ist `base_commit` nach Rebase KEIN Vorfahre mehr (Rebase schreibt Commits um, main-Stand bleibt aber
Vorfahre), greift dort `merge-base(origin/main, HEAD)`; das muss ein Test mit echtem Rebase belegen.

## Existing Specs
- `docs/specs/feat-250-teil-b-aufwandsbremse.md` (eingefroren, AC-6 "drittes Mal" überholt: PO-Entscheidung
  2026-10-03 → Rückfrage erst beim vierten Betreten, Wert > Grenze).

## Risks & Considerations
- Kern-Hooks: Messfehler dürfen den Abschluss nie blockieren (bestehende Anforderung AC-9).
- `--no-renames` und `-z` ändern das Ausgabeformat von `--numstat` (NUL-getrennt): Parser neu schreiben, Binärdateien (`-`) weiter als 0.
- Listener-Ausgabe der Rückfrage darf die Freigabe nicht beeinflussen.
- Scope: workflow.py, phase_listener.py, 1 Testdatei (~30 LoC Code).

## Analysis

### Type
Feature (Randfall-Korrekturen an #250 Teil B; Folgearbeit, gemeinsames Ziel: Zählung und Rückfrage stimmen in Randfällen)

### Recherche (vor der Analyse)
Git-Doku `diff-format`: Ohne `-z` werden ungewöhnliche Pfade nach `core.quotePath` in Anführungszeichen mit Oktal-Escapes ausgegeben; mit `-z` verbatim. Bei `--numstat -z` besteht ein Umbenennungs-Eintrag aus `added\tdeleted\t` + NUL + Vorher-Pfad + NUL + Nachher-Pfad + NUL, ein normaler aus `added\tdeleted\tpfad` + NUL.
Quellen: https://code.googlesource.com/git/+/HEAD/Documentation/diff-format.txt ; https://code.googlesource.com/git/+/f604652e05073aaef6d83e83b5d6499b55bb6dfd%5E%21/ (Commit „git-diff --numstat -z: make it machine readable")

### Reproduktion (Wegwerf-Repos, `_final_loc` real aufgerufen; Skript im Scratchpad `repro341.py`)
| Fall | erwartet (prod, test) | gemessen | Befund |
|------|----------------------|----------|--------|
| 1 Rebase: 10 Zeilen Feature, 100 Zeilen neu auf main, Feature auf main rebased | (10, 0) | **(110, 0)** | main-Zeilen zählen mit |
| 2 Umbenennung `core/hooks/old.py` → `tests/test_new.py` (+5 Zeilen) | — | (0, 5), Rohform `old => new` | Pfad ist ein Doppelpfad; Zuordnung hängt davon ab, welche Muster auf den zusammengesetzten Text passen (bei `{a => b}`-Kurzform unzuverlässig) |
| 3 Pfad `tests/Prüfung_test.py` | (0, 7) | **(7, 0)** | Rohform `"tests/Pr\303\274fung_test.py"` → Testmuster greift nicht, Testzeilen landen im Produktivcode |
| 4 Freigabe-Rückfrage | — | per Code belegt: `phase_listener.py:530` verwirft Rückgabe von `record_transition`; Ausgabe `_print_budget_question` gibt es nur in `cmd_phase` | Überschreitung beim Betreten von phase4_approved (z. B. Wiedereintritt nach Rückfall) wird protokolliert, aber nie gefragt |

### Root Cause
1 `_final_loc` ruft `git diff <base_commit>` gegen den Arbeitsbaum; nach Rebase bleibt base_commit der alte main-Stand.
2/3 `--numstat` ohne `-z` liefert gequotete bzw. zusammengesetzte Pfade, die der Parser (`split("\t")`, `parts[2]`) nicht auflöst.
4 Rückgabe verworfen.

### Affected Files (with changes)
| File | Change Type | Description |
|------|-------------|-------------|
| core/hooks/workflow.py | MODIFY | `_final_loc`: Basis über `adversary_dialog._phase8_base`, `-z`-Parser; `_print_budget_question`-Text als wiederverwendbare Funktion |
| core/hooks/phase_listener.py | MODIFY | Rückgabe von `record_transition` auswerten und Rückfrage ausgeben |
| tests/test_effort_budget_250b.py | MODIFY | je Teil ein Test (rot → grün), echter Rebase, echte Umbenennung, Umlaut-Pfad, Listener-Lauf |
| docs/specs/feat-341-aufwandsbremse-randfaelle.md | CREATE (Phase 3) | Spec; AC-6-Klärung steht hier |
| CHANGELOG.md | MODIFY | unter [Unreleased] |

### Scope Assessment
- Files: 4 (+ Spec)
- Estimated LoC: +60/-15 (Parser ~20, Basis ~8, Listener ~10, Tests im Testfile)
- Risk Level: LOW–MEDIUM (Kern-Hooks; Messfehler dürfen Abschluss nie blockieren → bestehender Fallback „None bei Fehler" bleibt)

### Technical Approach (Empfehlung)
Regelweg, kein Modell nötig (reine Git-Mechanik).
1. **Basis:** `_phase8_base(data, top)` aus `adversary_dialog` wiederverwenden (nicht `merge-base <base_commit> HEAD` wie im Issue-Text — das reicht nach Rebase nicht, siehe Erkenntnis oben). Ergebnis: Fall 1 → (10, 0).
2. **Parser:** `git diff <base> --numstat -z`, NUL-Tokens parsen: Eintrag mit leerem dritten Feld = Umbenennung → Nachher-Pfad nehmen. Zeilenzahl kommt dann aus Git-Rename-Erkennung (nur geänderte Zeilen), nicht doppelt.
3. **Listener:** Rückgabe auswerten und die Rückfrage an Claude geben (`additionalContext` über `_finish`-Note statt nur `systemMessage`, weil sie eine Anweisung an Claude ist); Freigabe bleibt unberührt (try/except bleibt).
4. **AC-6:** Klärung (vierte Betreten, Wert > Grenze, PO-Entscheidung 2026-10-03) steht in der neuen Spec; die eingefrorene Spec #250-B wird NICHT angefasst (würde Briefing/CI-spec-gate der alten Spec entwerten).

### Alternativen
- **Teil 2 anders als im Issue:** Das Issue schlägt `--no-renames` vor. Dann zählt eine reine Verschiebung einer 30-Zeilen-Datei als +30 Zeilen Neucode und reizt das Budget grundlos aus. Mein Vorschlag (Rename-Erkennung behalten, `-z`, Nachher-Pfad) weicht davon ab und misst fachlich richtiger. Alternative bleibt `--no-renames` (einfacher, überzählt Verschiebungen). Kippt keine ADR.
- **Teil 3 anders:** Statt Rückfrage beim Betreten von phase4_approved ausgeben → die Rückfrage entfällt dort ganz (Freigabe ist PO-Willenserklärung, der PO ist ohnehin am Zug) und wird beim nächsten `workflow.py phase` ausgegeben. Weniger Code, aber die Überschreitung bliebe bis dahin unsichtbar. Kippt nichts, schwächt AC der Teil-B-Spec.

### Open Questions
- [x] Teil 2: Rename-Erkennung behalten, `-z`, Nachher-Pfad (technische Entscheidung, kein PO-Thema; weicht bewusst vom Issue-Text `--no-renames` ab, Begründung oben).
- [x] Teil 3: Rückfrage bei Freigabe ausgeben, wie im Issue (technische Entscheidung).
