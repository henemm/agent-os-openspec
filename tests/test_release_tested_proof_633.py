"""Tests fuer den Tested-Nachweis im Release (Issue #633).

Nach dem Merge eines Release-PRs wiederholte `release.yml` die volle Testsuite,
obwohl derselbe Baum im PR schon gruen war. Der neue Modus
`release_check.py --tested-proof <sha>` weist nach, dass der veroeffentlichte
Baum exakt der im PR gruen getestete ist; nur dann entfaellt die Wiederholung.
Fail-closed: jede Unsicherheit ergibt `PROOF=no` und damit die volle Suite.

Teststil wie `tests/test_release_check_93.py`:
- Die Entscheidung `decide_tested_proof` ist pur; GitHub-Antworten werden als
  Python-Daten in der Form der API eingespeist (kein Mock-Objekt).
- Der Baumvergleich laeuft gegen echte Git-Repos auf `tmp_path`, inklusive
  `refs/pull/<N>/head` im Origin, wie GitHub ihn anlegt.
- `gh` ist die Netzgrenze: ein kleines Ersatz-Programm auf einem eigenen PATH
  liefert die API-Antworten aus Dateien (oder fehlt bzw. liefert Muell).
"""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
RELEASE_YML = REPO_ROOT / ".github" / "workflows" / "release.yml"
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import release_check  # noqa: E402


# --------------------------------------------------------------------------
# Hilfen
# --------------------------------------------------------------------------

MERGE_SHA = "a" * 40
HEAD_SHA = "c1f70ac" + "0" * 33
TREE = "7" * 40


def _git(args: list, cwd: Path) -> str:
    result = subprocess.run(["git", *args], cwd=str(cwd), check=True,
                            capture_output=True, text=True)
    return result.stdout.strip()


def _pr(number=631, merged=True, merge_sha=MERGE_SHA, head_sha=HEAD_SHA) -> dict:
    """PR-Eintrag in der Form von GET /repos/{o}/{r}/commits/{sha}/pulls."""
    return {
        "number": number,
        "state": "closed" if merged else "open",
        "merged_at": "2026-11-21T10:00:00Z" if merged else None,
        "merge_commit_sha": merge_sha,
        "head": {"sha": head_sha, "ref": f"branch-{number}"},
    }


def _run(name="tests", status="completed", conclusion="success", head_sha=HEAD_SHA) -> dict:
    """Check-Run in der Form eines Eintrags aus `check_runs` der Check-Runs-API."""
    return {"name": name, "status": status, "conclusion": conclusion, "head_sha": head_sha}


def _decide(prs, runs, head_tree=TREE, merge_tree=TREE, sha=MERGE_SHA):
    return release_check.decide_tested_proof(sha, prs, runs, head_tree, merge_tree)


def _assert_no(result, label: str) -> str:
    assert isinstance(result, tuple) and len(result) == 2, f"{label}: (bool, str) erwartet"
    ok, reason = result
    assert ok is False, f"{label}: erwartet no, bekam yes ({reason})"
    assert isinstance(reason, str) and reason.strip(), f"{label}: Grund fehlt"
    return reason


def _init_identity(repo: Path) -> None:
    _git(["config", "user.email", "test@example.invalid"], repo)
    _git(["config", "user.name", "Test"], repo)
    _git(["config", "commit.gpgsign", "false"], repo)


