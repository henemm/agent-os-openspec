---
entity_id: feat-591-spur
type: feature
created: 2026-11-13
updated: 2026-11-13
status: draft
version: "1.0"
workflow: feat-591-spur
tags: [workflow, endstate, vorschlag, spur, auftrag, herdr]
---

# Spur als Stufe 3 des nächsten Vorschlags (Issue #591, Teil B von #589)

## Approval

- [ ] Approved

## Purpose

Der PO kann einem Auftrag eine „Spur“ mitgeben, einen kurzen Namen für eine Reihe zusammengehöriger Aufgaben. Wenn eine Aufgabe fertig ist und kein Epic und kein Meilenstein weiterhilft, schlägt `workflow.py endstate` die nächste offene Aufgabe mit demselben GitHub-Label `spur:<name>` vor; bei einem autarken Auftrag macht Claude auf derselben Spur selbst weiter. Die Seitenleiste (herdr) zeigt die Spur nur an. Das ist Teil B von #589; Teil A (`docs/specs/feat-589-naechster-vorschlag.md`) hat den Parameter `spur=None` in `choose` bereits vorbereitet.

## Source

- **File:** `core/hooks/next_suggestion.py`, `core/hooks/hook_utils.py`, `core/hooks/workflow.py`, `core/hooks/herdr_bridge.py`
- **Identifier:** `next_suggestion.choose` (Stufe 3), `next_suggestion.SOURCE_TEXT`, `hook_utils.normalize_spur`, `hook_utils._normalize_auftrag`, `workflow.cmd_spur`, `workflow._parse_queue_add`, `workflow._print_queue`, `workflow._refresh_suggestion`, `workflow.cached_suggestion`, `herdr_bridge.TOKEN_NAMES`, `herdr_bridge.build_report`

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `docs/specs/feat-589-naechster-vorschlag.md` (Teil A, auf main) | spec | Rangfolge, `choose`, Cache, Autark-Anhängen; bleibt gültig und wird nur um Stufe 3 erweitert |
| `docs/specs/feat-551-auftragsliste.md`, `docs/specs/feat-466-herdr-sidebar.md` | spec | Auftrag (`.claude/auftrag.json`) und Seitenleiste; Verhalten ohne Spur bleibt unverändert |
| `core/hooks/hook_utils.py` (`_normalize_auftrag`, `read_auftrag`, `write_auftrag`, `auftrag_mark_done`) | module | Feld `spur` im Auftrag; ohne Aufnahme in die Normalisierung ginge es bei jedem Lesen/Schreiben verloren |
| `core/hooks/workflow.py` (`cmd_endstate`, `_refresh_suggestion`, `cached_suggestion`, `queue_end_args`, `cmd_queue`, `COMMANDS`) | module | CLI, Durchreichen der Spur an `choose`, Autark-Menge |
| `core/hooks/next_suggestion.py` (`_labels`, `_excluded`, `_sort_key`, `fetch`) | module | Labels stecken schon in der Antwort `issues?state=open&per_page=100`; kein neuer Netzaufruf |
| `core/hooks/herdr_bridge.py` (`build_report`, `TOKEN_NAMES`, `clear`, `report_workflow`) | module | Token `spur`, nur Anzeige |
| GitHub-Label `spur:<name>` | extern, Pflege durch Claude/PO | Abbildung der Spur an den Issues; das Framework legt keine Labels an |
| `core/commands/00-intake.md`, `scripts/sync_skills.py`, `skills/00-intake/SKILL.md` | doc/script | Befehlstext Schritt 1a, Generat |
| `tests/test_naechster_vorschlag_589.py`, `tests/test_auftrag_551.py`, `tests/test_herdr_sidebar_466.py` | test | Fixtures und Regressionsschutz; `TOKEN_NAMES`-Liste in `test_herdr_sidebar_466.py` wird mitgezogen |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| core/hooks/hook_utils.py | MODIFY | `normalize_spur(value)`; `_normalize_auftrag` übernimmt `spur`; Helfer `auftrag_set_spur(root, name)` |
| core/hooks/workflow.py | MODIFY | `queue add --spur`, neues `cmd_spur` + `COMMANDS["spur"]`, `SPUR=` in `_print_queue`, `QUEUE_USAGE`, Spur an `choose` in `_refresh_suggestion`/`cached_suggestion`, Autark-Menge um `spur` |
| core/hooks/next_suggestion.py | MODIFY | Stufe 3 in `choose`, `SOURCE_TEXT["spur"]`, Docstring (Platzhalter „kommt mit #591“ entfällt) |
| core/hooks/herdr_bridge.py | MODIFY | Token `spur` in `TOKEN_NAMES` und `build_report` |
| core/commands/00-intake.md | MODIFY | Schritt 1a nennt `--spur <name>` und das Label `spur:<name>` |
| skills/00-intake/SKILL.md | MODIFY | Generat per `python3 scripts/sync_skills.py` |
| tests/test_spur_591.py | CREATE | Tests zu allen AC; `gh` per Stub/Monkeypatch, kein Netz |
| tests/test_herdr_sidebar_466.py | MODIFY | Erwartete `TOKEN_NAMES` um `spur` ergänzen |
| tests/test_naechster_vorschlag_589.py | MODIFY (nur bei Bedarf) | Falls ein Test den Platzhalter „kommt mit #591“ oder die Wirkungslosigkeit von `spur` festschreibt |
| CHANGELOG.md | MODIFY | Eintrag unter `[Unreleased]` → `### Added`, nennt #591 |
| docs/specs/feat-591-spur.md | CREATE | diese Spec |

Nicht im Scope: neuer Kill-Switch, Anlegen von GitHub-Labels, Schreibpfad aus herdr in den Auftrag, Versionsnummer, `setup.py`.

### Estimated Changes

- Files: 6 Quell-/Befehlsdateien, 1 Generat, 2 Testdateien, CHANGELOG, Spec
- LoC: +90 bis +130 Produktivcode, +150 bis +200 Test
- Risk Level: LOW bis MEDIUM (ohne gesetzte Spur keine Wirkung; Hauptrisiko ist `_normalize_auftrag`, den viele Leser nutzen, und der Mengenvergleich der Seitenleisten-Tokens im Test)

## Implementation Details

**Namensregel (`hook_utils.normalize_spur`).** Ein führendes `spur:` wird toleriert und abgeschnitten. Dann: trimmen, Kleinschreibung, Leerzeichen und Unterstriche zu `-`, nur `[a-z0-9-]` behalten, mehrfache `-` zusammenziehen, `-` an den Rändern entfernen, auf 40 Zeichen kürzen (danach Ränder erneut strippen). Kein String, leeres oder nach der Bereinigung leeres Ergebnis ist ungültig (`None`). Das Label in GitHub heißt immer `spur:<name>`.

**Auftrag.** `_normalize_auftrag` bekommt das Feld `spur` (Text, Standard `""`, kaputte oder ungültige Werte werden zu `""`). Es bleibt bei `auftrag_mark_done`, `queue add` und jedem `write_auftrag` erhalten. `queue clear` löscht wie bisher die ganze Datei und damit auch die Spur.

**CLI.**
- `workflow.py queue add <N...> [--autark] [--note T] [--spur NAME]` setzt oder überschreibt die Spur; ohne `--spur` bleibt eine vorhandene Spur unverändert.
- `workflow.py spur NAME` setzt die Spur und legt bei Bedarf einen Auftrag mit leerer Liste an; `workflow.py spur --clear` setzt sie auf leer (die Datei bleibt bestehen); `workflow.py spur` ohne Argument zeigt nur an. Ausgabe immer `SPUR=<name>` bzw. `SPUR=none`.
- Ein ungültiger Name ergibt eine Fehlermeldung auf stderr, Exit 1 und die Usage; es wird nichts geschrieben.
- `_print_queue` gibt zusätzlich die Zeile `SPUR=<name>|none` aus.
- Kill-Switch `auftrag.enabled: false` (nur Literal `false`) ergibt wie bei `queue` die Ausgabe `SPUR=disabled` ohne Schreibzugriff.

**Auswahl (`choose`).** `choose(raw, done, claimed, spur=...)` hängt nach der Meilenstein-Stufe die Stufe `("spur", Kandidaten)` ein, wenn `spur` gesetzt ist. Kandidaten sind die offenen Issues, deren Labels (case-insensitiv, getrimmt) den Eintrag `spur:<name>` enthalten. Ausschlüsse (`_excluded`) und Sortierung (`_sort_key`) bleiben unverändert. Ergibt die Stufe keinen Treffer, etwa weil das Label nirgends vergeben ist, greift die nächste Stufe (verwandt, Priorität); das ist kein Fehler. `SOURCE_TEXT["spur"] = "gleiche Spur"`. Die Rangfolge lautet damit Epic, Meilenstein, Spur, verwandt, Priorität (PO-Vorgabe: Epic in GitHub zuerst, sonst die gesetzte Spur).

**Durchreichen.** Ein kleiner Helfer `_auftrag_spur()` in `workflow.py` liest `read_auftrag` und liefert die Spur oder `None`; er wirft nie. `cached_suggestion` und `_refresh_suggestion` rufen `choose(..., spur=_auftrag_spur())`. Der Cache hält Rohdaten, nicht die Auswahl; ein Spurwechsel wirkt deshalb sofort ohne Cache-Invalidierung.

**Autark.** In `_refresh_suggestion` wird die Menge der selbststartenden Quellen von `("epic", "milestone")` zu `("epic", "milestone", "spur")`. Angehängt wird nur bei `autark is True` und idempotent per Nummernvergleich wie in Teil A; ohne autark bleibt es bei der Vorschlagszeile.

**herdr.** `TOKEN_NAMES` bekommt `spur`; `build_report` füllt das Token aus der Spur des Auftrags (bereinigt über `_clean`); ohne Spur bleibt das Token leer wie `next`. `clear` und `report_workflow` iterieren weiter über `TOKEN_NAMES`. Fail-open; herdr liest oder schreibt nie einen Spur-Wert zurück, die Hoheit liegt beim Framework.

**Befehlstext.** `core/commands/00-intake.md`, Schritt 1a: Hat der PO eine Spur genannt oder gehört die Aufgabe zu einer erkennbaren Reihe, wird `--spur <name>` mitgegeben; das Label `spur:<name>` muss an den Issues in GitHub gesetzt sein; Epic hat Vorrang, die Spur wirkt als Stufe 3. Danach `python3 scripts/sync_skills.py`.

## Expected Behavior

- **Input:** `workflow.py spur NAME|--clear|<leer>`, `workflow.py queue add … --spur NAME`, abgeschlossener Workflow (`workflow.py endstate`), offene Issues mit Label `spur:<name>`
- **Output:** `SPUR=<name>|none|disabled`; bei fertigem Workflow ohne Epic-/Meilenstein-Nachfolger ein Vorschlag mit Quelle „gleiche Spur“ (`SUGGEST_SOURCE=spur`); bei autarkem Auftrag die Kettenzeile „⏳ Läuft noch: Claude startet #M aus deinem Auftrag …“; in der Seitenleiste das Token `spur`
- **Side effects:** Feld `spur` in `.claude/auftrag.json` (bei Bedarf wird die Datei mit leerer Liste angelegt); idempotentes Anhängen an den Auftrag nur bei autark; kein zusätzlicher Netzaufruf, kein Anlegen von Labels

## Known Limitations

- Der Auftrag gilt je Projekt, nicht je Sitzung: parallele Sitzungen im selben Projekt teilen sich eine Spur.
- Das Framework legt keine GitHub-Labels an; `spur:<name>` muss an den Issues bereits stehen (Pflege durch Claude/PO). Fehlt das Label, greift die nächste Stufe ohne Fehlermeldung.
- `queue clear` löscht den ganzen Auftrag samt Spur; die Spur separat zu löschen geht mit `spur --clear`.
- Es gilt die 100er-Seite der offenen Issues aus Teil A; Spur-Issues jenseits davon werden nicht gefunden.
- Ein Spur-Vorschlag startet nur bei autarkem Auftrag selbst; sonst bleibt er eine Vorschlagszeile.

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] Nach einer fertigen Aufgabe ohne Epic-/Meilenstein-Nachfolger nennt die Schlusszeile die nächste Aufgabe mit demselben `spur:<name>`-Label („gleiche Spur“); ein autarker Auftrag macht auf derselben Spur selbst weiter, ohne Doppelanhängen
- [ ] Die Seitenleiste zeigt die gesetzte Spur an und nichts, wenn keine gesetzt ist
- [ ] Ohne gesetzte Spur oder bei ausgeschaltetem Schalter verhält sich alles exakt wie vorher
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf `pytest tests/` grün)

