---
entity_id: feat-285-precondition-origins
type: feature
created: 2026-09-28
updated: 2026-09-28
status: draft
version: "1.0"
tags: [precondition-origins, testvorbedingungen, regelweg, cli, epic-273]
test_targets: ["tests/test_precondition_origins.py"]
---

# Werkzeug: Herkunft von Testvorbedingungen maschinell einsammeln (#285)

## Approval

- [ ] Approved

## GitHub Issue

- **Issue:** #285 — „Werkzeug: Herkunft von Testvorbedingungen maschinell einsammeln (Scheibe 1
  von #273)". Epic: #273 („Prüfkette belegt Korrektheit, nicht Erreichbarkeit"). Schnitt und
  Reihenfolge (T1 vor T2) festgelegt in `docs/context/feat-273-erreichbarkeitspruefung.md`,
  Abschnitt „Schnittvorschlag — sechs Teilvorgänge", T1.

## Purpose

Ein Test, der eine Ausgangslage per Zuweisung herstellt (`objekt.feld = wert`), prüft nur das
Verhalten ab dieser Lage — nicht, ob und wie der Betrieb je in diese Lage gerät. Diese Scheibe
liefert das Werkzeug, das die dafür nötigen drei Tatsachen maschinell einsammelt: welche Felder
ein Test per Zuweisung setzt, wo im Produktivcode dasselbe Feld tatsächlich geschrieben wird, und
wie oft. Reine Textanalyse (Reguläre Ausdrücke + Dateisuche), kein Sprachmodell.

**Das tragende Signal ist NICHT „viele Test-Zuweisungen gegen wenige Produktions-Schreibstellen"**
— das war eine Fehlzählung der ersten Machbarkeitsprobe (Issue #285, „Belegte Machbarkeit" sprach
von zwölf Zuweisungen). Nachgemessen gegen den echten Referenzfall `henemm/loose-ends#144`
(`c36fec6`) gibt es genau EINE Test-Zuweisung an `processedAt`
(`LooseEndsTests/EnrichmentTests.swift:404`) — in einer gemeinsam genutzten Hilfsfunktion
(`makeProcessed(...)`), von der mehrere Tests abhängen; die übrigen elf Fundstellen im Testfile
waren Prüfungen (`#expect(...)`) und Kommentare, keine Zuweisungen. Das eigentliche Signal ist
schärfer als angenommen: **im Betrieb wird das Feld höchstens einmal geschrieben, und mindestens
ein Test verlässt sich auf diese Lage** — unabhängig davon, wie viele Tests am Ende über eine
gemeinsame Hilfsfunktion von derselben einen Zuweisung abhängen.

## Source

- **File:** `core/hooks/precondition_origins.py` (neu)
  **Identifier:** CLI-Einstiegspunkt `main()`; Kernfunktionen `load_profile()`,
  `extract_model_fields()`, `find_assignments()`, `render_table()`
- **File:** `config.yaml`
  **Identifier:** neuer Block `precondition_origins.profiles` (Sprachprofile `swift`, `python`)

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `hook_utils.setup_path` (`core/hooks/hook_utils.py:407`) | function | Bootstrap für Same-Directory-Imports — Konvention aller `core/hooks/*.py` |
| `hook_utils.find_project_root` (`core/hooks/hook_utils.py:725`) | function | Default-Wurzel für `--root`, wenn keiner übergeben wird |
| `config_loader.load_config` (`core/hooks/config_loader.py:130`) | function | Liest `precondition_origins.profiles` aus `config.yaml`/`openspec.yaml` (Suchreihenfolge `CONFIG_NAMES`, `core/hooks/config_loader.py:29`) plus `settings.local.json`-Overrides |
| `pathlib.Path.glob`, `re` (Python-Stdlib) | stdlib | Der komplette Regelweg — Dateisuche und Textmuster, keine neue Dependency |
| PyYAML | Bibliothek | Bereits Projekt-Dependency über `config_loader` (`core/hooks/config_loader.py:22-25`), keine zusätzliche Installation nötig |

