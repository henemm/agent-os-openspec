---
entity_id: fix-965-ac-n-parse
type: bugfix
created: 2026-07-08
updated: 2026-07-08
status: draft
version: "1.0"
tags: [bugfix, hooks, adversary-dialog, spec-parsing, consumer-projects]
test_targets:
  - core/hooks/adversary_dialog.py
  - tests/test_adversary_dialog_parse.py
---

# Fix #965: AC-N-Format wird von adversary_dialog.py nicht geparst

## Approval

- [ ] Approved

## GitHub Issue

- **Issue:** gregor_zwanzig#965 (Consumer-Projekt, in dem der Bug entdeckt wurde)

## Purpose

Behebt einen Bug in `core/hooks/adversary_dialog.py`, durch den
`parse_spec_expected_behavior()` ausschließlich das alte
`## Expected Behavior`-Bullet-Format erkennt. Das seit Epic #191
(gregor_zwanzig) vorgeschriebene AC-N-Format
(`## Acceptance Criteria` mit `- **AC-N:** Given.../When.../Then...`, oft
mehrzeilig, teils mit Klammer-Zusätzen und eingerückten `- Test:`-Sub-Bullets)
wird komplett übersehen — der Adversary-Dialog erhält "Keine
Expected-Behavior-Punkte gefunden." statt der tatsächlichen Checkliste und
muss manuell aus der Spec extrahiert werden.

## Source

- **File:** `core/hooks/adversary_dialog.py`
- **Identifier:** `parse_spec_expected_behavior()` (Zeile 52-93)

## Dependencies

| Komponente | Typ | Abhängigkeit |
|-----------|-----|-------------|
| `core/commands/50-implement.md` (Zeile 186) | Aufrufer | Ruft `adversary_dialog.py parse <spec-pfad>` während der Implementierungsphase auf — Hauptverbraucher der Funktion |
| `core/agents/implementation-validator.md` (Zeile 76) | Konsument | Referenziert `adversary_dialog.py schema`, nutzt implizit die geparste Checkliste als Grundlage für Findings |
| `create_checklist()` (`core/hooks/adversary_dialog.py`) | Downstream-Funktion | Nimmt weiterhin nur `list[str]` entgegen — keine Signaturänderung nötig, rein additive Erweiterung |
| `templates/spec_template.md` | Format-Quelle | Nutzt bereits `## Acceptance Criteria` (Zeile 63) statt `## Expected Behavior` — Vorlage ist dem Parser bereits vorausgeeilt |
| `docs/specs/qa-gate-path-resolution.md`, `bash-gate-false-positive-fix.md`, u.a. (~10 Dateien) | Reale Testfixtures | Liefern die tatsächliche Formatvariation für Regressionstests |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|--------------|
| `core/hooks/adversary_dialog.py` | MODIFY | `parse_spec_expected_behavior()` (Zeile 52-93) auf State-Machine umgebaut: Section-Typ-Tracking (`expected_behavior`/`acceptance_criteria`), neuer AC-N-Bullet-Erkennungszweig mit Klammer-Toleranz, Fortsetzungszeilen-Handling über Einrückung der Rohzeile, Sub-Bullet-Ausschluss, additiver Merge beider Sections |
| `tests/test_adversary_dialog_parse.py` | CREATE | ~8-12 Fälle: AC-only, EB-only, beide koexistierend, geklammertes AC-Label, Sub-Bullet-Ausschluss, Soft-Wrap-Fortsetzung, leere Datei/keine Section, plus Regressionsfixtures gegen 3 echte Specs |

### Estimated Changes

- Files: 2 (1 MODIFY + 1 CREATE)
- LoC: +150/-0 bis +200/-10 (Funktion wächst um ~40-60 LoC, Testdatei ~100-150 LoC)
- Risk Level: LOW (additiv, kein Caller muss geändert werden)

## Root Cause

`parse_spec_expected_behavior()` erkennt eine Section ausschließlich per
Regex `^##\s+Expected Behavior` (case-insensitive) und akzeptiert als Bullet
nur Zeilen, die (nach `.strip()`) mit `- ` oder `\d+. ` beginnen — ohne
Multi-Line-Support. Das AC-N-Format unterscheidet sich strukturell:

1. Die Section heißt `## Acceptance Criteria`, nicht `## Expected Behavior`
   — der bestehende Section-Regex matcht sie nie, die Funktion liefert eine
   leere Liste zurück.
2. Reale AC-N-Einträge sind oft über mehrere Zeilen weich umgebrochen (z.B.
   `qa-gate-path-resolution.md` AC-1); die Fortsetzungszeilen tragen KEIN
   `-`-Präfix. Ein 1:1-Analogon zum bestehenden Zweig würde nur den ersten
   Teilsatz jedes AC erfassen.
