# Context: feat-551-auftragsliste

## Request Summary

Issue #551: Ein Mehr-Issue-Auftrag des PO („Setze 545, 547 und 548 komplett autark um … melde dich nur, wenn ein Clear sinnvoll ist“) ging beim `/clear` verloren; nur #545 wurde fertig. Ursache: Der Auftrag steht nur im Chat; der Workflow-State kennt nur sein eigenes Issue; die Übergabe vor `/clear` nennt nur `/<phase> #<N>`; nach `finish` prüft nichts, ob Issues offen sind.
Gewünscht: Auftragsliste auf der Platte (z. B. `workflow.py queue add 547 548`, Datei unter `.claude/`), die `/clear` und Worktree-Wechsel überlebt; Übergabe-Prompt nennt Rest und Arbeitsweise (autark); nach Auslieferung nächstes Issue per `/00-intake`; leere Liste = Endzustand „Erledigt“ (#550); Banner zeigt offene Liste. Verwandt: #188.
PO-Vorgabe 2026-11-09: In einem autarken Auftrag dürfen Kontext-Schnitt (`CONTEXT_CUT=on`), `autoclear` und die Checkpoint-Blöcke die Kette NICHT anhalten; stattdessen `/compact`. Cloud-Sitzungen liegen nach `/clear` schon bei ~100k, die Schwelle steht dort dauerhaft auf `on`.

## Related Files

| File | Relevance |
|------|-----------|
| core/hooks/hook_utils.py:1521-1540 | `find_project_root()`: löst Worktree auf das Haupt-Repo auf (CLAUDE_PROJECT_DIR, sonst cwd). Alles unter `<root>/.claude/` liegt damit im geteilten Haupt-Repo und überlebt Worktree-Wechsel |
| core/hooks/hook_utils.py:1676-1695, 1735-1742 | `read_state_json`/`read_state_text` (dir_fd + O_NOFOLLOW, wirft `UnsafeStateError`) und `atomic_write_text(path, text, root=)` (#416/#422); Pflicht-Muster für neue Zustandsdateien |
| core/hooks/workflow.py:617-618, 643-645 | `_workflows_dir()` = `<root>/.claude/workflows`; `_issue_titles_file()` = `.claude/issue_titles.json` als Präzedenz einer geteilten Projekt-Datei neben `workflows/` |
| core/hooks/workflow.py:764-770, 794, 809 | `_workflow_file`, `_archive_dir`, `_atomic_write`, `_read_active` |
| core/hooks/workflow.py:4047-4089 | `COMMANDS`-Dict; neue Unterbefehle (z. B. `queue`) werden hier eingetragen, `batch` (3830) schlägt über dieses Dict nach |
| core/hooks/workflow.py:3153-3170, 3195-3215, 3217-3231 | Muster `cmd_deploy_status`, `cmd_waiting`, `cmd_endstate`: Usage auf stderr + Exit 1, Ausgabe `KEY=value`, Auflösung über `_status_target` (3175) |
| core/hooks/workflow.py:381-392, 395-462 | `END_STATE_RULE`, `_end_state_final/_open`, `end_state(data, archived, deploy, autonomous)` (#550): reine Funktion, "kein Config-Zugriff"; `waiting_on` hat Vorrang (459-461) |
| core/hooks/workflow.py:2913-2950 | `cmd_complete` (alias `finish`, 4067): Log-Pflicht, `_validate_transition`, `waiting_on` leeren; hier prüft heute nichts auf offene Issues |
| core/hooks/workflow.py:1085-1108, 1111-1125, 3621-3638 | `autonomy_mode()` (`trusted_config()`, Env `OPENSPEC_AUTONOMY`), `auto_ship_enabled()`, `cmd_autonomy` (`AUTONOMY=`) |
| core/hooks/workflow.py:3654-3708 | `cmd_autoclear` (`AUTO_CLEAR=`) und `_record_auto_clear_boundary` (`auto_clear_boundary` im State) |
| core/hooks/workflow.py:3791-3815 | `cmd_context`: `CONTEXT_TOKENS=`/`CONTEXT_CUT=` aus `.claude/context_usage/<session>.json`; `on` bei `enabled` und Tokens >= Schwelle |
| core/hooks/workflow.py:543-600 | `status_note(data)` (#325): UserPromptSubmit-Hinweis; None bei Phase 8/ohne Workflow; enthält `END_STATE_RULE` |
| core/hooks/phase_listener.py:428-445, 488, 686 | `_emit_status_note()` und `_finish(...)`: hier hängt der Hinweis an jede Nutzereingabe |
| core/hooks/hook_utils.py:2509-2527 | `context_budget_settings()`: nur Literal `false` schaltet ab, Schwelle int >= 1000 |
| core/hooks/hook_utils.py:2629-2665 | `context_bucket`, `context_cut_note` = Text „KONTEXT-SCHWELLE: … beende den Turn mit Checkpoint-Block und Du-Zeile, damit `/clear` gefahrlos ist. Im Auto-Modus den naechsten Skill NICHT selbst aufrufen“ |
| core/hooks/post_bash.py:150-183 | `_track_context`: misst, gibt `context_cut_note` als PostToolUse-`additionalContext` aus (je Stufe einmal) |
| core/hooks/herdr_bridge.py:524-587 | `maybe_auto_clear`: Stop-Hook, tippt `/clear` + `/<cmd> #N`; Bedingungen u. a. `MANUAL_COMMANDS` (Abschluss bleibt manuell), Grenz-Vermerk, Once-Lock |
| core/hooks/herdr_bridge.py:188-259, 306-343 | `build_report` (Seitenleiste, display-only), `_auto_clear_config`, `auto_clear_enabled` |
| core/hooks/session_banner.py:489-513 | `build_output`: `systemMessage` (sichtbar) + optional `additionalContext` (nur für Claude); Wartung entfällt bei `source == "compact"`; Kopf-Doku 20-33 |
| core/commands/10-context.md:137-167, 20-analyse.md:167-199, 30-write-spec.md:230-271, 40-tdd-red.md:166-185, 50-implement.md:379-398 | Checkpoint-Block („✅ **`/clear` ist jetzt gefahrlos**“), Abschnitt „Auto-Modus: Kette selbst fortsetzen (#472)“, „Vor dem Selbstaufruf zusätzlich `workflow.py context`“ (CONTEXT_CUT=on → Turn beenden), „Herdr-Auto-/clear (#489)“ (AUTO_CLEAR=on → Turn beenden). Quelle für `skills/*/SKILL.md` |
| core/commands/60-validate.md:413-427, 70-deploy.md:112-122 | „Abschluss: Endzustand melden (Pflicht, #550)“: `workflow.py endstate <N>`, `FOOTER=` wörtlich ausgeben; Ansatzpunkt für „nächstes Issue“ |
| core/commands/00-intake.md | Einstieg jeder Aufgabe, ruft `session_singleton_guard.py claim --issue N` (CLAUDE.md); Ansatz für „nächstes Issue starten“ |
| config.yaml:331-335, 342-367, 369-378 | `context_budget`, `herdr` (+`auto_clear`, `plan_pane`), `autonomy` |
| .gitignore:34-38, 62-70 | `.claude/workflows/`, `session-locks/`, `context_usage/`, `issue_titles.json`, `herdr_*` ignoriert; eine neue Auftragsdatei braucht einen eigenen Eintrag |

## Existing Patterns

- **Zustand im Haupt-Repo:** Workflow-JSONs `.claude/workflows/<name>.json`, Archiv `_archive/`; `find_project_root()` bildet Worktrees auf das Haupt-Repo ab. Projektweite Einzeldatei neben `workflows/`: `.claude/issue_titles.json` (+ `.lock`, `.log`), gitignored (.gitignore:67-69). Sitzungs-Register `.claude/session-locks/<id>.json`.
- **Sichere Datei-I/O:** `read_state_text` + `atomic_write_text(path, text, root)` statt `read_text`/`write_text` (Verweis-Schutz #416/#422). `issue_titles` nutzt noch `json.loads(read_text())` (workflow.py:651), ist also kein Vorbild für sicheres Lesen.
- **CLI-Unterbefehle:** `cmd_<name>(args)` + Eintrag in `COMMANDS`; Auskunftsbefehle geben `KEY=value`, enden mit Exit 0, wirken ohne aktiven Workflow (`autonomy`, `context`, `autoclear`); Zustandsbefehle schreiben per `_atomic_write` und geben eine Quittungszeile (`WAITING_ON=…`). Usage-Fehler: stderr + Exit 1.
- **Kill-Switch:** `context_budget.enabled` und `herdr.enabled`: nur Literal `false` schaltet ab (fail-open); `autonomy.mode`: nur Literal `auto` schaltet an (fail-closed), Benutzer-Env `OPENSPEC_AUTONOMY`/`OPENSPEC_HERDR_AUTO_CLEAR` als globaler Default, Projekteintrag hat Vorrang.
- **Befehlstexte steuern die Kette:** Auto-Modus ruft den Folge-Skill selbst auf, außer `CONTEXT_CUT=on` oder `AUTO_CLEAR=on` → Turn beenden mit Checkpoint + ❗Du-Zeile `/<next> #<N>`. Die Wortlaute stehen identisch in mehreren Befehlen und werden per `scripts/sync_skills.py` nach `skills/` gespiegelt.
- **Hinweise an Claude:** PostToolUse-`additionalContext` (post_bash), UserPromptSubmit-Text (`status_note`), SessionStart-`additionalContext` (Banner, #399: „Was der Start nicht beheben darf, geht nur als additionalContext an Claude“).
- **Endzustand (#550):** genau eine Zeile `✅ Erledigt` / `⏳ Läuft noch` / `❗ Du`; `END_DONE` heißt „… Du kannst /clear ausführen und das nächste Issue starten“ (Wortlaut in `END_STATE_RULE`, workflow.py:381-386); `endstate` ist die einzige Quelle für Chat, Plan, Seitenleiste.

## Dependencies

- **Upstream:** `find_project_root`, `atomic_write_text`/`read_state_text`, `trusted_config`/`load_config`, `workflow_issue_number(data)` (Issue-Nr. aus State bzw. Workflow-Name), `gh`-CLI nur im Befehlstext (Issue-Status), `session_singleton_guard.py claim`.
- **Downstream:** `end_state()` (Plan-Schluss, Seitenleiste `herdr_bridge.build_report`, `endstate`-CLI, `footer_gate`), `status_note`, `context_cut_note`, die fünf Phasen-Befehle + 60/70 (Texte), `session_banner.build_output`, `setup.py` (kopiert Hooks/Befehle in Konsumenten-Projekte, `.gitignore`-Einträge), `skills/` (Sync-Drift blockt Release), CHANGELOG `[Unreleased]`.

## Existing Specs

docs/specs/: `feat-kontext-haushalt.md` (context_budget, CONTEXT_CUT), `fix-489-kette-auto-clear.md`, `fix-495-autoclear-mechanisch.md`, `fix-497-autoclear-grenze-beim-phasenwechsel.md`, `fix-506-autoclear-ohne-herdr-status.md`, `feat-467-herdr-auto-clear.md`, `feat-480-auto-clear-global.md`, `feat-466-herdr-sidebar.md`, `feat-476-herdr-plan-pane.md`, `feat-469-autonomie-schalter.md`, `feat-481-autonomy-global.md`, `feat-470-spec-ampel.md`, `feat-525-auto-ship.md`, `feat-510-plan-deploy-status.md`, `fix-550-endzustand.md`, `fix-399-start-wartung.md` (Banner), `fix-499-befehlsform-context-titel.md`, `fix-234-footer-gate.md`. Eine Spec zu `status_note` (#325) und zur Übergabenotiz (#188) liegt nicht unter diesen Namen; #325 ist nur über `tests/test_status_note_325.py` belegt, #188 ist offenes Issue (nicht in docs/specs gefunden).

## Risks & Considerations

Tests, die Wortlaute pinnen und berührt würden: `tests/test_kontext_haushalt.py` (KONTEXT-SCHWELLE-Text, CONTEXT_CUT-Abschnitte), `tests/test_clear_checkpoint_blocks.py` (POSITIVE_MARKER „✅ **`/clear` ist jetzt gefahrlos**“), `tests/test_kette_auto_clear_489.py`, `tests/test_autoclear_boundary_495.py`, `tests/test_autoclear_transition_497.py`, `tests/test_autonomy_kette_472.py`, `tests/test_status_note_325.py`, `tests/test_endzustand_550.py`, `tests/test_herdr_sidebar_466.py`, `tests/test_herdr_plan_pane_476.py`, `tests/test_session_banner.py`, `tests/test_skills_sync.py` (Drift core/commands ↔ skills), `tests/test_skill_stop_instruction.py`.

Gestaltungsfragen (nicht entschieden):
1. **Ablageort/Format:** `.claude/order_queue.json` o. Ä. im Haupt-Repo (find_project_root); gitignore-Eintrag nötig; Format (Liste + Metadaten „autark“, Meldepflicht, Erstellzeit, Quelle); Lock bei parallelen Sitzungen (vgl. `issue_titles.json.lock`); Worktree-sicher, aber projektweit statt je Sitzung/Workflow.
2. **Autark-Modus vs. Kontext-Schnitt:** `cmd_context` meldet `CONTEXT_CUT=on` ohne Wissen um Autarkie; in Cloud-Sitzungen dauerhaft `on` (~100k Grundkontext). Wo wird „autark“ ausgewertet: in `cmd_context`/`cmd_autoclear` (Ausgabe `off` bei aktiver autarker Liste), in `context_cut_note`, oder in den Befehlstexten? Der PO will `/compact` statt `/clear` — wer löst es aus (Claude kann `/compact` nicht selbst tippen; Herdr-Bridge könnte es) und was bleibt von den Checkpoint-Blöcken/❗Du-Zeilen?
3. **Verhältnis zu `autonomy`:** Auftrag „autark“ ist pro Auftrag, `autonomy.mode` pro Projekt/Benutzer; gilt „autark“ als Aktivierung von Auto-Modus-Verhalten (Auto-Ship, Auto-Approve) oder nur als Ketten-Regel? Menschliche Pflichtstopps (AMBIGUOUS, zweites BROKEN, Override, Deploy, Stop-Lock; 10-context.md:169) müssen bleiben.
4. **Wiederaufnahme nach /clear:** Der Übergabe-Prompt entsteht in den Befehlstexten und `context_cut_note`/`maybe_auto_clear` (tippt nur `/<cmd> #N`). Zusätzlich lesbar machen über Banner (SessionStart, auch bei `source == "clear"`; bei `compact` entfällt die Wartung, Auftragsliste dort bewusst anders behandeln?) und/oder `status_note`.
5. **Abschluss:** Wo „nächstes Issue“ ansetzt: `cmd_complete` (Hinweis `QUEUE_NEXT=`), `end_state` (reine Funktion ohne Config/Dateizugriff, daher Liste als Parameter wie `deploy`), oder `endstate`-CLI/60-validate-Abschnitt. Leere Liste → bisheriger Endzustand ✅; nicht leere Liste → welche Art (⏳ „ich mache mit #N weiter“ vs. ❗)? `END_DONE`-Text „Du kannst /clear ausführen und das nächste Issue starten“ widerspricht einem autarken Auftrag. `herdr_bridge.MANUAL_COMMANDS` (Abschluss bleibt manuell) betrifft Auto-Clear am Ende.
6. **Konsistenz der Liste:** Issue schon geschlossen/Duplikat, Issue wird parallel von anderer Sitzung bearbeitet (Register), Entfernen beim Abschluss (`queue done`), Abbruch (`abandon`), Reihenfolge ändern, Anzeige (`queue show`), `batch`-Kompatibilität.
7. **Kill-Switch/Config:** neuer Schlüssel (z. B. `order_queue.enabled`, nur Literal `false` schaltet ab) in config.yaml und setup.py/gitignore für Konsumenten-Projekte; Fail-open, da Banner/Hinweise nie blockieren dürfen.
8. **Regelwerk:** CLAUDE.md-Aufblähung wird von `claude_md_protection.py` geprüft; neue Regeln eher in `docs/arbeitsweise.md` und Befehlstexten. Versionsnummer nicht anfassen, CHANGELOG unter `[Unreleased]`.

## Analysis

### Type
Feature (Bugfix-Charakter: Auftrag geht beim `/clear` verloren)

### Technical Approach (Tech-Lead-Entscheidung)

1. **Ablage:** eine Datei `.claude/auftrag.json` im Haupt-Repo (`find_project_root()`, damit worktree-übergreifend), gitignored, gelesen per `read_state_text`, geschrieben per `atomic_write_text`. Inhalt: `issues` (geordnete Liste `{"n": int, "status": "open"|"done"}`), `autark` (bool), `note` (Wortlaut des Auftrags, optional), `created`, `updated`. Genau ein Auftrag je Projekt; kein Lock (eine Sitzung führt den Auftrag; Schreiben atomar).
2. **CLI `workflow.py queue`:** `queue add <N…> [--autark] [--note "<text>"]`, `queue` (bzw. `queue list`: `QUEUE=<offene Nummern>`, `AUTARK=on|off`, `NEXT=<N>|none`), `queue done <N>`, `queue clear`. Batch-fähig.
3. **Abhaken automatisch:** `cmd_complete` markiert die Issue-Nummer des abgeschlossenen Workflows im Auftrag als `done` (fail-open).
4. **Endzustand (#550):** `end_state(..., queue_next=None, autark=False)` bleibt rein; die Aufrufer (`endstate`, Plan, Seitenleiste) lesen den Auftrag. Fall „Workflow erledigt“: Auftrag leer → ✅ wie bisher. Auftrag offen + autark → ⏳ „Claude startet #M aus deinem Auftrag“. Auftrag offen + nicht autark → ❗ `/00-intake #M — nächstes Issue aus deinem Auftrag`.
5. **Kette bleibt autark (PO-Vorgabe 2026-11-09):** Ist ein autarker Auftrag offen, melden `workflow.py context` `CONTEXT_CUT=off` (Grund `AUTARK`) und `workflow.py autoclear` `AUTO_CLEAR=off`; der Kontext-Schwellen-Hinweis von `post_bash` sagt dann „weiterarbeiten, Claude Code komprimiert automatisch (/compact)“ statt „Turn beenden“. Claude kann `/compact` nicht selbst auslösen; die automatische Komprimierung von Claude Code ist der Ersatz.
6. **Wiederaufnahme nach `/clear` oder neuer Sitzung:** `status_note` (Hinweis an jede Nutzereingabe) und Sitzungs-Banner (`additionalContext`) nennen den offenen Auftrag mit nächstem Issue und Arbeitsweise; `workflow.py queue` liefert die fertige Prompt-Zeile `PROMPT=` zum Weitermachen.
7. **Befehlstexte:** `60-validate.md`/`70-deploy.md` Abschluss: nach `endstate` bei `ENDSTATE=waiting` mit Auftrag → `/00-intake #M` selbst aufrufen (Kette). `00-intake.md`: Mehr-Issue-Auftrag des PO zuerst per `queue add … [--autark]` sichern.
8. **Kill-Switch:** `config.yaml` → `auftrag.enabled` (nur Literal `false` schaltet ab; fail-open wie `context_budget`).

Nicht Teil: Seitenleisten-Anzeige der Liste (herdr), Kontext-Schwelle relativ zum Grundkontext (eigenes Issue), #188 Übergabenotiz.

### Affected Files (with changes)
| File | Change Type | Description |
|------|-------------|-------------|
| core/hooks/workflow.py | MODIFY | Auftrag lesen/schreiben, `cmd_queue`, `end_state`-Parameter, `cmd_complete` hakt ab, `context`/`autoclear` autark-bewusst, `status_note` |
| core/hooks/hook_utils.py | MODIFY | `context_cut_note` autark-Variante |
| core/hooks/post_bash.py | MODIFY | ggf. Übergabe der autark-Lage an `context_cut_note` |
| core/hooks/session_banner.py | MODIFY | offener Auftrag im `additionalContext` |
| core/commands/00-intake.md, 60-validate.md, 70-deploy.md | MODIFY | Auftrag sichern bzw. Kette fortsetzen |
| .gitignore | MODIFY | `.claude/auftrag.json` |
| config.yaml | MODIFY | `auftrag.enabled` |
| tests/test_auftrag_551.py | CREATE | Regressionstests |
| skills/* | REGENERATE | `sync_skills.py` |
| CHANGELOG.md | MODIFY | [Unreleased] |

### Scope Assessment
- Files: ~10 (+ regenerierte Skills)
- Estimated LoC: +250/-20 Produktion, +250 Test
- Risk Level: MEDIUM (Kern-Hook, aber additive Logik mit Kill-Switch; ohne Auftrag unverändertes Verhalten)

### Open Questions
- keine Produktfrage offen: Verhalten „autark“ hat der PO am 2026-11-09 festgelegt (kein Halt für `/clear`, `/compact` statt `/clear`).
