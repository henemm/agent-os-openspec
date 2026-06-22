# Agent OS + OpenSpec — Workflow-Handbuch

Dieses Dokument erklärt, was das Framework tut, warum es existiert, und wie die einzelnen Teile zusammenspielen. Es richtet sich sowohl an Entwickler, die mit dem System arbeiten, als auch an Product Owner, die verstehen wollen, welche Absicherungen es gibt und wann sie eingreifen.

---

## Wofür ist das Framework gut?

Ohne Struktur neigt Claude dazu, sofort Code zu schreiben — ohne vollständiges Verständnis der Anforderungen, ohne Tests, ohne Verifikation. Das führt zu:

- Implementierungen, die die eigentliche Anforderung verfehlen
- Code, der anfangs funktioniert aber keine Testabdeckung hat
- Commits, die mehr ändern als geplant
- Fehlern, die erst beim nächsten Deployment auffallen

Das Framework erzwingt technisch einen strukturierten Ablauf: **erst verstehen, dann spezifizieren, dann testen, dann implementieren, dann verifizieren.** Kein Schritt kann übersprungen werden — Gates blockieren Claude, bevor Dateien geschrieben werden.

---

## Die zwei Komponenten

### Agent OS
Hook-basiertes System, das Claude's Werkzeugaufrufe (Datei schreiben, Bash ausführen, git commit) abfängt und gegen Regeln prüft. Wenn eine Regel verletzt wird, wird der Werkzeugaufruf blockiert — nicht nur kommentiert, sondern technisch verhindert.

### OpenSpec
Workflow-Framework, das den Entwicklungsprozess in Phasen strukturiert und State persistent speichert. Jede Aufgabe (Feature, Bug) bekommt eine eigene JSON-Datei, die den aktuellen Stand festhält: welche Phase, welche Spec, welche Tests, welche Artefakte.

---

## Der 8-Phasen-Workflow

```
Phase 0: Idle (kein aktiver Workflow)
   ↓
Intake-Bewertung               /00-intake   [Track-Auswahl]
   ↓
Phase 1: Kontext sammeln        /10-context
   ↓
Phase 2: Analysieren            /20-analyse
   ↓
Phase 3: Spezifikation schreiben /30-write-spec
   ↓
Phase 4: User-Freigabe          → User sagt "approved"  [GATE]
   ↓
Phase 5: Failing Tests (RED)    /40-tdd-red             [GATE]
   ↓
Phase 6: Implementieren (GREEN) /50-implement
   ↓
Phase 6b: Adversary-Check       → User sagt "go"        [GATE]
   ↓
Phase 7: Validieren             /60-validate
   ↓
Phase 8: Abgeschlossen          → git commit möglich     [GATE]
   ↓
Deploy                         /70-deploy
```

Für Bugs und schnelle Features gibt es verkürzte Tracks (siehe unten).

---

## Was passiert in jeder Phase

### Vor dem Start — Intake (`/00-intake`)

`/00-intake` ist immer der erste Schritt. Es bewertet die Aufgabe nach drei Kriterien:

| Kriterium | Low (0) | Medium (1) | High (2) |
|-----------|---------|------------|----------|
| **Scope** | 1–3 Dateien, ≤30 LoC | 4–8 Dateien, ≤100 LoC | Neue Architektur |
| **Blast Radius** | Isoliertes Utility | Service-Schnittstelle | Auth, Infra, Breaking Change |
| **Unsicherheit** | Bekanntes Pattern | Teilweise bekannt | Neue Technologie |

- **Summe 0** → Fast Track (`feature-fast`): Phasen 3 → 4 → 6 → 8
- **Summe 1–3** → Standard (`feature`): alle Phasen
- **Summe 4–6** → Full Process: alle Phasen, volle Tiefe, 2+ Adversary-Runden

**Warum:** Verhindert, dass ein 10-Minuten-Fix durch alle 8 Phasen muss — und dass ein komplexes Feature ohne Analyse-Phasen startet.

### Phase 1 — Kontext sammeln (`/10-context`)