## Acceptance Criteria

Testaufbau: `choose` wird rein mit Rohdaten-Dictionaries getestet (Fixtures aus `tests/test_naechster_vorschlag_589.py`). CLI und `cmd_endstate` laufen in einem temporären Projekt mit `gh`-Stub im PATH; Netzfreiheit wird über einen Stub geprüft, der bei Aufruf einen Marker schreibt. Kein Netz, kein echtes GitHub.

- **AC-1:** Given Eingaben mit Großschreibung, Leerzeichen, Unterstrichen, Sonderzeichen, Präfix `spur:`, Mehrfach-Bindestrichen, mehr als 40 Zeichen sowie leer, nur Sonderzeichen oder kein String / When `normalize_spur` läuft / Then entsteht ein Name aus `[a-z0-9-]` ohne Rand-/Doppel-Bindestriche mit höchstens 40 Zeichen, und leere oder ungültige Eingaben ergeben `None`
  - Test: tests/test_spur_591.py::TestNamensregel::test_normalisierung_und_ungueltige_werte

- **AC-2:** Given ein Auftrag mit `spur` / When er per `write_auftrag`, `read_auftrag`, `auftrag_mark_done` und `queue add` ohne `--spur` hin- und hergeschrieben wird / Then bleibt die Spur erhalten, und ein fehlendes oder ungültiges Feld (Zahl, Liste, nur Sonderzeichen) wird zu `""` verworfen, ohne die übrigen Felder zu beschädigen
  - Test: tests/test_spur_591.py::TestAuftragRoundTrip::test_spur_bleibt_erhalten_ungueltig_wird_verworfen

