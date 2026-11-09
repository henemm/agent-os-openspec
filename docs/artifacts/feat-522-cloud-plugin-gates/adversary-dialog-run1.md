# Adversary Dialog — feat-522-cloud-plugin-gates
Spec: docs/specs/feat-522-cloud-plugin-gates.md
Datum: 2026-11-09 17:39

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
**Adversary:** Testlauf `tests/test_cloud_gates_522.py` (venv): 23 passed, 1 failed. Der Fehlschlag ist `test_cloud_session_proof_artifact_present` (AC-16, Export fehlt noch, erwartet). Ausgabe: `docs/artifacts/feat-522-cloud-plugin-gates/adversary-test-output.txt`. Danach eigene Angriffe.

Fail-closed, Bash-Lesewhitelist (`bash_allowed`, Code reference: core/cloud_bootstrap.py:231):
- Abgewehrt (False): `git -c core.pager=ls log`, `git log --output=x`, `git show --output x`, `rg --pre=ls`, `rg --pre ls`, `FOO=1 ls`, `env ls`, `sort -o`, `find -exec`, `python3 .claude/cloud_bootstrap.py --retry x`. Abkürzung `git diff --outp=` ist von git selbst als mehrdeutig abgelehnt, also kein Schreibweg.
- Erlaubt wie vorgesehen: `ls -la`, `git status`, `grep -r --include=*.py foo .`, Tab im Befehl, `$'..'` (shlex expandiert es nicht, kein Zweitbefehl).
- DURCHGELASSEN, obwohl es ein Programm startet: `rg --hostname-bin=/pfad/h.sh --hyperlink-format='file://{host}{path}' . datei`. Ich habe es ausgeführt: ripgrep 14.1.0 startete `h.sh` (Marker-Datei `pwn` entstand). Die Prüfung sperrt nur Wörter mit Präfix `--pre` (Code reference: core/cloud_bootstrap.py:248). Folge: Im Sperrzustand kann ein bereits vorhandenes ausführbares Programm gestartet werden (ohne Argumente); das widerspricht „ohne geladene Gates nur Lesen“. Es braucht ein schon vorhandenes Programm, weil schreibende Werkzeuge gesperrt sind. Siehe F001.
- `cat .env` / `cat ~/.ssh/id_rsa` / `head /proc/self/environ` sind erlaubt: dokumentierte Limitation (Spec Known Limitations, erster Punkt), Weitergabe nach außen ist gesperrt. Als Limitation akzeptiert.
- Unlesbares stdin bei PreToolUse: leeres stdin, `garbage`, `[]` oder JSON ohne `hook_event_name` enden mit Exit 0 (`_parse` liefert `{}`, `event != "PreToolUse"` gibt 0; Code reference: core/cloud_bootstrap.py:300 und core/cloud_bootstrap.py:275). Ein schreibendes Werkzeug würde also durchgelassen, wenn der Harness kaputtes JSON liefert. AC-6 verlangt Exit 0 nur für die Nicht-PreToolUse-Ereignisse. Der Harness erzeugt das Stdin selbst, das Modell kann es nicht beeinflussen. Siehe F002 (LOW).
- Tool-Namen: `Write` ohne `hook_event_name` wird nicht blockiert (gleicher Befund); mit Ereignis wird jedes Nicht-Lese-Werkzeug blockiert.

Override (`override_active`, Code reference: core/cloud_bootstrap.py:180):
- `  Override ` wird zu Datei `override-sA.json` mit Zeitstempel (bewiesen). `session_id=../x` ergibt keine Datei. Datei mit `created` in ferner Zukunft (9999999999) wird abgelehnt (Toleranz nur 60 s). Zweite Sitzung B erhält Exit 2.
- Selbst anlegen im Sperrzustand: mit erlaubten Werkzeugen nicht möglich (Write/Edit gesperrt, `>` und `tee` in der Whitelist verboten, `git --output` gesperrt). Kein Weg gefunden.

