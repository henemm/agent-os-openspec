---
spec_file: docs/specs/fix-365-heredoc-subst-klammer.md
spec_sha256: 57286821fbe4399a6327ad457795ed83a96fefd19b73d4a263120c9eb0c9d80c
---

# PO-Briefing: fix-365-heredoc-subst-klammer

- **Spec:** docs/specs/fix-365-heredoc-subst-klammer.md
- **Issue:** #365
- **Erstellt:** 2026-10-05

## Was gebaut wird

Die Sicherheitsprüfung für Befehle liest PR-/Commit-Texte künftig immer mit, sodass versteckte Folgebefehle nicht mehr unbemerkt durchrutschen.

## Definition of Done

Der bekannte Umgehungsfall wird blockiert, normale Commit-Texte laufen ohne Fehlalarm, und alle bestehenden Tests sowie der Zusatztest in der CI sind grün.

## Wie geprüft wird

Automatische Tests spielen den Umgehungsfall gegen die echten Prüfungen durch; bash 5 lässt sich nur in der CI nachweisen, nicht lokal.

## Kritische Anmerkungen

- Abweichung vom Issue: PR-Texte mit Gate-Wörtern (.env) lösen bei gh ca. 9 % Fehlalarme aus; Issue versprach keine.
- bash-5-Verhalten ist nur in der CI belegt, nicht lokal.

## Freigabe-Frage

Akzeptierst du ca. 9 % Fehlalarme bei PR-Texten, damit die Sicherheitslücke vollständig geschlossen wird?
