"""Nachgebaute Testdatei. Weist task.processed_at an fuenf Stellen zu, weist
task.energy_raw an einer Stelle zu (obwohl das Feld 0
Produktions-Schreibstellen hat) und task.title an zwei Stellen -- alle drei
Felder brauchen mindestens eine Test-Zuweisung, sonst fielen sie unter der
Filterregel aus der Ausgabetabelle heraus. notes wird bewusst NIE zugewiesen
(Beleg fuer AC-1b). Dazu Rauschen, das keinen Treffer erzeugen darf: eine
lokale Variable gleichen Namens ohne Objektbezug und Vergleiche mit ==.
"""

from datetime import datetime, timedelta

from models.task import Task


def _make_processed_task(minutes_ago: int) -> Task:
    task = Task(title="Sample")
    task.processed_at = datetime.now() - timedelta(minutes=minutes_ago)
    return task


def test_processed_at_is_set_for_morning_task():
    task = Task(title="Morning")
    task.processed_at = datetime.now()
    assert task.processed_at is not None


def test_processed_at_is_set_for_evening_task():
    task = Task(title="Evening")
    task.processed_at = datetime.now() - timedelta(hours=1)
    assert task.processed_at is not None


def test_processed_at_is_set_for_recurring_task():
    task = _make_processed_task(minutes_ago=5)
    task.processed_at = datetime.now()
    assert task.processed_at is not None


def test_processed_at_is_set_for_batch_task():
    task = Task(title="Batch")
    task.processed_at = datetime.now() - timedelta(hours=2)
    assert task.processed_at is not None


def test_processed_at_stays_none_until_assigned():
    processed_at = datetime.now()
    task = Task(title="Untouched")
    assert task.processed_at is None
    assert task.processed_at != processed_at


def test_processed_at_comparison_against_none():
    task = Task(title="Comparison")
    assert task.processed_at == None  # noqa: E711 - bewusst fuer den Pattern-Check


def test_energy_raw_defaults_to_zero():
    task = Task(title="Energy")
    task.energy_raw = 0
    assert task.energy_raw == 0


def test_title_is_renamed():
    task = Task(title="Old")
    task.title = "Renamed"
    assert task.title == "Renamed"


def test_title_is_renamed_again():
    task = Task(title="Old")
    task.title = "Renamed Again"
    assert task.title == "Renamed Again"


def test_title_comparison_is_not_an_assignment():
    task = Task(title="Fixed")
    assert task.title == "Fixed"
