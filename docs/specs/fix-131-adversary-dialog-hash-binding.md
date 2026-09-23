---
entity_id: fix-131-adversary-dialog-hash-binding
type: module
created: 2026-09-23
updated: 2026-09-23
status: draft
version: "1.0"
tags: [adversary, gate, hash, worktree]
test_targets: ["tests/test_adversary_dialog_hash_binding_131.py"]
---

# Adversary Dialog: Hash-Bindung statt Alters-Frist

## Approval

- [x] Approved

## GitHub Issue

- **Issue:** #131

## Purpose

`adversary_dialog.py` bindet die Gültigkeit eines Dialog-Protokolls heute an
die Datei-`mtime` (`MAX_AGE_MINUTES = 60`). Das ist ein grober Stellvertreter
für die eigentliche Frage — "wurde der geprüfte Code seither verändert?" —
und irrt in beide Richtungen: gültige, aber über Nacht liegen gebliebene
Protokolle werden blockiert (Falsch-negativ), und Code, der innerhalb der
Frist nach dem Dialog noch geändert wurde, wird unsichtbar durchgewunken
(Falsch-positiv, die gefährlichere Richtung). Diese Spec ersetzt die
Uhr durch eine Identitätsprüfung: das Protokoll trägt SHA-256-Prüfsummen der
untersuchten Dateien, das Gate vergleicht sie beim Validieren mit dem
Ist-Stand im Arbeitsbaum.

## Source

- **File:** `core/hooks/adversary_dialog.py`
- **Identifier:** `validate_dialog_artifact_ex`, neu: `stamp_dialog_artifact`

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `hook_utils.find_worktree_root` | function | Worktree-eigener Pfad-Root für Hash-Vergleich (statt geteiltem Haupt-Repo) |
| `hook_utils.find_project_root` | function | Fallback-Root ausserhalb eines Worktrees |
| `core/agents/implementation-validator.md` | agent | Muss `stamp` nach dem Schreiben des Protokolls aufrufen |
| `core/commands/50-implement.md` | command | Dokumentiert den `stamp`-Aufruf in Step 8c |
| `core/hooks/qa_gate.py` | hook | Ruft `validate_dialog_artifact_ex` unverändert mit einem Argument auf — Signatur bleibt kompatibel |

## Scope

- **Affected Files:** `core/hooks/adversary_dialog.py`, `core/agents/implementation-validator.md`, `core/commands/50-implement.md` (Quelle — `skills/50-implement/SKILL.md` wird daraus per `scripts/sync_skills.py` regeneriert, nicht von Hand editiert; `.claude/commands/50-implement.md` ist eine bereits vor dieser Aenderung veraltete, separat versionierte Installations-Kopie ausserhalb jeder Sync-Pipeline dieses Repos und bewusst NICHT Teil dieser Spec), `tests/test_adversary_dialog_hash_binding_131.py` (neu), `tests/test_adversary_dialog_verdict.py` (Bestandstests um gültigen Hash-Block ergänzt), `tests/test_verdict_pipeline_77.py` (dito)
- **Estimated Changes:** ~180 LoC (Kernlogik ~90, Testdatei neu ~150, Bestandstests +~20 Zeilen Hash-Block-Ergänzung, Agent-/Command-Doku ~20)

## Implementation Details

**Schreiben (neuer CLI-Befehl `stamp`):**

```python
def stamp_dialog_artifact(artifact_path: str) -> tuple[bool, str]:
    """Liest 'Code reference: <pfad>:<zeile>' aus Findings/Confirmations,
    hasht jede referenzierte Datei (SHA-256) und haengt einen
    '## Geprüfte Dateien'-Block ans Artifact an."""
```

Die Dateiliste wird bewusst NICHT aus der Spec-Source-Section oder
`affected_files` im Workflow-State abgeleitet (beides vom Issue als Option
genannt), sondern aus den bereits verpflichtenden `Code reference:
path:line`-Zeilen in Findings und Confirmations (`implementation-validator.md`
Zeile 75: "A finding without Code reference is INVALID"). Begründung siehe
ADR unten.

**Validieren (`validate_dialog_artifact_ex`):** Der bisherige Alters-Check
(Zeilen 442-448) entfällt ersatzlos. Ein neuer Check vergleicht die im
`## Geprüfte Dateien`-Block gespeicherten Hashes mit einer frischen
SHA-256-Berechnung der referenzierten Dateien (Pfad relativ zu
`find_worktree_root() or find_project_root()`, absolute Pfade unverändert).
Bei Abweichung: `(False, "Prüfling seit dem Dialog geändert: <datei>. Re-run dialog.", "format")` —
`failure_kind="format"` (nicht `"content"`), weil eine veraltete Bindung kein
inhaltliches Urteil des Adversary ist, exakt wie beim bisherigen Alters-Check.

