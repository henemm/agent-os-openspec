---
spec_file: docs/specs/fix-144-briefing-worktree-path.md
spec_sha256: 5c2a92c601aaf3a60ad047918fa7770e80eec8e8c95ef483684db895e9cedd11
---

# PO-Briefing: fix-144-briefing-worktree-path

- **Spec:** docs/specs/fix-144-briefing-worktree-path.md
- **Issue:** #144
- **Erstellt:** 2026-09-19

## Was gebaut wird

Der Fehler, dass eine isolierte Arbeitssitzung ihre eigene, gerade erst geschriebene Spezifikations- und Freigabe-Datei nicht findet, wird behoben, damit die Registrierung der Freigabe künftig ohne Umweg funktioniert.

## Definition of Done

Fertig ist es, wenn in einer echten isolierten Sitzung die Registrierung des Freigabe-Dokuments direkt gelingt (kein Workaround nötig) und alle bisherigen Funktionen nachweislich unverändert weiterlaufen.

## Wie geprüft wird

Automatisierte Tests weisen nach, dass Dateien in isolierten wie in normalen Sitzungen richtig gefunden werden und nichts Bestehendes kaputtgeht; sie zeigen aber nicht, ob die dabei reaktivierte Zusatzprüfung (siehe unten) andere, gerade laufende Freigaben in der Praxis stört.

## Kritische Anmerkungen

- Der Fix schaltet als Nebeneffekt eine seit Monaten stillschweigend wirkungslose Pflichtprüfung (dokumentierte Architektur-Entscheidung) für alle isolierten Sitzungen wieder scharf — das stand nicht in der Fehlermeldung und kann andere, bereits laufende Freigaben blockieren, deren Spezifikation diese Angabe nicht ausgefüllt hat.
- Der gewählte technische Lösungsweg weicht bewusst vom im Issue skizzierten Vorschlag ab (eine neue, eigene Hilfsfunktion statt der im Issue genannten, bereits vorhandenen); nachvollziehbar begründet (Risiko zirkulärer Abhängigkeiten), aber eine Abweichung vom wörtlichen Vorschlag.
- Ein seltener Sonderfall (Registrierung mit einem vollständigen statt dem üblichen kurzen Dateipfad) ist zwar beschrieben, aber durch keinen eigenen Test abgesichert.

## Freigabe-Frage

Soll dieser Fix wie vorgeschlagen freigegeben werden — inklusive der Nebenwirkung, dass die Architektur-Entscheidungs-Pflicht für alle isolierten Sitzungen wieder aktiv wird und dadurch auch andere, bereits laufende Arbeiten künftig blockieren kann?
