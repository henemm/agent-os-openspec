# Context: feat-250-teil-a-intake-einziger-eingang

## Request Summary
#250 Teil A, Stufe A1: `/00-intake` wird der einzige Eingang, auch für Bugs. Der Bug-Inhalt aus
`/00-bug` (Duplikatsuche, Fehler nachstellen, Ursache belegen) geht in `/00-intake` über,
`/00-bug` wird ein Hinweis, der eigene Bug-Schnellweg (`--type bug`, "Manuell testen", ohne
Gegenprüfung) entfällt. Kein Hook-Code. A2 (Typ `bug` aus den Hooks entfernen) ist ausdrücklich
nicht Teil dieses Auftrags.

## Related Files
| Datei | Relevanz |
|-------|----------|
| `core/commands/00-intake.md` | Erwähnt Bugs nirgends; bekommt den Bug-Abschnitt |
| `core/commands/00-bug.md` (122 Zeilen) | Quelle des Bug-Inhalts; enthält den Fast-Track-Block mit `--type bug` (Z. 88–122) |
| `core/commands/20-analyse.md` Z. 83–92 | Hat schon "Step 2b: Bug-Analyse (bug-intake/Haiku)" — Bug-Analyse ist dort bereits verankert |
| `core/agents/bug-intake.md`, `bug-investigator.md` | Bleiben unverändert; `00-bug.md` verweist auf `bug-investigator` |
| `skills/00-bug/SKILL.md`, `skills/00-intake/SKILL.md` | Generiert aus `core/commands` per `scripts/sync_skills.py` |
| `.claude/commands/00-bug.md` | Kurz-Alias, bleibt bestehen |
| `README.md` Z. 97, 157; `CLAUDE.md` Z. 449; `setup.py` Z. 774; `docs/WORKFLOW_GUIDE.md` Z. 268, 484 | Beschreiben `/00-bug` als Bug-Analyse-Einstieg |
| `tests/test_skills_sync.py` Z. 270 | `00-bug` ist als wiedereinstiegsfrei klassifiziert; Test verlangt, dass jede Befehlsdatei klassifiziert ist → `00-bug.md` darf nicht gelöscht werden |
| `tests/test_skill_path_resolution.py` Z. 185–200 | **Verlangt exakt 15 Skills mit Hook-Setup-Snippet**, `00-bug` ist einer davon (Kommentar "seit 3.23.0 inkl. 00-bug"). Wird `00-bug` zum reinen Hinweis ohne Workflow-Aufruf, entfällt der Snippet → Zahl 14, Test anpassen |

