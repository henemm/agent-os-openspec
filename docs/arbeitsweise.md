# Arbeitsweise in diesem Repo

Für jede Sitzung an `agent-os-openspec`, auch in der Cloud. Ergänzt den Abschnitt „Rollen und
Zusammenarbeit“ in `CLAUDE.md` um die festen Projektregeln, die bisher nur im lokalen Gedächtnis
einzelner Rechner standen. Stand: PO-Vorgaben Hennings bis 2026-11-08.

## Grundsätze

- **Gründlichkeit vor Geschwindigkeit.** Fertig heißt: es funktioniert beweisbar, nicht „Code
  geschrieben“. Workflow-Phasen werden nicht übersprungen; jeder Schritt eines Slash-Commands wird
  so ausgeführt, wie er dort steht (Agenten, Reihenfolge), keine selbstgebauten Umwege. Gibt ein
  Gate einen Befehl vor, genau diesen ausführen.
- **Recherche zuerst.** Bei jedem Fehler und jeder unbekannten Schnittstelle (Claude-Code-Hooks,
  Settings, Plugins, GitHub Actions) zuerst die wörtliche Fehlermeldung und die aktuelle Doku suchen,
  dann erst Theorien bilden. Quellen im Ergebnis nennen.
- **Reproduktion zuerst.** Kein Fix ohne selbst ausgelösten Fehler; der Fix ist erst belegt, wenn
  derselbe Ablauf den Fehler nicht mehr zeigt. Ist der Ausgangszustand weg, ihn in einer
  Wegwerf-Kopie wiederherstellen.
- **„Hat es bisher funktioniert?“** vor jeder Ursachensuche klären. Eine Verschlechterung grenzt die
  Suche auf die Änderungen seit dem letzten guten Stand ein (`git log`, `CHANGELOG.md`).
- **In Alternativen denken.** Jede Analyse und Empfehlung nennt mindestens eine echte Alternative
  und welche frühere Entscheidung (Spec, ADR) dafür kippen würde. Getroffene Entscheidungen sind
  Arbeitsstand, kein Gesetz; Sunk Cost ist kein Argument.
- **Regeln vor Modell.** Was deterministisch lösbar ist, wird mit Regeln gebaut; ein Sprachmodell
  bekommt nur, was Sprachverstehen erfordert.
- **Keine manuellen Tests für Henning.** Alles wird automatisiert geprüft; nie „bitte manuell
  testen/prüfen“.

## Umgang mit Henning (PO)

- **Einzige Eingabe von ihm im Workflow:** die Freigabe-Wörter (`approved`, `go`, `override`, …)
  als getippte Textzeile, weil `phase_listener.py` nur getippte Prompts sieht. Ist die Entscheidung
  dahinter eine echte Wahl, wird sie zusätzlich per `AskUserQuestion` gestellt.
- **Keine Frage ohne Kontext:** vorher in derselben Nachricht ein zusammenhängender Block in
  Alltagssprache (worum es geht, welches Problem es löst, was sich für ihn ändert, was er
  entscheiden soll), erst dann die Frage. Sagt er „mir fehlt der Kontext“, erst erklären, nicht
  erneut fragen.
- **Gate- und Sicherheits-Designfragen entscheidet Claude** (was ein Gate sperrt, Known
  Limitations, Prüfung an der Quelle) nach Best Practice und berichtet Entscheidung und Quelle.
  Gefragt wird nur, wenn sich sein Arbeitsablauf spürbar ändert (etwa ein neues Wort, das er tippen
  muss), und dann mit fertiger Empfehlung.
- **Kleine Infra-/Hook-Korrekturen:** Henning hat dafür den Weg über `override` statt des vollen
  Freigabe-Durchlaufs gewählt (2026-09-21). Analyse, Reproduktion und Regressionstests bleiben
  Pflicht; für das CI-Spec-Gate reicht eine Fast-Track-Spec unter `docs/specs/fast/`.
- **Start-Hinweis des Banners** (veraltete Kurzbefehle, Haupt-Ordner hinter `origin/main`): Claude
  erledigt die genannten Wartungsschritte sofort selbst; Henning versteht diese Meldung nicht.
- **Präferenzen sofort im Repo festhalten.** Äußert Henning eine Vorgabe, gehört sie in derselben
  Antwort in `CLAUDE.md` oder diese Datei. Lokales Gedächtnis allein reicht nicht, Cloud-Sitzungen
  sehen es nicht.
