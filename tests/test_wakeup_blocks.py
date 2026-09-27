"""Tests für die Weckruf-Reduktion (Issue #88, Spec feat-88-wakeup-blocks).

Vor dieser Änderung schreiben vier Befehlsdateien (`20-analyse`,
`30-write-spec`, `50-implement`, `60-validate`) je 3-4 eigene
"TIMEOUT-PFLICHT — sofort nach dem Spawn"-Blöcke mit `ScheduleWakeup(...)`-
Aufrufen vor, mit Intervallen zwischen 180 und 600 s. Das widerspricht der
Werkzeugbeschreibung von `ScheduleWakeup`: die Sitzung wird bei Fertigstellung
des überwachten Agenten ohnehin automatisch erneut aufgerufen, ein kurzer
Weckruf dazwischen kommt regelmäßig zu spät (Befund F9 der Analyse: 144 s
Rücklauf gegen einen vorgeschriebenen 300-s-Weckruf, der nie griff). Eine
PFLICHT, die strukturell nie greift, untergräbt die Verbindlichkeit der
übrigen Pflichtschritte derselben Datei. Kein Test schützte diese Stellen
bisher (Suche nach `ScheduleWakeup` in `tests/` lieferte vor dieser Datei
kein Ergebnis).

Ohne diese Tests könnte künftig wieder pro Spawn ein eigener Weckruf mit zu
kurzem Intervall eingeführt werden, oder der Ersatz-Absatz (primärer Schutz
über den automatischen Wiederaufruf plus `TaskList`/`TaskStop`-Nachfassen)
könnte ersatzlos verschwinden, ohne dass etwas rot wird.

Stil: reine String-/Regex-Präsenz-Checks über `pathlib.Path`, keine
Fixtures, kein Mocking — identisch zu `tests/test_skill_stop_instruction.py`
und `tests/test_clear_checkpoint_blocks.py`.
"""

import re
import sys

import pytest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
COMMANDS_DIR = REPO_ROOT / "core" / "commands"
SKILLS_DIR = REPO_ROOT / "skills"

WAKEUP_CALL = "ScheduleWakeup("
TIMEOUT_PFLICHT_MARKER = "TIMEOUT-PFLICHT"
MIN_INTERVAL_SECONDS = 1200

# Die drei Bausteine des Ersatz-Absatzes aus der Spec (Teil A, Abschnitt 1).
# Die Umsetzungsphase MUSS genau diese Wendungen übernehmen, nicht sinngemäße
# Umformulierungen — sonst wird dieser Test wirkungslos.
REPLACEMENT_MARKERS = {
    "auto_recall": "automatisch erneut aufgerufen",
    "task_list": "TaskList",
    "task_stop": "TaskStop",
}

# Nur diese vier Befehlsdateien sind heute von den TIMEOUT-PFLICHT-Blöcken
# betroffen und müssen deshalb den Ersatz-Absatz wortgleich enthalten
# (AC-4). Die Glob-Prüfungen für AC-1 bis AC-3 laufen dagegen bewusst über
# ALLE Dateien unter core/commands/*.md und skills/*/SKILL.md — siehe
# "## Known Limitations" der Spec: ein künftiger fünfter Befehl mit eigenen
# Weckruf-Blöcken soll nicht durch eine hartkodierte Liste durchrutschen.
REPLACEMENT_PARAGRAPH_FILES = [
    "20-analyse.md",
    "30-write-spec.md",
    "50-implement.md",
    "60-validate.md",
]

# Regex fürs erste Zahlen-Argument eines ScheduleWakeup(...)-Aufrufs.
WAKEUP_INTERVAL_RE = re.compile(r"ScheduleWakeup\(\s*(\d+)")

ALL_COMMAND_AND_SKILL_FILES = sorted(COMMANDS_DIR.glob("*.md")) + sorted(
    SKILLS_DIR.glob("*/SKILL.md")
)

