---
spec_file: docs/specs/feat-467-herdr-auto-clear.md
spec_sha256: 1b7e967e42a8e0d9eac47cd71eb84d4ff3c79f466da758b253262a87778619ad
spec_frozen_sha256: dcc9190c1f8331c3dcd66c8d7a8ab35ff5b5a125a12596e3cb8eaca32bb7b533
---

# PO-Briefing: feat-467-herdr-auto-clear

- **Spec:** docs/specs/feat-467-herdr-auto-clear.md
- **Issue:** #467
- **Erstellt:** 2026-10-28

## Was gebaut wird

Im Herdr-Terminal tippt Claude nach einem sicheren Checkpoint automatisch /clear und danach den nächsten Workflow-Befehl, nur auf Wunsch aktivierbar.

## Definition of Done

In echtem Herdr folgen nach einer Checkpoint-Antwort /clear und der nächste Befehl ohne Zutun; ohne Aktivierung verhält sich alles wie bisher.

## Wie geprüft wird

Automatische Tests mit Herdr-Attrappe prüfen Auslöser, Abbrüche und Reihenfolge; echtes Tippverhalten wird nur manuell abgenommen.

## Kritische Anmerkungen

- Gewünschte Ergänzung fehlt: Workflow-Stand nach /clear automatisch einspielen ist nicht spezifiziert; Wiedereinstieg hängt allein am Befehl mit Issue-Nummer.
- Neue Sitzungskennung nach /clear (Sitzungsregister, Herdr-Wiederaufnahme) ist ungetestet; Parallel-Tippen des Nutzers kann Text vermischen.
- Auslöser-Marker ist nur Textkonvention der Befehle; Vollständigkeit der Sicherung wird nicht geprüft.

## Freigabe-Frage

Freigabe trotz fehlender Stand-Einspielung nach /clear, mit Standard „aus"?
