---
entity_id: feat-612-plan-kopf-auslieferung
type: feature
created: 2026-11-15
updated: 2026-11-15
status: draft
version: "1.0"
workflow: feat-612-plan-kopf-auslieferung
tags: [herdr, plan-pane, endstate, ship, issue-brief, workflow]
---

# Plan-Pane: Issue-Kurzfassung im Kopf und Auslieferung als eigener Schritt (Issue #612)

## Approval

- [ ] Approved

## Purpose

Der Plan-Pane (Herdr, `workflow.py plan --watch`) soll oben sagen, worum es geht, und unten die Wahrheit über den Stand zeigen. Zwei Befunde des PO aus dem Alltag:

1. **Kopftext zu kurz.** Der Kopf zeigt nur die ersten sechs Wörter des Issue-Titels (`short_title`, #490), an der Pane-Breite gekappt („Paket F: Profile (Vorlieben je Pers“). Was das Issue beheben oder erreichen will, steht nirgends.
2. **„Erledigt“ zu früh.** `/60-validate` setzt in Step 4 `phase8_complete`; Commit, Push, PR, CI-Warten und Merge kommen danach. Ab Phase 8 zeigt der Plan „✔ 8 Fertig / ✅ Erledigt: #12 ist fertig“, während im Chat noch „⏳ Läuft noch: Testlauf …“ steht und `gh pr checks --watch` läuft. Das Feld `waiting_on` (#550) muss Claude von Hand setzen und wird vergessen; der Deploy hat seit #510 einen mechanischen Marker, die Auslieferung nicht.

## Source

- PO-Auftrag aus der Cloud-Sitzung 2026-11-15 mit Screenshot (Workflow #12 „feature-12-profile“, Phase 7 im Chat, Plan komplett abgehakt).
- Issue #612 (Problem/Ziel), PR #611 (Teil 1 bereits eingereicht: Tests, `ship.py`, Befehlstexte, Changelog).

## Dependencies

- #490/#492 Issue-Kurztitel und Cache `.claude/issue_titles.json`, `short_title`
- #476/#478/#510 Plan-Pane, `render_plan`, Deploy-Marker `deploy_status`
- #550/#555/#551/#589 `end_state`, `queue_end_args`, `endstate`, `waiting`
- #537 `scripts/ship.py`
- #466 Herdr-Seitenleiste (`herdr_bridge.build_report`, `STEP_LABELS`)

## Scope

### Affected Files

| Datei | Änderung |
|-------|----------|
| `core/hooks/workflow.py` | `extract_issue_brief`, Brief-Cache `.claude/issue_briefs.json`, `fetch_issue_title` holt Titel+Text als JSON, `issue-brief`-CLI, `_with_issue_title`/`_plan_fetch_missing`/`start` holen die Kurzfassung nach; `render_plan`/`_plan_lines` mit Kopfblock, Umbruch und Schritt „Ausliefern“; `ship_status` in `end_state`/`_end_state_final`, `queue_end_args` liefert `auto_mode`; `_mark_ship_open` in `cmd_phase`/`cmd_complete`; `ship-status`-CLI mit Archiv-Rückfall; `endstate` gibt `SHIP_STATUS=` aus; Rücksprung verwirft `ship_*` |
| `core/hooks/herdr_bridge.py` | `build_report`: Phase 8 mit offener Auslieferung meldet `step=SHIP` statt zu leeren |
| `scripts/ship.py` | `ship_status()` meldet `running`/`done`/`failed` an `workflow.py ship-status` (fail-open) |
| `core/commands/60-validate.md`, `core/commands/00-intake.md`, `skills/*/SKILL.md` | Step 4 „Code fertig“ + Handmeldung, Abschluss liest `SHIP_STATUS=`; Intake Schritt 1c `issue-brief` |
| `tests/test_plan_kopf_und_auslieferung_612.py` | neue Tests (TDD RED) |
| `tests/test_plan_issue_titel_490.py` | Erwartung voller Titel statt sechs Wörter (`issue-title`, Cache) |
| `CHANGELOG.md`, `.claude-plugin/plugin.json`, `README.md`, `CLAUDE.md` | 4.13.0 |

### Estimated Changes

- `workflow.py`: ca. +260 Zeilen (Extraktion, Cache, CLI, Plan, Endzustand), `herdr_bridge.py`: ca. +10, `ship.py`: ca. +45, Tests: ca. +420.
- Keine Gate-Wirkung: alle neuen Felder (`ship_status`, `ship_at`, `ship_note`, `issue_brief`) sind reine Anzeige; kein Hook blockt daran.

## Implementation Details

**Issue-Kurzfassung.** `fetch_issue_title(issue)` ruft einmal `gh api repos/{owner}/{repo}/issues/<N>` (ohne `--jq`) auf und liest `title` und `body` aus dem JSON; eine reine Textantwort (alter Stub, Fehlerfall) gilt als Titel ohne Text. Gespeichert werden der volle Titel (`short_title(..., max_words=24)`) in `issue_titles.json` und `{"title","problem","goal","source":"issue","at"}` in `issue_briefs.json` (Schreiben unter derselben Sperre wie `_store_issue_title`; eine Fassung mit `source: manual` wird vom Issue nie überschrieben). `extract_issue_brief(title, body)` ist pure: entfernt HTML-Kommentare, Code-Blöcke (Fences), Bilder, Link-Syntax (Text bleibt), Inline-Code-Backticks, Fett-/Kursiv-Marker und Checkbox-Marker; zerlegt an Markdown-Überschriften, rein fetten Zeilen (`**Problem:**`) und `Schlüssel:`-Zeilen (höchstens drei Wörter vor dem Doppelpunkt, Schlüssel aus den Wortlisten) in Abschnitte; „Problem“ ist der erste Abschnitt, dessen Überschrift ein Wort aus `BRIEF_PROBLEM_WORDS` enthält (problem, bug, fehler, beschreibung, description, summary, zusammenfassung, kontext, context, motivation, hintergrund, background, ist-zustand, aktuell, symptom, situation, ausgangslage, current behavior, warum, why), „Ziel“ der erste mit einem Wort aus `BRIEF_GOAL_WORDS` (ziel, goal, soll, erwartet, expected, lösung, loesung, solution, vorschlag, proposal, wunsch, nutzen, outcome, ergebnis, akzeptanz, acceptance, definition of done, anforderung, requirement, job to be done); ohne Problem-Treffer gilt der Text vor der ersten Überschrift, ohne jede Überschrift der ganze Text als Problem, Ziel bleibt leer. Absätze werden mit Leerzeichen, Listenpunkte mit „; “ verbunden; jeder Wert endet nach spätestens `BRIEF_MAX_CHARS` = 260 Zeichen an einer Wortgrenze mit „…“.

**Plan-Kopf.** `_plan_lines(data, archived, deploy, width)`: `Workflow #N`, Name, Titel (bei `width` per `textwrap` auf höchstens `PLAN_TITLE_MAX_LINES` = 3 Zeilen), Leerzeile, dann `Problem: …` und `Ziel: …` (je höchstens `PLAN_BRIEF_MAX_LINES` = 5 Zeilen, letzte endet mit „…“) und eine Leerzeile — nur wenn `data["issue_brief"]` ein dict mit nicht leerem Text ist; sonst ist die Ausgabe unverändert. `_with_issue_title` setzt `issue_title` (jetzt bis 24 Wörter) und `issue_brief` aus den Caches; Watcher (`_plan_fetch_missing`) und `start` holen nach, wenn die Kurzfassung im Cache fehlt — auch bei vorhandenem altem Titel, höchstens einmal je Issue und Prozess. CLI `issue-brief <N> [--problem T --ziel T | --auto]` gibt `ISSUE=`, `TITLE=`, `PROBLEM=`, `ZIEL=`, `SOURCE=issue|manual|none` aus, Exit immer 0.

**Auslieferung.** Neue Konstanten `SHIP_STATUS_VALUES = (running, done, failed, skipped)`, `SHIP_PENDING_VALUES = (open, running, failed)`. `_mark_ship_open(data)` setzt `ship_status: open`, wenn weder `no_build_reason` noch `status: abandoned` vorliegt und noch kein Marker existiert; Aufruf in `cmd_phase` (Ziel `phase8_complete`) und `cmd_complete`. `_reset_approvals_on_backstep` verwirft `ship_status/ship_at/ship_note` vor Phase 8 wie `deploy_*`. Plan: vor Phase 8 (ohne Build nie) „○ Ausliefern“ als letzter Schritt vor Deploy, Schritt 8 heißt dann „Code fertig“; ab Phase 8 nur mit Marker (`"ship_status" in data`, sonst Altbestand unverändert): `▶ Ausliefern  (offen)`, `▶ Ausliefern  (läuft)`, `✔ Ausliefern`, `✘ Ausliefern  (fehlgeschlagen)`, `○ Ausliefern  (entfällt)`; die Deploy-Zeile ist erst „offen/läuft/…“, wenn die Auslieferung `done`/`skipped` ist (vorher `○ Deploy`). `end_state(..., auto_mode=False)`: in `_end_state_final` nach abgebrochen/ohne Build und vor dem Deploy — `open` → im Auto-Modus `⏳ Läuft noch: die Auslieferung von #N (Commit, PR, CI, Merge)`, sonst `❗ Du: Sichern freigeben — der Code von #N ist fertig, Commit und Auslieferung stehen noch aus`; `running` → `⏳ Läuft noch: die Auslieferung von #N (<ship_note>)`; `failed` → `❗ Du: /60-validate #N — Auslieferung fehlgeschlagen (<ship_note>), bitte neu anstoßen` (`cmd=/60-validate #N`, gewinnt wie ein fehlgeschlagener Deploy gegen `waiting_on`); `done` → `✅ Erledigt: #N ist fertig und ausgeliefert` bzw. die unveränderte Deploy-Logik; `skipped`/kein Marker → wie bisher. Ein nächstes Issue aus dem Auftrag (#551) ersetzt nur `done`. `queue_end_args` liefert zusätzlich `auto_mode` (`autonomy_mode() == "auto"`, fail-open False). CLI `ship-status <wert> [<N|name>] [--note T]`: ohne Nummer der aktive Workflow, ersatzweise der jüngste archivierte mit `ship_status` `open`/`running` (weil `complete` vor CI und Merge archiviert), sonst Exit 1 mit Hinweis; schreibt atomar, meldet an die Seitenleiste (fail-open), gibt `SHIP_STATUS=<wert> (<name>)` aus. `endstate` gibt nach `FOOTER=` die Zeile `SHIP_STATUS=<wert|none>` aus. `herdr_bridge.build_report`: in `phase8_complete` mit `ship_status` in `SHIP_PENDING_VALUES` wird `step=SHIP` gemeldet (Titel `#N 8/8 SHIP`), sonst wie bisher None (Clear). `scripts/ship.py`: `ship_status(value, note)` sucht `workflow.py` relativ zum Skript (`../hooks/` bzw. `../core/hooks/`) und ruft `ship-status` auf; Aufrufe: `running` vor dem Push und je PR-/CI-Stand, `done` nach erfolgreichem Merge, `failed` bei Push-Fehler, fehlendem PR, roter CI, Konflikt oder abgelehntem Merge; `--dry-run` meldet nichts.

## Expected Behavior

- Beim Start eines Workflows zu Issue #N erscheint im Plan-Kopf innerhalb weniger Sekunden der volle Issue-Titel und darunter „Problem: …“ / „Ziel: …“.
- Während `/60-validate` nach Phase 8 pusht, den PR anlegt und die CI abwartet, zeigt der Plan „✔ 8 Code fertig / ▶ Ausliefern  (läuft)“ und als Schlusszeile ⏳ mit dem aktuellen PR-/CI-Stand; die Chat-Fußzeile (`endstate`) und die Herdr-Seitenleiste zeigen denselben Zustand.
- Erst nach dem Merge (bzw. `ship-status done`) steht „✔ Ausliefern“ und „✅ Erledigt: #N ist fertig und ausgeliefert“; mit Deploy-Config folgt danach der Deploy-Schritt wie bisher.
- Rote CI oder ein Konflikt ergeben „✘ Ausliefern  (fehlgeschlagen)“ und `❗ Du: /60-validate #N — Auslieferung fehlgeschlagen (<Grund>) …`.

## Known Limitations

- Die Kurzfassung ist eine Heuristik auf dem Issue-Text: Issues ohne Überschriften liefern nur den ersten Absatz als „Problem“ und kein „Ziel“; `/00-intake` Schritt 1c schließt die Lücke per `issue-brief --problem/--ziel`.
- Ohne `gh` (Cloud-Sitzung, fehlende Anmeldung) bleibt der Kopf wie bisher; Fehlschläge stehen in `.claude/issue_titles.log`.
- `ship_status: open` nach einem Turn-Ende ohne Auslieferung zeigt im Auto-Modus ⏳, obwohl Claude nichts mehr tut; das ist bewusst gewählt (ein falsches ⏳ ist weniger schädlich als ein falsches ✅) und wird durch den Pflichtschritt in `/60-validate` vermieden.
- Wer Push/PR/Merge von Hand statt per `ship.py` ausführt, muss `ship-status` selbst melden; vergisst Claude das, bleibt der Plan bei ⏳/▶ statt ✅ — sichtbar, nicht still falsch.
- Archivierte Workflows aus älteren Fassungen haben keinen Marker und bleiben ✅ (kein Rückwirken).

## Definition of Done

- Alle AC-1 bis AC-15 durch `tests/test_plan_kopf_und_auslieferung_612.py` bzw. die angepassten Bestandstests belegt, gesamte Testsuite grün.
- `scripts/sync_skills.py --check` ohne Drift; `release_check.py --no-tests` grün (Versionen 4.13.0 in plugin.json, CHANGELOG, README, CLAUDE.md).
- `/60-validate` und `/00-intake` beschreiben `ship-status` und `issue-brief`.

## Acceptance Criteria

- **AC-1:** Given ein Issue-Text mit `## Problem`/`## Ziel` (deutsch), `### Motivation`/`### Expected behavior` (englisch), `**Problem:**`/`**Ziel:**` (fett inline), ohne Überschriften oder leer / When `extract_issue_brief(title, body)` läuft / Then liefert es `problem`/`goal` als Fließtext ohne Code-Blöcke, HTML-Kommentare, Fett-Marker, Link-Syntax und Checkboxen, Listenpunkte mit „; “ verbunden, ohne Überschriften den ersten Absatz als Problem, bei leerem Text beide leer, jeder Wert höchstens 260 Zeichen und dann mit „…“.
- **AC-2:** Given Workflow-Daten mit `issue_title` und `issue_brief` / When `render_plan` ohne Breite läuft / Then sind die Zeilen `Workflow #N`, Name, Titel, leer, `Problem: …`, `Ziel: …`, leer, Schritte; ohne Kurzfassung (fehlend, leer, kein dict) ist die Ausgabe byte-gleich wie bisher; mit Breite ist keine Zeile länger als die Breite, der Titel höchstens 3 Zeilen, jeder Absatz höchstens 5 Zeilen mit „…“ am Ende.
- **AC-3:** Given ein `gh`-Stub, der JSON mit `title` und `body` liefert / When `workflow.py issue-brief <N>` läuft / Then genau ein `gh api repos/{owner}/{repo}/issues/<N>`-Aufruf, `TITLE=` voller Titel, `PROBLEM=`/`ZIEL=` aus dem Text, `SOURCE=issue`, beide Caches geschrieben; `plan` zeigt Titel und beide Absätze ohne weiteren Aufruf; `issue-title` gibt den vollen Titel aus; `--problem/--ziel` setzt `SOURCE=manual`, das ein erneutes Holen nicht überschreibt; `--auto` liest wieder aus dem Issue; `gh` mit Exit 1 ergibt `SOURCE=none`, leere Felder, Exit 0, keinen Cache; reine Textantwort zählt als Titel; ein kaputter Cache bricht `plan` nicht.
- **AC-4:** Given ein alter Titel-Cache ohne Kurzfassung / When `plan --watch` drei Runden läuft / Then holt der Watcher genau einmal nach und zeigt danach Titel, Problem und Ziel.
- **AC-5:** Given ein Workflow vor Phase 8 (auch Fast Track) / When `render_plan` läuft / Then steht „○ Ausliefern“ als letzter Schritt vor einem etwaigen „○ Deploy“ und Schritt 8 heißt „8 Code fertig“.
- **AC-6:** Given Phase 8 oder archiviert mit `ship_status` open/running/failed/done/skipped (mit und ohne `auto_mode`) / When Plan und `end_state` laufen / Then zeigt der Plan `▶ Ausliefern  (offen)`, `▶ Ausliefern  (läuft)`, `✘ Ausliefern  (fehlgeschlagen)`, `✔ Ausliefern` bzw. `○ Ausliefern  (entfällt)` und die Schlusszeile ist identisch mit `end_state(...)["line"]`: open → ⏳ (auto) bzw. `❗ Du: Sichern freigeben — …` ohne Git-Wort, running → ⏳ mit `(<Note>)`, failed → `❗ Du: /60-validate #N — Auslieferung fehlgeschlagen (<Note>), bitte neu anstoßen` mit `cmd`, done → `✅ Erledigt: #N ist fertig und ausgeliefert. …`, skipped → `✅ Erledigt: #N ist fertig. …`.
- **AC-7:** Given Phase 8 oder archiviert ohne `ship_status` (Altbestand), abgebrochen oder ohne Build / When `render_plan` läuft / Then gibt es keinen Schritt „Ausliefern“, Schritt 8 heißt „8 Fertig“ und die Schlusszeile ist wie vor dieser Änderung.
- **AC-8:** Given Deploy konfiguriert / When die Auslieferung läuft / Then bleibt Deploy „○ Deploy“ und die Schlusszeile nennt die Auslieferung; nach `ship_status: done` greift die Deploy-Logik aus #510/#550 unverändert (offen/läuft/fehlgeschlagen/deployt), nach `skipped` ebenso.
- **AC-9:** Given `waiting_on` gesetzt / When `ship_status` open oder running / Then gewinnt `waiting_on`; bei failed nicht; ein nächstes Issue aus dem Auftrag erscheint erst nach `done`; `queue_end_args` liefert `auto_mode` (Default False).
- **AC-10:** Given ein Workflow / When `_mark_ship_open` bzw. `phase phase8_complete`/`complete` läuft / Then steht `ship_status: open`, außer bei `no_build_reason`/`abandoned` oder vorhandenem Marker; ein Rücksprung vor Phase 8 entfernt `ship_status`, `ship_at`, `ship_note`.
- **AC-11:** Given aktiver Workflow in Phase 8, danach nur ein archivierter mit offener Auslieferung / When `ship-status running --note T`, `ship-status done --note T` (ohne Nummer), `ship-status failed <N> --note T`, `ship-status skipped <N>` laufen / Then schreiben sie `ship_status`/`ship_at`/`ship_note` in die richtige Datei (aktiv, sonst jüngster archivierter mit open/running; andere Archive unberührt), ohne `--note` entfällt eine alte Note; `endstate` gibt `SHIP_STATUS=` aus und die passende Zeile; ohne Treffer Exit 1 mit Hinweis auf die Issue-Nummer; ungültiger Wert Exit 1 mit Usage.
- **AC-12:** Given `scripts/ship.py` / When `ship_status()` in einem Projekt mit archiviertem Workflow (open) läuft / Then steht der Wert samt Note im Archiv; `_workflow_py()` findet `core/hooks/workflow.py`; der Quelltext meldet an jedem Ausgang von `main()` `running`, `failed` oder `done`.
- **AC-13:** Given `herdr_bridge.build_report` / When Phase 8 ohne Marker / Then None (Clear wie bisher); mit `ship_status` open/running/failed `step=SHIP` und `state` passend zu `end_state` (du/läuft/du); mit done None.
- **AC-14:** Given `core/commands/60-validate.md`, `00-intake.md` und die generierten Skills / When gelesen / Then nennen sie `ship-status` (inkl. `skipped`), „Code fertig“ und `issue-brief`; `sync_skills.py --check` meldet keine Drift.
- **AC-15:** Given die Bestandstests (#490, #476, #478, #510, #550, #555, #466) / When die gesamte Suite läuft / Then sind alle grün; `test_plan_issue_titel_490.py` erwartet für `issue-title` und den Cache den vollen Titel.

## Test Plan

- `python3 -m pytest tests/test_plan_kopf_und_auslieferung_612.py -q` — AC-1 bis AC-14.
- `python3 -m pytest tests/test_plan_issue_titel_490.py tests/test_endzustand_550.py tests/test_plan_deploy_status_510.py tests/test_nacharbeit_555.py tests/test_herdr_plan_pane_476.py tests/test_herdr_sidebar_466.py -q` — AC-15 gezielt.
- `python3 -m pytest tests -q` — gesamte Suite (AC-15).
- `python3 scripts/sync_skills.py --check`, `python3 scripts/release_check.py --no-tests` — DoD.

### Automated Tests (TDD RED)

- Test: `tests/test_plan_kopf_und_auslieferung_612.py` — alle Funktionen (`extract_issue_brief`, `issue-brief`, `ship-status`, `_mark_ship_open`, `auto_mode`, `SHIP`-Step) fehlen vor der Umsetzung; RED-Artefakt: `docs/artifacts/612-red.log`.
- Test: `tests/test_plan_issue_titel_490.py::test_issue_title_cli_fetch_and_fail_open` — erwartet nach Anpassung den vollen Titel und ist vor der Umsetzung rot.

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Keine neue Architektur: `ship_status` folgt exakt dem Muster von `deploy_status` (#510), die Kurzfassung dem Titel-Cache (#490); alles bleibt reine Anzeige ohne Gate-Wirkung, dieselbe Quelle `end_state` für Chat, Plan und Seitenleiste (#550) bleibt die eine Entscheidungsstelle.

## Changelog

- 1.0 (2026-11-15): Erstfassung nach PO-Auftrag; Teil 1 (Tests, `ship.py`, Befehlstexte, Changelog) in PR #611 bereits eingereicht.
