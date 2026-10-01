# Context: feat-273-erreichbarkeitspruefung

> Phase 1 (Kontext) zu Issue #273 — „Prüfkette belegt Korrektheit, nicht Erreichbarkeit".
> Epic. Erwartetes Ergebnis von Phase 2 ist ein Schnittvorschlag in einzeln abnehmbare Teilvorgänge,
> **nicht** eine Umsetzung am Stück.

## Request Summary

Die Prüfkette des Frameworks (RED-Phase → Implementierung → Prüfdialog → Validierungsphase) belegt
durchgehend *Korrektheit* („tut der Code das Richtige, wenn er läuft"), nie *Erreichbarkeit* („läuft
er überhaupt, in allen Lagen, in denen er laufen soll"). #273 benennt dafür vier Blindstellen und
fordert vier Gegenmaßnahmen. Die Abnahmebedingung ist bewusst hart: das neue Verfahren muss den
echten Befund aus `henemm/loose-ends#144` auf dem unveränderten Stand `c36fec6` selbst wiederfinden,
ohne diesen Befund zu kennen.

## Ausgangslage, die in Phase 1 belegt wurde

### A. Die vier Blindstellen sind im Framework nachweislich unadressiert

Volltextsuche über `core/`, `skills/`, `templates/`, `docs/specs/` nach
`Erreichbarkeit|reachabilit|Herkunftstabelle`: **null Treffer**. Die Begriffe „Vorbedingung" und
„skipped" kommen vor, aber ausschließlich in anderer Bedeutung (Checkpoint-Vokabular der
Übergabeblöcke bzw. das TAP-Summary-Muster in `tdd_enforcement.py:81`).

Prüfung aller fünf beteiligten Agent-Definitionen und beider Skills auf die drei Prüffragen aus
#273 (Erreichbarkeit / Herkunft von Testvorbedingungen / übersprungene Tests): **in keiner Datei
vorhanden**. Die drei nächsten Näherungen:

| Fundstelle | Was sie tut | Warum sie die Lücke nicht schließt |
|---|---|---|
| `core/agents/implementation-validator.md:59` | `Find all callers (Grep for function name)` | Regressions-Check auf *bestehende* Aufrufer — fragt nicht, ob der *neue* Code je erreicht wird |
| `core/agents/external-validator.md:14,46,51` | Testet die laufende App von außen, muss die Vorbedingung real herstellen | Prüft Erreichbarkeit faktisch, benennt sie nie als Kriterium; läuft nur bei UI-/HTTP-Apps |
| `core/agents/external-validator.md:49,89-91` | `BLOCKED` / `AMBIGUOUS` mit `Missing evidence:` | Einziger Mechanismus, der ein *nicht geprüftes* Kriterium sichtbar macht — auf Unit-Test-Ebene existiert kein Gegenstück |

### B. Blindstelle 4 ist im Framework selbst reproduziert

`qa_gate.validate_test_output()` akzeptiert einen Lauf, in dem **jeder** Test übersprungen wurde,
als bestanden. Reproduziert am 2026-09-28 gegen den Stand dieses Zweigs:

| Eingabe (realistische Testausgabe) | Ergebnis des Gates |
|---|---|
| pytest: `0 passed, 5 skipped in 0.31s` | `(True, 'Tests PASSED: 0 passed')` |
| xcodebuild: `Executed 5 tests, with 5 tests skipped and 0 failures` + `** TEST SUCCEEDED **` | `(True, 'TEST SUCCEEDED')` |

Der zweite Fall zeigt zugleich, dass die `Executed …`-Erkennung (`qa_gate.py:133`) an der
skipped-Variante vorbeiläuft und erst der generische `TEST SUCCEEDED`-Fallback greift. Das ist
**dieselbe Regex, die #275 anfassen will** — siehe „Kollisionen" unten.

Ergänzend: weder das Report-Template des `developer-agent` (Z. 68-71, nur `Bestanden` /
`Fehlgeschlagen`) noch der Validation-Report in `skills/60-validate/SKILL.md:195-216` haben
überhaupt ein Feld für übersprungene Tests.

### C. Blindstelle 1 ist strukturell, nicht redaktionell

Die Checkliste des Prüfdialogs wird aus der Spec **generiert**:
`adversary_dialog.parse_spec_expected_behavior()` (`:52`) liest `## Expected Behavior` und die
`- **AC-N:**`-Bullets, der CLI-Zweig `parse` (`:773-784`) gibt sie nummeriert aus, und
`skills/50-implement/SKILL.md:212` speist genau diese Punkte in den Prüfer-Auftrag. Die
Deckungsgleichheit von Spec und Protokoll ist damit kein Versehen des Prüfers, sondern die
vorgesehene Mechanik.

Verschärfend: `skills/50-implement/SKILL.md:227` weist den Prüfer an, **„Lies NUR die Spec (nicht
den Code!)"**. Eine Runde ohne Spec, nur auf Diff und Code, ist im heutigen Ablauf also nicht
vorgesehen, sondern ausdrücklich ausgeschlossen.

