# Context: fix-234-footer-command

## Request Summary

Die ❗Du-Fußzeile am Ende einer Claude-Antwort nannte einen bereits erledigten Befehl
(`/40-tdd-red`), obwohl der Workflow-State zum Zeitpunkt der Antwort schon den nächsten Schritt
(`/50-implement`) verlangte. Die Fußzeile ist die einzige Zeile, die der PO als „das tippe ich
jetzt" liest — ein falscher Wert dort schickt ihn in einen Leerlauf. Issue #234.

## Related Files

| File | Relevance |
|------|-----------|
| `core/hooks/workflow.py:164-184` | `next_step()` — berechnet den korrekten Pflicht-Schritt **deterministisch** aus dem State. Die Wahrheit existiert also schon. |
| `core/hooks/workflow.py:193-245` | `status_note()` — Text, der bei UserPromptSubmit in den Kontext gespielt wird; enthält seit #221 die Regel für selbst herbeigeführte Phasenwechsel. Textlich korrekt, wurde nicht befolgt. |
| `core/hooks/workflow.py:1137-1159` | `cmd_phase()` — gibt **nur** `Set phase to: <x>` aus. Kennt `next_step()` nicht, sagt also nichts über die Folge für die Fußzeile. |
| `core/hooks/workflow.py:1283-1298` | `cmd_mark_red()` / `cmd_mark_ui_red()` — setzen `red_test_done`, wodurch `next_step()` **ohne Phasenwechsel** von `/40-tdd-red` auf `/50-implement` umspringt. Ausgabe erwähnt das nicht. |
| `core/hooks/phase_listener.py:301-322` | `_emit_status_note()` — die einzige Injektionsstelle. Läuft ausschließlich bei UserPromptSubmit, also **nur zu Turn-Beginn**. |
| `core/hooks/post_bash.py` | Bestehender PostToolUse-Bash-Hook — möglicher Träger für eine Nachmeldung innerhalb des Turns. |
| `scripts/sync_skills.py::marker_block` | Zweite Quelle derselben Fußzeilen-Regel (für `skills/*/SKILL.md`). Jede Textänderung muss hier **und** in `workflow.py` erfolgen, sonst Drift. |
| `hooks/hooks.json` | Registrierte Events: SessionStart, PreToolUse, PostToolUse, UserPromptSubmit, SessionEnd. **Kein `Stop`-Hook** — der wäre neu für dieses Framework. |

## Existing Patterns

- **Deterministische Wahrheit, modellgeschriebene Ausgabe:** `next_step()` liefert den Wert exakt;
  die Fußzeile entsteht trotzdem als freier Modell-Text, den nichts nachprüft.
- **Injektion nur zu Turn-Beginn:** `status_note()` wird einmal pro User-Eingabe in den Kontext
  gegeben. Alles, was das Modell danach im selben Turn am State ändert, veraltet diesen Hinweis
  sofort — der Hinweis selbst weist auf diesen Umstand nur noch per Textregel hin.
- **Stille Zustandsänderung:** Alle `workflow.py`-Schreibkommandos melden die Mutation
  (`Set phase to: …`, `RED unit test marked done: …`), aber keines meldet die **Konsequenz**
  (welcher Pflicht-Schritt ab jetzt gilt).

## Dependencies

- **Upstream:** `next_step()` hängt an `current_phase`, `spec_file`, `red_test_done`,
  `ui_test_red_done` im Workflow-JSON.
- **Downstream:** `status_note()` → `phase_listener.py` → Kontext jeder Claude-Antwort;
  zusätzlich `scripts/sync_skills.py` → alle 15 `skills/*/SKILL.md`. Die Fußzeile erscheint nach
  **jedem** Slash-Command in **jedem** Projekt, das dieses Framework nutzt.

## Vorgeschichte: vier Textverschärfungen in Folge

| Issue | Commit | Was geändert wurde | Ergebnis |
|-------|--------|--------------------|----------|
| #174 | `7f58cde` (3.27.2) | Fußzeile eingeführt (❗ Du / ℹ️ Nichts zu tun) | Folgefehler |
| #209 | `e3b426e` (3.28.1) | PO-Briefing-Freigabe zeigt ❗Du-Markierung | Folgefehler |
| #213 | `269b0f8` (3.28.2) | ℹ️-Formulierung präzisiert | Folgefehler |
| #221 | `f664d8a` (3.30.1) | Regel für selbst herbeigeführten Phasenwechsel ergänzt | Folgefehler → #234 |

