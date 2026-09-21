---
entity_id: hook_paths_project_dir
type: module
created: 2026-09-21
updated: 2026-09-21
status: draft
version: "1.0"
tags: [hooks, setup, migration]
test_targets: [tests/test_hook_paths_project_dir_165.py]
---

# Hook-Pfade über ${CLAUDE_PROJECT_DIR} statt cwd-relativ

## Approval

- [ ] Approved

## GitHub Issue

- **Issue:** #165

## Purpose

Hook-Kommandos in `.claude/settings.json` dürfen nicht mehr vom aktuellen
Arbeitsverzeichnis abhängen. Sie werden über `${CLAUDE_PROJECT_DIR}` verankert,
damit ein Hook auch dann startet, wenn die Sitzung in einem Unterordner steht.

## Source

- **File:** `setup.py` — `generate_settings_json()`
- **File:** `migrate_to_plugin.py` — `_patch_settings()` + `migrate()`

## Scope

- **Affected Files:** `setup.py`, `migrate_to_plugin.py`,
  `tests/test_hook_paths_project_dir_165.py` (neu), `CHANGELOG.md`
- **Estimated Changes:** ~120 LoC

## Implementation Details

### 1. `setup.py` — Erzeugung (Kopier-Modus)

Statt eines eingebackenen absoluten Pfads:

```
vorher:  python3 /Users/hem/Developer/X/.claude/hooks/edit_gate.py
nachher: python3 "${CLAUDE_PROJECT_DIR}/.claude/hooks/edit_gate.py"
```

`collect_hooks()` prüft weiterhin die Existenz der Datei auf der Platte,
liefert aber den Platzhalter-Pfad zurück. Die Anführungszeichen sind Pflicht:
Projektordner mit Leerzeichen (`Meditationstimer iOS`) brechen sonst.

### 2. `migrate_to_plugin.py` — Reparatur (Bestandsprojekte)

Neuer Schritt neben dem bestehenden Entfernen von Plugin-Hooks:
Jedes verbleibende Hook-Kommando, das eine Datei unter `.claude/hooks/`
referenziert (projekteigene Hooks wie `session_start.py`), wird auf die
Platzhalter-Form umgeschrieben — relativer wie absoluter Pfad, Zusatzargumente
bleiben erhalten. Bereits platzhalter-basierte Kommandos bleiben unverändert
(idempotent).

**Der Pfad wird von rechts bestimmt, nicht von links.** Anker ist die Hook-Datei
selbst (`.claude/hooks/<name>.py`); von dort wird tokenweise nach links gesucht
und beim ersten Token mit Pfad-Sigel (`/`, `~/`, `./`, `../`) gestoppt. Von
links zu suchen wäre der naheliegende Weg und ist falsch: Bei
`/usr/bin/python3 /pfad/.claude/hooks/x.py` wäre das erste Sigel-Token der
Interpreter, und er würde mitverschluckt.

**Die Interpreter-Liste greift nur am Kopf des Aufrufs** — dem ersten Token nach
etwaigen Env-Zuweisungen. Sie auf jedes Token der Suche anzuwenden bricht Pfade
auseinander, in denen ein Ordner zufällig `env`, `node` oder `python3` heißt.
Am Kopf entscheidet sie zwischen zwei Lesarten derselben Form:
`/usr/bin/python3 My Projekt/…` (Aufrufer plus Pfad) und
`/Users/hem/My Projekt/…` (nur Pfad, direkt ausgeführt).

Das Ende ist immer das Ende der Hook-Datei — bis zum nächsten Leerzeichen zu
laufen verschluckt ein angehängtes `;`.

Ein Kommando mit unpaarigen Anführungszeichen wird unverändert gelassen.

Zusätzlich wird `settings.local.json` mitverarbeitet, sofern sie einen
`hooks`-Abschnitt hat. Der `permissions`-Abschnitt wird nicht angefasst.

## Expected Behavior

- **`setup.py` erzeugt keine cwd-relativen Hook-Kommandos:** Jedes erzeugte
  Kommando in `settings.json` enthält `${CLAUDE_PROJECT_DIR}`.
- **`setup.py` erzeugt keine eingebackenen absoluten Projektpfade** mehr in
  Hook-Kommandos.
- **Pfade mit Leerzeichen funktionieren:** Der Platzhalter steht in
  doppelten Anführungszeichen.
- **`migrate_to_plugin.py` repariert projekteigene Hooks:** Ein Eintrag
  `python3 .claude/hooks/session_start.py` wird zu
  `python3 "${CLAUDE_PROJECT_DIR}/.claude/hooks/session_start.py"`.
- **Zusatzargumente überleben:** `qa_gate.py --hook-mode` behält `--hook-mode`.
- **Idempotenz:** Ein zweiter Lauf ändert nichts mehr.
- **`settings.local.json` wird mitgenommen**, falls dort Hooks registriert sind.
- **Plugin-Hooks bleiben entfernt** — das bestehende Verhalten ändert sich nicht.

## Definition of Done

