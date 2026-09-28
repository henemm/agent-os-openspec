---
spec_file: docs/specs/feat-285-precondition-origins.md
spec_sha256: d9e30a174557a09ff92430a46f8d614e8615b68fee54a676412800aa3be5a1df
---

# PO-Briefing: feat-273-erreichbarkeitspruefung

- **Spec:** docs/specs/feat-285-precondition-origins.md
- **Issue:** #285 (Scheibe 1 von Epic #273)
- **Erstellt:** 2026-09-28

## Was gebaut wird

Ein Werkzeug findet automatisch, welche Felder Tests nur künstlich vorgeben und wo der Betrieb sie wirklich setzt – als sortierte Verdachtsliste für Prüfer.

## Definition of Done

Jede Abnahmebedingung hat einen automatischen Nachweis; zusätzlich bestätigt ein einmaliger, dokumentierter Testlauf am echten Altfall aus einem anderen Projekt den Befund im vollen Rauschen.

## Wie geprüft wird

Automatische Tests decken alle sieben Kernbedingungen ab, inklusive eines eingefrorenen echten Beispiels; die zusätzliche Vollprobe bleibt ein einmaliger, nicht wiederholbarer Handlauf.

## Kritische Anmerkungen

- Die Vollprobe ist Pflicht für „fertig", läuft aber nur einmal von Hand gegen einen Ordner, der nur auf einem Rechner liegt.
- Umfang wächst auf rund 360 statt 250 Zeilen; meist unverändertes fremdes Beispielmaterial, kaum neuer eigener Code.
- Das Werkzeug erkennt nur einfache Zuweisungen; Umwege wie Reflection oder Setter-Methoden bleiben unentdeckt – es ist ein Hinweis, kein Beweis.

## Freigabe-Frage

Reicht dieser Regelweg als Verdachtsliste für Prüfer, obwohl die abschließende Vollprobe nur einmalig und nicht von jedem wiederholbar ist?
