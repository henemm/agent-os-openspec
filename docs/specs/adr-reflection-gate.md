---
entity_id: adr-reflection-gate
type: feature
created: 2026-07-09
updated: 2026-07-09
status: draft
workflow: feat-63-adr-spec-gate
version: "1.0"
tags: [gate, adr, workflow, phase3, spec-approval]
---

# ADR-Reflexions-Gate (Spec-Freigabe, Phase 3→4)

## Approval

- [ ] Approved

## Purpose

Erzwingt bei der Spec-Freigabe (Phase 3→4), dass eine Spec bewusst über ihre Architektur-Relevanz
reflektiert: Die Sektion `## Architektur-Entscheidung (ADR)` muss ausgefüllt sein (ADR-Nummer **oder**
begründetes „keine"), bevor die Freigabe greift. Damit wird die ADR-Entscheidung nicht faktisch aufs
Commit-Gate verschoben und dort mit `[no-adr]` umgangen (Issue #63). Der Fix gehört ins Plugin-Core,
weil er alle Consumer betrifft.

## Source

- **File:** `core/hooks/workflow.py`
- **Identifier:** `def _check_adr` (neu) + `def _validate_transition` (erweitert)
- **File:** `core/hooks/phase_listener.py`
- **Identifier:** Approval-Block (aktuell Z. 225–236)

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `hook_utils.find_project_root` | module | Relativen `spec_file`-Pfad gegen Projekt-/Worktree-Root auflösen |
| `config_loader.load_config` | module | Kill-Switch `adr_gate.enabled` lesen |
| `workflow._check_adr` | function | Geteilter Helfer, aus `phase_listener.py` importiert (analog `_log_phase_transition`) |
| `re` | stdlib | Sektions-Extraktion, Platzhalter-Strip, Kriterium-Match |

## Scope

### Affected Files
| File | Change Type | Description |
|------|-------------|-------------|
| `core/hooks/workflow.py` | MODIFY | `_check_adr(data) -> str \| None`-Helfer + Aufruf in beiden `phase4_approved`-Blöcken von `_validate_transition` (standard + feature-fast) |
| `core/hooks/phase_listener.py` | MODIFY | ADR-Check im Approval-Block vor `spec_approved = True`, lenient-on-error |
| `core/agents/spec-writer.md` | MODIFY | ADR-Sektion ins emittierte Spec-Template + Ausfüll-Regel |
| `docs/specs/_template.md` | MODIFY | ADR-Sektion für manuelles Authoring |
| `core/agents/spec-validator.md` | MODIFY | ADR in „Required Sections" + Platzhalter-Erkennung |
| `config.yaml` | MODIFY | `adr_gate.enabled: true` (Kill-Switch) |
| `tests/test_adr_gate.py` | CREATE | Beide Pfade + Grandfathering + Platzhalter-Block |
| `CHANGELOG.md` | MODIFY | Eintrag unter [Unreleased] |

### Estimated Changes
- Files: 8
- LoC: +180/-5

## Implementation Details

### 1. Helfer `_check_adr(data) -> str | None` in `workflow.py`

Reine, testbare Funktion neben `_validate_transition`. Ablauf:

1. **Kill-Switch:** `load_config()` lesen; wenn `adr_gate.enabled` explizit `False` → `return None`.
   Fehlt der Key oder schlägt das Laden fehl → Default aktiv (nicht deaktivieren), aber lenient bei
   Exceptions (`return None` nur bei Config-`enabled: false`, nicht bei Ladefehler → Feature bleibt an).
2. **Spec-Pfad:** `spec_file` aus `data`; leer/None → `return None` (der bestehende `spec_file`-Gate
   deckt „nicht gesetzt" ab). Relativ auflösen: `find_project_root() / spec_file`.
3. **Lesen:** Datei nicht lesbar/existiert nicht → `return None` (lenient, Hook darf nie brechen).
4. **Sektion extrahieren:** Heading `## Architektur-Entscheidung (ADR)` **oder** `### …`
   (case-insensitive, Regex `^#{2,3}\s*Architektur-Entscheidung\s*\(ADR\)`) suchen, Body bis zum
   nächsten Heading beliebigen Rangs 1–3 (`(?=^#{1,3}\s|\Z)`) bzw. Dateiende — der Body endet an
   jedem Heading Rang 1–3, damit eine fremde `**ADR-Nr.:**`-Zeile unter einem späteren H1 (`# Anhang`)
   nicht in die Sektion leakt (F003). **Fehlt die Sektion →
   `return None`** (präsenzbasiertes Grandfathering: Alt-Specs/Consumer ohne ADR-Kultur bleiben
   unberührt).
5. **ADR-Nr.-Zeile extrahieren:** Aus dem Body NUR den Wert der `**ADR-Nr.:**`-Bullet-Zeile ziehen
   (`^\s*[-*]?\s*\*\*\s*ADR-Nr\.?\s*:?\s*\*\*\s*:?\s*(.*)$`, tolerant für Format-Varianten). Fehlt
   die kanonische `**ADR-Nr.:**`-Zeile ganz → als **nicht ausgefüllt** behandeln (blocken).
6. **Platzhalter entfernen + Kriterium (nur auf dem ADR-Nr.-Wert):** Aus dem captured Wert erst
   `re.sub(r"\[[^\]]*\]", "", value)` (Bracket-Spans raus), dann lowercased prüfen:
   `re.search(r"adr-\d+", v)` ODER `re.search(r"\bkeine\b|\bnone\b", v)`. Treffer → `return None`
   (ausgefüllt). Das Kriterium wird **ausschließlich** auf die `**ADR-Nr.:**`-Zeile angewandt, nie
   auf die freie `**Rationale:**`-Prosa (sonst würde ein zufälliges „keine"/„none" in der Rationale
   ein leeres ADR-Feld fälschlich durchlassen — F001).
7. Kein Treffer → `return` Fehlermeldung:
   `"Spec ohne ausgefülltes ADR-Feld — Sektion '## Architektur-Entscheidung (ADR)' braucht ADR-Nr. oder begründetes 'keine'."`

Warum Bracket-Strip zuerst: Der Template-Platzhalter `[ADR-NNNN oder "keine"]` enthält selbst „keine"
und das Muster „ADR-N…". Ohne vorheriges Entfernen würde der unausgefüllte Platzhalter fälschlich
als „ausgefüllt" gelten → Feature wirkungslos.

### 2. Einhängepunkt A — `_validate_transition` (workflow.py)

Im `phase4_approved`-Block **nach** dem `spec_approved`-Check, in beiden Pfaden:
- Standard-`feature` (nach der bestehenden `spec_approved`-Prüfung, aktuell Z. 437)
- `feature-fast` (nach der bestehenden `spec_approved`-Prüfung, aktuell Z. 415)

```
adr_err = _check_adr(data)
if adr_err:
    return adr_err
```

Deckt `cmd_phase` (workflow.py:603) und `cmd_complete` (:754) ab.

### 3. Einhängepunkt B — `phase_listener.py` Approval-Block

Vor `wf_data["spec_approved"] = True` (aktuell Z. 228), lenient-on-error (Hook wahrt Exit-0-Vertrag):

```
try:
    from workflow import _check_adr
    adr_err = _check_adr(wf_data)
except Exception:
    adr_err = None
if adr_err:
    print(f"Freigabe blockiert: {adr_err}", file=sys.stderr)
    # spec_approved NICHT setzen, current_phase bleibt phase3_spec
else:
    wf_data["spec_approved"] = True
    ... (bestehender Transition-Block)
```

„Soft-Block": Bei ADR-Fehler wird die Freigabe nicht gesetzt + stderr-Meldung. Der nachfolgende
`/40-tdd-red` (→ `cmd_phase` Ziel `phase5` > `phase4_approved`) blockt zusätzlich hart über
Einhängepunkt A (Defense-in-depth), ohne den Exit-0-Vertrag des Hooks zu verletzen.

### 4. ADR-Sektion in Template + Agenten

Kanonisches Format (aus gregor_zwanzig übernommen), in `spec-writer.md` (emittiertes Template) UND
`docs/specs/_template.md`:

```markdown
## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** [ADR-NNNN oder "keine"]
- **Rationale:** [kurz: warum diese Entscheidung bzw. warum keine nötig ist]
```

`spec-writer.md`: Regel ergänzen, dass der Agent ADR-Nr. **oder** begründetes „keine" einträgt (nie
den Platzhalter belassen). `spec-validator.md`: ADR in „Required Sections" + die bestehende
„No Placeholders"-Regel deckt den Bracket-Platzhalter ab (fängt leere ADR vor der Freigabe → bessere
UX als der harte Transition-Block).

### 5. config.yaml

Neuer Block analog `adversary_gate:`:

```yaml
# ADR Reflection Gate — enforce filled "## Architektur-Entscheidung (ADR)" at spec approval
# Used by workflow.py _check_adr (phase3→4). Set enabled: false to opt out.
adr_gate:
  enabled: true
```

## Test Plan

### Automated Tests (TDD RED)

Neue Datei `tests/test_adr_gate.py`, Muster wie `tests/test_gate_fixes_26_38_34.py` (`_run_phase`
Subprozess-Helper + Workflow-JSON-Fixture; echte tmp-Spec-Dateien, keine Mocks).

- [ ] Test 1 (Einhängepunkt A, block): GIVEN Workflow in phase4_approved-Anlauf mit Spec, deren
      ADR-Sektion nur den Platzhalter `[ADR-NNNN oder "keine"]` enthält, WHEN `workflow.py phase
      phase5_tdd_red`, THEN Exit ≠ 0 UND stderr enthält „ADR".
- [ ] Test 2 (Einhängepunkt A, block-missing-value): GIVEN Spec mit ADR-Sektion aber ohne ADR-Nr./
      „keine" (nur Rationale-Text), WHEN Phase-Transition Richtung phase5, THEN blockiert.
- [ ] Test 3 (pass, ADR-Nr.): GIVEN Spec mit `- **ADR-Nr.:** ADR-0001`, WHEN Phase-Transition,
      THEN Exit 0.
- [ ] Test 4 (pass, „keine"): GIVEN Spec mit `- **ADR-Nr.:** keine` + Rationale, WHEN Phase-
      Transition, THEN Exit 0.
- [ ] Test 5 (Grandfathering): GIVEN Spec **ohne** ADR-Sektion, WHEN Phase-Transition, THEN Exit 0
      (nicht blockiert).
- [ ] Test 6 (Kill-Switch): GIVEN `adr_gate.enabled: false` in config UND Spec mit Platzhalter-ADR,
      WHEN Phase-Transition, THEN Exit 0 (Gate deaktiviert).
- [ ] Test 7 (Einhängepunkt B — Approval-Pfad): GIVEN Spec mit Platzhalter-ADR in phase3_spec,
      WHEN `phase_listener.py` mit Approval-Keyword „approved", THEN `spec_approved` bleibt `False`
      UND stderr meldet die Blockade (Muster analog `tests/test_phase_listener_keyword_guard.py`).
- [ ] Test 8 (Einhängepunkt B — pass): GIVEN Spec mit ausgefülltem `keine`, WHEN Approval-Keyword,
      THEN `spec_approved` wird `True` UND current_phase → phase4_approved.
- [ ] Test 9 (F001-Regression, block): GIVEN Spec mit LEERER `- **ADR-Nr.:**`-Zeile UND einer
      Rationale, die zufällig „keine" enthält (z.B. „…betrifft keine Persistenz-Schicht"), WHEN
      Phase-Transition, THEN blockiert (Kriterium greift nur auf den ADR-Nr.-Wert, nicht die Prosa).
- [ ] Test 10 (F001-Regression, block): analog Test 9 mit englischem „none" in der Rationale →
      blockiert.
- [ ] Test 11 (F002-Regression, block): GIVEN Spec mit `###`-Heading (eine Ebene tiefer) und nur
      dem Platzhalter `[ADR-NNNN oder "keine"]` in der ADR-Nr.-Zeile, WHEN Phase-Transition, THEN
      blockiert (Heading-Regex erkennt `##` und `###`).
- [ ] Test 12 (F003-Regression, block): GIVEN ADR-Sektion OHNE ausgefüllte ADR-Nr.-Zeile (nur
      `- **Rationale:** keine.`), gefolgt von H1 `# Anhang` mit `- **ADR-Nr.:** ADR-9999` darunter,
      WHEN Phase-Transition, THEN blockiert — der Sektions-Body endet am H1 (`(?=^#{1,3}\s|\Z)`),
      die fremde ADR-Nr. leakt nicht in die Sektion.

## Acceptance Criteria

- **AC-1:** GIVEN eine Spec mit unausgefüllter ADR-Sektion (nur Platzhalter `[ADR-NNNN oder "keine"]`),
  WHEN die Phase-3→4-Transition über `workflow.py phase` versucht wird, THEN wird sie mit einer
  ADR-Fehlermeldung blockiert (Exit ≠ 0).
- **AC-2:** GIVEN eine Spec mit ausgefülltem ADR-Feld (`ADR-0001` **oder** begründetes `keine`),
  WHEN die Phase-3→4-Transition versucht wird, THEN ist sie erlaubt (Exit 0).
- **AC-3:** GIVEN eine Spec mit unausgefüllter ADR-Sektion in `phase3_spec`, WHEN der User im
  `phase_listener.py`-Pfad ein Approval-Keyword sendet, THEN wird `spec_approved` NICHT gesetzt und
  eine Blockade-Meldung auf stderr ausgegeben (der reale Approval-Pfad ist ebenfalls abgesichert).
- **AC-4:** GIVEN eine bestehende Spec **ohne** ADR-Sektion, WHEN eine Phase-Transition versucht
  wird, THEN wird sie NICHT durch das ADR-Gate blockiert (präsenzbasiertes Grandfathering).
- **AC-5:** GIVEN `adr_gate.enabled: false` in der Config, WHEN eine Spec mit unausgefüllter
  ADR-Sektion die Transition versucht, THEN greift das Gate nicht (Consumer-Opt-out).
- **AC-6:** GIVEN das aktualisierte Framework, WHEN eine neue Spec über den `spec-writer`-Flow
  erzeugt wird, THEN enthält sie die Sektion `## Architektur-Entscheidung (ADR)` mit den zwei
  Bullets (ADR-Nr. + Rationale) — das Framework blockiert sich nicht selbst.

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Das Feature fügt einen weiteren Gate-Check in das bereits etablierte kumulative
  Schwellen-Muster von `_validate_transition` ein und nutzt den vorhandenen Approval-Einhängepunkt
  in `phase_listener.py` — keine neue Architektur, sondern konsequente Fortführung der bestehenden
  Gate-Kultur. Es existiert im Framework-Repo (noch) keine `docs/adr/`-Registry; eine ADR-Nummer
  wäre daher gegenstandslos. Dies ist zugleich das erste bewusste „keine"-Beispiel für das neue Feld.

## Known Limitations

- Das Gate greift nur für Arbeit im 8-Phasen-Workflow (Spec-Freigabe). Ad-hoc-Änderungen ohne
  Workflow werden hier nicht erfasst — das ist Aufgabe eines separaten Commit-Gates (Stufe 2, im
  Framework-Core nicht Teil dieses Issues).
- Präsenzbasiertes Grandfathering bedeutet: Löscht jemand die ADR-Sektion bewusst aus einer Spec,
  greift das Gate nicht. Das ist ein bewusster Akt und wird durch `spec-validator` (Required
  Sections) vor der Freigabe abgefangen.
- Der Einhängepunkt B in `phase_listener.py` ist ein Soft-Block (Exit-0-Vertrag). Die harte
  Durchsetzung kommt aus der Kombination mit Einhängepunkt A beim nächsten `cmd_phase`.
- Ein ADR-Heading mit Zusatz-Suffix (z.B. `## Architektur-Entscheidung (ADR) - Draft`) matcht das
  Heading-Regex nicht und wird still grandfathered (F004, LOW). Das kanonische Template emittiert
  immer die exakte Überschrift; abweichende Hand-Überschriften sind ein bewusster Autor-Akt.

## Changelog

- 2026-07-09: Initial spec created (Issue #63)
- 2026-07-09: Adversary-Runden — Kriterium auf ADR-Nr.-Zeile beschränkt (F001), `###`-Heading (F002)
  und H1-Sektions-Leak (F003) behoben; Tests 9–12 ergänzt.