- **AC-3:** Given ein Projekt mit und ohne Auftrag / When `workflow.py spur NAME`, `spur` ohne Argument und `spur --clear` laufen / Then setzt der erste Aufruf die normalisierte Spur (legt bei Bedarf einen Auftrag mit leerer Liste an), der zweite zeigt `SPUR=<name>` bzw. `SPUR=none` ohne zu schreiben, der dritte leert die Spur, lässt die Datei bestehen, und ein ungültiger Name endet mit Exit 1, Usage auf stderr und ohne Schreibzugriff
  - Test: tests/test_spur_591.py::TestCliSpur::test_setzen_zeigen_leeren_und_ungueltiger_name

- **AC-4:** Given ein Auftrag und der Aufruf `queue add <N> --autark --spur "Mein Thema"` / When er läuft / Then enthält der Auftrag die Nummer, `autark: true` und die Spur `mein-thema`; ein späteres `queue add` ohne `--spur` ändert die Spur nicht, ein erneutes mit `--spur` überschreibt sie
  - Test: tests/test_spur_591.py::TestCliSpur::test_queue_add_spur_setzt_und_ueberschreibt

- **AC-5:** Given Aufträge mit und ohne Spur sowie `auftrag.enabled: false` (Literal `false`) / When `queue` (Anzeige) und `spur` laufen / Then gibt `_print_queue` zusätzlich `SPUR=<name>` bzw. `SPUR=none` aus, und bei ausgeschaltetem Auftrag liefert `spur` `SPUR=disabled` ohne Schreibzugriff; andere Werte, fehlender Abschnitt und kaputte Config gelten als „an“
  - Test: tests/test_spur_591.py::TestAnzeigeKillSwitch::test_spur_zeile_und_disabled

