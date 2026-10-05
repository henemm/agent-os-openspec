---
description: "Intake: Aufgaben-Klassifikation"
disable-model-invocation: false
---

# Intake: Aufgaben-Klassifikation

**Immer der erste Schritt** — vor jedem Feature-Workflow. Auch Bugs starten hier.
Bestimmt den Track und verhindert, dass ein 10-Minuten-Fix 8 Phasen durchläuft.

## Setup

```bash
# Hook-Pfad: (1) CLAUDE_PLUGIN_ROOT (2) installed_plugins.json (3) .claude/hooks
_H="${CLAUDE_PLUGIN_ROOT:+${CLAUDE_PLUGIN_ROOT}/core/hooks}"
if [ -z "$_H" ]; then _p="$(python3 -c 'import json,os;d=json.load(open(os.path.expanduser("~/.claude/plugins/installed_plugins.json")));print(next((e["installPath"] for k,v in d.get("plugins",{}).items() if k.startswith("agent-os-openspec@") for e in [next((x for x in v if x.get("scope")=="user"),v[0])]),""))' 2>/dev/null)"; [ -n "$_p" ] && [ -d "$_p/core/hooks" ] && _H="$_p/core/hooks"; fi
_H="${_H:-.claude/hooks}"
WF="python3 ${_H}/workflow.py"
```

## Scoring

Bewerte die Aufgabe anhand von 3 Kriterien:

| Kriterium | Low (0) | Medium (1) | High (2) |
|-----------|---------|------------|---------|
| **Scope** | 1–3 Dateien, ≤30 LoC | 4–8 Dateien, ≤100 LoC | Neue Architektur, neue Dateien |
| **Blast Radius** | Internes Utility, isoliert | Service-Schnittstelle | Infra, Auth, kritischer Pfad, Breaking Change |
| **Unsicherheit** | Bekanntes Pattern, vertrauter Code | Teilweise bekannt | Neue Technologie, unbekannter Bereich |

