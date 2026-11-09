# Context: feat-562-cloud-cache-finder

## Request Summary
Scheibe 2 zu #522: In Cloud-Sitzungen eines Plugin-Konsumenten (kein Plugin geladen, Framework liegt im
Cache `~/.cache/agent-os-openspec/<cloud_ref>`) sollen (1) die Shims `hook_utils.py`/`config_loader.py`,
(2) die Redirect-Kurzbefehle und (3) ein Drift-Hinweis im Session-Banner den Cache bzw. den Pin kennen.
DoD: `/10-context` liefert in frischer Cloud-Sitzung den Befehlstext; projekteigener Hook mit
`import hook_utils` läuft; lokal unverändert (Registry vor Cache).

## Related Files
| File | Relevance |
|------|-----------|
| `migrate_to_plugin.py:84-151` | `SHIM_TEMPLATE`: sucht nur `~/.claude/plugins/installed_plugins.json` → in der Cloud `ImportError` |
| `migrate_to_plugin.py:164ff` `_find_shim_candidates` | erkennt veraltete Shims (Inhaltsvergleich) → `migrate_to_plugin.py --apply` erneuert sie; `setup.py --update` tut das bisher NICHT |
| `core/hooks/alias_sync.py:100-145` | `_FALLBACK_SOURCE`/`_fallback_command`: Redirect-Alias sucht `skills/<n>/SKILL.md` nur in `CLAUDE_PROJECT_DIR`, cwd, argv → in Konsumenten `BEFEHLSTEXT FEHLT`. Gibt `export CLAUDE_PLUGIN_ROOT=<r>` aus, wenn `<r>/core/hooks` existiert (Cache erfüllt das) |
| `setup.py:1500ff` `refresh_command_aliases`, `alias_sync.refresh_aliases` | Erneuern veralteter Alias-Kopien (Inhaltsvergleich) — neuer Fallback-Text macht vorhandene Projekt-Aliase „veraltet“, Banner meldet das bereits lokal |
| `core/hooks/session_banner.py:90-125` `installed_plugin()`, `plugin_version()`; `main()` 537ff, `build_output` | Ort für den Drift-Hinweis (Plugin-Version lokal vs. `cloud_ref`) |
| `core/cloud_bootstrap.py` | `cache_base()` (Env `AGENT_OS_CLOUD_CACHE`), `read_pin()`, `cache_valid()`, `fetch()` (schreibt Zeiger `<base>/current` nur nach frischem Klon), `_write_pointer` |
| `setup.py:960-1022` `--cloud-gates`, `refresh_cloud_gates`; `update_project` 1355ff | schreiben `cloud_ref`/`cloud_sha` in `.claude/framework_version.json`; Ort, um Shims/Aliase beim Pin mitzuerneuern |
| `docs/specs/feat-522-cloud-plugin-gates.md`, `docs/context/feat-522-cloud-plugin-gates.md` | Scheibe 1, Abschnitt „Scheibe 2“ (Zeiger `current`) |

## Existing Patterns
- Registry-Suche (`installed_plugins.json`, `agent-os-openspec@`, `scope: user` bevorzugt) ist an drei Stellen dupliziert: Shim, Alias-Fallback, `session_banner.installed_plugin()`, Setup-Block der Skills.
- Generierte Dateien in Konsumenten werden per Inhaltsvergleich als veraltet erkannt und erneuert (Shims #165, Aliase #251/#399).
- Alias-Fallback: eine Zeile `python3 -c 'exec("…")'` ohne Shell-Operatoren (Permission-Präfix `Bash(python3 -c *)`), Exit immer 0.
- Banner: fail-open, Ausgabe als Zeilenliste/`additionalContext`.

## Dependencies
- Upstream: `cloud_bootstrap.py` (Cache-Layout, Pin-Format, Validierung), `installed_plugins.json`.
- Downstream: alle Plugin-Konsumenten (committete Shims + Projekt-Aliase), `tests/test_migrate_shims.py`, `tests/test_plugin_shim_sibling_import_165.py`, `tests/test_alias_*`, `tests/test_setup_command_aliases.py`, `tests/test_session_banner.py`, `tests/test_cloud_gates_522.py`.

## Existing Specs
- `docs/specs/feat-522-cloud-plugin-gates.md` — Scheibe 1
- `docs/specs/feat-251-kurzbefehle.md` — Redirect-Aliase

## Risks & Considerations
- **Reihenfolge/Timing:** Projekthooks desselben Events laufen parallel zu den Bausteinaufrufen; beim allerersten Event einer frischen Sitzung kann der Cache (und der Zeiger) noch fehlen. Shim muss dann selbst den Pin-Cache holen können oder sauber scheitern.
- **Zeiger vs. Pin:** `current` zeigt auf den zuletzt geklonten Stand im Container, nicht zwingend auf den Pin dieses Projekts (mehrere Repos je Sitzung). Pin-Cache `<base>/<cloud_ref>` des Projekts ist die genauere Quelle.
- **Vertrauen:** Cache-Inhalt nur nach `cache_valid` nutzen (Symlinks, SHA, sauberer Baum) — sonst lädt der Shim beliebigen Code aus `~/.cache`.
- **Lokal unverändert:** Registry bleibt vor Cache; `CLAUDE_PLUGIN_ROOT` ist laut #163 ein eingefrorener, ggf. älterer Stand — Einordnung klären.
- **Ausrollen:** Konsumenten bekommen neue Shims/Aliase nur durch erneutes Schreiben; `--update` erneuert Shims bisher nicht.
- Verwandt: #564 (Prüfung und Start der Cache-Skripte nicht atomar, F009).
