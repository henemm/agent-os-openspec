#!/usr/bin/env python3
"""CI-seitiges Spec-Gate — prüft auf dem Server, was lokale Hooks nur lokal erzwingen.

Warum es das gibt: Die Hooks in `core/hooks/` sind Leitplanken, keine Mauern.
Wer sie abschaltet, umschreibt oder per Bash umgeht, kommt an ihnen vorbei — und
`.claude/workflows/` ist gitignored, der Workflow-State erreicht die CI nie.
Dieses Gate arbeitet deshalb ausschliesslich mit **committeten** Dateien.

Geprüft wird pro Pull Request:

  1. Ändert der PR Code, liegt ihm eine Spec bei?
  2. Ist die Spec vollständig (Pflicht-Sektionen, AC-N, ausgefüllte ADR,
     keine Platzhalter)?
  3. Gibt es zur Spec ein PO-Briefing, ist es vollständig — und ist es AKTUELL?
     Die Aktualität prüft der `spec_sha256`-Stempel, den `workflow.py
     set-briefing` in den Briefing-Frontmatter schreibt.

Die Regeln kommen aus denselben Funktionen wie die lokalen Gates
(`workflow.check_briefing_content`, `workflow.check_adr_content`,
`hook_utils.extract_ac_entries`) — eine Regel, zwei Aufrufer.

Aufruf:

    python3 scripts/ci_spec_gate.py --base origin/main
    python3 scripts/ci_spec_gate.py --changed-files a.py docs/specs/x.md

Exit 0 = frei, 1 = blockiert (Report auf stdout).

Escape: Commit-Trailer `Spec-Gate: skip <Grund>` — sichtbar in der Historie und
im PR, im Gegensatz zu einem stillen Config-Flip. Kill-Switch:
config.yaml → `ci_spec_gate.enabled: false`.
"""

import argparse
import hashlib
import re
import subprocess
import sys
from pathlib import Path

# Pfade, unter denen die geteilten Hook-Funktionen liegen können: im Framework-
# Repo selbst (core/hooks) und in einem Projekt, in das setup.py installiert hat
# (.claude/hooks).
_HOOK_DIRS = ("core/hooks", ".claude/hooks")

# Dateien, die für sich genommen keine Spec verlangen.
DEFAULT_EXEMPT_PREFIXES = (
    "docs/", "tests/", ".github/", ".claude/", "openspec/",
)
DEFAULT_EXEMPT_SUFFIXES = (".md", ".txt", ".lock")
DEFAULT_EXEMPT_FILES = (".gitignore", "LICENSE", "CHANGELOG.md", "README.md")

SPEC_REQUIRED_SECTIONS = (
    ("Scope", r"Scope"),
    ("Definition of Done", r"(?:Definition\s+of\s+Done|DoD)"),
    ("Acceptance Criteria", r"Acceptance\s+Criteria"),
    ("Test Plan", r"Test\s*Plan"),
)

SPEC_PLACEHOLDERS = ("[todo", "[tbd", "todo:", "fixme:", "xxx:")

TRAILER_RE = re.compile(r"^\s*Spec-Gate:\s*skip\b[ \t]*(.*)$", re.IGNORECASE | re.MULTILINE)


def _hook_dir_candidates(root: Path) -> list[Path]:
    """Mögliche Fundorte der geteilten Hook-Module, in Prioritätsreihenfolge.

    Zuerst die des geprüften Projekts, dann die neben diesem Script: Das Gate
    wird zusammen mit den Hooks ausgeliefert (Framework-Repo: `scripts/` neben
    `core/hooks/`, installiertes Projekt: `.claude/scripts/` neben
    `.claude/hooks/`). Ohne diesen zweiten Pfad scheitert das Gate überall dort,
    wo `--root` auf einen Baum ohne eigene Hooks zeigt.
    """
    here = Path(__file__).resolve().parent
    return [root / rel for rel in _HOOK_DIRS] + [
        here.parent / "core" / "hooks", here.parent / "hooks", here,
    ]


def _load_hook_module(root: Path, name: str):
    """Importiere ein Hook-Modul aus dem Projekt oder aus der Script-Nachbarschaft."""
    for candidate in _hook_dir_candidates(root):
        if (candidate / f"{name}.py").exists():
            if str(candidate) not in sys.path:
                sys.path.insert(0, str(candidate))
            try:
                return __import__(name)
            except Exception:
                continue
    return None


