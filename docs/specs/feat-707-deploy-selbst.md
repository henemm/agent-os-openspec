---
entity_id: feat-707-deploy-selbst
type: feature
created: 2026-11-28
updated: 2026-11-28
status: draft
version: "1.0"
workflow: fix-707-deploy-selbst
tags: [deploy, autonomy, skill-gate, worktree, po-no-git]
---

# /70-deploy bei deploy.autonomous für Claude aufrufbar (Issue #707)

## Approval

- [ ] Approved

## Purpose

Mit `deploy.autonomous: true` soll Claude `/70-deploy` nach `/60-validate` selbst aufrufen und der Workflow mit „✅ … fertig und deployt“ enden. Heute verhindert `disable-model-invocation: true` jeden Skill-Aufruf durch Claude, deshalb bleibt am Ende ein „❗ Du“ stehen. Eine technische Sperre (PreToolUse-Hook auf das Skill-Tool) hält den Befehl ohne `autonomous` weiterhin beim PO. Zusätzlich liest `deploy_autonomous()` in einer Worktree-Sitzung den gemergten Stand der Config, damit ein bereits gemergtes `autonomous: true` sofort wirkt.

## Source

- **File:** `core/hooks/skill_gate.py` (neu), `core/hooks/workflow.py`, `core/hooks/alias_sync.py`, `core/commands/70-deploy.md`, `core/commands/60-validate.md`
- **Identifier:** `skill_gate.main` (neu), `workflow.deploy_autonomous` (Worktree-Regel), `alias_sync.embeds_full_skill` (feste Liste)

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `workflow.deploy_autonomous()` | function | einzige Quelle für den Schalter; Sperre und Endzustand nutzen dieselbe Funktion |
| `workflow._deploy_block()` / `config_loader.load_config` | function | Deploy-Config (#81, #478), bleibt unverändert |
| `config_loader.find_project_root()` | function | Worktree → Haupt-Ordner (#153), bleibt unverändert |
| `hook_utils._observable_base` (Muster) | function | Basiszweig über `refs/remotes/origin/HEAD`, kein geratener Name |
| `secret_egress_guard._read_payload` (Muster) | function | Payload aus stdin-JSON mit Env-Fallback `CLAUDE_TOOL_INPUT`/`CLAUDE_TOOL_NAME` |
| `alias_sync.embeds_full_skill`, `alias_content` | function | Vollkopie vs. Text-Redirect; 70-deploy bleibt Vollkopie |
| `scripts/sync_skills.py` | script | erzeugt `skills/*/SKILL.md` aus `core/commands` |
| `scripts/sync_cloud_hooks.py` | script | erzeugt den Cloud-/Consumer-Hookblock in `.claude/settings.json` |
| `workflow._end_state_final` (#550) | function | ✅-Endzustand bei `deploy_status=done`, Regressionsbezug |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| core/hooks/skill_gate.py | CREATE | PreToolUse-Hook, Matcher `Skill`; sperrt `70-deploy` ohne `deploy.autonomous: true` (fail-closed) |
| hooks/hooks.json | MODIFY | Registrierung `skill_gate.py` unter PreToolUse-Matcher `Skill` |
| .claude/settings.json | MODIFY | generiert per `python3 scripts/sync_cloud_hooks.py` |
| core/commands/70-deploy.md | MODIFY | neuer Step 0 (Selbstaufruf nur bei `autonomous: true`) |
| skills/70-deploy/SKILL.md | MODIFY | generiert; `disable-model-invocation: false` |
| .claude/commands/70-deploy.md | MODIFY | Alias bleibt Vollkopie, neu erzeugt per `setup.py --refresh-aliases` |
| core/hooks/alias_sync.py | MODIFY | 70-deploy steht in expliziter Liste der Vollkopie-Aliase |
| core/hooks/workflow.py | MODIFY | `deploy_autonomous()` mit Worktree-Regel (gemergter Stand) |
| core/commands/60-validate.md | MODIFY | „Autonomen Weiterlauf prüfen“: Skill `70-deploy` mit `#N` selbst aufrufen |
| skills/60-validate/SKILL.md | MODIFY | generiert per `python3 scripts/sync_skills.py` |
| docs/befehle/70-deploy.md | MODIFY | Selbstaufruf bei `autonomous`, Sperre, Worktree-Regel |
| docs/architektur.md | MODIFY | Hook-Liste um `Skill`-Matcher/`skill_gate.py` ergänzt |
| CHANGELOG.md | MODIFY | Eintrag zu #707 |
| .claude-plugin/plugin.json | MODIFY | Version 4.29.0 |
| tests/test_deploy_selbst_707.py | CREATE | Tests zu allen AC |

### Estimated Changes

- Files: 2 neu, 13 geändert (davon 3 generiert)
- LoC: +150 Code/Hook, +40 Command-/Doku-Text, +260 Test
- Risk Level: HIGH (Hook-/Gate-Code, Deploy-Berechtigung)

## Implementation Details

Entschieden ist Variante V1 (Skill-Sperre per Hook), siehe `docs/context/fix-707-deploy-selbst.md`, Abschnitt Analysis.

**`skill_gate.py`:** Liest den Payload aus stdin-JSON, Fallback auf `CLAUDE_TOOL_INPUT`/`CLAUDE_TOOL_NAME` (wie `secret_egress_guard._read_payload`). Der Skill-Name steht in `tool_input["skill"]`; normalisiert wird durch Entfernen eines führenden `/` und des Präfixes `agent-os-openspec:`. Ist das Ergebnis `70-deploy`, wird `workflow.deploy_autonomous()` gefragt; nur ein echtes `True` (bool) erlaubt (Exit 0). Fehlt der Schlüssel, ist er `false`, der String `"true"` oder die Config unlesbar, wird mit Exit 2 blockiert (fail-closed). Meldung auf stderr, deutsch: Deploy bleibt beim PO, der PO tippt `/70-deploy #N`. Alle anderen Skills und alle Nicht-Skill-Tools: Exit 0; ein kaputter Payload für einen Nicht-70-deploy-Fall ergibt ebenfalls Exit 0.

**Alias:** Der PO-getippte `/70-deploy` umgeht laut Claude-Code-Doku PreToolUse. Damit er nie über das Skill-Tool läuft, bleibt `.claude/commands/70-deploy.md` eine Vollkopie. `alias_sync` führt dafür eine feste Liste Vollkopie-Skills; `embeds_full_skill` liefert für 70-deploy wahr, für alle anderen Skills bleibt die bisherige Semantik (`disable-model-invocation: true`).

**`deploy_autonomous()` Worktree-Regel:** In einer Worktree-Sitzung gilt der gemergte Stand. Ist die Config-Datei im Haupt-Ordner gegenüber dessen HEAD unverändert, wird der Wert aus `git show <Ziel von refs/remotes/origin/HEAD>:<relpfad>` gelesen (Basis via `git symbolic-ref refs/remotes/origin/HEAD`, kein geratener Name). Lokale Änderungen der Datei im Haupt-Ordner, fehlendes `origin/HEAD` oder ein Git-Fehler führen zum bisherigen Wert aus dem Haupt-Ordner. Nicht-Worktree-Sitzungen bleiben unverändert. Ein Widerruf auf origin gewinnt (origin `false`, Haupt-Ordner sauber mit `true` → `false`). Betroffen ist nur dieser eine Schalter, nicht die Config insgesamt; #153 bleibt gewahrt, weil ein Zweig sich nichts selbst erlauben kann.

**Command-Texte:** `70-deploy.md` Step 0: Hat Claude den Befehl selbst aufgerufen (nicht vom PO getippt), prüft es `workflow.py deploy-config` auf `autonomous: true`, sonst STOP mit Ausgabe „❗ Du: `/70-deploy #N`“ (Rückfall, falls der Hook nicht registriert ist). `60-validate.md`: „Autonomen Weiterlauf prüfen“ ruft den Skill `70-deploy` mit `#N` selbst auf; blockiert der Hook, endet die Antwort mit der ❗-Du-Zeile.

**Autarkie:** Kein Schritt verlangt ein „override“ durch den PO; die wirksame Gate-Config `openspec.yaml` wird nicht geändert.

## Expected Behavior

- **Input:** Skill-Tool-Aufruf `{"skill": "70-deploy", "args": "#N"}` (auch `agent-os-openspec:70-deploy`, `/70-deploy`).
- **Output:** Exit 0 bei `deploy.autonomous: true`, sonst Exit 2 mit deutscher Meldung.
- **Side effects:** Keine Schreibzugriffe; lesende git-Aufrufe in der Worktree-Regel.

## Known Limitations

- Fehlt die Hook-Registrierung im Zielprojekt, greift nur die Step-0-Textregel.
- Die Worktree-Regel braucht ein vorhandenes `refs/remotes/origin/HEAD`; sonst gilt der Haupt-Ordner.
- Der PO-Aufruf `/70-deploy` wird nicht geprüft (Claude Code umgeht PreToolUse für getippte Befehle); das ist gewollt.

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] Mit `deploy.autonomous: true` ruft Claude `/70-deploy` nach `/60-validate` selbst auf und der Workflow endet mit „✅ … deployt“; ohne `autonomous` bleibt alles wie bisher
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf grün, `release_check.py` und `sync_cloud_hooks.py --check` grün)

## Acceptance Criteria

- **AC-1:** Given `deploy.autonomous` ist nicht `true` (fehlt, `false`, String `"true"` oder Config unlesbar) / When das Skill-Tool mit `70-deploy` (auch `agent-os-openspec:70-deploy` und `/70-deploy`) aufgerufen wird / Then beendet `skill_gate` mit Exit 2 und einer deutschen Meldung, dass Deploy beim PO bleibt (`/70-deploy #N` tippt der PO)
  - Test: tests/test_deploy_selbst_707.py::test_blocks_70_deploy_without_autonomous (parametrisiert: fehlt, false, "true", unlesbar, Namensvarianten)
- **AC-2:** Given `deploy.autonomous: true` (bool) / When das Skill-Tool mit `70-deploy` aufgerufen wird / Then Exit 0
  - Test: tests/test_deploy_selbst_707.py::test_allows_70_deploy_with_autonomous_true
- **AC-3:** Given beliebige andere Skills oder Nicht-Skill-Tools, auch mit kaputtem Payload bei einem Nicht-70-deploy-Fall / When `skill_gate` läuft / Then Exit 0; der Payload kommt aus stdin-JSON mit Env-Fallback `CLAUDE_TOOL_INPUT`/`CLAUDE_TOOL_NAME`, der Skill-Name aus `tool_input["skill"]`
  - Test: tests/test_deploy_selbst_707.py::test_other_skills_and_tools_always_allowed, ::test_malformed_payload_non_deploy_allowed, ::test_payload_env_fallback
- **AC-4:** Given der Generator-Lauf / When `skills/70-deploy/SKILL.md` und die Aliase geprüft werden / Then steht dort `disable-model-invocation: false`, `alias_sync` hält 70-deploy per expliziter Liste als Vollkopie (`.claude/commands/70-deploy.md` ist eine volle Kopie, committet und aktuell, keine veralteten Aliase), und `embeds_full_skill` verhält sich für alle anderen Skills unverändert
  - Test: tests/test_deploy_selbst_707.py::test_skill_flag_false_and_alias_full_copy, ::test_embeds_full_skill_other_skills_unchanged, ::test_committed_alias_not_stale
- **AC-5:** Given `hooks/hooks.json` / When die Registrierung geprüft wird / Then steht `skill_gate.py` unter PreToolUse-Matcher `Skill`, der Cloud-Hookblock in `.claude/settings.json` ist per `scripts/sync_cloud_hooks.py` erzeugt (`--check` besteht) und der Consumer-Hookblock spiegelt ihn
  - Test: tests/test_deploy_selbst_707.py::test_hooks_json_registers_skill_gate, ::test_cloud_hooks_in_sync, ::test_consumer_hooks_mirror
- **AC-6:** Given eine Worktree-Sitzung / When `deploy_autonomous()` liest / Then gilt: Haupt-Ordner-Config unverändert gegenüber dessen HEAD → Wert aus `git show <origin/HEAD-Ziel>:<relpfad>` (Basis via `git symbolic-ref refs/remotes/origin/HEAD`); lokale Änderung der Datei im Haupt-Ordner, fehlendes `origin/HEAD` oder Git-Fehler → Wert des Haupt-Ordners wie bisher; Nicht-Worktree-Sitzung unverändert; origin `false` bei sauberem Haupt-Ordner `true` → `false`; `skill_gate` nutzt dieselbe Funktion
  - Test: tests/test_deploy_selbst_707.py::test_worktree_reads_origin_value, ::test_worktree_dirty_main_uses_main_value, ::test_worktree_no_origin_head_falls_back, ::test_worktree_git_error_falls_back, ::test_non_worktree_unchanged, ::test_origin_revocation_wins, ::test_skill_gate_uses_deploy_autonomous
- **AC-7:** Given die Command-Texte / When `core/commands/70-deploy.md` und `60-validate.md` (samt generiertem Skill) gelesen werden / Then enthält 70-deploy einen Step 0 (bei Selbstaufruf `workflow.py deploy-config` auf `autonomous: true` prüfen, sonst STOP mit „❗ Du: `/70-deploy #N`“) und 60-validate „Autonomen Weiterlauf prüfen“ ruft den Skill `70-deploy` mit `#N` selbst auf und endet bei Hook-Sperre mit der ❗-Du-Zeile
  - Test: tests/test_deploy_selbst_707.py::test_70_deploy_step0_text, ::test_60_validate_self_call_text
- **AC-8:** Given `deploy.autonomous: true` und `deploy_status: done` / When der Endzustand berechnet wird / Then lautet der FOOTER „✅ Erledigt: #N ist fertig und deployt…“ (bestehendes Verhalten, Regression); ohne `autonomous` bleibt `ENDSTATE=you` mit `/70-deploy #N`
  - Test: tests/test_deploy_selbst_707.py::test_endstate_deployed_with_autonomous, ::test_endstate_you_without_autonomous

## Test Plan

Automatische Tests (jeweils an eine AC oben gebunden):
- `pytest tests/test_deploy_selbst_707.py`
- Regression: `tests/test_endzustand_550.py`, `tests/test_setup_command_aliases.py`, `tests/test_alias_marker_position_251.py`, `tests/test_fix_schritte_ueberspringen.py` (`REDIRECT_COUNT = 11`), `tests/test_repo_own_aliases_147.py`, `tests/test_cloud_hooks_520.py`, `tests/test_cloud_gates_522.py`, `tests/test_gate_event_log_181.py`
- Gates: `python3 scripts/sync_cloud_hooks.py --check`, `python3 scripts/sync_skills.py` (kein Drift), `release_check.py`

## Risks

- `disable-model-invocation: false` ohne wirksame Sperre ließe Claude auch ohne `autonomous` deployen; deshalb fail-closed und Step-0-Rückfall.
- Ein Text-Redirect statt Vollkopie würde den PO-Aufruf über das Skill-Tool leiten und fälschlich sperren; der Alias bleibt Vollkopie.
- Das `~`-Alias schattet das Projekt-Alias (#87); config-abhängige Alias-Inhalte wären unzuverlässig, deshalb Entscheidung in der Laufzeit-Sperre.
- Ein Worktree darf sich die Erlaubnis nicht im eigenen Zweig geben (#153); nur gemergter Stand zählt.
- Falscher Basiszweig oder Git-Fehler: Rückfall auf den Haupt-Ordner-Wert, nie auf „erlaubt“ aus unsicherer Quelle.

## Out of Scope

- Keine Änderung daran, wie der PO deployt (`/70-deploy #N` getippt, wie bisher).
- Keine allgemeine Änderung an `config_loader` oder an #153; die Worktree-Regel gilt nur für `deploy.autonomous`.
- V2 (Alias je Projekt) verworfen: brüchig, `~`-Alias schattet das Projekt-Alias, wirkt erst nach Refresh und Commit.
- V3 (Datei lesen und ausführen) verworfen: nur Textregel, keine technische Sperre.
- Keine Änderung der wirksamen Gate-Config `openspec.yaml`.

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Erweiterung der bestehenden Gate-Muster (PreToolUse-Hook, fail-closed) um einen weiteren Matcher; keine neue Architekturrichtung. Die Variantenwahl V1 ist im Kontextdokument begründet.

## Changelog

- 2026-11-28: Initial spec created
