---
entity_id: feat-633-release-ohne-doppeltest
type: feature
created: 2026-11-21
updated: 2026-11-21
status: draft
version: "1.0"
workflow: feat-633-release-ohne-doppeltest
tags: [release, ci, release-check, tests, fail-closed]
---

# Release ohne Doppeltest: volle Suite nur, wenn der getestete Stand nicht nachweislich derselbe ist (Issue #633)

## Approval

- [ ] Approved

## Purpose

Nach dem Merge eines Release-PRs wiederholt `release.yml` die volle Testsuite (rund 11 min), obwohl derselbe Stand im PR schon grün war. Künftig weist ein neuer Modus nach, dass der veröffentlichte Baum exakt der im PR grün getestete ist; nur dann entfällt die Wiederholung, in jedem anderen Fall läuft die volle Suite wie bisher.

Entscheidung PO (2026-11-21, #633): „Muss das sein oder können wir nicht verzichten? Es war doch alles getestet.“ Gewählt ist Variante A (Nachweis per Baum-Vergleich und Check-Run), B und C sind verworfen (siehe ADR-Abschnitt).

## Source

- Issue #633, Befund und Analyse: `docs/context/feat-633-release-ohne-doppeltest.md`.
- **File:** `scripts/release_check.py`, `.github/workflows/release.yml`
- **Identifier:** neu `decide_tested_proof` (pure Entscheidung), `fetch_tested_proof_inputs` (Abruf), `run_tested_proof` (Ausgabe), CLI-Modus `--tested-proof <sha>`; Schritt „Release-Vorbedingungen pruefen“ in `release.yml`

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `gh api` (GitHub CLI) | tool | `GET /repos/{o}/{r}/commits/{sha}/pulls` und `GET /repos/{o}/{r}/commits/{head}/check-runs?check_name=tests` |
| `git fetch origin refs/pull/<N>/head`, `git rev-parse <x>^{tree}` | tool | Head des PR holen (Branch kann nach dem Merge gelöscht sein) und Baum-SHAs vergleichen |
| `.github/workflows/ci.yml` Job `tests` | workflow | Name des Check-Runs, der als Nachweis dient |
| `scripts/release_check.py::_git`, `check_tests`, `main` | function | Bestehende Git-Hilfe, Suite-Lauf und Argument-Parser, an die der Modus anknüpft |
| `tests/test_release_check_93.py` | test | Vorbild für Teststil (echte Git-Repos auf `tmp_path`), bleibt grün |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| `scripts/release_check.py` | MODIFY | Pure Funktion `decide_tested_proof`, Abruf-Funktion, Modus `--tested-proof <sha>` mit `PROOF=`/`REASON=`, Exit immer 0 |
| `.github/workflows/release.yml` | MODIFY | Berechtigungen `checks: read`, `pull-requests: read`; Nachweis-Schritt mit `GH_TOKEN`; Prüfschritt wählt `--no-tests` oder volle Suite |
| `tests/test_release_tested_proof_633.py` | CREATE | Tests aller ACs: Entscheidung, echter Baumvergleich auf tmp-Repos, CLI, Workflow-Struktur |
| `CHANGELOG.md` | MODIFY | Eintrag unter `[Unreleased]`, keine Versionsnummer |

### Estimated Changes

- Files: 4 (Grenze 5)
- LoC: Produktivcode ca. +110/-3 (Grenze ±250), Tests ca. +200
- Keine Gate-Lockerung bei den inhaltlichen Prüfungen: Branch, Arbeitsbaum, Abgleich, Version, README, CLAUDE.md, Tag, Skills, Cloud-Hooks und Cloud-Agenten laufen in beiden Fällen.

## Implementation Details

**1. Entscheidung (pure).** `decide_tested_proof(sha, prs, check_runs, head_tree, merge_tree)` liefert `(bool, str)` und kennt weder Netz noch Git. `yes` nur wenn alle Bedingungen gelten:

- `prs` enthält genau einen PR mit gesetztem `merged_at` und `merge_commit_sha == sha` (andere PRs zum Commit zählen nicht mit, mehrere passende → no).
- Unter den Check-Runs mit Namen `tests` auf dem Head des PR ist jeder `completed` und `success`, und es gibt mindestens einen. Ein nicht erfolgreicher oder noch laufender `tests`-Run → no.
- `head_tree` und `merge_tree` sind nicht leer und gleich.

Jede nicht erfüllte Bedingung liefert `False` mit einem Grund in einem Satz.

Zusätzlich verlangt `--tested-proof <sha>`, dass der Baum des ausgecheckten `HEAD` (`REPO_ROOT`) gleich dem Baum von `<sha>` ist, sonst `PROOF=no` mit Grund „ausgecheckter Stand weicht ab“ (fail-closed, weil `release.yml` `main` auscheckt und nicht `github.sha`).

**2. Abruf (getrennt).** `fetch_tested_proof_inputs(sha)` ruft `gh api` für die PR-Liste und die Check-Runs, holt per `git fetch origin refs/pull/<N>/head` den Head und liest `git rev-parse <head>^{tree}` und `<sha>^{tree}`. Es gibt die Rohdaten an die pure Funktion; jeder Abruf-, Parse- oder Git-Fehler, fehlendes `gh` oder fehlendes Token wird als Fehlergrund zurückgegeben statt als Ausnahme.

**3. Modus.** `release_check.py --tested-proof <sha>` druckt genau `PROOF=yes|no` und `REASON=<Grund>`, Exit-Code immer 0 (das Ergebnis steht in der Ausgabe, nie im Exit-Code, damit ein Fehler im Nachweis den Workflow nicht abbricht). Fail-closed: Jede Unsicherheit ergibt `PROOF=no`.

**4. Workflow.** Vor dem Prüfschritt läuft ein Schritt „Tested-Nachweis“ mit `GH_TOKEN`, der `--tested-proof ${{ github.sha }}` aufruft und `proof=yes|no` nach `$GITHUB_OUTPUT` schreibt. Der Prüfschritt ist in zwei Schritte geteilt: bei `proof == 'yes'` läuft `python3 scripts/release_check.py --no-tests`, bei `proof != 'yes'` läuft `python3 scripts/release_check.py` (volle Suite). Die Berechtigungen werden um `checks: read` und `pull-requests: read` ergänzt.

**5. Rückwärtsverträglichkeit.** Alle bisherigen Modi (`--no-tests`, `--notes`, `--tag`, `--pr-gate`) und Tests aus `tests/test_release_check_93.py` bleiben unverändert.

## Expected Behavior

- **Input:** Commit-SHA des Release-Laufs (`github.sha`) und der Zugriff auf GitHub-API und `origin`.
- **Output:** `PROOF=yes` plus Grund (z. B. „PR #631, tests grün auf c1f70ac, Baum identisch“) oder `PROOF=no` plus Grund; Workflow startet die volle Suite nur bei `no`.
- **Side effects:** Ein `git fetch` des PR-Heads in das Checkout des Release-Laufs; nichts wird geschrieben oder veröffentlicht.

## Known Limitations

- Ein Merge per „Create a merge commit“ oder Rebase hat keinen Merge-Commit mit gleichem Baum zum PR-Head, wenn main zwischenzeitlich weiterging; dann ist der Baum verschieden und die volle Suite läuft (gewollt, fail-closed).
- Direkt-Push auf main ohne PR führt immer zu `PROOF=no` und damit zur vollen Suite.
- Der Nachweis stützt sich auf den Check-Run `tests`; wird der Job umbenannt, läuft bis zur Anpassung immer die volle Suite (sicher, nur langsamer).

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] Ein Release-PR, der mit grünem `tests` und unverändertem Baum gemergt wird, veröffentlicht in 1–2 min statt nach rund 11 min; in jedem anderen Fall läuft die volle Suite wie bisher
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (`tests/test_release_check_93.py` und Regressionslauf grün)
- [ ] CHANGELOG-Eintrag unter `[Unreleased]`; `python3 scripts/release_check.py --no-tests` grün

## Acceptance Criteria

- **AC-1:** Given genau ein gemergter PR mit `merge_commit_sha` gleich dem geprüften Commit, ein erfolgreicher Check-Run `tests` auf dessen Head und gleiche Baum-SHAs von Head und Merge-Commit / When die Entscheidung `decide_tested_proof` läuft / Then lautet das Ergebnis yes mit einem Grund, der PR und Head nennt.
  - Test: tests/test_release_tested_proof_633.py::test_nachweis_yes_nur_wenn_alle_bedingungen_erfuellt
- **AC-2:** Given kein PR, mehrere passende gemergte PRs, ein PR ohne `merged_at` oder mit anderem `merge_commit_sha` / When die Entscheidung läuft / Then lautet das Ergebnis no mit Grund, und fremde PRs in der Liste zählen nicht als passend.
  - Test: tests/test_release_tested_proof_633.py::test_nachweis_no_bei_pr_mehrdeutig_oder_fehlend
- **AC-3:** Given der Check-Run `tests` fehlt, läuft noch, ist rot oder einer von mehreren `tests`-Runs ist nicht erfolgreich / When die Entscheidung läuft / Then lautet das Ergebnis no mit Grund.
  - Test: tests/test_release_tested_proof_633.py::test_nachweis_no_bei_check_fehlt_laeuft_oder_rot
- **AC-4:** Given zwei echte Git-Repos auf `tmp_path`, einmal mit gleichem Baum von PR-Head und Merge-Commit (Squash eines aktuellen Branches) und einmal mit abweichendem Baum (main ging zwischenzeitlich weiter) / When der Abruf die Baum-SHAs ermittelt und die Entscheidung läuft / Then ist das Ergebnis bei gleichem Baum yes und bei abweichendem Baum no mit Grund „Baum“.
  - Test: tests/test_release_tested_proof_633.py::test_baumvergleich_auf_echten_git_repos
- **AC-5:** Given ein Fehler beim Abruf (fehlendes `gh`, kein Token, nicht parsbare Antwort, fehlgeschlagener `git fetch`) / When `release_check.py --tested-proof <sha>` läuft / Then gibt der Modus `PROOF=no` und `REASON=<Grund>` aus, der Exit-Code ist 0 und es entsteht keine Ausnahme nach außen.
  - Test: tests/test_release_tested_proof_633.py::test_cli_fail_closed_bei_abruffehler
- **AC-6:** Given `release.yml` / When die Datei als YAML geparst wird / Then startet die volle Suite (`release_check.py` ohne `--no-tests`) nur im Fall `proof != 'yes'`, `--no-tests` nur im Fall `proof == 'yes'`, der Nachweis-Schritt trägt `GH_TOKEN` und ruft `--tested-proof ${{ github.sha }}` auf, und die Berechtigungen enthalten `checks: read` und `pull-requests: read`.
  - Test: tests/test_release_tested_proof_633.py::test_release_workflow_struktur_proof_steuert_suite
- **AC-7:** Given die bestehenden Release-Wächter-Tests / When `tests/test_release_check_93.py` und die Modi `--no-tests`, `--notes`, `--tag`, `--pr-gate` laufen / Then bleiben sie grün und unverändert im Verhalten, und alle inhaltlichen Prüfungen laufen auch bei `PROOF=yes`.
  - Test: tests/test_release_tested_proof_633.py::test_inhaltliche_pruefungen_laufen_auch_ohne_suite

## Test Plan

Automatische Tests (jeweils an eine AC oben gebunden):
- `python3 -m pytest tests/test_release_tested_proof_633.py -q` (im venv): AC-1 bis AC-7.
- `python3 -m pytest tests/test_release_check_93.py -q`: Regression des Wächters (AC-7).

### Automated Tests (TDD RED)

- [ ] Test 1: GIVEN ein passender gemergter PR, grüner `tests`-Run und gleiche Bäume WHEN `decide_tested_proof` läuft THEN yes mit Grund.
- [ ] Test 2: GIVEN keinen, mehrere oder nicht passende PRs WHEN die Entscheidung läuft THEN no mit Grund.
- [ ] Test 3: GIVEN fehlenden, laufenden, roten oder teilweise roten `tests`-Check WHEN die Entscheidung läuft THEN no.
- [ ] Test 4: GIVEN echte tmp-Repos mit gleichem und abweichendem Baum WHEN Baum-SHAs gelesen und verglichen werden THEN yes bzw. no.
- [ ] Test 5: GIVEN Abruffehler (`gh` fehlt, Token fehlt, Müll-JSON, Fetch scheitert) WHEN `--tested-proof` läuft THEN `PROOF=no`, `REASON=`, Exit 0.
- [ ] Test 6: GIVEN `release.yml` WHEN geparst THEN Bedingungen, `GH_TOKEN`, Aufruf und Berechtigungen wie in AC-6.
- [ ] Test 7: GIVEN `--no-tests` WHEN der Wächter läuft THEN laufen Branch-, Version-, Tag-, Skills- und Cloud-Prüfungen weiterhin.

RED-Artefakt: `docs/artifacts/633-red.log`.

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Es entsteht keine neue Architektur. Die bestehende Regel „Release nur mit grüner Suite auf genau diesem Baum“ bleibt gültig; der Nachweis darf aus einem identischen, bereits im PR getesteten Baum stammen. Verworfen sind Alternative B (`release.yml` hängt sich per `workflow_run` an den `tests`-Lauf auf main: wartet dieselben rund 11 min, nur an anderer Stelle) und Alternative C (Tests im Release ganz streichen: ein Direkt-Push auf main oder ein veralteter Branch würde ungetestet veröffentlicht; bei Wahl von C fiele die Regel „Release verlangt grüne Suite auf genau diesem Baum“). Fail-closed bleibt tragend: jeder Fehler beim Nachweis führt zur vollen Suite, nie zur Abkürzung.

## Changelog

- 1.0 (2026-11-21): Erstfassung nach PO-Frage (#633), Variante A gewählt.