def _config(root: Path, section_name: str = "ci_spec_gate") -> dict:
    """Lies einen flachen Abschnitt (Default `ci_spec_gate:`) aus config.yaml —
    ohne PyYAML-Zwang.

    Reicht für flache Schalter; fehlt PyYAML, greift der Mini-Parser.
    """
    path = root / "config.yaml"
    if not path.exists():
        return {}
    text = path.read_text()
    try:
        import yaml  # type: ignore
        data = yaml.safe_load(text) or {}
        section = data.get(section_name, {})
        return section if isinstance(section, dict) else {}
    except Exception:
        pass
    match = re.search(r"^" + re.escape(section_name) + r":\s*$(.*?)(?=^\S|\Z)",
                      text, re.MULTILINE | re.DOTALL)
    if not match:
        return {}
    out = {}
    for line in match.group(1).splitlines():
        if ":" in line and line.startswith((" ", "\t")):
            key, _, value = line.strip().partition(":")
            value = value.strip()
            out[key.strip()] = {"true": True, "false": False}.get(value.lower(), value)
    return out


def _changed_files_from_git(root: Path, base: str) -> list[str]:
    merge_base = subprocess.run(
        ["git", "merge-base", base, "HEAD"], cwd=root, capture_output=True, text=True
    )
    ref = merge_base.stdout.strip() or base
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{ref}...HEAD"],
        cwd=root, capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"WARNUNG: git diff fehlgeschlagen ({result.stderr.strip()}) — Gate übersprungen.")
        return []
    return [line for line in result.stdout.splitlines() if line.strip()]


def _commit_messages(root: Path, base: str) -> str:
    result = subprocess.run(
        ["git", "log", "--format=%B", f"{base}..HEAD"],
        cwd=root, capture_output=True, text=True,
    )
    return result.stdout if result.returncode == 0 else ""


def _is_exempt(path: str) -> bool:
    return (
        path in DEFAULT_EXEMPT_FILES
        or path.startswith(DEFAULT_EXEMPT_PREFIXES)
        or path.endswith(DEFAULT_EXEMPT_SUFFIXES)
    )


def _is_spec(path: str) -> bool:
    return (
        path.startswith("docs/specs/")
        and path.endswith(".md")
        and Path(path).name != "_template.md"
    )


def _is_fast_spec(path: str) -> bool:
    return path.startswith("docs/specs/fast/")


def _section_body(content: str, pattern: str) -> "str | None":
    match = re.search(
        r"^#{2,3}\s*" + pattern + r"[^\n]*$(.*?)(?=^#{1,3}\s|\Z)",
        content, re.IGNORECASE | re.MULTILINE | re.DOTALL,
    )
    return match.group(1) if match else None


def _check_spec(root: Path, rel: str, problems: list[str]) -> None:
    content = (root / rel).read_text()

    for label, pattern in SPEC_REQUIRED_SECTIONS:
        if _section_body(content, pattern) is None:
            problems.append(f"{rel}: Pflicht-Sektion '## {label}' fehlt.")

    lowered = content.lower()
    for marker in SPEC_PLACEHOLDERS:
        if marker in lowered:
            problems.append(f"{rel}: enthält noch einen Platzhalter ('{marker}').")
            break

    hook_utils = _load_hook_module(root, "hook_utils")
    if hook_utils is not None and _section_body(content, r"Acceptance\s+Criteria") is not None:
        entries = hook_utils.extract_ac_entries(content)
        if not entries:
            problems.append(
                f"{rel}: '## Acceptance Criteria' ohne AC-N-Einträge "
                "(Format: '- **AC-1:** Given ... / When ... / Then ...')."
            )
        for label, desc, _raw in entries:
            if len(desc.strip()) < 30:
                problems.append(
                    f"{rel}: {label} ist zu knapp ({len(desc.strip())} Zeichen, ≥ 30 nötig)."
                )

    workflow = _load_hook_module(root, "workflow")
    if workflow is not None:
        adr_err = workflow.check_adr_content(content)
        if adr_err:
            problems.append(f"{rel}: {adr_err}")


def _find_briefing(root: Path, spec_rel: str, workflow) -> "tuple[Path, dict] | None":
    briefings_dir = root / "docs" / "briefings"
    if not briefings_dir.is_dir():
        return None
    for path in sorted(briefings_dir.rglob("*.md")):
        try:
            front = workflow.parse_briefing_frontmatter(path.read_text())
        except Exception:
            continue
        if front.get("spec_file") == spec_rel:
            return path, front
    return None


