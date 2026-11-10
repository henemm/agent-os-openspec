# Context: fix-566-plugin-update-sync

## Request Summary
`setup.py <projekt> --update` spiegelt in Plugin-Modus-Projekten ohne Cloud-Pin `core/hooks/*.py` und `core/commands/*.md` per `sync_dir` in vorhandene `.claude/hooks` bzw. `.claude/commands`. Shims (#33/#165) und markierte Kurzbefehle werden dadurch zu Vollkopien, fehlende Framework-Dateien angelegt. Soll: im Plugin-Modus kein Spiegeln dieser beiden Ordner; Shims und markierte Kurzbefehle nur über `refresh_shims` / `refresh_aliases`; projekteigene Dateien unberührt.

## Related Files
| File | Relevance |
|------|-----------|
| `setup.py:1308` `update_project` | Ursache: `sync_dir` für hooks (`:1349`) und commands (`:1356`) nur mit `not pinned` ausgeklammert |
| `setup.py:1345` `pinned` | heute `plugin_mode and (cloud_ref or cloud_sha)`; #562 hat nur den gepinnten Zweig gelöst |
| `setup.py:967` `refresh_pinned_rollout` | erneuert vorhandene veraltete Shims (`migrate_to_plugin.refresh_shims`) und markierte Kurzbefehle (`alias_sync.refresh_aliases`); legt nie etwas an; heute nur im gepinnten Zweig (`:1403–1406`) und in `--cloud-gates` aufgerufen |
| `migrate_to_plugin.py:248` `refresh_shims` | nur `SHIM_HOOKS` (`hook_utils.py`, `config_loader.py`) mit Marker; Shim funktioniert auch ohne Pin (Fallback auf installiertes Plugin) |
| `core/hooks/alias_sync.py` `refresh_aliases` | nur markierte, veraltete Aliase; derselbe Kern wie `setup.py --refresh-aliases` (`:1547`) |
| `tests/test_cache_finder_562.py:642` `test_update_without_pin_is_unchanged` (AC-15 aus #562) | sichert das heutige Verhalten ohne Pin ab: Shims/Aliase dürfen nicht dem Soll-Inhalt entsprechen; besteht heute nur, weil `sync_dir` sie zu Vollkopien macht → muss mit #566 neu gefasst werden |
| `tests/test_cache_finder_562.py:536` `_consumer`, `_setup`, `fw_copy` | Test-Bausteine (Plugin-Projekt mit/ohne Pin, Shims, Aliase, eigene Dateien) wiederverwendbar |
| `tests/test_setup_update_preserves_plugin_mode_159.py` | `--update` im Plugin-Modus erhält `plugin_mode`/Felder; darf nicht brechen |
| `tests/test_setup_update_keeps_local_72.py` | Copy-Modus-Sync mit Manifest/Backups; Copy-Modus bleibt unverändert |

## Existing Patterns
- #562: `existing` (framework_version.json) wird vor den Sync-Läufen gelesen, Gate über ein Bool (`pinned`) vor `sync_dir`.
- Rollout-Funktionen legen nie Dateien an, ersetzen nur markierte, veraltete Fassungen (Schutz vor Überschatten, #87/#163/#400).
- Copy-Modus: `sync_dir` mit Manifest, lokale Änderungen → `.new` / Backup (#72).

## Dependencies
- Upstream: `migrate_to_plugin.refresh_shims`, `alias_sync.refresh_aliases`, `sync_file`/Manifest.
- Downstream: jedes Konsumentenprojekt, das `setup.py --update` ausführt; `--cloud-gates` nutzt denselben Rollout.

## Existing Specs
- `docs/specs/feat-562-cloud-cache-finder.md` — Befund-Absatz (Zeile 71) und AC-13/14/15; #566 als Folge benannt.
- `docs/specs/feat-522-cloud-plugin-gates.md` — Pin/Plugin-Modus-Zweig in `update_project`.

## Risks & Considerations
- AC-15 aus #562 ist mit dem Soll von #566 unvereinbar (ohne Pin würden Shims/Aliase jetzt erneuert) → Test bewusst neu fassen, nicht löschen.
- Gleiche Fehlerklasse, aber nicht im Issue: `.claude/agents` (Spiegeln nur, wenn Ordner existiert), `core/tools` → `.claude/tools` (wird ohne Existenzprüfung angelegt), Modul-Hooks via `install_module`. Entscheidung in der Analyse, ob mit drin oder Folge-Issue.
- Ältere Plugin-Projekte, die schon Vollkopien in `.claude/hooks` haben, behalten diese (nichts wird gelöscht); Plugin-Modus nutzt sie nicht (Registrierung über `${CLAUDE_PLUGIN_ROOT}`), außer `hook_utils`/`config_loader` als Import-Ziel von Modul-Hooks.
- Kein Pin-Abruf im ungepinnten Zweig: `refresh_cloud_gates` bleibt an `pinned` gebunden.

## Analysis

### Type
Bug (Folge zu #562; Ursache belegt: `setup.py:1349` und `setup.py:1356` klammern nur den gepinnten Plugin-Zweig aus).

Reproduktion (heutiger Stand): Plugin-Projekt ohne Pin mit Shim `hook_utils.py`, markiertem Alias `10-context.md` und eigenen Dateien → `setup.py <proj> --update` → alle `core/hooks/*.py` und `core/commands/*.md` landen im Projekt, Shim und Alias sind Vollkopien („UEBERSCHRIEBEN, ALTE FASSUNG GESICHERT"). Der bestehende Test `test_update_without_pin_is_unchanged` besteht nur deshalb (Soll-Inhalt ≠ Vollkopie).

### Affected Files (with changes)
| File | Change Type | Description |
|------|-------------|-------------|
| `setup.py` | MODIFY | `update_project`: Spiegeln von `core/hooks` und `core/commands` im gesamten Plugin-Modus aus (Bool `plugin` statt `pinned`); Rollout (Shims + markierte Kurzbefehle) im Plugin-Zweig unabhängig vom Pin; `refresh_cloud_gates` bleibt an den Pin gebunden. `refresh_pinned_rollout` → `refresh_plugin_rollout` (Name + Docstring; 2 Aufrufer) |
| `tests/test_cache_finder_562.py` | MODIFY | AC-15-Test neu gefasst: ohne Pin werden Shims/Aliase jetzt erneuert, sonst nichts angelegt, kein Pin |
| `tests/test_plugin_update_sync_566.py` | CREATE | ACs von #566: keine Vollkopien ohne Pin, eigene Dateien/echte Kopien byte-gleich, keine neuen Dateien, idempotent, Copy-Modus unverändert |
| `CHANGELOG.md` | MODIFY | `[Unreleased]` → Fixed |

### Scope Assessment
- Files: 4
- Estimated LoC: +~120 (davon ~100 Tests) / −~15
- Risk Level: MEDIUM (Update-Pfad aller Konsumenten; Copy-Modus und gepinnter Zweig müssen unverändert bleiben)

### Technical Approach
- `plugin = bool(existing.get("plugin_mode"))` neben `pinned`; `sync_dir` für hooks/commands nur bei `not plugin`.
- Im Plugin-Zweig: `refresh_plugin_rollout(project_path)` immer (legt nie etwas an, ersetzt nur markierte veraltete Shims/Aliase, Symlinks/unbeschreibbare Dateien → `Skipped:`); bei Pin zusätzlich wie bisher `refresh_cloud_gates`. Shims funktionieren ohne Pin (Fallback aufs installierte Plugin), Aliase sind pin-unabhängig (gleicher Kern wie `--refresh-aliases`).
- Ausgabe ohne Pin mit eigenem Präfix (`plugin refresh:`), damit die Meldung nicht „cloud“ behauptet.

### Bewusst nicht im Scope (Begründung)
- `.claude/agents`: `.claude-plugin/plugin.json` liefert keine Agenten aus; Projekte brauchen die Kopien → Spiegeln bleibt.
- `core/tools` → `.claude/tools` und Modul-Dateien (`install_module`: hooks, standards, tools, workflows): enthalten projektseitig genutzte Inhalte; kein gemeldeter Schaden, eigener Befund wäre nötig. Kein Folge-Issue ohne Schadensnachweis.
- Vorhandene Alt-Vollkopien in Plugin-Projekten werden nicht gelöscht (Datenverlust-Risiko, Issue verlangt nur „nicht mehr spiegeln").

### Befunde gegen den Plan
- AC-15 aus #562 legt das Gegenteil fest → bewusste Neufassung, im Spec benannt (#562 hatte #566 dafür ausdrücklich vorgesehen).

### Open Questions
- keine (reine Technikentscheidung, Soll im Issue eindeutig)