def _make_scenario(tmp_path: Path, main_moved: bool, pr_number: int = 7) -> dict:
    """Origin + Release-Checkout mit einem squash-gemergten PR.

    main_moved=False: der Branch ist aktuell, der Squash-Merge-Commit hat
    denselben Baum wie der PR-Head. main_moved=True: main ging nach dem
    Abzweigen weiter, der Merge-Commit enthaelt mehr als der getestete Head.

    Der Head liegt im Origin nur unter refs/pull/<N>/head (der Branch ist nach
    dem Merge geloescht); der Release-Checkout kennt ihn erst nach dem Fetch.
    """
    tmp_path.mkdir(parents=True, exist_ok=True)
    origin = tmp_path / "origin.git"
    _git(["init", "--bare", "-b", "main", str(origin)], tmp_path)

    dev = tmp_path / "dev"
    dev.mkdir()
    _git(["init", "-b", "main"], dev)
    _init_identity(dev)
    (dev / "README.md").write_text("# x\n")
    _git(["add", "-A"], dev)
    _git(["commit", "-m", "init"], dev)
    _git(["remote", "add", "origin", str(origin)], dev)
    _git(["push", "-u", "origin", "main"], dev)

    _git(["checkout", "-b", "feature"], dev)
    (dev / "feature.txt").write_text("neu\n")
    _git(["add", "-A"], dev)
    _git(["commit", "-m", "feature"], dev)
    head_sha = _git(["rev-parse", "HEAD"], dev)
    _git(["push", "origin", f"feature:refs/pull/{pr_number}/head"], dev)

    _git(["checkout", "main"], dev)
    if main_moved:
        (dev / "woanders.txt").write_text("zwischenzeitlich auf main\n")
        _git(["add", "-A"], dev)
        _git(["commit", "-m", "main ging weiter"], dev)
    _git(["merge", "--squash", "feature"], dev)
    _git(["commit", "-m", f"Squash PR #{pr_number}"], dev)
    _git(["push", "origin", "main"], dev)
    merge_sha = _git(["rev-parse", "HEAD"], dev)

    release = tmp_path / "release"
    _git(["clone", str(origin), str(release)], tmp_path)
    _init_identity(release)

    return {
        "origin": origin,
        "dev": dev,
        "release": release,
        "head_sha": head_sha,
        "merge_sha": merge_sha,
        "pr_number": pr_number,
        "head_tree": _git(["rev-parse", f"{head_sha}^{{tree}}"], dev),
        "merge_tree": _git(["rev-parse", f"{merge_sha}^{{tree}}"], dev),
    }


_FAKE_GH = """#!{python}
import os, sys
args = " ".join(sys.argv[1:])
if os.environ.get("FAKE_GH_FAIL"):
    sys.stderr.write("gh: HTTP 500\\n")
    sys.exit(1)
if "check-runs" in args:
    path = os.environ.get("FAKE_GH_CHECKS", "")
elif "/pulls" in args:
    path = os.environ.get("FAKE_GH_PULLS", "")
else:
    sys.stderr.write("gh: unerwarteter Aufruf: " + args + "\\n")
    sys.exit(1)
with open(path, encoding="utf-8") as fh:
    sys.stdout.write(fh.read())
"""


def _bin_dir(tmp_path: Path, with_gh: bool) -> Path:
    """Eigener PATH: nur git und sh, optional das gh-Ersatzprogramm.

    So ist `gh` garantiert fehlend bzw. garantiert das Ersatzprogramm, egal was
    auf der Maschine installiert ist.
    """
    bindir = tmp_path / ("bin-gh" if with_gh else "bin-nogh")
    bindir.mkdir(exist_ok=True)
    for tool in ("git", "sh"):
        target = shutil.which(tool)
        assert target, f"{tool} fehlt auf dem Testrechner"
        link = bindir / tool
        if not link.exists():
            link.symlink_to(target)
    if with_gh:
        gh = bindir / "gh"
        gh.write_text(_FAKE_GH.format(python=sys.executable))
        gh.chmod(0o755)
    return bindir


def _write_api(tmp_path: Path, pulls, checks) -> tuple:
    pulls_file = tmp_path / "api-pulls.json"
    checks_file = tmp_path / "api-checks.json"
    pulls_file.write_text(pulls if isinstance(pulls, str) else json.dumps(pulls))
    checks_file.write_text(checks if isinstance(checks, str) else json.dumps(checks))
    return pulls_file, checks_file


def _green_api(scn: dict) -> tuple:
    pulls = [_pr(number=scn["pr_number"], merge_sha=scn["merge_sha"], head_sha=scn["head_sha"])]
    checks = {"total_count": 1,
              "check_runs": [_run(head_sha=scn["head_sha"])]}
    return pulls, checks