### D. Zwei Lücken im Bestand, die bei der Umsetzung auffallen werden

1. **Der Prüfer bekommt den Spec-Pfad nicht.** Der Auftragsblock
   `skills/50-implement/SKILL.md:222-232` enthält keinen `Spec:`-Platzhalter (der Developer-Auftrag
   bei `:124` hat einen). Der Prüfer soll „nur die Spec lesen", bekommt aber keinen Pfad dorthin.
2. **Totes Gerüst.** `create_checklist()` (`adversary_dialog.py:115`) und
   `render_dialog_artifact()` (`:163`) werden von keinem Skill und keinem CLI-Zweig aufgerufen.
   Das Protokoll schreibt faktisch der Orchestrator von Hand; die Pflichtmarker (`### Runde N`,
   `- [x]`, `## Verdict`) stehen in **keinem** Skill als Formatvorgabe, werden aber von
   `validate_dialog_artifact_ex()` erzwungen. Die Rundenzahl (`MIN_ROUNDS = 2`, `:34`) hängt damit
   an einer ungeschriebenen Formatkonvention.
3. **Marker-Uneinheitlichkeit.** `implementation-validator.md:119` schreibt `VERDICT: X`,
   `external-validator.md:82` schreibt `## Verdict: X`. Die Validierung kennt beide Formen
   (`adversary_dialog.py:492 ff.`), aber jede neue Pflichtsektion muss diese Doppelung mitdenken.

## Related Files

