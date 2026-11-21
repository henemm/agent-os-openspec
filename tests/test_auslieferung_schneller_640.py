"""Tests fuer die schnellere Auslieferung (Issue #640).

Zwei Hebel: Die Testsuite laeuft parallel (pytest-xdist, `-n auto`), in der CI
und in der Rueckfall-Suite des Release-Waechters; ohne Plugin bleibt sie
seriell. Und bei Einzel-Auslieferung enthaelt der Fix-PR den Versions-Bump
selbst, ein getrennter Release-PR bleibt nur beim Buendeln mehrerer Issues.

Teststil wie `tests/test_release_tested_proof_633.py`:
- Workflow-Dateien werden als YAML geparst, nicht per Textsuche.
- `build_suite_command` ist pur; die Verfuegbarkeit wird eingespeist.
- `check_tests` laeuft echt gegen eine kleine Suite auf `tmp_path`; ob xdist
  wirkte, verraet die Suite selbst (Umgebungsvariable `PYTEST_XDIST_WORKER`,
  die nur xdist-Worker setzen).
"""

import re
import sys
import textwrap
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
CI_YML = REPO_ROOT / ".github" / "workflows" / "ci.yml"
RELEASE_YML = REPO_ROOT / ".github" / "workflows" / "release.yml"
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import release_check  # noqa: E402
import sync_skills  # noqa: E402


def _steps(workflow_path: Path, job: str) -> list:
    data = yaml.safe_load(workflow_path.read_text())
    jobs = data.get("jobs") or {}
    assert job in jobs, f"Job '{job}' fehlt in {workflow_path.name}"
    return jobs[job].get("steps") or []


def _pip_packages(run: str) -> "set[str]":
    packages = set()
    for line in run.splitlines():
        match = re.search(r"pip install (.+)", line)
        if match:
            packages.update(tok for tok in match.group(1).split() if not tok.startswith("-"))
    return packages


# --------------------------------------------------------------------------
# AC-1: CI-Job `tests` installiert xdist und laeuft parallel
# --------------------------------------------------------------------------

def test_ci_tests_job_installiert_xdist_und_laeuft_parallel():
    steps = _steps(CI_YML, "tests")
    runs = [str(step.get("run") or "") for step in steps]

    installed = set()
    for run in runs:
        installed |= _pip_packages(run)
    assert {"pytest", "pyyaml", "pytest-xdist"} <= installed, (
        f"Job tests installiert nicht pytest, pyyaml und pytest-xdist: {sorted(installed)}")

    suite_calls = [line.strip() for run in runs for line in run.splitlines()
                   if "-m pytest" in line]
    assert suite_calls, "Job tests ruft die Suite nicht auf"
    assert "python3 -m pytest tests/ -q -n auto" in suite_calls, (
        f"Suite nicht parallel aufgerufen: {suite_calls}")


# --------------------------------------------------------------------------
# AC-2: build_suite_command, -n auto nur mit xdist
# --------------------------------------------------------------------------

def test_suite_kommando_parallel_nur_mit_xdist():
    parallel = release_check.build_suite_command(True)
    serial = release_check.build_suite_command(False)

    assert parallel == [sys.executable, "-m", "pytest", "tests/", "-q", "-n", "auto"]
    assert serial == [sys.executable, "-m", "pytest", "tests/", "-q"]
    assert "-n" not in serial
    # pur: wiederholter Aufruf liefert dasselbe, keine geteilte Liste
    serial.append("x")
    assert release_check.build_suite_command(False) == [
        sys.executable, "-m", "pytest", "tests/", "-q"]


# --------------------------------------------------------------------------
# AC-3: check_tests faellt ohne xdist auf seriell zurueck
# --------------------------------------------------------------------------

def _mini_suite(root: Path) -> Path:
    """Kleine Suite, die festhaelt, ob sie in einem xdist-Worker lief."""
    marker = root / "worker.txt"
    (root / "tests").mkdir()
    (root / "pytest.ini").write_text("[pytest]\n")
    (root / "tests" / "test_mini.py").write_text(textwrap.dedent(f"""
        import os
        from pathlib import Path

        def test_merkt_worker():
            Path({str(marker)!r}).write_text(os.environ.get("PYTEST_XDIST_WORKER", "seriell"))
    """))
    return marker


