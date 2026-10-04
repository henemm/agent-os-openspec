---
spec_file: docs/specs/feat-251-kurzbefehle.md
spec_sha256: a36d6f0c5bed04c4030d1f4c882f9e93a7a40079861806cd40f972593252d582
---

# PO-Briefing: feat-251-kurzbefehle

- **Spec:** docs/specs/feat-251-kurzbefehle.md
- **Issue:** #251
- **Erstellt:** 2026-10-04

## Was gebaut wird

Kurz-Befehle zeigen in der Befehlsauswahl ihre Beschreibung, und markierte Kurz-Befehle lassen sich per Werkzeug entfernen.

## Definition of Done

Befehlsauswahl zeigt Beschreibung statt Marker, alte Kopien werden aktualisiert, markierte lassen sich entfernen, eigene Dateien bleiben unberührt.

## Wie geprüft wird

Automatische Tests prüfen Format, Erkennung, Aktualisieren, Entfernen; nicht geprüft: ob Claude Code die Beschreibung wirklich anzeigt.

## Kritische Anmerkungen

- Prüfmodus im Release verlangt; Spec verzichtet bewusst (benennt es selbst), vorhandener Test genügt — PO entscheidet, ob das reicht.
- Zielbild „Vollkopien global“ und Worktree-Fix (#242) entfallen; eingefrorene Vollkopien werden nur per Test erkannt, nicht verhindert.
- Fußzeilen-Kriterium offen (#235); „jeder Name genau einmal“ folgt erst durch Datenschritt auf diesem Rechner, nicht durch Tests.

## Freigabe-Frage

Reicht Beschreibungs-Korrektur plus Entfernen-Werkzeug, ohne globale Ablage, Fußzeilen-Prüfung und Prüfmodus im Release?
