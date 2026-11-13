# Adversary Dialog — feat-591-spur
Spec: docs/specs/feat-591-spur.md
Datum: 2026-11-13 07:32

## Checkliste
- [x] **Input:** `workflow.py spur NAME|--clear|<leer>`, `workflow.py queue add … --spur NAME`, abgeschlossener Workflow (`workflow.py endstate`), offene Issues mit Label `spur:<name>`
- [x] **Output:** `SPUR=<name>|none|disabled`; bei fertigem Workflow ohne Epic-/Meilenstein-Nachfolger ein Vorschlag mit Quelle „gleiche Spur“ (`SUGGEST_SOURCE=spur`); bei autarkem Auftrag die Kettenzeile „⏳ Läuft noch: Claude startet #M aus deinem Auftrag …“; in der Seitenleiste das Token `spur`
- [x] **Side effects:** Feld `spur` in `.claude/auftrag.json` (bei Bedarf wird die Datei mit leerer Liste angelegt); idempotentes Anhängen an den Auftrag nur bei autark; kein zusätzlicher Netzaufruf, kein Anlegen von Labels
- [x] **AC-1:** Given Eingaben mit Großschreibung, Leerzeichen, Unterstrichen, Sonderzeichen, Präfix `spur:`, Mehrfach-Bindestrichen, mehr als 40 Zeichen sowie leer, nur Sonderzeichen oder kein String / When `normalize_spur` läuft / Then entsteht ein Name aus `[a-z0-9-]` ohne Rand-/Doppel-Bindestriche mit höchstens 40 Zeichen, und leere oder ungültige Eingaben ergeben `None`
- [x] **AC-2:** Given ein Auftrag mit `spur` / When er per `write_auftrag`, `read_auftrag`, `auftrag_mark_done` und `queue add` ohne `--spur` hin- und hergeschrieben wird / Then bleibt die Spur erhalten, und ein fehlendes oder ungültiges Feld (Zahl, Liste, nur Sonderzeichen) wird zu `""` verworfen, ohne die übrigen Felder zu beschädigen
- [x] **AC-3:** Given ein Projekt mit und ohne Auftrag / When `workflow.py spur NAME`, `spur` ohne Argument und `spur --clear` laufen / Then setzt der erste Aufruf die normalisierte Spur (legt bei Bedarf einen Auftrag mit leerer Liste an), der zweite zeigt `SPUR=<name>` bzw. `SPUR=none` ohne zu schreiben, der dritte leert die Spur, lässt die Datei bestehen, und ein ungültiger Name endet mit Exit 1, Usage auf stderr und ohne Schreibzugriff
- [x] **AC-4:** Given ein Auftrag und der Aufruf `queue add <N> --autark --spur "Mein Thema"` / When er läuft / Then enthält der Auftrag die Nummer, `autark: true` und die Spur `mein-thema`; ein späteres `queue add` ohne `--spur` ändert die Spur nicht, ein erneutes mit `--spur` überschreibt sie
- [x] **AC-5:** Given Aufträge mit und ohne Spur sowie `auftrag.enabled: false` (Literal `false`) / When `queue` (Anzeige) und `spur` laufen / Then gibt `_print_queue` zusätzlich `SPUR=<name>` bzw. `SPUR=none` aus, und bei ausgeschaltetem Auftrag liefert `spur` `SPUR=disabled` ohne Schreibzugriff; andere Werte, fehlender Abschnitt und kaputte Config gelten als „an“
- [x] **AC-6:** Given offene Geschwister (Epic), Aufgaben im selben Meilenstein, Aufgaben mit Label `spur:x` und eine verwandte Aufgabe / When `choose(..., spur="x")` läuft und die höheren Stufen nacheinander entfallen / Then gewinnt Epic vor Meilenstein vor Spur vor verwandt vor Priorität, die Spur-Stufe liefert `source="spur"` mit Text „gleiche Spur“, und ausgeschlossene Issues (erledigt, geclaimt, `status:deferred`, offener PR) werden auch auf der Spur nicht vorgeschlagen
- [x] **AC-7:** Given Labels `Spur:X`, ` spur:x ` und ein Issue ohne passendes Label, sowie eine gesetzte Spur ohne jedes Issue mit diesem Label / When `choose` läuft / Then trifft der Vergleich case-insensitiv und getrimmt, die Sortierung innerhalb der Stufe bleibt Meilenstein, Fälligkeit, Priorität, Nummer, und fehlt das Label überall, greift die nächste Stufe ohne Ausnahme; ohne gesetzte Spur ist das Ergebnis identisch zu Teil A
- [x] **AC-8:** Given ein Auftrag mit Spur, gefüllter Cache und ein Epic-/Meilenstein-loser Rest / When `workflow.py endstate` läuft und `cached_suggestion` liest / Then übergeben beide die Spur aus dem Auftrag an `choose`, `SUGGEST_SOURCE=spur` und die Schlusszeile nennt „gleiche Spur“; nach einem Spurwechsel wirkt die neue Spur sofort ohne neuen Netzabruf
- [x] **AC-9:** Given ein autarker Auftrag ohne weiteres offenes Issue und ein Spur-Vorschlag M / When `endstate` ein- und zweimal läuft / Then steht M genau einmal im Auftrag und die Zeile ist „⏳ Läuft noch: Claude startet #M aus deinem Auftrag …“; bei nicht autarkem Auftrag wird nichts angehängt und es bleibt bei der Vorschlagszeile; Epic und Meilenstein starten weiterhin selbst, `related` und `priority` weiterhin nicht
- [x] **AC-10:** Given ein gefüllter Cache und ein Auftrag mit Spur / When `end_state`, `queue_end_args`, `render_plan` und die Seitenleiste dieselbe Schlusszeile bauen / Then rufen sie keinen `gh`-Stub auf (Marker bleibt aus) und zeigen dieselbe Zeile wie `endstate`; die Spur kommt ausschließlich aus dem Auftrag und den bereits gecachten Labels
- [x] **AC-11:** Given ein Auftrag mit und ohne Spur / When `herdr_bridge.build_report` läuft und `TOKEN_NAMES` ausgewertet wird / Then enthält `TOKEN_NAMES` `spur`, das Token trägt den Spurnamen, bleibt ohne Spur leer, `clear` und `report_workflow` behandeln es wie die übrigen Tokens, ein Fehler beim Lesen des Auftrags bleibt fail-open, und es gibt keinen Schreibpfad von herdr in den Auftrag
- [x] **AC-12:** Given `core/commands/00-intake.md` und `skills/00-intake/SKILL.md` / When gelesen / Then nennt Schritt 1a `--spur <name>`, das Label `spur:<name>` und den Vorrang von Epic, und das Skill-Generat ist synchron zum Befehlstext (`scripts/sync_skills.py --check` bzw. `test_command_texts_and_skills_in_sync`)
- [x] **AC-13:** Given `CHANGELOG.md` / When gelesen / Then nennt `[Unreleased]` → `### Added` die Spur und `#591`, und es steht keine neue Versionsnummer darin
- [x] **AC-14:** Given die bestehenden Testdateien zu #589, #551 und #466 / When sie laufen (mit der um `spur` ergänzten `TOKEN_NAMES`-Liste in `test_herdr_sidebar_466.py`) / Then bleiben sie grün, und ohne gesetzte Spur ist jede Ausgabe der betroffenen Kommandos (`queue`, `endstate`, Plan, Seitenleiste) bis auf die neuen Zeilen `SPUR=` bzw. das leere Token unverändert

