---
entity_id: fix-440-test-zeilen
type: bugfix
created: 2026-10-14
updated: 2026-10-14
status: draft
workflow: fix-440-test-zeilen
version: "1.0"
tags: [spec-freeze, teil-hash, edit-gate, hook-utils, robustheit]
test_targets: ["tests/test_spec_freeze_continuation_440.py", "tests/test_spec_freeze_partial_hash_439.py"]
---

# Spec-Freeze: Fortsetzungszeilen unter `- Test:` sind eingefroren — #440

## Approval

- [ ] Approved

## GitHub Issue

- **Issue:** #440 (Restpunkt F004 aus der Adversary-Prüfung zu #439). Die Spec `docs/specs/feat-439-spec-freeze-teilhash.md` ist eingefroren und bleibt unverändert; ihre Regel „`- Test:`-Zeile samt Fortsetzung beweglich“ (AC-8) wird hier ersetzt.

## Purpose

Seit #439 sperrt `edit_gate.py` nach der Freigabe nur den freigegebenen Teil einer Spec; im Abschnitt Acceptance Criteria sind die eingerückten `- Test:`-Zeilen beweglich. Heute zählen auch alle tiefer eingerückten Folgezeilen dazu, außer sie enthalten ein AC-Label oder given/when/then (`_SPEC_AC_TEXT_RE`). Diese Wörterliste ist umgehbar: Fließtext („Das System muss zusätzlich Y tun“), „A C-31“, ein kyrillisches „А“, Soft-Hyphen oder Zero-Width-Space schleusen neuen Anforderungstext ohne Rücksprung nach `phase3_spec` ein. Die Spec macht die Regel fail-closed und einfach: Beweglich ist ausschließlich die `- Test:`-Zeile selbst, jede Folgezeile bleibt im Hash. Dazu kommt ein Robustheitsfix: `edit_gate.py` stürzt bei Müll-Payload (`file_path` keine Zeichenkette, `tool_input` kein Objekt) mit Exit 1 ab, statt sauber durchzulassen.

## Source

- **File:** `core/hooks/hook_utils.py` — `_SPEC_AC_TEXT_RE` (~Z.722), `_SPEC_BULLET_RE` (~Z.721), `_indent_width` (~Z.799), `_spec_ac_frozen_lines` (~Z.805), `frozen_spec_sha256` (~Z.832), `get_tool_input` (~Z.910); `core/hooks/edit_gate.py` — `main` (~Z.635-645)
- **Identifier:** `_spec_ac_frozen_lines`, `get_tool_input`, `edit_gate.main`
- **Analyse:** `docs/context/fix-440-test-zeilen.md` (Variante A gewählt)
- **Ursprungsanfrage:** GitHub-Issue #440

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `core/hooks/hook_utils.py` (`split_spec_sections`, `_SPEC_TEST_LINE_RE`, `frozen_spec_sha256`) | Modul | Zerleger und Teil-Hash; Ort der Regeländerung |
| `core/hooks/edit_gate.py` | Modul | Kern-Gate Edit/Write; simuliert die neue Fassung per `frozen_spec_sha256`; Ort des Robustheitsfixes |
| `core/hooks/workflow.py` (`set-briefing`, `_check_po_briefing`) | Modul | Stempelt und prüft den Teil-Hash; unverändert, übernimmt die neue Regel über `frozen_spec_sha256` |
| `scripts/ci_spec_gate.py` | Skript | Ruft dieselbe Funktion; Byte-Hash-Fallback für ältere Kopien bleibt unverändert |
| `tests/test_spec_freeze_partial_hash_439.py` | Test | Enthält AC-8 und F003 mit der alten Regel; wird umgeschrieben |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| `core/hooks/hook_utils.py` | MODIFY | `_spec_ac_frozen_lines`: nur die `- Test:`-Zeile entfällt aus dem Teil-Hash, alle Folgezeilen bleiben; `_SPEC_AC_TEXT_RE`, `test_indent`-Zustand und Fortsetzungslogik entfallen; `_indent_width` und `_SPEC_BULLET_RE` entfallen, soweit sonst unbenutzt (vorab per Suche zu prüfen); `get_tool_input` liefert nur ein dict, sonst `{}` |
| `core/hooks/edit_gate.py` | MODIFY | `main`: `file_path` keine Zeichenkette oder `tool_input` kein dict führt zu `allow()` ohne Traceback |
| `tests/test_spec_freeze_partial_hash_439.py` | MODIFY | AC-8 (~Z.489) und F003 (~Z.834) auf die neue Regel umschreiben |
| `tests/test_spec_freeze_continuation_440.py` | CREATE | Neue Tests je Umgehungsform, Regression des Hashes, Müll-Payload, Ende-zu-Ende |
| `CHANGELOG.md` | MODIFY | Eintrag unter `[Unreleased]`; „samt Fortsetzung“ im #439-Eintrag korrigieren; Migrationshinweis |

