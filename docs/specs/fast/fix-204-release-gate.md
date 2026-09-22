# Mini-Spec: Ursache der Release-Blockade beheben (#204)

## Problem

`release_check.py::latest_changelog_version` gibt `None` zurück, sobald irgendeine
`## [Unreleased]`-Überschrift existiert — auch eine leere. Nach jedem Release fügen
Beitragende gemäß Keep-a-Changelog-Konvention eine leere `## [Unreleased]`-Platzhalter-
Überschrift für die nächste Arbeit wieder ein (siehe `CHANGELOG.md`-Kopfzeile: „The format
is based on Keep a Changelog"). Genau das hat `release.yml` zweimal (3.27.1, 3.27.2) still
zum Scheitern gebracht: der Job wurde rot, niemand hat in die Actions geschaut, und
`plugin.json` zeigte eine Version, die nie getaggt wurde.

PR #203 hat die Sofortmaßnahme umgesetzt (leeren Block entfernt, 3.28.0 jetzt getaggt) —
das behebt nur den Einzelfall. Der nächste Beitragende, der nach einem Release wieder eine
leere `## [Unreleased]`-Zeile stehen lässt, steht erneut hier.

## Was ändert sich

Löst beide von Issue #204 vorgeschlagenen Richtungen (Empfehlung des Issues: „1 + 2"):

1. **`latest_changelog_version` überspringt einen leeren `## [Unreleased]`-Abschnitt.**
   Leer heißt: zwischen der Überschrift und der nächsten Versions-Überschrift steht nur
   Leerraum. Ein *gefüllter* Block blockiert weiterhin — das ist die ursprüngliche,
   bewusste Absicht (kein Release aus unvollständig dokumentiertem Stand).
2. **Der Fehlschlag wird vor dem Merge sichtbar, nicht erst danach in den Actions.**
   Neuer Job `release-readiness` in `.github/workflows/ci.yml` (`pull_request`-Trigger,
   wie der bestehende `spec-gate`-Job). Er lohnt sich nur für PRs, die tatsächlich eine
   Release-Version vorbereiten (Version in `plugin.json` weicht vom Basis-Branch ab) —
   ein gewöhnlicher Feature-/Bugfix-PR mit gefülltem `Unreleased`-Abschnitt und
   unveränderter Version ist der Normalfall und soll nicht rot werden.
   - Kein Versions-Bump im Diff → Job meldet „kein Versions-Bump, Gate übersprungen" und
     ist grün.
   - Versions-Bump im Diff → dieselben inhaltlichen Prüfungen wie `release_check.py`
     laufen gegen den PR-Stand: Version (mit dem Fix aus Punkt 1), README, Skills, Tag-frei.
     Die drei Prüfungen, die nur auf `main` selbst Sinn ergeben (Branch, sauberer
     Arbeitsbaum, Abgleich mit origin), entfallen — sie würden auf jedem Feature-Branch
     grundlos rot werden.
3. `scripts/release_check.py`: neuer CLI-Modus `--pr-gate --base <ref>`, der genau diese
   Unterscheidung trifft; `main()` nutzt weiterhin die volle Prüfliste unverändert.

## Was darf sich nicht ändern

- Ein *gefüllter* `## [Unreleased]`-Block blockiert das Release auf `main` weiterhin —
  das ist Absicht, kein Bug.
- `release.yml` (Post-Merge-Automatik) bleibt inhaltlich unverändert, profitiert aber vom
  Fix in `latest_changelog_version`.
- Gewöhnliche PRs ohne Versions-Bump werden vom neuen Job nicht rot.
- `release_check.py main()` (der volle, main-spezifische Lauf) bleibt unverändert.

## Wo ich für dich entschieden habe

- **Kein Session-Banner-Hinweis zusätzlich.** Issue #204 nennt das als dritte Option
  („dieselbe Denkrichtung wie #185"). Der PR-Gate greift zuverlässig bei jedem
  Versions-Bump-Versuch — genau dem Moment, in dem der Fehler entsteht. Ein zusätzlicher
  Banner-Hinweis würde nur greifen, wenn ohnehin schon jemand im Framework-Repo eine
  Session startet, was zwischen zwei Release-Versuchen Wochen dauern kann. Bei Bedarf
  eigenes Issue, aber der PR-Gate deckt den eigentlichen Fehlerfall vollständig ab.
- **Gate nur bei Versions-Bump aktiv**, nicht bei jedem PR: ein gefüllter
  `Unreleased`-Abschnitt ohne Versions-Bump ist der Normalzustand fast jedes PRs
  (z. B. dieser hier) und darf nicht rot werden.

## Acceptance Criteria

- **AC-1:** Given ein CHANGELOG mit leerer `## [Unreleased]`-Überschrift direkt über einem
  Versions-Eintrag, When `latest_changelog_version` läuft, Then liefert es die Version des
  darunterliegenden Eintrags (nicht `None`).
- **AC-2:** Given ein CHANGELOG mit *gefülltem* `## [Unreleased]`-Abschnitt, When
  `latest_changelog_version` läuft, Then liefert es weiterhin `None`.
- **AC-3:** Given ein PR ohne Versions-Änderung in `plugin.json`, When der
  `release-readiness`-Job läuft, Then ist er grün und meldet „kein Versions-Bump".
- **AC-4:** Given ein PR mit Versions-Bump und einem CHANGELOG-Stand, der
  `release_check.py` auf `main` zum Scheitern gebracht hätte (z. B. leerer Block blockiert
  fälschlich, oder README-Version weicht ab), When der `release-readiness`-Job läuft, Then
  ist er rot und nennt den Grund.
- **AC-5:** Given ein PR mit korrektem Versions-Bump (Version in plugin.json == oberster
  CHANGELOG-Eintrag, README stimmt, Tag noch frei), When der Job läuft, Then ist er grün.

## Manuelle Test-Schritte

1. `python3 scripts/release_check.py --pr-gate --base origin/main` lokal auf diesem Branch
   ausführen (kein Versions-Bump) → „übersprungen".
2. Lokal `plugin.json` testweise auf eine neue Version setzen, CHANGELOG unverändert lassen
   → Gate rot mit erkennbarem Grund. Danach zurücksetzen.

## Test Plan

- `tests/test_release_check.py` (neu, falls noch keine Tests für dieses Skript existieren —
  prüfen): Tests für leeren vs. gefüllten `Unreleased`-Block (AC-1/AC-2) und für den
  `--pr-gate`-Modus (AC-3–AC-5, mit Fake-Git-Repo in `tmp_path`).
- Volle Suite `python3 -m pytest tests/`.