def _run_cli(monkeypatch, capsys, repo: Path, sha: str) -> tuple:
    """`release_check.py --tested-proof <sha>` im Prozess gegen `repo`.

    Liefert (Exit-Code, PROOF-Wert, REASON-Text, alle stdout-Zeilen). Eine
    Ausnahme aus main() laesst den Test scheitern (AC-5: keine nach aussen).
    """
    monkeypatch.setattr(release_check, "REPO_ROOT", repo)
    monkeypatch.setattr(sys, "argv", ["release_check.py", "--tested-proof", sha])
    code = release_check.main()
    out = capsys.readouterr().out
    lines = [ln for ln in out.splitlines() if ln.strip()]
    proof = [ln for ln in lines if ln.startswith("PROOF=")]
    reason = [ln for ln in lines if ln.startswith("REASON=")]
    assert len(proof) == 1, f"genau eine PROOF=-Zeile erwartet: {out!r}"
    assert len(reason) == 1, f"genau eine REASON=-Zeile erwartet: {out!r}"
    assert len(lines) == 2, f"Modus druckt genau PROOF= und REASON=: {out!r}"
    return code, proof[0][len("PROOF="):], reason[0][len("REASON="):], lines


def _setup_cli_env(monkeypatch, tmp_path, scn, with_gh=True, token=True,
                   pulls=None, checks=None, fail=False) -> None:
    monkeypatch.setenv("PATH", str(_bin_dir(tmp_path, with_gh)))
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    if token:
        monkeypatch.setenv("GH_TOKEN", "ghs_testtoken_nicht_echt")
    green_pulls, green_checks = _green_api(scn)
    pulls_file, checks_file = _write_api(
        tmp_path,
        green_pulls if pulls is None else pulls,
        green_checks if checks is None else checks,
    )
    monkeypatch.setenv("FAKE_GH_PULLS", str(pulls_file))
    monkeypatch.setenv("FAKE_GH_CHECKS", str(checks_file))
    if fail:
        monkeypatch.setenv("FAKE_GH_FAIL", "1")
    else:
        monkeypatch.delenv("FAKE_GH_FAIL", raising=False)


# --------------------------------------------------------------------------
# AC-1
# --------------------------------------------------------------------------

def test_nachweis_yes_nur_wenn_alle_bedingungen_erfuellt():
    """AC-1: genau ein passender gemergter PR, gruener `tests`-Run auf dessen
    Head, gleiche Baeume -> yes, Grund nennt PR und Head. Faellt eine
    Bedingung weg (leerer oder abweichender Baum), ist es no."""
    prs = [_pr()]
    # Andere Check-Runs (anderer Name) zaehlen nicht mit, auch wenn rot.
    runs = [_run(), _run(name="spec-gate", conclusion="failure")]

    result = _decide(prs, runs)
    assert isinstance(result, tuple) and len(result) == 2, "(bool, str) erwartet"
    ok, reason = result
    assert ok is True, f"alle Bedingungen erfuellt, erwartet yes: {reason}"
    assert "631" in reason, f"Grund muss den PR nennen: {reason}"
    assert HEAD_SHA[:7] in reason, f"Grund muss den Head nennen: {reason}"

    # Nur wenn ALLE gelten: die Baum-Bedingung allein kippt das Ergebnis.
    _assert_no(_decide(prs, runs, head_tree=""), "leerer Head-Baum")
    _assert_no(_decide(prs, runs, merge_tree=""), "leerer Merge-Baum")
    _assert_no(_decide(prs, runs, head_tree=None), "Head-Baum None")
    _assert_no(_decide(prs, runs, head_tree="8" * 40), "abweichender Baum")


# --------------------------------------------------------------------------
# AC-2
# --------------------------------------------------------------------------

