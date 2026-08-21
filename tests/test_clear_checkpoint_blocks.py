"""Tests für die /clear-Checkpoint-Blöcke in core/commands (Issue #107).

Die fünf Phasen-Commands müssen statt der pauschalen Behauptung
"der Workflow-State liegt sicher auf der Platte" einen Checkpoint mit
Sicherungsliste und zwei Verdikt-Varianten (✅ / ⚠️) enthalten.
`60-validate.md` bekommt bewusst keinen Checkpoint (Commit folgt in
derselben Sitzung).

Der Checkpoint besteht aus drei Abschnitten mit fester Reihenfolge:

1. `### Checkpoint prüfen (Anweisung an dich — nicht ausgeben)` — die
   Vorbedingungs-Prüfung. Reine Instruktion, geht NICHT an den User.
2. `### Ausgabe A: Positiv-Block …` — wörtliche Ausgabe bei erfüllten
   Vorbedingungen.
3. `### Ausgabe B: Negativ-Block …` — wörtliche Ausgabe sonst.

Die Ausgabe-Abschnitte enthalten ausschließlich Text, den der User sehen
soll; Meta-Anweisungen stehen ausnahmslos im Instruktions-Abschnitt.
"""

import re

import pytest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
COMMANDS_DIR = REPO_ROOT / "core" / "commands"

CHECKPOINT_FILES = [
    "10-context.md",
    "20-analyse.md",
    "30-write-spec.md",
    "40-tdd-red.md",
    "50-implement.md",
]

NO_CHECKPOINT_FILE = "60-validate.md"

SAVED_MARKER = "**Gesichert auf der Platte:**"
POSITIVE_MARKER = "✅ **`/clear` ist jetzt gefahrlos**"
NEGATIVE_MARKER = "⚠️ **`/clear` jetzt NICHT**"
LEGACY_MARKERS = [
    "liegt sicher auf der Platte",
    "Bei kleinem Kontext optional",
]

INSTRUCTION_HEADING = "### Checkpoint prüfen (Anweisung an dich — nicht ausgeben)"
POSITIVE_HEADING = "### Ausgabe A: Positiv-Block (alle Vorbedingungen erfüllt)"
NEGATIVE_HEADING = "### Ausgabe B: Negativ-Block (mindestens eine Vorbedingung verletzt)"

# Der jeweils naechste Schritt, auf den sich der Checkpoint bezieht.
FOLLOW_COMMAND = dict(
    [
        ("10-context.md", "/20-analyse"),
        ("20-analyse.md", "/30-write-spec"),
        ("30-write-spec.md", "/40-tdd-red"),
        ("40-tdd-red.md", "/50-implement"),
        ("50-implement.md", "/60-validate"),
    ]
)

# Phasen 1-3 committen nichts und registrieren keine RED-Artefakte — dort wären
# beide Vorbedingungen tot bzw. dauerhaft verletzt (die Ergebnisdatei der Phase
# ist per Definition uncommitted und wird vom Folgeschritt gebraucht).
EARLY_PHASE_FILES = ["10-context.md", "20-analyse.md", "30-write-spec.md"]
LATE_PHASE_FILES = ["40-tdd-red.md", "50-implement.md"]

# So kündigt eine Command-Datei einen Phasenwechsel an.
PHASE_TRANSITION_RE = re.compile(
    r"workflow\.py phase (phase\w+)|State advances to `(phase\w+)`"
)
STATE_FILE_PHASE_RE = re.compile(
    r"`\.claude/workflows/<name>\.json` — Phase `(phase\w+)`"
)


def _read(name):
    path = COMMANDS_DIR / name
    assert path.exists(), f"Command-Datei fehlt: {path}"
    return path.read_text(encoding="utf-8")


def _heading_index(lines, heading, name):
    assert heading in lines, f"{name}: Abschnitt '{heading}' fehlt"
    return lines.index(heading)


def _section_until_next_heading(lines, start):
    end = start + 1
    while end < len(lines) and not lines[end].startswith("#"):
        end += 1
    return lines[start:end]


def _fenced_section(lines, start, name):
    """Abschnitt vom `###`-Titel bis einschließlich des zweiten `---`-Trenners."""
    end = start + 1
    seps = 0
    while end < len(lines):
        if lines[end].strip() == "---":
            seps += 1
            if seps == 2:
                return lines[start:end + 1]
        end += 1
    raise AssertionError(
        f"{name}: Ausgabe-Block ab '{lines[start]}' ist nicht abgeschlossen"
    )


