---
entity_id: feat-589-naechster-vorschlag
type: feature
created: 2026-11-12
updated: 2026-11-12
status: draft
version: "1.0"
workflow: feat-589-naechster-vorschlag
tags: [workflow, endstate, vorschlag, epic, meilenstein, autark]
---

# Nächster Vorschlag nach dem Abschluss (Issue #589, Teil A)

## Approval

- [ ] Approved

## Purpose

Meldet ein Workflow „fertig“, soll die Schlusszeile von `workflow.py endstate` gleich die passende nächste Aufgabe nennen (`/00-intake #M` mit kurzer Begründung), statt nur „nächstes Issue starten“. Die Auswahl folgt der PO-Rangfolge Epic-Geschwister, gleicher Meilenstein, verwandte Aufgabe, wichtigste offene Aufgabe; bei einem autarken Auftrag setzt sich die Kette bei Epic und Meilenstein von selbst fort. Teil B (freie „Spur“, Anzeige in herdr) ist Issue #591 und nicht Teil dieser Spec; `choose()` hat dafür nur den Parameter `spur=None`.

## Source

- **File:** `core/hooks/next_suggestion.py` (neu), Anbindung in `core/hooks/workflow.py`
- **Identifier:** `next_suggestion.choose`, `next_suggestion.fetch`, `next_suggestion.read_cache`/`write_cache`, `next_suggestion.settings`; in `workflow.py` `end_state(suggest=)`, `queue_end_args`, `cmd_endstate`

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `gh` CLI (REST über `gh api`, nie GraphQL) | extern, optional | Eltern-Issue, Sub-Issues, offene Issues samt Labels/Meilenstein/Body, offene PRs; fehlt es, gibt es keinen Vorschlag |
| `core/hooks/workflow.py` (`end_state`, `_end_state_final`, `_end_state_queue`, `queue_end_args`, `cmd_endstate`, `_read_session_entries`, `workflow_issue_number`) | module | Zeilenbau, Cache-Lesen, Netzabruf im Kommando, Session-Register |
| `core/hooks/hook_utils.py` (`read_auftrag`, `write_auftrag`, `auftrag_open_issues`, `auftrag_autark_open`, `atomic_write_text`, `read_state_text`) | module | Auftrag lesen/anhängen, atomarer Cache |
| `core/hooks/footer_gate.py`, `core/hooks/herdr_bridge.py` | module | bleiben unverändert; nur Nachweis, dass sie die erweiterte Zeile nicht stören |
| `config.yaml` (Muster `auftrag:`) | config | neuer Abschnitt `next_suggestion:` mit Kill-Switch |
| `core/commands/60-validate.md`, `scripts/sync_skills.py` | doc/script | Befehlstext „Abschluss: Endzustand melden“, Generat `skills/60-validate/SKILL.md` |
| `docs/specs/fix-550-endzustand.md`, `feat-551-auftragsliste.md`, `fix-555-nacharbeit-endzustand.md` | spec | Identität Plan = `endstate`, Kette, Eigen-Nummer-Ausschluss; bleiben gültig |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| core/hooks/next_suggestion.py | CREATE | `choose` (rein), `fetch` (REST, fail-open), Cache, Settings |
| core/hooks/workflow.py | MODIFY | `end_state(suggest=)`, `queue_end_args` liest Cache, `cmd_endstate` ruft `fetch`, gibt `SUGGEST_*` aus, hängt bei autark an |
| config.yaml | MODIFY | Abschnitt `next_suggestion:` (`enabled`, `timeout_s`, `cache_ttl_s`) |
| core/commands/60-validate.md | MODIFY | Abschnitt „Abschluss: Endzustand melden“ beschreibt den Vorschlag |
| skills/60-validate/SKILL.md | MODIFY | Generat aus `core/commands/60-validate.md` per `python3 scripts/sync_skills.py` |
| CHANGELOG.md | MODIFY | Eintrag unter `[Unreleased]` → `### Added`, nennt #589 |
| tests/test_naechster_vorschlag_589.py | CREATE | Tests zu allen AC; `gh` per PATH-Stub bzw. Monkeypatch, kein Netz |
| docs/specs/feat-589-naechster-vorschlag.md | CREATE | diese Spec |