**Nicht ändern:** `docs/specs/feat-439-spec-freeze-teilhash.md` (eingefroren), `workflow.py`, `scripts/ci_spec_gate.py`, `hooks/hooks.json`. `CLAUDE.md` nur anfassen, falls die Hook-Beschreibung dort „samt Fortsetzung“ nennt (Stand der Analyse: nicht der Fall).

### Estimated Changes

- Files: 5
- LoC: ca. +120/-20 (überwiegend Tests)
- Alle Funktionen bleiben unter 50 Zeilen.

## Implementation Details

**1. Zerleger.** `_spec_ac_frozen_lines` geht die Zeilen des AC-Abschnitts durch und lässt genau die Zeilen weg, die außerhalb einer Code-Fence auf `_SPEC_TEST_LINE_RE` (eingerücktes `- Test:`) passen. Jede andere Zeile bleibt in der Liste: auch tiefer eingerückte Folgezeilen, Fließtext, Leerzeilen und Fence-Inhalt. Es gibt keinen Zustand „Fortsetzung läuft“ und keine Wörterliste mehr; die Regel ist eine Allowlist mit genau einem beweglichen Zeilentyp (fail-closed, keine Heuristik).

**2. Aufräumen.** `_SPEC_AC_TEXT_RE`, der `test_indent`-Zustand und die Fortsetzungsprüfung entfallen. `_indent_width` und `_SPEC_BULLET_RE` werden vorab per Suche auf weitere Verwender geprüft (Stand der Analyse: nur diese Funktion) und dann entfernt; bei einem weiteren Verwender bleiben sie stehen.

**3. Hash-Verträglichkeit.** Specs ohne Fortsetzungszeilen unter `- Test:` behalten ihren Teil-Hash byte-identisch (Regressionstest mit festem Hash-Literal). Specs mit Fortsetzungen (gemessen: 75 Zeilen in 12 von 69 Alt-Specs) bekommen einen anderen Teil-Hash, weil die Fortsetzung nun mit hineinzählt. Bestehende Briefings solcher Specs gelten damit als veraltet. Migrationsweg: `workflow.py set-briefing` erneut ausführen (solange der Workflow nicht freigegeben ist) bzw. Rücksprung nach `phase3_spec`, neues Briefing, neue Freigabe. Das CI-Gate nutzt dieselbe Funktion `frozen_spec_sha256`; sein Byte-Hash-Fallback für ältere `workflow.py`-Kopien bleibt unverändert.

**4. Robustheit.** `get_tool_input` gibt nur dann etwas zurück, wenn der Wert ein dict ist, sonst `{}` (gilt für Umgebungsvariable und stdin). In `edit_gate.main` wird `file_path` nur verwendet, wenn es eine nichtleere Zeichenkette ist; andernfalls `allow()` wie heute bei leerem Pfad. Das ist kein neuer Bypass: Ohne gültigen Zeichenketten-Pfad schreibt das Werkzeug nichts, ein Traceback mit Exit 1 wäre dagegen ein unkontrolliertes Verhalten.

## Expected Behavior

- **Input:** Ein Edit/Write auf eine freigegebene Spec; ein Payload mit beliebigem `tool_input`.
- **Output:** Jede Änderung an einer Zeile des AC-Abschnitts außer der `- Test:`-Zeile selbst ändert den Teil-Hash und endet mit Exit 2 (Rücksprung nötig). Änderung nur der `- Test:`-Zeile bleibt erlaubt. Müll-Payload endet mit Exit 0 ohne Traceback.
- **Side effects:** Teil-Hash von Specs mit Fortsetzungen unter `- Test:` ändert sich (Migration siehe Implementation Details 3); keine neuen Subprozesse, Abhängigkeiten oder Config-Keys.

## Known Limitations

