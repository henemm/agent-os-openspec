---
entity_id: fix-60-69-gate-parsing
type: bugfix
created: 2026-07-17
updated: 2026-07-17
status: draft
version: "1.0"
tags: [bugfix, hooks, edit-gate, adversary-dialog, spec-parsing, worktree, consumer-projects]
test_targets:
  - core/hooks/edit_gate.py
  - core/hooks/adversary_dialog.py
  - core/hooks/hook_utils.py
  - tests/test_edit_gate_ac_check.py
  - tests/test_adversary_dialog_verdict.py
  - tests/test_adversary_dialog_parse.py
---

# Fix #60 / #69: Gate-Parsing — section-gebundener AC-Scan, Repo-Scoping, Worktree-Spec-Auflösung, letzter Verdict-Block

## Approval

- [ ] Approved

## GitHub Issue

- **Issue:** #60 (edit_gate AC-Längencheck matcht Prosa), #69 (Verdict-Parsing liest ersten statt letzten Block)
- **Consumer-Tracker:** henemm/gregor_zwanzig#1295

## Purpose

Behebt zwei naive globale Regex-Scans über strukturierte Markdown-Artefakte in `core/hooks/edit_gate.py` und `core/hooks/adversary_dialog.py`, die beide seit 2026-07-08 wiederholt fälschlich blockieren bzw. einen veralteten Zwischenstand statt des finalen Ergebnisses lesen. Konsolidiert die AC-Erkennung dabei in eine einzige geteilte Funktion, damit dieselbe Klasse von Fehler nicht ein zweites Mal an einer dritten Stelle entsteht.

## Source

- **File:** `core/hooks/edit_gate.py`, `core/hooks/adversary_dialog.py`, `core/hooks/hook_utils.py`
- **Identifier:** `_check_acceptance_criteria()` (edit_gate.py), `validate_dialog_artifact()` und `parse_spec_expected_behavior()` (adversary_dialog.py), neue geteilte Funktion in hook_utils.py

## Dependencies

| Komponente | Typ | Abhängigkeit |
|-----------|-----|-------------|
| `core/hooks/hook_utils.py::_find_worktree_root()` | Bestehende Utility | Wird bereits von `edit_gate.py::_is_stop_locked()` für exakt dieselbe Worktree-vor-Hauptrepo-Auflösung genutzt — Vorbild für die Spec-Pfad-Auflösung dieser Spec |
| `core/hooks/hook_utils.py::find_project_root()` | Bestehende Utility | Löst Worktrees transparent zum Hauptrepo auf; bleibt für die bestehende `_root`-Variable in `edit_gate.py` unverändert, wird für die neue Repo-Pfad-Prüfung als Referenzwurzel mitverwendet |
| `core/hooks/adversary_dialog.py::parse_spec_expected_behavior()` | Bestehender Konsument | Nutzt nach diesem Fix die geteilte Funktion für den AC-Teil statt der bisherigen eigenen inline-State-Machine; das `## Expected Behavior`-Bullet-Format bleibt unverändert dort implementiert |
| `core/hooks/edit_gate.py::_check_acceptance_criteria()` | Neuer Konsument | Nutzt nach diesem Fix dieselbe geteilte Funktion statt des bisherigen globalen `re.finditer`-Scans |
| `core/hooks/config_loader.py::get_ac_format_required_since()` | Bestehende Abhängigkeit | Legacy-Stichtag-Logik in `edit_gate.py` bleibt unverändert bestehen und wird durch diesen Fix nicht berührt |
| `tests/test_adversary_dialog_parse.py` | Bestehende Testdatei | Vorlage für Teststil (tmp_path-Fixtures, mock-frei) und Regressionsbasis — bestehende Tests dürfen nach der Konsolidierung nicht rot werden |
| `docs/specs/qa-gate-path-resolution.md`, `docs/specs/bash-gate-false-positive-fix.md` | Reale Testfixtures | Liefern echte Formatvariation (Soft-Wrap, Klammer-Zusatz) für Regressionstests beider Konsumenten |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|--------------|
| `core/hooks/hook_utils.py` | MODIFY | Neue geteilte Funktion, die section-gebunden AC-N-Bullets innerhalb einer `## Acceptance Criteria`-Section extrahiert (Label + Beschreibungstext getrennt), inkl. Soft-Wrap-Merge und Sub-Bullet-Ausschluss, wie bereits in `adversary_dialog.py` implementiert |
| `core/hooks/adversary_dialog.py` | MODIFY | `parse_spec_expected_behavior()` ruft für den AC-Teil die geteilte Funktion auf statt der bisherigen eigenen Regex-Logik; `validate_dialog_artifact()` wertet bei mehreren `## Verdict`-Blöcken den letzten statt den ersten |
| `core/hooks/edit_gate.py` | MODIFY | `_check_acceptance_criteria()` nutzt die geteilte Funktion statt des globalen `re.finditer(r'\bAC-\d+[:\s]+(.*)', content)`-Scans; zusätzlich Repo-Pfad-Scoping vor dem Check und Worktree-vor-Hauptrepo-Auflösung beim Laden der Spec-Datei (Vorbild: `_is_stop_locked()`) |
| `tests/test_edit_gate_ac_check.py` | CREATE | Subprozess-Tests analog `tests/test_edit_gate_orchestrator_files.py`: Fließtext-Querverweise, Tabellenzellen, Pfade außerhalb des Repos, Spec nur im Worktree, Legacy-Stichtag-Regression |
| `tests/test_adversary_dialog_verdict.py` | CREATE | Tests für `validate_dialog_artifact()` mit zwei bzw. drei `## Verdict`-Blöcken |
| `tests/test_adversary_dialog_parse.py` | MODIFY | Bestehende Tests bleiben grün (Regressionsnachweis der Konsolidierung); ein neuer Fall ergänzt die geteilte Funktion direkt |

