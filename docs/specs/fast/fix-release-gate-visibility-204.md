# Fast Track: Release-Automatik scheitert nicht mehr still (#204, 3.28.1)

## Problem

Am 21./22.09.2026 lag `main` auf 3.27.2, der letzte Tag war `agent-os-openspec--v3.27.0`. Zwei
fertige, dokumentierte, als erledigt geschlossene Versionen wurden **nie veröffentlicht** — die
Konsumenten-Projekte liefen weiter auf 3.27.0, ohne den Freigabe-Fix (#170) und ohne die
Fußzeilen-Änderung (#174). Innerhalb von zwölf Stunden trat derselbe Fehlschlag dreimal auf
(Release-Läufe #43, #44, #45). Aufgefallen ist er nur, weil bei der Abnahme von Epic #198 gezielt
nachgesehen wurde.

Zwei Ursachen:

1. **Ein leerer `## [Unreleased]`-Abschnitt blockierte das Release.** `latest_changelog_version`
   liefert `None`, sobald der oberste Eintrag `Unreleased` heißt; `release.yml` bricht daran ab.
   Die Absicht ist richtig — ein Release mit offenem, *gefülltem* Unreleased-Block wäre
   unvollständig dokumentiert. Die Umsetzung war zu grob: Die leere Überschrift ist der
   Keep-a-Changelog-Platzhalter, den jeder stehen lässt, und dokumentiert nichts.
2. **Der Fehlschlag war unsichtbar.** `release_check.py` lief ausschließlich in `release.yml`, also
   *nach* dem Merge. Der Job wird rot, aber nach einem Merge schaut niemand in die Actions.

Der zweite Punkt ist der schwerwiegendere: Ein Schutzmechanismus, dessen Versagen niemand sieht,
ist schlechter als keiner — er erzeugt begründetes Vertrauen in einen Zustand, den er nicht
absichert.

## Scope

- `scripts/release_check.py`:
  - `latest_changelog_version` überspringt einen **leeren** `[Unreleased]`-Abschnitt; ein
    **gefüllter** blockiert unverändert
  - neu: `version_tuple`, `latest_tagged_version`, `main_plugin_version`, `all_tags`,
    `check_main_release_published`
  - neu: Schalter `--content-only` — führt nur die inhaltlichen Prüfungen aus
  - Prüfungen getrennt in *Zustand* (Branch/Arbeitsbaum/Abgleich, nur beim Release) und *Inhalt*
    (Version/README/Skills/Release, auf jedem Branch)
- `.github/workflows/ci.yml`: neuer Job `release-readiness`, nur auf Pull Requests, mit
  `fetch-depth: 0`
- Version 3.28.1, `skills/` neu erzeugt, README, CHANGELOG
- **Nicht enthalten:** Eine Warnung im Session-Banner, wenn der letzte Tag hinter `plugin.json`
  liegt (Lösungsrichtung 2b des Issues). Sie überschneidet sich mit #185, kostet einen
  `git fetch` bei jedem Sitzungsstart und deckt denselben Fall ab, den der CI-Job jetzt vor dem
  Merge abfängt. Zurückgestellt, bis sich zeigt, dass eine Lücke bleibt.
- **Nicht enthalten:** Die `Tag`-Prüfung wandert *nicht* in den Inhaltsmodus. Ein Pull Request ohne
  Versions-Bump ist zulässig — das Release meldet dann „bereits veröffentlicht" und tut nichts.
  Ihn zu blockieren wäre ein neues Gate ohne Anlass, und genau davor warnt Epic #199.

## Definition of Done

Ein leerer `[Unreleased]`-Abschnitt verhindert kein Release mehr, ein gefüllter weiterhin schon.
Ein Pull Request, dessen Inhalt das Release blockieren würde, zeigt das als rotes Kreuz am Pull
Request — nicht erst nach dem Merge in einem Protokoll. Liegt auf `main` eine Version ohne Tag,
schlägt der nächste Pull Request Alarm, statt dass der Rückstand weiterwächst.

## Acceptance Criteria

- **AC-1:** Given ein CHANGELOG mit leerer `## [Unreleased]`-Überschrift über dem Versionseintrag, When `latest_changelog_version` läuft, Then liefert es die Version des nächsten Eintrags statt `None`.
- **AC-2:** Given ein CHANGELOG mit gefülltem `[Unreleased]`-Abschnitt (Text oder angefangene Rubrik), When `latest_changelog_version` läuft, Then liefert es weiterhin `None` und blockiert das Release.
- **AC-3:** Given `main` steht auf einer Version, für die kein Tag existiert, When `check_main_release_published` läuft, Then meldet es FAIL und nennt beide Zahlen; bei vorhandenem Tag, fehlenden Tags oder unlesbarem `main` meldet es OK.
- **AC-4:** Given Tag-Namen mit Versionen, When `latest_tagged_version` sie auswertet, Then gewinnt die numerisch höchste (3.28.0 vor 3.9.0) und Fremd-Tags werden ignoriert.
- **AC-5:** Given der Aufruf mit `--content-only`, When er läuft, Then erscheinen Version, README, Skills und Release in der Prüfliste, aber weder Branch noch Arbeitsbaum noch Abgleich — und auf sauberem Stand ist der Rückgabewert 0.
- **AC-6:** Given der Aufruf ohne `--content-only`, When er läuft, Then prüft er weiterhin auch Branch, Arbeitsbaum und Abgleich.
- **AC-7:** Given `.github/workflows/ci.yml`, When es gelesen wird, Then ruft es `release_check.py --content-only` auf und checkt mit `fetch-depth: 0` aus — sonst bliebe die Prüfung wirkungslos.

## Test Plan

`tests/test_release_gate_visibility_204.py`, 23 Tests in fünf Klassen:

- `TestEmptyUnreleasedDoesNotBlock` — leer, nur Leerzeilen, gefüllt, angefangene Rubrik, alleinige
  Überschrift, Normalfall, ohne Überschriften, echtes Repo-CHANGELOG (AC-1, AC-2)
- `TestPreviousReleasePublished` — getaggt, ungetaggt (der reale Zustand vom 21.09.), Tag voraus,
  gar keine Tags, `main` nicht lesbar (AC-3)
- `TestTagVersionParsing` — Extraktion, numerische statt lexikalischer Sortierung, Fremd-Plugins,
  keine Treffer (AC-4)
- `TestContentOnlyMode` — Zustandsprüfungen fehlen, Inhaltsprüfungen vorhanden, Rückgabewert 0,
  Vollmodus unverändert (AC-5, AC-6)
- `TestCiWiring` — der Aufruf steht in `ci.yml`, und es wird mit voller Historie ausgecheckt (AC-7)

Nachweis:

- Ausgangsstand: 1021 passed, 4 skipped
- RED vor der Umsetzung: 14 der 23 neuen Tests rot
- GREEN: 1044 passed, 4 skipped
- `release_check.py --content-only --no-tests`: alle vier Zeilen OK
- `sync_skills.py --check`: 16 Skills synchron

**Gegenprobe (Mutation).** Sechs gezielte Verfälschungen, jede wurde rot: leeren Unreleased-Block
wieder blockieren lassen; gefüllten Block durchlassen; Release-Prüfung immer bestehen lassen;
Versionsvergleich lexikalisch statt numerisch; Release-Prüfung aus der Inhaltsliste entfernen;
CI-Aufruf entfernen. Der Arbeitsbaum wurde danach nachweislich sauber wiederhergestellt.
