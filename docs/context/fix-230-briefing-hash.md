# Context: fix-230-briefing-hash

## Request Summary

`/60-validate` blockiert `phase8_complete`, weil Step 3 (docs-updater) die freigegebene Spec-Datei
anfasst und damit ihren `spec_sha256()` verändert, bevor Step 4 (`workflow.py phase
phase8_complete`) läuft — und `_check_po_briefing()` genau diesen Hash gegen den beim
`set-briefing`-Aufruf gestempelten Wert prüft, für **jede** Ziel-Phase ≥ `phase4_approved`.

## Related Files

| File | Relevance |
|------|-----------|
| `core/hooks/workflow.py:948-999` (`_validate_transition`) | Prüft `_check_po_briefing(data)` für jede Vorwärts-Transition mit `tgt_idx >= PHASES.index("phase4_approved")` — trifft auch `phase8_complete` |
| `core/hooks/workflow.py:857-916` (`_check_po_briefing`) | Schritt 6 (Z. 908-916): blockt bei `stored != spec_sha256(spec_content)` mit „PO-Briefing ist veraltet" |
| `core/hooks/workflow.py:715-717` (`spec_sha256`) | SHA-256 über den **gesamten** Spec-Inhalt, keine Ausnahme für einzelne Felder |
| `core/commands/60-validate.md:155-174` | Step 3 (docs-updater, Sonnet, `run_in_background: true`) steht **vor** Step 4 (`phase phase8_complete`) |
| `core/agents/docs-updater.md:26-35` | Listet „Entity specs → `docs/specs/[type]/[entity_id].md`" ausdrücklich als Ort, den der Agent aktualisiert — das ist der `spec_file` |
| `scripts/ci_spec_gate.py:255-264` | Prüft **dieselbe** Hash-Bindung serverseitig gegen die committeten Dateien im Pull Request |
| `tests/test_po_briefing_gate.py` | 27 Tests zur PO-Briefing-Gate-Logik; `test_4` und `test_14` decken „Spec nach Briefing geändert → Block" bereits für `phase5_tdd_red` bzw. die Freigabe-Transition ab — **keiner** für `phase8_complete` |

## Existing Patterns

- **`_check_adr(data)`** (Z. 597-628) ist strukturell analog zu `_check_po_briefing` — beide laufen
  in derselben `if tgt_idx >= PHASES.index("phase4_approved")`-Blockklammer. Eine Lösung sollte
  diese Klammer nicht pauschal für „ADR + Briefing" öffnen, sondern spezifisch für den
  Briefing-Hash-Check.
- **Reihenfolge-Kopplung ist im gesamten Framework die Ausnahme, nicht die Regel** — die anderen
  Phasenübergänge prüfen jeweils nur Vorbedingungen für die *eigene* Ziel-Phase, nicht für
  „mindestens so weit wie X". Der `>=`-Vergleich bei `phase4_approved` ist der einzige Ort, der eine
  spätere Phase (hier: `phase8_complete`) an eine Bedingung bindet, die eigentlich nur beim
  ursprünglichen `phase3 → phase4`-Übergang Sinn ergibt.

## Dependencies

- **Upstream:** `_check_po_briefing` liest `data.get("po_briefing")` (State, gesetzt von
  `cmd_set_briefing`) und `_read_spec_content(data)` (liest `spec_file` vom Datenträger).
- **Downstream:** `bash_gate.py` (Commit-Gate) und `_validate_transition` selbst rufen
  `_check_po_briefing` indirekt über denselben Codepfad auf — eine Änderung an der Funktion wirkt auf
  beide.

## Existing Specs

Keine Spec zu diesem Mechanismus selbst; die PO-Briefing-Gate-Funktionalität ist in CLAUDE.md,
Abschnitt „PO-Briefing-Gate (Freigabe Phase 3 → 4)" dokumentiert, aber nicht als eigene Entity-Spec.

## Befund aus der Recherche (gehört in die Analyse)

**Reihenfolge tauschen (Vorschlag 1 aus dem Issue) löst das Problem nicht.**
`scripts/ci_spec_gate.py:255-264` prüft dieselbe Hash-Bindung serverseitig auf den **committeten**
Dateien. Sobald der docs-updater die Spec anfasst, passt der gestempelte Hash im
Briefing-Frontmatter nicht mehr zur committeten Spec — unabhängig davon, ob das vor oder nach
`phase8_complete` geschieht. Das lokale Tauschen verschiebt den Bruch nur an eine teurere Stelle
(CI statt lokalem Hook).

