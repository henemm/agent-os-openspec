"""Issue #606: 'Code reference:' mit Leerzeichen im Pfad.

`_CODE_REF_RE` las bisher nur das erste Nicht-Leerzeichen-Token. Ein Pfad wie
`Meditationstimer iOS/CalendarView.swift:127` wurde bei `Meditationstimer`
abgeschnitten, `stamp` übersprang die Datei, und der Wechsel nach
phase7_validate blockierte mit „nicht zitiert und gehasht“.

Die Tests decken den Pfad mit Leerzeichen (mit Zeilenangabe, in Backticks)
ab und halten fest, dass nachfolgender Text in realen Artefakten
(` — Erklärung`, ` (Funktion)`, `, weitere/datei:12`, `;`) nicht zum Pfad wird.
"""

import hashlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "core" / "hooks"))

from adversary_dialog import (  # noqa: E402
    MIN_ROUNDS,
    _extract_examined_files,
    stamp_dialog_artifact,
    validate_dialog_artifact_ex,
)

ROUNDS = "".join(
    f"### Runde {i}\n**Adversary:** Angriff {i}\n**Implementierer:** Beweis {i}\n\n"
    for i in range(1, MIN_ROUNDS + 1)
)


def _artifact(tmp_path: Path, ref_line: str) -> Path:
    p = tmp_path / "adversary-dialog.md"
    p.write_text(
        "# Adversary Dialog — fix-606\nSpec: docs/specs/x.md\n\n"
        "Confirmation:\n  AC: AC-1\n"
        f"  Code reference: {ref_line}\n"
        "  Status: CONFIRMED\n\n" + ROUNDS + "## Verdict\n**VERIFIED**\n"
    )
    return p


def _spaced_file(tmp_path: Path) -> Path:
    target = tmp_path / "Meditationstimer iOS" / "CalendarView.swift"
    target.parent.mkdir(parents=True)
    target.write_text("struct CalendarView {}\n")
    return target


def _assert_stamped(tmp_path: Path, art: Path, target: Path) -> None:
    ok, msg = stamp_dialog_artifact(str(art))
    assert ok is True, msg
    assert "Uebersprungen" not in msg, msg
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    assert f"sha256:{digest}  {target}" in art.read_text()
    ok, reason = validate_dialog_artifact_ex(str(art))[:2]
    assert ok is True, reason


def test_stamp_hashes_path_with_space_and_line(tmp_path):
    target = _spaced_file(tmp_path)
    _assert_stamped(tmp_path, _artifact(tmp_path, f"{target}:127"), target)


def test_stamp_hashes_backticked_path_with_space(tmp_path):
    target = _spaced_file(tmp_path)
    _assert_stamped(tmp_path, _artifact(tmp_path, f"`{target}:127`"), target)


def test_backticked_path_with_space_without_line_and_trailing_text():
    scan = "  Code reference: `Meditationstimer iOS/CalendarView.swift` — Erklärung\n"
    assert _extract_examined_files(scan) == ["Meditationstimer iOS/CalendarView.swift"]


def test_relative_path_with_space_and_range():
    scan = "Code reference: Meditationstimer iOS/CalendarView.swift:127-130\n"
    assert _extract_examined_files(scan) == ["Meditationstimer iOS/CalendarView.swift"]


def test_trailing_text_after_path_is_not_part_of_path():
    scan = "".join(f"  Code reference: {ref}\n" for ref in (
        "Shared/Services/CalendarSync.swift:84 — `sourceOrder` filtert auf `.calDAV`",
        "scripts/sim.sh:194-198 (cmd_unit)",
        "LooseEndsUITests/Walkthrough.swift:61-66, Shared/Models/ViewRules.swift:17",
        "scripts/sim.sh:278 und scripts/sim.sh:300",
        "tests/helpers/orakel.py:574-622; dazu mehr",
        "scripts/tests/device-test.sh (nicht vorhanden)",
        "src/plain.py:12",
        "unknown — cannot determine without source access",
    ))
    assert _extract_examined_files(scan) == sorted({
        "LooseEndsUITests/Walkthrough.swift",
        "Shared/Services/CalendarSync.swift",
        "scripts/sim.sh",
        "scripts/tests/device-test.sh",
        "src/plain.py",
        "tests/helpers/orakel.py",
        "unknown",
    })