- Nach einem abgeschlossenen Auftrag (gemergt, Issues aktuell) auf `/clear` hinweisen, mit einem
  Satz, was die nächste Sitzung als Erstes aufgreift.

## Aufgaben und Issues

- **Jede Aufgabe beginnt mit `/00-intake #<N>`.** Andere Einstiege werden nicht empfohlen.
- **Vor jedem neuen Issue die offenen durchsuchen**, nach dem Mechanismus („briefing“, „worktree“),
  nicht nach dem eigenen Titel. Gibt es eins, kommt der Mehrwert als Kommentar dorthin.
- **Mehrere Befunde:** jeder wird vor Sitzungsende entweder behoben und committet oder als eigenes
  Issue angelegt; sonst geht er mit `/clear` verloren.
- **Folgearbeit nach Ziel bündeln**, nicht ein Mini-Issue je Befund. Gehen Einzel-Issues vollständig
  in einem Sammel-Issue auf, werden sie mit „Aufgegangen in #X“ geschlossen.
- **„Nicht mehr umsetzen“ heißt schließen** (`not planned`, mit Grund und Datum), nicht nach hinten
  schieben.
- **Parallele Sitzungen:** Vor der Implementierung und vor jedem Commit Issue-Status, offene PRs und
  `origin/main` prüfen; hat eine andere Sitzung dasselbe schon gebaut oder offen, nicht doppelt bauen.

## Ausliefern

- **Weg:** eigener Branch → PR mit `Closes #<N>` → CI (`tests` immer; `spec-gate` und
  `release-readiness` bei PRs) → Squash-Merge (Repo-Konvention: Commit-Titel endet mit `(#<PR>)`).
  `scripts/ship.py` erledigt Push, PR, CI-Warten und Merge in einem Aufruf.
- **CI wirklich abwarten:** `gh pr checks <N> --watch` bis alle Checks fertig sind. `gh pr merge
  --auto` hat hier früher sofort gemergt, ohne auf `tests` zu warten.
- **Spec-Gate:** Reine Doku-Änderungen (`.md`, `.txt`) sind ausgenommen. Alles andere braucht eine
  committete Spec unter `docs/specs/` (Fast Track: `docs/specs/fast/`) samt Briefing, oder den
  sichtbaren Commit-Trailer `Spec-Gate: skip <Grund>`.
- **CHANGELOG:** jede Änderung unter `## [Unreleased]`, ohne Versionsnummer.
- **Keine Versionsnummer in Fix- oder Feature-PRs.** Der Bump in `.claude-plugin/plugin.json` ist eine
  eigene Release-Aufgabe: Er zieht README, `CLAUDE.md` (`**Version**:`), die Kurzbefehle unter
  `.claude/commands/` (`python3 setup.py . --refresh-aliases`) und einen abgeschlossenen
  CHANGELOG-Abschnitt mit. Liegt eine neue Version auf `main`, setzt `release.yml` Tag und Release
  automatisch (der Workflow pusht nur Tags, nie `main`).
- Konsumenten-Projekte erhalten die neue Version per Plugin-Update
  (`claude plugin update agent-os-openspec@henemm-private`); das führt Claude aus, nie Henning.
- Hook-Dateien (`core/hooks/`) nie per Bash oder Skript schreiben, nur per Edit über die Gates.

## Tests lokal

- Im System-Python fehlt `pytest`. Eigenes venv im Sitzungs-Scratchpad anlegen und **immer**
  `pip install pytest pyyaml` (ohne `pyyaml` brechen mehrere Module schon beim Einsammeln ab), dann
  `python -m pytest tests/ -q` mit diesem venv.
- `scripts/release_check.py` und `scripts/ci_spec_gate.py` mit demselben venv-Python starten, sonst
  meldet `release_check` eine rote Suite, die nur am fehlenden `pytest` liegt.

## Cloud-Sitzungen und Plugin

- Die Cloud lädt keine Plugins, auch nicht über `enabledPlugins` in der Projekt-`settings.json`
  (#520). Darum steht dort bewusst kein `enabledPlugins`: Die Gates laufen in der Cloud aus dem
  `hooks`-Block der `.claude/settings.json` (nur bei `CLAUDE_CODE_REMOTE=true`), lokal aus dem
  installierten Plugin, nie doppelt. Nach jeder Änderung an `hooks/hooks.json`
  `python3 scripts/sync_cloud_hooks.py` ausführen.
- Die Kurzbefehle unter `.claude/commands/` liefern ohne geladenes Plugin den Befehlstext aus
  `skills/<name>/SKILL.md` nach.