**Der aktuelle `docs-updater` hat keine explizite Anweisung, `status: implemented` zu setzen oder
AC-Checkboxen abzuhaken** (`core/agents/docs-updater.md` enthält keinen Treffer für diese Muster).
Stichprobe an zwei realen Specs in diesem Repo (`docs/specs/short-command-aliases.md`,
`docs/specs/issue-14-name-validation.md`) zeigt weiterhin `status: draft` und `- [ ] Approved`
trotz abgeschlossener Workflows. Der im Issue beschriebene Byte-Änderungs-Effekt ist trotzdem real:
`docs-updater` darf laut seiner eigenen Dokumentationsliste die Entity-Spec-Datei anfassen — jede
Änderung, ob Status-Feld oder ein Changelog-Eintrag, ändert den Hash.

## Risks & Considerations

- **Risiko bei Weg 2 (Hash nur über inhaltlichen Teil):** Eine inhaltlich echte Änderung, die
  unglücklich nur in einem „ignorierten" Feld landet, gilt fälschlich als aktuell. Das Gate hätte
  dann eine stille Lücke.
- **Risiko bei Weg 3 (docs-updater fasst Spec nicht an):** Die Spec verliert die Eigenschaft, aus
  sich selbst heraus zu zeigen, dass sie umgesetzt ist. Ob das ein echter Verlust ist, hängt davon
  ab, ob die Spec als Vertrag (Zustand bei Freigabe, dauerhaft) oder als Archiv (Zustand bei
  Abschluss) gelesen werden soll — reale Stichprobe oben zeigt: heute wird sie in der Praxis
  offenbar nicht konsequent als Archiv gepflegt (`status: draft` bleibt stehen).
- **Blast Radius:** `_validate_transition` und `_check_po_briefing` sind Kernlogik, die in jedem
  Konsumenten-Projekt mit aktivem PO-Briefing-Gate greift (Default: aktiv, `skip_fast_track: true`).
  Eine Änderung hier ist nicht projektlokal.
- **CI-Gate-Parität:** Jede lokale Änderung an der Hash-Bindung muss serverseitig
  (`scripts/ci_spec_gate.py`) gespiegelt werden, sonst laufen lokaler Hook und CI-Gate auseinander —
  genau die Fehlerklasse aus #279 (zweite Wahrheiten driften).

## Analysis

### Type
Bug (Framework-Kernlogik, betrifft `agent-os-openspec` selbst und jedes Konsumenten-Projekt mit
aktivem PO-Briefing-Gate).

### Root Cause (bestätigt, mit Zeilenangaben — Stand `e4b7b6d`)
- `core/hooks/workflow.py:987-997` — `_check_po_briefing(data)` läuft für jede Vorwärts-Transition
  mit `tgt_idx >= PHASES.index("phase4_approved")`, trifft also auch `phase8_complete`.
- `core/hooks/workflow.py:908-916` — Schritt 6 der Prüfung blockt bei Hash-Abweichung mit
  „PO-Briefing ist veraltet — die Spec wurde nach dem Briefing geändert."
