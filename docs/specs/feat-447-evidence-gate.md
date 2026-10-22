---
entity_id: feat-447-evidence-gate
type: feature
created: 2026-10-22
updated: 2026-10-22
status: draft
version: "1.0"
workflow: feat-447-evidence-gate
tags: [evidence-gate, phase8, simulator-proof, opt-in, write-protection]
test_targets: ["tests/test_evidence_gate_447.py"]
---

# Evidence-Gate — Simulator-Beleg als Pflicht vor Phase 8 (opt-in) + Schreibsperre (#447)

## Approval

- [ ] Approved

## GitHub Issue

- **Issue:** #447 — Teil von Epic #430. Herkunft: henemm/loose-ends#145 Schnitt 2
  („darf nicht von Hand setzbar sein“, „Prüfsumme passt zum aktuellen Stand“). Schnitt 2a
  (Gate) und 2b (Schreibsperre) laufen hier in einem Workflow.
- **Hinweis Restrisiko:** Die im Issue genannte Analyse `docs/context/feat-145-s2-gate.md`
  (loose-ends) ist auf GitHub nicht auffindbar. Maßgeblich ist der Issue-Text; verdeckte
  Anforderungen aus jener Analyse sind nicht ausgeschlossen.

## Purpose

Ein Projekt kann per Config verlangen, dass `phase8_complete` (auch über `complete` und
`finish`) nur erreichbar ist, wenn ein maschinell erzeugter Simulator-Beleg
(`docs/artifacts/<workflow>/simulator-run.txt`) vorliegt, der zum aktuellen Quellstand passt und
dessen Testergebnis das Gate selbst neu aus dem Ergebnisbündel `run.xcresult` ableitet. Der Beleg
darf nicht von Hand setzbar sein: Eine Schreibsperre sorgt dafür, dass nur der Erzeuger
(`scripts/sim.sh test-proof` bzw. `scripts/sim_proof.py`) die Beleg-Dateien schreibt. Ohne Config
ändert sich für kein Projekt irgendetwas an `_validate_transition`.

## Source

- **File:** `core/hooks/evidence_gate.py` (neu) — **Identifier:** `check_evidence(target, data, *,
  runner=None)`, Verifier-Registry `VERIFIERS` (erstes Mitglied `xcresult_proof`)
- **File:** `core/hooks/workflow.py` — **Identifier:** `_validate_transition` (Phase-8-Zweig und
  feature-fast-Zweig)
- **File:** `core/hooks/edit_gate.py` — **Identifier:** Schutz-Prüfung für Write/Edit
  (`PROTECTED_STATE_FILES`-Bereich)
