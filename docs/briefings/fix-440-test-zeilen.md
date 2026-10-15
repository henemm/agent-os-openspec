---
spec_file: docs/specs/fix-440-test-zeilen.md
spec_sha256: bd8aa4b7695b9fb1a2a7851936a052575f4534354ffecacef54a019b4df9b9b4
---

# PO-Briefing: fix-440-test-zeilen

- **Spec:** docs/specs/fix-440-test-zeilen.md
- **Issue:** #440
- **Erstellt:** 2026-10-14

## Was gebaut wird

Nach der Freigabe lässt sich in einer Spec nur noch die Testzuordnungs-Zeile ändern; Folgezeilen und Fließtext sind gesperrt.

## Definition of Done

Neuer Anforderungstext unter einer Testzeile wird immer blockiert, die Testzeile selbst bleibt änderbar, und fehlerhafte Eingaben führen nicht mehr zum Absturz.

## Wie geprüft wird

Automatische Tests belegen Sperre je Umgehungsform, gleichen Schutz für Specs ohne Fortsetzung und Absturzfreiheit; nicht belegt: Inhalt der Testzeile selbst.

## Kritische Anmerkungen

- Bei 12 von 69 Alt-Specs ändert sich der Schutzwert; deren Briefings gelten als veraltet.
- Die Testzeile selbst darf weiter beliebigen Text tragen; dort eingetragene Anforderungen kommen ohne Rücksprung durch.
- Zeilenumbruch langer Testpfade zählt künftig als Spec-Änderung und erfordert Rücksprung.

## Freigabe-Frage

Soll die Sperre auf alles außer der Testzeile ausgeweitet werden, obwohl alte Briefings dadurch neu erstellt werden müssen?