Nicht im Scope: Spur und Spur-Anzeige (#591), `herdr_bridge.py`, `footer_gate.py`, `hook_utils._normalize_auftrag`, `00-intake.md`, `setup.py`, Versionsnummer.

### Estimated Changes

- Files: 6 im Code-/Doku-Bereich plus Generat und Spec
- LoC: +200 Modul, +80 `workflow.py`, +40 Rest, +250 Test
- Risk Level: MEDIUM (berührt die Schlusszeile in `workflow.py`, die Plan, Seitenleiste und Kette speist; abgefedert durch Fail-open und Byte-Gleichheit ohne Vorschlag)

## Implementation Details

**Reine Auswahl `choose`.** `next_suggestion.choose(raw, done_number, claimed, spur=None, now=None)` bekommt die Rohdaten (offene Issues, Eltern-Beziehung der erledigten, Geschwister, offene Meilensteine, Nummern mit offenem PR), die Nummer der erledigten Aufgabe und die von anderen Sitzungen beanspruchten Nummern. Sie macht keinen Netz-, Datei- oder Config-Zugriff und liefert `{"n", "source", "reason", "title"}` oder `None`.

**Rangfolge.** Stufe 1 `epic` (offene Geschwister unter demselben Eltern-Issue), Stufe 2 `milestone` (offene Aufgaben im Meilenstein der erledigten), Stufe 3 Spur (nur Parameter `spur`, in Teil A ohne Wirkung), Stufe 4 `related` (Body enthält streng `Folge zu #N`, `aus #N` oder `Follow-up (to|of) #N` mit N = erledigte Nummer; sonstige Nennungen von `#N` zählen nicht), Stufe 5 `priority` (wichtigste offene Aufgabe überhaupt). Die erste Stufe mit mindestens einem Kandidaten gewinnt.

**Sortierung innerhalb einer Stufe.** Aufgabe mit Meilenstein vor ohne; früheres `due_on` zuerst (Meilenstein ohne `due_on` nachrangig); dann Priorität `priority:critical` > `high` > `medium` > `low` > ohne Label; zuletzt kleinste Nummer als stabiler Tie-Breaker.

**Ausschlüsse.** Die erledigte selbst; geschlossene; Einträge mit Schlüssel `pull_request` (PRs); Label `epic` (Container); Label `status:deferred`; Label `spec-proposal`; Eltern-Issues mit offenen Sub-Issues (nur Blätter werden vorgeschlagen); Issues, die eine andere Sitzung laut Session-Register beansprucht (`claimed`); Issues mit offenem PR, soweit erkennbar (Nummer im PR-Titel, Branch oder Body als `#N`/`Closes #N`; der PR-Abruf ist optional und fail-open).

**Abruf `fetch`.** `fetch(root, timeout_s)` nutzt ausschließlich `gh api` (REST) mit `shutil.which("gh")`-Prüfung, `subprocess.run(..., timeout=..., stdin=DEVNULL, cwd=root)`, Abfangen von `TimeoutExpired`, Rückgabecode und kaputtem JSON. Aufrufe: `issues/N/parent`, `issues/<Eltern>/sub_issues`, `issues?state=open&per_page=100`, `milestones?state=open`, optional `pulls?state=open`. Jeder Fehler ergibt `None`, nie eine Ausnahme. Die 100er-Seite wird ohne Fehler abgeschnitten.

**Cache.** Die Rohdaten (nicht das Ergebnis) liegen in `.claude/next_suggestion.json` im Haupt-Repo, atomar über `atomic_write_text`, mit Zeitstempel und der erledigten Nummer als Schlüssel; Standard-TTL 300 s (`cache_ttl_s`). `choose` läuft bei jedem Lesen frisch auf den Rohdaten, damit das Session-Register nie veraltet. Ein abgelaufener oder fremder Cache liefert keinen Vorschlag.

**Anbindung in `workflow.py`.** Nur `cmd_endstate` holt Netzdaten (einmal je Aufruf, TTL schützt vor Wiederholung). `end_state` und `render_plan` bleiben rein: `end_state` bekommt den Parameter `suggest` und baut den Zusatz nur im Fall „fertig, kein offener Auftrag“ (Art `done`). `queue_end_args` liest den Vorschlag ausschließlich aus dem Cache (`choose` auf Cache-Rohdaten, kein Netz); Plan und Seitenleiste zeigen damit dieselbe Zeile wie `endstate`, sobald `endstate` einmal gelaufen ist, vorher die heutige Zeile. `end_state()["kind"]` bleibt `done`.

**Zeilenform.** Die Schlusszeile bleibt eine einzige ✅-Zeile. Der heutige Schluss „Du kannst /clear ausführen und das nächste Issue starten.“ wird mit Vorschlag zu „Du kannst /clear ausführen und mit /00-intake #M weitermachen (<Quelle>: <Kurztitel>).“ Die Quelle in Alltagssprache: `epic` = „gleiche Sammelaufgabe“, `milestone` = „gleicher Meilenstein“, `related` = „knüpft an eine Aufgabe an“, `priority` = „wichtigste offene Aufgabe“. Der Kurztitel wird auf 60 Zeichen gekürzt; die Zeile enthält keine Git-Wörter. Ohne Vorschlag bleibt die Zeile byte-gleich.

**Zusatzzeilen der Ausgabe.** `cmd_endstate` gibt nur bei vorhandenem Vorschlag `SUGGEST_ISSUE=<M>`, `SUGGEST_SOURCE=epic|milestone|related|priority` und `SUGGEST_REASON=<Text in Klammern>` aus. `ENDSTATE=` und `FOOTER=` bleiben unverändert aufgebaut.

**Auftrag hat Vorrang.** Hat ein offener Auftrag ein nächstes Issue (`queue_next`), gilt unverändert `_end_state_queue`; ein Vorschlag wird dann weder berechnet noch angezeigt noch angehängt.

**Autark.** Ist der Auftrag autark, hat kein nächstes Issue mehr und stammt der Vorschlag aus `epic` oder `milestone`, hängt `cmd_endstate` die Nummer M an den Auftrag (`write_auftrag`) und rechnet `queue_end_args` neu; das Ergebnis ist die bestehende Kettenzeile „⏳ Läuft noch: Claude startet #M aus deinem Auftrag …“. Das Anhängen ist idempotent: steht M schon im Auftrag (offen oder erledigt), geschieht nichts. Bei `related` und `priority` bleibt es beim Vorschlag. Begründung: Epic und Meilenstein sind die Spur des Auftrags und in ihrer Größe begrenzt.

**Kill-Switch.** `config.yaml` → `next_suggestion.enabled`; nur das Literal `false` schaltet ab (Muster `auftrag_settings`), andere Werte, fehlender Abschnitt und kaputte Config bedeuten „an“. Aus: kein Netzabruf, kein Cache-Lesen, heutige Zeile.

**footer_gate und Auto-/clear bleiben unberührt.** Der Zusatz steht in der ✅-Zeile; `footer_gate.py` wertet nur ❗Du-Zeilen aus, `expected_footer_command` liefert in Phase 8 `None`, und `herdr_bridge.maybe_auto_clear` bricht dort mangels Slash-Befehl als nächstem Pflichtschritt ab. Der Vorschlag löst also weder eine Blockade noch ein automatisches `/clear` aus.

**Befehlstext.** `core/commands/60-validate.md` (Abschnitt „Abschluss: Endzustand melden“) sagt: die Zeile aus `FOOTER=` wörtlich ausgeben (sie enthält den Vorschlag); die Kette wird weiterhin nur bei „aus deinem Auftrag“ in der Zeile gestartet, nie wegen eines bloßen Vorschlags; `SUGGEST_*` sind Auskunft für Claude. `skills/60-validate/SKILL.md` wird per `scripts/sync_skills.py` erzeugt.

## Expected Behavior

- **Input:** Abgeschlossener Workflow (`workflow.py endstate [N]`), optional Auftrag, Session-Register, `gh` mit Zugriff aufs Repo
- **Output:** Eine ✅-Zeile mit Zusatz „mit /00-intake #M weitermachen (<Quelle>: <Kurztitel>)“ plus `SUGGEST_ISSUE=`, `SUGGEST_SOURCE=`, `SUGGEST_REASON=`; bei autarkem Auftrag mit Epic-/Meilenstein-Vorschlag stattdessen die Kettenzeile „⏳ … startet #M aus deinem Auftrag …“
- **Side effects:** Cache `.claude/next_suggestion.json` (atomar); bei autarkem Auftrag idempotentes Anhängen einer Nummer an `.claude/auftrag.json`; sonst keine

## Known Limitations

- Ohne `gh`, Anmeldung oder Netz gibt es keinen Vorschlag; die heutige Zeile bleibt, ohne Hinweis (fail-open).
- Die Issue-Liste ist auf 100 offene Einträge gedeckelt; in größeren Projekten kann ein passender Kandidat fehlen.
- „Verwandt“ erkennt nur die strengen Muster `Folge zu #N`, `aus #N`, `Follow-up (to|of) #N`; freie Erwähnungen zählen bewusst nicht.
- Die Erkennung „offener PR“ ist eine Heuristik auf Nummern in PR-Titel, Branch und Body.
- Plan und Seitenleiste zeigen den Vorschlag erst, nachdem `endstate` einmal gelaufen ist und der Cache gültig ist (TTL 300 s).
- Die Spur (Stufe 3) hat in dieser Fassung keine Wirkung; sie kommt mit #591.
- Ein autarker Auftrag arbeitet bei Epic und Meilenstein bis zu deren Ende durch; die Länge begrenzt nur die Größe von Epic bzw. Meilenstein.

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] Nach einem abgeschlossenen Auftrag nennt die Schlusszeile in einer Zeile die passende nächste Aufgabe samt Grund in Alltagssprache; ohne Vorschlag ist sie unverändert
- [ ] Ein autarker Auftrag startet bei Epic- oder Meilenstein-Nachfolgern die nächste Aufgabe selbst, ohne dass ein Auftrag doppelt angehängt wird
- [ ] Ohne `gh`/Netz oder bei ausgeschaltetem Schalter verhält sich der Abschluss exakt wie vorher
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf `pytest tests/` grün)