**Summe 0**: Fast Track (`feature-fast`) — Phasen 3→4→6→8
**Summe ≥ 1**: Voller Prozess (`feature`) — alle Phasen 1→8, Adversary: mindestens 2 Dialog-Runden bei hohem Risiko, eine Runde bei niedrigem Risiko
(`MIN_ROUNDS` in `adversary_dialog.py`). Das Risiko folgt mechanisch aus der Dateiliste der Änderung
(Hook-/Gate-Code, Guards, Konfiguration = hoch; nur Anweisungstext, Doku, Tests = niedrig; im Zweifel hoch) —
`python3 ${_H}/adversary_dialog.py risk` zeigt Stufe, Grund und geforderte Runden (#342)

Der Workflow-State kennt genau diese zwei Stufen (`feature-fast`, `feature`). Die **Tiefe** im vollen
Prozess richtet sich nach der Summe — das ist eine Anweisung, kein Zustand im State (#254):

- Summe 1–3: Kontext und Analyse kurz in einem Durchgang (1x Explore)
- Summe 4–6: Kontext und Analyse getrennt, Analyse mit 3x Haiku parallel

## Deine Aufgaben

### 1. Aufgabe verstehen + schnell recherchieren

Lies den Aufgaben-Kontext aus dem Gespräch (ARGUMENTS oder letzte User-Nachricht).
Bei Unklarheit über Scope: schnelle Suche:

```bash
# Betroffene Dateien schätzen
grep -rn "keyword" --include="*.py" -l | head -10
```

### 1b. Issue-Nummer(n) ins Session-Register eintragen

Sobald die Issue-Nummer(n) aus dem Aufgaben-Kontext bekannt sind — noch vor der
Track-Bewertung, denn im Fast Track entsteht nie ein Workflow:

```bash
python3 ${_H}/session_singleton_guard.py claim --issue <N>[,<M>...]
```

Damit weiß jede andere Session, wer gerade an Issue #N arbeitet. Ohne Issue-Nummer
(z.B. reiner Wartungs-Task) entfällt der Schritt.

### 1c. Bugs: Vorprüfung vor dem Scoring

Bei einem Fehlerbericht, noch bevor bewertet wird:

1. **Duplikatsuche:** `gh issue list --label "bug" --state open` und
   `gh issue list --search "<Stichwort>" --state open`. Duplikat → bestehendes Issue verwenden.
2. **Fehler nachstellen** und die Ursache mit `file:line` belegen. Die ausführliche Vorgehensweise
   steht in `/20-analyse` Step 2b.
3. **Scoring speisen:** Ursache bekannt und ≤3 Dateien → Unsicherheit **Low**.
   Ursache unklar → Unsicherheit mindestens Medium.
4. **STOP** und nachfragen, wenn: Ursache unklar, nicht reproduzierbar, mehrere mögliche Ursachen,
   Fix > 5 Dateien.

Es gibt keinen eigenen Bug-Typ: Der Nachweis ist ein Test, der den Fehler vorher rot zeigt.
Danach gilt dieselbe Wahl `feature-fast` / `feature` wie für jede andere Aufgabe.

### 2. Score präsentieren und Track vorschlagen

Gib dem User exakt dieses Format aus:

```
## Intake-Bewertung: [Aufgaben-Titel]

| Kriterium     | Score  | Begründung            |
|---------------|--------|-----------------------|
| Scope         | Low    | 2 Dateien, ~20 LoC    |
| Blast Radius  | Low    | Internes Utility      |
| Unsicherheit  | Low    | Bekanntes Pattern     |

Summe: 0 → **Fast Track** · Modell: **Sonnet**

Was das bedeutet:
- Kein Context-Doc, keine Analyse-Phase
- Mini-Spec (Bullets statt vollständige Spec) + User-Freigabe
- Inline-Test während Implementierung (kein separates TDD-RED)
- Kein Adversary Agent
```

**Workflow-Name:** Leite ihn selbst aus dem Aufgaben-Titel ab (Issue-Nummer + Stichwort, z.B. `fix-862-col-labels`). Nie beim User erfragen.

### 3. Workflow starten (nach User-Bestätigung des Tracks)

**Fast Track:**
```bash
$WF start [name] --type feature-fast
export OPENSPEC_ACTIVE_WORKFLOW=[name]
```
→ Weiter mit `/30-write-spec` (Mini-Spec-Format, siehe unten)

**Voller Prozess:**
```bash
$WF start [name] --type feature
export OPENSPEC_ACTIVE_WORKFLOW=[name]
```
→ Summe 1–3: weiter mit `/10-context` (Context + Analyse in einem Durchgang kombinieren)
→ Summe 4–6: weiter mit `/10-context`, dann `/20-analyse` (getrennt, 3x parallele Agenten), dann `/30-write-spec`

## Modell-Empfehlung

| Stufe | Hauptkontext | Begründung |
|-------|-------------|-----------|
| Fast Track | **Sonnet** | Bekannte Aufgabe, kein komplexes Reasoning nötig |
| Voller Prozess, Summe 1–3 | **Sonnet** | Kreativ/analytisch aber gut definiert — Kosten/Qualitäts-Optimum |
| Voller Prozess, Summe 4–6 | **Opus** | Hohe Komplexität, hoher Einsatz, potenziell Neuland — Mehrpreis lohnt im Haupt-Reasoning-Loop |

Die Modell-Wahl gilt für den **Hauptkontext** (die laufende Claude-Session).
Sub-Agenten haben eigene Modelle (Haiku für mechanische Tasks, Sonnet für Analyse/Specs) — das bleibt unabhängig vom Track.

Modell wechseln: `/model` in der Claude-Code-Session oder beim Start `claude --model claude-opus-4-8`.

## Unterschiede nach Stufe und Tiefe

| Phase | Fast Track | Voller Prozess, Summe 1–3 | Voller Prozess, Summe 4–6 |
|-------|-----------|---------|-------------|
| Context-Doc | ❌ entfällt | ✅ kurz, inline | ✅ vollständig |
| Analyse | ❌ entfällt | ✅ 1x Explore | ✅ 3x Haiku parallel |
| Spec | ✅ Mini-Spec | ✅ Vollständig | ✅ Vollständig |
| User-Freigabe | ✅ immer | ✅ immer | ✅ immer |
| TDD RED | ❌ inline | ✅ Separate Phase | ✅ Separate Phase |
| Adversary | ❌ entfällt | ✅ mindestens 2 Runden bei hohem Risiko, 1 bei niedrigem | ✅ mindestens 2 Runden bei hohem Risiko, 1 bei niedrigem |
| Validierung | ✅ immer | ✅ immer | ✅ immer |

## Mini-Spec (Fast Track)

Beim Fast Track schreibt der Hauptkontext direkt (kein Sonnet-Agent) eine Mini-Spec.
Datei: `docs/specs/fast/[name].md`

```markdown
# Mini-Spec: [Name]

## Was ändert sich
- [Änderung 1]
- [Änderung 2]

## Was darf sich nicht ändern
- [Invariante]

## Manuelle Test-Schritte
1. [Schritt]
2. [Schritt]

## Inline-Test (wird während Implementierung geschrieben)
- [ ] Test für [Hauptverhalten]
```

Nach User-Freigabe ("approved") direkt zu `/50-implement`.

## Was beim Fast Track IMMER aktiv bleibt

- **Spec + User-Freigabe** — keine Implementierung ohne "approved"
- **Rebase-Gate** — Branch muss auf `origin/main` stehen
- **Secrets Guard** — nie Credentials im Code
- **Stop-Lock** — "stopp" pausiert sofort

## Versions-Marker (Pflicht)

Beende deine letzte Nachricht in diesem Befehl mit diesen Zeilen, in dieser Reihenfolge:

❗ Du: `/<befehl> #<N>` — <ein Halbsatz, warum>
ℹ️ Status: Workflow `<name>` · Phase `<x>` von 8
⚙ /00-intake · agent-os-openspec 3.36.1

Die erste Zeile sagt, wer am Zug ist — GENAU EINMAL, nur hier in der Fußzeile, nie zusätzlich als Vokabular mitten im Fließtext davor — und steht in genau einer von zwei Formen: `❗ Du: …`, wenn der PO den Schritt tippen oder eine Entscheidung treffen muss (bei Dringendem `‼️` statt `❗`). Das gilt AUCH, wenn du selbst gerade nichts mehr zu tun hast und nur auf den nächsten Befehl des PO wartest — das ist niemals „nichts zu tun“. Oder `ℹ️ Nichts zu tun: <du arbeitest gerade selbst / wartest auf ein Ergebnis, z. B. einen Hintergrund-Agenten> — danach: /<befehl> #<N>`, ausschließlich wenn du auf etwas ANDERES als den PO wartest. So muss der PO nie raten, ob etwas von ihm erwartet wird.

Schritt und Phase übernimmst du aus dem Hinweis `[agent-os-openspec] AKTIVER WORKFLOW …`, den der Hook bei jeder Nachricht mitliefert (dort heißt der Schritt „Nächster Pflicht-Schritt“) — Phase und Schritt wörtlich von dort. Fehlt der Hinweis (kein Workflow oder `phase8_complete`), entfallen die erste Zeile und die Statuszeile.

Hast DU SELBST in dieser Nachricht per `workflow.py phase <x>` (oder `complete`) die Phase gewechselt, ist der Hinweis noch der ALTE Stand von Turn-Beginn — nutze trotzdem den NEUEN, von dir selbst herbeigeführten Stand für Schritt und Phase. Die Marker-Zeilen entfallen NIE aus diesem Grund; die ⚙-Zeile bleibt immer die letzte Zeile.

Solange die Phase kleiner als 8 ist, ist dieser Schritt **Pflicht**: nie „bei Bedarf“, „optional“ oder „wenn du magst“ — und nie „fertig“, „abgeschlossen“ oder „erledigt“ für den Workflow als Ganzes (das gilt erst ab `phase8_complete`; eine einzelne Phase darfst du abgeschlossen nennen). In frei formulierten Arbeitsstandsmeldungen steht der Pflicht-Schritt vor jeder `/clear`- oder Kosten-Empfehlung, und die Nachricht endet nie mit einer solchen Empfehlung. (Die wörtlich vorgegebenen Übergabe-Blöcke oben bleiben unverändert — dort gehören `/clear` und Folgebefehl zusammen.)

In diesen Zeilen ersetzt du `<name>`, `<x>` und `/<befehl> #<N>` durch die Werte aus dem Hook-Hinweis — Platzhalter bleiben nie stehen. Die ⚙-Zeile übernimmst du wörtlich und unverändert. Alle Zeilen stehen je genau einmal in der Nachricht, **nach** dem Übergabe-Block — auch nach dessen abschließendem `---` —, und die ⚙-Zeile ist immer die allerletzte Zeile der Nachricht, auch wenn die übrigen Zeilen entfallen.