Claude erkundet das Projekt: betroffene Dateien, bestehende Tests, relevante Muster. Das Ergebnis wird in `docs/context/<workflow>.md` gespeichert. Erst danach kann Phase 2 beginnen.

**Warum:** Claude soll das Problem verstehen, nicht erraten. Kontext verhindert, dass Implementierungen vorhandene Patterns ignorieren oder Abhängigkeiten übersehen.

### Phase 2 — Analysieren (`/20-analyse`)

Drei parallele Explore-Agenten durchsuchen den Code nach: (a) betroffenen Komponenten, (b) existierenden Tests, (c) potenziellen Konflikten. Ergebnisse werden in der Context-Datei konsolidiert.

**Warum:** Parallelität spart Zeit. Drei unabhängige Searches decken mehr auf als eine sequenzielle.

### Phase 3 — Spezifikation schreiben (`/30-write-spec`)

Claude schreibt eine formale Spezifikation in `docs/specs/<bereich>/<feature>.md`. Diese enthält zwingend:
- `## Acceptance Criteria` mit nummerierten ACs (`AC-1`, `AC-2`, ...)
- `## Expected Behavior` (für den späteren Adversary-Check)

Das edit_gate.py prüft später, ob diese Struktur vorhanden ist, bevor Code-Edits erlaubt werden.

**Warum:** Ohne schriftliche ACs gibt es kein gemeinsames Verständnis davon, wann die Implementierung "fertig" ist.

### Phase 4 — User-Freigabe [GATE]

Der User liest die Spec und sagt `approved` (oder ähnliche Varianten: "freigabe", "lgtm", "sieht gut aus"). Erst dann kann Phase 5 beginnen.

**Was technisch passiert:** `phase_listener.py` erkennt das Keyword im User-Prompt, setzt `spec_approved: true` im Workflow-JSON und wechselt die Phase automatisch. Ohne diese Freigabe blockiert das edit_gate.py alle Code-Edits.

**Warum:** Der Product Owner gibt explizit grünes Licht für die Spezifikation. Claude kann nicht heimlich weitermachen, wenn die Anforderungen unklar sind.

### Phase 5 — Failing Tests schreiben (`/40-tdd-red`)

Tests werden geschrieben, **bevor** der zugehörige Code existiert. Die Tests müssen fehlschlagen. Der Test-Output wird als Artefakt gespeichert:

```bash
pytest tests/test_feature.py > docs/artifacts/test-red.txt 2>&1
workflow.py add-artifact test_output "docs/artifacts/test-red.txt" "3 tests failed" phase5_tdd_red
workflow.py mark-red "3 tests failed"
```

**Warum:** TDD (Test-Driven Development) stellt sicher, dass Tests die Anforderung prüfen, nicht die Implementierung nachzeichnen. Ein Test, der sofort grün ist, ohne dass Code geschrieben wurde, testet nichts.

### Phase 6 — Implementieren (`/50-implement`)

Ein spezialisierter Developer Agent bekommt die Spec und die failing Tests und schreibt minimalen Code, um die Tests grün zu machen. Nicht mehr, nicht weniger.

**Was technisch passiert:** Das edit_gate.py prüft vor jedem Datei-Edit:
1. Gibt es RED-Artefakte aus Phase 5? (Blockiert sonst)
2. Hat die Spec Acceptance Criteria? (Blockiert sonst)
3. Überschreitet der kumulierte Code-Delta das LoC-Limit (default 250)? (Blockiert sonst)

### Phase 6b — Adversary-Check [GATE]

Der User sagt `go`. Dann startet der Adversary-Dialog:

1. Ein `implementation-validator`-Agent (Sonnet) versucht aktiv, die Implementierung zu brechen
2. Er liest die Spec, prüft die ACs, sucht nach Edge Cases
3. Mindestens 2 Runden Dialog zwischen Fixer (Hauptkontext) und Adversary
4. Ergebnis: **VERIFIED** / **BROKEN** / **AMBIGUOUS**

