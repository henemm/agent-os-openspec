# Context: fix-528-ship-default-branch

## Request Summary
Issue #528 (Folge von #525, Adversary-Funde F002/F003): Im Auto-Modus mit `AUTO_SHIP=on` fehlt in
`/60-validate` ein Weg für den Fall, dass der Checkout direkt auf dem Default-Branch (oder detached
`HEAD`) steht. Heute gilt Punkt 2: „nur committen und der PO in der Abschlussmeldung darauf
hingewiesen“ — das wäre ein Git-Auftrag an den PO und widerspricht #525. Dazu: Text-Tests aus #525
prüfen zu weite Fenster (F002), und der Ausliefer-Block hängt unter Punkt 3 „Deploy bleibt beim PO“
(Layout). PO-Auftrag 2026-11-06: „ja, mach weiter“.

## Related Files
| File | Relevance |
|------|-----------|
| `core/commands/60-validate.md:270-330` | Auto-Modus Punkte 1–4; Punkt 2 Default-Branch-Regel; Punkt 3 enthält Deploy-Satz + `auto-ship`-Block + off-Fall (4.5.4) |
| `skills/60-validate/SKILL.md` | generiert (`scripts/sync_skills.py`) |
| `tests/test_auto_ship_525.py:103` | `_on_windows` (4000 Zeichen ab jedem `AUTO_SHIP=on`) — vom off-Absatz miterfüllt |
| `tests/test_autonomy_kette_472.py` | Fenster-Tests ab `AUTONOMY=auto` (Deploy-Satz muss im Fenster bleiben) |
| `CHANGELOG.md` | [Unreleased] |

## Existing Patterns
- Command-Text steuert das Verhalten; Tests prüfen den Text abschnittsgenau.
- Nie `--force`, nie den Default-Branch pushen (Punkt 2), Schutzregeln nie umgehen (#525).

## Risiken
- Lokale Commits schon auf dem Default-Branch: ein neuer Branch nimmt sie mit; den lokalen
  Default-Branch zurückzusetzen wäre destruktiv (kein `reset`), nach Squash-Merge divergiert er.
- Umstellen der Punkte darf Fenster-Tests aus #472/#489/#525 nicht brechen.

## Analysis

### Type
Bug (Lücke in der Anweisung, Folge von #525)

### Affected Files (with changes)
| File | Change Type | Description |
|------|-------------|-------------|
| core/commands/60-validate.md | MODIFY | `auto-ship`-Prüfung als eigener Punkt vor dem Commit; bei `AUTO_SHIP=on` und Checkout auf Default-Branch/detached `HEAD`: vor dem Commit Feature-Branch `<workflow-name>` anlegen (`git switch -c`), dann normal pushen und ausliefern; nie Git-Auftrag an den PO; off-Fall von Punkt 2 unverändert; Deploy-Punkt ohne Ausliefer-Block |
| skills/60-validate/SKILL.md | MODIFY | per `scripts/sync_skills.py` |
| tests/test_auto_ship_525.py | MODIFY | Fenster auf den on-Absatz begrenzen (Ende am off-Marker) |
| tests/test_ship_default_branch_528.py | CREATE | Text-Tests für den neuen Pfad |
| CHANGELOG.md | MODIFY | [Unreleased] |

### Scope Assessment
- Files: 1 Command (+ generierte Kopie), 2 Tests, CHANGELOG; kein Python-Code
- Estimated LoC: +20/−10 Command-Text
- Risk Level: LOW (nur Anweisungstext und Tests)

### Technical Approach
Reihenfolge im Auto-Modus: (0) `auto-ship` prüfen, (1) bei `on` und Default-Branch/detached `HEAD`
zuerst Branch anlegen, dann committen, (2) pushen, (3) ausliefern, (4) Deploy getrennt, (5) Freigaben
auflisten. Lokaler Default-Branch wird nie zurückgesetzt.

### Open Questions
- keine
