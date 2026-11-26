# Hintergrund zur Fußzeile (Versions-Marker und Hook-Hinweis)

Begründungen zu `scripts/sync_skills.py::marker_block` (Versions-Marker-Block am Ende jedes Befehls) und zu `core/hooks/workflow.py` (`END_STATE_RULE`, `_status_note_base`, Hook-Hinweis je Nutzer-Nachricht). Beide Texte enthalten seit #679 nur noch die Regeln; der frühere Wortlaut mit allen Begründungen steht hier unverändert.

## Versions-Marker-Block (bis 4.26.2)

Beende deine letzte Nachricht in diesem Befehl mit diesen Zeilen, in dieser Reihenfolge:

```
❗ Du: `/<befehl> #<N>` — <ein Halbsatz, warum>
ℹ️ Status: Workflow `<name>` · Phase `<x>` von 8
⚙ /<name> · agent-os-openspec <version>
```

Die erste Zeile sagt, wer am Zug ist — GENAU EINMAL, nur hier in der Fußzeile, nie zusätzlich als Vokabular mitten im Fließtext davor — und steht in genau einer von drei Formen (es gibt keine vierte):

- `✅ Erledigt: <was>. Du kannst /clear ausführen und das nächste Issue starten.` — nur wenn der Workflow wirklich abgeschlossen ist.
- `⏳ Läuft noch: <worauf gewartet wird>. Du musst nichts tun, ich melde mich.` — du wartest auf CI, einen Hintergrund-Agenten oder einen Server.
- `❗ Du: …` (`❗ Du: <Schritt> — <warum>`), wenn der PO den Schritt tippen oder eine Entscheidung treffen muss (bei Dringendem `‼️` statt `❗`). Das gilt AUCH, wenn du selbst gerade nichts mehr zu tun hast und nur auf den nächsten Befehl des PO wartest — das ist immer ❗, nie ⏳.

Beendest du einen Turn, während du auf CI, Agent oder Server wartest, setze vorher `workflow.py waiting "<worauf>"` und gib die ⏳-Zeile aus; ist das Ergebnis da, `workflow.py waiting --clear`. Die passende Zeile liefert `workflow.py endstate [#<N>]` als `FOOTER=…` — gib sie wörtlich aus. So muss der PO nie raten, ob etwas von ihm erwartet wird.

Schritt und Phase geben den Stand AM ENDE dieser Nachricht wieder. Quelle ist der Hinweis `[agent-os-openspec] AKTIVER WORKFLOW …`, den der Hook bei jeder Nachricht mitliefert (dort heißt der Schritt „Nächster Pflicht-Schritt“) — aber nur, solange du die Phase in dieser Nachricht nicht selbst gewechselt hast. Hast du per `workflow.py phase <x>` (oder `complete`) gewechselt, beschreibt der Hinweis den Stand von Turn-Beginn; maßgeblich ist dann der neue Stand, den `workflow.py status` zeigt. Fehlt der Hinweis (kein Workflow oder `phase8_complete`), entfällt die Statuszeile; die erste Zeile kommt dann aus `workflow.py endstate #<N>` und entfällt nur ohne Workflow. Die Marker-Zeilen entfallen NIE wegen eines Phasenwechsels; die ⚙-Zeile bleibt immer die letzte Zeile.

Solange die Phase kleiner als 8 ist, ist dieser Schritt **Pflicht**: nie „bei Bedarf“, „optional“ oder „wenn du magst“ — und nie „fertig“, „abgeschlossen“ oder „erledigt“ für den Workflow als Ganzes (das gilt erst ab `phase8_complete`; eine einzelne Phase darfst du abgeschlossen nennen). In frei formulierten Arbeitsstandsmeldungen steht der Pflicht-Schritt vor jeder `/clear`- oder Kosten-Empfehlung, und die Nachricht endet nie mit einer solchen Empfehlung. (Die wörtlich vorgegebenen Übergabe-Blöcke oben bleiben unverändert — dort gehören `/clear` und Folgebefehl zusammen.)

In diesen Zeilen ersetzt du `<name>`, `<x>` und `/<befehl> #<N>` durch die Werte aus dem Hook-Hinweis — Platzhalter bleiben nie stehen. Die ⚙-Zeile übernimmst du wörtlich und unverändert. Alle Zeilen stehen je genau einmal in der Nachricht, **nach** dem Übergabe-Block — auch nach dessen abschließendem `---` —, und die ⚙-Zeile ist immer die allerletzte Zeile der Nachricht, auch wenn die übrigen Zeilen entfallen.

## Hook-Hinweis je Nachricht (bis 4.26.2)

Kopfzeile (unverändert): `[agent-os-openspec] AKTIVER WORKFLOW <name> · Phase N von 8 (<phase>) · Nächster Pflicht-Schritt: <schritt>`

### Normalfall

Nenne diesen Schritt in jeder Arbeitsstandsmeldung als Pflicht — nie als „bei Bedarf“ oder „optional“; Empfehlungen zu /clear oder Token-Kosten stehen nie darüber.

Kennzeichne für den PO, wer am Zug ist, mit GENAU EINER Zeile ganz am Ende der Nachricht — nie zusätzlich mitten im Fließtext — in genau einer von drei Formen: „✅ Erledigt: <was>. Du kannst /clear ausführen und das nächste Issue starten.“ (nur wenn der Workflow wirklich abgeschlossen ist), „⏳ Läuft noch: <worauf gewartet wird>. Du musst nichts tun, ich melde mich.“ (du wartest auf CI, einen Hintergrund-Agenten oder einen Server) oder „❗ Du: <Schritt> — <warum>“, wenn der PO tippen oder entscheiden muss. Wartest du nur auf den nächsten Befehl des PO, ist das immer ❗, nie ⏳. Beendest du einen Turn, während du auf CI, Agent oder Server wartest, setze vorher `workflow.py waiting "<worauf>"` und gib die ⏳-Zeile aus; ist das Ergebnis da, `workflow.py waiting --clear`. Die passende Zeile liefert `workflow.py endstate` als FOOTER.

Hast DU SELBST in dieser Nachricht per `workflow.py phase <x>` (oder `complete`) die Phase gewechselt, ist dieser Hinweis hier noch der ALTE Stand von Turn-Beginn — nutze für Schritt und Phase in der Fußzeile trotzdem den NEUEN, von dir selbst herbeigeführten Stand. Die Marker-Zeilen entfallen NIE aus diesem Grund.

✅/⏳/❗/ℹ️/⚙ erscheinen AUSSCHLIESSLICH in den hier und in den Command-Vorlagen fest vorgeschriebenen Zeilen. Erfinde keine weiteren Zeilen mit diesen oder anderen Emojis (z. B. eine eigene „ℹ️ Status: ...“-Zusammenfassung) — Statusrekaps im Fließtext bleiben Emoji-frei.

„fertig“/„abgeschlossen“/„erledigt“ gilt für den Workflow erst ab phase8_complete.

### Auto-Freigabe (#470)

Diesen Schritt führst du selbst aus (Auto-Modus, Ampel im PO-Briefing grün) — der PO muss dafür nichts tippen, es gibt dafür KEINE Du-Zeile; die Fußzeile lautet „⏳ Läuft noch: Auto-Freigabe der Spec läuft. Du musst nichts tun, ich melde mich.“ Meldet `workflow.py auto-approve` AUTO_APPROVE=human, entscheidet der PO wie bisher per Freigabe-Stichwort.

„fertig“/„abgeschlossen“/„erledigt“ gilt für den Workflow erst ab phase8_complete.
