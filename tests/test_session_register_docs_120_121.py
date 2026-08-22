"""Dokument-ACs zu fix-120-121-session-register (AC-18, AC-34, AC-35).

Der Issue-Claim (#121) lebt nicht im Code allein: er muss aus `/00-intake`
heraus aufgerufen werden, sobald die Issue-Nummer bekannt ist. Ohne den
Aufruf in den beiden Command-Dateien bleibt der neue `claim`-Modus toter Code.

`core/commands/00-intake.md` und `skills/00-intake/SKILL.md` sind bewusst zwei
unabhaengig gepflegte Kopien (Known Limitation der Spec) — beide werden hier
einzeln geprueft, damit ein Drift zwischen ihnen auffaellt.
"""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

COMMAND_FILE = REPO_ROOT / "core" / "commands" / "00-intake.md"
SKILL_FILE = REPO_ROOT / "skills" / "00-intake" / "SKILL.md"
FEAT_106_SPEC = REPO_ROOT / "docs" / "specs" / "feat-106-session-register.md"

# Ueberschrift, vor der der Claim stehen muss: der Claim braucht keinen
# laufenden Workflow und gehoert daher vor die Track-Bewertung.
TRACK_HEADING = "### 2. Score präsentieren"


def _read(path: Path) -> str:
    assert path.is_file(), f"{path.relative_to(REPO_ROOT)} existiert nicht"
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# AC-18 — feat-106 AC-11 ist als ueberholt markiert
# ---------------------------------------------------------------------------

def test_feat_106_ac11_marked_superseded():
    """AC-18: die revidierte AC der Vorgaenger-Spec verweist auf diese Spec.

    feat-106 AC-11 ('guard legt niemals einen Eintrag an') wird durch A2
    bewusst ungueltig. Eine stillschweigende Revision einer freigegebenen AC
    waere nicht nachvollziehbar — der Verweis muss in der Datei stehen.
    """
    text = _read(FEAT_106_SPEC)

    match = re.search(r"^- \*\*AC-11.*$", text, re.MULTILINE)
    assert match, "AC-11 in feat-106-session-register.md nicht gefunden"

    line = match.group(0)
    assert "ÜBERHOLT" in line.upper() or "UEBERHOLT" in line.upper(), (
        f"AC-11 nicht als ueberholt markiert: {line!r}"
    )
    assert "fix-120-121-session-register" in line, (
        "AC-11 verweist nicht auf die ersetzende Spec"
    )


# ---------------------------------------------------------------------------
# AC-34 / AC-35 — Claim-Aufruf in beiden Intake-Dateien
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path,invocation", [
    pytest.param(
        COMMAND_FILE,
        "python3 .claude/hooks/session_singleton_guard.py claim --issue",
        id="core/commands/00-intake.md",
    ),
    pytest.param(
        SKILL_FILE,
        "python3 ${_H}/session_singleton_guard.py claim --issue",
        id="skills/00-intake/SKILL.md",
    ),
])
def test_intake_claims_issue_before_track_assessment(path, invocation):
    """AC-34/AC-35: der Claim-Aufruf steht VOR der Track-Bewertung.

    Platzierung ist Teil der AC: erst beim Workflow-Start zu claimen waere zu
    spaet — im Fast Track entsteht nie ein Workflow, und genau dort will man
    trotzdem wissen, wer an Issue #N sitzt.
    """
    text = _read(path)

    assert invocation in text, (
        f"{path.name} ruft den Claim nicht auf (erwartet: {invocation!r})"
    )

    heading_pos = text.find(TRACK_HEADING)
    assert heading_pos != -1, f"{path.name}: Abschnitt {TRACK_HEADING!r} nicht gefunden"

    claim_pos = text.find(invocation)
    assert claim_pos < heading_pos, (
        f"{path.name}: Claim-Aufruf steht hinter der Track-Bewertung "
        f"(Position {claim_pos} vs. {heading_pos})"
    )
