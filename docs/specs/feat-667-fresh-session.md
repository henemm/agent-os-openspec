---
entity_id: feat-667-fresh-session
type: feature
created: 2026-11-25
updated: 2026-11-25
status: draft
version: "1.0"
workflow: feat-667-fresh-session
tags: [kontext, auftrag, workflow, herdr, cloud, epic-649]
---

# Frischer Kontext je Aufgabe eines Auftrags (Issue #667, Epic #649)

## Approval

- [ ] Approved

## Purpose

Seit #662/#663 läuft die Phasenkette im Auto-Modus in der Hauptsitzung selbst durch. Bei einem Auftrag über mehrere Issues (`workflow.py queue`) wächst der Hauptkontext dadurch weit über die Kontext-Schwelle. Neu: Ist ein Issue ausgeliefert und steht im autarken Auftrag ein nächstes offenes Issue, startet dieses in einer eigenen, frischen Sitzung (Cloud: neue Sitzung über das Werkzeug `create_session`; lokal: Herdr startet in einem neuen Pane eine neue Claude-Sitzung, ohne zu tippen). Auftrag und Fortschritt reisen im Startauftrag der neuen Sitzung, nicht im Gespräch. Ohne Cloud und ohne Herdr bleibt der bisherige Selbstaufruf erhalten.

## Source

