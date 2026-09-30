#!/usr/bin/env python3
"""Herkunft von Testvorbedingungen maschinell einsammeln (Issue #285).

Reiner Regelweg — Dateisuche plus regulaere Ausdruecke, kein Sprachmodell.
Je Sprachprofil (`config.yaml` -> `precondition_origins.profiles`) werden die
Feldnamen aus den Modelldateien gelesen, danach die Punkt-Zuweisungen
(`objekt.feld = wert`) in Test- und Produktivcode gesucht und als
Markdown-Verdachtsliste gerendert.

Gelesen werden ALLE Modellfelder; gelistet werden nur die Felder mit
mindestens einer Test-Zuweisung. Die beiden letzten Tabellenspalten
("Bedingung davor", "Test fuer diesen Weg") bleiben leer — sie fuellt der
menschliche Pruefer.

Spec: docs/specs/feat-285-precondition-origins.md

Aufruf:
    python3 core/hooks/precondition_origins.py --lang swift \
        [--root <pfad>] [--config <pfad zu config.yaml>] [--out <pfad>]
"""

from hook_utils import setup_path, find_project_root

setup_path()

import argparse  # noqa: E402
import re  # noqa: E402
import sys  # noqa: E402
from pathlib import Path  # noqa: E402

import yaml  # noqa: E402

from config_loader import load_config  # noqa: E402

PROFILE_KEYS = (
    "model_globs",
    "field_pattern",
    "test_globs",
    "production_globs",
    "production_exclude_globs",
    "assignment_pattern",
)

HEADER = (
    "| Feld | Test-Zuweisungen | Produktions-Schreibstellen "
    "| Bedingung davor | Test für diesen Weg |"
)
SEPARATOR = "|---|---|---|---|---|"
NO_PRODUCTION_WRITE = "**0 — keine Schreibstelle im Produktivcode**"
NO_TEST_ASSIGNMENT = "**0**"
EMPTY_TABLE_HINT = (
    "Kein Feld mit Test-Zuweisung gefunden — nichts zu pruefen."
)


def _fail(message: str) -> None:
    """Meldung nach stderr, Exit 1 — kein stiller Fallback."""
    print(f"FEHLER: {message}", file=sys.stderr)
    sys.exit(1)


def _compile_or_fail(pattern: str, label: str):
    """re.compile mit sprechender Fehlermeldung statt Traceback."""
    try:
        return re.compile(pattern)
    except re.error as exc:
        _fail(f"Ungueltiger regulaerer Ausdruck in '{label}': {exc}")


def _read_lines(path: Path) -> list:
    """Zeilen einer Datei; fail-open pro Datei (Warnung nach stderr)."""
    try:
        return path.read_text(encoding="utf-8").splitlines()
    except (UnicodeDecodeError, PermissionError, OSError) as exc:
        print(f"WARNUNG: uebersprungen {path}: {exc}", file=sys.stderr)
        return []


def load_profile(config: dict, lang: str) -> dict:
    """Sprachprofil aus der Config holen und vollstaendig validieren."""
    section = (config or {}).get("precondition_origins") or {}
    profiles = section.get("profiles") or {}
    if lang not in profiles:
        available = ", ".join(sorted(profiles)) or "(keines)"
        _fail(
            f"Kein Profil '{lang}' unter precondition_origins.profiles. "
            f"Verfuegbare Profile: {available}"
        )
    profile = profiles[lang] or {}
    for key in PROFILE_KEYS:
        if profile.get(key) is None:
            _fail(f"Profil '{lang}': Schluessel '{key}' fehlt oder ist leer.")
    _compile_or_fail(profile["field_pattern"], f"{lang}.field_pattern")
    _compile_or_fail(
        str(profile["assignment_pattern"]).replace("{field}", re.escape("probe")),
        f"{lang}.assignment_pattern",
    )
    return profile


def _expand_glob(pattern: str) -> list:
    """Ein auf '/**' endendes Muster erfasst je nach Python-Version nur
    Verzeichnisse — deshalb zusaetzlich die Dateivariante mitfuehren."""
    if pattern.endswith("/**"):
        return [pattern, pattern + "/*"]
    return [pattern]


def iter_glob_files(root: Path, globs: list, exclude: list = ()) -> list:
    """Dateien unter root, die auf globs passen und nicht auf exclude."""

    def collect(patterns) -> set:
        found = set()
        for pattern in patterns or []:
            for expanded in _expand_glob(str(pattern)):
                for path in root.glob(expanded):
                    if path.is_file():
                        found.add(path)
        return found

    return sorted(collect(globs) - collect(exclude))


def extract_model_fields(root: Path, profile: dict) -> list:
    """Alle Feldnamen aus den Modelldateien — ungefragt und vollstaendig."""
    field_re = _compile_or_fail(profile["field_pattern"], "field_pattern")
    fields = set()
    for path in iter_glob_files(root, profile["model_globs"]):
        for line in _read_lines(path):
            match = field_re.search(line)
            if match:
                fields.add(match.group(1))
    return sorted(fields)


