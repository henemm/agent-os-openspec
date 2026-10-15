# Context: fix-440-test-zeilen

## Request Summary
#440 (Restpunkt F004 aus #439): Fortsetzungszeilen unter einer `- Test:`-Zeile sind beweglich, solange sie
weder AC-Label noch given/when/then enthalten — damit lässt sich neuer Anforderungstext ohne Rücksprung
einschleusen (Fließtext, „A C-31“, kyrillisches А, Soft-Hyphen/Zero-Width-Space). Vorschlag des Issues:
Fortsetzungszeilen abschaffen (Test-Zuordnung = genau eine Zeile). Nebenbefund: `edit_gate.py` stürzt
(Exit 1) bei `file_path` als Zahl oder `tool_input` als String ab.

## Related Files
| File | Relevance |
|------|-----------|
| core/hooks/hook_utils.py:722 `_SPEC_AC_TEXT_RE` | Heuristik, die Fortsetzungen mit AC-Text einfriert — die Lücke |
| core/hooks/hook_utils.py:~805 `_spec_ac_frozen_lines` | Zerleger: verwirft `- Test:`-Zeile samt Fortsetzungen; hier ansetzen |
| core/hooks/hook_utils.py:910 `get_tool_input` | liefert `tool_input` ungeprüft zurück (String/Zahl möglich) |
| core/hooks/edit_gate.py:641-643 | `tool_input.get("file_path")` bricht bei Nicht-dict / Nicht-String |
| tests/test_spec_freeze_partial_hash_439.py (AC-8 ~Z.489, F003 ~Z.834) | Tests, die Fortsetzungen heute als beweglich festschreiben |
| docs/specs/feat-439-spec-freeze-teilhash.md (AC-8, Z.79/151) | alte Spec, eingefroren — nicht anfassen |
| CHANGELOG.md, CLAUDE.md (Hook-Beschreibung) | nennen „samt Fortsetzung“ — müssen nachgezogen werden |