## Acceptance Criteria

Testaufbau: `choose` wird tabellarisch mit Rohdaten-Dictionaries getestet (rein, ohne Mock). `fetch` und `cmd_endstate` laufen mit einem `gh`-Stub im PATH (`tmp_path`), der feste JSON-Antworten liefert oder fehlschlägt; kein Netz, kein echtes GitHub.

- **AC-1:** Given offene Geschwister unter demselben Eltern-Issue, Aufgaben im selben Meilenstein, eine verwandte und eine allgemein wichtige Aufgabe / When `choose` läuft / Then gewinnt die höchste vorhandene Stufe in der Reihenfolge Epic, Meilenstein, verwandt, Priorität und liefert `source` entsprechend
  - Test: tests/test_naechster_vorschlag_589.py::TestChooseRangfolge::test_stufen_epic_vor_meilenstein_vor_verwandt_vor_prioritaet

- **AC-2:** Given mehrere Kandidaten in derselben Stufe mit und ohne Meilenstein, mit verschiedenen Fälligkeiten und Prioritäten / When `choose` läuft / Then gilt Meilenstein vor ohne, früheres `due_on` zuerst, dann `critical` > `high` > `medium` > `low`, dann kleinste Nummer
  - Test: tests/test_naechster_vorschlag_589.py::TestChooseSortierung::test_meilenstein_faelligkeit_prioritaet_nummer

