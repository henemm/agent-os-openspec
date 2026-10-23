---
spec_file: docs/specs/fix-453-proof-lock-gaps.md
spec_sha256: bd2e3d9381b479b68025562eede165ba420e77a0964b8d37f34d08d86993f9cd
spec_frozen_sha256: fcb7f7469c28229d3b988fbbf9458a9d2ff260154cf25c4dcce805f3435f8487
---

# PO-Briefing: fix-453-proof-lock-gaps

- **Spec:** docs/specs/fix-453-proof-lock-gaps.md
- **Issue:** #453
- **Erstellt:** 2026-10-23

## Was gebaut wird

Claude kann den Simulator-Beleg nicht mehr per Umweg von Hand fälschen; ein Fehlalarm beim reinen Lesen entfällt.

## Definition of Done

Alle genannten Umgehungen werden blockiert, der Fehlalarm ist behoben, bestehende Tests bleiben grün.

## Wie geprüft wird

Automatische Tests probieren jeden Umweg und erlaubte Gegenbeispiele gegen die echte Sperre; unbekannte weitere Umgehungen decken sie nicht ab.

## Kritische Anmerkungen

- Löschen des Belegs und Ordneranlegen bleiben bewusst erlaubt, obwohl die Anfrage sie nannte.
- Die Variante "X=Beleg tee $X" bleibt erlaubt, da technisch kein Angriff.
- Weitere Umgehungen (su, runuser, mehrstufige Variablen) bleiben offen.

## Freigabe-Frage

Ist es akzeptabel, nur Fälschen zu sperren, da die Abschlussprüfung gelöschte Belege ohnehin ablehnt?
