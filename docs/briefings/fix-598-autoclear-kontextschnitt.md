---
spec_file: docs/specs/fix-598-autoclear-kontextschnitt.md
spec_sha256: b050c4ffb9c13bc323760d288e34070e6673c0c4916e9ae048ba2f38c5b107f6
spec_frozen_sha256: 4ef88c820209876240b0222850dc9dbccbc9cf07d4452d1d55ae333e3cd3518a
---

# PO-Briefing: fix-598-autoclear-kontextschnitt

- **Spec:** docs/specs/fix-598-autoclear-kontextschnitt.md
- **Issue:** #598
- **Erstellt:** 2026-11-25

## Was gebaut wird

Automatisches Neustarten der Sitzung greift jetzt auch, wenn mitten in einer Phase die Kontext-Grenze erreicht wird.

## Definition of Done

Bei erreichter Kontext-Grenze startet der Neustart ohne Zutun des Modells, wenn die Fußzeile den Folgebefehl nennt; alle bisherigen Schutzregeln bleiben.

## Wie geprüft wird

Automatische Tests an der echten Abschlussprüfung prüfen Auslösen und alle Nicht-Auslöse-Fälle; der Live-Ablauf im Herdr-Fenster wird nicht getestet.

## Kritische Anmerkungen

- Ohne Messdatei der Sitzung greift der Neustart weiterhin nicht; der Fix deckt nur Fälle mit vorhandener Messung ab.
- Gilt für alle im Ticket genannten Fälle (Fix-Schleife, Rücksprung nach Prüfer-Urteil, mitten in der Umsetzung); es ist eine Übergangslösung bis zum geplanten Umbau.

## Freigabe-Frage

Keine – Ampel gruen.

## Ampel

Ampel: gruen
