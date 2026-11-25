---
spec_file: docs/specs/feat-662-kette-flach.md
spec_sha256: 10ebed7b8e5a391015d1644fd4c09f2d523f31ba60a84eb204261a8261ff1d37
spec_frozen_sha256: 913392c1a58283eff53b5424db8cfe335470d015af7868f0ac8091d106dbea13
---

# PO-Briefing: feat-662-kette-flach

- **Spec:** docs/specs/feat-662-kette-flach.md
- **Issue:** #662
- **Erstellt:** 2026-11-25

## Was gebaut wird

Im Auto-Modus läuft die Phasenkette durchgehend weiter; Herdr tippt kein /clear mehr und hält nichts mehr an.

## Definition of Done

Im Auto-Modus hält die Kette nie für Herdr an, im Modus manual weiter an der Kontext-Schwelle mit Checkpoint, alle Tests grün, Version 4.23.0 veröffentlicht.

## Wie geprüft wird

Automatische Tests belegen jede Anforderung einzeln; die Messung, ob der Hauptkontext über eine ganze Kette klein bleibt, fehlt noch.

## Kritische Anmerkungen

- Auch im Modus manual tippt Herdr nichts mehr; du tippst /clear selbst (durch Epic-Entscheidung gedeckt).
- Ohne /clear wächst der Hauptkontext im Auto-Modus; Ausgleich sind nur Teilagenten und automatische Komprimierung.
- Umfang sprengt das Schnittlimit, vom Tech Lead bewusst angenommen.

## Freigabe-Frage

Keine – Ampel gruen.

## Ampel

Ampel: gruen