## Existing Patterns
- Bug-Analyse in der Kette existiert bereits: `/20-analyse` Step 2b ruft den Agenten `bug-intake`.
- Vorbild für Textänderungen mit String-Präsenz-Tests: `tests/test_wakeup_blocks.py` (#88),
  `tests/test_intake_two_tracks_254.py` (PR #330).
- `workflow.py start --type bug` legt den Workflow bei `phase6_implement` mit `spec_approved=True`
  und `red_test_done=True` an (`workflow.py` Z. 1075–1080) — der Mechanismus, der den Schnellweg
  an Spec und TDD vorbeiführt. Vier Hook-Dateien kennen den Typ `bug` (`edit_gate` Z. 667,
  `bash_gate` Z. 892, `workflow` mehrfach, `adversary_dialog` Z. 678) → A2, nicht A1.
- Das in `docs/specs/user-initiated-bug-workflow.md` beschriebene Flag-Gate
  (`bug_workflow_requested.json`, blockt `--type bug` ohne vorheriges `/00-bug`) ist im Code
  **nicht mehr vorhanden** (keine Treffer in `core/hooks/*.py`). Die Spec ist veraltet; für A1
  ohne Bedeutung.

## Dependencies
- Upstream: `scripts/sync_skills.py` erzeugt `skills/` aus `core/commands/`; `tests/test_skills_sync.py`
  prüft Drift.
- Downstream: Version-Marker-Zeile `⚙ /00-bug · …` in der Skill-Datei; Kurz-Aliase aus `setup.py`.

## Existing Specs
- `docs/specs/bug-fix-fast-track.md` — hat den `/00-bug`-Fast-Track eingeführt (wird mit A1 überholt).
- `docs/specs/user-initiated-bug-workflow.md` — veraltet (siehe oben).
- `docs/context/feat-250-prozess-abstufung.md` — Analyse des Sammel-Vorgangs.

## Risks & Considerations
1. **Konflikt mit offenem PR #330** (zwei Stufen statt drei): ändert ebenfalls `core/commands/00-intake.md`,
   `skills/00-intake/SKILL.md`, README, CLAUDE.md. A1 muss darauf aufbauen oder nach dessen Merge starten,
   sonst Konflikte in genau diesen Dateien. #330 wartet auf PO-Bestätigung.
2. **Snippet-Zählertest** (15 → 14), siehe oben.
3. **Dateizahl:** `00-intake.md`, `00-bug.md`, 2 generierte Skills, README, CLAUDE.md, setup.py-Tabelle,
   WORKFLOW_GUIDE, 2 Tests ≈ 10 Dateien, aber überwiegend Einzeiler in Tabellen. Logik-Dateien: 2 Befehle + Tests.
   Grenzfall zur Hausregel; Doku-Tabellen sind kaum LoC.
4. **Modellfrage:** Der Fast-Track-Block in `00-bug.md` ist der einzige Ort, der `--type bug` in Befehlen
   anlegt. Entfällt er, legt kein Befehl mehr diesen Typ an; Altbestand im Archiv bleibt lesbar.
5. **Trivialer Bug im Fast Track:** Die Voraussetzung "Ursache bekannt, ≤3 Dateien" wandert als
   Intake-Kriterium (Unsicherheit Low) in den Score, kein eigener Weg mehr.

## Analysis

### Type
Feature (Anweisungstext, kein Hook-Code). Kein UI → kein Entwurfs-Artefakt nötig.

### Stand nach erneuter Prüfung (2026-10-03)
- Risiko 1 der Kontext-Phase ist erledigt: #330 ist gemergt (HEAD `5b273e6`). `00-intake.md` kennt
  jetzt genau zwei Stufen (`feature-fast`, `feature`) und die Tiefe nach Score-Summe. A1 baut darauf auf.
- `00-intake.md` erwähnt Bugs nirgends. Ein Bug läuft heute entweder über `/00-bug` (Analyse, danach
  optional `--type bug` ohne Spec/TDD/Gegenprüfung, "Manuell testen") oder fälschlich über den
  Score ohne Ursachenbeleg.
- Zahlen aus dem Issue (gate-audit-data): Typ `bug` Median 91 min / P90 6,6 h, `feature-fast`
  Median 20 min. Der Bug-Schnellweg ist also weder schnell noch geprüft — er spart nur Nachweise.

### Affected Files
| Datei | Change | Inhalt |
|-------|--------|--------|
| `core/commands/00-intake.md` | MODIFY | neuer Abschnitt "Bugs": Duplikatsuche, Fehler nachstellen, Ursache belegen (file:line), STOP-Bedingungen; "Ursache bekannt, ≤3 Dateien" = Unsicherheit Low |
| `core/commands/00-bug.md` | MODIFY | auf Hinweis kürzen ("→ `/00-intake`"), Fast-Track-Block mit `--type bug` entfällt, keine Workflow-Aufrufe mehr |
| `skills/00-intake/SKILL.md`, `skills/00-bug/SKILL.md` | GENERATE | `python3 scripts/sync_skills.py`, nie von Hand |
| `tests/test_skill_path_resolution.py` | MODIFY | Snippet-Zähler 15 → 14 (nur falls `00-bug` den Snippet verliert; bei der Spec zu verifizieren) |
| `tests/test_intake_bugs_250a1.py` | CREATE | String-Präsenz nach Vorbild `test_intake_two_tracks_254.py` |
| `README.md` Z. 97/157, `CLAUDE.md` Z. 449, `setup.py` Z. 733/774, `docs/WORKFLOW_GUIDE.md` Z. 268/484 | MODIFY | Zeile "Bug-Analyse" → "Hinweis auf /00-intake" (je 1 Zeile) |
| `CHANGELOG.md` | MODIFY | unter [Unreleased] |

### Scope Assessment
- Logik-Dateien: 2 Befehle + 2 Tests; mit Doku-Einzeilern ≈ 10 Dateien (Grenzfall, aber 7 davon Einzeiler
  bzw. generiert — kein Logik-Zuwachs). Ich werte es als ein Ticket, weil die Doku-Zeilen sonst
  inkonsistent zum Befehl wären.
- LoC: ca. +70 / −85 (netto kleiner, da Fast-Track-Block und Bug-Doppelung entfallen)
- Risk: LOW — kein Hook, kein State-Format. Altbestand `--type bug` im Archiv bleibt lesbar; die Hooks
  akzeptieren den Typ weiter bis A2.

### Technical Approach (Empfehlung)
`/00-bug` bleibt als Datei bestehen (Test `test_skills_sync.py` Z. 270 verlangt jede Befehlsdatei
klassifiziert; Kurz-Alias und Gewohnheit bleiben erhalten), wird aber ein zehnzeiliger Hinweis auf
`/00-intake`. Der Bug-Inhalt zieht in den Intake als Schritt "Bug-Vorprüfung" **vor** dem Scoring:
Duplikat suchen → nachstellen → Ursache belegen. Das Ergebnis speist Scope und Unsicherheit. Danach
gilt dieselbe Wahl `feature-fast` / `feature` wie für alles andere; "Manuell testen" entfällt, der
Nachweis ist der Test, der den Fehler vorher rot zeigt.

### Alternativen (und was sie kippen würden)
1. **`/00-bug` ganz löschen** — sauberster Einstieg, aber bricht Alias, Reentry-Test und Gewohnheit;
   verworfen für A1, möglich nach A2.
2. **Bug-Analyse nicht in `/00-intake`, sondern nur in `/20-analyse` Step 2b lassen** (existiert schon)
   — kein Duplikat von Text. Nachteil: Der Intake bewertet dann ohne Ursachenkenntnis, genau die
   Fehlklassifizierung, die A1 beheben soll. Nicht gewählt, aber der Bug-Text im Intake sollte kurz
   bleiben und auf Step 2b verweisen, statt ihn zu kopieren.
3. **Bug-Schnellweg behalten, aber mit Gegenprüfung** — würde ADR "Bug-Fast-Track" (`docs/specs/bug-fix-fast-track.md`)
   erhalten; verworfen, weil der Weg im Archiv nicht schneller ist (Median 91 min) und die dritte Stufe
   #254 gerade entfernt wurde.
Regel statt Modell: nicht berührt, alles bleibt Textregel; ohne Modell geht hier ohnehin nichts schief.

### Dependencies
`scripts/sync_skills.py` → `skills/`; `tests/test_skills_sync.py` (Drift); A2 (Hooks, eigenes Ticket) folgt danach.

### Open Questions
- [ ] Snippet-Zähler: verliert `00-bug` den Hook-Snippet wirklich (hängt davon ab, ob der Hinweis
      `workflow.py` erwähnt)? In der Spec per Lauf klären, nicht raten.
- [x] Konflikt mit #330 — erledigt (gemergt).
