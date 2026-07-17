# Kontext: fix-60-69-gate-parsing

**Issues:** #60 (edit_gate AC-Längencheck), #69 (Verdict-Parsing)
**Consumer-Tracker:** henemm/gregor_zwanzig#1295
**Plugin-Version bei Fund:** 3.9.1

## Warum beides in einem Zug

Beide Fehler sind dasselbe Grundmuster: **ein naiver globaler Regex-Scan über ein strukturiertes Markdown-Artefakt**, der Fundstellen wertet, die gar keine Deklarationen sind. Sie liegen in derselben Datei-Familie (`core/hooks/edit_gate.py`, `core/hooks/adversary_dialog.py`) und werden vom selben Gate-Pfad ausgelöst. Getrennt zu fixen hieße, zweimal dieselbe Konsolidierungs-Entscheidung zu treffen.

## Befund 1 — #60: AC-Längencheck matcht Prosa

`core/hooks/edit_gate.py:194`:
```python
for m in re.finditer(r'\bAC-\d+[:\s]+(.*)', content):
    desc = m.group(1).strip()
    if len(desc) < 30:
        return ("BLOCKED: AC entry too short ...")
```

Der Scan läuft über die **ganze Datei** und wertet **jede Erwähnung** von `AC-N` gefolgt von `:` oder Whitespace als AC-Deklaration. Jeder Querverweis im Fließtext („…wie in AC-2 beschrieben…"), jede Tabellenzelle `| AC-1 … AC-8 |` und jeder Zeilenumbruch nach einer AC-Nummer erzeugt einen kurzen „Beschreibungstext" und blockt an der 30-Zeichen-Schwelle.

**Wirkung:** blockt ab Phase 6 **jeden** Write des Workflows, nicht nur die Spec-Datei. Seit 2026-07-08 dokumentiert **7×** im Consumer-Projekt aufgetreten, jedes Mal Kategorie c (fälschlich blockierendes Gate).

Belegte Fundstellen aus `docs/specs/bugfix/fix_1275_sms_thunder_today.md` (6 einwandfreie AC-Definitionen, alle > 30 Zeichen):

| Zeichen | Match | tatsächliche Herkunft |
|---|---|---|
| 25 | `'durch SMS-, Telegram- und'` | „…aus **AC-1** durch SMS-, Telegram- und…" (Zeilenumbruch) |
| 3 | `'und'` | „…in **AC-2** und…" |
| 20 | `'nie gegen den echten'` | „…**AC-2** nie gegen den echten Renderpfad geprüft…" |

### Teilbefund 1a — Scope-Leck über Repo-Grenze

Der Längencheck feuerte auch bei einem `Write` auf einen Pfad **außerhalb** des Repos (Session-Scratchpad unter `/tmp`). Der Check gehört auf Repo-Pfade begrenzt.

### Teilbefund 1b — der Check hängt an der Spec-Spiegelung

`core/hooks/edit_gate.py:165-169`:
```python
spec_path = _root / spec_file
if not spec_path.exists():
    return None
```

`_root` ist das **Haupt-Repo**. Liegt die Spec nur im Worktree, existiert sie unter `_root` nicht — der Check steigt aus und lässt **alles** durch. Er springt erst an, sobald die Spec nach `main` gespiegelt wird, und blockt dann das Falsche.

**Daraus folgt: Der Check hat nie gehalten, was er sollte, und hält jetzt das Falsche.** Specs, die nie gespiegelt werden, prüft er gar nicht.

## Befund 2 — #69: Verdict-Parsing liest den ersten statt den letzten Block

`core/hooks/adversary_dialog.py:335` (einzige Fundstelle; `qa_gate.py` ruft hierüber auf):
```python
verdict_match = re.search(r"## Verdict\s*\n\*\*(.+?)\*\*", content)
```

Nach einem Fix-Loop (BROKEN → Fix → Adversary hängt Runde 3 mit VERIFIED an) enthält das Artefakt **zwei** `## Verdict`-Blöcke. `re.search` liefert den **ersten** — das veraltete BROKEN. Das Gate blockt, obwohl final VERIFIED vergeben wurde.

**Warum das gefährlich ist:** Der einzige Ausweg ist heute Handarbeit am Gate-Artefakt. Genau das erzwingt das self-modifying-gate-Muster, das die Projektregeln verbieten — und es normalisiert einen Handgriff, den irgendwann jemand auch dann macht, wenn das Ergebnis nicht stimmt.

## Wiederverwendbare korrekte Lösung existiert bereits

`core/hooks/adversary_dialog.py::parse_spec_expected_behavior` (ab ~:75) macht es **richtig**: eine section-gebundene State-Machine, die nur unindentierte AC-Bullet-Deklarationszeilen wertet und alle vier Label-Varianten abdeckt:

```python
ac_bullet_re = re.compile(r"^-\s+\*{0,2}AC-\d+[^:*]*\*{0,2}\s*:")
```
- `- **AC-1:** …` (Doppelpunkt innerhalb Bold)
- `- **AC-1**: …` (Doppelpunkt außerhalb Bold)
- `- **AC-8 (praezisiert):** …` (Klammer-Zusatz)
- `- AC-1: …` (ohne Bold)

Entstanden in PR #59 als Fix für **denselben Bug-Typ** in `adversary_dialog.py`. `edit_gate.py` wurde damals nicht mitgezogen — daher #60.

**Konsequenz für den Fix:** Die Erkennung wird **geteilt**, nicht ein zweites Mal geschrieben. Zwei divergente Parser für dasselbe Format sind die Ursache dieses Issues. Naheliegender Ort: `core/hooks/hook_utils.py` (Shared Bootstrap, von beiden Hooks bereits importiert); `adversary_dialog.py` nutzt die geteilte Funktion weiter, `edit_gate.py` neu.

## PO-Entscheidung zum Scope (2026-07-17)

Teilbefund 1b wird **mitrepariert**: Die Spec-Auflösung greift künftig auch, wenn die Spec nur im Worktree liegt. Damit hängt der Check nicht länger an der Spiegelung nach `main`.

Das macht das Gate **strenger als heute** — Specs, die bisher unbemerkt durchliefen, werden ab sofort geprüft. Bewusst so entschieden: Ein Check, der nur zufällig greift, hat keinen Wert. `hook_utils._find_worktree_root()` existiert bereits und wird in `edit_gate.py` an anderer Stelle (`_is_stop_locked`) bereits genau dafür verwendet.

## Randbedingungen

- **Keine Breaking Changes** ohne Migration-Pfad (Repo-Konvention)
- Der Legacy-Stichtag (`ac_format_required_since`) bleibt unangetastet
- `CHANGELOG.md` unter `[Unreleased]` pflegen, danach Version-Bump auf 3.9.2 + Verteilung — sonst wirkt der Fix im Consumer-Projekt nicht
- Test-Suite vorhanden: `tests/` (pytest). `tests/test_adversary_dialog_parse.py` deckt die korrekte Parse-Logik aus PR #59 ab und ist Vorlage für die neuen Tests
- Nebenbefund: `.worktrees/` fehlt in `.gitignore` (untracked sichtbar) — Einzeiler, kann mit
