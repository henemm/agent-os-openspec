---
spec_file: docs/specs/feat-470-spec-ampel.md
spec_sha256: 6d78718f4b12f2725b11bdfd27fe1f0be8ab8756eaf97fa082c18f836f31d1e8
spec_frozen_sha256: 5763d92912f69f85c751e99ef9fe0e7cf854c4a9eb2b11b98448fa1fd1aa90da
---

# PO-Briefing: feat-470-spec-ampel

- **Spec:** docs/specs/feat-470-spec-ampel.md
- **Issue:** #470
- **Erstellt:** 2026-10-28

## Was gebaut wird

Im Auto-Modus gibt eine grüne Ampel im Briefing die Spec automatisch frei; bei Rot entscheidest du weiterhin.

## Definition of Done

Bei grüner, unveränderter Ampel geht die Spec ohne dein Wort weiter; bei Rot, Handbetrieb oder geändertem Briefing bleibt sie stehen.

## Wie geprüft wird

Automatische Tests prüfen jede Anforderung; nicht prüfbar bleibt, ob das Briefing wirklich unabhängig entstand.

## Kritische Anmerkungen

- Auflistung automatischer Freigaben in der Abschlussmeldung fordert das Ticket, die Spec verweist dafür nur auf #472.
- Fake-Grün bleibt möglich: Die Urheberschaft des Briefings wird nicht erzwungen, nur Prüfsumme und Protokoll mindern das.

## Freigabe-Frage

Freigeben, obwohl die Abschlussmeldungs-Liste erst mit #472 kommt und Fake-Grün als Restrisiko bleibt?

## Ampel

Ampel: rot
