"""Regressionstest (fix-140-po-decision-gates, Adversary-Finding F001).

Seit `skills/40-tdd-red/SKILL.md` per `disable-model-invocation: false` auch
ueber das Skill-Tool geladen werden kann, ist diese Datei auf dem
Auto-Chaining-Pfad das EINZIGE Dokument, das Claude am Ende der RED-Phase
liest — `core/commands/40-tdd-red.md` wird dabei nie gelesen.

Die STOPP-Anweisung ("nicht selbst implementieren, auf `/50-implement` warten")
muss daher auch im Skill stehen. Faellt sie weg, gibt es keine textuelle
Absicherung mehr gegen unbeaufsichtigtes Weiterschreiben von Code, sobald
`current_phase == phase6_implement` gesetzt ist: der Phase-Gate in
`edit_gate.py` prueft nur den Zustand, nicht ob der User `/50-implement`
tatsaechlich getippt hat.

Reiner String-Praesenz-Check (Stil wie test_clear_checkpoint_blocks.py).
Die beiden Haelften der Anweisung werden bewusst einzeln geprueft, damit auch
ein teilweises Ausduennen auffaellt.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TDD_RED_SKILL = REPO_ROOT / "skills" / "40-tdd-red" / "SKILL.md"
TDD_RED_COMMAND = REPO_ROOT / "core" / "commands" / "40-tdd-red.md"

STOP_INSTRUCTION = (
    "**NICHT** selbst mit der Implementierung beginnen. "
    "Warte bis der User `/50-implement` tippt."
)


def test_skill_forbids_self_starting_implementation():
    """Haelfte 1: Claude darf nicht von sich aus implementieren."""
    content = TDD_RED_SKILL.read_text()
    assert "**NICHT** selbst mit der Implementierung beginnen" in content, (
        "skills/40-tdd-red/SKILL.md fehlt das Implementierungs-Verbot — auf dem "
        "Skill-Tool-Pfad gibt es dann keine STOPP-Anweisung mehr."
    )


def test_skill_requires_waiting_for_implement_command():
    """Haelfte 2: Gewartet wird auf den vom User getippten /50-implement."""
    content = TDD_RED_SKILL.read_text()
    assert "Warte bis der User `/50-implement` tippt" in content, (
        "skills/40-tdd-red/SKILL.md fehlt die Wartebedingung auf den vom User "
        "getippten `/50-implement`."
    )


def test_skill_stop_instruction_follows_phase_transition():
    """Die STOPP-Anweisung muss NACH dem Phasenwechsel stehen, sonst wirkungslos."""
    content = TDD_RED_SKILL.read_text()
    phase_switch = content.find("$WF phase phase6_implement")
    stop = content.find("**NICHT** selbst mit der Implementierung beginnen")
    assert phase_switch != -1, "Phasenwechsel phase6_implement fehlt im Skill"
    assert stop != -1, "STOPP-Anweisung fehlt im Skill"
    assert stop > phase_switch, (
        "STOPP-Anweisung steht vor dem Phasenwechsel — sie muss direkt danach "
        "kommen, damit sie den Uebergang zu /50-implement absichert."
    )


def test_skill_and_command_instruction_are_identical():
    """Skill und Command duerfen inhaltlich nicht auseinanderlaufen."""
    assert STOP_INSTRUCTION in TDD_RED_COMMAND.read_text(), (
        "Wortlaut in core/commands/40-tdd-red.md hat sich geaendert — "
        "Skill und Command muessen konsistent bleiben."
    )
    assert STOP_INSTRUCTION in TDD_RED_SKILL.read_text(), (
        "skills/40-tdd-red/SKILL.md weicht vom Wortlaut in "
        "core/commands/40-tdd-red.md ab."
    )
