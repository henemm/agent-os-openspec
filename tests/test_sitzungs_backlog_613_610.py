"""Eigener Backlog je Sitzung (Issues #613, #610).

Spec: docs/specs/feat-613-610-sitzungs-backlog.md (AC-1 bis AC-9).

Vertraege, die diese Tests festlegen:
- Sitzungskennung `hook_utils.auftrag_owner_key()`: `herdr-<HERDR_WORKSPACE_ID>`, sonst
  `session-<CLAUDE_CODE_SESSION_ID>`, sonst "". Mit Kennung liegt der Auftrag in
  `<Haupt-Repo>/.claude/auftrag/<key>.json`, ohne Kennung wie bisher in `.claude/auftrag.json`.
- `queue` gibt `OWNER=<key|projekt>` aus; besitzerloser Altbestand erscheint in Sitzungen mit
  Kennung nur als `ALTAUFTRAG=<Nummern>`; `queue claim` uebernimmt ihn.
- `herdr_bridge.parse_session_scope(payload, workspace)` -> {"workspace", "epic", "busy"}.
- `next_suggestion.choose` mit `raw["session"] = {"epic", "busy", "sub_issues"}`:
  Kinder in Plan-Reihenfolge, sonst `{"n": None, "source": "epic-leer", "epic": E, ...}`.
- `endstate` gibt bei `epic-leer` `SUGGEST_SOURCE=epic-leer` und `SUGGEST_EPIC=E` aus.

Kein Netz, keine Mocks im Prozess: CLI und Hooks laufen als Subprozess mit echten Dateien;
`gh` und `herdr` sind Stub-Programme im PATH bzw. `HERDR_BIN_PATH`, die feste Antworten in
der Form der echten Programme liefern und jeden Aufruf protokollieren.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_auftrag_551 import (  # noqa: E402
    _active_project, _banner, _banner_context, _cli, _data, _env, _kv, _plain_project,
    _plugin,
)
from test_naechster_vorschlag_589 import (  # noqa: E402
    DONE, _calls, _genv, _iss, _session_lock, _stub,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"

# Echte Antwort von `herdr workspace list` (gekuerzt), Stand 16.11.2026
HERDR_WORKSPACES = {"id": "cli:workspace:list", "result": {"type": "workspace_list", "workspaces": [
    {"active_tab_id": "w1:t1", "agent_status": "blocked", "focused": False,
     "label": "A · Plattform, Testsuite", "number": 1, "pane_count": 2, "tab_count": 1,
     "workspace_id": "w1"},
    {"active_tab_id": "w3:t1", "agent_status": "working", "focused": False,
     "label": "C · #2913 Einstellungen neu", "number": 2, "pane_count": 2, "tab_count": 1,
     "tokens": {"wf": "#2981 · 8 abgeschlossen"}, "workspace_id": "w3"},
    {"active_tab_id": "w4:t1", "agent_status": "working", "focused": True,
     "label": "B · #3047 Einstellung = Mail (Kanal-Liste)", "number": 3, "pane_count": 2,
     "tab_count": 1, "tokens": {"wf": "#2999 · 6 Umsetzung"}, "workspace_id": "w4"},
    {"active_tab_id": "w19:t1", "agent_status": "working", "focused": False,
     "label": "#3048 Einzelauftrag (Altbestand-Trips)", "number": 5, "pane_count": 2,
     "tab_count": 1, "tokens": {"wf": "#3048 · 6b Gegenprüfung"}, "workspace_id": "w19"},
]}}

HERDR_STUB = """#!{py}
import json, os, sys
args = sys.argv[1:]
with open(os.environ["HERDR_LOG"], "a") as f:
    f.write(json.dumps(args) + "\\n")
if args[:2] == ["workspace", "list"]:
    print(open(os.environ["HERDR_FIXTURE"]).read())