Jeder dieser Fixes hat **ausschließlich Prompt-Text ergänzt**. Der Fehler kam jedes Mal in einer
neuen Variante zurück. Commit `f664d8a` nennt sich selbst „Dritte Präzisierung in Folge nach #209
und #213" — die vierte war #221, dieser Issue wäre die fünfte. Das ist das zentrale Signal für die
Analyse-Phase: Die Ursache liegt nicht in fehlendem Regeltext.

## Erkenntnis aus der Recherche (Claude-Code-Hook-Doku)

- Ein `Stop`-Hook erhält laut Doku `last_assistant_message`, läuft aber **nach** der Anzeige beim
  User und ist in der „Can Block?"-Tabelle mit **No** geführt. Ob er die Fortsetzung des Turns
  erzwingen kann (das übliche Stop-Hook-Muster), war in der Recherche widersprüchlich —
  **offene Frage für `/20-analyse`**, muss belegt und nicht vermutet werden.
- `MessageDisplay` ist laut Doku „display-only", kann Nachrichten nicht ändern.
- Blockierbar ist nur, was **vor** der Generierung liegt: `UserPromptSubmit`, `PreToolUse`.
- Quelle: https://code.claude.com/docs/en/hooks#hook-lifecycle

## Kandidat, der im Issue nicht steht

Der Issue listet drei Alternativen (Text schärfen / Stop-Hook-Prüfung / nichts tun). Die Code-Lage
legt eine vierte nahe, die deutlich kleiner ist als der Stop-Hook und deterministisch bleibt:

**Die zustandsändernden CLI-Kommandos melden die Konsequenz mit.** `cmd_phase()` kennt den neuen
State und könnte `next_step()` direkt aufrufen und ausgeben, z. B.
`Set phase to: phase6_implement` + `Fußzeile muss jetzt nennen: /50-implement #234`.
Dasselbe für `mark-red`, `mark-ui-red`, `complete`, `switch`.

Warum das genau am Fehlerort greift: Das Modell liest dieses Tool-Ergebnis **im selben Turn,
Sekunden bevor es die Fußzeile schreibt** — nicht Minuten vorher zu Turn-Beginn. Es braucht keinen
neuen Hook-Typ, keine Antwort auf die offene Stop-Hook-Frage, und die Wahrheit kommt aus derselben
Funktion, die schon heute die Quelle ist. Es bleibt aber Modell-Ausgabe, die niemand nachprüft —
also eine Verbesserung der Zulieferung, keine echte Durchsetzung. Bewertung gehört in `/20-analyse`.

## Risks & Considerations

- **Doppelte Textquelle:** Jede Änderung am Fußzeilen-Text muss in `core/hooks/workflow.py`
  **und** `scripts/sync_skills.py` erfolgen; `skills/*/SKILL.md` ist generiert, Drift blockt das
  Release.
- **Blast Radius:** Betrifft jede Antwort in jedem Konsumenten-Projekt. Ein zu gesprächiger
  Zusatz in `cmd_phase()` landet in jedem Tool-Ergebnis.
- **Infrastruktur-Gate:** `core/hooks/` verlangt einen Override-Token, auch im Fast Track.
- **Sunk Cost ist kein Argument:** Dass vier Fixes bereits auf den Textweg gesetzt haben, spricht
  nicht dafür, ihn ein fünftes Mal zu gehen.