- `VERIFIED` → Phase 7 freigegeben, git commit möglich
- `BROKEN` → Zurück zu Phase 6, Defekte müssen behoben werden
- `AMBIGUOUS` → User-Review erforderlich, Commit blockiert bis Klärung

**Warum:** Der Implementierer validiert sich nicht selbst. Ein unabhängiger Agent findet Probleme, die der Implementierer übersehen hat.

### Phase 7 — Validieren (`/60-validate`)

Manuelle Tests, Integration-Tests, UI-Checks. Claude dokumentiert den Validierungsstand. Am Ende: `workflow.py complete` archiviert den Workflow.

### Nach dem Abschluss — Deploy (`/70-deploy`) und Reset (`/99-reset`)

`/70-deploy` deployt den aktuellen Stand auf Produktion. Das Command ist projektspezifisch und muss angepasst werden — es enthält Pre-Flight-Checks (Branch, uncommitted changes, Rebase-Status) und das eigentliche Deploy-Kommando.

`/99-reset` schließt und archiviert den aktiven Workflow, oder löscht ihn, wenn er sich noch in einer frühen Phase befindet. Sinnvoll nach erfolgreichem Abschluss oder wenn ein Workflow abgebrochen werden soll.

### Phase 8 — Abgeschlossen

`git commit` wird nur erlaubt, wenn ein VERIFIED-Adversary-Verdict vorliegt. Das bash_gate.py blockiert den Commit sonst.

---

## Die vier Hooks — technischer Wächter

Hooks sind Python-Skripte, die Claude Code bei bestimmten Ereignissen automatisch ausführt. Sie können erlauben (Exit 0) oder blockieren (Exit 2).

### `phase_listener.py` — Keyword-Wächter (UserPromptSubmit)

Läuft bei **jeder User-Eingabe**. Erkennt Schlüsselwörter und aktualisiert den Workflow-State:

| Keyword | Aktion |
|---------|--------|
| `approved`, `freigabe`, `lgtm`, `sieht gut aus` | Phase 3 → 4, spec_approved = true |
| `go`, `green ok`, `tests ok` | Phase 6/6b → validated, green_approved = true |
| `stop`, `stopp`, `halt` | Stop-Lock aktivieren |
| `weiter`, `continue`, `resume` | Stop-Lock deaktivieren |
| `override`, `ich genehmige` | Override-Token erstellen |

Dieser Hook blockiert nie — er reagiert nur und aktualisiert State.

### `edit_gate.py` — Code-Wächter (PreToolUse Edit/Write)

Läuft **bevor Claude eine Datei schreibt oder bearbeitet**. Prüft sequenziell:

```
1. State-Dateien? → immer BLOCK
2. Immer-erlaubte Verzeichnisse (tests/, docs/, .claude/)? → ALLOW
3. Immer-erlaubte Dateitypen (.md, .yaml, .json)? → ALLOW
4. Keine Code-Datei? → ALLOW
5. Infra-Dateien (.claude/hooks/)? → nur mit Override-Token
6. Stop-Lock aktiv? → BLOCK
7. Kein Workflow für diese Datei? → BLOCK
8. Phase < 6 (phase6_implement)? → BLOCK (ohne Override)
9. Override-Token vorhanden? → ALLOW (überspringt Rest)
10. Keine RED-Artefakte? → BLOCK (außer bug/feature-fast)
11. Spec ohne Acceptance Criteria? → BLOCK
12. LoC-Delta > Limit? → BLOCK
→ ALLOW
```

### `bash_gate.py` — Shell-Wächter (PreToolUse Bash)

Läuft **bevor Claude einen Shell-Befehl ausführt**. Besonders relevant bei `git commit`:

```
1. Stop-Lock aktiv? → BLOCK
2. Reiner git-Befehl (kein commit)? → ALLOW (Fast Path)
3. Versucht Workflow-State direkt zu manipulieren? → BLOCK
4. Sensitive Datei + Output-Befehl? → BLOCK
5. Hardcoded Credentials im Befehl? → BLOCK
6. git commit:
   a. Required-Files nicht staged? → BLOCK
   b. Branch hinter origin/main? → BLOCK
   c. Kein VERIFIED-Verdict? → BLOCK
→ ALLOW
```

