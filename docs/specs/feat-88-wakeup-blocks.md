---
entity_id: feat-88-wakeup-blocks
type: module
created: 2026-09-26
updated: 2026-09-26
status: draft
version: "1.0"
tags: [prozess, commands, skills, issue-88, issue-250]
---

# Weckruf-Pflichtblöcke auf einen Rückfall je Befehl reduzieren (Issue #88)

## Approval

- [ ] Approved

## Purpose

Vier Befehlsdateien (`20-analyse`, `30-write-spec`, `50-implement`, `60-validate`) schreiben
nach jedem Subagenten-Spawn einen eigenen Block „**TIMEOUT-PFLICHT — sofort nach dem Spawn**“
mit einem `ScheduleWakeup(...)`-Aufruf vor, 13 Vorkommen in den vier Dateien und identisch 13
weitere in den generierten `skills/*/SKILL.md` — macht 26. Die Werkzeugbeschreibung von
`ScheduleWakeup` widerspricht dem direkt: kurze Weckrufe zum Abfragen selbst gestarteter
Hintergrundarbeit sind verschwendet, weil die Sitzung bei Fertigstellung automatisch erneut
aufgerufen wird; sie nennt 1200 s+ als Rückfall und ordnet das Werkzeug primär der Selbsttaktung
im `/loop`-Modus zu. In dieser Analyse (Befund F9) meldete sich der Strategie-Agent nach 144 s
zurück — der vorgeschriebene 300-s-Weckruf in `20-analyse.md` Zeile 107 wäre ins Leere gelaufen
und wurde deshalb gar nicht erst gesetzt. Eine Anweisung, die strukturell nie greift, aber als
PFLICHT geführt wird, untergräbt die Verbindlichkeit der übrigen Pflichtschritte derselben Datei.
Kein einziger Test schützt diese Stellen heute (Suche nach `ScheduleWakeup` in `tests/` → leer).

