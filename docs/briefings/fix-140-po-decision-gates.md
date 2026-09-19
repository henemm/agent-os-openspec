---
spec_file: docs/specs/fix-140-po-decision-gates.md
spec_sha256: fbd225d1d835c52116a1badad891e7c28006f0056a056b8565e86f8658ef5d3d
---

# PO-Briefing: fix-140-po-decision-gates

- **Spec:** docs/specs/fix-140-po-decision-gates.md
- **Issue:** #140
- **Erstellt:** 2026-09-19

## Was gebaut wird

Nach deinem "approved" geht es beim Schreiben der Tests automatisch weiter, ohne dass du danach noch selbst einen Befehl eintippen musst.

## Definition of Done

Du erkennst es daran, dass nach "approved" kein weiterer Tastendruck von dir mehr nötig ist, bis die Tests geschrieben sind — der Schritt danach zum eigentlichen Programmieren bleibt weiterhin an deine ausdrückliche Freigabe gebunden.

## Wie geprüft wird

Automatische Tests belegen, dass die Sicherheitsregel (der Stopp vor dem eigentlichen Programmieren) an der richtigen Stelle erhalten bleibt und nichts Bestehendes kaputtgeht, aber nicht, ob das automatische Weitermachen nach "approved" im echten Gespräch tatsächlich eintritt — das lässt sich nur einmalig von Hand beobachten, nicht dauerhaft automatisch nachprüfen.

## Kritische Anmerkungen

- Der wichtigste Effekt dieser Änderung — dass nach "approved" wirklich von selbst weitergemacht wird — hat keinen automatischen Test, sondern nur eine einmalige manuelle Kontrolle. Wird dieses Verhalten durch eine spätere Änderung wieder kaputtgemacht, würde kein Testlauf das bemerken.
- Von den zwei in Issue #140 gemeldeten Problemen wird hier nur eines vollständig gelöst. Das zweite (verständliche Sprache bei der Freigabe) wird nicht mehr in dieser Änderung behoben, sondern soll über ein bereits separat eingeführtes Briefing abgedeckt sein — nachvollziehbar begründet, aber du gibst hier bewusst nicht den vollen ursprünglich gemeldeten Umfang frei.

## Freigabe-Frage

Reicht es dir, wenn nach "approved" nur der Sprung zum Testschreiben automatisch passiert (der Sprung zum eigentlichen Programmieren bleibt weiter manuell), und akzeptierst du, dass dieses automatische Weitermachen nur einmalig von Hand kontrolliert wurde statt dauerhaft automatisch getestet zu sein?