**Reihenfolge im Code:** Der Hash-Check laeuft NICHT an der alten Position
des Alters-Checks (direkt nach Existenzpruefung), sondern NACH der
Verdict-Klassifikation, vor der `AMBIGUOUS`/`VERIFIED`-Rueckgabe. Ein
BROKEN-Verdict oder ein unbekanntes Verdict blockt weiterhin unabhaengig vom
Hash-Stand — das ist bereits die sichere Richtung, eine Datei-Identitaetspruefung
aendert daran nichts. Nur Artefakte, die sonst `valid=True` ergeben wuerden
(VERIFIED/HOLDS/AMBIGUOUS), muessen zusaetzlich die Hash-Pruefung bestehen.

## Expected Behavior

- **Input:** Ein Dialog-Artifact-Pfad (`validate`) bzw. ein zu stempelndes
  Artifact (`stamp`), plus der aktuelle Arbeitsbaum-Stand der referenzierten
  Dateien.
- **Output:** `(valid: bool, message: str, failure_kind: str | None)` wie
  bisher — Signatur unveraendert, `qa_gate.py` braucht keine Anpassung.
- **Side effects:** `stamp` schreibt das Artifact-File (haengt einen Abschnitt
  an); `validate` liest nur, schreibt nichts.

## Error Handling

- Referenzierte Datei existiert nicht mehr (geloescht seit dem Dialog): wird
  wie eine Aenderung behandelt (Hash nicht berechenbar → Format-Fehler mit
  Dateiname).
