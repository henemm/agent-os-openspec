# Context: feat-525-auto-ship

## Request Summary
Issue #525: Der PO hat mit Git nichts zu tun und will nie einen PR erstellen oder mergen. Im
Auto-Modus soll Claude nach `phase8_complete` den PR anlegen, die CI abwarten und selbst mergen;
keine ❗Du-Zeile und keine Abschlussmeldung nennt dem PO einen Git-Schritt. PO-Entscheidung
(2026-11-05): gilt für alle Projekte im Auto-Modus, abschaltbar per Config-Schalter; Deploy bleibt
getrennt (`deploy.autonomous`).

## Related Files
| File | Relevance |
|------|-----------|
| `core/commands/60-validate.md:266-350` | Auto-Modus Punkt 1–4 und Abschlussvorlage; 4.5.4 hat Merge/PR nur bei Git-Policy in der Projekt-`CLAUDE.md` freigegeben, sonst „Merge und PR bleiben beim PO“, Vorlage „Offen beim PO: Merge / PR“, ❗Du-Zeile „Merge/PR prüfen“ |
| `skills/60-validate/SKILL.md` | generiert aus `core/commands/60-validate.md` (`scripts/sync_skills.py`), Drift blockt Release |
| `.claude/commands/60-validate.md` | Kurz-Alias, nur Verweis auf den Plugin-Befehl, keine Kopie des Inhalts |
| `core/hooks/workflow.py:976` | `autonomy_mode()` liest `autonomy.mode` nur über `trusted_config()` (#470), Fallback Env `OPENSPEC_AUTONOMY` (#481) |
| `core/hooks/workflow.py:3433` | `cmd_autonomy` / `cmd_autoclear`: Auskunfts-Befehle mit einer Zeile `KEY=value`, Exit immer 0 — Vorbild |
| `core/hooks/workflow.py:3801` | Kommando-Tabelle (`"autonomy": cmd_autonomy`, …) |
| `config.yaml:356` | Abschnitt `autonomy:` (nur `mode` dokumentiert); Schreibzugriff ist per Config-Schutz gesperrt (Ausweg „override“) |
| `CHANGELOG.md` | [Unreleased] |

## Existing Patterns
- Auskunft statt Gate: `workflow.py autonomy` → `AUTONOMY=auto|manual`, `workflow.py autoclear` →
  `AUTO_CLEAR=on|off`; fail-closed, Exit 0, kein aktiver Workflow nötig.
- Kill-Switch-Semantik: nur ein ausdrückliches `false` schaltet ab.
- Command-Text ist die Steuerung für Claude; Tests prüfen den Command-Text (z. B. Tests zu #472/#489).

## Dependencies / Dependents
- Hängt an `autonomy_mode()` und `trusted_config()`.
- Konsumenten-Projekte bekommen den neuen Text über Plugin/`setup.py --update`.

## Risiken
- Automatischer Merge auf den Default-Branch in jedem Auto-Modus-Projekt: Schutzregeln
  (Branch-Protection, Pflicht-Reviews) nie umgehen, rote CI nie überbrücken, nie `--force`.
- Projekte ohne CI: „CI abwarten“ ist leer — Regel nötig (keine Checks → Merge erlaubt? oder
  lokale Tests als Ersatz).
- Projekte ohne Remote/ohne GitHub-Zugang: Merge unmöglich → Problem in Alltagssprache melden,
  ohne Git-Auftrag an den PO.

## Analysis

### Type
Feature (Verhaltensänderung Auto-Modus)

### Affected Files (with changes)
| File | Change Type | Description |
|------|-------------|-------------|
| core/hooks/workflow.py | MODIFY | `auto_ship_enabled()` + `cmd_auto_ship` → `AUTO_SHIP=on|off` (on nur bei `AUTONOMY=auto` und `autonomy.ship` nicht `false`, gelesen über `trusted_config()`) |
| core/commands/60-validate.md | MODIFY | Auto-Modus Punkt 3: bei `AUTO_SHIP=on` PR anlegen → CI abwarten → mergen (Merge-Methode des Repos), bei roter CI reparieren oder in Alltagssprache melden; Abschlussvorlage ohne Git-Schritte für den PO; bei `off` bisheriger Text (Git-Policy der Projekt-`CLAUDE.md` aus 4.5.4) |
| skills/60-validate/SKILL.md | MODIFY | per `scripts/sync_skills.py` |
| tests/test_auto_ship_525.py | CREATE | CLI-Auskunft + Command-Text |
| CHANGELOG.md | MODIFY | [Unreleased] |

### Scope Assessment
- Files: 1 Code, 1 Command (+ generierte Skill-Kopie), 1 Test neu, CHANGELOG
- Estimated LoC: +40 Code, +30/−15 Command-Text
- Risk Level: HIGH (automatischer Merge in Konsumenten-Projekten)

### Technical Approach
Auskunfts-Befehl nach Vorbild `autonomy`/`autoclear`, Command-Text steuert das Verhalten. Kein
Config-Datei-Edit nötig: Default „an“ im Auto-Modus steckt im Code, `autonomy.ship: false` schaltet
ab (Dokumentation im Command-Text und CHANGELOG; Kommentar in `config.yaml` nur per „override“).

### Open Questions
- keine (PO-Entscheidungen liegen vor)
