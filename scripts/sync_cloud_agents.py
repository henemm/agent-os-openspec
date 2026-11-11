#!/usr/bin/env python3
"""Projekt-Agenten `.claude/agents/` aus `core/agents/` erzeugen (#577).

Cloud-Sitzungen (Claude Code on the web) laden keine Plugins (#520). Die
Framework-Agenten (`implementation-validator`, `po-briefer`, ...) fehlten dort
als Agent-Typen; ein benannter Start fiel auf `general-purpose` zurueck, erbte
das Modell der Hauptsitzung und las seine Definition per `cat` nach.
Projekt-Agenten aus `.claude/agents/` sind Teil des Klons und werden auch in
der Cloud geladen; das Modell kommt dann aus dem Frontmatter.

`core/agents/` bleibt die einzige Quelle. Jede Kopie ist identisch zur Quelle
bis auf eine Markerzeile (`AGENT_MARKER`) direkt hinter dem schliessenden
`---` des Frontmatters (ohne Frontmatter: als erste Zeile; Muster
`core/hooks/alias_sync.py`). Regeln je Zieldatei:

- fehlt: schreiben (`--check`: "fehlt")
- markiert, Inhalt weicht ab: ueberschreiben (`--check`: "abweichend")
- markiert, ohne Quelle: entfernen (`--check`: "veraltet")
- nicht markiert (Eigenbau, Modul-Agent): nie ueberschreiben, nie loeschen,
  als "Skipped" melden; `--check` zaehlt das nicht als Drift

    python3 scripts/sync_cloud_agents.py          # .claude/agents neu schreiben
    python3 scripts/sync_cloud_agents.py --check  # nur pruefen, Exit 1 bei Drift

`setup.py` (`--cloud-gates`, `--update` mit Cloud-Pin) nutzt `plan()` fuer
Plugin-Konsumenten. `release_check.py` (Zeile "Cloud-Agenten") blockt das
Release bei Drift.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

AGENT_MARKER = "<!-- openspec-cloud-agent: generated from core/agents, do not edit -->"
_MARKER_PREFIX = "<!-- openspec-cloud-agent:"

SYNC_HINT = "python3 scripts/sync_cloud_agents.py"


def _frontmatter_close(lines: "list[str]") -> "int | None":
    """Index des schliessenden `---`, wenn die Datei mit Frontmatter beginnt."""
    if not lines or lines[0].rstrip("\r\n").rstrip() != "---":
        return None
    for index in range(1, len(lines)):
        if lines[index].rstrip("\r\n").rstrip() == "---":
            return index
    return None


def render_agent(text: str) -> str:
    """Quelle -> Generat: Markerzeile hinter das Frontmatter (sonst an den Anfang)."""
    lines = text.splitlines(keepends=True)
    close = _frontmatter_close(lines)
    if close is None:
        return f"{AGENT_MARKER}\n{text}"
    head = lines[:close + 1]
    if not head[-1].endswith("\n"):
        head[-1] += "\n"
    return "".join(head) + f"{AGENT_MARKER}\n" + "".join(lines[close + 1:])


def is_generated(text: str) -> bool:
    """True, wenn die Datei eine markierte Kopie ist (Marker in Zeile 1 oder hinter dem Frontmatter)."""
    lines = text.splitlines()
    if not lines:
        return False
    if lines[0].startswith(_MARKER_PREFIX):
        return True
    close = _frontmatter_close(lines)
    if close is None or close + 1 >= len(lines):
        return False
    return lines[close + 1].startswith(_MARKER_PREFIX)


def _read_text(path: Path) -> "str | None":
    try:
        return path.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def plan(src_dir: Path, dst_dir: Path) -> "tuple[list, list, list]":
    """Reine Berechnung, schreibt nichts.

    Rueckgabe `(writes, removals, skipped)`:
      writes    [(Zielpfad, Bytes)] — fehlende oder abweichende markierte Kopien
      removals  [Zielpfad]          — markierte Kopien ohne Quelle
      skipped   ["<datei> (Grund)"] — unmarkierte oder unlesbare Dateien, nie angefasst
    """
    src_dir, dst_dir = Path(src_dir), Path(dst_dir)
    sources = {p.name: p for p in sorted(src_dir.glob("*.md")) if p.is_file()}
    writes: list = []
    removals: list = []
    skipped: list = []

    for name, src in sources.items():
        data = render_agent(src.read_bytes().decode("utf-8")).encode("utf-8")
        dst = dst_dir / name
        if dst.is_symlink():
            skipped.append(f"{name} (Symlink)")
            continue
        if not dst.exists():
            writes.append((dst, data))
            continue
        if not dst.is_file():
            skipped.append(f"{name} (keine regulaere Datei)")
            continue
        current = _read_text(dst)
        if current is None:
            skipped.append(f"{name} (nicht lesbar)")
            continue
        if not is_generated(current):
            skipped.append(f"{name} (eigene Datei)")
            continue
        if current.encode("utf-8") != data:
            writes.append((dst, data))

    if dst_dir.is_dir():
        for dst in sorted(dst_dir.glob("*.md")):
            if dst.name in sources:
                continue
            if dst.is_symlink() or not dst.is_file():
                continue
            current = _read_text(dst)
            if current is not None and is_generated(current):
                removals.append(dst)
            else:
                skipped.append(f"{dst.name} (eigene Datei)")
    return writes, removals, skipped


def _paths(root: Path) -> "tuple[Path, Path]":
    root = Path(root)
    return root / "core" / "agents", root / ".claude" / "agents"


def sync(root: Path = REPO_ROOT) -> "tuple[list, list, list]":
    """Schreibt nur Abweichendes, entfernt veraltete markierte Kopien.

    Rueckgabe `(geschrieben, entfernt, skipped)` (Pfade bzw. Meldungen).
    """
    src_dir, dst_dir = _paths(root)
    if not src_dir.is_dir():
        raise OSError(f"{src_dir} fehlt")
    writes, removals, skipped = plan(src_dir, dst_dir)
    written = []
    for path, data in writes:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        written.append(path)
    for path in removals:
        path.unlink()
    return written, removals, skipped


def drift(root: Path = REPO_ROOT) -> "tuple[list, list]":
    """(Drift-Zeilen, Skipped-Meldungen) — schreibt nichts."""
    src_dir, dst_dir = _paths(root)
    if not src_dir.is_dir():
        raise OSError(f"{src_dir} fehlt")
    writes, removals, skipped = plan(src_dir, dst_dir)
    lines = []
    for path, _ in writes:
        state = "abweichend" if path.exists() else "fehlt"
        lines.append(f"{state}: .claude/agents/{path.name}")
    for path in removals:
        lines.append(f"veraltet: .claude/agents/{path.name}")
    return lines, skipped


def check(root: Path = REPO_ROOT) -> "tuple[bool, str]":
    """(synchron?, Meldung) — schreibt nichts. Unmarkierte Dateien sind keine Drift."""
    try:
        lines, skipped = drift(root)
    except (OSError, ValueError) as exc:
        return False, f"Cloud-Agenten nicht pruefbar: {exc} — {SYNC_HINT}"
    if lines:
        return False, (f"Cloud-Agenten nicht synchron ({'; '.join(lines)}) — "
                       f"{SYNC_HINT} ausführen")
    count = len([p for p in _paths(root)[0].glob("*.md") if p.is_file()])
    extra = f", {len(skipped)} eigene Datei(en) uebersprungen" if skipped else ""
    return True, f"Cloud-Agenten synchron mit core/agents ({count} Agenten{extra})"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true",
                        help="nichts schreiben; Exit 1, wenn .claude/agents abweicht")
    parser.add_argument("--root", type=Path, default=REPO_ROOT,
                        help="Repo-Wurzel mit core/agents und .claude/agents "
                             "(Default: dieses Repo)")
    args = parser.parse_args()
    root = args.root.resolve()

    if args.check:
        try:
            lines, skipped = drift(root)
        except (OSError, ValueError) as exc:
            print(f"Cloud-Agenten nicht pruefbar: {exc} — {SYNC_HINT}", file=sys.stderr)
            return 1
        for entry in skipped:
            print(f"Skipped: {entry}")
        for line in lines:
            print(f"Drift {line}", file=sys.stderr)
        ok, msg = check(root)
        print(msg, file=sys.stdout if ok else sys.stderr)
        return 0 if ok else 1

    try:
        written, removed, skipped = sync(root)
    except (OSError, ValueError) as exc:
        print(f"Cloud-Agenten nicht erzeugt: {exc}", file=sys.stderr)
        return 1
    for path in written:
        print(f"Geschrieben: .claude/agents/{path.name}")
    for path in removed:
        print(f"Entfernt: .claude/agents/{path.name}")
    for entry in skipped:
        print(f"Skipped: {entry}")
    if not written and not removed:
        print(".claude/agents: unveraendert.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