- **Die `- Test:`-Zeile selbst bleibt beweglich und darf beliebigen Text tragen.** Die Test-Zuordnung ist genau eine Zeile (Design aus #439); wer dort Anforderungstext einträgt, kommt ohne Rücksprung durch. Eine inhaltliche Prüfung dieser Zeile wäre wieder eine umgehbare Heuristik und ist bewusst nicht Teil dieser Änderung.
- **Umbrechen langer Testpfade ist künftig eine Spec-Änderung:** Wer eine `- Test:`-Zeile oder deren Fortsetzung umbricht, muss nach `phase3_spec` zurückspringen. Neue Specs schreiben die Test-Zeile daher in einer Zeile.
- **Bestehende Briefings** von Specs mit Fortsetzungen gelten nach dem Update als veraltet und müssen neu gestempelt werden (siehe Implementation Details 3).
- **Doku-Lücke #439:** `core/hooks/hook_utils.py` fehlt in der Scope-Tabelle der eingefrorenen Spec `feat-439-spec-freeze-teilhash.md`, obwohl dort die Teil-Hash-Logik liegt. Die alte Spec wird nicht geändert; diese Spec benennt `hook_utils.py` als Ort der Regel.
- **Abschnittsgrenzen:** Setext-Überschriften (`Text` mit `---`/`===` darunter) und H3-Überschriften sind keine Abschnittsgrenze des Zerlegers; nur H2 mit `##` trennt Abschnitte. Das ist fail-closed (Inhalt bleibt im vorherigen Abschnitt), wurde aber bisher nur im Changelog erwähnt.
- Verteilung: wirkt in Konsumentenprojekten erst nach dem Plugin-Update.

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] Eine Fortsetzungszeile unter `- Test:` einer freigegebenen Spec lässt sich in keiner Formulierung (Fließtext, „A C-31“, kyrillisches „А“, Soft-Hyphen, Zero-Width-Space) mehr ohne Rücksprung ändern oder ergänzen; das Gate endet mit Exit 2
- [ ] Die `- Test:`-Zeile selbst lässt sich weiter ohne Rücksprung ändern
- [ ] Specs ohne Fortsetzungen behalten ihren Teil-Hash byte-identisch
- [ ] Ein Müll-Payload (`file_path` als Zahl, `tool_input` als Zeichenkette) endet in `edit_gate.py` mit Exit 0 ohne Traceback
- [ ] CHANGELOG-Eintrag nennt die neue Regel, den Migrationshinweis und die Known Limitations; „samt Fortsetzung“ ist korrigiert
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (`tests/test_spec_freeze*`, Gate-Tests und Vollsuite grün)

## Acceptance Criteria

- **AC-1:** Given eine freigegebene Spec mit `- Test:`-Zeile und Fortsetzungszeile / When die Fortsetzung durch Fließtext mit neuer Anforderung ergänzt oder geändert wird / Then ändert sich der Teil-Hash und das Gate endet mit Exit 2
  - Test: `tests/test_spec_freeze_continuation_440.py::test_fliesstext_fortsetzung_aendert_hash_und_blockt`
- **AC-2:** Given eine freigegebene Spec mit `- Test:`-Zeile und Fortsetzungszeile / When eine Fortsetzung mit der Schreibweise „A C-31“ (Leerzeichen im Label) hinzukommt / Then ändert sich der Teil-Hash
  - Test: `tests/test_spec_freeze_continuation_440.py::test_label_mit_leerzeichen_aendert_hash`
- **AC-3:** Given dieselbe Spec / When eine Fortsetzung mit kyrillischem „А“ (U+0410) statt lateinischem „A“ im Label hinzukommt / Then ändert sich der Teil-Hash
  - Test: `tests/test_spec_freeze_continuation_440.py::test_kyrillisches_a_aendert_hash`
- **AC-4:** Given dieselbe Spec / When eine Fortsetzung mit Soft-Hyphen (U+00AD) oder Zero-Width-Space (U+200B) mitten im Schlüsselwort hinzukommt / Then ändert sich der Teil-Hash
  - Test: `tests/test_spec_freeze_continuation_440.py::test_soft_hyphen_und_zero_width_space_aendern_hash`
- **AC-5:** Given eine Spec mit `- Test:`-Zeile und tiefer eingerückten Folgezeilen / When nur die `- Test:`-Zeile selbst geändert wird / Then bleibt der Teil-Hash gleich
  - Test: `tests/test_spec_freeze_continuation_440.py::test_aenderung_nur_der_test_zeile_laesst_hash_gleich`