- `core/commands/60-validate.md:155-174` — Step 3 (docs-updater) steht vor Step 4
  (`phase phase8_complete`) und darf laut `core/agents/docs-updater.md:37`
  („Entity specs → `docs/specs/[type]/[entity_id].md`") die freigegebene Spec anfassen.
- Weder `60-validate.md` noch `docs-updater.md` enthalten eine explizite Anweisung, AC-Platzhalter
  zu ersetzen oder `status: implemented` zu setzen (per Grep verifiziert — kein Treffer) — trotzdem
  geschieht es in der Praxis (3 dokumentierte reale Vorfälle in den Issue-Kommentaren), weil es die
  naheliegende Interpretation von „aktualisiere betroffene Dokumentation" für eine Entity-Spec ist.
- `scripts/ci_spec_gate.py:255-264` prüft dieselbe Hash-Bindung serverseitig auf den committeten
  Dateien und enthält **keine** Prüfung von Status-Feldern oder AC-Checkboxen (per Grep verifiziert)
  → Weg 3 berührt diese Datei nicht.

### Technical Approach — Entscheidung

**Weg 3 aus dem Issue** (docs-updater fasst die freigegebene Spec nach `phase4_approved` nicht mehr
an), **zusätzlich technisch durchgesetzt** über einen neuen Check in `edit_gate.py` — Vorbild:
`claude_md_protection.py`, das eine andere Datei nach demselben Muster schützt. Bestehender
Override-Mechanismus (`"override"`-Schlüsselwort, 1h TTL) bleibt der Fluchtweg für den seltenen
Fall einer echten, gewollten Nachbesserung — kein neuer Mechanismus nötig.

Begründung:
1. Weg 1 (Reihenfolge tauschen) ist bereits im Issue-Verlauf widerlegt — verschiebt den Bruch nur
   zum teureren CI-Gate.
2. Weg 2 (Hash nur über inhaltlichen Teil) baut eine Ausnahme in die Prüfsummenbindung ein, die für
   immer begründen muss, welche Felder harmlos sind — Risiko einer stillen Lücke bei künftigen
   Spec-Feldern.
3. Weg 3 entfernt die Ursache statt sie abzufedern und berührt `workflow.py` /
   `ci_spec_gate.py` nicht.
4. Reine Dokumentations-Disziplin („docs-updater soll die Spec nicht anfassen") ist nach dem
   eigenen Grundsatz dieses Projekts („Das Framework erzwingt technisch, nicht nur durch
   Dokumentation", CLAUDE.md) genau die Fehlerklasse, die drei reale Vorfälle bereits erzeugt hat —
   obwohl bisher noch nicht einmal eine Instruktion dazu existierte. Ein Guard in `edit_gate.py`
   macht die Regel unumgehbar statt hoffnungsvoll.

**Abgewogene Alternative:** Nur die Dokumentations-Instruktion ändern (docs-updater.md +
60-validate.md + Template), ohne technischen Guard. Günstiger (kein Eingriff in Kernlogik, kein
neuer Test), aber ohne Durchsetzung nicht ausgeschlossen, dass eine künftige Session denselben
Fehler wiederholt — genau das Muster der drei bisherigen Vorfälle. Kippt keine bestehende ADR,
reine Aufwand-vs-Robustheit-Abwägung; als technische Entscheidung von Claude getroffen (Weg 3 +
Guard), nicht dem PO zur Wahl vorgelegt.

**Bewusst aus dem Scope genommen:** Die AC→Testname-Zuordnung, die bisher (unbeabsichtigt) in der
Spec landete, an anderer Stelle (z. B. `workflow.py write-log`) weiterzuführen. Würde eine 6. Datei
und zusätzliche Logik hinzufügen und den ±250-LoC-Rahmen strapazieren, ohne die Ursache des Bugs zu
berühren. Vorschlag für ein separates Issue, falls die Nachvollziehbarkeit vermisst wird.

### Affected Files
| File | Change Type | Description |
|------|-------------|-------------|
| `core/hooks/edit_gate.py` | MODIFY | Neuer Check: Edit/Write auf `spec_file` blockieren, sobald `current_phase`-Index `>= phase4_approved` (kein Override-Token registriert) |
| `core/agents/docs-updater.md` | MODIFY | „Entity specs" nicht mehr als Ziel nach Freigabe; explizite Regel gegen das Anfassen der freigegebenen Spec |
| `core/commands/60-validate.md` | MODIFY | Step 3: docs-updater-Auftrag ohne `spec_file_path` als Edit-Ziel |
| `docs/specs/_template.md` | MODIFY | Platzhalter „wird nach der TDD-RED-Phase eingetragen" entfernen/umformulieren — verspricht sonst eine Änderung, die der neue Guard verhindert |
| `tests/test_edit_gate_spec_freeze_230.py` (neu) | CREATE | Regressionstest: Edit auf `spec_file` ab `phase4_approved` blockiert, vor `phase4_approved` und mit Override-Token erlaubt |

### Scope Assessment
- Files: 5 (Scoping-Limit erreicht, nicht überschritten)
- Geschätzte LoC: +90/-15 (überwiegend Markdown-Text + ein kleiner Check in `edit_gate.py` + Tests)
- Risk Level: MEDIUM — Änderung an Kernlogik (`edit_gate.py`), wirkt in jedem Konsumenten-Projekt

### Dependencies
- Neuer Check muss sich in die bestehende Prüfreihenfolge in `edit_gate.py` einfügen (Protected
  State → Always-Allowed → Code-Check → Infra → Stop-Lock → Workflow → Phase → Override → TDD) und
  denselben Override-Token-Mechanismus nutzen wie die übrigen Checks dort.
- `docs/specs/_template.md`-Änderung wirkt erst auf künftig erzeugte Specs; bestehende Specs mit dem
  alten Platzhaltertext sind nicht betroffen (kein Blast Radius auf Altbestand).

### Open Questions
Keine — alle drei ursprünglich erwogenen Alternativen sind technische Entscheidungen im
Verantwortungsbereich von Claude (CLAUDE.md-Rollenregel), nicht PO-Themen. Entscheidung getroffen
und oben begründet.
