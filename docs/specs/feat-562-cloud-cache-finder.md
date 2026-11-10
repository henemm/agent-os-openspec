---
entity_id: feat-562-cloud-cache-finder
type: feature
created: 2026-11-09
updated: 2026-11-09
status: draft
version: "1.0"
workflow: feat-562-cloud-cache-finder
tags: [hooks, cloud, plugin-consumers, shims, aliases, banner, setup]
---

# Cloud-Cache-Suche für Shims, Kurzbefehle und Banner (Issue #562, Scheibe 2 zu #522)

## Approval

- [ ] Approved

## Purpose

Scheibe 1 (#522) lädt die Gates für Plugin-Konsumenten in Cloud-Sitzungen aus einem gepinnten Cache (`~/.cache/agent-os-openspec/<cloud_ref>`). Drei Teile des Frameworks kennen diesen Cache noch nicht und scheitern deshalb in der Cloud: die Shims `.claude/hooks/hook_utils.py` und `config_loader.py` (projekteigene Hooks mit `import hook_utils` brechen mit `ImportError`), die Redirect-Kurzbefehle (`/10-context` endet mit `BEFEHLSTEXT FEHLT`) und der Session-Banner (kein Hinweis, wenn der Pin hinter der lokalen Plugin-Version zurückliegt). Diese Änderung bringt allen drei Stellen die Suche im Pin-Cache bei, ohne das lokale Verhalten zu ändern (Plugin-Registry hat weiter Vorrang), und sorgt dafür, dass `--cloud-gates` und `--update` die neuen Shims und Kurzbefehle in den Konsumenten-Projekten ausrollen.

## Source

- **File:** `migrate_to_plugin.py`, `core/hooks/alias_sync.py`, `core/hooks/session_banner.py`, `setup.py`
- **Identifier:** `migrate_to_plugin.SHIM_TEMPLATE`, `migrate_to_plugin.refresh_shims` (neu); `alias_sync._FALLBACK_SOURCE`, `alias_sync._fallback_command`; `session_banner.build_output` mit neuem Drift-Hinweis; `setup.apply_cloud_gates`, `setup.refresh_cloud_gates`, `setup.update_project`

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `core/cloud_bootstrap.py` (#522) | module | `read_pin`, `cache_base`, `cache_valid`, `fetch`, `FetchError`; wird nicht geändert; im Konsumenten als `.claude/cloud_bootstrap.py` vorhanden |
| `.claude/framework_version.json` | config | trägt `cloud_ref` und `cloud_sha` (der Pin) |
| `~/.claude/plugins/installed_plugins.json` | registry | lokale Fundstelle des Plugins; bleibt erste Wahl |
| `migrate_to_plugin._is_shim`, `_find_shim_candidates`, `_render_shim` (#165) | function | erkennen veraltete Shims am Marker und Inhaltsvergleich; Basis für `refresh_shims` |
| `alias_sync.alias_content`, `refresh_aliases` (#251/#399) | function | einzige Quelle der Kurzbefehl-Dateien; Rollout nutzt sie unverändert |
| `AGENT_OS_CLOUD_CACHE`, `CLAUDE_CODE_REMOTE`, `CLAUDE_PROJECT_DIR` | env | Cache-Ort (Tests), Cloud-Kennung, Projektordner |
| `docs/specs/feat-522-cloud-plugin-gates.md` | spec | Scheibe 1; diese Spec setzt deren Abschnitt „Known Limitations“ (Verweis auf #562) um |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| migrate_to_plugin.py | MODIFY | `SHIM_TEMPLATE`: Registry, dann Pin-Cache des Projekts (nach Validierung, bei fehlendem Cache `fetch()`), sonst unveränderter `ImportError`; neuer Helfer `refresh_shims(project)` (nur vorhandene, veraltete Shims) |
| core/hooks/alias_sync.py | MODIFY | `_FALLBACK_SOURCE`: weiterer Kandidat `<cache_base>/<cloud_ref>` aus `.claude/framework_version.json`, nur ohne Symlink und mit `.ok` gleich `cloud_sha`; `BEFEHLSTEXT FEHLT` nennt „Cache noch nicht bereit“ |
| core/hooks/session_banner.py | MODIFY | Drift-Hinweis, wenn der Pin hinter der lokalen Plugin-Version liegt (PO-Zeile ohne Befehl, Befehl nur in `additionalContext`) |
| setup.py | MODIFY | `apply_cloud_gates` und der gepinnte Zweig von `update_project`/`refresh_cloud_gates` erneuern veraltete Shims und vorhandene Projekt-Kurzbefehle |
| .claude/commands/*.md, ggf. skills/ | MODIFY (regeneriert) | Repo-Aliase byte-gleich mit `alias_content()` |
| tests/test_cache_finder_562.py | CREATE | alle ACs unten |
| tests/test_migrate_shims.py, tests/test_plugin_shim_sibling_import_165.py, tests/test_session_banner.py, tests/test_cloud_gates_522.py, tests/test_alias_*.py, tests/test_setup_command_aliases.py | MODIFY (nur wo Literale den alten Text prüfen) | folgen meist `alias_content()` und `_render_shim` |
| CHANGELOG.md | MODIFY | Eintrag unter `[Unreleased]` mit `#562` |
| README.md, CLAUDE.md | MODIFY | Cloud-Abschnitt und Alias-Zeile: Konsumenten laufen einmal `--update` bzw. `--cloud-gates` |

### Estimated Changes

- Files: 1 neu (Test), 4 produktiv geändert plus regenerierte Aliase, Tests und Doku angepasst
- LoC: +100 Produktion / +200 Test
- Risk Level: HIGH (die Shims laufen in jedem projekteigenen Hook aller Konsumenten; Setup schreibt in Konsumenten-Projekte; der Shim lädt Code aus `~/.cache`)

## Implementation Details

**Shim (`SHIM_TEMPLATE`).** Reihenfolge: (1) Plugin-Registry wie bisher; gefunden heißt: Verhalten byte-identisch zu heute. (2) Pin-Cache: Projektordner aus dem Shim-Pfad (`.claude/hooks/` drei Ebenen hoch), ersatzweise `CLAUDE_PROJECT_DIR`. `.claude/cloud_bootstrap.py` wird per `importlib.util.spec_from_file_location` geladen (nicht über `sys.path`, damit kein fremdes Modul gleichen Namens greift). Dann `read_pin()`, Cache-Ordner `cache_base()/<cloud_ref>`, Nutzung nur nach `cache_valid(cache, sha, "<modul>.py")` (kein Symlink, SHA stimmt, Baum sauber). Fehlt der Cache, holt der Shim ihn selbst mit `fetch()` (Sperre, höchstens ein Klon, `CLONE_TIMEOUT`), weil projekteigene Hooks beim ersten Ereignis parallel zum Baustein laufen. (3) Jeder Fehler (kein Pin, Validierung scheitert, `FetchError`, Importfehler) führt zum unveränderten `ImportError` von heute. Der Zeiger `<base>/current` wird nirgends gelesen: er zeigt auf den zuletzt geklonten Stand im Container und kann bei mehreren Repos je Sitzung auf einen fremden, ungeprüften Pin zeigen. `CLAUDE_PLUGIN_ROOT` bleibt draußen: laut #163 ein eingefrorener Stand, projekteigene Hooks bekommen ihn in der Cloud nicht, der alte Shim nutzte ihn nie. Gefundene Quelle kommt vorn in `sys.path`, damit Geschwister-Importe (#165, etwa `hook_utils` importiert `config_loader`) aus demselben Ordner laufen.

**Alias-Fallback (`_FALLBACK_SOURCE`).** Bleibt ein Einzeiler `python3 -c 'exec("…")'` ohne `&&`, `;`, `|` (Permission-Präfix), Exit immer 0. Neuer Kandidat nach den bisherigen: `<cache_base>/<cloud_ref>` mit `cloud_ref`/`cloud_sha` aus `<projekt>/.claude/framework_version.json`. Leichte Prüfung, weil der Text in den Prompt geht und nicht ausgeführt wird: kein Symlink (Ordner, `.ok`, `skills/<name>/SKILL.md`) und Inhalt von `.ok` gleich `cloud_sha`. Gedruckt wird der Befehlstext samt `export CLAUDE_PLUGIN_ROOT=<cache>` (der Cache erfüllt die bestehende Bedingung `<r>/core/hooks`). Kein `git`, kein Abruf im Einzeiler. Ohne passenden Cache nennt `BEFEHLSTEXT FEHLT` zusätzlich „Cache noch nicht bereit“ mit dem Hinweis auf `python3 .claude/cloud_bootstrap.py --retry`.

**Banner.** `build_output` bekommt einen Hinweis, wenn `cloud_ref` im Projekt gesetzt ist, die Sitzung nicht in der Cloud läuft (`CLAUDE_CODE_REMOTE` nicht `true`; in der Cloud ist der Pin selbst das Framework) und die lokale Plugin-Version numerisch neuer ist als die Version im Tag (`agent-os-openspec--vX.Y.Z`; Vergleich über `alias_sync.version_tuple`). PO-Zeile: einfacher Satz ohne Befehl (Regel aus fix-399). Der Befehl `python3 <framework>/setup.py <projekt> --update` steht nur im `additionalContext` für Claude. Jeder Fehler (kaputte JSON, unlesbare Version) führt zu keinem Hinweis (fail-open).

**Rollout.** `migrate_to_plugin.refresh_shims(project) -> list[Path]` ersetzt vorhandene Dateien aus `SHIM_HOOKS`, deren erste Zeile `SHIM_MARKER` ist und deren Inhalt von `_render_shim` abweicht; echte Kopien (ohne Marker) und fehlende Dateien bleiben unberührt. `setup.apply_cloud_gates` (`--cloud-gates`) und der gepinnte Zweig von `update_project` (`--update`, nur wenn `cloud_ref`/`cloud_sha` gesetzt sind) rufen `refresh_shims` und `alias_sync.refresh_aliases` auf `.claude/commands` des Projekts auf und nehmen geänderte Dateien in die Ausgabe der zu committenden Dateien auf. Es wird nie ein Shim oder Kurzbefehl neu angelegt. Ohne Pin ist `--update` unverändert. Idempotent: ein zweiter Lauf ändert kein Byte.

**Befund aus TDD RED (`--update` im Plugin-Modus).** `update_project` spiegelt heute `core/hooks/*.py` und `core/commands/*.md` per `sync_dir` in vorhandene Ordner `.claude/hooks` bzw. `.claude/commands`, auch im Plugin-Modus: Shims und markierte Kurzbefehle werden dabei zu Vollkopien (alte Fassung in `update-backups/`), echte Kopien überschrieben, fehlende Dateien angelegt. Damit wären AC-13 und AC-14 unerfüllbar. Entscheidung: Im gepinnten Plugin-Zweig (Pin gesetzt) entfallen diese beiden `sync_dir`-Läufe; Shims und Kurzbefehle erneuern dort allein `refresh_shims` und `refresh_aliases`. Dafür wird `framework_version.json` vor den Sync-Läufen gelesen. Ohne Pin bleibt das heutige Verhalten unverändert (AC-15); das allgemeine Problem im ungepinnten Plugin-Modus ist #566. `refresh_shims` liegt in `migrate_to_plugin.py`; `setup.py` importiert es erst im Bedarfsfall, damit Framework-Kopien ohne diese Datei (Testaufbau #522) weiter laufen.

**Repo-Aliase.** `.claude/commands/*.md` (und ggf. `skills/`-Ableitungen) dieses Repos werden mit dem vorhandenen Generator neu erzeugt und sind danach byte-gleich mit `alias_content()`.

**Tests.** Echte Dateien in `tmp_path`, Aufruf der Shims und des Alias-Einzeilers per `subprocess`; Fake-Framework-Repo und Cache über `AGENT_OS_CLOUD_CACHE`, Registry über ein Fake-`HOME`. Kein Mock von Shell oder git.

## Expected Behavior

- **Input:** (a) `import hook_utils` bzw. `import config_loader` aus einem projekteigenen Hook eines Plugin-Konsumenten; (b) Aufruf eines Redirect-Kurzbefehls wie `/10-context` ohne geladenes Plugin; (c) SessionStart in einer lokalen Sitzung eines Konsumenten mit Pin; (d) `setup.py <projekt> --cloud-gates` oder `--update`.
- **Output:** (a) Modul wird aus der Registry geladen (lokal, unverändert), sonst aus dem validierten Pin-Cache; sonst der bisherige `ImportError`. (b) Befehlstext des Skills samt `export CLAUDE_PLUGIN_ROOT=<cache>`, sonst `BEFEHLSTEXT FEHLT` mit „Cache noch nicht bereit“; immer Exit 0. (c) Eine PO-Zeile zum veralteten Pin, nur wenn der Pin älter ist als das lokale Plugin. (d) Erneuerte Dateien werden aufgelistet.
- **Side effects:** Der Shim kann den Pin-Cache per `fetch()` anlegen (wie der Baustein aus #522). `--cloud-gates`/`--update` schreiben Shims und Kurzbefehle im Projekt neu, wenn sie veraltet sind.

## Known Limitations

- Konsumenten müssen einmal `setup.py <projekt> --update` (mit Pin) oder `--cloud-gates` laufen lassen und die geänderten Dateien committen; vorher bleiben alte Shims und Kurzbefehle im Projekt.
- Prüfung und Start der Cache-Skripte sind nicht atomar (TOCTOU, F009); das ist ein eigenes Issue (#564) und wird hier nicht gelöst.
- `CLAUDE_PLUGIN_ROOT` wird bewusst nicht als Quelle genutzt (eingefrorener Stand, in der Cloud für projekteigene Hooks nicht gesetzt).
- Der Alias-Fallback prüft nur leicht (`.ok` gleich `cloud_sha`, kein Symlink), weil sein Ergebnis Text für den Prompt ist; die volle Prüfung (`cache_valid`) gilt nur im Shim, der Code ausführt.
- Wenn die Cloud-Umgebung github.com nicht erreicht und der Cache fehlt, scheitert der Shim weiterhin mit dem bisherigen `ImportError`; Abhilfe bleibt Netzfreigabe plus `--retry` (#522).
- Der Drift-Hinweis erscheint nur lokal; in der Cloud ist der Pin das Framework und kein Vergleich sinnvoll.

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test in `tests/test_cache_finder_562.py` belegt
- [ ] In einer frischen Cloud-Sitzung eines Konsumenten liefert `/10-context` den Befehlstext des Skills; es erscheint kein `BEFEHLSTEXT FEHLT` (AC-7)
- [ ] Ein projekteigener Hook mit `import hook_utils` läuft in der Cloud ohne `ImportError` (AC-1, AC-5)
- [ ] Lokal mit installiertem Plugin verhält sich alles wie bisher; die Registry hat Vorrang vor dem Cache (AC-2)
- [ ] Ein Cache mit falscher SHA, Symlink oder verschmutztem Baum wird nie benutzt (AC-3, AC-8)
- [ ] Der Banner weist lokal darauf hin, dass der Cloud-Stand hinter dem lokalen Plugin liegt, ohne dem PO einen Befehl zuzumuten (AC-9 bis AC-11)
- [ ] `--cloud-gates` und `--update` bringen veraltete Shims und Kurzbefehle in Konsumenten-Projekten auf den neuen Stand, ohne echte Kopien anzufassen und ohne etwas neu anzulegen (AC-12 bis AC-15)
- [ ] Regressionslauf `pytest tests/` grün, insbesondere die Tests zu #165, #251, #399 und #522

## Acceptance Criteria

Testaufbau: echte Dateien in `tmp_path`, `subprocess.run` für Shim und Alias-Einzeiler, Fake-Framework mit annotiertem Tag über `file://`, `AGENT_OS_CLOUD_CACHE` auf `tmp_path`, Fake-`HOME` für die Registry.

- **AC-1:** Given ein Konsumenten-Projekt mit neuem Shim, gültigem Pin und gültigem Cache `<base>/<cloud_ref>` sowie ohne Plugin-Registry / When ein Hook-Skript `import hook_utils` ausführt / Then wird das Modul aus dem Pin-Cache geladen und der Import gelingt
  - Test: tests/test_cache_finder_562.py::test_shim_finds_pin_cache_when_registry_missing

- **AC-2:** Given eine Registry, die auf ein Plugin zeigt, und zusätzlich ein gültiger Pin-Cache / When `import hook_utils` läuft / Then stammt das Modul aus dem Plugin der Registry und nicht aus dem Cache (lokal unverändert)
  - Test: tests/test_cache_finder_562.py::test_registry_wins_over_pin_cache

- **AC-3:** Given ein Pin-Cache, dessen Ordner ein Symlink ist, dessen `.ok` eine andere SHA nennt als `cloud_sha`, oder dessen Baum verändert wurde, und keine Registry, und der Abruf ist nicht möglich / When `import hook_utils` läuft / Then bleibt es beim unveränderten `ImportError` und es wird nichts aus diesem Cache importiert
  - Test: tests/test_cache_finder_562.py::test_shim_rejects_invalid_cache_with_unchanged_import_error

- **AC-4:** Given ein Pin-Cache, in dem `hook_utils.py` seinerseits `config_loader` aus demselben Ordner importiert / When ein projekteigener Hook `import hook_utils` ausführt / Then gelingt auch der Geschwister-Import (#165) aus dem Cache
  - Test: tests/test_cache_finder_562.py::test_sibling_import_works_via_cache

- **AC-5:** Given gültiger Pin, fehlender Cache und erreichbares `file://`-Fake-Repo mit passendem Tag, keine Registry / When `import hook_utils` läuft / Then holt der Shim den Cache per `fetch()` und der Import gelingt; ist die Quelle nicht erreichbar oder der Tag falsch, endet es mit dem unveränderten `ImportError` und ohne halben Cache-Ordner
  - Test: tests/test_cache_finder_562.py::test_shim_fetches_missing_cache_and_fails_closed_on_fetch_error

- **AC-6:** Given ein Zeiger `<base>/current`, der auf einen gültigen, aber fremden Cache zeigt, und ein Pin ohne eigenen Cache bei nicht erreichbarer Quelle, keine Registry / When `import hook_utils` läuft / Then wird der Zeiger nicht benutzt und es bleibt beim unveränderten `ImportError`
  - Test: tests/test_cache_finder_562.py::test_shim_never_uses_current_pointer

- **AC-7:** Given ein Konsumenten-Projekt mit Redirect-Alias und Pin sowie ein Cache mit `skills/<name>/SKILL.md`, `.ok` gleich `cloud_sha`, ohne geladenes Plugin / When der Alias-Einzeiler läuft / Then druckt er den Befehlstext des Skills samt `export CLAUDE_PLUGIN_ROOT=<cache>`, Exit 0, und die Einzeiler-Quelle enthält weder `&&` noch `;` noch `|` außerhalb des Python-Textes (kein Shell-Operator in der Kommandozeile)
  - Test: tests/test_cache_finder_562.py::test_alias_fallback_prints_command_text_from_pin_cache

- **AC-8:** Given ein Cache ohne `.ok`, mit abweichender SHA in `.ok` oder mit Symlink als `SKILL.md` bzw. Cache-Ordner / When der Alias-Einzeiler läuft / Then wird der Cache nicht benutzt, die Ausgabe beginnt mit `BEFEHLSTEXT FEHLT` und nennt „Cache noch nicht bereit“, Exit 0
  - Test: tests/test_cache_finder_562.py::test_alias_fallback_rejects_cache_and_reports_not_ready

- **AC-9:** Given ein Projekt mit Pin `cloud_ref` kleiner als die lokale Plugin-Version, lokale Sitzung (`CLAUDE_CODE_REMOTE` nicht gesetzt) / When der Banner läuft / Then enthält die PO-Ausgabe eine Zeile zum veralteten Cloud-Stand ohne `setup.py` oder Befehl, und der `additionalContext` enthält den Befehl `setup.py <projekt> --update`
  - Test: tests/test_cache_finder_562.py::test_banner_reports_pin_drift_without_command_for_po

- **AC-10:** Given kein Pin, oder `CLAUDE_CODE_REMOTE=true`, oder Pin-Version gleich der lokalen Plugin-Version, oder Pin-Version neuer / When der Banner läuft / Then erscheint kein Drift-Hinweis
  - Test: tests/test_cache_finder_562.py::test_banner_no_drift_hint_without_pin_in_cloud_or_equal_version

- **AC-11:** Given eine kaputte `framework_version.json` oder ein unlesbarer `cloud_ref` / When der Banner läuft / Then läuft er ohne Fehler und ohne Drift-Hinweis durch (fail-open)
  - Test: tests/test_cache_finder_562.py::test_banner_drift_check_is_fail_open

- **AC-12:** Given ein Plugin-Modus-Projekt mit Pin, veralteten Shims (Marker, alter Inhalt) und vorhandenen veralteten Redirect-Kurzbefehlen / When `setup.py <projekt> --cloud-gates` läuft / Then sind Shims und Kurzbefehle erneuert (Inhalt gleich `_render_shim` bzw. `alias_content()`), die Dateien stehen in der Ausgabe, und ein zweiter Lauf ändert kein Byte
  - Test: tests/test_cache_finder_562.py::test_cloud_gates_refreshes_stale_shims_and_aliases_idempotently

- **AC-13:** Given dasselbe Projekt mit Pin / When `setup.py <projekt> --update` läuft / Then werden veraltete Shims und vorhandene Projekt-Kurzbefehle ebenfalls erneuert und der Pin bleibt erhalten
  - Test: tests/test_cache_finder_562.py::test_update_with_pin_refreshes_shims_and_aliases

- **AC-14:** Given ein Projekt mit echten Kopien von `hook_utils.py`/`config_loader.py` (erste Zeile ohne Shim-Marker), fehlenden Shims und fehlenden Kurzbefehlen / When `--cloud-gates` oder `--update` mit Pin läuft / Then bleiben die echten Kopien byte-gleich, und es wird kein Shim und kein Kurzbefehl neu angelegt
  - Test: tests/test_cache_finder_562.py::test_rollout_leaves_real_copies_alone_and_creates_nothing

- **AC-15:** Given ein Plugin-Modus-Projekt ohne Pin mit veralteten Shims und Kurzbefehlen / When `setup.py <projekt> --update` läuft / Then bleibt das Verhalten gegenüber heute unverändert (Shims und Kurzbefehle werden nicht durch den neuen Rollout verändert)
  - Test: tests/test_cache_finder_562.py::test_update_without_pin_is_unchanged

- **AC-16:** Given die Redirect-Aliase dieses Repos nach der Regenerierung / When ihre Dateien mit `alias_content(name, skill_text)` verglichen werden / Then sind sie byte-gleich
  - Test: tests/test_cache_finder_562.py::test_regenerated_repo_aliases_match_alias_content

## Test Plan

Automatische Tests (jeweils an eine AC oben gebunden, GIVEN/WHEN/THEN wie dort beschrieben):

- Neue Datei: `pytest tests/test_cache_finder_562.py`
- Betroffene bestehende Tests: `pytest tests/test_migrate_shims.py tests/test_plugin_shim_sibling_import_165.py tests/test_session_banner.py tests/test_cloud_gates_522.py tests/test_setup_command_aliases.py tests/test_fix_schritte_ueberspringen.py` sowie `pytest tests/ -k "alias"`
- TDD RED: Die neue Testdatei muss vor der Implementierung fehlschlagen (Shim, Alias-Fallback, Banner und Rollout kennen den Cache noch nicht)
- Regressionslauf: `pytest tests/`
- Nachweis DoD in der Cloud: In einer frischen Cloud-Sitzung eines Konsumenten läuft `/10-context` ohne `BEFEHLSTEXT FEHLT`, sobald das Projekt mit `--update` erneuert wurde

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Das Repo führt keine ADR-Sammlung (`docs/adr/` existiert nicht), und #522 hat bewusst keine ADR eingetragen (siehe `docs/specs/feat-522-cloud-plugin-gates.md`, Abschnitt ADR). Diese Spec setzt dessen Entscheidung „gepinnter Release-Stand im Cache“ fort und ergänzt drei Regeln: Erstens hat die Plugin-Registry Vorrang vor dem Pin-Cache, damit lokal nichts anders läuft. Zweitens wird nie der Zeiger `current` genutzt, sondern der Cache des Pins dieses Projekts, weil der Zeiger bei mehreren Repos je Sitzung auf einen fremden, ungeprüften Stand zeigen kann. Drittens wird Cache-Inhalt nur nach Validierung benutzt (kein Symlink, SHA, sauberer Baum), weil der Shim sonst beliebigen Code aus `~/.cache` ausführen würde; der Alias-Fallback prüft leichter, da er nur Text liefert. Kein neues Gate und keine neue Regel, daher keine eigene ADR.

## Changelog

- 2026-11-09: Initial spec created
