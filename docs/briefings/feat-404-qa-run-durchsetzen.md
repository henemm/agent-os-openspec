---
spec_file: docs/specs/feat-404-qa-run-durchsetzen.md
spec_sha256: 4bc1f7f1bfc120d87e6e591bccfb0ab56c5754d742a1be88b9296fc62eb7f2b9
spec_frozen_sha256: 1b8f9e44129ed82b12904f2571536bbdf8539cc3d39d41410f2c0fafeedbdf31
---

# PO-Briefing: feat-404-qa-run-durchsetzen

- **Spec:** docs/specs/feat-404-qa-run-durchsetzen.md
- **Issue:** #404
- **Erstellt:** 2026-11-26

## Was gebaut wird

Testurteile beruhen künftig auf einem vom Prüfwerkzeug selbst gemessenen Testlauf, der per Schalter vor Commit und Abschluss Pflicht wird.

## Definition of Done

Mit eingeschalteter Pflicht lässt sich ohne grünen, zum aktuellen Code passenden Selbstlauf weder committen noch abschließen; alle Befehle und Agenten nutzen den neuen Aufruf.

## Wie geprüft wird

Für jede Anforderung gibt es einen automatischen Test; nicht belegt wird, ob die Tests inhaltlich gut sind.

## Kritische Anmerkungen

- Pflicht ist standardmäßig aus; ohne Einschalten ändert sich nur ein Hinweistext, Fälschbarkeit bleibt bestehen.
- Geheimnis-Prüfung (F004) anders gelöst als im Ticket: Testbefehl mit Geheimnisdatei wird verweigert, Umwege bleiben unerkannt.
- Rote Testläufe der Phase 5 bleiben dateibasiert und ungeprüft.

## Freigabe-Frage

Keine – Ampel gruen.

## Ampel

Ampel: gruen
