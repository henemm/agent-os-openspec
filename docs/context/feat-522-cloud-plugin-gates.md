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

## Analysis

### Type
Feature (Sicherheitslücke schließen: Konsumenten ohne Gates in der Cloud)

### Entscheidung Lösungsweg (Tech Lead)
**A: gepinnter Abruf in einen Cache + kleiner, committeter Startbaustein** (`.claude/cloud_bootstrap.py`)
statt Vendoring. Vergleich (Plan-Agent, Zahlen gemessen bzw. aus `du`):

| | A: Abruf in Cache | B: Vendoring `.claude/framework/` |
|---|---|---|
| Zusatz im Konsumenten-Repo | ~0,1 MB (Baustein ~120 LoC + ~25 Hook-Einträge) | ~2,5 MB, bei jedem Update neu committet |
| Netz | einmal je Container ~1,5 s (`git clone --depth 1`), danach Cache | keins |
| Veralten | Tag + Commit-SHA gepinnt, `setup.py --update` hebt an | gleich, plus Diff-Lärm |
| Fehlerbilder | Netz/Tag fehlt → fail-closed mit Meldung | veraltete/lokal veränderte Kopie |

### Affected Files (Scheibe 1 = dieser Workflow)
| File | Change Type | Description |
|------|-------------|-------------|
| `core/cloud_bootstrap.py` (Quelle, wird nach `.claude/cloud_bootstrap.py` kopiert) | CREATE | Cloud-Startbaustein: Pin lesen, Cache prüfen, bei Bedarf Tag klonen + SHA prüfen (atomar, flock), Skript mit `CLAUDE_PLUGIN_ROOT=<cache>` und durchgereichtem stdin starten, Exit-Code weitergeben; Fehlschlag: PreToolUse Edit/Write/MultiEdit/NotebookEdit und Bash (außer Lese-Whitelist und `--retry`) blocken, übrige Events Exit 0; SessionStart warnt per additionalContext |
| `scripts/sync_cloud_hooks.py` | MODIFY | Generator um Modus „consumer“ erweitern (Kommando → `python3 "${CLAUDE_PROJECT_DIR}/.claude/cloud_bootstrap.py" <script> [args]`), eine Quelle `hooks.json` |
| `setup.py` | MODIFY | Option `--cloud-gates` (und bei `--update` im Plugin-Modus): Baustein kopieren, Einträge mergen (Merge-Schlüssel für Baustein-Einträge), `cloud_ref`/`cloud_sha` in `.claude/framework_version.json`, plugin_mode-Zweig von `update_project` erhält die Schlüssel |
| `core/hooks/edit_gate.py`, `core/hooks/bash_gate.py` | MODIFY | `.claude/cloud_bootstrap.py` und `.claude/framework_version.json` als geschützte Pfade (sonst schreibt sich das Modell das Gate weg) |
| `tests/test_cloud_gates_522.py` | CREATE | Einheiten- und Ende-zu-Ende-Tests mit lokalem `file://`-Fake-Tag-Repo |
| `README.md`, `CHANGELOG.md` | MODIFY | Weg beschreiben, #522 |

### Scope Assessment
- Dateien: 7 (1 neu Code, 1 neu Test), ~+280 LoC Code, ~+350 LoC Tests
- Risk Level: HIGH (Hook-Ausführung in allen Konsumenten, Gate-Code)

### Technical Approach
1. Kommando je Hook in der Konsumenten-settings.json:
   `[ "$CLAUDE_CODE_REMOTE" != "true" ] || python3 "${CLAUDE_PROJECT_DIR}/.claude/cloud_bootstrap.py" <script>.py [args]`
   — lokal Exit 0 vor stdin, also nie doppelt (wie #520). Timeout je Eintrag = Original + 25 s (erster Abruf).
2. Pin in `.claude/framework_version.json` (`cloud_ref` = `agent-os-openspec--v<X.Y.Z>`, `cloud_sha` = Commit),
   nicht im Kommandotext → ein Update ändert die settings.json nicht.
3. Abruf lazy im ersten Hook-Aufruf (nicht nur SessionStart), Klon in Temp-Ordner neben dem Ziel, SHA-Abgleich, atomares Umbenennen unter flock, Marker `.ok`; Zeiger `~/.cache/agent-os-openspec/current` für Scheibe 2.
4. Fail-closed nur für schreibende Werkzeuge; Lesen bleibt möglich; Stop/PostToolUse/SessionEnd nie blockieren.
5. Nachweis DoD (a): Wegwerf-Zweig eines Konsumenten-artigen Repos, frische Cloud-Sitzung, geblockter Edit im Transkript.

### Dependencies
`hooks/hooks.json`, `setup._PLUGIN_HOOK_CMD_RE`, `setup._merge_hook_entries`, Release-Tags aus `release.yml`, Cloud-Git-Proxy.

### Scheibe 2 (eigenes Issue)
Shims (`hook_utils`/`config_loader`) und Redirect-Aliase finden den Cache über den Zeiger; Drift-Hinweis im Banner (Pin hinter Plugin-Version).

### Open Questions
- keine Produktfragen; alle Punkte technisch entschieden (Tech Lead).