- **AC-6:** Given offene Geschwister (Epic), Aufgaben im selben Meilenstein, Aufgaben mit Label `spur:x` und eine verwandte Aufgabe / When `choose(..., spur="x")` läuft und die höheren Stufen nacheinander entfallen / Then gewinnt Epic vor Meilenstein vor Spur vor verwandt vor Priorität, die Spur-Stufe liefert `source="spur"` mit Text „gleiche Spur“, und ausgeschlossene Issues (erledigt, geclaimt, `status:deferred`, offener PR) werden auch auf der Spur nicht vorgeschlagen
  - Test: tests/test_spur_591.py::TestChooseSpur::test_rang_nach_meilenstein_vor_verwandt_und_ausschluesse

- **AC-7:** Given Labels `Spur:X`, ` spur:x ` und ein Issue ohne passendes Label, sowie eine gesetzte Spur ohne jedes Issue mit diesem Label / When `choose` läuft / Then trifft der Vergleich case-insensitiv und getrimmt, die Sortierung innerhalb der Stufe bleibt Meilenstein, Fälligkeit, Priorität, Nummer, und fehlt das Label überall, greift die nächste Stufe ohne Ausnahme; ohne gesetzte Spur ist das Ergebnis identisch zu Teil A
  - Test: tests/test_spur_591.py::TestChooseSpur::test_case_insensitiv_fehlendes_label_naechste_stufe_ohne_spur_wie_vorher

