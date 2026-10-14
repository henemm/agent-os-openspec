---
entity_id: feat-439-spec-freeze-teilhash
type: feature
created: 2026-10-13
updated: 2026-10-13
status: draft
workflow: feat-439-spec-freeze-teilhash
version: "1.0"
tags: [spec-freeze, teil-hash, edit-gate, po-briefing, ci-spec-gate, override]
test_targets: ["tests/test_spec_freeze_partial_hash_439.py", "tests/test_edit_gate_spec_freeze_230.py", "tests/test_po_briefing_gate.py", "tests/test_ci_spec_gate.py"]
---

# Spec-Freeze nur für den freigegebenen Teil (Teil-Hash) — #439

## Approval

- [ ] Approved

## GitHub Issue

- **Issue:** #439. Folge zu #230 (Gesamt-Freeze nach Freigabe) und #405 (Rücksprung setzt Freigaben zurück). Bash-Schreibwege auf die Spec sind **nicht** Teil dieser Spec.

## Purpose

Seit #230 ist die gesamte Spec nach der Freigabe gesperrt, auch für harmlose Nachträge wie einen korrigierten Testnamen; der einzige Ausweg „override“ öffnet dabei eine Stunde lang alle Gates. Künftig sperrt und hasht das Framework nur noch, was der PO freigegeben hat (Purpose, Scope, Definition of Done, Acceptance-Criteria-Text, ADR und alles, was nicht ausdrücklich als beweglich gilt). Begleittext (Frontmatter, `- Test:`-Zeilen, Test Plan, Known Limitations, Implementation Details, Changelog) bleibt ohne Token änderbar und hinterlässt eine Spur im Workflow-State. „override“ öffnet den Spec-Freeze nicht mehr; Änderungen am Freigegebenen gehen nur über den Rücksprung nach `phase3_spec` mit neuem Briefing und neuer Freigabe.

## Source

