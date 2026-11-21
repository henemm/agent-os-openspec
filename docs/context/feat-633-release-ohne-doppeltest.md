# Context: feat-633-release-ohne-doppeltest

## Request Summary
Nach dem Merge eines Release-PRs wiederholt `.github/workflows/release.yml` die volle Testsuite (rund 11 min), obwohl derselbe Stand im PR schon grün war. PO 2026-11-21: „Muss das sein oder können wir nicht verzichten? Es war doch alles getestet.“ Ziel: Veröffentlichung in 1–2 min, wenn der getestete Stand nachweislich gleich ist, sonst wie bisher volle Suite (#633).

## Befund
- `release.yml`, Schritt „Release-Vorbedingungen pruefen“: `python3 scripts/release_check.py` ohne `--no-tests` → `release_check.py:253` startet `pytest tests/ -q`.
- 4.17.0: Release-Lauf 18:34:45 → Tag 18:44:02. Der PR #631 hatte `tests` auf Head c1f70ac grün (18:23:39–18:34:17). Squash-Merge dd0d962 enthält denselben Baum, weil der Branch aktuell auf main war.
- Der parallele `tests`-Lauf auf main (Push-Event) startet im selben Moment und dauert gleich lang, darauf zu warten spart nichts.

## Related Files
| File | Relevance |
|------|-----------|
| `.github/workflows/release.yml` | Release-Job; Checkout `ref: main`, `fetch-depth: 0`, Python 3.12, `GH_TOKEN` nur im Tag-Schritt |
| `scripts/release_check.py` | Wächter: Branch, Arbeitsbaum, Abgleich, Version, README, CLAUDE.md, Tag, Skills, Cloud-Hooks/-Agenten, Suite; Modi `--no-tests`, `--notes`, `--tag`, `--pr-gate` |
| `tests/test_release_check_93.py` | Tests gegen echte Git-Repos auf `tmp_path` (keine gemockten Git-Ausgaben) |
| `.github/workflows/*.yml` (Check `tests`) | Name des PR-Checks, der als Nachweis dient |

## Analyse
**Nachweis „derselbe Stand ist grün“:** (1) Zum Merge-Commit gehört genau ein gemergter PR (`GET /repos/{o}/{r}/commits/{sha}/pulls`). (2) Auf dessen Head-SHA ist der Check-Run `tests` `completed/success` (`GET /commits/{head}/check-runs?check_name=tests`). (3) `git rev-parse <head>^{tree}` == `git rev-parse <merge>^{tree}`; der Head wird per `git fetch origin refs/pull/<N>/head` geholt, weil der PR-Branch nach dem Merge gelöscht sein kann. Alle drei → `--no-tests`, sonst volle Suite.

**Empfehlung (Variante A):** Neue Funktion/Modus in `release_check.py` (z. B. `--tested-proof <sha>`), die nur Git und die GitHub-API (über `gh api`) nutzt und `PROOF=yes|no` mit Grund ausgibt. `release.yml` ruft sie mit `GH_TOKEN` auf und wählt danach `--no-tests` oder die volle Suite. Testbar: Baumvergleich gegen echte tmp-Repos, API-Antworten als eingespeiste JSON (Funktion trennt Abruf und Entscheidung).

**Alternative B:** `release.yml` hängt sich per `workflow_run` an den `tests`-Lauf auf main. Verworfen: wartet dieselben 11 min, nur an anderer Stelle.

**Alternative C:** Tests im Release ganz streichen. Verworfen: Direkt-Push auf main oder ein veralteter Branch würde ungetestet veröffentlicht. Würde C gewählt, fiele die ADR „Release verlangt grüne Suite auf genau diesem Baum“.

**ADR:** keine neue Architektur. Die bestehende Regel „Release nur mit grüner Suite“ bleibt; der Nachweis darf aus einem identischen, schon getesteten Baum stammen.

## Risks & Considerations
- Fail-closed: Jeder Fehler beim Nachweis (API, Fetch, fehlender Check) → volle Suite, nie Abkürzung.
- `GH_TOKEN` muss im Prüfschritt gesetzt sein; Berechtigung `contents: write` reicht für Check-Runs lesen? `checks: read` und `pull-requests: read` ergänzen.
- Mehrere PRs zum Commit: nur ein gemergter PR, dessen `merge_commit_sha` == SHA, zählt.
