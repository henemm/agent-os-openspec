"""Naechster Vorschlag nach dem Abschluss (Issue #589, Teil A).

Spec: docs/specs/feat-589-naechster-vorschlag.md (AC-1 bis AC-17).

Vertraege, die diese Tests festlegen (Spec laesst sie offen, der Test entscheidet):

- Modul `core/hooks/next_suggestion.py`:
  - `choose(raw, done_number, claimed, spur=None, now=None)` -> `None` oder
    `{"n": int, "source": "epic"|"milestone"|"related"|"priority", "reason": str,
    "title": str}`; `title` ist der Kurztitel (<= 60 Zeichen), `reason` der Text in
    Klammern der Zeile: `"<Quelle in Alltagssprache>: <title>"` (SOURCE_TEXT unten).
  - `claimed`: Iterable aus int oder str; ein str ist der rohe `issue`-Wert des
    Session-Registers, also auch eine Komma-Liste ("711,712").
  - Form von `raw` (REST-Antworten von `gh api`, unveraendert gespeichert):
        {"done":       <issues/<N>>              Issue-Objekt der erledigten oder None,
         "parent":     <issues/<N>/parent>       Issue-Objekt oder None (HTTP 404),
         "sub_issues": <issues/<P>/sub_issues>   Liste ([] ohne Eltern),
         "issues":     <issues?state=open&per_page=100>  Liste (enthaelt PRs),
         "milestones": <milestones?state=open>   Liste,
         "pulls":      <pulls?state=open>        Liste (optional, [] bei Fehler)}
    Issue-Objekt: `number`, `title`, `state`, `labels` [{"name"}], `milestone`
    ({"number", "title", "due_on"} oder None), `body`, optional `pull_request`,
    optional `sub_issues_summary` {"total", "completed"} (offen = total - completed).
    Zusaetzlich zur Aufrufliste der Spec holt `fetch` also `issues/<N>` (REST): nur
    dort steht der Meilenstein der erledigten Aufgabe.
  - `fetch(root, done_number, timeout_s=...)` -> raw oder None (nie Ausnahme);
    `issues/<N>/parent` mit HTTP 404 bedeutet "kein Eltern-Issue", nicht Fehler.
  - `write_cache(root, done_number, raw, now=None)`,
    `read_cache(root, done_number, ttl_s=300, now=None)` -> raw oder None;
    Datei `<root>/.claude/next_suggestion.json`, atomar ersetzt.
  - `settings(config=None)` -> `{"enabled": bool, "timeout_s": Zahl, "cache_ttl_s": 300}`.
- `workflow.end_state(..., suggest=<choose-Ergebnis>|None)`; `queue_end_args(data)`
  liefert den Vorschlag aus dem Cache (Schluesselname frei, er muss nur in
  `end_state(**queue_end_args(data))` passen).
- Eigene Sitzung = `CLAUDE_CODE_SESSION_ID`; deren Claim schliesst nichts aus.

Kein Netz: `gh` ist ein Stub-Skript im PATH (`tmp_path`), das jeden Aufruf
protokolliert und je REST-Pfad feste JSON-Antworten liefert. Das Modul wird erst im
Testkoerper importiert, CLI und Hooks laufen als Subprozess: fehlende Funktionen
erscheinen als Test-FAIL, nicht als Collection-Error.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_auftrag_551 import (  # noqa: E402
    WAIT_548, YOU_548, _active_project, _auftrag_path, _cli, _data, _env, _kv,
    _read_auftrag, _write_auftrag,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
COMMANDS_DIR = REPO_ROOT / "core" / "commands"
SKILLS_DIR = REPO_ROOT / "skills"

DONE = 547  # _data() aus test_auftrag_551 heisst feat-547-x
TODAY = f"✅ Erledigt: #{DONE} ist fertig. Du kannst /clear ausführen und das nächste Issue starten."
SOURCE_TEXT = {"epic": "gleiche Sammelaufgabe", "milestone": "gleicher Meilenstein",
               "related": "knüpft an eine Aufgabe an", "priority": "wichtigste offene Aufgabe"}
EXPECT = {"epic": 610, "milestone": 620, "related": 630, "priority": 640}
SUGGEST_KEYS = ("SUGGEST_ISSUE", "SUGGEST_SOURCE", "SUGGEST_REASON")

MS3 = {"number": 3, "title": "Q4 2026", "due_on": "2026-12-18T07:00:00Z", "state": "open"}
MS_EARLY = {"number": 4, "title": "Frueh", "due_on": "2026-12-01T07:00:00Z", "state": "open"}
MS_LATE = {"number": 5, "title": "Spaet", "due_on": "2027-01-01T07:00:00Z", "state": "open"}
MS_NODUE = {"number": 6, "title": "Offen", "due_on": None, "state": "open"}

GH_STUB = """#!{py}
import json, os, re, sys, time
args = sys.argv[1:]
with open(os.environ["GH_LOG"], "a") as f:
    f.write(json.dumps(args) + "\\n")
if os.environ.get("GH_SLEEP"):
    time.sleep(float(os.environ["GH_SLEEP"]))
if os.environ.get("GH_EXIT", "0") != "0":
    sys.stderr.write("gh: Server Error (HTTP 500)\\n")
    sys.exit(int(os.environ["GH_EXIT"]))