3. Unter jedem AC hängt oft ein eingerückter `- Test: ...`-Sub-Bullet (siehe
   `templates/spec_template.md` Zeile 66/69). Nach `.strip()` beginnt auch
   diese Zeile mit `- ` — ein naiver Bullet-Regex würde sie fälschlich als
   eigenen, zusätzlichen Checklist-Punkt zählen.
4. Manche AC-Labels tragen Klammer-Zusätze (`- **AC-8 (präzisiert):**`,
   belegt in `bash-gate-false-positive-fix.md:253`) — ein starrer
   `AC-\d+:`-Regex ohne Klammer-Toleranz würde diese nicht matchen.

**Symptom:** Für Specs im AC-N-Format (mittlerweile ~10 Dateien im Repo)
liefert `adversary_dialog.py parse <spec>` "Keine Expected-Behavior-Punkte
gefunden." — der Adversary-Dialog verliert seine automatisch generierte
Checkliste und muss die ACs manuell aus der Spec extrahieren, obwohl die
Spec formal vollständig ist.

## Implementierungsdetails

### State-Machine statt einfachem `in_section`-Bool

```python
# Section-Start zusätzlich für Acceptance Criteria erkennen:
if re.match(r"^##\s+Expected Behavior", stripped, re.IGNORECASE):
    section = "expected_behavior"
    continue
if re.match(r"^##\s+Acceptance Criteria", stripped, re.IGNORECASE):
    section = "acceptance_criteria"
    continue
if section and re.match(r"^##\s+", stripped):
    section = None
```

### Neuer AC-N-Bullet-Regex mit Klammer-Toleranz

Ein neuer AC-Punkt beginnt bei einer **unindentierten** Zeile, die
`^-\s+\*\*AC-\d+[^*:]*:\*\*` matcht. Die Zeichenklasse `[^*:]*` deckt
Varianten wie `- **AC-8 (präzisiert):**` ab.

### Unterscheidung Sub-Bullet vs. Fortsetzungszeile über Einrückung der Rohzeile

Die Prüfung erfolgt auf der **ungestrippten** Zeile (nicht auf `stripped`):

- Eingerückt (führendes Whitespace in der Rohzeile) + beginnt (nach Strip)
  mit `-` → Sub-Bullet (z.B. `  - Test:`), wird verworfen.
- Eingerückt + beginnt NICHT mit `-` → Fortsetzungszeile, wird an den
  aktuellen AC-Punkt angehängt (`.strip()`, mit Leerzeichen verbunden).
- Unindentiert + matcht den AC-Bullet-Regex → neuer Punkt.

Robust, weil AC-Bullets in allen geprüften Specs exakt bei Spalte 0 stehen.

### Additiver Merge bei Koexistenz beider Sections

Beide Listen werden additiv konkatenieren (Expected-Behavior-Punkte zuerst,
dann Acceptance-Criteria-Punkte), keine Priorisierungs-Heuristik nötig.

### Normalisierung

Ein String pro AC-Punkt, Label `**AC-N:**` bleibt im Ergebnisstring erhalten
(Traceability für den Adversary-Dialog).

### Unverändert

Der bestehende `Expected Behavior`-Zweig (Section-Erkennung, Single-Line-
Bullet-Sammlung) bleibt vollständig unverändert — kein Beleg für Soft-Wrap
dort, Scope-Disziplin.

## Expected Behavior

- **Input:** Pfad zu einer Spec-Datei (`.md`), die entweder `##
  Expected Behavior`, `## Acceptance Criteria`, beide, oder keine der beiden
  Sections enthält.
- **Output bei reinem AC-N-Format:** Liste von Strings, ein Eintrag pro
  `AC-N:`-Bullet, inklusive Fließtext-Fortsetzungszeilen, exklusive
  eingerückter `- Test:`-Sub-Bullets.
- **Output bei Koexistenz beider Sections:** Additiv zusammengeführte Liste
  — zuerst alle Expected-Behavior-Punkte, danach alle Acceptance-Criteria-
  Punkte.
- **Output bei reinem Expected-Behavior-Format (Regression):** Identisch zum
  bisherigen Verhalten — keine Verhaltensänderung für bestehende Specs.
- **Output bei fehlender Datei oder fehlender Section:** Leere Liste (wie
  bisher).
- **Side effects:** Keine — reine Lesefunktion ohne Schreibzugriff.

## Error Handling

- Datei existiert nicht → `path.exists()`-Check liefert weiterhin leere
  Liste (unverändertes Verhalten).
- Weder `## Expected Behavior` noch `## Acceptance Criteria` vorhanden →
  leere Liste, kein Fehler.
