---
entity_id: feat-696-handoff-phasenwechsel
type: feature
created: 2026-11-26
updated: 2026-11-26
status: draft
version: "1.0"
workflow: feat-696-handoff-phasenwechsel
tags: [workflow, herdr, handoff, kontext, phasenwechsel, epic-649]
---

# Frische Sitzung am Phasenwechsel innerhalb eines Issues (Issue #696)

## Approval

- [ ] Approved

## Purpose

Im Auto-Modus wächst der Kontext innerhalb eines Issues ungebremst (Beleg #691: rund 200k bei einer Schwelle von rund 150k), und seit #663 tippt niemand mehr `/clear`; frischen Kontext gibt es nur je Issue (`workflow.py handoff`, #667/#694). Neu: Liegt die Messung an einem Phasenwechsel mit positivem Checkpoint über der Schwelle, startet Claude per `workflow.py handoff --same --start` eine neue Sitzung für denselben Workflow im selben Worktree (Startauftrag `/<nächster Befehl> #N`, eigener Tab, Aufräumen der Vorgängerin wie #694) und beendet seine Antwort.

## Source

- **File:** `core/hooks/workflow.py`, `core/commands/10-context.md`, `20-analyse.md`, `30-write-spec.md`, `40-tdd-red.md`, `50-implement.md`, `80-workflow.md`, `docs/befehle/80-workflow.md`
- **Identifier:** `workflow.cmd_context` (neue Zeile `CONTEXT_HANDOFF`), `workflow.cmd_handoff` (Schalter `--same`), `workflow.handoff_same_prompt` (neu), Workflow-State-Feld `handoff_same`

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `workflow.cmd_context`, `_context_measurement` | function | Messung und Ausgabe `CONTEXT_*`; bekommt `CONTEXT_HANDOFF` |
| `hook_utils.context_budget_settings`, `effective_context_threshold` | function | Schalter und wirksame Schwelle (Baseline plus Wachstum) |
| `workflow.expected_footer_command`, `next_step` | function | Folgebefehl inkl. Issue-Nummer; Freitext-Schritte beginnen nicht mit `/` |
| `workflow.cmd_handoff`, `handoff_prompt`, `_handoff_label` | function | Muster für Startauftrag, Label und `queue add`-Zeile; Verhalten ohne `--same` unverändert |
| `herdr_bridge.start_session` (#667/#694), `_pane`, `start_predecessor_cleanup` | function | Start im eigenen Tab, Pane-Erkennung, Aufräumen der Vorgängerin bei Endzustand ⏳ |
| `workflow.cmd_waiting`, State-Feld `waiting_on` | function | Endzustand ⏳ der Vorgängerin als Bedingung für das Aufräumen |
| `.claude/auftrag.json` | state | optionaler autarker Auftrag; liefert die `queue add`-Zeile |
| Autonomie-Modus `auto`, Env `CLAUDE_CODE_REMOTE`, `claude` im PATH | env | Voraussetzungen des Weges `herdr` |
| `scripts/sync_skills.py`, `scripts/sync_cloud_agents.py` | tool | Generat nach Befehlstext-Änderung neu erzeugen |
| docs/specs/feat-694-handoff-tab.md, docs/specs/feat-667-fresh-session.md | spec | Vorarbeit |
| Issue #696, Epic #649, #662, #663, #557 | issue | Auftrag, Auto-Kette, Schwelle |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| core/hooks/workflow.py | MODIFY | `cmd_context` gibt `CONTEXT_HANDOFF=on\|off` aus; `cmd_handoff` kennt `--same`; neue Helfer für Worktree-Wurzel, Startauftrag, Vermerk `handoff_same` |
| core/commands/10-context.md, 20-analyse.md, 30-write-spec.md, 40-tdd-red.md, 50-implement.md | MODIFY | Abschnitt Auto-Modus/Kontext-Haushalt: bei `CONTEXT_HANDOFF=on` Übergabe statt Selbstaufruf |
| core/commands/80-workflow.md, docs/befehle/80-workflow.md | MODIFY | `handoff --same` dokumentiert |
| skills/*/SKILL.md, .claude/agents | REGENERATE | `python3 scripts/sync_skills.py`, `python3 scripts/sync_cloud_agents.py` |
| tests/test_feat_696_handoff_same.py | CREATE | Tests zu den ACs (Fake-herdr-Binary wie in tests/test_handoff_tab_694.py) |
| CHANGELOG.md, .claude-plugin/plugin.json, CLAUDE.md (Versionszeile), README.md | MODIFY | Version 4.28.0, Eintrag |

Nicht geändert: `config.yaml` und jede wirksame Gate-Config (Defaults genügen), `herdr_bridge.py` (Start und Aufräumen aus #694 unverändert), `hooks/hooks.json`, `footer_gate.py`, `end_state`, der Weg ohne `--same`.

### Estimated Changes

- Files: 1 Hook, 5 Phasenbefehle, 2 Doku-Dateien, 1 Testdatei, 4 Versionsdateien, Generat
- LoC: ca. +300/-10 (Code ca. 150, Tests ca. 150)
- Risk Level: HIGH (Hook-Code in allen Konsumenten; startet Sitzungen, die Vorgängerin wird aufgeräumt) — Adversary mit zwei Runden

### Out of Scope

- Phasenwechsel `/60-validate` nach Auslieferung: dort greift der Issue-Handoff (#667)
- Cloud und Terminal ohne Herdr: bisheriges Verhalten (automatische Verdichtung)
- Phase 3 mit Freigabe-Schritt (Freitext-Folgebefehl): keine Übergabe
- Änderungen an `herdr_bridge.py`, Config-Schlüssel für die Übergabe

## Implementation Details

1. **`CONTEXT_HANDOFF`.** `cmd_context` ergänzt vor der weiterhin letzten Zeile `CONTEXT_STOP=` die Zeile `CONTEXT_HANDOFF=on|off`. `on` genau dann, wenn alles gilt: `context_budget` an, Messung ≥ `effective_context_threshold`, Messung aus der eigenen Sitzung (eigene Messdatei oder eigenes Transcript, nicht der Rückfall auf die jüngste fremde Messdatei; sonst liest die frisch gestartete Nachfolgerin den Wert der Vorgängerin und übergibt sofort wieder), Autonomie `auto`, `CLAUDE_CODE_REMOTE` nicht `true`, Herdr-Pane vorhanden (`herdr_bridge._pane()`), `claude` im PATH. Gilt auch bei offenem autarkem Auftrag; dort bleiben `CONTEXT_CUT=off` und `CONTEXT_REASON=AUTARK` unverändert. Jeder Fehler ergibt `off`; alle bisherigen Zeilen bleiben unverändert.
2. **`handoff --same`.** Übergabe desselben aktiven Workflows. Ausgabe `HANDOFF=herdr|none`, `NEXT=<Folgebefehl inkl. #N>|none` (aus `expected_footer_command(state)`; nur wenn er mit `/` beginnt, sonst `HANDOFF=none`), bei `--start` zusätzlich `STARTED=yes|no|already` (bei `no` mit `REASON=`) und der Startauftrag zwischen `PROMPT_BEGIN` und `PROMPT_END`. `herdr` nur bei aktivem Workflow, Autonomie `auto`, nicht Cloud, Herdr-Pane und `claude`; sonst `none`. Kein autarker Auftrag nötig. `--same` mit `--mark` ist ein Usage-Fehler (Exit 1). Ohne `--same` verhält sich `handoff` exakt wie bisher.
3. **Arbeitsordner.** `cwd` der neuen Sitzung ist die Wurzel des aktuellen Worktrees (`git rev-parse --show-toplevel` im cwd), nicht `find_project_root()`: dieses löst Worktrees zum Haupt-Repo auf, die neue Sitzung bekäme per Worktree-Pflicht einen frischen Worktree von origin/main ohne die laufenden Änderungen. Scheitert die Ermittlung: `STARTED=no`, `REASON` nennt es, kein Start.
4. **Start.** `herdr_bridge.start_session(prompt, cwd, label)` mit Label `#N Titel` (Tab, Env `OPENSPEC_HANDOFF_PREV_PANE`, Rückfall Split, Aufräumen der Vorgängerin) unverändert aus #694.
5. **Doppelstart-Schutz.** Nach erfolgreichem Start schreibt der Befehl ins Workflow-State das Feld `handoff_same = {"phase": <aktuelle Phase>, "next": <NEXT>, "at": <UTC ISO>}`. Steht dort bereits dieselbe Phase und derselbe NEXT, meldet er `STARTED=already` ohne zweiten Start. Ohne `--start` wird nichts geschrieben. Der Vermerk hängt am Workflow-State, weil es keinen Auftrag geben muss.
6. **Endzustand ⏳.** Nach `STARTED=yes` setzt der Befehl `waiting_on` im State auf einen Text wie „frische Sitzung setzt /50-implement #N fort", damit die Vorgängerin im Endzustand ⏳ endet (Bedingung für das Aufräumen aus #694). Bei `already` bleibt `waiting_on` unverändert.
7. **Startauftrag** (ohne Gesprächswissen lesbar): nennt Workflow-Name und Issue; enthält, falls `.claude/auftrag.json` offen ist, dieselbe `queue add`-Zeile wie `handoff_prompt` (alle offenen Issues einschließlich des laufenden, `--autark`, `--note`, `--spur`); dann `python3 <hooks>/workflow.py waiting --clear` und den Folgebefehl („Kurzbefehl `50-implement` mit Argument `#N`", Fallback-Hinweis auf `skills/<befehl>/SKILL.md` wie im bestehenden Prompt); den Hinweis „Diese Sitzung setzt den Workflow mit frischem Kontext fort (#696)"; die autark-Zeile wie bisher; die Bitte, in der ersten Meldung den Stand des Workflows in einem Satz zu nennen.
8. **Phasenbefehle 10 bis 50.** Im Abschnitt Auto-Modus/Kontext-Haushalt, nach dem Checkpoint und vor dem Selbstaufruf: bei `CONTEXT_HANDOFF=on` `workflow.py handoff --same --start`; bei `STARTED=yes` oder `already` den Folge-Skill nicht aufrufen und die Antwort mit Checkpoint-Block und ⏳-Zeile beenden (Turn sofort beenden, keine weitere Arbeit); bei `STARTED=no` die Kette wie bisher fortsetzen. Die `CONTEXT_STOP`-Regel (Modus manual) bleibt unverändert. Nur an diesen Phasenwechseln mit positivem Checkpoint. Danach `python3 scripts/sync_skills.py`.
9. **Version.** 4.28.0 (Minor, neue Funktion) in `.claude-plugin/plugin.json`, CLAUDE.md-Versionszeile, README; CHANGELOG-Eintrag.

## Expected Behavior

- **Input:** Workflow im Auto-Modus unter Herdr, Phasenwechsel mit positivem Checkpoint, Messung der eigenen Sitzung über der wirksamen Schwelle
- **Output:** `context` meldet `CONTEXT_HANDOFF=on`; `handoff --same --start` meldet `HANDOFF=herdr`, `NEXT=/50-implement #N`, `STARTED=yes`; neue Sitzung im eigenen Tab im selben Worktree setzt den Workflow fort; die Vorgängerin beendet ihren Turn mit ⏳
- **Side effects:** Neuer Herdr-Tab; State-Felder `handoff_same` und `waiting_on`; später Schließen des Vorgänger-Tabs (#694); ohne Herdr oder in der Cloud keinerlei Änderung gegenüber heute

## Known Limitations

- Phasenwechsel in /60-validate nach Auslieferung sind nicht abgedeckt; dort gibt es den Issue-Handoff.
- Die Vorgängerin muss ihren Turn sofort beenden; arbeitet sie nach dem Start weiter, laufen zwei Sitzungen im selben Worktree (das Aufräumen schließt erst bei ⏳, nie bei laufender Arbeit). Der Befehlstext verlangt das Beenden, ein Hook erzwingt es nicht.
- Ohne Herdr (Cloud, Terminal) bleibt es bei der automatischen Verdichtung wie bisher.
- Startet die Nachfolgerin schon groß (Grundkontext), schützt gegen sofortige Wiederholung der Vermerk je Phase und die wirksame Schwelle (Baseline plus Wachstum), nicht eine absolute Grenze.
- Der Echtlauf mit Herdr ist aus der Cloud nicht ausführbar; belegt ist er gegen das Fake-Binary, der Echtbeleg steht im Abschlusskommentar des Issues.

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] Ein Workflow im Auto-Modus unter Herdr, der die Schwelle an einem Phasenwechsel überschreitet, setzt sich in einem neuen Tab mit dem Folgebefehl im selben Worktree fort, und der Vorgänger-Tab wird geschlossen (Beleg im Abschlusskommentar des Issues)
- [ ] In der Cloud, ohne Herdr, im Modus manual und bei Phase 3 mit Freigabe verhält sich die Kette wie bisher
- [ ] `skills/` und `.claude/agents` ohne Drift, Regressionslauf `pytest tests/` grün, kein `pytest.skip` zur Entschärfung, Doku, CHANGELOG und Version 4.28.0 veröffentlicht

## Acceptance Criteria

- **AC-1:** Given `context_budget` an, Messung aus der eigenen Sitzung ≥ wirksame Schwelle, Autonomie `auto`, `CLAUDE_CODE_REMOTE` nicht gesetzt, Herdr-Pane (Fake-Env) und `claude` im PATH / When `workflow.py context` läuft / Then enthält die Ausgabe `CONTEXT_HANDOFF=on` unmittelbar vor der letzten Zeile `CONTEXT_STOP=`, und alle bisherigen Zeilen sind unverändert
  - Test: tests/test_feat_696_handoff_same.py::test_context_handoff_on_when_all_conditions_hold

- **AC-2:** Given je eine Abweichung (Messung unter Schwelle, `context_budget` aus, Autonomie nicht `auto`, `CLAUDE_CODE_REMOTE=true`, kein Herdr-Pane, `claude` nicht im PATH, Fehler beim Messen) / When `workflow.py context` läuft / Then lautet die Zeile `CONTEXT_HANDOFF=off`, der Exit-Code ist 0 und `CONTEXT_STOP=` bleibt die letzte Zeile
  - Test: tests/test_feat_696_handoff_same.py::test_context_handoff_off_matrix

- **AC-3:** Given nur die Messdatei einer fremden Sitzung (Rückfall auf die jüngste Messdatei) mit Wert über der Schwelle, eigene Sitzung ohne Messung / When `workflow.py context` läuft / Then lautet `CONTEXT_HANDOFF=off`
  - Test: tests/test_feat_696_handoff_same.py::test_context_handoff_off_for_foreign_measurement

- **AC-4:** Given ein offener autarker Auftrag und Messung über der Schwelle sonst wie in AC-1 / When `workflow.py context` läuft / Then lautet `CONTEXT_HANDOFF=on`, während `CONTEXT_CUT=off` und `CONTEXT_REASON=AUTARK` unverändert bleiben
  - Test: tests/test_feat_696_handoff_same.py::test_context_handoff_on_with_autark_auftrag_keeps_cut_off

- **AC-5:** Given aktiver Workflow in Phase mit Folgebefehl `/50-implement #N`, Autonomie `auto`, Fake-Herdr, `claude` im PATH / When `workflow.py handoff --same` (ohne `--start`) läuft / Then gibt es `HANDOFF=herdr` und `NEXT=/50-implement #N` aus, startet nichts (keine Herdr-Aufrufe) und schreibt keinen Vermerk `handoff_same`
  - Test: tests/test_feat_696_handoff_same.py::test_same_without_start_only_reports

- **AC-6:** Given Folgebefehl ohne führendes `/` (Phase 3 wartet auf Freigabe), kein aktiver Workflow, Autonomie nicht `auto`, `CLAUDE_CODE_REMOTE=true`, kein Herdr-Pane oder `claude` fehlt / When `workflow.py handoff --same --start` läuft / Then lautet die Ausgabe `HANDOFF=none`, es gibt keinen Start, und `handoff` ohne `--same` verhält sich in denselben Fällen wie vor der Änderung
  - Test: tests/test_feat_696_handoff_same.py::test_same_none_matrix_and_plain_handoff_unchanged

- **AC-7:** Given `--same` zusammen mit `--mark` / When `workflow.py handoff --same --mark` läuft / Then endet der Befehl mit Exit 1 und einer Usage-Meldung, ohne Start und ohne Zustandsänderung
  - Test: tests/test_feat_696_handoff_same.py::test_same_with_mark_is_usage_error

- **AC-8:** Given ein Test in einem Git-Worktree (Hauptrepo und Worktree mit unterschiedlichen Pfaden), Fake-Herdr-Binary / When `workflow.py handoff --same --start` im Worktree läuft / Then lautet `cwd` im `tab create`-Aufruf die Worktree-Wurzel (`git rev-parse --show-toplevel`) und nicht das Hauptrepo
  - Test: tests/test_feat_696_handoff_same.py::test_start_uses_worktree_toplevel_as_cwd

- **AC-9:** Given ein cwd, aus dem `git rev-parse --show-toplevel` scheitert / When `workflow.py handoff --same --start` läuft / Then lautet die Ausgabe `STARTED=no` mit `REASON=` (nennt die fehlende Worktree-Wurzel), Exit 0, es gibt keinen Herdr-Aufruf und keinen Vermerk
  - Test: tests/test_feat_696_handoff_same.py::test_toplevel_failure_means_no_start

- **AC-10:** Given Fake-Herdr, das `tab create` und `pane run` annimmt / When `workflow.py handoff --same --start` läuft / Then ruft es `start_session` so auf, dass `tab create` das Label `#N Titel` und Env `OPENSPEC_HANDOFF_PREV_PANE=<eigenes Pane>` erhält, danach `pane run` mit `exec claude` und dem Startauftrag folgt, und die Ausgabe `STARTED=yes` lautet
  - Test: tests/test_feat_696_handoff_same.py::test_start_goes_through_start_session_in_tab

- **AC-11:** Given ein erfolgreicher Start / When `workflow.py handoff --same --start` endet / Then steht im Workflow-State `handoff_same` mit `phase` gleich der aktuellen Phase, `next` gleich dem ausgegebenen NEXT und einem UTC-ISO-Zeitstempel in `at`; scheitert der Start (`STARTED=no`), wird nichts geschrieben
  - Test: tests/test_feat_696_handoff_same.py::test_started_writes_handoff_same_note

- **AC-12:** Given `handoff_same` mit derselben Phase und demselben NEXT / When `workflow.py handoff --same --start` erneut läuft / Then lautet die Ausgabe `STARTED=already`, es gibt keinen zweiten `tab create`, und `handoff_same` und `waiting_on` bleiben unverändert; bei anderer Phase oder anderem NEXT startet es erneut
  - Test: tests/test_feat_696_handoff_same.py::test_second_start_same_phase_is_already

- **AC-13:** Given ein erfolgreicher Start (`STARTED=yes`) / When der Befehl endet / Then ist `waiting_on` im State ein Text, der die Fortsetzung durch die frische Sitzung mit dem Folgebefehl nennt (zum Beispiel „frische Sitzung setzt /50-implement #N fort"), sodass `end_state` ⏳ ergibt
  - Test: tests/test_feat_696_handoff_same.py::test_started_sets_waiting_on_for_hourglass_end_state

- **AC-14:** Given ein offener autarker Auftrag und ein aktiver Workflow / When `workflow.py handoff --same --start` den Startauftrag ausgibt / Then steht er zwischen `PROMPT_BEGIN` und `PROMPT_END`, nennt Workflow-Name und Issue, enthält dieselbe `queue add`-Zeile wie `handoff_prompt` (alle offenen Issues einschließlich des laufenden, `--autark`, `--note`, `--spur`), dann `workflow.py waiting --clear`, den Folgebefehl („Kurzbefehl `50-implement` mit Argument `#N`" samt Fallback-Hinweis auf `skills/50-implement/SKILL.md`), den Hinweis „Diese Sitzung setzt den Workflow mit frischem Kontext fort (#696)", die autark-Zeile und die Bitte um einen Satz zum Stand des Workflows; ohne offenen Auftrag fehlen `queue add` und autark-Zeile
  - Test: tests/test_feat_696_handoff_same.py::test_prompt_contains_all_building_blocks

- **AC-15:** Given die Befehlstexte `core/commands/10-context.md`, `20-analyse.md`, `30-write-spec.md`, `40-tdd-red.md`, `50-implement.md` samt erzeugten Skills / When der Abschnitt Auto-Modus/Kontext-Haushalt gelesen wird / Then verlangt er bei `CONTEXT_HANDOFF=on` den Aufruf `workflow.py handoff --same --start`, bei `STARTED=yes` oder `already` Antwort beenden ohne Folge-Skill-Aufruf, bei `STARTED=no` Kette wie bisher, und lässt die `CONTEXT_STOP`-Regel unverändert; `sync_skills.py --check` und `sync_cloud_agents.py --check` melden keine Drift
  - Test: tests/test_feat_696_handoff_same.py::test_phase_commands_describe_handoff_and_skills_in_sync

- **AC-16:** Given `core/commands/80-workflow.md` und `docs/befehle/80-workflow.md` / When der Absatz zu `handoff` gelesen wird / Then beschreibt er `handoff --same [--start]` mit Ausgaben `HANDOFF`, `NEXT`, `STARTED`, und `CHANGELOG.md` führt Version 4.28.0 mit Verweis auf #696, Versionsangaben in plugin.json, CLAUDE.md und README stimmen überein
  - Test: tests/test_feat_696_handoff_same.py::test_docs_changelog_and_version_consistent

## Test Plan

Automatische Tests, jeweils an eine AC gebunden, ohne Netzwerk, mit tmp-Projekt (für AC-8 und AC-9 mit echtem `git worktree`), Subprozess-Aufruf von `workflow.py` und einem Fake-Herdr-Binary (Muster aus tests/test_handoff_tab_694.py), das Aufrufe protokolliert. Das Test-Env setzt `OPENSPEC_AUTONOMY`, `CLAUDE_CODE_REMOTE`, `HERDR_ENV`, `HERDR_PANE_ID`, `HERDR_WORKSPACE_ID`, `HERDR_BIN_PATH` und `PATH` (mit Fake-`claude`) explizit; Messdateien werden im tmp-Projekt vorgegeben.

- GIVEN alle Voraussetzungen und Messung über Schwelle WHEN `context` THEN `CONTEXT_HANDOFF=on` vor `CONTEXT_STOP=` (AC-1)
- GIVEN je eine Abweichung WHEN `context` THEN `off`, Exit 0 (AC-2)
- GIVEN nur fremde Messdatei WHEN `context` THEN `off` (AC-3)
- GIVEN autarker Auftrag WHEN `context` THEN `on`, `CUT=off`, `REASON=AUTARK` (AC-4)
- GIVEN `handoff --same` ohne `--start` WHEN gelaufen THEN nur Meldung, kein Herdr-Aufruf, kein Vermerk (AC-5)
- GIVEN Freitext-Folgebefehl, Cloud, kein Herdr, kein Workflow WHEN `--same --start` THEN `HANDOFF=none`; `handoff` ohne `--same` unverändert (AC-6)
- GIVEN `--same --mark` WHEN gelaufen THEN Exit 1 (AC-7)
- GIVEN Worktree WHEN `--same --start` THEN `cwd` ist die Worktree-Wurzel (AC-8)
- GIVEN fehlschlagendes `git rev-parse` WHEN `--same --start` THEN `STARTED=no`, `REASON` (AC-9)
- GIVEN Fake-Herdr WHEN `--same --start` THEN Tab mit Label und Env, danach `pane run`, `STARTED=yes` (AC-10)
- GIVEN Erfolg und Misserfolg WHEN `--same --start` THEN Vermerk `handoff_same` nur bei Erfolg (AC-11)
- GIVEN Vermerk mit gleicher Phase und NEXT WHEN `--same --start` THEN `already`, kein zweiter Tab; bei anderer Phase Start (AC-12)
- GIVEN Erfolg WHEN State gelesen THEN `waiting_on` nennt die Fortsetzung, `end_state` ergibt ⏳ (AC-13)
- GIVEN Auftrag mit und ohne WHEN Startauftrag THEN alle Bausteine bzw. ohne Auftragsbausteine (AC-14)
- GIVEN Befehlstexte und Skills WHEN gelesen und `--check` THEN Übergabe-Regel vorhanden, keine Drift (AC-15)
- GIVEN Doku, CHANGELOG, Versionsdateien WHEN gelesen THEN `handoff --same` und 4.28.0 konsistent (AC-16)

Läufe:

- `pytest tests/test_feat_696_handoff_same.py tests/test_handoff_tab_694.py tests/test_handoff_667.py tests/test_handoff_668.py` (RED zuerst, dann GREEN)
- Regressionslauf: `pytest tests/` (insbesondere Kontext-Tests und `footer_gate`-Tests)
- `python3 -m py_compile core/hooks/workflow.py`
- `python3 scripts/sync_skills.py --check` und `python3 scripts/sync_cloud_agents.py --check`

Echtbeleg (manuell, Herdr lokal): Ein Workflow im Auto-Modus unter Herdr überschreitet die Schwelle an einem Phasenwechsel. Erwartet: neuer Tab mit dem Folgebefehl im selben Worktree startet, der Vorgänger-Tab wird geschlossen. Der Beleg (Tab-Liste vorher und nachher, Anzeige des Worktree-Pfads der neuen Sitzung) steht im Abschlusskommentar des Issues.

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Die Änderung erweitert den bestehenden Herdr-Start aus #667/#694 um einen Schalter und eine Ausgabezeile; es entsteht keine neue Architekturebene, kein neuer Hook und keine Gate-Config. Entscheidung 1, Übergabe statt `/clear`-Tippen: Das Tippen (#663) ist zu fragil und für Auto-Läufe nicht automatisierbar; eine neue Sitzung mit Startauftrag liefert frischen Kontext ohne Eingriff. Entscheidung 2, Worktree-Wurzel als cwd: `find_project_root()` löst auf das Haupt-Repo auf, die Nachfolgerin verlöre per Worktree-Pflicht den Arbeitsstand. Entscheidung 3, Vermerk im Workflow-State statt im Auftrag: Es muss keinen Auftrag geben, der Workflow existiert immer. Reversibel: ohne Herdr oder bei `STARTED=no` läuft die Kette wie bisher.
- **Alternative A, `/clear` per Tastatureingabe in die eigene Pane:** verworfen, fragil (#663).
- **Alternative B, Vermerk im Auftrag (`handoff`, Schlüssel Issue):** verworfen, kein Auftrag nötig und Schlüssel je Issue trennt Phasen nicht.
- **Alternative C, `find_project_root()` als cwd:** verworfen, Verlust der laufenden Änderungen.

## Changelog

- 2026-11-26: Initial spec created