### `post_bash.py` — Test-Detektor (PostToolUse Bash)

Läuft **nachdem Claude einen Bash-Befehl ausgeführt hat**. Erkennt Test-Framework-Output:

Frameworks: pytest, jest, xcodebuild, go test, cargo test, vitest, mocha

Wenn ein Test-Run "passed" meldet → setzt automatisch `adversary_verdict = "VERIFIED:<framework>"` im Workflow-State. Kein manueller Schritt nötig.

---

## Agenten — Rollen, Modelle und Kontext

Das Framework arbeitet mit spezialisierten Agenten, die vom Hauptkontext (Orchestrator) gespawnt werden. Jeder Agent bekommt bewusst nur den Kontext, den er für seine Aufgabe braucht — nicht mehr.

### Warum Kontext-Isolation?

Ein Agent, der beim Validieren denselben Gedankenfluss sieht wie der Implementierer, tendiert dazu, dessen Logik unbewusst zu bestätigen ("Conversation Drift"). Daher gilt:

- Der **implementation-validator** sieht nie die Reasoning-Chain des Implementierers — nur Spec und Test-Output
- Der **external-validator** liest nie den Source Code — nur Spec und die laufende App
- Der **fresh-eyes-inspector** kennt nicht einmal den Bug-Kontext — er beschreibt nur, was er sieht

### Alle Agenten im Überblick

| Agent | Modell | Tools | Kontext, den er bekommt | Wann eingesetzt |
|-------|--------|-------|-------------------------|-----------------|
| **bug-intake** | Haiku | Read, Grep, Glob, Bash, Task | User-Symptom + Projekt-Codebase | `/00-bug`, Erstaufnahme |
| **analysis-challenger** | Sonnet | Read, Grep, Glob | Fertige Bug-Analyse (kein Reasoning des Investigators) | Nach Bug-Analyse, Devil's Advocate |
| **bug-investigator** | Sonnet | Read, Grep, Glob, Bash, Task, Write, Edit | Vollständiger Code-Zugriff + Bug-Kontext | Tiefe Bug-Analyse |
| **feature-planner** | Sonnet | Read, Grep, Glob, Bash, Task, Write, Edit | Vollständiger Code-Zugriff + Feature-Beschreibung | Phase 1–3 bei Feature-Planung |
| **spec-writer** | Sonnet | Read, Glob, Grep, Write | feature_name + analysis_summary + affected_files | Phase 3: Spec schreiben |
| **spec-validator** | Haiku | Read, Glob, Grep | Nur die Spec-Datei | Nach spec-writer, Qualitätsprüfung |
| **developer-agent** | Opus | Read, Grep, Glob, Bash, Edit, Write | Spec + affected_files + test_command (kein breiterer Kontext) | Phase 6: Implementieren |
| **implementation-validator** | Sonnet | Read, Grep, Glob, Bash | Spec + Test-Outputs — **kein Implementierer-Reasoning** | Phase 6b: Adversary-Check |
| **external-validator** | Sonnet | Bash, WebFetch | Nur Spec (ACs) + App-URL — **kein Source Code** | Phase 7: Externe Validierung |
| **fresh-eyes-inspector** | Sonnet | Read | Nur Screenshots — **kein Bug-Kontext, kein Code** | Phase 6b: UI-Bewertung |
| **test-runner** | Haiku | Bash, Read, Grep | Projekt-Typ (erkennt selbst), kein Feature-Kontext | `/82-test`, Phase 5+6 |
| **docs-updater** | Sonnet | Read, Glob, Grep, Edit, Write | changed_files + feature_summary | Nach Implementierung |
| **user-story-planner** | Opus | Read, Grep, Glob, Write, Edit | Vollständiger Kontext + interaktives JTBD-Interview | `/83-user-story` |