## Dialog

### Runde 1
**Adversary:** Ursachenanalyse pruefen: Ist der rote Test ein Produktfehler (paralleles report/clear)?
Code reference: core/hooks/herdr_bridge.py:240 (clear) und core/hooks/herdr_bridge.py:254 (report_workflow): beide starten den herdr-Binary je einmal detached; report_workflow ruft clear() nur im Zweig `report is None`, also nie zusaetzlich zu einem Report. core/hooks/workflow.py:1162 (_herdr) ruft genau eine der beiden Aktionen je Aufruf. Parallelitaet entsteht nur im Test, der beide in zwei Python-Prozessen direkt hintereinander startete. herdr bekommt ohnehin Aufrufe aus getrennten Hooks/Prozessen; Reihenfolge laeuft ueber `--seq`. Kein Produktfehler, nur der printf-Stub des Tests ist nicht atomar.
Code reference: tests/test_spur_591.py:594 (Test) mit Serialisierung um Z. 634-643 (`_settled_calls(log, 1)` vor dem clear). tests/test_herdr_sidebar_466.py:37 (TOKEN_NAMES um `spur`) unveraendert gegenueber Runde 1. Der Fix verdeckt nichts: die Assertions auf je 1 Report und 1 Clear mit Token `spur` bleiben.
Stabilitaet: 20x einzeln = 0 Fehlschlaege; 3x parallel zusammen mit test_herdr_sidebar_466.py (6 Prozesse gleichzeitig) = alle rc=0.
**Implementierer:** Bestaetigt durch Auftrag; Produkt-Diff seit Runde 1 unveraendert (git diff --stat: 9 Dateien, nur Test um 5 Zeilen ergaenzt).