def find_assignments(root: Path, globs: list, exclude: list,
                     fields: list, assignment_pattern: str) -> dict:
    """field -> ['datei:zeile', ...], sortiert nach Fundstelle.

    `datei` ist relativ zu `root`. Gezaehlt wird nur die Punkt-Zuweisung
    (`.feld =`), nicht der Vergleich (`.feld ==`) und nicht eine gleichnamige
    lokale Variable ohne Objektbezug.
    """
    compiled = {
        field: _compile_or_fail(
            str(assignment_pattern).replace("{field}", re.escape(field)),
            f"assignment_pattern[{field}]",
        )
        for field in fields
    }
    hits = {field: [] for field in fields}
    for path in iter_glob_files(root, globs, exclude):
        try:
            location = path.relative_to(root).as_posix()
        except ValueError:
            location = path.as_posix()
        for number, line in enumerate(_read_lines(path), start=1):
            for field, regex in compiled.items():
                if regex.search(line):
                    hits[field].append(f"{location}:{number}")
    return hits


def _cell(locations: list, zero_text: str) -> str:
    """'<Anzahl> — <Datei:Zeile><br>...' bzw. der Null-Hinweistext."""
    if not locations:
        return zero_text
    return f"{len(locations)} — " + "<br>".join(locations)


def render_table(fields: list, test_hits: dict, prod_hits: dict) -> str:
    """Markdown-Tabelle — nur Felder mit mindestens einer Test-Zuweisung.

    Sortiert aufsteigend nach Zahl der Produktions-Schreibstellen,
    Tie-Break Feldname alphabetisch. Felder mit 0 Schreibstellen stehen
    dadurch oben und tragen den Hinweistext in ihrer Zelle.
    """
    listed = [f for f in fields if test_hits.get(f)]
    if not listed:
        return EMPTY_TABLE_HINT + "\n"
    listed.sort(key=lambda field: (len(prod_hits.get(field) or []), field))
    rows = [HEADER, SEPARATOR]
    for field in listed:
        test_cell = _cell(test_hits.get(field) or [], NO_TEST_ASSIGNMENT)
        prod_cell = _cell(prod_hits.get(field) or [], NO_PRODUCTION_WRITE)
        rows.append(f"| {field} | {test_cell} | {prod_cell} |  |  |")
    return "\n".join(rows) + "\n"


def _load_config_source(config_path) -> dict:
    """--config liest genau diese YAML-Datei, sonst config_loader."""
    if not config_path:
        return load_config()
    path = Path(config_path).expanduser()
    if not path.is_file():
        _fail(f"--config existiert nicht oder ist keine Datei: {path}")
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        _fail(f"--config nicht lesbar ({path}): {exc}")


def _emit(text: str, out) -> None:
    """Ausgabe nach --out oder stdout."""
    if not out:
        print(text.rstrip("\n"))
        return
    target = Path(out).expanduser()
    if target.parent and not target.parent.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text if text.endswith("\n") else text + "\n",
                      encoding="utf-8")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="precondition_origins.py",
        description="Herkunft von Testvorbedingungen einsammeln (Issue #285).",
    )
    parser.add_argument("--lang", required=True,
                        help="Name des Sprachprofils aus der Config")
    parser.add_argument("--root", default=None,
                        help="zu scannender Baum (Default: find_project_root())")
    parser.add_argument("--config", default=None,
                        help="Pfad zu einer config.yaml (Default: config_loader)")
    parser.add_argument("--out", default=None,
                        help="Ausgabedatei (Default: stdout)")
    return parser.parse_args()


def main() -> None:
    """CLI-Einstiegspunkt. Erfolg kehrt zurueck, Fehler beenden mit Exit 1."""
    args = _parse_args()
    root = Path(args.root).expanduser() if args.root else find_project_root()
    if not root.is_dir():
        _fail(f"--root existiert nicht oder ist kein Verzeichnis: {root}")

    profile = load_profile(_load_config_source(args.config), args.lang)

    model_files = iter_glob_files(root, profile["model_globs"])
    if not model_files:
        _emit(f"Keine Modelldateien gefunden unter {profile['model_globs']}",
              args.out)
        return
    fields = extract_model_fields(root, profile)
    if not fields:
        _emit(
            f"Keine Feldnamen extrahierbar aus {len(model_files)} Modelldatei(en) "
            f"mit field_pattern {profile['field_pattern']!r}",
            args.out,
        )
        return

    test_hits = find_assignments(root, profile["test_globs"], [], fields,
                                 profile["assignment_pattern"])
    prod_hits = find_assignments(root, profile["production_globs"],
                                 profile["production_exclude_globs"], fields,
                                 profile["assignment_pattern"])
    _emit(render_table(fields, test_hits, prod_hits), args.out)


if __name__ == "__main__":
    main()
