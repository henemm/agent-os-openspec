# Herkunft dieser Fixture

**Repository:** `henemm/loose-ends`
**Commit:** `c36fec6`
**Entnahmedatum:** 2026-09-28

## Entnommene Originalpfade

- `Shared/Models/TaskItem.swift`
- `Shared/Enrichment/EnrichmentWriter.swift`
- `Shared/Enrichment/EnrichmentCoordinator.swift`
- `LooseEndsTests/EnrichmentTests.swift`

Entnommen mit `git -C /Users/hem/Developer/loose-ends show c36fec6:<Pfad>` je Datei,
1:1 in dieselbe relative Verzeichnisstruktur unter diesem Ordner geschrieben.

## Zusicherung

**Unverändert übernommen — keine Zeile angefasst.** Kein Reformatieren, kein
Kürzen, keine eingefügten Kommentare, keine Anpassung von Einrückung oder
Zeilenenden.

## ⚠️ Warnung — nicht anfassen

**Die Unveränderlichkeit ist der ganze Wert dieser Fixture.** Wer eine der
vier Dateien anpasst, damit ein Test grün wird, hat den Nachweis zerstört.
Der zugehörige automatisierte Test (`test_ac7_*` in
`tests/test_precondition_origins.py`) beweist nur dann etwas, wenn dieses
Material exakt dem realen, historischen Zustand entspricht — nicht einem
nachträglich passend gemachten Ausschnitt.

## Was dieser Ausschnitt belegt

Ein Feld (`processedAt`), das im Betrieb genau einmal geschrieben wird
(`Shared/Enrichment/EnrichmentWriter.swift:94`, hinter einer Bedingung),
gegen eine Testdatei (`LooseEndsTests/EnrichmentTests.swift`, 684 Zeilen),
die `processedAt` 15-mal nennt. `Shared/Enrichment/EnrichmentCoordinator.swift`
ist Teil des Ausschnitts, damit die Zählung der Produktions-Schreibstellen
über den vollen `production_globs`-Bereich läuft, statt künstlich auf eine
einzige Datei verengt zu sein.

Dies ist der reale Referenzfall aus Issue #285, an dem die grundsätzliche
Wirksamkeit des Werkzeugs gezeigt wird — kein Beleg für Vollständigkeit
gegenüber künftigen Fällen (siehe Spec `docs/specs/feat-285-precondition-origins.md`,
Abschnitt „Known Limitations").