- **File:** `core/hooks/bash_gate.py` — **Identifier:** `PROTECTED_FILE_PATTERNS`
- **File:** `config.yaml` — **Identifier:** neuer Abschnitt `evidence_checks`

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `adversary_dialog.phase8_code_files` | function | Gate-Menge (Code-Dateien der Änderung seit Basis), liefert `(files, info)`, wirft `ChangeSetError`, `files` ist `None` ohne Git-Baum; wird hier unabhängig von `coverage_gate_enabled()` aufgerufen |
| `adversary_dialog._hash_root` / `_resolve_hash_path` / `display_path` | function | Wurzel des Belegs (Worktree vor Hauptrepo), Pfadauflösung und repo-relative Anzeige |
| `adversary_dialog` Hash-Block-Parser (`_parse_examined_files_section`) | function | Zeilenformat `- sha256:<hex>  <pfad>`, hier auf den Abschnitt `## Geprüfte Dateien` angewendet |
| `config_loader.load_config` | function | Liest `evidence_checks` und `exempt_paths` |
| `override_token.has_valid_token` | function | Ausweg „override“; workflow-gebunden, lesend, ohne Verbrauch |
| `hook_utils.is_gated_code_path` | function | Gemeinsame Code-Definition; der Erzeuger spiegelt sie (Drift-Risiko, siehe Known Limitations) |
| git-CLI | external | Änderungsmenge und Hash-Wurzel |
| `xcrun xcresulttool` | external | Neuableitung des Testergebnisses (nur macOS mit Xcode); fehlt es, wird abgewiesen |
| loose-ends `scripts/sim_proof.py` (Commit b9bd75216dcf3f40e1874d005688163d31cae45b) | external | Referenz-Erzeuger des Belegformats; Funktion `format_proof(header, files)` erzeugt die Test-Fixture |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| `core/hooks/evidence_gate.py` | CREATE | Verifier-Registry, `check_evidence`, Config-Lesen, Beleg-Parser, Neuableitung via `xcrun xcresulttool` |
| `core/hooks/workflow.py` | MODIFY | `_validate_transition`: Aufruf im Phase-8-Zweig nach dem Dialog-Check und im feature-fast-Zweig nur für `phase8_complete` |
| `core/hooks/edit_gate.py` | MODIFY | Schreibsperre für Write/Edit auf die zwei Beleg-Muster (Regex, eng) |
| `core/hooks/bash_gate.py` | MODIFY | `PROTECTED_FILE_PATTERNS` um dieselben zwei Muster erweitert |
| `config.yaml` | MODIFY | Kommentierter Abschnitt `evidence_checks` (Default leer) mit `exempt_paths` |
| `tests/test_evidence_gate_447.py` | CREATE | Je ein Test pro Ablehnungsgrund, grüner Fall, Fast Track, Override, ohne Config identisch, Schreibsperre |
| `tests/fixtures/evidence_447/` | CREATE | Beleg-Fixture (aus `format_proof` erzeugt, Quell-SHA vermerkt), `summary.json`, Fake-`xcrun` |
| `CHANGELOG.md`, `setup.py` | MODIFY | Release-Eintrag, Version, Nebenwirkung der Schreibsperre benannt |
| `docs/specs/feat-447-evidence-gate.md` | CREATE | Diese Spec |

### Estimated Changes

- **Files:** 9 (davon 3 neu)
- **LoC:** Produktiv ca. +230, Tests ca. +350. Die Standardlimits (250 Produktiv / 500 Tests)
  reichen knapp; bei Überschreitung gilt `loc_limit_override` statt Aufteilung.

## Wo ich für dich entschieden habe

Fünf Punkte, bei denen ich vom Issue abweiche oder eine Lücke geschlossen habe. Kurz erklärt:

1. **Die Prüf-Funktion bekommt andere Eingaben als im Issue.** Im Issue steht
   `check_evidence(target_phase, wf)`; gebaut wird `check_evidence(target, data)`. Grund: Um zu
   wissen, welche Code-Dateien sich geändert haben, braucht die vorhandene Funktion
   `phase8_code_files` den ganzen Workflow-Datensatz (`data`); der Workflow-Name steckt darin
   (`data["name"]`). Alternative: nur den Namen übergeben und den Datensatz neu laden — mehr Code,
   zweite Fehlerquelle, kein Nutzen.