- Kein von `setup.py` erzeugtes Hook-Kommando ist cwd-relativ oder enthält einen
  eingebackenen Projektpfad.
- `migrate_to_plugin.py` hinterlässt in `settings.json` und `settings.local.json`
  kein Hook-Kommando mit cwd-relativem Pfad.
- Der gemeldete Fall (`Meditationstimer`) startet seine Hooks wieder, nachgewiesen
  mit demselben Ablauf, der zuvor den Abbruch zeigte.
- Gesamte Testsuite grün, `scripts/sync_skills.py --check` ohne Drift.

## Acceptance Criteria

- **AC-1:** Given ein Projekt mit Leerzeichen im Ordnernamen / When `setup.py`
  die `settings.json` erzeugt / Then enthält jedes Hook-Kommando
  `"${CLAUDE_PROJECT_DIR}/.claude/hooks/<datei>.py"` in doppelten
  Anführungszeichen und keinen absoluten Projektpfad.
- **AC-2:** Given eine `settings.json` mit dem projekteigenen Eintrag
  `python3 .claude/hooks/session_start.py` / When `migrate_to_plugin.py --apply`
  läuft / Then steht dort
  `python3 "${CLAUDE_PROJECT_DIR}/.claude/hooks/session_start.py"`, während
  Plugin-Hooks weiterhin entfernt werden.
- **AC-3:** Given ein Hook-Kommando mit Env-Präfix und Zusatzargument / When es
  verankert wird / Then bleiben Präfix und Argument unverändert erhalten, und ein
  zweiter Lauf ändert nichts mehr (Idempotenz).
- **AC-4:** Given eine `settings.local.json` mit Hooks und einem
  `permissions`-Abschnitt / When die Migration läuft / Then sind die Hooks
  verankert und `permissions` ist unverändert; unlesbares JSON dort bricht die
  Migration der `settings.json` nicht ab.
- **AC-5:** Given ein Hook-Kommando mit **ungequotetem absolutem Pfad, der ein
  Leerzeichen enthält** (die Form, die die alte `setup.py` tatsächlich erzeugte)
  / When es verankert wird / Then zerfällt das Ergebnis in genau die Tokens
  `python3`, den verankerten Pfad und die ursprünglichen Argumente — kein Rest
  des alten Pfads bleibt als eigenes Token stehen.
- **AC-6:** Given ein Eintrag, dessen sämtliche Hooks als Plugin-Hooks entfernt
  wurden / When die Migration läuft / Then bleibt kein leerer Rumpf mit bloßem
  Matcher zurück; Einträge mit verbleibenden Hooks bleiben unverändert, schon
  vorher leere Einträge werden nicht angefasst, und Trockenlauf wie Anwendung
  melden dieselbe Änderungsliste.
- **AC-7:** Given der Interpreter ist selbst absolut geschrieben
  (`/usr/bin/python3 …`) oder vor dem Hook-Pfad steht ein absolutes Argument
  / When das Kommando verankert wird / Then bleiben beide unverändert erhalten.
- **AC-8:** Given ein Trennzeichen folgt unmittelbar auf den Pfad
  (`… /p/.claude/hooks/x.py; fi`) / When das Kommando verankert wird / Then
  bleibt das Trennzeichen stehen.
- **AC-9:** Given ein Ordner im Pfad heißt wie ein Interpreter
  (`/Users/hem/env foo/.claude/hooks/x.py`) / When das Kommando verankert wird
  / Then gehört er zum Pfad und bleibt nicht als eigenes Token stehen; die
  Interpreter-Erkennung greift nur am Kopf des Aufrufs.
- **AC-10:** Given ein Kommando mit unpaarigen Anführungszeichen / When es
  verankert werden soll / Then bleibt es unverändert — was nicht verlässlich
  gelesen werden kann, wird nicht umgeschrieben.
- **AC-11:** Given Präfix und Kopf sind durch einen Tabulator getrennt
  (`WF=1<TAB>python3 …`) / When das Kommando verankert wird / Then bleiben
  Präfix und Interpreter erhalten — die Tokenisierung ist im ganzen Modul
  dieselbe.
- **AC-12:** Given vor dem Pfad steht ein Shell-Operator oder ein Schalter
  (`echo hi; python3 bar/.claude/hooks/a.py`) / When das Kommando verankert
  wird / Then läuft die Linkssuche nicht darüber hinweg; fremde Kommandoteile
  bleiben stehen.

## Test Plan