Diese Spezifikation deckt ausschließlich Issue #88 (Teilauftrag 1 der Prozessabstufungs-Analyse)
ab. Die Teilaufträge 2–4 (#147: Validierung abstufen, ein neuer Vorgang als Vorbedingung für
Issue #182, #182: Aufwandsbremse) sind bewusst ausgeklammert und bekommen je eine eigene Spec.

## Source

- **File:** `core/commands/20-analyse.md`, `core/commands/30-write-spec.md`,
  `core/commands/50-implement.md`, `core/commands/60-validate.md`
- **Identifier:** Abschnitt „TIMEOUT-PFLICHT — sofort nach dem Spawn“ (13 Vorkommen in diesen
  vier Dateien, je Datei 3–4 Blöcke)

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `scripts/sync_skills.py` | Generator-Skript | Erzeugt `skills/*/SKILL.md` aus `core/commands/*.md`; muss nach jeder Textänderung an den vier Befehlsdateien laufen, sonst driften Skill und Command auseinander |
| `scripts/release_check.py::check_skills_sync()` | Funktion | Bricht den Release-Check ab, wenn `skills/` nicht exakt dem Generat aus `core/commands` entspricht — deckt eine vergessene `sync_skills.py`-Ausführung auf |
| `tests/test_skills_sync.py` | bestehende Tests | Prüft dieselbe Drift bereits auf Testebene; muss nach der Textänderung unverändert grün bleiben |
| `tests/test_skill_stop_instruction.py` | bestehende Tests | String-Präsenz-Checks auf `skills/40-tdd-red/SKILL.md`; berührt keine der vier hier geänderten Dateien, muss aber unverändert grün bleiben (Regressionsnachweis, dass die Änderung isoliert bleibt) |
| `tests/test_clear_checkpoint_blocks.py` | bestehende Tests | Prüft Struktur der `/clear`-Checkpoint-Blöcke in denselben vier plus einer fünften Befehlsdatei; die hier entfernten TIMEOUT-PFLICHT-Blöcke liegen außerhalb dieser Checkpoint-Abschnitte, dürfen deren Struktur aber nicht verschieben |
| `ScheduleWakeup` (Werkzeugbeschreibung) | externes Werkzeug | Quelle der Empfehlung „1200 s+ als Rückfall, primär für `/loop`“, gegen die diese Spec die verbleibenden Blöcke kalibriert |
| `TaskList` / `TaskStop` | externe Werkzeuge | Primärer Ersatzmechanismus: Nachfassen beim nächsten eigenen Zug statt Weckruf |

## Scope

- **Affected Files:** `core/commands/20-analyse.md`, `core/commands/30-write-spec.md`,
  `core/commands/50-implement.md`, `core/commands/60-validate.md`,
  `skills/20-analyse/SKILL.md` (generiert), `skills/30-write-spec/SKILL.md` (generiert),
  `skills/50-implement/SKILL.md` (generiert), `skills/60-validate/SKILL.md` (generiert),
  `tests/test_wakeup_blocks.py` (neu), `CHANGELOG.md`, `.claude-plugin/plugin.json`
- **Estimated Changes:** ≈ −40 / +90 LoC

Logik-Dateien im Sinn der Scoping-Grenze (max. 4–5 Dateien, ±250 LoC): **5** — die vier
`core/commands/*.md`-Dateien plus `tests/test_wakeup_blocks.py`. Die vier `skills/*/SKILL.md`-
Dateien zählen nicht mit: sie sind reines Generat aus `scripts/sync_skills.py` und werden nie
von Hand editiert (ein Hand-Edit würde `release_check.py::check_skills_sync()` zum Scheitern
bringen). `CHANGELOG.md` und `.claude-plugin/plugin.json` zählen ebenfalls nicht mit: reine
Buchführung (Änderungseintrag, Versionsbump), keine Logikänderung. Damit bleibt die Änderung
innerhalb der Hausregel, obwohl formal 11 Dateien im Repository berührt werden.

## Implementation Details

### 0. Variantenwahl gegen die drei Vorschläge aus #88

Vorgang #88 nennt drei mögliche Wege. Diese Spec entscheidet sie ausdrücklich, damit die Wahl
nicht beliebig bleibt:

Vorab eine Richtigstellung zur Ursprungsanfrage: #88 begründet das Problem damit, `ScheduleWakeup`
sei außerhalb von `/loop` **gar nicht aufrufbar**. Das ist widerlegt (Kommentar in #88 vom
2026-09-26: am selben Tag viermal in einer gewöhnlichen Sitzung erfolgreich benutzt). Der tragende
Befund ist ein anderer und bleibt gültig: Die vorgeschriebenen Intervalle von 180–600 s feuern
regelmäßig erst, nachdem der überwachte Agent längst zurückgemeldet hat — verschwendete Abfragen
statt eines einzigen langen Rückfalls. Diese Spec baut auf dem korrigierten Befund auf, nicht auf
der widerlegten Prämisse.

| Vorschlag aus #88 | Entscheidung | Begründung |
|---|---|---|
| (1) Nachfassen beim nächsten Zug statt Wecker (`TaskList`/`TaskStop`) | **gewählt, als primärer Mechanismus** | Deckt sich mit der Werkzeugbeschreibung: die Sitzung wird bei Fertigstellung des Hintergrund-Agenten automatisch erneut aufgerufen. Ein kurzer Wecker dazwischen kommt regelmäßig zu spät und bringt nichts, was der automatische Wiederaufruf nicht schon geliefert hat — Variante (1) braucht deshalb überhaupt kein Wartewerkzeug. |
| (2) `Monitor` verwenden | **verworfen** | `Monitor` wartet aktiv auf eine Bedingung und hält damit den laufenden Zug auf. Bei Hintergrundarbeit, die den Wiederaufruf ohnehin selbst auslöst, erzeugt das nur Wartezeit ohne Erkenntnisgewinn — Variante (1) leistet dasselbe zum Preis von Null. Das ist die vollständige Begründung; eine Aussage über die Verfügbarkeit von `Monitor` wird hier ausdrücklich **nicht** getroffen, weil sie ungeprüft wäre. |
| (3) `ScheduleWakeup` nur noch als Option im `/loop`-Kontext ausweisen | **gewählt, als nachrangiger Rückfall** | Im `/loop`-Betrieb ist Selbsttaktung der bestimmungsgemäße Zweck des Werkzeugs. Dort bleibt ein Rückfall sinnvoll — aber ehrlich als kontextabhängige Option gekennzeichnet, nicht als Pflicht für alle Sitzungsarten. |

Die Spec setzt also (1) als Regel und (3) als Ausnahme um; (2) ist begründet verworfen und wird
nicht umgesetzt.

### 1. Je Befehlsdatei: 3–4 Blöcke → 1 Rückfall

In jeder der vier Dateien werden alle bestehenden „TIMEOUT-PFLICHT — sofort nach dem Spawn“-
Blöcke entfernt und durch **einen einzigen** neuen Abschnitt „### Hängende Subagenten“ ersetzt,
platziert direkt vor dem ersten Spawn-Schritt der Datei (also einmal pro Datei, nicht mehr pro
Spawn). Der Abschnitt hat zwei Teile:

**Teil A — der Ersatz-Absatz (identischer Wortlaut in allen vier Dateien):**

> Primärer Schutz gegen einen hängenden Subagenten: Die Sitzung wird automatisch erneut
> aufgerufen, sobald der Hintergrund-Agent fertig ist. Liegt beim nächsten eigenen Zug noch kein
> Bericht vor, `TaskList` prüfen — ist der Agent dort noch als aktiv gelistet, ihn mit
> `TaskStop` beenden und mit präziserem Briefing neu starten. Kein endloses Warten.

**Teil B — der verbleibende Rückfall, nur für den `/loop`-Kontext:**

> Nur falls dieser Befehl innerhalb eines `/loop`-Laufs (Selbsttaktung, dynamischer Modus) läuft,
> zusätzlich dieser Rückfall:

Je Datei genau ein `ScheduleWakeup(...)`-Aufruf mit Intervall ≥ 1200 s, der den ganzen Phasen-
Ablauf abdeckt statt eines einzelnen Spawns:

- `core/commands/20-analyse.md`:
  `ScheduleWakeup(1200, "Analyse-Agenten Rückfall [20-analyse], nur im /loop-Kontext: TaskList → noch aktiver Explore-/Bug-Intake-/Plan-Agent? JA → TaskStop, dann User: 'Analyse-Agent hängt — bitte /20-analyse neu starten.' NEIN → ignorieren, fertig.")`
- `core/commands/30-write-spec.md`:
  `ScheduleWakeup(1200, "Spec-Schreiben Rückfall [30-write-spec], nur im /loop-Kontext: TaskList → noch aktiver Spec-Writer-/Validator-/PO-Briefer-Agent? JA → TaskStop, dann User: 'Agent hängt — bitte /30-write-spec neu starten.' NEIN → ignorieren, fertig.")`
- `core/commands/50-implement.md`:
  `ScheduleWakeup(1200, "Implementierung Rückfall [50-implement], nur im /loop-Kontext: TaskList → noch aktiver Explore-/Developer-/Adversary-Agent? JA → TaskStop, dann User: 'Agent hängt — bitte /50-implement neu starten.' NEIN → ignorieren, fertig.")`
- `core/commands/60-validate.md`:
  `ScheduleWakeup(1200, "Validierung Rückfall [60-validate], nur im /loop-Kontext: TaskList → noch aktiver Kontext-/Validierungs-/Auto-Fix-/Docs-Updater-Agent? JA → TaskStop, dann User: 'Agent hängt — bitte /60-validate neu starten.' NEIN → ignorieren, fertig.")`

Die genaue Formulierung der einzelnen Agentennamen im String wird während `/40-tdd-red` und
`/50-implement` final abgestimmt; bindend aus dieser Spec sind: höchstens ein Vorkommen je
Datei, Intervall ≥ 1200, kein `TIMEOUT-PFLICHT` mehr, und der Ersatz-Absatz aus Teil A wortgleich
in allen vier Dateien.

### 2. Generierte Skills nachziehen

Nach den vier Textänderungen: `python3 scripts/sync_skills.py` ausführen. Das schreibt
`skills/20-analyse/SKILL.md`, `skills/30-write-spec/SKILL.md`, `skills/50-implement/SKILL.md`
und `skills/60-validate/SKILL.md` neu — kein Hand-Edit an diesen vier Dateien, sonst bricht
`scripts/release_check.py::check_skills_sync()` bei nächster Prüfung ab.

### 3. Neuer Test `tests/test_wakeup_blocks.py`

Iteriert über **alle** Dateien unter `core/commands/*.md` und `skills/*/SKILL.md` (Glob, keine
hartkodierte Liste der vier heute betroffenen Namen — siehe Known Limitations), und prüft je
Datei:

1. Anzahl `ScheduleWakeup(` ≤ 1.
2. Ist genau ein Vorkommen vorhanden, wird die erste Zahl im Aufruf per Regex extrahiert und
   muss ≥ 1200 sein.
3. Der String `TIMEOUT-PFLICHT` kommt in der Datei nicht vor.

Zusätzlich, parametrisiert nur über die vier heute betroffenen `core/commands/*.md`-Dateien:

4. Der Ersatz-Absatz („Primärer Schutz gegen einen hängenden Subagenten“ + „`TaskList`“ +
   „`TaskStop`“) ist wortgleich vorhanden.

Stil: reine String-/Regex-Präsenz-Checks über `pathlib.Path`, keine Fixtures, kein Mocking —
identisch zu `tests/test_skill_stop_instruction.py` und `tests/test_clear_checkpoint_blocks.py`.

### 4. CHANGELOG.md und Versionsbump

Neuer Eintrag unter einem neuen Abschnitt `## [3.32.0]`, Kategorie `### Changed`, mit Verweis
auf Issue #88: von 26 Weckruf-Pflichtblöcken auf einen Rückfall je Befehl reduziert — vier in
`core/commands/` plus die vier daraus erzeugten Skill-Varianten, also acht Vorkommen statt 26;
`TIMEOUT-PFLICHT` durch den ehrlichen Rückfall-Hinweis mit Mindestintervall 1200 s ersetzt.
`.claude-plugin/plugin.json`: `"version"` von `"3.31.1"` auf `"3.32.0"` (MINOR — Verhaltens-
und Text-Änderung an mehreren Befehlen, keine Breaking-Change, kein neuer Hook).

## Expected Behavior

- **Input:** Die vier Befehlsdateien `core/commands/{20-analyse,30-write-spec,50-implement,
  60-validate}.md` vor der Änderung, mit je 3–4 `TIMEOUT-PFLICHT`-Blöcken und Intervallen
  zwischen 180 und 600 s.
- **Output:** Dieselben vier Dateien enthalten danach je genau einen `ScheduleWakeup`-Aufruf
  mit Intervall ≥ 1200 s, eingebettet in den Ersatz-Absatz, der den automatischen Wiederaufruf
  und das `TaskList`/`TaskStop`-Nachfassen als primären Mechanismus benennt. `TIMEOUT-PFLICHT`
  kommt in keiner der Dateien mehr vor. Die vier generierten `skills/*/SKILL.md`-Dateien
  spiegeln denselben Stand exakt wider.
- **Side effects:** Keine Änderung an Hook-Code, keine Änderung am Workflow-State-Schema, kein
  neues Gate. `scripts/sync_skills.py --check` läuft nach der Änderung ohne Drift durch.

## Known Limitations

- Der neue Test ist ein reiner String-/Regex-Präsenz-Check auf Dateiinhalte. Er kann nicht
  prüfen, ob Claude den verbliebenen Rückfall zur Laufzeit tatsächlich beachtet oder das
  `TaskList`/`TaskStop`-Nachfassen tatsächlich ausführt — das bleibt Verhaltensvertrauen, wie
  bei jeder reinen Prompt-Instruktion in diesem Framework.
- Die Regel „höchstens ein `ScheduleWakeup` je Datei, Intervall ≥ 1200, kein `TIMEOUT-PFLICHT`“
  gilt nach dieser Spec nur für die vier heute betroffenen Befehle. Ein künftiger fünfter Befehl
  mit eigenen Weckruf-Blöcken würde von einer hartkodierten Dateiliste nicht erfasst. Deshalb
  iteriert `tests/test_wakeup_blocks.py` zwingend über **alle** Dateien unter `core/commands/`
  und `skills/` (Glob auf `*.md` bzw. `*/SKILL.md`), nicht über eine benannte Teilmenge — das
  ist Teil dieser Spec und keine spätere Kür.

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] `pytest tests/ -q` läuft vollständig grün, ohne einen einzigen Fehlschlag
- [ ] `python3 scripts/release_check.py` läuft durch (schließt `check_skills_sync()` ein)
- [ ] `CHANGELOG.md` und `.claude-plugin/plugin.json` sind aktualisiert (Eintrag unter
      `[3.32.0]`, Versionsstring exakt `"3.32.0"`)
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf grün, insbesondere
      `tests/test_skills_sync.py`, `tests/test_skill_stop_instruction.py` und
      `tests/test_clear_checkpoint_blocks.py`)

