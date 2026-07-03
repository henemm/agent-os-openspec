# Mini-Spec: fix-46-notification-keyword-bypass

## Problem (Issue #46, sicherheitsrelevant, live in gregor_zwanzig aufgetreten)
`phase_listener.py` (UserPromptSubmit-Hook) erkennt Freigabe-Stichworte per
Wortgrenzen-Regex irgendwo im gesamten Prompt-Text. Task-Notifications
(Ergebnistexte von Background-Agenten) laufen durch denselben Pfad — enthält so
ein Text die Phrase nur als **Erwähnung** ("Bestätige mit 'approved' um
fortzufahren"), wird die Freigabe gesetzt, ohne dass der User je zugestimmt hat.
Betrifft alle keyword-sensitiven Gates (approved/go/override/stop/...).

## Was ändert sich (`core/hooks/phase_listener.py`)

**Verteidigung 1 — Notification-Turns komplett überspringen:**
Neue Guard-Funktion am Anfang der Verarbeitung: Enthält der Prompt einen der
Marker `<task-notification>`, `[SYSTEM NOTIFICATION`, `<system-reminder>`,
`<bash-input>`, `<local-command-caveat>` → SÄMTLICHE Keyword-Erkennung für
diesen Turn überspringen (Exit 0 ohne Aktion). Diese Marker kommen
ausschließlich in harness-injizierten Turns vor, nie in echten User-Eingaben.

**Verteidigung 2 — Stichwort muss vorne stehen:**
`_matches()` bekommt eine Zusatzbedingung für die freigabe-relevanten
Phrasen-Sets (approval, GREEN, override): Die Phrase muss innerhalb der
**ersten Zeile** des Prompts UND innerhalb der ersten 120 Zeichen vorkommen.
Echte User-Freigaben führen mit dem Stichwort ("approved", "go", "approved
(oder kann ich...)"), während zitierte Erwähnungen in Agenten-/Meta-Texten
typischerweise tief im Text stehen. Stop-Lock-Phrasen ("stop"/"halt") bleiben
BEWUSST beim bisherigen Verhalten (großzügig matchen — ein Not-Aus darf eher
zu oft als zu selten greifen).

Zusätzlich: `CHANGELOG.md`-Eintrag, Version 3.8.1 → 3.8.2 (PATCH).

## Was darf sich nicht ändern
- Echte User-Freigaben funktionieren wie bisher: "approved", "go", "freigabe",
  "approved (mit Nachsatz...)", "ja, weiter" — sofern das Stichwort in der
  ersten Zeile/den ersten 120 Zeichen steht.
- Stop-Lock: unverändert großzügig (Sicherheit vor Komfort).
- Kein Verhalten der anderen Hooks berührt.

## Manuelle Test-Schritte
1. Echten Freigabe-Text tippen → greift wie bisher.
2. Einen Text mit eingebettetem "Bestätige mit 'approved'" tief im Text als
   Prompt simulieren → keine Freigabe.
3. Simulierte Task-Notification mit Freigabe-Phrase → keine Freigabe.

## Inline-Tests (werden während Implementierung geschrieben)
- [ ] Marker-Guard: Prompt mit `<task-notification>`-Tag + "approved" im Text
      → spec_approved bleibt false.
- [ ] Positionsregel: "approved" als erste Zeile → Freigabe gesetzt;
      "...Bestätige mit 'approved' oder 'freigabe'..." (Position > 120) → nicht.
- [ ] Realfall aus dieser Session: "approved (oder kann ich nicht einfach...)"
      → Freigabe gesetzt (Rückwärtskompatibilität echter User-Muster).
- [ ] Stop-Phrase mitten im Text → Stop-Lock greift weiterhin (unverändert).
