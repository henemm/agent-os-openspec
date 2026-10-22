#!/usr/bin/env python3
"""Evidence-Gate (#447): maschinell erzeugter Beleg als Pflicht vor Phase 8 — opt-in.

`check_evidence(target, data)` liefert None (erlaubt) oder einen Grund als Text, nie eine
Exception. Ohne `evidence_checks` in der Config kehrt es sofort zurueck — vor jedem Git-
und `xcrun`-Aufruf. Vorhandene, aber kaputte Config weist ab (fail-closed).

Verifier-Registry `VERIFIERS`: weitere Belegtypen kosten nur einen Eintrag. Erstes Mitglied
`xcresult_proof` prueft `docs/artifacts/<wf>/simulator-run.txt` (Format: loose-ends
`scripts/sim_proof.py`) und leitet das Testergebnis selbst neu aus `run.xcresult` ab.
Die Test-Naht `runner` ist ausschliesslich ein Python-Parameter.
"""

import fnmatch
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

XCRESULT_TIMEOUT = 120
_COUNTERS = ("totalTestCount", "passedTests", "failedTests", "skippedTests")
_TESTS_LINE_RE = re.compile(
    r"^(\d+) gesamt, (\d+) bestanden, (\d+) fehlgeschlagen, (\d+) übersprungen$")
_SUMMARY_SHA_RE = re.compile(r"\ssha256:([0-9a-f]{64})\s*$")
_MENTION_RE = re.compile(r"(?m)^[^#\n]*\bevidence_checks\b")


class _Reject(Exception):
    """Interner Abweisungsgrund — wird in check_evidence zum Rueckgabetext."""


def _raw_config_mentions_gate() -> bool:
    """Nicht ladbare Config-Datei, die `evidence_checks` nennt? (AC-3)

    `load_config` schluckt kaputtes YAML (nur Warnung + Defaults) — das Gate prueft die
    Ladbarkeit deshalb selbst. Nur eine Datei, die das Gate erwaehnt, zaehlt: Projekte
    ohne Opt-in bleiben bei kaputter Config unveraendert.
    """
    from config_loader import find_config_file, find_project_root
    path = find_config_file(find_project_root())
    if path is None:
        return False
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    if not _MENTION_RE.search(text):  # auskommentierte Vorlage zaehlt nicht
        return False
    try:
        import yaml
        yaml.safe_load(text)
    except Exception:
        return True
    return False


def _gate_entries(target: str) -> "tuple[list, list] | None":
    """(Eintraege, exempt_paths) oder None, wenn das Gate fuer `target` aus ist."""
    if _raw_config_mentions_gate():
        raise _Reject("Config nicht ladbar (evidence_checks gesetzt) — Gate bleibt zu")
    from config_loader import load_config
    section = load_config().get("evidence_checks")
    if not section:
        return None
    if not isinstance(section, dict):
        raise _Reject("Config evidence_checks ist kein Objekt")
    entries = section.get(target)
    if not entries:
        return None
    exempt = section.get("exempt_paths") or []
    if not isinstance(entries, list):
        raise _Reject(f"Config evidence_checks.{target} ist keine Liste")
    if not isinstance(exempt, list) or not all(isinstance(p, str) for p in exempt):
        raise _Reject("Config evidence_checks.exempt_paths ist keine Liste von Mustern")
    for entry in entries:
        _validate_entry(entry, target)
    return entries, exempt


def _validate_entry(entry, target: str) -> None:
    where = f"Config evidence_checks.{target}"
    if not isinstance(entry, dict):
        raise _Reject(f"{where}: Eintrag ist kein Objekt ({entry!r})")
    verifier, file = entry.get("verifier"), entry.get("file")
    if not isinstance(verifier, str) or not verifier:
        raise _Reject(f"{where}: `verifier` fehlt")
    if not isinstance(file, str) or not file:
        raise _Reject(f"{where}: `file` fehlt")
    if "/" in file or "\\" in file or ".." in file:
        raise _Reject(f"{where}: `file` darf weder Pfadtrenner noch `..` enthalten ({file!r})")
    if verifier not in VERIFIERS:
        raise _Reject(f"{where}: unbekannter verifier `{verifier}`")


def _gate_files(data: dict, exempt: list) -> list:
    """Gate-Menge (#259-Menge, realpath-absolut) minus exempt_paths; fail-closed."""
    import adversary_dialog as ad
    try:
        files, _info = ad.phase8_code_files(data)
    except ad.ChangeSetError as exc:
        raise _Reject(str(exc))
    if files is None:
        raise _Reject("Änderungsmenge nicht ermittelbar — kein Git-Arbeitsbaum")
    return [f for f in files
            if not any(fnmatch.fnmatch(ad.display_path(f), p) for p in exempt)]


def _inside(root: str, path: Path) -> Path:
    """realpath von `path`, sofern unter `root` — sonst Abweisung (Symlink-Ausbruch)."""
    real = os.path.realpath(path)
    if os.path.commonpath([root, real]) != root:
        raise _Reject(f"Beleg-Pfad fuehrt aus dem Projekt hinaus: {path} -> {real}")
    return Path(real)