def _check_briefing(root: Path, spec_rel: str, problems: list[str]) -> None:
    workflow = _load_hook_module(root, "workflow")
    if workflow is None:
        problems.append(
            "workflow.py nicht gefunden (weder core/hooks noch .claude/hooks) — "
            "Briefing kann nicht geprüft werden."
        )
        return

    found = _find_briefing(root, spec_rel, workflow)
    if found is None:
        problems.append(
            f"{spec_rel}: kein PO-Briefing in docs/briefings/ gefunden, das auf diese Spec "
            "verweist. Erstellen (/30-write-spec Step 3b) und mit "
            "`workflow.py set-briefing <pfad>` registrieren — das schreibt den nötigen "
            "Frontmatter-Stempel."
        )
        return

    path, front = found
    rel = path.relative_to(root).as_posix()

    # Wortgrenze aus po_briefing_gate.max_words — nur, wenn das geladene
    # workflow.py sie schon kennt (ältere Projekt-Kopien: nur Vollständigkeit).
    max_words_fn = getattr(workflow, "po_briefing_max_words", None)
    if max_words_fn is not None:
        limit = max_words_fn(_config(root, "po_briefing_gate"))
        content_err = workflow.check_briefing_content(path.read_text(), limit)
    else:
        content_err = workflow.check_briefing_content(path.read_text())
    if content_err:
        problems.append(f"{rel}: {content_err}")

    stored = front.get("spec_sha256", "")
    if not stored:
        problems.append(
            f"{rel}: ohne `spec_sha256` im Frontmatter — die Bindung an die Spec-Fassung "
            "fehlt. Mit `workflow.py set-briefing <pfad>` registrieren."
        )
        return

    current = hashlib.sha256((root / spec_rel).read_bytes()).hexdigest()
    if stored != current:
        problems.append(
            f"{rel}: Briefing ist VERALTET — es beschreibt eine andere Fassung von "
            f"{spec_rel} als die in diesem PR. Briefing neu erstellen und registrieren."
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Projekt-Wurzel (Default: .)")
    parser.add_argument("--base", help="Basis-Ref für git diff, z.B. origin/main")
    parser.add_argument("--changed-files", nargs="*", default=None,
                        help="Explizite Dateiliste statt git diff (für Tests)")
    parser.add_argument("--commit-message", default=None,
                        help="Commit-Text für den Skip-Trailer (statt git log)")
    args = parser.parse_args()

    root = Path(args.root).resolve()

    cfg = _config(root)
    if cfg.get("enabled") is False:
        print("Spec-Gate: per config.yaml deaktiviert (ci_spec_gate.enabled: false).")
        return 0

    if args.changed_files is not None:
        changed = list(args.changed_files)
    elif args.base:
        changed = _changed_files_from_git(root, args.base)
    else:
        print("Spec-Gate: weder --base noch --changed-files angegeben — nichts zu prüfen.")
        return 0

    message = args.commit_message
    if message is None and args.base:
        message = _commit_messages(root, args.base)
    if message:
        trailer = TRAILER_RE.search(message)
        if trailer:
            reason = trailer.group(1).strip() or "(kein Grund angegeben)"
            print(f"Spec-Gate: skip per Commit-Trailer — Grund: {reason}")
            return 0

    code_changed = [f for f in changed if not _is_exempt(f)]
    specs = [f for f in changed if _is_spec(f)]

    if not code_changed:
        print("Spec-Gate: keine Code-Änderung im PR — nichts zu prüfen.")
        return 0

    problems: list[str] = []

    if not specs:
        problems.append(
            "Der PR ändert Code, enthält aber keine Spec unter docs/specs/.\n"
            "    Betroffen: " + ", ".join(code_changed[:8])
            + ("" if len(code_changed) <= 8 else f" (+{len(code_changed) - 8} weitere)")
            + "\n    Spec nachreichen — oder bewusst aussteigen mit dem Commit-Trailer "
              "'Spec-Gate: skip <Grund>'."
        )

    for spec_rel in specs:
        if not (root / spec_rel).exists():
            continue  # Im PR gelöschte Spec — nicht prüfbar
        if _is_fast_spec(spec_rel):
            print(f"Spec-Gate: {spec_rel} ist eine Fast-Track-Spec — Briefing nicht verlangt.")
            continue
        _check_spec(root, spec_rel, problems)
        _check_briefing(root, spec_rel, problems)

    if problems:
        print("SPEC-GATE: BLOCKIERT")
        print("=" * 60)
        for problem in problems:
            print(f"  - {problem}")
        print("=" * 60)
        print(
            "Diese Prüfung läuft serverseitig, weil lokale Hooks abschaltbar sind.\n"
            "Kill-Switch fürs ganze Projekt: config.yaml → ci_spec_gate.enabled: false"
        )
        return 1

    print("SPEC-GATE: OK")
    if specs:
        print(f"  Geprüfte Specs: {', '.join(specs)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
