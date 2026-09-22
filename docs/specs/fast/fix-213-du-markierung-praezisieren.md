# Mini-Spec: ℹ️-Formulierung präzisieren — nie mit „PO ist dran" verwechselbar (#213)

## Problem

Live-Beispiel (agent-os-openspec 3.27.2, nach `/50-implement`):

```
ℹ️ Nichts zu tun: Claude wartet auf deinen nächsten Befehl — danach: /60-validate #2268
```

Irreführend: der PO muss selbst den nächsten Befehl tippen — klassischer `❗ Du`-Fall.

Die ursprüngliche #174-Spec meinte mit `ℹ️` explizit „Claude arbeitet oder wartet auf einen
**Hintergrund-Agenten**". Die ausgelieferte Formulierung in `core/hooks/workflow.py::status_note`
und `scripts/sync_skills.py::marker_block` sagt nur vage „Claude arbeitet / wartet auf …" —
das lässt „wartet auf den nächsten Befehl des PO" offen, obwohl das immer `❗ Du` sein muss.

Zweites, schlimmeres Live-Beispiel: eine Nachricht enthielt BEIDE Marker gleichzeitig —
eine `ℹ️`-Zeile mitten im Fließtext UND am Ende eine `❗ Du`-Zeile, die selbst sagt „bis dahin
ist nichts von dir nötig" (in sich widersprüchlich). Ursache vermutlich: `ℹ️`/`❗` wurden auch
als beschreibendes Vokabular im Fließtext verwendet, nicht nur als die eine Pflicht-Fußzeile.

## Was ändert sich

- `core/hooks/workflow.py::status_note`: Erklärsatz präzisiert — `❗ Du` gilt ausdrücklich
  auch, wenn Claude selbst nichts mehr zu tun hat und nur auf den nächsten Befehl des PO
  wartet. `ℹ️ Nichts zu tun` gilt ausschließlich, wenn Claude auf etwas **anderes** als den
  PO wartet (Beispiel: Hintergrund-Agent).
- `scripts/sync_skills.py::marker_block`: dieselbe Präzisierung, wortgleiche Bedeutung
  (die Docstring verlangt bereits Gleichlauf beider Bausteine, sonst driften sie auseinander).
- Beide Bausteine zusätzlich verschärft: die `❗`/`ℹ️`-Kennzeichnung steht **ausschließlich**
  in der terminalen Fußzeile — nie als beschreibendes Vokabular im Fließtext davor. Grund:
  zweites Live-Beispiel mit `ℹ️`-Zeile im Fließtext UND widersprüchlicher `❗`-Fußzeile in
  derselben Nachricht.
- `skills/*/SKILL.md` neu generiert (`sync_skills.py`).
- Erforderliche Literale bleiben erhalten (von bestehenden Tests geprüft): `` `❗ Du: …` ``,
  `ℹ️ Nichts zu tun:`, `danach: /<befehl> #<N>`, `‼️`, Reihenfolge ❗Du → ℹ️Status → ⚙.

## Was darf sich nicht ändern

- Format/Reihenfolge der drei Fußzeilen (❗Du/ℹ️-Zeile, ℹ️ Status, ⚙-Marker) bleibt unverändert.
- `30-write-spec` bleibt `MARKER_EXEMPT`.
- Keine neue Logik, reine Text-/Instruktionspräzisierung — kein Verhalten, das ein Hook
  technisch erzwingen könnte (das bleibt bewusst zurückgestellt, siehe #177).

## Acceptance Criteria

- **AC-1:** Given `status_note()`-Text, When gelesen, Then sagt er ausdrücklich, dass „Claude
  wartet auf den nächsten Befehl des PO" IMMER `❗ Du` ist, nicht `ℹ️`.
- **AC-2:** Given `marker_block()`-Text, When gelesen, Then sagt er dieselbe Einschränkung für
  den `ℹ️`-Fall (nur bei Warten auf etwas anderes als den PO, z. B. Hintergrund-Agent).
- **AC-3:** Given bestehende Tests zu Reihenfolge/Pflicht-Wörtern/Literalen, When sie nach der
  Änderung laufen, Then bleiben sie grün (keine Regression an der Struktur).
- **AC-4:** Given `sync_skills.py --check`, When es nach der Änderung läuft, Then meldet es
  „Skills synchron".
- **AC-5:** Given beide Textbausteine, When gelesen, Then sagen sie ausdrücklich, dass die
  `❗`/`ℹ️`-Kennzeichnung genau einmal und ausschließlich als terminale Fußzeile steht — nie
  als Vokabular im Fließtext davor.

## Manuelle Test-Schritte

1. `python3 -c "..."` `workflow.status_note({...phase7_validate...})` ausgeben und lesen:
   enthält die Klarstellung.
2. `skills/60-validate/SKILL.md` nach dem Sync öffnen: Marker-Abschnitt enthält dieselbe
   Klarstellung.

## Test Plan

- Volle Suite `python3 -m pytest tests/` (insbesondere `test_status_note_325.py`,
  `test_skills_sync.py`).
- `python3 scripts/sync_skills.py --check`.
