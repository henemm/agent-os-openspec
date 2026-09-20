# Fast Track: `framework_version.json` behauptet im Plugin-Modus eine Version, die sie nicht kennt (3.26.0)

## Problem

In gregor_zwanzig stand `.claude/framework_version.json` auf `3.4.13`, während das Plugin 3.25.1
auslieferte. Kein Übertragungsfehler, sondern Bauart:

- `setup.py::install_plugin_mode` schreibt `framework_version: FRAMEWORK_VERSION` zusammen mit
  `plugin_mode: True`. Das ist die Version des `setup.py`, das zufällig gerade lief.
- Danach laufen alle Aktualisierungen über `claude plugin update`. Das rührt diese Datei nie an.
- `migrate_to_plugin.py::migrate` setzt beim Umstellen `plugin_mode: True`, lässt die alte
  Copy-Mode-Zahl aber stehen — genau der Zustand von gregor_zwanzig.

Die Zahl ist damit ab der ersten Plugin-Aktualisierung falsch, in **jedem** Plugin-Modus-Projekt.
Die README empfiehlt ausdrücklich, sie zu lesen („Check installed version"). Gleiche Fehlerklasse
wie #155: eine Auskunft, die wie eine Messung aussieht und keine ist.

Im Copy-Modus ist die Zahl richtig und bleibt: dort hat `setup.py` die Dateien selbst kopiert, die
Datei **ist** dort die Auskunftsquelle.

## Scope

- `setup.py`: neue Konstanten `PLUGIN_MODE_VERSION_SOURCE` / `PLUGIN_MODE_VERSION_NOTE`;
  `install_plugin_mode` schreibt `framework_version: null` plus Quellenangabe statt einer Zahl
- `migrate_to_plugin.py`: beim Markieren von `plugin_mode` wird eine vorhandene Copy-Mode-Zahl
  entfernt — auch dann, wenn `plugin_mode` bereits gesetzt ist (sonst braucht jedes betroffene
  Bestandsprojekt Handarbeit)
- `README.md`: „Check installed version" bekommt die Plugin-Modus-Fallunterscheidung
- Nicht enthalten: `setup.py::update_project` (Zeile ~806) verliert beim `--update` das Feld
  `plugin_mode` komplett und stuft ein Plugin-Projekt damit still auf Copy-Modus zurück. Eigener
  Gegenstand, eigenes Fehlerbild, eigener Testbedarf → eigenes Issue
- Nicht enthalten: die Datei bleibt reine Dokumentation. Kein Hook und kein Script liest sie
  (geprüft: nur `setup.py`, `migrate_to_plugin.py` und die README nennen sie)

## Definition of Done

Ein Plugin-Modus-Projekt trägt in `framework_version.json` keine Versionsnummer mehr, sondern die
Angabe, wo die geladene Version wirklich abzulesen ist. Copy-Modus-Projekte behalten ihre Zahl.

## Acceptance Criteria

- **AC-1:** Given `install_plugin_mode` läuft, When die Datei geschrieben wird, Then ist
  `framework_version` `null` und `plugin_mode` `true`.
- **AC-2:** Given `install_plugin_mode` läuft, When die Datei geschrieben wird, Then nennt sie mit
  `version_source: "plugin"` und einem `note`-Feld die wirkliche Quelle (`claude plugin list` bzw.
  den Phasen-Marker aus 3.24.0).
- **AC-3:** Given ein Copy-Modus-Projekt, When `update_project` läuft, Then wird weiterhin die
  installierte Version festgehalten — dort ist die Datei die Auskunftsquelle.
- **AC-4:** Given ein Copy-Modus-Projekt mit alter Zahl, When `migrate_to_plugin --apply` läuft,
  Then ist die Zahl entfernt und die Quellenangabe gesetzt.
- **AC-5:** Given ein Trockenlauf, When `migrate_to_plugin` ohne `--apply` läuft, Then ändert sich
  nichts an der Datei.
- **AC-6:** Given ein bereits umgestelltes Projekt, When die Migration erneut läuft, Then bleibt
  das Ergebnis unverändert (Idempotenz).
- **AC-7:** Given ein Projekt mit `plugin_mode: true` **und** alter Zahl (der Fundfall
  gregor_zwanzig), When die Migration läuft, Then wird die Zahl entfernt — ein gesetztes
  `plugin_mode` darf die Falschauskunft nicht konservieren.

## Test Plan

- `tests/test_framework_version_plugin_mode.py`: 7 Tests (AC-1 bis AC-7), echte Projektordner auf
  `tmp_path`, echte Aufrufe von `install_plugin_mode`, `update_project` und `migrate`.
- RED vor dem Fix: 5 von 7 rot; grün blieben genau die beiden Gegenproben (Copy-Modus behält
  seine Zahl, Trockenlauf ändert nichts) — die Richtung des Fixes ist damit eingegrenzt.
- Volle Suite nach dem Fix.

## ADR

**Entscheidung:** Die Zahl wird entfernt, nicht nachgezogen.

**Alternative:** `framework_version` in gregor_zwanzig auf 3.25.1 setzen. Verworfen — sie wäre beim
nächsten `claude plugin update` wieder falsch. Das ist dieselbe Falle, nur später.

**Alternative 2:** Die Datei beim Plugin-Update automatisch aktualisieren lassen. Nicht möglich:
`claude plugin update` ist Claude Codes eigener Mechanismus, das Framework hängt sich dort nicht
ein. Eine Zahl, die niemand pflegen kann, gehört nicht in die Datei.

**Kein Migrationspfad nötig:** Kein Hook und kein Script liest das Feld; es ist reine
Dokumentation für Menschen. Die Änderung ist trotzdem MINOR und nicht PATCH, weil sich das Format
einer Datei ändert, die Konsumenten-Projekte bereits besitzen — das soll im CHANGELOG sichtbar
sein und nicht als stiller Patch durchlaufen.