- Malformed AC-Zeile (z.B. `AC-N:` ohne führendes `**`) wird schlicht nicht
  als Bullet erkannt und ignoriert — keine Exception, konsistent mit dem
  bestehenden `Expected Behavior`-Zweig, der ebenfalls nicht-matchende
  Zeilen stillschweigend überspringt.

## Known Limitations

- Fließtext einer AC, der selbst mit `-` beginnt (z.B. ein Aufzählungspunkt
  innerhalb der AC-Beschreibung), würde fälschlich als Sub-Bullet verworfen
  statt als Fortsetzung angehängt zu werden. In allen geprüften Specs im
  Repo nicht vorhanden — wird dokumentiert, nicht gelöst.
- Der Fix behandelt ausschließlich `parse_spec_expected_behavior()`. Andere
  Konsumenten der Spec-Datei (z.B. `spec-validator`-Agent) sind nicht
  betroffen und werden hier nicht angefasst.
- Keine Priorisierungs-Heuristik bei Koexistenz beider Sections — reine
  additive Konkatenation, keine Deduplizierung, falls dieselbe Aussage in
  beiden Sections vorkäme (in den geprüften Specs nicht der Fall).

## Acceptance Criteria

- **AC-1:** Given eine Spec-Datei mit ausschließlich einer `##
  Acceptance Criteria`-Section mit Standard-`- **AC-N:** Given.../
  When.../Then...`-Bullets (keine Klammer-Zusätze, keine Sub-Bullets,
  keine Soft-Wraps) / When `parse_spec_expected_behavior()` auf diese Datei
  angewendet wird / Then liefert die Funktion eine Liste mit genau einem
  Eintrag pro AC-N-Bullet, in Dateireihenfolge, jeweils inklusive des
  `AC-N:`-Labels.

- **AC-2:** Given eine Spec-Datei mit einem AC-Label mit Klammer-Zusatz
  (`- **AC-8 (präzisiert):** Given.../When.../Then...`) / When
  `parse_spec_expected_behavior()` diese Datei parst / Then wird dieser
  Eintrag trotzdem als eigenständiger Punkt erkannt und in der
  Ergebnisliste geführt, statt übersprungen zu werden.

- **AC-3:** Given ein mehrzeiliger AC-Eintrag, dessen zweite (und weitere)
  Zeile(n) mit Fließtext ohne `-`-Präfix fortgesetzt werden (Soft-Wrap,
  z.B. wie in `docs/specs/qa-gate-path-resolution.md` AC-1) / When
  `parse_spec_expected_behavior()` diese Datei parst / Then landet der
  vollständige, über mehrere Zeilen verteilte Text (Erstzeile plus alle
  Fortsetzungszeilen, mit Leerzeichen verbunden) in genau einem
  Listeneintrag statt in mehreren oder abgeschnitten.

- **AC-4:** Given ein AC-Eintrag mit einem eingerückten `  - Test: ...`-
  Sub-Bullet direkt darunter / When `parse_spec_expected_behavior()` diese
  Datei parst / Then erscheint der Sub-Bullet-Text NICHT als eigener
  Eintrag in der Ergebnisliste — die Ergebnisliste enthält für diesen AC
  genau einen Eintrag (den AC-Text selbst, ohne den Test-Verweis).

- **AC-5:** Given eine Spec-Datei, die sowohl `## Expected Behavior` als
  auch `## Acceptance Criteria` mit jeweils eigenen Bullet-Punkten enthält
  / When `parse_spec_expected_behavior()` diese Datei parst / Then enthält
  die Ergebnisliste additiv beide Punktmengen — zuerst alle Expected-
  Behavior-Punkte in Dateireihenfolge, danach alle Acceptance-Criteria-
  Punkte in Dateireihenfolge, ohne dass einer der beiden Sätze fehlt oder
  dedupliziert wird.

- **AC-6:** Given eine Spec-Datei im bisherigen, ausschließlichen `##
  Expected Behavior`-Format (keine `## Acceptance Criteria`-Section) / When
  `parse_spec_expected_behavior()` diese Datei nach dem Fix parst / Then
  liefert die Funktion exakt dieselbe Ergebnisliste wie vor dem Fix (keine
  Regression im bestehenden Zweig).

- **AC-7:** Given eine echte, unveränderte Spec-Datei aus dem Repo im
  AC-N-Format (`docs/specs/qa-gate-path-resolution.md`) / When
  `parse_spec_expected_behavior()` auf diese Datei angewendet wird / Then
  liefert die Funktion eine nicht-leere Liste mit genau 5 Einträgen (AC-1
  bis AC-5 aus dieser Datei), keinem der `- Test:`- oder Code-Block-
  Fragmente als zusätzlichem Eintrag.

## Test Plan

### Automated Tests (TDD RED)

