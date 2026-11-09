# Adversary Dialog — feat-522-cloud-plugin-gates
Spec: docs/specs/feat-522-cloud-plugin-gates.md
Datum: 2026-11-09 20:16

## Checkliste
- [x] **Input:** Hook-Aufruf (stdin-JSON) in einer Sitzung eines Plugin-Konsumenten, der `--cloud-gates` ausgeführt hat
- [x] **Output:** Cloud-Sitzung: dieselben Gates wie lokal mit Plugin, geladen aus dem gepinnten Tag; Exit-Code und Ausgabe des Hook-Skripts werden unverändert weitergegeben. Lokale Sitzung: die Baustein-Einträge enden sofort mit Exit 0, es läuft nur die Plugin-Kopie. Abruf gescheitert: schreibende Werkzeuge gesperrt mit Meldung samt Abhilfe und dem Ausweg „PO: `override` tippen (gilt 1 h für diese Sitzung)“, SessionStart warnt, alles andere läuft weiter. Tippt der PO `override`, sind schreibende Werkzeuge für diese Sitzung 1 Stunde freigegeben, der Vorgang steht im Protokoll.
- [x] **Side effects:** Cache unter `~/.cache/agent-os-openspec/` (Klon, `.ok`, `current`, `.lock`, `override-<session_id>.json`); Zeile in `.claude/gate-events.jsonl` bei jeder Ausnahme; im Projekt: `.claude/cloud_bootstrap.py`, erweiterte `.claude/settings.json`, `cloud_ref`/`cloud_sha` in `.claude/framework_version.json`.
- [x] **AC-1:** Given ein Fake-Framework-Repo mit annotiertem Tag und passendem Pin in `framework_version.json` / When der Baustein mit `probe.py` und einer stdin-Payload aufgerufen wird, deren Probe mit Exit 2 endet / Then wird der Tag geklont, `probe.py` startet mit `CLAUDE_PLUGIN_ROOT=<cache>` und vollständig angekommenem stdin, stdout/stderr werden durchgereicht und der Exit-Code des Bausteins ist 2
- [x] **AC-2:** Given ein erzeugter Konsumenten-Eintrag mit Pfad zum Projekt (mit Leerzeichen im Pfad) / When der Befehl ohne `CLAUDE_CODE_REMOTE`, mit `CLAUDE_CODE_REMOTE=false` und mit `CLAUDE_CODE_REMOTE=true` läuft / Then endet er in den ersten beiden Fällen mit Exit 0, ohne dass Baustein oder Cache berührt werden, und im dritten Fall startet das Hook-Skript
- [x] **AC-3:** Given ein Pin, dessen `cloud_sha` nicht zum geklonten Tag-Commit passt / When der Baustein für ein Edit-PreToolUse-Event läuft / Then Exit 2 mit Meldung zur SHA-Abweichung, kein `.ok`-Marker und kein Cache-Ordner bleiben zurück, und `probe.py` wurde nicht gestartet
- [x] **AC-4:** Given ein nicht abrufbarer Tag, ein fehlender Pin oder ein nicht existierendes Skript / When der Baustein für PreToolUse mit `Edit`, `Write`, `MultiEdit`, `NotebookEdit`, `WebFetch`, `Agent` und `mcp__github__issue_write` läuft / Then Exit 2 und die stderr-Meldung nennt Grund, Abhilfe `python3 .claude/cloud_bootstrap.py --retry` samt Hinweis auf github.com und den PO-Ausweg `override`; für `Read`, `Grep`, `Glob` Exit 0
- [x] **AC-5:** Given ein fehlgeschlagener Abruf / When der Baustein für PreToolUse Bash mit (a) `python3 .claude/cloud_bootstrap.py --retry`, (b) `git status`, `ls -la`, `grep foo src` und (c) `echo x > f`, `ls; rm f`, `cat a | sh`, `git log $(id)`, `touch f` läuft / Then Exit 0 für (a) und (b), Exit 2 für (c)
- [x] **AC-6:** Given ein fehlgeschlagener Abruf / When der Baustein für Stop, PostToolUse, SessionEnd, UserPromptSubmit und PreToolUse mit Read oder Grep läuft / Then Exit 0 ohne Blockade, auch bei unlesbarem stdin
- [x] **AC-7:** Given ein fehlgeschlagener Abruf / When der Baustein für SessionStart läuft / Then Exit 0 und stdout ist JSON mit `hookSpecificOutput.additionalContext`, der Gates nicht geladen, gesperrte schreibende Werkzeuge und die Abhilfe nennt; bei erfolgreichem Abruf startet stattdessen `session_banner.py` aus dem Cache und es erscheint keine Warnung
- [x] **AC-8:** Given leerer Cache und mehrere gleichzeitig gestartete Baustein-Prozesse / When alle denselben Hook aufrufen / Then gibt es genau einen Klon-Vorgang, alle Prozesse erhalten das Skriptergebnis, `<cache>/.ok` existiert, kein halber Cache-Ordner und kein temporärer Ordner bleibt zurück
- [x] **AC-9:** Given ein gültiger Cache / When der Baustein erneut läuft, auch ohne erreichbare Quelle, sowie wenn `--retry` aufgerufen wird / Then nutzt der erste Lauf den Cache ohne Netzzugriff und `--retry` verwirft ihn, holt neu und endet mit Exit 0 (bei unerreichbarer Quelle mit Exit 1); der Zeiger `<base>/current` nennt den Cache-Pfad
- [x] **AC-10:** Given ein Plugin-Modus-Projekt mit eigenen Hooks, `enabledPlugins`, `permissions` und `env` in der `settings.json` / When `setup.py <projekt> --cloud-gates` zweimal läuft / Then enthält `.claude/cloud_bootstrap.py` den Baustein, die Baustein-Einträge stehen in `settings.json`, alle projekteigenen Schlüssel und Hooks sind unverändert, und der zweite Lauf ändert kein Byte
- [x] **AC-11:** Given ein Plugin-Modus-Projekt ohne `.claude/settings.json` (Fall loose-ends) / When `setup.py <projekt> --cloud-gates` läuft / Then wird die Datei mit dem vollständigen `hooks`-Block angelegt und `framework_version.json` enthält `cloud_ref` (Tag `agent-os-openspec--v<Version>`) und `cloud_sha` (40 Hex-Zeichen); ein Copy-Modus-Projekt wird mit Hinweis und Exit 1 abgewiesen
- [x] **AC-12:** Given `hooks/hooks.json` dieses Repos / When `sync_cloud_hooks.consumer_hooks` läuft / Then enthält das Ergebnis jedes Event, jede Gruppe mit gleichem Matcher und jeden Eintrag in derselben Reihenfolge, jedes `command` hat die Form `[ "$CLAUDE_CODE_REMOTE" != "true" ] || python3 "${CLAUDE_PROJECT_DIR}/.claude/cloud_bootstrap.py" <datei>.py<args>`, `timeout` ist Original + 25 (fehlt er im Original, fehlt er auch im Ergebnis; dann gilt der Claude-Code-Default, laut code.claude.com/docs/en/cloud-environments.md 600 s; heute haben alle Einträge in `hooks/hooks.json` einen Timeout), und ein nicht zerlegbares Kommando bricht mit Fehler ab; `scripts/sync_cloud_hooks.py --check` für dieses Repo (#520) bleibt unverändert grün
- [x] **AC-13:** Given ein Tag, der im lokalen Framework-Checkout nicht auflösbar ist, aber per `git ls-remote` auf dem Remote existiert (annotiert) / When die Pin-Auflösung läuft / Then liefert sie die Commit-SHA des Tags (den Commit, nicht das Tag-Objekt)
- [x] **AC-21:** Given ein Tag, der weder lokal noch auf dem Remote existiert / When `setup.py <projekt> --cloud-gates` läuft / Then Exit 1 mit Meldung, und keine Datei im Projekt wird geschrieben oder geändert
- [x] **AC-14:** Given ein Plugin-Modus-Projekt mit gesetztem `cloud_ref`/`cloud_sha` und veraltetem Baustein / When `setup.py <projekt> --update` läuft / Then bleiben `cloud_ref` und `cloud_sha` erhalten (neu aufgelöst auf den aktuellen Tag), Baustein und Einträge sind erneuert, `plugin_mode` bleibt `true`; ohne gesetzten Pin schreibt `--update` weder Baustein noch Einträge noch Pin
- [x] **AC-15:** Given ein aktiver Workflow bzw. ein Hook-Aufruf per Edit/Write und per Bash / When versucht wird, `.claude/cloud_bootstrap.py` oder `.claude/framework_version.json` zu schreiben (Edit/Write, Umleitung, `tee`, `sed -i`, `cp`) / Then blocken `edit_gate` und `bash_gate` ohne Override, mit Override-Token geht es durch; das Lesen (`cat`) und der Aufruf `python3 .claude/cloud_bootstrap.py --retry` bleiben erlaubt, und die Änderung nur von `enabledPlugins` in `settings.json` (#543) funktioniert weiter
- [x] **AC-16:** Given ein Wegwerf-Zweig eines Konsumenten-artigen Repos mit `setup.py --cloud-gates` / When in einer frischen Cloud-Sitzung auf diesem Zweig ein Edit ohne Workflow versucht wird / Then blockt `edit_gate` ihn, und das Transkript-Ereignis liegt als Artefakt `docs/artifacts/feat-522-cloud-plugin-gates/cloud-session-events.json` vor: unverändert per `list_events` aus der Sitzung exportiert, mit Sitzungs-ID, dem Edit-Werkzeugaufruf und dem zugehörigen Ergebnis, das die Blockmeldung von `edit_gate` (`BLOCKED`) enthält. Automatisch geprüft wird der Inhalt dieses Exports (Edit-Aufruf und dazu gehörendes Ergebnis mit `BLOCKED`), nicht der Live-Lauf selbst
- [x] **AC-17:** Given `README.md` und `CHANGELOG.md` / When gelesen / Then beschreibt der Abschnitt zu Cloud-Sitzungen den Weg für Plugin-Konsumenten mit `--cloud-gates`, `cloud_bootstrap.py`, `--retry` und `github.com`, verweist nicht mehr auf #522 als offen, und `[Unreleased]` enthält einen Eintrag, der `#522` nennt
- [x] **AC-18:** Given ein fehlgeschlagener Abruf / When der Baustein für UserPromptSubmit mit `prompt` `  Override ` (Rand-Leerraum, andere Schreibweise) und gültiger `session_id` läuft / Then Exit 0, stdout enthält den Hinweis „Ausnahme gesetzt“, `<base>/override-<session_id>.json` mit Zeitstempel existiert, `<projekt>/.claude/gate-events.jsonl` hat genau eine neue Zeile mit `hook` `cloud_bootstrap` und `reason` `override: gates not loaded`, und die Sperrmeldung der schreibenden Werkzeuge nennt wörtlich „PO: `override` tippen (gilt 1 h für diese Sitzung)“
- [x] **AC-19:** Given eine gesetzte Ausnahme für Sitzung A bei fehlgeschlagenem Abruf / When der Baustein für PreToolUse mit Edit, Write, MultiEdit, WebFetch und Bash (auch `echo x > f`) mit `session_id` A läuft / Then Exit 0 und es entsteht keine zusätzliche Datei und keine weitere Protokollzeile; mit `session_id` B oder mit einer um mehr als 1 Stunde zurückdatierten Ausnahmedatei dagegen wieder Exit 2 mit der Sperrmeldung
- [x] **AC-20:** Given ein ladbarer Cache oder ein Prompt, der nicht ausschließlich `override` lautet (etwa `bitte override setzen`) oder eine ungültige `session_id` (`../x`) / When der Baustein für UserPromptSubmit läuft / Then wird keine Ausnahmedatei geschrieben und keine Protokollzeile angelegt; bei ladbarem Cache läuft `phase_listener.py` aus dem Cache mit durchgereichtem stdin, und schreibende Werkzeuge entscheiden allein die echten Gates

## Dialog

### Runde 1
**Adversary:** Lauf 4, Kurz-Prüfung nur des F008-Fixes (PO-Entscheidung). Nicht neu geprüfte Checklisten-Punkte (Input, Output, Side effects, AC-1 bis AC-15, AC-17 bis AC-21) sind in Lauf 1–3 belegt (`adversary-dialog-run1.md`, `-run2.md`, `-run3.md`) und hier nur durch die Regression der Zielsuite erneut gedeckt. AC-16 (Live-Export aus Cloud-Sitzung) bleibt offen wie vereinbart. F009 ist als #564 ausgelagert und nicht Gegenstand.

Fix-Stellen gelesen:
Code reference: scripts/sync_cloud_hooks.py:76
(`CONSUMER_COMMAND` erzeugt jetzt `python3 -I "${CLAUDE_PROJECT_DIR}/.claude/cloud_bootstrap.py" <datei>.py<args>`)
Code reference: core/cloud_bootstrap.py:45
(`_strip_script_dir`: ohne `-I`/`-P` wird `sys.path[0]` gelöscht, dann `''`/`'.'` und jede realpath-gleiche Schreibweise des Skriptordners; Aufruf Zeile 59 vor allen Nicht-Builtin-Imports ab Zeile 62, `from __future__` entfernt, einziger Import davor ist das Builtin `sys`)
Code reference: core/cloud_bootstrap.py:304
(Kindprozess `sys.executable -E -s -B <skript>`)

F008 selbst nachgestellt (Test-Hilfen `_ctx`, `_hijack_run`, `_evil_module` aus der Testdatei, Edit-PreToolUse, Probe-Exit 2; Skript `/tmp/claude-0/-home-user-agent-os-openspec/a3bf6853-0157-5004-90ae-6e21b8403818/scratchpad/adv4/probe_f008.py`):
- a) Erzeugtes Kommando (mit `-I`), Shadow-Datei `.claude/<m>.py` für 28 Module: alle Stdlib-Importe des Bausteins (`json`, `os`, `re`, `hashlib`, `shlex`, `shutil`, `subprocess`, `time`, `datetime`, `pathlib`, `fcntl`, `__future__`) plus transitive bzw. Startmodule (`io`, `abc`, `codecs`, `encodings`, `site`, `sitecustomize`, `usercustomize`, `selectors`, `signal`, `threading`, `contextlib`, `warnings`, `locale`, `tempfile`, `fnmatch`, `errno`) und Paket-Variante `.claude/json/__init__.py`: jeweils rc=2, Probe genau 1x gelaufen, Marker-Datei nicht entstanden.
- b) Erzeugtes Kommando mit `PYTHONPATH=<shadow>` (`json`, `os`, `sitecustomize`): rc=2, kein Marker.
- c) Alter Eintrag ohne `-I` (`OLD_CONSUMER_PREFIX`), dieselben 28 Module plus Paket: rc=2, kein Marker. Auch Aufruf relativ `python3 .claude/cloud_bootstrap.py`, `python3 ./.claude/../.claude/cloud_bootstrap.py`, mit `PYTHONSAFEPATH=1` und mit `PYTHONPATH` = Symlink auf `.claude/`: rc=2, kein Marker (realpath-Vergleich greift).
- Kindprozess: `json.py` im Projekt-Root (cwd des Kindes) und `PYTHONPATH`/`PYTHONSTARTUP` auf Shadow-Ordner: rc=2, kein Marker (`-E`, Skriptordner ist der hash-geprüfte Cache).