Cache und Abruf (`fetch`, Code reference: core/cloud_bootstrap.py:131; `cache_valid`, Code reference: core/cloud_bootstrap.py:93):
- Fake-Repo mit annotiertem Tag: Klon, Weitergabe von stdin, Exit 2 durchgereicht (AC-1 live bewiesen). Cache-Ordner ohne `.ok` oder mit falscher SHA im `.ok`: wird neu geklont (RAN, Exit 2), nicht benutzt. Gültig ist nur `.ok == cloud_sha`.
- Sechs gleichzeitige Prozesse bei leerem Cache: genau ein Cache-Ordner, `.lock` und `current`, kein `.tmp-*`, alle sechs bekamen das Skriptergebnis.
- Cache nach dem Klon manipuliert (Skript ersetzt, `.ok` unverändert): der Baustein führt die veränderte Datei aus (Ausgabe `EVIL`, Exit 0). Ebenso Symlink als Cache-Ordner mit passendem `.ok`: wird ausgeführt (`EVIL2`). Es gibt keine Inhaltsprüfung, nur `.ok`. Siehe F003.
- `--retry` bei unerreichbarer Quelle: Exit 1 wie in AC-9, aber der bis dahin gültige Cache ist danach gelöscht (`force` löscht vor dem Klon), die Sitzung ist danach gesperrt. Siehe F004 (LOW).

setup.py (Code reference: setup.py:965, Code reference: setup.py:1002):
- `--cloud-gates` zweimal auf Projekt mit eigenen Hooks (Bash-Gruppe, Gruppe ohne Matcher, `Custom`-Event), `permissions`, `env`, `enabledPlugins`: eigene Hooks und Schlüssel unverändert; zweiter Lauf Byte-gleich („Alles aktuell“, md5 gleich). `plugin_mode:false` wird mit Exit 1 abgewiesen, nichts geschrieben. Pin 4.9.0 löst lokal auf SHA 98ac6f96... auf.
- `scripts/sync_cloud_hooks.py --check` bleibt grün, 23 Einträge, Anzahl je Event gleich hooks.json (Code reference: scripts/sync_cloud_hooks.py:113), Timeout +25 (Beispiel 30).

**Implementierer:** (nicht beteiligt, Kontextisolation: der Adversary hat die Belege selbst erbracht)

### Runde 2
**Adversary:** Gate-Schutz der neuen Pfade und Gegenprobe der Früheinigung.