- **File:** `core/hooks/workflow.py` — `spec_sha256` (~Z.784, bleibt unverändert), `_check_po_briefing` (~Z.926), `cmd_set_briefing` (~Z.1495), `stamp_briefing_frontmatter` (~Z.903); `core/hooks/edit_gate.py` — Schritt 1d (~Z.580); `core/hooks/edit_verify.py`; `scripts/ci_spec_gate.py` — `_check_briefing` (~Z.286–330)
- **Identifier:** `frozen_spec_sha256` (neu, eine Quelle in `workflow.py`), Abschnitts-Zerleger (neu), Edit-Gate-Schritt 1d (umgebaut), `spec_post_approval_edits` (neue State-Liste)
- **Analyse:** `docs/context/feat-439-spec-freeze-teilhash.md`
- **Ursprungsanfrage:** GitHub-Issue #439

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `core/hooks/workflow.py` | Modul | Heimat von `frozen_spec_sha256`, `_check_po_briefing`, `cmd_set_briefing`; Legacy-`spec_sha256` bleibt byte-genau |
| `core/hooks/hook_utils.py` | Modul | Gehärtete State-API (`read_state_json`, `atomic_write_text`, #416/#422) für die Spur |
| `core/hooks/edit_gate.py` | Modul | Kern-Gate Edit/Write; Schritt 1d wird auf Teil-Hash-Vergleich mit Simulation umgebaut |
| `core/hooks/edit_verify.py` | Modul | PostToolUse; schreibt die Spur, bleibt fail-open |
| `core/hooks/override_token.py` | Modul | Wird für Schritt 1d nicht mehr konsultiert; sonst unverändert |
| `scripts/ci_spec_gate.py` | Modul | Lädt `workflow.py` per `_load_hook_module`; nutzt `frozen_spec_sha256` mit getattr-Fallback |
| `docs/briefings/*.md` | Daten | ~50 bestehende Briefings mit Gesamt-Hash müssen bis zur nächsten Freigabe gültig bleiben |
| `core/agents/docs-updater.md`, `core/commands/60-validate.md`, `templates/spec_template.md`, `CLAUDE.md`, `CHANGELOG.md`, `skills/` | Doku | Texte zur #230-Regel und zu override anpassen; Skills per `scripts/sync_skills.py` neu erzeugen |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| `core/hooks/workflow.py` | MODIFY | `frozen_spec_sha256(content)` samt Abschnitts-Zerleger; `cmd_set_briefing` schreibt Doppelstempel und darf nach Freigabe migrieren; `_check_po_briefing` vergleicht bevorzugt den Teil-Hash |
| `core/hooks/edit_gate.py` | MODIFY | Schritt 1d: Simulation der neuen Fassung, Teil-Hash-Vergleich, Legacy-Gesamt-Freeze, override öffnet nicht mehr |
| `core/hooks/edit_verify.py` | MODIFY | Spur-Eintrag nach Edit an beweglichem Teil über die gehärtete State-API |
| `scripts/ci_spec_gate.py` | MODIFY | Teil-Hash über `workflow.frozen_spec_sha256`, getattr-Fallback auf Byte-Gesamt-Hash |
| `templates/spec_template.md` | MODIFY | Kurzer Hinweis, welche Abschnitte nach Freigabe beweglich sind |
| `core/agents/docs-updater.md` | MODIFY | #230-Regel auf Teil-Freeze umstellen |
| `core/commands/60-validate.md` | MODIFY | Hinweis zum Spec-Hash anpassen |
| `CLAUDE.md` | MODIFY | Override-Abschnitt und Hook-Beschreibung knapp anpassen |
| `CHANGELOG.md` | MODIFY | Eintrag unter `[Unreleased]` inklusive Breaking-Hinweis zu override |
| `skills/*/SKILL.md` | MODIFY | Generiert per `python3 scripts/sync_skills.py`, nicht von Hand |
| `tests/test_spec_freeze_partial_hash_439.py` | CREATE | Neue Tests: Zerleger, Umgehungen, Gate, Legacy-Migration, CI-Fallback, Spur |
| `tests/test_edit_gate_spec_freeze_230.py` | MODIFY | `test_edit_with_override_allowed` wird umgedreht, weitere Fälle auf Teil-Freeze angepasst |
| `tests/test_po_briefing_gate.py` | MODIFY | Fixtures für Doppelstempel und Legacy-Pfad |
| `tests/test_ci_spec_gate.py` | MODIFY | Fixtures für Teil-Hash und Fallback |
| `tests/test_workflow_resolution_consolidation.py` | MODIFY (nur falls nötig) | Muss grün bleiben; Fixtures nur anpassen, falls sie den Stempel prüfen |

**Nicht ändern:** `workflow.spec_sha256` und der Byte-Hash im CI-Gate für Legacy-Stempel (byte-genau unverändert), `override_token.py`, `phase_listener.py`, `hooks/hooks.json`, `modules/`. Kein neuer Hook, keine neue Datei im Hook-Verzeichnis.

### Estimated Changes

- Files: 14 (davon 4 Test-Dateien, 1 generierter Skills-Satz)
- LoC: ca. +450 bis +650 (davon ca. 250 Tests), ca. -30
- Risiko HOCH (Kern-Gate und Briefing-Gate; ein Klassifikationsfehler im Hash ist ein Gate-Bypass) → 2 Adversary-Runden

## Implementation Details

**1. Beweglich ist nur, was auf der Allowlist steht; alles andere ist eingefroren (fail-closed).** Beweglich: das Frontmatter; die H2-Abschnitte `Known Limitations`, `Implementation Details` / `Implementierungsdetails`, `Changelog`, `Test Plan` und `Approval`; im Abschnitt `Acceptance Criteria` ausschließlich eingerückte Zeilen, die mit `- Test:` beginnen, samt ihrer Fortsetzungszeilen (tiefer eingerückt, kein neuer Bullet). `Approval` ist beweglich: der Haken ist reine Dokumentation (maßgeblich ist die Freigabe im Workflow-State), und eingefroren würde schon das Abhaken nach der Freigabe blocken. Der Test Plan ist beweglich, weil 62 bestehende Specs Testnamen dort führen und das Issue-Beispiel „Testname ändern“ sonst blocken würde; seine Existenz prüft das CI-Gate weiterhin.

**2. Überschriften-Erkennung.** CommonMark-H2: 0–3 Leerzeichen Einrückung, `##`, danach Leerzeichen oder Tab. H3 und tiefer gehören zum umgebenden H2. Normalisierung: Kleinbuchstaben, Klammerzusatz ab `(` weg, Whitespace kollabiert, Abgleich gegen die en/de-Alias-Tabelle (normalisierte Form → beweglich): `known limitations`, `bekannte einschränkungen`, `implementation details`, `implementierungsdetails`, `changelog`, `test plan`, `testplan`, `approval`, `freigabe`. Jede andere Überschrift ist eingefroren. Code-Fences mit ``` und `~~~` werden erkannt, `##` darin ist keine Überschrift. Eine nicht geschlossene Fence macht den Rest der Datei zum Fence-Inhalt; dadurch ändert sich die Klassifikation, der Teil-Hash ändert sich, und der Edit wird geblockt.

**3. Hash-Form `frozen_spec_sha256(content)` (eine Quelle in `workflow.py`).** `\r\n` wird zu `\n`. Gehasht wird die Folge der eingefrorenen Abschnitte (Überschriftenzeile plus Body); bewegliche Abschnitte fallen komplett heraus. Text vor der ersten H2 (nach dem Frontmatter, z. B. der Titel) ist eingefroren. Je Abschnitt werden Trailing-Whitespace und Leerzeilen am Body-Ende gestrippt, ebenso am Dateiende, damit das Anhängen eines Changelog-Abschnitts hinter einem eingefrorenen ADR am Dateiende nicht blockt. Verschiebt jemand Text aus einem eingefrorenen in einen beweglichen Abschnitt oder zerteilt er einen eingefrorenen Abschnitt durch eine neue bewegliche Überschrift, ändert sich der Hash. `extract_ac_entries` wird nicht wiederverwendet: es verwirft alle eingerückten Sub-Bullets, und eingerückte Given/When/Then-Zeilen wären sonst ein Bypass.

**4. Legacy-Algorithmus byte-genau unverändert.** `workflow.spec_sha256` (Text, utf-8, ganze Datei) und der Byte-Hash im CI-Gate bleiben exakt wie sie sind. Die Normalisierung gilt nur für den neuen Teil-Hash. Nichts wird „nebenbei vereinheitlicht“, sonst brechen alle bestehenden Briefings.

**5. Doppelstempel.** `spec_sha256` bleibt der Gesamt-Hash; das neue Feld `spec_frozen_sha256` steht im State-Eintrag `po_briefing` und im Briefing-Frontmatter. Neue Prüfungen vergleichen bevorzugt `spec_frozen_sha256`; fehlt es, gilt der Gesamt-Hash-Vergleich (Legacy). Das CI-Gate ruft `workflow.frozen_spec_sha256` per `getattr` auf; fehlt die Funktion (ältere Projekt-Kopie von `workflow.py`), fällt es auf den Byte-Gesamt-Hash zurück.

**6. Edit-Gate Schritt 1d.** Bleibt vor den Always-Allowed-Schritten. Referenz ist der Teil-Hash der aktuellen Datei gegen den Teil-Hash der simulierten neuen Fassung (nicht der gespeicherte Stempel; so sind auch Workflows ohne Briefing, etwa Fast Track, wie in #230 geschützt). Simulation: Edit = exakter `str.replace` (einmal bzw. `replace_all`), MultiEdit sequentiell, Write = voller Inhalt. Fehlt `old_string`, ist er ohne `replace_all` mehrdeutig, oder ist die Datei nicht lesbar → Block (fail-closed) mit Hinweis „Edit präzisieren oder Write verwenden“. Gleicher Teil-Hash → erlaubt, die restlichen Prüfungen laufen weiter. Verschiedener Teil-Hash → Block: „Das ändert, was freigegeben wurde → `workflow.py phase phase3_spec`, neues Briefing, neue Freigabe“. Override-Tokens (Workflow, `__infra__`, global) öffnen 1d nicht mehr.

**7. Legacy-Falle schließen.** Hat der Workflow ein Briefing **ohne** `spec_frozen_sha256`, behält 1d den alten Gesamt-Freeze (jede Änderung geblockt) mit der Meldung: „Erst `workflow.py set-briefing <pfad>` ausführen (migriert den Stempel), danach sind Änderungen an beweglichen Teilen erlaubt“. `set-briefing` ist nach der Freigabe erlaubt, wenn der gespeicherte Gesamt-Hash exakt zum aktuellen Inhalt passt (Inhalt nachweislich identisch, keine neue Freigabe nötig), und schreibt dann den Doppelstempel. Passt er nicht, lehnt `set-briefing` mit Rücksprung-Hinweis ab. Workflows ganz ohne Briefing (Fast Track, Gate aus) nutzen den Teil-Hash-Vergleich aus Punkt 6.

**8. Spur.** `edit_verify.py` (PostToolUse, fail-open) bekommt nur `tool_input`. Ist die Datei die `spec_file` eines Workflows ab `phase4_approved`, hängt es einen Eintrag `{ts, tool, sections}` an die State-Liste `spec_post_approval_edits`. Bei Edit und MultiEdit werden die Abschnitte über die Fundstelle(n) von `new_string` in der Datei **nach** dem Edit bestimmt; bei Write steht `sections: ["*"]` (das Gate hat den eingefrorenen Teil bereits als unverändert belegt). Geschrieben wird nur über die gehärtete State-API aus `hook_utils`. Jeder Fehler bleibt still und blockt nie.

**9. Doku.** `docs-updater.md`, `60-validate.md`, `CLAUDE.md` (Override-Abschnitt und Hook-Beschreibung knapp), `CHANGELOG.md` unter `[Unreleased]`, danach `python3 scripts/sync_skills.py`. `templates/spec_template.md` bekommt einen kurzen Hinweis zu den beweglichen Abschnitten.

## Expected Behavior

- **Input:** Edit, MultiEdit oder Write auf die `spec_file` eines Workflows ab `phase4_approved`; außerdem `set-briefing`, jede Transition ab `phase4_approved` und der CI-Lauf im Pull Request.
- **Output:** Ändert die Fassung nur bewegliche Teile, läuft der Edit durch, das Briefing bleibt gültig und `phase8_complete` klappt. Ändert sie Freigegebenes (auch mit Override-Token), endet das Gate mit Exit 2 und dem Rücksprung-Hinweis.
- **Side effects:** Neuer State-Eintrag `spec_post_approval_edits`; neues Briefing-Frontmatter-Feld `spec_frozen_sha256`. Keine neuen Subprozesse, keine neuen Config-Keys.

| Änderung an der freigegebenen Spec | Heute (#230) | Soll |
|------------------------------------|--------------|------|
| `- Test:`-Zeile ändern | Block (ohne Override) | erlaubt, Spur |
| Known Limitations, Test Plan, Changelog, Frontmatter, Implementation Details ändern | Block | erlaubt, Spur |
| Changelog-Abschnitt am Dateiende anhängen | Block | erlaubt |
| Purpose, Scope, Definition of Done, AC-Text, ADR ändern | Block (Ausweg override) | Block, auch mit override |
| Eingerückte Given/When/Then-Zeile im AC ändern | Block | Block |
| Text in beweglichen Abschnitt verschieben, eingefrorenen Abschnitt durch neue bewegliche Überschrift zerteilen | Block | Block |
| Legacy-Briefing (nur Gesamt-Hash), egal welche Änderung | Block | Block bis `set-briefing` migriert hat |

## Known Limitations

- **Bash-Weg bleibt ungedeckt:** `sed`/`echo` auf die Spec per Bash fängt 1d nicht (seit #230 so). Eingefrorene Änderungen per Bash fängt `_check_po_briefing` erst bei der nächsten Transition; bewegliche Änderungen per Bash hinterlassen keine Spur.
- **Alte CI-Kopien:** Eine bereits committete ältere `ci_spec_gate.py` in einem Konsumentenprojekt wertet Änderungen an beweglichen Teilen weiter als „veraltet“, bis dort `setup.py --update` lief. Das Plugin (Stempel-Schreiber) aktualisiert sich dagegen automatisch; deshalb bleibt `spec_sha256` der Gesamt-Hash.
- **Fehlblocks durch Simulation:** Normalisiert Claude Code Anführungszeichen in `old_string`, kann die Simulation den Edit nicht nachbilden und blockt (sicherer Fehlermodus; Hinweis „Edit präzisieren oder Write verwenden“).
- **Spur nur grob:** Die Spur nennt Abschnitte über die Fundstelle von `new_string`; bei Write steht nur `*`. Sie ist ein Protokoll, kein Revisionsverlauf.
- **Notausgang bei Fehlklassifikation:** Rücksprung nach `phase3_spec` (setzt Freigaben zurück, #405). Override hilft hier nicht mehr.
- Verteilung: wirkt in Konsumentenprojekten erst nach dem Plugin-Update.

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] Nach der Freigabe lässt sich ein `- Test:`-Name sowie Known Limitations, Test Plan, Changelog und Frontmatter ohne Override-Token ändern, das Briefing bleibt gültig und der Abschluss nach `phase8_complete` klappt
- [ ] Purpose, Scope, Definition of Done, AC-Text und ADR sind nach der Freigabe nicht mehr änderbar, auch nicht mit Workflow-, `__infra__`- oder globalem Override-Token; Umgehungen (Verschieben, Zerteilen, Einrückung, Code-Fence, offene Fence) greifen nicht
- [ ] Bestehende Briefings mit Gesamt-Hash bleiben bis zur nächsten Freigabe gültig; die Migration per `set-briefing` funktioniert und der Legacy-Gesamt-Freeze gilt bis dahin
- [ ] CI-Gate und lokale Briefing-Prüfung nutzen denselben Teil-Hash; ältere `workflow.py` führt zum Gesamt-Hash-Fallback
- [ ] Legacy-Hashfunktionen sind byte-identisch (Regressionstest gegen ein bestehendes Briefing)
- [ ] Änderungen an beweglichen Teilen hinterlassen eine Spur im State; `edit_verify.py` blockt nie
- [ ] Doku (`docs-updater.md`, `60-validate.md`, `CLAUDE.md`, Template, CHANGELOG) und `skills/` sind nachgezogen; Vollsuite grün

## Acceptance Criteria

- **AC-1:** Given eine freigegebene Spec (Phase ab `phase4_approved`) mit Teil-Hash-Briefing / When eine `- Test:`-Zeile unter einer AC per Edit geändert wird / Then lässt das Edit-Gate den Edit ohne Override-Token durch
  - Test: `tests/test_spec_freeze_partial_hash_439.py::test_test_zeile_aendern_erlaubt`
- **AC-2:** Given dieselbe Situation / When nach der Änderung der `- Test:`-Zeile `_check_po_briefing` und der Übergang nach `phase8_complete` laufen / Then gilt das Briefing als aktuell und der Übergang klappt
  - Test: `tests/test_spec_freeze_partial_hash_439.py::test_briefing_bleibt_gueltig_und_phase8_klappt`
- **AC-3:** Given eine freigegebene Spec / When Known Limitations, Test Plan, Changelog, Implementation Details, Approval bzw. das Frontmatter geändert werden / Then sind diese Edits ohne Token erlaubt
  - Test: `tests/test_spec_freeze_partial_hash_439.py::test_bewegliche_abschnitte_erlaubt`
- **AC-4:** Given eine freigegebene Spec / When Purpose, Scope, Definition of Done, AC-Text oder ADR geändert wird / Then blockt das Gate mit Exit 2 und dem Rücksprung-Hinweis auf `phase3_spec`
  - Test: `tests/test_spec_freeze_partial_hash_439.py::test_eingefrorene_abschnitte_blocken`
- **AC-5:** Given dieselbe Änderung und ein Override-Token (Workflow-Token, `__infra__`-Token oder globales Token) / When das Gate läuft / Then blockt es weiterhin, für alle drei Token-Arten
  - Test: `tests/test_spec_freeze_partial_hash_439.py::test_override_oeffnet_spec_freeze_nicht`
- **AC-6:** Given der bisherige Test `test_edit_with_override_allowed` / When er auf das neue Verhalten umgedreht wird / Then belegt er, dass ein Edit an eingefrorenem Text trotz Override geblockt wird
  - Test: `tests/test_edit_gate_spec_freeze_230.py::test_edit_with_override_allowed`
- **AC-7:** Given ein AC mit eingerückten Given/When/Then-Sub-Bullets / When einer dieser Sub-Bullets geändert wird / Then blockt das Gate (nur eingerückte Zeilen mit `- Test:` sind beweglich)
  - Test: `tests/test_spec_freeze_partial_hash_439.py::test_eingerueckte_given_when_then_eingefroren`
- **AC-8:** Given eine `- Test:`-Zeile mit Fortsetzungszeile / When Zeile und Fortsetzung geändert werden / Then ist das erlaubt; wird dagegen eine neue Bullet-Zeile ohne `- Test:` eingefügt, blockt das Gate
  - Test: `tests/test_spec_freeze_partial_hash_439.py::test_test_zeile_fortsetzung_beweglich_neuer_bullet_nicht`
- **AC-9:** Given eine freigegebene Spec / When Text aus einem eingefrorenen Abschnitt (z. B. Scope) in einen beweglichen Abschnitt (z. B. Known Limitations) verschoben wird / Then ändert sich der Teil-Hash und das Gate blockt
  - Test: `tests/test_spec_freeze_partial_hash_439.py::test_verschieben_in_beweglichen_abschnitt_blockt`
- **AC-10:** Given eine freigegebene Spec / When ein eingefrorener Abschnitt durch eine neu eingefügte bewegliche Überschrift (z. B. `## Changelog` mitten im Scope) zerteilt wird / Then blockt das Gate
  - Test: `tests/test_spec_freeze_partial_hash_439.py::test_zerteilen_durch_bewegliche_ueberschrift_blockt`
- **AC-11:** Given Überschriften mit bis zu drei Leerzeichen Einrückung (`   ## Scope`) oder Tab nach `##` / When die Spec zerlegt wird / Then werden sie als H2 erkannt und korrekt eingefroren bzw. als beweglich behandelt; vier Leerzeichen Einrückung zählen nicht als Überschrift
  - Test: `tests/test_spec_freeze_partial_hash_439.py::test_ueberschrift_einrueckung_und_tab`
- **AC-12:** Given ein `##` innerhalb eines Code-Blocks mit ``` oder `~~~` / When die Spec zerlegt wird / Then ist es keine Überschrift
  - Test: `tests/test_spec_freeze_partial_hash_439.py::test_code_fence_ueberschrift_ist_keine_ueberschrift`
- **AC-13:** Given eine nicht geschlossene Code-Fence / When sie eingefügt oder entfernt wird / Then gilt der Rest der Datei als Fence-Inhalt, der Teil-Hash ändert sich und das Gate blockt
  - Test: `tests/test_spec_freeze_partial_hash_439.py::test_offene_fence_blockt`
- **AC-14:** Given ein eingefrorener ADR-Abschnitt am Dateiende / When dahinter ein neuer `## Changelog`-Abschnitt angehängt wird / Then ist das erlaubt (Trailing-Whitespace am Abschnitts- und Dateiende zählt nicht)
  - Test: `tests/test_spec_freeze_partial_hash_439.py::test_changelog_am_dateiende_anhaengen_erlaubt`
- **AC-15:** Given dieselbe Spec mit `\r\n`- bzw. `\n`-Zeilenenden / When der Teil-Hash berechnet wird / Then ist er identisch
  - Test: `tests/test_spec_freeze_partial_hash_439.py::test_crlf_aendert_teilhash_nicht`
- **AC-16:** Given Überschriften mit Klammerzusatz, abweichender Groß-/Kleinschreibung oder deutschem Titel (`Implementierungsdetails`) / When sie gegen die Alias-Tabelle normalisiert werden / Then werden sie als beweglich erkannt, unbekannte Überschriften bleiben eingefroren
  - Test: `tests/test_spec_freeze_partial_hash_439.py::test_ueberschrift_normalisierung_und_unbekannt_eingefroren`
- **AC-17:** Given ein Edit, dessen `old_string` in der Datei fehlt, oder der ohne `replace_all` mehrdeutig ist, oder eine nicht lesbare Datei / When das Gate die neue Fassung simulieren will / Then blockt es (fail-closed) mit dem Hinweis „Edit präzisieren oder Write verwenden“
  - Test: `tests/test_spec_freeze_partial_hash_439.py::test_simulation_fail_closed`
- **AC-18:** Given MultiEdit mit mehreren Edits bzw. Write mit vollem Inhalt / When die neue Fassung simuliert wird / Then wird sequentiell bzw. mit dem vollen Inhalt verglichen und beweglich vs. eingefroren richtig entschieden
  - Test: `tests/test_spec_freeze_partial_hash_439.py::test_multiedit_und_write_simulation`
- **AC-19:** Given ein Workflow mit Legacy-Briefing (nur Gesamt-Hash, kein `spec_frozen_sha256`) / When irgendeine Änderung an der Spec versucht wird / Then gilt der Gesamt-Freeze (Block) mit dem Hinweis auf `workflow.py set-briefing`
  - Test: `tests/test_spec_freeze_partial_hash_439.py::test_legacy_briefing_behaelt_gesamt_freeze`
- **AC-20:** Given ein Legacy-Briefing, dessen gespeicherter Gesamt-Hash zum aktuellen Inhalt passt / When `set-briefing` nach der Freigabe läuft / Then schreibt es den Doppelstempel in State und Briefing-Frontmatter, und danach sind bewegliche Änderungen erlaubt
  - Test: `tests/test_spec_freeze_partial_hash_439.py::test_set_briefing_migriert_legacy_wenn_hash_passt`
- **AC-21:** Given ein Legacy-Briefing, dessen Gesamt-Hash nicht mehr zum Inhalt passt / When `set-briefing` nach der Freigabe läuft / Then lehnt es mit Rücksprung-Hinweis ab und ändert den Stempel nicht
  - Test: `tests/test_spec_freeze_partial_hash_439.py::test_set_briefing_lehnt_ab_wenn_hash_nicht_passt`
- **AC-22:** Given ein Workflow ganz ohne Briefing (Fast Track oder Gate aus) / When die Spec nach der Freigabe geändert wird / Then entscheidet der Teil-Hash-Vergleich aktuelle Datei gegen simulierte Fassung
  - Test: `tests/test_spec_freeze_partial_hash_439.py::test_workflow_ohne_briefing_nutzt_teilhash_vergleich`
- **AC-23:** Given ein Briefing mit `spec_frozen_sha256` / When `_check_po_briefing` nach einer Änderung an beweglichen Teilen läuft / Then ist das Briefing aktuell; nach einer Änderung an eingefrorenem Text (z. B. per Bash) meldet es „PO-Briefing ist veraltet“
  - Test: `tests/test_po_briefing_gate.py::test_teilhash_stempel_bewegliche_aenderung_gueltig_eingefrorene_veraltet`
- **AC-24:** Given ein Pull Request mit Teil-Hash-Briefing / When das CI-Gate läuft / Then vergleicht es `spec_frozen_sha256` gegen `workflow.frozen_spec_sha256`; bewegliche Änderungen bleiben grün, eingefrorene werden als veraltet gemeldet
  - Test: `tests/test_ci_spec_gate.py::test_ci_gate_prueft_teilhash`
- **AC-25:** Given eine ältere Projekt-Kopie von `workflow.py` ohne `frozen_spec_sha256` / When das CI-Gate läuft / Then fällt es auf den Byte-Gesamt-Hash zurück und stürzt nicht ab
  - Test: `tests/test_ci_spec_gate.py::test_ci_gate_fallback_aeltere_workflow_kopie`
- **AC-26:** Given ein bestehendes Briefing aus `docs/briefings/` mit Gesamt-Hash / When `spec_sha256` bzw. der Byte-Hash im CI-Gate auf die zugehörige Spec angewandt wird / Then ergeben beide exakt den gestempelten Wert (Legacy-Algorithmus unverändert)
  - Test: `tests/test_spec_freeze_partial_hash_439.py::test_legacy_hashfunktionen_byte_identisch`
- **AC-27:** Given ein erlaubter Edit an einem beweglichen Teil einer freigegebenen Spec / When `edit_verify.py` danach läuft / Then steht ein Eintrag mit `ts`, `tool` und `sections` in `spec_post_approval_edits` des Workflow-States
  - Test: `tests/test_spec_freeze_partial_hash_439.py::test_spur_nach_edit_an_beweglichem_teil`
- **AC-28:** Given ein vom Gate geblockter Edit bzw. eine Datei, die keine freigegebene `spec_file` ist / When `edit_verify.py` läuft / Then entsteht kein Spur-Eintrag
  - Test: `tests/test_spec_freeze_partial_hash_439.py::test_keine_spur_bei_geblocktem_edit_oder_fremder_datei`
- **AC-29:** Given ein defekter State, nicht lesbare Dateien oder fehlerhafte Eingaben / When `edit_verify.py` läuft / Then endet es immer mit Exit 0 und blockt nie
  - Test: `tests/test_spec_freeze_partial_hash_439.py::test_edit_verify_blockt_nie`
- **AC-30:** Given der bestehende Testbestand / When `tests/test_edit_gate_spec_freeze_230.py`, `tests/test_po_briefing_gate.py`, `tests/test_ci_spec_gate.py` und `tests/test_workflow_resolution_consolidation.py` laufen / Then sind sie nach den Fixture-Anpassungen grün
  - Test: `tests/test_edit_gate_spec_freeze_230.py`, `tests/test_po_briefing_gate.py`, `tests/test_ci_spec_gate.py`, `tests/test_workflow_resolution_consolidation.py` (Lauf grün)

> Die Test-Zuordnung steht **bei der Spec-Erstellung** hier, weil diese Spec selbst nach der Freigabe noch unter den alten Gesamt-Freeze (#230) fällt: Jede spätere Änderung verschiebt den PO-Briefing-Hash. Stimmt ein Testname später nicht mehr, gehört die Korrektur in die TDD-RED-Artefakte (`workflow.py add-artifact`).

## Test Plan

Automatische Tests (jeweils an eine AC oben gebunden):

- `pytest tests/test_spec_freeze_partial_hash_439.py` — Zerleger und `frozen_spec_sha256` als Unit-Tests; Edit-Gate und `edit_verify.py` als Subprozess gegen die echten Hooks in einer Sandbox mit Workflow-State, freigegebener Spec und Override-Tokens (Workflow, `__infra__`, global); `set-briefing`-Migration gegen echte Workflow-Dateien; Regressionstest gegen ein bestehendes Briefing aus `docs/briefings/`. Die RED-Läufe zeigen vor der Implementierung fehlende Funktion bzw. Block statt Erlaubnis und werden als Artefakte registriert.
- `pytest tests/test_edit_gate_spec_freeze_230.py tests/test_po_briefing_gate.py tests/test_ci_spec_gate.py tests/test_workflow_resolution_consolidation.py` — angepasste Fixtures und der umgedrehte Override-Test.
- Regression: `pytest tests/` (Vollsuite); danach `python3 scripts/sync_skills.py` und der Skills-Drift-Check.
- Risiko HOCH: zwei Adversary-Runden mit Schwerpunkt auf Klassifikations-Umgehungen (Verschieben, Zerteilen, Einrückung, Fences, CRLF, Unicode-Randfälle).

## Wo ich für dich entschieden habe

- **Nur Freigegebenes wird gesperrt.** Der Titel, Zweck, Umfang, Fertig-Kriterien, Abnahmetexte und die Architektur-Entscheidung bleiben nach deiner Freigabe fest. Begleittext wie Testnamen, Hinweise und Changelog darf Claude ohne Sonderfreigabe nachziehen. Alles, was nicht ausdrücklich als beweglich eingetragen ist, bleibt gesperrt; im Zweifel also lieber zu streng.
- **Der Testplan zählt als Begleittext.** Mehr als 60 vorhandene Specs führen die Testnamen auch im Testplan. Wäre er gesperrt, würde genau das Beispiel aus dem Ticket („Testname ändern“) weiter blockieren.
- **Der Freigabe-Haken darf nachträglich gesetzt werden.** Der Abschnitt „Approval“ in der Spec ist nur ein Merkzettel; ob freigegeben ist, steht im Workflow-Zustand. Wäre er gesperrt, würde schon das Abhaken als „Änderung am Freigegebenen“ blocken.
- **„override“ öffnet die Spec nicht mehr.** Bisher hat dein „override“ eine Stunde lang alles aufgemacht. Für die freigegebene Spec gilt das nicht mehr. Der Weg für echte Änderungen am Freigegebenen ist der Rücksprung in die Spezifikations-Phase mit neuem Briefing und neuer Freigabe. Das ist eine bewusste Verschärfung.
- **Alte Briefings bleiben gültig.** Bestehende Briefings werden nicht ungültig. Solange ein Workflow noch ein altes Briefing hat, gilt die bisherige komplette Sperre. Mit einem Befehl (`set-briefing`) wird das Briefing umgestellt, sofern sich die Spec seit der Freigabe nicht verändert hat; danach gilt die neue, lockerere Regel.
- **Zwei Prüfsummen statt einer.** Ältere Prüfungen in Fremdprojekten verstehen nur die alte Prüfsumme. Deshalb bleibt sie bestehen, und die neue kommt daneben. Dort, wo das Prüfskript noch alt ist, gelten Änderungen an Begleittext weiter als „veraltet“, bis das Projekt aktualisiert wird.
- **Eine Spur, kein Zusatz-Schloss.** Jede Änderung an Begleittext nach der Freigabe wird mit Zeit und Abschnitt im Workflow-Protokoll vermerkt. Fehler beim Protokollieren stören nie die Arbeit.
- **Unklare Edits werden geblockt.** Kann das Gate nicht sicher berechnen, was ein Edit bewirkt, blockt es und verlangt einen genaueren Edit. Das kann gelegentlich lästig sein, ist aber die sichere Seite.
- **Bash-Wege bleiben außen vor.** Änderungen an der Spec über die Kommandozeile erfasst dieses Ticket nicht (wie schon seit #230); eingefrorene Änderungen fallen spätestens beim nächsten Phasenwechsel auf.

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Die Änderung verfeinert die bestehende Entscheidung aus #230 („freigegebene Spec ist eingefroren, Kontrolle über den PO-Briefing-Hash“) von „ganze Datei“ auf „freigegebener Teil“; sie führt kein neues Architekturmuster ein und nutzt Kern-Gate, gehärtete State-API und CI-Gate-Wiederverwendung wie bisher. Das Breaking-Verhalten (override öffnet den Spec-Freeze nicht mehr) ist beabsichtigt und begründet: override öffnet sonst alle Gates für eine Stunde und ist damit zu grob für eine Nachbesserung an Begleittext; der Notausgang für echte Änderungen am Freigegebenen ist der Rücksprung nach `phase3_spec`, der Freigaben zurücksetzt (#405). Verworfen: Präfix-Version im selben Stempelfeld (würde alle committeten alten CI-Kopien in Konsumentenprojekten brechen, daher Doppelstempel), Wiederverwendung von `extract_ac_entries` (verwirft eingerückte Sub-Bullets, Bypass), Vereinheitlichung der Legacy-Hash-Funktionen (würde ~50 bestehende Briefings ungültig machen).

## Changelog

- 2026-10-13: Initial spec created (#439)