Neue Tests decken a/b/c ab:
Code reference: tests/test_cloud_gates_522.py:431
Code reference: tests/test_cloud_gates_522.py:440
Code reference: tests/test_cloud_gates_522.py:451

Restgrenze (kein Befund): alter Eintrag ohne `-I` UND `PYTHONPATH` auf einen beliebigen fremden Ordner bleibt kaperbar (rc=0 bzw. 1, Marker entstand). Das Modell setzt die Hook-Umgebung nicht (Bewertung wie Lauf 3), und `--update` ersetzt Alt-Einträge: nachgestellt mit `merge_cloud_gate_entries` auf einen settings-Block aus 23 Alt-Einträgen plus einem projekteigenen Hook, Ergebnis 23 Einträge mit `-I`, 0 alte, eigener Hook erhalten.
Code reference: setup.py:905

```
Confirmation:
  AC: Output (F008-Fix, dieselben Gates aus dem gepinnten Tag)
  Code reference: core/cloud_bootstrap.py:59
  Evidence: Bereinigung von sys.path läuft vor jedem Nicht-Builtin-Import; alle 3 F008-Wege und 60+ Varianten liefern den Probe-Exit 2 ohne Fremdcode
  Status: CONFIRMED
```

**Implementierer:** (nicht beteiligt, Kontextisolation)