### Modell-Logik

| Modell | Wofür | Agenten |
|--------|-------|---------|
| **Haiku** | Schnelle, mechanische Aufgaben | bug-intake, spec-validator, test-runner |
| **Sonnet** | Analytische und kreative Arbeit | analysis-challenger, bug-investigator, feature-planner, spec-writer, implementation-validator, external-validator, fresh-eyes-inspector, docs-updater |
| **Opus** | Kern-Implementierung + User-Interaktion | developer-agent, user-story-planner, Orchestrator (Hauptkontext) |

### Kontext-Details der kritischen Agenten

**`developer-agent` (Opus):**
Der Agent bekommt genau vier Inputs: Spec-Datei, affected_files, test_files, test_command. Er sieht keine vorherigen Gesprächsrunden, keine Analyse-Phasen, keine Entscheidungspfade — nur das, was er zum Implementieren braucht. Das verhindert Scope Creep durch Kontext-Rauschen.

**`implementation-validator` (Sonnet):**
Bekommt ausdrücklich *nicht* die Reasoning-Chain des Implementierers. Er liest die Spec, führt die Tests aus und sucht aktiv nach Gegenbeweisen. Das ist der Kern des Adversary-Prinzips: er soll die Implementierung angreifen, nicht bestätigen.

**`external-validator` (Sonnet):**
Liest keinen Source Code. Er interagiert mit der laufenden App über HTTP/WebFetch wie ein echter User und prüft jeden AC direkt gegen die App — nicht gegen die Implementierung.

**`fresh-eyes-inspector` (Sonnet):**
Bekommt nur einen Screenshot, keinen Bug-Bericht, keine Erwartung. Er beschreibt, was er sieht. Der Wert liegt in der Unvoreingenommenheit: Er findet andere Probleme als jemand, der den Bug-Kontext kennt.

---

## Workflow-State: das Herzstück

Jede Aufgabe speichert ihren State in einer eigenen JSON-Datei:

```
.claude/workflows/
├── feature-login.json       ← aktiver Workflow
├── bug-checkout-error.json  ← paralleler Workflow
└── _archive/
    └── feature-old.json     ← abgeschlossen
```

Der aktive Workflow wird über die Umgebungsvariable `OPENSPEC_ACTIVE_WORKFLOW` identifiziert. Alle Hooks lesen diese Variable, um den richtigen State zu laden.

**Wichtige Felder im Workflow-JSON:**

| Feld | Bedeutung |
|------|-----------|
| `current_phase` | Aktuelle Phase (z.B. `phase6_implement`) |
| `spec_approved` | Hat der User die Spec freigegeben? |
| `spec_file` | Pfad zur Spezifikationsdatei |
| `affected_files` | Welche Dateien gehören zu diesem Workflow |
| `test_artifacts` | Registrierte Artefakte (RED-Tests, Screenshots) |
| `red_test_done` | Wurden RED-Tests durchgeführt? |
| `adversary_verdict` | VERIFIED / BROKEN / AMBIGUOUS |
| `loc_delta_current` | Aktueller Code-Delta in Lines |
| `phase_log` | Timeline aller Phasen mit Zeiten |

---

## Fast-Track-Varianten

### Bug-Fix (`--type bug`)
Startet direkt bei Phase 6. Überspringt: Kontext, Analyse, Spec, TDD. Sinnvoll für klare, isolierte Bugs.
- TDD-Gate übersprungen (konfigurierbar: `bug_fix.require_tdd: false`)
- Adversary-Check übersprungen
- Rebase-Gate bleibt aktiv

### Feature Fast Track (`--type feature-fast`)
Startet bei Phase 3 (Spec). Überspringt: Kontext, Analyse.
- TDD als Teil der Implementierung (inline, kein separater RED-Phase-Schritt)
- Spec + User-Freigabe weiterhin Pflicht
- Adversary-Check übersprungen

---

## Stop-Lock und Override-Token

