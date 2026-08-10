#!/usr/bin/env python3
"""Vorbedingungen fuer ein Release pruefen (Issue #93).

Dieses Repo ist gleichzeitig Arbeitsordner und Auslieferungsquelle. Wer einen
Katalog mit `source: "directory"` auf den Arbeitsordner registriert, liefert
maschinenweit aus, was gerade ausgecheckt ist — inklusive Arbeitsbranch und
unversionierter Dateien. Ausgeliefert werden dabei die Gates, die in JEDEM
Projekt jeden Commit pruefen; eine unfertige Fassung blockiert entweder
legitime Arbeit oder laesst Fehlerhaftes durch, und beides faellt erst in der
naechsten Sitzung auf ("restart required to apply").

Der eigentliche Schutz ist ein Katalog mit Ref-Pin (siehe README, Abschnitt
"Ausliefern"). Dieses Skript ist die zweite Verteidigungslinie: Es bricht ab,
bevor ein Tag auf einen Stand gesetzt wird, der nicht dem entspricht, was auf
main veroeffentlicht ist.

    python3 scripts/release_check.py            # pruefen
    python3 scripts/release_check.py --no-tests # ohne Testlauf (schneller)
    python3 scripts/release_check.py --notes    # CHANGELOG-Abschnitt ausgeben
    python3 scripts/release_check.py --tag      # Tag-Namen ausgeben

Exit-Code 0 = alle Pruefungen bestanden, 1 = mindestens eine gescheitert.

Wird ueblicherweise nicht von Hand aufgerufen, sondern von
.github/workflows/release.yml beim Push auf main.
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN_JSON = REPO_ROOT / ".claude-plugin" / "plugin.json"
CHANGELOG = REPO_ROOT / "CHANGELOG.md"
RELEASE_BRANCH = "main"

# Tag-Konvention: die Form, die Claude Code fuer Plugin-Abhaengigkeiten
# versteht ({plugin-name}--v{version}).
TAG_TEMPLATE = "{name}--v{version}"

# Erste Ueberschrift der Form "## [3.11.4] - 2026-08-10"
_CHANGELOG_VERSION_RE = re.compile(r"^##\s*\[([^\]]+)\]", re.MULTILINE)


def _git(*args: str) -> "subprocess.CompletedProcess":
    return subprocess.run(["git", *args], cwd=str(REPO_ROOT),
                          capture_output=True, text=True)


def plugin_manifest() -> dict:
    """Name und Version aus plugin.json — die Quelle, aus der Claude Code die
    Version liest (plugin.json gewinnt immer gegen den Marketplace-Eintrag)."""
    return json.loads(PLUGIN_JSON.read_text())


def latest_changelog_version(text: str) -> "str | None":
    """Version des obersten Eintrags im CHANGELOG, oder None.

    'Unreleased' zaehlt bewusst NICHT als Version: ein Release aus einem
    Stand mit offenem Unreleased-Block waere unvollstaendig dokumentiert.
    """
    for match in _CHANGELOG_VERSION_RE.finditer(text):
        version = match.group(1).strip()
        if version.lower() == "unreleased":
            return None
        return version
    return None


def changelog_section(text: str, version: str) -> str:
    """Fliesstext des CHANGELOG-Abschnitts zu `version` — ohne dessen eigene
    Ueberschrift, bis zur naechsten Versions-Ueberschrift.

    Wird als Text des GitHub-Releases verwendet, damit die Release-Notiz und
    der CHANGELOG nicht auseinanderlaufen koennen: es gibt nur eine Quelle.
    """
    headings = list(_CHANGELOG_VERSION_RE.finditer(text))
    for index, match in enumerate(headings):
        if match.group(1).strip() != version:
            continue
        start = text.find("\n", match.end())
        if start < 0:
            return ""
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        return text[start:end].strip()
    return ""


def check_branch() -> "tuple[bool, str]":
    result = _git("rev-parse", "--abbrev-ref", "HEAD")
    branch = result.stdout.strip()
    if branch != RELEASE_BRANCH:
        return False, f"Branch ist '{branch}', erwartet '{RELEASE_BRANCH}'"
    return True, f"Branch '{branch}'"


def check_clean_tree() -> "tuple[bool, str]":
    # --untracked-files=all: ohne das fasst git ein unversioniertes Verzeichnis
    # zu einer Zeile zusammen ('?? .claude/') und die Meldung nennt die
    # eigentliche Datei nicht — gerade bei .claude/pending_validation_*.json
    # ist aber genau der Dateiname die brauchbare Information.
    result = _git("status", "--porcelain", "--untracked-files=all")
    dirty = [line for line in result.stdout.splitlines() if line.strip()]
    if dirty:
        preview = ", ".join(line[3:] for line in dirty[:5])
        more = f" (+{len(dirty) - 5} weitere)" if len(dirty) > 5 else ""
        return False, f"{len(dirty)} nicht committete/unversionierte Datei(en): {preview}{more}"
    return True, "Arbeitsbaum sauber"


def check_in_sync() -> "tuple[bool, str]":
    """Weder vor noch hinter origin/main — sonst weicht der getaggte Stand von
    dem ab, was andere per Katalog ziehen."""
    fetch = _git("fetch", "origin", RELEASE_BRANCH, "--quiet")
    if fetch.returncode != 0:
        return False, f"'git fetch origin {RELEASE_BRANCH}' fehlgeschlagen — kein Netz?"
    counts = _git("rev-list", "--left-right", "--count",
                  f"HEAD...origin/{RELEASE_BRANCH}")
    if counts.returncode != 0:
        return False, "Abgleich mit origin nicht moeglich"
    try:
        ahead, behind = (int(x) for x in counts.stdout.split())
    except ValueError:
        return False, f"Unerwartete rev-list-Ausgabe: {counts.stdout!r}"
    if ahead or behind:
        return False, f"{ahead} Commit(s) vor, {behind} hinter origin/{RELEASE_BRANCH}"
    return True, f"synchron mit origin/{RELEASE_BRANCH}"


def check_version_match(manifest_version: str, changelog_version: "str | None") -> "tuple[bool, str]":
    if changelog_version is None:
        return False, "Oberster CHANGELOG-Eintrag ist 'Unreleased' oder fehlt"
    if manifest_version != changelog_version:
        return False, (f"plugin.json sagt {manifest_version}, "
                       f"oberster CHANGELOG-Eintrag {changelog_version}")
    return True, f"Version {manifest_version} in plugin.json und CHANGELOG"


def check_tag_free(tag: str) -> "tuple[bool, str]":
    _git("fetch", "origin", "--tags", "--quiet")
    result = _git("tag", "--list", tag)
    if result.stdout.strip():
        return False, f"Tag '{tag}' existiert bereits — Version bumpen"
    return True, f"Tag '{tag}' noch frei"


def check_tests() -> "tuple[bool, str]":
    result = subprocess.run([sys.executable, "-m", "pytest", "tests/", "-q"],
                            cwd=str(REPO_ROOT), capture_output=True, text=True)
    if result.returncode != 0:
        tail = result.stdout.strip().splitlines()[-1:] or ["(keine Ausgabe)"]
        return False, f"Testsuite rot: {tail[0]}"
    summary = result.stdout.strip().splitlines()[-1:] or [""]
    return True, f"Testsuite gruen — {summary[0]}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-tests", action="store_true",
                        help="Testlauf ueberspringen")
    parser.add_argument("--notes", action="store_true",
                        help="CHANGELOG-Abschnitt der aktuellen Version ausgeben und beenden")
    parser.add_argument("--tag", action="store_true",
                        help="Tag-Namen der aktuellen Version ausgeben und beenden")
    args = parser.parse_args()

    manifest = plugin_manifest()
    version = manifest.get("version", "")
    name = manifest.get("name", "")
    tag = TAG_TEMPLATE.format(name=name, version=version)

    if args.tag:
        print(tag)
        return 0
    if args.notes:
        print(changelog_section(CHANGELOG.read_text(), version))
        return 0

    checks = [
        ("Branch", check_branch()),
        ("Arbeitsbaum", check_clean_tree()),
        ("Abgleich", check_in_sync()),
        ("Version", check_version_match(version, latest_changelog_version(CHANGELOG.read_text()))),
        ("Tag", check_tag_free(tag)),
    ]
    if not args.no_tests:
        checks.append(("Tests", check_tests()))

    failed = 0
    for label, (ok, detail) in checks:
        print(f"  {'OK  ' if ok else 'FAIL'}  {label:12} {detail}")
        if not ok:
            failed += 1

    print()
    if failed:
        print(f"ABBRUCH: {failed} Pruefung(en) gescheitert — kein Release aus diesem Stand.",
              file=sys.stderr)
        return 1
    print(f"Bereit fuer Release {version}. Tag: {tag}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