## Existing Patterns
- Fail-closed: Allowlist beweglicher Teile, alles andere eingefroren (#439).
- Release-stabile Doku-Tests (Eintrag über Marker, nicht über `[Unreleased]`).
- Gate-Fehler in Hooks: Exit 2 blockt, ein Traceback (Exit 1) wäre fail-open.

## Dependencies
- Upstream: `split_spec_sections`, `_indent_width`, `_SPEC_TEST_LINE_RE`.
- Downstream: `frozen_spec_sha256` → `workflow.py` (`set-briefing`, `_check_po_briefing`, Doppelstempel),
  `edit_gate.py` (Freeze-Simulation), `scripts/ci_spec_gate.py` (CI, Fallback auf Byte-Hash).

## Existing Specs
- `docs/specs/feat-439-spec-freeze-teilhash.md` — Ursprung; AC-8 beschreibt die Fortsetzungsregel.

## Risks & Considerations
- **Hash ändert sich:** Wird die Fortsetzung nicht mehr herausgerechnet, bleibt sie im Hash. Für Specs ohne
  Fortsetzungen unverändert; Specs MIT Fortsetzungen unter `- Test:` bekommen einen anderen Teil-Hash →
  bestehende Briefings würden als veraltet gelten. Migration/Verträglichkeit prüfen (62 Alt-Specs, CI-Gate).
- Zerleger und CI-Gate müssen dieselbe Regel nutzen (CI hat Byte-Hash-Fallback für ältere Kopien).
- Menschen brechen lange Testpfade evtl. um; die neue Regel macht das zur Spec-Änderung (Rücksprung nötig).
- Hochrisiko laut Adversary-Regel (Gate-Code): mindestens 2 Prüf-Runden.
- Nebenbefund: Robustheit nur fail-open-sicher lösen (Müll-Payload → allow), nie neuer Bypass.

## Analysis

### Type
Bug (Lücke im Spec-Freeze, LOW) + Robustheits-Nebenbefund. Hochrisiko-Bereich (Gate-Code).

### Befund (belegt)
`_spec_ac_frozen_lines` (hook_utils.py ~805) wirft die `- Test:`-Zeile UND alle tiefer eingerückten Folgezeilen aus dem Teil-Hash;
nur Folgezeilen mit AC-Label/given/when/then (`_SPEC_AC_TEXT_RE`) bleiben drin. Jede andere Formulierung (Fließtext, „A C-31“,
kyrillisches А, Soft-Hyphen/ZWSP) ist ohne Rücksprung änderbar. Eine Regex-Denylist ist prinzipiell umgehbar → Allowlist-Prinzip.

### Messung Alt-Specs (Variantenvergleich)
Gemessen: 75 Fortsetzungszeilen in 12 von 69 Alt-Specs (fix-147, fix-253, fix-131, fix-275, feat-285/286 …) — Fortsetzungen
sind üblicher Schreibstil (lange Testpfade, Begründungen), kein Randfall.

| Variante | Wirkung | Risiko |
|----------|---------|--------|
| A Fortsetzung eingefroren (nur die `- Test:`-Zeile selbst beweglich) | Lücke zu; Regex entfällt; Ändern/Umbrechen einer Fortsetzung = Spec-Änderung (Rücksprung) | Teil-Hash der 12 Alt-Specs ändert sich → laufende, freigegebene Workflows mit Fortsetzungen gelten als „veraltet“ (Migration über `set-briefing`) |
| B Issue-Vorschlag: Fortsetzungen verbieten | wie A, plus Fehlermeldung | Alt-Specs müssten umformatiert werden → unnötiger Aufwand |
| C nur als Known Limitation dokumentieren | keine Änderung | Lücke bleibt; widerspricht fail-closed aus #439 |

### Affected Files (with changes)
| File | Change Type | Description |
|------|-------------|-------------|
| core/hooks/hook_utils.py | MODIFY | `_spec_ac_frozen_lines`: nur die `- Test:`-Zeile entfällt, Folgezeilen bleiben im Hash; `_SPEC_AC_TEXT_RE` + `test_indent`-Zustand entfernen; `get_tool_input` liefert nur dict |
| core/hooks/edit_gate.py | MODIFY | `file_path` nicht-String / `tool_input` nicht-dict → `allow()` (wie bisher bei leerem Pfad), kein Traceback |
| tests/test_spec_freeze_partial_hash_439.py | MODIFY | AC-8 (~Z.489) und F003 (~Z.834) auf neue Regel umschreiben |
| tests/test_spec_freeze_continuation_440.py | CREATE | Fließtext/„A C-31“/Kyrillisch/ZWSP-Fortsetzung → Block; Test-Zeile allein ändern → erlaubt; Müll-Payload → Exit 0 |
| CHANGELOG.md | MODIFY | Eintrag unter [Unreleased]; „samt Fortsetzung“ korrigieren; Migrationshinweis |
| docs/specs/fix-440-test-zeilen.md | CREATE | neue Spec; Doku-Lücken aus dem Issue-Kommentar (hook_utils in Scope-Tabelle, Setext/H3 keine Abschnittsgrenze) als Known Limitations |

### Scope Assessment
- Files: 4 Code/Test + Changelog + Spec
- Estimated LoC: +~120 (überwiegend Tests) / -~20
- Risk Level: MEDIUM — kleine Codeänderung, aber Gate-Code; Hash-Änderung wirkt auf bestehende Freigaben

### Technical Approach (Empfehlung: Variante A)
1. Zerleger: nach einer `- Test:`-Zeile nur diese eine Zeile weglassen; alles Weitere (auch eingerückte Folgezeilen) bleibt Hashbestandteil. Fail-closed, keine Heuristik.
2. Specs ohne Fortsetzungen: Hash unverändert (Regressionstest). Specs mit Fortsetzungen: neuer Hash → Briefing „veraltet“, Weg: `set-briefing` erneut bzw. Rücksprung.
3. edit_gate: Typprüfung vor `.get`; Müll-Payload → allow (kein neuer Bypass: ohne gültigen `file_path` wird nichts geschrieben).
4. CI-Gate nutzt dieselbe Funktion (`hook_utils.frozen_spec_sha256`); Byte-Hash-Fallback unverändert.

### Dependencies
`frozen_spec_sha256` → workflow.py (`set-briefing`, `_check_po_briefing`), edit_gate.py (Simulation), scripts/ci_spec_gate.py.

### Open Questions
- [ ] Offene Workflows mit freigegebener Spec + Fortsetzungen unter `- Test:`? (Beim Spec-Schreiben in .claude/workflows/ prüfen; sonst reicht Migrationshinweis.)
- [ ] Soll die `- Test:`-Zeile selbst weiter beliebigen Text tragen dürfen? Empfehlung: ja, als Known Limitation (Zuordnung = eine Zeile bleibt beweglich per #439-Design).