if not args or args[0] != "api":
    sys.stderr.write("stub: nur gh api\\n")
    sys.exit(4)
path = next((a for a in args[1:] if re.match(r"^/?(repos/|issues|milestones|pulls)", a)), "")
p = path.lstrip("/")
if p.startswith("repos/"):
    p = p.split("/", 3)[3] if p.count("/") >= 3 else ""
key = p.split("?")[0]
if os.environ.get("GH_BROKEN"):
    print("{{kaputt")
    sys.exit(0)
fixtures = json.loads(open(os.environ["GH_FIXTURES"]).read())
if key in fixtures:
    print(json.dumps(fixtures[key]))
    sys.exit(0)
sys.stderr.write("gh: Not Found (HTTP 404)\\n")
sys.exit(1)
"""


# --- Helfer ------------------------------------------------------------------

def _ns():
    sys.path.insert(0, str(HOOKS_DIR))
    import next_suggestion  # noqa: PLC0415
    return next_suggestion


def _wf():
    sys.path.insert(0, str(HOOKS_DIR))
    import workflow  # noqa: PLC0415
    return workflow


def _iss(n, title=None, labels=(), ms=None, body="", state="open", **extra) -> dict:
    data = {"number": n, "title": title or f"Aufgabe {n}", "state": state,
            "labels": [{"name": name} for name in labels], "milestone": ms, "body": body}
    data.update(extra)
    return data


def _world(kind: str) -> dict:
    """REST-Antworten je Pfad (ohne `repos/{owner}/{repo}/`) fuer den gh-Stub."""
    done = _iss(DONE, "Erledigte Aufgabe", state="closed",
                ms=MS3 if kind == "milestone" else None)
    fx = {f"issues/{DONE}": done, "milestones": [MS3], "pulls": []}
    issues = []
    if kind == "epic":
        fx[f"issues/{DONE}/parent"] = _iss(500, "Sammelaufgabe", labels=["epic"])
        fx["issues/500/sub_issues"] = [done, _iss(610, "Plan zeigt Vorschlag"),
                                       _iss(611, "Schon erledigt", state="closed")]
        issues.append(_iss(610, "Plan zeigt Vorschlag"))
    if kind in ("epic", "milestone", "related"):
        issues.append(_iss(620, "Meilenstein Aufgabe", ms=MS3))
        issues.append(_iss(630, "Anschlussarbeit", body=f"Folge zu #{DONE}, Rest"))
    if kind != "none":
        issues.append(_iss(640, "Wichtige Aufgabe", labels=["priority:high"]))
    fx["issues"] = issues
    return fx


def _raw(fx: dict) -> dict:
    parent = fx.get(f"issues/{DONE}/parent")
    subs = fx.get(f"issues/{parent['number']}/sub_issues", []) if parent else []
    return {"done": fx.get(f"issues/{DONE}"), "parent": parent, "sub_issues": subs,
            "issues": fx.get("issues", []), "milestones": fx.get("milestones", []),
            "pulls": fx.get("pulls", [])}


def _base_raw(issues, **kw) -> dict:
    raw = {"done": _iss(DONE, state="closed"), "parent": None, "sub_issues": [],
           "issues": issues, "milestones": [MS3, MS_EARLY, MS_LATE, MS_NODUE], "pulls": []}
    raw.update(kw)
    return raw


def _stub(root: Path, fixtures: "dict | None" = None, gh: bool = True):
    """bin/gh (Stub) + Log + Fixtures; liefert (bindir, log, fixture-Datei)."""
    root.mkdir(parents=True, exist_ok=True)
    bindir = root / "bin"
    bindir.mkdir(exist_ok=True)
    log = root / "gh.log"
    fx = root / "gh_fixtures.json"
    fx.write_text(json.dumps(fixtures or {}))
    if gh:
        stub = bindir / "gh"
        stub.write_text(GH_STUB.format(py=sys.executable))
        stub.chmod(0o755)
    elif not (bindir / "python3").exists():
        (bindir / "python3").symlink_to(sys.executable)
    return bindir, log, fx


def _calls(log: Path) -> list:
    return [json.loads(ln) for ln in log.read_text().splitlines() if ln] if log.exists() else []


def _genv(proj: Path, bindir: Path, log: Path, fx: Path, gh: bool = True, **extra) -> dict:
    env = _env(proj, **extra)
    for key in ("GH_EXIT", "GH_SLEEP", "GH_BROKEN"):
        if key not in extra:
            env.pop(key, None)
    env["GH_LOG"] = str(log)
    env["GH_FIXTURES"] = str(fx)
    env["PATH"] = f"{bindir}{os.pathsep}{os.environ.get('PATH', '')}" if gh else str(bindir)
    return env


def _case(tmp_path: Path, label: str, kind: str = "epic", gh: bool = True,
          config: "str | None" = None, data: "dict | None" = None):
    """Aktiver Workflow feat-547-x in Phase 8 + gh-Stub mit Welt `kind`."""
    proj = _active_project(tmp_path / label / "proj", data or _data(), config=config)
    bindir, log, fx = _stub(tmp_path / label, _world(kind), gh=gh)
    return proj, log, _genv(proj, bindir, log, fx, gh=gh)


def _suggest_line(n: int, reason: str) -> str:
    return (f"✅ Erledigt: #{DONE} ist fertig. Du kannst /clear ausführen und mit "
            f"/00-intake #{n} weitermachen ({reason}).")


def _session_lock(proj: Path, sid: str, issue: str) -> None:
    locks = proj / ".claude" / "session-locks"
    locks.mkdir(parents=True, exist_ok=True)
    try:
        boot = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    except OSError:
        boot = None
    now = time.time()
    (locks / f"{sid}.json").write_text(json.dumps({
        "session_id": sid, "cwd": str(proj), "pid": os.getpid(), "started_at": now - 60,
        "last_seen": now, "boot_id": boot, "agent_name": sid, "branch": "x",
        "workflow": f"feat-{issue.split(',')[0]}-y", "issue": issue,
        "phase": "phase6_implement", "issue_source": "claim"}))


def _plan_tail(proj: Path, env: dict) -> str:
    res = _cli(proj, "plan", env=env)
    assert res.returncode == 0, (res.stdout, res.stderr)
    return res.stdout.rstrip("\n").splitlines()[-1]


# --- AC-1, AC-6 ----------------------------------------------------------------

class TestChooseRangfolge:
    def test_stufen_epic_vor_meilenstein_vor_verwandt_vor_prioritaet(self):
        ns = _ns()
        for kind, n in EXPECT.items():
            got = ns.choose(_raw(_world(kind)), DONE, [])
            assert got is not None, kind
            assert got["n"] == n and got["source"] == kind, (kind, got)
            assert got["reason"] == f"{SOURCE_TEXT[kind]}: {got['title']}", got
            assert got["title"] and len(got["title"]) <= 60, got

        # Alles zugleich vorhanden: Stufen fallen der Reihe nach weg
        raw = _raw(_world("epic"))
        raw["done"] = _iss(DONE, state="closed", ms=MS3)
        order = []
        for _ in range(4):
            got = ns.choose(raw, DONE, [])
            order.append((got["source"], got["n"]))
            if got["source"] == "epic":
                raw["parent"], raw["sub_issues"] = None, []
            elif got["source"] == "milestone":
                raw["done"] = _iss(DONE, state="closed")
            elif got["source"] == "related":
                raw["issues"] = [i for i in raw["issues"] if i["number"] != 630]
        assert order == [("epic", 610), ("milestone", 620), ("related", 630),
                         ("priority", 620)], order

    def test_kein_kandidat_none_und_spur_ohne_wirkung(self):
        ns = _ns()
        assert ns.choose(_raw(_world("none")), DONE, []) is None
        assert ns.choose(_base_raw([]), DONE, []) is None
        assert ns.choose(_base_raw([_iss(DONE)]), DONE, []) is None
        assert ns.choose(_raw(_world("none")), DONE, [], spur="tests") is None
        for kind in EXPECT:
            raw = _raw(_world(kind))
            assert ns.choose(raw, DONE, [], spur="tests") == ns.choose(raw, DONE, []), kind


# --- AC-2 ------------------------------------------------------------------------

class TestChooseSortierung:
    def test_meilenstein_faelligkeit_prioritaet_nummer(self):
        ns = _ns()
        issues = [
            _iss(701, labels=["priority:critical"]),
            _iss(702, ms=MS_LATE, labels=["priority:low"]),
            _iss(703, ms=MS_EARLY, labels=["priority:low"]),
            _iss(704, ms=MS_EARLY, labels=["priority:high"]),
            _iss(705, ms=MS_NODUE, labels=["priority:critical"]),
            _iss(706, ms=MS_EARLY, labels=["priority:high"]),
            _iss(708, labels=["priority:medium"]),
            _iss(690),
        ]
        raw = _base_raw(list(issues))
        order = []
        while True:
            got = ns.choose(raw, DONE, [])
            if got is None:
                break
            assert got["source"] == "priority", got
            order.append(got["n"])
            raw["issues"] = [i for i in raw["issues"] if i["number"] != got["n"]]
        assert order == [704, 706, 703, 702, 705, 701, 708, 690], order

        # Prioritaet innerhalb gleicher Lage: critical > high > medium > low > ohne
        prio = [_iss(800 + i, labels=[f"priority:{p}"] if p else [])
                for i, p in enumerate(["", "low", "medium", "high", "critical"])]
        raw = _base_raw(prio)
        order = []
        for _ in prio:
            got = ns.choose(raw, DONE, [])
            order.append(got["n"])
            raw["issues"] = [i for i in raw["issues"] if i["number"] != got["n"]]
        assert order == [804, 803, 802, 801, 800], order

        # Gleiche Sortierung auch in der Stufe Epic: Meilenstein vor ohne
        raw = _base_raw([], parent=_iss(500, labels=["epic"]),
                        sub_issues=[_iss(651), _iss(652, ms=MS_LATE)])
        got = ns.choose(raw, DONE, [])
        assert (got["source"], got["n"]) == ("epic", 652), got


# --- AC-3, AC-4 -------------------------------------------------------------------

class TestChooseAusschluesse:
    def test_ausgeschlossene_kandidaten(self):
        ns = _ns()
        crit = ["priority:critical"]
        issues = [
            _iss(DONE, labels=crit),                                   # die erledigte selbst
            _iss(711, labels=crit, state="closed"),                    # geschlossen
            _iss(712, labels=crit, pull_request={"url": "x"}),         # PR
            _iss(713, labels=crit + ["epic"]),                         # Container
            _iss(714, labels=crit + ["status:deferred"]),
            _iss(715, labels=crit + ["spec-proposal"]),
            _iss(716, labels=crit,                                     # Eltern mit offenen Subs
                 sub_issues_summary={"total": 3, "completed": 1, "percent_completed": 33}),
            _iss(717, labels=crit),                                    # offener PR
            _iss(799, labels=["priority:low"]),
        ]
        pulls = [{"number": 900, "title": "Arbeit an etwas", "body": "Closes #717",
                  "head": {"ref": "feat-x"}, "state": "open"}]
        got = ns.choose(_base_raw(issues, pulls=pulls), DONE, [])
        assert got is not None and got["n"] == 799, got
        assert got["source"] == "priority", got

        # Eltern mit erledigten Subs zaehlt als Blatt
        leaf = _iss(718, labels=crit,
                    sub_issues_summary={"total": 2, "completed": 2, "percent_completed": 100})
        got = ns.choose(_base_raw(issues + [leaf], pulls=pulls), DONE, [])
        assert got["n"] == 718, got

        # Stufe Epic: nur ausgeschlossene Geschwister -> naechste Stufe
        subs = [_iss(DONE, state="closed"), _iss(721, state="closed"),
                _iss(722, labels=["status:deferred"]), _iss(723, labels=["epic"]),
                _iss(724, pull_request={"url": "x"}), _iss(725, labels=["spec-proposal"])]
        raw = _base_raw([_iss(799)], parent=_iss(500, labels=["epic"]), sub_issues=subs)
        got = ns.choose(raw, DONE, [])
        assert (got["source"], got["n"]) == ("priority", 799), got

    def test_von_anderer_sitzung_beanspruchtes_issue(self):
        ns = _ns()
        raw = _base_raw([_iss(711, labels=["priority:critical"]),
                         _iss(712, labels=["priority:high"]),
                         _iss(713, labels=["priority:low"])])
        assert ns.choose(raw, DONE, [])["n"] == 711
        assert ns.choose(raw, DONE, [711])["n"] == 712
        assert ns.choose(raw, DONE, ["711"])["n"] == 712
        assert ns.choose(raw, DONE, ["711,712"])["n"] == 713
        assert ns.choose(raw, DONE, {"711", "712"})["n"] == 713
        assert ns.choose(raw, DONE, ["711,712,713"]) is None

        # Auch in der Stufe Epic
        raw = _base_raw([_iss(799)], parent=_iss(500, labels=["epic"]),
                        sub_issues=[_iss(651), _iss(652)])
        assert ns.choose(raw, DONE, [])["n"] == 651
        got = ns.choose(raw, DONE, ["651"])
        assert (got["source"], got["n"]) == ("epic", 652), got


# --- AC-5 --------------------------------------------------------------------------

class TestChooseVerwandt:
    def test_strenge_regex_nur_erledigte_nummer(self):
        ns = _ns()
        issues = [
            _iss(721, body=f"Folge zu #{DONE}: Rest erledigen"),
            _iss(722, body=f"Entstanden aus #{DONE} im Review."),
            _iss(723, body=f"Siehe auch #{DONE} und #12."),
            _iss(724, body=f"Folge zu #{DONE}0, anderes Thema"),
            _iss(725, body=f"Follow-up to #{DONE}"),
            _iss(726, body=f"Follow-up of #{DONE}."),
            _iss(727, body="Folge zu #54, aus #5"),
            _iss(728, body=None),
        ]
        raw = _base_raw(issues)
        related = []
        while True:
            got = ns.choose(raw, DONE, [])
            if got is None or got["source"] != "related":
                break
            related.append(got["n"])
            raw["issues"] = [i for i in raw["issues"] if i["number"] != got["n"]]
        assert sorted(related) == [721, 722, 725, 726], related
        assert got is not None and got["source"] == "priority", got
        assert got["n"] in (723, 724, 727, 728), got


# --- AC-7, AC-8 ----------------------------------------------------------------------

class TestFetch:
    def test_nur_rest_aufrufe_und_rohdaten(self, tmp_path, monkeypatch):
        ns = _ns()
        for kind in ("epic", "milestone", "none"):
            proj = tmp_path / kind / "proj"
            (proj / ".claude").mkdir(parents=True)
            fixtures = _world(kind)
            bindir, log, fx = _stub(tmp_path / kind, fixtures)
            monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ.get('PATH', '')}")
            monkeypatch.setenv("GH_LOG", str(log))
            monkeypatch.setenv("GH_FIXTURES", str(fx))
            for key in ("GH_EXIT", "GH_SLEEP", "GH_BROKEN"):
                monkeypatch.delenv(key, raising=False)

            raw = ns.fetch(proj, DONE, timeout_s=10)
            assert isinstance(raw, dict), (kind, raw)
            assert set(raw) >= {"done", "parent", "sub_issues", "issues", "milestones",
                                "pulls"}, (kind, sorted(raw))
            want = _raw(fixtures)
            assert raw["done"]["number"] == DONE, raw["done"]
            assert (raw["parent"] or {}).get("number") == (want["parent"] or {}).get("number")
            assert [i["number"] for i in raw["sub_issues"]] == \
                [i["number"] for i in want["sub_issues"]], (kind, raw["sub_issues"])
            assert [i["number"] for i in raw["issues"]] == \
                [i["number"] for i in want["issues"]], (kind, raw["issues"])
            assert [m["number"] for m in raw["milestones"]] == [3], raw["milestones"]
            assert ns.choose(raw, DONE, []) == ns.choose(want, DONE, []), kind

            calls = _calls(log)
            assert calls, kind
            for argv in calls:
                assert argv[0] == "api", argv
                assert not any("graphql" in a.lower() for a in argv), argv
            paths = " ".join(" ".join(a) for a in calls)
            assert f"issues/{DONE}/parent" in paths, paths
            assert "state=open" in paths and "milestones" in paths, paths
            if kind != "epic":
                assert "sub_issues" not in paths, (kind, paths)

    def test_fail_open_ohne_gh_fehler_timeout_json(self, tmp_path, monkeypatch):
        ns = _ns()
        proj = tmp_path / "proj"
        (proj / ".claude").mkdir(parents=True)

        # kein gh im PATH
        bindir, log, fx = _stub(tmp_path / "nogh", _world("epic"), gh=False)
        monkeypatch.setenv("PATH", str(bindir))
        assert ns.fetch(proj, DONE, timeout_s=5) is None

        cases = [("exit", {"GH_EXIT": "1"}, 5), ("broken", {"GH_BROKEN": "1"}, 5),
                 ("timeout", {"GH_SLEEP": "4"}, 1)]
        for label, extra, timeout in cases:
            bindir, log, fx = _stub(tmp_path / label, _world("epic"))
            monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ.get('PATH', '')}")
            monkeypatch.setenv("GH_LOG", str(log))
            monkeypatch.setenv("GH_FIXTURES", str(fx))
            for key in ("GH_EXIT", "GH_SLEEP", "GH_BROKEN"):
                monkeypatch.delenv(key, raising=False)
            for key, value in extra.items():
                monkeypatch.setenv(key, value)
            start = time.monotonic()
            assert ns.fetch(proj, DONE, timeout_s=timeout) is None, label
            assert time.monotonic() - start < 10, label
            assert _calls(log), label


# --- AC-9 -------------------------------------------------------------------------------

class TestCache:
    def test_atomar_ttl_schluessel_und_frisches_choose(self, tmp_path):
        ns = _ns()
        proj = tmp_path / "proj"
        (proj / ".git").mkdir(parents=True)
        (proj / ".claude").mkdir()
        raw = _raw(_world("epic"))
        path = proj / ".claude" / "next_suggestion.json"

        ns.write_cache(proj, DONE, raw, now=1000.0)
        assert path.is_file()
        json.loads(path.read_text())
        inode = path.stat().st_ino
        ns.write_cache(proj, DONE, raw, now=1000.0)
        assert path.stat().st_ino != inode, "Cache wird nicht atomar ersetzt"
        assert not [p.name for p in (proj / ".claude").iterdir()
                    if p.name != "next_suggestion.json"], list((proj / ".claude").iterdir())

        assert ns.read_cache(proj, DONE, ttl_s=300, now=1100.0) == raw
        assert ns.read_cache(proj, DONE, ttl_s=300, now=1299.0) == raw
        assert ns.read_cache(proj, DONE, ttl_s=300, now=1301.0) is None
        assert ns.read_cache(proj, DONE + 1, ttl_s=300, now=1100.0) is None
        path.write_text("{kaputt")
        assert ns.read_cache(proj, DONE, ttl_s=300, now=1100.0) is None
        assert ns.read_cache(tmp_path / "leer", DONE, ttl_s=300, now=1100.0) is None

        st = ns.settings({})
        assert st["enabled"] is True and st["cache_ttl_s"] == 300, st
        assert st["timeout_s"] > 0, st

        # Frisches choose: Cache bleibt, neu beanspruchtes Issue faellt sofort weg
        world = _world("epic")
        world["issues/500/sub_issues"].append(_iss(612, "Zweite Teilaufgabe"))
        world["issues"].append(_iss(612, "Zweite Teilaufgabe"))
        proj, log, env = _case(tmp_path, "frisch")
        Path(env["GH_FIXTURES"]).write_text(json.dumps(world))
        ns.write_cache(proj, DONE, _raw(world), now=time.time())
        env["CLAUDE_CODE_SESSION_ID"] = "eigene-sitzung"
        _session_lock(proj, "eigene-sitzung", "612")  # eigener Claim zaehlt nicht

        res = _cli(proj, "endstate", env=env)
        assert res.returncode == 0, (res.stdout, res.stderr)
        assert _kv(res.stdout, "SUGGEST_ISSUE") == "610", res.stdout
        assert _plan_tail(proj, env) == _kv(res.stdout, "FOOTER")

        _session_lock(proj, "fremde-sitzung", "610,999")
        res = _cli(proj, "endstate", env=env)
        assert res.returncode == 0, (res.stdout, res.stderr)
        assert _kv(res.stdout, "SUGGEST_ISSUE") == "612", res.stdout
        footer = _kv(res.stdout, "FOOTER")
        assert "/00-intake #612" in footer, footer
        assert _plan_tail(proj, env) == footer


# --- AC-10 -----------------------------------------------------------------------------

class TestEndStateZeile:
    def test_zeile_mit_zusatz_und_ohne_byte_gleich(self):
        wf = _wf()
        from klartext_gate import treffer  # noqa: PLC0415

        data = _data()
        sug = {"n": 612, "source": "epic", "title": "Plan zeigt Vorschlag",
               "reason": "gleiche Sammelaufgabe: Plan zeigt Vorschlag"}
        for archived in (False, True):
            base = wf.end_state(data, archived=archived)
            assert base["line"] == TODAY, base
            assert wf.end_state(data, archived=archived, suggest=None) == base
            got = wf.end_state(data, archived=archived, suggest=sug)
            assert got["kind"] == "done", got
            assert got["line"] == _suggest_line(612, sug["reason"]), got["line"]
            assert "\n" not in got["line"] and got["line"].count("✅") == 1, got
            assert treffer(got["line"]) == [], treffer(got["line"])

        # Quelle in Alltagssprache und Kurztitel <= 60 Zeichen aus choose
        ns = _ns()
        long_title = "Sehr langer Titel " + "mit vielen Woertern " * 8
        for kind, n in EXPECT.items():
            raw = _raw(_world(kind))
            for issue in raw["issues"] + raw["sub_issues"]:
                if issue["number"] == n:
                    issue["title"] = long_title
            choice = ns.choose(raw, DONE, [])
            assert len(choice["title"]) <= 60, choice
            assert choice["title"][:10] == long_title[:10], choice
            line = wf.end_state(data, suggest=choice)["line"]
            assert line == _suggest_line(n, f"{SOURCE_TEXT[kind]}: {choice['title']}"), line
            assert treffer(line) == [], (kind, treffer(line))

        # Vorschlag wirkt nur im Fall "fertig, kein offener Auftrag"
        for d, kw in ((_data(phase="phase6_implement"), {}),
                      (_data(waiting_on="CI von 12"), {}),
                      (_data(), {"queue_next": 548, "autark": True}),
                      (_data(), {"queue_next": 548, "autark": False}),
                      (_data(), {"deploy": "configured"}),
                      (_data(deploy_status="failed"), {"deploy": "configured"})):
            assert wf.end_state(d, suggest=sug, **kw) == wf.end_state(d, **kw), (d, kw)


# --- AC-11 ------------------------------------------------------------------------------

class TestEndstateKommando:
    def test_suggest_zeilen_nur_bei_vorschlag(self, tmp_path):
        for kind, n in EXPECT.items():
            proj, log, env = _case(tmp_path, kind, kind=kind)
            res = _cli(proj, "endstate", env=env)
            assert res.returncode == 0, (kind, res.stdout, res.stderr)
            assert _kv(res.stdout, "ENDSTATE") == "done", res.stdout
            assert _kv(res.stdout, "SUGGEST_ISSUE") == str(n), (kind, res.stdout)
            assert _kv(res.stdout, "SUGGEST_SOURCE") == kind, (kind, res.stdout)
            reason = _kv(res.stdout, "SUGGEST_REASON")
            assert reason and reason.startswith(SOURCE_TEXT[kind] + ": "), (kind, reason)
            assert _kv(res.stdout, "FOOTER") == _suggest_line(n, reason), res.stdout
            assert (proj / ".claude" / "next_suggestion.json").is_file(), kind
            assert _calls(log), kind

        for label, kw in (("ohne-gh", {"gh": False}), ("exit", {}), ("kein-kandidat", {})):
            proj, log, env = _case(tmp_path, label, kind="none" if label == "kein-kandidat"
                                   else "epic", **kw)
            if label == "exit":
                env["GH_EXIT"] = "1"
            res = _cli(proj, "endstate", env=env)
            assert res.returncode == 0, (label, res.stdout, res.stderr)
            assert _kv(res.stdout, "ENDSTATE") == "done", (label, res.stdout)
            assert _kv(res.stdout, "FOOTER") == TODAY, (label, res.stdout)
            for key in SUGGEST_KEYS:
                assert _kv(res.stdout, key) is None, (label, key, res.stdout)
            assert "Traceback" not in res.stderr, res.stderr

    def test_ohne_vorschlag_heutige_zeile_unveraendert(self, tmp_path):
        """Grundlinie (heute schon gruen): ohne gh bleibt `endstate`/Plan byte-gleich."""
        wf = _wf()
        assert wf.end_state(_data())["line"] == TODAY
        assert wf.end_state(_data(), archived=True)["line"] == TODAY
        proj, log, env = _case(tmp_path, "grundlinie", gh=False)
        res = _cli(proj, "endstate", env=env)
        assert res.returncode == 0, (res.stdout, res.stderr)
        assert res.stdout.splitlines() == ["ENDSTATE=done", f"FOOTER={TODAY}"], res.stdout
        assert _plan_tail(proj, env) == TODAY


# --- AC-12------------------------------------------------------------------------------

class TestNetzfrei:
    def test_plan_und_end_state_ohne_netz_gleiche_zeile(self, tmp_path):
        proj, log, env = _case(tmp_path, "netz")
        res = _cli(proj, "endstate", env=env)
        assert res.returncode == 0, (res.stdout, res.stderr)
        footer = _kv(res.stdout, "FOOTER")
        assert "/00-intake #610" in footer, footer
        assert _calls(log), "endstate holt die Rohdaten"
        log.write_text("")

        res = _cli(proj, "endstate", env=env)
        assert _kv(res.stdout, "FOOTER") == footer, res.stdout
        assert _calls(log) == [], "gueltiger Cache: kein zweiter Abruf"

        assert _plan_tail(proj, env) == footer
        code = ("import json, sys\n"
                f"sys.path.insert(0, {str(HOOKS_DIR)!r})\n"
                "import workflow\n"
                "data = json.loads(sys.stdin.read())\n"
                "args = workflow.queue_end_args(data)\n"
                "line = workflow.end_state(data, **args)['line']\n"
                "plan = workflow.render_plan(data, queue=args)\n"
                "print(json.dumps({'line': line, 'plan': plan.splitlines()[-1]}))\n")
        out = subprocess.run([sys.executable, "-c", code], input=json.dumps(_data()),
                             capture_output=True, text=True, env=env, cwd=str(proj),
                             timeout=60)
        assert out.returncode == 0, out.stderr
        got = json.loads(out.stdout.strip().splitlines()[-1])
        assert got == {"line": footer, "plan": footer}, got
        assert _calls(log) == [], _calls(log)


# --- AC-13 -------------------------------------------------------------------------------

class TestAuftragVorrang:
    def test_offener_auftrag_hat_vorrang(self, tmp_path):
        for autark, line, kind in ((True, WAIT_548, "waiting"), (False, YOU_548, "you")):
            proj, log, env = _case(tmp_path, f"auftrag-{autark}")
            path = _write_auftrag(proj, [(DONE, "done"), (548, "open")], autark=autark)
            before = path.read_bytes()
            res = _cli(proj, "endstate", env=env)
            assert res.returncode == 0, (res.stdout, res.stderr)
            assert _kv(res.stdout, "ENDSTATE") == kind, res.stdout
            assert _kv(res.stdout, "FOOTER") == line, res.stdout
            for key in SUGGEST_KEYS:
                assert _kv(res.stdout, key) is None, (key, res.stdout)
            assert path.read_bytes() == before
            assert _calls(log) == [], "kein Vorschlag berechnet"
            assert _plan_tail(proj, env) == line


# --- AC-14 -------------------------------------------------------------------------------

class TestAutark:
    def test_anhaengen_idempotent_nur_epic_und_meilenstein(self, tmp_path):
        for kind in ("epic", "milestone"):
            n = EXPECT[kind]
            wait = (f"⏳ Läuft noch: Claude startet #{n} aus deinem Auftrag. "
                    "Du musst nichts tun, ich melde mich.")
            proj, log, env = _case(tmp_path, f"autark-{kind}", kind=kind)
            _write_auftrag(proj, [(DONE, "done")], autark=True)
            for run in (1, 2):
                res = _cli(proj, "endstate", env=env)
                assert res.returncode == 0, (kind, run, res.stdout, res.stderr)
                assert _kv(res.stdout, "ENDSTATE") == "waiting", (kind, run, res.stdout)
                assert _kv(res.stdout, "FOOTER") == wait, (kind, run, res.stdout)
                nums = [e["n"] for e in _read_auftrag(proj)["issues"]]
                assert nums.count(n) == 1, (kind, run, nums)
                status = {e["n"]: e["status"] for e in _read_auftrag(proj)["issues"]}
                assert status == {DONE: "done", n: "open"}, (kind, run, status)
                assert _read_auftrag(proj)["autark"] is True
            assert _plan_tail(proj, env) == wait

        # Steht M schon (erledigt) im Auftrag: nichts anhaengen
        proj, log, env = _case(tmp_path, "autark-schon-drin", kind="epic")
        path = _write_auftrag(proj, [(DONE, "done"), (610, "done")], autark=True)
        before = path.read_bytes()
        res = _cli(proj, "endstate", env=env)
        assert res.returncode == 0, (res.stdout, res.stderr)
        assert path.read_bytes() == before

        # related / priority / nicht autark: nur Vorschlag, nichts angehaengt
        for label, kind, autark in (("rel", "related", True), ("prio", "priority", True),
                                    ("manuell", "epic", False)):
            n = EXPECT[kind]
            proj, log, env = _case(tmp_path, f"nur-{label}", kind=kind)
            path = _write_auftrag(proj, [(DONE, "done")], autark=autark)
            before = path.read_bytes()
            res = _cli(proj, "endstate", env=env)
            assert res.returncode == 0, (label, res.stdout, res.stderr)
            assert _kv(res.stdout, "ENDSTATE") == "done", (label, res.stdout)
            reason = _kv(res.stdout, "SUGGEST_REASON")
            assert _kv(res.stdout, "SUGGEST_ISSUE") == str(n), (label, res.stdout)
            assert _kv(res.stdout, "FOOTER") == _suggest_line(n, reason), (label, res.stdout)
            assert path.read_bytes() == before, label


# --- AC-15 --------------------------------------------------------------------------------

class TestKillSwitch:
    def test_nur_literal_false_schaltet_ab(self, tmp_path):
        ns = _ns()
        assert ns.settings({})["enabled"] is True
        assert ns.settings({"next_suggestion": {"enabled": False}})["enabled"] is False
        assert ns.settings({"next_suggestion": {"enabled": "false"}})["enabled"] is True
        assert ns.settings({"next_suggestion": {"enabled": 0}})["enabled"] is True
        assert ns.settings({"next_suggestion": "kaputt"})["enabled"] is True
        assert ns.settings("kaputt")["enabled"] is True

        # Aus: kein gh, kein Cache-Lesen, heutige Zeile (auch im Plan)
        proj, log, env = _case(tmp_path, "aus", config="next_suggestion:\n  enabled: false\n")
        ns.write_cache(proj, DONE, _raw(_world("epic")), now=time.time())
        res = _cli(proj, "endstate", env=env)
        assert res.returncode == 0, (res.stdout, res.stderr)
        assert _kv(res.stdout, "FOOTER") == TODAY, res.stdout
        for key in SUGGEST_KEYS:
            assert _kv(res.stdout, key) is None, (key, res.stdout)
        assert _plan_tail(proj, env) == TODAY
        assert _calls(log) == [], _calls(log)

        # Alles andere gilt als an
        for label, cfg in (("string", 'next_suggestion:\n  enabled: "false"\n'),
                           ("wort", "next_suggestion:\n  enabled: aus\n"),
                           ("fehlt", "auftrag:\n  enabled: true\n"),
                           ("kaputt", "next_suggestion: [kaputt\n")):
            proj, log, env = _case(tmp_path, f"an-{label}", config=cfg)
            res = _cli(proj, "endstate", env=env)
            assert res.returncode == 0, (label, res.stdout, res.stderr)
            assert _kv(res.stdout, "SUGGEST_ISSUE") == "610", (label, res.stdout)
            assert _calls(log), label


# --- AC-16 ---------------------------------------------------------------------------------

class TestFooterGate:
    def test_erweiterte_zeile_wird_nicht_geblockt(self, tmp_path):
        from test_endzustand_550 import WF as WF550, _run_footer_gate  # noqa: PLC0415
        wf = _wf()
        sug = {"n": 612, "source": "milestone", "title": "Plan zeigt Vorschlag",
               "reason": "gleicher Meilenstein: Plan zeigt Vorschlag"}
        data = _data(name=WF550)
        assert wf.expected_footer_command(data) is None
        line = wf.end_state(data, suggest=sug)["line"]
        assert "/00-intake #612" in line and line.startswith("✅ Erledigt"), line

        proj = tmp_path / "proj"
        (proj / ".git").mkdir(parents=True)
        wf_dir = proj / ".claude" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / f"{WF550}.json").write_text(json.dumps(data))
        (proj / ".claude" / "active_workflow").write_text(WF550)
        msg = f"Arbeit beendet.\n\n{line}\n⚙ /60-validate · agent-os-openspec 9.9.9"
        res = _run_footer_gate(proj, msg, "00000000-0000-0000-0000-000000000589")
        assert res.returncode == 0, res.stderr
        assert "Traceback" not in res.stderr, res.stderr


# --- AC-17 ---------------------------------------------------------------------------------

def _section(text: str, heading: str) -> str:
    start = text.find(heading)
    if start < 0:
        return ""
    rest = text[start + len(heading):]
    ends = [i for i in (rest.find("\n## "), rest.find("\n### ")) if i >= 0]
    return rest[:min(ends)] if ends else rest


class TestDokumentation:
    def test_befehlstext_skill_sync_und_changelog(self):
        heading = "### Abschluss: Endzustand melden"
        for where, path in (("command", COMMANDS_DIR / "60-validate.md"),
                            ("skill", SKILLS_DIR / "60-validate" / "SKILL.md")):
            sec = _section(path.read_text(encoding="utf-8"), heading)
            assert sec, (where, "Abschnitt fehlt")
            for needle in ("SUGGEST_ISSUE", "SUGGEST_SOURCE", "SUGGEST_REASON",
                           "Vorschlag", "aus deinem Auftrag", "FOOTER="):
                assert needle in sec, (where, needle)

        res = subprocess.run([sys.executable, str(REPO_ROOT / "scripts" / "sync_skills.py"),
                              "--check"], capture_output=True, text=True,
                             cwd=str(REPO_ROOT), timeout=60)
        assert res.returncode == 0, (res.stdout, res.stderr)

        changelog = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        # [Unreleased] plus juengster Versionsabschnitt: nach einem Release steht der
        # Eintrag dort.
        kopf = changelog.split("## [Unreleased]", 1)[1]
        unreleased = "\n## [".join(kopf.split("\n## [", 2)[:2])
        added = _section(unreleased, "### Added")
        assert "#589" in added, "CHANGELOG [Unreleased]/neuestes Release -> ### Added nennt #589 nicht"
