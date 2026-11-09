# Adversary Dialog — feat-522-cloud-plugin-gates
Spec: docs/specs/feat-522-cloud-plugin-gates.md
Datum: 2026-11-09 18:00

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
- [ ] **AC-16:** Given ein Wegwerf-Zweig eines Konsumenten-artigen Repos mit `setup.py --cloud-gates` / When in einer frischen Cloud-Sitzung auf diesem Zweig ein Edit ohne Workflow versucht wird / Then blockt `edit_gate` ihn, und das Transkript-Ereignis liegt als Artefakt `docs/artifacts/feat-522-cloud-plugin-gates/cloud-session-events.json` vor: unverändert per `list_events` aus der Sitzung exportiert, mit Sitzungs-ID, dem Edit-Werkzeugaufruf und dem zugehörigen Ergebnis, das die Blockmeldung von `edit_gate` (`BLOCKED`) enthält. Automatisch geprüft wird der Inhalt dieses Exports (Edit-Aufruf und dazu gehörendes Ergebnis mit `BLOCKED`), nicht der Live-Lauf selbst
- [x] **AC-17:** Given `README.md` und `CHANGELOG.md` / When gelesen / Then beschreibt der Abschnitt zu Cloud-Sitzungen den Weg für Plugin-Konsumenten mit `--cloud-gates`, `cloud_bootstrap.py`, `--retry` und `github.com`, verweist nicht mehr auf #522 als offen, und `[Unreleased]` enthält einen Eintrag, der `#522` nennt
- [x] **AC-18:** Given ein fehlgeschlagener Abruf / When der Baustein für UserPromptSubmit mit `prompt` `  Override ` (Rand-Leerraum, andere Schreibweise) und gültiger `session_id` läuft / Then Exit 0, stdout enthält den Hinweis „Ausnahme gesetzt“, `<base>/override-<session_id>.json` mit Zeitstempel existiert, `<projekt>/.claude/gate-events.jsonl` hat genau eine neue Zeile mit `hook` `cloud_bootstrap` und `reason` `override: gates not loaded`, und die Sperrmeldung der schreibenden Werkzeuge nennt wörtlich „PO: `override` tippen (gilt 1 h für diese Sitzung)“
- [x] **AC-19:** Given eine gesetzte Ausnahme für Sitzung A bei fehlgeschlagenem Abruf / When der Baustein für PreToolUse mit Edit, Write, MultiEdit, WebFetch und Bash (auch `echo x > f`) mit `session_id` A läuft / Then Exit 0 und es entsteht keine zusätzliche Datei und keine weitere Protokollzeile; mit `session_id` B oder mit einer um mehr als 1 Stunde zurückdatierten Ausnahmedatei dagegen wieder Exit 2 mit der Sperrmeldung
- [x] **AC-20:** Given ein ladbarer Cache oder ein Prompt, der nicht ausschließlich `override` lautet (etwa `bitte override setzen`) oder eine ungültige `session_id` (`../x`) / When der Baustein für UserPromptSubmit läuft / Then wird keine Ausnahmedatei geschrieben und keine Protokollzeile angelegt; bei ladbarem Cache läuft `phase_listener.py` aus dem Cache mit durchgereichtem stdin, und schreibende Werkzeuge entscheiden allein die echten Gates

## Dialog

### Runde 1
**Adversary:** Testlauf `tests/test_cloud_gates_522.py` (venv): 24 passed, 1 failed (`test_cloud_session_proof_artifact_present`, AC-16, Export steht bis nach dem Verdict aus, erwartet). Ausgabe: `docs/artifacts/feat-522-cloud-plugin-gates/adversary-test-output.txt`.

F001 erneut angegriffen (Code reference: core/cloud_bootstrap.py:278, Whitelist `bash_allowed`; READ_COMMANDS Code reference: core/cloud_bootstrap.py:55): `rg` ist gestrichen (`rg --hostname-bin ...` Exit-Pfad zu), `less`, `cat <(id)` und `git ... --output/--ext-diff/--textconv` werden abgelehnt (False). Abgekürzte Optionen (`--outp=`, `--out=`, `--ext`, `--textc`, `--show-sig`, `--show-s`) habe ich mit git 2.43 real ausgeführt: git lehnt alle als "unrecognized argument" ab, also kein Schreib- oder Ausführungsweg. `git log --format=%G?`/`%GG` startet nur das System-gpg (Programm aus Config, nicht aus Argumenten, nicht vom Modell steuerbar), `git diff --no-index a b` und `-O<datei>` lesen nur. F001 gilt als behoben.

