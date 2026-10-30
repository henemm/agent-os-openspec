---
spec_file: docs/specs/fix-495-autoclear-mechanisch.md
spec_sha256: d94a31c87da609be64f28accc8220751b69288ce6cd5412eb88d0f458c38bf7d
spec_frozen_sha256: 8707db46bcb65c83da543060c8f4fee18834d8c707199a52aed9828e4ee2b457
---

# PO-Briefing: fix-495-autoclear-mechanisch

- **Spec:** docs/specs/fix-495-autoclear-mechanisch.md
- **Issue:** #495
- **Erstellt:** 2026-10-30

## Was gebaut wird

An der Phasengrenze tippt Herdr automatisch /clear und den Folgebefehl, ohne dass Claude einen bestimmten Satz schreiben muss.

## Definition of Done

Im echten Herdr mit eingeschaltetem Auto-/clear erscheint am Phasenende /clear samt Folgebefehl, auch ohne den bisherigen Pflichtsatz; du bestätigst das manuell.

## Wie geprüft wird

Automatische Tests belegen Vermerk, Auslösen, Nicht-Auslösen bei veraltetem Stand oder Veto und Einmaligkeit; das echte Herdr-Verhalten belegen sie nicht.

## Kritische Anmerkungen

- Ruft Claude am Phasenende den Vermerk-Befehl nicht auf, bleibt der Fehler bestehen; die Spec sichert das nicht ab.
- Die geforderte gründliche Recherche ist in der Spec nicht belegt; sie nennt nur die Log-Ursache.
- Der Vermerk garantiert nicht, dass der Stand gesichert ist; nur das Veto des Modells verhindert ein verfrühtes /clear.

## Freigabe-Frage

Keine – Ampel gruen.

## Ampel

Ampel: gruen
