---
entity_id: feat-461-issue-registrierung
type: feature
created: 2026-11-24
updated: 2026-11-24
status: draft
version: "1.0"
workflow: feat-461-issue-registrierung
tags: [workflow, registrierung, github, session-register, mehrere-rechner]
---

# Verpflichtende Registrierung je Issue, rechnerübergreifend über GitHub (Issue #461)

## Approval

- [ ] Approved

## Purpose

Jede Sitzung, die an einem Issue arbeitet, trägt sich beim Start als Kommentar am Issue ein: wo sie läuft (iMac, Server, Cloud), unter welchem Namen und wie sie erreichbar ist. Eine zweite Sitzung auf demselben Issue wird dadurch erkannt und bricht mit Klartext ab, statt unbemerkt parallel zu arbeiten. Der Eintrag lebt mit der Arbeit am Issue, nicht mit der Sitzungs-ID, und wirkt über Rechner und Claude-Konten hinweg, weil nur GitHub als gemeinsamer Ort dient.

Auftrag PO (24.11.2026, dritter Kommentar zu #461): Registrierung verpflichtend, rechnerübergreifend, unabhängig vom Claude-Konto (iMac und Server laufen mit verschiedenen Konten, `claude --teleport` hilft daher nicht). Ortswahl (#585) und herdr-Anzeige (eigenes Issue in `henemm-infra`) folgen später und sind nicht Teil dieser Spec.

## Source

- Issue #461, Analyse und Entscheidungen: `docs/context/feat-461-issue-registrierung.md`.
- **File:** `core/hooks/issue_claim.py` (neu), Einhängepunkte in `core/hooks/workflow.py`
- **Identifier:** neu `issue_claim.register`, `issue_claim.release`, `issue_claim.refresh`, `issue_claim.read_claims`, `issue_claim.pick_winner`, `issue_claim.detect_location`, `issue_claim.build_comment`; in `workflow.py` `cmd_start`, `cmd_switch`, `cmd_abandon`, `cmd_ship_status`, Phasenwechsel, neuer Befehl `claim`

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `gh` CLI mit Token | external | Kommentare lesen, anlegen, bearbeiten (`gh api repos/{owner}/{repo}/issues/{n}/comments`) |
| `workflow.fetch_issue_title`, `_spawn_issue_title_fetch` | function | Vorbild für `gh api` mit Zeitlimit, fail-open, Logdatei und abgekoppelten Hintergrundabruf |
| `hook_utils.workflow_issue_number` | function | Issue-Nummer aus dem Workflow-Namen |
| `hook_utils.atomic_write_json` | function | Kommentar-ID im Workflow-State sichern |
| `config_loader` | module | Abschnitt `issue_claim:` mit lokalen Overrides |
| `session_singleton_guard.py` | module | Lokales Register bleibt unverändert; Vorbild für `CLAUDE_CODE_REMOTE`- und herdr-Erkennung |
| `mention_guard.py` | hook | Blockt nacktes `@name` in gh-Texten; der Kommentartext erzeugt keines |
| `workflow.cmd_ship_status` (#612) | function | `done`/`skipped` markiert das Ende der Auslieferung und löst die Freigabe aus |
| `scripts/sync_skills.py` | script | Erzeugt `skills/` aus den geänderten Befehlstexten |
| `tests/test_release_tested_proof_633.py` | test | Vorbild für Fake-Programme im PATH |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| `core/hooks/issue_claim.py` | CREATE | Utility (kein Hook, wie `herdr_bridge.py`): Eintrag am Issue lesen, anlegen, bearbeiten, freigeben, Ort und Erreichbarkeit ermitteln, Kommentartext bauen, Gewinner bei Doppelstart bestimmen |
| `core/hooks/workflow.py` | MODIFY | `cmd_start` (vor dem Schreiben der Workflow-Datei) registriert und bricht bei fremdem gültigem Eintrag ab; `cmd_switch` prüft und holt nach; `cmd_abandon` und `cmd_ship_status done/skipped` geben frei; Phasenwechsel trägt Stand abgekoppelt nach; neuer Befehl `claim` (`status`, `nachholen`); `sessions` zeigt Registrierungsstand |
| `config.yaml` | MODIFY | Abschnitt `issue_claim:` (`enabled`, `timeout_seconds`, `location_label`) |
| `tests/conftest.py` | MODIFY | Autouse-Fixture setzt `OPENSPEC_ISSUE_CLAIM=0`, damit die bestehenden Start-Tests nie echtes `gh` rufen |
| `tests/test_issue_claim_461.py` | CREATE | Tests aller ACs mit Fake-`gh` im PATH |
| `core/commands/00-intake.md`, `core/commands/10-context.md`, `core/commands/80-workflow.md` | MODIFY | Hinweis auf Abbruch bei fremder Registrierung und auf `--uebernehmen` |
| `skills/*/SKILL.md` | GENERATED | per `python3 scripts/sync_skills.py`, nie von Hand (zählt nicht zum Umfang) |
| `CHANGELOG.md`, `.claude-plugin/plugin.json`, `README.md`, `CLAUDE.md` | MODIFY | Version 4.21.0 im selben PR (Einzel-Auslieferung), Tabelle „Wichtige Dateien“ und Hook-Architektur um `issue_claim.py` ergänzt |

### Estimated Changes

- Files: 8 Produktiv-, Doku- und Testdateien plus generierte Skills und Kurzbefehle. Der Schnitt in mehrere Teile würde eine halb gültige Pflicht veröffentlichen (Registrierung ohne Freigabe oder ohne Test-Isolation), deshalb ein Umfang.
- LoC: Produktivcode ca. +200/-10, Tests ca. +250, Doku ca. +30.
- Risiko hoch: `cmd_start` ist der Eingang jedes Workflows in jedem Konsumenten-Projekt, und der Startpfad bekommt einen Netzaufruf.

## Implementation Details

Codebeschreibung in Worten; der Code liegt in `core/hooks/issue_claim.py`.

**1. Eigenes Modul, keine neue Hook-Datei.** `issue_claim.py` kapselt alles zum GitHub-Eintrag, `workflow.py` ruft nur auf. Die Pflicht sitzt im Code von `start` und `switch`, nicht in einem Hook und nicht im Befehlstext. So greift sie auch bei `/10-context`, in Cloud-Sitzungen mit Repo-Hooks und bei direktem Aufruf von `workflow.py start`.

**2. Eintrag = ein Kommentar je Arbeit am Issue.** Der Kommentar beginnt mit dem versteckten Marker `<!-- openspec-claim v1 id=<zufall> -->` und enthält danach einen maschinenlesbaren Block: Ort, Sitzungsname (= Workflow-Name), Beginn (UTC), Phase, Status (`aktiv`, `freigegeben`, `zurückgezogen`, `übernommen`), Erreichbarkeit, dazu ein Klartextsatz. Aktualisierungen gehen per Bearbeiten desselben Kommentars (PATCH), nie als neuer Kommentar (keine Benachrichtigungsflut). Der Text enthält kein `@`, keine Dateipfade, keine Links und keine Rechner-Adressen, weil Konsumenten-Repos öffentlich sein können.

**3. Doppelstart.** Ablauf in `start`: eigenen Kommentar schreiben, Kommentare neu lesen, gültige Einträge bestimmen, Gewinner wählen. Gültig ist ein Kommentar nur mit Marker, `authorAssociation == OWNER`, Status `aktiv` und offenem Issue. Der früheste Eintrag gewinnt (`createdAt`, danach Kommentar-ID). Ist der eigene nicht der Gewinner, setzt der Verlierer seinen Kommentar auf `zurückgezogen`, `start` bricht ab, schreibt keine Workflow-Datei und nennt im Klartext, wer (Sitzungsname), wo (Ort), seit wann und wie erreichbar. Ausweg: `workflow.py start <name> --uebernehmen` setzt den fremden Eintrag auf `übernommen` und trägt die eigene Sitzung ein.

**4. Ort und Erreichbarkeit.** `CLAUDE_CODE_REMOTE=true` ergibt „Cloud“. Sonst gilt `issue_claim.location_label` (lokale Konfiguration je Rechner, etwa „iMac“ oder „Server“), ersatzweise nach `platform.system()` „Mac“ beziehungsweise „Linux-Rechner“ (sonst „Rechner“). Erreichbarkeit: `HERDR_ENV=1` ergibt „herdr“, Cloud ergibt „Sitzungsliste des Claude-Kontos, Antwort am Issue“, sonst „Terminal“.

**5. Lebensdauer an der Arbeit.** Die Kommentar-ID steht im Workflow-State unter `issue_claim` (ID, Status, Zeitstempel), nicht in der Sitzungs-ID; sie überlebt `/clear` und `switch`. Freigabe (Status `freigegeben`) bei `ship-status done` oder `skipped` und bei `abandon`; nicht bei `complete`, weil die Auslieferung dann noch aussteht. Ein geschlossenes Issue gilt beim Lesen als frei.

**6. Ohne Netz, ohne `gh`, bei Zeitüberschreitung.** `start` läuft weiter, gibt eine deutliche Warnung aus und setzt `issue_claim.status=pending`. `switch`, `claim nachholen` und der nächste Phasenwechsel holen die Registrierung nach (fail-open: ohne Netz soll keine Arbeit stehen). Fehler gehen in eine Logdatei unter `.claude/`. Zeitlimit aus `issue_claim.timeout_seconds` (Standard 8 s).

**7. Ohne Issue-Nummer** im Workflow-Namen: keine Registrierung, einzeilige Notiz, kein Block.

**8. Arbeitsstand.** Beim Phasenwechsel wird der Kommentar abgekoppelt aktualisiert (Hintergrundprozess nach Muster `_spawn_issue_title_fetch`), ohne Warten.

**9. Verwaiste Einträge.** `workflow.py claim status` zeigt für den Eintrag am Issue den Besitzer, das Alter und die offenen Pull Requests zum Issue. Übernahme geschieht nie automatisch, nur explizit per `--uebernehmen`.

**10. Abschaltung.** `issue_claim.enabled: false` in `config.yaml` oder Umgebungsvariable `OPENSPEC_ISSUE_CLAIM=0` schaltet die gesamte Pflicht ab (kein `gh`-Aufruf). Die Testumgebung setzt `OPENSPEC_ISSUE_CLAIM=0` per autouse in `tests/conftest.py`; Tests der Funktion setzen die Variable gezielt zurück.

## Expected Behavior

- **Input:** `workflow.py start <name>` mit Issue-Nummer im Namen; `switch`, `abandon`, `ship-status`, Phasenwechsel und `claim status|nachholen`.
- **Output:** Ein Kommentar am Issue mit Marker und Stand; bei fremdem gültigem Eintrag Abbruch mit Klartext (Sitzung, Ort, Beginn, Erreichbarkeit) und Hinweis auf `--uebernehmen`; `claim status` zeigt Eintrag, Alter und offene Pull Requests.
- **Side effects:** Kommentar am GitHub-Issue (anlegen, bearbeiten); Feld `issue_claim` im Workflow-State; Logdatei bei `gh`-Fehlern.

## Known Limitations

- Ein Start ohne Netz, ohne `gh` oder nach Zeitüberschreitung umgeht den Doppelstart-Schutz (bewusst fail-open); nachgeholt wird erst bei `switch`, `claim nachholen` oder dem nächsten Phasenwechsel, dann kann der Konflikt erst dort auffallen.
- Cloud-Sitzungen haben nicht sicher `gh` und Token; dort entsteht ggf. nur die Warnung. Aus der Entwicklungssitzung nicht prüfbar; der Nachweis erfolgt später in einer echten Cloud-Sitzung.
- Kommentare in öffentlichen Konsumenten-Repos sind öffentlich; deshalb nur Ortsetikett, Workflow-Name, Zeit und Phase, nie Pfade, Links oder Adressen.
- Arbeit ohne Workflow (reine Dokumentation, Issue-Pflege) hat keinen Einhängepunkt und wird nicht registriert.
- Schreibrennen werden nur über „schreiben, neu lesen, frühester gewinnt“ aufgelöst; bei gleichem `createdAt` entscheidet die Kommentar-ID. Es gibt keine Sperre auf Seiten von GitHub.
- Nicht Teil dieser Spec (Folge-Issue): Spalte „Dateien“ und Überschneidungen in `sessions`, Aufräumen alter lokaler Einträge, Ortswahl (#585), herdr-Anzeige (`henemm-infra`).

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] Ein `workflow.py start` zu einem Issue legt am Issue sichtbar einen Eintrag an (Ort, Name, Beginn, Phase, aktiv), und ein zweiter Start auf demselben Issue bricht mit verständlicher Meldung ab, wer wo seit wann arbeitet
- [ ] Ohne Netz startet die Arbeit weiter, mit Warnung, und wird später nachgetragen
- [ ] Die Freigabe erfolgt mit dem Ende der Auslieferung oder dem Abbruch, nicht schon bei `complete`
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf grün, bestehende Start-Tests unverändert grün)
- [ ] CHANGELOG-Abschnitt `[4.21.0]` mit Eintrag (#461), Bump im selben PR

## Acceptance Criteria

- **AC-1:** Given ein Workflow-Name mit Issue-Nummer und ein Fake-`gh` im PATH / When `workflow.py start` läuft / Then wird genau ein Kommentar am Issue angelegt, der den Marker `openspec-claim v1` und Ort, Workflow-Name, Beginn (UTC), Phase und Status `aktiv` enthält, und der Kommentartext enthält weder `@`, noch Dateipfade, noch Links.
  - Test: tests/test_issue_claim_461.py::test_start_registriert_kommentar_mit_marker_ohne_at_pfade_links
- **AC-2:** Given am Issue steht bereits ein gültiger Eintrag einer anderen Sitzung (OWNER, aktiv, offen) / When `start` mit eigenem Eintrag läuft / Then gewinnt der früheste gültige Eintrag, der Verlierer setzt seinen Kommentar auf `zurückgezogen`, `start` endet mit Fehlercode, schreibt keine Workflow-Datei und nennt im Klartext Sitzung, Ort, Beginn und Erreichbarkeit des Gewinners.
  - Test: tests/test_issue_claim_461.py::test_doppelstart_fruehester_gewinnt_verlierer_zieht_zurueck_ohne_workflow_datei
- **AC-3:** Given ein fremder gültiger Eintrag / When `start <name> --uebernehmen` läuft / Then wird der fremde Eintrag auf `übernommen` gesetzt, ein eigener Eintrag angelegt und die Workflow-Datei geschrieben.
  - Test: tests/test_issue_claim_461.py::test_uebernehmen_setzt_fremden_eintrag_und_startet
- **AC-4:** Given Kommentare mit Marker, deren `authorAssociation` nicht `OWNER` ist, oder Kommentare ohne Marker / When die Einträge gelesen werden / Then werden sie ignoriert und blockieren den Start nicht.
  - Test: tests/test_issue_claim_461.py::test_nicht_owner_und_markerlose_kommentare_werden_ignoriert
- **AC-5:** Given das Issue ist geschlossen und trägt einen aktiven fremden Eintrag / When `start` läuft / Then gilt das Issue als frei und der Start gelingt.
  - Test: tests/test_issue_claim_461.py::test_geschlossenes_issue_gilt_als_frei
- **AC-6:** Given `gh` fehlt im PATH, liefert einen Fehler oder überschreitet das Zeitlimit / When `start` läuft / Then wird die Workflow-Datei geschrieben, eine Warnung ausgegeben und `issue_claim.status` ist `pending`; ein anschließendes `switch` oder der nächste Phasenwechsel holt die Registrierung bei erreichbarem `gh` nach und setzt den Status auf aktiv.
  - Test: tests/test_issue_claim_461.py::test_offline_startet_mit_warnung_pending_und_holt_bei_switch_und_phasenwechsel_nach
- **AC-7:** Given ein Workflow-Name ohne Issue-Nummer / When `start` läuft / Then erfolgt kein `gh`-Aufruf, eine einzeilige Notiz erscheint und der Start wird nicht blockiert.
  - Test: tests/test_issue_claim_461.py::test_ohne_issue_nummer_keine_registrierung_kein_block
- **AC-8:** Given ein registrierter Workflow / When `switch` (auch nach `/clear`) auf ihn erfolgt / Then steht die Kommentar-ID weiter im Workflow-State unter `issue_claim` und es wird kein zweiter Kommentar angelegt.
  - Test: tests/test_issue_claim_461.py::test_kommentar_id_im_state_ueberlebt_switch
- **AC-9:** Given ein registrierter Workflow / When `ship-status done` oder `skipped` gesetzt wird oder `abandon` läuft / Then wird der Kommentar auf `freigegeben` gesetzt; bei `complete` bleibt er `aktiv`.
  - Test: tests/test_issue_claim_461.py::test_freigabe_bei_ship_status_done_skipped_und_abandon_nicht_bei_complete
- **AC-10:** Given ein registrierter Workflow / When die Phase wechselt / Then wird die Phase im Kommentar per Bearbeiten (PATCH, nicht neuer Kommentar) aktualisiert und der Phasenwechsel wartet nicht auf die Antwort von GitHub.
  - Test: tests/test_issue_claim_461.py::test_phasenwechsel_aktualisiert_per_patch_abgekoppelt
- **AC-11:** Given ein fremder Eintrag und offene Pull Requests zum Issue / When `workflow.py claim status` läuft / Then zeigt die Ausgabe Besitzer-Sitzung, Ort, Alter des Eintrags und die offenen Pull Requests, und ändert nichts am Eintrag.
  - Test: tests/test_issue_claim_461.py::test_claim_status_zeigt_fremden_eintrag_mit_alter_und_offenen_prs
- **AC-12:** Given `issue_claim.enabled: false` in `config.yaml` oder `OPENSPEC_ISSUE_CLAIM=0` / When `start` läuft / Then erfolgt kein `gh`-Aufruf und der Start verläuft wie bisher.
  - Test: tests/test_issue_claim_461.py::test_kill_switch_config_und_umgebungsvariable
- **AC-13:** Given unterschiedliche Umgebungen / When der Ort bestimmt wird / Then ergibt `CLAUDE_CODE_REMOTE=true` „Cloud“, sonst `issue_claim.location_label`, ersatzweise die Bezeichnung nach `platform.system()`; die Erreichbarkeit ist „herdr“ bei `HERDR_ENV=1`, in der Cloud „Sitzungsliste des Claude-Kontos, Antwort am Issue“, sonst „Terminal“.
  - Test: tests/test_issue_claim_461.py::test_ort_und_erreichbarkeit_cloud_label_und_fallback
- **AC-14:** Given die Testumgebung des Repos / When ein beliebiger bestehender Test `workflow.py start` aufruft / Then ist `OPENSPEC_ISSUE_CLAIM=0` über die conftest-Autouse-Fixture gesetzt und es wird nie echtes `gh` gerufen.
  - Test: tests/test_issue_claim_461.py::test_conftest_setzt_kill_switch_automatisch
- **AC-15:** Given die geänderten Befehlstexte `00-intake`, `10-context`, `80-workflow` / When `scripts/sync_skills.py` im Prüfmodus läuft / Then meldet es keine Abweichung zwischen `core/commands/` und `skills/`, und die Befehlstexte nennen Abbruch bei fremder Registrierung und `--uebernehmen`.
  - Test: tests/test_issue_claim_461.py::test_befehlstexte_nennen_uebernehmen_skills_ohne_drift

## Test Plan

Automatische Tests (jeweils an eine AC oben gebunden):
- `python3 -m pytest tests/test_issue_claim_461.py -q` (im venv mit `pytest`, `pyyaml`): AC-1 bis AC-15.
- Aufbau: Fake-`gh` als ausführbares Skript in einem Temp-Verzeichnis, vorangestellt im PATH (Muster `tests/test_release_tested_proof_633.py`). Es führt ein Protokoll der Aufrufe und hält Kommentare in einer JSON-Datei, sodass Anlegen, Bearbeiten, Lesen und Doppelstart ohne Netz prüfbar sind. Fehlerfälle: Fake mit Exit-Code 1, mit Schlafzeit über dem Zeitlimit, und PATH ohne `gh`.
- Isolation: `tests/conftest.py` setzt per Autouse `OPENSPEC_ISSUE_CLAIM=0`; die Tests dieser Datei setzen die Variable gezielt zurück, damit bestehende Start-Tests nie echtes `gh` rufen.
- Regression: `python3 -m pytest tests/ -q` (parallel mit `-n auto`, wenn xdist vorhanden), bestehende Start-, Switch- und Sessions-Tests grün.

### Automated Tests (TDD RED)

- [ ] Test 1: GIVEN Fake-`gh` und Issue-Workflow WHEN `start` THEN ein Kommentar mit Marker, Ort, Name, Beginn, Phase, aktiv, ohne `@`, Pfade, Links.
- [ ] Test 2: GIVEN fremder gültiger Eintrag WHEN `start` THEN Verlierer zieht zurück, Abbruch mit Klartext, keine Workflow-Datei.
- [ ] Test 3: GIVEN fremder Eintrag WHEN `start --uebernehmen` THEN fremder Eintrag `übernommen`, eigener angelegt, Workflow-Datei da.
- [ ] Test 4: GIVEN Nicht-OWNER- und markerlose Kommentare WHEN gelesen THEN ignoriert, Start nicht blockiert.
- [ ] Test 5: GIVEN geschlossenes Issue mit fremdem aktivem Eintrag WHEN `start` THEN Start gelingt.
- [ ] Test 6: GIVEN `gh` fehlt, scheitert oder Zeitlimit WHEN `start` THEN Start mit Warnung und `pending`; `switch` und Phasenwechsel holen nach.
- [ ] Test 7: GIVEN Name ohne Issue-Nummer WHEN `start` THEN kein `gh`-Aufruf, kein Block.
- [ ] Test 8: GIVEN registrierter Workflow WHEN `switch` THEN Kommentar-ID bleibt, kein zweiter Kommentar.
- [ ] Test 9: GIVEN registrierter Workflow WHEN `ship-status done` oder `skipped` oder `abandon` THEN `freigegeben`; bei `complete` weiter `aktiv`.
- [ ] Test 10: GIVEN registrierter Workflow WHEN Phasenwechsel THEN PATCH am selben Kommentar, abgekoppelt.
- [ ] Test 11: GIVEN fremder Eintrag und offene PRs WHEN `claim status` THEN Besitzer, Alter, PRs, keine Änderung.
- [ ] Test 12: GIVEN Kill-Switch per Konfiguration oder Umgebungsvariable WHEN `start` THEN kein `gh`-Aufruf.
- [ ] Test 13: GIVEN Cloud-, Label- und Fallback-Umgebung WHEN Ort bestimmt THEN „Cloud“, Label, Systembezeichnung; Erreichbarkeit herdr, Cloud-Text oder Terminal.
- [ ] Test 14: GIVEN Testumgebung WHEN conftest geladen THEN `OPENSPEC_ISSUE_CLAIM=0` gesetzt.
- [ ] Test 15: GIVEN geänderte Befehlstexte WHEN Skill-Sync geprüft THEN kein Drift und Hinweis auf `--uebernehmen` vorhanden.

RED-Artefakt: `docs/artifacts/461-red.log`.

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Das Repo führt kein ADR-Verzeichnis; die Entscheidung ist hier festgehalten und im Issue #461 belegt. Gewählt ist: ein Kommentar am Issue als Eintrag. Verworfen sind Label oder Zuweisung am Issue (tragen weder Ort noch Erreichbarkeit noch Beginn, eine Zuweisung braucht ein GitHub-Konto je Rechner und löst Benachrichtigungen aus) und ein Register im Claude-Konto (iMac und Server nutzen verschiedene Konten, `claude --teleport` hilft deshalb nicht). Der Kommentar ist konto-unabhängig, für alle Beteiligten sichtbar und per Bearbeiten aktualisierbar. Bei Netzfehlern gilt fail-open (Start mit Warnung, Nachholen später), weil eine Pflicht ohne Netz sonst jede Arbeit stoppen würde; der Preis ist die Lücke im Doppelstart-Schutz (Known Limitations). Die Pflicht sitzt in `cmd_start` statt in einem Hook, weil sie dann unabhängig von Befehlstext, Hook-Registrierung und Cloud-Sitzung greift. Kein Hook-Eintrag, kein neues Gate, keine Änderung der Gate-Architektur.

## Changelog

- 1.0 (2026-11-24): Erstfassung nach Auftrag PO vom 24.11.2026 (dritter Kommentar zu #461), Entscheidungen des Tech Leads aus der Analyse übernommen.