| Prüfung | Art | Ort |
|---------|-----|-----|
| AC-1 (Platzhalter, kein absoluter Pfad, gequotet) | automatisiert | `tests/test_hook_paths_project_dir_165.py` |
| AC-2 (projekteigener Hook verankert, Plugin-Hook entfernt) | automatisiert | ebenda |
| AC-3 (Präfix, Argumente, Idempotenz, absoluter Pfad) | automatisiert | ebenda |
| AC-4 (`settings.local.json`, `permissions`, kaputtes JSON) | automatisiert | ebenda |
| AC-5 (ungequoteter absoluter Pfad mit Leerzeichen, `shlex`-Rundlauf) | automatisiert | ebenda |
| AC-6 (leerer Eintrag entfernt, belegter bleibt, Vorschau = Anwendung) | automatisiert | ebenda |
| AC-7 (absoluter Interpreter, absolutes Argument) | automatisiert | ebenda |
| AC-8 (Trennzeichen hinter dem Pfad) | automatisiert | ebenda |
| Adversary-Runde 1 | Gegenprüfung | F001 (CRITICAL) → behoben, F002 (LOW) → behoben, F003 (LOW) → bewusst offen |
| AC-9 (Ordner heißt wie ein Interpreter) | automatisiert | ebenda |
| AC-10 (unpaarige Anführungszeichen) | automatisiert | ebenda |
| Adversary-Runde 2 | Gegenprüfung | F004 (CRITICAL, Regression aus der Behebung von F001) → behoben, F005 (MEDIUM) → behoben |
| AC-11 (Tabulator vor dem Kopf) | automatisiert | ebenda |
| AC-12 (Shell-Operator/Schalter als Grenze der Linkssuche) | automatisiert | ebenda |
| Adversary-Runde 3 | Gegenprüfung | F006 (CRITICAL, Interpreter-Erkennung griff mitten im Pfad) → behoben, F007 (LOW) → behoben |
| Adversary-Runde 4 | Gegenprüfung | F008 (HIGH, Tabulator) → behoben, F009 (MEDIUM, Suche ohne Grenze) → behoben |
| Eigene Randfallprüfung nach dem Umbau | Nachstellung | v2-Wrapper ungequotet verlor das Semikolon → AC-8 ergänzt und behoben |
| Defekt im Vorzustand belegt | Nachstellung | `git show HEAD:` beider Dateien, Ausführung gegen dieselben Fälle |
| Gemeldeter Fall läuft wieder | Nachstellung | Hook-Start aus dem Unterordner `Meditationstimer iOS/Media` |

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Begründung:** Die Änderung führt kein neues Konzept ein, sondern folgt der
  dokumentierten Vorgabe von Claude Code (`${CLAUDE_PROJECT_DIR}` für
  Hook-Pfade, https://code.claude.com/docs/en/hooks). Die geprüfte Alternative —
  jeden Hook den Projekt-Root selbst auflösen zu lassen — hilft nicht: Der
  Interpreter findet die Datei gar nicht erst, der Hook-Code läuft nie an.

## Error Handling

- Fehlt `settings.local.json` oder hat sie keinen `hooks`-Abschnitt: kein Fehler,
  Schritt wird übersprungen.
- Unlesbares JSON in `settings.local.json`: Warnung, `settings.json` wird
  trotzdem migriert.

## Out of Scope

- `hooks/hooks.json` (Plugin-Modus) — nutzt bereits `${CLAUDE_PLUGIN_ROOT}`.
- Reparatur der Bestandsprojekte selbst (separater Betriebsschritt nach dem Fix).
- **Shell-bewusstes Umschreiben (Adversary-Befund F003, LOW):** Die Ersetzung ist
  eine Textersetzung ohne Kenntnis der Shell-Grammatik. Ein `.claude/hooks/*.py`,
  das in einem angehängten Shell-Kommentar steht, wird mit umgeschrieben. Bewusst
  akzeptiert: Hook-Kommandos in `settings.json` sind schlichte
  `python3 <pfad> [args]`-Zeilen ohne Kommentare, und ein echter Shell-Parser
  wäre ein Vielfaches an Umfang für einen Fall, der in keinem der drei
  Bestandsprojekte vorkommt. Die Umschreibung bleibt in diesem Fall funktional
  korrekt — nur der Kommentartext ändert sich mit.
- **Windows-Pfade** (Backslash-Trennzeichen) werden nicht erkannt. Das Werkzeug
  läuft auf macOS/Linux.
- **Schalter-Werte, die wie Pfadstücke aussehen:** Die Linkssuche stoppt an
  einem Schalter (`-X`), nicht an dessen Wert. Bei
  `python3 -X importtime foo bar/.claude/hooks/a.py` würde `importtime` dem
  Pfad zugeschlagen. Bewusst akzeptiert: Diese Form entsteht weder aus
  `setup.py` noch aus einem der beiden dokumentierten Alt-Formate, und sie
  zuverlässig zu trennen verlangte einen echten Shell-Parser.

### Die Grenze des Verfahrens

Der Umfang dieser Änderung ist über vier Gegenprüfungs-Runden von ~30 auf ~300
Zeilen gewachsen, jede Runde an derselben Wurzel: Wo ein Dateipfad in einer
Kommandozeile *endet*, ist ohne Shell-Grammatik nicht entscheidbar, sobald er
Leerzeichen enthält und nicht in Anführungszeichen steht. Das Verfahren hier
löst die Formen, die tatsächlich vorkommen, und benennt die, die es nicht löst.
Wer es weiter treibt, sollte statt weiterer Regeln einen Shell-Parser
(`shlex`) einsetzen — der scheitert aber seinerseits genau an der ungequoteten
Lücke, um die es geht.
