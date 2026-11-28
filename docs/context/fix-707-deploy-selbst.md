# Context: fix-707-deploy-selbst (Issue #707)

## Request Summary

Bei `deploy.autonomous: true` soll Claude `/70-deploy` nach `/60-validate` selbst aufrufen
können; der Workflow endet dann mit `✅ … fertig und deployt`. Heute blockiert
`disable-model-invocation: true` (Skill und Vollkopie-Alias) jeden Skill-Aufruf durch Claude.
Ohne `autonomous` bleibt der Befehl dem PO vorbehalten.
Zweiter Befund: in einer Worktree-Sitzung liest die Config den Haupt-Ordner; ein im Zweig
bereits gemergtes `deploy.autonomous: true` wirkt erst, wenn der Haupt-Ordner nachgezogen ist.

## Related Files

- `core/commands/70-deploy.md` (Quelle) → `skills/70-deploy/SKILL.md` (Generat, `scripts/sync_skills.py`),
  `.claude/commands/70-deploy.md` (Alias, Vollkopie wegen `disable-model-invocation: true`).
- `core/hooks/alias_sync.py:43` `embeds_full_skill()` — Vollkopie genau bei `disable-model-invocation: true`;
  `alias_content()` erzeugt sonst einen Text-Redirect (`/agent-os-openspec:<name>`), den Claude per Skill-Tool auflöst.
- `setup.py:1556` `generate_command_aliases`, `refresh_command_aliases`; `session_banner.py:153` frischt `~`-Aliase beim Start auf.
- `core/commands/60-validate.md:112-116` „Autonomen Weiterlauf prüfen“: bei `deploy.autonomous` `/70-deploy` selbst aufrufen.
- `core/hooks/workflow.py:4903` `deploy_autonomous()`, `:4638` `_deploy_block()` (über `config_loader.load_config`),
  `:470` `_end_state_final` (⏳ „Claude deployt #N“ bei autonomous, ✅ „fertig und deployt“ bei `deploy_status=done`).
- `core/hooks/config_loader.py:201` `find_project_root()` — Worktree → Haupt-Ordner (gewollt, #153: Grenzen aus dem Haupt-Ordner).
- `hooks/hooks.json` + `scripts/sync_cloud_hooks.py` (Cloud-/Consumer-Generat in `.claude/settings.json`, geprüft von `release_check.py`).

## Existing Patterns

- Gates als PreToolUse-Hooks, Exit 2 = blockiert, Meldung auf stderr; fail-closed bei Grenzen.
- Bestehende PreToolUse-Matcher: `""`, `Edit|Write|MultiEdit`, `Bash`, `Read` — kein `Skill`-Matcher.
- `secrets_guard_patterns` (config_loader:439): dokumentierte Ausnahme vom Haupt-Ordner-Grundsatz, eng begrenzt.
- `_observable_base` (hook_utils:2371): Basiszweig über `refs/remotes/origin/HEAD`, kein geratener Name.

## Dependencies / Dependents

- Tests zu Aliasen: `tests/test_setup_command_aliases.py`, `test_setup_alias_sync_150.py`, `test_alias_*`,
  `test_fix_schritte_ueberspringen.py` (`REDIRECT_COUNT = 11`), `test_repo_own_aliases_147.py`.
- Tests zum Endzustand/Deploy: `tests/test_*550*`, `test_*deploy*`.

## Existing Specs

- `docs/specs/short-command-aliases.md` (Alias-Strategien), Deploy-Endzustand #550, Deploy-Config #81/#478.

## Risks

- `disable-model-invocation: false` für 70-deploy ohne technische Sperre ließe Claude auch ohne `autonomous` deployen.
- Text-Redirect statt Vollkopie würde für den PO-Aufruf `/70-deploy` einen Skill-Aufruf erzeugen, den eine Sperre dann fälschlich blockiert → Alias muss Vollkopie bleiben.
- `~`-Alias schattet Projekt-Alias (#87) — config-abhängige Alias-Inhalte wären unzuverlässig.
- Worktree darf sich die Deploy-Erlaubnis nicht im eigenen Zweig selbst geben (#153).