- **AC-6:** Given eine Fixture-Spec ohne Fortsetzungszeilen unter `- Test:` / When `frozen_spec_sha256` sie hasht / Then entspricht das Ergebnis einem festen Hash-Literal aus dem Stand vor dieser Änderung (byte-identisch)
  - Test: `tests/test_spec_freeze_continuation_440.py::test_spec_ohne_fortsetzung_hash_identisch_zum_vorstand`
- **AC-7:** Given ein Payload mit `file_path` als Zahl, Liste oder `null` bzw. mit `tool_input` als Zeichenkette / When `edit_gate.py` als Subprozess läuft / Then endet es mit Exit 0 und ohne Traceback auf stderr
  - Test: `tests/test_spec_freeze_continuation_440.py::test_muell_payload_endet_mit_exit_0_ohne_traceback`
- **AC-8:** Given ein freigegebener Workflow mit Spec und Fortsetzung unter `- Test:` / When das echte `edit_gate.py` einen Edit sieht, der die Fortsetzung ändert / Then endet es mit Exit 2 und der Rücksprung-Meldung; derselbe Edit nur an der `- Test:`-Zeile endet mit Exit 0
  - Test: `tests/test_spec_freeze_continuation_440.py::test_edit_gate_ende_zu_ende_fortsetzung_blockt`
- **AC-9:** Given die bisherigen Tests AC-8 und F003 der #439-Testdatei / When sie auf die neue Regel umgeschrieben sind (Fortsetzung geändert führt zum Block, nur die Test-Zeile geändert bleibt erlaubt) / Then sind sie und die übrigen Tests der Datei grün
  - Test: `tests/test_spec_freeze_partial_hash_439.py::test_test_zeile_fortsetzung_beweglich_neuer_bullet_nicht`, `tests/test_spec_freeze_partial_hash_439.py::test_f003_fortsetzung_mit_ac_text_eingefroren`

> Die Test-Zuordnung wird **bei der Spec-Erstellung** eingetragen, nicht nachträglich:
> Nach der Freigabe ist diese Datei eingefroren (#230) — jede Änderung verschiebt den
> PO-Briefing-Hash und blockt den Workflow-Abschluss. Stimmt der Testname später nicht
> mehr, gehört die Korrektur in die TDD-RED-Artefakte (`workflow.py add-artifact`),
> nicht in diese Datei.

## Test Plan

Automatische Tests (jeweils an eine AC oben gebunden):

- `pytest tests/test_spec_freeze_continuation_440.py` — Hash-Tests direkt gegen `hook_utils.frozen_spec_sha256`; Gate-Tests als Subprozess gegen das echte `core/hooks/edit_gate.py` mit freigegebenem Workflow in einer Sandbox nach dem Muster aus `tests/test_spec_freeze_partial_hash_439.py` (`_approved_project`, `_edit`). Die RED-Läufe zeigen vor der Implementierung Exit 0 statt Exit 2 (Umgehungsformen), Traceback statt Exit 0 (Müll-Payload) und werden als Artefakte registriert. Das Hash-Literal für AC-6 wird vor der Änderung mit dem Ist-Stand erzeugt und fest eingetragen.
- `pytest tests/test_spec_freeze_partial_hash_439.py` — umgeschriebene AC-8/F003 und der übrige Bestand.
- Regression: `pytest tests/test_spec_freeze*` und die Gate-Tests, danach die Vollsuite. Zusätzlich ein Messlauf über die Alt-Specs: Hash-Änderung nur bei den Specs mit Fortsetzungen.
- Hochrisiko-Bereich (Gate-Code): im Adversary-Lauf mindestens 2 Runden (Stufe laut `adversary_dialog.py risk`); die Runden prüfen weitere Umgehungsformen (Tabs, tiefere Einrückung, Fence-Fortsetzungen, `\r`) und Müll-Payloads.

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Die Änderung setzt das in #439 beschlossene fail-closed-Prinzip („beweglich ist nur, was auf einer Allowlist steht“) konsequenter um und entfernt dafür eine Heuristik; es entsteht kein neues Muster, keine Abhängigkeit und kein neuer Hook. Verworfen: Regex-Denylist erweitern (prinzipiell umgehbar), Fortsetzungen per Fehlermeldung verbieten (Variante B: würde Alt-Specs unnötig umformatieren) und nur dokumentieren (Variante C: widerspricht fail-closed).

## Changelog

- 2026-10-14: Initial spec created (#440)