- **AC-8:** Given ein Auftrag mit Spur, gefüllter Cache und ein Epic-/Meilenstein-loser Rest / When `workflow.py endstate` läuft und `cached_suggestion` liest / Then übergeben beide die Spur aus dem Auftrag an `choose`, `SUGGEST_SOURCE=spur` und die Schlusszeile nennt „gleiche Spur“; nach einem Spurwechsel wirkt die neue Spur sofort ohne neuen Netzabruf
  - Test: tests/test_spur_591.py::TestEndstateSpur::test_endstate_und_cache_nutzen_spur_des_auftrags

- **AC-9:** Given ein autarker Auftrag ohne weiteres offenes Issue und ein Spur-Vorschlag M / When `endstate` ein- und zweimal läuft / Then steht M genau einmal im Auftrag und die Zeile ist „⏳ Läuft noch: Claude startet #M aus deinem Auftrag …“; bei nicht autarkem Auftrag wird nichts angehängt und es bleibt bei der Vorschlagszeile; Epic und Meilenstein starten weiterhin selbst, `related` und `priority` weiterhin nicht
  - Test: tests/test_spur_591.py::TestAutarkSpur::test_anhaengen_idempotent_nur_bei_autark

- **AC-10:** Given ein gefüllter Cache und ein Auftrag mit Spur / When `end_state`, `queue_end_args`, `render_plan` und die Seitenleiste dieselbe Schlusszeile bauen / Then rufen sie keinen `gh`-Stub auf (Marker bleibt aus) und zeigen dieselbe Zeile wie `endstate`; die Spur kommt ausschließlich aus dem Auftrag und den bereits gecachten Labels
  - Test: tests/test_spur_591.py::TestNetzfrei::test_plan_und_seitenleiste_ohne_netzaufruf

- **AC-11:** Given ein Auftrag mit und ohne Spur / When `herdr_bridge.build_report` läuft und `TOKEN_NAMES` ausgewertet wird / Then enthält `TOKEN_NAMES` `spur`, das Token trägt den Spurnamen, bleibt ohne Spur leer, `clear` und `report_workflow` behandeln es wie die übrigen Tokens, ein Fehler beim Lesen des Auftrags bleibt fail-open, und es gibt keinen Schreibpfad von herdr in den Auftrag
  - Test: tests/test_spur_591.py::TestHerdrAnzeige::test_token_spur_nur_anzeige_fail_open

