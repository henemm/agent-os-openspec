---
spec_file: docs/specs/fix-313-327-qa-gate-testausgabe.md
spec_sha256: bc745ccf790b63e2a7d5d36940d5ae0804637ea285f239d992c439c618fd81cc
---

# PO-Briefing: fix-313-327-qa-gate-testausgabe

- **Spec:** docs/specs/fix-313-327-qa-gate-testausgabe.md
- **Issue:** #313, #327
- **Erstellt:** 2026-10-03

## Was gebaut wird

Das Qualitäts-Tor erkennt Testergebnisse von unittest und node --test zuverlässig als bestanden oder fehlgeschlagen.

## Definition of Done

Echte grüne und rote Testläufe beider Werkzeuge ergeben über das Tor das richtige Urteil; ein roter Lauf geht nie als grün durch.

## Wie geprüft wird

Automatische Tests mit echten Beispielausgaben belegen alle 16 Kriterien; nicht belegt ist, dass von Hand geschriebene Ausgaben abgewiesen werden.

## Kritische Anmerkungen

- Kleine unittest-Läufe unter 100 Byte (ein Test, ohne -v) werden weiter abgewiesen, obwohl #313 sie nennt.
- Dateiende-Regel aus #327 bewusst nicht übernommen, sonst würden rote Läufe übersehen; Spec begründet das nachvollziehbar.
- Von Hand angehängte Erfolgszeilen bleiben möglich; Lösung dafür ist erst Issue #345.

## Freigabe-Frage

Soll das Tor diese Formate erkennen, obwohl Einzeltest-Läufe ohne -v weiter abgewiesen werden?