2. **Auch der Fast Track wird geprüft, aber nur wenn das Projekt das Gate eingeschaltet hat und
   nur beim letzten Schritt (`phase8_complete`).** Grund: Man kann jeden Workflow frei als
   „Fast Track“ starten; ohne diese Regel wäre das ganze Gate mit einem Befehl umgehbar
   (#145 fordert „nicht umgehbar“). Ohne Config ändert sich der Fast Track nicht. Alternative:
   Fast Track ausnehmen wie das Dialog-Gate — verworfen, weil es die Lücke offen ließe.
3. **Wie weit das getippte „override“ reicht.** Ein gültiges `override` öffnet nur das
   Evidence-Gate, nicht das Dialog-Gate (#253). Es gilt für den ganzen Workflow (nicht nur für
   dieses eine Gate): Hat man im selben Workflow für etwas anderes „override“ getippt (gilt 1
   Stunde), öffnet das auch dieses Gate. Es wird dabei nicht verbraucht. Das ist der
   bestehende Standard aller Override-Wege und bewusst so übernommen; damit es nicht
   unbemerkt passiert, schreibt das Gate dann „Evidence-Gate per override umgangen“ nach stderr.
   Alternative: eigener, gate-gebundener Token — verworfen, weil er einen zweiten
   Token-Mechanismus neben dem bestehenden einführen würde.
4. **Die Schreibsperre gilt überall und immer, ist aber sehr eng.** Gesperrt sind nur
   `docs/artifacts/<workflow>/simulator-run.txt` und alles unter
   `docs/artifacts/<workflow>/simulator-run/`; sie wirkt auch in Projekten, die das Gate nicht
   eingeschaltet haben (wie alle übrigen geschützten Dateien, so bleibt die Regel einfach).
   Andere Dateien unter `docs/artifacts/` und Doku, die den Pfad nur erwähnt, bleiben
   schreibbar; Lesen bleibt erlaubt; der Erzeuger darf schreiben. Alternative: Sperre nur bei
   eingeschaltetem Gate — verworfen, weil ein Hook dann von Config-Zustand abhängt und ein Beleg
   vor dem Einschalten von Hand angelegt werden könnte.
5. **Ein Workflow statt zwei (2a/2b getrennt).** Zusammen passt es knapp in die Größenlimits;
   zwei Workflows würden nur doppelten Freigabe-Aufwand bedeuten. Alternative: erst die
   kleine Sperre, dann das Gate — möglich, aber ohne Sicherheitsgewinn.

## Implementation Details

Beweglicher Teil: Details dürfen bei der Umsetzung nachgeschärft werden, die ACs unten nicht.

- **Einstieg und Reihenfolge.** `check_evidence(target, data, *, runner=None) -> str | None`
  (`None` = erlaubt, sonst Grund als Text, nie eine Exception). Der erste Schritt liest die
  Config; fehlt `evidence_checks`, ist es `{}` oder ist `phase8_complete` leer, kehrt die Funktion
  sofort mit `None` zurück — vor jedem Git-Aufruf und jedem `xcrun`. Danach: Config-Struktur
  prüfen (Liste von Einträgen mit `verifier` und `file`; unbekannter `verifier`, fehlendes `file`
  oder `file` mit Pfadtrenner/`..` = Abweisung), Override prüfen, Gate-Menge bilden, Verifier
  aufrufen.
- **Aufruf in `_validate_transition`.** Im normalen Phase-8-Zweig nach dem Dialog-Check
  (#253/#259), vor `return None`. Im feature-fast-Zweig (der ganz am Anfang zurückkehrt, vor der
  Same-Phase-Logik, #337) nur für `target == "phase8_complete"`. `cmd_complete` und damit
  `finish` rufen `_validate_transition` ohnehin auf; Same-Phase `phase8_complete` wird wie bisher
  voll geprüft.
- **Gate-Menge.** `phase8_code_files(data)` direkt (nicht hinter `coverage_gate_enabled()`),
  Pfade relativ zu `_hash_root()` umgerechnet, minus `exempt_paths` (fnmatch auf dem
  repo-relativen Pfad). Leer = kein Beleg nötig. `files is None` oder `ChangeSetError` = Abweisung.
- **Beleg-Ort und Pfadvergleich.** `_hash_root()/docs/artifacts/<wf>/<file>`; `wf` ohne `/` und
  `..`; nach `realpath` muss der Pfad unter `_hash_root()` liegen. Belegpfade werden über
  `realpath(_resolve_hash_path(rel))` mit der realpath-absoluten Gate-Menge verglichen
  (Vorbild `_uncovered_files`). Datei als UTF-8 gelesen.
- **Prüfkette `xcresult_proof`.** Beleg vorhanden → jede Gate-Datei mit aktuellem Hash im Block
  `## Geprüfte Dateien` (Obermenge erlaubt, `head:` nicht gebunden) → `summary.json` vorhanden und
  Prüfsumme gleich der `summary:`-Zeile → `run.xcresult` vorhanden → `xcrun xcresulttool get
  test-results summary --path <bundle> --compact` mit Timeout → JSON parsen → `result` und die vier
  Zähler (`totalTestCount`, `passedTests`, `failedTests`, `skippedTests`) semantisch mit
  `summary.json`, der `ergebnis:`-Zeile und der `tests:`-Zeile vergleichen (kein Bytevergleich,
  weil Felder nicht deterministisch sind) → `result == Passed` und `passedTests >= 1`.
- **Test-Nähte.** `runner` ist ausschließlich ein Python-Parameter für Unit-Tests; weder Config
  noch Umgebungsvariable können ihn setzen (sonst Fälschungsweg). Für Tests über die echten
  Hook-Skripte liegt ein Fake-`xcrun` im `PATH` des Subprozesses (auch für „Tool fehlt“,
  „Timeout“, „ungültiges JSON“, „Nicht-null-Exit“).
- **Schreibsperre.** `edit_gate.py`: Regex-Test auf `file_path` für beide Muster (immer, wie
  `PROTECTED_STATE_FILES`). `bash_gate.py`: dieselben zwei Muster in `PROTECTED_FILE_PATTERNS`
  (wirken in `_redirects_to_protected` und in der Prüfung „geschützter Pfad + Schreibindikator“).
  Der Erzeuger-Aufruf (`scripts/sim.sh test-proof`, `python3 scripts/sim_proof.py …`) nennt den
  Beleg-Pfad nicht als Schreibziel und wird dadurch nicht geblockt; der Test belegt das.
- **Fixture.** Der Beleg für den grünen Fall entsteht durch Aufruf von `format_proof` aus einer
  Kopie von `sim_proof.py` unter `tests/fixtures/evidence_447/` (mit vermerkter Quell-SHA
  `b9bd75216dcf3f40e1874d005688163d31cae45b`), nicht von Hand nachgebaut.

## Expected Behavior

- **Input:** Workflow-Datensatz, Ziel-Phase, Projekt-Config (`evidence_checks`,
  `exempt_paths`), Beleg-Dateien unter `docs/artifacts/<workflow>/`, Git-Zustand.
- **Output:** Übergang erlaubt (Exit 0) oder abgewiesen (Exit ungleich 0, Grund als Text auf
  stderr, der den fehlgeschlagenen Schritt nennt). Beim Override-Ausweg zusätzlich der Hinweis
  „Evidence-Gate per override umgangen“.
- **Side effects:** Keine schreibenden. Das Gate liest nur und ruft `xcrun xcresulttool` lesend
  auf.

## Error Handling

- Jeder Ablehnungsgrund wird im Text benannt (welche Datei, welcher Schritt). Ein unerwarteter
  interner Fehler wird zur Grund-Meldung mit Fehlerklasse (fail-closed), nie zur Exception.
- Vorhandene aber kaputte Config = Abweisung; fehlende/leere Config = kein Verhalten
  (klar getrennt, AC-1 bis AC-3).
- Ausweg: gültiges `override` des Workflows (nur Evidence-Gate) oder `exempt_paths` in der Config.

## Known Limitations

1. Ein älteres `run.xcresult` eines früheren grünen Laufs kann wiederverwendet werden: `head:` ist
   laut Issue nicht gebunden, der Hash-Block bindet nur den Quellstand.
2. Ein echter grüner Lauf einer anderen Testklasse ist nicht unterscheidbar (die Testklasse wird
   nicht gegen die Spec geprüft).
3. Die Schreibsperre wirkt nur über die Hooks, nicht gegen Prozesse außerhalb. `rm` eines
   veralteten Belegs ist ebenfalls gesperrt; neu erzeugen geht nur über den Erzeuger (gewollt).
4. Das `override` ist workflow-, nicht gate-gebunden (Entscheidung 3).
5. Der Erzeuger spiegelt `is_gated_code_path` (Stand 3.34.0, ohne Config-Override). Weicht die
   Projekt-Config (`strict_code_gate`) ab, kann eine Gate-Datei im Beleg fehlen; das ergibt eine
   Abweisung mit klarer Meldung, kein Fälschungsweg. „Obermenge erlaubt“ deckt die Gegenrichtung ab.
6. Config-Schutz: Im Worktree ist die wirksame Config im Hauptordner durch `worktree_write_guard`
   gesperrt, per Bash durch `_writes_effective_config` (#418). Restlücke nur in einer
   Hauptordner-Sitzung, die durch die Worktree-Pflicht ohnehin geblockt ist.
7. Das CI-Zielbild (Testklasse im Pull Request selbst ausführen) löst 1 und 2, ist laut Issue
   vertagt.
8. Die im Issue genannte Analyse `feat-145-s2-gate.md` ist nicht auffindbar (Restrisiko
   verdeckter Anforderungen).
9. Konsumenten mit eigenen Dateien `docs/artifacts/*/simulator-run.txt` bekommen durch die
   Schreibsperre eine Nebenwirkung; das steht im CHANGELOG.

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] Ein Projekt ohne `evidence_checks` verhält sich nachweislich identisch (kein Git-, kein
      `xcrun`-Aufruf); mit eingeschaltetem Gate ist `phase8_complete` ohne gültigen Beleg nicht
      erreichbar, mit dem echten Belegformat aus `sim_proof.format_proof` dagegen schon
- [ ] Die Beleg-Dateien lassen sich weder per Write/Edit noch per Bash-Umleitung schreiben, der
      Erzeuger aber läuft weiter
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf
      `python3 -m pytest tests/ -q` grün)
- [ ] CHANGELOG (inkl. Nebenwirkung Schreibsperre) und Version aktualisiert;
      `python3 scripts/ci_spec_gate.py --base origin/main` grün

## Acceptance Criteria

- **AC-1:** Given ein Projekt, in dem (a) der Schlüssel `evidence_checks` fehlt, (b)
  `evidence_checks: {}` steht oder (c) `phase8_complete: []` leer ist / When `phase`, `complete`
  oder `finish` nach `phase8_complete` läuft / Then verhält sich der Übergang exakt wie vor dieser
  Änderung, und es erfolgt weder ein Git- noch ein `xcrun`-Aufruf durch das Evidence-Gate.
  - Test: `tests/test_evidence_gate_447.py::test_ac1_without_config_identical`

- **AC-2:** Given eine vorhandene, aber strukturell kaputte `evidence_checks`-Config
  (`phase8_complete` ist keine Liste, ein Eintrag ist kein Objekt, `verifier` oder `file` fehlt,
  oder `file` enthält einen Pfadtrenner oder `..`) / When `phase8_complete` angefordert wird /
  Then wird abgewiesen, und die Meldung nennt die Config als Ursache.
  - Test: `tests/test_evidence_gate_447.py::test_ac2_broken_config_rejected`

- **AC-3:** Given eine vorhandene Config-Datei, die nicht geladen werden kann (z. B. ungültiges
  YAML) / When `phase8_complete` angefordert wird / Then wird abgewiesen (invertiert zum
  Kill-Switch-Muster: Nicht-Ladbarkeit schaltet das Gate nicht ab).
  - Test: `tests/test_evidence_gate_447.py::test_ac3_unloadable_config_rejected`

- **AC-4:** Given ein `verifier`-Name, der nicht in der Registry steht / When `phase8_complete`
  angefordert wird / Then wird abgewiesen, und die Meldung nennt den unbekannten Namen.
  - Test: `tests/test_evidence_gate_447.py::test_ac4_unknown_verifier_rejected`

- **AC-5:** Given eingeschaltetes Gate und eine Gate-Menge, die nach Abzug von `exempt_paths`
  (fnmatch auf dem repo-relativen Pfad) leer ist / When `phase8_complete` angefordert wird / Then
  ist kein Beleg nötig und der Übergang gelingt; ist dieselbe Menge ohne `exempt_paths` nicht
  leer, wird ohne Beleg abgewiesen.
  - Test: `tests/test_evidence_gate_447.py::test_ac5_empty_gate_set_and_exempt_paths`

- **AC-6:** Given eingeschaltetes Gate und kein Git-Arbeitsbaum (`phase8_code_files` liefert
  `(None, info)`) oder ein `ChangeSetError` / When `phase8_complete` angefordert wird / Then wird
  abgewiesen (fail-closed) mit einem Grund, der die nicht ermittelbare Änderungsmenge nennt.
  - Test: `tests/test_evidence_gate_447.py::test_ac6_no_git_tree_or_changeset_error_rejected`

- **AC-7:** Given ein Workflow-Name, der `/` oder `..` enthält / When `phase8_complete`
  angefordert wird / Then wird abgewiesen, und es wird keine Datei außerhalb von
  `docs/artifacts/` gelesen.
  - Test: `tests/test_evidence_gate_447.py::test_ac7_workflow_name_with_slash_or_dotdot_rejected`

- **AC-8:** Given ein Beleg-Pfad (oder dessen Ordner), der per Symlink aus `_hash_root()`
  hinausführt / When das Gate den Beleg lesen will / Then wird abgewiesen; liegt derselbe Beleg
  regulär unterhalb von `_hash_root()`, wird er gelesen.
  - Test: `tests/test_evidence_gate_447.py::test_ac8_symlink_escape_rejected`

- **AC-9:** Given eingeschaltetes Gate, nicht leere Gate-Menge und kein
  `docs/artifacts/<wf>/simulator-run.txt` / When `phase8_complete` angefordert wird / Then wird
  abgewiesen, und die Meldung nennt den erwarteten Beleg-Pfad.
  - Test: `tests/test_evidence_gate_447.py::test_ac9_proof_missing_rejected`

- **AC-10:** Given ein Beleg, dessen Block `## Geprüfte Dateien` eine Gate-Datei nicht enthält
  (auch die Zeile „(keine Code-Dateien geändert)“ bei nicht leerer Gate-Menge) / When
  `phase8_complete` angefordert wird / Then wird abgewiesen, und die Meldung nennt die fehlende
  Datei.
  - Test: `tests/test_evidence_gate_447.py::test_ac10_gate_file_missing_in_block_rejected`

- **AC-11:** Given ein Beleg, in dem der Hash einer Gate-Datei nicht mehr zum aktuellen
  Arbeitsbaum passt (Datei nach dem Lauf geändert) / When `phase8_complete` angefordert wird /
  Then wird abgewiesen, und die Meldung nennt die veraltete Datei.
  - Test: `tests/test_evidence_gate_447.py::test_ac11_stale_hash_rejected`

- **AC-12:** Given ein Beleg, dessen `summary.json` fehlt, dessen `summary:`-Zeile „fehlt (kein
  Ergebnisbündel)“ lautet oder dessen sha256-Prüfsumme nicht zur Datei passt / When
  `phase8_complete` angefordert wird / Then wird abgewiesen.
  - Test: `tests/test_evidence_gate_447.py::test_ac12_summary_json_missing_or_checksum_wrong_rejected`

- **AC-13:** Given ein Beleg, dessen `run.xcresult` nicht existiert / When `phase8_complete`
  angefordert wird / Then wird abgewiesen, ohne `xcrun` aufzurufen.
  - Test: `tests/test_evidence_gate_447.py::test_ac13_xcresult_missing_rejected`

- **AC-14:** Given ein System ohne `xcrun`/`xcresulttool` / When `phase8_complete` angefordert
  wird / Then wird abgewiesen, und die Meldung nennt das fehlende Werkzeug.
  - Test: `tests/test_evidence_gate_447.py::test_ac14_xcresulttool_missing_rejected`

- **AC-15:** Given ein `xcresulttool`, das mit Exit-Code ungleich 0 endet / When
  `phase8_complete` angefordert wird / Then wird abgewiesen, und die Meldung nennt den Exit-Code.
  - Test: `tests/test_evidence_gate_447.py::test_ac15_nonzero_exit_rejected`

- **AC-16:** Given ein `xcresulttool`, dessen Ausgabe kein gültiges JSON ist / When
  `phase8_complete` angefordert wird / Then wird abgewiesen.
  - Test: `tests/test_evidence_gate_447.py::test_ac16_invalid_json_rejected`

- **AC-17:** Given ein `xcresulttool`, das nicht innerhalb des Zeitlimits antwortet / When
  `phase8_complete` angefordert wird / Then wird abgewiesen, und die Meldung nennt den Timeout.
  - Test: `tests/test_evidence_gate_447.py::test_ac17_timeout_rejected`

- **AC-18:** Given eine Neuableitung, deren `result` oder einer der vier Zähler von der
  `summary.json` abweicht / When `phase8_complete` angefordert wird / Then wird abgewiesen, und
  die Meldung nennt das abweichende Feld.
  - Test: `tests/test_evidence_gate_447.py::test_ac18_semantic_mismatch_vs_summary_json_rejected`

- **AC-19:** Given eine Neuableitung, die mit der `summary.json` übereinstimmt, aber von der
  `ergebnis:`-Zeile oder der `tests:`-Zeile des Belegs abweicht / When `phase8_complete`
  angefordert wird / Then wird abgewiesen.
  - Test: `tests/test_evidence_gate_447.py::test_ac19_semantic_mismatch_vs_proof_lines_rejected`

- **AC-20:** Given eine übereinstimmende Neuableitung mit `result != Passed` / When
  `phase8_complete` angefordert wird / Then wird abgewiesen.
  - Test: `tests/test_evidence_gate_447.py::test_ac20_result_not_passed_rejected`

- **AC-21:** Given eine übereinstimmende Neuableitung mit `result == Passed`, aber `passedTests`
  kleiner als 1 / When `phase8_complete` angefordert wird / Then wird abgewiesen.
  - Test: `tests/test_evidence_gate_447.py::test_ac21_zero_passed_tests_rejected`

- **AC-22:** Given ein Beleg im echten Format (erzeugt durch `sim_proof.format_proof`), dessen
  Block alle Gate-Dateien mit aktuellem Hash enthält und zusätzlich weitere Dateien (Obermenge),
  mit einem `head:`, der nicht dem aktuellen HEAD entspricht, passender `summary.json`,
  vorhandenem `run.xcresult` und übereinstimmender Neuableitung mit `Passed` und mindestens einem
  bestandenen Test / When `phase8_complete` angefordert wird / Then gelingt der Übergang.
  - Test: `tests/test_evidence_gate_447.py::test_ac22_green_case_real_format`

- **AC-23:** Given eingeschaltetes Gate ohne gültigen Beleg / When `workflow.py phase
  phase8_complete`, `workflow.py complete` oder `workflow.py finish` ausgeführt wird, auch bei
  einem Workflow, der bereits in `phase8_complete` steht (Same-Phase, #337-Zwilling) / Then ist
  der Exit-Code in allen Fällen ungleich 0; der Evidence-Grund wird erst gemeldet, nachdem der
  Dialog-Check (#253/#259) bestanden ist.
  - Test: `tests/test_evidence_gate_447.py::test_ac23_all_completion_paths_checked`

- **AC-24:** Given einen Workflow vom Typ `feature-fast` und eingeschaltetes Gate ohne gültigen
  Beleg / When `phase8_complete` angefordert wird / Then wird abgewiesen; für jede andere
  Ziel-Phase des Fast Track und ohne `evidence_checks` bleibt das Verhalten unverändert.
  - Test: `tests/test_evidence_gate_447.py::test_ac24_fast_track_gated_only_phase8_with_config`

- **AC-25:** Given ein gültiger Override-Token des Workflows / When `phase8_complete` ohne gültigen
  Beleg angefordert wird / Then wird das Evidence-Gate geöffnet und stderr enthält „Evidence-Gate
  per override umgangen“; fehlt zugleich der Dialog-Nachweis, wird weiterhin am Dialog-Gate
  abgewiesen (der Override öffnet nur das Evidence-Gate); ohne Token oder mit Token eines anderen
  Workflows bleibt das Gate zu.
  - Test: `tests/test_evidence_gate_447.py::test_ac25_override_opens_only_evidence_gate`

- **AC-26:** Given die Test-Naht `runner` / When Config-Einträge oder Umgebungsvariablen versuchen,
  einen eigenen Runner oder ein eigenes Kommando einzuschleusen / Then wird `runner` nicht
  beeinflusst; er ist nur als Python-Parameter von `check_evidence` setzbar, und das Gate ruft
  sonst ausschließlich `xcrun xcresulttool`.
  - Test: `tests/test_evidence_gate_447.py::test_ac26_runner_not_overridable_by_config_or_env`

- **AC-27:** Given ein Write- oder Edit-Aufruf auf `docs/artifacts/<wf>/simulator-run.txt` oder
  auf eine Datei unter `docs/artifacts/<wf>/simulator-run/` / When `edit_gate.py` ihn prüft /
  Then wird er geblockt (Exit 2), unabhängig davon, ob `evidence_checks` eingeschaltet ist.
  - Test: `tests/test_evidence_gate_447.py::test_ac27_edit_gate_blocks_proof_files`

- **AC-28:** Given ein Bash-Schreibzugriff (Umleitung `>`/`>>`, `tee`, `cp`, `mv`, `sed -i`,
  `rm`) auf dieselben zwei Muster / When `bash_gate.py` ihn in einem Workflow mit Durchsetzung
  prüft / Then wird er geblockt (Exit 2), auch wenn die Umleitung hinter einem erlaubten Befehl
  steht.
  - Test: `tests/test_evidence_gate_447.py::test_ac28_bash_gate_blocks_proof_writes`

- **AC-29:** Given (a) `docs/artifacts/x/other.txt`, (b) eine Doku-Datei, die den Beleg-Pfad nur
  im Text erwähnt, (c) ein lesender Zugriff wie `cat docs/artifacts/<wf>/simulator-run.txt` und
  (d) der Erzeuger-Aufruf `scripts/sim.sh test-proof …` bzw. `python3 scripts/sim_proof.py <wf>
  <testklasse> docs/artifacts/<wf>/simulator-run/run.xcresult <endzeile> <befehl> <exit>` (das
  Bündel-Argument liegt selbst unter dem gesperrten Ordner) /
  When Edit-/Bash-Gate sie prüfen / Then wird keiner dieser Fälle geblockt.
  - Test: `tests/test_evidence_gate_447.py::test_ac29_write_protection_is_narrow`

- **AC-30:** Given das `config.yaml`-Template / When es geladen wird / Then enthält es einen
  kommentierten Abschnitt `evidence_checks` mit `exempt_paths`, dessen Wirkung im Default leer
  ist (geladene Config enthält keinen aktiven Eintrag).
  - Test: `tests/test_evidence_gate_447.py::test_ac30_config_template_documents_evidence_checks`

## Test Plan

Automatische Tests (jeweils an eine AC oben gebunden), Datei `tests/test_evidence_gate_447.py`:

- Unit-Ebene mit Test-Naht `runner` (kein macOS nötig) für die Prüfkette, AC-2 bis AC-22 und
  AC-26.
- Hook-Ebene über die echten Skripte (`workflow.py`, `edit_gate.py`, `bash_gate.py`) mit
  Wegwerf-Projekt, Wegwerf-Git-Repo und Fake-`xcrun` im `PATH` des Subprozesses: AC-1, AC-6,
  AC-14 bis AC-17, AC-23 bis AC-25, AC-27 bis AC-29.
- Fixture `tests/fixtures/evidence_447/`: Beleg durch Aufruf von `format_proof` (Kopie von
  `sim_proof.py`, Quell-SHA `b9bd75216dcf3f40e1874d005688163d31cae45b`) erzeugt, zugehörige
  `summary.json`, Fake-`xcrun`.
- Vorlagen für Aufbau: `tests/test_adversary_coverage_gate_259.py`,
  `tests/test_adversary_evidence_gate_253.py`, `tests/test_complete_recheck_337.py`,
  `tests/test_bash_gate_state_integrity_410.py`.
- Regression: `python3 -m pytest tests/ -q`; `python3 scripts/ci_spec_gate.py --base origin/main`.

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Keine neue Architektur, sondern ein weiteres, opt-in geschaltetes Gate im
  bestehenden Muster von #253/#259 (gleiche Gate-Menge, gleiches Hash-Format, fail-closed). Tragende
  Festlegungen: (1) Verifier-Registry, damit weitere Belegtypen nur Config kosten;
  (2) das Gate leitet das Ergebnis lokal neu aus `run.xcresult` ab und vergleicht semantisch
  (Zielbild CI-Durchlauf vertagt); (3) Opt-in per Config, ohne Config unverändert, kaputte Config
  weist ab statt abzuschalten; (4) Schreibsperre eng und global, Override workflow- statt
  gate-gebunden (bestehender Standard).

## Changelog

- 2026-10-22: Initial spec created
