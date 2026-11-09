---
entity_id: feat-522-cloud-plugin-gates
type: feature
created: 2026-11-09
updated: 2026-11-09
status: draft
version: "1.0"
workflow: feat-522-cloud-plugin-gates
tags: [hooks, cloud, plugin-consumers, bootstrap, setup, enforcement]
---

# Gates in Cloud-Sitzungen für Plugin-Konsumenten (Issue #522)

## Approval

- [ ] Approved

## Purpose

Projekte, die das Framework als Plugin nutzen (etwa gregor_zwanzig, loose-ends), haben in Cloud-Sitzungen (Claude Code on the web) keine Gates: Die Cloud lädt keine Plugins, und die Hook-Skripte liegen im Konsumenten-Repo nicht vor. Künftig kopiert `setup.py --cloud-gates` einen kleinen Startbaustein (`.claude/cloud_bootstrap.py`) ins Projekt und trägt in dessen `.claude/settings.json` alle Hooks aus `hooks/hooks.json` ein, jeweils nur für die Cloud (`CLAUDE_CODE_REMOTE=true`). Der Baustein holt beim ersten Aufruf den im Projekt gepinnten Release-Tag des Frameworks (Tag plus Commit-SHA) in einen Cache und startet die Hook-Skripte von dort. Gelingt der Abruf nicht, sind schreibende Werkzeuge gesperrt, damit die Gates nicht still entfallen. Lokal mit installiertem Plugin läuft nichts doppelt.

## Source

