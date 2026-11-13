# Context: feat-591-spur

## Request Summary
Issue #591 (Teil B von #589): "Spur" als Stufe 3 der Vorschlagsrangfolge nach "fertig". Ein Name, der im Auftrag (`.claude/auftrag.json`) steht, per `queue add --spur` / `workflow.py spur` gesetzt wird und in GitHub als Label `spur:<name>` abgebildet ist. `next_suggestion.choose(..., spur=)` waehlt dann offene Issues mit diesem Label; autark startet ein Spur-Vorschlag wie epic/milestone selbst; herdr zeigt die Spur nur an. Bekannte Schwaeche: Auftrag gilt je Projekt, nicht je Sitzung.

## Related Files
- core/hooks/hook_utils.py:2854 `_normalize_auftrag` - baut feste Form `{issues, autark, note, created, updated}`; Unbekanntes faellt weg (Spur muss hier rein, sonst geht sie bei jedem read/write verloren).
- core/hooks/hook_utils.py:2871/2882 `read_auftrag`/`write_auftrag` - write kopiert das dict unveraendert; `auftrag_open_issues`, `auftrag_note_text` (2925) fuer Banner-Satz.
- core/hooks/workflow.py:4057 `QUEUE_USAGE`, 4063 `_queue_usage_exit`, 4075 `_print_queue` (Ausgabe QUEUE/AUTARK/NEXT/PROMPT), 4087 `_parse_queue_add` (Tupel numbers/autark/note), 4106 `_queue_add`, 4125 `cmd_queue`, 4385 `COMMANDS` (4415 `"queue"`).
- core/hooks/workflow.py:3390 `cmd_endstate`, 3420 `_refresh_suggestion` (Autark-Menge `("epic","milestone")` bei 3442; `choose(raw, done, claimed)` ohne Spur), 553 `cached_suggestion` (ebenfalls ohne Spur), 572 `queue_end_args`.
- core/hooks/next_suggestion.py:33 `SOURCE_TEXT`, 110 `_labels` (liest Labels aus Issue-dict, dict oder str), 210 `choose` (Parameter `spur` ohne Wirkung; Platzhalter-Kommentar "Stufe 3 Spur: kommt mit #591" bei Zeile ~236), 277 `fetch`: `issues?state=open&per_page=100` enthaelt Labels bereits -> kein neuer Netzaufruf.
- core/hooks/herdr_bridge.py:80 `TOKEN_NAMES`, 188 `build_report` (Tokens workflow/issue/phase/step/next/state), 229 `clear` und 254 `report_workflow` iterieren `TOKEN_NAMES`.
- core/commands/00-intake.md:55-62 (Schritt 1a, `queue add <N...> [--autark] [--note]`); skills/00-intake/SKILL.md ist Generat (`scripts/sync_skills.py`).
- tests/test_naechster_vorschlag_589.py (Fixtures `_iss`, `_raw`, `_base_raw`, `_stub`, `_case`, `_genv`; Klassen TestChooseRangfolge, TestAutark, TestKillSwitch, TestDokumentation), tests/test_auftrag_551.py, tests/test_herdr_sidebar_466.py (`TOKEN_NAMES`-Liste in Zeile 36, Mengenvergleich Zeile 237 - muss mitgezogen werden).
- config.yaml:336-347 Abschnitte `auftrag` / `next_suggestion` (Kill-Switches).

## Existing Patterns
- Auftrag-Felder: normalisieren in `_normalize_auftrag` (Typpruefung, Default), Schreiben per `write_auftrag` (atomar, Zeitstempel).
- `queue add`-Flags in `_parse_queue_add`; Ausgabe zeilenweise `KEY=value` in `_print_queue`.
- Vorschlag: reine `choose` ohne I/O; Quellen als `(source, candidates)`-Stufen, `SOURCE_TEXT[source]` Alltagssprache; Ausschluesse zentral in `_excluded` (Epic-Label, deferred, spec-proposal, erledigt, geclaimt, offener PR).
- Autark-Anhaengen idempotent per Nummernvergleich in `_refresh_suggestion`; Fail-open, `except Exception` ueberall.
- Kill-Switch nur Literal `false` (`auftrag.enabled`, `next_suggestion.enabled`).
- Seitenleiste: reine Anzeige aus `workflow.*`-Funktionen, lazy import.

