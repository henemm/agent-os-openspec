# Fast Track: Fußzeile sagt, wer am Zug ist (#174, 3.27.2)

## Problem

Jede Phasen-Nachricht endete mit „… Nächster Pflicht-Schritt: /befehl“. Der PO (nicht-technisch)
las das als Aufforderung, etwas tun zu müssen — auch wenn Claude gerade selbst arbeitete oder auf
einen Hintergrund-Agenten wartete. Rückmeldung vom 2026-09-21: „das wirkt auf mich immer irritierend,
also müsste ich etwas tun. Dabei ist es nur Teil vom Footer.“

## Scope

- `scripts/sync_skills.py`: Textbaustein `marker_block` legt fest, dass die erste Zeile am Ende
  entweder `❗ Du: …` (PO ist dran) oder `ℹ️ Nichts zu tun: … — danach: …` (Claude arbeitet) lautet,
  gefolgt von `ℹ️ Status: Workflow … · Phase x von 8` und der unveränderten ⚙-Zeile
- `core/hooks/workflow.py`: `status_note` gibt Claude dieselbe Kennzeichnung mit, damit sie auch in
  frei formulierten Nachrichten gilt (Loop-Aufwacher, Zwischenfragen)
- `skills/*/SKILL.md` neu generiert, Version 3.27.2, CHANGELOG
- Nicht enthalten: ein Stop-Hook, der das Format erzwingt (zurückgestellt in #177)

## Definition of Done

Der PO erkennt am Ende jeder Phasen-Nachricht an der ersten Zeile, ob er etwas tun muss (`❗`) oder
nichts zu tun ist (`ℹ️`). Der nächste Schritt wird weiterhin in jeder Nachricht genannt, und die
Regel „Phase kleiner als 8 ist nie optional“ bleibt bestehen.

## Acceptance Criteria

- **AC-1:** Given ein generierter Skill außer `30-write-spec`, When er ausgeführt wird, Then verlangt sein Marker-Abschnitt als erste Schlusszeile entweder `❗ Du:` oder `ℹ️ Nichts zu tun:`, danach die Zeile `ℹ️ Status: Workflow` und zuletzt die ⚙-Zeile.
- **AC-2:** Given der Statusvermerk des Hooks für einen aktiven Workflow vor Phase 8, When er erzeugt wird, Then nennt er weiterhin „Nächster Pflicht-Schritt: <schritt>“ und zusätzlich beide Kennzeichnungen `❗ Du:` und `ℹ️ Nichts zu tun:`.
- **AC-3:** Given Marker-Abschnitt und Hook-Vermerk, When beide verglichen werden, Then verwenden sie dieselben zwei Kennzeichnungen, und der Marker-Abschnitt verweist auf den Namen „Nächster Pflicht-Schritt“ aus dem Hook-Hinweis.
- **AC-4:** Given die Phase ist kleiner als 8, When der Marker-Abschnitt gelesen wird, Then verbietet er weiterhin „bei Bedarf“, „optional“ und „fertig“ für den Workflow als Ganzes.
- **AC-5:** Given eine Änderung an `core/commands` oder `sync_skills.py`, When `sync_skills.py --check` läuft, Then meldet es alle 16 Skills synchron.

## Test Plan

- `tests/test_skills_sync.py`: ein neuer Test für die zwei Formen der ersten Zeile, drei angepasste Tests für Reihenfolge, Hook-Abgleich und Skill-Inhalt (AC-1, AC-3, AC-4)
- `tests/test_status_note_325.py`: ein neuer Test, dass der Hook-Vermerk beide Kennzeichnungen enthält (AC-2)
- Volle Suite: 980 passed; `sync_skills.py --check` meldet 16 Skills synchron (AC-5)
- Wirkung im Alltag: wird nach dem Plugin-Update am Ende der nächsten Phasen-Nachricht beobachtet