### Stop-Lock
Sofortbremse: User sagt `stop` → alle Edit/Write/Bash-Operationen werden blockiert, bis der User `weiter` oder `continue` sagt. Nützlich, wenn Claude in eine falsche Richtung läuft und sofort gestoppt werden muss.

### Override-Token
Einmal-Bypass: User sagt `override` oder `ich genehmige` → ein Token wird erstellt, das den Phase- und TDD-Check für den nächsten Edit-Vorgang überspringt. Das Token ist einmalig und workflow-spezifisch.

**Wann sinnvoll:** Wenn ein Gate irrtümlich blockiert (z.B. Phase-State inkonsistent) oder wenn bewusst eine Ausnahme gemacht werden soll.

---

## Gate-Blockierungen: Was der User sieht

Wenn ein Gate blockiert, sieht Claude (und damit der User) eine strukturierte Meldung:

```
BLOCKED: No RED test artifacts found for workflow.
Run /40-tdd-red and register artifacts first.
[wf=feature-login (env) | token=keins | phase=phase6_implement]
```

Die Klammer am Ende zeigt immer:
- Welcher Workflow aktiv ist und wie er aufgelöst wurde (`env` = Umgebungsvariable)
- Ob ein Override-Token vorhanden ist
- Die aktuelle Phase
- Bei LoC-Blocks: aktuelles Delta und Limit

---

## Slash-Commands und Hooks: das Zusammenspiel

```
User tippt /10-context
    ↓
phase_listener.py erkennt Command-Kontext
    ↓
Claude sammelt Kontext (Read/Grep — keine Gates)
    ↓
Claude schreibt docs/context/<wf>.md
    ↓ edit_gate.py: .md-Datei? → ALLOW
Claude führt workflow.py phase phase2_analyse aus
    ↓ bash_gate.py: kein git commit, kein Secret → ALLOW
Phase wechselt zu phase2_analyse

User tippt "approved"
    ↓
phase_listener.py erkennt Approval-Keyword
    ↓
spec_approved = true, Phase → phase4_approved (automatisch)

User tippt /50-implement
    ↓
Developer Agent startet
    ↓
Agent versucht src/auth.py zu bearbeiten
    ↓ edit_gate.py:
      - Phase 6? ✓
      - RED-Artefakte vorhanden? ✓
      - Spec hat ACs? ✓
      - LoC-Delta < 250? ✓
      → ALLOW
Agent schreibt Code
    ↓
Agent führt pytest aus
    ↓ bash_gate.py: kein commit → ALLOW
Tests laufen durch
    ↓
post_bash.py: pytest + "passed" erkannt
    ↓
adversary_verdict = "VERIFIED:pytest" (automatisch)

User tippt "go"
    ↓
phase_listener.py: green_approved = true
    ↓
Adversary-Dialog startet (implementation-validator Agent)
    ↓
VERIFIED → Phase 7 freigegeben

User tippt git commit
    ↓ bash_gate.py:
      - Branch hinter main? nein ✓
      - VERIFIED-Verdict? ✓
      → ALLOW
Commit wird erstellt
```

---

## Parallele Workflows

Mehrere Features/Bugs können gleichzeitig laufen, jeder in einem eigenen State-File. Der aktive Workflow wird per `OPENSPEC_ACTIVE_WORKFLOW` umgeschaltet:

```bash
export OPENSPEC_ACTIVE_WORKFLOW=feature-login
# Alle Hooks arbeiten jetzt mit feature-login.json

export OPENSPEC_ACTIVE_WORKFLOW=bug-checkout-error
# Alle Hooks arbeiten jetzt mit bug-checkout-error.json
```

Das verhindert, dass parallele Arbeiten sich gegenseitig den State überschreiben.

---

## Retrospektive (`/90-retro`)

Nach dem Abschluss eines Workflows analysiert `/90-retro` den archivierten Workflow:

```
/90-retro              → zuletzt abgeschlossenen Workflow analysieren
/90-retro <name>       → bestimmten archivierten Workflow analysieren
/90-retro list         → alle archivierten Workflows auflisten
```

