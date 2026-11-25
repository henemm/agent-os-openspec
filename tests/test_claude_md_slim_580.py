"""Issue #580: CLAUDE.md verschlanken — Groessenwaechter und Pinn-Tests.

CLAUDE.md wird in jedem Hauptzug und jedem Teilagenten-Start mitgelesen. Sie
behaelt nur, was in jedem Zug gelten muss; Nachschlagewissen steht in
docs/architektur.md.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CLAUDE_MD = REPO_ROOT / "CLAUDE.md"
ARCHITEKTUR = REPO_ROOT / "docs" / "architektur.md"

BUDGET_BYTES = 12 * 1024

MOVED_SECTIONS = [
    "Architektur",
    "8-Phasen-Workflow",
    "Parallele Workflows",
    "TDD mit ECHTEN Artefakten",
    "Modell-Zuweisungsstrategie",
    "Adversary System",
    "PO-Briefing-Gate",
    "CI-Spec-Gate",
    "Stop Lock",
    "Override Token",
    "Hook-Architektur",
    "Session-Register",
    "Improvement-Flow",
    "Wichtige Dateien",
    "Slash-Commands Übersicht",
]


def _headings(text: str) -> list[str]:
    return [m.group(1) for m in re.finditer(r"^#{2,4} (.+)$", text, re.M)]


def test_claude_md_within_budget():
    size = len(CLAUDE_MD.read_bytes())
    assert size <= BUDGET_BYTES, (
        f"CLAUDE.md hat {size} Bytes, Budget {BUDGET_BYTES} (#580). "
        "Nachschlagewissen gehoert nach docs/architektur.md.")


def test_claude_md_links_architektur():
    assert "docs/architektur.md" in CLAUDE_MD.read_text(encoding="utf-8")
    assert ARCHITEKTUR.is_file()


def test_architektur_has_moved_sections():
    heads = _headings(ARCHITEKTUR.read_text(encoding="utf-8"))
    missing = [s for s in MOVED_SECTIONS if not any(h.startswith(s) or s in h for h in heads)]
    assert not missing, f"docs/architektur.md ohne Abschnitte: {missing}"


def test_claude_md_keeps_core_rules():
    text = CLAUDE_MD.read_text(encoding="utf-8")
    heads = _headings(text)
    for s in ("Rollen und Zusammenarbeit", "Arbeitsweise", "Orchestrator-Prinzip",
              "Workflow-Isolation", "Adversary-Limit"):
        assert any(s in h for h in heads), f"CLAUDE.md ohne Abschnitt {s!r}"
    assert re.search(r"^\*\*Version\*\*: \d+\.\d+\.\d+", text, re.M)
    assert "#165" in text and "cwd-relativ" in text, "Regel Hook-Pfade fehlt"
    assert "core/hooks/" in text and "core/agents/" in text and "override" in text, \
        "Regel Infrastruktur-Schutz fehlt"
    assert "skills/" in text and "sync_skills.py" in text, "Regel generierte skills/ fehlt"


def test_reference_facts_still_documented():
    both = CLAUDE_MD.read_text(encoding="utf-8") + "\n" + ARCHITEKTUR.read_text(encoding="utf-8")
    zeilen = [z for z in both.splitlines() if "core/hooks/hook_utils.py" in z]
    for fn in ("read_state_text", "atomic_write_text", "is_stop_locked"):
        assert any(fn in z for z in zeilen), fn
    assert "scripts/sync_cloud_agents.py" in both and ".claude/agents/" in both
    assert any(ln.startswith("| **Haiku**") for ln in both.splitlines())
    for marker in ("Agent-Kaskaden-Effekt", "Teste Hooks",
                   "Siehst du einen anderen Workflow", "Beim Bearbeiten des Frameworks"):
        assert marker in both, marker