def test_nachweis_no_bei_pr_mehrdeutig_oder_fehlend():
    """AC-2: kein PR, mehrere passende, ungemergt oder anderer merge_commit_sha
    -> no mit Grund; fremde PRs in der Liste zaehlen nicht als passend."""
    runs = [_run()]

    _assert_no(_decide([], runs), "kein PR")
    _assert_no(_decide([_pr(number=631), _pr(number=632)], runs), "zwei passende PRs")
    _assert_no(_decide([_pr(merged=False)], runs), "PR ohne merged_at")
    _assert_no(_decide([_pr(merge_sha="b" * 40)], runs), "anderer merge_commit_sha")
    _assert_no(
        _decide([_pr(number=500, merge_sha="b" * 40), _pr(number=501, merged=False)], runs),
        "nur fremde PRs",
    )

    # Fremde PRs neben genau einem passenden stoeren nicht.
    mixed = [
        _pr(number=500, merge_sha="b" * 40, head_sha="d" * 40),
        _pr(number=631),
        _pr(number=501, merged=False, merge_sha="e" * 40, head_sha="f" * 40),
    ]
    ok, reason = _decide(mixed, runs)
    assert ok is True, f"fremde PRs duerfen nicht als passend zaehlen: {reason}"
    assert "631" in reason


# --------------------------------------------------------------------------
# AC-3
# --------------------------------------------------------------------------

def test_nachweis_no_bei_check_fehlt_laeuft_oder_rot():
    """AC-3: `tests`-Run fehlt, laeuft noch, ist rot oder einer von mehreren
    `tests`-Runs ist nicht erfolgreich -> no mit Grund."""
    prs = [_pr()]

    _assert_no(_decide(prs, []), "keine Check-Runs")
    _assert_no(_decide(prs, [_run(name="lint")]), "nur ein anders benannter Run")
    _assert_no(_decide(prs, [_run(status="in_progress", conclusion=None)]), "laeuft noch")
    _assert_no(_decide(prs, [_run(status="queued", conclusion=None)]), "wartet")
    _assert_no(_decide(prs, [_run(conclusion="failure")]), "rot")
    _assert_no(_decide(prs, [_run(conclusion="cancelled")]), "abgebrochen")
    _assert_no(_decide(prs, [_run(conclusion="skipped")]), "uebersprungen")
    _assert_no(_decide(prs, [_run(), _run(conclusion="failure")]), "einer von zwei rot")
    _assert_no(
        _decide(prs, [_run(), _run(status="in_progress", conclusion=None)]),
        "einer von zwei laeuft noch",
    )

    ok, reason = _decide(prs, [_run(), _run()])
    assert ok is True, f"zwei gruene tests-Runs sind ein Nachweis: {reason}"


# --------------------------------------------------------------------------
# AC-4
# --------------------------------------------------------------------------

def test_baumvergleich_auf_echten_git_repos(tmp_path, monkeypatch, capsys):
    """AC-4: echte Repos. Squash eines aktuellen Branches -> gleicher Baum ->
    yes; main ging zwischenzeitlich weiter -> abweichender Baum -> no mit
    Grund "Baum". Einmal direkt ueber die Entscheidung mit den von Git
    gelesenen Baum-SHAs, einmal ueber den Abruf (gh-Ersatz + git fetch des
    PR-Heads aus refs/pull/<N>/head) im CLI-Modus."""
    same = _make_scenario(tmp_path / "gleich", main_moved=False)
    moved = _make_scenario(tmp_path / "weiter", main_moved=True)

    # Vorbedingung der Szenarien selbst (nicht Teil des Pruefgegenstands).
    assert same["head_tree"] == same["merge_tree"]
    assert moved["head_tree"] != moved["merge_tree"]

    def decide(scn):
        prs = [_pr(number=scn["pr_number"], merge_sha=scn["merge_sha"], head_sha=scn["head_sha"])]
        runs = [_run(head_sha=scn["head_sha"])]
        return release_check.decide_tested_proof(
            scn["merge_sha"], prs, runs, scn["head_tree"], scn["merge_tree"])

    ok, reason = decide(same)
    assert ok is True, reason
    reason = _assert_no(decide(moved), "main ging weiter")
    assert "Baum" in reason, f"Grund muss den Baum nennen: {reason}"

    # Ueber den Abruf: der Release-Checkout kennt den Head erst nach dem Fetch.
    probe = subprocess.run(["git", "cat-file", "-e", same["head_sha"]],
                           cwd=str(same["release"]), capture_output=True)
    assert probe.returncode != 0, "Head darf im Release-Checkout vorab nicht bekannt sein"

    (tmp_path / "gleich" / "api").mkdir()
    _setup_cli_env(monkeypatch, tmp_path / "gleich" / "api", same)
    code, proof, reason, _ = _run_cli(monkeypatch, capsys, same["release"], same["merge_sha"])
    assert code == 0
    assert proof == "yes", f"gleicher Baum muss yes ergeben: {reason}"

    (tmp_path / "weiter" / "api").mkdir()
    _setup_cli_env(monkeypatch, tmp_path / "weiter" / "api", moved)
    code, proof, reason, _ = _run_cli(monkeypatch, capsys, moved["release"], moved["merge_sha"])
    assert code == 0
    assert proof == "no", f"abweichender Baum muss no ergeben: {reason}"
    assert "Baum" in reason, f"Grund muss den Baum nennen: {reason}"