## Acceptance Criteria

- **AC-1:** Given alle Dateien unter `core/commands/*.md` und `skills/*/SKILL.md` nach der
  Umsetzung / When `tests/test_wakeup_blocks.py` je Datei die Anzahl der Vorkommen von
  `ScheduleWakeup(` zählt / Then ist die Anzahl in jeder einzelnen Datei ≤ 1.
  - Test: *(wird nach der TDD-RED-Phase eingetragen)*
- **AC-2:** Given eine Datei mit genau einem `ScheduleWakeup(...)`-Vorkommen aus AC-1 / When die
  erste Zahl im Aufruf per Regex extrahiert wird / Then ist dieser Wert ≥ 1200.
  - Test: *(wird nach der TDD-RED-Phase eingetragen)*
- **AC-3:** Given alle Dateien unter `core/commands/*.md` und `skills/*/SKILL.md` nach der
  Umsetzung / When nach dem Literal `TIMEOUT-PFLICHT` gesucht wird / Then kommt es in keiner
  dieser Dateien mehr vor.
  - Test: *(wird nach der TDD-RED-Phase eingetragen)*
- **AC-4:** Given die vier Dateien `core/commands/{20-analyse,30-write-spec,50-implement,
  60-validate}.md` nach der Umsetzung / When ihr Inhalt gelesen wird / Then enthält jede der
  vier Dateien wortgleich den Ersatz-Absatz mit den Begriffen „automatisch erneut aufgerufen“,
  „`TaskList`“ und „`TaskStop`“ — der Beleg, dass die gestrichenen Pflichtblöcke nicht
  ersatzlos entfernt, sondern durch den primären Mechanismus ersetzt wurden.
  - Test: *(wird nach der TDD-RED-Phase eingetragen)*