- **File:** `core/cloud_bootstrap.py` (neu; Kopie im Konsumenten: `.claude/cloud_bootstrap.py`), `scripts/sync_cloud_hooks.py`, `setup.py`, `core/hooks/edit_gate.py`, `core/hooks/bash_gate.py`
- **Identifier:** `cloud_bootstrap.main`, `cloud_bootstrap.fetch`, `cloud_bootstrap.fail_response` (neu); `sync_cloud_hooks.consumer_hooks`, `sync_cloud_hooks.consumer_command` (neu); `setup.apply_cloud_gates`, `setup.resolve_cloud_pin`, `setup.merge_cloud_gate_entries` (neu), `setup.update_project` (plugin_mode-Zweig geändert), `setup.main` (Option `--cloud-gates`); `edit_gate.ORCHESTRATOR_FILES`, `bash_gate`-Schreibzielprüfung (erweitert)

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `hooks/hooks.json` | config | einzige Quelle der Hook-Liste (Event, Matcher, Reihenfolge, Timeout, Argumente) |
| `setup._PLUGIN_HOOK_CMD_RE` (#279) | regex | zerlegt `${CLAUDE_PLUGIN_ROOT}/core/hooks/<datei>.py [args]`; wird importiert, nicht kopiert |
| `setup._merge_hook_entries` (#543-Umfeld) | function | Vorbild für das idempotente Mergen in eine bestehende `settings.json` |
| `scripts/sync_cloud_hooks.py` (#520) | script | bestehende Erzeugung für dieses Repo; bleibt unverändert, bekommt eine zweite Erzeugungsart |
| `hook_utils.find_plugin_root` | function | liest `CLAUDE_PLUGIN_ROOT`; der Baustein setzt es auf den Cache-Ordner |
| `release.yml` (Tags `agent-os-openspec--vX.Y.Z`) | workflow | liefert die Tags, die gepinnt und geklont werden |
| `CLAUDE_CODE_REMOTE`, `CLAUDE_PROJECT_DIR` | env | von Claude Code gesetzt; `CLAUDE_CODE_REMOTE=true` nur in Cloud-Sitzungen |
| `git` | tool | Klon, `rev-parse`, `ls-remote`; in der Cloud-Umgebung vorhanden, sonst fail-closed |
| öffentliches Repo `henemm/agent-os-openspec` | remote | anonym klonbar (gemessen 1,5 s, ~11 MB); Voraussetzung: Umgebung erreicht github.com |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| core/cloud_bootstrap.py | CREATE | Startbaustein (nur Standardbibliothek, Python ≥ 3.8): Pin lesen, Cache holen/prüfen, Hook-Skript weiterleiten, Fehlschlag-Verhalten, `--retry` |
| scripts/sync_cloud_hooks.py | MODIFY | zweite Erzeugungsart `consumer_hooks` (Kommando über den Baustein, Timeout + 25); Erzeugung für dieses Repo (#520) unverändert |
| setup.py | MODIFY | Option `--cloud-gates`; Merge der Baustein-Einträge; Pin-Auflösung; `--update` im Plugin-Modus erhält/erneuert Baustein, Einträge und Pin |
| core/hooks/edit_gate.py | MODIFY | `.claude/cloud_bootstrap.py` und `.claude/framework_version.json` in `ORCHESTRATOR_FILES` (Schritt 1b, wie `.claude/settings.json`) |
| core/hooks/bash_gate.py | MODIFY | dieselben zwei Pfade als geschützte Schreibziele (eigene Liste, siehe Implementation Details) |
| tests/test_cloud_gates_522.py | CREATE | Einheiten- und Ende-zu-Ende-Tests mit lokalem `file://`-Repo und annotiertem Tag |
| docs/artifacts/feat-522-cloud-plugin-gates/cloud-session-events.json | CREATE | Ereignis-Export der echten Cloud-Sitzung als Nachweis (AC-16) |
| README.md | MODIFY | Abschnitt „Cloud sessions (Claude Code on the web)“: Weg für Plugin-Konsumenten statt Verweis auf #522 |
| CHANGELOG.md | MODIFY | Eintrag unter `[Unreleased]` |
| scripts/release_check.py | KEINE ÄNDERUNG | Der Konsumenten-Block wird nicht eingecheckt, sondern bei jedem `--cloud-gates`/`--update` aus `hooks/hooks.json` erzeugt; Drift ist daher nicht möglich, die Vollständigkeit prüft AC-12 |

### Estimated Changes

- Files: 3 neu (davon 1 Nachweis-Artefakt), 6 geändert
- LoC: +300 Produktion / +450 Test
- Risk Level: HIGH (führt in jedem Konsumenten-Projekt Gate-Code aus, der aus dem Netz geholt wird; schaltet bei Fehlschlag schreibende Werkzeuge ab)

## Implementation Details

**Eintragsform** je Hook in der Konsumenten-`settings.json` (aus `hooks/hooks.json`-Kommando `${CLAUDE_PLUGIN_ROOT}/core/hooks/<datei>.py<args>`):

```
[ "$CLAUDE_CODE_REMOTE" != "true" ] || python3 "${CLAUDE_PROJECT_DIR}/.claude/cloud_bootstrap.py" <datei>.py<args>
```

Event, Matcher, Reihenfolge und `type` wie im Original, `timeout` = Original + 25 s (erster Abruf; fehlt er im Original, fehlt er auch hier). Lokal endet der Befehl vor dem Lesen von stdin mit Exit 0, also läuft neben dem Plugin nichts doppelt (Verfahren wie #520). Ein Kommando, das nicht zu `_PLUGIN_HOOK_CMD_RE` passt, bricht die Erzeugung ab (kein halber Schutz).

**`core/cloud_bootstrap.py`** (Aufruf `python3 "${CLAUDE_PROJECT_DIR}/.claude/cloud_bootstrap.py" <script>.py [args]`, stdin = Hook-JSON):

1. Pin lesen: `cloud_ref` (Tag `agent-os-openspec--vX.Y.Z`) und `cloud_sha` (40 Hex-Zeichen) aus `<projekt>/.claude/framework_version.json`. Der Pin steht bewusst nicht im Kommandotext, ein Update ändert die `settings.json` nicht.
2. Cache: `<base>/<cloud_ref>` mit `<base>` = `~/.cache/agent-os-openspec` (überschreibbar per `AGENT_OS_CLOUD_CACHE`, nur für Tests). Gilt als vollständig, wenn die Marker-Datei `<cache>/.ok` existiert.
3. Fehlt der Marker: unter `fcntl.flock` auf `<base>/.lock` erneut prüfen; sonst `git clone --quiet --depth 1 --branch <cloud_ref> <url> <tmp neben dem Ziel>` (Timeout 20 s; `<url>` aus `AGENT_OS_CLOUD_REPO`, Default `https://github.com/henemm/agent-os-openspec`, `file://` nur für Tests). `git -C <tmp> rev-parse HEAD` muss `cloud_sha` ergeben, dann `<tmp>/.ok` schreiben und atomar nach `<cache>` umbenennen. Danach Zeiger `<base>/current` (Textdatei mit dem Cache-Pfad) schreiben; ihn nutzt die Folgearbeit #562.
4. Weiterleiten: `<script>` muss `[A-Za-z0-9_]+\.py` entsprechen und unter `<cache>/core/hooks/` existieren. Start mit `CLAUDE_PLUGIN_ROOT=<cache>`, unverändertem stdin und durchgereichtem stdout/stderr; Exit-Code des Skripts ist der Exit-Code des Bausteins.
5. Fehlschlag (kein Pin, Netz, Tag fehlt, SHA weicht ab, git fehlt, Skript fehlt oder ungültiger Name): Event und Werkzeug aus dem stdin-JSON (`hook_event_name`, `tool_name`):
   - PreToolUse, Grundsatz „nur Lesen“: Über die Gruppe mit leerem Matcher in `hooks/hooks.json` (`session_singleton_guard.py`, `secret_egress_guard.py`) erreicht jedes Werkzeug den Baustein. Durchgelassen (Exit 0) werden nur die lesenden Werkzeuge `Read`, `Grep`, `Glob`, `LS`, `TodoWrite`, `AskUserQuestion`, `ToolSearch` sowie Bash nach der Regel unten. Jedes andere Werkzeug (u. a. `Edit`, `Write`, `MultiEdit`, `NotebookEdit`, `WebFetch`, `WebSearch`, `Agent`/`Task`, MCP-Werkzeuge `mcp__*`) bekommt Exit 2 mit Meldung auf stderr: Grund, Abhilfe (`python3 .claude/cloud_bootstrap.py --retry`; die Umgebung muss github.com erreichen) und der PO-Ausweg aus Punkt 7. So kann ohne geladene Gates weder geschrieben noch etwas nach außen gegeben werden.
   - PreToolUse mit `Bash`: Exit 2, außer der Befehl ist exakt der Retry-Aufruf oder beginnt mit einem Lese-Befehl aus der festen Liste `git status|diff|log|show`, `ls`, `cat`, `head`, `tail`, `grep`, `rg`, `pwd` und enthält keines von `>`, `|`, `;`, `&&`, `||`, Backtick, `$(`.
   - SessionStart: Abruf versuchen; bei Fehlschlag JSON mit `hookSpecificOutput.additionalContext` (Warnung: Gates nicht geladen, schreibende Werkzeuge gesperrt, Abhilfe) und Exit 0.
   - Alle übrigen Events (Stop, PostToolUse, SessionEnd, UserPromptSubmit außer Punkt 7, Notification): Exit 0, nie blockieren.
6. CLI `--retry`: Cache für den Pin verwerfen, neu holen, Ergebnis ausgeben, Exit 0 bei Erfolg, 1 sonst.
7. PO-Ausnahme (`override`) für den Fehlschlag-Zustand, gleiche Bedienung wie überall im Framework: Der PO tippt das Wort `override` als ganze Nachricht (Groß-/Kleinschreibung und Leerraum am Rand egal).
   - Die Konsumenten-Einträge für UserPromptSubmit laufen ebenfalls über den Baustein (`phase_listener.py`). Ist der Cache nicht ladbar und lautet `prompt` im stdin-JSON `override`, schreibt der Baustein `<base>/override-<session_id>.json` mit Zeitstempel; `session_id` kommt aus dem stdin-JSON und muss `[A-Za-z0-9_-]+` entsprechen, sonst entsteht keine Ausnahme. Die Ausnahme gilt 1 Stunde und nur für diese Sitzung.
   - Der Baustein gibt per UserPromptSubmit-stdout einen kurzen Hinweis aus („Ausnahme gesetzt: Gates nicht geladen, schreibende Werkzeuge 1 h freigegeben, Abhilfe: `python3 .claude/cloud_bootstrap.py --retry`“), Exit 0.
   - Solange die Ausnahme gilt, lässt der Fehlschlag-Zweig aus Punkt 5 alle Werkzeuge durch (Exit 0); je Durchlass wird nichts Neues geschrieben. Jeder Ausnahme-Start wird als eine JSON-Zeile in `<projekt>/.claude/gate-events.jsonl` protokolliert (`hook`: `cloud_bootstrap`, `reason`: `override: gates not loaded`, dazu Zeitstempel und `session_id`).
   - Fälschungsschutz: Nur ein echter UserPromptSubmit setzt die Ausnahme. Im Fehlschlag-Zustand sind Edit/Write und schreibendes Bash gesperrt, das Modell kann die Datei also nicht selbst anlegen. Eine abgelaufene Ausnahme (älter als 1 h) oder eine fremde `session_id` zählt nicht, dann gilt wieder Punkt 5. Ist der Cache ladbar, wird die Ausnahme weder gesetzt noch ausgewertet; dann entscheiden die echten Gates samt ihrem eigenen Override-Token wie gewohnt.
   - Die Sperrmeldung aus Punkt 5 nennt den Ausweg wörtlich: „PO: `override` tippen (gilt 1 h für diese Sitzung)“.

**`scripts/sync_cloud_hooks.py`:** `consumer_hooks(hooks_json) -> dict` (reine Funktion) und `consumer_command(plugin_command)`; CLI-Schalter `--consumer` gibt den Block als JSON auf stdout aus und schreibt nichts. Ohne den Schalter und mit `--check` verhält sich das Skript wie bisher (#520).

**`setup.py --cloud-gates`** (nur Plugin-Modus-Projekte; bei Copy-Modus-Projekten Hinweis und Exit 1):
- `resolve_cloud_pin`: Tag = `agent-os-openspec--v` + Framework-Version; SHA aus `git -C <framework> rev-parse <tag>^{commit}`, ersatzweise `git ls-remote <url> refs/tags/<tag>^{}`. Nicht auflösbar: Exit 1 mit Meldung, nichts geschrieben.
- Baustein von `core/cloud_bootstrap.py` nach `<projekt>/.claude/cloud_bootstrap.py` kopieren.
- `merge_cloud_gate_entries`: Einträge in die bestehende `.claude/settings.json` mergen; erkannt werden Baustein-Einträge am Skriptnamen hinter `cloud_bootstrap.py`. Projekteigene Hooks, `enabledPlugins`, `extraKnownMarketplaces`, `permissions` und `env` bleiben unangetastet; fehlt die Datei (Fall loose-ends), wird sie mit `hooks`-Block angelegt. Bereits vorhandene Baustein-Einträge werden an ihrer Stelle erneuert, fehlende angehängt.
- `cloud_ref` und `cloud_sha` in `.claude/framework_version.json` setzen (übrige Schlüssel bleiben).
- Idempotent: ein zweiter Lauf ändert keine Datei.

**`setup.py --update` im Plugin-Modus:** Der plugin_mode-Zweig von `update_project` baut heute das Versions-Dict neu auf und würde `cloud_ref`/`cloud_sha` verlieren. Neu: sind sie gesetzt, werden sie erhalten und gemeinsam mit Baustein und Einträgen auf den Stand des aktuellen Frameworks gebracht (Pin neu aufgelöst); sind sie nicht gesetzt, bleibt das Verhalten unverändert.

**Schutzpfade (Entscheidung 4):** Ohne Schutz könnte das Modell Baustein oder Pin umschreiben und so das Gate abschalten.
- `edit_gate.py`: `ORCHESTRATOR_FILES` (Schritt 1b „Orchestrator-only Files“) bekommt `.claude/cloud_bootstrap.py` und `.claude/framework_version.json` neben `.claude/settings.json`. Die Ausnahme #543 (nur `enabledPlugins`/`extraKnownMarketplaces`) gilt weiter ausschließlich für `settings.json`; für die beiden neuen Pfade gibt es nur den Override-Token.
- `bash_gate.py`: Die zwei Pfade kommen bewusst NICHT in `PROTECTED_FILE_PATTERNS` (dort blockt schon eine bloße Erwähnung, und der Retry-Aufruf `python3 .claude/cloud_bootstrap.py --retry` würde sich selbst sperren), sondern in eine eigene Liste, die wie `PROOF_FILE_PATTERNS` nur echte Schreibziele prüft (Umleitung, `tee`, `cp`/`mv` nach dort, `sed -i`). Lesen und der Retry-Aufruf bleiben frei; Ausweg: Override.

**Testaufbau:** echte Dateien in `tmp_path`, Aufruf per `subprocess`; Fake-Framework-Repo mit `core/hooks/probe.py` (schreibt stdin, `CLAUDE_PLUGIN_ROOT` und Marker in eine Datei, Exit-Code aus stdin steuerbar), annotiertem Tag und `AGENT_OS_CLOUD_REPO=file://…`; `AGENT_OS_CLOUD_CACHE` zeigt auf `tmp_path`. Kein Mock der Shell oder von git.

**README:** Abschnitt „Cloud sessions (Claude Code on the web)“ beschreibt: Cloud lädt keine Plugins; `python3 /pfad/zu/agent-os-openspec/setup.py <projekt> --cloud-gates` einmal ausführen und die geänderten Dateien committen (`.claude/cloud_bootstrap.py`, `.claude/settings.json`, `.claude/framework_version.json`); Pin heben mit `--update`; Verhalten bei Fehlschlag und `--retry`; Voraussetzung github.com erreichbar; Grenzen aus „Known Limitations“.

**Nachweis DoD (a):** Wegwerf-Zweig eines Konsumenten-artigen Repos (z. B. `henemm/playground`) mit `setup.py --cloud-gates`, committet und gepusht; in einer frischen Cloud-Sitzung auf diesem Zweig wird ein Edit ohne Workflow von `edit_gate` geblockt. Das Transkript-Ereignis mit der Blockmeldung wird als Artefakt unter `docs/artifacts/feat-522-cloud-plugin-gates/` abgelegt.

## Expected Behavior

- **Input:** Hook-Aufruf (stdin-JSON) in einer Sitzung eines Plugin-Konsumenten, der `--cloud-gates` ausgeführt hat
- **Output:** Cloud-Sitzung: dieselben Gates wie lokal mit Plugin, geladen aus dem gepinnten Tag; Exit-Code und Ausgabe des Hook-Skripts werden unverändert weitergegeben. Lokale Sitzung: die Baustein-Einträge enden sofort mit Exit 0, es läuft nur die Plugin-Kopie. Abruf gescheitert: schreibende Werkzeuge gesperrt mit Meldung samt Abhilfe und dem Ausweg „PO: `override` tippen (gilt 1 h für diese Sitzung)“, SessionStart warnt, alles andere läuft weiter. Tippt der PO `override`, sind schreibende Werkzeuge für diese Sitzung 1 Stunde freigegeben, der Vorgang steht im Protokoll.
- **Side effects:** Cache unter `~/.cache/agent-os-openspec/` (Klon, `.ok`, `current`, `.lock`, `override-<session_id>.json`); Zeile in `.claude/gate-events.jsonl` bei jeder Ausnahme; im Projekt: `.claude/cloud_bootstrap.py`, erweiterte `.claude/settings.json`, `cloud_ref`/`cloud_sha` in `.claude/framework_version.json`.

## Known Limitations

- Solange die Gates nicht geladen sind, fehlen auch die Secret-Wächter (`secrets_guard.py`, `secret_egress_guard.py`) für die erlaubten Lese-Werkzeuge: `Read` einer Datei mit Zugangsdaten wird dann nicht geblockt. Weitergeben kann das Modell den Inhalt in diesem Zustand nicht, weil alle schreibenden und nach außen gehenden Werkzeuge gesperrt sind; mit PO-Ausnahme (`override`) gilt diese Sperre bewusst nicht.
- Alle Einträge aus `hooks/hooks.json` laufen über den Baustein, auch die Hilfs-Hooks `process_watchdog.py` (PostToolUse Bash, SessionEnd) und `herdr_bridge.py` (Seitenleiste). Sie sind fail-open: In der Cloud gibt es kein herdr, `herdr_bridge.py` endet dort wie lokal ohne herdr still mit Exit 0. Bei fehlgeschlagenem Abruf gelten für sie die Regeln aus Punkt 5 (keine Schreib-Werkzeuge, also Exit 0).

- Cloud-„project threads“ führen laut Claude-Code-Doku keine Repo-Hooks aus (Hooks kommen dort aus server-verwalteten Settings); im Repo nicht lösbar.
- Umgebung ohne Netz oder ohne github.com: Der Abruf scheitert, die Sitzung läuft fail-closed (schreibende Werkzeuge gesperrt, Lesen möglich); Abhilfe ist die Netzfreigabe plus `--retry`.
- Wer lokal `CLAUDE_CODE_REMOTE=true` von Hand setzt, bekommt Doppelläufe neben dem Plugin; das Modell kann die Umgebung des Hook-Prozesses nicht ändern.
- Der Pin hinkt dem lokalen `autoUpdate@main` des Plugins hinterher, bis `setup.py --update` ausgeführt wird; die Cloud nutzt bewusst einen festen Release-Stand.
- Die Hook-Skripte des Frameworks importieren `hook_utils`/`config_loader` aus demselben Ordner und laufen deshalb aus dem Cache; die Shims der Konsumenten-Projekte (`.claude/hooks/hook_utils.py`), die Redirect-Aliase und der Drift-Hinweis im Banner sind außerhalb des Umfangs (Folge-Issue #562).

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt; bei AC-16 prüft der Test den Inhalt des eingecheckten Transkript-Artefakts aus der echten Cloud-Sitzung
- [ ] In einer frischen Cloud-Sitzung eines Konsumenten-artigen Wegwerf-Zweigs blockt `edit_gate` einen Edit ohne Workflow; das Transkript-Ereignis liegt als Artefakt im Issue bzw. PR (AC-16)
- [ ] Der PO kann im Fehlschlag-Zustand per `override` die Sitzung 1 Stunde freigeben (AC-18 bis AC-20)
- [ ] Lokal mit installiertem Plugin läuft kein Hook doppelt (AC-2)
- [ ] `setup.py --cloud-gates` und `README.md` beschreiben den Weg für Plugin-Konsumenten
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf `pytest tests/` grün, insbesondere die Tests zu #520, #543 und #545)

## Acceptance Criteria

Testaufbau: echte Dateien in `tmp_path`, `subprocess.run` mit stdin-JSON, lokales `file://`-Repo mit annotiertem Tag als Framework-Quelle.

- **AC-1:** Given ein Fake-Framework-Repo mit annotiertem Tag und passendem Pin in `framework_version.json` / When der Baustein mit `probe.py` und einer stdin-Payload aufgerufen wird, deren Probe mit Exit 2 endet / Then wird der Tag geklont, `probe.py` startet mit `CLAUDE_PLUGIN_ROOT=<cache>` und vollständig angekommenem stdin, stdout/stderr werden durchgereicht und der Exit-Code des Bausteins ist 2
  - Test: tests/test_cloud_gates_522.py::test_bootstrap_fetches_tag_and_forwards_stdin_and_exit_code

- **AC-2:** Given ein erzeugter Konsumenten-Eintrag mit Pfad zum Projekt (mit Leerzeichen im Pfad) / When der Befehl ohne `CLAUDE_CODE_REMOTE`, mit `CLAUDE_CODE_REMOTE=false` und mit `CLAUDE_CODE_REMOTE=true` läuft / Then endet er in den ersten beiden Fällen mit Exit 0, ohne dass Baustein oder Cache berührt werden, und im dritten Fall startet das Hook-Skript
  - Test: tests/test_cloud_gates_522.py::test_command_runs_only_in_cloud

- **AC-3:** Given ein Pin, dessen `cloud_sha` nicht zum geklonten Tag-Commit passt / When der Baustein für ein Edit-PreToolUse-Event läuft / Then Exit 2 mit Meldung zur SHA-Abweichung, kein `.ok`-Marker und kein Cache-Ordner bleiben zurück, und `probe.py` wurde nicht gestartet
  - Test: tests/test_cloud_gates_522.py::test_sha_mismatch_fails_closed_and_leaves_no_cache

- **AC-4:** Given ein nicht abrufbarer Tag, ein fehlender Pin oder ein nicht existierendes Skript / When der Baustein für PreToolUse mit `Edit`, `Write`, `MultiEdit`, `NotebookEdit`, `WebFetch`, `Agent` und `mcp__github__issue_write` läuft / Then Exit 2 und die stderr-Meldung nennt Grund, Abhilfe `python3 .claude/cloud_bootstrap.py --retry` samt Hinweis auf github.com und den PO-Ausweg `override`; für `Read`, `Grep`, `Glob` Exit 0
  - Test: tests/test_cloud_gates_522.py::test_fetch_failure_blocks_write_tools

- **AC-5:** Given ein fehlgeschlagener Abruf / When der Baustein für PreToolUse Bash mit (a) `python3 .claude/cloud_bootstrap.py --retry`, (b) `git status`, `ls -la`, `grep foo src` und (c) `echo x > f`, `ls; rm f`, `cat a | sh`, `git log $(id)`, `touch f` läuft / Then Exit 0 für (a) und (b), Exit 2 für (c)
  - Test: tests/test_cloud_gates_522.py::test_bash_whitelist_and_retry_when_fetch_failed

- **AC-6:** Given ein fehlgeschlagener Abruf / When der Baustein für Stop, PostToolUse, SessionEnd, UserPromptSubmit und PreToolUse mit Read oder Grep läuft / Then Exit 0 ohne Blockade, auch bei unlesbarem stdin
  - Test: tests/test_cloud_gates_522.py::test_non_write_events_never_blocked

- **AC-7:** Given ein fehlgeschlagener Abruf / When der Baustein für SessionStart läuft / Then Exit 0 und stdout ist JSON mit `hookSpecificOutput.additionalContext`, der Gates nicht geladen, gesperrte schreibende Werkzeuge und die Abhilfe nennt; bei erfolgreichem Abruf startet stattdessen `session_banner.py` aus dem Cache und es erscheint keine Warnung
  - Test: tests/test_cloud_gates_522.py::test_session_start_warns_on_failure_and_forwards_on_success

- **AC-8:** Given leerer Cache und mehrere gleichzeitig gestartete Baustein-Prozesse / When alle denselben Hook aufrufen / Then gibt es genau einen Klon-Vorgang, alle Prozesse erhalten das Skriptergebnis, `<cache>/.ok` existiert, kein halber Cache-Ordner und kein temporärer Ordner bleibt zurück
  - Test: tests/test_cloud_gates_522.py::test_concurrent_calls_fetch_once_and_leave_valid_cache

- **AC-9:** Given ein gültiger Cache / When der Baustein erneut läuft, auch ohne erreichbare Quelle, sowie wenn `--retry` aufgerufen wird / Then nutzt der erste Lauf den Cache ohne Netzzugriff und `--retry` verwirft ihn, holt neu und endet mit Exit 0 (bei unerreichbarer Quelle mit Exit 1); der Zeiger `<base>/current` nennt den Cache-Pfad
  - Test: tests/test_cloud_gates_522.py::test_cache_reuse_and_retry_and_current_pointer

- **AC-10:** Given ein Plugin-Modus-Projekt mit eigenen Hooks, `enabledPlugins`, `permissions` und `env` in der `settings.json` / When `setup.py <projekt> --cloud-gates` zweimal läuft / Then enthält `.claude/cloud_bootstrap.py` den Baustein, die Baustein-Einträge stehen in `settings.json`, alle projekteigenen Schlüssel und Hooks sind unverändert, und der zweite Lauf ändert kein Byte
  - Test: tests/test_cloud_gates_522.py::test_cloud_gates_merges_and_is_idempotent

- **AC-11:** Given ein Plugin-Modus-Projekt ohne `.claude/settings.json` (Fall loose-ends) / When `setup.py <projekt> --cloud-gates` läuft / Then wird die Datei mit dem vollständigen `hooks`-Block angelegt und `framework_version.json` enthält `cloud_ref` (Tag `agent-os-openspec--v<Version>`) und `cloud_sha` (40 Hex-Zeichen); ein Copy-Modus-Projekt wird mit Hinweis und Exit 1 abgewiesen
  - Test: tests/test_cloud_gates_522.py::test_cloud_gates_creates_missing_settings_and_rejects_copy_mode

- **AC-12:** Given `hooks/hooks.json` dieses Repos / When `sync_cloud_hooks.consumer_hooks` läuft / Then enthält das Ergebnis jedes Event, jede Gruppe mit gleichem Matcher und jeden Eintrag in derselben Reihenfolge, jedes `command` hat die Form `[ "$CLAUDE_CODE_REMOTE" != "true" ] || python3 "${CLAUDE_PROJECT_DIR}/.claude/cloud_bootstrap.py" <datei>.py<args>`, `timeout` ist Original + 25 (fehlt er im Original, fehlt er auch im Ergebnis; dann gilt der Claude-Code-Default, laut code.claude.com/docs/en/cloud-environments.md 600 s; heute haben alle Einträge in `hooks/hooks.json` einen Timeout), und ein nicht zerlegbares Kommando bricht mit Fehler ab; `scripts/sync_cloud_hooks.py --check` für dieses Repo (#520) bleibt unverändert grün
  - Test: tests/test_cloud_gates_522.py::test_consumer_hooks_mirror_hooks_json_completely

- **AC-13:** Given ein Tag, der im lokalen Framework-Checkout nicht auflösbar ist, aber per `git ls-remote` auf dem Remote existiert (annotiert) / When die Pin-Auflösung läuft / Then liefert sie die Commit-SHA des Tags (den Commit, nicht das Tag-Objekt)
  - Test: tests/test_cloud_gates_522.py::test_pin_resolution_falls_back_to_ls_remote

- **AC-21:** Given ein Tag, der weder lokal noch auf dem Remote existiert / When `setup.py <projekt> --cloud-gates` läuft / Then Exit 1 mit Meldung, und keine Datei im Projekt wird geschrieben oder geändert
  - Test: tests/test_cloud_gates_522.py::test_unresolvable_pin_writes_nothing

- **AC-14:** Given ein Plugin-Modus-Projekt mit gesetztem `cloud_ref`/`cloud_sha` und veraltetem Baustein / When `setup.py <projekt> --update` läuft / Then bleiben `cloud_ref` und `cloud_sha` erhalten (neu aufgelöst auf den aktuellen Tag), Baustein und Einträge sind erneuert, `plugin_mode` bleibt `true`; ohne gesetzten Pin schreibt `--update` weder Baustein noch Einträge noch Pin
  - Test: tests/test_cloud_gates_522.py::test_update_in_plugin_mode_keeps_and_refreshes_pin

- **AC-15:** Given ein aktiver Workflow bzw. ein Hook-Aufruf per Edit/Write und per Bash / When versucht wird, `.claude/cloud_bootstrap.py` oder `.claude/framework_version.json` zu schreiben (Edit/Write, Umleitung, `tee`, `sed -i`, `cp`) / Then blocken `edit_gate` und `bash_gate` ohne Override, mit Override-Token geht es durch; das Lesen (`cat`) und der Aufruf `python3 .claude/cloud_bootstrap.py --retry` bleiben erlaubt, und die Änderung nur von `enabledPlugins` in `settings.json` (#543) funktioniert weiter
  - Test: tests/test_cloud_gates_522.py::test_gates_protect_bootstrap_and_pin_files

- **AC-16:** Given ein Wegwerf-Zweig eines Konsumenten-artigen Repos mit `setup.py --cloud-gates` / When in einer frischen Cloud-Sitzung auf diesem Zweig ein Edit ohne Workflow versucht wird / Then blockt `edit_gate` ihn, und das Transkript-Ereignis liegt als Artefakt `docs/artifacts/feat-522-cloud-plugin-gates/cloud-session-events.json` vor: unverändert per `list_events` aus der Sitzung exportiert, mit Sitzungs-ID, dem Edit-Werkzeugaufruf und dem zugehörigen Ergebnis, das die Blockmeldung von `edit_gate` (`BLOCKED`) enthält. Automatisch geprüft wird der Inhalt dieses Exports (Edit-Aufruf und dazu gehörendes Ergebnis mit `BLOCKED`), nicht der Live-Lauf selbst
  - Test: tests/test_cloud_gates_522.py::test_cloud_session_proof_artifact_present

- **AC-17:** Given `README.md` und `CHANGELOG.md` / When gelesen / Then beschreibt der Abschnitt zu Cloud-Sitzungen den Weg für Plugin-Konsumenten mit `--cloud-gates`, `cloud_bootstrap.py`, `--retry` und `github.com`, verweist nicht mehr auf #522 als offen, und `[Unreleased]` enthält einen Eintrag, der `#522` nennt
  - Test: tests/test_cloud_gates_522.py::test_readme_and_changelog_document_cloud_gates

- **AC-18:** Given ein fehlgeschlagener Abruf / When der Baustein für UserPromptSubmit mit `prompt` `  Override ` (Rand-Leerraum, andere Schreibweise) und gültiger `session_id` läuft / Then Exit 0, stdout enthält den Hinweis „Ausnahme gesetzt“, `<base>/override-<session_id>.json` mit Zeitstempel existiert, `<projekt>/.claude/gate-events.jsonl` hat genau eine neue Zeile mit `hook` `cloud_bootstrap` und `reason` `override: gates not loaded`, und die Sperrmeldung der schreibenden Werkzeuge nennt wörtlich „PO: `override` tippen (gilt 1 h für diese Sitzung)“
  - Test: tests/test_cloud_gates_522.py::test_override_prompt_sets_session_exception_and_logs

- **AC-19:** Given eine gesetzte Ausnahme für Sitzung A bei fehlgeschlagenem Abruf / When der Baustein für PreToolUse mit Edit, Write, MultiEdit, WebFetch und Bash (auch `echo x > f`) mit `session_id` A läuft / Then Exit 0 und es entsteht keine zusätzliche Datei und keine weitere Protokollzeile; mit `session_id` B oder mit einer um mehr als 1 Stunde zurückdatierten Ausnahmedatei dagegen wieder Exit 2 mit der Sperrmeldung
  - Test: tests/test_cloud_gates_522.py::test_exception_allows_writes_only_for_same_session_within_one_hour

- **AC-20:** Given ein ladbarer Cache oder ein Prompt, der nicht ausschließlich `override` lautet (etwa `bitte override setzen`) oder eine ungültige `session_id` (`../x`) / When der Baustein für UserPromptSubmit läuft / Then wird keine Ausnahmedatei geschrieben und keine Protokollzeile angelegt; bei ladbarem Cache läuft `phase_listener.py` aus dem Cache mit durchgereichtem stdin, und schreibende Werkzeuge entscheiden allein die echten Gates
  - Test: tests/test_cloud_gates_522.py::test_override_never_set_when_cache_loadable_or_prompt_not_exact

## Test Plan

Automatische Tests (jeweils an eine AC oben gebunden):

- `pytest tests/test_cloud_gates_522.py`
- Regression der Nachbarbereiche: `pytest tests/test_cloud_hooks_520.py tests/test_copy_mode_hooks_279.py tests/test_hook_paths_project_dir_165.py tests/test_release_check_93.py` sowie alle Tests zu #543 und #545 (Schutzpfade) und `tests/test_session_singleton*`
- `python3 scripts/sync_cloud_hooks.py --check` und `python3 scripts/release_check.py --no-tests`
- Regressionslauf: `pytest tests/`
- Nachweis AC-16: einmalig in einer echten Cloud-Sitzung; der Ereignis-Export wird eingecheckt, der Test prüft Sitzungs-ID, den Edit-Aufruf und die `edit_gate`-Blockmeldung im zugehörigen Ergebnis

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Kein neues Gate und keine neue Regel; dieselben Hooks bekommen für Plugin-Konsumenten einen zweiten, dokumentierten Ladeweg in der Cloud, abgeleitet aus der einen Quelle `hooks/hooks.json` (wie #279 und #520). Gewählt: gepinnter Abruf des Release-Tags in einen Cache plus kleiner, eingecheckter Startbaustein. Gegenüber Vendoring (`.claude/framework/`) spart das rund 2,4 MB und den Diff-Lärm bei jedem Update im Konsumenten-Repo; der Preis ist ein Netzzugriff je Container (gemessen 1,5 s) und die Abhängigkeit von github.com. Tag plus Commit-SHA schließen aus, dass ein verschobener Tag fremden Code einschleust. Fail-closed gilt nur für schreibende Werkzeuge: Eine vollständig gesperrte Sitzung wäre unbenutzbar, ein stillschweigend ausfallendes Gate wäre die Sicherheitslücke selbst. Damit fail-closed den PO nicht aussperrt, gibt es eine Ausnahme im Stil des Framework-Overrides: Das Wort `override` als echter Prompt gibt schreibende Werkzeuge für genau diese Sitzung 1 Stunde frei, protokolliert in `.claude/gate-events.jsonl`. Sie ist fälschungssicher, weil nur ein UserPromptSubmit sie setzt und das Modell im gesperrten Zustand die Datei nicht schreiben kann; sie gilt nie bei ladbarem Cache, dort entscheiden die echten Gates samt eigenem Override-Token. Der Preis: Während dieser Stunde läuft die Sitzung ohne Gates, bewusst und vom PO ausgelöst. Verworfen: (a) Setup-Skript der Umgebung installiert das Plugin — laut Doku lädt die Cloud Plugins nicht, außerdem liegt es außerhalb des Repos und ist nicht versioniert; (b) Hooks ohne Cloud-Bedingung — lokal doppelte Ausführung neben dem Plugin; (c) Pin im Kommandotext — jedes Update würde die `settings.json` umschreiben. Reversibel: Baustein und Einträge lassen sich entfernen, das Plugin bleibt unberührt.

## Changelog

- 2026-11-09: Initial spec created
