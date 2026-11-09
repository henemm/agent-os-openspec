# Adversary Dialog — feat-522-cloud-plugin-gates
Spec: docs/specs/feat-522-cloud-plugin-gates.md
Datum: 2026-11-09 18:19

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
**Adversary:** Testlauf `tests/test_cloud_gates_522.py` (venv): 24 passed, 1 failed (`test_cloud_session_proof_artifact_present`, AC-16, Export steht bis nach dem Verdict aus, erwartet). Ausgabe: `docs/artifacts/feat-522-cloud-plugin-gates/adversary-test-output.txt`. Keine Regression der übrigen ACs.

F007 erneut angegriffen (Code reference: core/cloud_bootstrap.py:158, `cache_valid`; Code reference: core/cloud_bootstrap.py:99, `_git_check`; Code reference: core/cloud_bootstrap.py:120, `_tree_matches`): Nachstellung aus Lauf 2 (Skript im Cache ersetzt, `filter.f.clean` mit `git show HEAD:...`, `core/hooks/probe.py filter=f` in `.git/info/attributes`). Ergebnis: Exit 2 (Original-Probe lief nach Neuabruf), EVIL-Marker nicht entstanden, Filter-Marker nicht entstanden. F007 behoben: die Prüfung ruft nur noch `rev-parse` und `ls-tree`, hasht in Python selbst.

Neue Umgehungen der Inhaltsprüfung, alle real ausgeführt (manipuliertes Skript plus Config-Eintrag, jeweils Exit 2, kein EVIL, kein Marker, d. h. kein Befehl aus der Config lief): `core.fsmonitor`, `core.hooksPath`, `alias.rev-parse`/`alias.ls-tree` (`!`-Befehl), `core.gitProxy`, `core.pager`/`pager.ls-tree`, `include.path`, `safe.directory=*`, `core.worktree`, `core.sshCommand`, `extensions.worktreeConfig`. `.git` als Datei (`gitdir:` auf Kopie): abgelehnt, Neuabruf (`is_dir`-Prüfung in `cache_valid`). Hardlink `probe.py` auf Außendatei: bei gleichem Inhalt gültig (Inhalt stimmt), nach Änderung über den anderen Link erkannt und neu geholt. Restgrenze gefälschte Objektdateien/`commondir`/`alternates` im Objektspeicher bleibt wie in der README dokumentiert.

Gate-Schutz (Code reference: core/hooks/edit_gate.py:62, Code reference: core/hooks/bash_gate.py:74, Code reference: core/hooks/bash_gate.py:1886): geschützt sind nur `.claude/cloud_bootstrap.py` und `framework_version.json`. Real gegen `edit_gate`/`bash_gate` geprüft: `Write .claude/json.py` ohne Workflow geblockt ("No active workflow"), in einem Workflow ab Phase 6 ist es eine normale Code-Datei; `echo ... > .claude/json.py` und `cp x .claude/shutil.py` per Bash: Exit 0, keine Sperre, auch ohne Workflow.

