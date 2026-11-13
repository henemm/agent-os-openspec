# Adversary Dialog — feat-591-spur
Spec: docs/specs/feat-591-spur.md
Datum: 2026-11-13 07:15

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
**Adversary:** Angriff auf Namensregel und Auftrag-Normalisierung (AC-1/2/3/4/5). Fuzz mit 20000 Zufallsstrings plus gezielte Fälle (Prä­fix `spur:`, `spur:spur:x`, 60 Zeichen, Bindestrich an der Kürzungsstelle, Zeilenumbruch, `$(rm)`, Backticks, Unicode, Fullwidth, None/5/Liste): immer `[a-z0-9]+(-[a-z0-9]+)*`, <=40, idempotent (0 Verstöße). Alte/kaputte Aufträge (`spur` fehlt, Zahl, Liste, `!!!`) werden zu `""`, Rest unverändert. CLI im Scratchpad-Projekt: `spur` ohne Auftrag -> `SPUR=none` ohne Datei; `spur "Mein Thema"` legt Auftrag an; `spur '!!!'`, `spur ''`, `spur a b` -> Exit 1, Usage auf stderr, Datei unverändert; `--clear` lässt Datei bestehen; `queue add 5 --autark --spur "X y"` -> `x-y`, späteres `queue add 6` lässt Spur, doppeltes `--spur` überschreibt, `--spur` ohne Wert und `--spur %%` -> Usage ohne Schreiben; `queue done` erhält die Spur; Auftrag ohne `spur`-Feld -> `SPUR=none`; `auftrag.enabled: false` -> `SPUR=disabled` bzw. `QUEUE=disabled` ohne Schreiben. Injektion über Name nicht möglich (nur `[a-z0-9-]` erreicht `SPUR=`/herdr `--token`).
**Implementierer:** Code liest wie erwartet (hook_utils.py:2857/2875/2947, workflow.py:4099/4176). Gefunden: F002 (`spur:spur:x` -> `spurx`, still), F003 (`spur` überschreibt eine kaputte auftrag.json, weil read_auftrag None liefert; gleiches Verhalten wie `queue add` aus #551).

### Runde 2
**Adversary:** Angriff auf choose Stufe 3, Autark, Netzfreiheit, herdr (AC-6..11, 14). choose-Probe mit Labels `Spur:X`, ` spur:x `, `spur:y`, verwandtem Issue, `status:deferred`: Spur `x`/`X`/` x ` -> #10 source spur; geclaimtes #10 -> #11; deferred ausgeschlossen; Spur ohne Treffer, None, "", 5, Liste -> nächste Stufe related ohne Ausnahme; Epic vor Meilenstein vor Spur vor related/priority bestätigt; eigenes erledigtes Issue mit Label nicht vorgeschlagen; nicht-String-Labels werfen nicht (`_labels` filtert). Autark: `_refresh_suggestion` hängt nur bei `queue["autark"] is True` und Quelle epic/milestone/spur an, `all(e["n"] != n)` macht es idempotent; kein Schleifenpfad. herdr: `_spur_token` nur `read_auftrag`, try/except, Quelltext enthält keinen Schreib-Helfer. Testläufe: tests/test_spur_591.py 14 passed (mehrfach); Gesamtsuite 3750 passed, 30 skipped, 0 failed; Teilmenge #550/#551/#555/#589/#466/#591: einmal 1 Fehler in `test_token_spur_nur_anzeige_fail_open` (tests/test_spur_591.py:594) während parallel die Gesamtsuite lief, danach 3x allein und in der Gesamtsuite grün -> F001 (Flake unter Last, Herdr-Stub-Log). `sync_skills.py --check` synchron; CHANGELOG nennt #591 unter Unreleased ohne Versionsnummer.
**Implementierer:** Keine Spec-Abweichung gefunden; F001-F003 sind LOW/Nacharbeit, kein Blocker.

## Herkunft der Vorbedingungen

kein Sprachprofil konfiguriert (`precondition_origins.default_lang`)

## Verdict

Finding:
  ID: F001
  Severity: LOW
  Category: edge_case
  Code reference: tests/test_spur_591.py:594
  Description: test_token_spur_nur_anzeige_fail_open wartet auf Herdr-Stub-Log (_settled_calls) und schlug einmal fehl, als parallel die Gesamtsuite lief; danach 3x grün.
  Spec requirement: AC-11 — Token/clear/report_workflow wie übrige Tokens
  Conflict: Zeitabhängiger Test, mögliche Flake unter Last (kein Produktfehler belegt).
  Remediation: Wartezeit/Polling im Test großzügiger.

Finding:
  ID: F002
  Severity: LOW
  Category: edge_case
  Code reference: core/hooks/hook_utils.py:2857
  Description: `spur:spur:x` wird nur einmal entpräfixt, das zweite `:` fällt weg -> `spurx`.
  Spec requirement: AC-1 — Präfix `spur:` abschneiden
  Conflict: Stilles, unerwartetes Ergebnis bei doppeltem Präfix; Regeln (Zeichenmenge) bleiben aber eingehalten.
  Remediation: Optional Präfix in Schleife abschneiden oder dokumentieren.

Finding:
  ID: F003
  Severity: LOW
  Category: edge_case
  Code reference: core/hooks/hook_utils.py:2947
  Description: auftrag_set_spur überschreibt eine kaputte auftrag.json mit leerem Auftrag (read_auftrag liefert None).
  Spec requirement: AC-2 — übrige Felder nicht beschädigen
  Conflict: Bei nicht lesbarer Datei gehen deren Reste verloren; identisch zu queue add aus #551.
  Remediation: Bestandsverhalten; optional bei vorhandener, aber unlesbarer Datei abbrechen.

Confirmation:
  AC: AC-1
  Code reference: core/hooks/hook_utils.py:2857
  Evidence: normalize_spur: Fuzz 20000 Fälle, Regex/Länge/Idempotenz ok, ungültig -> None
  Status: CONFIRMED

Confirmation:
  AC: AC-2
  Code reference: core/hooks/hook_utils.py:2875
  Evidence: _normalize_auftrag verwirft ungültiges spur zu ""; mark_done/write_auftrag erhalten es
  Status: CONFIRMED

Confirmation:
  AC: AC-3
  Code reference: core/hooks/workflow.py:4176
  Evidence: cmd_spur: setzen/zeigen/--clear/ungültig Exit 1 ohne Schreiben per CLI-Probe belegt
  Status: CONFIRMED

Confirmation:
  AC: AC-4
  Code reference: core/hooks/workflow.py:4099
  Evidence: queue add --autark --spur; ohne --spur unverändert, erneut überschreibt (CLI-Probe)
  Status: CONFIRMED

Confirmation:
  AC: AC-5
  Code reference: core/hooks/workflow.py:4096
  Evidence: SPUR=<name>|none in _print_queue; SPUR=disabled bei auftrag.enabled false
  Status: CONFIRMED

Confirmation:
  AC: AC-6
  Code reference: core/hooks/next_suggestion.py:239
  Evidence: Stufe 3 spur zwischen milestone und related; Ausschlüsse greifen (Probe)
  Status: CONFIRMED

Confirmation:
  AC: AC-7
  Code reference: core/hooks/next_suggestion.py:239
  Evidence: strip().lower() auf Spur und Labels; ohne Treffer nächste Stufe
  Status: CONFIRMED

Confirmation:
  AC: AC-8
  Code reference: core/hooks/workflow.py:553
  Evidence: _auftrag_spur speist cached_suggestion und _refresh_suggestion ohne Netz
  Status: CONFIRMED

Confirmation:
  AC: AC-9
  Code reference: core/hooks/workflow.py:3451
  Evidence: Autark-Anhängen nur bei autark, idempotent über all(e['n']!=n)
  Status: CONFIRMED

Confirmation:
  AC: AC-10
  Code reference: tests/test_spur_591.py:558
  Evidence: TestNetzfrei: gh-Stub-Marker bleibt aus
  Status: CONFIRMED

Confirmation:
  AC: AC-11
  Code reference: core/hooks/herdr_bridge.py:188
  Evidence: _spur_token nur lesend, fail-open; TOKEN_NAMES enthält spur (herdr_bridge.py:80)
  Status: CONFIRMED

Confirmation:
  AC: AC-12
  Code reference: tests/test_spur_591.py:113
  Evidence: Befehlstext/Skill: sync_skills.py --check synchron (15 geprüft)
  Status: CONFIRMED

Confirmation:
  AC: AC-13
  Code reference: tests/test_spur_591.py:343
  Evidence: CHANGELOG-Eintrag #591 unter Unreleased/Added, keine Versionsnummer (git diff geprüft)
  Status: CONFIRMED

Confirmation:
  AC: AC-14
  Code reference: tests/test_herdr_sidebar_466.py:37
  Evidence: TOKEN_NAMES um spur ergänzt; Tests #550/#551/#555/#589/#466 grün, Gesamtsuite 3750 passed
  Status: CONFIRMED

Weitere Code-Referenzen (Abdeckung):
  Code reference: core/hooks/hook_utils.py:2857
  Code reference: core/hooks/workflow.py:4176
  Code reference: core/hooks/next_suggestion.py:239
  Code reference: core/hooks/herdr_bridge.py:188
  Code reference: tests/test_spur_591.py:594
  Code reference: tests/test_herdr_sidebar_466.py:37

═══════════════════════════════════════
VERDICT: VERIFIED
═══════════════════════════════════════
Tests: 3750 passed, 0 failed, 30 übersprungen (Gesamtsuite); tests/test_spur_591.py 14 passed
Edge cases: geprüft, nur LOW (F001-F003)
Regressions: None found
Checklist: 14/14 points proven

## Geprüfte Dateien

- sha256:0f7b25278505afa581b2a2307e6313cc270da8d90b1739ea1e1920baff196979  core/hooks/herdr_bridge.py
- sha256:b0bc1c3e44548562f10261f1038a11262e6b7b4c45b633108e35e01f3b8faae5  core/hooks/hook_utils.py
- sha256:e31bd918ead2e93e9433b4eb2c9bba28d824da12f42219815d8bc2e4c2e060b5  core/hooks/next_suggestion.py
- sha256:9159a2e3a31703039e73e74fd64c284b14b042fac39a24263f61325e5e33c0be  core/hooks/workflow.py
- sha256:9a9e430cf4b5ba839a2efdc9766380c9fc324365bb76b3ff2f8a1173417618a9  tests/test_herdr_sidebar_466.py
- sha256:5e078cbc6ada5ffcee2f9325e54972921855d9b76e3776044674ab011e4f2d27  tests/test_spur_591.py

## Prüfbasis

- base: 7715c60a9e9e4311970958c2b9c38b2b9533b763
- blob:5a4560c8cb5070a18477da486c18c2a1536c65eb  core/hooks/herdr_bridge.py
- blob:0493877e83f160d517f59d0e17e9dd8e556f6ddc  core/hooks/hook_utils.py
- blob:500877a76e22c844f6c45d60e8a9dd5fc1a51b75  core/hooks/next_suggestion.py
- blob:07a62e9ee9c844c041daa85fa35b339a1ad0c591  core/hooks/workflow.py
- blob:2bc3cf7d4394e1e2385ac72775668e1ecf451183  tests/test_herdr_sidebar_466.py
- blob:1177095b48c54d1dd261ab44541bbfbf5091c0a9  tests/test_spur_591.py