- [ ] Test 1 (deckt AC-1 ab): GIVEN eine `tmp_path`-Fixture-Datei mit
      `## Acceptance Criteria` und 3 Standard-`AC-N:`-Bullets (Single-Line)
      WHEN `parse_spec_expected_behavior(path)` aufgerufen wird THEN liefert
      es eine Liste der Länge 3, jeder Eintrag beginnt mit `AC-1:`/`AC-2:`/
      `AC-3:` in dieser Reihenfolge.
- [ ] Test 2 (deckt AC-2 ab): GIVEN eine Fixture mit
      `- **AC-8 (präzisiert):** ...` WHEN geparst wird THEN ist ein Eintrag
      in der Liste, dessen Text `AC-8` und den restlichen Bullet-Inhalt
      enthält.
- [ ] Test 3 (deckt AC-3 ab): GIVEN eine Fixture mit einem AC-Bullet, dessen
      zweite Zeile eingerückter Fließtext ohne `-` ist WHEN geparst wird
      THEN enthält der resultierende Listeneintrag beide Zeilenanteile
      zusammengefügt (Prüfung per Substring-Check auf Text aus beiden
      Zeilen im selben Listeneintrag).
- [ ] Test 4 (deckt AC-4 ab): GIVEN eine Fixture mit einem AC-Bullet gefolgt
      von `  - Test: *(populated after TDD RED phase)*` WHEN geparst wird
      THEN hat die Ergebnisliste für diesen AC genau einen Eintrag, kein
      zusätzlicher Eintrag beginnend mit `Test:`.
- [ ] Test 5 (deckt AC-5 ab): GIVEN eine Fixture mit sowohl `##
      Expected Behavior` (2 Bullets) als auch `## Acceptance Criteria`
      (2 AC-Bullets) WHEN geparst wird THEN liefert es eine Liste der Länge
      4 in der Reihenfolge Expected-Behavior zuerst, dann Acceptance-
      Criteria.
- [ ] Test 6 (deckt AC-6 ab): GIVEN eine Fixture ausschließlich im alten
      `## Expected Behavior`-Format WHEN vor und nach dem Fix geparst wird
      THEN ist das Ergebnis identisch (Regressionstest gegen fixiertes
      Erwartungsergebnis).
- [ ] Test 7 (deckt AC-7 ab): GIVEN die echte Datei
      `docs/specs/qa-gate-path-resolution.md` im Repo WHEN
      `parse_spec_expected_behavior()` darauf angewendet wird THEN liefert
      es eine Liste der Länge 5.
- [ ] Test 8 (Edge Case): GIVEN eine leere Datei oder eine Datei ohne
      `## Expected Behavior`/`## Acceptance Criteria`-Section WHEN geparst
      wird THEN liefert es eine leere Liste, keine Exception.
- [ ] Test 9 (Regression, zusätzliche echte Spec): GIVEN
      `docs/specs/bash-gate-false-positive-fix.md` (enthält Klammer-Zusatz-
      AC) WHEN geparst wird THEN liefert es eine nicht-leere Liste mit
      korrekt erkanntem `AC-8 (präzisiert)`-Eintrag.
- [ ] Test 10 (Regression, Template): GIVEN `templates/spec_template.md`
      WHEN geparst wird THEN liefert es genau 2 Einträge (AC-1, AC-2 aus
      der Vorlage), keine `- Test:`-Sub-Bullets als eigenen Eintrag.

### Test-Implementierung

Neue Datei `tests/test_adversary_dialog_parse.py`, mock-freies Pattern über
`tmp_path`-Fixture-Dateien und Regressionschecks gegen echte Repo-Specs
(kein Mocking von Dateisystem-Zugriffen):

```python
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "core" / "hooks"))
from adversary_dialog import parse_spec_expected_behavior


def test_ac_n_format_single_line(tmp_path):
    spec = tmp_path / "spec.md"
    spec.write_text(
        "## Acceptance Criteria\n\n"
        "- **AC-1:** Given a / When b / Then c\n\n"
        "- **AC-2:** Given d / When e / Then f\n\n"
        "- **AC-3:** Given g / When h / Then i\n"
    )
    points = parse_spec_expected_behavior(str(spec))
    assert len(points) == 3
    assert points[0].startswith("**AC-1:**")


def test_real_spec_qa_gate_path_resolution():
    spec = REPO_ROOT / "docs" / "specs" / "qa-gate-path-resolution.md"
    points = parse_spec_expected_behavior(str(spec))
    assert len(points) == 5
```

Ausführung:

```bash
python3 -m pytest tests/test_adversary_dialog_parse.py -v
```

## Changelog

- 2026-07-08: Initial spec erstellt für gregor_zwanzig#965
