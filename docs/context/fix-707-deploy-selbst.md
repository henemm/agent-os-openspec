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

## Analysis

**Type:** Feature (Erweiterung bestehender Deploy-Kette) mit Bugfix-Anteil (Worktree-Config).

**Belege (Doku Claude Code, hooks):** „a PreToolUse hook matching the `Skill` tool fires only when Claude
calls the tool, but typing `/skillname` directly bypasses `PreToolUse`.“ Plugin-Skills heißen
`<plugin>:<skill>`. Das Skill-Tool nimmt `{"skill": "<name>", "args": "..."}` (Tool-Schema der Sitzung).

### Varianten

| | V1 Skill-Sperre (Hook) | V2 Alias je Projekt | V3 Datei lesen + ausführen |
|---|---|---|---|
| PO-only ohne autonomous | technisch erzwungen | brüchig (`~` schattet, #87) | nur Text |
| Wirkt sofort bei Config-Wechsel | ja | erst nach Alias-Refresh + Commit | ja |
| Scope | ~6 Dateien + Tests, ~150 LoC | ~5 Dateien, viele Alias-Tests | 1 Datei |

**Entscheidung: V1.**

### Affected Files

- CREATE `core/hooks/skill_gate.py` — PreToolUse, Matcher `Skill`: Skill-Name (ohne führendes `/`, ohne `agent-os-openspec:`) == `70-deploy` → nur erlaubt bei `deploy.autonomous: true`, sonst Exit 2 mit Hinweis „Deploy bleibt beim PO“. Fehler → blockieren (fail-closed). Andere Skills: immer erlaubt.
- MODIFY `hooks/hooks.json` (+ Generat `.claude/settings.json` via `scripts/sync_cloud_hooks.py`).
- MODIFY `core/commands/70-deploy.md` → `disable-model-invocation: false` + Step 0 (Selbstaufruf nur bei `autonomous: true`); Generate `skills/70-deploy/SKILL.md`, `.claude/commands/70-deploy.md`.
- MODIFY `core/hooks/alias_sync.py` — 70-deploy bleibt Vollkopie (feste Liste), damit der PO-Aufruf `/70-deploy` nie über das Skill-Tool läuft.
- MODIFY `core/hooks/workflow.py` `deploy_autonomous()` — Worktree-Regel (unten); gleiche Funktion nutzt die Sperre.
- MODIFY `core/commands/60-validate.md` — Selbstaufruf heißt Skill `70-deploy`.
- Tests: neu `tests/test_deploy_selbst_707.py`; Anpassungen laut Test-Übersicht.
- Doku: `docs/befehle/70-deploy.md`, `docs/architektur.md` (Hook-Liste), CHANGELOG, Version 4.29.0.

### Worktree-Regel (zweiter Befund)

In einer Worktree-Sitzung gilt für `deploy.autonomous` der gemergte Stand: ist die Config-Datei im
Haupt-Ordner unverändert gegenüber dessen HEAD, wird der Wert aus `git show <origin/HEAD>:<relpfad>`
gelesen (Basiszweig über `refs/remotes/origin/HEAD`, kein geratener Name). Hat der Haupt-Ordner lokale
Änderungen an der Datei, oder schlägt git fehl, gilt der Haupt-Ordner wie bisher. Ein Zweig kann sich so
nichts selbst erlauben (#153 bleibt gewahrt): nur gemergter Stand zählt, auch ein Widerruf wirkt sofort.
Nur dieser eine Schalter, nicht die ganze Config.

### Risk

Hoch (Hook-/Gate-Code, Konfiguration). Rückfall bei fehlender Hook-Registrierung: Step-0-Textregel.

### Open Questions

Keine Produktfrage offen; Verhalten ohne `autonomous` bleibt unverändert.

### Test-Übersicht (Explore)

- Flag liegt nur in `skills/70-deploy/SKILL.md` (Frontmatter bleibt bei `sync_skills.py` erhalten).
- Bleibt 70-deploy Vollkopie (feste Liste in `alias_sync`), bleiben `REDIRECT_COUNT=11`,
  `test_alias_marker_position_251` (FULL_COPY_SKILL) und AC-3b in `test_setup_command_aliases` gültig;
  die versionierte Kopie `.claude/commands/70-deploy.md` per `setup.py --refresh-aliases` neu erzeugen.
- Neuer Hook: Cloud-Hookblock der Projekt-Settings per `scripts/sync_cloud_hooks.py` neu erzeugen
  (`test_cloud_hooks_520`, `test_cloud_gates_522`, `release_check.py`); Skriptname `^[A-Za-z0-9_]+\.py$`.
- `deploy_autonomous()`: End-to-End über `tests/test_endzustand_550.py:229-250` (Main-Sitzung, unverändert).
- `docs/architektur.md:271-283` Hook-Liste um `Skill` ergänzen; `tests/test_gate_event_log_181.py` ggf. neuen Hook aufnehmen.