- **AC-3:** Given Kandidaten, die erledigte selbst, geschlossen, Pull Request (Schlüssel `pull_request`), Label `epic`, `status:deferred`, `spec-proposal`, Eltern mit offenen Sub-Issues oder mit offenem PR sind / When `choose` läuft / Then wird keiner davon vorgeschlagen
  - Test: tests/test_naechster_vorschlag_589.py::TestChooseAusschluesse::test_ausgeschlossene_kandidaten

- **AC-4:** Given ein Issue, das laut Session-Register eine andere Sitzung beansprucht, auch als Komma-Liste / When `choose` läuft / Then wird es übersprungen und die nächste Aufgabe vorgeschlagen
  - Test: tests/test_naechster_vorschlag_589.py::TestChooseAusschluesse::test_von_anderer_sitzung_beanspruchtes_issue

- **AC-5:** Given Issue-Bodys mit `Folge zu #N`, `aus #N`, einer bloßen Erwähnung `#N` und einer Erwähnung einer fremden Nummer / When `choose` die Stufe „verwandt“ prüft / Then zählen nur die strengen Muster mit der erledigten Nummer
  - Test: tests/test_naechster_vorschlag_589.py::TestChooseVerwandt::test_strenge_regex_nur_erledigte_nummer

- **AC-6:** Given keine offene Aufgabe bleibt übrig, und separat der Parameter `spur` gesetzt / When `choose` läuft / Then ist das Ergebnis `None`, und `spur` ändert in Teil A nichts am Ergebnis
  - Test: tests/test_naechster_vorschlag_589.py::TestChooseRangfolge::test_kein_kandidat_none_und_spur_ohne_wirkung

