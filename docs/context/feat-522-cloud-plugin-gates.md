# Context: feat-522-cloud-plugin-gates

## Request Summary
Projekte, die das Framework als Plugin nutzen (gregor_zwanzig, loose-ends …), laufen in Cloud-Sitzungen
(Claude Code on the web) ganz ohne Gates und ohne Befehlstexte. Ziel (#522): In einer frischen
Cloud-Sitzung eines Plugin-Konsumenten greift ein Gate nachweislich, lokal läuft kein Hook doppelt,
`setup.py`/README beschreiben den Weg. Folge zu #520 (dort nur dieses Repo selbst abgesichert).

## Belegte Fakten (2026-11-09)

| Frage | Befund | Quelle |
|-------|--------|--------|
| Lädt die Cloud Plugins? | Nein, weder über `enabledPlugins`/`extraKnownMarketplaces` der Projekt-settings.json noch User-Plugins | code.claude.com/docs/en/cloud-environments.md („What carries over“), plugins/install.md (Cloud-Tab) |
| Laufen Projekt-Hooks in der Cloud? | Ja, auch SessionStart; Default-Timeout 600 s | cloud-environments.md („Setup scripts vs. SessionStart hooks“, „Time limits“) |
| `CLAUDE_CODE_REMOTE`, `CLAUDE_PROJECT_DIR` | dokumentiert; `CLAUDE_CODE_REMOTE="true"` nur in der Cloud | hooks.md |
| Doppelte Handler | gleiche Handler aus mehreren Settings-Dateien laufen einmal; die Plugin-Kopie bleibt getrennt (läuft zusätzlich) | hooks.md |
| Setup-Skript installiert Plugin? | Doku schweigt; da die Cloud Plugins grundsätzlich nicht lädt, wirkungslos zu erwarten | cloud-environments.md |
| Framework-Repo erreichbar? | `henemm/agent-os-openspec` ist **öffentlich**; anonymes `git clone --depth 1` über den Cloud-Git-Proxy klappt (gemessen: 1,5 s, 11 MB Arbeitsstand) | Messung in dieser Sitzung, add_repo-Auskunft |
| Release-Tags | `agent-os-openspec--v<X.Y.Z>`, von `release.yml` automatisch gesetzt (aktuell v4.9.0) | `git ls-remote --tags` |
| Projekt-Threads | in „project threads“ kommen Hooks aus server-verwalteten Settings, nicht aus dem Repo | cloud-environments.md |

## Konsumenten heute

- **gregor_zwanzig** (`.claude/settings.json`): `enabledPlugins: {agent-os-openspec@henemm-private: true}`,
  `extraKnownMarketplaces.henemm-private = github henemm/agent-os-openspec@main, autoUpdate: true`;
  dazu ~20 projekteigene Hooks (`if [ -f "${CLAUDE_PROJECT_DIR}/.claude/hooks/x.py" ]; then python3 …; fi`).
  `.claude/hooks/hook_utils.py` und `config_loader.py` sind **Shims** (migrate_to_plugin.py, #33), die das
  echte Modul über `~/.claude/plugins/installed_plugins.json` laden — in der Cloud fehlt diese Datei, die
  Projekt-Hooks, die `hook_utils` importieren, brechen dort also ebenfalls bzw. laufen ins Leere.
  Kurzbefehle unter `.claude/commands/` (projekteigene 70-deploy u. a.).
- **loose-ends**: gar keine `.claude/settings.json` im Repo — Plugin nur user-weit lokal aktiv.

## Related Files

| Datei | Relevanz |
|-------|----------|
| `hooks/hooks.json` | einzige Quelle aller Hook-Registrierungen (Plugin-Modus) |
| `scripts/sync_cloud_hooks.py` | #520: erzeugt cloud-bedingten hooks-Block für **dieses** Repo (`[ "$CLAUDE_CODE_REMOTE" != "true" ] || CLAUDE_PLUGIN_ROOT="${CLAUDE_PROJECT_DIR}" python3 "${CLAUDE_PROJECT_DIR}/core/hooks/x.py"`); `--check` für Drift |
| `.claude/settings.json` (dieses Repo) | Ergebnis von sync_cloud_hooks.py — Vorbild für Konsumenten |
| `setup.py` | `_PLUGIN_HOOK_CMD_RE` (Zerlegung der hooks.json-Kommandos), `copy_mode_hooks`, `_merge_hook_entries`, `install_plugin_mode`, `generate_command_aliases`, CLI-Optionen |
| `core/hooks/session_singleton_guard.py` | #520: keine Worktree-Pflicht bei `CLAUDE_CODE_REMOTE=true` |
| `core/hooks/session_banner.py` | SessionStart: Version, Alias-Refresh — Ort für Hinweise |
| `alias_sync.py` / Alias-Vorlage in setup.py | Redirect-Aliase: Fallback sucht `skills/<n>/SKILL.md` in `CLAUDE_PROJECT_DIR`, cwd und argv-Pfaden → bei Konsumenten `BEFEHLSTEXT FEHLT` |
| `migrate_to_plugin.py` | Shims für `hook_utils.py`/`config_loader.py` in Konsumenten |
| `scripts/release_check.py` | Zeile „Cloud-Hooks“ (Drift) |
| `tests/test_cloud_hooks_520.py` | Testmuster für cloud-bedingte Kommandos |
| `README.md` („Cloud sessions“) | verweist für Plugin-Konsumenten auf #522 |

## Existing Patterns

- Cloud-Bedingung als Kommando-Präfix `[ "$CLAUDE_CODE_REMOTE" != "true" ] || …` — lokal Exit 0 ohne stdin zu lesen, also nie doppelt (#520).
- Eine Quelle (`hooks.json`), abgeleitete Blöcke werden erzeugt und per `--check` auf Drift geprüft (#279, #520).
- `setup.py` mergt Hook-Einträge in bestehende settings.json, ohne projekteigene Hooks anzufassen (`_merge_hook_entries`).
- Hook-Pfade nie cwd-relativ, `${CLAUDE_PROJECT_DIR}` in Anführungszeichen (#165).

## Lösungswege aus dem Issue, bewertet nach Faktenlage

1. **SessionStart-Fetch (cloud-only)**: Hook klont den gepinnten Release-Tag (`agent-os-openspec--vX.Y.Z`) nach
   `~/.cache/agent-os-openspec/<tag>`; übrige Hooks rufen die Skripte von dort. Netz und Zeit sind belegt
   machbar (öffentliches Repo, 1,5 s). Kein Repo-Ballast beim Konsumenten; Version per Tag gepinnt.
2. **Vendoring (`setup.py --cloud-hooks` → `.claude/framework/`)**: ~1 MB Hooks + Skills im Konsumenten-Repo
   committet, veraltet ohne `--update`, Diff-Lärm. Funktioniert ohne Netz.
3. **Setup-Skript der Umgebung**: Plugin installieren lädt es laut Doku nicht; außerhalb des Repos, pro Umgebung → verworfen.

## Dependencies
- Upstream: hooks.json, Release-Tags von release.yml, Cloud-Git-Proxy (öffentliche Repos anonym lesbar).
- Downstream: alle Plugin-Konsumenten-Repos (settings.json, Shims, Aliase); release_check.

## Risks & Considerations
- **Fehlschlag des Fetch**: Wenn der Cache fehlt, dürfen Gates nicht still entfallen (Sicherheitsziel) —
  aber auch nicht die Sitzung unbenutzbar machen. Verhalten muss in der Spec entschieden werden.
- **Doppellauf lokal**: Cloud-Präfix verhindert ihn; lokal läuft weiter nur die Plugin-Kopie.
- **Versionsdrift**: Konsument pinnt einen Tag; lokal autoUpdate@main. Aktualisieren über `setup.py --update`.
- **Shims** (`hook_utils`/`config_loader`) in Konsumenten müssen in der Cloud den Cache finden, sonst brechen projekteigene Hooks.
- **Aliase**: Fallback muss den Cache als Befehlstext-Quelle kennen.
- **Projekt-Threads** der Cloud ignorieren Repo-Hooks — nicht lösbar im Repo, nur dokumentieren.
- Netzwerkrichtlinie „kein Internet“ einer Umgebung würde den Fetch verhindern → Meldung nötig.
- Schreibsperren: Konsumenten-settings.json wird von edit_gate/bash_gate geschützt (#543 enge Ausnahme nur für Plugin-Einträge) — setup.py schreibt außerhalb von Sitzungs-Gates, unkritisch.
