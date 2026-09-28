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
