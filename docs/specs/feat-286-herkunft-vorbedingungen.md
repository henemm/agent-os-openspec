---
entity_id: feat-286-herkunft-vorbedingungen
type: feature
created: 2026-09-30
updated: 2026-09-30
status: draft
version: "1.0"
tags: [adversary, precondition-origins, gate, config, epic-273]
test_targets: ["tests/test_precondition_section_gate.py"]
---

# Herkunft der Vorbedingungen zur Pflichtsektion des Prüfprotokolls machen (#286)

## Approval

- [ ] Approved

## GitHub Issue

- **Issue:** #286 — „Herkunft von Testvorbedingungen im Prüfprotokoll verpflichtend machen
  (Scheibe 2 von #273)". Epic: #273 („Prüfkette belegt Korrektheit, nicht Erreichbarkeit").
  Schnitt und Reihenfolge (T1 vor T2) festgelegt in
  `docs/context/feat-273-erreichbarkeitspruefung.md`, Abschnitt „Schnittvorschlag — sechs
  Teilvorgänge", T2. Voraussetzungen (#285 Werkzeug, #278 Protokollformat) sind beide gemergt.

## Purpose

Das Werkzeug aus #285 (`core/hooks/precondition_origins.py`) liest maschinell aus, welche
Modellfelder ein Test per Zuweisung herstellt und wie oft dasselbe Feld im Produktivcode
tatsächlich geschrieben wird — aber ruft bisher niemand auf. Diese Scheibe macht die daraus
entstehende Tabelle zu einer Pflichtsektion `## Herkunft der Vorbedingungen` im
Adversary-Prüfprotokoll, nach demselben Muster, mit dem `## Geprüfte Dateien` (#131/#253)
bereits erzwungen wird, und verlangt vom menschlichen bzw. Adversary-Prüfer zusätzlich für jede
auffällige Zeile (höchstens eine Produktions-Schreibstelle) zwei Angaben: unter welcher
Bedingung der Produktivcode das Feld schreibt, und ob ein Test genau diesen Weg auslöst — nicht
nur das Ergebnis.

## Source

- **File:** `core/hooks/adversary_dialog.py`
  **Identifier:** neu `_parse_precondition_section()`, `_is_suspect_row()`,
  `_verify_precondition_section()`; geändert `validate_dialog_artifact_ex()` (neuer Prüfschritt),
  `scaffold_dialog_artifact()` (neuer Platzhalter-Abschnitt)
- **File:** `config.yaml`
  **Identifier:** neuer Block `precondition_section_gate`, neues Feld
  `precondition_origins.default_lang`

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `core/hooks/precondition_origins.py` (#285) | script | Liefert die Tabelle (`Feld \| Test-Zuweisungen \| Produktions-Schreibstellen \| Bedingung davor \| Test für diesen Weg`), die diese Sektion trägt — unverändert wiederverwendet |
| `validate_dialog_artifact_ex()` (`core/hooks/adversary_dialog.py:420`) | function | Einhängepunkt für den neuen Prüfschritt, nach der bestehenden Datei-Hash-Verifikation |
| `scaffold_dialog_artifact()` (`core/hooks/adversary_dialog.py:1049`) | function | Muss den neuen Platzhalter mitrendern, sonst driftet Gerüst und Gate wieder auseinander (#278-Lehre) |
| `config_loader.load_config()` | function | Liest `precondition_section_gate` und `precondition_origins.default_lang` aus der Projekt-`config.yaml` |
| `resolve_active_workflow()` (bereits in `adversary_dialog.py` importiert, siehe `_persist_adversary_metrics`) | function | Ermittelt `workflow_type` für die Fast-Track-Ausnahme (`skip_fast_track`) |
| `core/commands/50-implement.md` Step 8a | doc | Orchestrierung: bedingter Aufruf von `precondition_origins.py`, Auftragserweiterung an den Adversary-Agenten |
| `core/agents/implementation-validator.md` | doc | Neuer Pflichtabschnitt im Berichtsformat, analog „Structured Findings" |
| `skills/50-implement/SKILL.md` | generated | Spiegel von `core/commands/50-implement.md`, via `scripts/sync_skills.py` |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|--------------|
| `core/hooks/adversary_dialog.py` | MODIFY | Drei neue Funktionen, Einhängung in `validate_dialog_artifact_ex()` (Kill-Switch-gesteuert), Erweiterung von `scaffold_dialog_artifact()` um den Platzhalter |
| `core/commands/50-implement.md` | MODIFY | Step 8a: bedingter Aufruf von `precondition_origins.py`, Auftragserweiterung an den Adversary-Agenten |
| `core/agents/implementation-validator.md` | MODIFY | Neuer Pflichtabschnitt „Herkunft der Vorbedingungen" im Berichtsformat |
| `config.yaml` | MODIFY | Neuer Block `precondition_section_gate` (enabled/mode/skip_fast_track) + `precondition_origins.default_lang` (optional) |
| `skills/50-implement/SKILL.md` | GENERATED | `python3 scripts/sync_skills.py` nach der `.md`-Änderung, nicht von Hand |
| `tests/test_precondition_section_gate.py` | CREATE | Alle Acceptance Criteria unten |
| `CHANGELOG.md` | MODIFY | Eintrag unter `[Unreleased]` |

### Estimated Changes

- Files: 5 handgeschriebene Produktivdateien (`adversary_dialog.py`, `50-implement.md`,
  `implementation-validator.md`, `config.yaml`, `CHANGELOG.md`) — an der Hausgrenze (max. 4-5),
  nicht darüber.
- LoC: +180/-10 (drei Funktionen + Einhängung + Scaffold-Ergänzung ~95, Doku-Ergänzungen zwei
  `.md`-Dateien ~40, Config-Block ~15, CHANGELOG ~10) — innerhalb ±250.
- Test-Fixtures: `tests/fixtures/precondition_origins/{swift,python}/` aus #285 werden
  **wiederverwendet**, nicht neu angelegt (enthalten bereits eine bekannte
  Verdachtsgruppen-Zeile: `processedAt`/`processed_at`, 1 Produktions-Schreibstelle).

## Implementation Details

**1. Neue Sektion `## Herkunft der Vorbedingungen`** — Bausteine analog `## Geprüfte Dateien`,
aber OHNE Hash-Bindung (die Sektion enthält keine Dateiinhalte, nur eine Werkzeug-Tabelle plus
Prüfer-Prosa):

```python
def _parse_precondition_section(scan: str) -> "list[dict] | None":
    """Letzte '## Herkunft der Vorbedingungen'-Sektion, oder None wenn sie fehlt.
    Enthaelt die Sektion nur den Hinweistext (kein Sprachprofil / keine
    Modelldateien), liefert die Funktion [] (Sektion vorhanden, 0 Zeilen).
    Sonst je Tabellenzeile ein dict:
    {field, test_refs, prod_refs, condition, test_for_path}."""

def _is_suspect_row(row: dict) -> bool:
    """Verdachtsgruppe: hoechstens 1 Produktions-Schreibstelle in row['prod_refs']
    (dieselbe Schwelle wie #285 AC-7: 0 oder 1 <br>-getrennte Fundstelle,
    bzw. der '0 — keine Schreibstelle'-Marker)."""

def _verify_precondition_section(scan: str) -> "tuple[bool, str, str | None]":
    """None (Sektion fehlt) -> (False, msg, 'format').
    Vorhanden, aber eine Verdachtsgruppen-Zeile ohne 'Bedingung davor' ODER
    'Test fuer diesen Weg' -> (False, msg, 'content').
    Sonst (auch bei 0 Verdachtsgruppen-Zeilen bzw. Hinweistext statt Tabelle)
    -> (True, msg, None)."""
```

Einhängung in `validate_dialog_artifact_ex()` als neuer Schritt nach der bestehenden
Datei-Hash-Verifikation (Schritt 5, endet aktuell ~Zeile 518), vor der abschließenden
VERIFIED/AMBIGUOUS-Rückgabe:

```python
gate = load_config().get("precondition_section_gate", {})
if gate.get("enabled", True):
    skip = gate.get("skip_fast_track", True) and _active_workflow_is_fast_track()
    if not skip:
        ok, p_msg, p_kind = _verify_precondition_section(scan)
        if not ok:
            if gate.get("mode", "warn") == "block":
                return False, p_msg, p_kind
            print(f"WARNUNG (precondition_section_gate, mode=warn): {p_msg}", file=sys.stderr)
```

`_active_workflow_is_fast_track()` liest `workflow_type` über `resolve_active_workflow()` /
den Workflow-State (dasselbe Muster wie `_persist_adversary_metrics()`) und prüft gegen
`("bug", "feature-fast")` — identisch zur bestehenden Fast-Track-Liste in `bash_gate.py`/
`workflow.py`. Kein aktiver Workflow oder nicht lesbarer State → gilt NICHT als Fast Track
(fail-closed: die Prüfung läuft im Zweifel).

**2. Orchestrierung in `core/commands/50-implement.md` Step 8a** (Spiegel: `skills/50-implement/
SKILL.md`, via `sync_skills.py`): direkt nach dem bestehenden `scaffold`-Aufruf, wenn
`precondition_origins.default_lang` in der Projekt-`config.yaml` gesetzt ist:

```bash
python3 .claude/hooks/precondition_origins.py --lang <default_lang> --root .
```

Die Ausgabe wird dem `implementation-validator`-Auftrag beigelegt (wie die Checkliste aus
`parse` bereits heute). Ist `default_lang` nicht gesetzt, entfällt der Aufruf; der Agent
schreibt stattdessen den Hinweistext „kein Sprachprofil konfiguriert
(`precondition_origins.default_lang`)" in die Sektion — das gilt als vollständig (kein
Format-Fehler, 0 Verdachtsgruppen-Zeilen).

**3. Zweistufiger Kill-Switch** (`config.yaml`, neuer Block):

```yaml
precondition_section_gate:
  enabled: true
  # warn: Sektion fehlt/unvollstaendig -> Warnung (stderr), Gate blockt NICHT.
  # block: wie jede andere Format-/Content-Pruefung -> blockt Commit/Phase 8.
  mode: warn
  skip_fast_track: true   # Fast Track hat ohnehin keinen Adversary-Dialog — informativ
```

Fehlt der Block komplett in der `config.yaml` eines installierten Projekts (bestehende
Installation ohne Update), gelten dieselben Defaults (`enabled: true, mode: warn,
skip_fast_track: true`) — ein Update blockt also nirgends sofort hart, sondern warnt zuerst.

**4. `precondition_origins.default_lang`** (neues optionales Feld unter dem bestehenden
`precondition_origins`-Block, Projekt-`config.yaml`, nicht `modules/*/config.yaml` — dieselbe
Einschränkung wie bei `observable_surface.surface_patterns`):

```yaml
precondition_origins:
  default_lang: swift   # optional; fehlt es, ruft der Orchestrator das Werkzeug nicht auf
  profiles:
    swift: { ... }       # unveraendert aus #285
```

**5. `scaffold_dialog_artifact()` (#278) ergänzen** um einen leeren Platzhalter, positioniert
nach den `### Runde N`-Köpfen und vor `## Verdict` (analog zur Positionierung von „Structured
Findings" im Berichtsformat des Adversary-Agenten):

```python
lines += [
    "## Herkunft der Vorbedingungen", "",
    "<!-- vom Prüfer auszufüllen, siehe `precondition_origins.py` -->", "",
]
lines += ["## Verdict", ""]
```

**6. `core/agents/implementation-validator.md`** — neuer Pflichtabschnitt analog „Structured
Findings": Anleitung, die vom Orchestrator beigelegte Tabelle (oder den Hinweistext bei
fehlendem `default_lang`) in die Sektion zu übernehmen und für jede Verdachtsgruppen-Zeile
(höchstens eine Produktions-Schreibstelle) „Bedingung davor" (unter welcher Bedingung schreibt
der Produktivcode das Feld) und „Test für diesen Weg" (existiert ein Test, der GENAU diesen Weg
— nicht nur das Ergebnis — auslöst) auszufüllen.

## Expected Behavior

- **Input:** Ein Dialog-Artefakt (Markdown) mit oder ohne `## Herkunft der Vorbedingungen`;
  `precondition_section_gate`-Konfiguration (enabled/mode/skip_fast_track); der aktive
  Workflow-State (für die Fast-Track-Ausnahme).
- **Output:** `validate_dialog_artifact_ex()` liefert wie bisher `(valid, message,
  failure_kind)` — bei `mode: block` blockt eine fehlende/unvollständige Sektion zusätzlich zu
  den bisherigen Prüfungen; bei `mode: warn` bleibt das Ergebnis unverändert gültig, zusätzlich
  eine Warnzeile auf stderr. `scaffold_dialog_artifact()` liefert zusätzlich den neuen
  Platzhalter-Abschnitt.
- **Side effects:** Keine neuen Schreibzugriffe — die Prüfung liest nur; `scaffold` schreibt wie
  bisher nur auf stdout (der Aufrufer leitet in die Datei um).

## Error Handling

- `config.yaml` fehlt der Block `precondition_section_gate` ganz → Defaults greifen
  (`enabled: true, mode: warn, skip_fast_track: true`), kein Absturz.
- `config.yaml`-Werte ungültig (z. B. `mode: "strict"` statt `warn`/`block`) → wird wie `warn`
  behandelt (konservativ, fail-open in Richtung „blockt nicht grundlos").
- Workflow-State nicht lesbar oder kein aktiver Workflow beim Fast-Track-Check → gilt NICHT als
  Fast Track, die Prüfung läuft (fail-closed für die Prüfung selbst, nicht für den Commit —
  `mode: warn` bleibt die Absicherung).
- Tabellenzeile mit fehlerhaftem Spaltenformat (z. B. zu wenige `|`-Trenner) → wird beim Parsen
  übersprungen, keine KeyError/Exception; eine übersprungene Zeile zählt nicht als geprüft und
  kann daher indirekt den „unvollständig"-Fall auslösen, wenn sie eine Verdachtszeile war.

## Known Limitations

- **Keine Hash-Bindung.** Ein Prüfer könnte plausible, aber erfundene „Bedingung davor"-Prosa
  eintragen, ohne dass das Gate es erkennt. Dasselbe Risiko besteht heute bereits bei der
  AC-Checkliste selbst (auch nicht hash-gebunden) — kein neues Muster, keine
  Sonderbehandlung.
- **Dieses Repo selbst (`agent-os-openspec`) hat keine `model_globs`-Treffer.** Es ist ein reines
  Python-Hook-Repo ohne Modellschicht im Sinne von #285. Die neue Pflichtsektion wird für
  **eigene** Workflows dieses Repos also fast immer trivial erfüllt sein (Hinweistext „keine
  Modelldateien gefunden", keine Verdachtsgruppen-Zeilen, kein Format-/Content-Fehler möglich).
  Die eigentliche Wirkung entfaltet sich erst in Konsumenten-Projekten mit echter Modellschicht
  (z. B. das iOS/SwiftUI-Modul). Die Acceptance Criteria dieser Spec, die die Content-Prüfung
  beweisen, laufen deshalb gegen die wiederverwendeten `tests/fixtures/precondition_origins/`
  aus #285, nicht gegen den eigenen Projektstand.
- **`mode: warn` ist keine dauerhafte Empfehlung, nur die Einführungsstufe.** Ob und wann ein
  Projekt auf `mode: block` umstellt, ist eine spätere PO-Entscheidung dieses bzw. eines
  Konsumenten-Projekts, nicht Teil dieser Spec.
- **Der Fast-Track-Check ist informativ, keine echte Zusatzlogik.** Fast-Track-Workflows
  (`bug`, `feature-fast`) durchlaufen den Adversary-Dialog heute ohnehin nicht (siehe
  `bash_gate.py` 5c-Ausnahme) — `skip_fast_track` verhindert lediglich, dass ein
  handgeschriebenes oder nachträglich gestempeltes Fast-Track-Artefakt an dieser neuen Sektion
  scheitert, falls doch einmal `validate_dialog_artifact_ex()` darauf läuft.

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] `python3 scripts/sync_skills.py --check` meldet keine Drift (SKILL.md nachgezogen)
- [ ] `CHANGELOG.md` hat einen `[Unreleased]`-Eintrag für #286
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf grün, insbesondere
      `tests/test_adversary_dialog_hash_binding_131.py`,
      `tests/test_adversary_coverage_gate_259.py`,
      `tests/test_adversary_evidence_gate_253.py`,
      `tests/test_adversary_protokoll_format_278.py`)

## Acceptance Criteria

- **AC-1:** Given ein Dialog-Artefakt ohne jede `## Herkunft der Vorbedingungen`-Sektion, sonst
  vollständig (Checkliste abgehakt, ≥2 Runden, `VERDICT: VERIFIED`, gültiger Hash-Block),
  `precondition_section_gate: { enabled: true, mode: block }` / When
  `validate_dialog_artifact_ex()` läuft / Then Exit/Ergebnis `valid=False`,
  `failure_kind='format'` — kein VERIFIED trotz sonst vollständigem Artefakt.
  - Test: `test_precondition_section_gate.py::test_ac1_missing_section_is_format_failure`

- **AC-2:** Given dasselbe Artefakt mit vorhandener Sektion und einer Tabelle (aus den
  #285-Fixtures), in der JEDE Verdachtsgruppen-Zeile (≤1 Produktions-Schreibstelle) sowohl
  „Bedingung davor" als auch „Test für diesen Weg" ausgefüllt hat, `mode: block` / When
  `validate_dialog_artifact_ex()` läuft / Then `valid=True` — die neue Sektion blockt nicht.
  - Test: `test_precondition_section_gate.py::test_ac2_complete_suspect_rows_pass`

- **AC-3:** Given dieselbe Tabelle, aber genau eine Verdachtsgruppen-Zeile (≤1
  Produktions-Schreibstelle) ohne „Bedingung davor" ODER ohne „Test für diesen Weg", `mode:
  block` / When `validate_dialog_artifact_ex()` läuft / Then `valid=False`,
  `failure_kind='content'` — dasselbe BROKEN-würdige Verhalten wie ein offener
  Checklisten-Punkt.
  - Test: `test_precondition_section_gate.py::test_ac3_incomplete_suspect_row_is_content_failure`

- **AC-4:** Given je einmal den Fall aus AC-1 (Sektion fehlt) und AC-3 (Zeile unvollständig),
  jeweils mit `mode: warn` / When `validate_dialog_artifact_ex()` läuft / Then `valid=True`
  (blockt NICHT), zusätzlich erscheint eine Warnzeile auf stderr, die den Grund nennt.
  - Test: `test_precondition_section_gate.py::test_ac4_warn_mode_missing_section_passes_with_stderr_warning`,
    `test_precondition_section_gate.py::test_ac4_warn_mode_incomplete_row_passes_with_stderr_warning`

- **AC-5:** Given dieselben zwei Fälle mit `mode: block` / When `validate_dialog_artifact_ex()`
  läuft / Then `valid=False` mit dem jeweiligen `failure_kind` (`format`/`content`) — die neue
  Sektion verhält sich unter `block` wie jede andere Format-/Content-Prüfung in dieser Funktion.
  - Test: `test_precondition_section_gate.py::test_ac5_block_mode_missing_section_fails_format`,
    `test_precondition_section_gate.py::test_ac5_block_mode_incomplete_row_fails_content`

- **AC-6:** Given den Fall aus AC-1 (Sektion fehlt) mit `precondition_section_gate: { enabled:
  false }` / When `validate_dialog_artifact_ex()` läuft / Then `valid=True`, keine Warnzeile auf
  stderr — die Prüfung ist vollständig deaktiviert, nicht nur stumm geschaltet.
  - Test: `test_precondition_section_gate.py::test_ac6_disabled_gate_skips_check_no_warning_no_block`

- **AC-7:** Given ein Artefakt mit vorhandener Sektion, deren Inhalt NUR der Hinweistext „kein
  Sprachprofil konfiguriert (`precondition_origins.default_lang`)" ist (keine Tabelle), `mode:
  block` / When `validate_dialog_artifact_ex()` läuft / Then `valid=True` — der Hinweistext
  zählt als vollständig (0 Verdachtsgruppen-Zeilen).
  - Test: `test_precondition_section_gate.py::test_ac7_hint_text_without_default_lang_counts_as_complete`

- **AC-8:** Given einen Workflow-Namen und einen Spec-Pfad / When
  `scaffold_dialog_artifact(workflow_name, spec_path)` läuft / Then enthält die Ausgabe eine
  `## Herkunft der Vorbedingungen`-Überschrift mit dem Platzhalter-Kommentar, positioniert nach
  den `### Runde N`-Köpfen und vor `## Verdict`.
  - Test: `test_precondition_section_gate.py::test_ac8_scaffold_renders_precondition_placeholder_section`

- **AC-9:** Given ein Workflow mit `workflow_type: "bug"` bzw. `"feature-fast"` und ein Artefakt
  ohne `## Herkunft der Vorbedingungen`-Sektion, `precondition_section_gate: { enabled: true,
  mode: block, skip_fast_track: true }` / When `validate_dialog_artifact_ex()` läuft / Then
  `valid=True` — die neue Prüfung wird für Fast-Track-Workflows übersprungen, unabhängig von
  `mode`.
  - Test: `test_precondition_section_gate.py::test_ac9_fast_track_workflow_skips_section_check`

- **AC-10:** Given `core/commands/50-implement.md` und `core/agents/implementation-validator.md`
  / When man die Dateien liest / Then nennt `50-implement.md` in Step 8a den bedingten Aufruf von
  `precondition_origins.py` UND `implementation-validator.md` nennt in seinem Pflichtabschnitt
  die Sektion `## Herkunft der Vorbedingungen` wörtlich — nach demselben Doku-Prüfmuster wie
  `test_ac16_docs_describe_coverage_gate` (#259) bzw.
  `test_docs_reference_scaffold_and_keep_required_files_mentions` (#278). Die bestehenden
  `scaffold`- und `required-files`-Erwähnungen in den von #259/#278 geprüften Abschnitten bleiben
  dabei unverändert vorhanden (reiner Regressionsschutz, keine neue Prüfung dafür nötig — die
  Tests aus #259/#278 laufen im Regressionslauf ohnehin mit).
  - Test: `test_precondition_section_gate.py::test_ac10_docs_mention_precondition_section_duty`

- **AC-11:** Given ein Dialog-Artefakt, das GLEICHZEITIG zwei Defekte trägt — einen offenen
  Checklistenpunkt (`- [ ]` statt `- [x]`) UND eine fehlende `## Herkunft der
  Vorbedingungen`-Sektion —, `mode: block` / When `validate_dialog_artifact_ex()` läuft / Then
  liefert die Funktion `failure_kind='content'` (vom bestehenden Checklisten-Schritt, der VOR dem
  neuen Sektions-Schritt läuft) — NICHT `'format'` vom neuen Schritt. Beweist, dass die
  #77-Reihenfolge (Inhaltsfehler vor Formfehler) durch die reine Platzierung des neuen Schritts
  als letzten in der Funktion erhalten bleibt, auch wenn beide Defekte gleichzeitig vorliegen.
  - Test: `test_precondition_section_gate.py::test_ac11_mixed_defect_content_wins_over_new_format_check`

- **AC-12:** Given ein vollständiges, gestempeltes Dialog-Artefakt OHNE die neue Sektion,
  registriert für einen aktiven Workflow in einem echten Git-Repo, `precondition_section_gate: {
  enabled: true, mode: block }` / When (a) `bash_gate.py` einen `git commit` prüft UND (b)
  `workflow.py phase phase8_complete` (bzw. `complete`/`finish`) läuft — beides End-zu-Ende über
  die echten Hook-Skripte, Muster wie `tests/test_adversary_coverage_gate_259.py::_run`/
  `_make_repo` / Then (a) Exit 2 beim Commit UND (b) `BLOCKED: …` bei Exit ≠ 0 beim
  Phasenübergang — beide blocken, weil `check_dialog_evidence()` über
  `validate_dialog_artifact_ex()` denselben neuen Prüfschritt durchläuft, ohne dass `bash_gate.py`
  oder `workflow.py` selbst geändert werden. Mit vollständiger Sektion (alle
  Verdachtsgruppen-Zeilen ausgefüllt) laufen beide Wege mit Erfolg durch.
  - Test: `test_precondition_section_gate.py::test_ac12_commit_gate_blocks_and_allows_via_inherited_check`,
    `test_precondition_section_gate.py::test_ac12b_phase8_transition_blocks_and_allows_via_inherited_check`

## Test Plan

Automatische Tests (jeweils an eine AC oben gebunden):
- `python3 -m pytest tests/test_precondition_section_gate.py -q` (AC-1 bis AC-12)
- Regressionslauf: `python3 -m pytest tests/ -q` (insbesondere
  `tests/test_adversary_dialog_hash_binding_131.py`,
  `tests/test_adversary_coverage_gate_259.py`,
  `tests/test_adversary_evidence_gate_253.py`,
  `tests/test_adversary_protokoll_format_278.py`)
- Drift-Check: `python3 scripts/sync_skills.py --check`

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Kein neues Architektur-Muster — drei bewusste Festlegungen, je mit einer
  erwogenen und verworfenen Alternative:

  1. **Keine Hash-Bindung für die neue Sektion.** Erwogene Alternative: dasselbe
     Hash-Bindungs-Muster wie `## Geprüfte Dateien` (#131) — jede in der Tabelle referenzierte
     Fundstelle zusätzlich als SHA-256 binden. Verworfen, weil die Sektion keine Dateiinhalte
     enthält, sondern eine vom Werkzeug erzeugte Tabelle plus Prüfer-Prosa in zwei Spalten; eine
     Hash-Bindung würde nicht den Inhalt der Prosa schützen (die bleibt ungeprüft, siehe „Known
     Limitations"), nur die referenzierten Code-Zeilen — das leistet die bereits bestehende
     `## Geprüfte Dateien`-Prüfung an denselben Dateien schon, eine zweite Bindung auf dieselben
     Pfade wäre redundant. Kosten des gewählten Wegs: die „Bedingung davor"/„Test für diesen
     Weg"-Prosa selbst bleibt ungeprüft fälschbar — dasselbe Restrisiko wie bei der
     AC-Checkliste.

  2. **`mode: warn|block`-Schalter statt Versionsbindung.** Die Epic-Analyse (#273) skizzierte
     ursprünglich „ab Framework-Version X block". Verworfen, weil das voraussetzt, dass jedes
     installierte Projekt seine Framework-Version korrekt und zeitnah meldet, und der Schalter
     dadurch indirekt und schwerer nachvollziehbar wird als ein Wort, das der PO eines Projekts
     selbst umstellt. Ein explizites `mode:`-Feld ist direkter und entspricht dem bereits
     etablierten Ein-Wort-Kill-Switch-Stil dieses Repos (`po_briefing_gate.enabled`,
     `adversary_coverage_gate.enabled`) — hier zweistufig statt einstufig, weil eine unbedingte
     neue Pflicht jeden Abschluss in jedem angebundenen Projekt sofort blockieren würde, ohne
     eine Übergangsstufe zu erlauben.

  3. **`precondition_origins.default_lang` als explizites optionales Config-Feld statt
     Auto-Detect.** Erwogene Alternative: das Sprachprofil aus den im Repo vorhandenen
     Dateiendungen ableiten (z. B. „überwiegend `.swift`-Dateien → `swift`"). Verworfen, weil
     #285 bereits bewusst entschieden hat, dass `--lang` am CLI ohne Auto-Detect Pflicht ist
     (siehe `docs/specs/feat-285-precondition-origins.md`, ADR-Punkt „Sprachprofil aus explizitem
     `--lang`"); ein impliziter Auto-Detect an dieser Stelle würde diese Entscheidung über einen
     Umweg wieder einführen und in einem mehrsprachigen Projekt (z. B. Swift-App mit
     Python-Tooling) falsch raten können. Ein explizites, vom PO gesetztes Feld bleibt
     deterministisch und macht sichtbar, dass die Prüfung (noch) nicht konfiguriert ist — der
     Hinweistext statt einer stillen Falschauswahl.

## Changelog

- 2026-09-30: Initial spec created
- 2026-09-30: AC-10 ergänzt (Doku-Inhaltsprüfung: beide Anleitungstexte müssen die Pflicht
  tatsächlich nennen, nicht nur der Scaffold-Renderer) — Lücke aus dem unabhängigen PO-Briefing
  vor der Freigabe geschlossen
- 2026-09-30: AC-11 (gemischter Defekt: #77-Reihenfolge bleibt auch mit zwei gleichzeitigen
  Fehlern erhalten) und AC-12 (Ende-zu-Ende-Nachweis, dass das Commit-Gate den neuen Prüfschritt
  über den bestehenden Aufrufpfad erbt, ohne `bash_gate.py` zu ändern) ergänzt — zweite Runde des
  unabhängigen PO-Briefings
- 2026-09-30: AC-12 um den `phase8_complete`-Übergang erweitert (Issue-AC-4 verlangt wörtlich
  Commit-Gate UND Phase-8-Übergang; bisher war nur der Commit-Weg end-to-end geprüft) — dritte,
  finale Runde des unabhängigen PO-Briefings
