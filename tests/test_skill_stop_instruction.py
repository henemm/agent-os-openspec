"""Regressionstest, umgedreht (Issue #147, fix-147-validierung-abstufen).

Vorgeschichte (fix-140-po-decision-gates, Adversary-Finding F001): Seit
`skills/40-tdd-red/SKILL.md` per `disable-model-invocation: false` ueber das
Skill-Tool geladen werden kann, ist die SKILL.md auf dem Auto-Chaining-Pfad
das EINZIGE Dokument, das Claude beim Verlassen dieser Phase liest —
`core/commands/40-tdd-red.md` wird dabei nie gelesen. Diese Spec (#147)
schaltet denselben Selbstaufruf-Mechanismus jetzt zusaetzlich fuer
`skills/50-implement/SKILL.md` und `skills/60-validate/SKILL.md` frei
(`disable-model-invocation: false`). Damit kippt die Bedeutung der bisherigen
STOPP-Saetze ("NICHT selbst weitermachen, warte auf den vom User getippten
Slash-Befehl") um: Sie sind keine Absicherung mehr, sondern der einzige
verbliebene Blocker fuer genau die Automatisierung, die Issue #147 verlangt
(siehe docs/specs/fix-147-validierung-abstufen.md, ADR-0147). Dieser Test
prueft deshalb das Gegenteil vom Vorgaenger: dass die STOPP-Saetze weg sind
und durch eine Chaining-Anweisung ersetzt wurden, die Claude anweist, den
Folge-Skill selbst aufzurufen.

Was NICHT wegfaellt: Die technische Durchsetzung haengt laut ADR-0147 nie am
getippten Befehl. `tdd_enforcement.py` verlangt weiterhin registrierte
RED-Artefakte vor jedem Code-Edit in Phase 6, und `bash_gate.py` blockt
`git commit` weiterhin ohne VERIFIED-Adversary-Verdict — kein Hook wird durch
diese Spec veraendert. Die real gebliebene PO-Entscheidung (Adversary
VERIFIED/AMBIGUOUS-Klaerung + GREEN-Freigabe `go`) bleibt an eine explizite
User-Eingabe gebunden; nur der reine Tastendruck OHNE neue Entscheidung
danach entfaellt (siehe AC-5-Tests unten).

Reiner String-Praesenz- und Positions-Check (Stil wie
test_clear_checkpoint_blocks.py), damit auch ein teilweises Ausduennen
auffaellt.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

TDD_RED_SKILL = REPO_ROOT / "skills" / "40-tdd-red" / "SKILL.md"
TDD_RED_COMMAND = REPO_ROOT / "core" / "commands" / "40-tdd-red.md"
FIFTY_SKILL = REPO_ROOT / "skills" / "50-implement" / "SKILL.md"
FIFTY_COMMAND = REPO_ROOT / "core" / "commands" / "50-implement.md"

# Alte Wartebedingungen (fix-140-Stand) — muessen nach dieser Spec verschwunden sein.
OLD_STOP_TO_50_IMPLEMENT = (
    "**NICHT** selbst mit der Implementierung beginnen. "
    "Warte bis der User `/50-implement` tippt."
)
OLD_STOP_TO_60_VALIDATE = (
    "**NICHT** selbst mit der Validierung beginnen. "
    "Warte bis der User `/60-validate` tippt."
)

# Kernfragment der neuen Chaining-Anweisung. Wortlaut aus
# docs/specs/fix-147-validierung-abstufen.md, Implementation Details
# Abschnitt 2/3 — dieselbe Formulierung, die bereits produktiv in
# core/commands/30-write-spec.md / skills/30-write-spec/SKILL.md fuer den
# Uebergang approved -> /40-tdd-red steht ("Rufe den Skill `40-tdd-red`
# jetzt sofort selbst\nauf —", dort ueber einen Zeilenumbruch mitten im Satz
# gebrochen). `_normalize()` kollabiert deshalb Whitespace/Zeilenumbrueche,
# damit ein harmloser Zeilenumbruch an dieser Stelle den Test nicht bricht.
CHAIN_TO_50_IMPLEMENT = "Rufe den Skill `50-implement` jetzt sofort selbst auf"
CHAIN_TO_60_VALIDATE = "Rufe den Skill `60-validate` jetzt sofort selbst auf"


def _normalize(text: str) -> str:
    """Kollabiert jede Folge von Whitespace (inkl. Zeilenumbruch) zu einem Leerzeichen."""
    return " ".join(text.split())


def _line_index_containing(lines, fragment, name):
    for i, line in enumerate(lines):
        if fragment in line:
            return i
    raise AssertionError(f"{name}: Fragment '{fragment}' in keiner Zeile gefunden")


def _end_of_negative_block(lines, name):
    """Zeilenindex des schliessenden '---' des Ausgabe-B-Blocks.

    Eigene, schlanke Kopie der Fenced-Section-Logik aus
    test_clear_checkpoint_blocks.py — bewusst nicht importiert, damit beide
    Testdateien unabhaengig voneinander lauffaehig bleiben.
    """
    heading = "### Ausgabe B: Negativ-Block (mindestens eine Vorbedingung verletzt)"
    assert heading in lines, f"{name}: Ausgabe-B-Ueberschrift fehlt"
    start = lines.index(heading)
    seps = 0
    idx = start + 1
    while idx < len(lines):
        if lines[idx].strip() == "---":
            seps += 1
            if seps == 2:
                return idx
        idx += 1
    raise AssertionError(f"{name}: Ausgabe-B-Block ist nicht abgeschlossen")


# --- AC-3: Uebergang 40-tdd-red -> 50-implement --------------------------------

def test_tdd_red_skill_no_longer_forbids_self_starting_implementation():
    content = TDD_RED_SKILL.read_text()
    assert OLD_STOP_TO_50_IMPLEMENT not in content, (
        "skills/40-tdd-red/SKILL.md enthaelt noch die alte STOPP-Anweisung — "
        "AC-3 verlangt, dass sie durch die Chaining-Anweisung ersetzt wurde."
    )


def test_tdd_red_command_no_longer_forbids_self_starting_implementation():
    content = TDD_RED_COMMAND.read_text()
    assert OLD_STOP_TO_50_IMPLEMENT not in content, (
        "core/commands/40-tdd-red.md enthaelt noch die alte STOPP-Anweisung — "
        "AC-3 verlangt, dass sie durch die Chaining-Anweisung ersetzt wurde."
    )


def test_tdd_red_skill_contains_chaining_instruction_to_50_implement():
    content = _normalize(TDD_RED_SKILL.read_text())
    assert CHAIN_TO_50_IMPLEMENT in content, (
        "skills/40-tdd-red/SKILL.md fehlt die Chaining-Anweisung zum Selbstaufruf "
        "von 50-implement (AC-3)."
    )


def test_tdd_red_command_contains_chaining_instruction_to_50_implement():
    content = _normalize(TDD_RED_COMMAND.read_text())
    assert CHAIN_TO_50_IMPLEMENT in content, (
        "core/commands/40-tdd-red.md fehlt die Chaining-Anweisung zum Selbstaufruf "
        "von 50-implement (AC-3)."
    )


def test_chaining_instruction_to_50_implement_follows_phase_transition():
    """Positionslogik wie beim Vorgaenger-Test, umgekehrtes Vorzeichen.

    Geprueft wird bewusst NUR im Skill: Auf dem Skill-Tool-Pfad wird
    ausschliesslich skills/40-tdd-red/SKILL.md gelesen, nie
    core/commands/40-tdd-red.md (siehe Modul-Docstring) — nur dort muss die
    Chaining-Anweisung technisch wirksam NACH dem Phasenwechsel stehen.
    """
    content = TDD_RED_SKILL.read_text()
    phase_switch = content.find("$WF phase phase6_implement")
    chaining = content.find("Rufe den Skill `50-implement`")
    assert phase_switch != -1, "Phasenwechsel phase6_implement fehlt im Skill"
    assert chaining != -1, "Chaining-Anweisung zu 50-implement fehlt im Skill"
    assert chaining > phase_switch, (
        "Chaining-Anweisung steht vor dem Phasenwechsel — sie muss danach stehen, "
        "sonst greift sie, bevor der Phasenwechsel im State steht."
    )


def test_tdd_red_skill_and_command_chaining_are_identical():
    """Skill und Command duerfen im Chaining-Wortlaut nicht auseinanderlaufen."""
    assert CHAIN_TO_50_IMPLEMENT in _normalize(TDD_RED_COMMAND.read_text()), (
        "Wortlaut der Chaining-Anweisung in core/commands/40-tdd-red.md weicht ab."
    )
    assert CHAIN_TO_50_IMPLEMENT in _normalize(TDD_RED_SKILL.read_text()), (
        "skills/40-tdd-red/SKILL.md weicht vom Wortlaut in "
        "core/commands/40-tdd-red.md ab."
    )


def test_tdd_red_chaining_instruction_is_outside_clear_checkpoint_block():
    """AC-6: Die Chaining-Anweisung steht ausserhalb des /clear-Checkpoint-Blocks
    ('### Checkpoint pruefen' bis '### Ausgabe B: Negativ-Block ...'), damit
    test_clear_checkpoint_blocks.py strukturell unangetastet bleibt."""
    lines = TDD_RED_COMMAND.read_text().split("\n")
    name = "40-tdd-red.md"
    neg_end = _end_of_negative_block(lines, name)
    common_mistakes = _line_index_containing(lines, "## Common Mistakes", name)
    chaining_line = _line_index_containing(lines, "Rufe den Skill `50-implement`", name)
    assert neg_end < chaining_line < common_mistakes, (
        f"{name}: Chaining-Anweisung (Zeile {chaining_line}) muss zwischen dem "
        f"Ende des Ausgabe-B-Blocks (Zeile {neg_end}) und '## Common Mistakes' "
        f"(Zeile {common_mistakes}) stehen, also ausserhalb des "
        f"/clear-Checkpoint-Blocks."
    )


# --- AC-4: Uebergang 50-implement -> 60-validate -------------------------------

def test_fifty_implement_skill_no_longer_forbids_self_starting_validation():
    content = FIFTY_SKILL.read_text()
    assert OLD_STOP_TO_60_VALIDATE not in content, (
        "skills/50-implement/SKILL.md enthaelt noch die alte STOPP-Anweisung — "
        "AC-4 verlangt, dass sie durch die Chaining-Anweisung ersetzt wurde."
    )


def test_fifty_implement_command_no_longer_forbids_self_starting_validation():
    content = FIFTY_COMMAND.read_text()
    assert OLD_STOP_TO_60_VALIDATE not in content, (
        "core/commands/50-implement.md enthaelt noch die alte STOPP-Anweisung — "
        "AC-4 verlangt, dass sie durch die Chaining-Anweisung ersetzt wurde."
    )


def test_fifty_implement_skill_contains_chaining_instruction_to_60_validate():
    content = _normalize(FIFTY_SKILL.read_text())
    assert CHAIN_TO_60_VALIDATE in content, (
        "skills/50-implement/SKILL.md fehlt die Chaining-Anweisung zum "
        "Selbstaufruf von 60-validate (AC-4)."
    )


def test_fifty_implement_command_contains_chaining_instruction_to_60_validate():
    content = _normalize(FIFTY_COMMAND.read_text())
    assert CHAIN_TO_60_VALIDATE in content, (
        "core/commands/50-implement.md fehlt die Chaining-Anweisung zum "
        "Selbstaufruf von 60-validate (AC-4)."
    )


def test_chaining_instruction_to_60_validate_follows_phase_transition():
    """Nur im Skill relevant — s. Docstring von
    test_chaining_instruction_to_50_implement_follows_phase_transition."""
    content = FIFTY_SKILL.read_text()
    phase_switch = content.find("$WF phase phase7_validate")
    chaining = content.find("Rufe den Skill `60-validate`")
    assert phase_switch != -1, "Phasenwechsel phase7_validate fehlt im Skill"
    assert chaining != -1, "Chaining-Anweisung zu 60-validate fehlt im Skill"
    assert chaining > phase_switch, (
        "Chaining-Anweisung steht vor dem Phasenwechsel — sie muss danach stehen, "
        "sonst greift sie, bevor der Phasenwechsel im State steht."
    )


def test_fifty_implement_skill_and_command_chaining_are_identical():
    assert CHAIN_TO_60_VALIDATE in _normalize(FIFTY_COMMAND.read_text()), (
        "Wortlaut der Chaining-Anweisung in core/commands/50-implement.md weicht ab."
    )
    assert CHAIN_TO_60_VALIDATE in _normalize(FIFTY_SKILL.read_text()), (
        "skills/50-implement/SKILL.md weicht vom Wortlaut in "
        "core/commands/50-implement.md ab."
    )


def test_fifty_implement_chaining_instruction_is_outside_clear_checkpoint_block():
    """AC-6, analog zu test_tdd_red_chaining_instruction_is_outside_clear_checkpoint_block."""
    lines = FIFTY_COMMAND.read_text().split("\n")
    name = "50-implement.md"
    neg_end = _end_of_negative_block(lines, name)
    common_mistakes = _line_index_containing(lines, "## Common Mistakes", name)
    chaining_line = _line_index_containing(lines, "Rufe den Skill `60-validate`", name)
    assert neg_end < chaining_line < common_mistakes, (
        f"{name}: Chaining-Anweisung (Zeile {chaining_line}) muss zwischen dem "
        f"Ende des Ausgabe-B-Blocks (Zeile {neg_end}) und '## Common Mistakes' "
        f"(Zeile {common_mistakes}) stehen, also ausserhalb des "
        f"/clear-Checkpoint-Blocks."
    )


# --- AC-5 (Regressionsschutz — JETZT SCHON GRUEN, muss es bleiben) -------------
#
# Diese zwei Tests pruefen NUR die relative Reihenfolge fester Ueberschriften
# (Step 6 / "## Next Step" / die Adversary-VERIFIED-Vorbedingung / "## Common
# Mistakes"), nicht den Wortlaut der Chaining-Anweisung selbst. Dadurch sind
# sie bereits VOR der Implementierung gruen (die Reihenfolge existiert schon
# heute mit der alten STOPP-Anweisung an derselben Stelle) und bleiben es
# nach dem Textumbau, ohne dass jemand hier den neuen Wortlaut nachpflegen
# muesste. Genau das macht sie zu einem Regressionsschutz statt einem
# weiteren RED-Test: faellt beim Ausduennen der STOPP-Saetze versehentlich
# die Vorbedingung (Adversary VERIFIED / GREEN-Freigabe "go") mit weg oder
# rutscht sie hinter die Chaining-Anweisung, schlagen sie an.

def test_fifty_implement_command_precondition_precedes_chaining_section():
    content = FIFTY_COMMAND.read_text()
    step6 = content.find("### Step 6: User-Freigabe der GREEN-Ergebnisse")
    next_step = content.find("## Next Step")
    verified = content.find("Wenn Adversary VERIFIED")
    common_mistakes = content.find("## Common Mistakes")
    assert -1 not in (step6, next_step, verified, common_mistakes), (
        "core/commands/50-implement.md: eine der erwarteten festen Ueberschriften/"
        "Saetze fehlt (Step 6 / ## Next Step / 'Wenn Adversary VERIFIED' / "
        "## Common Mistakes)."
    )
    assert step6 < next_step < verified < common_mistakes, (
        "core/commands/50-implement.md: Die Vorbedingung (GREEN-Freigabe 'go' in "
        "Step 6, Adversary-VERIFIED-Hinweis in '## Next Step') muss vor dem Ende "
        "des Next-Step-Abschnitts stehen — sonst waere der Selbstaufruf ungesichert."
    )


def test_fifty_implement_skill_precondition_precedes_chaining_section():
    content = FIFTY_SKILL.read_text()
    step6 = content.find("### Step 6: User-Freigabe der GREEN-Ergebnisse")
    next_step = content.find("## Next Step")
    verified = content.find("Wenn Adversary VERIFIED")
    common_mistakes = content.find("## Common Mistakes")
    assert -1 not in (step6, next_step, verified, common_mistakes), (
        "skills/50-implement/SKILL.md: eine der erwarteten festen Ueberschriften/"
        "Saetze fehlt (Step 6 / ## Next Step / 'Wenn Adversary VERIFIED' / "
        "## Common Mistakes)."
    )
    assert step6 < next_step < verified < common_mistakes, (
        "skills/50-implement/SKILL.md: Die Vorbedingung (GREEN-Freigabe 'go' in "
        "Step 6, Adversary-VERIFIED-Hinweis in '## Next Step') muss vor dem Ende "
        "des Next-Step-Abschnitts stehen — sonst waere der Selbstaufruf ungesichert."
    )
