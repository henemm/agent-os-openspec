"""Tests für parse_spec_expected_behavior() AC-N-Format-Support (Issue gregor_zwanzig#965).

`adversary_dialog.py parse` erkannte bisher ausschließlich die alte
`## Expected Behavior`-Section mit einfachen Bullets. Das seit Epic #191
vorgeschriebene AC-N-Format (`## Acceptance Criteria` mit
`- **AC-N:** Given.../When.../Then...`) wurde komplett übersehen.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
sys.path.insert(0, str(HOOKS_DIR))

from adversary_dialog import parse_spec_expected_behavior


def test_ac_n_format_single_line(tmp_path):
    """AC-1: reine Acceptance-Criteria-Section mit Standard-AC-N-Bullets."""
    spec = tmp_path / "spec.md"
    spec.write_text(
        "## Acceptance Criteria\n\n"
        "- **AC-1:** Given a / When b / Then c\n\n"
        "- **AC-2:** Given d / When e / Then f\n\n"
        "- **AC-3:** Given g / When h / Then i\n"
    )
    points = parse_spec_expected_behavior(str(spec))
    assert len(points) == 3
    assert points[0].startswith("**AC-1:**")
    assert points[1].startswith("**AC-2:**")
    assert points[2].startswith("**AC-3:**")


def test_ac_label_with_parenthetical_suffix(tmp_path):
    """AC-2: AC-Label mit Klammer-Zusatz wird trotzdem erkannt."""
    spec = tmp_path / "spec.md"
    spec.write_text(
        "## Acceptance Criteria\n\n"
        "- **AC-8 (präzisiert):** Given a / When b / Then c\n"
    )
    points = parse_spec_expected_behavior(str(spec))
    assert len(points) == 1
    assert "AC-8" in points[0]
    assert "präzisiert" in points[0]


def test_ac_multiline_soft_wrap_continuation(tmp_path):
    """AC-3: mehrzeiliger AC-Eintrag mit Fließtext-Fortsetzung ohne '-'-Präfix."""
    spec = tmp_path / "spec.md"
    spec.write_text(
        "## Acceptance Criteria\n\n"
        "- **AC-1:** Given eine Bedingung die sich über mehrere\n"
        "  Zeilen erstreckt und hier fortgesetzt wird / When etwas\n"
        "  passiert / Then folgt ein Ergebnis\n"
    )
    points = parse_spec_expected_behavior(str(spec))
    assert len(points) == 1
    assert "erstreckt" in points[0]
    assert "fortgesetzt" in points[0]
    assert "Ergebnis" in points[0]


def test_ac_sub_bullet_test_line_excluded(tmp_path):
    """AC-4: eingerückter '- Test: ...'-Sub-Bullet wird nicht als eigener Punkt gezählt."""
    spec = tmp_path / "spec.md"
    spec.write_text(
        "## Acceptance Criteria\n\n"
        "- **AC-1:** Given a / When b / Then c\n"
        "  - Test: *(populated after TDD RED phase)*\n\n"
        "- **AC-2:** Given d / When e / Then f\n"
        "  - Test: *(populated after TDD RED phase)*\n"
    )
    points = parse_spec_expected_behavior(str(spec))
    assert len(points) == 2
    assert not any(p.strip().startswith("Test:") for p in points)


def test_both_sections_merged_additively(tmp_path):
    """AC-5: Koexistenz von Expected Behavior UND Acceptance Criteria wird additiv gemergt."""
    spec = tmp_path / "spec.md"
    spec.write_text(
        "## Expected Behavior\n\n"
        "- eb point one\n"
        "- eb point two\n\n"
        "## Acceptance Criteria\n\n"
        "- **AC-1:** Given a / When b / Then c\n\n"
        "- **AC-2:** Given d / When e / Then f\n"
    )
    points = parse_spec_expected_behavior(str(spec))
    assert len(points) == 4
    assert points[0] == "eb point one"
    assert points[1] == "eb point two"
    assert points[2].startswith("**AC-1:**")
    assert points[3].startswith("**AC-2:**")


def test_expected_behavior_only_format_no_regression(tmp_path):
    """AC-6: reines altes Expected-Behavior-Format bleibt unverändert (Regressionsschutz)."""
    spec = tmp_path / "spec.md"
    spec.write_text(
        "## Expected Behavior\n\n"
        "- first point\n"
        "- second point\n"
        "1. numbered point\n"
    )
    points = parse_spec_expected_behavior(str(spec))
    assert points == ["first point", "second point", "numbered point"]


def test_real_spec_qa_gate_path_resolution():
    """AC-7: Regressionscheck gegen echte Spec-Datei im Repo.

    Die Datei hat sowohl `## Expected Behavior` (3 Input/Output/Side-effects-
    Descriptor-Bullets, unveraendertes Bestandsverhalten, siehe AC-6) als auch
    `## Acceptance Criteria` (5 AC-Bullets) -- additiver Merge (AC-5) liefert
    daher mehr als nur die 5 ACs. Gezaehlt werden hier gezielt die AC-markierten
    Eintraege, nicht die Gesamtlaenge.
    """
    spec = REPO_ROOT / "docs" / "specs" / "qa-gate-path-resolution.md"
    points = parse_spec_expected_behavior(str(spec))
    ac_points = [p for p in points if p.startswith("**AC-")]
    assert len(ac_points) == 5
    assert ac_points[0].startswith("**AC-1:**")
    assert ac_points[4].startswith("**AC-5:**")


def test_empty_file_or_no_section_returns_empty_list(tmp_path):
    """Test 8 (Edge Case): keine der beiden Sections vorhanden -> leere Liste, kein Crash."""
    spec = tmp_path / "spec.md"
    spec.write_text("# Some Spec\n\nJust prose, no relevant sections.\n")
    points = parse_spec_expected_behavior(str(spec))
    assert points == []


def test_real_spec_bash_gate_false_positive_fix_parenthetical():
    """Test 9: echte Spec mit AC-8 wird korrekt aus der kanonischen Section erkannt.

    Section-Scoping stellt sicher, dass NUR der aktuelle AC-8 aus der echten
    `## Acceptance Criteria`-Section (Zeile 271, OHNE "präzisiert") gezählt wird
    -- der veraltete historische Eintrag `- **AC-8 (präzisiert):**` aus dem
    Abschnitt `## Fix-Loop Iteration 1` liegt ausserhalb der Section und wird
    korrekt NICHT mehr erfasst.
    """
    spec = REPO_ROOT / "docs" / "specs" / "bash-gate-false-positive-fix.md"
    points = parse_spec_expected_behavior(str(spec))
    assert len(points) > 0
    assert any("AC-8" in p for p in points)
    assert not any("präzisiert" in p for p in points)


def test_real_spec_resolve_execution_context_colon_outside_bold():
    """Test 11: echte Spec mit Label-Variante '- **AC-N**:' (Doppelpunkt ausserhalb Bold).

    `resolve-execution-context-consolidation.md` nutzt `- **AC-1**: GIVEN ...`
    -- Doppelpunkt liegt AUSSERHALB des Bold. Die `## Acceptance Criteria`-Section
    enthaelt genau 6 ACs (AC-1 bis AC-6).
    """
    spec = REPO_ROOT / "docs" / "specs" / "resolve-execution-context-consolidation.md"
    points = parse_spec_expected_behavior(str(spec))
    ac_points = [p for p in points if "AC-" in p]
    assert len(ac_points) == 6


def test_real_spec_retro_command_no_bold_label():
    """Test 12: echte Spec mit Label-Variante '- AC-N:' (ganz ohne Bold).

    `fast/retro-command.md` nutzt `- AC-1: text` ohne jegliches Bold-Markup.
    Die `## Acceptance Criteria`-Section enthaelt genau 6 ACs (AC-1 bis AC-6).
    """
    spec = REPO_ROOT / "docs" / "specs" / "fast" / "retro-command.md"
    points = parse_spec_expected_behavior(str(spec))
    ac_points = [p for p in points if "AC-" in p]
    assert len(ac_points) == 6


def test_real_spec_template_two_acs_no_test_sub_bullets():
    """Test 10: Template-Spec liefert genau 2 ACs, keine Test-Sub-Bullets als eigene Einträge.

    Die Vorlage hat zusaetzlich `## Expected Behavior` (3 Input/Output/Side-
    effects-Descriptor-Bullets, unveraendertes Bestandsverhalten) -- additiver
    Merge liefert daher mehr als nur die 2 ACs. Gezaehlt werden hier gezielt
    die AC-markierten Eintraege.
    """
    spec = REPO_ROOT / "templates" / "spec_template.md"
    points = parse_spec_expected_behavior(str(spec))
    ac_points = [p for p in points if p.startswith("**AC-")]
    assert len(ac_points) == 2
    assert ac_points[0].startswith("**AC-1:**")
    assert ac_points[1].startswith("**AC-2:**")
    assert not any(p.strip().startswith("Test:") for p in points)