## Dependencies
`choose` <- `cached_suggestion`, `_refresh_suggestion` (beide brauchen die Spur aus `read_auftrag`). `build_report` <- `read_auftrag`. Sync: `scripts/sync_skills.py` (Skill 00-intake), ggf. `scripts/sync_cloud_agents.py` nicht betroffen. Test-Konstante `TOKEN_NAMES` in test_herdr_sidebar_466.py. CHANGELOG `[Unreleased]`.

## Existing Specs
Spec zu #589/#551/#466 unter docs/specs (Teil A: next-suggestion); keine Spec zur Spur. Neue Spec `docs/specs/...feat-591-spur` in Phase 3.

## Risks & Considerations
- `_normalize_auftrag` muss `spur` erhalten, sonst verliert `write_auftrag` (via `auftrag_mark_done`, `_queue_add`) die Spur still. Test: Round-Trip.
- Auftrag existiert evtl. nicht, wenn `spur` zuerst gesetzt wird: `workflow.py spur <name>` legt dann einen Auftrag mit leerer `issues`-Liste an. Folgen: `auftrag_open_issues` = [], `auftrag_autark_open` False, `read_auftrag` liefert Dict (nicht None) - `queue_end_args` setzt dann `queue_next=None` -> `cached_suggestion` laeuft weiter (korrekt). `_print_queue` zeigt `QUEUE=none`; Banner (`auftrag_note_text`) leer ohne offene Issues - gewollt.
- `queue clear` loescht die ganze Datei inkl. Spur (Verhalten dokumentieren; Spur separat per `spur --clear`).
- Spur-Vorschlag nur autark selbststartend: Anhaengen an Auftrag nur wenn `autark is True`; ohne autark nur Vorschlagszeile.
- Label fehlt in GitHub: kein Treffer -> Stufe leer -> naechste Stufe (related/priority); kein Fehler, kein Label-Anlegen durch das Framework (Label-Pflege ist GitHub-Seite, `gh label create` waere Schreibzugriff am Live-System).
- Rangfolge: Spec nennt Epic > Meilenstein > Spur > verwandt > Prioritaet; Stufe 3 steht also NACH Epic/Meilenstein (PO-Vorgabe "Epic in GitHub zuerst").
- Pro Projekt, nicht je Sitzung: parallele Sitzungen im selben Projekt teilen eine Spur (bekannt, dokumentieren).
- Cache (`next_suggestion.json`) haelt Rohdaten, nicht die Auswahl -> Spurwechsel wirkt sofort, kein Cache-Invalidieren noetig.
- Label-Namen in GitHub koennen Grossschreibung/Leerzeichen haben: Vergleich auf `spur:` + normalisierten Namen case-insensitiv.

## Analysis

### Type
Feature (Erweiterung eines bestehenden Mechanismus).

### Affected Files (with changes)
| Datei | Change Type | Aenderung |
|---|---|---|
| core/hooks/hook_utils.py | Modify | `normalize_spur(value)` (Namensregel), `_normalize_auftrag` uebernimmt `spur` (str, "" = keine); `auftrag_set_spur(root, name)` Helfer |
| core/hooks/workflow.py | Modify | `queue add --spur`, neues `cmd_spur` + `COMMANDS["spur"]`, `_print_queue` Zeile `SPUR=`, `QUEUE_USAGE`, `_refresh_suggestion` (Spur uebergeben, Autark-Menge um `spur`), `cached_suggestion` (Spur uebergeben) |
| core/hooks/next_suggestion.py | Modify | Stufe 3 in `choose`, `SOURCE_TEXT["spur"]`, Docstring |
| core/hooks/herdr_bridge.py | Modify | Token `spur` (`TOKEN_NAMES`, `build_report`) |
| core/commands/00-intake.md | Modify | `--spur <name>` in Schritt 1a erwaehnen |
| skills/00-intake/SKILL.md | Regenerate | `python3 scripts/sync_skills.py` |
| tests/test_spur_591.py | Create | Neue Tests (choose-Stufe, normalize, Round-Trip, CLI, Autark, Sidebar) |
| tests/test_herdr_sidebar_466.py | Modify | `TOKEN_NAMES` um `spur` |
| tests/test_naechster_vorschlag_589.py | Modify (ggf.) | Docstring/Dokumentationstest, falls "kommt mit #591" geprueft wird |
| CHANGELOG.md | Modify | `[Unreleased]` |
| CLAUDE.md / docs | Modify (klein) | kurze Erwaehnung im next_suggestion-/Auftrag-Absatz falls vorhanden |