### Estimated Changes

- Files: 6 (3 MODIFY Kern-Code + 2 CREATE Tests + 1 MODIFY Test)
- LoC: +180/-40 (geteilte Funktion ~50 LoC, Integrationsänderungen in beiden Konsumenten ~30 LoC, Tests ~150 LoC)
- Risk Level: MEDIUM (Worktree-Spec-Auflösung ist eine bewusste Verhaltensverschärfung, siehe Known Limitations)

## Root Cause

Beide Fehler sind dasselbe Grundmuster — ein naiver globaler Regex-Scan über ein strukturiertes Markdown-Artefakt, der Fundstellen wertet, die keine Deklarationen sind:

1. `edit_gate.py` sucht mit `re.finditer(r'\bAC-\d+[:\s]+(.*)', content)` über die **gesamte Datei**, nicht nur über die Acceptance-Criteria-Section. Jede Erwähnung einer AC-Nummer im Fließtext, jede Tabellenzelle und jeder Zeilenumbruch nach einer AC-Nummer erzeugt einen kurzen Rest-Text, der die 30-Zeichen-Schwelle unterschreitet und blockt.
2. Derselbe Check greift unabhängig davon, ob der bearbeitete Pfad überhaupt im Repo liegt — die Workflow-Ermittlung in `edit_gate.py::main()` liest zuerst den aktiven Workflow ohne Bezug zum konkreten `file_path`, sodass ein beliebiger Code-Datei-Write während eines aktiven Workflows den Check auslöst, auch wenn die Datei außerhalb des Repos liegt.
3. Die Spec-Existenzprüfung `spec_path = _root / spec_file; if not spec_path.exists(): return None` verwendet ausschließlich das Hauptrepo (`_root`). Liegt die Spec nur im aktuellen Worktree, greift der Check nicht — er hält damit weder verlässlich das Richtige zurück, noch lässt er verlässlich das Korrekte durch.
4. `adversary_dialog.py::validate_dialog_artifact()` sucht den Verdict mit `re.search(r"## Verdict\s*\n\*\*(.+?)\*\*", content)`. `re.search` liefert grundsätzlich den ersten Treffer. Nach einem Fix-Loop, der eine weitere Runde mit neuem Verdict anhängt, enthält das Artefakt mehrere `## Verdict`-Blöcke — der Check bewertet den veralteten ersten statt des finalen letzten.