# --------------------------------------------------------------------------
# AC-5
# --------------------------------------------------------------------------

def test_cli_fail_closed_bei_abruffehler(tmp_path, monkeypatch, capsys):
    """AC-5: fehlendes gh, kein Token, nicht parsbare Antwort, gh-Fehler,
    fehlgeschlagener git fetch -> PROOF=no, REASON=<Grund>, Exit 0, keine
    Ausnahme nach aussen. Jeder Fall laeuft gegen ein Szenario, das mit
    funktionierendem Abruf yes ergaebe; nur der eine Fehler macht es zu no."""
    scn = _make_scenario(tmp_path / "repo", main_moved=False)

    def case(label, **env):
        api = tmp_path / f"api-{label}"
        api.mkdir()
        _setup_cli_env(monkeypatch, api, scn, **env)
        code, proof, reason, _ = _run_cli(monkeypatch, capsys, scn["release"], scn["merge_sha"])
        assert code == 0, f"{label}: Exit-Code muss 0 sein, war {code}"
        assert proof == "no", f"{label}: erwartet PROOF=no, bekam {proof} ({reason})"
        assert reason.strip(), f"{label}: REASON leer"
        return reason

    # Gegenprobe: derselbe Aufbau mit funktionierendem Abruf ist yes — sonst
    # wuerden die Fehlerfaelle unten nichts belegen.
    api_ok = tmp_path / "api-ok"
    api_ok.mkdir()
    _setup_cli_env(monkeypatch, api_ok, scn)
    code, proof, reason, _ = _run_cli(monkeypatch, capsys, scn["release"], scn["merge_sha"])
    assert (code, proof) == (0, "yes"), f"Gegenprobe muss yes sein: {reason}"

    case("ohne-gh", with_gh=False)
    case("ohne-token", token=False)
    case("muell-pulls", pulls="<html>kein json</html>")
    case("muell-checks", checks="{nicht: json")
    case("checks-ohne-liste", checks=json.dumps({"message": "Not Found"}))
    case("gh-fehler", fail=True)
    bad_pr = [_pr(number=99, merge_sha=scn["merge_sha"], head_sha=scn["head_sha"])]
    case("fetch-scheitert", pulls=bad_pr)  # refs/pull/99/head gibt es im Origin nicht

    # Echter Prozess: der Exit-Code der Kommandozeile selbst ist 0.
    env = dict(os.environ)
    env["PATH"] = str(_bin_dir(tmp_path, with_gh=False))
    env.pop("GH_TOKEN", None)
    env.pop("GITHUB_TOKEN", None)
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "release_check.py"),
         "--tested-proof", scn["merge_sha"]],
        cwd=str(scn["release"]), env=env, capture_output=True, text=True,
    )
    assert proc.returncode == 0, f"Exit-Code {proc.returncode}: {proc.stderr}"
    lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    assert "PROOF=no" in lines, proc.stdout
    assert any(ln.startswith("REASON=") and len(ln) > len("REASON=") for ln in lines), proc.stdout
    assert "Traceback" not in proc.stderr, proc.stderr