### Scope Assessment
- Dateien: 6 Quell-/Befehlsdateien + 1 Generat + 2-3 Tests + CHANGELOG (~10).
- LoC: ca. 90-130 Produktivcode, ca. 150-200 Tests.
- Risk: Niedrig-mittel. Alles fail-open, ohne gesetzte Spur keine Wirkung; Haupt-Risiko `_normalize_auftrag` (zentral, viele Leser) und Sidebar-Tokenliste (Test-Mengenvergleich).

### Technical Approach
1. **Namensregel** (`hook_utils.normalize_spur`): trimmen, Kleinschreibung, Leerzeichen/Unterstriche -> `-`, nur `[a-z0-9-]`, Mehrfach-`-` zusammenziehen, Raender strippen, max. 40 Zeichen; Ergebnis leer -> ungueltig (CLI: Fehler auf stderr, Exit 1, Usage). Label dazu immer `spur:<name>`. Ein Praefix `spur:` im Argument wird toleriert und abgeschnitten.
2. **Auftrag**: Feld `spur` (str, Default ""), in `_normalize_auftrag` per `normalize_spur(raw.get("spur")) or ""` uebernommen (kaputte Werte -> ""). Bleibt bei `auftrag_mark_done` erhalten.
3. **CLI**: `queue add <N...> [--autark] [--note T] [--spur NAME]` setzt/ueberschreibt Spur; `workflow.py spur <name>` setzt (legt Auftrag mit leerer Liste an, falls keiner existiert), `workflow.py spur --clear` setzt "" (Auftrag bleibt, Datei wird nicht geloescht), `workflow.py spur` ohne Argument zeigt nur. Ausgabe immer `SPUR=<name>` bzw. `SPUR=none`; `_print_queue` gibt zusaetzlich `SPUR=` aus. Kill-Switch `auftrag.enabled:false` -> wie `queue`: `SPUR=disabled`, keine Schreibung. `queue clear` entfernt wie bisher die ganze Datei (inkl. Spur).
4. **choose**: `choose(raw, done, claimed, spur=...)`; nach der Milestone-Stufe `if spur: stages.append(("spur", [i for i in issues if f"spur:{spur}" in {l.lower() for l in _labels(i)}]))`; Sortierung/Ausschluesse unveraendert (`_sort_key`, `_excluded`). `SOURCE_TEXT["spur"] = "gleiche Spur"`. Kein Label im Repo / kein Treffer -> Stufe leer, naechste Stufe greift (kein Fehler, Framework legt keine Labels an).
5. **Durchreichen**: kleiner Helfer `_auftrag_spur()` in workflow.py (liest `read_auftrag`, gibt `spur` oder None; wirft nie); `cached_suggestion` und `_refresh_suggestion` rufen `choose(..., spur=_auftrag_spur())`. Autark-Menge in `_refresh_suggestion` -> `("epic","milestone","spur")`; Anhaengen unveraendert idempotent.
6. **herdr**: Token `spur` in `TOKEN_NAMES` und `build_report` (`_clean(spur or "")`; leer = Token leer, wie `next`). Nur Anzeige, kein Schreibpfad; Hoheit beim Framework (kein Lesen eines herdr-Werts).
7. **Doku**: 00-intake Schritt 1a: "Hat der PO eine Spur genannt (oder gehoert die Aufgabe zu einer Epic-Reihe), `--spur <name>` mitgeben"; Hinweis Label `spur:<name>` in GitHub; Epic hat Vorrang, Spur wirkt als Stufe 3. Danach `sync_skills.py`.
8. **Kein neuer Kill-Switch**: ohne gesetzte Spur keine Wirkung; `auftrag.enabled` und `next_suggestion.enabled` decken ab.
9. Tests (RED zuerst): choose mit/ohne Label, Rang nach Epic/Meilenstein, Normalisierung (Gross, Leerzeichen, Sonderzeichen, zu lang, leer), Round-Trip ueber `mark_done`, CLI set/clear/show + `queue add --spur`, Autark haengt Spur-Vorschlag an (idempotent), nicht-autark nur Zeile, Sidebar-Token, Kill-Switch.

### Dependencies
Teil A (#589) auf main; kein neuer GitHub-API-Aufruf; keine neuen Libraries; Label `spur:<name>` muss vom PO/Claude in GitHub gesetzt sein (Issue-Pflege, ausserhalb des Codes).

### Open Questions
Keine echten. Entschieden: Spur-Stufe nach Epic/Meilenstein (PO: "Epic in GitHub zuerst"); `spur --clear` laesst Auftrag bestehen; Label wird nicht automatisch angelegt. (Produktfragen: keine.)