Die korrekte, section-gebundene Erkennungslogik existiert bereits in `adversary_dialog.py::parse_spec_expected_behavior()` (entstanden in PR #59 für exakt dieses Format), wurde aber bei der Entstehung von `edit_gate.py`s Check nicht mitgezogen — daher zwei divergente Parser für dasselbe Format in derselben Datei-Familie.

## Implementierungsdetails

### 1. Geteilte Funktion in `hook_utils.py`

Neue Funktion, die den section-gebundenen Scan aus der bestehenden State-Machine in `adversary_dialog.py::parse_spec_expected_behavior()` (Zeilen ~77-127) übernimmt, aber Label und Beschreibungstext getrennt zurückgibt statt eines vorformatierten Strings:

```python
def extract_ac_entries(content: str) -> list[tuple[str, str]]:
    """Section-gebunden AC-N-Bullets aus '## Acceptance Criteria' extrahieren.

    Liefert (label, description) je Bullet, z.B. ("AC-1", "Given ... Then ...").
    Soft-Wrap-Fortsetzungszeilen werden angehängt, eingerueckte Sub-Bullets
    (z.B. '- Test:') verworfen. Nur Bullets INNERHALB der Section zaehlen —
    weder Fliesstext-Querverweise noch Tabellenzellen noch Vorkommen in
    anderen Sections.
    """
```

Der bestehende `ac_bullet_re = re.compile(r"^-\s+\*{0,2}AC-\d+[^:*]*\*{0,2}\s*:")` und die Section-State-Machine (unindentierte Bullet-Start-Erkennung, Sub-Bullet- vs. Fortsetzungszeilen-Unterscheidung über Einrückung der Rohzeile, unindentierte Nicht-AC-Zeile beendet einen offenen Block) wandern unverändert in diese Funktion. Label (`AC-1`) und Beschreibungstext werden beim Bullet-Start per Regex getrennt, statt wie bisher als ein zusammengesetzter String geführt.

### 2. `adversary_dialog.py::parse_spec_expected_behavior()` nutzt die geteilte Funktion

Der AC-Zweig ruft `extract_ac_entries()` auf und formatiert jedes Ergebnis-Tupel zurück zum bisherigen Ausgabeformat (`f"**{label}:** {description}"`), damit bestehende Konsumenten (Adversary-Checkliste, bestehende Tests wie `points[0].startswith("**AC-1:**")`) unverändert funktionieren. Der `## Expected Behavior`-Zweig bleibt vollständig unverändert.

### 3. `edit_gate.py::_check_acceptance_criteria()` nutzt dieselbe Funktion

Ersetzt den globalen `re.finditer`-Scan durch `extract_ac_entries(content)` und prüft je Eintrag `len(description.strip()) < 30` — inhaltlich dieselbe Schwelle wie bisher, aber nur noch auf echte Deklarationszeilen innerhalb der Section angewendet. Vorher/Nachher-Kontrast:

```python
# vorher: globaler Scan über die ganze Datei
for m in re.finditer(r'\bAC-\d+[:\s]+(.*)', content):
    desc = m.group(1).strip()

# nachher: section-gebunden über die geteilte Funktion
for label, desc in extract_ac_entries(content):
    desc = desc.strip()
```

### 4. Repo-Pfad-Scoping

`_check_acceptance_criteria()` erhält zusätzlich `file_path: str` als Parameter. Vor jeder inhaltlichen Prüfung wird verifiziert, dass der aufgelöste `file_path` unterhalb der relevanten Repo-Wurzel liegt — Hauptrepo-Root (`_root`) ODER, falls die Session in einem Worktree läuft, die Worktree-Root (`_find_worktree_root()`). Liegt der Pfad außerhalb beider, gibt die Funktion sofort `None` zurück (Check greift nicht), unabhängig davon, ob ein aktiver Workflow existiert.

### 5. Worktree-vor-Hauptrepo-Auflösung der Spec-Datei

Die Spec-Existenzprüfung wird um denselben Auflösungsschritt ergänzt, den `_is_stop_locked()` bereits für die Lock-Datei verwendet:

```python
from hook_utils import _find_worktree_root
wt = _find_worktree_root()
spec_path = (wt / spec_file) if (wt is not None and (wt / spec_file).exists()) else (_root / spec_file)
if not spec_path.exists():
    return None
```

Damit wird eine Spec zuerst im Worktree gesucht (falls die Session in einem läuft und sie dort existiert), sonst im Hauptrepo — bisher wurde ausschließlich das Hauptrepo geprüft.

### 6. Letzter statt erster Verdict-Block

`validate_dialog_artifact()` sammelt alle `## Verdict`-Blöcke und wertet den letzten:

```python
# vorher:
verdict_match = re.search(r"## Verdict\s*\n\*\*(.+?)\*\*", content)

# nachher:
verdict_matches = list(re.finditer(r"## Verdict\s*\n\*\*(.+?)\*\*", content))
verdict_match = verdict_matches[-1] if verdict_matches else None
```

Alle nachgelagerten Prüfungen (BROKEN/AMBIGUOUS/VERIFIED-Auswertung) bleiben unverändert — sie operieren nur noch auf dem letzten statt dem ersten Treffer.

## Expected Behavior

- **Input `edit_gate.py`:** Ein `Edit`/`Write`-Tool-Call mit `file_path` und aktivem Workflow, dessen Spec-Datei referenziert wird.
- **Output — section-gebundener Scan:** Ein AC-Querverweis im Fließtext, eine Tabellenzelle mit AC-Nummer oder ein Vorkommen einer AC-Nummer außerhalb der `## Acceptance Criteria`-Section (auch innerhalb der Section, aber nicht als eigene Bullet-Deklaration) löst den Check nicht mehr aus. Nur echte `- **AC-N:** ...`-Deklarationszeilen innerhalb der Section werden gegen die 30-Zeichen-Schwelle geprüft.
- **Output — Repo-Scoping:** Liegt `file_path` außerhalb des Repos (Hauptrepo-Root und, falls vorhanden, Worktree-Root), greift der Check nicht, unabhängig vom Workflow-Status.
- **Output — Worktree-Spec-Auflösung:** Existiert die referenzierte Spec-Datei nur im Worktree (nicht im Hauptrepo), wird sie trotzdem gefunden und inhaltlich geprüft, statt den Check stillschweigend zu überspringen.
- **Input `adversary_dialog.py`:** Ein Dialog-Artifact mit mehreren `## Verdict`-Blöcken (Fix-Loop-Runden).
- **Output — letzter Verdict-Block:** `validate_dialog_artifact()` wertet ausschließlich den zuletzt im Dokument vorkommenden `## Verdict`-Block; frühere Blöcke (z.B. ein veraltetes BROKEN vor einem Fix) werden ignoriert.
- **Side effects:** Keine Persistenz-Änderungen; alle vier Verhaltensänderungen sind reine Lese-/Auswertungslogik in bestehenden Gate-/Validierungsfunktionen.

## Error Handling

- Spec-Datei existiert weder im Worktree noch im Hauptrepo → unverändert `return None` (Check übersprungen, wie bisher).
- `file_path` lässt sich nicht auflösen (z.B. ungültiger Pfad-String) → Repo-Scoping fällt fail-safe auf „nicht geprüft, also nicht blocken" zurück, analog zum bestehenden Umgang mit nicht auflösbaren Pfaden bei der Orchestrator-Datei-Prüfung in `edit_gate.py`.
- Kein `## Verdict`-Block im Artifact vorhanden → unverändert `return False, "Kein Verdict im Artifact gefunden."`.
- Legacy-Stichtag (`ac_format_required_since`) greift weiterhin vor jeder inhaltlichen AC-Prüfung — Specs, die vor dem konfigurierten Datum erstellt wurden, werden unverändert durchgelassen, unabhängig von der Worktree-Auflösung.

## Known Limitations

- Die Worktree-Spec-Auflösung macht das Gate bewusst **strenger als heute**: Specs, die nie nach `main` gespiegelt werden, wurden vom Check bisher nie geprüft und werden es ab diesem Fix. Das ist eine dokumentierte, PO-entschiedene Verhaltensänderung (siehe Kontext-Dokument, PO-Entscheidung 2026-07-17), keine Nebenwirkung.
- Der Fix wirkt in Consumer-Projekten erst nach Version-Bump und Verteilung — siehe „Out of Scope / Verteilung" unten.
- Fließtext innerhalb einer AC-Beschreibung, der selbst mit `-` beginnt, wird weiterhin (unverändertes Bestandsverhalten der übernommenen State-Machine) als Sub-Bullet verworfen statt angehängt — bereits dokumentierte Limitation aus PR #59, hier nicht neu und nicht Gegenstand dieses Fixes.
- Die geteilte Funktion deckt ausschließlich das AC-N-Bullet-Format ab; das `## Expected Behavior`-Bullet-Format bleibt eine separate, unveränderte Code-Pfad in `adversary_dialog.py`.

## Out of Scope / Verteilung

- Version-Bump von `setup.py` auf 3.9.2 und Eintrag in `CHANGELOG.md` unter `[Unreleased]` sind Teil der Implementierung dieses Fixes (Repo-Konvention „CHANGELOG.md bei jeder Änderung aktualisieren"), aber die **Verteilung** in Consumer-Projekte (`python3 setup.py <project> --update`) ist ein separater, nachgelagerter Schritt außerhalb dieser Spec — ohne ihn bleibt der Fix im Consumer-Projekt (z.B. gregor_zwanzig) wirkungslos.
- `.worktrees/` fehlt in `.gitignore` — im Kontext-Dokument als Nebenbefund vermerkt, kein Bestandteil dieser Spec.

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Reine Konsolidierung bestehender, bereits im Repo etablierter Muster (section-gebundene State-Machine aus PR #59, Worktree-vor-Hauptrepo-Auflösung aus `_is_stop_locked()`) auf eine zweite Verwendungsstelle. Keine neue Architekturentscheidung, kein neuer Mechanismus, keine strukturelle Weichenstellung, die eine eigene Aufzeichnung rechtfertigt.

## Acceptance Criteria

- **AC-1:** Given eine Spec-Datei mit einer `## Acceptance Criteria`-Section, die ausschließlich echte, mindestens 30 Zeichen lange `- **AC-N:** ...`-Deklarationen enthält, sowie zusätzlich an anderer Stelle in der Datei (im Fließtext außerhalb dieser Section, in einer Tabellenzelle, und als reiner Querverweis innerhalb der Section ohne eigene Bullet-Form) mehrfache kurze Erwähnungen einer AC-Nummer gefolgt von Doppelpunkt oder Leerzeichen und wenig Resttext / When ein `Edit`-Tool-Call auf eine zum aktiven Workflow gehörende Datei während `phase6_implement` ausgeführt wird / Then blockt `edit_gate.py` diesen Edit nicht wegen der kurzen Erwähnungen — nur eine tatsächlich zu kurze Bullet-Deklaration innerhalb der Section darf noch blocken.

- **AC-2:** Given ein `Edit`-Tool-Call, dessen Zielpfad außerhalb sowohl der Hauptrepo-Wurzel als auch einer eventuell vorhandenen Worktree-Wurzel liegt, während ein Workflow mit unvollständiger Spec aktiv ist / When der Edit ausgeführt wird / Then greift die Acceptance-Criteria-Prüfung für diesen Pfad nicht — der Edit wird nicht wegen des Spec-Inhalts blockiert.

- **AC-3:** Given eine Spec-Datei, die ausschließlich im aktuellen Git-Worktree existiert und im Hauptrepo unter demselben relativen Pfad nicht vorhanden ist, mit einer zu kurzen AC-Deklaration in der Section / When ein `Edit`-Tool-Call auf eine Datei des zugehörigen Workflows während `phase6_implement` ausgeführt wird / Then wird die Worktree-Spec gefunden und inhaltlich geprüft, und der Edit wird wegen der zu kurzen Deklaration blockiert — der Check steigt nicht mehr aus, nur weil die Spec im Hauptrepo fehlt.

- **AC-4:** Given ein Adversary-Dialog-Artefakt mit zwei `## Verdict`-Blöcken, wobei der erste Block ein negatives Ergebnis und der zweite, spätere Block ein positives Endergebnis trägt (Fix-Loop-Runde) / When `validate_dialog_artifact()` dieses Artefakt auswertet / Then basiert die Auswertung ausschließlich auf dem zweiten, letzten Block — ein Fix-Loop mit angehängter neuer Runde erfordert keine manuelle Nachbearbeitung des Artefakts, um als bestanden zu gelten.

- **AC-5:** Given die AC-Bullet-Erkennung in `hook_utils.py` sowie ihre Nutzung durch `edit_gate.py` und `adversary_dialog.py` nach diesem Fix / When der Code beider Konsumenten statisch auf eigene Regex-Implementierungen für das AC-N-Bullet-Muster inspiziert wird / Then existiert die section-gebundene Bullet-Erkennungslogik (Regex plus Section-State-Machine) nur an einer einzigen Stelle im Repo, und beide Konsumenten rufen dieselbe geteilte Funktion auf statt eigene Kopien der Erkennung zu pflegen.

- **AC-6:** Given eine Spec-Datei, deren Änderungszeitpunkt vor dem konfigurierten `ac_format_required_since`-Stichtag liegt und die keine valide `## Acceptance Criteria`-Section enthält / When ein `Edit`-Tool-Call auf eine zugehörige Workflow-Datei während `phase6_implement` ausgeführt wird / Then lässt der Legacy-Stichtag-Mechanismus den Edit weiterhin unverändert durch, exakt wie vor diesem Fix — die Konsolidierung ändert an dieser bestehenden Ausnahme nichts.

## Test Plan

### Automated Tests (TDD RED)

- [ ] Test 1 (deckt AC-1 ab): GIVEN eine `tmp_path`-Fixture-Spec mit `## Acceptance Criteria`, drei validen ≥30-Zeichen-Bullets sowie einem Fließtext-Satz außerhalb der Section und einer Tabellenzeile mit AC-Nummern innerhalb der Section WHEN `edit_gate.py` per Subprozess auf eine zugehörige Workflow-Datei in `phase6_implement` angewendet wird THEN `returncode == 0`.
- [ ] Test 2 (deckt AC-1 ab, Gegenprobe): GIVEN dieselbe Fixture, aber ein echter Bullet mit < 30 Zeichen Beschreibungstext WHEN derselbe Aufruf erfolgt THEN `returncode == 2` und stderr enthält den Hinweis auf den zu kurzen Eintrag.
- [ ] Test 3 (deckt AC-2 ab): GIVEN ein aktiver Workflow mit unvollständiger Spec und ein `file_path` außerhalb von Hauptrepo- und Worktree-Wurzel (z.B. unter einem separaten `tmp_path`-Verzeichnis) WHEN `edit_gate.py` aufgerufen wird THEN `returncode == 0` (kein Block wegen des Spec-Inhalts).
- [ ] Test 4 (deckt AC-3 ab): GIVEN ein simuliertes Worktree-Layout (`.git`-Datei statt -Verzeichnis, verweist aufs Hauptrepo) mit der Spec-Datei ausschließlich im Worktree, kurzer AC-Deklaration WHEN `edit_gate.py` mit `cwd` im Worktree aufgerufen wird THEN `returncode == 2`.
- [ ] Test 5 (deckt AC-4 ab): GIVEN ein Artefakt-String mit zwei `## Verdict`-Blöcken (`**BROKEN**` zuerst, `**VERIFIED: ...**` zuletzt) WHEN `validate_dialog_artifact()` direkt aufgerufen wird THEN liefert es `(True, ...)` mit VERIFIED im Meldungstext.
- [ ] Test 6 (deckt AC-5 ab): GIVEN der Quellcode von `edit_gate.py` und `adversary_dialog.py` nach dem Fix WHEN beide Dateien per `grep`/Text-Suche auf das Muster `AC-\\d+` in eigenständigen `re.compile`/`re.finditer`-Aufrufen außerhalb von `hook_utils.py` durchsucht werden THEN findet sich keine zweite eigenständige Section-Bullet-Erkennung.
- [ ] Test 7 (deckt AC-6 ab): GIVEN eine Spec-Datei mit `mtime` vor dem konfigurierten Stichtag und ohne valide AC-Section WHEN `edit_gate.py` auf eine zugehörige Workflow-Datei angewendet wird THEN `returncode == 0`.
- [ ] Test 8 (Regression): GIVEN die bestehenden Fälle in `tests/test_adversary_dialog_parse.py` (u.a. der reale Abgleich gegen `docs/specs/qa-gate-path-resolution.md` mit 5 erwarteten Einträgen) WHEN sie nach der Umstellung auf die geteilte Funktion erneut laufen THEN bleiben alle Ergebnisse unverändert identisch zum Stand vor diesem Fix.

### Test-Implementierung

Subprozess-Muster für `edit_gate.py`-Tests analog `tests/test_edit_gate_orchestrator_files.py` (Fake-Projekt mit `.git`, `CLAUDE_PROJECT_DIR`-Env, JSON-Payload über stdin); direkter Funktionsaufruf für `validate_dialog_artifact()` und `extract_ac_entries()` analog `tests/test_adversary_dialog_parse.py` (tmp_path-Fixtures, kein Mocking von Dateisystemzugriffen).

Ausführung:

```bash
python3 -m pytest tests/test_edit_gate_ac_check.py tests/test_adversary_dialog_verdict.py tests/test_adversary_dialog_parse.py -v
```

## Changelog

- 2026-07-17: Initial spec erstellt für #60/#69 (henemm/gregor_zwanzig#1295)
