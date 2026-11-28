---
spec_file: docs/specs/feat-707-deploy-selbst.md
spec_sha256: b370aba11e525211675af52099e75bc8a8ca18e0a84c5eeda30099aa6c927bb9
spec_frozen_sha256: 3d84a1c89c1cebd973653c0fc494f303d2d411fa6e6a8f0c1b67e25ace72a941
---

# PO-Briefing: fix-707-deploy-selbst

- **Spec:** docs/specs/feat-707-deploy-selbst.md
- **Issue:** #707
- **Erstellt:** 2026-11-28

## Was gebaut wird

Ist Autonomie fürs Deployen eingeschaltet, löst Claude das Deployen nach der Prüfung selbst aus; sonst bleibt es beim PO.

## Definition of Done

Mit eingeschalteter Autonomie endet der Ablauf ohne PO-Eingriff mit „✅ … deployt“; ohne Autonomie fordert er weiterhin den PO zum Deploy auf.

## Wie geprüft wird

Automatische Tests prüfen Sperre, Freigabe, Anleitungstexte und Endmeldung; einen echten Durchlauf mit Deploy beweisen sie nicht.

## Kritische Anmerkungen

- Zusatz zum Ticket: Deploy-Schalter wird im Worktree vom gemergten Stand gelesen; ein Widerruf auf origin gewinnt.
- Die Abnahme „Claude ruft selbst auf“ ist nur über Anleitungstexte getestet, nicht live.

## Freigabe-Frage

Keine – Ampel gruen.

## Ampel

Ampel: gruen