def _checkpoint_sections(name):
    """Liefert (Instruktion, Positiv-Block, Negativ-Block) als Zeilenlisten."""
    lines = _read(name).split("\n")
    i_instr = _heading_index(lines, INSTRUCTION_HEADING, name)
    i_pos = _heading_index(lines, POSITIVE_HEADING, name)
    i_neg = _heading_index(lines, NEGATIVE_HEADING, name)
    return (
        _section_until_next_heading(lines, i_instr),
        _fenced_section(lines, i_pos, name),
        _fenced_section(lines, i_neg, name),
    )


def _skeleton(section_lines):
    """Struktur-Gerüst: ohne Leerzeilen, ohne Aufzählungspunkte, ohne Command-Namen."""
    skeleton = []
    for line in section_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("- "):
            continue
        skeleton.append(re.sub(r"/\d\d-[a-z-]+", "/<FOLGE>", line.rstrip()))
    return skeleton


@pytest.mark.parametrize("name", CHECKPOINT_FILES)
def test_exactly_one_saved_block(name):
    """AC-1: Jede Zieldatei enthält genau einen 'Gesichert auf der Platte'-Block."""
    content = _read(name)
    assert content.count(SAVED_MARKER) == 1, (
        f"{name}: erwartet genau 1x '{SAVED_MARKER}', "
        f"gefunden {content.count(SAVED_MARKER)}x"
    )


@pytest.mark.parametrize("name", CHECKPOINT_FILES)
def test_both_verdict_variants_present(name):
    """AC-1/AC-2: Positiv- und Negativ-Verdikt stehen in jeder Zieldatei."""
    content = _read(name)
    assert POSITIVE_MARKER in content, f"{name}: Positiv-Verdikt fehlt"
    assert NEGATIVE_MARKER in content, f"{name}: Negativ-Verdikt fehlt"


@pytest.mark.parametrize("name", CHECKPOINT_FILES)
def test_no_legacy_formulations(name):
    """AC-3: Die Alt-Formulierungen sind restlos entfernt."""
    content = _read(name)
    for marker in LEGACY_MARKERS:
        assert marker not in content, (
            f"{name}: Alt-Formulierung '{marker}' noch vorhanden"
        )


def test_validate_command_has_no_checkpoint():
    """60-validate.md bekommt keinen Checkpoint — Commit folgt in derselben Sitzung."""
    content = _read(NO_CHECKPOINT_FILE)
    for marker in (SAVED_MARKER, POSITIVE_MARKER, NEGATIVE_MARKER):
        assert marker not in content, (
            f"{NO_CHECKPOINT_FILE}: Checkpoint-Marker '{marker}' darf hier nicht stehen"
        )


@pytest.mark.parametrize("name", CHECKPOINT_FILES)
def test_instruction_section_precedes_output_sections(name):
    """AC-2: Erst die Prüf-Anweisung, dann die beiden Ausgabe-Vorlagen."""
    lines = _read(name).split("\n")
    i_instr = _heading_index(lines, INSTRUCTION_HEADING, name)
    i_pos = _heading_index(lines, POSITIVE_HEADING, name)
    i_neg = _heading_index(lines, NEGATIVE_HEADING, name)
    assert i_instr < i_pos < i_neg, (
        f"{name}: Reihenfolge muss Instruktion, Positiv-Block, Negativ-Block sein, "
        f"ist aber {i_instr} / {i_pos} / {i_neg}"
    )


@pytest.mark.parametrize("name", CHECKPOINT_FILES)
def test_preconditions_listed_in_instruction_section(name):
    """AC-2: Die Vorbedingungs-Prüfung steht vollständig im Instruktions-Abschnitt."""
    instruction = "\n".join(_checkpoint_sections(name)[0])
    follow = FOLLOW_COMMAND[name]
    expected = [
        "- Phase im Workflow-State geschrieben — "
        "`python3 .claude/hooks/workflow.py status` bestätigt sie",
        "- Alle Ergebnisdateien dieser Phase liegen auf der Platte",
        f"- Keine Erkenntnis, die für `{follow}` nötig und nirgends niedergeschrieben ist",
    ]
    for bullet in expected:
        assert bullet in instruction, f"{name}: Vorbedingung fehlt: {bullet}"
    assert "Sind alle Punkte erfüllt:" in instruction, (
        f"{name}: Entscheidungsregel Positiv-/Negativ-Block fehlt"
    )


