---
spec_file: docs/specs/feat-447-evidence-gate.md
spec_sha256: 0234a45943e5d2422dbd4635a83b9d1371a034efbfc13dbd8c26c95af4229b82
spec_frozen_sha256: e3814fb1bca79e3264ec4ab77ae7570e853c89719a259b01ac117a7a253a446d
---

# PO-Briefing: feat-447-evidence-gate

- **Spec:** docs/specs/feat-447-evidence-gate.md
- **Issue:** #447
- **Erstellt:** 2026-10-22

## Was gebaut wird

Projekte können einschalten, dass der Abschluss nur mit einem echten, nicht von Hand erzeugbaren Simulator-Testbeleg möglich ist.

## Definition of Done

Mit eingeschaltetem Gate scheitert der Abschluss ohne passenden grünen Beleg, mit echtem Beleg gelingt er; ohne Einstellung ändert sich nichts.

## Wie geprüft wird

Automatische Tests prüfen jeden Ablehnungsgrund und den grünen Fall, aber nur mit simuliertem Apple-Werkzeug, nicht mit einem echten Testlauf.

## Kritische Anmerkungen

- Zusatz: Auch der Fast Track wird bei eingeschaltetem Gate geprüft; das Issue verlangt das nicht.
- Ein alter grüner Lauf oder eine andere Testklasse bleibt als Beleg verwendbar (bekannte Lücke).
- Release und Einschalten in loose-ends sind nicht Teil der Spec.

## Freigabe-Frage

Soll das Gate so gebaut werden, mit Fast-Track-Prüfung und globaler Schreibsperre?
