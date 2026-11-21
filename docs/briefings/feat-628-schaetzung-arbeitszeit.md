---
spec_file: docs/specs/feat-628-schaetzung-arbeitszeit.md
spec_sha256: 9bdb950438286aebacc1a78dcfa5a2a65b552f2e0b5257e8cd19698f48297b5b
spec_frozen_sha256: 39058791d5cef9e13201ed5d62a5609ce8edceb66e09b7d60a39158ea4b5f42f
---

# PO-Briefing: feat-628-schaetzung-arbeitszeit

- **Spec:** docs/specs/feat-628-schaetzung-arbeitszeit.md
- **Issue:** #628
- **Erstellt:** 2026-11-21

## Was gebaut wird

Die Zeitschätzung im Plan zeigt nur noch echte Arbeitszeit, ohne Nacht und Warten auf deine Freigabe.

## Definition of Done

Die Zeitspanne wird auf elf alten Workflows nachgerechnet und liegt dann meist unter zwei Stunden; „+ Wartezeit auf dich“ erscheint bei offenem „approved“ oder „go“.

## Wie geprüft wird

Automatische Tests belegen jede Anforderung, auch die Nachrechnung mit elf echten Altdaten; wie nützlich die Spanne im Alltag ist, prüft kein Test.

## Kritische Anmerkungen

- Alte Workflows ohne Aktivitätsdaten behalten Leerlauf nach automatischer Freigabe; die Schätzung bleibt dort etwas zu hoch (in der Spec benannt).
- Die Beschreibung im Umsetzungsteil nennt den Hinweis noch nur für „approved“; maßgeblich ist die Anforderung, die „go“ einschließt.

## Freigabe-Frage

Keine – Ampel gruen.

## Ampel

Ampel: gruen
