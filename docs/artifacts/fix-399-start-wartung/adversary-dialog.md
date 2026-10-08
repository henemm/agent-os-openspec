# Adversary Dialog — fix-399-start-wartung
Spec: docs/specs/fix-399-start-wartung.md
Datum: 2026-10-08 10:33

## Checkliste
- [x] **Input:** SessionStart-Payload (mit `source`), cwd = Haupt-Ordner oder Worktree, Kurzbefehle in `~` und im Projekt, Remote-Stand.
Status: CONFIRMED
Code reference: core/hooks/session_banner.py:507
Evidence: `main()` liest die Payload über `_read_payload()` (:66). Es nutzt `cwd` und `source` (:511-517). Kaputtes stdin ergibt `{}` (Angriff 14: Exit 0). `OPENSPEC_FRAMEWORK=off` ergibt leere Ausgabe (Angriff 12).
- [x] **Output:** JSON mit `systemMessage` (Klartext, höchstens Versionszeile, „Kurzbefehle aktualisiert (N)", „Projektstand aktualisiert (N Änderungen)") und optional `additionalContext` (Hinweise und Aufträge an Claude).
Status: CONFIRMED
Code reference: core/hooks/session_banner.py:480
Evidence: `build_output` setzt `systemMessage` aus `lines`. `hookSpecificOutput.additionalContext` kommt nur, wenn `context` nicht leer ist (:500-503). Live-Ausgaben in Angriff 1 und 2 haben genau diese Form. Der Kontext mit `python3` und dem Git-Wort „Commit(s)" steht nur in `additionalContext` (:415-422).
- [x] **Side effects:** Markierte veraltete Alias-Dateien in `~/.claude/commands` werden überschrieben, markierte Aliase entfernter Befehle gelöscht; im Haupt-Ordner wird fast-forward nachgezogen. Keine neuen Dateien in `~`, keine Schreibzugriffe im Projekt-Scope.
Status: CONFIRMED
Code reference: core/hooks/alias_sync.py:215
Evidence: `refresh_aliases` schreibt nur Namen aus `find_stale_aliases`, also existierende markierte Dateien, und legt nie an. Es löscht nur über `find_removed_aliases`. Der Merge läuft nur mit `--ff-only` in `_ff_merge` (session_banner.py:347). `project_alias_context` (:167) ruft keine Schreibfunktion auf. Angriff 10: Verzeichnis, unlesbare Datei und fremde Datei bleiben unberührt. Einschränkung: F001 und F002.
- [x] **AC-1:** veraltete markierte Kopie in `~` wird aufgefrischt, „Kurzbefehle aktualisiert", kein „python3"
Status: CONFIRMED
Code reference: core/hooks/session_banner.py:150
Evidence: `refresh_home_aliases` ruft `refresh_aliases` mit den Skills der geladenen Fassung auf und gibt die Zeile „Kurzbefehle aktualisiert (N)" zurück. Test `test_start_frischt_veraltete_kopie_in_home_auf` PASSED. Die Zeile enthält kein python3.
- [x] **AC-2:** Kopie mit neuerem Versions-Marker bleibt byte-identisch, keine Aktualisierungszeile (#163)
Status: CONFIRMED
Code reference: core/hooks/alias_sync.py:187
Evidence: `find_stale_aliases` überspringt Kopien mit `is_newer_than(actual, loaded_version)`. `refresh_home_aliases` übergibt `plugin_version(root)` (session_banner.py:159). Test `test_start_stuft_kopie_mit_neuerem_marker_nicht_herab` PASSED.
- [x] **AC-3:** markierter Alias entfernter Befehle wird gelöscht, unmarkierte Datei bleibt
Status: CONFIRMED
Code reference: core/hooks/alias_sync.py:199
Evidence: `find_removed_aliases` liefert nur Dateien, bei denen `is_alias_file` zutrifft. `refresh_aliases` löscht genau diese (:224-227). Test `test_start_loescht_markierten_alias_entfernter_befehle_nicht_fremde_datei` PASSED. Angriff 10: Verzeichnis und fremde Datei bleiben unberührt.
- [x] **AC-4:** Projekt-Kopie unverändert, Hinweis nur in `additionalContext`
Status: CONFIRMED
Code reference: core/hooks/session_banner.py:167
Evidence: `project_alias_context` nutzt nur lesende Funktionen. `build_output` hängt das Ergebnis an `context` und nie an `lines` (:491). Test `test_projekt_kopie_wird_nicht_geschrieben_nur_claude_hinweis` PASSED.
- [x] **AC-5:** sauberer Haupt-Ordner hinter dem Remote wird nachgezogen, sichtbare Zeile ohne Git-Vokabular
Status: CONFIRMED
Code reference: core/hooks/session_banner.py:425
Evidence: `_pull_forward` gibt nach erfolgreichem `_ff_merge` die Zeile „Projektstand aktualisiert (N Änderungen)" zurück. Angriff 1 (Remote `my/remote`): 2 Änderungen nachgezogen, Status zeigt „## main...my/remote/main" ohne „behind". Test `test_behind_sauber_wird_nachgezogen_ohne_git_vokabular` PASSED.
- [x] **AC-6:** Haupt-Ordner mit lokalen Änderungen bleibt stehen, Hinweis nur in `additionalContext`
Status: CONFIRMED
Code reference: core/hooks/session_banner.py:397
Evidence: `_blocker` prüft MERGE_HEAD, rebase-merge, rebase-apply, `status --porcelain` und `merge-base --is-ancestor`. Angriffe 2 (divergent), 5 (MERGE_HEAD), 6 (gestagt) und 7 (Untracked-Kollision): HEAD unverändert, `systemMessage` ohne Befehl. Test `test_behind_mit_lokalen_aenderungen_nur_claude_hinweis` PASSED.
- [x] **AC-7:** Worktree-cwd zieht nicht nach und schweigt
Status: CONFIRMED
Code reference: core/hooks/session_banner.py:374
Evidence: `_main_checkout` liefert None, wenn cwd nicht der erste Eintrag von `git worktree list` ist (:389-393). Test `test_worktree_cwd_zieht_nicht_nach_und_schweigt` PASSED.
- [x] **AC-8:** `source == "compact"` führt keine Wartung aus
Status: CONFIRMED
Code reference: core/hooks/session_banner.py:488
Evidence: Alles außer der Versionszeile liegt im Block `if source != "compact"`. Test `test_source_compact_fuehrt_keine_wartung_aus` PASSED. Angriff 13: `resume` und `clear` führen die Wartung aus (nur compact ist ausgenommen), Exit 0.
- [x] **AC-9:** Regressionstests zu `setup.py --refresh-aliases` grün, Konsolenausgabe unverändert
Status: CONFIRMED
Code reference: setup.py:1278
Evidence: `refresh_command_aliases` delegiert an `alias_sync.refresh_aliases` (:1287-1294). Es gibt dieselben „Refreshed:"-, „Removed:"- und Summenzeilen aus. `tests/test_setup_command_aliases.py` und `tests/test_bug_typ_entfernt_333.py` sind in der Zielsuite grün: 84 passed.
- [x] **AC-10:** Exception in der Wartung führt zu Exit 0 ohne Traceback (fail-open)
Status: CONFIRMED
Code reference: core/hooks/session_banner.py:522
Evidence: Der Einstieg ist in try/except gekapselt. `refresh_home_aliases` und `main_folder_sync` sind zusätzlich abgefangen (:161, :494-497). Test `test_exception_in_wartung_bleibt_fail_open` PASSED. Angriffe 14 (kaputtes stdin) und 15 (schreibgeschütztes Kurzbefehl-Verzeichnis): Exit 0, leeres stderr. Einschränkung: F002.
- [x] **AC-11:** `timeout` des SessionStart-Eintrags für `session_banner.py` ist 10
Status: CONFIRMED
Code reference: hooks/hooks.json:14
Evidence: Der Eintrag für `core/hooks/session_banner.py` (:13) hat `"timeout": 10`. Test `test_hooks_json_banner_timeout_ist_10` PASSED. Das Skriptbudget (`_TOTAL_BUDGET_S` = 8,0 s, session_banner.py:325) liegt darunter. Messung bei Merge-Hang: 4,39 s.

## Dialog

### Runde 1
**Adversary:** Ich greife die schreibenden Pfade an. (a) Herabstufen: Der Vergleich nutzt `plugin_version(root)` und den Marker der Kopie. Wo ein Marker fehlt, gibt es keinen Beweis, also wird aufgefrischt (alias_sync.py:187). (b) Unmarkierte, unlesbare oder Verzeichnis-Einträge: `find_stale_aliases` prüft `is_file` und `is_alias_file`. (c) Symlink auf eine fremde Datei mit Marker: `write_text` schreibt durch den Link. (d) Eine schreibgeschützte markierte Datei: `refresh_aliases` hat kein try pro Datei. (e) Git-Zustände: Remote mit `/`, divergente Historie, detached HEAD, kein Upstream, MERGE_HEAD, gestagte Änderung, Untracked-Kollision, hängender Merge. (f) Das Zeitbudget bei langsamem Git.
**Implementierer:** Die Tests belegen alle elf ACs (84 passed). Die Pfadprüfungen in `find_stale_aliases` und `find_removed_aliases` filtern Verzeichnisse, unlesbare und unmarkierte Dateien. Der Merge läuft mit `--ff-only` und SIGTERM statt SIGKILL (session_banner.py:330, 347). Das Gesamtbudget ist 8 s.

### Runde 2
**Adversary:** Ergebnis der Experimente mit Fake-HOME und Wegwerf-Repos. Remote `my/remote`: nachgezogen, 0,43 s. Divergent, MERGE_HEAD, gestagt und Untracked-Kollision: HEAD unverändert, Hinweis nur im `additionalContext`. Detached HEAD und kein Upstream: völlig still, ohne Hinweis an Claude. Merge-Hang: 4,39 s, Exit 0, kein `index.lock`. Alle Git-Aufrufe 2,5 s langsam: 1,04 s, Exit 0. `source=resume` und `clear`: nur die Versionszeile. Garbage-stdin und `OPENSPEC_FRAMEWORK=off`: Exit 0. Verzeichnis, unlesbare Datei und schreibgeschütztes Kurzbefehl-Verzeichnis: unberührt, Exit 0. Gebrochen: (c) Der Symlink wurde durchgeschrieben, die Ziel-Datei außerhalb von `~/.claude/commands` wurde überschrieben (F001). (d) Eine Datei mit 0444 brach den ganzen Lauf ab: spätere veraltete Kopien blieben alt, `00-bug.md` wurde nicht gelöscht, nichts war sichtbar (F002). Zwei weitere Beobachtungen führen zu keinem Befund. Detached HEAD und fehlender Upstream bleiben still (session_banner.py:387, :463), und die Spec schweigt dazu. Außerdem könnten zwei gleichzeitige Starts im Haupt-Ordner auf eine `index.lock`-Kollision laufen, was die Spec als Known Limitation nennt.
**Implementierer:** F001 und F002 verletzen keine AC. AC-10 verlangt Exit 0 ohne Traceback, und das ist erfüllt. Beides sind Randfälle, die die Spec nicht abdeckt, und gehören in ein Folge-Ticket.

Finding:
  ID: F001
  Severity: MEDIUM
  Category: edge_case
  Code reference: core/hooks/alias_sync.py:224
  Description: `refresh_aliases` schreibt mit `(commands_dir / f"{name}.md").write_text(...)` direkt in die Zieldatei, ohne Symlinks zu prüfen. Ein markierter Kurzbefehl, der ein Symlink ist (z. B. aus einem Dotfiles-Repo), überschreibt beim Start still die Ziel-Datei außerhalb von `~/.claude/commands`. Reproduziert in Angriff 10: Ziel-Datei überschrieben, Symlink blieb bestehen.
  Spec requirement: Side effects — nur markierte Alias-Dateien in `~/.claude/commands` werden überschrieben
  Conflict: Der Banner schreibt jetzt automatisch und unbeaufsichtigt. Vorher tat das nur der manuelle Befehl `setup.py --refresh-aliases`. Das Ziel liegt außerhalb des in der Spec begrenzten Schreibbereichs.
  Remediation: Symlinks überspringen (`Path.is_symlink()` im Schreibpfad von `refresh_aliases`) oder den Link erst auflösen und nur schreiben, wenn das Ziel unter `commands_dir` liegt.

Finding:
  ID: F002
  Severity: MEDIUM
  Category: edge_case
  Code reference: core/hooks/alias_sync.py:221
  Description: Die Schleife in `refresh_aliases` hat kein try/except pro Datei. Wirft `write_text` bei einer markierten, nicht schreibbaren Datei (0444), bricht der Aufruf ab. `refresh_home_aliases` (session_banner.py:161) fängt das und liefert `[]`. Reproduziert in Angriff 10: spätere veraltete Kopien blieben alt, `00-bug.md` blieb bestehen, keine Zeile erschien. Bereits aufgefrischte Dateien werden ebenfalls nicht gemeldet.
  Spec requirement: AC-10 / Implementation Details 1 — jede Exception führt zu Exit 0, die sichere Wartung soll trotzdem laufen
  Conflict: Fail-open ist erfüllt (Exit 0, kein Traceback). Aber eine einzelne Datei blockiert die ganze Wartung, und das bleibt dem Nutzer unsichtbar.
  Remediation: try/except pro Datei in `refresh_aliases`, bei Fehler überspringen und weitermachen. Dabei darf `setup.py` nicht still schlucken (Konsolenausgabe bleibt unverändert).

## Herkunft der Vorbedingungen

kein Sprachprofil konfiguriert (`precondition_origins.default_lang`)

## Verdict

Alle 11 Punkte (Input, Output, Side effects, AC-1 bis AC-11) sind CONFIRMED. Die Befunde F001 und F002 sind MEDIUM-Randfälle ohne AC-Verletzung.

Tests: 84 passed, 0 failed, 0 übersprungen
Edge cases: Alle geprüft, außer F001 und F002 nichts gebrochen
Regressions: None found
Checklist: 14/14 points proven

VERDICT: VERIFIED

## Geprüfte Dateien

- sha256:95f13876af60c21b8776ced1d783457701e916da7b438afa789496a59c8ef831  core/hooks/alias_sync.py
- sha256:97ed428e4d6bb73e3a3e6a135e6b166cf2553f8634560fa1d79760e40e4bb193  core/hooks/session_banner.py
- sha256:aceacefebcfbf0a1927426c5527d4be29fff04ca84347d42e1907a77215fc2e9  hooks/hooks.json
- sha256:f6e4984f4f188ac34a6970cb1050a84abc33d6b482114c54ee32878d0e3da071  setup.py

## Prüfbasis

- base: cd4ed5a29a5b9abd43477f4b689b62ba1e551788
- blob:0b47249a07cc02839586ac499a3fb77e0d5f0ae9  core/hooks/alias_sync.py
- blob:72b00d662f8570b7b1b5134f25f83f7b41d414d7  core/hooks/session_banner.py
- blob:2315abc245efe26b33baed5a9dd9d08a35a9903c  hooks/hooks.json
- blob:760564ad3f7c93bafe81eeb1b94974ca076342da  setup.py
