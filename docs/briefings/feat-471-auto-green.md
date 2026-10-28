---
spec_file: docs/specs/feat-471-auto-green.md
spec_sha256: 2981bfccadf7a8e332937db187d7f786e3433cdf34151bcd02e0f310a04dad5e
spec_frozen_sha256: 8156d76b208e28cf89c25e2e82b6f4cd0ed7ed7c410b88b97b891ef18bd64ad4
---

# PO-Briefing: feat-471-auto-green

- **Spec:** docs/specs/feat-471-auto-green.md
- **Issue:** #471
- **Erstellt:** 2026-10-28

## Was gebaut wird

Im Auto-Modus erteilt das System die Freigabe nach den grünen Tests selbst, ohne dass „go" getippt werden muss.

## Definition of Done

Im Auto-Modus läuft die Implementierung ohne Nachfrage weiter und die Freigabe steht im Protokoll; im manuellen Modus bleibt alles unverändert.

## Wie geprüft wird

17 automatische Tests prüfen Freigabe, Sperrfälle und Protokoll; nicht geprüft wird, ob die Testergebnisse inhaltlich grün sind.

## Kritische Anmerkungen

- Die Freigabe prüft nur, dass ein Testprotokoll existiert, nicht dessen Inhalt; fehlschlagende Tests könnten automatisch freigegeben werden.
- Auffälligkeiten stoppen die Freigabe nicht, wie entschieden; sie gehen nur an den Prüfer und die Abschlussmeldung.

## Freigabe-Frage

Soll die Freigabe im Auto-Modus automatisch erfolgen, auch wenn nur das Vorhandensein eines Testprotokolls geprüft wird?

## Ampel

Ampel: gruen
