"""Nachgebauter Produktivcode. Schreibt processed_at genau einmal, hinter
einer if-Bedingung; schreibt title dreimal; schreibt energy_raw nie.
"""

from datetime import datetime

from models.task import Task


def mark_processed(task: Task, now: datetime) -> None:
    if task.processed_at is None:
        task.processed_at = now


def apply_title(task: Task, raw: str) -> None:
    task.title = raw.strip()


def fallback_title(task: Task) -> None:
    if not task.title:
        task.title = "Untitled"


def reset_title(task: Task) -> None:
    task.title = ""