- **AC-7:** Given ein `gh`-Stub mit gültigen REST-Antworten / When `fetch` läuft / Then werden ausschließlich `gh api`-Aufrufe ohne GraphQL gemacht und Rohdaten für `choose` geliefert
  - Test: tests/test_naechster_vorschlag_589.py::TestFetch::test_nur_rest_aufrufe_und_rohdaten

- **AC-8:** Given kein `gh` im PATH, ein Stub mit Rückgabecode ungleich 0, ein Timeout und kaputtes JSON / When `fetch` läuft / Then kommt `None` ohne Ausnahme zurück
  - Test: tests/test_naechster_vorschlag_589.py::TestFetch::test_fail_open_ohne_gh_fehler_timeout_json

- **AC-9:** Given Rohdaten / When der Cache geschrieben und gelesen wird, innerhalb und nach Ablauf der TTL, und bei fremder erledigter Nummer / Then entsteht `.claude/next_suggestion.json` atomar, ein gültiger Cache wird geliefert, ein abgelaufener oder fremder nicht, und `choose` rechnet bei jedem Lesen frisch (neu beanspruchtes Issue wird sofort übersprungen)
  - Test: tests/test_naechster_vorschlag_589.py::TestCache::test_atomar_ttl_schluessel_und_frisches_choose

- **AC-10:** Given ein Vorschlag / When `end_state` den Fall „fertig, kein offener Auftrag“ baut / Then ist die Schlusszeile eine einzige ✅-Zeile mit dem Zusatz „mit /00-intake #M weitermachen (<Quelle in Alltagssprache>: <Kurztitel>)“ ohne Git-Wörter, `kind` bleibt `done`; ohne Vorschlag ist die Zeile byte-gleich zur heutigen
  - Test: tests/test_naechster_vorschlag_589.py::TestEndStateZeile::test_zeile_mit_zusatz_und_ohne_byte_gleich

- **AC-11:** Given ein Vorschlag im Cache / When `workflow.py endstate` läuft / Then enthält die Ausgabe `SUGGEST_ISSUE=`, `SUGGEST_SOURCE=` (epic|milestone|related|priority) und `SUGGEST_REASON=`; ohne Vorschlag (kein `gh`, Netzfehler, kein Kandidat) fehlen diese Zeilen und `FOOTER=` ist die heutige Zeile
  - Test: tests/test_naechster_vorschlag_589.py::TestEndstateKommando::test_suggest_zeilen_nur_bei_vorschlag

- **AC-12:** Given ein gefüllter Cache / When Plan (`render_plan` über `queue_end_args`) und `endstate` denselben Zustand ausgeben / Then stimmt die Schlusszeile überein, ohne dass `end_state`, `queue_end_args` oder `render_plan` einen Netzabruf machen (`gh`-Stub wird dort nie aufgerufen)
  - Test: tests/test_naechster_vorschlag_589.py::TestNetzfrei::test_plan_und_end_state_ohne_netz_gleiche_zeile

- **AC-13:** Given ein offener Auftrag mit nächstem Issue und ein verfügbarer Vorschlag / When `endstate` läuft / Then gilt die bestehende Auftragszeile, der Vorschlag erscheint nicht und es wird nichts angehängt
  - Test: tests/test_naechster_vorschlag_589.py::TestAuftragVorrang::test_offener_auftrag_hat_vorrang

