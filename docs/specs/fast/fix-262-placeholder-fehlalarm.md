# Fast Track: TDD-Gate blockt an seiner eigenen Platzhalter-Warnung (#262)

## Problem

`tdd_enforcement.py` wies in `phase6_implement`/`phase6b_adversary` jeden `Edit`/`Write` ab mit
„Artefakt enthaelt Platzhalter-Text", obwohl das registrierte RED-Artefakt eine echte,
unveraenderte `pytest`-Ausgabe war. Live aufgetreten am 2026-09-27 im Vorgang
`fix-147-validierung-abstufen`.

Ursache: `_PLACEHOLDER_RE` (`\b(TODO|PLACEHOLDER|FIXME)\b` u. a.) lief ueber den KOMPLETTEN
Artefakt-Inhalt. Prueft ein RED-Test den Inhalt eines Framework-Dokuments, schreibt `pytest` bei
gescheiterter Assertion das ganze Dokument in die Ausgabe — und `skills/40-tdd-red/SKILL.md`
enthaelt die Zeile „❌ **Placeholder artifacts** → Hook will block implementation". Das Gate
erklaerte seine eigene Warnung vor gefaelschten Artefakten zum Beweis fuer ein gefaelschtes
Artefakt.

Am 2026-09-28 am echten Ablauf nachgestellt: Testdatei mit
`assert "NOCH-NICHT-IMPLEMENTIERTE-REGEL" in SKILL.read_text(), content`, `pytest` ausgefuehrt,
Ausgabe (13 940 Bytes) als `test_output`-Artefakt an `_validate_artifact()` gegeben → Rueckgabe
„Artefakt enthaelt Platzhalter-Text". Volltextsuche im Artefakt: genau zwei Treffer des Musters,
beide auf `E `-Zeilen (`E   - Be a **real file** (not placeholder)` und
`E   ❌ **Placeholder artifacts** → …`), also beide in dem Bereich, den `pytest` selbst als
Zitat markiert. Kein Treffer im Rahmen, den `pytest` erzeugt.

Abgrenzung: nicht #89 (Wort als Teilstring in einem Bezeichner, per `\b`-Grenzen geloest) und
nicht #73 (TAP-Summenzeilen von `node --test`). Gleiche Familie wie Epic #199.

## Scope