- **AC-12:** Given `core/commands/00-intake.md` und `skills/00-intake/SKILL.md` / When gelesen / Then nennt Schritt 1a `--spur <name>`, das Label `spur:<name>` und den Vorrang von Epic, und das Skill-Generat ist synchron zum Befehlstext (`scripts/sync_skills.py --check` bzw. `test_command_texts_and_skills_in_sync`)
  - Test: tests/test_spur_591.py::TestDokumentation::test_befehlstext_und_skill_synchron

- **AC-13:** Given `CHANGELOG.md` / When gelesen / Then nennt `[Unreleased]` → `### Added` die Spur und `#591`, und es steht keine neue Versionsnummer darin
  - Test: tests/test_spur_591.py::TestDokumentation::test_changelog_nennt_591

- **AC-14:** Given die bestehenden Testdateien zu #589, #551 und #466 / When sie laufen (mit der um `spur` ergänzten `TOKEN_NAMES`-Liste in `test_herdr_sidebar_466.py`) / Then bleiben sie grün, und ohne gesetzte Spur ist jede Ausgabe der betroffenen Kommandos (`queue`, `endstate`, Plan, Seitenleiste) bis auf die neuen Zeilen `SPUR=` bzw. das leere Token unverändert
  - Test: tests/test_spur_591.py::TestRegression::test_ohne_spur_unveraendert

## Test Plan

Automatische Tests (jeweils an eine AC oben gebunden):

- `pytest tests/test_spur_591.py`
- Regressionslauf: `pytest tests/` (insbesondere `test_naechster_vorschlag_589.py`, `test_auftrag_551.py`, `test_herdr_sidebar_466.py`, `test_endzustand_550.py`, `test_footer_gate_234.py`)
- `python3 -m py_compile core/hooks/next_suggestion.py core/hooks/hook_utils.py core/hooks/workflow.py core/hooks/herdr_bridge.py`
- `python3 scripts/sync_skills.py --check`

TDD-Reihenfolge: Die Tests werden vor dem Code geschrieben und schlagen zuerst fehl (`normalize_spur`, `cmd_spur`, Stufe 3 und Token fehlen). Beispiele (GIVEN/WHEN/THEN):

- GIVEN die Eingabe „  Mein Thema_2 “ WHEN `normalize_spur` läuft THEN kommt `mein-thema-2` zurück.
- GIVEN zwei offene Issues, nur eines mit Label `spur:x`, kein Epic und kein Meilenstein WHEN `choose(..., spur="x")` läuft THEN wird genau dieses Issue mit `source=spur` vorgeschlagen.
- GIVEN ein autarker Auftrag ohne offenes Issue und ein Spur-Vorschlag WHEN `endstate` zweimal läuft THEN steht die Nummer einmal im Auftrag.
- GIVEN ein Auftrag mit Spur `x` WHEN `build_report` läuft THEN trägt das Token `spur` den Wert `x`, und ohne Spur ist es leer.

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** `docs/adr/` enthält keine Einträge, und die Änderung folgt vorhandenen Mustern: Auftragsfeld in `_normalize_auftrag`, Stufe in der reinen Funktion `choose` mit `SOURCE_TEXT`, `KEY=value`-Ausgabe in `_print_queue`, Kill-Switch „nur Literal false“ wie `auftrag:`, Seitenleiste als reine Anzeige. Kein neuer Netzaufruf, kein neuer Kill-Switch, per Entfernen des Feldes rückbaubar. Verworfen: (a) Spur je Sitzung statt je Projekt, weil der Auftrag projektweit liegt und ein Sitzungsspeicher ein neues Register bräuchte (als Known Limitation geführt); (b) Anlegen der GitHub-Labels durch das Framework, weil das ein Schreibzugriff am Live-System wäre; (c) Spur vor Epic/Meilenstein, weil der PO „Epic in GitHub zuerst“ vorgegeben hat.

## Changelog

- 2026-11-13: Initial spec created