- **AC-14:** Given ein autarker Auftrag ohne weiteres Issue und ein Vorschlag aus Epic bzw. Meilenstein / When `endstate` ein- und zweimal läuft / Then steht M genau einmal im Auftrag und die Zeile ist „⏳ Läuft noch: Claude startet #M aus deinem Auftrag …“; bei Quelle `related` oder `priority` oder nicht autarkem Auftrag wird nichts angehängt und es bleibt beim Vorschlag
  - Test: tests/test_naechster_vorschlag_589.py::TestAutark::test_anhaengen_idempotent_nur_epic_und_meilenstein

- **AC-15:** Given `next_suggestion.enabled: false` in `config.yaml` (und separat andere Werte, fehlender Abschnitt, kaputte Config) / When `endstate` läuft / Then wird bei Literal `false` weder `gh` aufgerufen noch Cache gelesen und die Zeile ist die heutige; alle anderen Fälle gelten als „an“
  - Test: tests/test_naechster_vorschlag_589.py::TestKillSwitch::test_nur_literal_false_schaltet_ab

- **AC-16:** Given eine Antwort mit der erweiterten ✅-Zeile / When `footer_gate` den Stop prüft / Then endet es mit Exit 0, und `expected_footer_command` bleibt für den Fertig-Zustand `None`
  - Test: tests/test_naechster_vorschlag_589.py::TestFooterGate::test_erweiterte_zeile_wird_nicht_geblockt

- **AC-17:** Given `core/commands/60-validate.md`, `skills/60-validate/SKILL.md` und `CHANGELOG.md` / When gelesen / Then beschreibt der Abschnitt „Abschluss: Endzustand melden“ den Vorschlag samt `SUGGEST_*` und der Kette nur bei „aus deinem Auftrag“, das Skill-Generat ist synchron (`test_command_texts_and_skills_in_sync`), und `[Unreleased]` → `### Added` nennt `#589`
  - Test: tests/test_naechster_vorschlag_589.py::TestDokumentation::test_befehlstext_skill_sync_und_changelog

## Test Plan

Automatische Tests (jeweils an eine AC oben gebunden):

- `pytest tests/test_naechster_vorschlag_589.py`
- Regressionslauf: `pytest tests/` (insbesondere `test_endzustand_550.py`, `test_auftrag_551.py`, `test_nacharbeit_555.py`, `test_footer_gate_234.py`, `test_herdr_sidebar_466.py`)
- `python3 -m py_compile core/hooks/next_suggestion.py core/hooks/workflow.py`

TDD-Reihenfolge: Die Tests werden vor dem Modul geschrieben und schlagen zuerst fehl (Modul fehlt). Beispiele (GIVEN/WHEN/THEN):

- GIVEN zwei offene Geschwister und ein Meilenstein-Issue WHEN `choose` läuft THEN gewinnt das Geschwister (`source=epic`).
- GIVEN ein `gh`-Stub, der mit Rückgabecode 1 endet WHEN `endstate` läuft THEN ist die Zeile byte-gleich zur heutigen und es gibt keine `SUGGEST_*`-Zeilen.
- GIVEN ein autarker Auftrag ohne offenes Issue und ein Epic-Vorschlag WHEN `endstate` zweimal läuft THEN steht die Nummer einmal im Auftrag.

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** `docs/adr/` enthält keine Einträge, und die Änderung folgt vorhandenen Mustern: `gh api` (REST) mit `shutil.which`, Timeout und Fail-open wie `fetch_issue_title` und `scripts/ship.py`, Kill-Switch „nur Literal false“ wie `auftrag:`, Zeilenbau in der reinen Funktion `end_state` mit Netz allein im Kommando. Die neue Netzabhängigkeit ist optional und folgenlos bei Ausfall (heutige Zeile), per Schalter abschaltbar und durch Löschen des Moduls rückbaubar. Verworfen: (a) Netzabruf in `end_state`/Plan/Seitenleiste, weil diese bei jeder Anzeige laufen; (b) zweite ❗Du-Zeile, weil die Fußzeilen-Regel genau eine Schlusszeile verlangt und `footer_gate` sonst scharf würde.

## Changelog

- 2026-11-12: Initial spec created
