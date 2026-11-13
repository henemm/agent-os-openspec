"""Vorlagen ohne Git-Wörter in wörtlich ausgegebenen Texten (Issue #597, AC-1).

Spec: docs/specs/fix-597-autoclear-klartext.md

`klartext_gate.py` (#582) weist jede Antwort mit Git-Wörtern per Exit 2 zurück.
Gibt Claude einen Ausgabeblock einer Vorlage wörtlich aus und enthält dieser
Block selbst ein Git-Wort ("committed", "Commit", "committen"), wird die
Abschlussmeldung zurückgewiesen und der Auto-/clear-Runner stolpert über den
Folge-Stop. Dieser Test hält die Wurzel trocken.

Geprüft werden in `core/commands/*.md` und `skills/*/SKILL.md`:
- jeder Block zwischen `---`-Trennern nach einer Überschrift mit "Ausgabe"
  (Abschnitt bis zur nächsten Überschrift; Inhalt nach dem 1., 3., ... Trenner,
  ein offener Block endet an der nächsten Überschrift). Mitgeprüft werden
  Überschriften mit "an den User" (`60-validate.md` "### Zusammenfassung an den
  User" ist laut Spec, Affected Files, ein auszugebender Block mit
  "Bereit für: Commit"/„Soll ich den Code committen?"),
- jede deutsch zitierte Phrase „…“ bzw. „…".
"""

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
SYNC = REPO_ROOT / "scripts" / "sync_skills.py"

HEADING_RE = re.compile(r"^#{1,6}\s")
OUTPUT_HEADING_RE = re.compile(r"Ausgabe|an den User")
SEPARATOR_RE = re.compile(r"^-{3,}\s*$")
QUOTE_RE = re.compile(r"„([^“\"\n]{1,400})[“\"]")


def _treffer():
    sys.path.insert(0, str(HOOKS_DIR))
    try:
        import klartext_gate  # noqa: PLC0415
    finally:
        sys.path.remove(str(HOOKS_DIR))
    return klartext_gate.treffer


def _template_files() -> list:
    files = sorted((REPO_ROOT / "core" / "commands").glob("*.md"))
    files += sorted((REPO_ROOT / "skills").glob("*/SKILL.md"))
    return files


def output_blocks(text: str) -> list:
    """[(Überschrift, Zeilennummer, Blocktext)] aller Ausgabeblöcke einer Vorlage."""
    blocks = []
    section = None  # (heading, start_line, [(lineno, line)])
    in_fence = False

    def flush():
        if section is None:
            return
        heading, _, body = section
        segments = [[]]
        for lineno, line in body:
            if SEPARATOR_RE.match(line):
                segments.append([])
            else:
                segments[-1].append((lineno, line))
        for i in range(1, len(segments), 2):
            seg = segments[i]
            if seg:
                blocks.append((heading, seg[0][0], "\n".join(ln for _, ln in seg)))

    for lineno, line in enumerate(text.splitlines(), start=1):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
        if not in_fence and HEADING_RE.match(line):
            flush()
            section = (line.strip(), lineno, []) if OUTPUT_HEADING_RE.search(line) else None
            continue
        if section is not None:
            section[2].append((lineno, line))
    flush()
    return blocks


def quoted_phrases(text: str) -> list:
    """[(Zeilennummer, Phrase)] aller „…“/„…"-Zitate."""
    out = []
    for m in QUOTE_RE.finditer(text):
        out.append((text.count("\n", 0, m.start()) + 1, m.group(0)))
    return out


def test_parser_findet_ausgabebloecke():
    """AC-1 (Selbstprüfung des Prüfers): der Parser findet die bekannten Blöcke.

    Ohne diese Gegenprobe könnte der Vorlagen-Test leer durchlaufen.
    """
    sample = ("### Ausgabe A: Positiv\n\n---\nZeile A1\nZeile A2\n\n"
              "### Ausgabe B: Negativ\n\n---\nZeile B\n\n---\n\nNachtext gehört nicht dazu\n"
              "## Andere Überschrift\n---\nkein Ausgabeblock\n---\n")
    blocks = [b[2] for b in output_blocks(sample)]
    assert blocks == ["Zeile A1\nZeile A2\n", "Zeile B\n"], blocks
    assert quoted_phrases("Frage „Soll ich?\" und „zweite“.") == \
        [(1, "„Soll ich?\""), (1, "„zweite“")]
    for name in ("40-tdd-red", "50-implement", "60-validate", "10-context"):
        text = (REPO_ROOT / "core" / "commands" / f"{name}.md").read_text(encoding="utf-8")
        assert output_blocks(text), f"{name}.md: kein Ausgabeblock erkannt"


def test_ausgabebloecke_und_fragen_ohne_git_woerter():
    """AC-1: kein Ausgabeblock und keine zitierte Frage enthält ein Git-Wort.

    Gegeben alle `core/commands/*.md` und `skills/*/SKILL.md`; jeder Block
    zwischen `---` nach einer "Ausgabe"-Überschrift und jede „…“-Phrase läuft
    durch `klartext_gate.treffer`; erwartet: kein einziger Treffer, und
    `skills/` ist nach `sync_skills.py` synchron zu `core/commands`.
    """
    treffer = _treffer()
    files = _template_files()
    assert len(files) >= 20, files
    befunde = []
    for path in files:
        rel = path.relative_to(REPO_ROOT)
        text = path.read_text(encoding="utf-8")
        for heading, lineno, block in output_blocks(text):
            hits = treffer(block)
            if hits:
                zeilen = [ln.strip() for ln in block.splitlines() if treffer(ln)]
                befunde.append(f"{rel}:{lineno} Block unter {heading!r}: {hits} in {zeilen}")
        for lineno, phrase in quoted_phrases(text):
            hits = treffer(phrase)
            if hits:
                befunde.append(f"{rel}:{lineno} Zitat {phrase!r}: {hits}")
    assert not befunde, ("Git-Wörter in wörtlich ausgegebenen Vorlagen-Texten "
                         f"({len(befunde)}):\n" + "\n".join(befunde))

    res = subprocess.run([sys.executable, str(SYNC), "--check"], capture_output=True,
                         text=True, cwd=str(REPO_ROOT), timeout=60)
    assert res.returncode == 0, "skills/ weicht von core/commands ab:\n" + res.stdout + res.stderr
