---
spec_file: docs/specs/infra/feat-543-settings-plugin-exception.md
spec_sha256: 864301e66a512eabedce9e0d0dc53312abe7a7a24af8d24266a7cb7d456231a2
spec_frozen_sha256: 67485214327312a11466406de70c5db81062a259e7960042c4e7dda3776e904f
---

# PO-Briefing: feat-543-settings-plugin-exception

- **Spec:** docs/specs/infra/feat-543-settings-plugin-exception.md
- **Issue:** #543
- **Erstellt:** 2026-11-08

## Was gebaut wird

Sitzungen dürfen Plugins und Marketplaces in die Projekt-Einstellungsdatei eintragen; alle anderen Einstellungen bleiben gesperrt.

## Definition of Done

Neue Datei und Plugin-Ergänzung gehen ohne Override durch, Änderungen an Hooks, Rechten und Umgebung bleiben gesperrt.

## Wie geprüft wird

Automatische Tests belegen Erlaubnis, Sperre, kaputte Eingaben, Meldungstext und Override; ob ein Plugin vertrauenswürdig ist, prüfen sie nicht.

## Kritische Anmerkungen

- Ein eingetragenes Plugin bringt eigene Hooks mit; Hooks sind nur gegen direktes Eintragen geschützt, nicht gegen fremde Plugins.
- Die Restock-Einrichtung ist nicht Teil dieser Änderung, sondern folgt nach Auslieferung als eigener Schritt.
- Zusätzlich zum Ticket entfällt der Skill-Hinweis in der Sperrmeldung; stattdessen steht dort der Weg über „override“.

## Freigabe-Frage

Keine – Ampel gruen.

## Ampel

Ampel: gruen