```
Finding:
  ID: F008
  Severity: MEDIUM
  Category: security
  Code reference: core/cloud_bootstrap.py:28
  Description: Der Baustein läuft als `python3 .claude/cloud_bootstrap.py`; Python setzt das Skriptverzeichnis `.claude/` an die erste Stelle von `sys.path`. Stdlib-Module, die der Baustein erst danach importiert (`json`, `hashlib`, `shlex`, `shutil`, `subprocess`, `datetime`), kann eine Datei `.claude/json.py` ersetzen. Der Baustein startet weder mit `-I` noch bereinigt er `sys.path[0]`; die Kaperung läuft vor jeder Cache-Prüfung und umgeht alle Gates.
  Spec requirement: Output: dieselben Gates wie lokal mit Plugin, geladen aus dem gepinnten Tag; AC-15 (Baustein und Pin gegen Überschreiben geschützt).
  Conflict: Reproduziert (Fake-Framework, Pin, Cache wie Test-Ctx): `.claude/json.py` mit `open(EVIL,'w'); raise SystemExit(0)` angelegt, Baustein mit Edit-PreToolUse-Payload aufgerufen: Exit 0 (statt 2 aus der Probe), EVIL-Datei entstand, kein Gate lief. Die Datei anzulegen lässt `bash_gate` per `echo > .claude/json.py` zu (Exit 0). PYTHONPATH wirkt gleich (Exit 0, EVIL), ist aber nicht vom Modell setzbar und deshalb nur Randnotiz.
  Remediation: Als erste Anweisung vor allen Imports `sys.path[0:1] = []` bzw. den Eintrag für das Skriptverzeichnis entfernen (nur wenn er dem Skriptverzeichnis entspricht), und den Kindprozess in `forward` mit `-I` starten (bereinigt auch PYTHONPATH/User-Site); zusätzlich `.claude/*.py` im Konsumenten-Projekt in den Cloud-Gate-Schutz aufnehmen. Test: `.claude/json.py` anlegen, Baustein muss die Probe-Exit-Zahl liefern.
```

**Implementierer:** (nicht beteiligt, Kontextisolation)

### Runde 2
**Adversary:** Zweite Runde gegen Frühkonsens (Fix für F007 sauber, Tests grün, heißt nicht, dass die Umgebung dicht ist). Ausführung: Code reference: core/cloud_bootstrap.py:263 (`forward`): Kind mit `sys.executable script`, ohne `-I`, `PYTHONDONTWRITEBYTECODE=1`; Skriptverzeichnis im Cache ist durch `cache_valid` geprüft, dort kein Treffer. `.pth`/`sitecustomize`/`usercustomize`: `sitecustomize` wird vor dem Einfügen des Skriptverzeichnisses importiert und ist aus `.claude/` nicht erreichbar; User-Site und `PYTHONPATH` setzt das Modell nicht (Hook-Umgebung stammt aus der Sitzung, `env` in `settings.json` ist geschützt). Realer Weg bleibt F008.

TOCTOU (realistisch bewertet): zwischen zwei Hook-Aufrufen schreibt das Modell, dann holt der nächste Lauf neu (getestet). Während eines Hooks schreibt nur ein Hintergrundprozess des Modells. Real nachgestellt: Hintergrundschleife wechselt `core/hooks/probe.py` im Cache dauernd zwischen Original und EVIL; nach 19 Hook-Aufrufen führte der Baustein EVIL aus (Prüfung sah das Original, Start las EVIL). Voraussetzung: gezielt gestartetes Hintergrundprogramm, das den Cache-Pfad kennt, den kein Gate sperrt. Dasselbe gilt für das lokale Plugin-Cache-Verzeichnis ohne jede Prüfung.

```
Finding:
  ID: F009
  Severity: LOW
  Category: security
  Code reference: core/cloud_bootstrap.py:225
  Description: Prüfung (`cache_valid`) und Start (`forward`) sind nicht atomar; ein Hintergrundprozess kann die Datei im Cache dazwischen austauschen.
  Spec requirement: Output: Gates aus dem gepinnten Tag.
  Conflict: Reproduziert mit Dauerschleife (19 Hook-Läufe bis EVIL lief). Außerhalb des Modells "kein Schreiben während eines Hooks"; gezielte Gegenwehr nötig, Auswirkung wie F007.
  Remediation: Schreibzugriff auf `~/.cache/agent-os-openspec/` in edit_gate/bash_gate sperren oder die Restgrenze in der README nennen. Kein Blocker allein.
```

Weitere Abdeckung: Code reference: setup.py:948 (Baustein und Einträge werden unverändert geschrieben, kein neuer Befund), Code reference: scripts/sync_cloud_hooks.py:117 (`consumer_hooks`, Kommando-Form unverändert, `python3` ohne `-I`, vgl. F008), Code reference: scripts/sync_cloud_hooks.py:73. F002/F004/F005/F006 bleiben LOW, kein schwererer Angriff gefunden (F002/F004/F005/F006 nicht neu hochgestuft). AC-16 bleibt offen (Live-Export folgt), allein kein BROKEN.

**Implementierer:** (nicht beteiligt, Kontextisolation)


## Herkunft der Vorbedingungen

kein Sprachprofil konfiguriert (`precondition_origins.default_lang`)

## Verdict

Bewertung: F007 behoben (Nachstellung scheitert, Config-Varianten wirkungslos, Hardlink und `.git`-Datei erkannt). Neu F008 (MEDIUM): Import-Kaperung über `.claude/` vor jeder Prüfung umgeht alle Gates; F009 (LOW): Race per Hintergrundprozess. Tests: 24 grün, AC-16 offen wie vereinbart. F008 ist in einer Zeile behebbar, der Cache selbst ist dicht.

VERDICT: BROKEN