- **Nulllinie mitmessen:** Vor jeder Modell-/Prompt-Lösung muss belegt werden, warum der
  deterministische Weg nicht reicht (CLAUDE.md „Regeln vor Modell").

---

## Analysis

### Type

Bug — Framework-Infrastruktur (`core/hooks/`, `scripts/`, `core/commands/`).

### Root Cause — belegt, nicht vermutet

Der Issue vermutet einen „Befolgungsfehler des Modells in diesem einzelnen Turn". Das ist
widerlegt. Im selben Turn zeigen **drei** Textquellen auf den ALTEN Stand und nur **eine**
Ausnahmeklausel auf den neuen:

| # | Quelle | Aussage | Wirkung |
|---|--------|---------|---------|
| 1 | `core/hooks/workflow.py:218-221` | Hinweis zu Turn-Beginn: „Nächster Pflicht-Schritt: /40-tdd-red #12" | per Konstruktion veraltet, sobald der Befehl die Phase weiterschaltet |
| 2 | `scripts/sync_skills.py:103-107` (→ alle `skills/*/SKILL.md`) | „Schritt und Phase übernimmst du aus dem Hinweis … — Phase und Schritt **wörtlich von dort**." | konkreteste, handlungsnächste Anweisung: *kopiere den alten Wert* |
| 3 | `core/commands/40-tdd-red.md:158` | Pflicht-Ausgabeblock enthält hartkodiert ``Phase: `phase5_tdd_red` ✓`` | widerspricht Zeile 134 desselben Befehls, die unmittelbar davor `phase phase6_implement` setzt |
| 4 | `scripts/sync_skills.py:109-113` | Ausnahme: „nutze trotzdem den NEUEN … Stand" | einzige Quelle für den richtigen Wert |

Der beobachtete Turn ist der Mehrheit gefolgt. `core/commands/40-tdd-red.md` ist der **einzige**
Befehl mit hartkodierter Phase im Ausgabetext (`grep "Phase: \`phase" core/commands/*.md`) — und
genau der Befehl, in dem der Fehler auftrat.

Damit ist auch erklärt, warum die vier Vorgänger-Fixes (#174/#209/#213/#221) wirkungslos blieben:
Jeder hat **die Ausnahme verstärkt**, keiner hat **den Widerspruch entfernt**.

### Recherche-Ergebnis (Doku, Quelle: https://code.claude.com/docs/en/hooks)

Die im Kontext offen gelassene Stop-Hook-Frage ist beantwortet:

- **`Stop` kann blocken.** Tabelle „Exit code 2 behavior per event": `Stop` → *Can block?* **Yes**,
  *What happens on exit 2:* „Prevents Claude from stopping, continues the conversation."
- **Die letzte Assistant-Nachricht liegt strukturiert vor.** Doku: „Hooks that need the final
  assistant text of the current turn should use `last_assistant_message` on `Stop` and
  `SubagentStop` instead of reading the transcript." Kein JSONL-Parsing nötig.
- **`MessageDisplay` ist display-only** — kann die Nachricht weder blocken noch ändern.
- **Folgerung:** Eine Assistant-Nachricht **vor** der Anzeige zu korrigieren, ist nicht möglich.
  Deterministisch machbar ist nur: nach der Anzeige mechanisch prüfen und die Fortsetzung des
  Turns erzwingen. Die falsche Fußzeile bleibt kurz sichtbar, die letzte Zeile der Antwort ist
  danach die richtige.
- Beleg, dass `Stop` in dieser Installation real genutzt wird: `~/.claude/settings.json:116` führt
  bereits zwei Stop-Hooks.

### Bewertete Alternativen

| # | Ansatz | Deterministisch | Aufwand | Bewertung |
|---|--------|-----------------|---------|-----------|
| A | Fünfte Textverschärfung (Beispiel ergänzen) | nein | XS | **Abgelehnt** — vier Vorläufer ohne Wirkung; verstärkt erneut nur die Ausnahme |
| B | Widerspruch entfernen (`sync_skills.py` „wörtlich von dort", `40-tdd-red.md:158`) | nein | S | **Nötig, aber allein nicht ausreichend** — senkt die Trefferquote, prüft aber nichts |
| C | `cmd_phase`/`mark-red`/`mark-ui-red`/`complete` geben `next_step()` mit aus | nein (bessere Zulieferung) | S | Verbesserung, bleibt ungeprüfter Modell-Output |
| D | **Stop-Hook `footer_gate.py`: `❗ Du:`-Zeile gegen `next_step()` prüfen, bei Abweichung Exit 2** | **ja** | M | **Empfehlung** |
| E | Nichts tun | – | – | **Abgelehnt** — fünftes Auftreten derselben Fehlerklasse, nicht Einzelfall |

**Nulllinie (CLAUDE.md „Regeln vor Modell"):** `next_step()` liefert die Wahrheit bereits
deterministisch aus dem State. Der Abgleich ist ein Regex plus Stringvergleich — im Prüfpfad
steckt kein Sprachmodell. Es gibt keinen Beleg, dass Prompt-Text hier ausreicht; vier
Gegenbelege existieren.

### Technischer Ansatz (Empfehlung D)

Neuer Hook `core/hooks/footer_gate.py`, registriert auf dem Event `Stop` (neu für dieses
Framework — bisher: SessionStart, PreToolUse, PostToolUse, UserPromptSubmit, SessionEnd).

Ablauf:
1. `last_assistant_message` aus dem Payload lesen.
2. Letzte `❗ Du:` / `‼️ Du:`-Zeile suchen, darin den ersten `/<befehl>` extrahieren.
3. Aktiven Workflow lesen, `workflow.next_step(data)` aufrufen.
4. Nur wenn beide einen Slash-Befehl liefern und diese **verschieden** sind → Exit 2 mit
   stderr: „Fußzeile nennt `/40-tdd-red`, korrekt ist `/50-implement #12`. Gib die Fußzeile
   erneut aus." Sonst Exit 0.

Fail-open-Regeln (jede führt zu Exit 0, nie zu einer Blockade):
- kein aktiver Workflow, `phase8_complete`, unlesbarer State, `framework_disabled()`
- keine `❗ Du:`-Zeile in der Nachricht (freie Gesprächsturns feuern nie)
- `next_step()` liefert keinen Slash-Befehl (z. B. „Freigabe der Spec")
- **Fehlende** Fußzeile wird in v1 NICHT erzwungen — sonst feuert der Hook in jedem
  Zwischen-Turn.

Schleifenschutz (Pflicht, da Exit 2 den Turn fortsetzt): höchstens **eine** Korrektur pro
`prompt_id`; Zähler in `.claude/` (analog `stop_lock.json`), danach Exit 0. Zusätzlich
`stop_hook_active` auswerten, falls im Payload vorhanden — ob das Feld existiert, ist in der
Doku an der abgeschnittenen Stelle nicht belegbar und wird in `/40-tdd-red` empirisch geklärt.

### Affected Files (with changes)

| File | Change Type | Description |
|------|-------------|-------------|
| `core/hooks/footer_gate.py` | CREATE | Stop-Hook: Fußzeile gegen `next_step()`, fail-open, Schleifenschutz (~110 LoC) |
| `hooks/hooks.json` | MODIFY | Event `Stop` registrieren (~8 LoC) |
| `core/hooks/workflow.py` | MODIFY | `expected_footer_command(data)` — dünne Hülle um `next_step()` + `issue_number()`, damit Hook und Statusvermerk dieselbe Quelle nutzen (~12 LoC) |
| `tests/test_footer_gate_234.py` | CREATE | AC-Tests: Treffer, Fail-open-Fälle, Schleifenschutz (~130 LoC) |
| `CHANGELOG.md`, `.claude-plugin/plugin.json` | MODIFY | Versionshistorie (Buchhaltung) |

### Scope Assessment

- Dateien: 4 inhaltlich + 2 Buchhaltung
- Geschätzte LoC: **+260 / -0** — knapp über dem 250er-Limit, fast ausschließlich Tests.
  Wird es enger, fliegt zuerst der Test-Umfang, nicht die Fail-open-Logik; sonst
  LoC-Override anfordern.
- Risiko: **MITTEL-HOCH** — der Hook läuft bei **jedem** Turn-Ende in **jedem**
  Konsumenten-Projekt. Ein falsch-positiver Exit 2 würde jedes Turn-Ende blockieren. Deshalb
  ist Fail-open die tragende Anforderung, nicht die Erkennungsrate. Gegenprobe in `/40-tdd-red`:
  Ein Test muss belegen, dass der Hook bei kaputtem/fehlendem State Exit 0 liefert.

### Dependencies

- **Upstream:** `workflow.next_step()` (hängt an `current_phase`, `spec_file`, `red_test_done`,
  `ui_test_red_done`), `hook_utils.resolve_active_workflow()`, `framework_disabled()`.
- **Downstream:** `hooks/hooks.json` → jedes Projekt im Plugin-Modus. Der Copy-Modus ist
  gesondert zu betrachten (siehe offene Befunde).

### Offene Befunde → eigene Issues (nicht in #234 mitfixen)

1. **#235 — Widerspruch im Fußzeilen-Text** (Alternative B): `scripts/sync_skills.py:103-107`
   („wörtlich von dort") und `core/commands/40-tdd-red.md:158` (hartkodiert `phase5_tdd_red`).
   Kleiner, eigenständiger Fix; senkt die Trefferquote des Gates.
2. **#236 — `setup.py::generate_settings_json()` (Copy-Modus) ist drift-behaftet:** Es registriert
   nur 4 Hooks (`edit_gate`, `bash_gate`, `post_bash`, `phase_listener`) und kennt weder
   `session_singleton_guard`, `worktree_write_guard`, `secrets_guard`, `edit_verify` noch die
   Events `SessionStart`/`SessionEnd`. Der Plugin-Modus generiert dagegen aus `hooks/hooks.json`.
   Ein neuer Stop-Hook würde im Copy-Modus stillschweigend fehlen.
3. **#237 — `secret_egress_guard.py` blockt `/dev/null` und das Sitzungs-Scratchpad**, obwohl die
   eigene Fehlermeldung das Scratchpad als richtiges Ziel nennt. Zweimal während dieser Analyse
   ausgelöst.

### Open Questions

- [ ] Keine — der Ansatz hängt an keiner Entscheidung des PO. Die einzige technische Unklarheit
      (`stop_hook_active` vorhanden?) wird in `/40-tdd-red` empirisch geklärt und ist durch den
      eigenen Schleifenschutz ohnehin abgesichert.