@pytest.mark.parametrize("name", CHECKPOINT_FILES)
def test_output_sections_contain_no_meta_instructions(name):
    """Die wörtlich auszugebenden Blöcke enthalten keine Anweisungen an Claude."""
    _, positive, negative = _checkpoint_sections(name)
    forbidden = [
        "Anweisung an dich",
        "Vorbedingungen prüfen",
        "Positiv-Block",
        "Negativ-Block",
        "bevor du unten etwas ausgibst",
        "Gib den",
        "###",
    ]
    blocks = ((positive[1:], "Positiv-Block"), (negative[1:], "Negativ-Block"))
    for section, label in blocks:
        body = "\n".join(section)
        for phrase in forbidden:
            assert phrase not in body, (
                f"{name}: Meta-Anweisung '{phrase}' steht im {label}, "
                f"der wörtlich an den User geht"
            )


@pytest.mark.parametrize("name", EARLY_PHASE_FILES)
def test_no_commit_precondition_in_early_phases(name):
    """Phasen 1-3 committen nichts — eine Commit-Vorbedingung wäre immer verletzt."""
    instruction = "\n".join(_checkpoint_sections(name)[0])
    assert "uncommitteten" not in instruction, (
        f"{name}: Commit-Vorbedingung ist hier immer verletzt (die Ergebnisdatei der "
        f"Phase ist per Definition uncommitted und wird vom Folgeschritt gebraucht) — "
        f"sie darf nicht in der Prüfliste stehen"
    )


@pytest.mark.parametrize("name", LATE_PHASE_FILES)
def test_commit_precondition_kept_in_late_phases(name):
    """Ab Phase 5 wird tatsächlich committed — dort bleibt die Vorbedingung stehen."""
    instruction = "\n".join(_checkpoint_sections(name)[0])
    follow = FOLLOW_COMMAND[name]
    expected = (
        f"- Keine uncommitteten Änderungen an Dateien, die `{follow}` braucht"
    )
    assert expected in instruction, f"{name}: Commit-Vorbedingung fehlt"


@pytest.mark.parametrize("name", EARLY_PHASE_FILES)
def test_no_red_artifact_precondition_in_early_phases(name):
    """RED-Artefakte gibt es erst ab Phase 5 — in Phase 1-3 ist der Punkt toter Text."""
    instruction = "\n".join(_checkpoint_sections(name)[0])
    assert "add-artifact" not in instruction, (
        f"{name}: RED-Artefakt-Vorbedingung trifft in dieser Phase nie zu"
    )


@pytest.mark.parametrize("name", CHECKPOINT_FILES)
def test_positive_block_phase_matches_declared_transition(name):
    """Die im Positiv-Block genannte Phase ist die, in die dieselbe Datei wechselt."""
    content = _read(name)
    match = STATE_FILE_PHASE_RE.search(content)
    assert match, f"{name}: Positiv-Block nennt keine Phase im Workflow-State"
    claimed = match.group(1)

    transitions = [
        m.group(1) or m.group(2)
        for m in PHASE_TRANSITION_RE.finditer(content)
        if m.start() < match.start()
    ]
    assert transitions, (
        f"{name}: Datei deklariert vor dem Checkpoint keinen Phasenwechsel"
    )
    assert claimed == transitions[-1], (
        f"{name}: Positiv-Block behauptet Phase '{claimed}', die Datei setzt aber "
        f"zuletzt '{transitions[-1]}'"
    )


def test_checkpoint_structure_identical_across_files():
    """AC-3: Der Checkpoint ist in allen fünf Dateien strukturgleich aufgebaut.

    Verglichen wird das Gerüst aus Überschriften, Trennern und feststehenden
    Sätzen. Die phasenspezifischen Aufzählungen (Vorbedingungen, Sicherungsliste)
    und der Name des Folge-Befehls sind ausgenommen — nur sie dürfen abweichen.
    """
    reference_name = CHECKPOINT_FILES[0]
    reference = [_skeleton(part) for part in _checkpoint_sections(reference_name)]
    labels = ("Instruktion", "Positiv-Block", "Negativ-Block")

    for name in CHECKPOINT_FILES[1:]:
        current = [_skeleton(part) for part in _checkpoint_sections(name)]
        for expected, actual, label in zip(reference, current, labels):
            assert actual == expected, (
                f"{name}: {label} weicht strukturell von {reference_name} ab\n"
                f"erwartet: {expected}\ngefunden: {actual}"
            )