### Runde 2
**Adversary:** Regression/AC-Abdeckung: Produktcode seit Runde 1 unveraendert, daher gelten die Belege aus adversary-dialog-runde1.md fuer AC-1..AC-14 weiter.
Code reference: core/hooks/hook_utils.py:2857 (normalize_spur, AC-1) und core/hooks/hook_utils.py:2893 (read_auftrag, AC-2); core/hooks/workflow.py:4176 (cmd_spur, AC-3/AC-5) und :4086 (_print_queue); core/hooks/workflow.py:3449 und :576 (Spur an choose, AC-8/AC-10); core/hooks/next_suggestion.py:211 (choose, AC-6/AC-7); core/hooks/herdr_bridge.py:80 (TOKEN_NAMES, AC-11, kein Schreibpfad). AC-12/13/14 durch Tests (Sync Skill, CHANGELOG, #589/#551/#466-Dateien) in der Vollsuite gruen.
Vollsuite: 3750 passed, 30 skipped, 0 failed (docs/artifacts/feat-591-spur/adversary-test-output.txt). Die 30 Skips sind vorbestehend/umgebungsbedingt, 0 bestanden ist nicht der Fall.
**Implementierer:** Keine Einwaende. Keine Findings.

Confirmation:
  AC: AC-1
  Code reference: core/hooks/hook_utils.py:2857
  Evidence: normalize_spur normalisiert auf [a-z0-9-], max. 40, sonst None
  Status: CONFIRMED

Confirmation:
  AC: AC-2
  Code reference: core/hooks/hook_utils.py:2893
  Evidence: read_auftrag verwirft ungültiges spur zu leer, übrige Felder bleiben
  Status: CONFIRMED

Confirmation:
  AC: AC-3
  Code reference: core/hooks/workflow.py:4176
  Evidence: cmd_spur setzt/zeigt/leert, ungültig Exit 1 ohne Schreiben
  Status: CONFIRMED

Confirmation:
  AC: AC-6
  Code reference: core/hooks/next_suggestion.py:211
  Evidence: choose: Spur-Stufe nach Meilenstein, source=spur, Ausschlüsse greifen
  Status: CONFIRMED

Confirmation:
  AC: AC-8
  Code reference: core/hooks/workflow.py:3449
  Evidence: endstate übergibt Spur aus dem Auftrag an choose
  Status: CONFIRMED

Confirmation:
  AC: AC-11
  Code reference: core/hooks/herdr_bridge.py:80
  Evidence: TOKEN_NAMES enthält spur, kein Schreibpfad in den Auftrag
  Status: CONFIRMED

Confirmation:
  AC: AC-11
  Code reference: tests/test_spur_591.py:594
  Evidence: Test belegt Token spur, report/clear, fail-open (serialisiert, stabil)
  Status: CONFIRMED

Confirmation:
  AC: AC-14
  Code reference: tests/test_herdr_sidebar_466.py:37
  Evidence: TOKEN_NAMES um spur ergänzt, Test grün
  Status: CONFIRMED

## Herkunft der Vorbedingungen

kein Sprachprofil konfiguriert (`precondition_origins.default_lang`)

## Verdict

═══════════════════════════════════════
VERDICT: VERIFIED
═══════════════════════════════════════
Die Implementierung hat den Adversary-Test bestanden.
Tests: 3750 passed, 0 failed, 30 uebersprungen
Edge cases: Flaky-Test geprueft (20x einzeln, 3x parallel gruen); Ursache liegt im Test-Stub, nicht im Produktcode
Regressions: None found
Checklist: 17/17 points proven

## Geprüfte Dateien

- sha256:0f7b25278505afa581b2a2307e6313cc270da8d90b1739ea1e1920baff196979  core/hooks/herdr_bridge.py
- sha256:b0bc1c3e44548562f10261f1038a11262e6b7b4c45b633108e35e01f3b8faae5  core/hooks/hook_utils.py
- sha256:e31bd918ead2e93e9433b4eb2c9bba28d824da12f42219815d8bc2e4c2e060b5  core/hooks/next_suggestion.py
- sha256:9159a2e3a31703039e73e74fd64c284b14b042fac39a24263f61325e5e33c0be  core/hooks/workflow.py
- sha256:9a9e430cf4b5ba839a2efdc9766380c9fc324365bb76b3ff2f8a1173417618a9  tests/test_herdr_sidebar_466.py
- sha256:e8f9c3c8871b2d33dceee7eb8bf17e53102e34b228a0016db3538147b5bf5112  tests/test_spur_591.py

## Prüfbasis

- base: 7715c60a9e9e4311970958c2b9c38b2b9533b763
- blob:5a4560c8cb5070a18477da486c18c2a1536c65eb  core/hooks/herdr_bridge.py
- blob:0493877e83f160d517f59d0e17e9dd8e556f6ddc  core/hooks/hook_utils.py
- blob:500877a76e22c844f6c45d60e8a9dd5fc1a51b75  core/hooks/next_suggestion.py
- blob:07a62e9ee9c844c041daa85fa35b339a1ad0c591  core/hooks/workflow.py
- blob:2bc3cf7d4394e1e2385ac72775668e1ecf451183  tests/test_herdr_sidebar_466.py
- blob:ef514142afe3909fd5c28a08b5fc29b34f96223c  tests/test_spur_591.py