Zeigt: Phasen-Timeline, Dauer pro Phase, Qualitätssignale (Adversary-Findings, Fix-Loop-Iterationen), LoC-Delta, E2E-Scope.

Nützlich für: Prozess-Verbesserungen, Team-Reflektionen, Schätzungs-Kalibrierung.

---

## Alle Slash-Commands auf einen Blick

| Command | Phase | Beschreibung |
|---------|-------|--------------|
| `/00-intake` | vor 1 | Aufgabe bewerten, Track wählen (bug / feature-fast / feature) |
| `/00-bug` | — | Bug-Analyse starten (Analysis-First) |
| `/01-feature` | — | Feature planen (startet feature-planner Agent) |
| `/10-context` | 1 | Relevanten Kontext sammeln |
| `/20-analyse` | 2 | Anforderungen analysieren |
| `/30-write-spec` | 3 | Spezifikation erstellen |
| `/40-tdd-red` | 5 | Failing Tests schreiben (RED) |
| `/50-implement` | 6 | Implementieren (Tests grün machen) |
| `/60-validate` | 7 | Manuelle Validierung |
| `/70-deploy` | nach 8 | Deploy auf Produktion (projektspezifisch anpassen) |
| `/80-workflow` | — | Workflows verwalten (start, switch, status) |
| `/81-add-artifact` | — | Test-Artefakte registrieren |
| `/82-test` | — | Tests ausführen (startet test-runner Agent) |
| `/83-user-story` | — | JTBD-basierte User Story Discovery |
| `/90-retro` | nach 8 | Abgeschlossenen Workflow analysieren |
| `/99-reset` | — | Workflow abschließen oder abbrechen |

---

## Konfiguration

Das Framework wird über `openspec.yaml` im Projektverzeichnis konfiguriert. Wichtige Parameter:

| Parameter | Default | Bedeutung |
|-----------|---------|-----------|
| `scope_guard.max_loc_delta` | 250 | Maximale Lines of Code pro Workflow |
| `bug_fix.require_tdd` | false | TDD-Pflicht auch für Bugs |
| `bug_fix.max_files` | 4 | Maximale geänderte Dateien bei Bugs |
| `workflow.approval_phrases` | [approved, lgtm, ...] | Freigabe-Keywords |
| `stop_lock.stop_keywords` | [stop, stopp, ...] | Stopp-Keywords |
| `bash_gate.whitelist` | [] | Scripts, die den State-Integritäts-Check überspringen |

---

## Übersicht: Wer blockiert wann was

| Situation | Hook | Blockiert weil |
|-----------|------|----------------|
| Code-Edit vor Phase 6 | edit_gate | Phase zu früh |
| Code-Edit ohne Spec-Freigabe | edit_gate | Phase zu früh |
| Code-Edit ohne RED-Tests | edit_gate | TDD-Pflicht |
| Code-Edit ohne Acceptance Criteria | edit_gate | Spec unvollständig |
| Code-Edit > 250 LoC Delta | edit_gate | Scope zu groß |
| Bash nach "stop" | bash_gate | Stop-Lock aktiv |
| git commit ohne VERIFIED | bash_gate | Adversary-Check fehlt |
| git commit, Branch hinter main | bash_gate | Rebase-Pflicht |
| Hardcoded API-Key im Befehl | bash_gate | Credentials-Schutz |
| Direktes Schreiben in Workflow-JSON | bash_gate | State-Integrität |

---

## Kurz zusammengefasst

**Für den Product Owner:** Das Framework stellt sicher, dass keine Zeile Produktionscode entsteht, bevor du die Spezifikation freigegeben hast. Außerdem verhindert es, dass Änderungen unkontrolliert wachsen oder ohne Verifikation committet werden.

**Für den Entwickler:** Jede Einschränkung ist ein Gate mit einer klaren Fehlermeldung. Gates blockieren nicht willkürlich — sie sagen dir genau, was fehlt und wie du weitermachst. Fast Tracks für Bugs und schnelle Features sind explizit vorgesehen.