- **File:** `core/hooks/workflow.py`, `core/hooks/hook_utils.py`, `core/hooks/herdr_bridge.py`, `core/commands/60-validate.md`, `core/commands/70-deploy.md`, `core/commands/80-workflow.md`
- **Identifier:** `workflow.cmd_handoff`, `hook_utils._normalize_auftrag`, `herdr_bridge.start_session`

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `workflow.queue_end_args` / `hook_utils.auftrag_open_issues` | function | liefern das nächste offene Issue (erste offene Nummer ungleich Issue des aktiven Workflows) |
| `hook_utils.read_auftrag`, `write_auftrag`, `_normalize_auftrag` (#551, #613) | function | Auftrag je Sitzung lesen/schreiben; Normalisierung muss das neue Feld `handoff` erhalten |
| `workflow.autonomy_mode`, `workflow.auftrag_autark_open` | function | Bedingung „Auto-Modus und autarker Auftrag" |
| `herdr_bridge._pane`, `_binary`, `_pp_call`, `_pp_spawn_watcher` | function | Herdr-Pane-Erkennung, Binary, fail-open-Aufruf mit Timeout, Muster für `pane split` |
| Env `CLAUDE_CODE_REMOTE=true` | env | Cloud-Erkennung |
| Cloud-Werkzeug `create_session` (claude-code-remote) | tool | startet die frische Cloud-Sitzung; nur von Claude aufrufbar, nicht von Python |
| `footer_gate.py`, `workflow.end_state` | hook | hängen an der Zeile „aus deinem Auftrag"; bleiben unverändert |
| `scripts/sync_skills.py`, `scripts/sync_cloud_agents.py` | tool | Generat nach Befehlstext-Änderung neu erzeugen |
| docs/specs/feat-551-auftragsliste.md, feat-662-kette-flach.md, chore-663-rueckbau-autoclear.md | spec | Vorarbeit (Auftrag, flache Kette, kein Auto-/clear) |
| Issue #667, Epic #649 | issue | Auftrag und Rahmen |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| core/hooks/workflow.py | MODIFY | neuer Befehl `handoff` (`--start`, `--mark <weg>`), Startauftrag-Bau, Wegwahl, Usage/Docstring |
| core/hooks/hook_utils.py | MODIFY | `_normalize_auftrag` behält Feld `handoff` (gültige int-Nummer, Weg cloud oder herdr), sonst weglassen |
| core/hooks/herdr_bridge.py | MODIFY | neue Funktion `start_session(prompt, cwd)`: `pane split` + `pane run`, fail-open |
| core/commands/60-validate.md, core/commands/70-deploy.md | MODIFY | Absatz „Kette bei offenem Auftrag": erst `workflow.py handoff`, je Weg `create_session`, `handoff --start` oder bisheriger Selbstaufruf |
| core/commands/80-workflow.md | MODIFY | Befehl `handoff` dokumentieren |
| skills/*/SKILL.md, .claude/agents | REGENERATE | `python3 scripts/sync_skills.py`, `python3 scripts/sync_cloud_agents.py` |
| tests/test_handoff_667.py | CREATE | Tests zu allen ACs (tmp-Projekt, Subprozess-Aufruf von workflow.py, Fake-Herdr-Binary) |
| CHANGELOG.md, .claude-plugin/plugin.json, CLAUDE.md (Versionszeile, Hook-Architektur knapp), README.md | MODIFY | Eintrag und Version 4.25.0 |

Nicht geändert: `config.yaml` (autarker Auftrag, keine Gate-Config-Änderung, kein Override), `end_state`/endstate-Zeile, `footer_gate.py`, `hooks/hooks.json`.

### Estimated Changes

- Files: 3 Hooks, 3 Befehle, 1 neue Testdatei, 4 Doku-/Versionsdateien, Generat
- LoC: ca. +350/-10
- Umfang: überschreitet das Schnittlimit. Der Tech Lead nimmt das bewusst an: Wegwahl, Startauftrag, Vermerk und Herdr-Start sind ein Ziel; ein Teilschnitt ließe die Kette widersprüchlich (Befehlstext ruft Befehl, der noch fehlt).
- Risk Level: HIGH (Hook-/CLI-Code, Kettenverhalten jedes autarken Auftrags in allen Konsumenten)

## Implementation Details

1. **Befehl `workflow.py handoff [--start] [--mark <weg>]`.** Auskunfts-CLI mit `KEY=value`-Zeilen, Exit immer 0, fail-open (jeder interne Fehler ergibt `HANDOFF=none`). Ausgabe in dieser Reihenfolge: `HANDOFF=none|cloud|herdr|inline`, `NEXT=<M>|none`, bei `cloud` zusätzlich `REPO_URL=<https-URL aus git remote origin, Endung .git entfernt>` (fehlt der Remote oder ist er kein https, lautet die Zeile `REPO_URL=none`), bei `--start` `STARTED=yes|no|already` und bei `no` `REASON=<kurz>`. Nur wenn `HANDOFF` ungleich `none`, folgt der Startauftrag zwischen den Zeilen `PROMPT_BEGIN` und `PROMPT_END`.
2. **Wegwahl**, in dieser Reihenfolge, erster Treffer gilt:
   1. Kill-Switch `auftrag.enabled: false` ergibt `none`.
   2. Kein Auftrag, Auftrag nicht autark, Autonomie ungleich `auto` oder kein offenes nächstes Issue ergibt `none`. Das nächste Issue ist die erste offene Nummer, die nicht zum aktiven Workflow gehört (`NEXT=none`).
   3. Env `CLAUDE_CODE_REMOTE=true` ergibt `cloud`.
   4. Herdr-Pane aktiv (`herdr_bridge._pane()` liefert eine ID) und `claude` per `shutil.which` gefunden ergibt `herdr`.
   5. Sonst `inline`: der bisherige Selbstaufruf `/00-intake #M` in derselben Sitzung (Rückwärtskompatibilität).
3. **Startauftrag** (deutsch, ohne Gesprächswissen lesbar), fünf Bausteine:
   - Aufgabe: „Bitte Issue #M in diesem Repo bearbeiten: beginne mit dem Befehl 00-intake für #M (Kurzbefehl `00-intake` mit Argument `#M`; fehlt das Plugin, liegt der Befehlstext unter skills/00-intake/SKILL.md bzw. im Konsumenten-Projekt der Redirect-Alias) und folge dem Workflow bis zur Auslieferung."
   - Wiederherstellung: „Lege zuerst den Auftrag neu an: `python3 <hooks>/workflow.py queue add <alle offenen Nummern ab M, Reihenfolge erhalten> --autark` mit `--note "<note>"` und `--spur <spur>` nur, wenn gesetzt; Anführungszeichen in der Note sind sicher maskiert. `<hooks>` ist der Pfad relativ zum Projekt-Root, unter dem `workflow.py` tatsächlich liegt: `.claude/hooks` im Konsumenten-Projekt, `core/hooks` im Framework-Repo.
   - Haltregel: „Autarker Auftrag: kein Halt für /clear; halte nur an PO-Punkten (Freigabe ohne Auto-Freigabe, AMBIGUOUS, Override, Produktfragen per AskUserQuestion)."
   - Herkunft: „Diese Sitzung startet bewusst mit frischem Kontext (#667)."
   - Messung: „Nenne beim Abschluss im Abschlusskommentar des Issues den Wert `CONTEXT_TOKENS` aus `python3 <hooks>/workflow.py context` (Kontextgröße dieser Sitzung)."
4. **Vermerk und Idempotenz.** Bei erfolgreichem `--start` (herdr) und bei `--mark cloud` (Claude hat `create_session` aufgerufen) schreibt `handoff` ins Auftragsfeld `handoff` den Wert `{"issue": M, "mode": weg, "at": ISO-Zeit}`. `hook_utils._normalize_auftrag` erhält das Feld nur mit gültiger int-Nummer und Weg aus `cloud|herdr`, sonst lässt es das Feld weg. Ein weiteres `--start` für dieselbe Nummer startet nichts und meldet `STARTED=already`. `--mark` mit ungültigem Weg (alles außer `cloud`, `herdr`) schreibt Usage auf stderr, endet mit Exit 1 und schreibt nichts. Das ist die einzige Ausnahme vom Grundsatz „Exit immer 0".
5. **Herdr-Start.** `herdr_bridge.start_session(prompt, cwd) -> (bool, reason)`: `pane split <eigenes Pane> --direction right --cwd <Projekt-Root> --no-focus` (Muster wie `_pp_spawn_watcher`), `pane_id` aus der JSON-Antwort, nie das eigene Pane; danach `pane run <neues Pane> "exec claude <shlex-quoted prompt>"`. Alle Aufrufe fail-open über `_pp_call` mit Timeout, eine Log-Zeile in die bestehende Herdr-Logdatei. Misslingt der Start, meldet `handoff --start` `STARTED=no` mit `REASON`, und der Befehlstext fällt auf `inline` zurück. Das alte Pane bleibt stehen. Herdr tippt nie in ein Claude-Pane; es startet nur einen Prozess.
6. **Cloud.** Python kann das MCP-Werkzeug nicht aufrufen. Der Absatz „Kette bei offenem Auftrag" in `60-validate.md` und `70-deploy.md` wird geändert: Bei `ENDSTATE=waiting` mit „aus deinem Auftrag" zuerst `workflow.py handoff`.
   - `cloud`: Werkzeug `create_session` (claude-code-remote) mit `prompt` = Startauftrag, `source_url` = `REPO_URL` (nur wenn ungleich `none`), Titel „#M …". Bei Erfolg `workflow.py handoff --mark cloud`, ⏳-Zeile ausgeben, Turn beenden, keinen Selbstaufruf. Misslingt `create_session`, wie `inline`.
   - `herdr`: `workflow.py handoff --start`; bei `STARTED=yes|already` Turn beenden, bei `no` wie `inline`.
   - `inline`: wie bisher `/00-intake #M` selbst aufrufen.
   - `none`: keine Übergabe, bisheriger Weg.
   Bei `ENDSTATE=you` bleibt alles unverändert. `80-workflow.md` dokumentiert den Befehl. Skills und Cloud-Agents sind Generat.
7. **`end_state` bleibt unverändert**, weil `footer_gate.py` an „aus deinem Auftrag" hängt.
8. **Version und Doku.** 4.25.0 (MINOR) in `.claude-plugin/plugin.json`, CLAUDE.md-Versionszeile und README; CHANGELOG-Eintrag; danach `sync_skills.py` und `sync_cloud_agents.py`. Kein Config-Schlüssel.

## Expected Behavior

- **Input:** Auftrag der Sitzung (autark, offene Nummern, optional note/spur), `OPENSPEC_AUTONOMY`, `CLAUDE_CODE_REMOTE`, Herdr-Umgebung (`HERDR_ENV`, `HERDR_PANE_ID`, `HERDR_BIN_PATH`), `claude` im PATH, Argumente `--start` bzw. `--mark <weg>`
- **Output:** Zeilen `HANDOFF=`, `NEXT=`, bei cloud `REPO_URL=`, bei `--start` `STARTED=` (und `REASON=`), danach Startauftrag zwischen `PROMPT_BEGIN` und `PROMPT_END`
- **Side effects:** Nur `--start` (erfolgreich, herdr) und `--mark cloud` schreiben das Auftragsfeld `handoff`; `--start` startet im herdr-Weg einen neuen Pane mit neuer Claude-Sitzung; sonst keine Schreibung

## Known Limitations

- Der lokale End-to-End-Beleg mit echtem Herdr steht aus: Er ist aus der Cloud nicht ausführbar und wird am Epic #649 festgehalten. Belegt ist lokal nur der Weg gegen ein Fake-Binary.
- Das alte Herdr-Pane bleibt offen (lieber ein überzähliges Pane als ein geschlossenes mit laufender Arbeit; Grundsatz Plan-Pane, #496).
- Die Cloud-Übergabe hängt daran, dass die Sitzung das Werkzeug `create_session` hat; fehlt es oder schlägt es fehl, gilt `inline` (wachsender Kontext).
- Lokal ist die neue Sitzung kein frischer Container, sondern eine neue Claude-Sitzung im selben Projektordner; der Auftrag der alten Sitzung (Kennung je Sitzung, #613) wird aus dem Startauftrag neu angelegt, `queue add` ist idempotent.
- Ob die neue Sitzung den Startauftrag befolgt, erzwingt kein Hook; das Format ist Auskunft.

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] Ein Auftrag mit mindestens zwei Issues läuft ohne Tippen durch, jedes Issue in frischem Kontext. Cloud-Echtbeleg: Der Auftrag dieser Sitzung wird vor der Auslieferung um #665 erweitert (`queue add 665 --autark`); nach dem Merge von #667 übergibt die Sitzung #665 per `create_session` an eine neue Sitzung, die #665 ohne Tippen bis zur Auslieferung bearbeitet. Lokal belegt gegen Fake-Herdr; der echte lokale Herdr-Durchlauf wird gemäß PO-Auftrag (Vorgängersitzung: „Bleibt am Epic etwas offen (lokaler Durchlauf mit Herdr), halte es im Issue fest“) am Epic #649 als offen vermerkt
- [ ] Messung je Sitzung: Der Startauftrag verlangt, beim Abschluss den Wert `CONTEXT_TOKENS` aus `workflow.py context` im Abschlusskommentar des Issues zu nennen; der Wert der Sitzung von #665 und der dieser Sitzung stehen am Epic #649 und liegen unter der Schwelle `CONTEXT_THRESHOLD`
- [ ] Ohne Cloud und ohne Herdr verhält sich die Kette wie bisher (`inline`), ohne Auftrag oder bei `ENDSTATE=you` ändert sich nichts
- [ ] Der Auftrag und sein Fortschritt liegen auf der Platte bzw. im Startauftrag, nicht im Gespräch; Halt nur an PO-Punkten
- [ ] Keine bestehende Funktion ist kaputtgegangen (Regressionslauf `pytest tests/` grün, `skills/` und `.claude/agents` ohne Drift, kein `pytest.skip` zur Entschärfung), Doku, CHANGELOG und Version 4.25.0 veröffentlicht

## Acceptance Criteria

- **AC-1:** Given Kill-Switch `auftrag.enabled: false`, kein Auftrag, ein nicht autarker Auftrag, Autonomie `manual` oder kein offenes nächstes Issue / When `workflow.py handoff` läuft / Then lautet die Ausgabe `HANDOFF=none`, es folgt kein `PROMPT_BEGIN`, Exit 0
  - Test: tests/test_handoff_667.py::test_handoff_none_cases

- **AC-2:** Given autarker Auftrag im Auto-Modus mit offenem nächsten Issue M und `CLAUDE_CODE_REMOTE=true` / When `workflow.py handoff` läuft / Then lauten die Zeilen `HANDOFF=cloud`, `NEXT=<M>` und `REPO_URL=<https-URL ohne .git>` (ohne https-Remote `REPO_URL=none`), gefolgt vom Startauftrag
  - Test: tests/test_handoff_667.py::test_handoff_cloud_with_repo_url

- **AC-3:** Given autarker Auftrag im Auto-Modus, kein Cloud-Env, aktives Herdr-Pane und `claude` im PATH / When `workflow.py handoff` läuft / Then lautet der Weg `HANDOFF=herdr`; ohne Herdr-Pane oder ohne `claude` im PATH lautet er `HANDOFF=inline`
  - Test: tests/test_handoff_667.py::test_handoff_route_herdr_and_inline

- **AC-4:** Given ein autarker Auftrag mit note (mit Anführungszeichen) und spur und mehreren offenen Nummern / When der Startauftrag ausgegeben wird / Then nennt er Issue #M, den Befehl 00-intake mit Hinweis auf skills/00-intake/SKILL.md, `queue add` mit allen offenen Nummern ab M in erhaltener Reihenfolge und `--autark`, `--note` (Anführungszeichen maskiert) und `--spur` nur wenn gesetzt, die Haltregel für PO-Punkte, den Satz zum frischen Kontext (#667) und die Messanweisung mit `workflow.py context`/`CONTEXT_TOKENS`; der Hook-Pfad ist `.claude/hooks` im Konsumenten-Projekt bzw. `core/hooks` im Framework-Repo
  - Test: tests/test_handoff_667.py::test_prompt_content_numbers_note_spur

- **AC-5:** Given Weg `herdr` und ein Fake-Herdr-Binary (`HERDR_ENV=1`, `HERDR_PANE_ID`, `HERDR_BIN_PATH`), das split-JSON liefert und Aufrufe protokolliert / When `workflow.py handoff --start` läuft / Then ruft es `pane split <eigenes Pane> --direction right --cwd <Projekt-Root> --no-focus` und danach `pane run <neues Pane>` mit `exec claude` und dem shlex-gequoteten Startauftrag auf, nie mit dem eigenen Pane als Ziel von `pane run`, meldet `STARTED=yes` und schreibt das Auftragsfeld `handoff` mit Nummer, Weg `herdr` und ISO-Zeit
  - Test: tests/test_handoff_667.py::test_herdr_start_with_fake_binary

- **AC-6:** Given ein bereits vermerkter Start für dieselbe Nummer M / When `workflow.py handoff --start` erneut läuft / Then lautet die Ausgabe `STARTED=already` und das Fake-Binary erhält keinen weiteren Aufruf
  - Test: tests/test_handoff_667.py::test_start_idempotent_already

- **AC-7:** Given ein Fake-Herdr-Binary, dessen `pane split` oder `pane run` fehlschlägt, oder ein fehlendes Binary / When `workflow.py handoff --start` läuft / Then lauten die Zeilen `STARTED=no` mit `REASON=<kurz>`, Exit 0, und es wird kein `handoff`-Vermerk geschrieben
  - Test: tests/test_handoff_667.py::test_herdr_failure_started_no

- **AC-8:** Given `workflow.py handoff --mark cloud` bzw. `--mark herdr` / When der Befehl läuft / Then steht im Auftrag `handoff` mit Nummer, Weg und ISO-Zeit; bei `--mark` mit ungültigem Weg schreibt der Befehl Usage auf stderr, endet mit Exit 1 und der Auftrag bleibt unverändert; `_normalize_auftrag` verwirft ein `handoff`-Feld mit ungültiger Nummer oder ungültigem Weg
  - Test: tests/test_handoff_667.py::test_mark_validation_and_normalize

- **AC-9:** Given die Befehlstexte `core/commands/60-validate.md` und `70-deploy.md` samt erzeugten Skills / When ihr Absatz „Kette bei offenem Auftrag" gelesen wird / Then enthält er `workflow.py handoff`, `create_session`, `handoff --mark cloud` und `handoff --start`, behält den Selbstaufruf `/00-intake #M` als Weg `inline`, und `80-workflow.md` dokumentiert `handoff`; `sync_skills.py --check` meldet keine Drift
  - Test: tests/test_handoff_667.py::test_command_texts_mention_handoff

- **AC-10:** Given ein Auftrag, in dem `end_state` „aus deinem Auftrag" ausgibt / When `workflow.py endstate` und der Stop-Hook `footer_gate.py` laufen / Then bleibt die Zeile unverändert und das Gate bewertet sie wie bisher
  - Test: tests/test_handoff_667.py::test_endstate_unchanged (zusätzlich bleiben die Bestandstests zu `footer_gate` und `end_state` grün)

## Test Plan

Automatische Tests, jeweils an eine AC gebunden, ohne Netzwerk, mit tmp-Projekt und Subprozess-Aufruf von `workflow.py`. Das Test-Env setzt `OPENSPEC_AUTONOMY`, `CLAUDE_CODE_REMOTE`, `HERDR_ENV`, `HERDR_PANE_ID`, `HERDR_BIN_PATH` und `PATH` explizit, weil die Cloud-Umgebung `OPENSPEC_AUTONOMY=auto` und `CLAUDE_CODE_REMOTE=true` vorgibt.

- GIVEN kein autarker Auftrag oder Modus manual WHEN `handoff` THEN `HANDOFF=none` (AC-1)
- GIVEN Cloud-Env und autarker Auftrag mit https-Remote `.git` WHEN `handoff` THEN `HANDOFF=cloud`, `REPO_URL` ohne `.git` (AC-2)
- GIVEN Herdr-Env und `claude` im PATH WHEN `handoff` THEN `herdr`; ohne beides `inline` (AC-3)
- GIVEN note mit Anführungszeichen und spur WHEN Startauftrag THEN Nummernliste, Maskierung, spur, Haltregel (AC-4)
- GIVEN Fake-Binary WHEN `handoff --start` THEN split und run protokolliert, `STARTED=yes`, Vermerk (AC-5)
- GIVEN Vermerk vorhanden WHEN `--start` erneut THEN `already`, keine neuen Aufrufe (AC-6)
- GIVEN Fake-Binary schlägt fehl WHEN `--start` THEN `STARTED=no` mit `REASON`, kein Vermerk (AC-7)
- GIVEN `--mark` gültig bzw. ungültig WHEN Aufruf THEN Vermerk bzw. Exit 1 ohne Schreibung (AC-8)
- GIVEN Befehlstexte WHEN gelesen THEN `handoff` und `create_session` enthalten (AC-9)
- GIVEN Auftrag WHEN `endstate` THEN Zeile unverändert (AC-10)

Läufe:

- `pytest tests/test_handoff_667.py` (RED zuerst, dann GREEN)
- Regressionslauf: `pytest tests/` (insbesondere `test_auftrag_551.py` und die `footer_gate`-Tests)
- `python3 -m py_compile core/hooks/workflow.py core/hooks/hook_utils.py core/hooks/herdr_bridge.py`
- `python3 scripts/sync_skills.py --check` und `python3 scripts/sync_cloud_agents.py --check`

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Die Übergabe ist eine Auskunfts-CLI mit optionaler Aktion nach dem Muster von `queue`, `autonomy` und `context`; sie führt keine neue Architekturebene ein. Der Cloud-Weg liegt im Befehlstext, weil nur Claude das MCP-Werkzeug `create_session` aufrufen kann; Python liefert Wegwahl und Startauftrag. Der Herdr-Weg startet nur einen Prozess und tippt nie in ein Claude-Pane, das hält die Entscheidung aus #662/#663 (Herdr tippt nichts) ein. Der Rest-Auftrag reist im Startauftrag, weil die Auftragsdatei an die Sitzungskennung gebunden ist (#613) und ein Cloud-Container frisch ist; `queue add` ist idempotent. Reversibel: Rückfall `inline` ist der bisherige Weg.
- **Alternative A, Herdr tippt `/clear` und Folgebefehl:** verworfen, in #662/#663 als fehleranfällig zurückgebaut.
- **Alternative B, Auftragsdatei in die neue Sitzung kopieren oder teilen:** verworfen. Die Datei gehört der alten Sitzungskennung, ein Cloud-Container hat sie nicht; Neuanlage aus dem Startauftrag deckt beide Orte gleich ab.
- **Alternative C, altes Pane schließen:** verworfen, schließt im Zweifel laufende Arbeit; ein überzähliges Pane ist harmlos (Known Limitation).
- **Alternative D, Config-Schlüssel für den Weg:** verworfen, die Umgebung entscheidet eindeutig; der bestehende Schalter `auftrag.enabled` genügt als Kill-Switch, `config.yaml` bleibt unangetastet.

## Changelog

- 2026-11-25: Initial spec created