# Für die Test-IDs lesbare relative Pfade statt absoluter Pfade.
ALL_COMMAND_AND_SKILL_IDS = [
    str(path.relative_to(REPO_ROOT)) for path in ALL_COMMAND_AND_SKILL_FILES
]


@pytest.mark.parametrize(
    "path", ALL_COMMAND_AND_SKILL_FILES, ids=ALL_COMMAND_AND_SKILL_IDS
)
def test_at_most_one_wakeup_call_per_file(path):
    """AC-1: Höchstens ein `ScheduleWakeup(`-Vorkommen je Datei.

    Vor der Umsetzung stehen in den vier betroffenen Befehlsdateien (und den
    daraus generierten Skills) 3-4 Vorkommen je Datei — dieser Test muss
    also heute fehlschlagen.
    """
    content = path.read_text(encoding="utf-8")
    count = content.count(WAKEUP_CALL)
    assert count <= 1, (
        f"{path.relative_to(REPO_ROOT)}: {count}x '{WAKEUP_CALL}' gefunden, "
        f"erlaubt ist höchstens 1 Vorkommen je Datei — die restlichen "
        f"TIMEOUT-PFLICHT-Blöcke müssen zu einem einzigen '### Hängende "
        f"Subagenten'-Abschnitt zusammengefasst werden."
    )


@pytest.mark.parametrize(
    "path", ALL_COMMAND_AND_SKILL_FILES, ids=ALL_COMMAND_AND_SKILL_IDS
)
def test_wakeup_interval_is_at_least_1200_seconds(path):
    """AC-2: Jedes `ScheduleWakeup(...)`-Zahlen-Argument in der Datei muss
    mindestens 1200 (Sekunden) betragen.

    Die Spec formuliert AC-2 für den Zielzustand ("ist genau ein Vorkommen
    vorhanden") — geprüft wird hier bewusst jedes einzelne per Regex
    gefundene Vorkommen, nicht nur der Fall mit genau einem Treffer. Das
    deckt denselben Zielzustand ab (dort gibt es ohnehin nur noch einen
    Treffer je Datei) und macht den Test zusätzlich schon HEUTE aussage-
    kräftig: vor der Umsetzung liegen alle Intervalle zwischen 180 und 600,
    also unterhalb der Grenze — der Test muss deshalb schon jetzt für jede
    betroffene Datei fehlschlagen, nicht erst nach AC-1.
    """
    content = path.read_text(encoding="utf-8")
    intervals = WAKEUP_INTERVAL_RE.findall(content)
    if not intervals:
        pytest.skip(
            f"{path.relative_to(REPO_ROOT)}: kein ScheduleWakeup(-Vorkommen, "
            f"AC-2 hat hier nichts zu prüfen"
        )
    for raw_value in intervals:
        interval = int(raw_value)
        assert interval >= MIN_INTERVAL_SECONDS, (
            f"{path.relative_to(REPO_ROOT)}: ScheduleWakeup-Intervall ist "
            f"{interval}, erwartet ≥ {MIN_INTERVAL_SECONDS} — ein kurzer "
            f"Weckruf kommt regelmäßig zu spät, weil die Sitzung ohnehin "
            f"automatisch erneut aufgerufen wird, sobald der Hintergrund-"
            f"Agent fertig ist."
        )


@pytest.mark.parametrize(
    "path", ALL_COMMAND_AND_SKILL_FILES, ids=ALL_COMMAND_AND_SKILL_IDS
)
def test_timeout_pflicht_marker_removed(path):
    """AC-3: Das Literal `TIMEOUT-PFLICHT` kommt in keiner Datei mehr vor.

    Vor der Umsetzung steht der Marker in allen vier betroffenen
    Befehlsdateien (und ihren generierten Skills) mehrfach — dieser Test
    muss dort heute fehlschlagen.
    """
    content = path.read_text(encoding="utf-8")
    assert TIMEOUT_PFLICHT_MARKER not in content, (
        f"{path.relative_to(REPO_ROOT)}: enthält noch das Literal "
        f"'{TIMEOUT_PFLICHT_MARKER}' — muss durch den Ersatz-Absatz "
        f"('### Hängende Subagenten') ersetzt werden."
    )


