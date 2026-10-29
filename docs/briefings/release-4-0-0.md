---
spec_file: docs/specs/release-4-0-0.md
spec_sha256: 75ecbe7dce12cd8d0540da64c8ec3758a7731d1f989b836deaef47c2660925cf
spec_frozen_sha256: 772c345234bec9732149a1de96e278325eac140d37daad8f1882c4e2bca5ef4a
---

# PO-Briefing: release-4-0-0

- **Spec:** docs/specs/release-4-0-0.md
- **Issue:** keine
- **Erstellt:** 2026-10-29

## Was gebaut wird

Die zuletzt gemergten Funktionen werden als neue Hauptversion 4.0.0 des Plugins bereitgestellt.

## Definition of Done

Alle Versionsangaben zeigen 4.0.0, das Änderungsprotokoll nennt die Breaking-Änderungen, und nach dem Merge erscheint Version 4.0.0 automatisch.

## Wie geprüft wird

Tests belegen übereinstimmende Versionsangaben und den Protokoll-Abschnitt; sie prüfen weder die einzelnen Ticketnummern noch den Breaking-Hinweis.

## Kritische Anmerkungen

- Der Breaking-Hinweis im Änderungsprotokoll (Kriterium 6) hat keinen Test; Sie prüfen ihn selbst im Review.
- Die Ticketnummern im Protokoll sind ungetestet; Vollständigkeit prüfen Sie selbst.
- Bestehende Anwender können Verhaltensänderungen erleben: Config-Sperre, strengere Edit-Grenzen.

## Freigabe-Frage

Soll Version 4.0.0 ausgeliefert werden, wobei Sie Breaking-Hinweis und Ticketnummern selbst prüfen?

## Ampel

Ampel: rot
