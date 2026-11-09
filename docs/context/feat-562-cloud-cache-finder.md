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

## Analysis

### Type
Feature (Folge zu #522, Scheibe 2)

### Affected Files (with changes)
| File | Change Type | Description |
|------|-------------|-------------|
| `migrate_to_plugin.py` | MODIFY | `SHIM_TEMPLATE`: Registry → Pin-Cache des Projekts → unveränderter `ImportError`; neuer Helfer `refresh_shims(project)` (nur vorhandene, veraltete Shims, nie echte Kopien) |
| `core/hooks/alias_sync.py` | MODIFY | `_FALLBACK_SOURCE`: weiterer Kandidat `<cache_base>/<cloud_ref>` aus `.claude/framework_version.json`, nur wenn kein Symlink und `.ok` == `cloud_sha`; `BEFEHLSTEXT FEHLT` um Hinweis „Cache noch nicht bereit“ ergänzt |
| `core/hooks/session_banner.py` | MODIFY | Drift-Hinweis: Pin `cloud_ref` vorhanden und Plugin-Version numerisch neuer → PO-Zeile ohne Befehl (fix-399), Befehl nur in `additionalContext`; fail-open |
| `setup.py` | MODIFY | `apply_cloud_gates` + `refresh_cloud_gates` (gepinnter Zweig von `update_project`): veraltete Shims und Projekt-Kurzbefehle erneuern, in Commit-Liste aufnehmen |
| `.claude/commands/*.md`, ggf. `skills/` | MODIFY (regeneriert) | Byte-Gleichheit mit `alias_content()` |
| `tests/test_cache_finder_562.py` | CREATE | Shim über Fake-Cache (`AGENT_OS_CLOUD_CACHE`), Ablehnung bei SHA-/Symlink-Abweichung, Geschwister-Import #165 über Cache, Alias-Fallback, Banner-Hinweis, Rollout idempotent, echte Kopien unberührt |
| bestehende Tests (`test_migrate_shims`, `test_plugin_shim_sibling_import_165`, `test_fix_schritte_ueberspringen`, `test_session_banner`, `test_cloud_gates_522`) | MODIFY (prüfen) | folgen meist `alias_content()`/`_render_shim`; nur anpassen, wo Literal |
| `CHANGELOG.md`, `README.md`, `CLAUDE.md` (Alias-Zeile) | MODIFY | Doku |
| `docs/specs/feat-562-cloud-cache-finder.md` | CREATE | Spec |

### Scope Assessment
- Files: ~5 produktiv + regenerierte Aliase + Tests + Doku
- Estimated LoC: ~+100 Produktion, ~+200 Tests
- Risk Level: HIGH (Shims laufen in jedem projekteigenen Hook aller Konsumenten; Setup schreibt in Konsumenten)

### Technical Approach (Entscheidungen)
1. **Shim-Reihenfolge: Registry → Pin-Cache → ImportError.** `CLAUDE_PLUGIN_ROOT` bleibt draußen: Issue-Text nannte es zuerst, DoD verlangt lokal unverändertes Verhalten; der alte Shim nutzte es nie, laut #163 ist es ein eingefrorener Stand, und projekteigene Hooks bekommen es in der Cloud nicht. Null lokales Risiko.
2. **Pin statt Zeiger `current`.** Projektordner aus dem Shim-Pfad (`.claude/hooks/` → drei Ebenen hoch), `CLAUDE_PROJECT_DIR` nur als Ersatz. `.claude/cloud_bootstrap.py` per `importlib.util.spec_from_file_location` laden (nicht über `sys.path`), dann `read_pin()`, `cache_base()/ref`, Nutzung nur nach `cache_valid(cache, sha, "<modul>.py")`. `current` wird nirgends genutzt (zeigt evtl. auf fremden Pin, ungeprüft).
3. **Shim holt fehlenden Cache selbst** per `fetch()` (Sperre, max. einmal `CLONE_TIMEOUT`), Grund: projekteigene Hooks laufen beim ersten Ereignis parallel zum Baustein. Jeder Fehler → unveränderter AC-5-`ImportError`.
4. **Kurzbefehl-Fallback** bleibt eine Zeile ohne `&&`/`;`/`|`, Exit 0; Cache-Kandidat nur mit leichter Prüfung (`.ok` == `cloud_sha`, kein Symlink) — Text geht in den Prompt, wird nicht ausgeführt. Kein `git` im Einzeiler, kein Abruf.
5. **Banner**: Hinweis nur lokal sinnvoll (in der Cloud ist `root` der Pin selbst → kein Hinweis). PO-Zeile ohne Befehl, Befehl `setup.py <projekt> --update` nur für Claude.
6. **Ausrollen**: `--cloud-gates` und `--update` (nur mit Pin) erneuern veraltete Shims (nur Dateien mit Shim-Marker) und vorhandene Projekt-Kurzbefehle (legt nie an). Ohne Pin unverändert.

### Dependencies
- `core/cloud_bootstrap.py` (import-sicher, `read_pin`, `cache_base`, `cache_valid`, `fetch`, `FetchError`) — wird nicht geändert.
- Verwandt: #564 (Prüfung/Start nicht atomar) bleibt eigenes Issue.

### Open Questions
- keine (alle Punkte technisch, vom Tech Lead entschieden)
