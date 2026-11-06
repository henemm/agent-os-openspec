# Context: fix-530-default-branch-fallback

## Request Summary
Issue #530 (Folge von #528, Adversary-Funde F001–F003): Im Auto-Modus von `/60-validate`
ermitteln Punkt 2 und 3 den Default-Branch nur über `git symbolic-ref --short
refs/remotes/origin/HEAD`. Fehlt `origin/HEAD` lokal, wird heute nicht gepusht und bei
`AUTO_SHIP=on` nicht ausgeliefert. Dazu: Namenskonflikt beim neuen Feature-Branch nennt nicht
„lokal oder Remote“; kein Test bindet die Punktnummern-Verweise. PO-Entscheidung 2026-11-06: Claude
entscheidet als Tech Lead; alle drei Punkte in einem Durchgang.

## Related Files
| File | Relevance |
|------|-----------|
| `core/commands/60-validate.md:282-295` | Punkt 2 (Branch-Anlage, Namenskonflikt) und Punkt 3 (Default-Branch-Ermittlung, „Schlägt `git symbolic-ref` fehl, wird nicht gepusht“) |
| `core/commands/60-validate.md` Punkt 5 + Abschlussvorlage | Verweise „Nach Punkt 2 und 3“, „Das Verbot aus Punkt 3“, „siehe Punkt 5“ (2×) |
| `skills/60-validate/SKILL.md` | generiert (`scripts/sync_skills.py`) |
| `tests/test_ship_default_branch_528.py` | Abschnitts-/Listenpunkt-Parser für Text-Tests (Vorbild) |
| `CHANGELOG.md` | [Unreleased] |

## Existing Patterns
- `git ls-remote --symref origin HEAD` liefert `ref: refs/heads/<branch>\tHEAD` ohne lokales
  `origin/HEAD` (in diesem Repo geprüft: `ref: refs/heads/main	HEAD`).
- Bei `AUTO_SHIP=on` nie ein Git-Auftrag an den PO (#525/#528); bei `off` bleibt der bisherige Text.

## Risiken
- `ls-remote` braucht Netz/Zugang: schlägt es fehl, muss der Meldeweg klar sein (on: Alltagssprache,
  off: wie bisher „nicht gepusht, gemeldet“).
- Fenster-Tests aus #472 (Deploy-Satz in 4000 Zeichen ab `AUTONOMY=auto`): neuer Text vor Punkt 4
  verlängert den Abstand — knapp halten (seit #528 noch etwa 3600 Zeichen bis zum Deploy-Satz, nachmessen).

## Analysis

### Type
Bug (Lücke in der Anweisung)

### Affected Files (with changes)
| File | Change Type | Description |
|------|-------------|-------------|
| core/commands/60-validate.md | MODIFY | Punkt 3: Fallback `git ls-remote --symref origin HEAD`, Meldeweg je `AUTO_SHIP`; Punkt 2: Verweis auf diese Ermittlung, Namenskonflikt „lokal oder auf dem Remote“ |
| skills/60-validate/SKILL.md | MODIFY | per `scripts/sync_skills.py` |
| tests/test_default_branch_fallback_530.py | CREATE | Text-Tests zu Fallback, Meldeweg, Namenskonflikt, Punkt-Verweisen |
| CHANGELOG.md | MODIFY | [Unreleased] |

### Scope Assessment
- Files: 1 Command (+ generierte Kopie), 1 Test neu, CHANGELOG; kein Python-Code
- Estimated LoC: +8/−3 Command-Text, +120 Test
- Risk Level: LOW

### Technical Approach
Ermittlung einmal in Punkt 3 beschreiben (erst `symbolic-ref`, dann `ls-remote`), Punkt 2 verweist
darauf statt den Befehl zu wiederholen (spart Zeichen vor dem Deploy-Satz). Verweis-Test: jede
Stelle „Punkt N“ im Auto-Modus-Abschnitt wird gegen den fett gesetzten Titel des Listenpunkts N
geprüft (erwartete Zuordnung im Test festgehalten).

### Open Questions
- keine