bash_gate (Code reference: core/hooks/bash_gate.py:1169, Code reference: core/hooks/bash_gate.py:1887), echte Aufrufe mit aktivem Workflow, ohne Override:
- Block (Exit 2): `>`, `>>`, `tee`, `sed -i`, `cp`, `mv`, `rm`, `ln -sf`, `dd of=`, `truncate`, `git checkout --`, `cd .claude && echo x > cloud_bootstrap.py`, `"$PWD/.claude/framework_version.json"`.
- Erlaubt wie verlangt: `cat .claude/cloud_bootstrap.py`, `python3 .claude/cloud_bootstrap.py --retry`; `sed -i` auf `settings.json` blockt weiter (bestehende Regel, #543-Ausnahme für `enabledPlugins` unverändert, Code reference: core/hooks/edit_gate.py:62).
- NICHT erkannt (Exit 0): Glob `echo x > .claude/cloud_boot*`, Klammern `{cloud_bootstrap.py,y}`, `cp x .claude/cloud_bootstrap.p[y]`, `python3 -c "open('.claude/cloud_bootstrap.py','w')..."`. Das ist die vom Entwickler genannte Lücke; sie liegt auf der Ebene der übrigen Pfad-Schutzregeln dieses Gates (Heuristik, keine Sandbox). Der Schreibzugriff per Edit/Write ist vollständig dicht (edit_gate, Code reference: core/hooks/edit_gate.py:994: direkter, relativer, `..`-Pfad und fremdes Projekt geblockt, Substring-Treffer; `core/cloud_bootstrap.py` bleibt frei). Bewertung F005 (LOW).
- Gate-Schutz des Caches: `sed -i` auf `~/.cache/agent-os-openspec/<tag>/core/hooks/edit_gate.py` besteht bash_gate UND secret_egress_guard (je Exit 0); ein Write auf `~/.cache/.../override-adv.json` besteht edit_gate (Exit 0). Mit geladenen Gates kann das Modell die gecachten Gate-Skripte also umschreiben, und weil der Baustein nur `.ok` prüft, läuft die manipulierte Fassung. Das ist dieselbe Wurzel wie F003, höher bewertet (MEDIUM), weil es kein Umweg über Dateisystem-Vorarbeit braucht.
- Lokal kein Doppellauf (Shell-Präfix `[ "$CLAUDE_CODE_REMOTE" != "true" ] ||` wirklich ausgeführt): leer, `false`, `TRUE`, `True`, `1`, ` true` enden mit Exit 0 ohne Lauf; nur `true` läuft. Konsistent mit AC-2.

Commit-Gate im fremden Repo (Befund des Orchestrators): `git diff core/hooks/bash_gate.py` zeigt nur den Block 1b'' (Code reference: core/hooks/bash_gate.py:1887) und `_writes_cloud_gate_file`; das Commit-Gate Schritt 5 hängt an `workflow_enforced and _creates_commit(command)` und misst in `_measurement_root()`, also am aktiven Workflow der Sitzung, nicht am Zielrepo. Diese Zeilen sind unverändert. Vorbestehend, keine Folge dieser Änderung. F006 (LOW, vorbestehend, eigenes Issue).

AC-16 live nachgestellt: `echo '<PreToolUse Write src/app.py>' | CLAUDE_CODE_REMOTE=true CLAUDE_PROJECT_DIR=/home/user/playground AGENT_OS_CLOUD_CACHE=<scratchpad> python3 .claude/cloud_bootstrap.py edit_gate.py` holte den echten Tag `agent-os-openspec--v4.9.0` von GitHub und endete mit Exit 2 `BLOCKED: No active workflow for app.py`. Der Codepfad ist belegt; der Export `cloud-session-events.json` aus einer echten Cloud-Sitzung fehlt noch, AC-16 bleibt offen bis dahin (kein BROKEN).

Früheinigung hinterfragt: Alle Tests grün hieße nicht, dass die Whitelist dicht ist; die Tests prüfen die Beispiele der Spec, nicht Programme-Startoptionen von erlaubten Befehlen. F001 trägt das.

```
Finding:
  ID: F001
  Severity: MEDIUM
  Category: security
  Code reference: core/cloud_bootstrap.py:248
  Description: `rg --hostname-bin=<programm> --hyperlink-format=file://{host}{path}` besteht bash_allowed und startet ein beliebiges vorhandenes Programm; nur Wörter mit Präfix --pre werden abgelehnt.
  Spec requirement: Spec Punkt 5, Bash-Whitelist: ohne geladene Gates nur Lesen, nichts ausführen.
  Conflict: Reproduziert mit ripgrep 14.1.0 (Marker-Datei entstand). Programm muss schon existieren, ohne Argumente.
  Remediation: rg aus READ_COMMANDS streichen oder Optionen `--pre*`, `--hostname-bin*`, `-z`/`--search-zip` ablehnen; Test dazu.

Finding:
  ID: F002
  Severity: LOW
  Category: edge_case
  Code reference: core/cloud_bootstrap.py:275
  Description: PreToolUse mit unlesbarem oder JSON-losem stdin endet mit Exit 0, auch für schreibende Werkzeuge (fail-open).
  Spec requirement: AC-6 meint nur Nicht-PreToolUse; für PreToolUse sagt die Spec nichts.
  Conflict: Harness-seitig nicht vom Modell beeinflussbar.
  Remediation: Bei fehlendem `hook_event_name` und unlesbarem JSON wie PreToolUse mit unbekanntem Werkzeug behandeln (Exit 2), außer der Aufruf ist `--retry`.

Finding:
  ID: F003
  Severity: MEDIUM
  Category: security
  Code reference: core/cloud_bootstrap.py:93
  Description: Der Cache gilt allein wegen `.ok == cloud_sha`; Inhalt und Symlink-Ordner werden nicht geprüft, und weder edit_gate noch bash_gate noch secret_egress_guard schützen `~/.cache/agent-os-openspec/`. Mit geladenen Gates lässt sich ein Gate-Skript im Cache per `sed -i` oder Write umschreiben und läuft danach.
  Spec requirement: Spec Output: „dieselben Gates wie lokal mit Plugin, geladen aus dem gepinnten Tag“.
  Conflict: Lokal ist das Plugin-Verzeichnis durch die Pfadschutz-Regeln nicht frei beschreibbar; hier schon.
  Remediation: `~/.cache/agent-os-openspec` in edit_gate/bash_gate als Schreibziel schützen, und/oder vor dem Start `git -C <cache> rev-parse HEAD`/`status --porcelain` prüfen und `is_symlink()` ablehnen.

Finding:
  ID: F004
  Severity: LOW
  Category: edge_case
  Code reference: core/cloud_bootstrap.py:131
  Description: `--retry` löscht den gültigen Cache vor dem Klon; scheitert das Netz, ist danach auch ein funktionierender Stand weg.
  Spec requirement: AC-9 (verwirft, holt neu, Exit 1 bei unerreichbarer Quelle) — so umgesetzt.
  Conflict: Verlust der Arbeitsfähigkeit durch einen Netzfehler.
  Remediation: Neu in Temp-Ordner klonen und erst nach Erfolg austauschen.

Finding:
  ID: F005
  Severity: LOW
  Category: security
  Code reference: core/hooks/bash_gate.py:1169
  Description: Glob-, Klammer- und `python -c`-Ziele für `.claude/cloud_bootstrap.py` und `framework_version.json` werden von bash_gate nicht erkannt.
  Spec requirement: AC-15 (Umleitung, tee, sed -i, cp blocken).
  Conflict: AC-15 ist für die genannten Formen erfüllt; die Lücke ist heuristik-typisch und wie bei den anderen Pfadschutz-Regeln.
  Remediation: Als Known Limitation in der Spec nennen.

Finding:
  ID: F006
  Severity: LOW
  Category: regression
  Code reference: core/hooks/bash_gate.py:2058
  Description: Das Commit-Gate (Schritt 5) hängt am aktiven Workflow der Sitzung und blockt `git commit` in einem anderen Repo. Vorbestehend, im Diff dieser Änderung nicht berührt.
  Spec requirement: keine; CLAUDE.md „Workflow-Isolation“.
  Conflict: Keine Folge von #522.
  Remediation: Eigenes Issue.
```

Bewertung: Alle ACs sind durch Tests und eigene Läufe belegt (AC-16 offen bis Cloud-Export). F001 und F003 sind reproduzierbare Umgehungen des Fail-closed- bzw. Gate-Grundsatzes.

**Implementierer:** (nicht beteiligt, Kontextisolation)

## Herkunft der Vorbedingungen

kein Sprachprofil konfiguriert (`precondition_origins.default_lang`)

## Verdict

═══════════════════════════════════════
VERDICT: BROKEN
═══════════════════════════════════════
Zwei MEDIUM-Befunde mit Reproduktion: F001 (`rg --hostname-bin` startet ein Programm im Sperrzustand, Spec Punkt 5 verletzt) und F003 (Cache-Inhalt und Cache-Ordner ungeschützt, gecachte Gate-Skripte umschreibbar). F002, F004, F005, F006 sind LOW und nicht blockierend. Alle ACs außer dem offenen AC-16 sind belegt.
Tests: 23 passed, 1 failed (AC-16 Export fehlt, erwartet)
Edge cases: Whitelist, Override, Cache, Nebenläufigkeit, setup.py, Gate-Schutz, lokal kein Doppellauf geprüft
Regressions: Keine durch diese Änderung; Commit-Gate im fremden Repo ist vorbestehend (F006)
Checklist: alle Punkte außer AC-16 bewiesen