sys.exit(0)
"""


def _hu():
    sys.path.insert(0, str(HOOKS_DIR))
    import hook_utils  # noqa: PLC0415
    return hook_utils


def _ns():
    sys.path.insert(0, str(HOOKS_DIR))
    import next_suggestion  # noqa: PLC0415
    return next_suggestion


def _bridge():
    sys.path.insert(0, str(HOOKS_DIR))
    import herdr_bridge  # noqa: PLC0415
    return herdr_bridge


def _ws(proj: Path, ws: str) -> dict:
    """Umgebung einer herdr-Sitzung (nur die Kennung, Bridge inaktiv)."""
    return _env(proj, HERDR_WORKSPACE_ID=ws)


def _session_dir(proj: Path) -> Path:
    return proj / ".claude" / "auftrag"


def _legacy(proj: Path) -> Path:
    return proj / ".claude" / "auftrag.json"


def _status_note_env(proj: Path, data: dict, env: dict) -> "str | None":
    code = ("import json, sys\n"
            f"sys.path.insert(0, {str(HOOKS_DIR)!r})\n"
            "import workflow\n"
            "print(json.dumps(workflow.status_note(json.loads(sys.stdin.read()))))\n")
    res = subprocess.run([sys.executable, "-c", code], input=json.dumps(data),
                         capture_output=True, text=True, env=env, cwd=str(proj), timeout=60)
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout.strip().splitlines()[-1])


def _banner_env(proj: Path, plugin: Path, env: dict) -> str:
    env = dict(env, CLAUDE_PLUGIN_ROOT=str(plugin))
    res = subprocess.run([sys.executable, str(HOOKS_DIR / "session_banner.py")],
                         input=json.dumps({"source": "clear", "cwd": str(proj)}),
                         capture_output=True, text=True, env=env, cwd=str(proj), timeout=60)
    assert res.returncode == 0, res.stderr
    return _banner_context(json.loads(res.stdout))


# --- AC-1, AC-2: herdr-Sitzungen haben je einen eigenen Auftrag -------------------

def test_auftrag_je_herdr_workspace_getrennt(tmp_path):
    proj = _plain_project(tmp_path / "p")
    a, b = _ws(proj, "w1"), _ws(proj, "w3")

    res = _cli(proj, "queue", "add", "3048", "3052", env=a)
    assert res.returncode == 0, (res.stdout, res.stderr)
    assert _kv(res.stdout, "QUEUE") == "3048,3052", res.stdout
    assert _kv(res.stdout, "OWNER") == "herdr-w1", res.stdout
    assert (_session_dir(proj) / "herdr-w1.json").is_file()
    assert not _legacy(proj).exists(), "mit Kennung kein projektweiter Auftrag"
    # Der Ordner versteckt sich selbst vor git (Konsumenten-Projekte ohne Eintrag)
    assert (_session_dir(proj) / ".gitignore").read_text().strip() == "*"
    owner = json.loads((_session_dir(proj) / "herdr-w1.json").read_text())["owner"]
    assert owner["key"] == "herdr-w1", owner

    res = _cli(proj, "queue", env=b)
    assert _kv(res.stdout, "QUEUE") == "none", res.stdout
    assert _kv(res.stdout, "NEXT") == "none", res.stdout
    assert _kv(res.stdout, "OWNER") == "herdr-w3", res.stdout

    # B legt eigenen Auftrag an, haekt ab, leert: A bleibt unberuehrt
    assert _kv(_cli(proj, "queue", "add", "2990", env=b).stdout, "QUEUE") == "2990"
    _cli(proj, "queue", "done", "3048", env=b)
    _cli(proj, "queue", "clear", env=b)
    res = _cli(proj, "queue", env=a)
    assert _kv(res.stdout, "QUEUE") == "3048,3052", res.stdout
    assert not (_session_dir(proj) / "herdr-w3.json").exists()

    # Ohne Kennung (Shell ausserhalb einer Sitzung): kein Auftrag sichtbar
    assert _kv(_cli(proj, "queue", env=_env(proj)).stdout, "QUEUE") == "none"


def test_fremder_auftrag_erscheint_nirgends(tmp_path):
    data = _data()  # feat-547-x, Phase 8
    proj = _active_project(tmp_path / "p", data)
    assert _cli(proj, "queue", "add", "3048", "--autark", env=_ws(proj, "w1")).returncode == 0
    plugin = _plugin(tmp_path)

    # Gegenprobe: die besitzende Sitzung sieht ihn ueberall
    own = _ws(proj, "w1")
    assert "#3048" in (_status_note_env(proj, _data(phase="phase7_validate"), own) or "")
    assert "#3048" in _banner_env(proj, plugin, own)
    res = _cli(proj, "endstate", env=own)
    assert "#3048" in _kv(res.stdout, "FOOTER"), res.stdout

    other = _ws(proj, "w3")
    note = _status_note_env(proj, _data(phase="phase7_validate"), other) or ""
    assert "#3048" not in note and "auftrag" not in note.lower(), note
    assert "#3048" not in _banner_env(proj, plugin, other)
    res = _cli(proj, "endstate", env=other)
    assert res.returncode == 0, (res.stdout, res.stderr)
    footer = _kv(res.stdout, "FOOTER")
    assert footer.startswith("✅ Erledigt: #547"), footer
    assert "#3048" not in footer and "aus deinem Auftrag" not in footer, footer
    # Die Kette (complete hakt ab) laeuft nur im eigenen Auftrag
    hu_code = ("import json, sys\n"
               f"sys.path.insert(0, {str(HOOKS_DIR)!r})\n"
               "import hook_utils\n"
               "print(hook_utils.auftrag_mark_done(None, 3048))\n")
    res = subprocess.run([sys.executable, "-c", hu_code], capture_output=True, text=True,
                         env=other, cwd=str(proj), timeout=60)
    assert res.stdout.strip() == "False", res.stdout
    assert _kv(_cli(proj, "queue", env=own).stdout, "QUEUE") == "3048"


# --- AC-3: Ersatzkennung Sitzungs-Id, Nachfolger nach /clear ------------------------

def test_sitzungs_id_und_nachfolger_nach_clear(tmp_path):
    proj = _plain_project(tmp_path / "p")
    # Lebende Prozesse als Claude-Prozesse: dieser Testlauf und sein Elternprozess
    me, parent = str(os.getpid()), str(os.getppid())
    s1 = _env(proj, CLAUDE_CODE_SESSION_ID="s1", CLAUDE_PID=me)
    res = _cli(proj, "queue", "add", "701", "702", env=s1)
    assert _kv(res.stdout, "OWNER") == "session-s1", res.stdout
    assert (_session_dir(proj) / "session-s1.json").is_file()

    # Parallele Sitzung (anderer Claude-Prozess): sieht nichts
    other = _env(proj, CLAUDE_CODE_SESSION_ID="x9", CLAUDE_PID=parent)
    assert _kv(_cli(proj, "queue", env=other).stdout, "QUEUE") == "none"

    # /clear: neue Sitzungs-Id, derselbe Claude-Prozess -> derselbe Auftrag
    s2 = _env(proj, CLAUDE_CODE_SESSION_ID="s2", CLAUDE_PID=me)
    assert _kv(_cli(proj, "queue", env=s2).stdout, "QUEUE") == "701,702"
    res = _cli(proj, "queue", "done", "701", env=s2)
    assert _kv(res.stdout, "QUEUE") == "702", res.stdout
    assert (_session_dir(proj) / "session-s2.json").is_file()
    assert not (_session_dir(proj) / "session-s1.json").exists(), "Vorgaenger umgezogen"
    assert _kv(_cli(proj, "queue", env=other).stdout, "QUEUE") == "none"


# --- AC-4: ohne Kennung wie bisher -----------------------------------------------------

def test_ohne_kennung_projektweit_wie_bisher(tmp_path):
    proj = _plain_project(tmp_path / "p")
    env = _env(proj)
    res = _cli(proj, "queue", "add", "547", "548", env=env)
    assert _kv(res.stdout, "QUEUE") == "547,548", res.stdout
    assert _kv(res.stdout, "OWNER") is None, "ohne Kennung Ausgabe wie bisher"
    assert _legacy(proj).is_file()
    assert not _session_dir(proj).exists()
    assert "owner" not in json.loads(_legacy(proj).read_text())
    assert _kv(_cli(proj, "queue", "clear", env=env).stdout, "QUEUE") == "none"
    assert not _legacy(proj).exists()


# --- AC-5: verwaiste Auftraege (Altbestand ohne Besitzer, beendete Sitzung) ------------

def _legacy_write(proj: Path) -> None:
    _legacy(proj).write_text(json.dumps({
        "issues": [{"n": 3048, "status": "open"}, {"n": 3052, "status": "open"}],
        "autark": True, "note": "beide umsetzen", "created": "x", "updated": "x"}))


def test_einzige_sitzung_uebernimmt_verwaisten_auftrag(tmp_path):
    """Laeuft keine andere Sitzung, arbeitet die einzige wie bisher weiter."""
    proj = _plain_project(tmp_path / "p")
    _legacy_write(proj)
    env = _env(proj, CLAUDE_CODE_SESSION_ID="s1", CLAUDE_PID=str(os.getpid()))
    res = _cli(proj, "queue", env=env)
    assert _kv(res.stdout, "QUEUE") == "3048,3052", res.stdout
    assert _kv(res.stdout, "ALTAUFTRAG") is None, res.stdout
    res = _cli(proj, "queue", "done", "3048", env=env)
    assert _kv(res.stdout, "QUEUE") == "3052", res.stdout
    assert not _legacy(proj).exists(), "Altbestand in die Sitzungsdatei umgezogen"
    assert (_session_dir(proj) / "session-s1.json").is_file()

    # Neustart von Claude Code (neuer Prozess, neue Id), wieder allein: weiter da
    dead = _session_dir(proj) / "session-s1.json"
    data = json.loads(dead.read_text())
    data["owner"]["pid"] = "999999999"  # Prozess beendet
    dead.write_text(json.dumps(data))
    env2 = _env(proj, CLAUDE_CODE_SESSION_ID="s7", CLAUDE_PID=str(os.getppid()))
    assert _kv(_cli(proj, "queue", env=env2).stdout, "QUEUE") == "3052"

    # Laeuft daneben eine andere Sitzung: nur Hinweis, nicht als eigener Auftrag
    _session_lock(proj, "fremde-sitzung", "2999")
    res = _cli(proj, "queue", env=env2)
    assert _kv(res.stdout, "QUEUE") == "none", res.stdout
    assert _kv(res.stdout, "ALTAUFTRAG") == "3052", res.stdout


def test_altbestand_nur_mit_claim(tmp_path):
    data = _data()
    proj = _active_project(tmp_path / "p", data)
    _legacy_write(proj)
    _session_lock(proj, "fremde-sitzung", "2999")  # parallele Sitzung laeuft
    env = _ws(proj, "w3")

    res = _cli(proj, "queue", env=env)
    assert _kv(res.stdout, "QUEUE") == "none", res.stdout
    assert _kv(res.stdout, "ALTAUFTRAG") == "3048,3052", res.stdout
    assert "queue claim" in res.stdout, res.stdout
    note = _status_note_env(proj, _data(phase="phase7_validate"), env) or ""
    assert "#3048" not in note, note
    footer = _kv(_cli(proj, "endstate", env=env).stdout, "FOOTER")
    assert "#3048" not in footer, footer

    # Ohne Kennung bleibt der Altbestand der Auftrag (wie bisher)
    assert _kv(_cli(proj, "queue", env=_env(proj)).stdout, "QUEUE") == "3048,3052"

    _cli(proj, "queue", "add", "2990", env=env)
    res = _cli(proj, "queue", "claim", env=env)
    assert res.returncode == 0, (res.stdout, res.stderr)
    assert _kv(res.stdout, "QUEUE") == "2990,3048,3052", res.stdout
    assert _kv(res.stdout, "AUTARK") == "on", res.stdout
    assert _kv(res.stdout, "ALTAUFTRAG") is None, res.stdout
    assert not _legacy(proj).exists()
    # Eine andere Sitzung sieht ihn danach nicht mehr
    assert _kv(_cli(proj, "queue", env=_ws(proj, "w1")).stdout, "QUEUE") == "none"

    # claim ohne Altbestand: Hinweis, Exit 0, nichts geaendert
    res = _cli(proj, "queue", "claim", env=env)
    assert res.returncode == 0, (res.stdout, res.stderr)
    assert _kv(res.stdout, "QUEUE") == "2990,3048,3052", res.stdout


# --- AC-6: Sitzungs-Epic aus dem herdr-Workspace-Namen ---------------------------------

def test_parse_session_scope_aus_echter_antwort():
    br = _bridge()
    scope = br.parse_session_scope(HERDR_WORKSPACES, "w3")
    assert scope == {"workspace": "w3", "epic": 2913, "busy": [2999, 3048]}, scope
    scope = br.parse_session_scope(HERDR_WORKSPACES, "w4")
    assert scope["epic"] == 3047 and scope["busy"] == [2981, 3048], scope
    scope = br.parse_session_scope(HERDR_WORKSPACES, "w1")  # Label ohne #N
    assert scope["epic"] is None and scope["busy"] == [2981, 2999, 3048], scope
    assert br.parse_session_scope(HERDR_WORKSPACES, "wX")["epic"] is None
    for bad in (None, {}, {"result": {}}, "kaputt", {"result": {"workspaces": "x"}}):
        assert br.parse_session_scope(bad, "w3") == {"workspace": "w3", "epic": None,
                                                     "busy": []}, bad


# --- AC-7: Auswahl nur aus dem Sitzungs-Epic --------------------------------------------

def _epic_raw(subs, issues=(), busy=()):
    return {"done": _iss(DONE, state="closed"), "parent": None, "sub_issues": [],
            "issues": list(issues) + [_iss(2221, "Fachfremd, aber wichtig",
                                           labels=["priority:critical"])],
            "milestones": [], "pulls": [],
            "session": {"epic": 2913, "busy": list(busy), "sub_issues": list(subs)}}


def test_choose_nur_kinder_des_sitzungs_epics():
    ns = _ns()
    subs = [_iss(DONE, state="closed"), _iss(3010, "Erledigt", state="closed"),
            _iss(3020, "Belegt"), _iss(3005, "Dritter Schritt"), _iss(3001, "Vierter")]
    got = ns.choose(_epic_raw(subs, busy=[3020]), DONE, [])
    # Plan-Reihenfolge der Sub-Issue-Liste, nicht Nummer oder Prioritaet
    assert got["n"] == 3005 and got["source"] == "epic", got

    # Session-Register zaehlt weiter als belegt
    got = ns.choose(_epic_raw(subs, busy=[3020]), DONE, ["3005"])
    assert got["n"] == 3001, got

    # "Teil von #2913" im Text zaehlt als Kind, nach den Sub-Issues
    extra = [_iss(3100, "Lose verknuepft", body="Teil von #2913, Schritt 9"),
             _iss(3101, "Anderes Epic", body="Teil von #29130")]
    got = ns.choose(_epic_raw([], issues=extra), DONE, [])
    assert got["n"] == 3100, got

    # Alles erledigt oder belegt: kein Ersatzvorschlag ausserhalb
    leer = ns.choose(_epic_raw(subs, busy=[3020, 3005, 3001]), DONE, [])
    assert leer["n"] is None and leer["source"] == "epic-leer", leer
    assert leer["epic"] == 2913 and "#2913" in leer["reason"], leer

    sys.path.insert(0, str(HOOKS_DIR))
    import workflow as wf  # noqa: PLC0415
    line = wf.end_state(_data(), suggest=leer)["line"]
    assert line == wf.end_state(_data())["line"], line
    assert "#2221" not in line

    # Ohne Epic, aber mit belegten Issues: alte Rangfolge ohne die belegten
    raw = _epic_raw([])
    raw["session"] = {"epic": None, "busy": [2221], "sub_issues": []}
    raw["issues"].append(_iss(2222, "Zweitwichtigste", labels=["priority:high"]))
    got = ns.choose(raw, DONE, [])
    assert got["n"] == 2222 and got["source"] == "priority", got


# --- AC-8: endstate mit herdr- und gh-Stub ------------------------------------------------

def _herdr_env(tmp_path: Path, proj: Path, world: dict, ws: str = "w3"):
    bindir, log, fx = _stub(tmp_path / "stubs", world)
    herdr = bindir / "herdr"
    herdr.write_text(HERDR_STUB.format(py=sys.executable))
    herdr.chmod(0o755)
    fixture = tmp_path / "stubs" / "workspaces.json"
    fixture.write_text(json.dumps(HERDR_WORKSPACES))
    hlog = tmp_path / "stubs" / "herdr.log"
    env = _genv(proj, bindir, log, fx)
    env.update({"HERDR_ENV": "1", "HERDR_PANE_ID": f"{ws}:p1", "HERDR_WORKSPACE_ID": ws,
                "HERDR_BIN_PATH": str(herdr), "HERDR_LOG": str(hlog),
                "HERDR_FIXTURE": str(fixture)})
    return env, log, hlog


def _epic_world(children) -> dict:
    done = _iss(DONE, "Erledigte Aufgabe", state="closed")
    return {f"issues/{DONE}": done, "milestones": [], "pulls": [],
            "issues/2913/sub_issues": [done] + children,
            "issues": [c for c in children if c["state"] == "open"]
            + [_iss(2221, "Fachfremd", labels=["priority:critical"])]}


def test_endstate_schlaegt_kind_des_workspace_epics_vor(tmp_path):
    proj = _active_project(tmp_path / "p", _data())
    world = _epic_world([_iss(2999, "Von Workspace B belegt"), _iss(3003, "Naechster Schritt")])
    env, log, hlog = _herdr_env(tmp_path, proj, world)

    res = _cli(proj, "endstate", env=env)
    assert res.returncode == 0, (res.stdout, res.stderr)
    assert _kv(res.stdout, "SUGGEST_ISSUE") == "3003", res.stdout
    assert _kv(res.stdout, "SUGGEST_SOURCE") == "epic", res.stdout
    assert "/00-intake #3003" in _kv(res.stdout, "FOOTER"), res.stdout
    paths = [c[1] for c in _calls(log) if c and c[0] == "api"]
    assert any("issues/2913/sub_issues" in p for p in paths), paths
    assert ["workspace", "list"] in [json.loads(ln) for ln in hlog.read_text().splitlines()]


def test_endstate_epic_leer_ohne_ersatzvorschlag(tmp_path):
    proj = _active_project(tmp_path / "p", _data())
    world = _epic_world([_iss(2999, "Von Workspace B belegt"),
                         _iss(3001, "Erledigt", state="closed")])
    env, _, _ = _herdr_env(tmp_path, proj, world)

    res = _cli(proj, "endstate", env=env)
    assert res.returncode == 0, (res.stdout, res.stderr)
    footer = _kv(res.stdout, "FOOTER")
    assert footer == ("✅ Erledigt: #547 ist fertig. Du kannst /clear ausführen und das "
                      "nächste Issue starten."), footer
    assert _kv(res.stdout, "SUGGEST_ISSUE") is None, res.stdout
    assert _kv(res.stdout, "SUGGEST_SOURCE") == "epic-leer", res.stdout
    assert _kv(res.stdout, "SUGGEST_EPIC") == "2913", res.stdout
    assert "Abschluss" in (_kv(res.stdout, "SUGGEST_REASON") or ""), res.stdout


# --- AC-9: Vorschlags-Cache je Workspace ----------------------------------------------------

def test_cache_gehoert_dem_workspace(tmp_path):
    proj = _plain_project(tmp_path / "p")
    code = ("import json, sys\n"
            f"sys.path.insert(0, {str(HOOKS_DIR)!r})\n"
            "import next_suggestion as ns\n"
            "mode = sys.argv[1]\n"
            "if mode == 'w':\n"
            "    print(ns.write_cache(sys.argv[2], 547, {'issues': []}))\n"
            "else:\n"
            "    print(ns.read_cache(sys.argv[2], 547) is not None)\n")

    def run(mode, ws):
        env = _env(proj, HERDR_WORKSPACE_ID=ws) if ws else _env(proj)
        res = subprocess.run([sys.executable, "-c", code, mode, str(proj)], env=env,
                             capture_output=True, text=True, cwd=str(proj), timeout=60)
        assert res.returncode == 0, res.stderr
        return res.stdout.strip()

    assert run("w", "w1") == "True"
    assert run("r", "w1") == "True"
    assert run("r", "w3") == "False"
    assert run("r", "") == "False"
    assert json.loads((proj / ".claude" / "next_suggestion.json").read_text())["workspace"] == "w1"


# --- Nachtraege aus der Gegenpruefung (Adversary F001/F002, Mutationen) -----------------

def test_herdr_hat_vorrang_und_kennung_ist_dateiname(tmp_path):
    proj = _plain_project(tmp_path / "p")
    both = _env(proj, HERDR_WORKSPACE_ID="w1", CLAUDE_CODE_SESSION_ID="s1")
    res = _cli(proj, "queue", "add", "11", env=both)
    assert _kv(res.stdout, "OWNER") == "herdr-w1", res.stdout
    # Nach /clear neue Sitzungs-Id, gleicher Workspace: derselbe Auftrag
    after = _env(proj, HERDR_WORKSPACE_ID="w1", CLAUDE_CODE_SESSION_ID="s2")
    assert _kv(_cli(proj, "queue", env=after).stdout, "QUEUE") == "11"

    evil = _env(proj, HERDR_WORKSPACE_ID="../../x y")
    res = _cli(proj, "queue", "add", "12", env=evil)
    assert res.returncode == 0, (res.stdout, res.stderr)
    names = sorted(p.name for p in _session_dir(proj).iterdir())
    assert names == [".gitignore", "herdr-.._.._x_y.json", "herdr-w1.json"], names
    assert not (proj / "x y.json").exists() and not (tmp_path / "x y.json").exists()


def test_clear_entfernt_auch_die_uebernommene_quelle(tmp_path):
    proj = _plain_project(tmp_path / "p")
    _legacy_write(proj)
    env = _env(proj, CLAUDE_CODE_SESSION_ID="s1", CLAUDE_PID=str(os.getpid()))
    assert _kv(_cli(proj, "queue", env=env).stdout, "QUEUE") == "3048,3052"
    assert _kv(_cli(proj, "queue", "clear", env=env).stdout, "QUEUE") == "none"
    assert not _legacy(proj).exists(), "uebernommener Altbestand darf nicht wiederkommen"


def test_auftrag_ohne_pid_ist_nie_verwaist(tmp_path):
    """F001: ohne CLAUDE_PID geschriebener Auftrag gehoert weiter seiner Sitzung."""
    proj = _plain_project(tmp_path / "p")

    def nopid(sid):
        env = _env(proj, CLAUDE_CODE_SESSION_ID=sid)
        env.pop("CLAUDE_PID", None)  # die laufende Testumgebung erbt sonst einen
        return env

    _cli(proj, "queue", "add", "21", env=nopid("aaa"))
    other = nopid("bbb")
    res = _cli(proj, "queue", env=other)
    assert _kv(res.stdout, "QUEUE") == "none", res.stdout
    _cli(proj, "queue", "add", "22", env=other)
    assert (_session_dir(proj) / "session-aaa.json").is_file()
    assert _kv(_cli(proj, "queue", env=nopid("aaa")).stdout, "QUEUE") == "21"


def test_choose_epic_textkinder_pr_und_grenzen():
    ns = _ns()
    extra = [_iss(3102, "Spaeter", body="Teil von #2913"),
             _iss(3101, "Frueher", body="Part of #2913")]
    assert ns.choose(_epic_raw([], issues=extra), DONE, [])["n"] == 3101
    # #29130 ist nicht #2913; das Epic selbst ist nie Kandidat
    only = [_iss(3101, "Anderes Epic", body="Teil von #29130")]
    assert ns.choose(_epic_raw([_iss(2913, "Epic selbst")], issues=only), DONE,
                     [])["source"] == "epic-leer"
    # Kind mit offenem PR gilt als belegt
    raw = _epic_raw([_iss(3005, "Hat PR"), _iss(3006, "Frei")])
    raw["pulls"] = [{"state": "open", "title": "Fix #3005", "body": "", "head": {"ref": "x"}}]
    assert ns.choose(raw, DONE, [])["n"] == 3006


def test_endstate_loest_unter_epic_auf_und_bleibt_ohne_herdr_still(tmp_path):
    proj = _active_project(tmp_path / "p", _data())
    nested = _iss(2950, "Unter-Epic", sub_issues_summary={"total": 2, "completed": 1})
    world = _epic_world([nested])
    world["issues/2950/sub_issues"] = [_iss(2951, "Erledigt", state="closed"),
                                       _iss(2952, "Im Unter-Epic offen")]
    world["issues"].append(_iss(2952, "Im Unter-Epic offen"))
    env, _, _ = _herdr_env(tmp_path, proj, world)
    res = _cli(proj, "endstate", env=env)
    assert _kv(res.stdout, "SUGGEST_ISSUE") == "2952", res.stdout

    # F002: herdr-Sitzung, aber Workspace-Liste unlesbar -> kein Vorschlag, kein Cache
    proj2 = _active_project(tmp_path / "q" / "p", _data())
    env2, _, _ = _herdr_env(tmp_path / "q", proj2, _epic_world([_iss(3003, "Kind")]))
    Path(env2["HERDR_FIXTURE"]).write_text("{kaputt")
    res = _cli(proj2, "endstate", env=env2)
    assert res.returncode == 0, (res.stdout, res.stderr)
    assert _kv(res.stdout, "SUGGEST_ISSUE") is None, res.stdout
    assert "#2221" not in _kv(res.stdout, "FOOTER"), res.stdout
    assert not (proj2 / ".claude" / "next_suggestion.json").exists()