### Runde 2
**Adversary:** Zweite Runde gegen Frühkonsens: Umfeld des Fixes mit echten Framework-Hooks statt Probe. Fake-Framework aus dem aktuellen Arbeitsbaum (`core/`, `hooks/`, `.claude-plugin/`, `modules/`, `templates/`, `config.yaml`) als annotierter Tag, Pin, Konsumentenprojekt (Pfad mit Leerzeichen) mit geplanter `.claude/json.py`, Einträge aus `consumer_hooks` (Skript `/tmp/claude-0/-home-user-agent-os-openspec/a3bf6853-0157-5004-90ae-6e21b8403818/scratchpad/adv4/real_hooks.py`):
- PreToolUse Edit auf `src/app.py` ohne Workflow, alle 5 Edit-Einträge: `worktree_write_guard`, `claude_md_protection`, `tdd_enforcement`, `post_implementation_gate` rc=0; `edit_gate.py` rc=2 mit `BLOCKED: No active workflow for app.py`. Geschwister-Importe (`hook_utils`, `config_loader`, …) funktionieren trotz `-E -s -B`; Marker der Shadow-Datei nicht entstanden.
- SessionStart (`session_singleton_guard.py register`, `session_banner.py`): rc=0, Banner-JSON aus dem Cache.
- Danach `__pycache__` im Cache: keiner (`-B` greift, `cache_valid` bleibt grün).
- `python3 -I .claude/cloud_bootstrap.py --retry` und ohne `-I`, jeweils mit `.claude/json.py` vorhanden: rc=0, „Gates geladen", `current` zeigt auf den Cache, Marker nicht entstanden.

