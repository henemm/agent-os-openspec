---
spec_file: docs/specs/feat-97-secret-egress-redirect-guard.md
spec_sha256: 332766b6d76b48a3784ac1e8acadc8a5be6de4faac3e704519bb50df5682bc24
---

# PO-Briefing: feat-97-secret-egress-redirect-guard

- **Spec:** docs/specs/feat-97-secret-egress-redirect-guard.md
- **Issue:** #97
- **Erstellt:** 2026-09-22

## Was gebaut wird

Schliesst eine Lücke im Leck-Schutz: Befehle, die Zugangsdaten unbemerkt in Dateien ausserhalb des Projekts schreiben, werden blockiert.

## Definition of Done

Der im Ticket gemessene Leck-Fall wird nachweislich blockiert; alle vorgeschriebenen Tests laufen grün, nichts Bestehendes bricht.

## Wie geprüft wird

Automatisierte Tests prüfen jede Anforderung und den realen Vorfall; sie zeigen nicht, ob andere Leck-Wege abgedeckt sind.

## Kritische Anmerkungen

- Scratchpad-Schreibziele sind per Default nicht ausgenommen; das ist der Fehlalarm, den die Anfrage vermeiden wollte.
- Andere Wege, um Daten nach aussen zu schreiben, etwa Datei-Uploads per Kommandozeile, werden noch nicht erkannt.
- Eine einmalige Freigabe schaltet die neue Prüfung eine volle Stunde lang ab, nicht nur für den einen Befehl.

## Freigabe-Frage

Trotz Default-Fehlalarmen bei Scratchpad-Nutzung und fehlender Abdeckung von Upload-Befehlen: Soll dieser Teilschutz jetzt freigegeben werden, mit Nacharbeit später?