- Kein `## Geprüfte Dateien`-Block im Artifact: Format-Fehler ("Re-run
  dialog"), ersetzt den alten "zu alt"-Fehler als Forcing-Function.
- `stamp` ohne jede `Code reference:`-Zeile im Artifact: `stamp` schlägt mit
  klarer Fehlermeldung fehl, statt einen leeren/nutzlosen Block zu schreiben.
- Mehrere `## Geprüfte Dateien`-Bloecke (Fix-Loop-Iterationen): nur der
  LETZTE (Dokumentposition) zaehlt — spiegelt das bestehende
  Last-Verdict-Wins-Verhalten.

## Known Limitations

- Bestandstests, die Dialog-Artefakte ohne Hash-Block per Hand bauen und
  `valid=True` erwarten, muessen einen gueltigen Block ergaenzen (siehe
  Scope) — Tests, die ohnehin bei einem frueheren Check auf `valid=False`
  enden (BROKEN-Verdict, offene Checkliste, kein Verdict gefunden), sind
  nicht betroffen, weil der Hash-Check erst nach der Verdict-Klassifikation
  laeuft.
- Schuetzt nur Dateien, die tatsaechlich per `Code reference:` zitiert
  wurden — ein Finding/Confirmation ohne Code-Referenz ist laut
  `implementation-validator.md` bereits ungueltig, aber technisch nicht
  erzwungen; diese Luecke ist nicht Teil dieser Spec (vorbestehend).
- Der Vorschlag des Issues, eine zweite, unabhaengige Adversary-Runde zu
  verlangen ("mindestens zwei Durchlaeufe mit disjunkten
  Mutationsfamilien"), ist explizit NICHT Teil dieser Spec — das Issue
  selbst nennt das als moegliche SEPARATE Anforderung, nicht als
  Nebenwirkung der Frist.

## Definition of Done

Fertig ist diese Änderung, wenn:

- [x] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [x] Ein Dialog-Artifact mit unveraendertem Hash-Block gilt unabhaengig von
      seinem Alter als gueltig; ein Artifact mit einer seither geaenderten
      referenzierten Datei wird abgelehnt — beides nachvollziehbar per Test,
      nicht nur per Behauptung
- [x] `MAX_AGE_MINUTES` und der Alters-Check sind vollstaendig entfernt
      (keine Koexistenz zweier Mechanismen — verifiziert per Grep: kein
      Treffer mehr im gesamten Repo ausserhalb dieser Spec/Tests)
- [x] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf grün:
      volle Suite 1130 passed, 4 skipped)

## Acceptance Criteria

- **AC-1:** Given ein Dialog-Artifact mit `## Geprüfte Dateien`-Block, dessen
  Hashes exakt zum aktuellen Inhalt aller gelisteten Dateien passen / When
  `validate_dialog_artifact_ex` laeuft / Then ist das Ergebnis gueltig,
  unabhaengig vom Datei-Alter (mtime).
  - Test: `test_valid_hash_block_passes_regardless_of_artifact_age`

- **AC-2:** Given ein Dialog-Artifact, dessen Hash-Block eine seither
  geaenderte Datei nennt / When validiert wird / Then schlaegt die Validierung
  fehl mit `failure_kind="format"` und einer Meldung, die die geaenderte
  Datei nennt ("Prüfling seit dem Dialog geändert: ..."), OHNE einen
  bestehenden `adversary_verdict` im Workflow-State zu ueberschreiben.
  - Test: `test_modified_referenced_file_is_rejected_as_format_error`,
    `test_deleted_referenced_file_is_rejected`

- **AC-3:** Given ein Dialog-Artifact mit sonst gueltigem VERIFIED-Verdict
  aber OHNE jeden `## Geprüfte Dateien`-Block / When validiert wird / Then
  schlaegt die Validierung als Format-Fehler fehl (erzwingt den `stamp`-Schritt).
  - Test: `test_missing_hash_block_is_rejected_as_format_error`,
    `test_broken_verdict_without_hash_block_still_fails_as_content` (Gegenprobe:
    BROKEN scheitert weiterhin am eigentlichen Grund, nicht am Hash-Check)

- **AC-4:** Given ein Dialog-Artifact mit einer `mtime` weit ausserhalb der
  frueheren 60-Minuten-Grenze, aber einem zum Ist-Stand passenden Hash-Block
  / When validiert wird / Then ist das Ergebnis gueltig — die Alters-Regel
  existiert nicht mehr, auch nicht als Zusatzpruefung.
  - Test: `test_valid_hash_block_passes_regardless_of_artifact_age`

- **AC-5:** Given ein Artifact mit zwei `## Geprüfte Dateien`-Bloecken aus
  zwei Fix-Loop-Iterationen (der erste referenziert eine seither veraenderte
  Datei, der zweite nur unveraenderte) / When validiert wird / Then zaehlt
  ausschliesslich der LETZTE Block.
  - Test: `test_only_last_hash_block_counts_across_fix_loop`,
    `test_stale_last_hash_block_fails_even_if_earlier_block_matches` (Spiegelfall)

- **AC-6:** Given ein frisch geschriebenes Dialog-Artifact mit
  `Code reference: <pfad>:<zeile>`-Zeilen in Findings/Confirmations / When
  `python3 adversary_dialog.py stamp <artifact-pfad>` laeuft / Then enthaelt
  das Artifact danach einen `## Geprüfte Dateien`-Block mit je einer
  `sha256:<hex>  <pfad>`-Zeile pro eindeutiger referenzierter Datei.
  - Test: `test_stamp_writes_hash_block_from_code_references`,
    `test_stamp_dedupes_files_cited_multiple_times`,
    `test_stamp_without_any_code_reference_fails_clearly`,
    `test_stamp_cli_subcommand_smoke`

- **AC-7:** Given eine Session, die in einem Git-Worktree laeuft (Datei nur
  dort veraendert, nicht im Haupt-Repo) / When `stamp` oder `validate` einen
  relativen Pfad aufloest / Then wird gegen den Worktree-eigenen Root
  (`find_worktree_root()`) aufgeloest, nicht gegen den geteilten
  Haupt-Repo-Root.
  - Test: `test_worktree_relative_path_resolves_against_worktree_root`,
    `test_worktree_change_in_worktree_copy_is_detected`

## Test Plan

Automated tests (linked to AC above):
- `pytest tests/test_adversary_dialog_hash_binding_131.py`
- Regressionslauf: `pytest tests/test_adversary_dialog_verdict.py tests/test_verdict_pipeline_77.py` (nach Ergaenzung der Hash-Bloecke weiterhin gruen)
- Vollstaendige Suite: `pytest`

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Zwei Design-Entscheidungen weichen bewusst vom Issue-Text ab
  bzw. praezisieren ihn:
  1. **Dateiliste aus `Code reference:` statt Spec-Source/`affected_files`.**
     Das Issue nennt beides als Beispiel ("ergibt sich aus..."), nicht als
     Pflichtvorgabe. `## Source` der Spec ist strukturell ein Einzelpfad,
     kein Mehrdateien-Feld; `affected_files` im Workflow-State ist ein rein
     manueller, nirgends automatisch aufgerufener Befehl
     (`workflow.py set-affected-files`) und in der Praxis meist leer. Die
     `Code reference:`-Zeilen sind dagegen bereits durch
     `implementation-validator.md` verpflichtend, spiegeln exakt das, was
     der Adversary tatsaechlich gelesen hat ("untersuchte Dateien" im
     Wortlaut des Issues), und machen das Artifact selbst-enthalten (keine
     Abhaengigkeit von Spec-Parsing oder Workflow-State-Schema beim
     Validieren).
  2. **Hash-Check laeuft nach der Verdict-Klassifikation, nicht an der alten
     Alters-Check-Position.** Vermeidet einen Bruch von rund 17 bestehenden
     Tests in `test_adversary_dialog_verdict.py` und `test_verdict_pipeline_77.py`,
     die Verdict-Parsing und Fence-Stripping pruefen und dabei absichtlich
     kein Hash-Feature testen. Da ein BROKEN- oder unbekanntes Verdict ohnehin
     `valid=False` liefert, aendert die Reihenfolge nichts an der
     sicherheitsrelevanten Richtung (ein stale VERIFIED/AMBIGUOUS wird
     weiterhin zuverlaessig abgefangen) — nur unveraendert gueltige Tests
     brauchen einen ergaenzten Hash-Block.

## Changelog

- 2026-09-23: Initial spec created