| Datei | Relevanz |
|---|---|
| `core/hooks/adversary_dialog.py` | Kern. Checklisten-Erzeugung aus der Spec (`:52`, `:115`), Protokoll-Rendering (`:163`), Pflichtprüfung des Protokolls (`:412`), Hash-Block `## Geprüfte Dateien` (`:540-630`), Stempel (`:631`), Nachweis für Commit-Gate (`:713`) |
| `core/hooks/qa_gate.py` | Bewertet Testausgaben (`:109`) und ruft die Protokollprüfung über `--checklist` (`:252`). Hier sitzt Blindstelle 4 |
| `core/hooks/tdd_enforcement.py` | Bewertet RED-Artefakte (`_FAILURE_RE` `:54`, Prüfung `:218`). Zweite Stelle, an der „übersprungen ≠ fehlgeschlagen" entschieden wird |
| `core/hooks/bash_gate.py` | Commit-Gate verlangt gültigen Dialog-Nachweis (#253). Hebel, um eine neue Pflichtsektion durchzusetzen |
| `core/hooks/workflow.py` | `_validate_transition` nach `phase8_complete`; zweiter Hebel für dieselbe Pflicht |
| `core/agents/implementation-validator.md` | Der Prüfer. AC-für-AC-Vorgabe (`:64-69`, `:107`), Finding-/Confirmation-Format (`:80-105`), Verdict (`:109-154`) |
| `core/agents/fresh-eyes-inspector.md` | **Vorlage für die spec-freie Runde.** Schaut bewusst ohne Vorwissen (`:13-14`), darf keinen Code lesen (`:79`), erzeugt aber keine maschinenlesbaren Marker — für eine Gate-Auswertung müsste er ein Ausgabeformat bekommen |
| `core/agents/external-validator.md` | Stärkste AC-für-AC-Bindung (`:33-49`, `:79`, `:100`); der einzige mit `BLOCKED`/`Missing evidence:` |
| `core/agents/spec-validator.md` | Reiner Struktur-Check der Spec (`:23-65`), keine inhaltliche AC-Prüfung — entgegen der Formulierung in #273 |
| `core/agents/developer-agent.md` | Report-Template ohne skipped-Feld (`:68-71`) |
| `skills/50-implement/SKILL.md` | Step 8 = Prüfdialog (`:205-296`): Checklistenerzeugung `:209-215`, Prüferauftrag `:219-233`, Protokollablage `:244-249`, Registrierung `:251-256`, Stempel `:258-266`, Gate-Wirkung `:268-273`, QA-Gate `:275-288` |
| `skills/60-validate/SKILL.md` | Vier parallele Prüfungen (`:122-145`), Auto-Fix (`:154-168`), Report-Template (`:195-216`). Task 3 und Task 4 bekommen heute **keine** Eingaben mit |
| `core/commands/50-implement.md`, `core/commands/60-validate.md` | Spiegelquellen der Skills — jede Änderung muss beide treffen (vgl. Zweite-Wahrheiten-Problem #279) |
| `docs/specs/fix-253-adversary-evidence-gate.md` | **Präzedenzfall-Spec**: wie eine neue Pflicht am Protokoll in Gates verankert wurde |
| `docs/specs/fix-131-adversary-dialog-hash-binding.md` | Präzedenzfall für eine gestempelte Pflichtsektion mit Hash-Bindung |

## Existing Patterns

1. **Pflichtsektion im Protokoll + Gate, das sie erzwingt** — bereits gebaut für
   `## Geprüfte Dateien` (#131/#253): Der Prüfer zitiert Dateien über `Code reference:`, ein
   Stempel-Lauf hängt die sha256-Liste an, und `validate_dialog_artifact_ex()` weist das Protokoll
   ab, wenn die Hashes nicht zum Ist-Stand passen. **Die Herkunftstabelle aus #273 kann exakt diesem
   Muster folgen** — das ist der kürzeste Weg von „Regel im Dokument" zu „überprüfbar statt
   behauptbar".
2. **Trennung Form- vs. Inhaltsfehler** — `validate_dialog_artifact_ex()` liefert
   `failure_kind = 'content' | 'format'`, damit ein Formfehler kein negatives Urteil in den State
   schreibt (#77). Jede neue Pflichtprüfung muss sich in diese Zweiteilung einordnen.
3. **Prüfer ohne Vorwissen** — `fresh-eyes-inspector` existiert als Rolle, ist aber nur auf
   Screenshots angewandt. #273 will dieselbe Haltung auf Diff und Code.
4. **Regeln vor Modell** — #273 sagt ausdrücklich, dass das Einsammeln der per Zuweisung gesetzten
   Testvorbedingungen eine Textsuche ist und kein Sprachmodell braucht. Deckt sich mit der
   Hausregel; der Regelweg gehört in den Vorschlag, der Modellweg allenfalls als Alternative.
5. **Parallele Haiku-Prüfungen** — `skills/60-validate/SKILL.md:122-145` ist die vorhandene Stelle,
   an der eine fünfte, spec-freie Prüfung andocken könnte, ohne den Ablauf umzubauen.

## Dependencies

- **Upstream** (was die Änderung benutzt): `hook_utils` (Pfadauflösung, `extract_ac_entries`),
  `config_loader`, `override_token`, `workflow.py` (Artefakt-Register, Phasenübergänge).
- **Downstream** (was davon abhängt): `bash_gate.py` (Commit), `workflow.py` (`phase8_complete`),
  `qa_gate.py` (`--checklist`), beide Skills **und** beide Command-Spiegel, sowie **jedes
  installierte Projekt** — eine neue Pflichtsektion blockt dort sofort jeden Abschluss, der sie
  nicht liefert.

## Existing Specs

- `docs/specs/fix-253-adversary-evidence-gate.md` — Nachweis-Pflicht in Commit-Gate und Phase 8
- `docs/specs/fix-131-adversary-dialog-hash-binding.md` — Hash-Bindung des Protokolls
- `docs/specs/fix-965-ac-n-parse.md` — AC-N-Parsing der Checkliste
- `docs/specs/fix-71-qa-gate-zero-failed.md`, `docs/specs/fix-60-69-gate-parsing.md` — Vorgeschichte
  der Testausgaben-Bewertung in `qa_gate`

## Referenzfall für die Abnahmebedingung

Lokal vorhanden und damit prüfbar:

- Repository `/Users/hem/Developer/loose-ends`, Stand `c36fec6`
  („feat: Wortgleicher Rohtext setzt Dauer und Kontexte von früher (#136)") existiert.
- `LooseEndsTests/EnrichmentTests.swift:394` — Hilfsfunktion `makeProcessed(...)`;
  `:404` setzt `task.processedAt = Date(...)` **per Zuweisung**.
- Im heutigen Stand von loose-ends gibt es **keine** Produktionszuweisung an `processedAt` mehr;
  der Befund wurde dort inzwischen behoben. Die Gegenprobe muss deshalb zwingend gegen `c36fec6`
  in einer Wegwerf-Kopie laufen, nicht gegen den aktuellen Stand.

## Kollisionen mit anderen offenen Vorgängen

| Vorgang | Berührungspunkt | Konsequenz |
|---|---|---|
| #275 (Testausgabe-Erkennung) | Fasst `qa_gate.py:133` und `tdd_enforcement.py:54` an — dieselben Stellen wie Blindstelle 4 | #275 sagt selbst: „ob skipped als grün zählen darf, gehört in #273". Reihenfolge festlegen, sonst überschreiben sich die beiden |
| #279 (Zweite Wahrheiten driften) | `core/commands/*.md` und `skills/*/SKILL.md` sind Dubletten | Jede Änderung hier muss doppelt gepflegt werden, solange #279 offen ist |
| #259 / PR #266 (Nachweis an den Diff binden) | Erweitert denselben Nachweis-Mechanismus | Offener Entwurf — vor dem Schnitt prüfen, ob er Teile von #273 vorwegnimmt |
| #200 (Epic Verbindlichkeit) | Gleiche Grundfrage: Regeln, die nicht greifen | Abgrenzung in Phase 2 benennen |

## Risks & Considerations

1. **Wirkung auf alle Projekte.** Eine neue Pflichtsektion im Protokoll blockt ab Installation jeden
   Abschluss in jedem angebundenen Projekt. Ohne Übergangsregel (Warnung vor Block, oder Bindung an
   die Framework-Version) ist das ein Bruch.
2. **Scope.** Die vier Maßnahmen aus #273 überschreiten die Hausgrenze (5 Dateien / ±250 LoC) um ein
   Vielfaches. Der Schnitt in einzeln abnehmbare Teile ist das eigentliche Ergebnis von Phase 2.
3. **Die Abnahmebedingung ist selbst ein Arbeitspaket.** „Findet den Befund aus #144 wieder" heißt:
   Wegwerf-Kopie auf `c36fec6`, neues Verfahren dagegen laufen lassen, Ergebnis belegen. Das ist
   kein Nebensatz in einer Spec.
4. **Die Herkunftstabelle darf nicht zur Pflichtprosa verkommen.** Wenn sie ohne maschinelle
   Vorbefüllung eingeführt wird, schreibt sie der Prüfer aus dem Gedächtnis — und sie wird genau so
   spiegelbildlich wie die AC-Liste. Die Textsuche, die die Zuweisungen einsammelt, ist der
   tragende Teil, nicht die Tabelle.
5. **Sprachabhängigkeit.** Eine Textsuche nach Feldzuweisungen in Testdateien ist pro Sprache
   verschieden (Swift, Python, Go …). Entweder auf ein Sprachmodul beschränken oder von vornherein
   als konfigurierbares Muster bauen.
6. **Falschalarm-Risiko.** Eine zu breite Suche meldet jede Zuweisung in jedem Test. Ohne Filter
   (nur Modell-/Entitätsfelder, nicht lokale Variablen) erzeugt Maßnahme 1 mehr Rauschen als Befund
   — und wird dann umgangen.
7. **Totes Gerüst zuerst klären.** `create_checklist()` und `render_dialog_artifact()` werden nicht
   benutzt. Vor dem Anbau einer weiteren Sektion ist zu entscheiden, ob das Protokoll künftig
   erzeugt oder weiter von Hand geschrieben wird — sonst baut man an zwei Wahrheiten gleichzeitig.

---

# Analysis (Phase 2)

## Type

**Feature — Epic.** Ergebnis dieser Phase ist ein Schnitt in einzeln abnehmbare Teilvorgänge, keine
Umsetzung. Die Spec in Phase 3 beschreibt **eine** dieser Scheiben, nicht das Ganze.

## Was in Phase 2 zusätzlich belegt wurde

### 1. Der Regelweg für die Herkunftstabelle trägt — und lässt sich scharf stellen

Probe am Referenzprojekt `/Users/hem/Developer/loose-ends` (Arbeitsstand, nicht `c36fec6`):

| Verfahren | Treffer | Brauchbar? |
|---|---|---|
| Naive Suche `\w+\.\w+ = ` in `LooseEndsTests/` | 199 | Nein — Rauschen (lokale Variablen, Testgerüst) |
| Eingegrenzt auf die aus `Shared/Models/*.swift` maschinell gelesenen 83 Feldnamen | 161 Zuweisungen über **28 Felder** | Fast — 28 Zeilen sind eine Tabelle |
| Je Feld zusätzlich: Zahl der **Produktions-Schreibstellen** | 28 Zeilen, sortierbar | **Ja** — der Befund steht oben |

Sortiert nach Produktions-Schreibstellen aufsteigend liefert die Tabelle ohne jede Kenntnis des
Falls genau die verdächtigen Zeilen:

- 3 Felder mit **0** Schreibstellen im Betrieb (`energyRaw`, `calendarEventID`, `showInCalendar`)
- 5 Felder mit **genau 1** Schreibstelle, darunter `processedAt` — 1 Schreibstelle im Betrieb
  (`Shared/Enrichment/EnrichmentWriter.swift:94`) gegen 12 Zuweisungen im Test. Das ist der Befund
  aus `loose-ends#144`.

**Folge für den Schnitt:** Die Tabelle ist zu zwei Dritteln maschinell befüllbar. Die Spalten
*Feld*, *Test-Zuweisungen (Datei:Zeile)* und *Produktions-Schreibstellen (Datei:Zeile)* kommen aus
einer Textsuche. Nur *Bedingung davor* und *Test für diesen Weg* schreibt der Prüfer — für höchstens
eine Handvoll Zeilen, nicht für 161. Risiko 6 oben (Falschalarm) ist damit entschärft, ohne ein
Sprachmodell zu bemühen.

### 2. Korrektur an der Ausgangsannahme: die Symmetrieprüfung ist kein reiner Regelweg

Der Nachtrag in #273 stuft sie als deterministisch ein („die Lücke ist eine Mengendifferenz der
Testnamen"). Am Referenzfall hält das nicht. Die drei gleichartigen Regeln tragen ihre Tests als
Fließtextsätze:

```
DueDateRuleTests            (8)  „Ein Satz ohne Zeitausdruck liefert kein Ergebnis (AC-6)"
ImportanceUrgencyRuleTests  (7)  „Kein Treffer bleibt nil, kein Default (AC-3)"
RecognitionRuleTests       (16)  „Ein anderer Text liefert nichts — kein Standardwert (AC-2)"
```

**Aufzählen** der Geschwister-Tests ist mechanisch (Dateinamens-Konvention `*RuleTests.swift`,
`@Test("…")`). Der **Abgleich** „welchen Test hat das Geschwister, der dem Neuen fehlt" ist eine
Bedeutungsfrage und braucht Sprachverstehen. Die Symmetrieprüfung ist also ein Hybrid: Regel sammelt
ein, Modell vergleicht. Das ändert ihre Einstufung — teurer als angenommen — und damit ihren Platz
in der Reihenfolge.

### 3. Der Präzedenzfall `## Geprüfte Dateien` ist als Bauplan vollständig brauchbar

`adversary_dialog.py` hält das Muster in fünf kleinen Bausteinen bereit, die eine neue Pflichtsektion
eins zu eins nachbauen kann: `_extract_examined_files()` (`:545`, 16 LoC) sammelt ein,
`render_examined_files_section()` (`:578`, 7 LoC) rendert, `stamp_dialog_artifact()` (`:631`, 43 LoC)
hängt an, `_parse_examined_files_section()` (`:587`, 16 LoC) und `_verify_examined_file_hashes()`
(`:605`, 24 LoC) prüfen. Eingehängt wird an **einer** Stelle: `validate_dialog_artifact_ex()`
(`:412`), Schritt 6 von 6, nach der Verdict-Klassifikation.

Wichtig für die Spec: Die Reihenfolge in `validate_dialog_artifact_ex()` ist bedeutungstragend. Ein
inhaltliches Urteil (`BROKEN`, offene Checklistenpunkte → `failure_kind='content'`) blockt **vor**
der Formprüfung, damit ein Formfehler nie ein Urteil in den State schreibt (#77). Eine neue
Pflichtsektion ist ein **Formfehler**, solange sie nur fehlt — und ein **Inhaltsfehler**, sobald sie
da ist und eine Zeile ohne Herkunftsnachweis enthält. Diese Zweiteilung muss die Spec benennen.

**Kein Kill-Switch vorhanden.** Die bestehende Pflichtsektion ist unbedingt; `config.yaml` kennt
keinen Schalter dafür. Für eine neue Pflicht, die jedes installierte Projekt sofort blockt, ist das
zu wenig (Risiko 1 oben) — sie braucht einen eigenen Schalter und eine Warnstufe vor der Blockstufe.

### 4. Blindstelle 4 sitzt an vier Stellen, nicht an einer

| Datei | Stelle | Verhalten heute |
|---|---|---|
| `qa_gate.py` | `:145-153` (pytest-Summary), `:133-139` (`Executed …`) | `skipped` wird nicht extrahiert; `0 failed` genügt für grün |
| `tdd_enforcement.py` | `_FAILURE_RE` `:54`, Prüfung `:218` | kennt kein `skipped`; ein rein übersprungener Lauf zeigt keine Fehler-Evidenz |
| `post_bash.py` | `pass_patterns` `:81-87` | kennt keinen Status „skipped"; State bleibt unberührt |
| Report-Vorlagen | `implementation-validator.md:122,152`, `test-runner.md:39,46`, `skills/82-test:74,80`, `skills/60-validate:209` | überall nur `passed/failed`, nirgends ein Feld für Übersprungenes |

Alle vier Stellen fasst #275 ohnehin an. Das ist die entscheidende Kollision (siehe T5).

### 5. Der Prüferauftrag hat keinen Spec-Pfad (Bestätigung von D.1 oben)

`skills/50-implement/SKILL.md:219-233` übergibt dem `implementation-validator` die Checklistenpunkte
und die Regel „Lies NUR die Spec (nicht den Code!)" — aber **keinen Pfad zur Spec** und **keinen
Diff**. Der Auftragsblock des Developer Agent (`:124`) hat einen Spec-Platzhalter. Für eine
spec-freie Runde ist das günstig: es muss nichts entfernt, nur der Diff hinzugefügt werden.

Beide Spiegelquellen (`skills/50-implement/SKILL.md`, `core/commands/50-implement.md`) sind in diesem
Abschnitt inhaltlich deckungsgleich; sie unterscheiden sich nur in der Hook-Pfad-Auflösung. Jede
Änderung trifft beide (#279).

### 6. Runden sind untypisiert

`adversary_dialog.py:484` zählt Runden mit `^### Runde \d+`. Es gibt kein Feld, keinen Marker und
keine Struktur, um eine Runde als „spec-frei" zu kennzeichnen — `render_dialog_artifact()`
(`:228-235`) kennt je Runde nur `round`, `adversary`, `implementer`, `verdict`. Eine Pflicht
„mindestens eine Runde ohne Spec" braucht also zuerst eine Rundentypisierung.

---

## Schnittvorschlag — sechs Teilvorgänge

Reihenfolge nach Wirksamkeit je Aufwand. T1 und T2 zusammen decken den belegten Fall ab.

### T1 — Werkzeug: Herkunft von Testvorbedingungen einsammeln (Regelweg)

Neues Hilfsprogramm, das aus Modell-/Entitätsdefinitionen die Feldnamen liest, ihre Zuweisungen in
Testdateien einsammelt und je Feld die Schreibstellen im Produktivcode zählt. Ausgabe: eine
vorbefüllte Markdown-Tabelle, aufsteigend nach Produktions-Schreibstellen.

| Datei | Art | Beschreibung |
|---|---|---|
| `core/hooks/precondition_origins.py` | CREATE | Feldextraktion, Zuweisungssuche, Schreibstellen-Zählung, Tabellen-Rendering, CLI |
| `config.yaml` | MODIFY | Sprachprofile (Swift/Python), Pfadmuster für Modelle/Tests/Produktivcode |
| `tests/test_precondition_origins.py` | CREATE | Regelweg gegen Beispielbäume beider Sprachen |
| `CHANGELOG.md` | MODIFY | `[Unreleased]` |

Umfang: 4 Dateien, geschätzt +320/-0. **Über der Hausgrenze von ±250** — vertretbar, weil es eine
neue, isolierte Datei ist und kein Bestand umgebaut wird. Risiko: **niedrig** — greift in kein Gate
ein, ändert an keinem laufenden Projekt etwas.

### T2 — Pflichtsektion „Herkunft der Vorbedingungen" im Prüfprotokoll + Gate

Die Tabelle aus T1 wird Pflichtbestandteil des Protokolls, nach dem Muster von `## Geprüfte Dateien`.
Enthält zugleich die Erreichbarkeitsfrage aus Blindstelle 3 als zweite Spalte („hinter welcher
Bedingung steht die Schreibstelle"), weil es dieselbe Frage eine Ebene höher ist und dieselbe
Gate-Mechanik braucht.

| Datei | Art | Beschreibung |
|---|---|---|
| `core/hooks/adversary_dialog.py` | MODIFY | Parser/Renderer/Prüfung analog `:545-628`, Einhängung in `validate_dialog_artifact_ex()`, Form/Inhalt-Trennung |
| `skills/50-implement/SKILL.md` | MODIFY | Prüferauftrag: Tabelle aus T1 beilegen, Pflicht zur Vervollständigung |
| `core/commands/50-implement.md` | MODIFY | Spiegel (#279) |
| `core/agents/implementation-validator.md` | MODIFY | Pflichtabschnitt im Berichtsformat |
| `config.yaml` | MODIFY | Schalter + Warnstufe/Blockstufe |
| `tests/test_precondition_section.py` | CREATE | Pflicht, Warnstufe, Form/Inhalt-Trennung, Kill-Switch |

Umfang: 6 Dateien, geschätzt +300/-20. **Über beiden Hausgrenzen.** Risiko: **hoch** — eine neue
Pflicht blockt ab Installation jeden Abschluss in jedem angebundenen Projekt. Deshalb zwingend mit
Warnstufe vor Blockstufe und Kill-Switch.

**Harte Vorbedingung: #278 muss vorher erledigt sein.** #278 belegt, dass das erzwungene
Protokollformat in keiner Anweisung steht (`### Runde N` wird verlangt, nirgends gesagt) und dass
der passende Generator keinen CLI-Zugang hat. Eine zweite Pflichtsektion an ein Format zu hängen,
das niemandem mitgeteilt wird, verdoppelt genau den Fehler, den #278 beschreibt.

### T3 — Symmetrieprüfung gegen gleichartige Bausteine

Die fünfte Blindstelle aus dem Nachtrag. Aufzählung der Geschwister-Tests mechanisch, Abgleich durch
den Prüfer. Eigener Abschnitt im Protokoll, kein eigenes Werkzeug.

| Datei | Art | Beschreibung |
|---|---|---|
| `core/agents/implementation-validator.md` | MODIFY | Prüffrage + Berichtsabschnitt |
| `skills/50-implement/SKILL.md` | MODIFY | Auftrag: Geschwister benennen |
| `core/commands/50-implement.md` | MODIFY | Spiegel |
| `core/hooks/adversary_dialog.py` | MODIFY | Abschnitt prüfen (leicht, kein Hash) |
| `tests/test_sibling_symmetry.py` | CREATE | Pflichtabschnitt vorhanden/fehlend |

Umfang: 5 Dateien, geschätzt +140/-10. Risiko: **mittel** — wieder eine Pflicht in allen Projekten,
aber ohne maschinelle Vorbefüllung und damit anfällig für Pflichtprosa (Risiko 4 oben).

### T4 — Eine Prüfrunde ohne Spec (Blindstelle 1)

Rundentypisierung in `adversary_dialog.py` (Marker `### Runde N (ohne Spec)`), spec-freier
Prüferauftrag mit Diff statt Checkliste, Prüfung „mindestens eine Runde ist spec-frei".

**Empfehlung zur Ausgestaltung:** Die spec-freie Runde **ersetzt Runde 1**, sie kommt nicht hinzu.
`MIN_ROUNDS` bleibt 2. Begründung: Der unvoreingenommene Blick wirkt nur, solange er unvoreingenommen
ist — läuft er nach der AC-Runde, kennt der Prüfer die Kriterien bereits. Und das Token-Budget bleibt
unverändert, was die Regel „kein Fix-Loop nach VERIFIED" (CLAUDE.md) mitträgt.

| Datei | Art | Beschreibung |
|---|---|---|
| `core/hooks/adversary_dialog.py` | MODIFY | Rundentyp erkennen, zählen, prüfen |
| `core/agents/fresh-eyes-inspector.md` | MODIFY | Von Screenshots auf Diff/Code erweitern, maschinenlesbare Marker ergänzen |
| `skills/50-implement/SKILL.md` | MODIFY | Runde 1 spec-frei, Diff beilegen |
| `core/commands/50-implement.md` | MODIFY | Spiegel |
| `tests/test_specfree_round.py` | CREATE | Rundentyp, Mindestpflicht |

Umfang: 5 Dateien, geschätzt +180/-40. Risiko: **mittel**.

### T5 — Übersprungene Tests zählen nicht als grün (Blindstelle 4)

**Empfehlung: gehört nach #275, nicht hierher.** #275 fasst dieselben vier Stellen an
(`qa_gate.py:133/145`, `tdd_enforcement.py:54`, `post_bash.py:81`) und sagt selbst, die Semantikfrage
gehöre nach #273. Beide Vorgänge getrennt an denselben Regexen arbeiten zu lassen heißt: zweimal
lesen, zweimal testen, einmal überschreiben. #273 liefert die **Regel** („ein übersprungener
Pflichttest ist ein Fehlschlag"), #275 baut sie beim ohnehin fälligen Umbau der Erkennung ein.

Wird das nicht so entschieden, ist T5 ein eigener Teilvorgang: 3 Hooks + 4 Report-Vorlagen + Tests,
geschätzt 8 Dateien / +200.

### T6 — Gegenprobe am echten Fall + die Lehre in der Dokumentation

Die Abnahmebedingung des Epics. Wegwerf-Kopie von `loose-ends` auf `c36fec6`, das gebaute Verfahren
(T1+T2) dagegen laufen lassen, Ergebnis als Artefakt ablegen. Dazu der Dokumentationsteil aus der
Definition of Done („Die Lehre steht in der Plugin-Dokumentation, nicht nur in einer Prompt-Zeile").

Wichtig: Am 2026-09-27 wurde die Gegenprobe bereits **von Hand** gefahren und bestanden — belegt ist
damit, dass die **Frage** trägt. Offen ist, ob das **eingebaute Verfahren** sie ebenso findet. Das
ist der Unterschied zwischen „ein Agent mit dem richtigen Auftrag findet es" und „das Werkzeug stellt
den Auftrag von selbst".

| Datei | Art | Beschreibung |
|---|---|---|
| `docs/artifacts/<workflow>/gegenprobe-c36fec6.md` | CREATE | Lauf + Ergebnis |
| `docs/` (Plugin-Doku) | MODIFY | Die vier Blindstellen als Lehrtext |
| `CLAUDE.md` | MODIFY | Kurzregel |

Umfang: 3 Dateien, +150. Risiko: **niedrig**.

## Scope Assessment (Epic gesamt)

- Teilvorgänge: 6 (bei Verschiebung von T5 nach #275: 5)
- Dateien insgesamt: ~20 verschiedene, mit Mehrfachberührung von `adversary_dialog.py`,
  `skills/50-implement/SKILL.md` und `core/commands/50-implement.md` in vier von sechs Scheiben
- Geschätzt: +1300/-70
- Risiko gesamt: **hoch** — vier der sechs Scheiben setzen neue Pflichten in allen installierten
  Projekten durch

## Technical Approach — Empfehlung

**Gebaut wird zuerst T1, dann T2. Alles Weitere erst danach entscheiden.**

Begründung: T1+T2 sind die einzige Kombination, für die belegt ist, dass sie den Fall findet — die
Probe oben zeigt `processedAt` an erster Stelle einer 28-zeiligen Tabelle, ohne den Fall zu kennen.
T3 und T4 sind plausibel, aber unbelegt; T4 ist teuer und T3 teurer als im Nachtrag angenommen. Nach
T2 liegt mit T6 ein harter Beleg vor, an dem sich entscheiden lässt, ob T3 und T4 überhaupt noch
gebraucht werden.

**Die tragende Entscheidung ist der Regelweg, nicht die Tabelle.** Eine Pflichtsektion ohne
maschinelle Vorbefüllung schreibt der Prüfer aus dem Gedächtnis und wird dann genauso spiegelbildlich
wie die AC-Liste — der Fehler, den #273 überhaupt erst beschreibt. Deshalb steht T1 vor T2 und nicht
umgekehrt.

## Alternativen (ernsthaft erwogen, nicht empfohlen)

**A — Eigenes Gate-Artefakt statt Abschnitt im Prüfprotokoll.** Die Herkunftstabelle als eigener
Artefakt-Typ (`precondition_origins`), registriert wie ein RED-Artefakt, geprüft vom Commit-Gate.
*Dafür:* rührt das brüchige Protokollformat nicht an, umgeht die Kollision mit #278 vollständig,
wirkt auch im Fast Track, wo gar kein Prüfdialog läuft. *Dagegen:* noch ein Artefakt-Typ, noch ein
Ort zum Nachsehen; die Herkunftsfrage verliert den Zusammenhang mit dem Prüferurteil. **Diese
Alternative wird wieder aufgenommen, falls #278 sich verzögert** — dann ist sie die schnellere.

**B — Die Frage nach vorn ziehen, ohne Gate.** Das Werkzeug aus T1 läuft in `/20-analyse` oder
`/40-tdd-red`, sein Ergebnis wandert in den `## Test Plan` der Spec. *Dafür:* die Lücke wird erkannt,
bevor sie gebaut wird — dort ist sie am billigsten; kein Eingriff in irgendein Gate; keine Wirkung auf
bestehende Projekte. *Dagegen:* nicht erzwungen, also genau die Regel, „die nur im Dokument lebt",
gegen die sich #273 richtet. **Kippt Denkweise:** wäre die Absage an das Gate-Prinzip. Empfehlung
nur, falls die Warnstufe aus T2 sich als zu störend erweist.

**C — Zusätzliche Runde statt Ersatz bei T4.** Die spec-freie Runde kommt zu den zwei AC-Runden
hinzu. *Dagegen:* verdreifacht faktisch den Prüfaufwand und kippt die CLAUDE.md-Regel „kein Fix-Loop
nach VERIFIED", die aus einer realen Sitzung mit 177 Minuten und ~3 Mio. Ausgabe-Tokens stammt.
Deshalb im Vorschlag der Ersatz, nicht die Ergänzung.

## Dependencies und Reihenfolge

```
#278 (Protokollformat + Generator)  ──┐
                                      ├──► T2 ──► T6 ──► [T3 / T4 neu bewerten]
T1 (Werkzeug, unabhängig) ────────────┘

#275 (Testausgaben-Erkennung) ──────────► T5 (Semantik „skipped ≠ grün")
```

- **T1** hängt an nichts. Kann sofort beginnen.
- **T2** hängt an T1 **und** an #278.
- **T5** gehört nach #275 (Empfehlung) — sonst eigenständig, aber dann vor #275 zu terminieren.
- **#259 / PR #266** (Nachweis an den Diff binden) erweitert denselben Nachweis-Mechanismus wie T2.
  Vor T2 abschließen oder schließen — sonst kollidieren zwei Erweiterungen derselben Funktion.
- **#186** (Mutation als Pflichtartefakt) und **#194** (Adversary-Schwarm) sind Prüfaufträge, keine
  beschlossene Arbeit. Beide adressieren dieselbe Familie. Abgrenzung: #186 fragt „würde der Test den
  Fehler merken", T1/T2 fragen „kommt überhaupt Material am Test an". Ergänzend, nicht überlappend.
  Entscheidung über beide gehört zusammen mit T3/T4 nach T6.
- **#200** (Epic Verbindlichkeit) fragt, warum Pflichtregeln nicht greifen. #273 fragt, warum
  greifende Regeln das Falsche prüfen. Getrennte Vorgänge, keine Überschneidung im Code.

## Entscheidungen des PO (2026-09-28) — keine offenen Fragen mehr

| Frage | Entscheidung |
|---|---|
| Welche Scheiben werden jetzt gebaut? | **T1 und T2**, danach Gegenprobe, dann T3/T4 neu bewerten |
| Wohin gehört „übersprungen ≠ grün" (T5)? | **In #275** — dieselben vier Stellen, dort als Anforderung ergänzt |
| #278 vorziehen oder auf Alternative A ausweichen? | **#278 wird vorgezogen** — Alternative A bleibt Rückfalloption, falls #278 sich verzögert |

## Angelegte Vorgänge

| Teil | Vorgang | Status |
|---|---|---|
| T1 — Werkzeug: Herkunftstabelle maschinell vorbefüllen | **#285** | wird jetzt gebaut |
| T2 — Pflichtsektion im Prüfprotokoll + Gate (inkl. Blindstelle 3) | **#286** | umgesetzt (edfb9cd) |
| T3 + T4 — Symmetrieprüfung und spec-freie Prüfrunde | **#287** | zurückgestellt bis nach der Gegenprobe |
| T5 — „übersprungen ≠ grün" | Kommentar an **#275** | dort eingeplant |
| T6 — Gegenprobe c36fec6 + Doku | bleibt in **#273** | Abnahme des Epics |
| Vorbedingung für T2 | Kommentar an **#278** | vorgezogen |

**Nächster Schritt:** Die Spec in Phase 3 beschreibt **#285** (T1) — nicht das Epic, nicht T2.
