---
spec_file: docs/specs/feat-448-proof-lock-bypass.md
spec_sha256: 05a5e32733eff002d7617fa107dd4e71f894a40e2e8ae9861cf43ee2ab10d3c1
spec_frozen_sha256: 523bfcff44f070617bde35d825ddbf5704b641ae704297be4fa2e78532304dcc
---

# PO-Briefing: feat-448-proof-lock-bypass

- **Spec:** docs/specs/feat-448-proof-lock-bypass.md
- **Issue:** #448
- **Erstellt:** 2026-10-23

## Was gebaut wird

Die Sperre gegen handgeschriebene Simulator-Belege wird gegen gängige Umgehungs-Einzeiler und Symlink-Tricks abgedichtet.

## Definition of Done

Alle 28 bekannten Umgehungsformen werden blockiert, die 10 harmlosen Vergleichsbefehle bleiben frei, und die Fehlermeldung nennt die Ordner-Regel.

## Wie geprüft wird

Automatische Tests spielen jede Umgehungsform und jeden harmlosen Befehl nach; in Skriptdateien versteckte Schreibzugriffe prüfen sie nicht.

## Kritische Anmerkungen

- Bewusste Lücke: Schreibzugriffe über Skriptdateien, xargs oder zusammengesetzte Pfade bleiben möglich; Ziel ist nur „kein trivialer Einzeiler“.
- Verschieben oder Umbenennen des Beleg-Ordners wird auch beim legitimen Aufräumen blockiert, ohne Override-Ausweg.
- Gleiche Lücke bei Config- und Hauptordner-Sperre bleibt offen (Folge-Ticket #452).

## Freigabe-Frage

Soll die Sperre mit diesen bewussten Restlücken und ohne Override-Ausweg so gehärtet werden?
