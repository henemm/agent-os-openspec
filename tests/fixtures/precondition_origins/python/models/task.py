"""Minimal, nachgebautes Beispielmodell fuer die Regelweg-Tests von
precondition_origins.py. Traegt vier Felder: processed_at (1x
Produktions-Schreibstelle), energy_raw (0x), title (3x) -- alle drei mit
mindestens einer Test-Zuweisung --, und notes, das aus dem Modell gelesen
wird (AC-1a), aber von KEINER Testdatei je zugewiesen wird und deshalb nicht
in der gefilterten Ausgabetabelle erscheinen darf (AC-1b).
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Task:
    processed_at: Optional[datetime] = None
    energy_raw: Optional[int] = None
    title: str = ""
    notes: Optional[str] = None