- **AC-5:** Given die vier `core/commands/*.md`-Dateien wurden geändert und
  `python3 scripts/sync_skills.py` wurde danach ausgeführt / When
  `python3 scripts/sync_skills.py --check` läuft / Then meldet es keine Drift (Exit 0).
  - Test: *(wird nach der TDD-RED-Phase eingetragen)*

## Test Plan

Automatische Tests (jeweils an eine AC oben gebunden):
- `pytest tests/test_wakeup_blocks.py -q` (AC-1 bis AC-4)
- `python3 scripts/sync_skills.py --check` (AC-5)
- Volle Regressionssuite: `pytest tests/ -q` (muss vollständig grün sein, insbesondere
  `tests/test_skills_sync.py`, `tests/test_skill_stop_instruction.py`,
  `tests/test_clear_checkpoint_blocks.py`)

Hinweis zur Testumgebung: Es gibt in diesem Projekt kein System-`pytest`. Tests laufen nur in
einem eigenen Scratchpad-venv mit `pytest` **und** `pyyaml` — fehlt `pyyaml`, läuft die Suite
still ins Leere, statt Fehler zu zeigen.

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Diese Änderung ist eine reine Text-/Anweisungsänderung an vier Markdown-
  Befehlsdateien plus einem neuen String-Präsenz-Test — kein neuer Mechanismus, kein neues
  Gate, kein Hook-Code betroffen. Es wird kein bestehender ADR gekippt: Das Generator-Muster
  (`core/commands/` als Quelle, `skills/` als Generat) und die Test-Stilkonvention (reine
  Dateiinhalts-Checks) bleiben exakt wie bisher, nur ihr Inhalt ändert sich.

## Changelog

- 2026-09-26: Initial spec created