F003 erneut angegriffen (Code reference: core/cloud_bootstrap.py:114, `cache_valid`; Aufruf Code reference: core/cloud_bootstrap.py:173): geprüft sind Symlinks, `.ok`, HEAD, `status --porcelain=v2 --ignored --untracked-files=all` und `ls-files -v` (assume-unchanged/skip-worktree), ohne Replace-Objekte und globale Config, mit `core.fsmonitor=false`. Das fängt direkte Änderung, fremde Dateien, ignorierte Dateien und Index-Flags. NICHT abgedeckt: die lokale Repo-Config des Cache. Reproduktion: Skript im Cache ersetzen, dann `git config filter.f.clean "sh -c '...; git show HEAD:core/hooks/probe.py'"` plus `core/hooks/probe.py filter=f` in `.git/info/attributes`. Ergebnis: `status` meldet den Arbeitsbaum als sauber (Clean-Filter liefert die Originalfassung), `cache_valid` bleibt wahr, der Baustein führt die manipulierte Datei aus (`EVIL`, Exit 0) und der Filter-Befehl selbst lief im Baustein (Marker-Datei entstand). `.git/hooks` und Alias-Config bleiben dagegen wirkungslos (der Baustein ruft nur `status`/`ls-files`). Siehe F007.

Gate-Schutz des Cache (Code reference: core/hooks/edit_gate.py:62, Code reference: core/hooks/bash_gate.py:1169): geschützt sind nur `.claude/cloud_bootstrap.py` und `framework_version.json`; ein Schreibzugriff auf `~/.cache/agent-os-openspec/` ist weiter nicht gesperrt (kein Treffer in core/hooks). Damit ist die Integritätsprüfung die einzige Sperre.

```
Finding:
  ID: F007
  Severity: MEDIUM
  Category: security
  Code reference: core/cloud_bootstrap.py:114
  Description: Die Unversehrtheitsprüfung des Cache vertraut `git status`, das lokale Repo-Config (`filter.<n>.clean` samt `.git/info/attributes`) ausführt und beeinflusst; ein Clean-Filter, der die Originalfassung ausgibt, tarnt eine manipulierte Gate-Datei und der Filter-Befehl läuft zusätzlich selbst.
  Spec requirement: Output: dieselben Gates wie lokal mit Plugin, geladen aus dem gepinnten Tag (Fix F003).
  Conflict: Reproduziert (Fake-Repo, Tag, Cache): Skript manipuliert + Config + Attributes geschrieben, Baustein führt EVIL aus, FILTER_RAN-Marker entstand. Voraussetzung: Schreibzugriff aufs Cache-Verzeichnis, den die Gates nicht sperren.
  Remediation: Cache nicht per `git status` prüfen, sondern Inhalte direkt hashen (`git ls-tree -r HEAD` gegen Dateihashes im Arbeitsbaum, `git hash-object --no-filters`), `.git/config` und `.git/info/attributes` auf erwarteten Inhalt prüfen, `.git`-Verzeichnis auf Extras (config-Schlüssel ausser Klon-Standard, hooks, info/attributes) ablehnen; und/oder `~/.cache/agent-os-openspec` in edit_gate/bash_gate als Schreibziel sperren.
```

**Implementierer:** (nicht beteiligt, Kontextisolation)


### Runde 2
**Adversary:** Übrige ACs und Gegenprobe der Früheinigung.

Tests: 24 von 25 grün, nur der AC-16-Export fehlt (erwartet). AC-10/11/14 (setup.py, Code reference: setup.py:965 und Code reference: setup.py:1002) und AC-12 (Code reference: scripts/sync_cloud_hooks.py:113) sind durch die Tests belegt; `sync_cloud_hooks.py --check` bleibt grün. AC-15: edit_gate-Liste (Code reference: core/hooks/edit_gate.py:62) und bash_gate-Block (Code reference: core/hooks/bash_gate.py:1887) unverändert gegenüber Lauf 1. AC-16-Codepfad per lokalem Nachbau gegen den echten Tag in Lauf 1 belegt, kein BROKEN-Grund.

Fail-closed-Pfad nochmals: fehlender Pin, ungültiger Skriptname und Cache ohne gültigen `.ok` gehen in `fail_response` (Code reference: core/cloud_bootstrap.py:305): Schreibwerkzeuge Exit 2, Lesewerkzeuge und `--retry` frei. Cache-Neuabruf nach fehlgeschlagener Prüfung funktioniert (Cache wird verworfen und neu geklont, Code reference: core/cloud_bootstrap.py:173).

Früheinigung hinterfragt: Dass F001 sauber behoben ist und die Tests grün sind, heißt nicht, dass die Cache-Prüfung dicht ist. Das Testbeispiel deckt Dateiänderung, Fremddatei, Symlink und Index-Flags ab, nicht die Config des Cache-Repos. Genau dort fand ich F007. F002/F004/F005/F006 bleiben LOW, kein schwererer Angriff gefunden.

**Implementierer:** (nicht beteiligt, Kontextisolation)


## Herkunft der Vorbedingungen

kein Sprachprofil konfiguriert (`precondition_origins.default_lang`)

## Verdict

Bewertung: F001 behoben. F003-Fix wird durch F007 (Clean-Filter in der Cache-Config) umgangen.

VERDICT: BROKEN