def test_check_tests_faellt_ohne_xdist_auf_seriell_zurueck(tmp_path, monkeypatch):
    marker = _mini_suite(tmp_path)
    monkeypatch.setattr(release_check, "REPO_ROOT", tmp_path)

    # Ohne xdist: serielles Kommando, keine Ausnahme, Suite gruen.
    monkeypatch.setattr(release_check, "xdist_available", lambda: False)
    ok, message = release_check.check_tests()
    assert ok is True, message
    assert marker.read_text() == "seriell", "Suite lief trotz fehlendem xdist parallel"

    # Gegenprobe: Verfuegbarkeit stammt aus xdist_available() — mit True laeuft
    # dieselbe Suite in einem xdist-Worker (xdist ist im Test-venv installiert).
    pytest.importorskip("xdist")
    marker.unlink()
    monkeypatch.setattr(release_check, "xdist_available", lambda: True)
    ok, message = release_check.check_tests()
    assert ok is True, message
    assert marker.read_text().startswith("gw"), (
        f"Suite lief trotz xdist_available()=True nicht parallel: {marker.read_text()!r}")


# --------------------------------------------------------------------------
# AC-4: release.yml installiert xdist
# --------------------------------------------------------------------------

def test_release_workflow_installiert_xdist():
    data = yaml.safe_load(RELEASE_YML.read_text())
    steps = [step for job in (data.get("jobs") or {}).values()
             for step in (job.get("steps") or [])]
    install = [step for step in steps if step.get("name") == "Install dependencies"]
    assert len(install) == 1, "Schritt 'Install dependencies' fehlt oder ist doppelt"
    packages = _pip_packages(str(install[0].get("run") or ""))
    assert {"pytest", "pyyaml", "pytest-xdist"} <= packages, (
        f"Install dependencies installiert: {sorted(packages)}")


# --------------------------------------------------------------------------
# AC-5: Doku nennt die Ausnahme Einzel-Auslieferung konsistent
# --------------------------------------------------------------------------

DOC_FILES = [
    REPO_ROOT / "CLAUDE.md",
    REPO_ROOT / "docs" / "arbeitsweise.md",
    REPO_ROOT / "core" / "commands" / "60-validate.md",
]

# Formulierungen, die den Bump ausserhalb eines Release-PRs verbieten
RESTRICTION = re.compile(
    r"keine Versionsnummer|nur in eigenen Release-PRs|Release als eigener PR", re.IGNORECASE)


def _blocks(text: str) -> "list[str]":
    """Absaetze bzw. Listenpunkte: Grenze bei Leerzeile oder neuem Listenpunkt."""
    blocks, current = [], []
    for line in text.splitlines():
        starts_item = re.match(r"\s{0,3}(?:[-*]|\d+\.)\s", line)
        if not line.strip() or starts_item:
            if current:
                blocks.append("\n".join(current))
            current = [line] if line.strip() else []
        else:
            current.append(line)
    if current:
        blocks.append("\n".join(current))
    return blocks


def test_doku_nennt_einzel_auslieferung_ausnahme_konsistent():
    # doc-compliance-test
    for path in DOC_FILES:
        text = path.read_text()
        rel = path.relative_to(REPO_ROOT)
        assert "Einzel-Auslieferung" in text, f"{rel}: Regel Einzel-Auslieferung fehlt"

        rule_blocks = [b for b in _blocks(text) if "Einzel-Auslieferung" in b]
        assert any(re.search(r"b(ü|ue)ndel", b, re.IGNORECASE) for b in rule_blocks), (
            f"{rel}: Einzel-Auslieferung ohne Hinweis, dass der Release-PR nur beim "
            f"Buendeln mehrerer Issues getrennt bleibt")
        assert any(re.search(r"Bump|Versionsnummer|Version", b) for b in rule_blocks), (
            f"{rel}: Einzel-Auslieferung nennt den Versions-Bump im PR nicht")

        for block in _blocks(text):
            if RESTRICTION.search(block):
                assert "Einzel-Auslieferung" in block, (
                    f"{rel}: uneingeschraenktes Bump-Verbot ohne Ausnahme:\n{block}")


# --------------------------------------------------------------------------
# AC-6: skills/60-validate ohne Drift
# --------------------------------------------------------------------------

def test_skills_60_validate_ohne_drift():
    drift = sync_skills.check()
    assert "60-validate" not in drift, "skills/60-validate/SKILL.md weicht ab"
    skill = (REPO_ROOT / "skills" / "60-validate" / "SKILL.md").read_text()
    assert "Einzel-Auslieferung" in skill, (
        "SKILL.md traegt die Regel nicht — sync_skills.py nach der Aenderung nicht gelaufen")
