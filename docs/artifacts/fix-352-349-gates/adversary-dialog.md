# Adversary Dialog — fix-352-349-gates
Spec: docs/specs/fix-352-349-gates.md
Datum: 2026-10-05 08:00

## Checkliste
- [x] **Input #352:** `git commit` bei laufendem Merge von `origin/main` mit gelösten Konflikten.
- [x] **Output #352:** Commit wird nicht von 5b geblockt; unvollständiger Merge bleibt geblockt, Meldung ohne `--autostash`.
- [x] **Input #349:** RED-Artefakt mit spec-Reporter-Ausgabe (`ℹ tests 3`, `ℹ todo 0`, `ℹ fail 1`).
- [x] **Output #349:** Kein Platzhalter-Block durch die Summary-Zeilen; echte Platzhalter im Rahmen blocken weiter.
- [x] **Side effects:** keine.
- [x] **AC-1:** Given ein Wegwerf-Repo mit Rückstand zu `origin/main` und einem durchgeführten `git merge --no-commit --no-ff origin/main` (`MERGE_HEAD` gesetzt, `MERGE_HEAD..origin/main` = 0) / When das Gate `git commit -m x` prüft / Then blockt 5b nicht (Exit 0)
- [x] **AC-2:** Given ein laufender Merge, der `origin/main` nicht vollständig hereinholt (`MERGE_HEAD..origin/main` > 0) / When das Gate `git commit` prüft / Then blockt es (Exit 2), die Meldung nennt `git merge origin/main` und enthält **nicht** `--autostash`
- [x] **AC-3:** Given kein laufender Merge und Rückstand > 0 / When das Gate `git commit` prüft / Then blockt es wie bisher mit der `--autostash`-Meldung (Verhalten unverändert)
- [x] **AC-4:** Given `rev-parse` für `MERGE_HEAD` schlägt mit Timeout bzw. `OSError` fehl / When das Gate `git commit` prüft / Then fällt es auf den alten Pfad (Basis `HEAD`) zurück und stürzt nicht ab
- [x] **AC-5:** Given die Ausgabe eines echten `node --test --test-reporter=spec`-Laufs mit einem roten Test / When `tdd_enforcement._find_placeholder` sie prüft / Then liefert es `None` (die Zeile `ℹ todo 0` löst keinen Block aus)
- [x] **AC-6:** Given eine Ausgabe im Runner-Rahmen mit einem echten Platzhalter (z. B. `TODO: fill in`) neben spec-Reporter-Summary-Zeilen / When `_find_placeholder` sie prüft / Then wird der echte Platzhalter weiterhin gefunden
- [x] **AC-7:** Given die TAP-Form (`# todo 0`) / When `_find_placeholder` sie prüft / Then liefert es weiterhin `None` (Bestandsverhalten aus #73 bleibt)

## Dialog

### Runde 1
**Adversary:** Ich fordere für jeden Punkt Beweis. Testlauf: 56 passed, 0 failed, 0 skipped (beide neuen Dateien plus Regression 299, 26_38_34, tdd_enforcement_*). Der Test für AC-5 braucht node und läuft real, also nicht übersprungen. Angriffe auf #352:
(a) Merge eines anderen Branches als origin/main bei Rückstand.
(b) MERGE_HEAD im Worktree.
(c) Fehler bei rev-list.
(d) Ob die Meldung im Merge-Fall `--autostash` enthält.
(e) Ob das Gate bei laufendem Merge pauschal durchlässt.
**Implementierer:** Aus dem Code, nicht per Lauf bestätigt (der Sandbox-Guard lehnte die Wegwerf-Repo-Skripte des Prüfers ab; der Worktree-Fall (b) ist zusätzlich durch den Test `test_abschliessender_merge_im_worktree_wird_durchgelassen` belegt):
(a) bash_gate.py:888 blockt bei `basis == "MERGE_HEAD"` und `behind > 0`. Ein Merge eines fremden Branches, der origin/main nicht enthält, bleibt also geblockt, mit Merge-Rat. Kein Überspringen von 5b (vgl. verworfene ADR-Alternative a).
(b) MERGE_HEAD ist pro Worktree. `rev-parse` läuft mit `cwd=os.getcwd()` und sieht deshalb den Merge-Stand des aktuellen Worktrees.
(c) Bei einem rev-list-Fehler ist stdout leer, also `int("0")` und kein Block. Das ist dasselbe fail-open wie vorher.
(d) Die Merge-Meldung enthält kein `--autostash`; das steht nur im unveränderten Zweig. Die Tests AC-2 und AC-3 belegen beides.
(e) Kein pauschaler Durchlass: AC-2 (unvollständiger Merge, rc=2) ist grün.
Befund: AC-1 bis AC-4 belegt, alle Tests grün. Der innere except-Zweig wird vom Test `test_rev_parse_timeout_faellt_auf_head_zurueck` per git-Shim real getroffen.

### Runde 2
**Adversary:** Frühe Einigkeit ist verdächtig, also gezielt auf #349. `_find_placeholder` wurde real mit Varianten aufgerufen:
- `ℹ todo 0\nℹ fail 1` ergibt None (gut).
- `# todo 0` ergibt None (AC-7).
- `ℹ tests 3\nTODO: fill in` ergibt (2, 'TODO: fill in'), der echte Platzhalter wird gefunden (AC-6).
- `ℹ TODO fill in` ergibt einen Fund: Die Regex ist nicht case-insensitive, es blockt weiterhin.
- `ℹ todo: fill in the test` und `ℹ todo 0 TODO fill in` ergeben None: Die Zeile wird als Summary entfernt, weil `\b.*$` den Rest schluckt. Identisch zum Bestand der TAP-Form.
- `  ℹ todo 0` (eingerückt) ergibt einen Fund, weil `^` keine Einrückung zulässt. Identisch zur TAP-Form; node schreibt die Summary in Spalte 0.
Die Fehler-Evidenz `_FAILURE_RE` läuft weiter auf dem Original, eine `ℹ fail 1`-Zeile bleibt also Evidenz.
**Implementierer:** Die Erweiterung auf `[#ℹ]` bringt keine neue Angriffsfläche, die über #73 hinausgeht: Die Schlüsselwortliste ist unverändert, nur das Präfix ist erweitert. Dass hinter einem Summary-Schlüsselwort beliebiger Text folgen darf, ist bestehendes Verhalten von `\b.*$`. Wird als LOW dokumentiert, nicht als Spec-Verstoß.

Finding:
  ID: F001
  Severity: LOW
  Category: edge_case
  Code reference: core/hooks/tdd_enforcement.py:88
  Description: `_TAP_SUMMARY_RE` entfernt jede Zeile, die mit `#` oder `ℹ`, Whitespace und einem Summary-Schlüsselwort beginnt, samt Rest der Zeile (`.*$`). `ℹ todo: fill in the test` und `ℹ todo 0 TODO fill in` liefern deshalb `None`.
  Spec requirement: AC-6 — ein echter Platzhalter im Runner-Rahmen wird weiterhin gefunden
  Conflict: Ein Platzhalter hinter einem Summary-Keyword in derselben Zeile wird nicht gefunden. Für `#` bestand diese Lücke bereits vor dem Fix (Parität). Echte Platzhalter auf eigener Zeile werden gefunden. Praktisch kaum ausnutzbar, weil das Artefakt zusätzlich echte Fehler-Evidenz braucht.
  Remediation: Optional die Regex auf Zahlenwerte einschränken. Gehört nicht in dieses Ticket.

Finding:
  ID: F002
  Severity: LOW
  Category: edge_case
  Code reference: core/hooks/bash_gate.py:884
  Description: Wenn `rev-list --count` fehlschlägt oder leer ausgibt, wird `behind` zu 0 und 5b lässt durch. Auch im neuen MERGE_HEAD-Zweig gilt damit fail-open.
  Spec requirement: AC-4 — Fehler im neuen Pfad stürzen nicht ab, alter Pfad bleibt
  Conflict: Kein Verstoß. Verhalten unverändert zum Bestand und von der Spec so vorgegeben.
  Remediation: Keine; bewusst fail-open.

Confirmation:
  AC: AC-1
  Code reference: core/hooks/bash_gate.py:872
  Evidence: Z. 872-882 setzen `basis = "MERGE_HEAD"`, wenn `rev-parse -q --verify MERGE_HEAD` rc 0 liefert. Z. 884 misst `MERGE_HEAD..origin/main`, bei 0 greift kein Block. Tests test_abschliessender_merge_commit_wird_durchgelassen und test_abschliessender_merge_im_worktree_wird_durchgelassen grün.
  Status: CONFIRMED

Confirmation:
  AC: AC-2
  Code reference: core/hooks/bash_gate.py:888
  Evidence: `behind > 0 and basis == "MERGE_HEAD"` blockt mit `git fetch origin && git merge origin/main`, ohne `--autostash`. Test test_unvollstaendiger_merge_blockt_ohne_autostash_rat grün.
  Status: CONFIRMED

Confirmation:
  AC: AC-3
  Code reference: core/hooks/bash_gate.py:873
  Evidence: Ohne MERGE_HEAD bleibt `basis = "HEAD"`, und der unveränderte Zweig mit `git rebase --autostash origin/main` greift. Test test_ohne_merge_bleibt_rueckstand_block_unveraendert grün.
  Status: CONFIRMED

Confirmation:
  AC: AC-4
  Code reference: core/hooks/bash_gate.py:882
  Evidence: `except (subprocess.TimeoutExpired, OSError): basis = "HEAD"`. Ein rev-parse ohne verwertbare Ausgabe (rc 0, leer) führt ebenfalls zu HEAD. Tests test_rev_parse_fehler_faellt_auf_head_zurueck und test_rev_parse_timeout_faellt_auf_head_zurueck grün; der Timeout-Test fällt gegen eine Gate-Kopie ohne den except-Zweig durch.
  Status: CONFIRMED

Confirmation:
  AC: AC-5
  Code reference: core/hooks/tdd_enforcement.py:88
  Evidence: `^[#ℹ]\s*(tests|suites|pass|fail|cancelled|skipped|todo|duration_ms)\b.*$` wird in `_iter_frame_lines` (Z. 141) angewendet. Reale Eingabe `ℹ todo 0\nℹ fail 1` ergibt None. Test test_spec_reporter_summary_ist_kein_platzhalter grün (nicht übersprungen).
  Status: CONFIRMED

Confirmation:
  AC: AC-6
  Code reference: core/hooks/tdd_enforcement.py:146
  Evidence: `_find_placeholder` ergibt für `ℹ tests 3\nTODO: fill in` den Fund (2, 'TODO: fill in'). Test test_echter_platzhalter_blockt_weiterhin grün.
  Status: CONFIRMED

Confirmation:
  AC: AC-7
  Code reference: core/hooks/tdd_enforcement.py:141
  Evidence: `# todo 0` ergibt weiterhin None (Zeichenklasse enthält `#` unverändert). Test test_tap_summary_bleibt_unbeanstandet grün.
  Status: CONFIRMED

## Herkunft der Vorbedingungen

kein Sprachprofil konfiguriert (`precondition_origins.default_lang`)

## Verdict

═══════════════════════════════════════
VERDICT: VERIFIED
═══════════════════════════════════════
The implementation withstood adversary testing.
Tests: 56 passed, 0 failed, 0 übersprungen
Edge cases: Alle geprüft, keine gebrochen (F001/F002 nur LOW, Bestandsparität). Merge eines anderen Branches und rev-list-Fehler nur statisch aus dem Code abgeleitet.
Regressions: None found
Checklist: 12/12 points proven

## Geprüfte Dateien

- sha256:fb251defeb107e05faa93a9fa8e5b00bc75d4b72e30e9f168925af8796964585  core/hooks/bash_gate.py
- sha256:e7530df16c83b772cad99af37b4df4a2c9a5232614bdf9662de83fce2517396b  core/hooks/tdd_enforcement.py