Schutz von Baustein und Pin weiter aktiv (unverändert seit Lauf 3, für den Fix relevant, weil das Kommando nur dann trägt, wenn der Baustein selbst nicht überschreibbar ist):
Code reference: core/hooks/edit_gate.py:62
Code reference: core/hooks/bash_gate.py:1887

Analytische Prüfung weiterer Shadowing-Wege: Vor `_strip_script_dir` lädt der Interpreter nur Startmodule (`encodings`, `site`, …) aus der Stdlib, bevor das Skriptverzeichnis eingetragen wird; nachgestellt in Runde 1 (`.claude/site.py`, `.claude/encodings.py` ohne Wirkung). Ein `.pth` im System-site-packages wird auch unter `-I` ausgewertet; das setzt Root-Schreibzugriff außerhalb des Projekts voraus, gilt lokal mit Plugin genauso und ist keine Lücke dieses Fixes (gleiche Klasse wie F009/#564).

```
Finding:
  ID: F010
  Severity: LOW
  Category: edge_case
  Code reference: core/cloud_bootstrap.py:304
  Description: Der Kindprozess startet mit `-s`, damit fehlt die User-site (z. B. `~/.local/lib/python3.x/site-packages`). Liegt PyYAML nur dort (`pip install --user`), läuft `config_loader` ohne YAML: Projekt-Config wird ignoriert, jeder Hook schreibt die WARNING auf stderr. Lokal mit Plugin (ohne `-s`) wäre YAML da.
  Spec requirement: Output — dieselben Gates wie lokal mit Plugin.
  Conflict: Analytisch, nicht reproduziert: in dieser Cloud-Umgebung liegt PyYAML in `/root/.local` UND im System-site, `python3 -s -c "import yaml"` endet mit 0. Sicherheitsgewinn von `-s` gering, weil in der Cloud (root) auch System-site-packages schreibbar ist.
  Remediation: `-s` streichen (`-E -B` reicht gegen PYTHONPATH/PYTHONSTARTUP) oder die Einschränkung in der README nennen. Kein Blocker.
```

Regression: `tests/test_cloud_gates_522.py` im venv: 29 passed, 1 failed (`test_cloud_session_proof_artifact_present` = AC-16, Live-Export fehlt bewusst). Ausgabe: `docs/artifacts/feat-522-cloud-plugin-gates/adversary-test-output.txt`.

```
Confirmation:
  AC: AC-9 / AC-4 (Abhilfe `--retry` unter -I)
  Code reference: core/cloud_bootstrap.py:304
  Evidence: --retry mit und ohne -I rc=0 mit geplantem Shadow-Modul; echte Hooks aus dem Cache ohne __pycache__; edit_gate blockt
  Status: CONFIRMED
```

**Implementierer:** (nicht beteiligt, Kontextisolation)

## Herkunft der Vorbedingungen

kein Sprachprofil konfiguriert (`precondition_origins.default_lang`)

## Verdict

Bewertung: F008 behoben. Alle drei Wege (Shadow in `.claude/` über das erzeugte Kommando, PYTHONPATH, Alt-Eintrag ohne `-I`) liefern den Probe-Exit 2 ohne Fremdcode, ebenso 60+ Varianten; echte Hooks laufen aus dem Cache mit Geschwister-Importen, kein `__pycache__`, `--retry` geht mit `-I`. Neu nur F010 (LOW, `-s` verdeckt User-site, analytisch). F009 ausgelagert (#564). Tests: 29 grün, 1 rot = AC-16 Live-Nachweis, offen wie vereinbart.

VERDICT: VERIFIED

Nachtrag Orchestrator (AC-16, Live-Nachweis): frische Cloud-Sitzung session_01GtRxphksjRU1RNj2b24hXy auf Wegwerf-Zweig e2e-522-cloud-gates; Edit auf src/main.py von edit_gate geblockt (BLOCKED: No active workflow). Export: docs/artifacts/feat-522-cloud-plugin-gates/cloud-session-events.json; Zielsuite danach 30 passed.

## Geprüfte Dateien

- sha256:54b9ce76bcb5a9b4046ef046bc482fc83d8e2b2aa7f2b7a9320837ebe7bf4d50  core/cloud_bootstrap.py
- sha256:22d071aaa1d1ce4e9228b207c77e650f82e59266931e362fa5351f34f282fd11  core/hooks/bash_gate.py
- sha256:d2d9c039ccaced6587cdfec2cf884c9b22425ca629ca137588da8fb46512e251  core/hooks/edit_gate.py
- sha256:9a66d4a495b5e0d793465fb0a979ef30272afafef380b43a0269602c3fbc239f  scripts/sync_cloud_hooks.py
- sha256:388368b5ed8f630be684ee95a363be80c16f38cbec1ddbe1cda333d55ab9eb10  setup.py
- sha256:6fbb056197be43f1d35436b98fab532877438572c41b50c7118459caead56093  tests/test_cloud_gates_522.py

## Prüfbasis

- base: 98ac6f966c603a63d95e6a77ef92aeb99405458c
- blob:13e013f7543d8bab525df4d1563a701309c6743f  core/cloud_bootstrap.py
- blob:e34706bfebb3a5435bc9042aa59b3a8cce7e5d57  core/hooks/bash_gate.py
- blob:eb9702f91e3dd95e905810dfefd1db0db62c3122  core/hooks/edit_gate.py
- blob:e60b9f07a22d6a8ff663c501f7d52aecbb1b10af  scripts/sync_cloud_hooks.py
- blob:4692f5358428276850c74762c4e41ca40d7845b2  setup.py
- blob:de0fd165568a34e48ff33985d5454adffa0a7d3f  tests/test_cloud_gates_522.py
