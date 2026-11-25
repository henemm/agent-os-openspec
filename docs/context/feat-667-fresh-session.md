# Context: feat-667-fresh-session

## Request Summary
Issue #667 (Epic #649, PO-Entscheidung 2026-11-25 „Frischer Start je Aufgabe“): Ist ein Issue eines autarken
Auftrags (`workflow.py queue`) ausgeliefert, startet das nächste nicht mehr per Selbstaufruf `/00-intake #M` im
wachsenden Kontext der Hauptsitzung, sondern in einer neuen, frischen Sitzung. Cloud: über die Sitzungs-Werkzeuge
(`create_session` der claude-code-remote-Werkzeuge). Lokal: Herdr startet eine neue Claude-Sitzung in einem neuen
Pane (startet, tippt nicht). Auftrag und Fortschritt liegen auf der Platte bzw. im Startauftrag der neuen Sitzung.

## Related Files
| File | Relevance |
|------|-----------|
| core/hooks/workflow.py:5500-5640 `QUEUE_USAGE`, `_print_queue`, `_queue_add`, `cmd_queue` | Auftragsliste; `PROMPT=/00-intake #<NEXT>` + `QUEUE_AUTARK_SUFFIX` (Text „Auftrag aus .claude/auftrag.json weiter abarbeiten“) |
| core/hooks/workflow.py:531-547 `end_state` (Zweig Auftrag) | ⏳ „Claude startet #M aus deinem Auftrag“ bei autark+auto, ❗ `/00-intake #M` sonst |
| core/hooks/workflow.py:643 `queue_end_args` | `queue_next` = erste offene Nummer ≠ eigener Workflow |
| core/hooks/hook_utils.py:2868-3140 `auftrag_owner_key`, `auftrag_settings`, `auftrag_path`, `read_auftrag`, `write_auftrag`, `auftrag_open_issues` | Auftrag je Sitzung (#613): `.claude/auftrag/<key>.json`, Kennung herdr-Workspace bzw. Sitzungs-Id |
| core/hooks/herdr_bridge.py:82 `_binary`, :92 `_enabled`, :106 `_pane`, :466 `_pp_call`, :796 `pane split`, :833 `pane run` | Herdr-Aufrufe; Plan-Pane zeigt das Muster split + run eines Befehls im neuen Pane |
| core/commands/60-validate.md:464-470, 70-deploy.md:146-152 | „Kette bei offenem Auftrag“: heute Selbstaufruf `/00-intake #M` |
| core/commands/80-workflow.md:51-65 | Doku Auftragsliste |
| skills/*/SKILL.md | Generat (`scripts/sync_skills.py`) |

## Existing Patterns
- Auskunfts-CLI mit `KEY=value`-Zeilen, Exit 0, fail-open (`queue`, `autonomy`, `context`, `endstate`).
- Herdr-Aufrufe fail-open über `_pp_call` mit Timeout, Kill-Switch `herdr.enabled`.
- Cloud-Erkennung: Env `CLAUDE_CODE_REMOTE=true` (gesetzt in jeder Cloud-Sitzung).
- Präzedenz Cloud: Diese Sitzung wurde von der Vorgängersitzung per `create_session` mit einem Startauftrag
  gestartet, der den Auftrag samt `queue add 667 --autark` enthielt — ein Cloud-Container ist frisch, die
  Auftragsdatei der alten Sitzung existiert dort nicht. Der Startauftrag muss also den Rest-Auftrag tragen.

## Dependencies
- Upstream: #551 (Auftrag), #613 (Auftrag je Sitzung), #662/#663 (Kette flach, kein Auto-/clear), Herdr-Binary lokal.
- Downstream: 60-validate/70-deploy (Kette), endstate-Zeile bleibt unverändert (footer_gate prüft „aus deinem Auftrag“).

## Existing Specs
- docs/specs/feat-551-auftragsliste.md, docs/specs/feat-662-kette-flach.md, docs/specs/chore-663-rueckbau-autoclear.md

## Risks & Considerations
- Lokal kein frischer Container: neue Sitzung im selben Haupt-Repo; Auftragsdatei je Sitzung (#613) gehört der
  alten Kennung → die neue Sitzung legt den Auftrag aus dem Startauftrag neu an (gleich wie Cloud).
- Herdr-Workspace-Kennung (`herdr-<workspace>`) ist in neuer Pane gleich → Auftrag wäre schon da; `queue add`
  ist idempotent (Doppelte ignoriert) → unschädlich.
- Doppelstart vermeiden: Übergabe im Auftrag vermerken; zweiter Start für dieselbe Nummer → `STARTED=already`.
- Ohne Cloud und ohne Herdr bleibt der alte Selbstaufruf (Fallback `inline`), damit nichts bricht.
- Lokaler Nachweis (DoD „lokal belegt“) ist aus der Cloud nicht ausführbar → am Epic festhalten.

## Analysis

### Type
Feature

### Affected Files (with changes)
| File | Change Type | Description |
|------|-------------|-------------|
| core/hooks/workflow.py | MODIFY | neuer Befehl `handoff [--start]` (Übergabe an frische Sitzung), Usage/Docstring |
| core/hooks/hook_utils.py | MODIFY | `_normalize_auftrag` behält Feld `handoff` (Nummer, Weg, Zeit) |
| core/hooks/herdr_bridge.py | MODIFY | `start_session(prompt, cwd)`: `pane split` + `pane run` mit `claude <prompt>` (fail-open) |
| core/commands/60-validate.md, 70-deploy.md | MODIFY | Kette: statt Selbstaufruf `workflow.py handoff` → cloud: `create_session`; herdr: `handoff --start`; inline: alter Selbstaufruf |
| core/commands/80-workflow.md | MODIFY | Doku `handoff` |
| skills/60-validate, 70-deploy?, 80-workflow SKILL.md | REGEN | `scripts/sync_skills.py` |
| tests/test_handoff_667.py | CREATE | Tests für Weg-Erkennung, Startauftrag, Idempotenz, Herdr-Start (Fake-Binary), Fallback |
| CHANGELOG.md, .claude-plugin/plugin.json, CLAUDE.md-Version | MODIFY | 4.25.0 |

### Scope Assessment
- Files: ~9
- Estimated LoC: +350/-10
- Risk Level: HIGH (Hook-/CLI-Code, Kettenverhalten jedes autarken Auftrags)

### Technical Approach
`workflow.py handoff` ist eine Auskunft mit optionaler Aktion. Sie liest den Auftrag der Sitzung und entscheidet den
Weg: kein autarker Auftrag oder kein offenes nächstes Issue → `HANDOFF=none`; `CLAUDE_CODE_REMOTE=true` → `cloud`;
Herdr-Pane aktiv (`herdr_bridge._pane()`) und `claude` auf PATH → `herdr`; sonst `inline` (bisheriger Selbstaufruf,
nichts bricht). Ausgabe `HANDOFF=`, `NEXT=`, `REPO_URL=` (nur cloud), `STARTED=` (nur mit `--start`) und der
Startauftrag zwischen `PROMPT_BEGIN`/`PROMPT_END`. Der Startauftrag ist eigenständig: Issue, `/00-intake #M`,
Wiederherstellung des Rest-Auftrags per `queue add <offene> --autark [--note] [--spur]`, Halt nur an PO-Punkten,
Hinweis auf skills/00-intake/SKILL.md ohne Plugin. Die Übergabe wird im Auftrag vermerkt (`handoff`); ein zweites
`--start` für dieselbe Nummer startet nichts (`STARTED=already`). Cloud kann Python nicht selbst starten
(MCP-Werkzeug) → der Befehlstext weist Claude an, `create_session` mit dem Startauftrag und `REPO_URL` aufzurufen
und danach `handoff --mark cloud` zu setzen. Die endstate-Zeile bleibt unverändert.
Alternative verworfen: Herdr tippt `/clear` + Befehl (#663 zurückgebaut, fehleranfällig).

### Dependencies
#551/#613 Auftrag, Herdr-CLI (`pane split`, `pane run`), Cloud-Werkzeug `create_session`.

### Open Questions
- [x] Altes Herdr-Pane schließen? Nein: lieber ein überzähliges Pane stehen lassen (Grundsatz Plan-Pane, #496); Known Limitation.
- [ ] Lokaler End-to-End-Beleg mit Herdr: aus der Cloud nicht ausführbar → am Epic #649 festhalten.