@pytest.mark.parametrize("name", REPLACEMENT_PARAGRAPH_FILES)
def test_replacement_paragraph_mentions_automatic_recall(name):
    """AC-4 (Baustein 1/3): Beleg, dass der gestrichene Pflichtblock nicht
    ersatzlos wegfällt — der Ersatz-Absatz benennt den automatischen
    Wiederaufruf der Sitzung als primären Schutzmechanismus.

    Fehlt dieser Baustein allein, ist der Ersatz-Absatz nur teilweise
    ausgedünnt worden — deshalb wird er einzeln geprüft (wie die zwei
    Hälften in test_skill_stop_instruction.py).
    """
    content = (COMMANDS_DIR / name).read_text(encoding="utf-8")
    assert REPLACEMENT_MARKERS["auto_recall"] in content, (
        f"{name}: Ersatz-Absatz fehlt der Baustein "
        f"'{REPLACEMENT_MARKERS['auto_recall']}' — ohne ihn ist nicht mehr "
        f"belegt, dass der automatische Wiederaufruf als primärer Schutz "
        f"gegen hängende Subagenten benannt wird."
    )


@pytest.mark.parametrize("name", REPLACEMENT_PARAGRAPH_FILES)
def test_replacement_paragraph_mentions_task_list(name):
    """AC-4 (Baustein 2/3): Der Ersatz-Absatz nennt `TaskList` als Weg, um
    beim nächsten eigenen Zug nachzufassen, ob ein Agent noch aktiv ist.
    """
    content = (COMMANDS_DIR / name).read_text(encoding="utf-8")
    assert REPLACEMENT_MARKERS["task_list"] in content, (
        f"{name}: Ersatz-Absatz fehlt der Baustein "
        f"'{REPLACEMENT_MARKERS['task_list']}' — ohne ihn fehlt der "
        f"Nachfass-Mechanismus, der TIMEOUT-PFLICHT ersetzt."
    )


@pytest.mark.parametrize("name", REPLACEMENT_PARAGRAPH_FILES)
def test_replacement_paragraph_mentions_task_stop(name):
    """AC-4 (Baustein 3/3): Der Ersatz-Absatz nennt `TaskStop`, um einen
    hängenden Agenten tatsächlich zu beenden statt endlos zu warten.
    """
    content = (COMMANDS_DIR / name).read_text(encoding="utf-8")
    assert REPLACEMENT_MARKERS["task_stop"] in content, (
        f"{name}: Ersatz-Absatz fehlt der Baustein "
        f"'{REPLACEMENT_MARKERS['task_stop']}' — ohne ihn fehlt das Mittel, "
        f"einen hängenden Agenten zu beenden statt endlos zu warten."
    )


def test_generated_skills_have_no_drift_from_commands():
    """AC-5: `scripts/sync_skills.py --check` läuft ohne Drift durch.

    Dieser Test ist heute bereits GRÜN, nicht rot — `skills/` ist im
    aktuellen Stand synchron zu `core/commands/`. Er ist trotzdem Teil
    dieser Datei, weil er in der GREEN-Phase die Absicherung dafür ist,
    dass die Umsetzung nach dem Ändern der vier Befehlsdateien nicht
    vergisst, `python3 scripts/sync_skills.py` laufen zu lassen (siehe
    `scripts/release_check.py::check_skills_sync()` als Vorbild für diesen
    Import-Weg). Ein Fehlschlag hier bedeutet nicht "Test falsch
    geschrieben", sondern "Skills und Commands sind auseinandergelaufen".
    """
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import sync_skills

    drift = sync_skills.check()
    assert not drift, (
        f"skills/ weicht von core/commands ab ({', '.join(drift)}) — "
        f"python3 scripts/sync_skills.py ausführen"
    )