**Downstream:** bewusst keine. Diese Scheibe hängt an keinem Gate und wird von keinem bestehenden
Hook aufgerufen — siehe „Nicht in dieser Spec" unten. Die Pflicht im Prüfprotokoll folgt in einer
eigenen Scheibe (#286, T2 aus der Analyse).

## Scope

### Affected Files

| Datei | Art | Beschreibung |
|---|---|---|
| `core/hooks/precondition_origins.py` | CREATE | Feldextraktion, Zuweisungssuche, Schreibstellen-Zählung, Tabellen-Rendering, CLI (`main()`) |
| `config.yaml` | MODIFY | Neuer Block `precondition_origins.profiles` mit den Sprachprofilen `swift` und `python` |
| `tests/test_precondition_origins.py` | CREATE | Regelweg gegen mitgelieferte Beispielbäume beider Sprachen (AC-1 bis AC-6) und gegen den eingefrorenen echten Ausschnitt (AC-7) |
| `tests/fixtures/precondition_origins/{swift,python}/**` | CREATE | Nachgebaute Beispielbäume je Sprachprofil (siehe „Implementation Details" → Fixtures) — tragen AC-1 bis AC-6 |
| `tests/fixtures/precondition_origins/reference-c36fec6/**` | CREATE | Eingefrorener, UNVERÄNDERTER Ausschnitt aus `henemm/loose-ends`, Stand `c36fec6` (vier Originaldateien) plus `PROVENANCE.md` — trägt AC-7. Siehe „Implementation Details" → Fixtures |
| `CHANGELOG.md` | MODIFY | Eintrag unter `[Unreleased]` → `### Added` |

### Estimated Changes

~360 LoC gesamt: Kernprogramm `precondition_origins.py` ~170 LoC, `config.yaml`-Block ~20 LoC,
Testdatei ~100 LoC, nachgebaute Fixtures (`swift/`, `python/`) ~70 LoC, eingefrorener Ausschnitt
`reference-c36fec6/` (vier unveränderte Originaldateien plus `PROVENANCE.md`) ~40 LoC-äquivalent
zusätzlich.

**Überschreitung der Hausgrenze (±250 LoC) — begründet:** Der gesamte Umfang liegt in einer
einzigen neuen, isolierten Datei plus ihrer eigenen Testdatei und deren Fixtures. Es wird kein
bestehender Hook umgebaut, keine bestehende Funktion geändert (außer dem rein additiven
`config.yaml`-Block) und kein bestehender Test angefasst. Die Überschreitung entsteht, weil ein
vollständiges, eigenständig lauffähiges Werkzeug mit zwei Sprachprofilen und den Fixtures für AC-7
mehr Zeilen braucht als ein einzelner Hook-Patch — nicht, weil mehrere Baustellen gleichzeitig
angefasst würden (vgl. Präzedenz in `docs/specs/fix-253-adversary-evidence-gate.md`, Abschnitt
„Scope", das dieselbe Art Begründung für eine Überschreitung in die andere Richtung nutzt: viele
Dateien statt einer großen). Der Zuwachs von ~320 auf ~360 LoC gegenüber der ersten Fassung dieser
Spec ist außerdem größtenteils übernommenes Fremdmaterial (die vier unveränderten Originaldateien
aus `loose-ends@c36fec6`), kein zusätzlich selbst geschriebener Code — die eigentliche
Implementierungslast wächst dadurch kaum.

### Nicht in dieser Spec

- **Keine Pflichtsektion, kein Gate.** Das Werkzeug wird von keinem Hook aufgerufen, kein
  bestehendes Gate (`adversary_dialog.py`, `bash_gate.py`, `workflow.py`) wird angefasst. Es
  entsteht ein eigenständig aufrufbares CLI-Programm, das an keinem angebundenen Projekt etwas
  automatisch ändert oder blockiert. Diese Scheibe ist bewusst reversibel und risikoarm — sie
  installiert bei jedem `setup.py --update` nur eine zusätzliche, ungenutzte Datei.
- Die Pflicht im Prüfprotokoll und die Gate-Anbindung (#286 / T2 der Analyse).
- Die Symmetrieprüfung gegen gleichartige Bausteine (T3 der Analyse).
- Die spec-freie Prüfrunde (T4 der Analyse).
- Die Semantik übersprungener Tests — gehört nach #275.
- Die Bedingungs-Analyse selbst („hinter welcher Bedingung steht die Schreibstelle") — die Spalte
  *Bedingung davor* bleibt vom Werkzeug leer und wird vom menschlichen Prüfer gefüllt.
- Sprachprofile jenseits von Swift und Python (z. B. Go, Kotlin) — AC-6 verlangt nur, dass ein
  drittes Profil ohne Codeänderung ergänzbar *wäre*; dieser Nachweis läuft gegen eine Test-Fixture,
  keine dritte Sprache wird produktiv eingerichtet.

## Implementation Details

**Ablauf:** (1) Sprachprofil aus `config.yaml` laden. (2) Modelldateien nach `model_globs`
suchen, Feldnamen mit `field_pattern` extrahieren (dedupliziert, alphabetisch sortiert für
deterministische Weiterverarbeitung) — **alle** gefundenen Felder, ungefragt (AC-1). (3) Für
jedes Feld: Testdateien nach `test_globs` durchsuchen, Zeilen sammeln, die `assignment_pattern`
(mit `{field}` als Platzhalter für den escapten Feldnamen) treffen — mit `Datei:Zeile`. (4)
Dieselbe Suche gegen `production_globs` minus `production_exclude_globs`. (5) Tabelle rendern —
**nur für Felder mit mindestens einer Test-Zuweisung aus Schritt (3)** —, aufsteigend nach Zahl
der Produktions-Schreibstellen sortiert (Tie-Break: Feldname alphabetisch), Felder mit 0
Schreibstellen sichtbar markiert.

**Nur Felder mit Test-Zuweisung erscheinen in der Tabelle.** Schritt (2) liest weiterhin
sämtliche Feldnamen aus den Modelldateien — AC-1 verlangt genau das, ungefragt und vollständig.
Schritt (5) filtert davon vor dem Rendern auf die Teilmenge, die mindestens einen Treffer in
Schritt (3) hat. Ohne diesen Filter wächst die Tabelle unbrauchbar: gegen den eingefrorenen
Referenzausschnitt (siehe „Fixtures" unten) stehen ohne Filter 56 statt 18 Zeilen, davon 23 mit 0
Schreibstellen, und das gesuchte Feld rutscht auf Rang 35 ab — die Liste verliert ihren Zweck als
Verdachtsliste. Die Machbarkeitsprobe in Phase 2 der Analyse hatte diese Einschränkung bereits
implizit eingebaut (28 Zeilen statt 83 mögliche Felder — nur wer mindestens eine Test-Zuweisung
hatte, kam überhaupt in die 28er-Liste).

**Warum `assignment_pattern` eine Punkt-Zuweisung verlangt (`\.{field}\s*=\s*(?!=)`):** Genau das
unterscheidet eine Objekt-Zuweisung (`task.processedAt = Date(...)`) von einer gleichnamigen
lokalen Variablen (`let processedAt = Date()`) oder einem Vergleich (`x.processedAt == y`). Die
negative Lookahead `(?!=)` schließt `==` aus. Das ist der entscheidende Filter für AC-2 — er kam
aus der Probe in Phase 2 der Analyse (naive Suche ohne diesen Filter: 199 Treffer, davon Rauschen;
mit Filter + Feldnamen-Eingrenzung: 161 Zuweisungen, verteilt über 28 echte Felder). Diese Zahlen
sind eine Aussage auf **Feld-Ebene** (wie viele verschiedene Felder überhaupt Zuweisungen tragen),
keine Zuweisungszahl eines einzelnen Feldes — die Nachmessung gegen `c36fec6` für das konkrete
Feld `processedAt` liegt deutlich niedriger (genau 1, siehe „Purpose" und AC-7/AC-8).

**Sprachprofil-Struktur** (Auszug `config.yaml`, vollständig konfigurierbar, keine
Codeänderung für ein drittes Profil nötig — AC-6):

```yaml
precondition_origins:
  profiles:
    swift:
      model_globs: ["**/Models/*.swift", "**/Shared/Models/*.swift"]
      field_pattern: '(?:var|let)\s+(\w+)\s*:'
      test_globs: ["**/*Tests/**/*.swift", "**/*Tests.swift"]
      production_globs: ["**/*.swift"]
      production_exclude_globs: ["**/*Tests/**", "**/*Tests.swift"]
      assignment_pattern: '\.{field}\s*=\s*(?!=)'
    python:
      model_globs: ["**/models/*.py", "**/models.py"]
      field_pattern: '^\s*(\w+)\s*:\s*[A-Za-z_].*$'
      test_globs: ["tests/**/*.py", "**/test_*.py", "**/*_test.py"]
      production_globs: ["**/*.py"]
      production_exclude_globs: ["tests/**", "**/test_*.py", "**/*_test.py"]
      assignment_pattern: '\.{field}\s*=\s*(?!=)'
```

`field_pattern` läuft zeilenweise über jede Datei aus `model_globs` (`re.search`, Gruppe 1 =
Feldname). `assignment_pattern` wird pro Feld mit `re.escape(feldname)` in `{field}` eingesetzt
und ebenfalls zeilenweise angewendet (`re.search`), damit `Datei:Zeile` exakt bestimmbar bleibt.
Ein Profil, das diese sechs Schlüssel liefert, ist vollständig — ein drittes Profil ist ein
weiterer Eintrag unter `precondition_origins.profiles`, ohne dass `precondition_origins.py`
angefasst wird.

**Kernfunktionen (Signaturen, keine vollständige Implementierung):**

```python
def load_profile(config: dict, lang: str) -> dict: ...
def iter_glob_files(root: Path, globs: list[str],
                     exclude: list[str] = ()) -> list[Path]: ...
def extract_model_fields(root: Path, profile: dict) -> list[str]: ...
def find_assignments(root: Path, globs: list[str], exclude: list[str],
                      fields: list[str], assignment_pattern: str
                      ) -> dict[str, list[str]]:
    """field -> ['datei:zeile', ...], sortiert nach Fundstelle."""
def render_table(fields: list[str], test_hits: dict[str, list[str]],
                  prod_hits: dict[str, list[str]]) -> str: ...
def main() -> None:
    """CLI: --lang, --root (default: find_project_root()),
    --config (default: ueber config_loader aufgeloest), --out."""
```

**CLI:**

```
python3 core/hooks/precondition_origins.py --lang swift \
    [--root <pfad, default: find_project_root()>] \
    [--config <pfad zu config.yaml, default: config_loader-Standardsuche>] \
    [--out <pfad, default: stdout>]
```

`--config` getrennt von `--root` ist nötig für die Gegenprobe (siehe „Test Plan"): Ein externer
Referenzbaum ohne eigene `config.yaml` scannt `--root <externer-pfad>`, liest die Sprachprofile
aber weiterhin aus diesem Framework-Repo (`--config <dieses-repo>/config.yaml`).

**Tabellenformat** (Spalten exakt wie in Issue #285 gefordert):

```
| Feld | Test-Zuweisungen | Produktions-Schreibstellen | Bedingung davor | Test für diesen Weg |
```

Zellinhalt Test-Zuweisungen/Produktions-Schreibstellen: `<Anzahl> — <Datei:Zeile>` je Fundstelle,
mit `<br>` getrennt (GitHub-Markdown rendert `<br>` in Tabellenzellen als Zeilenumbruch). Zeilen
mit 0 Produktions-Schreibstellen tragen den Text `**0 — keine Schreibstelle im Produktivcode**`
in dieser Spalte; die beiden letzten Spalten bleiben in jeder Zeile leer — sie füllt der
menschliche Prüfer, nicht dieses Werkzeug.

**Fixtures für die automatisierten Tests** (`tests/fixtures/precondition_origins/`):

- `swift/Shared/Models/Task.swift` — Modelldatei mit **vier** Feldern: `processedAt` (Vorbild für
  den Ein-Schreibstellen-Fall), `energyRaw` (Vorbild für den Null-Schreibstellen-Fall), `title`
  (neutrales Feld mit mehreren Schreibstellen als Kontrastfall) und `notes` — ein viertes Feld,
  das in KEINER Testdatei zugewiesen wird. `notes` ist der Beleg für die Filterregel: Schritt (2)
  liest es (AC-1, Teil a: Extraktion über `extract_model_fields()` direkt geprüft, ungefragt, alle
  vier Felder), Schritt (5) listet es trotzdem nicht in der Tabelle (AC-1, Teil b: keine
  Test-Zuweisung).
- `swift/Sources/EnrichmentWriter.swift` — genau eine Schreibstelle für `processedAt`, hinter
  einer `if`-Bedingung; mehrere Schreibstellen für `title`; keine für `energyRaw` oder `notes`.
- `swift/Tests/TaskTests.swift` — Test-Zuweisungen für `processedAt`, `energyRaw` und `title`
  (sonst fielen sie unter der Filterregel „Nur Felder mit Test-Zuweisung erscheinen in der
  Tabelle" aus der Tabelle heraus und AC-3/AC-4/AC-5 hätten keine drei Zeilen mehr zu vergleichen):
  `task.processedAt = Date(...)` (mehrfach, in einer Helper-Funktion), `task.energyRaw = 0`
  (mindestens einmal, obwohl das Feld 0 Produktions-Schreibstellen hat) und `task.title = "x"`
  (mehrfach) — bewusst KEINE Zuweisung an `notes`. Dazu Rauschen, das keinen Treffer erzeugen
  darf: eine lokale Variable `let processedAt = Date()` ohne Objektbezug und ein Vergleich
  `task.processedAt == nil`.
- `python/models/task.py`, `python/writer.py`, `python/tests/test_task.py` — dieselbe Lage wie
  die korrigierte Swift-Fixture oben: vier Modellfelder, drei davon (`processed_at`,
  `energy_raw`, `title`) mit mindestens einer Test-Zuweisung, ein viertes (`notes`) ohne — Python-
  Syntax (`processed_at: datetime | None = None` als Feld, `task.processed_at = value` als
  Zuweisung, `self.processed_at == None` als Rauschen-Vergleich).

**Der eingefrorene echte Ausschnitt** (`tests/fixtures/precondition_origins/reference-c36fec6/`,
PO-Entscheidung vom 2026-09-28): Die nachgebauten Fixtures oben tragen AC-1 bis AC-6 und das
Python-Profil, beweisen aber nur, dass das Werkzeug an einem selbst konstruierten Beispiel fündig
wird — genau das Muster, gegen das sich Epic #273 richtet („ein Test, der sich seinen
Ausgangszustand selbst herstellt, prüft nur den halben Weg"). AC-7 verlangt deshalb einen
automatisierten Test gegen UNVERÄNDERTES echtes Material. Dieser Ausschnitt enthält die vier
Originaldateien aus `henemm/loose-ends`, Stand `c36fec6`, die nachweislich das Feld `processedAt`
tragen (geprüft am 2026-09-28 gegen den lokal vorhandenen Checkout):

- `Shared/Models/TaskItem.swift` — das Modell mit dem Feld `processedAt`.
- `Shared/Enrichment/EnrichmentWriter.swift` — die einzige Schreibstelle im Betrieb (Zeile 94,
  hinter einer Bedingung).
- `Shared/Enrichment/EnrichmentCoordinator.swift` — nennt das Feld ebenfalls; wird mit
  aufgenommen, damit die Zählung der Produktions-Schreibstellen nicht künstlich auf eine einzige
  Datei verengt wird (sonst prüfte der Test nur „findet die eine Datei", nicht „zählt über den
  ganzen production_globs-Bereich richtig").
- `LooseEndsTests/EnrichmentTests.swift` — die Testdatei mit der einen Zuweisung an `processedAt`
  in der gemeinsam genutzten Hilfsfunktion `makeProcessed(...)` (Zeile 404), von der mehrere
  Tests abhängen. Die übrigen Fundstellen des Feldnamens in dieser Datei sind Prüfungen
  (`#expect(task.processedAt == nil)` u. Ä.) und Kommentare — keine Zuweisungen, und das
  Werkzeug darf sie nicht als solche zählen (dieselbe Regel wie AC-2, hier am echten Material).

Der Ausschnitt MUSS aus dem alten Stand `c36fec6` gezogen werden, nicht aus dem heutigen
`loose-ends`-Hauptzweig: Dort ist `processedAt` aus `Shared/Models/TaskItem.swift` bereits
entfernt (der reale Befund wurde dort inzwischen behoben) — eine Entnahme aus dem aktuellen Stand
wäre für den Nachweis wertlos, weil das Feld dann gar nicht mehr existiert.

**Pflicht: `PROVENANCE.md` neben der Fixture.** Sie hält fest: Herkunfts-Repository
(`henemm/loose-ends`), Commit (`c36fec6`), Entnahmedatum, die vier Original-Dateipfade und die
ausdrückliche Zusicherung „unverändert übernommen, keine Zeile angefasst". Dazu ein Warnsatz: **Die
Unveränderlichkeit ist der ganze Wert dieser Fixture — wer eine der vier Dateien anpasst, damit ein
Test grün wird, hat den Nachweis zerstört.** Der zugehörige Test darf sich bei fehlender Fixture
NICHT überspringen, sondern muss fehlschlagen (siehe AC-7).

## Expected Behavior

- **Input:** Sprachprofil-Name (`--lang`), Wurzelverzeichnis des zu scannenden Baums (`--root`,
  Default über `find_project_root()`), Config-Quelle für die Profile (`--config`, Default über
  `config_loader.load_config()`).
- **Output:** Eine Markdown-Tabelle auf stdout (oder in die per `--out` angegebene Datei), die
  **nur Felder mit mindestens einer Test-Zuweisung** führt (gelesen werden aus den Modelldateien
  alle Felder — AC-1 —, gelistet nur die mit Test-Zuweisung, siehe „Implementation Details"),
  aufsteigend nach Produktions-Schreibstellen sortiert, Felder mit 0 Schreibstellen oben und
  markiert. Exit-Code 0 bei erfolgreichem Lauf — auch wenn die Tabelle leer ist (dann mit einem
  Hinweistext statt einer leeren Tabelle).
- **Side effects:** Keine, außer der optionalen Ausgabedatei unter `--out`. Kein Schreibzugriff
  auf Workflow-State, keine Registrierung als Artefakt, kein Hook wird ausgelöst.

## Error Handling

- `--lang` ohne passendes Profil in `precondition_origins.profiles` → Exit 1, Meldung nennt die
  verfügbaren Profile.
- `--root` existiert nicht oder ist keine Verzeichnis → Exit 1 mit dem geprüften Pfad in der
  Meldung.
- Ein Profil-Feld fehlt oder ist kein gültiger regulärer Ausdruck (`re.compile` wirft) → Exit 1,
  Meldung nennt das betroffene Profil-Feld und den Compile-Fehler — kein stiller Fallback auf ein
  eingebautes Muster.
- Keine Modelldatei nach `model_globs` gefunden → Exit 0, Ausgabe ist der Hinweistext „Keine
  Modelldateien gefunden unter <model_globs>" statt einer leeren Tabelle.
- Keine Feldnamen aus den gefundenen Modelldateien extrahierbar → Exit 0, analoger Hinweistext.
- Datei nicht als UTF-8 lesbar (`UnicodeDecodeError`) oder Lesefehler (`PermissionError`) → Datei
  wird übersprungen, eine Warnzeile geht nach stderr, der Lauf wird fortgesetzt (fail-open pro
  Datei, damit eine einzelne kaputte Datei nicht den ganzen Bericht verhindert).

## Known Limitations

Die Textsuche ist heuristisch — eine Verdachtsliste für den menschlichen Prüfer, kein Beweis.
Konkret nicht erkannt werden:

- **Zuweisungen über Umwege.** Property-Wrapper mit `didSet`/`willSet`, Reflection-Zuweisungen
  (Swift `obj[keyPath: \.feld] = wert`, Python `setattr(obj, "feld", wert)`), Memberwise-
  Initializer (`Task(processedAt: ...)` ohne `=`-Zuweisungsform) und Setter-Methoden
  (`func setProcessedAt(_:)`) — sie haben keine `.feld =`-Form und werden nicht gezählt.
- **Berechnete Feldnamen.** Ein Feldname, der erst zur Laufzeit als String zusammengesetzt wird
  (`setattr(obj, field_name, wert)`), ist im Quelltext nicht als `.feld =` sichtbar.
- **Mehrfachtreffer je Zeile.** Kettenzuweisungen (`a.x = a.y = 1`) werden nur teilweise erkannt,
  da die zeilenweise Regex-Suche pro Feld unabhängig läuft.
- **Kommentierter Code.** Eine Zuweisung in einem Kommentar, die wie eine echte aussieht, wird
  mitgezählt — es gibt keine echte Tokenisierung, nur Textmuster.
- **Feldherkunft außerhalb der `model_globs`.** Geerbte Felder aus Basisklassen oder
  Protokoll-Extensions, die nicht unter den konfigurierten Modell-Pfaden liegen, werden nicht
  gefunden.
- **Warum das für den Zweck reicht:** Das Werkzeug ersetzt keine Entscheidung, es lenkt die aus
  Zeitgründen sonst unterbliebene Aufmerksamkeit des Prüfers auf die wahrscheinlichsten Zeilen.
  Falsch-positive Treffer kosten höchstens eine überflüssige Tabellenzeile; falsch-negative
  Treffer sind nicht schlechter als der heutige Zustand ganz ohne Werkzeug (der Prüfer prüft das
  heute überhaupt nicht). Die Machbarkeitsprobe in Issue #285 hat den bekannten Referenzfall trotz
  dieser Lücken ohne Kenntnis des Falls wiedergefunden.
- **Der eingefrorene Ausschnitt (AC-7) belegt Wirksamkeit an einem einzigen dokumentierten Fall,
  keine allgemeine Vollständigkeit.** `reference-c36fec6/` zeigt, dass das Werkzeug DIESEN echten
  Befund zuverlässig wiederfindet — nicht, dass es jeden künftigen Fall dieser Art findet. Die
  Fixture altert zudem: sie bildet den Sprachstand von Swift/`loose-ends` zum Zeitpunkt der
  Entnahme ab und wird nicht mit künftigen Sprachänderungen mitgepflegt. Das ist gewollt (sie ist
  eingefroren, siehe „Implementation Details"), begrenzt aber ihre Aussagekraft auf genau diesen
  einen Fall.
- **Die Größe der Verdachtsgruppe (AC-7/AC-8: „höchstens 12 Zeilen") ist eine Kalibrierung an
  gemessenem Material, keine allgemeine Naturkonstante.** Wie viele Felder mit ≤1
  Produktions-Schreibstelle in der Tabelle stehen, hängt davon ab, wie viele Felder das
  gescannte Modell überhaupt erklärt und wie breit der geprüfte Baum ist: ein sehr schmaler
  Ausschnitt (wenige Modelldateien) lässt die Gruppe künstlich klein oder — je nach Feldmischung
  — künstlich groß erscheinen. Am gemessenen Material lag die Gruppe bei 10 Zeilen (eingefrorener
  Ausschnitt) bzw. 9 Zeilen (voller Projektstand); der Schwellwert 12 ist bewusster Spielraum
  darüber, kein empirisch hergeleiteter Grenzwert für beliebige Projekte.

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt (AC-1 bis AC-7;
      AC-8 durch den unten genannten dokumentierten manuellen Nachweis)
- [ ] `python3 core/hooks/precondition_origins.py --lang swift --root
      tests/fixtures/precondition_origins/reference-c36fec6` liefert auf einem frischen Checkout,
      ohne externes Repository, eine Markdown-Tabelle mit dem erwarteten Befund am echten
      Ausschnitt (`processedAt` in der Verdachtsgruppe der Felder mit höchstens einer
      Produktions-Schreibstelle, diese Gruppe höchstens 12 Zeilen groß) — das ist das
      beobachtbare Ergebnis für AC-7, nicht nur ein grüner Testlauf
- [ ] AC-8: Die einmalige Gegenprobe gegen den vollständigen `/Users/hem/Developer/loose-ends@c36fec6`
      ist als Artefakt unter `docs/artifacts/feat-285/gegenprobe-c36fec6.md` abgelegt und zeigt
      `processedAt` ebenfalls in der Verdachtsgruppe (höchstens 12 Zeilen) — im vollen Rauschen
      von 89 Feldern
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf grün)
- [ ] `CHANGELOG.md` nennt das neue Werkzeug unter `[Unreleased]`

## Acceptance Criteria

- **AC-1:** Given einen Beispielbaum mit einer Modelldatei unter dem profilkonfigurierten
  `model_globs`-Muster (`Shared/Models/Task.swift` mit den vier Feldern `processedAt`,
  `energyRaw`, `title`, `notes` — keines davon dem Aufruf als Parameter übergeben) / When (a) die
  Feldextraktion (`extract_model_fields()`) direkt aufgerufen wird bzw. (b) das Werkzeug mit
  `--lang swift --root <Baum>` läuft / Then (a) liefert die Extraktion alle vier Feldnamen,
  ungefragt und vollständig — auch `notes`, das keine Testdatei je zuweist; (b) die
  Ausgabetabelle enthält dagegen nur `processedAt`, `energyRaw` und `title` — die drei mit
  mindestens einer Test-Zuweisung; `notes` fehlt, obwohl es aus dem Modell gelesen wurde (siehe
  „Implementation Details" → „Nur Felder mit Test-Zuweisung erscheinen in der Tabelle"). Beides
  zusammen belegt: gelesen werden alle Felder, gelistet nur die mit Test-Zuweisung.
  - Test: `test_ac1_extraction_reads_all_fields_without_naming_them`,
    `test_ac1_untested_field_extracted_but_not_listed` (Swift- und Python-Fixture)

- **AC-2:** Given Testdateien mit (a) echten Feld-Zuweisungen (`task.processedAt = Date(...)`),
  (b) einer lokalen Variablen gleichen Namens ohne Objektbezug (`let processedAt = Date()`) und
  (c) einem Vergleich (`task.processedAt == nil`) / When das Werkzeug läuft / Then zählt die
  Spalte „Test-Zuweisungen" nur (a); (b) und (c) erzeugen keinen Treffer.
  - Test: `test_ac2_local_variables_and_comparisons_produce_no_hit`,
    `test_ac2_only_dot_assignments_counted`

- **AC-3:** Given eine Produktionsdatei mit einer bekannten Zahl an Schreibstellen je Feld (im
  Fixture: 1× `processedAt`, 0× `energyRaw`, 3× `title`) / When das Werkzeug läuft / Then zeigt
  jede Tabellenzeile die korrekte Anzahl UND die `Datei:Zeile`-Fundstellen für das jeweilige Feld.
  - Test: `test_ac3_production_write_sites_counted_and_located`

- **AC-4:** Given die drei Felder aus dem Fixture mit unterschiedlicher Schreibstellen-Zahl
  (0, 1, 3) / When die Tabelle gerendert wird / Then stehen die Zeilen in der Reihenfolge
  `energyRaw` (0), `processedAt` (1), `title` (3) — aufsteigend nach Produktions-Schreibstellen.
  - Test: `test_ac4_table_sorted_ascending_by_production_writes`

- **AC-5:** Given `energyRaw` mit 0 Produktions-Schreibstellen neben Feldern mit ≥ 1 / When die
  Tabelle gerendert wird / Then steht `energyRaw` in der obersten Zeile und die Zelle
  „Produktions-Schreibstellen" enthält sichtbar den Hinweistext „keine Schreibstelle im
  Produktivcode".
  - Test: `test_ac5_zero_write_field_on_top_and_marked`

- **AC-6:** Given ein drittes, in `config.yaml` frei ergänztes Profil (Test-Fixture, kein
  Codeeingriff in `precondition_origins.py`) mit eigenem `model_globs`/`field_pattern`/
  `assignment_pattern` gegen einen passenden Beispielbaum / When das Werkzeug mit
  `--lang <neues-profil>` läuft / Then liefert es dieselbe Art Tabelle wie für Swift/Python, ohne
  dass der Testlauf eine Änderung an `precondition_origins.py` voraussetzt.
  - Test: `test_ac6_third_profile_addable_without_code_change`

- **AC-7:** Given den eingefrorenen echten Ausschnitt `tests/fixtures/precondition_origins/
  reference-c36fec6/` — UNVERÄNDERTE Originaldateien aus `henemm/loose-ends@c36fec6`
  (`Shared/Models/TaskItem.swift`, `Shared/Enrichment/EnrichmentWriter.swift`,
  `Shared/Enrichment/EnrichmentCoordinator.swift`, `LooseEndsTests/EnrichmentTests.swift`), nicht
  gegen nachgebaute Beispiele / When das Werkzeug mit `--lang swift --root
  tests/fixtures/precondition_origins/reference-c36fec6` läuft / Then erscheint `processedAt` in
  der **Verdachtsgruppe** — den Zeilen mit höchstens einer Produktions-Schreibstelle —, diese
  Gruppe umfasst höchstens 12 Zeilen (gemessen: 10), und die Zeile zu `processedAt` weist genau
  eine Produktions-Schreibstelle aus, `Shared/Enrichment/EnrichmentWriter.swift:94`. Der Schwellwert
  12 statt des gemessenen Werts 10 ist bewusster Spielraum: eine zulässige Verfeinerung von
  `field_pattern` (z. B. genauere Groß-/Kleinschreibungsregeln) darf die Gruppengröße geringfügig
  verschieben, ohne den Test zu brechen. Der Test läuft in der normalen Testsuite, überall und bei
  jeder künftigen Änderung, und schlägt fehl (nicht: wird übersprungen), wenn die Fixture fehlt.
  - Test: `test_ac7_real_frozen_excerpt_field_in_suspect_group`,
    `test_ac7_fixture_missing_fails_not_skips`

- **AC-8:** Given eine Wegwerf-Kopie des vollständigen `loose-ends`-Projektstands auf `c36fec6`
  (89 Modellfelder, davon 32 mit mindestens einer Test-Zuweisung — das volle Rauschen eines
  echten Projekts, nicht nur der vier-Dateien-Ausschnitt aus AC-7) / When das Werkzeug einmalig
  gegen diese Kopie läuft / Then steht `processedAt` in der Ergebnistabelle ebenfalls in der
  Verdachtsgruppe (höchstens eine Produktions-Schreibstelle, `Shared/Enrichment/
  EnrichmentWriter.swift:94`), die Gruppe umfasst höchstens 12 Zeilen (gemessen: 9); das Ergebnis
  wird als Artefakt unter `docs/artifacts/feat-285/gegenprobe-c36fec6.md` abgelegt. Unterschied zu
  AC-7: AC-7 prüft an einem schmalen, eingefrorenen echten Ausschnitt, dass das Werkzeug den Fall
  grundsätzlich findet — automatisiert, jederzeit wiederholbar. AC-8 prüft dieselbe Aussage
  zusätzlich im vollen Rauschen eines realen Projekts — einmalig angestoßen, nicht Teil der
  automatisierten Suite (ein vollständiger Fremd-Repository-Checkout ist kein CI-taugliches
  Testfixture).
  - Nachweis (einmalig, **nicht** Teil der automatisierten Suite): manueller Lauf gegen den
    echten Referenzbaum `/Users/hem/Developer/loose-ends`, Stand `c36fec6`, in einer
    Wegwerf-Kopie — siehe „Test Plan" → „AC-8: Gegenprobe am vollständigen Referenzbaum".

## Test Plan

Automatische Tests (jeweils an eine AC oben gebunden):
- `python3 -m pytest tests/test_precondition_origins.py -q` (AC-1 bis AC-6 gegen die
  nachgebauten Fixtures `swift/`/`python/`; **AC-7 gegen den eingefrorenen echten Ausschnitt**
  `reference-c36fec6/` — läuft überall, ohne externes Repository, prüft die Zugehörigkeit zur
  Verdachtsgruppe (höchstens 12 Zeilen, ≤1 Produktions-Schreibstelle) statt eines Rangplatzes, und
  schlägt fehl statt sich zu überspringen, wenn die Fixture fehlt)
- Regressionslauf: `python3 -m pytest tests/ -q`
- Drift-Checks: `python3 scripts/sync_skills.py --check`,
  `python3 scripts/ci_spec_gate.py --base origin/main`

### AC-8: Gegenprobe am vollständigen Referenzbaum (manuell, nicht Teil der automatisierten Suite)

AC-8 verlangt zusätzlich zu AC-7 den Nachweis, dass `processedAt` auch im vollen Rauschen eines
echten Projekts (89 Modellfelder, davon 32 mit mindestens einer Test-Zuweisung) in der
Verdachtsgruppe steht — dafür braucht es den vollständigen `loose-ends`-Stand, nicht nur den
vier-Dateien-Ausschnitt aus `reference-c36fec6/`. Dieser volle Checkout ist lokal vorhanden
(`/Users/hem/Developer/loose-ends`), existiert aber in der CI nicht, und sein Stand `c36fec6` ist
im heutigen `loose-ends`-Hauptzweig bereits behoben (`docs/context/
feat-273-erreichbarkeitspruefung.md`, Abschnitt „Referenzfall für die Abnahmebedingung"). Dieser
Lauf ist deshalb **kein automatisierter Test**, sondern ein einmalig angestoßener, dokumentierter
Nachweis:

1. Wegwerf-Kopie von `/Users/hem/Developer/loose-ends` auf Stand `c36fec6` anlegen (z. B. `git
   worktree add` in einen Scratch-Pfad, `git checkout c36fec6` dort). Dieselbe Kopie liefert auch
   die vier Originaldateien für `reference-c36fec6/` (Schritt vorgelagert, einmalig bei der
   Erstellung dieser Scheibe): Dateien 1:1 kopieren, keine Zeile ändern, danach `PROVENANCE.md`
   mit Repository, Commit `c36fec6`, Entnahmedatum, den vier Original-Pfaden und der Zusicherung
   „unverändert übernommen" schreiben.
2. `python3 core/hooks/precondition_origins.py --lang swift --root <Wegwerf-Kopie> --config
   <dieses-Repo>/config.yaml --out docs/artifacts/feat-285/gegenprobe-c36fec6.md` in diesem Repo
   ausführen — gegen den VOLLEN Projektstand, nicht gegen `reference-c36fec6/`.
3. Prüfen, dass `processedAt` mit 1 Produktions-Schreibstelle
   (`Shared/Enrichment/EnrichmentWriter.swift:94`) in der Verdachtsgruppe steht (gemessen: 9
   Zeilen mit ≤1 Produktions-Schreibstelle, Schwelle ≤12) — trotz 31 weiterer Felder mit
   Test-Zuweisung im selben Lauf.
4. Das Ergebnis (die vollständige Tabelle, nicht nur die eine Zeile) bleibt als Artefakt unter
   `docs/artifacts/feat-285/gegenprobe-c36fec6.md` im Repo liegen und wird in der Definition of
   Done abgehakt, nicht in der Testsuite.

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Kein neues Architektur-Muster, vier bewusste Festlegungen mit je einer ernsthaft
  erwogenen und abgelehnten Alternative:

  1. **Regelweg (Regex + Dateisuche) statt echtem Parsen.** Erwogene Alternative: SwiftSyntax für
     Swift, Pythons `ast`-Modul für Python. Abgelehnt, weil (a) SwiftSyntax eine
     Swift-Toolchain-Abhängigkeit in einen reinen Python-Hooks-Ordner zöge — ein Bruch mit „keine
     neuen Dependencies ohne Freigabe" (CLAUDE.md) und mit der Tatsache, dass dieses Framework
     sprachneutral bleiben muss; (b) `ast` nur Python abdeckt, Swift bräuchte trotzdem einen
     zweiten, völlig andersartigen Codepfad — das widerspricht AC-6 („ein drittes Profil ohne
     Codeänderung"), denn ein echter Parser lässt sich nicht per Config-Eintrag hinzufügen,
     sondern nur per neuem Parser-Adapter im Code; (c) die Machbarkeitsprobe in Issue #285 hat den
     realen Fall bereits ohne Parsing gefunden — die Zusatzgenauigkeit eines echten Parsers zahlt
     sich für eine Verdachtsliste (kein Beweis, siehe „Known Limitations") nicht aus. Kosten des
     gewählten Wegs: die in „Known Limitations" benannten blinden Flecken (Reflection, Setter,
     berechnete Feldnamen).

  2. **Eigenständiges Programm statt direktem Gate/Hook.** Erwogene Alternative: das Werkzeug
     sofort als `PreToolUse`- oder `Stop`-Hook registrieren, analog `adversary_dialog.py`.
     Abgelehnt für diese Scheibe, weil Issue #285 das ausdrücklich ausschließt („Kein Gate, keine
     Pflicht. Diese Scheibe verändert an keinem angebundenen Projekt etwas") und die Analyse in
     T2 (#286) bereits eine eigene, größere Scheibe dafür vorsieht (Formprüfung, Hash-Bindung nach
     dem Muster von `## Geprüfte Dateien`, Kill-Switch). Ein Gate ab dieser Scheibe würde sofort
     jeden Abschluss in jedem installierten Projekt betreffen, ohne dass die Pflichtsektion im
     Prüfprotokoll überhaupt existiert — das wäre ein Blocker ohne Gegenstück. Kosten des
     gewählten Wegs: das Werkzeug hat bis #286 keinerlei erzwingende Wirkung, es muss von Hand
     aufgerufen werden.

  3. **Konsumiert in einer späteren Phase (Prüfdialog, T2) statt vorgezogen in `/20-analyse`.**
     Erwogene Alternative: das Werkzeug schon in der Analyse-Phase laufen lassen, bevor Tests
     existieren. Abgelehnt, weil zu diesem Zeitpunkt die Spalte „Test-Zuweisungen" leer wäre — die
     Tests, die die Vorbedingung herstellen, werden erst in `phase5_tdd_red` geschrieben. Der
     Vergleich „viele Test-Zuweisungen gegen wenige Produktions-Schreibstellen" trägt nur, wenn
     beide Seiten existieren. Diese Entscheidung betrifft ohnehin die Integration (wo im Ablauf
     das Werkzeug aufgerufen wird), nicht diese Scheibe: `precondition_origins.py` bleibt
     aufruf-agnostisch (reines CLI-Programm mit `--root`/`--out`), sodass T2 später frei
     entscheiden kann, ob es im Prüfdialog oder anderswo eingehängt wird, ohne dass diese Scheibe
     erneut angefasst werden muss.

  4. **Verdachtsgruppe (≤1 Produktions-Schreibstelle, Größenschwelle) statt Rangplatz („oberste
     fünf Zeilen") als Abnahmemaß für AC-7/AC-8.** Erwogene und abgelehnte Alternative: die
     Sortierregel oder die Tie-Break-Logik so lange nachschärfen, bis `processedAt` tatsächlich
     unter den obersten fünf Zeilen landet — z. B. durch ein zusätzliches Gewicht für das
     Verhältnis Test-Zuweisungen zu Schreibstellen. Abgelehnt, weil das exakt das Muster wäre,
     gegen das sich Epic #273 richtet: eine Prüfung so lange verbiegen, bis der bekannte Fall
     besteht, statt die Prüfung an dem zu messen, was sie tatsächlich leisten kann. Die
     Nachmessung am echten Material (siehe „Purpose") zeigt, dass „oberste fünf Zeilen" weder am
     eingefrorenen Ausschnitt (Rang 7 von 18) noch am vollen Stand (Rang 8 von 32) erreichbar ist,
     ohne eine willkürliche Sonderregel für genau diesen einen Fall einzubauen — eine Regel, die
     an jedem anderen Projekt wieder falsch läge. Die Verdachtsgruppe misst stattdessen das
     eigentliche Signal direkt (höchstens eine Schreibstelle im Betrieb, mindestens ein Test
     verlässt sich darauf) und bleibt an einer Größenschwelle überprüfbar, ohne die Sortierung an
     einen einzelnen bekannten Fall anzupassen. Kosten: die Prüfung ist weniger scharf als „ganz
     oben" — sie bestätigt Zugehörigkeit zu einer Gruppe von bis zu zwölf Zeilen, nicht einen
     Platz unter den ersten fünf; das ist laut „Known Limitations" eine Kalibrierung an
     gemessenem Material, keine Naturkonstante.

## Changelog

- 2026-09-28: Initial spec created
- 2026-09-28: AC-7 auf eingefrorenen echten Ausschnitt umgestellt, AC-8 ergänzt (PO-Entscheidung)
- 2026-09-28: AC-7/AC-8 von Rangplatz auf Verdachtsgruppe umgestellt; Tabelle führt nur Felder mit
  Test-Zuweisung (beides PO-Entscheidung nach Messung am echten Stand)