- `core/hooks/tdd_enforcement.py`: Die Platzhalter-Suche sieht nur noch den RAHMEN, den der
  Runner selbst erzeugt. Vom Runner ZITIERTER Fremdinhalt ist ausgenommen: `E `-Zeilen
  (Assertion-Detail/longrepr), `> `-Zeilen (ausgefuehrte Quellzeile) und aufgefangene
  Ausgabebloecke (`---- Captured stdout call ----` bis zum naechsten Abschnittskopf). Neue
  Helfer `_iter_frame_lines()`, `_find_placeholder()`; neue Muster `_QUOTED_LINE_RE`,
  `_CAPTURED_HEADER_RE`, `_SECTION_HEADER_RE`. Vorbild ist `_TAP_SUMMARY_RE` im selben Hook (#73).
- Blockier-Meldung nennt Zeilennummer und Fundstelle. Im Livefall wies sie nur die Datei aus —
  das war der eigentliche Zeitfresser bei der Ursachensuche.
- CHANGELOG unter `[Unreleased] → Fixed`. Kein Versions-Bump: `plugin.json` bleibt bei 3.33.0,
  `skills/` damit unveraendert. Ein Bump wuerde die Release-Bereitschaftspruefung ausloesen
  (CHANGELOG-Release-Abschnitt, README- und CLAUDE.md-Marker) — das ist eine Release-Aufgabe,
  nicht Teil dieser Korrektur. Vorbild: PR #271 (#260).
- **Nicht enthalten:** Vorschlag (2) aus dem Vorgang — ein Artefakt mit erkennbarer
  Test-Zusammenfassung pauschal als echt durchwinken. Das haette das Gate geoeffnet: eine
  erfundene Datei mit gefaelschter Summenzeile waere trotz „TODO: echte Ausgabe einfuegen"
  durchgekommen. Der Fehlalarm verschwindet ohne diese Lockerung.
- **Nicht enthalten:** Vorschlag (3) — das Wortmuster verengen. Verschiebt die Grenze nur;
  `TODO` und `FIXME` stehen als eigene Woerter auch in echten Quellcode-Dumps.
- **Nicht enthalten:** Die Platzhalter-Pruefung ganz streichen (als Alternative vorgelegt und
  vom PO abgelehnt). Sie ist das einzige Mittel gegen ein glatt erfundenes Artefakt.

## Definition of Done

Eine echte `pytest`-Ausgabe, die den Inhalt eines Framework-Dokuments zitiert, wird als gueltiges
RED-Artefakt akzeptiert. Ein Platzhalter im Artefakt-Rahmen blockt unveraendert. Die
Blockier-Meldung benennt die ausloesende Zeile. Gesamte Suite gruen.

## Acceptance Criteria

- **AC-1:** Given die am 2026-09-28 nachgestellte, echte `pytest`-Ausgabe mit eingebettetem
  `skills/40-tdd-red/SKILL.md`, When `_validate_artifact()` sie prueft, Then ist das Ergebnis
  `None` (gueltig) — vorher: „Artefakt enthaelt Platzhalter-Text".
- **AC-2:** Given ein Platzhalter-Wort auf einer `E `-Zeile (Assertion-Detail), Then loest es
  die Platzhalter-Pruefung nicht aus.
- **AC-3:** Given ein Platzhalter-Wort auf einer `> `-Zeile (zitierte Quellzeile), Then loest es
  die Pruefung nicht aus.
- **AC-4:** Given ein Platzhalter-Wort innerhalb eines `Captured stdout call`-Abschnitts, Then
  loest es die Pruefung nicht aus; der Abschnitt endet erst am naechsten echten Abschnittskopf,
  nicht an einer zitierten `---`-Zeile (YAML-Frontmatter).
- **AC-5:** Given ein Platzhalter im Artefakt-Rahmen (`PLACEHOLDER - replace with actual test
  output`, `<test_output>`, `TODO: …` neben einer echten Summenzeile), Then blockt das Gate
  weiterhin — der Fix darf das Gate nicht oeffnen.
- **AC-6:** Given ein blockierendes Artefakt, When die Meldung erzeugt wird, Then enthaelt sie
  Zeilennummer und den Text der ausloesenden Zeile.

## Test Plan

`tests/test_tdd_enforcement_embedded_content_262.py`, 8 Tests (Stilvorlage:
`tests/test_tdd_enforcement_placeholder_wordboundary_89.py`, direkter Aufruf von
`_validate_artifact` mit echten Dateien in `tmp_path`):

- `TestEmbeddedDocumentContentNotTreatedAsPlaceholder` — 4 Tests: der woertliche Auszug des
  nachgestellten Livefalls, Platzhalter auf `E `-Zeile, `TODO`/`FIXME` auf `> `-Zeile,
  Platzhalter im `Captured stdout call`-Abschnitt (AC-1 bis AC-4)
- `TestFabricatedArtifactsStillBlocked` — 3 Tests als Gegenprobe: freistehender Platzhalter,
  `TODO`-Zeile neben echter Summenzeile, Klammer-Muster `<test_output>` (AC-5)
- `TestBlockMessageNamesOffendingLine` — 1 Test: Meldung enthaelt „Zeile 2" und den Zeilentext
  (AC-6)

Nachweis:

- Livefall vor dem Fix direkt nachgestellt: `_validate_artifact()` auf die echte 13 940-Byte-
  `pytest`-Ausgabe → „Artefakt enthaelt Platzhalter-Text"
- RED vor dem Fix: 5 der 8 neuen Tests rot; die 3 gruenen sind die Gegenproben aus AC-5 und
  sichern unveraendertes Blockier-Verhalten ab
- GREEN nach dem Fix: 8 passed
- Derselbe Livefall nach dem Fix erneut geprueft: Ergebnis `None`
- Gesamte Suite nach dem Fix: 1382 passed, 25 skipped

Artefakte: `docs/artifacts/fix-262-placeholder-fehlalarm/test-red-output.txt` (RED) und
`test-green-full-suite.txt` (GREEN, gesamte Suite).
