---
spec_file: docs/specs/fix-141-stop-lock-false-positive.md
spec_sha256: 38a4bbb022c761f7d5d4b188cb0d831cfdb1c510c253c23a2b3c7e51ba5422ed
---

# PO-Briefing: fix-141-stop-lock-false-positive

- **Spec:** docs/specs/fix-141-stop-lock-false-positive.md
- **Issue:** #141
- **Erstellt:** 2026-09-19

## Was gebaut wird

Wenn ein von Claude im Hintergrund gestarteter Hilfs-Assistent in seinem Abschlussbericht ein Stop-Wort wie "STOPP" oder "halt" nur zitiert (z. B. als Beispieltext), soll das nicht mehr fälschlich einen echten Not-Halt der ganzen Session auslösen.

## Definition of Done

Fertig ist es, wenn sechs automatische Testfälle belegen, dass ein im Bericht eines Hilfs-Assistenten zitiertes Stop-Wort keinen Halt mehr auslöst und einen bereits aktiven Halt nicht fälschlich aufhebt, dass ein echtes "stop" vom User selbst weiterhin sofort und unverändert greift, und dass die bestehende Test-Suite dabei grün bleibt.

## Wie geprüft wird

Die Tests bilden genau die gemeldete Situation nach (zitiertes Stop-Wort im Bericht eines Hilfs-Assistenten) und prüfen automatisiert, ob der Not-Halt greift oder nicht — sie können laut Spec aber nicht beweisen, dass der als Erkennungsmerkmal gewählte Rahmentext in der echten Systemumgebung tatsächlich so ankommt wie angenommen, weil das am lebenden System nicht gegengetestet wurde (geschützte Kern-Datei, kein Testzugriff vor Freigabe).

## Kritische Anmerkungen

- Größtes Risiko laut Spec selbst: Die zentrale Annahme, dass der umschließende Rahmentext um den Bericht des Hilfs-Assistenten wirklich so bei der Prüfung ankommt wie erwartet, wurde nicht direkt am echten System nachgewiesen. Ist die Annahme falsch, tritt der ursprüngliche Fehler trotz Fix unverändert wieder auf — das würde sich erst bei einem erneuten Vorfall in echtem Betrieb zeigen.
- Zwei verwandte, aber andere Ursachen für denselben Fehlalarm bleiben bewusst außen vor und laufen als eigene Themen: ein häufiges deutsches Füllwort ("halt"), das auch in echten Nachrichten von Menschen vorkommt, sowie ein unabhängiger Fehler in einem ganz anderen Schutzmechanismus. Nachvollziehbar begründet, aber "STOPP"-Fehlalarme sind mit diesem Fix noch nicht vollständig ausgeschlossen.
- Kleines, bewusst in Kauf genommenes Restrisiko (bereits heute bei fünf ähnlichen Fällen akzeptiert): Zitiert ein echter Mensch einen der beiden neuen Erkennungstexte wörtlich in einer Nachricht, die im selben Moment auch einen echten Halt oder eine echte Freigabe enthält, wird dieser Teil der Nachricht ignoriert.

## Freigabe-Frage

Soll dieser gezielte, risikoarme Fix für den zweimal live aufgetretenen Fall (Fehlalarm durch Hilfs-Assistenten-Bericht) jetzt freigegeben werden — wohl wissend, dass die zwei verwandten Stop-Wort-Probleme (Füllwort "halt", anderer Schutzmechanismus) bewusst offen bleiben und getrennt behandelt werden?
