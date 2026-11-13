---
entity_id: fix-597-autoclear-klartext
type: bugfix
created: 2026-11-13
updated: 2026-11-13
status: draft
version: "1.0"
workflow: fix-597-autoclear-klartext
tags: [herdr, auto-clear, hooks, klartext, stop-hook, templates, e2e]
---

# Auto-/clear übersteht zurückgewiesene Antworten (Issue #597)

## Approval

- [ ] Approved

## Purpose

Der Auto-Modus mit Herdr-Auto-/clear bleibt an Phasengrenzen stehen (beobachtet nach `/40-tdd-red` und `/50-implement`, laut PO "mehr oder weniger alle Phasen inkl. `/70-deploy`"), sobald die Abschlussantwort einmal von einem anderen Stop-Hook zurückgewiesen wird. Ursachenkette (belegt): (1) Die Ausgabeblöcke der Vorlagen enthalten Git-Wörter ("committed", "Commit", "committen"); `klartext_gate.py` (#582) weist die wörtlich ausgegebene Abschlussmeldung deshalb per Exit 2 zurück. (2) Stop-Hooks laufen laut Claude-Code-Doku parallel, ohne Reihenfolge, keiner sieht das Verdict des anderen: `footer_gate.py` startet über `herdr_bridge.maybe_auto_clear` den Runner, während `klartext_gate.py` denselben Stop blockt. (3) `maybe_auto_clear` verbraucht beim Spawn die Grenze (`_consume_boundary`) und setzt den 600-s-Once-Lock; der Runner sieht den Folge-Stop und bricht mit "Claude arbeitet weiter" ab. (4) Der Folge-Stop trägt `stop_hook_active: true`, `maybe_auto_clear` verwirft die Grenze dort ausdrücklich (`skip: stop_hook_active`, #495). Ein zweiter Versuch ist damit unmöglich, obwohl nie `/clear` getippt wurde.

Kernproblem: Claude Code kennt kein Ereignis "Turn wirklich zu Ende, nachdem alle Stop-Hooks durch sind". Ein geblockter Stop erzeugt aber immer einen weiteren Stop (Cap 8 Blocks in Folge); der letzte Stop nach einer Ruhephase ist daher per Konstruktion das echte Turn-Ende.

Der PO-Einwand "Kannst du nicht viel sinnvoller mit herdr interagieren? Wirkt total kompliziert gedacht" führt zu einer einzigen Regel statt Sonderfällen: **Jedes saubere Antwortende darf die Übergabe starten, ein späteres ersetzt ein früheres, als erledigt gilt sie erst, wenn wirklich getippt wurde.** Der Grenz-Vermerk `auto_clear_boundary` wird zum einzigen Einmal-Token (Idempotenz-Schlüssel): Der Runner nimmt ihn atomar unmittelbar vor dem Tippen von `/clear`; wer ihn nicht bekommt, tippt nicht. Der 600-s-Once-Lock entfällt, ebenso der Verbrauch beim Spawn und die Sonderbehandlung von `stop_hook_active`. Zusätzlich verhindern bereinigte Vorlagen und eine Klartext-Vorprüfung den beobachteten Auslöser an der Wurzel. Herdr bleibt reine Tastatur (Begründung #506: Herdrs eigene Claude-Integration mappt `Stop` auf `idle` und hat dieselbe Lücke; `agent prompt` lehnt bei `blocked` ab).

## Source

- **File:** `core/hooks/herdr_bridge.py` (`maybe_auto_clear`, `_consume_boundary`, `_acquire_lock`/`_release_lock`, `spawn_auto_clear`, `_Runner`, `run_auto_clear`), `core/hooks/klartext_gate.py` (`main`), `core/hooks/footer_gate.py` (Aufrufstelle), `core/commands/40-tdd-red.md`, `50-implement.md`, `60-validate.md` (+ ggf. `01`, `82`, `83`, `90`, `99`, generierte `skills/*/SKILL.md`)
- **Identifier:** `herdr_bridge.maybe_auto_clear`, neu `_Runner._take_boundary`, `run_auto_clear` (Abbruchbehandlung), neu `klartext_gate.pruefe`

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `core/hooks/klartext_gate.py` (#582) | module | `treffer`, Ausnahmen; neu `pruefe(payload)` als wiederverwendbarer Kern von `main` |
| `core/hooks/footer_gate.py` | module | ruft `maybe_auto_clear` mit dem Stop-Payload auf; `_discard_boundary` (#497a) bleibt; `_record_stop` bleibt |
| `core/hooks/hook_utils.py` | module | `atomic_write_json`, `read_state_json`, `find_project_root` (Grenz-Entnahme im Hauptrepo-State) |
| `core/hooks/workflow.py` | module | schreibt `auto_clear_boundary` (`cmd_autoclear`, `_note_transition_boundary`), `expected_footer_command` |
| `scripts/sync_skills.py` | script | erzeugt `skills/*/SKILL.md` aus `core/commands/*.md`; Drift blockt Release |
| `scripts/e2e_auto_clear.sh` | script | E2E am echten Herdr (Szenarien A–S), lokal beim PO, nicht in CI |
| `fcntl` (Stdlib, POSIX) | extern | Datei-Sperre für die atomare Token-Entnahme (wie bestehende `_pp_flock`) |
| `docs/specs/fix-495`, `fix-497`, `fix-506`, `feat-467` | specs | Vorgänger; diese Spec ändert bewusst deren Verbrauchs-, `stop_hook_active`- und Once-Lock-Regeln |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| core/commands/40-tdd-red.md | MODIFY | Positiv-Block ("(committed)") und Checkpoint-Zeile "uncommitteten" ohne Git-Wörter ("gesichert", "ungesicherte Änderungen") |
| core/commands/50-implement.md | MODIFY | Positiv-Block ("Commit der Implementierung … committed … `git status`") und Checkpoint-Zeile ohne Git-Wörter |
| core/commands/60-validate.md | MODIFY | wörtlich ausgegebene Frage „Soll ich den Code committen?" (Ausgabeblock und Tabelle) → z. B. „Soll ich den Stand sichern?"; "Bereit für: Commit" und weitere Treffer in Ausgabeblöcken (u. a. "Merge-Commit", "Commit-Hash") in Alltagssprache |
| core/commands/01-feature.md, 82-test.md, 83-user-story.md, 90-retro.md, 99-reset.md | MODIFY (nur falls Treffer) | alle Treffer, die der neue Vorlagen-Test findet (laut Kontext-Scan Treffer in diesen Dateien), in Ausgabeblöcken und wörtlichen Fragen bereinigen |
| skills/*/SKILL.md | GENERATED | `python3 scripts/sync_skills.py` nach den Vorlagen-Änderungen |
| core/hooks/klartext_gate.py | MODIFY | `main` in reine Funktion `pruefe(payload) -> list[str]` + dünnes `main`; Verhalten unverändert |
| core/hooks/herdr_bridge.py | MODIFY | `maybe_auto_clear`: `stop_hook_active`-Zweig, `_consume_boundary` beim Spawn und Once-Lock raus, Klartext-Vorprüfung neu, Spawn übergibt `--boundary-at`; `_acquire_lock`, `_release_lock`, `_lock_active`, `_read_lock_state`, `AC_STATE_FILE`, `AC_LOCK_SECONDS` entfernen (nur wenn nach dem Umbau ungenutzt); `_Runner._take_boundary` neu (flock + atomares Löschen); `run_auto_clear`: Abbruchbehandlung (Token behalten/zurücklegen vs. verwerfen); `_consume_boundary` bleibt (footer_gate `_discard_boundary`, Negativ-Marker, veralteter Vermerk) |
| core/hooks/footer_gate.py | UNCHANGED (erwartet) | `payload` wird bereits durchgereicht (`_maybe_auto_clear(payload, …)`); `_discard_boundary` bleibt |
| tests/test_vorlagen_klartext_597.py | CREATE | Vorlagen-Test (AC-1) |
| tests/test_autoclear_retry_597.py | CREATE | Tests zu AC-2 bis AC-12 (RED zuerst) |
| tests/test_herdr_auto_clear_467.py | MODIFY | siehe "Anzupassende Bestandstests" |
| tests/test_autoclear_boundary_495.py | MODIFY | siehe "Anzupassende Bestandstests" |
| tests/test_autoclear_eigene_signale_506.py | MODIFY | siehe "Anzupassende Bestandstests" |
| tests/test_befehlsform_context_titel_499.py | MODIFY | liest `herdr_auto_clear_state.json` (Zeile ~327); Prüfung auf den Once-Lock-Schlüssel ersetzen durch: Datei existiert nicht, Grenze nach `OK` verbraucht |
| tests/test_klartext_gate_582.py | MODIFY (klein) | optional: `pruefe` direkt testen; bestehendes Verhalten von `main` bleibt grün |
| scripts/e2e_auto_clear.sh | MODIFY | Szenario R neu; Szenario D (entfernt Once-Lock-Datei, Zeile ~516) auf Wegfall des Locks anpassen |
| CHANGELOG.md | MODIFY | Eintrag unter [Unreleased] / Fixed (#597); keine Versionsnummer (Umsetzung schreibt ihn) |

### Estimated Changes

- Files: 2 neu (Tests), ~10 geändert + generierte `skills/`
- LoC: ca. +250/-120 (rund 60 % Tests)
- Risk Level: HIGH (Stop-Hook-Pfad läuft in jedem Projekt bei jedem Turn-Ende; Tipp-Sicherheit bei Berechtigungsdialogen)

## Implementation Details

**1. Vorlagen (Wurzel des beobachteten Auslösers).** Aus jedem wörtlich auszugebenden Block (Text zwischen den `---`-Trennern nach einer Überschrift mit "Ausgabe") und jeder wörtlich zitierten Frage („…") werden Wörter entfernt, die `klartext_gate.treffer` findet. Ersatz in Alltagssprache, z. B. "gesichert" statt "committed", „Soll ich den Stand sichern?" statt „Soll ich den Code committen?". Anweisungen an Claude außerhalb der Ausgabeblöcke (z. B. Checkpoint-Liste) dürfen Git-Wörter behalten, sofern sie nicht ausgegeben werden; die Checkpoint-Zeilen "Keine uncommitteten Änderungen …" werden dennoch umformuliert, weil Claude sie erfahrungsgemäß in die Antwort übernimmt. `skills/` wird per `sync_skills.py` neu erzeugt, nie direkt editiert.

**2. `klartext_gate.pruefe(payload) -> list[str]`.** Reine Funktion mit exakt den bisherigen Ausnahmen von `main`: `OPENSPEC_KLARTEXT` aus (off/0/false/no/disabled) → `[]`; Payload kein dict oder `stop_hook_active` gesetzt → `[]`; kein Antworttext (weder `last_assistant_message` noch aus dem Transkript) → `[]`; letzte Nutzernachricht enthält selbst Treffer → `[]`; sonst `treffer(antwort)`. Jede Ausnahme in der Funktion → `[]` (fail-open). `main` ist ein dünner Wrapper: Payload von stdin lesen, `adopt_payload_cwd`, bei `pruefe(...)` mit Treffern dieselbe `block(...)`-Meldung wie bisher, sonst Exit 0. Ausgabetext, Exit-Codes und Fail-open bleiben identisch (`tests/test_klartext_gate_582.py` bleibt grün). `pruefe` ruft selbst kein `adopt_payload_cwd` auf (kein Prozess-Seiteneffekt in der Vorprüfung; `footer_gate` hat das Payload-cwd bereits übernommen).

**3. `maybe_auto_clear` (neue Reihenfolge).**
- Beibehalten: Pane und Opt-in-Config prüfen, Workflow/Phase, erwarteter Slash-Befehl, `/clear`-Ausschluss, `MANUAL_COMMANDS` (`/99-reset`), Fußzeile nennt den Befehl.
- Entfällt (a): der `stop_hook_active`-Zweig (weder Skip noch Verwerfen); solche Stops werden wie jeder andere ausgewertet. Folge-Stops nach einem Block tragen `stop_hook_active: true` und sind genau die "späteren sauberen Antwortenden".
- Neu (d), vor jeder Vermerk-Behandlung: `klartext_gate.pruefe(payload)` liefert Treffer → `_ac_skip("Klartext-Prüfung weist die Antwort zurück")`, Rückgabe False, **Vermerk unangetastet** (der Folge-Stop kommt garantiert). Ein Import- oder Laufzeitfehler der Vorprüfung gilt als "keine Treffer" (fail-open: dann entscheidet allein der Runner-Abbruch bei Folge-Stop).
- Unverändert (e): fehlt der Vermerk → Skip "keine Grenze vermerkt"; ist der Vermerk vorhanden, wird er bei Negativ-Marker (`_consume_boundary`, dann Skip) und bei veraltetem Vermerk (`_boundary_fresh` falsch: `_consume_boundary`, dann Skip "Grenze veraltet") wie bisher verbraucht; passt der Vermerk nicht zu Phase/Befehl (`_boundary_matches`) bleibt das bisherige Verhalten (Skip "keine Grenze vermerkt", Vermerk wurde zuvor verbraucht).
- Entfällt (b)/(c): kein `_consume_boundary` beim Spawn, kein `_acquire_lock`/`_release_lock`. Der Spawn übergibt dem Runner die Zeit des Vermerks als `--boundary-at <at-Text>` (identisch mit `boundary["at"]`); schlägt der Spawn fehl → Skip "Spawn fehlgeschlagen", Vermerk bleibt.

**4. Runner (`_Runner`, `run_auto_clear`).**
- Neu `_take_boundary()`: unter `fcntl.flock(LOCK_EX)` auf `<Haupt-Projektroot>/.claude/herdr_auto_clear.lock` (Basis wie der Workflow-State, `find_project_root()`, nicht die worktree-lokale `_ac_base`, weil die Workflow-JSONs im geteilten Hauptrepo liegen) den Workflow-State `<root>/.claude/workflows/<workflow>.json` lesen (`read_state_json`), verlangen, dass `auto_clear_boundary` ein dict ist, dessen `phase` gleich `--phase`, `command` gleich `--command` und `at` gleich `--boundary-at` ist; dann das Feld entfernen und per `atomic_write_json` zurückschreiben, `True`. Sonst `False`. Die Sperre wird in jedem Fall freigegeben; Lock-Fehler, nicht lesbarer State oder fehlendes `fcntl` → `False` (kein Tippen: sicher).
- Aufruf: unmittelbar nach dem letzten `_check_activity` und `_recheck("vor /clear")`, direkt vor `t_clear`/`_prompt("/clear", …)`. `False` → `_Abort("Grenze bereits vergeben")`, nichts wird getippt. Damit tippt bei mehreren Runnern für dieselbe Grenze höchstens einer.
- Abbruchbehandlung in `run_auto_clear` (Vermerk-Schicksal je Abbruchgrund): Der Runner merkt sich, ob er den Vermerk genommen hat (`taken`) und ob `/clear` abgeschickt wurde (Enter erfolgreich, `submitted`).
  - Abbruch **vor** dem Abschicken von `/clear`, Grund ist eine Fortsetzung von Claude ("Claude arbeitet weiter": Signalarten `activity`/`stop`, auch der Fall zwischen Text und Enter mit `ctrl+u`): Hat der Runner den Vermerk noch nicht genommen, bleibt er liegen (nichts zu tun). Hat er ihn genommen (nur zwischen `_take_boundary` und Enter möglich), legt er ihn zurück, aber nur wenn inzwischen kein Vermerk im State steht (kein Überschreiben eines neueren). Der nächste saubere Stop startet einen neuen Runner.
  - Jeder andere Abbruch (Nutzer hat weitergeschrieben, Sitzung beendet/neu gestartet, Herdr-Fehler, Gesamt-Deadline, Phase gewechselt/erwarteter Befehl geändert, `/99-reset`-Sperre, "Grenze bereits vergeben"): Vermerk wird verworfen (hat der Runner ihn noch nicht genommen, entfernt er ihn jetzt nur, wenn er noch dem eigenen `--boundary-at` entspricht, über denselben Pfad wie `_consume_boundary`); kein automatischer Neuversuch, wie bisher.
  - Abbruch **nach** abgeschicktem `/clear` (Warten auf SessionStart, Folgebefehl): Vermerk bleibt verbraucht (bereits genommen), unverändert.
  - Der Abbruchgrund wird danach wie bisher ins Log geschrieben (`ABBRUCH: …`); bei "bleibt/zurückgelegt" ergänzt `; Grenze bleibt` das Log.
- Unverändert: Grace-Pause, `_check_activity` nach `since` vor `/clear` und zwischen Text und Enter, `ctrl+u`, `_recheck`, Warten auf SessionStart(clear), Folgebefehl, `/99-reset` manuell, Exit 0 und `OK`/`ABBRUCH` im Log.

**5. Ergebnis: "das neueste saubere Antwortende gewinnt".** Stop #1 qualifiziert → Runner 1 startet (Grenze liegt weiter); fremder Hook blockt; Claude schreibt neu; Stop #2 (`stop_hook_active`) qualifiziert → Runner 2 startet mit späterem `since`; Runner 1 sieht Stop #2 (`stop` Signal nach seinem `since`) und bricht ab, ohne den Vermerk zu verwerfen; Runner 2 nimmt den Vermerk und tippt. Weist `klartext_gate` Stop #1 zurück, startet gar kein Runner 1. Das gilt für jede Phase (10..70), weil es nicht an der Formulierung der Vorlage hängt.

**6. Unverändert.** Berechtigungsdialog-Schutz (#506 Szenario P: Runner bricht bei jeder Aktivität/Stop/Eingabe nach seiner Referenz ab), `ctrl+u` zwischen Text und Enter, `footer_gate._discard_boundary` nach zweimal falscher Fußzeile (#497a), `/99-reset` bleibt manuell, Herdr nur als Tastatur, alles fail-open, Exit 0.

**7. Anzupassende Bestandstests (angepasst, nicht gelöscht).**
- `tests/test_herdr_auto_clear_467.py::test_no_spawn_when_stop_hook_active` → umbenannt `test_spawn_when_stop_hook_active`: Ein `stop_hook_active`-Stop mit passender Grenze und sauberer Antwort spawnt jetzt einen Runner (Stub-Protokoll mit Benachrichtigung).
- `tests/test_herdr_auto_clear_467.py::test_once_lock_blocks_duplicate_and_expires_after_10_min` → ersetzt durch `test_second_identical_stop_does_not_double_type`: zwei identische Stops erzeugen höchstens zwei Runner, getippt wird `/clear` + Folgebefehl genau einmal; kein 600-s-Ablauf mehr, keine `herdr_auto_clear_state.json`. Der Kopfkommentar zum Once-Lock im Modul-Docstring (Zeile ~24) wird aktualisiert.
- `tests/test_autoclear_boundary_495.py::test_once_lock_single_spawn` → `test_single_boundary_types_once`: Zwei Stops mit derselben Grenze, getippt wird genau einmal (Token), nicht "genau ein Spawn".
- `tests/test_autoclear_boundary_495.py::test_boundary_consumed_after_spawn` → `test_boundary_consumed_after_typing`: der Vermerk ist nach dem Spawn noch vorhanden und erst nach `OK` (Tippen) verbraucht; `_age_lock` entfällt; die Zusicherung "zweiter Stop mitten in der Phase löst nicht erneut aus" bleibt (Skip "keine Grenze vermerkt").
- `tests/test_autoclear_boundary_495.py::test_boundary_consumed_on_stop_hook_active` → `test_boundary_kept_on_stop_hook_active`: Grenze bleibt, Runner wird gestartet.
- `tests/test_autoclear_eigene_signale_506.py::test_manual_lock_and_recheck_unchanged`, Teil (b) (Once-Lock, Zeilen ~574–590): ersetzt durch "Vermerk bereits von anderem Runner genommen" (kein Vermerk im State → Skip "keine Grenze vermerkt", keine Aufrufe); Teile (a) und (c) bleiben.
- `tests/test_befehlsform_context_titel_499.py` (~Zeile 327): Once-Lock-Assertion entfällt (siehe Affected Files).
- Zu prüfen und nur bei Rot anzupassen: `tests/test_kette_auto_clear_489.py`, `tests/test_autoclear_transition_497.py` (`test_footer_gate_stop_hook_active_discards_boundary` betrifft `footer_gate._discard_boundary` und bleibt unverändert), `tests/test_auto_clear_global_480.py`, `tests/test_herdr_plan_deploy_sessionstart_478.py`.

**8. E2E Szenario R.** Wie A (Testdouble `20-analyse`), aber ein projektlokaler fremder Stop-Hook blockt genau einmal (`decision: block`); Claude schreibt die Fußzeile neu; erwartet: im TUI genau ein `❯ /clear` und genau ein Folgebefehl; Log zeigt zuerst `ABBRUCH: … Claude arbeitet weiter`, danach `OK`. Szenario D entfernt die nicht mehr existierende Once-Lock-Datei nicht mehr, prüft stattdessen, dass der Vermerk nach A verbraucht ist. Standard-`ONLY` bleibt in den Skriptkopf-Hinweisen konsistent (R ergänzen). Läuft nur lokal beim PO mit echtem Herdr, nicht in CI.

## Expected Behavior

- **Input:** Auto-/clear aktiv, Phasenwechsel hat `auto_clear_boundary` gesetzt, Antwort endet mit `❗ Du: /<nächster> #N`; ein weiterer Stop-Hook (z. B. `klartext_gate`) weist die Antwort einmal zurück, Claude schreibt sie neu
- **Output:** Nach der Neufassung (Folge-Stop, `stop_hook_active`) startet ein Runner, nimmt den Vermerk atomar und tippt genau einmal `/clear` und den Folgebefehl; ein früher gestarteter Runner bricht beim neueren Stop ab, ohne den Vermerk zu verwerfen
- **Vorprüfung:** Würde `klartext_gate` die Antwort zurückweisen, startet `maybe_auto_clear` keinen Runner (Log `skip: Klartext-Prüfung weist die Antwort zurück`), der Vermerk bleibt
- **Nutzer schreibt, Sitzung endet, Phase wechselt:** Abbruch, Vermerk verworfen, keine Wiederholung
- **Side effects:** neue Sperrdatei `.claude/herdr_auto_clear.lock` (leer, im Hauptprojekt); keine `herdr_auto_clear_state.json` mehr; Runner-Log wie bisher (`ABBRUCH`/`OK`/`skip:`); Vorlagen-Texte ohne Git-Wörter

## Known Limitations

- Fremder, unbekannter Stop-Hook plus stilles Neuschreiben ohne Werkzeugaufruf, das länger als `grace_s` (+ settle) dauert: bis dahin entsteht kein Signal (unverändert zu heute, Spec #506). Der häufige Klartext-Fall ist durch Vorlagen und Vorprüfung deterministisch abgedeckt.
- Die neue Hook-Logik wirkt erst nach einem Neustart von Claude Code: Hook-Registrierungen werden beim Sitzungsstart eingelesen, ein Plugin-Update in laufender Sitzung ändert nur Befehlstexte. Nebenbefund ausgelagert in Issue #599.
- Ein Vermerk, der nach "Claude arbeitet weiter" liegen bleibt und danach nicht verbraucht wird (z. B. Folge-Antwort mit falscher Fußzeile oder Klartext-Zurückweisung ohne späteren sauberen Stop), kann bis zu 15 Minuten (`AC_BOUNDARY_MAX_AGE_S`) später einen Runner für einen sauberen Stop derselben Phase auslösen; Schutz: Vermerk muss zu Phase und erwartetem Befehl passen, Nutzereingabe in der Runner-Grace-Zeit bricht ab, Altersgrenze.
- Szenario R und das Verhalten am echten Herdr sind nur lokal beim PO prüfbar (echtes Herdr und Claude-TUI), nicht in CI; automatisiert sind Stub-Herdr-Tests mit zwei Runnern.
- `fcntl` ist nur auf POSIX verfügbar; ohne `fcntl` tippt der Runner nie (`_take_boundary` → False), das Verhalten ist dann "kein Auto-/clear" (fail-open zur sicheren Seite).
- Nach dem Abschicken von `/clear` gibt es keinen Neuversuch; scheitert danach der Folgebefehl, bleibt der Vermerk verbraucht (wie bisher).

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt (AC-12 durch das lokale E2E-Skript, nicht in CI)
- [ ] Vorlagen-Test grün; `python3 scripts/sync_skills.py` erzeugt keine Drift; `klartext_gate.pruefe` und `main` verhalten sich identisch zu vorher
- [ ] Bestandstests aus "Anzupassende Bestandstests" sind angepasst und grün, vollständiger Lauf `pytest tests/` grün, `python3 -m py_compile core/hooks/herdr_bridge.py core/hooks/klartext_gate.py` ohne Fehler
- [ ] E2E Szenario R sowie A, D, H, P, Q, S am echten Herdr beim PO grün, Belege (Log, Pane-Auszug) liegen vor
- [ ] CHANGELOG-Eintrag unter [Unreleased] vorhanden, keine Versionsnummer

## Acceptance Criteria

- **AC-1:** Given alle `core/commands/*.md` und alle `skills/*/SKILL.md` / When jeder Block zwischen den `---`-Trennern nach einer Überschrift mit "Ausgabe" und jede deutsch zitierte Phrase („…“ bzw. „…") durch `klartext_gate.treffer` läuft / Then gibt es keinen einzigen Treffer; `skills/` stimmt nach `sync_skills.py` mit `core/commands` überein
  - Test: tests/test_vorlagen_klartext_597.py::test_ausgabebloecke_und_fragen_ohne_git_woerter

- **AC-2:** Given `klartext_gate.pruefe(payload)` / When Antwort Git-Wörter außerhalb von Code enthält, bzw. `OPENSPEC_KLARTEXT=0`, bzw. `stop_hook_active`, bzw. letzte Nutzernachricht enthält selbst Git-Wörter, bzw. kein Antworttext, bzw. Payload kein dict / Then liefert sie die Trefferliste bzw. in allen Ausnahmefällen `[]`, ohne Exception; `main` blockt unverändert mit Exit 2 und derselben Meldung nur bei Treffern
  - Test: tests/test_autoclear_retry_597.py::test_klartext_pruefe_matches_main_behaviour

- **AC-3:** Given Grenze passt, Antwort sauber, Payload mit `stop_hook_active: true` / When `footer_gate.py` (`maybe_auto_clear`) läuft / Then wird ein Runner gestartet (kein `skip: stop_hook_active`, Vermerk bleibt bis zum Tippen liegen)
  - Test: tests/test_autoclear_retry_597.py::test_stop_hook_active_stop_spawns_runner

- **AC-4:** Given Grenze passt und die Antwort enthält Git-Wörter (`klartext_gate.pruefe` liefert Treffer) / When `maybe_auto_clear` läuft / Then wird kein Runner gestartet, das Log enthält `skip: Klartext-Prüfung weist die Antwort zurück` und der Vermerk ist unverändert vorhanden; bei Negativ-Marker oder veraltetem Vermerk bleibt das bisherige Verhalten (Vermerk verbraucht, Skip-Grund wie bisher)
  - Test: tests/test_autoclear_retry_597.py::test_klartext_pre_check_skips_and_keeps_boundary

- **AC-5:** Given ein gültiger Vermerk / When ein Runner gespawnt wurde (noch vor dem Tippen) / Then liegt der Vermerk weiter im Workflow-State (kein Verbrauch beim Spawn) und es gibt keinen 600-s-Once-Lock (keine `herdr_auto_clear_state.json`, zwei Stops in Folge sind nicht per Sperre blockiert); der Spawn übergibt `--boundary-at` mit dem `at` des Vermerks
  - Test: tests/test_autoclear_retry_597.py::test_spawn_keeps_boundary_and_has_no_once_lock

- **AC-6:** Given zwei Runner für dieselbe Grenze starten gleichzeitig `_take_boundary` / When beide bis vor das Tippen kommen / Then bekommt genau einer den Vermerk (atomar unter flock), der andere bricht mit "Grenze bereits vergeben" ab ohne zu tippen; getippt wird `/clear` und der Folgebefehl insgesamt genau einmal
  - Test: tests/test_autoclear_retry_597.py::test_two_runners_only_one_takes_token

- **AC-7:** Given `_take_boundary` / When der Vermerk fehlt, `phase`, `command` oder `at` nicht zu den Runner-Argumenten passen, der State nicht lesbar ist oder die Sperre fehlschlägt / Then liefert sie False, der State bleibt unverändert und der Runner tippt nichts
  - Test: tests/test_autoclear_retry_597.py::test_take_boundary_requires_exact_match_and_fails_safe

- **AC-8:** Given Runner 1 im Wartefenster und ein neuerer Stop (`stop`-Signal nach seinem `since`), dann Runner 2 / When Runner 1 abbricht und Runner 2 weiterläuft / Then verwirft Runner 1 den Vermerk nicht ("Claude arbeitet weiter", Vermerk bleibt), Runner 2 nimmt ihn und tippt genau einmal `/clear` und den Folgebefehl; Log zeigt zuerst `ABBRUCH`, dann `OK`
  - Test: tests/test_autoclear_retry_597.py::test_newest_clean_stop_wins

- **AC-9:** Given der Runner hat den Vermerk genommen, aber zwischen `send-text` und Enter trifft ein `stop`- oder `activity`-Signal ein / When er mit `ctrl+u` abbricht / Then wird der Vermerk zurückgelegt, aber nur, wenn im State kein (neuerer) Vermerk steht; ein vorhandener neuerer Vermerk wird nicht überschrieben
  - Test: tests/test_autoclear_retry_597.py::test_restore_boundary_on_continuation_between_text_and_enter

- **AC-10:** Given Abbruch vor dem Abschicken von `/clear` durch Nutzereingabe ("Nutzer hat weitergeschrieben"), Sitzungsende/Neustart, Phasenwechsel/Befehl geändert, Herdr-Fehler oder Gesamt-Deadline / When der Runner abbricht / Then ist der Vermerk verworfen und es gibt keinen automatischen Neuversuch; nach abgeschicktem `/clear` bleibt der Vermerk verbraucht, `ABBRUCH` im Log
  - Test: tests/test_autoclear_retry_597.py::test_discard_boundary_on_user_input_and_other_aborts

- **AC-11:** Given die unveränderten Schutzfunktionen / When Berechtigungsdialog-Szenario (Aktivität/Stop nach der Referenz), `/99-reset`, zweimal falsche Fußzeile (`footer_gate._discard_boundary`), Negativ-Marker, veralteter Vermerk und Phasenwechsel in der Grace-Zeit laufen / Then verhalten sie sich wie vor der Änderung (kein Tippen bzw. Vermerk verworfen wie bisher); die angepassten Bestandstests (#467, #495, #497, #499, #506, #489, #480, #478) sind grün
  - Test: Regressionslauf `pytest tests/` (u. a. tests/test_autoclear_eigene_signale_506.py, tests/test_autoclear_transition_497.py)

- **AC-12:** Given echtes Herdr mit Claude-TUI und ein fremder Stop-Hook, der genau einmal blockt (Szenario R) / When Claude die Antwort neu schreibt / Then erscheinen im TUI genau ein `❯ /clear` und genau ein Folgebefehl, das Log zeigt `ABBRUCH` des ersten und `OK` des zweiten Runners; Szenarien A, D, H, P, Q, S bleiben grün (lokal beim PO, nicht in CI)
  - Test: scripts/e2e_auto_clear.sh (ONLY="R A D H P Q S")

## Test Plan

Muster: `tests/test_herdr_auto_clear_467.py` und `tests/test_autoclear_eigene_signale_506.py` (isoliertes Projekt, Stub-Herdr mit Aufruf-Protokoll, `HOME` auf Wegwerf-Verzeichnis, Signal-Marker direkt als Dateien, Runner mit explizitem `--since`/`--boundary-at`). Der Zwei-Runner-Test startet zwei Runner-Prozesse (oder zwei `_Runner.run` in Threads) gegen denselben Projektordner und wertet das Stub-Protokoll aus. Hook-Tests starten `footer_gate.py` bzw. `klartext_gate.py` als Subprozess mit Stop-Payload (`last_assistant_message`, optional `stop_hook_active`).

### Automated Tests (TDD RED)

- [ ] Test 1: GIVEN alle Vorlagen/Skills WHEN Ausgabeblöcke und „…“-Fragen durch `treffer` THEN 0 Treffer (`test_ausgabebloecke_und_fragen_ohne_git_woerter`)
- [ ] Test 2: GIVEN verschiedene Payloads WHEN `pruefe` und `main` THEN identische Entscheidung, `pruefe` wirft nie (`test_klartext_pruefe_matches_main_behaviour`)
- [ ] Test 3: GIVEN `stop_hook_active` mit gültiger Grenze WHEN `footer_gate` THEN Runner gespawnt (`test_stop_hook_active_stop_spawns_runner`)
- [ ] Test 4: GIVEN Antwort mit Git-Wort WHEN `maybe_auto_clear` THEN kein Spawn, Skip-Grund, Vermerk bleibt (`test_klartext_pre_check_skips_and_keeps_boundary`)
- [ ] Test 5: GIVEN Spawn WHEN vor dem Tippen THEN Vermerk vorhanden, kein Lock, `--boundary-at` übergeben (`test_spawn_keeps_boundary_and_has_no_once_lock`)
- [ ] Test 6: GIVEN zwei Runner WHEN beide `_take_boundary` THEN genau einer tippt (`test_two_runners_only_one_takes_token`)
- [ ] Test 7: GIVEN Vermerk fehlt/anders/State kaputt WHEN `_take_boundary` THEN False, State unverändert (`test_take_boundary_requires_exact_match_and_fails_safe`)
- [ ] Test 8: GIVEN Stop #1, Block, Stop #2 WHEN Runner 1 und 2 THEN Runner 1 bricht ohne Verwerfen ab, Runner 2 tippt einmal (`test_newest_clean_stop_wins`)
- [ ] Test 9: GIVEN Signal zwischen Text und Enter nach `_take_boundary` WHEN Abbruch THEN Vermerk zurückgelegt, neuerer Vermerk nie überschrieben (`test_restore_boundary_on_continuation_between_text_and_enter`)
- [ ] Test 10: GIVEN Nutzereingabe/Sitzungsende/Phasenwechsel/Herdr-Fehler vor `/clear` WHEN Abbruch THEN Vermerk verworfen, kein Neuversuch; nach `/clear` bleibt er verbraucht (`test_discard_boundary_on_user_input_and_other_aborts`)
- [ ] Test 11: GIVEN angepasste Bestandstests aus Implementation Details Punkt 7 WHEN `pytest tests/` THEN grün
- E2E Szenario R (lokal beim PO, echtes Herdr): siehe AC-12

Weitere Läufe:

- `pytest tests/test_vorlagen_klartext_597.py tests/test_autoclear_retry_597.py tests/test_klartext_gate_582.py`, danach `pytest tests/` (nur im venv mit `pytest` und `pyyaml`)
- `python3 scripts/sync_skills.py` und Drift-Prüfung; `python3 -m py_compile core/hooks/herdr_bridge.py core/hooks/klartext_gate.py core/hooks/footer_gate.py`
- E2E: `ONLY="R A D H P Q S" bash scripts/e2e_auto_clear.sh` beim PO

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** ADR-0597 (Konvention: ADR-Nummer = Issue-Nummer)
- **Rationale:** Gewählt: "das neueste saubere Antwortende gewinnt", mit dem Grenz-Vermerk als einzigem Einmal-Token (Idempotenzschlüssel, atomar unter flock vom Runner unmittelbar vor dem Tippen genommen, "acknowledge after success"), plus Klartext-Vorprüfung und bereinigte Vorlagen. Grundlage: Stop-Hooks laufen parallel und sehen das Verdict der anderen nicht; ein Ereignis "nach allen Stop-Hooks" gibt es nicht; ein geblockter Stop erzeugt immer einen weiteren, der letzte Stop nach Ruhe ist das echte Turn-Ende. Die bisherigen Sonderregeln (Verbrauch beim Spawn, 600-s-Once-Lock, Verwerfen bei `stop_hook_active`) verbrauchten das Token, bevor etwas getippt war, und verhinderten jeden zweiten Versuch; sie entfallen und werden durch eine einzige Regel ersetzt, die für alle Phasen gleich gilt. Verworfene Alternativen: (1) Nur Klartext-Fix (Vorlagen bereinigen): behebt den beobachteten Auslöser, aber nicht die Ursache; jeder andere Stop-Hook, der einmal blockt (fremder Hook, künftige Wortlisten, neue Vorlagen), reproduziert den Fehler, und Vorlagen-Drift wäre unbemerkt möglich. Deshalb nur als erster Schritt (AC-1), nicht als Lösung. (2) Debounce in einem Runner (auf Ruhe warten, dann den letzten Zustand auswerten): gleichwertig in der Wirkung, aber ein größerer Umbau des bewährten Runners (Ruhefenster, Stop-Verdict im Signal, Lock-Übernahme, Exit-Race) mit mehr neuer Zeit- und Zustandslogik; die Ersetzungs-Variante hält den Runner fast unverändert, braucht keinen Lock-Ablauf und erzeugt höchstens kurzlebige Zusatz-Runner, die von selbst abbrechen. (3) Herdr `agent-state`/`report-agent` oder `agent wait` nutzen: Herdrs eigene Claude-Integration mappt `Stop` auf `idle` und hat dieselbe Lücke (erster Stop = idle); das PO-Manifest stuft `❗ Du:` als `blocked` ein und `agent prompt` lehnt dann ab (#506). Herdr bleibt deshalb nur Tastatur; das beantwortet den PO-Einwand "zu kompliziert" ohne neue Herdr-Abhängigkeit. Folgen: weniger Zustand (kein Once-Lock, kein Verbrauch beim Spawn, kein `stop_hook_active`-Sonderfall), eine Datei-Sperre als einzige neue Mechanik, bewusste Änderung der Bestandstests; Restrisiko siehe Known Limitations (Token bleibt nach "Claude arbeitet weiter" bis 15 min liegen).

## Changelog

- 2026-11-13: Initial spec created