# --------------------------------------------------------------------------
# AC-6
# --------------------------------------------------------------------------

def _norm(text) -> str:
    return re.sub(r"\s+", " ", str(text or "").replace('"', "'")).strip()


def _release_steps() -> tuple:
    data = yaml.safe_load(RELEASE_YML.read_text())
    job = data["jobs"]["release"]
    return data, job, job["steps"]


def test_release_workflow_struktur_proof_steuert_suite():
    """AC-6: volle Suite nur bei proof != 'yes', --no-tests nur bei
    proof == 'yes'; Nachweis-Schritt mit GH_TOKEN und
    --tested-proof ${{ github.sha }}; Berechtigungen checks/pull-requests: read."""
    data, job, steps = _release_steps()

    perms = dict(data.get("permissions") or {})
    perms.update(job.get("permissions") or {})
    assert perms.get("checks") == "read", f"checks: read fehlt: {perms}"
    assert perms.get("pull-requests") == "read", f"pull-requests: read fehlt: {perms}"
    assert perms.get("contents") == "write", "contents: write (Tag/Release) muss bleiben"

    proof_idx = [i for i, s in enumerate(steps) if "--tested-proof" in str(s.get("run", ""))]
    assert len(proof_idx) == 1, "genau ein Nachweis-Schritt mit --tested-proof erwartet"
    proof_step = steps[proof_idx[0]]
    assert "--tested-proof ${{ github.sha }}" in _norm(proof_step["run"]), proof_step["run"]
    assert "GITHUB_OUTPUT" in proof_step["run"] and "proof=" in proof_step["run"], \
        "Nachweis-Schritt muss proof=... nach $GITHUB_OUTPUT schreiben"
    assert (proof_step.get("env") or {}).get("GH_TOKEN"), "Nachweis-Schritt braucht GH_TOKEN"
    step_id = proof_step.get("id")
    assert step_id, "Nachweis-Schritt braucht eine id, damit die Folgeschritte proof lesen"

    flags = ("--no-tests", "--notes", "--tag", "--tested-proof", "--pr-gate")
    full = [i for i, s in enumerate(steps)
            if "release_check.py" in str(s.get("run", ""))
            and not any(f in str(s.get("run", "")) for f in flags)]
    quick = [i for i, s in enumerate(steps) if "release_check.py --no-tests" in _norm(s.get("run"))]
    assert len(full) == 1, "genau ein Schritt mit voller Suite (release_check.py ohne Flag)"
    assert len(quick) == 1, "genau ein Schritt mit release_check.py --no-tests"

    ne = re.compile(rf"steps\.{re.escape(step_id)}\.outputs\.proof\s*!=\s*'yes'")
    eq = re.compile(rf"steps\.{re.escape(step_id)}\.outputs\.proof\s*==\s*'yes'")
    full_if = _norm(steps[full[0]].get("if"))
    quick_if = _norm(steps[quick[0]].get("if"))
    assert ne.search(full_if) and not eq.search(full_if), \
        f"volle Suite nur bei proof != 'yes': {full_if!r}"
    assert eq.search(quick_if) and not ne.search(quick_if), \
        f"--no-tests nur bei proof == 'yes': {quick_if!r}"

    # Beide Pruefschritte bleiben an "Version noch nicht veroeffentlicht"
    # gebunden — sonst scheitert check_tag_free bei jedem gewoehnlichen Push.
    for label, cond in (("volle Suite", full_if), ("--no-tests", quick_if)):
        assert "steps.version.outputs.needed == 'true'" in cond, \
            f"{label}: Bedingung needed == 'true' fehlt: {cond!r}"

    assert proof_idx[0] < min(full[0], quick[0]), "Nachweis muss vor den Pruefschritten laufen"


# --------------------------------------------------------------------------
# AC-7
# --------------------------------------------------------------------------