def _sha256(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _header(text: str) -> dict:
    """Kopfzeilen `schluessel: wert` vor `## Geprüfte Dateien` (erste gewinnt)."""
    head = text.split("\n## ", 1)[0]
    out = {}
    for line in head.splitlines():
        key, sep, value = line.partition(": ")
        if sep and key.isidentifier():
            out.setdefault(key, value.strip())
    return out


def _check_hash_block(text: str, gate: list) -> None:
    """Jede Gate-Datei mit aktuellem Hash im Block (Obermenge erlaubt)."""
    import adversary_dialog as ad
    entries = ad._parse_examined_files_section(text) or []
    bound = {os.path.realpath(ad._resolve_hash_path(rel)): sha for sha, rel in entries}
    missing = [ad.display_path(f) for f in gate if f not in bound]
    if missing:
        raise _Reject("Beleg bindet Gate-Dateien nicht (## Geprüfte Dateien): "
                      + ", ".join(missing))
    stale = [ad.display_path(f) for f in gate if _sha256(f) != bound[f]]
    if stale:
        raise _Reject("Beleg veraltet — Datei nach dem Lauf geändert: " + ", ".join(stale))


def _run_xcresulttool(bundle: Path, runner) -> dict:
    argv = ["xcrun", "xcresulttool", "get", "test-results", "summary",
            "--path", str(bundle), "--compact"]
    try:
        proc = runner(argv, capture_output=True, text=True, timeout=XCRESULT_TIMEOUT)
    except subprocess.TimeoutExpired:
        raise _Reject(f"xcrun xcresulttool: Timeout (Zeitlimit {XCRESULT_TIMEOUT}s überschritten)")
    except OSError as exc:
        raise _Reject(f"xcrun/xcresulttool nicht verfügbar ({type(exc).__name__}: {exc})")
    if proc.returncode != 0:
        raise _Reject(f"xcrun xcresulttool endete mit Exit-Code {proc.returncode}")
    try:
        derived = json.loads(proc.stdout)
    except (TypeError, ValueError):
        raise _Reject("xcresulttool-Ausgabe ist kein gültiges JSON")
    if not isinstance(derived, dict):
        raise _Reject("xcresulttool-Ausgabe ist kein JSON-Objekt")
    return derived


def _compare(derived: dict, stored: dict, header: dict) -> None:
    """Semantischer Vergleich: result + vier Zaehler gegen summary.json und Belegzeilen."""
    for field in ("result",) + _COUNTERS:
        if derived.get(field) != stored.get(field):
            raise _Reject(f"Neuableitung weicht von summary.json ab: {field} "
                          f"{derived.get(field)!r} != {stored.get(field)!r}")
    if header.get("ergebnis") != derived.get("result"):
        raise _Reject(f"ergebnis-Zeile {header.get('ergebnis')!r} passt nicht zur "
                      f"Neuableitung {derived.get('result')!r}")
    m = _TESTS_LINE_RE.match(header.get("tests", ""))
    if not m or [int(g) for g in m.groups()] != [derived.get(c) for c in _COUNTERS]:
        raise _Reject(f"tests-Zeile {header.get('tests')!r} passt nicht zur Neuableitung")
    if derived.get("result") != "Passed":
        raise _Reject(f"Testergebnis result={derived.get('result')!r}, nicht Passed")
    if not isinstance(derived.get("passedTests"), int) or derived["passedTests"] < 1:
        raise _Reject("passedTests < 1 — kein bestandener Test")


def _verify_xcresult_proof(proof: Path, root: str, gate: list, runner) -> None:
    """Prueft einen Beleg im Format von `sim_proof.format_proof` (AC-9 … AC-22)."""
    if not proof.is_file():
        raise _Reject(f"Beleg fehlt: {proof} (erzeugen mit scripts/sim.sh test-proof)")
    text = proof.read_text(encoding="utf-8")
    _check_hash_block(text, gate)
    header = _header(text)
    run_dir = _inside(root, proof.parent / proof.stem)
    summary = _inside(root, run_dir / "summary.json")
    sha = _SUMMARY_SHA_RE.search(" " + header.get("summary", ""))
    if not summary.is_file() or not sha:
        raise _Reject(f"summary.json fehlt oder ohne Prüfsumme im Beleg: {summary}")
    if _sha256(summary) != sha.group(1):
        raise _Reject(f"summary.json passt nicht zur Prüfsumme im Beleg: {summary}")
    bundle = _inside(root, run_dir / "run.xcresult")
    if not bundle.exists():
        raise _Reject(f"Ergebnisbündel run.xcresult fehlt: {bundle}")
    stored = json.loads(summary.read_text(encoding="utf-8"))
    if not isinstance(stored, dict):
        raise _Reject("summary.json ist kein JSON-Objekt")
    _compare(_run_xcresulttool(bundle, runner), stored, header)


VERIFIERS = {"xcresult_proof": _verify_xcresult_proof}


def _workflow_name(data: dict) -> str:
    name = data.get("name")
    if not isinstance(name, str) or not name or "/" in name or "\\" in name or ".." in name:
        raise _Reject(f"Workflow-Name ungültig für den Beleg-Ort: {name!r}")
    return name


def _check(target: str, data: dict, runner) -> "str | None":
    gate_cfg = _gate_entries(target)
    if gate_cfg is None:
        return None
    entries, exempt = gate_cfg
    name = _workflow_name(data)
    from override_token import has_valid_token
    if has_valid_token(name):
        print("Evidence-Gate per override umgangen", file=sys.stderr)
        return None
    gate = _gate_files(data, exempt)
    if not gate:
        return None
    import adversary_dialog as ad
    root = os.path.realpath(ad._hash_root())
    for entry in entries:
        proof = _inside(root, Path(root) / "docs" / "artifacts" / name / entry["file"])
        VERIFIERS[entry["verifier"]](proof, root, gate, runner or subprocess.run)
    return None


def check_evidence(target: str, data: dict, *, runner=None) -> "str | None":
    """None = erlaubt, sonst Abweisungsgrund (fail-closed, nie eine Exception)."""
    try:
        return _check(target, data, runner)
    except _Reject as exc:
        return f"Evidence-Gate: {exc}"
    except Exception as exc:
        return f"Evidence-Gate: Prüfung nicht verfügbar ({type(exc).__name__}: {exc})"
