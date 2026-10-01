# Context: feat-286-herkunft-vorbedingungen

## Request Summary

Issue #286 (Scheibe 2 von Epic #273, „Prüfkette belegt Korrektheit, nicht Erreichbarkeit"): Das
Werkzeug aus Scheibe 1 (#285, `core/hooks/precondition_origins.py`, bereits gemergt) liest maschinell
aus, welche Modellfelder ein Test per Zuweisung herstellt und wie oft dasselbe Feld im Produktivcode
tatsächlich geschrieben wird — aber ruft niemand auf. Diese Scheibe macht die daraus entstehende
Tabelle zur Pflichtsektion des Adversary-Prüfprotokolls, nach demselben Muster, mit dem
`## Geprüfte Dateien` (#131/#253) bereits erzwungen wird, und schließt dabei zugleich Blindstelle 3
aus #273 („hinter welcher Bedingung steht die Schreibstelle") als zweite Tabellenspalte ein.

**Voraussetzungen sind jetzt beide erfüllt:** #285 ist gemergt (PR #290), #278 (Protokollformat +
`scaffold`-Generator) ist gemergt (PR #303, heute). Die Analyse selbst nennt #278 als **harte
Vorbedingung** — ohne dokumentiertes Format wäre eine zweite Pflichtsektion an ein Geheimnis gehängt
worden.

## Vorhandene Phase-1+2-Analyse (Epic-Ebene, wiederverwendet statt wiederholt)

`docs/context/feat-273-erreichbarkeitspruefung.md` enthält bereits eine vollständige Phase-1+2-Analyse
für das gesamte Epic, inklusive eines fertigen Schnitts in sechs Teilvorgänge. Dieses Dokument
wiederholt sie NICHT, sondern zieht nur die für T2 (#286) relevanten Teile heran und ergänzt, was
seit ihrer Erstellung (2026-09-28) an Code-Stand dazukam (insbesondere #278, das Zeilennummern in
`adversary_dialog.py` verschoben hat).

Relevante Abschnitte dort: „Schnittvorschlag — sechs Teilvorgänge" → T2, „Was in Phase 2 zusätzlich
belegt wurde" Punkte 3 (Präzedenzfall als Bauplan), 5 (Prüferauftrag ohne Spec-Pfad — betrifft T4,
nicht T2), 6 (Runden untypisiert — betrifft T4, nicht T2), „Alternativen" A und B, „Entscheidungen des
PO (2026-09-28)".

## Related Files (mit aktuellem Zeilenstand, nach #278)

| File | Relevance |
|------|-----------|
| `core/hooks/adversary_dialog.py:420` | `validate_dialog_artifact_ex()` — Einhängepunkt für die neue Prüfung, nach dem bestehenden Schritt 5 (Datei-Hash-Verifikation) |
| `core/hooks/adversary_dialog.py:578-660` | Fünf-Bausteine-Muster `## Geprüfte Dateien` (`_extract_examined_files`, `render_examined_files_section`, `_parse_examined_files_section`, `_verify_examined_file_hashes`, `stamp_dialog_artifact`) — **Bauplan für die neue Sektion**, aber OHNE Hash-Bindung (siehe „Existing Patterns" unten, Abweichung 1) |
| `core/hooks/adversary_dialog.py:1049` | `scaffold_dialog_artifact()` (#278) — das Gerüst muss künftig auch einen leeren `## Herkunft der Vorbedingungen`-Platzhalter enthalten, sonst driftet das Gerüst wieder vom Gate weg (derselbe Fehler, den #278 gerade behoben hat) |
| `core/hooks/precondition_origins.py` | Scheibe 1 (#285), bereits fertig. CLI: `--lang <profil> --root <pfad> [--out <datei>]`. Tabellenspalten exakt: `Feld \| Test-Zuweisungen \| Produktions-Schreibstellen \| Bedingung davor \| Test für diesen Weg`. Die letzten beiden Spalten liefert das Werkzeug IMMER leer — das ist der menschliche Anteil, den T2 erzwingen soll. |
| `core/commands/50-implement.md:190-296` | Step 8 (Adversary-Dialog). `8a` (Zeile 194-207) ruft bereits `adversary_dialog.py scaffold` auf — dort ist der natürliche Ort, zusätzlich `precondition_origins.py` aufzurufen und die Tabelle dem Prüferauftrag beizulegen |
| `core/agents/implementation-validator.md` | Step 1 (Zeile 22-34) enthält bereits den `scaffold`-Aufruf (#278). Neuer Pflichtabschnitt im Berichtsformat, analog dem bestehenden „Structured Findings"-Abschnitt (Zeile 87-121) |
| `skills/50-implement/SKILL.md` | Generierter Spiegel von `core/commands/50-implement.md` — NICHT von Hand editieren, `python3 scripts/sync_skills.py` nach der `.md`-Änderung |
| `config.yaml:278-300` | Bestehende Kill-Switch-Muster (`po_briefing_gate`, `adversary_coverage_gate`) — beide ein einfaches `enabled: true/false`. **Kein bestehendes Muster für eine zweistufige Warn/Block-Eskalation** — muss neu entworfen werden (siehe „Risks" unten) |
| `config.yaml:399-414` | `precondition_origins.profiles` (swift, python) — von #285 bereits angelegt. Es gibt noch **kein** Feld, das einem Projekt sein Standard-Sprachprofil zuweist; `--lang` ist am CLI bewusst Pflicht, kein Auto-Detect (ADR-Punkt 3 in `docs/specs/feat-285-precondition-origins.md`) |
| `tests/test_adversary_protokoll_format_278.py` | Muster für hermetische CLI-Tests gegen die echten Hook-Skripte (aus #278, heute) — direkt wiederverwendbar für die neuen Tests dieser Scheibe |
| `tests/test_adversary_dialog_hash_binding_131.py`, `tests/test_adversary_coverage_gate_259.py` | Bestehende Tests für das `## Geprüfte Dateien`-Muster — Regressionswächter, falls die neue Sektion versehentlich mit der Hash-Prüfung kollidiert |

## Existing Patterns

1. **Pflichtsektion + Gate nach dem `## Geprüfte Dateien`-Muster** — der tragende Bauplan, siehe oben.
   **Wichtige Abweichung:** `## Geprüfte Dateien` ist hash-gebunden (beweist, dass der Prüfer genau
   diesen Code-Stand gelesen hat). Die neue Sektion braucht **keine** Hash-Bindung — sie enthält keine
   Dateiinhalte, sondern eine vom Werkzeug erzeugte Tabelle plus Prüfer-Prosa in zwei Spalten. Die
   Prüfung ist strukturell (Sektion vorhanden? jede Verdachtsgruppen-Zeile mit gefüllten Spalten?),
   nicht kryptographisch. Das vereinfacht den Bauplan gegenüber dem Vorbild: nur `render`/`parse`/
   `verify`-Bausteine nötig, kein `stamp`-Äquivalent.
2. **Form- vs. Inhaltsfehler-Trennung (#77)** — `validate_dialog_artifact_ex()` liefert
   `failure_kind = 'content' | 'format'`. Für die neue Sektion (Analyse bereits entschieden):
   Sektion **fehlt** → `format`; Sektion **vorhanden**, aber eine Verdachtsgruppen-Zeile ohne
   „Bedingung davor"/„Test für diesen Weg" → `content` (wie ein offener Checklistenpunkt).
3. **Kill-Switches** — `po_briefing_gate.enabled`, `adversary_coverage_gate.enabled`: beide
   einstufig. Diese Scheibe braucht laut Analyse zweistufig (Warnung vor Block) — neues Muster,
   siehe „Technical Approach" unten.
4. **Scaffold als einzige Formquelle (#278, heute gemergt)** — die Lehre aus #278 gilt hier direkt
   weiter: Das Gerüst (`scaffold_dialog_artifact()`) muss die neue Sektion von Anfang an enthalten,
   sonst entsteht exakt dieselbe Lücke (Format im Gate, aber nirgends im erzeugten Gerüst).

## Dependencies

- **Upstream (Voraussetzung):** #285 (Werkzeug, gemergt), #278 (Protokollformat + Generator,
  gemergt heute). Beide erfüllt — T2 kann beginnen.
- **Downstream:** `bash_gate.py` (Commit-Gate, #253-Nachweispfad) und `workflow.py`
  (`_validate_transition` nach `phase8_complete`) prüfen beide über `check_dialog_evidence()` →
  `validate_dialog_artifact_ex()` — eine neue Pflichtsektion wirkt dort automatisch mit, ohne dass
  diese beiden Dateien selbst geändert werden müssen (derselbe Hebel wie bei #131/#253).
- **Jedes installierte Projekt:** Eine unbedingte neue Pflicht würde jeden Abschluss sofort blocken
  — deshalb die Warnstufe (siehe Risks).
- **T6 (Gegenprobe, bleibt in #273):** hängt an T1+T2 zusammen, nicht an T2 allein — folgt erst nach
  dieser Scheibe.
- **Kollision #259/PR #266** (bereits gemergt, Diff-Abdeckung) — erweitert denselben
  Nachweis-Mechanismus; laut Epic-Analyse vor T2 abzuschließen. Ist inzwischen gemergt (aus dem
  Log dieser Session ersichtlich: `f6eab8c fix(#259)…` liegt bereits auf `main`). Keine offene
  Kollision mehr.

## Existing Specs

- `docs/specs/feat-285-precondition-origins.md` — Werkzeug-Interface (CLI, Tabellenformat, Config-Profile)
- `docs/specs/fix-278-adversary-protokoll-format.md` — `scaffold`, Rundenformat, Kennzahlen-Rückschrieb
- `docs/specs/fix-131-adversary-dialog-hash-binding.md` — Vorlage für eine gehashte Pflichtsektion
- `docs/specs/fix-253-adversary-evidence-gate.md` — Vorlage für Scope-Überschreitungs-Begründung
  und Form/Inhalt-Trennung
- `docs/context/feat-273-erreichbarkeitspruefung.md` — Epic-Analyse, Schnittvorschlag, PO-Entscheidungen

## Risks & Considerations

1. **Wirkung auf alle installierten Projekte.** Bestätigt aus der Epic-Analyse. Erfordert eine
   zweistufige Config (Warnung → Block), die es in diesem Repo noch nicht gibt. Entwurf (Tech-Lead-
   Entscheidung, keine PO-Frage): `precondition_section_gate: { enabled: true, mode: warn|block,
   skip_fast_track: true }` — ein `mode`-Feld statt einer Versionsbindung. *Verworfene Alternative:*
   „ab Framework-Version X block" (so in der Epic-Analyse skizziert) — verworfen, weil das
   voraussetzt, dass jedes installierte Projekt seine Framework-Version selbst korrekt meldet und
   der Schalter dadurch indirekt und schwerer nachvollziehbar wird. Ein explizites `mode:`-Wort, das
   der PO eines Projekts selbst umstellt, ist direkter und entspricht dem bereits etablierten
   Ein-Wort-Kill-Switch-Stil dieses Repos.
2. **Sprachprofil-Zuordnung ist ungelöst.** `precondition_origins.py --lang` ist am CLI Pflicht,
   ohne Auto-Detect (bewusste #285-Entscheidung). T2 muss entscheiden, welches Profil der
   Orchestrator beim Aufruf aus `50-implement.md` Step 8 verwendet. Vorschlag (Tech-Lead-Entscheidung):
   neues optionales Feld `precondition_origins.default_lang` in der PROJEKT-eigenen `config.yaml`
   (nicht in `modules/*/config.yaml` — dieselbe Einschränkung gilt bereits für
   `observable_surface.surface_patterns`, siehe Kommentar dort). Fehlt das Feld, ruft der
   Orchestrator das Werkzeug nicht auf; die Sektion wird trotzdem angelegt, mit dem Hinweistext
   „kein Sprachprofil konfiguriert (`precondition_origins.default_lang`)" statt einer Tabelle — das
   zählt als vollständig (kein Format-Fehler), da hier strukturell nichts zu vervollständigen ist.
3. **Dieses Repo selbst hat keine `model_globs`-Treffer.** `agent-os-openspec` ist ein reines
   Python-Hook-Repo ohne Modellschicht im Sinne von #285 (`**/models/*.py` existiert hier nicht).
   Die neue Pflichtsektion wird für **eigene** Workflows dieses Repos also fast immer trivial
   erfüllt sein (Hinweistext „keine Modelldateien gefunden", keine Verdachtsgruppen-Zeilen). Die
   eigentliche Wirkung entfaltet sich in Konsumenten-Projekten mit echter Modellschicht (z. B. das
   iOS/SwiftUI-Modul). **Konsequenz für die Spec:** Die Acceptance Criteria, die die Content-Prüfung
   (unvollständige Verdachtsgruppen-Zeile blockt) beweisen sollen, brauchen ein Test-Fixture mit
   echten Modellfeldern — das Repo selbst reicht als Testgrund nicht aus. `tests/fixtures/
   precondition_origins/{swift,python}/` aus #285 sind genau ein solches Fixture und wiederverwendbar.
4. **Hash-Bindung absichtlich weggelassen** (siehe „Existing Patterns" Punkt 1) — Risiko: ein
   Prüfer könnte plausible, aber erfundene „Bedingung davor"-Prosa eintragen, ohne dass das Gate es
   erkennt. Dasselbe Risiko besteht heute bereits bei der AC-Checkliste selbst (auch nicht
   hash-gebunden) — kein neues Muster, keine Sonderbehandlung nötig.
5. **Scope-Nähe zur Hausgrenze.** Die Epic-Analyse schätzt T2 auf 6 Dateien / +300/-20 LoC — über
   beiden Grenzen (±250 LoC, max. 4-5 Dateien), mit derselben Art Begründung wie `fix-253` (siehe
   dortiger Scope-Abschnitt): eine neue Pflicht, die an mehreren bereits bestehenden Stellen
   (Gate-Funktion, zwei Spiegelquellen, Agenten-Doku, Config) angebunden werden muss, ist strukturell
   verteilt, nicht aufblähend. In Phase 3 sauber als mehrere AC-Blöcke führen, damit ein Review sie
   einzeln prüfen kann.
6. **Scaffold-Nacharbeit.** `scaffold_dialog_artifact()` (#278) muss einen Platzhalter für die neue
   Sektion mitrendern, sonst fällt das frisch behobene #278-Problem (Gerüst und Gate driften
   auseinander) für die neue Sektion sofort wieder an. Das gehört als eigener AC-Punkt in die Spec,
   nicht als Nebensatz.

---

# Analysis (Phase 2)

## Type

Feature (Scheibe 2 eines laufenden Epics, #273/T2).

## Technical Approach

**1. Neue Sektion `## Herkunft der Vorbedingungen`** — Bausteine analog `## Geprüfte Dateien`,
aber ohne Hash-Bindung (siehe „Existing Patterns"):

```python
def _parse_precondition_section(scan: str) -> "list[dict] | None":
    """Zeilen der letzten '## Herkunft der Vorbedingungen'-Tabelle, oder None wenn Sektion fehlt.
    Jede Zeile: {field, test_refs, prod_refs, condition, test_for_path} — die beiden letzten
    Felder sind roh (Prüfer-Prosa), koennen leer sein."""

def _is_suspect_row(row: dict) -> bool:
    """Verdachtsgruppe: hoechstens 1 Produktions-Schreibstelle (dieselbe Schwelle wie #285 AC-7)."""

def _verify_precondition_section(scan: str) -> tuple[bool, str, "str | None"]:
    """None (Sektion fehlt) -> (False, msg, 'format').
    Vorhanden, aber eine Verdachtsgruppen-Zeile ohne 'Bedingung davor' ODER 'Test fuer diesen Weg'
    -> (False, msg, 'content').
    Sonst (auch bei 0 Verdachtsgruppen-Zeilen, z.B. Hinweistext 'keine Modelldateien gefunden')
    -> (True, msg, None)."""
```

Einhängung in `validate_dialog_artifact_ex()` als neuer Schritt nach der bestehenden
Datei-Hash-Verifikation (aktuell endend ~Zeile 516), vor dem finalen VERIFIED/AMBIGUOUS-Return.
Läuft **nur**, wenn `precondition_section_gate.enabled: true` UND `mode` mindestens `warn` ist
(siehe Punkt 3) — bei `warn` wird ein Format-/Content-Fehler als Warnung auf stderr ausgegeben,
liefert aber `(True, ..., None)` (blockt nicht); bei `block` verhält es sich wie jede andere
Format-/Content-Prüfung in dieser Funktion.

**2. Orchestrierung in `core/commands/50-implement.md` Step 8a** (Spiegel: `skills/50-implement/
SKILL.md`, automatisch via `sync_skills.py`): direkt nach dem bestehenden `scaffold`-Aufruf, wenn
`precondition_origins.default_lang` in der Projekt-`config.yaml` gesetzt ist:

```bash
python3 .claude/hooks/precondition_origins.py --lang <default_lang> --root .
```

Ergebnis wird dem `implementation-validator`-Auftrag beigelegt (wie die Checkliste aus `parse`
bereits heute). Ist `default_lang` nicht gesetzt, entfällt der Aufruf; der Prüfer schreibt
stattdessen den Hinweistext in die Sektion (siehe Risk 2 oben) — kein Fehlerfall.

**3. Zweistufiger Kill-Switch** (`config.yaml`, neuer Block, Format an `po_briefing_gate`
angelehnt):

```yaml
precondition_section_gate:
  enabled: true
  # warn: Sektion fehlt/unvollstaendig -> Warnung (stderr), Gate blockt NICHT.
  # block: wie jede andere Format-/Content-Pruefung -> blockt Commit/Phase 8.
  mode: warn
  skip_fast_track: true   # Fast Track hat ohnehin keinen Adversary-Dialog — informativ, keine Zusatzlogik
```

**4. `scaffold_dialog_artifact()` (#278) ergänzen** um einen leeren
`## Herkunft der Vorbedingungen`-Platzhalter mit Hinweistext „vom Prüfer auszufüllen, siehe
\`precondition_origins.py\`" — verhindert die in Risk 6 genannte erneute Formatlücke.

**5. `core/agents/implementation-validator.md`** — neuer Pflichtabschnitt analog „Structured
Findings": Anleitung, die beigelegte Tabelle in die Sektion zu übernehmen und für jede
Verdachtsgruppen-Zeile „Bedingung davor" (unter welcher Bedingung schreibt der Produktivcode das
Feld) und „Test für diesen Weg" (existiert ein Test, der GENAU diesen Weg — nicht nur das
Ergebnis — auslöst) auszufüllen.

## Affected Files

| File | Change Type | Description |
|------|-------------|--------------|
| `core/hooks/adversary_dialog.py` | MODIFY | Drei neue Funktionen (`_parse_precondition_section`, `_is_suspect_row`, `_verify_precondition_section`), Einhängung in `validate_dialog_artifact_ex()`, Erweiterung von `scaffold_dialog_artifact()` um den Platzhalter |
| `core/commands/50-implement.md` | MODIFY | Step 8a: bedingter Aufruf von `precondition_origins.py`, Auftragserweiterung |
| `core/agents/implementation-validator.md` | MODIFY | Neuer Pflichtabschnitt „Herkunft der Vorbedingungen" im Berichtsformat |
| `config.yaml` | MODIFY | Neuer Block `precondition_section_gate` (enabled/mode/skip_fast_track) + `precondition_origins.default_lang` (optional, Projekt-Ebene) |
| `skills/50-implement/SKILL.md` | GENERATED | `python3 scripts/sync_skills.py` nach der `.md`-Änderung, nicht von Hand |
| `tests/test_precondition_section_gate.py` | CREATE | Sektion fehlt (format) / unvollständig (content) / vollständig (VERIFIED), warn- vs. block-Modus, Fixture mit echter Verdachtsgruppen-Zeile (aus #285-Fixtures wiederverwendet), Scaffold-Platzhalter vorhanden |
| `CHANGELOG.md` | MODIFY | `[Unreleased]` |

## Scope Assessment

- Dateien (ohne generierten Spiegel, ohne Test): 4 handgeschriebene Produktivdateien
  (`adversary_dialog.py`, `50-implement.md`, `implementation-validator.md`, `config.yaml`) + 1 Doku
  (`CHANGELOG.md`) = 5 — an der Hausgrenze, nicht darüber (anders als die Epic-Analyse grob
  geschätzt hatte, weil dort `skills/*.md` noch mitgezählt war, das aber generiert ist).
- Geschätzte LoC: +180/-10 (drei Funktionen ~70, Einhängung + Scaffold-Ergänzung ~25,
  Doku-Ergänzungen zwei `.md`-Dateien ~40, Config-Block ~15, CHANGELOG ~10) — innerhalb ±250,
  **wenn** kein zusätzliches Test-Fixture-Verzeichnis neu angelegt werden muss (siehe unten).
- Test-Fixtures: Risk 3 oben verlangt ein Beispiel mit echter Modellschicht. Die
  `tests/fixtures/precondition_origins/{swift,python}/` aus #285 sind bereits genau dafür gebaut
  und werden **wiederverwendet**, nicht neu angelegt — das hält den Umfang innerhalb der Grenze.
- Risk Level: MEDIUM-HIGH — neue Pflicht in einer Gate-Funktion, die jeden Abschluss in jedem
  angebundenen Projekt betrifft; durch `mode: warn` als Standard-Einführungsstufe abgefedert
  (identische Absicherung wie von der Epic-Analyse gefordert, nur technisch einfacher umgesetzt
  als die dort skizzierte Versionsbindung).

## Open Questions

- [x] Hash-Bindung für die neue Sektion? **Entschieden (Tech Lead, siehe Existing Patterns):**
  Nein — die Sektion enthält keine Dateiinhalte, nur eine Werkzeug-Tabelle plus Prüfer-Prosa.
- [x] Versionsbindung oder `mode`-Schalter für die Warnstufe? **Entschieden (Tech Lead):**
  `mode: warn|block` — einfacher, direkter, entspricht dem Repo-Stil.
- [x] Woher kommt `--lang` für den Orchestrator-Aufruf? **Entschieden (Tech Lead):** neues
  optionales Feld `precondition_origins.default_lang` in der Projekt-`config.yaml`; fehlt es,
  entfällt der Werkzeug-Aufruf und die Sektion trägt einen Hinweistext statt einer Tabelle.
- [ ] **Offen für die Spec-Phase, keine PO-Frage:** exakter Wortlaut des Hinweistexts bei
  fehlendem `default_lang` sowie die genaue Formulierung der Verdachtsgruppen-Schwelle (dieselbe
  wie #285, „höchstens 1 Produktions-Schreibstelle", oder konfigurierbar?) — wird in Phase 3 als
  AC festgelegt.

## Dependencies (Analyse-Ebene)

- Downstream unverändert: siehe „Dependencies" oben (Kontext-Teil).
- Keine offene Upstream-Abhängigkeit mehr — sowohl #285 als auch #278 sind gemergt.