@pytest.fixture
def release_repo(tmp_path, monkeypatch):
    """Sauberer main-Stand mit passenden Versionsdateien, wie in test_release_check_93."""
    origin = tmp_path / "origin.git"
    _git(["init", "--bare", "-b", "main", str(origin)], tmp_path)
    work = tmp_path / "work"
    work.mkdir()
    _git(["init", "-b", "main"], work)
    _init_identity(work)
    (work / ".claude-plugin").mkdir()
    (work / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"name": "agent-os-openspec", "version": "1.0.0"}))
    (work / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [Unreleased]\n\n## [1.0.0] - 2026-11-21\n\n- x\n")
    (work / "README.md").write_text("**Version**: 1.0.0 · [Changelog](CHANGELOG.md)\n")
    (work / "CLAUDE.md").write_text("# Projekt\n\n**Version**: 1.0.0\n")
    _git(["add", "-A"], work)
    _git(["commit", "-m", "release 1.0.0"], work)
    _git(["remote", "add", "origin", str(origin)], work)
    _git(["push", "-u", "origin", "main"], work)

    monkeypatch.setattr(release_check, "REPO_ROOT", work)
    monkeypatch.setattr(release_check, "PLUGIN_JSON", work / ".claude-plugin" / "plugin.json")
    monkeypatch.setattr(release_check, "CHANGELOG", work / "CHANGELOG.md")
    monkeypatch.setattr(release_check, "README", work / "README.md")
    monkeypatch.setattr(release_check, "CLAUDE_MD", work / "CLAUDE.md")
    return work


def test_inhaltliche_pruefungen_laufen_auch_ohne_suite(release_repo, monkeypatch, capsys):
    """AC-7: Im Fall PROOF=yes ruft release.yml den Waechter ohne Suite auf;
    alle inhaltlichen Pruefungen laufen trotzdem, nur die Suite entfaellt.
    Die bestehenden Modi und tests/test_release_check_93.py bleiben gruen."""
    _, _, steps = _release_steps()
    quick = [s for s in steps if "release_check.py --no-tests" in _norm(s.get("run"))
             and "proof" in _norm(s.get("if"))]
    assert len(quick) == 1, "release.yml: Schritt fuer den Fall PROOF=yes fehlt"
    cmd = _norm(quick[0]["run"])
    args = cmd.split("release_check.py", 1)[1].split()
    assert args == ["--no-tests"], f"PROOF=yes-Schritt darf nur die Suite auslassen: {cmd!r}"

    suite_calls = []

    def _suite_sentinel():
        suite_calls.append(True)
        return True, "Suite gelaufen"

    monkeypatch.setattr(release_check, "check_tests", _suite_sentinel)
    monkeypatch.setattr(sys, "argv", ["release_check.py", *args])
    release_check.main()
    out = capsys.readouterr().out

    for label in ("Branch", "Arbeitsbaum", "Abgleich", "Version", "README", "CLAUDE.md",
                  "Tag", "Skills", "Cloud-Hooks", "Cloud-Agenten"):
        assert re.search(rf"^\s*(OK|FAIL)\s+{re.escape(label)}\s", out, re.MULTILINE), \
            f"inhaltliche Pruefung '{label}' lief nicht:\n{out}"
    assert not suite_calls, "im Fall PROOF=yes darf die Suite nicht laufen"
    assert not re.search(r"^\s*(OK|FAIL)\s+Tests\s", out, re.MULTILINE), out

    # Bestehende Modi unveraendert.
    monkeypatch.setattr(sys, "argv", ["release_check.py", "--tag"])
    assert release_check.main() == 0
    assert capsys.readouterr().out.strip() == "agent-os-openspec--v1.0.0"
    monkeypatch.setattr(sys, "argv", ["release_check.py", "--notes"])
    assert release_check.main() == 0
    assert "- x" in capsys.readouterr().out
    monkeypatch.setattr(sys, "argv", ["release_check.py", "--pr-gate"])
    assert release_check.main() == 1, "--pr-gate ohne --base bleibt ein Fehler"
    capsys.readouterr()

    # Regression des Waechters aus #93.
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_release_check_93.py", "-q",
         "-p", "no:cacheprovider"],
        cwd=str(REPO_ROOT), capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stdout[-2000:]
