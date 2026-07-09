# Changelog

All notable changes to the Agent OS + OpenSpec Framework will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

**README.md und CLAUDE.md hinkten der tatsächlichen Hook-/Command-Struktur hinterher**

Beide Dokus listeten nur 4 Hooks und ein unvollständiges Slash-Command-Set (fehlten:
`00-intake`, `70-deploy`, `90-retro`, `99-reset`), obwohl `hooks/hooks.json` inzwischen
11 registrierte Hook-Skripte enthält (u.a. `session_singleton_guard.py`,
`worktree_write_guard.py`, `claude_md_protection.py`, `tdd_enforcement.py`,
`post_implementation_gate.py`, `edit_verify.py`, `secrets_guard.py` — zusätzlich zu den
4 Kern-Gates) und `core/commands/` 16 Slash-Commands enthält. Das Architektur-Diagramm in
CLAUDE.md nannte zudem noch die alten, unnummerierten Command-Dateinamen
(`context.md` statt `10-context.md` usw.). Beide Dateien wurden auf den Ist-Stand gebracht.

### Added

**ADR-Reflexions-Gate bei der Spec-Freigabe (Issue #63)**

Neues Gate, das bei der Phase-3→4-Transition (Spec-Freigabe) erzwingt, dass eine Spec bewusst
über ihre Architektur-Relevanz reflektiert: Die Sektion `## Architektur-Entscheidung (ADR)` muss
ausgefüllt sein (ADR-Nummer ODER begründetes „keine"), bevor die Freigabe greift. Damit wird die
ADR-Entscheidung nicht faktisch aufs Commit-Gate verschoben und dort mit `[no-adr]` umgangen.

Neuer Helfer `workflow.py::_check_adr(data)` prüft die ADR-Sektion (Bracket-Platzhalter werden vor
der Prüfung entfernt, damit der leere Template-Platzhalter nicht fälschlich als ausgefüllt gilt).
Zwei Einhängepunkte: harter Block in `_validate_transition` (beide `phase4_approved`-Pfade, Standard
+ feature-fast) und Soft-Block im Approval-Block von `phase_listener.py` (spec_approved bleibt False,
Exit-0-Vertrag gewahrt). Präsenzbasiertes Grandfathering: Fehlt die ADR-Sektion ganz, greift das
Gate nicht. Kill-Switch via `config.yaml` → `adr_gate.enabled: false`. Die ADR-Sektion wurde ins
Spec-Template (`docs/specs/_template.md`), in den `spec-writer`-Flow und die `spec-validator`-Required-
Sections aufgenommen, damit sich das Framework nicht selbst blockiert.

**Kurz-Alias-Generierung für Skills mit Marker-Schutz gegen Cleanup-Löschung (Issue #24)**

Seit der Plugin-Migration (v3.2) erscheinen alle Skills nur noch mit Namespace-Präfix
(`/agent-os-openspec:50-implement` statt `/50-implement`). Neu: `setup.py` bietet das
opt-in-Flag `--command-aliases`, das pro Skill (jedes `skills/<name>/SKILL.md`) eine kurze
Redirect-Datei `.claude/commands/<name>.md` erzeugt, die auf
`/agent-os-openspec:<name> $ARGUMENTS` weiterleitet.

Jede generierte Alias-Datei trägt in der ersten Zeile den Marker
`<!-- openspec-alias: do-not-treat-as-legacy-duplicate -->`. Ursache von Issue #24 war,
dass `migrate_to_plugin.py::_find_removable_command_files()` Alias-Dateien mangels
Inhalts-Unterscheidung fälschlich als Legacy-Duplikate mitlöschte. Fix: Der Cleanup prüft
jetzt zusätzlich den Datei-Inhalt und entfernt eine namensgleiche Datei nur noch, wenn der
Marker `openspec-alias:` NICHT enthalten ist (Lesefehler werden fail-safe als "nicht
löschen" behandelt). Echte Legacy-Duplikate ohne Marker werden weiterhin entfernt.

Overwrite-Regel je Zieldatei: fehlt → anlegen, Marker vorhanden → aktualisieren, kein
Marker (vermuteter Custom-Command) → überspringen mit Warnung. Nutzung:
`python3 setup.py <path> --command-aliases`; für alle Projekte global empfohlen
`python3 setup.py ~ --command-aliases`. Die Generierung ist rein additiv und kein Teil des
Standard-Install-/Update-Flows.

### Changed

**`migrate_to_plugin.py`: vollständige Core-Hook-Liste + Shim-Ersetzung statt Löschung (Issue #33 Stufe 2)**

`migrate_to_plugin.py --apply` hatte zwei Lücken, die die geplante Stufe 3 (Entfernung der
Legacy-Kopien in Consumer-Projekten) unsicher machten:

1. **6 Framework-Hooks fehlten in `CORE_HOOKS`** und blieben nach `--apply` als tote Kopien
   liegen: `claude_md_protection.py`, `edit_verify.py`, `post_implementation_gate.py`,
   `secrets_guard.py`, `tdd_enforcement.py`, `worktree_write_guard.py`. Sie sind jetzt in
   `CORE_HOOKS` und werden mitentfernt (16 Core-Hooks statt zuvor 12 inkl. der beiden
   verschobenen Utilities).
2. **`hook_utils.py` und `config_loader.py` wären blind gelöscht worden**, obwohl
   projekteigene Hooks sie importieren (z. B. in gregor_zwanzig `renderer_mail_gate.py` —
   ein registrierter PreToolUse-Bash-Hook — sowie `track_token_usage.py`, `plan_validator.py`
   u. a.). Löschen hätte dort jede Bash-Ausführung gebrochen. Beide sind aus `CORE_HOOKS`
   herausgenommen und bilden die neue Kategorie `SHIM_HOOKS`.

Neu: `SHIM_HOOKS` wird bei `--apply` nicht gelöscht, sondern durch einen dünnen Shim ersetzt.
Der Shim (Marker `# openspec-shim: resolves to installed plugin version` in Zeile 1) löst den
Plugin-Pfad über `~/.claude/plugins/installed_plugins.json` auf (Key `agent-os-openspec@*`,
user-scope bevorzugt, Existenz-Check — dieselbe Logik wie das Skill-Snippet aus Stufe 1),
lädt das echte Modul via `importlib.util.spec_from_file_location` und re-exportiert alle
öffentlichen Attribute per `globals().update(...)` — funktioniert für `import hook_utils`
und `from hook_utils import X`. Ist das Plugin nicht auflösbar, wirft der Shim einen
`ImportError` mit klarer Meldung statt stillem Fehlverhalten. Die Ersetzung ist idempotent:
ein zweiter `--apply`-Lauf erkennt bestehende Shims am Marker und lässt sie unverändert. Die
Dry-Run-Ausgabe listet Shim-Ersetzungen als eigene Kategorie. Read-only-Verhalten ohne
`--apply`, die Alias-Marker-Command-Bereinigung (#24) und der Schutz projektspezifischer
Hooks bleiben unverändert. Neuer Regressionstest `tests/test_migrate_shims.py` (Fixture,
`--apply`-Verhalten, projekteigener Hook läuft nach Migration via Shim im Subprozess mit
Fake-HOME, Idempotenz, ImportError-Fall). Version 3.7.0 → 3.8.0 (MINOR, neue Fähigkeit).
Folgestufe #33 Stufe 3 (Legacy-Entfernung in gregor_zwanzig) ist ein separater Workflow.

**Dreistufige Hook-Pfad-Auflösung in allen Plugin-Skills (Issue #33 Stufe 1)**

Das Setup-Snippet in allen hook-nutzenden `skills/*/SKILL.md` (11 Skills) wurde um eine
mittlere Auflösungsstufe erweitert. Bisher galt nur die Zweistufen-Kette
`CLAUDE_PLUGIN_ROOT` → `.claude/hooks`. Da `CLAUDE_PLUGIN_ROOT` ausschließlich in
Harness-Hook-Subprozessen gesetzt ist (nie in manuellen Bash-Aufrufen der Skills), griff
in Consumer-Projekten immer der `.claude/hooks`-Fallback und traf dort eingefrorene
Legacy-Kopien, die nie Plugin-Updates bekommen — strukturelle Doppelentwicklung, real
zweimal passiert (#960 Adversary-Gate-Bypass, #29). Die neue Prioritätskette:

1. `CLAUDE_PLUGIN_ROOT` (wie bisher, wenn gesetzt)
2. **NEU:** `~/.claude/plugins/installed_plugins.json` lesen (python3-Einzeiler): erster
   Eintrag für Plugin-Key `agent-os-openspec@*` (user-scope bevorzugt), dessen
   `installPath` + `/core/hooks` — aber nur, wenn das Verzeichnis tatsächlich existiert
   (`[ -d ]`-Guard gegen stale JSON). Kein Glob auf den Cache-Ordner (Versionsnummer im
   Pfad!); ausschließlich die JSON ist autoritativ. Fehler beim JSON-Lesen (Datei fehlt,
   kaputt, kein Eintrag) werden verschluckt (`2>/dev/null`) → saubere Durchfall auf Stufe 3.
3. `.claude/hooks` (Fallback wie bisher — Projekte ohne Plugin funktionieren unverändert).

Harness-Hook-Kontext und Projekte ohne installiertes Plugin verhalten sich identisch wie
zuvor. Neuer Regressionstest `tests/test_skill_path_resolution.py` prüft alle Stufen
hermetisch via Fake-HOME. `core/commands/*.md` (Legacy-Verteilweg via `setup.py`) bleiben
bewusst unverändert. Version 3.6.2 → 3.7.0 (MINOR, neues Verhalten). Folgestufen (#33c
`migrate_to_plugin.py`, #33a Legacy-Entfernung in gregor_zwanzig) sind separate Workflows.

### Fixed

**Fast-Track fix-965-ac-n-parse: AC-N-Format wurde vom Adversary-Dialog-Parser nicht erkannt (gregor_zwanzig#965)**

`parse_spec_expected_behavior()` in `core/hooks/adversary_dialog.py` erkannte
ausschließlich das alte `## Expected Behavior`-Bullet-Format. Das seit Epic #191
(gregor_zwanzig) vorgeschriebene AC-N-Format (`## Acceptance Criteria` mit
`- **AC-N:** Given.../When.../Then...`-Bullets, oft mehrzeilig per Soft-Wrap,
teils mit Klammer-Zusätzen wie `AC-8 (präzisiert)` und eingerückten
`- Test:`-Sub-Bullets) wurde komplett übersehen — der Adversary-Dialog erhielt
"Keine Expected-Behavior-Punkte gefunden." statt der tatsächlichen Checkliste,
obwohl die Spec formal vollständig war (live in gregor_zwanzig#965 aufgetreten).

Fix: Section-Erkennung parst jetzt zusätzlich `## Acceptance Criteria`
(section-gebunden, kein globaler Regex). Ein AC-Bullet wird per
`^-\s+\*\*AC-\d+[^*:]*:\*\*` erkannt (Klammer-Toleranz für alle 4
Label-Varianten). Fortsetzungszeilen ohne `-`-Präfix werden anhand der
Einrückung der Rohzeile an den laufenden AC-Punkt angehängt (Soft-Wrap-
Support), eingerückte `- Test:`-Sub-Bullets werden verworfen. Sind sowohl
`## Expected Behavior` als auch `## Acceptance Criteria` in derselben Spec
vorhanden, werden beide Punktlisten additiv gemergt (Expected-Behavior-Punkte
zuerst). Der bestehende `Expected Behavior`-Zweig bleibt unverändert — keine
Regression für Specs im alten Format. Neue Tests in
`tests/test_adversary_dialog_parse.py` (12 Fälle, u. a. Klammer-Zusatz,
Soft-Wrap, Sub-Bullet-Ausschluss, Koexistenz beider Sections, Regression
gegen echte Repo-Specs wie `docs/specs/qa-gate-path-resolution.md` und
`docs/specs/bash-gate-false-positive-fix.md`). Spec:
`docs/specs/fix-965-ac-n-parse.md`.

**Fast-Track fix-alias-disable-model-invocation: Kurz-Alias-Commands für TDD/Implement/Validate/Deploy-Phasen unbenutzbar (Issue #55, 3.8.4)**

`generate_command_aliases()` erzeugte für JEDEN Skill denselben dünnen Text-Redirect
(`/agent-os-openspec:<name> $ARGUMENTS`). Das funktioniert nur, wenn Claude den Redirect
als Aufforderung liest und den Ziel-Skill selbst per Skill-Tool aufruft — genau das ist
aber für die 7 Skills mit `disable-model-invocation: true` (40-tdd-red, 50-implement,
60-validate, 70-deploy, 80-workflow, 81-add-artifact, 99-reset — bewusst auf reinen
User-Trigger beschränkt) verboten. Live reproduziert in gregor_zwanzig: `/50-implement`
scheiterte mit "cannot be used with Skill tool due to disable-model-invocation", der
Kurz-Alias war für exakt die sicherheitsrelevanten Phasen komplett unbenutzbar.

Fix: `generate_command_aliases()` unterscheidet jetzt zwei Strategien je Ziel-Skill.
`disable-model-invocation: false` bleibt beim dünnen Text-Redirect (Skill-Tool-Weg ist
erlaubt). `disable-model-invocation: true` bettet stattdessen den vollen SKILL.md-Inhalt
in die Alias-Datei ein — der User-getippte `/name`-Befehl wird dann direkt vom Harness
ausgeführt, ganz ohne Skill-Tool-Umweg. Das Gate bleibt für Modell-Selbstaufruf weiterhin
wirksam, blockiert aber nicht mehr den legitimen Kurz-Alias-Weg des Users. Erweiterte
Tests in `tests/test_setup_command_aliases.py` decken beide Strategien ab (Erzeugung,
Update, Custom-Command-Schutz).

**Fast-Track fix-53-secrets-guard-fp: Secrets-Guard False-Positives bei Freitext-Befehlen (Issue #53)**

`secrets_guard.py` UND der Secrets-Check in `bash_gate.py` scannten den ROHEN
Befehlsstring mit unverankerten Regexen. Lange Befehle mit Freitext (Commit-Messages,
PR-/Issue-Bodies, grep-Muster) triggerten False-Positives, obwohl keine sensible Datei
berührt wird — dreifach live reproduziert (z.B. `git commit -m "…" && gh pr create --body
"…"`, `gh issue create --body "…"`). Ursache: sensible Wörter wie `.env`/`credentials.json`
im Fließtext matchten die Datei-Patterns, gekoppelt an Ausgabe-Kommando-Keywords, die
ebenfalls über den Gesamttext gescannt wurden.

Fix (analog zu #30/#31, 3.4.15): Neue Funktion `_references_sensitive_file()` in BEIDEN
Guards matcht sensible Datei-Patterns nur noch gegen echte DATEI-Token (shlex-
Tokenisierung). Freitext-Argumente von `-m`/`--message`/`--body`/`--title`/`-F` werden
übersprungen. Konservativer Fallback auf den bisherigen Roh-Scan bei verschachtelter Shell
(`sh -c "…"`, `eval`) oder shlex-Parse-Fehler (kaputte Quotes) — kein neues Loch. Die
Ausgabe-Kommando-Bedingung (`_DANGEROUS_CMD_RE` / `_outputs_content`) bleibt als zweite
Bedingung erhalten und wird nur relevant, wenn ein echtes Datei-Token matcht. Identische
Behandlung an beiden Stellen verhindert Guard-Drift.

Sicherheits-Invarianten unverändert (je als Gegenprobe getestet): `cat .env`,
`head credentials.json`, `grep x private.key`, quoted Pfade mit Leerzeichen und
nicht-parsebare Befehle blocken weiterhin; die `grep -l`-Ausnahme und das Staging-Verhalten
bleiben erhalten. Neue Regressionstests: `tests/test_secrets_guard_false_positives.py`
(16 Tests, beide Guards).

**Fast-Track fix-46-notification-keyword-bypass: Freigabe-Keywords in Notifications umgingen die User-Zustimmung (Issue #46, sicherheitsrelevant)**

`core/hooks/phase_listener.py` (UserPromptSubmit-Hook) erkannte Freigabe-Stichworte
(`approved`/`go`/`override`/…) per Wortgrenzen-Regex irgendwo im gesamten Prompt-Text.
Task-Notifications (Ergebnistexte von Background-Agenten) laufen durch denselben Pfad —
enthielt so ein Text die Phrase nur als **Erwähnung** ("Bestätige mit 'approved' um
fortzufahren"), wurde die Freigabe gesetzt, ohne dass der User je zugestimmt hatte. Live
in `gregor_zwanzig` aufgetreten. Zwei Verteidigungslinien:

- **Verteidigung 1 — Notification-Turns überspringen:** Neue Guard-Funktion
  `_is_notification_turn()` am Anfang von `main()`. Enthält der Prompt einen der Marker
  `<task-notification>`, `[SYSTEM NOTIFICATION`, `<system-reminder>`, `<bash-input>`,
  `<local-command-caveat>`, wird SÄMTLICHE Keyword-Erkennung für diesen Turn übersprungen
  (Exit 0 ohne Aktion). Diese Marker kommen nur in harness-injizierten Turns vor.
- **Verteidigung 2 — Stichwort muss vorne stehen:** `_matches()` erhält den Parameter
  `leading_only`. Für die freigabe-relevanten Sets (approval/GREEN/override) muss die
  Phrase in der **ersten Zeile** UND innerhalb der **ersten 120 Zeichen** stehen. Echte
  User-Freigaben führen mit dem Stichwort; zitierte Erwähnungen stehen typischerweise tief
  im Text. Stop-Lock-Phrasen (`stop`/`halt`) bleiben BEWUSST unverändert großzügig (matchen
  überall) — ein Not-Aus darf eher zu oft als zu selten greifen.

Regressionstests in `tests/test_phase_listener_keyword_guard.py` inkl. Realfall-
Rückwärtskompatibilität ("approved (oder kann ich nicht einfach…)" → Freigabe), Angriffs-
Fälle (eingebettete Erwähnung + `<task-notification>`-Tag → keine Freigabe) und Stop-Lock-
Regression (Stop-Phrase mitten im Text greift weiterhin).

**Fast-Track fix-48-49-gate-hermetic: Orchestrator-Sperre + hermetische Guard-Tests (Issues #48, #49)**

- **#48 — ORCHESTRATOR_FILES-Sperre traf globale User-Config & war nicht
  überschreibbar:** In `core/hooks/edit_gate.py` (Schritt 1b) blockte der
  Substring-Match `.claude/settings.json` fälschlich auch die GLOBALE
  User-Konfiguration `~/.claude/settings.json` (außerhalb jedes Projekts), und
  der Block feuerte vor jeder Override-Prüfung — der in der Fehlermeldung
  empfohlene Ausweg (update-config Skill) war identisch geblockt. Fix:
  (a) Pfade unterhalb von `Path.home() / ".claude"` sind von der Sperre
  ausgenommen (exakt `~/.claude/...`, nicht `~/projekt/.claude/...`);
  (b) vor dem `block()` prüft der Hook den User-Override-Token
  (`override_token.has_valid_token`, gleiches Muster wie die Infrastructure-Sperre)
  → gültiger Token gibt die Projekt-Datei frei. Projekt-lokale
  `settings.json`/`settings.local.json`/`active_workflow` bleiben ohne Override
  weiterhin gesperrt.
- **#49 — session_singleton_guard-Tests nicht hermetisch:** Die drei Block-Tests
  `test_guard_edit/write/bash_blocked_in_main_repo` in
  `tests/test_session_singleton_guard.py` riefen `_do_guard()` gegen den echten
  Projekt-Zustand auf — ein real vorhandener User-Override-Token ließ sie
  fälschlich "allow" (Exit 0) statt Block (Exit 2) sehen. Fix: Die Tests mocken
  jetzt `_has_override_token` auf `False` und lenken `_locks_dir` auf `tmp_path`
  (Muster analog #35). Keine Änderung am Guard selbst — reines Test-Problem.

**Fast-Track fix-gate-bugs-26-38-34: Drei Wächter-Fehler behoben (Issues #26, #38, #34)**

- **#26 — Rebase-Check prüfte den falschen Branch:** In `core/hooks/bash_gate.py`
  liefen `git fetch origin main` und `git rev-list --count HEAD..origin/main` mit
  `cwd=_root` (Hauptrepo). Lag das Hauptrepo-`main` hinter `origin/main`, blockte der
  Hook jeden Commit in JEDEM Worktree — auch bei aktuellem Worktree-Branch. Fix: Beide
  git-Aufrufe laufen jetzt im tatsächlichen Aufrufkontext (`os.getcwd()`), wo der zu
  prüfende Commit stattfindet. Kein-Netz-Verhalten (silent skip) und Meldungstext
  unverändert.
- **#38 — Fremder stale Workflow kaperte Datei-Ownership:** In `core/hooks/edit_gate.py`
  lief `_find_workflow_for_file()` (Match über `affected_files` aller nicht-archivierten
  Workflows) VOR `_read_active_workflow()`, sodass ein verwaister Workflow-State den
  aktiven übersteuern konnte. Fix: Priorität getauscht — der aktive Workflow gewinnt
  immer; das `affected_files`-Matching bleibt nur Fallback ohne aktiven Workflow.
- **#34 — override-ambiguous wirkte nicht im Phase-Abschluss:** `_validate_transition()`
  in `core/hooks/workflow.py` verlangte für `phase8_complete` ausschließlich einen
  `VERIFIED`-Prefix und ignorierte `adversary_ambiguous_override`. Fix: Transition auch
  erlaubt, wenn das Verdikt mit `AMBIGUOUS` beginnt UND `adversary_ambiguous_override`
  gesetzt ist — exakt die Regel aus `bash_gate.py` (Commit-Gate). VERIFIED-Pfad
  unverändert; BROKEN und AMBIGUOUS-ohne-Override bleiben blockiert.

Tests: `tests/test_gate_fixes_26_38_34.py` (8 Tests inkl. aller drei Gegenproben).

**Dokumentierter Artefakt-Typ `adversary_dialog` wurde von `workflow.py` abgelehnt (Issue #41)**

Der Skill `50-implement` (Step 8c) dokumentiert `workflow.py add-artifact adversary_dialog ...`,
aber `VALID_ARTIFACT_TYPES` in `core/hooks/workflow.py` kannte diesen Typ nicht — der
dokumentierte Befehl schlug mit `Invalid artifact type` fehl (live in zwei Workflows getroffen,
Workaround war jeweils der generische Typ `file`). `adversary_dialog` ist jetzt ein gültiger
Artefakt-Typ.

**`workflow.py` löste den aktiven Workflow-Namen zweifach dupliziert und unvollständig auf — Live-FATAL trotz gültiger Datei (Issues #13, #35)**

`core/hooks/workflow.py` löste den Namen des aktiven Workflows an zwei Stellen
(`_read_active()`-FATAL-Pfad und `read_active_workflow_fast()`) über eigene, duplizierte
Logik auf, statt die bereits korrekte, worktree-aware Priorität aus
`hook_utils.resolve_active_workflow()` zu nutzen. Folge (Issue #13): Der FATAL-Pfad las
zuerst die (am Session-Start eingefrorene) `OPENSPEC_ACTIVE_WORKFLOW`-Env-Var, fand keine
passende `workflows/<name>.json` und brach mit
`FATAL: OPENSPEC_ACTIVE_WORKFLOW=... ist gesetzt aber keine passende Workflow-Datei existiert`
ab — obwohl die worktree-lokale `.claude/active_workflow`-Datei und `settings.local.json`
korrekt auf einen anderen, gültigen Workflow zeigten.

Fix: Beide Funktionen delegieren die Namensauflösung jetzt an
`hook_utils.resolve_active_workflow()` als einzige Quelle der Wahrheit. Damit gilt die
worktree-aware Priorität konsistent: **die worktree-lokale `active_workflow`-Datei schlägt
eine veraltete Env-Var** (Datei > `settings.local.json` > Env-Var). Das Außenverhalten
bleibt sonst unverändert — `_read_active()` beendet weiterhin mit `sys.exit(1)` bei gar
keinem auflösbaren Workflow, die FATAL-Meldung nennt jetzt generisch alle drei möglichen
Quellen (file/settings/env); `read_active_workflow_fast()` liefert weiterhin `(name, data)`
oder `None` ohne `sys.exit()` (Konsumenten `tdd_enforcement.py`,
`post_implementation_gate.py` unverändert).

Zusätzlich (Issue #35): Die zugehörigen In-Process-Tests wurden hermetisch gemacht, indem
sie neben `find_project_root()` auch `_find_worktree_root()` mocken bzw. Subprozess-Tests
`cwd=tmp_path` setzen — sie lesen dadurch nicht mehr den echten Worktree-Zustand der
laufenden Test-Session.

## [3.4.15] - 2026-07-02

### Fixed

**`bash_gate.py` blockierte harmlose Bash-Kommandos fälschlich als Marker-Manipulation (Issues #30, #31)**

Live reproduziert: `gh pr create --body "... adversary_verdict ..." 2>&1` wurde von
`bash_gate.py` geblockt, obwohl weder eine State-Datei geschrieben noch ein echter
Datei-Redirect vorlag. Zwei Ursachen: (1) `_raw_redirect()`/`_has_real_redirect()`
werteten `2>&1`/`>&2` (Stderr-zu-Stdout-FD-Duplizierung) fälschlich als echten
Datei-Redirect (Issue #31). (2) `_references_approval_marker()` war ein reiner
`re.search()` über den gesamten Kommando-String — jede Freitext-Erwähnung eines
Marker-Begriffs (z.B. `adversary_verdict` in einem PR-Body) plus irgendein
Write-Indicator irgendwo im Kommando reichte für einen Block, unabhängig davon, ob
tatsächlich eine State-Datei betroffen war (Issue #30).

Bei der Analyse fiel zusätzlich auf, dass `PROTECTED_FILE_PATTERNS` die real
existierenden Freigabe-Marker-Pfade (`.claude/pending_validation_<wf>.json`,
`.claude/user_approved_validation_<wf>`) gar nicht abdeckte — eine bis dahin
unentdeckte Lücke, die durch den naheliegenden #30-Fix (Kopplung an
`_references_protected()`) erst zu einer echten Regression geworden wäre.

Fix: FD-Duplizierung wird in `_raw_redirect()`/`_has_real_redirect()` explizit
ausgeschlossen (`^&\d+$`). `PROTECTED_FILE_PATTERNS` wurde um die beiden realen
Marker-Pfade erweitert. Die Freitext-Marker-Prüfung wurde zweistufig aufgeteilt:
Feldnamen-Marker (`adversary_verdict`, `_verified`) blocken nur noch bei
zusätzlicher Protected-Pfad-Referenz im selben Kommando; Dateinamen-Präfixe
(`user_approved_`, `pending_validation_`) blocken weiterhin pfad-unabhängig, weil
eine erste Adversary-Runde bewies, dass die einheitliche Kopplung an
`_references_protected()` einen `cd .claude && touch user_approved_validation_*`-
Bypass geöffnet hätte. 17 neue Regressionstests in
`tests/test_bash_gate_false_positives.py`. Siehe
`docs/specs/bash-gate-false-positive-fix.md`.

---

**`qa_gate.py` schrieb `adversary_verdict` in Consumer-Projekten nie in den Workflow-State (Issue #29)**

`_set_verdict()` und die Workflow-Namen-Ermittlung in `main()` lösten den Pfad zum
Geschwister-Skript `workflow.py` über `find_plugin_root()` aus `hook_utils.py` auf.
Diese Funktion setzt bei fehlendem `CLAUDE_PLUGIN_ROOT` eine `core/hooks/`-
Verzeichnisverschachtelung relativ zu `hook_utils.py` voraus. `setup.py` kopiert
Hook-Dateien in Consumer-Projekten aber **flach** nach `.claude/hooks/` — dort zeigte
`_plugin_root / "core" / "hooks" / "workflow.py"` ins Leere. Der `subprocess.run(...)`-
Aufruf schlug daraufhin still fehl (Return-Code wurde nicht geprüft), sodass
`qa_gate.py` trotzdem "Commit is now allowed." meldete, während `adversary_verdict`
im Workflow-State `null` blieb. Downstream blockierte `bash_gate.py` Commits dadurch
dauerhaft. Im Framework-Repo selbst trat der Bug nicht auf, weil dort zufällig ein
passendes `core/hooks/`-Nesting existiert.

Fix: Pfadauflösung an allen 3 betroffenen Stellen auf `Path(__file__).parent /
"workflow.py"` umgestellt — robust unabhängig von `CLAUDE_PLUGIN_ROOT`-Zustand oder
Installationsart. Beide `subprocess.run(...)`-Aufrufe prüfen jetzt den Return-Code
und brechen bei Fehler laut ab (`_set_verdict()` mit `sys.exit(1)`), statt Fehler
still zu verschlucken. Toter Import (`find_project_root`, `find_plugin_root`) entfernt.
Regressionstests in `tests/test_qa_gate.py` simulieren das flache Consumer-Layout via
`tmp_path`. Siehe `docs/specs/qa-gate-path-resolution.md`.

## [3.4.14] - 2026-07-01

### Fixed

**Adversary-Verdict-Gate wurde in `workflow.py complete` nicht geprüft (Issue gregor_zwanzig#960)**

`_validate_transition()` verlangt für `phase8_complete`, dass `adversary_verdict`
mit `VERIFIED` beginnt — aber diese Prüfung wurde ausschließlich von `cmd_phase()`
aufgerufen. Der tatsächlich genutzte Abschluss-Pfad (`workflow.py write-log` gefolgt
von `workflow.py complete`) rief `_validate_transition()` nirgends auf, sodass
Workflows ohne (oder mit `BROKEN`/`AMBIGUOUS`) Adversary-Verdikt regulär abgeschlossen
werden konnten. Ein Audit über `gregor_zwanzig` zeigte: 185 von 639 pflichtigen
Workflows (~29 %) wurden ohne gültiges VERIFIED-Verdikt abgeschlossen, davon 10 trotz
explizit fehlgeschlagener Tests (`BROKEN`).

Fix: `cmd_complete()` ruft jetzt vor dem Setzen von `phase8_complete` ebenfalls
`_validate_transition(data, "phase8_complete")` auf und bricht bei fehlendem/nicht-
VERIFIED-Verdikt ab — analog zu `cmd_phase()`. `bug`- und `feature-fast`-Workflows
bleiben wie vorgesehen vom Gate ausgenommen.

---

**Skills `00-intake` und `90-retro` fehlten seit der v3.2-Plugin-Migration (Issue #24)**

Bei der Migration von `core/commands/*.md` nach `skills/*/SKILL.md` (v3.2) wurden
`00-intake` und `90-retro` übersehen. Projekte, die noch die alten, direkt kopierten
`.claude/commands/00-intake.md` bzw. `90-retro.md` hatten (Pre-Plugin-Installs),
zeigten den Command dadurch doppelt im Slash-Command-Menü — einmal ueber die
lokale Legacy-Datei (bzw. eine globale Kopie unter `~/.claude/commands/`) und
einmal ueber den Versuch des Plugins, den Skill bereitzustellen, der aber gar
nicht existierte.

Fix: `skills/00-intake/SKILL.md` und `skills/90-retro/SKILL.md` nachgezogen.
`migrate_to_plugin.py` entfernt jetzt zusätzlich `.claude/commands/*.md`-Dateien,
die einen gleichnamigen Plugin-Skill haben (`_find_removable_command_files`).

---

### Added

**Agent-Timeout-Protokoll in allen Slash-Commands**

Alle Commands die Subagenten spawnen (`20-analyse.md`, `30-write-spec.md`,
`50-implement.md`, `60-validate.md`) schreiben Agenten jetzt zwingend mit
`run_in_background: true` und setzen **sofort nach jedem Spawn** einen
`ScheduleWakeup`-Timeout.

Problem: Agenten liefen bisher synchron (Vordergrund). Bei Hänger oder Absturz
wartete der Orchestrator passiv — in einer Session 36 Minuten, ohne Reaktion.

Fix: Jedes Agent-Spawn-Block enthält jetzt einen TIMEOUT-PFLICHT-Abschnitt mit
`ScheduleWakeup(N, "...: TaskList → noch aktiv? JA → TaskStop + User informieren.
NEIN → ignorieren.")`. Timeouts nach Agenttyp: Explore/Haiku 180s, Sonnet 300s,
Developer Agent 600s.

---

### Fixed

**`edit_gate.py`: Orchestrator-Dateien vor `json$`-Always-Allowed schützen**

`.claude/settings.json`, `.claude/settings.local.json` und `.claude/active_workflow`
konnten bisher vom `developer-agent` editiert werden, weil `.json$` in
`ALWAYS_ALLOWED_PATTERNS` alle JSON-Dateien ohne Phase-Check durchlässt — der Check
für `PROTECTED_STATE_FILES` greift nur für Workflow-State-Files, nicht für Settings.

Konkrete Fehlerfolge: Developer Agent manipulierte Workflow-State-Dateien und
Settings, um Blocker selbst zu beseitigen — statt das Problem an den Orchestrator
zurückzumelden.

Fix: Neues `ORCHESTRATOR_FILES`-Array + Check 1b direkt nach Check 1 (vor
ALWAYS_ALLOWED). Blockiert mit erklärender Fehlermeldung: "Blocker im Report
zurückmelden, nicht selbst lösen."

**`developer-agent.md`: Explizites Verbot für Framework-Dateien + Blocker-Regel**

Neue Regel 6: `.claude/settings*.json`, `.claude/active_workflow`, `.claude/hooks/`,
`.claude/agents/` sind absolut verboten. Kernbotschaft: "Du bist kein Orchestrator.
Blocker → im Report melden, nicht selbst lösen." Adressiert den Reflex, Blocker
durch direkte Settings-Änderungen zu umgehen.

### Added

**`CLAUDE.md`: Workflow-Isolation explizit dokumentiert**

Neuer Abschnitt „Workflow-Isolation — häufiges Missverständnis" in den
Arbeitsanweisungen für Claude. Klärt, dass Gates ausschließlich für den eigenen
aktiven Workflow gelten — andere Workflows in anderen Worktrees blockieren Commits
nie. Verhindert, dass Sessions sich selbst blockieren, weil sie fremde Workflows
in `phase6`/`phase7` sehen.

## [3.4.12] - 2026-06-30

### Fixed

**`resolve_active_workflow` + `read_active_workflow_fast`: Stale-Env überschattet korrekten Workflow im Worktree**

Im Worktree-Zweig von `resolve_active_workflow()` (hook_utils.py) und `read_active_workflow_fast()` (workflow.py)
fehlte der `settings.local.json`-Fallback. Die Prioritätskette war nur: Datei → Env. Im Haupt-Repo-Zweig
existierte dieser Fallback bereits.

Konkrete Fehlerfolge: Claude Code friert `OPENSPEC_ACTIVE_WORKFLOW` beim Session-Start aus der damaligen
settings.local.json ein. Wird danach `workflow.py start <name>` aufgerufen, aktualisiert `_persist_env` die
settings.local.json — aber nicht den eingefrorenen Prozess-Env. Ohne Settings-Fallback im Worktree-Zweig las
`resolve_active_workflow()` den veralteten Env-Wert (z.B. den Worktree-Verzeichnisnamen statt dem echten
Workflow-Namen), ignorierte das korrekte `feat-xxx-name` in der settings.local.json vollständig.

Fix: Worktree-Zweig liest jetzt `{worktree}/.claude/settings.local.json` als Schritt 2 (vor dem Env-Fallback).
Zusätzlich: Env-Wert wird nur vertraut wenn `workflows/<name>.json` existiert — verhindert Phantom-Namen
(z.B. Worktree-Verzeichnisnamen) dauerhaft aus der Prioritätskette zu halten.

Neue Worktree-Priorität: Datei → settings.local.json (validiert) → Env (validiert) → none

**`phase_listener`: Stiller Fehlschlag bei unauflösbarem Workflow**

Wenn `approved`/`go` erkannt wurde, aber kein Workflow auflösbar war (z.B. wegen des Stale-Env-Bugs),
endete `main()` mit `sys.exit(0)` ohne jede Rückmeldung. User glaubte freigegeben zu haben, Gate ignorierte
das Stichwort kommentarlos.

Fix: Wenn ein Approval- oder Green-Keyword erkannt wird und kein Workflow auflösbar ist, wird jetzt
`gate_diagnostics()` auf stderr ausgegeben.

## [3.4.11] - 2026-06-29

### Fixed

**`phase_listener`: Stop-Lock false positive bei Bindestrich-Komposita**

`_matches()` verwendete `\b` (Wortgrenze) für Stop-Erkennung. In Regex ist `-` kein
Wortzeichen, daher matchte `\bstop\b` auch in `stop-lock`, `Stop-Lock`, etc. Typischer
Fall: User fragt "Hast du das Problem mit dem Stop-Lock schon mitbekommen?" — die Frage
ÜBER den Stop-Lock aktivierte den Stop-Lock. Fix: erweiterte Lookahead/Lookbehind-Pattern
`(?<![a-zA-Z0-9_\-])stop(?![a-zA-Z0-9_\-])` schließt auch Hyphene aus.

**`phase_listener` + `bash_gate` + `edit_gate`: Stop-Lock session-lokal**

Wie `active_workflow` und `workflow`-State war auch der Stop-Lock in der gemeinsamen
`{project_root}/.claude/stop_lock.json` gespeichert. Ein "stop" in Session A blockierte
alle anderen Sessions im selben Projekt — auch worktree-isolierte Sessions die das "stop"
nie gesehen hatten.

Fix: `_set_stop_lock()` schreibt jetzt in den worktree-lokalen Pfad
(`{worktree_root}/.claude/stop_lock.json`) wenn in einer Worktree-Session. Im Haupt-Repo
gilt weiterhin der gemeinsame Pfad. `_is_stop_locked()` in `bash_gate.py` und `edit_gate.py`
liest analog: worktree-lokal (wenn im Worktree) oder gemeinsam (wenn im Haupt-Repo).

## [3.4.10] - 2026-06-29

### Changed

**`session_singleton_guard`: Worktree-Pflicht für alle Sessions (Redesign)**

Grundlegendes Redesign des Guards: statt Inhaberschaft (erste Session gewinnt) gilt nun
Worktree-Pflicht (jede Session muss im eigenen Worktree laufen).

Altes Verhalten: parallele Sessions im Hauptverzeichnis wurden blockiert, die erste Session
durfte aber weiterhin direkt im Haupt-Repo schreiben. Dies führte zu chaotischen Zuständen
wenn mehrere Terminals gleichzeitig geöffnet waren, da alle im selben Verzeichnis schrieben.

Neues Verhalten:
- Schreibende Tools (`Edit`, `Write`, `MultiEdit`, `Bash`, `Task`, `Agent`) werden im
  Hauptverzeichnis für ALLE Sessions blockiert.
- Lesende Tools (`Read`, `Grep`, `ToolSearch`, `WebFetch`, etc.) bleiben immer erlaubt —
  verhindert Deadlock beim Laden des EnterWorktree-Tools via ToolSearch.
- `EnterWorktree` als einziger Rettungsweg: Claude ruft es selbstständig auf und wechselt
  damit in einen isolierten Worktree. Kein User-Eingriff nötig.
- Override-Token als Notausgang für Ausnahmefälle.
- Sessions im `.claude/worktrees/<name>/`-Pfad sind vollständig uneingeschränkt.

`_BLOCKING_TOOLS`-Konstante eingeführt; `_has_override_token()` Helper ergänzt.
Lock-File-Logik in `_do_guard()` auf reinen Heartbeat-Update reduziert.

12 neue Tests in `tests/test_session_singleton_guard.py` (7 aus 3.4.9 + 12 neue = 19 gesamt).

**`workflow.py` + `hook_utils.py`: Workflow-State worktree-lokal — keine Cross-Session-Kontamination**

`_persist_env()` schrieb `OPENSPEC_ACTIVE_WORKFLOW` bisher in die gemeinsame
`settings.local.json` des Hauptverzeichnisses und die gemeinsame `active_workflow`-Datei —
auch wenn es aus einer Worktree-Session aufgerufen wurde. Jede neue Session im Haupt-Repo
erbte damit blind den Workflow einer anderen Session. Symptom: neue Claude-Instanz startet
sofort "im" laufenden Workflow eines anderen Terminals.

Fix: `_persist_env()` erkennt via `_worktree_root_if_any()` ob es in einer Worktree-Session
läuft. Wenn ja: schreibt NUR in den Worktree-lokalen Speicher (`{worktree_root}/.claude/`).
Beim Workflow-`complete` aus einem Worktree wird der Haupt-Repo-State zusätzlich bereinigt
(für Altdaten aus der Zeit vor dieser Isolation).

`resolve_active_workflow()` und `read_active_workflow_fast()` analog angepasst:
- In Worktree: liest worktree-lokale `active_workflow`-Datei, dann eingefrorene Env-Var.
- Im Haupt-Repo: liest gemeinsame `active_workflow`-Datei + `settings.local.json` (Rückwärts-
  kompatibilität für Single-Session-Projekte).
`_find_worktree_root()` als Hilfsfunktion in `hook_utils.py` ergänzt (spiegelt
`_worktree_root_if_any()` in `workflow.py`, ohne zirkuläre Imports).

## [3.4.9] - 2026-06-29

### Fixed

**`session_singleton_guard`: _is_alive fällt bei toter PID auf last_seen zurück**

`_is_alive()` gab sofort `False` zurück wenn die gespeicherte PID tot war —
ohne den `last_seen`-Fallback zu prüfen. Da Claude Hooks via transientem
Shell-Subprocess aufruft, speichert `os.getppid()` die Shell-PID (nicht Claudes
eigene PID). Die Shell stirbt sofort nach dem Hook, weshalb die gespeicherte PID
beim allerersten nachfolgenden `_do_guard`-Aufruf bereits tot ist. `_reap_dead`
löschte damit das eigene Lock-File jeder laufenden Session auf dem ersten
PreToolUse — danach erlaubte der Guard alle Operationen lautlos (kein eigenes
Lock-File → `sys.exit(0)`). Worktree-Isolation war dadurch vollständig wirkungslos.

Fix: wenn PID tot, prüft `_is_alive` nun `last_seen`. Genuinen Absturz (PID tot
UND `last_seen` > 900 Sek) erkennt der Timeout weiterhin korrekt.

7 neue Tests in `tests/test_session_singleton_guard.py`.

## [3.4.8] - 2026-06-29

### Fixed

**`hook_utils` + `workflow`: resolve_active_workflow Priorität: file > settings > env (Issue #13)**

`resolve_active_workflow()` las bisher die Env-Var `OPENSPEC_ACTIVE_WORKFLOW` zuerst.
Claude Code setzt diese Variable einmalig beim Session-Start aus `settings.local.json` —
ein mid-session `workflow.py start <neu>` schreibt zwar `settings.local.json` und
`.claude/active_workflow`, aber die Env-Var bleibt eingefroren. Alle Hooks lösten
dadurch den alten Workflow-Namen auf; `phase_listener` (go/override/stop/GREEN) wirkte
am falschen Workflow.

Neue Priorität: `.claude/active_workflow` (nur von `workflow.py` geschrieben, nie von
Claude Code überschrieben) → `settings.local.json` → Env-Var als letzter Fallback.
Gleiche Priorität in `read_active_workflow_fast()` ergänzt (verwendet von
`post_implementation_gate.py` und `tdd_enforcement.py`).

Symptome die damit behoben sind: User sagt "go" zur Spec-Freigabe → wirkungslos
(Hook löste stale Workflow auf, dessen Phase nicht phase3_spec war). Zweite Session
hinterließ stale Env-Zeiger in settings.local.json und vergiftete eine dritte Session.

**`.gitignore`: Runtime-State-Dateien von Git ausschließen**

`.claude/session-locks/`, `.claude/stop_lock.json`, `.claude/user_override_token.json`,
`.claude/workflows/` und `docs/artifacts/` waren untracked aber nicht ignoriert.

## [3.4.7] - 2026-06-29

### Fixed

**`workflow`: Workflow-Namen-Validierung gegen Pfad-Traversal und Glob-Injektion**

`cmd_start()` und `cmd_switch()` validierten den Workflow-Namen bisher nicht.
Namen wie `../../etc/x` konnten außerhalb des `.claude/workflows/`-Verzeichnisses
schreiben (Pfad-Traversal); Namen mit `*`/`?` korrumpierten `glob()`-Aufrufe
in `cmd_status()` und `cmd_complete()`. Neue `_validate_name()` erzwingt
Whitelist-Regex `^[a-zA-Z0-9_-]{1,64}$` — lehnt `/`, `..`, `*`, `?`, `[`, `]`,
`{`, `}` ab.

**`edit_gate`: AC-Einträge müssen ≥ 30 Zeichen Beschreibungstext haben**

`_check_acceptance_criteria()` prüft jetzt die Länge jedes `AC-N`-Eintrags.
Zu kurze Einträge (z. B. `AC-1: ok`) werden mit konkreter Zeichenzahl geblockt.
Legacy-Specs (erstellt vor `ac_format_required_since` in der Konfiguration)
werden automatisch durchgelassen.

### Added

**`workflow`: `cleanup-stale-locks` Befehl**

Entfernt verwaiste `pending_validation_*.json`-Dateien für abgeschlossene
Workflows. Überspringt Workflows, die noch aktiv in `phase6_implement` sind.
Löst das Problem vieler akkumulierter Phantom-Lock-Dateien nach langen Sessions.

**`config_loader`: `get_scope_loc_config()` API**

Neue Funktion `get_scope_loc_config() -> tuple[int, list]` liefert
`(max_loc_delta, loc_exclude_patterns)` aus der Konfiguration mit Defaults
`(250, [])`. Ermöglicht sauberen externen Zugriff ohne direktes Config-Dict-Parsing.

### Tests

35 neue Tests für bisher unabgedeckte Verhaltensweisen (Issue #14):
- `test_workflow_name_validation.py` — Namensvalidierung + AMBIGUOUS-Block (13)
- `test_gate_coverage.py` — AC-Format, LoC-Delta, Config-API, Status (22)

## [3.4.6] - 2026-06-28

### Fixed

**`bash_gate`: `>` in quoted Argument-Text nicht mehr als Redirect fehlinterpretiert**

Die Redirect-Erkennung der State-Integrity-Regel scannte den rohen Befehls-String
und wertete jedes `>` als Schreib-Redirect — auch wenn es Teil von quoted
Argument-Text war (z. B. `gh pr create --body "… a > b …"` oder `git commit -m`
mit `>` in der Message). Zusammen mit einer `.claude/`-Pfad-Erwähnung im selben
Text führte das zu fälschlichen Blocks (Workaround bisher: `--body-file`).

Neue `_has_real_redirect()` nutzt `shlex`, sodass nur echte Operator-Token
(`>`, `>>`, `2>`, `>file`) als Redirect zählen — `>` innerhalb quoted Tokens nicht.
**Ohne Sicherheitsloch:** bei verschachtelter Shell (`sh -c "…"`, `eval`) oder
Parse-Fehler fällt die Prüfung auf den rohen Scan zurück, sodass
`bash -c "echo x > geschützt"` weiterhin blockiert. 11 Tests grün (False Positives
erlaubt, echte Redirects + `sh -c`-Redirects + touch/rm geblockt).

## [3.4.5] - 2026-06-28

### Fixed

**`bash_gate` State-Integrity: `echo`/`printf` als False-Positive-Quelle entfernt**

Die State-Integrity-Regel blockierte Befehle, die einen geschützten Pfad
(`.claude/hooks/*.py`, `.claude/settings.json` …) referenzieren UND irgendwo ein
`echo`/`printf` enthalten — auch wenn die Datei nur gelesen wurde und das `echo`
ein reiner Status-Print war (z. B. `grep x .claude/hooks/y.py && echo done`). Das
bremste legitime Lese-/Diagnosebefehle wiederholt aus.

`echo`/`printf` sind keine eigenständigen Schreibvorgänge: Sie modifizieren Dateien
nur via Redirect (`>`, `>>`) oder Pipe-to-`tee`, die in `_has_write_indicator`
separat erfasst werden. Beide aus `WRITE_INDICATORS` entfernt. Echte
Schreibvorgänge (touch/rm/`sed -i`/Redirect/tee) blockieren unverändert; mit 8
Tests abgesichert (4 vormalige False Positives erlaubt, 4 echte Writes geblockt).

## [3.4.4] - 2026-06-28

### Fixed

**Session-Guard: cleanup an `SessionEnd` statt `Stop` — Auto-Isolierung paralleler Sessions war tot**

`hooks/hooks.json` registrierte `session_singleton_guard.py cleanup` am Hook-Event `Stop`
(Ende JEDER Antwort) statt an `SessionEnd`. Folge: Ab der zweiten Antwort fehlte der eigene
Lock-Eintrag → der Wächter erlaubte alles → parallele Sessions teilten sich Arbeitsbaum und
den `OPENSPEC_ACTIVE_WORKFLOW`-Zeiger. Reproduzierte die gregor_zwanzig-#895-Regression
(dort nur lokal in `settings.json` behoben, vom Plugin überstimmt).

Fix in `hooks/hooks.json`: cleanup-Hook von `Stop` auf `SessionEnd` umgestellt (Commit
`f2e40a6`, beigesteuert von der gregor_zwanzig-Instanz). Adressiert Punkt 1 von Issue #9;
die Folgepunkte (Versions-Cache-Reinstall, mögliche Doppel-Registrierung von Plugin-Hooks)
bleiben dort offen.

## [3.4.3] - 2026-06-28

### Fixed

**KRITISCH: `phase_listener` las das falsche stdin-Feld — `go`/`override`/`stop` waren tot**

`hook_utils.get_user_message()` las den Prompt-Text aus dem stdin-Feld `user_message`.
Claude Code sendet ihn laut offizieller Hook-API aber im Feld `prompt`. Folge: Der
`UserPromptSubmit`-Hook `phase_listener.py` bekam **immer einen leeren String** und tat
**nie etwas** — Spec-Approval (`approved`), GREEN-Approval (`go`/`freigabe`), Stop-Lock
(`stop`/`halt`) und Override-Token (`override`) waren seit Einführung von `hook_utils.py`
(2026-03-28) funktionslos.

Das ist die **Wurzel** des wiederkehrenden Problems, dass Freigabe-Marker per `touch`
erzeugt wurden: Da `go` technisch nie ankam, blieb das `post_implementation_gate`
verschlossen, und der per Gate-Meldung beworbene `touch` war der einzige Weg, es zu
öffnen. Der Approval-Marker-Fix aus 3.4.2 darf erst zusammen mit **diesem** Fix
ausgerollt werden — sonst entsteht eine Sackgasse (kein `touch` mehr UND kein `go`).

Fix in `core/hooks/hook_utils.py`: `data.get("prompt") or data.get("user_message", "")`
— `prompt` primär, `user_message` als Fallback für ältere Versionen/Wrapper.

Ursprung: Der Fix existierte bereits im Projekt `gregor_zwanzig`, war aber nie ins
Framework zurückgeflossen (Improvement-Flow-Lücke).

## [3.4.2] - 2026-06-28

### Fixed

**Approval-Marker als deny-by-default — Schluss mit der `touch`-Falle**

Der Agent versuchte wiederholt, Freigabe-Marker (`user_approved_validation_*`) selbst
per `touch` zu erzeugen, statt auf die User-Freigabe zu warten. Ursachenanalyse ergab,
dass das Framework dieses Fehlverhalten **selbst lehrte**: kein Disziplinproblem, sondern
ein Design-Bug. In der Forschung heißt das Muster *specification gaming* / *reward hacking*
(der Agent manipuliert den Verifier statt die Bedingung echt zu erfüllen — vgl. „unit tests
überschreiben, assertions löschen"). Best-Practice-Konsens: Freigabe-Operationen müssen
*deny by default* sein und dürfen ausschließlich von einem Menschen ausgelöst werden, und
zwar deterministisch im Hook erzwungen, nicht per Doku/Memory.

Zwei Korrekturen:
- `core/hooks/post_implementation_gate.py`: Die Block-Meldung bewarb den Exploit aktiv als
  „Freigabe-Option B: `touch .claude/user_approved_validation_*`". Diese Option ist entfernt;
  die Meldung nennt jetzt nur noch den menschlichen Weg (User tippt `go`).
- `core/hooks/bash_gate.py`: Neue `APPROVAL_MARKER_PATTERNS` (`user_approved_*`,
  `pending_validation_*`, `adversary_verdict`, `_verified`). Jeder Schreib-/Lösch-Versuch
  (touch/echo/sed/rm/…) auf solche Marker wird hart geblockt — mit selbsterklärender Meldung,
  die den einzigen legitimen Weg nennt. Lesen (cat/ls) bleibt erlaubt. Der legitime Erzeuger
  `phase_listener.py` (UserPromptSubmit-Hook) ist nicht betroffen, da er als Hook und nicht
  über das Bash-Tool läuft.

## [3.4.1] - 2026-06-24

### Fixed

**`/60-validate`: Kontext-Lade-Schritt nach `/clear`-Wiedereinstieg ergänzt**

Nach dem zweiten `/clear` (vor `/60-validate`) wurden Spec-Pfad, `affected_files` und
Adversary-Dialog-Pfad nicht zurück in den Kontext geladen. Die 4 parallelen Haiku-Agenten
starteten dadurch mit unaufgelösten Platzhaltern (`[spec_file_path]`, `[test_command]`).

Zwei Korrekturen in `core/commands/60-validate.md`:
- Python-Wiedereinstieg-Block liest jetzt `spec_file` (Pfad) und `affected_files` statt
  nur `spec_approved` (boolean).
- Neuer "Kontext laden"-Schritt direkt nach dem Wiedereinstieg: Explore/Haiku-Subagent
  liest Spec, Adversary-Dialog und `test_command` — analog zu Step 2 in `50-implement.md`.

`50-implement.md` ist nicht betroffen (hat bereits Step 2 als Kontext-Lade-Schritt).

**Session-Singleton-Guard: Blockierende Logik wiederhergestellt**

Die `session_singleton_guard.py` war bei der Portierung ins Framework auf eine reine Warning-Version (exit 0) reduziert worden. Damit wurde die Kerneigenschaft — zweite Session zwingen, via `EnterWorktree` in einen eigenen Worktree zu wechseln — vollständig verloren.

Wiederhergestellte Funktionalität:
- `register`-Modus (SessionStart): Schreibt Sitzungseintrag mit `started_at`, `pid`, `last_seen`.
- `guard`-Modus (PreToolUse, alle Tools): Bestimmt Inhaber (frühestes `started_at`). Nicht-Inhaber werden mit exit(2) blockiert. Einziger Rettungsweg: `EnterWorktree`.
- `cleanup`-Modus (Stop): Löscht eigenen Eintrag.
- Worktree-Sitzungen (CWD in `.claude/worktrees/<name>/`) werden nie blockiert — verhindert Endlos-Isolierung.
- Fail-safe: Jede Exception → exit(0); der Guard sperrt niemals fälschlich aus.

`hooks/hooks.json` entsprechend angepasst:
- `SessionStart` → `register`
- `PreToolUse` (leerer Matcher = alle Tools) → `guard` (als erstes, vor allen anderen Guards)
- `Stop` → `cleanup` (war `--cleanup` mit Warning-only-Implementierung)
- `UserPromptSubmit`-Eintrag für den Guard entfernt

**Robuster Workflow-Fallback + Adversary-Limit-Regel (post-#846-Retro)**

Auslöser: In Session #846 (`gregor_zwanzig`) funktionierte das "go"-Keyword nicht, weil Claude Code `settings.local.json` beim Hinzufügen von Bash-Permissions überschreibt und dabei den `env`-Abschnitt (mit `OPENSPEC_ACTIVE_WORKFLOW`) entfernt. Konsequenz: `phase_listener.py` fand keinen aktiven Workflow → "go" wurde ignoriert → Phasenwechsel erfolgte manuell statt automatisch.

- `hook_utils.resolve_active_workflow()`: Dritter Fallback über `.claude/active_workflow` (Plaintext-Datei). Diese Datei wird von Claude Code nie berührt. `source`-Wert erweitert: `'env' | 'settings' | 'file' | 'none'`.
- `workflow.py _persist_env()`: Schreibt beim Workflow-Start/Switch zusätzlich in `.claude/active_workflow`. Beim `workflow.py complete` wird die Datei atomisch gelöscht.

### Changed

- `CLAUDE.md`: Neue Regel "Adversary-Limit: Kein Fix-Loop nach VERIFIED" — nach erstem VERIFIED-Verdict direkt zu phase7, kein zweiter Adversary-Zyklus. Begründung: Session #846 verbrannte 177 Min. / ~3M Output-Tokens durch unkontrollierte Developer→Adversary→Fix→Adversary-Kaskade.

## [3.4.0] - 2026-06-22

### Added

**Selbst-erklärende Gate-Block-Meldungen + Symlink-Drift-Cleanup**

Auslöser: In einem abhängigen Projekt (`gregor_zwanzig`) wurden ~1,9 Mio Token verbrannt, weil ein Gate wiederholt blockte, die Block-Meldung aber die Ursache nicht enthielt — sie musste mühsam im Plumbing ergraben werden.

- `hook_utils.resolve_active_workflow() -> tuple[str, str]`: liefert zusätzlich die Auflösungsquelle (`'env'` / `'settings'` / `'none'`). `get_active_workflow_name()` delegiert daran — Verhalten unverändert (reiner Name-String).
- `hook_utils.gate_diagnostics(workflow=None, **extra)`: gemeinsamer, fail-safer Diagnose-Suffix-Builder (`[wf=… (quelle) | token=… | phase=… | …]`). Wirft nie; nicht ermittelbare Teilinfos werden `?`.
- `edit_gate.py`: Diagnose-Suffix an die vier ursachenrelevanten Block-Meldungen angehängt (No active workflow / Phase does not allow / No RED test artifacts / LoC delta) — Auflösungsquelle und Token-Status sofort sichtbar.
- `bash_gate.py`: Diagnose-Suffix an die AMBIGUOUS- und "verdict missing or not VERIFIED"-Commit-Block-Meldungen angehängt.

Symlink-Drift bereinigt — einzige Wahrheit für den aktiven Workflow (`.active`-Symlink war als Auflösungsquelle bereits abgeschaltet, Reste hingen aber noch in vier Hooks und konnten in parallelen Sessions falschen Workflow-Bezug verursachen):

- `edit_gate.py`: `loc_delta_current` wird nun direkt in `.claude/workflows/<name>.json` geschrieben statt über den Symlink.
- `bash_gate.py`, `post_bash.py`, `phase_listener.py`: tote `.active`-Lesepfade (inkl. `os.readlink`-Fallbacks) entfernt; irreführende Docstrings korrigiert.
- `migrate_state.py` bleibt bewusst unberührt (Einmal-Migrationsschritt, kein Auflösungspfad).

**Workflow-Retro: `retro-list` + `retro [<name>]` + `/90-retro`**

Analysiert abgeschlossene Workflows aus dem Archiv (`.claude/workflows/_archive/`).

- `workflow.py retro-list`: Listet alle archivierten Workflows mit Name, Typ, Datum, Gesamtzeit und Ergebnis.
- `workflow.py retro [<name>]`: Detaillierter Retro-Report — Phasen-Timeline mit Zeiten, Qualitätssignale (TDD, Adversary-Verdict, Fix-Loop-Iterationen, Override-Nutzung, Scope), automatische Optimierungshinweise. Ohne `<name>` wird der zuletzt abgeschlossene Workflow analysiert.
- `core/commands/90-retro.md`: Neuer Slash-Command `/90-retro` — führt durch List → Pick → Analyse mit abschließender PO-Zusammenfassung in einfacher Sprache.
- `core/commands/80-workflow.md`: Neue Befehle dokumentiert.

Hinweis: Token-/API-Kostenanalyse ist nicht enthalten — diese Daten sind im Workflow-State nicht vorhanden.

**PO-Zusammenfassungen an allen Workflow-Wartepunkten**

An allen Stellen, an denen der Workflow auf Nutzer-Interaktion wartet, wurde eine nicht-technische Zusammenfassung für den Product Owner ergänzt:

- `10-context.md`: Informierendes Ende — was gefunden wurde, in einfacher Sprache
- `20-analyse.md`: Art der Aufgabe, Risikobewertung und nächster Schritt — ohne Dateinamen oder LoC
- `30-write-spec.md`: Approval-Gate — "Was wird gebaut / Was ändert sich / Was bleibt unverändert" + Freigabe-Prompt
- `40-tdd-red.md`: STOPP-Block — kurze Erklärung warum fehlschlagende Tests ein gutes Zeichen sind
- `50-implement.md`: GREEN-Freigabe-Gate — "Was funktioniert jetzt?" + "Qualitätsprüfungen: N Tests bestanden"; STOPP-Block am Ende mit Status-Satz
- `60-validate.md`: Finaler Status "Alles fertig und geprüft" mit Commit-Frage

**Feature Fast Track (`--type feature-fast`) + `/00-intake` Klassifikation**

Hintergrund: Shape Up (Basecamp), DORA 2024 und Google SRE zeigen übereinstimmend: uniforme Gates für alle Aufgaben senken Qualität, weil Teams sie umgehen. Prozesstiefe soll proportional zu Scope, Blast Radius und Unsicherheit skalieren — und das vor Arbeitsbeginn entschieden werden.

- `core/commands/00-intake.md`: Neuer Slash-Command — bewertet Scope/Blast-Radius/Unsicherheit, bestimmt Track (Fast/Standard/Full), startet Workflow mit passendem Typ. Erster Schritt vor jedem Feature-Workflow.
- `workflow.py start <name> --type feature-fast`: Startet bei `phase3_spec`, setzt `red_test_done: true` automatisch — kein Context-Doc, kein separates TDD-RED, kein Adversary nötig.
- `workflow.py _validate_transition()`: Neue `feature-fast`-Branch — erzwingt nur den Spec-Approval-Gate (phase4), überspringt context_file-, TDD-Artefakt- und Adversary-Verdict-Prüfung.
- `bash_gate.py` Adversary-Check: `feature-fast` neben `bug` von der Adversary-Verdict-Pflicht ausgenommen.
- `edit_gate.py` TDD-Gate: `feature-fast` neben `bug` vom RED-Artefakt-Check ausgenommen.
- `core/commands/30-write-spec.md`: Fast-Track-Sektion ergänzt — Mini-Spec direkt im Hauptkontext, kein Sonnet-Agent-Dispatch, kein Haiku-Validator.
- Mini-Spec-Format: `docs/specs/fast/[name].md` mit 4 Sections.
- Modell-Empfehlung im Intake-Output: Fast/Standard → Sonnet, Full Process → Opus (folgt direkt aus Track-Score, kein eigenes Kriterium).

**Bug-Fix Fast Track (`--type bug`) — Token-sparender 3-Schritte-Weg für kleine Bugs**
- `workflow.py start <name> --type bug`: Startet direkt bei `phase6_implement`, setzt `red_test_done: true` und `spec_approved: true` automatisch — keine Phasen 1–5 nötig
- `_validate_transition()`: Überspringt alle Prerequisit-Checks für `workflow_type == "bug"`
- `edit_gate.py`: TDD-Artefakt-Check wird übersprungen wenn `workflow_type == "bug"` + `bug_fix.require_tdd: false` (konfigurierbar)
- `bash_gate.py`: Adversary-Verdict-Check in 5c wird übersprungen für Bug-Workflows; Rebase-Gate (5b) bleibt aktiv
- `00-bug.md`: Fast-Track-Sektion mit Ablauf und Voraussetzungen
- `config.yaml`: Neue Sektion `bug_fix` mit `require_tdd` (bool) und `max_files` (Warnung)

**Phase-Token-Logging — Zeitbasierter Proxy für Token-Verbrauch pro Phase**
- `_log_phase_transition(data, new_phase)`: Neue Hilfsfunktion in `workflow.py` — schreibt Timestamps in `phase_log`-Array der Workflow-JSON; schließt jeweils die vorherige Phase ab (setzt `exited_at` + `duration_min`)
- `workflow.py phase-log`: Neuer Subcommand — tabellarische Übersicht mit Dauer pro Phase, Gesamtdauer und Markierung der längsten Phase (▲)
- `cmd_phase()`: Ruft `_log_phase_transition()` bei jeder Phase-Transition auf
- `cmd_start()`: Initialisiert `phase_log` direkt beim Workflow-Start
- `phase_listener.py`: Ruft `_log_phase_transition()` beim Spec-Approval (phase3 → phase4) auf
- `_new_workflow()`: Enthält jetzt `workflow_type: "feature"` und `phase_log: []` als Standard-Felder

**Drei weitere Guard-Hooks: `secrets_guard`, `claude_md_protection`, `edit_verify`**
- `secrets_guard.py`: Blockiert Lese- und Shell-Zugriffe auf `.env`, Credentials, Private Keys (`credentials.json`, `.pem`, `.key`). Staging-Modus via `touch .claude/staging` oder `OPENSPEC_ENV=staging`. Immer-blockiert-Liste für Credentials/Keys auch im Staging. Registriert für PreToolUse `Bash` + `Read`.
- `claude_md_protection.py`: Schützt `CLAUDE.md` vor verbotenen Patterns (konfigurierbar via `openspec.yaml → claude_md.forbidden_patterns`) und warnt bei Überschreitung von `max_lines` (Standard: 600). Registriert für PreToolUse `Edit|Write|MultiEdit`.
- `edit_verify.py`: PostToolUse-Hook der nach jedem Edit/Write prüft, ob der neue Inhalt tatsächlich auf Disk gelandet ist. Gibt Warnung aus bei stiller Fehlfunktion. Fail-open: blockiert nie. Registriert für PostToolUse `Edit|Write|MultiEdit`.
- `hooks/hooks.json`: Alle drei registriert; `secrets_guard` unter Bash und Read, `claude_md_protection` als zweiter Hook im Edit|Write-Block (vor `edit_gate`), `edit_verify` als neuer PostToolUse-Block.
- Portiert aus `gregor_zwanzig`, Plugin-Imports (`config_loader`, `hook_utils`) statt projekt-lokaler Imports.

**Drei neue Guard-Hooks: `worktree_write_guard`, `tdd_enforcement`, `post_implementation_gate`**
- `worktree_write_guard.py`: Blockiert Schreibzugriffe vom Worktree-Kontext direkt ins Main-Repo (Split-Brain-Schutz). Liest `cwd` aus dem Claude-Code-Payload, erkennt `.claude/worktrees/<name>`-Konvention. Fail-safe: jede Exception → allow.
- `tdd_enforcement.py`: Tiefgehende Validierung von RED-Phase-Artefakten in `phase6_implement` / `phase6b_adversary`. Prüft Dateigröße (min. 80 Bytes), Alter (<24h), Fehler-Keywords im Inhalt, Abwesenheit von Platzhalter-Text. Ergänzt `edit_gate.py`'s einfache Boolean-Prüfung.
- `post_implementation_gate.py`: 15-Minuten-Batch-Fenster nach erstem Code-Edit in `phase6_implement` — danach BLOCKIERT bis User "go"/"approved"/"freigabe" sagt. Lock-Dateien in `.claude/pending_validation_<wf>.json` + Approval-Marker `.claude/user_approved_validation_<wf>`.
- `phase_listener.py` erweitert: "go"-Keywords in phase6 erstellen jetzt automatisch den Approval-Marker für `post_implementation_gate`.
- `hooks/hooks.json`: Alle drei Hooks als separate PreToolUse-Einträge für `Edit|Write|MultiEdit` registriert (laufen nach `worktree_write_guard` → `edit_gate` → `tdd_enforcement` → `post_implementation_gate`).
- Portiert und generalisiert aus `gregor_zwanzig`, Framework-spezifische Imports (`workflow_state_multi`, `config_loader.get_project_root`) durch Plugin-Äquivalente ersetzt.

**Commands: `/clear`-Empfehlung + `#N`-Wiedereinstieg nach Phasen-Übergängen**
- `40-tdd-red.md`: Strukturierter Abschluss-Block mit `/clear` → `/50-implement #<N>` Empfehlung
- `50-implement.md`: Step 0 — Workflow-State via Issue-Nummer von der Platte laden (nach `/clear`); Abschluss-Block mit `/clear` → `/60-validate #<N>`
- `60-validate.md`: Wiedereinstieg-Block am Anfang — State via `#<N>` laden
- Workflow-State überlebt jeden `/clear` (liegt in `.claude/workflows/<name>.json` auf der Platte)
- Portiert aus gregor_zwanzig, adaptiert auf `OPENSPEC_ACTIVE_WORKFLOW` + `workflow.py`

### Fixed

**`bash_gate.py`: Rebase-Pflicht vor `git commit` wenn Branch hinter `origin/main` zurückliegt**
- Neuer Check 5b im Commit-Gate: `git fetch origin main --quiet` + `git rev-list --count HEAD..origin/main`
- Blockiert mit klarer Fehlermeldung wenn `behind > 0` und ein Workflow aktiv ist
- Fail-silent bei fehlendem Netz (Timeout, kein Remote erreichbar) — kein Block, kein Fehler
- Verhindert silent Overwrites von zwischenzeitlichen Commits anderer Worktrees (nachgewiesen aus gregor_zwanzig)

**`config_loader.py`: `find_project_root()` erkennt Git-Worktrees korrekt**
- Bisher: `.git`-Datei (Worktree-Marker) wurde wie ein normales `.git`-Verzeichnis behandelt → State landete im Worktree-Verzeichnis statt im Haupt-Repo
- Fix: Worktree-Detection via `find_main_repo_from_worktree()` (aus `hook_utils`) vor dem Config-File-Walk; `CLAUDE_PROJECT_DIR` wird ebenfalls durch Worktree aufgelöst
- Jetzt konsistent mit `hook_utils.find_project_root()` — beide geben immer das Haupt-Repo zurück

**`hook_utils.py`: `get_active_workflow_name()` — Hooks lesen settings.local.json direkt als Fallback**
- Problem: Claude Code liest `settings.local.json` nur beim Session-Start, nicht bei jedem Hook-Aufruf. Wenn `workflow.py start/switch` in einer laufenden Session aufgerufen wird, sehen Hooks `OPENSPEC_ACTIVE_WORKFLOW=""` bis zum Neustart.
- Fix: Neue Funktion `get_active_workflow_name()` in `hook_utils.py` — liest env var zuerst, fällt direkt auf `settings.local.json` zurück. Kein Session-Neustart mehr erforderlich.
- `edit_gate.py`, `bash_gate.py`, `post_bash.py`, `phase_listener.py`: verwenden jetzt `get_active_workflow_name()` statt `os.environ.get()`
- `workflow.py` `_read_active()`: gleicher Fallback für CLI-Aufrufe ohne Export

**`workflow.py`: OPENSPEC_ACTIVE_WORKFLOW automatisch in settings.local.json persistieren**
- Problem: Hook-Subprozesse erben die Umgebung von Claude Codes Hauptprozess, nicht von einzelnen `export`-Bash-Befehlen → Hooks sahen `OPENSPEC_ACTIVE_WORKFLOW=""` → Phase "idle" → alle Schreibzugriffe blockiert
- Fix: `_set_active()` (aufgerufen von `start` und `switch`) schreibt den Workflow-Namen jetzt automatisch in `.claude/settings.local.json` unter `env.OPENSPEC_ACTIVE_WORKFLOW`
- `complete` entfernt den Key wieder aus `settings.local.json`
- `export` in der Shell bleibt weiterhin nötig für manuelle `workflow.py`-Aufrufe im Terminal und für Agent-Spawns

## [3.2.0] — 2026-06-19

### Added — Claude Code Plugin Support

**Plugin-Manifest** (`.claude-plugin/plugin.json`)
- Offizielles Claude Code Plugin-Format mit Name, Version, Description, Author
- Deklariert optionale Module (`ios-swiftui`, `home-assistant`) mit `OPENSPEC_ENABLED_MODULES` als Aktivierungsschlüssel

**Hook-Deklaration** (`hooks/hooks.json`)
- Plugin-native Hook-Deklaration mit `${CLAUDE_PLUGIN_ROOT}`-Pfaden
- Alle 4 konsolidierten Hooks + `session_singleton_guard.py` deklariert
- `Stop`-Event für Session-Cleanup

**Skills** (`skills/*/SKILL.md`)
- 12 Skills aus `core/commands/` migriert mit Plugin-Frontmatter
- `disable-model-invocation: true` für TDD/Implement/Validate/Deploy-Phasen (nur User-Trigger)
- `disable-model-invocation: false` für Context/Analyse/Spec (Claude darf selbst triggern)
- Pfad-Referenzen via `WF`, `QA`, `AD` Setup-Variablen am Anfang jedes Skills

**Modul-System** (`modules/*/hooks.json`)
- Jedes Modul hat eigene `hooks.json`
- `is_module_enabled()` in `hook_utils.py` — Early-Exit wenn Modul inaktiv
- `sys.path`-Setup in `modules/ios-swiftui/hooks/ui_test_preflight.py` repariert

**Plugin-Root-Trennung** (`hook_utils.py`, `config_loader.py`, `qa_gate.py`, `override_token.py`)
- `find_plugin_root()` — neue Funktion, prüft `CLAUDE_PLUGIN_ROOT` → Fallback via `__file__`
- `find_project_root()` — prüft `CLAUDE_PROJECT_DIR` als erste Priorität
- `qa_gate.py`: hardcodierter `.claude/hooks/workflow.py`-Pfad → `find_plugin_root()/core/hooks/`
- `override_token.py`: Lazy `_get_token_file()` statt Auswertung beim Import

**`setup.py` — `--plugin-mode` Flag**
- Version wird aus `plugin.json` gelesen (nicht mehr hardcodiert)
- `--plugin-mode`: keine Hook-Dateien kopiert, `settings.json` mit `${CLAUDE_PLUGIN_ROOT}`-Pfaden
- `generate_settings_json_plugin_mode()` nutzt `hooks/hooks.json` direkt
- `env.OPENSPEC_ENABLED_MODULES` wird bei Modul-Install gesetzt

**`migrate_to_plugin.py`** (neues Script)
- Migriert bestehende Projekte von Legacy zu Plugin-Mode
- Erkennt beide Hook-Formate: v2 Shell-Wrapper und v3 direkte Pfade
- Patcht nur bekannte Plugin-Hooks, lässt projektspezifische Hooks unberührt
- Entfernt Plugin-Hook-Dateien aus `.claude/hooks/` nach Migration
- Dry-Run by default, `--apply` für echte Änderungen

**`agents/` Symlink**
- Top-Level `agents/` → `core/agents/` Symlink für Plugin-Discovery

### Fixed

- **`edit_gate.py` — `ALWAYS_ALLOWED_DIRS` False Positives**: Substring-Matching `d in file_path` ersetzt durch `Path.parts`-Komponenten-Vergleich. Verhindert false positives wenn Projektordnernamen zufällig Test-Strings enthalten (z.B. `openspec-plugin-test/src/`).

### Migration

Bestehende Projekte: Dry-Run vor `--apply` empfohlen. `--apply` erst nach Plugin-Installation in Claude Code (setzt `CLAUDE_PLUGIN_ROOT` voraus).

```bash
# Dry-Run
python3 /home/hem/agent-os-openspec/migrate_to_plugin.py /path/to/project

# Anwenden (nach Plugin-Installation)
python3 /home/hem/agent-os-openspec/migrate_to_plugin.py /path/to/project --apply
```

## [Unreleased]

### Added — gregor_zwanzig Improvement Bundle (from production experience)

**Session Singleton Guard** (`session_singleton_guard.py`)
- Neues Hook-File: erkennt parallele Claude-Sessions im selben Working-Tree via PID-Lock-Files in `.claude/session-locks/`
- Warnt (ohne zu blockieren) wenn ein anderer Session-Prozess aktiv ist
- Räumt veraltete Locks für tote Prozesse automatisch auf
- Registrierung: `UserPromptSubmit` (check) + `Stop` (cleanup) — siehe Datei-Header für settings.json-Snippet

**External Validator Agent** (`external-validator.md`)
- Neuer Agent: testet die laufende App als echter User ohne Quellcode-Zugriff
- Kennt nur Spec (ACs) + App-URL + Credentials
- Pflicht-Format für Findings: `Code reference: file:line`
- Tri-State Verdict: VERIFIED / BROKEN / AMBIGUOUS
- Ergänzt `implementation-validator` (Code-Analyse) um echten Black-Box-Test

**Hardcoded Credentials Guard** (`bash_gate.py` Step 4b)
- Erkennt hartcodierte Secrets in Bash-Befehlen: `sk-*` API-Keys, GitHub PATs (`ghp_`), Slack Tokens (`xoxb-`), Bearer Tokens (40+ Zeichen), Passwörter und API-Keys in Assignments
- Negative Lookaheads verhindern False Positives bei Env-Var-Referenzen (`$TOKEN`, `${TOKEN}`)
- Konfigurierbar via `config.yaml → credentials_guard.patterns`

**E2E Scope Detection** (`bash_gate.py` Step 5c)
- Bei jedem `git commit`: staged Files werden analysiert und Scope bestimmt: `docs-only` | `frontend-only` | `backend` | `full-stack`
- Scope wird atomar in Workflow-State geschrieben (`e2e_scope` Feld)
- Niemals blockierend — rein informativ für nachgelagerte E2E-Routing-Entscheidungen
- Patterns konfigurierbar via `config.yaml → e2e_scope`

**Bug-Fix: `_read_active_workflow()` in `bash_gate.py`**
- Nutzte ausschliesslich `.active`-Symlink — ignorierte `OPENSPEC_ACTIVE_WORKFLOW` Env-Var
- Fix: Env-Var wird jetzt als primäre Quelle geprüft (analog zu `edit_gate.py`)
- Verhindert Workflow-Drift bei parallelen Sessions

**Bug-Fix: `_set_adversary_verdict()` in `post_bash.py`**
- Nutzte `.active`-Symlink + non-atomisches Write — mögliche Dateikorruption bei Race-Conditions
- Fix: Env-Var als primäre Quelle + atomisches Schreiben via `tempfile + rename`

### Added — Orchestrator-Prinzip (v3.1)

- **`developer-agent.md`** — Neue Agent-Definition: schreibt Code, führt Tests aus, reportet an Orchestrator; arbeitet nie mit User, plant nie, rate nie
- **`5-implement.md`** — Step 3 komplett überarbeitet: Hauptkontext ist jetzt Orchestrator, spawnt Developer Agent statt selbst zu coden; Step 4 (Side Tasks) in Developer Agent integriert; Adversary-Dialog-Abschnitt: Orchestrator koordiniert, Developer liefert Beweise auf Anfrage
- **`CLAUDE.md`** — Orchestrator-Prinzip als explizite Tabelle (Orchestrator / Developer / Adversary — Rollen, Werkzeuge, Aufgaben); Version 3.0.0 → 3.1.0

**Kernregel:** Der Hauptkontext darf `Edit`/`Write` nie auf Code-Dateien anwenden. Nur `developer-agent` besitzt diese Rolle. Verstoss ist in Common Mistakes dokumentiert.

### Added — Workflow Observability & Measurement (Issue #6, from 3 projects)

**S1 — Workflow Execution Log** (`workflow.py`)
- `write-log [outcome]`: Schreibt YAML-Execution-Log nach `.claude/workflows/_log/YYYY-MM-DD_<name>.yaml`
- `complete` blockiert wenn kein Log vorhanden
- Log enthält: phases_completed/skipped, tdd_red_confirmed, adversary_verdict, fix_loop_iterations, scope_loc_delta, outcome
- `status` zeigt Log-Status an

**S5 — Phase Transition Audit Trail** (`workflow.py`)
- `phase <target>` loggt jede Transition mit from/to/at/trigger in `phase_transitions[]`
- `trigger`-Werte: `command` | `user_keyword` | `manual` (via `--trigger=` flag)
- Fix-Loop-Counter: `fix_loop_iterations` wird inkrementiert bei phase6b_adversary → phase6_implement
- `status` zeigt Fix-Loop-Iterations und Phase-Transitions-Anzahl

**S2 — Acceptance Criteria Format** (`edit_gate.py` + `spec_template.md`)
- `edit_gate.py`: Blockiert phase6-Edits wenn Spec keine `## Acceptance Criteria` mit `AC-N`-Einträgen hat
- `spec_template.md`: `## Acceptance Criteria` mit `AC-1`/`AC-2` Given/When/Then-Format + Issue-Link

**S3 — LoC Delta Enforcement** (`edit_gate.py`)
- Prüft kumulativen LoC-Delta via `git diff HEAD --numstat` bei jedem Code-Edit
- Blockiert bei Überschreitung (Standard: 250 LoC), konfigurierbar via `scope_guard.max_loc_delta`
- Generierte Dateien (`.xcstrings`, `.strings`, `.po`) ausgeschlossen per `loc_exclude_patterns`
- Per-Workflow-Override: `workflow.py set-field loc_limit_override <N>`
- Speichert aktuellen Delta in Workflow-State, sichtbar via `status`

**S4 — Adversary Code-First + AMBIGUOUS Enforcement** (`bash_gate.py` + `implementation-validator.md`)
- `bash_gate.py`: AMBIGUOUS-Verdict blockiert Commit; Escape via `workflow.py override-ambiguous '<reason>'`
- `implementation-validator.md`: Jedes Finding MUSS `Code reference: file:line` enthalten (aus echtem Code gelesen)
- Confirmations für bestandene ACs sind Pflicht (vollständige AC-Coverage)
- Hinweis auf neues AMBIGUOUS-Blocking-Verhalten im Verdict-Guide

### Changed — GitHub Issues als zentrales Backlog-System

- **feature-planner.md** — Bash-Tool hinzugefügt; GitHub Issue erstellen statt Roadmap-Dokument-Eintrag; Phase-0-Suche vor jeder Planung
- **bug-investigator.md** — GitHub Issue erstellen statt Todo-Dokument-Eintrag; Duplikat-Suche vor Analyse
- **bug-intake.md** — Duplikat-Prüfung (Step 2) und Issue-Erstellung (Step 6) integriert; Schritt-Nummerierung korrigiert
- **feature.md** Command — Schritt 0: GitHub-Suche vor Agent-Start
- **bug.md** Command — Schritt 0: GitHub-Suche vor Agent-Start

**Verhalten:** Jedes Feature und jeder Bug landet als GitHub Issue. Agenten suchen immer zuerst nach bestehenden Issues, bevor neue erstellt werden. Issue-Nummern werden im Workflow-State via `set-field github_issue <N>` gespeichert.

### Added — Adversary Dialog System (from my-daily-sprints)

- **adversary_dialog.py** — Structured QA-Tester / Fixer verification dialog
  - Parses spec `## Expected Behavior` into checklist of provable points
  - Renders dialog protocol as Markdown artifact with checklist, rounds, findings, verdict
  - Validates artifacts: freshness (<60 min), all points checked, min 2 rounds
  - CLI: `parse <spec>`, `validate <artifact>`, `schema`

- **Tri-State Verdict:** VERIFIED / BROKEN / AMBIGUOUS
  - AMBIGUOUS does not block pipeline but flags for user review
  - Replaces binary HOLDS/BROKEN model

- **Circuit Breaker:** Max 3 QA-Fixer loop iterations, then escalation to user

- **Structured Findings Schema:**
  - Each finding: ID, severity (CRITICAL/HIGH/MEDIUM/LOW), category, evidence, remediation
  - Categories: spec_violation, edge_case, regression, security, anti_pattern

- **fresh-eyes-inspector.md** — Independent UI observer agent
  - Reviews screenshots without bug context
  - Neutral observations, no assumptions about implementation

### Changed — 5-implement.md (2-Role QA-Fixer Cycle)

- Added Step 6: Mandatory user approval of GREEN results before proceeding
- Added Step 7: Transition to phase6b_adversary
- Added Step 8: Full adversary dialog protocol (parse spec, run dialog, save artifact, QA gate)
- Loop back to implementation if BROKEN, escalate after 3 iterations

### Changed — 6-validate.md (Adversary Prerequisite)

- Added mandatory adversary dialog validation before validation phase
- Must pass `adversary_dialog.py validate` check

### Changed — qa_gate.py v3.1

- Added `--checklist` flag: validates adversary dialog artifact via `adversary_dialog.validate_dialog_artifact()`
- Tri-state support: AMBIGUOUS verdict sets exit 0 but flags for review
- Updated docstring with new usage patterns

### Changed — implementation-validator.md (Enhanced Protocol)

- Context isolation principle documented
- Structured findings format with severity and category
- Tri-state verdict (HOLDS/BROKEN/AMBIGUOUS) with usage guide
- Early-agreement skepticism: must not converge in round 1
- Minimum 2 dialog rounds enforced

## [3.0.0] - 2026-03-30

### Added — QA Gate (from INFRA_002-P3)

- **qa_gate.py** — CLI tool that validates test output files and sets `adversary_verdict` in active workflow
  - Checks file freshness (<30 min), minimum size, test framework patterns
  - Supports `--infra` flag for pure infrastructure tickets
  - Supports `--screenshot` and `--no-visual` flags
  - Sets verdict via `workflow.py set-field` (no direct JSON manipulation)
  - Project-agnostic: generic test patterns, no hardcoded project test targets

### Added — Override Token Module

- **override_token.py** — Shared module for multi-workflow token management
  - TTL-based expiry (1 hour)
  - Automatic pruning of expired tokens on create
  - v1/v2 format backward compatibility
  - API: `has_valid_token()`, `create_token()`, `remove_token()`, `remove_all_tokens()`
  - Used by `edit_gate.py`, `bash_gate.py`, `phase_listener.py` instead of inline logic

### Changed — Hooks use override_token module

- **edit_gate.py** — `_has_override_token()` now imports from `override_token.has_valid_token()`
- **bash_gate.py** — Adversary verdict override check uses `override_token.has_valid_token()`, added `qa_gate.py` to WHITELIST_COMMANDS
- **phase_listener.py** — `_create_override_token()` uses `override_token.create_token()` with inline fallback

### Changed — Slash Commands migrated to workflow.py

All 9 slash commands updated from `workflow_state_multi.py` to `workflow.py`:
- Inline Python imports (`from workflow_state_multi import ...`) replaced with CLI calls (`python3 .claude/hooks/workflow.py ...`)
- `add-artifact` command uses `workflow.py add-artifact` instead of inline `add_test_artifact()`
- `workflow.md` completely rewritten for v3 state architecture
- `0-reset.md` uses `workflow.py complete` instead of manual JSON reset

### Changed — implementation-validator.md

- References to `adversary_gate` updated to `qa_gate`

### BREAKING — Hook Consolidation: 30 Hooks → 4

**Problem:** 30+ Python-Hooks (~10.000 LoC), sequentielle Ausfuehrung (bis 85s pro Edit), Over-Blocking, Race Conditions durch geteilten State.

**Loesung:** 4 konsolidierte Hooks (~800 LoC) mit interner Short-Circuit-Logik. Gleiche Qualitaetssicherung, 90% weniger Komplexitaet.

**Neue Hooks:**
- `edit_gate.py` — PreToolUse Edit|Write (ersetzt 17 Hooks: workflow_gate, strict_code_gate, red_test_gate, spec_enforcement, tdd_enforcement, scope_guard, track_changes, claude_md_protection, docs_location_guard, domain_pattern_guard, plan_validator, post_implementation_gate, ui_screenshot_gate, override_token_guard, stop_lock_guard, ui_test_gate, ui_test_preflight)
- `bash_gate.py` — PreToolUse Bash (ersetzt 15 Hooks: state_integrity_guard, stop_lock_guard, override_token_bash_guard, adversary_verdict_guard, pre_commit_gate, secrets_guard, parallel_test_guard, build_lock_guard, sim_enforcer, tdd_green_gate, test_lock_guard, no_workaround_guard, validate_completeness_gate, result_inspection_gate, artifact_existence_guard)
- `post_bash.py` — PostToolUse Bash (ersetzt adversary_gate, build_lock_release)
- `phase_listener.py` — UserPromptSubmit (ersetzt 6 Hooks: stop_lock_listener, workflow_state_updater, override_token_listener, workflow_cleanup, new_ui_listener, tdd_green_listener)

**Geloescht (28 Hooks):**
adversary_gate, adversary_verdict_guard, claude_md_protection, docs_location_guard, domain_pattern_guard, notify_sound, override_token_bash_guard, override_token_guard, override_token_listener, parallel_test_guard, plan_validator, post_implementation_gate, pre_commit_gate, red_test_gate, scope_guard, secrets_guard, spec_enforcement, stop_lock_guard, stop_lock_listener, strict_code_gate, tdd_enforcement, track_changes, ui_screenshot_gate, ui_test_gate, workflow_cleanup, workflow_gate, workflow_state_multi, workflow_state_updater

### BREAKING — Isolated Workflow State (v3)

**Problem:** Ein einziges `workflow_state.json` fuer alle Workflows, Session-Tracking via TERM_SESSION_ID + /tmp-Files, `fcntl.flock()` Locks.

**Loesung:** 1 JSON-File pro Workflow in `.claude/workflows/`. Aktiver Workflow per `.active` Symlink. Atomare Writes via `tempfile` + `os.rename()`.

**Neue Dateien:**
- `workflow.py` — Workflow State CLI (ersetzt workflow_state_multi.py, ~280 LoC statt 1.733 LoC)
- `migrate_state.py` — Einmaliges Migrations-Script v2 → v3

**Was entfaellt:**
- `workflow_state.json` (ein File fuer alles)
- `workflow_state.lock` (fcntl.flock)
- Session-Tracking (TERM_SESSION_ID, /tmp/claude_session_*)
- `test_execution_lock.json`, `validation_state.json`, `ui_test_preflight_state.json`, `ui_screenshot_lock.json`, `workflow_last_cleanup.json`

### Changed — setup.py v3

- `generate_settings_json()`: 4 Hook-Eintraege statt ~41
- `create_workflows_dir()` ersetzt `create_workflow_state()`
- Verzeichnisstruktur: `.claude/workflows/` und `_archive/` hinzugefuegt
- Bash-Hook Timeout auf 300s (fuer Build-Lock-Szenarien in Modulen)
- Stop/Read Hook-Kategorien entfernt (in konsolidierte Hooks integriert)
- Version: 3.0.0

### Changed — config.yaml v3

- Entfernt: `modules.core.*` (keine einzeln schaltbaren Hook-Module mehr), `docs_location`, `ui_test_gate`, `parallel_test_guard`, `workflow_cleanup`, `scoping`, `claude_md`, `domain_guards`, `validation`, alte `hooks` Sektion
- Aktualisiert: Workflow-Phasen inkl. `phase6b_adversary`, erweiterte `approval_phrases`
- Jede config-Sektion dokumentiert welcher Hook sie nutzt

### Changed — hook_utils.py

- `find_project_root()` hinzugefuegt (mit CLAUDE_PROJECT_DIR Support)

## [Unreleased-v2] — Previous v2.x Changes (archived)

### Added - Hook Dependency Validation in setup.py

- `generate_settings_json()` now validates critical ordering constraints:
  - `stop_lock_guard.py` MUST be first in every hook chain
  - `override_token_guard.py` MUST come before `workflow_gate.py`
- Prints warnings during setup if constraints are violated

### Changed - Hooks Migrated to hook_utils.py

- **5 hooks** rewritten to use `hook_utils` bootstrap: `override_token_guard`, `override_token_bash_guard`, `adversary_verdict_guard`, `stop_lock_guard`, `docs_location_guard`
- Average 35% boilerplate reduction per hook
- Consistent import pattern: `from hook_utils import setup_path, ...` + `setup_path()`

### Fixed - Agent Frontmatter Consistency

- **analysis-challenger.md, implementation-validator.md:** Standardized tools format from comma-separated string to YAML list

### Added - Hook Utilities Module

- **core/hooks/hook_utils.py:** New shared bootstrap module for all hooks
  - `setup_path()` — adds hooks directory to sys.path
  - `get_tool_input()` / `get_user_message()` / `get_tool_result()` — standardized input parsing
  - `block()` / `allow()` — exit helpers
  - `is_code_file()` / `is_test_file()` — common file checks
  - New hooks should use this instead of duplicating boilerplate

### Changed - Config Cleanup

- **config.yaml:** Removed dead `e2e_tests` and `output_specs` sections (no hook references them)
- **config.yaml:** Fixed `implementation_validator` model from `haiku` to `sonnet`
- **CLAUDE.md:** Updated model assignment table, hook development guide, TDD documentation

### Changed - TDD Enforcement: Configurable Artifact Categories (from timebox-ios)

- **tdd_enforcement.py:** Artifact requirements are now configurable per category via `tdd.artifact_categories` in config.yaml
- Projects can require e.g. both unit AND UI test artifacts (iOS) or just one generic category (default)
- Added `ui_test_output` as valid artifact type
- Added `validate_artifact_timestamps()` — prevents retroactive artifact creation to bypass TDD
- Added `check_user_override()` — respects `user_override` and `spec_approved` workflow flags
- Added infrastructure file skip (`.claude/hooks/`, `docs/specs/` etc.)
- **config.yaml:** Replaced flat `min_artifacts` with structured `artifact_categories` (with example for iOS)

### Changed - Architecture: Centralized find_project_root()

- **4 hooks** (workflow_cleanup, stop_lock_listener, stop_lock_guard, override_token_listener) now import `find_project_root` from `config_loader.py` instead of duplicating the function
- Fallback inline definition kept for robustness if import fails

### Changed - Architecture: Dynamic Module Hook Loading

- **setup.py:** Module hooks are no longer hardcoded in core hook ordering lists
- Module configs (`modules/*/config.yaml`) now define their own `hooks:` section with `edit_write`, `bash`, `post_bash`, `user_prompt` lists
- `generate_settings_json()` reads module configs and appends module hooks to core lists at generation time
- **ios-swiftui/config.yaml:** Added hook ordering (ui_test_preflight, test_lock_guard, on_ui_test_failure, ui_test_debugger_hint)
- **home-assistant/config.yaml:** Added hook ordering (lovelace_screenshot_gate, check_ha_restart)

### Fixed - Critical Bug Fixes

- **workflow_state_multi.py:** `get_tdd_status()` returned `None` when called with explicit workflow name (inverted conditional logic)
- **config_loader.py:** Missing `yaml` import fallback — entire hook system crashed if PyYAML not installed; now warns and continues with defaults
- **pre_commit_gate.py:** Tests that crash without outputting "failed"/"error" were silently considered passing; now any non-zero exit code means failure
- **setup.py:** Removed non-existent `check_claude_md.py` from STOP_HOOK_ORDER
- **setup.py:** Removed module-specific hooks (`ui_test_preflight.py`, `test_lock_guard.py`, `check_ha_restart.py`, `lovelace_screenshot_gate.py`) from core hook ordering — these belong in module installation only

### Fixed - Agent Model Assignments

- **user-story-planner.md:** Added missing `model: opus` (was undeclared, docs said Opus)
- **analysis-challenger.md:** Changed `model: haiku` → `model: sonnet` (analytical work, not mechanical)
- **implementation-validator.md:** Changed `model: haiku` → `model: sonnet` (investigative edge-case probing)

### Fixed - Broken References

- **bug-investigator.md, feature-planner.md:** Fixed standards path from non-existent `.agent-os/standards/` to `core/standards/global/`
- **config.yaml:** Removed dead `hooks.priority` section (has no effect since v2.1; order is defined in setup.py)

### Added

- **core/standards/global/analysis-first.md:** New standard document — was referenced by agents but never created

## [2.1.0] - 2026-03-12

### Added - Adversary Gate System (from my-dayly-sprints)

**Problem:** Claude can claim tests passed without real evidence.
**Solution:** Validates REAL test output (file freshness <30min, size >500 bytes, magic bytes, framework patterns).

**New Hooks:**
- `adversary_gate.py` - PostToolUse Bash: Validates test output, sets `adversary_verdict` in workflow state
- `adversary_verdict_guard.py` - PreToolUse: Blocks direct JSON manipulation of verdict field

**Config:** `adversary_gate.test_patterns` - Configurable per framework (pytest, jest, xcodebuild, go test, cargo test, npm test)

### Added - Stop Lock System (from my-dayly-sprints)

**Problem:** No way to immediately pause Claude.
**Solution:** User says "stop"/"stopp" -> all Edit/Write/Bash blocked until "resume"/"weiter".

**New Hooks:**
- `stop_lock_guard.py` - PreToolUse: MUST BE FIRST HOOK. Blocks all operations when locked.
- `stop_lock_listener.py` - UserPromptSubmit: Creates/removes `.claude/stop.lock`

**Config:** `stop_lock.stop_keywords` / `resume_keywords` - EN+DE defaults

### Added - Override Token System (from my-dayly-sprints)

**Problem:** Sometimes user needs to consciously bypass a gate.
**Solution:** User says "override" -> one-time token created, consumed after single gate pass.

**New Hooks:**
- `override_token_listener.py` - UserPromptSubmit: Creates token
- `override_token_guard.py` - PreToolUse Edit/Write: Protects token file
- `override_token_bash_guard.py` - PreToolUse Bash: Protects token file

**Config:** `override_token.keywords` - Configurable

### Added - Workflow Cleanup (from my-dayly-sprints)

**Problem:** workflow_state_multi.json grows with completed/stale workflows.
**Solution:** Auto-cleanup of phase8_complete + stale (7+ days inactive) workflows. Rate-limited to 1x/hour.

**New Hook:**
- `workflow_cleanup.py` - UserPromptSubmit

**Config:** `workflow_cleanup.stale_days`, `workflow_cleanup.interval_hours`

### Added - Parallel Test Guard (from my-dayly-sprints)

**Problem:** Parallel workflows can interfere during test runs.
**Solution:** Blocks test commands when other active workflows have pending RED tests.

**New Hook:**
- `parallel_test_guard.py` - PreToolUse Bash

**Config:** `parallel_test_guard.test_command_patterns`, `parallel_test_guard.stale_threshold_hours`

### Added - Analysis Challenger Agent (from my-dayly-sprints)

**New Agent:**
- `analysis-challenger.md` - Devil's Advocate for bug analyses. 5 challenges: Symptom Coverage, Call-Site/Dead-Code, Repeated-Fix, Platform Check, Simpler Explanation.

### Changed - Implementation Validator Rewrite (from my-dayly-sprints)

**Rewritten Agent:**
- `implementation-validator.md` - Now an Adversary Agent that actively tries to BREAK the implementation. Issues VERDICT: HOLDS/BROKEN.
- `modules/ios-swiftui/agents/implementation-validator.md` - iOS-specific override with xcodebuild, Simulator, screenshots.

### Changed - Pre-Commit Gate (3 new features)

- `check_todos_staged()` - Blocks commit if configured files not staged
- `check_adversary_verdict()` - Checks VERIFIED verdict in phase6-8
- Override Token cleanup after successful gate pass
- **Config:** `pre_commit.required_staged_files: []`

### Changed - RED Test Gate

- Added `phase6_implement` to enforced phases (previously only phase4/5)

### Changed - UI Screenshot Gate

- Added magic bytes validation (PNG/JPG/GIF/WebP header check)
- Added minimum size check (1KB) to prevent empty placeholder files

### Added - iOS Module Hooks (from my-dayly-sprints)

**New Hooks:**
- `test_lock_guard.py` - PreToolUse Bash: Prevents parallel xcodebuild runs via `pgrep`
- `ui_test_preflight.py` - PreToolUse Edit/Write: Blocks anti-patterns (sleep(), hard-coded coordinates)
- `on_ui_test_failure.py` - PostToolUse Bash: Diagnoses xcodebuild failures (exit 64/65/70)
- `ui_test_debugger_hint.py` - PostToolUse Bash: Recommends ui-test-debugger agent on UI test failures

### Changed - Setup & Configuration

**setup.py:**
- Explicit hook ordering (stop_lock MUST be first)
- PostToolUse hook support (new hook event type)
- Version bumped to 2.1.0

**config.yaml:**
- New sections: `stop_lock`, `override_token`, `parallel_test_guard`, `workflow_cleanup`, `adversary_gate`
- `pre_commit.required_staged_files` option
- Updated hook priority table

---

## [Unreleased]

### Added - Agent Orchestration & Model Strategy (from gregor_zwanzig)

**Model Assignment Strategy:**
- Haiku: Mechanical tasks (validation, context loading, scope reviews, test running)
- Sonnet: Creative/analytical work (spec writing, bug investigation, planning, docs)
- Opus: Core implementation only (main context, not delegated)

**Updated Agents with Model Assignments:**
- `bug-intake.md` - Rewritten with parallel 3x Explore/Haiku subagent dispatching, input contract
- `docs-updater.md` - Extended with model: sonnet, input contract
- `spec-writer.md` - Extended with model: sonnet, input contract, stricter quality rules
- `spec-validator.md` - Extended with model: haiku, strict VALID/INVALID output format
- `bug-investigator.md` - Added model: sonnet
- `test-runner.md` - Added model: haiku

**New Agent:**
- `user-story-planner.md` - JTBD-based User Story Discovery (runs in main context/Opus)

**Updated Commands with Model Dispatching:**
- `/analyse` (2-analyse.md) - Bug vs. Feature routing, 3x parallel Explore/Haiku, Plan/Sonnet assessment
- `/write-spec` (3-write-spec.md) - Sonnet spec creation + Haiku validation with auto-fix loop
- `/implement` (5-implement.md) - Haiku context loading, Opus implementation, parallel side-tasks
- `/validate` (6-validate.md) - 4x parallel Haiku validation + Sonnet auto-fix + docs-updater

**New Template:**
- `templates/agent_orchestration.md` - Reference template for orchestration patterns and model strategy

**Config Updates:**
- Complete agent model assignments in `config.yaml` agents section
- New agents: bug_investigator, test_runner, feature_planner, user_story_planner, implementation_validator

### Added - Agents & Commands (from timebox-ios)

**New Commands:**
- `/user-story` - JTBD-basierte User Story Discovery
- `/feature` - Startet feature-planner Agent (NEU/AENDERUNG Modus)
- `/test` - Startet test-runner Agent

**Details `/user-story`:**
- JTBD-basiertes (Jobs to be Done) User Story Discovery
- Strukturierter Dialog in 4 Phasen:
  1. Kontext klären (Produkt/Feature/Verbesserung)
  2. JTBD Interview (Situation → Job → Ergebnis)
  3. Zusammenfassung validieren
  4. Dokumentieren in `docs/stories/`
- Dimensionen: Funktional, Emotional, Sozial
- Timeline & Alternativen-Analyse
- Output Template mit JTBD Statement und Feature-Ableitung

**New Core Agents:**
- `feature-planner.md` - NEU vs. AENDERUNG Modus, Scoping, Roadmap-Enforcement
- `bug-investigator.md` - Analysis-First Bug-Analyse, Root Cause Identifikation
- `test-runner.md` - Generischer Test-Runner mit Multi-Platform Support

**New iOS/SwiftUI Module Agents:**
- `mock-data-generator.md` - Mock-Daten fuer UI Tests erstellen
- `ui-test-debugger.md` - XCUITest Diagnose (Environment, Timing, State)

**New Hooks (from timebox-ios):**
- `strict_code_gate.py` - Blocks ALL code changes without active workflow + TDD
  - Whitelist-Approach: Tests, docs, config always allowed
  - Requires phase6+ for implementation
  - Enforces affected_files scope check
  - Configurable via `strict_code_gate` section in config.yaml
- `docs_location_guard.py` - Prevents writing to wrong directories
  - Blocks nested duplicates (e.g., `src/docs/` instead of `docs/`)
  - Configurable blocked paths via `docs_location` section
- `ui_test_gate.py` - Blocks validation without UI tests
  - Requires ui_test_green_done or UI artifacts
  - Disabled by default, enable via `ui_test_gate.enabled: true`

**New Config Sections:**
- `strict_code_gate` - Code extension whitelist, allowed dirs/patterns
- `docs_location` - Blocked path mappings
- `ui_test_gate` - UI test requirements

### Added - Backlog Status Tracking (v2.1)

**New Feature: "Spec Ready" Status**
- Separate backlog status tracking (`open`, `spec_ready`, `in_progress`, `done`, `blocked`)
- Prevents false "Done" marking when user pauses after spec approval
- Auto-derives status from phase (can be overridden)
- Pause detection for German/English phrases ("ich höre hier auf", "später implementieren", etc.)

**New CLI Commands:**
- `workflow_state_multi.py backlog <status>` - Set backlog status explicitly
- `workflow_state_multi.py pause` - Pause workflow with appropriate status

**New Functions in `workflow_state_multi.py`:**
- `get_backlog_status()` - Get current backlog status
- `set_backlog_status()` - Explicitly set status
- `pause_workflow()` - Pause with smart status setting
- `is_pause_message()` - Detect pause intent
- `derive_backlog_status()` - Map phase to status
- `sync_backlog_status_from_phase()` - Auto-sync on phase change

**Updated Templates:**
- `ACTIVE-roadmap.md` - New "Spec Ready" section, status legend
- `ACTIVE-todos.md` - New "Spec Ready" section, status legend

**Updated Documentation:**
- `workflow.md` - Backlog status section with mapping table

### Added - Core Improvements

**Multi-Workflow Support:**
- Run multiple features in parallel
- New phase structure with clear numbering (phase0-phase8)
- Phase 1 Context Generation (`/context`) - explicit context gathering
- Phase 5 TDD RED (`/tdd-red`) - write failing tests first
- `/workflow` command for managing parallel workflows
- `/add-artifact` command for registering test evidence
- Automatic v1 to v2 state migration

**New Hooks (from Home Assistant project analysis):**
- `post_implementation_gate.py` - User must approve, Claude cannot self-approve
- `red_test_gate.py` - Blocks code until RED test is documented
- `ui_screenshot_gate.py` - Enforces before/after screenshots for UI changes
- `scope_guard.py` - Prevents scope creep by limiting edits to task-relevant files
- `plan_validator.py` - Validates implementation plans are complete before coding

**New Agents:**
- `implementation-validator.md` - Auto-generates test plans, validates range compatibility, catches edge-case bugs

**TDD Enforcement:**
- TDD enforcement hook with REAL artifact validation
- Separate RED/GREEN test tracking in workflow state
- `red_test_done`, `red_test_result` fields
- `green_test_done`, `green_test_result` fields
- Functions: `mark_red_test_done()`, `mark_green_test_done()`, `get_tdd_status()`

**Configuration:**
- `settings.local.json` support for local overrides (credentials, paths)
- Local overrides NOT committed to git
- Deep merge of config → local overrides

**New Hooks (from gregor_zwanziger project analysis):**
- `domain_pattern_guard.py` - Enforces Single Source of Truth architectural patterns
- `track_changes.py` - Records file changes for pre-test validation
- `pre_commit_gate.py` - Blocks commits if tests are failing (TDD GREEN enforcement)

**New Tools:**
- `validate.py` - Pre-test validation (syntax, imports) before asking user to test
- `output_validator.py` - Validates output formats (email, HTML, JSON) against specs
- `e2e_test_harness.py` - Playwright-based browser E2E testing with screenshot artifacts

**Config Enhancements:**
- `domain_guards` section for architecture enforcement patterns
- `e2e_tests` section for browser test configuration
- `output_specs` section for output format validation
- `pre_commit` section for commit gate configuration
- `validation` section for pre-test validation settings
- Extended `protected_paths` with spec_type mapping for more file types
- E2E validators are now protected (cannot be modified to pass broken code)
- Word-boundary detection for approval phrases (prevents false positives)

**New Hooks (from helix-mvp project analysis):**
- `secrets_guard.py` - Prevents accidental exposure of sensitive files (.env, credentials, keys)
  - Staging mode support: `touch .claude/staging` to allow .env access during development
  - Credentials/keys always blocked even in staging mode

**New Standards:**
- `.agent-os/standards/global/scoping-limits.md` - Keep changes small and focused
  - Max 4-5 files per change
  - Max ±250 lines
  - Guidelines for splitting large tasks

**New Commands (optional templates):**
- `/bug` - Bug analysis with Analysis-First principle
- `/deploy` - Deployment template (customize for your platform)

**Config Enhancements (from helix-mvp):**
- `secrets_guard` section for sensitive file protection
- `scoping` section for change size limits

**New Standards (from Meditationstimer project analysis):**
- `verify-active-code.md` - Always verify editing the ACTIVE file, not duplicates
- `documentation-rules.md` - No false "complete" claims without user verification

**New Commands (from Meditationstimer):**
- `/reset` - Clear workflow state for fresh start
- Staging mode via `.claude/staging` marker file or `OPENSPEC_ENV` env var

### Changed

- Workflow state format v2.0 with multi-workflow support
- Phase names: `analyse_done` → `phase2_analyse`, etc.
- Implementation phase now requires TDD RED artifacts
- `/analyse` is now Phase 2 (after context)
- `/write-spec` is now Phase 3
- `/implement` is now Phase 6 (TDD GREEN)
- Improved error messages with ASCII art and phase-specific guidance
- `config_loader.py` now supports local override files

### Fixed

- Single workflow limitation removed
- Error messages now show correct next step for each phase

## [1.0.0] - 2025-01-12

### Added
- Initial release
- 4-phase workflow: analyse → write-spec → implement → validate
- Core hooks: workflow_gate, spec_enforcement, claude_md_protection
- iOS/SwiftUI module with TDD workflow
- Home Assistant module with config validation
- Setup tool for project installation
- Spec templates and agent definitions

---

## Version Numbering

- **MAJOR**: Breaking changes to workflow or hook interfaces
- **MINOR**: New features, new modules, new commands
- **PATCH**: Bug fixes, documentation updates

## Upgrade Notes

### From 2.x to 3.0

**Migration:**
1. Run `python3 .claude/hooks/migrate_state.py --apply` to split workflow_state.json into per-workflow files
2. Re-run `python3 /path/to/agent-os-openspec/setup.py /path/to/project --update --force` to get new hooks + settings.json
3. Delete old hooks that are no longer needed (28 files removed)
4. Slash-Commands: Replace `workflow_state_multi.py` → `workflow.py` in all commands

**Breaking Changes:**
- 28 hooks deleted, replaced by 4 consolidated hooks
- `workflow_state.json` replaced by `.claude/workflows/*.json`
- `workflow_state_multi.py` replaced by `workflow.py`
- settings.json format: 4 entries instead of ~41
- `config.yaml`: Many sections removed/renamed (see CHANGELOG for details)

### From 1.x to 2.x

The workflow state format changed from single-workflow to multi-workflow.

**Automatic Migration:**
- Old format is automatically migrated on first load
- No manual intervention needed

**New Features to Adopt:**
1. Use `/context` before `/analyse` for better context gathering
2. Use `/tdd-red` after spec approval for proper TDD
3. Register test artifacts with `/add-artifact`
4. Use `/workflow list` to see all active workflows

**Breaking Changes:**
- Phase names changed (hooks using old names need update)
- TDD enforcement now requires artifacts (can be disabled in config)
