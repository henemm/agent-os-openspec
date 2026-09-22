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
README = REPO_ROOT / "README.md"
RELEASE_BRANCH = "main"

# Tag-Konvention: die Form, die Claude Code fuer Plugin-Abhaengigkeiten
# versteht ({plugin-name}--v{version}).
TAG_TEMPLATE = "{name}--v{version}"

# Erste Ueberschrift der Form "## [3.11.4] - 2026-08-10"
_CHANGELOG_VERSION_RE = re.compile(r"^##\s*\[([^\]]+)\]", re.MULTILINE)

# Versionszeile des README: "**Version**: 3.27.2 · [Changelog](CHANGELOG.md)".
# Bewusst an den Marker gebunden und nicht an "die erste Zahl im Dokument" —
# sonst gewinnt eine Versionsnummer aus einem Beispielblock (Issue #195).
_README_VERSION_RE = re.compile(
    r"^\*\*Version\*\*:\s*(\d+(?:\.\d+)*)", re.MULTILINE
)


def _git(*args: str) -> "subprocess.CompletedProcess":
    return subprocess.run(["git", *args], cwd=str(REPO_ROOT),
                          capture_output=True, text=True)


def plugin_manifest() -> dict:
    """Name und Version aus plugin.json — die Quelle, aus der Claude Code die
    Version liest (plugin.json gewinnt immer gegen den Marketplace-Eintrag)."""
    return json.loads(PLUGIN_JSON.read_text())


def latest_changelog_version(text: str) -> "str | None":
    """Version des obersten Eintrags im CHANGELOG, oder None.

    Ein **gefuellter** 'Unreleased'-Block zaehlt bewusst nicht als Version: Ein
    Release aus einem solchen Stand waere unvollstaendig dokumentiert — die dort
    beschriebenen Aenderungen bekaemen keine Versionsnummer.

    Ein **leerer** 'Unreleased'-Block wird dagegen uebersprungen (Issue #204).
    Er ist der Keep-a-Changelog-Platzhalter, den jeder stehen laesst, und
    dokumentiert nichts. Dass er blockierte, hat zwei fertige Versionen
    (3.27.1, 3.27.2) daran gehindert, ueberhaupt veroeffentlicht zu werden.
    """
    matches = list(_CHANGELOG_VERSION_RE.finditer(text))
    for index, match in enumerate(matches):
        version = match.group(1).strip()
        if version.lower() != "unreleased":
            return version

        # Abschnittsrumpf: ab dem Zeilenende der Ueberschrift bis zur naechsten
        # '## [...]'-Ueberschrift. Unterueberschriften wie '### Added' matchen
        # das Muster nicht und zaehlen damit als Inhalt — wer eine Rubrik
        # anlegt, hat etwas vor, und im Zweifel wird blockiert.
        body_start = text.find("\n", match.end())
        if body_start == -1:
            return None
        body_end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        if text[body_start:body_end].strip():
            return None
        # Leer — weiter zum naechsten Eintrag.
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


def version_tuple(version: str) -> tuple:
    """'3.28.0' -> (3, 28, 0). Fuer Vergleiche — als Text waere '3.9.0'
    groesser als '3.28.0'."""
    return tuple(int(part) for part in version.split("."))


def latest_tagged_version(tags: "list[str]", name: str) -> "str | None":
    """Hoechste veroeffentlichte Version aus einer Tag-Liste, oder None."""
    prefix = TAG_TEMPLATE.format(name=name, version="")
    versions = [
        tag[len(prefix):] for tag in tags
        if tag.startswith(prefix) and re.fullmatch(r"\d+(?:\.\d+)*", tag[len(prefix):])
    ]
    return max(versions, key=version_tuple) if versions else None


def main_plugin_version() -> "str | None":
    """Version, die aktuell auf `main` liegt — oder None, wenn nicht lesbar."""
    result = _git("show", f"origin/{RELEASE_BRANCH}:.claude-plugin/plugin.json")
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout).get("version") or None
    except json.JSONDecodeError:
        return None


def all_tags() -> "list[str]":
    _git("fetch", "origin", "--tags", "--quiet")
    result = _git("tag", "--list")
    return result.stdout.split() if result.returncode == 0 else []


