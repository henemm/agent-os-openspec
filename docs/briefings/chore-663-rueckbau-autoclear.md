---
spec_file: docs/specs/chore-663-rueckbau-autoclear.md
spec_sha256: e2eaff6d999c53545f6d69ed3291a1880fbb4de946e6d47a5fa8691f5d365509
spec_frozen_sha256: bbe6abdd4adf62b6c6f8a14424aa53c2fdb3912263b441bcd61326f5e73294a9
---

# PO-Briefing: chore-663-rueckbau-autoclear

- **Spec:** docs/specs/chore-663-rueckbau-autoclear.md
- **Issue:** #663
- **Erstellt:** 2026-11-25

## Was gebaut wird

Der tote Auto-/clear-Code verschwindet vollständig; Herdr zeigt nur noch an, Seitenleiste und Plan-Fenster bleiben unverändert.

## Definition of Done

Nichts tippt mehr in Herdr, Seitenleiste und Plan-Fenster funktionieren wie zuvor, alle Tests grün, Version 4.24.0 veröffentlicht, Issues 505, 601, 503 geschlossen.

## Wie geprüft wird

Neue Tests belegen, dass nichts mehr startet oder schreibt; bestehende Seitenleisten- und Plan-Tests laufen unverändert; echtes Herdr-Verhalten bleibt ungeprüft.

## Kritische Anmerkungen

- Konfigdatei bleibt unverändert: ihr Kommentar beschreibt Auto-/clear weiter als wirksam; Aufräumen nur als Folge-Ticket.
- Anfrage verlangt Doku ohne Auto-/clear; CLAUDE.md behält eine Halbzeile zum weiterhin antwortenden Befehl „autoclear“.
- Rund 6000 gelöschte Zeilen sprengen das Schnittlimit; bewusst als eine zusammenhängende Löschung begründet.

## Freigabe-Frage

Keine – Ampel gruen.

## Ampel

Ampel: gruen