def check_main_release_published(main_version: "str | None",
                                 latest_tag: "str | None") -> "tuple[bool, str]":
    """Liegt auf `main` eine Version, die nie veroeffentlicht wurde? (Issue #204)

    Das ist die Pruefung, die am 21.09.2026 gefehlt hat: `main` stand auf
    3.27.2, der letzte Tag war 3.27.0. Zwei Versionen waren fertig, dokumentiert
    und geschlossen — und kamen bei keinem Konsumenten-Projekt an, weil der
    Release-Job nach dem Merge rot wurde und niemand in die Actions schaut.

    Laeuft in der Inhaltspruefung, also im Pull Request: Dort wird ein rotes
    Kreuz gesehen. Der naechste PR nach einem verpassten Release schlaegt Alarm,
    statt dass der Rueckstand weiterwaechst.
    """
    if not main_version:
        # Flacher Klon o.ae. — eine Pruefung, die an einer Git-Eigenheit
        # scheitert, ist schlimmer als der Fehler, den sie sucht.
        return True, f"Stand von {RELEASE_BRANCH} nicht lesbar — uebersprungen"
    if not latest_tag:
        return True, "noch kein Release getaggt"
    if version_tuple(latest_tag) >= version_tuple(main_version):
        return True, f"letztes Release {latest_tag} deckt {RELEASE_BRANCH} ({main_version}) ab"
    return False, (
        f"{RELEASE_BRANCH} steht auf {main_version}, letzter Tag ist {latest_tag} — "
        "das letzte Release ist nicht herausgekommen (Issue #204). "
        "Zuerst den Release-Lauf auf main reparieren, sonst waechst der Rueckstand."
    )


def readme_version(text: str) -> "str | None":
    """Version aus der Marker-Zeile des README, oder None."""
    match = _README_VERSION_RE.search(text)
    return match.group(1) if match else None


def check_readme_version(manifest_version: str, readme_text: str) -> "tuple[bool, str]":
    """README-Version gegen plugin.json (Issue #195).

    Das README nannte ueber Monate 3.9.0, waehrend 3.27.x ausgeliefert wurde —
    weil nichts es geprueft hat. Es ist die Datei, die ein Fremder zuerst
    liest; eine falsche Zahl dort ist teurer als in jeder internen Datei.
    """
    found = readme_version(readme_text)
    if found is None:
        return False, "Keine '**Version**:'-Zeile im README gefunden"
    if found != manifest_version:
        return False, (f"README sagt {found}, plugin.json {manifest_version}")
    return True, f"Version {manifest_version} auch im README"


def check_tag_free(tag: str) -> "tuple[bool, str]":
    _git("fetch", "origin", "--tags", "--quiet")
    result = _git("tag", "--list", tag)
    if result.stdout.strip():
        return False, f"Tag '{tag}' existiert bereits — Version bumpen"
    return True, f"Tag '{tag}' noch frei"


def check_skills_sync() -> "tuple[bool, str]":
    """skills/ muss exakt dem Generat aus core/commands entsprechen.

    Das Plugin liefert nur skills/ aus; eine Aenderung, die nur in
    core/commands steht, erreicht keinen Nutzer (3.18–3.22 so passiert).
    """
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import sync_skills

    drift = sync_skills.check()
    if drift:
        return False, (f"Skills weichen von core/commands ab ({', '.join(drift)}) — "
                       "python3 scripts/sync_skills.py ausführen")
    return True, "skills/ synchron mit core/commands"


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
    parser.add_argument("--content-only", action="store_true",
                        help="Nur die inhaltlichen Pruefungen — fuer den Pull "
                             "Request, wo Branch/Arbeitsbaum/Abgleich nie "
                             "erfuellt sein koennen (Issue #204)")
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

    # Zwei Gruppen, inhaltlich getrennt (Issue #204):
    #
    #   Zustand  — beschreibt den Release-Lauf selbst (steht er auf main, ist
    #              der Baum sauber, ist er synchron). Im Pull Request per
    #              Definition nicht erfuellbar.
    #   Inhalt   — beschreibt den Commit (Versionen konsistent, Skills
    #              synchron, letztes Release draussen). Gilt auf jedem Branch
    #              und laeuft deshalb schon im Pull Request, wo ein rotes Kreuz
    #              gesehen wird — anders als ein roter Job nach dem Merge.
    content_checks = [
        ("Version", check_version_match(version, latest_changelog_version(CHANGELOG.read_text()))),
        ("README", check_readme_version(version, README.read_text())),
        ("Skills", check_skills_sync()),
        ("Release", check_main_release_published(
            main_plugin_version(), latest_tagged_version(all_tags(), name))),
    ]

    if args.content_only:
        checks = content_checks
    else:
        checks = [
            ("Branch", check_branch()),
            ("Arbeitsbaum", check_clean_tree()),
            ("Abgleich", check_in_sync()),
            # Die Release-Pruefung entfaellt hier: Beim Release steht auf main
            # genau die Version, die dieser Lauf gerade taggt — sie hat noch
            # keinen Tag, und das ist der Normalfall.
            *[c for c in content_checks if c[0] != "Release"],
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
        reason = ("dieser Stand wuerde das Release blockieren"
                  if args.content_only
                  else "kein Release aus diesem Stand")
        print(f"ABBRUCH: {failed} Pruefung(en) gescheitert — {reason}.",
              file=sys.stderr)
        return 1
    if args.content_only:
        print(f"Inhalt in Ordnung — Version {version} ist release-faehig.")
        return 0
    print(f"Bereit fuer Release {version}. Tag: {tag}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
