"""Spur als Stufe 3 des naechsten Vorschlags (Issue #591, Teil B von #589).

Spec: docs/specs/feat-591-spur.md (AC-1 bis AC-14).

Vertraege, die diese Tests festlegen (die Spec laesst sie offen, der Test entscheidet):

- Fundort der Namensregel: `hook_utils.normalize_spur(value) -> str | None`
  (`[a-z0-9-]`, ohne Rand-/Doppel-Bindestriche, hoechstens 40 Zeichen; ungueltig -> None).
- `hook_utils._normalize_auftrag(raw)` liefert immer den Schluessel `spur` (str, "" = keine).
- CLI `workflow.py spur [NAME | --clear]`: stdout ist GENAU eine Zeile
  `SPUR=<name>` bzw. `SPUR=none` (Kill-Switch: genau `SPUR=disabled`). Ungueltiger
  Name: Exit 1, stderr enthaelt "usage" (gross/klein egal), keine Schreibung.
  `spur` steht in `COMMANDS` (also auch per `batch` erreichbar).
- `queue add ... --spur NAME`: `--spur` ohne Wert oder mit ungueltigem Namen ->
  Exit 1, Usage auf stderr, keine Schreibung. `_print_queue` gibt eine Zeile
  `SPUR=<name>|none` aus (Position frei).
- `next_suggestion.choose(raw, done, claimed, spur=...)`: Stufe `source="spur"`,
  `SOURCE_TEXT["spur"] == "gleiche Spur"`, `reason == "gleiche Spur: <title>"`;
  `spur=None` und `spur=""` gelten als "keine Spur".
- `workflow.cached_suggestion` und `workflow._refresh_suggestion` reichen die Spur an
  `next_suggestion.choose` durch (als Keyword `spur=` oder viertes Positionsargument).
- Seitenleiste: `herdr_bridge.TOKEN_NAMES` enthaelt `spur`; `build_report(data)["tokens"]
  ["spur"]` ist der Spurname aus dem Auftrag oder "" (wie `next`), gemeldet als
  `--token spur=<name>` bzw. `--token spur=`; `clear()` sendet `--clear-token spur`.
  Die Spur kommt ueber `hook_utils.read_auftrag` (bzw. dessen Import in `workflow`);
  wirft der Leser, bleibt der Report bestehen und das Token leer (fail-open).
  `herdr_bridge.py` enthaelt keinen Schreibpfad (`write_auftrag`, `auftrag_set_spur`).

Kein Netz: `gh` ist der Stub aus tests/test_naechster_vorschlag_589.py, der jeden
Aufruf protokolliert. Neue Funktionen werden erst im Testkoerper (bzw. im
Subprozess) angesprochen: Fehlendes erscheint als Test-FAIL, nicht als
Collection-Error. TestRegression (AC-14) ist bewusst schon vor der Umsetzung
gruen: sie haelt das heutige Verhalten ohne Spur fest und blendet nur die neuen
`SPUR=`-Zeilen bzw. das leere Token aus.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_herdr_sidebar_466 as h466  # noqa: E402
from test_auftrag_551 import (  # noqa: E402
    AUTARK_SUFFIX, KILL_CFG, _auftrag_path, _cli, _data, _env, _hu, _kv, _plain_project,
    _read_auftrag, _write_auftrag,
)
from test_naechster_vorschlag_589 import (  # noqa: E402
    DONE, EXPECT, HOOKS_DIR, MS3, MS_EARLY, MS_LATE, REPO_ROOT, SKILLS_DIR, COMMANDS_DIR,
    _base_raw, _calls, _case, _iss, _ns, _plan_tail, _raw, _section, _suggest_line, _world,
)

SPUR_N = 650
OTHER_N = 670
WAIT = ("⏳ Läuft noch: Claude startet #{n} aus deinem Auftrag. "
        "Du musst nichts tun, ich melde mich.")
NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
OLD_TOKENS = {"workflow", "issue", "phase", "step", "next", "state"}


# --- Helfer ------------------------------------------------------------------

def _spur_world(kind: str = "related", spur: str = "thema") -> dict:
    """Welt aus #589 plus ein Issue mit `spur:<spur>` und eines mit `spur:anders`."""
    fx = _world(kind)
    fx["issues"] = fx["issues"] + [
        _iss(SPUR_N, "Naechster Schritt der Reihe", labels=[f"spur:{spur}"]),
        _iss(OTHER_N, "Andere Reihe", labels=["spur:anders"]),
    ]
    return fx


def _spur_case(tmp_path: Path, label: str, kind: str = "related"):
    proj, log, env = _case(tmp_path, label, kind=kind)
    Path(env["GH_FIXTURES"]).write_text(json.dumps(_spur_world(kind)))
    return proj, log, env


def _write_spur_auftrag(root: Path, issues, spur, autark: bool = False,
                        note: str = "") -> Path:
    path = _write_auftrag(root, issues, autark=autark, note=note)
    data = json.loads(path.read_text())
    data["spur"] = spur
    path.write_text(json.dumps(data))
    return path


def _py(proj: Path, code: str, env: "dict | None" = None):
    """Python-Schnipsel im Projekt (frischer Config-Cache); letzte stdout-Zeile als JSON."""
    prelude = f"import json, sys\nsys.path.insert(0, {str(HOOKS_DIR)!r})\n"
    res = subprocess.run([sys.executable, "-c", prelude + code], capture_output=True,
                         text=True, env=env if env is not None else _env(proj),
                         cwd=str(proj), timeout=60)
    assert res.returncode == 0, (res.stdout, res.stderr)
    return json.loads(res.stdout.strip().splitlines()[-1])


def _report(proj: Path, data: dict, env: "dict | None" = None):
    return _py(proj, ("import herdr_bridge\n"
                      f"rep = herdr_bridge.build_report({data!r})\n"
                      "print(json.dumps({'rep': rep, 'names': list(herdr_bridge.TOKEN_NAMES)}))\n"),
               env=env)


def _no_spur(lines: list) -> list:
    return [ln for ln in lines if not ln.startswith("SPUR=")]


# --- AC-1 ----------------------------------------------------------------------

class TestNamensregel:
    def test_normalisierung_und_ungueltige_werte(self):
        hu = _hu()
        cases = {
            "  Mein Thema_2 ": "mein-thema-2",
            "Mein Thema": "mein-thema",
            "a_b c": "a-b-c",
            "Fix #591: Spur!": "fix-591-spur",
            "spur:release-1": "release-1",
            "spur:Mein Thema": "mein-thema",
            "a--b---c": "a-b-c",
            "--x--": "x",
            "  - x _ y -  ": "x-y",
            "x" * 50: "x" * 40,
            "a" * 39 + " bcd": "a" * 39,      # Schnitt nach 40 -> Rand erneut gestrippt
            "thema": "thema",
        }
        for raw, want in cases.items():
            got = hu.normalize_spur(raw)
            assert got == want, (raw, got, want)
            assert NAME_RE.match(got) and len(got) <= 40, (raw, got)
            assert hu.normalize_spur(got) == got, ("nicht idempotent", raw, got)

        for bad in ("", "   ", "!!!", "--", "spur:", "spur:!!", "Ä Ö ü", None, 5, 1.5,
                    True, ["x"], {"x": 1}):
            assert hu.normalize_spur(bad) is None, bad


# --- AC-2 ----------------------------------------------------------------------

class TestAuftragRoundTrip:
    def test_spur_bleibt_erhalten_ungueltig_wird_verworfen(self, tmp_path):
        hu = _hu()
        proj = _plain_project(tmp_path / "p")
        got = _py(proj, (
            "import hook_utils as hu\n"
            "from pathlib import Path\n"
            "root = Path.cwd()\n"
            "hu.write_auftrag(root, {'issues': [{'n': 547, 'status': 'open'},"
            " {'n': 548, 'status': 'open'}], 'autark': True, 'note': 'Wortlaut',"
            " 'spur': 'thema', 'created': '', 'updated': ''})\n"
            "first = hu.read_auftrag(root)\n"
            "ok = hu.auftrag_mark_done(root, 547)\n"
            "second = hu.read_auftrag(root)\n"
            "print(json.dumps({'first': first, 'ok': ok, 'second': second}))\n"))
        assert got["first"]["spur"] == "thema", got
        assert got["ok"] is True, got
        second = got["second"]
        assert second["spur"] == "thema", second
        assert second["autark"] is True and second["note"] == "Wortlaut", second
        assert [(e["n"], e["status"]) for e in second["issues"]] == \
            [(547, "done"), (548, "open")], second
        assert _read_auftrag(proj)["spur"] == "thema"

        # queue add ohne --spur laesst die Spur stehen
        res = _cli(proj, "queue", "add", "549")
        assert res.returncode == 0, (res.stdout, res.stderr)
        data = _read_auftrag(proj)
        assert data["spur"] == "thema", data
        assert [e["n"] for e in data["issues"]] == [547, 548, 549], data

        # Fehlendes oder ungueltiges Feld -> "", uebrige Felder heil
        base = {"issues": [{"n": 547, "status": "done"}, {"n": 548, "status": "open"}],
                "autark": True, "note": "Wortlaut", "created": "c", "updated": "u"}
        for label, extra in (("fehlt", {}), ("zahl", {"spur": 5}), ("liste", {"spur": ["x"]}),
                             ("sonderzeichen", {"spur": "!!!"}), ("none", {"spur": None}),
                             ("bool", {"spur": True})):
            norm = hu._normalize_auftrag({**base, **extra})
            assert norm is not None, label
            assert norm["spur"] == "", (label, norm)
            assert norm["issues"] == base["issues"], (label, norm)
            assert norm["autark"] is True and norm["note"] == "Wortlaut", (label, norm)
            assert norm["created"] == "c" and norm["updated"] == "u", (label, norm)

        # Auch beim Lesen von der Platte
        bad = _plain_project(tmp_path / "bad")
        _write_spur_auftrag(bad, [(547, "open")], 17, autark=True, note="n")
        got = _py(bad, "import hook_utils as hu\nprint(json.dumps(hu.read_auftrag()))\n")
        assert got["spur"] == "" and got["autark"] is True and got["note"] == "n", got
        assert got["issues"] == [{"n": 547, "status": "open"}], got


# --- AC-3, AC-4 -------------------------------------------------------------------

class TestCliSpur:
    def test_setzen_zeigen_leeren_und_ungueltiger_name(self, tmp_path):
        proj = _plain_project(tmp_path / "p")
        path = _auftrag_path(proj)

        show = _cli(proj, "spur")
        assert show.returncode == 0, (show.stdout, show.stderr)
        assert show.stdout.splitlines() == ["SPUR=none"], show.stdout
        assert not path.exists(), "Anzeigen schreibt nichts"

        # Ungueltig ohne Auftrag: nichts angelegt
        for bad in ("!!!", "", "spur:"):
            inv = _cli(proj, "spur", bad)
            assert inv.returncode == 1, (bad, inv.stdout, inv.stderr)
            assert "usage" in inv.stderr.lower(), (bad, inv.stderr)
            assert not path.exists(), bad

        res = _cli(proj, "spur", "Mein Thema")
        assert res.returncode == 0, (res.stdout, res.stderr)
        assert res.stdout.splitlines() == ["SPUR=mein-thema"], res.stdout
        data = _read_auftrag(proj)
        assert data["spur"] == "mein-thema", data
        assert data["issues"] == [] and data["autark"] is False, data

        before = path.read_bytes()
        show = _cli(proj, "spur")
        assert show.returncode == 0, (show.stdout, show.stderr)
        assert show.stdout.splitlines() == ["SPUR=mein-thema"], show.stdout
        assert path.read_bytes() == before, "Anzeigen schreibt nichts"

        # Ungueltig mit Auftrag: Datei byte-gleich
        inv = _cli(proj, "spur", "?? !!")
        assert inv.returncode == 1, (inv.stdout, inv.stderr)
        assert "usage" in inv.stderr.lower(), inv.stderr
        assert path.read_bytes() == before

        clr = _cli(proj, "spur", "--clear")
        assert clr.returncode == 0, (clr.stdout, clr.stderr)
        assert clr.stdout.splitlines() == ["SPUR=none"], clr.stdout
        assert path.is_file(), "--clear laesst die Datei bestehen"
        assert _read_auftrag(proj)["spur"] == "", _read_auftrag(proj)
        assert _cli(proj, "spur").stdout.splitlines() == ["SPUR=none"]

        # Vorhandener Auftrag: Liste, autark und Wortlaut bleiben
        full = _plain_project(tmp_path / "voll")
        _write_auftrag(full, [(547, "done"), (548, "open")], autark=True, note="Wortlaut")
        res = _cli(full, "spur", "spur:Release")
        assert res.returncode == 0, (res.stdout, res.stderr)
        assert res.stdout.splitlines() == ["SPUR=release"], res.stdout
        data = _read_auftrag(full)
        assert data["spur"] == "release", data
        assert [(e["n"], e["status"]) for e in data["issues"]] == [(547, "done"), (548, "open")]
        assert data["autark"] is True and data["note"] == "Wortlaut", data

        # `spur` steht in COMMANDS: batch findet es
        bat = _cli(full, "batch", "spur", "zwei", "--", "queue")
        assert bat.returncode == 0, (bat.stdout, bat.stderr)
        assert "SPUR=zwei" in bat.stdout.splitlines(), bat.stdout

    def test_queue_add_spur_setzt_und_ueberschreibt(self, tmp_path):
        proj = _plain_project(tmp_path / "p")
        path = _write_auftrag(proj, [(547, "done")])

        res = _cli(proj, "queue", "add", "548", "--autark", "--spur", "Mein Thema")
        assert res.returncode == 0, (res.stdout, res.stderr)
        assert _kv(res.stdout, "SPUR") == "mein-thema", res.stdout
        data = _read_auftrag(proj)
        assert data["spur"] == "mein-thema", data
        assert data["autark"] is True, data
        assert [(e["n"], e["status"]) for e in data["issues"]] == [(547, "done"), (548, "open")]

        res = _cli(proj, "queue", "add", "549")
        assert res.returncode == 0, (res.stdout, res.stderr)
        assert _kv(res.stdout, "SPUR") == "mein-thema", res.stdout
        assert _read_auftrag(proj)["spur"] == "mein-thema"

        res = _cli(proj, "queue", "add", "550", "--spur", "anders", "--note", "neu")
        assert res.returncode == 0, (res.stdout, res.stderr)
        assert _kv(res.stdout, "SPUR") == "anders", res.stdout
        data = _read_auftrag(proj)
        assert data["spur"] == "anders" and data["note"] == "neu", data
        assert [e["n"] for e in data["issues"]] == [547, 548, 549, 550], data

        # Ungueltiger oder fehlender Name: Exit 1, Usage, nichts geschrieben
        before = path.read_bytes()
        for args in (("551", "--spur", "!!!"), ("551", "--spur"), ("--spur", "x")):
            inv = _cli(proj, "queue", "add", *args)
            assert inv.returncode == 1, (args, inv.stdout, inv.stderr)
            assert "usage" in inv.stderr.lower(), (args, inv.stderr)
            assert path.read_bytes() == before, args

        # Ohne vorhandenen Auftrag
        fresh = _plain_project(tmp_path / "frisch")
        res = _cli(fresh, "queue", "add", "560", "--spur", "x")
        assert res.returncode == 0, (res.stdout, res.stderr)
        assert _read_auftrag(fresh)["spur"] == "x"
        assert _kv(res.stdout, "QUEUE") == "560", res.stdout


# --- AC-5 ----------------------------------------------------------------------------

class TestAnzeigeKillSwitch:
    def test_spur_zeile_und_disabled(self, tmp_path):
        # SPUR= in der queue-Ausgabe
        proj = _plain_project(tmp_path / "mit")
        _write_spur_auftrag(proj, [(547, "open")], "thema")
        for args in (("queue",), ("queue", "list")):
            res = _cli(proj, *args)
            assert res.returncode == 0, (args, res.stderr)
            assert _kv(res.stdout, "SPUR") == "thema", (args, res.stdout)
        ohne = _plain_project(tmp_path / "ohne")
        _write_auftrag(ohne, [(547, "open")])
        assert _kv(_cli(ohne, "queue").stdout, "SPUR") == "none"
        leer = _plain_project(tmp_path / "leer")
        assert _kv(_cli(leer, "queue").stdout, "SPUR") == "none"

        # Kill-Switch: SPUR=disabled, Exit 0, keine Schreibung
        off = _plain_project(tmp_path / "aus", KILL_CFG)
        path = _write_spur_auftrag(off, [(547, "open")], "thema", autark=True)
        before = path.read_bytes()
        for args in (("spur",), ("spur", "neu"), ("spur", "--clear")):
            res = _cli(off, *args)
            assert res.returncode == 0, (args, res.stdout, res.stderr)
            assert res.stdout.strip() == "SPUR=disabled", (args, res.stdout)
            assert path.read_bytes() == before, args
        res = _cli(off, "queue")
        assert res.stdout.strip() == "QUEUE=disabled", res.stdout
        empty = _plain_project(tmp_path / "aus-leer", KILL_CFG)
        res = _cli(empty, "spur", "neu")
        assert res.returncode == 0 and res.stdout.strip() == "SPUR=disabled", res.stdout
        assert not _auftrag_path(empty).exists()

        # Alles andere gilt als an
        for label, cfg in (("string", 'auftrag:\n  enabled: "false"\n'),
                           ("wort", "auftrag:\n  enabled: aus\n"),
                           ("fehlt", "next_suggestion:\n  enabled: true\n"),
                           ("kaputt", "auftrag: [kaputt\n")):
            on = _plain_project(tmp_path / f"an-{label}", cfg)
            res = _cli(on, "spur", "neu")
            assert res.returncode == 0, (label, res.stdout, res.stderr)
            assert res.stdout.splitlines() == ["SPUR=neu"], (label, res.stdout)
            assert _read_auftrag(on)["spur"] == "neu", label


# --- AC-6, AC-7 ------------------------------------------------------------------------

class TestChooseSpur:
    def test_rang_nach_meilenstein_vor_verwandt_und_ausschluesse(self):
        ns = _ns()
        assert ns.SOURCE_TEXT.get("spur") == "gleiche Spur", ns.SOURCE_TEXT

        raw = _raw(_world("epic"))
        raw["done"] = _iss(DONE, state="closed", ms=MS3)
        raw["issues"].append(_iss(SPUR_N, "Spur Aufgabe", labels=["spur:x"]))
        spur = "x"
        order = []
        for _ in range(5):
            got = ns.choose(raw, DONE, [], spur=spur)
            assert got is not None, order
            order.append((got["source"], got["n"]))
            if got["source"] == "epic":
                raw["parent"], raw["sub_issues"] = None, []
            elif got["source"] == "milestone":
                raw["done"] = _iss(DONE, state="closed")
            elif got["source"] == "spur":
                assert got["reason"] == f"gleiche Spur: {got['title']}", got
                assert got["title"] == "Spur Aufgabe", got
                spur = None
            elif got["source"] == "related":
                raw["issues"] = [i for i in raw["issues"] if i["number"] != 630]
        assert order == [("epic", 610), ("milestone", 620), ("spur", SPUR_N),
                         ("related", 630), ("priority", 620)], order

        # Ausschluesse gelten auch auf der Spur
        lab = ["spur:x"]
        issues = [
            _iss(DONE, labels=lab),                                    # die erledigte selbst
            _iss(651, labels=lab),                                     # anderswo beansprucht
            _iss(652, labels=lab + ["status:deferred"]),
            _iss(653, labels=lab),                                     # offener PR
            _iss(654, labels=lab, state="closed"),
            _iss(655, labels=lab, pull_request={"url": "x"}),
            _iss(656, labels=lab + ["epic"]),
            _iss(657, labels=lab,                                      # Eltern mit offenen Subs
                 sub_issues_summary={"total": 2, "completed": 0, "percent_completed": 0}),
            _iss(658, labels=lab + ["spec-proposal"]),
            _iss(659, labels=lab + ["priority:low"]),
            _iss(699, labels=["priority:critical"]),
        ]
        pulls = [{"number": 901, "title": "Arbeit", "body": "Closes #653",
                  "head": {"ref": "feat-x"}, "state": "open"}]
        got = ns.choose(_base_raw(issues, pulls=pulls), DONE, ["651"], spur="x")
        assert got is not None and (got["source"], got["n"]) == ("spur", 659), got
        rest = [i for i in issues if i["number"] != 659]
        got = ns.choose(_base_raw(rest, pulls=pulls), DONE, ["651"], spur="x")
        assert got is not None and (got["source"], got["n"]) == ("priority", 699), got

    def test_case_insensitiv_fehlendes_label_naechste_stufe_ohne_spur_wie_vorher(self):
        ns = _ns()
        issues = [
            _iss(661, labels=["Spur:X", "priority:critical"]),
            _iss(662, ms=MS_LATE, labels=[" spur:x ", "priority:low"]),
            _iss(663, labels=["spur:y"]),
            _iss(664),
            _iss(665, ms=MS_EARLY, labels=["SPUR:x"]),
            _iss(666, ms=MS_EARLY, labels=["spur:x", "priority:high"]),
        ]
        raw = _base_raw(list(issues))
        order = []
        while True:
            got = ns.choose(raw, DONE, [], spur="x")
            assert got is not None, order
            if got["source"] != "spur":
                break
            order.append(got["n"])
            raw["issues"] = [i for i in raw["issues"] if i["number"] != got["n"]]
        assert order == [666, 665, 662, 661], order
        assert (got["source"], got["n"]) == ("priority", 663), got

        # Label nirgends vergeben: naechste Stufe, keine Ausnahme
        for kind, n in EXPECT.items():
            raw = _raw(_world(kind))
            got = ns.choose(raw, DONE, [], spur="nirgends")
            assert got == ns.choose(raw, DONE, []), kind
            assert (got["source"], got["n"]) == (kind, n), (kind, got)

        # Ohne Spur: Ergebnis wie Teil A, Spur-Labels wirken nicht
        raw = _base_raw(list(issues))
        for no_spur in (None, ""):
            got = ns.choose(raw, DONE, [], spur=no_spur)
            assert got == ns.choose(raw, DONE, []), no_spur
            assert got["source"] == "priority", got
        raw = _raw(_spur_world("related"))
        assert ns.choose(raw, DONE, [])["source"] == "related"
        assert ns.choose(raw, DONE, [], spur="thema")["n"] == SPUR_N


# --- AC-8 ---------------------------------------------------------------------------

SPY = ("import next_suggestion, workflow\n"
       "seen = []\n"
       "orig = next_suggestion.choose\n"
       "def spy(*a, **kw):\n"
       "    seen.append(kw['spur'] if 'spur' in kw else (a[3] if len(a) > 3 else None))\n"
       "    return orig(*a, **kw)\n"
       "next_suggestion.choose = spy\n")


class TestEndstateSpur:
    def test_endstate_und_cache_nutzen_spur_des_auftrags(self, tmp_path):
        proj, log, env = _spur_case(tmp_path, "es")
        _write_spur_auftrag(proj, [(DONE, "done")], "thema")

        res = _cli(proj, "endstate", env=env)
        assert res.returncode == 0, (res.stdout, res.stderr)
        assert _kv(res.stdout, "ENDSTATE") == "done", res.stdout
        assert _kv(res.stdout, "SUGGEST_ISSUE") == str(SPUR_N), res.stdout
        assert _kv(res.stdout, "SUGGEST_SOURCE") == "spur", res.stdout
        reason = _kv(res.stdout, "SUGGEST_REASON")
        assert reason and reason.startswith("gleiche Spur: "), reason
        footer = _kv(res.stdout, "FOOTER")
        assert footer == _suggest_line(SPUR_N, reason), footer
        assert _calls(log), "endstate holt die Rohdaten"
        assert _plan_tail(proj, env) == footer

        # cached_suggestion und _refresh_suggestion geben die Spur an choose
        data = _data()
        got = _py(proj, SPY + (
            f"data = {data!r}\n"
            "cached = workflow.cached_suggestion(data)\n"
            "ok = workflow._refresh_suggestion(data, workflow.queue_end_args(data))\n"
            "print(json.dumps({'cached': cached, 'ok': ok, 'seen': seen}))\n"), env=env)
        assert got["cached"] and got["cached"]["n"] == SPUR_N, got
        assert got["cached"]["source"] == "spur", got
        assert got["ok"] is True, got
        assert got["seen"] and all(s == "thema" for s in got["seen"]), got

        # Spurwechsel wirkt sofort, ohne neuen Abruf
        log.write_text("")
        sw = _cli(proj, "spur", "anders", env=env)
        assert sw.returncode == 0, (sw.stdout, sw.stderr)
        res = _cli(proj, "endstate", env=env)
        assert res.returncode == 0, (res.stdout, res.stderr)
        assert _kv(res.stdout, "SUGGEST_ISSUE") == str(OTHER_N), res.stdout
        assert _kv(res.stdout, "SUGGEST_SOURCE") == "spur", res.stdout
        assert _plan_tail(proj, env) == _kv(res.stdout, "FOOTER")

        clr = _cli(proj, "spur", "--clear", env=env)
        assert clr.returncode == 0, (clr.stdout, clr.stderr)
        res = _cli(proj, "endstate", env=env)
        assert _kv(res.stdout, "SUGGEST_ISSUE") == "630", res.stdout
        assert _kv(res.stdout, "SUGGEST_SOURCE") == "related", res.stdout
        assert _calls(log) == [], _calls(log)

        # Spur per CLI gesetzt (Auftrag mit leerer Liste) wirkt ebenso
        proj2, log2, env2 = _spur_case(tmp_path, "cli")
        assert _cli(proj2, "spur", "Thema", env=env2).returncode == 0
        res = _cli(proj2, "endstate", env=env2)
        assert res.returncode == 0, (res.stdout, res.stderr)
        assert _kv(res.stdout, "ENDSTATE") == "done", res.stdout
        assert _kv(res.stdout, "SUGGEST_ISSUE") == str(SPUR_N), res.stdout


# --- AC-9 ------------------------------------------------------------------------------

class TestAutarkSpur:
    def test_anhaengen_idempotent_nur_bei_autark(self, tmp_path):
        wait = WAIT.format(n=SPUR_N)
        proj, log, env = _spur_case(tmp_path, "autark")
        _write_spur_auftrag(proj, [(DONE, "done")], "thema", autark=True)
        for run in (1, 2):
            res = _cli(proj, "endstate", env=env)
            assert res.returncode == 0, (run, res.stdout, res.stderr)
            assert _kv(res.stdout, "ENDSTATE") == "waiting", (run, res.stdout)
            assert _kv(res.stdout, "FOOTER") == wait, (run, res.stdout)
            data = _read_auftrag(proj)
            nums = [e["n"] for e in data["issues"]]
            assert nums.count(SPUR_N) == 1, (run, nums)
            assert {e["n"]: e["status"] for e in data["issues"]} == \
                {DONE: "done", SPUR_N: "open"}, (run, data)
            assert data["autark"] is True and data["spur"] == "thema", (run, data)
        assert _plan_tail(proj, env) == wait

        # Nicht autark: nur Vorschlagszeile, nichts angehaengt
        proj, log, env = _spur_case(tmp_path, "manuell")
        path = _write_spur_auftrag(proj, [(DONE, "done")], "thema", autark=False)
        before = path.read_bytes()
        res = _cli(proj, "endstate", env=env)
        assert res.returncode == 0, (res.stdout, res.stderr)
        assert _kv(res.stdout, "ENDSTATE") == "done", res.stdout
        assert _kv(res.stdout, "SUGGEST_SOURCE") == "spur", res.stdout
        reason = _kv(res.stdout, "SUGGEST_REASON")
        assert _kv(res.stdout, "FOOTER") == _suggest_line(SPUR_N, reason), res.stdout
        assert path.read_bytes() == before

        # Epic/Meilenstein starten weiterhin selbst (vor der Spur)
        for kind in ("epic", "milestone"):
            n = EXPECT[kind]
            proj, log, env = _spur_case(tmp_path, f"vorrang-{kind}", kind=kind)
            _write_spur_auftrag(proj, [(DONE, "done")], "thema", autark=True)
            res = _cli(proj, "endstate", env=env)
            assert res.returncode == 0, (kind, res.stdout, res.stderr)
            assert _kv(res.stdout, "FOOTER") == WAIT.format(n=n), (kind, res.stdout)
            nums = [e["n"] for e in _read_auftrag(proj)["issues"]]
            assert nums == [DONE, n], (kind, nums)

        # related/priority (Spur ohne Treffer) starten nicht selbst
        for kind in ("related", "priority"):
            n = EXPECT[kind]
            proj, log, env = _case(tmp_path, f"kein-start-{kind}", kind=kind)
            path = _write_spur_auftrag(proj, [(DONE, "done")], "thema", autark=True)
            before = path.read_bytes()
            res = _cli(proj, "endstate", env=env)
            assert res.returncode == 0, (kind, res.stdout, res.stderr)
            assert _kv(res.stdout, "ENDSTATE") == "done", (kind, res.stdout)
            assert _kv(res.stdout, "SUGGEST_ISSUE") == str(n), (kind, res.stdout)
            assert path.read_bytes() == before, kind


# --- AC-10 -----------------------------------------------------------------------------

class TestNetzfrei:
    def test_plan_und_seitenleiste_ohne_netzaufruf(self, tmp_path):
        proj, log, env = _spur_case(tmp_path, "netz")
        path = _write_spur_auftrag(proj, [(DONE, "done")], "thema")
        res = _cli(proj, "endstate", env=env)
        assert res.returncode == 0, (res.stdout, res.stderr)
        footer = _kv(res.stdout, "FOOTER")
        assert f"/00-intake #{SPUR_N}" in footer, footer
        assert _calls(log), "endstate holt die Rohdaten"
        log.write_text("")
        before = path.read_bytes()

        res = _cli(proj, "endstate", env=env)
        assert _kv(res.stdout, "FOOTER") == footer, res.stdout
        assert _plan_tail(proj, env) == footer
        side = _data(phase="phase7_validate")
        got = _py(proj, (
            "import workflow, herdr_bridge\n"
            f"data = {_data()!r}\n"
            "args = workflow.queue_end_args(data)\n"
            "line = workflow.end_state(data, **args)['line']\n"
            "plan = workflow.render_plan(data, queue=args)\n"
            f"rep = herdr_bridge.build_report({side!r})\n"
            "print(json.dumps({'line': line, 'plan': plan.splitlines()[-1],"
            " 'n': (args.get('suggest') or {}).get('n'), 'tokens': rep['tokens']}))\n"),
            env=env)
        assert got["line"] == footer and got["plan"] == footer, got
        assert got["n"] == SPUR_N, got
        assert got["tokens"].get("spur") == "thema", got
        assert _calls(log) == [], _calls(log)
        assert path.read_bytes() == before, "Anzeige schreibt den Auftrag nicht"


# --- AC-11 ------------------------------------------------------------------------------

class TestHerdrAnzeige:
    def test_token_spur_nur_anzeige_fail_open(self, tmp_path):
        data = _data(phase="phase6_implement")

        mit = _plain_project(tmp_path / "mit")
        path = _write_spur_auftrag(mit, [(548, "open")], "mein-thema")
        before = path.read_bytes()
        got = _report(mit, data)
        assert "spur" in got["names"], got["names"]
        assert got["rep"] is not None, got
        assert set(got["rep"]["tokens"]) == set(got["names"]), got
        assert got["rep"]["tokens"]["spur"] == "mein-thema", got
        assert path.read_bytes() == before

        for label, setup in (("ohne-spur", lambda p: _write_auftrag(p, [(548, "open")])),
                             ("ohne-auftrag", lambda p: None),
                             ("kaputt", lambda p: _auftrag_path(p).write_text("{kaputt"))):
            proj = _plain_project(tmp_path / label)
            setup(proj)
            got = _report(proj, data)
            assert got["rep"] is not None, (label, got)
            assert got["rep"]["tokens"].get("spur") == "", (label, got)

        # Leser wirft: Report bleibt, Token leer
        got = _py(mit, (
            "import hook_utils\n"
            "def boom(*a, **k):\n"
            "    raise RuntimeError('kaputt')\n"
            "hook_utils.read_auftrag = boom\n"
            "import workflow, herdr_bridge\n"
            "workflow.read_auftrag = boom\n"
            f"rep = herdr_bridge.build_report({data!r})\n"
            "print(json.dumps(rep))\n"))
        assert got is not None, "build_report bleibt fail-open"
        assert got["tokens"].get("spur") == "", got

        # report_workflow / clear behandeln das Token wie die uebrigen
        log = tmp_path / "herdr.log"
        stub = h466._make_stub(tmp_path)
        env = _env(mit, HERDR_ENV="1", HERDR_PANE_ID=h466.PANE,
                   HERDR_BIN_PATH=str(stub), STUB_LOG=str(log))
        _py(mit, ("import herdr_bridge\n"
                  f"herdr_bridge.report_workflow({data!r})\n"
                  "herdr_bridge.clear()\n"
                  "print('null')\n"), env=env)
        calls = h466._settled_calls(log, 2)
        reports = [c for c in calls if "--title" in c]
        clears = [c for c in calls if "--clear-title" in c]
        assert len(reports) == 1 and len(clears) == 1, calls
        tokens = h466._tokens(reports[0])
        assert tokens.get("spur") == "mein-thema", reports[0]
        assert set(tokens) >= OLD_TOKENS | {"spur"}, tokens
        assert "spur" in h466._flag_values(clears[0], "--clear-token"), clears[0]
        assert path.read_bytes() == before, "herdr schreibt nie in den Auftrag"

        src = (HOOKS_DIR / "herdr_bridge.py").read_text(encoding="utf-8")
        for writer in ("write_auftrag", "auftrag_set_spur", "auftrag_mark_done"):
            assert writer not in src, writer


# --- AC-12, AC-13 ------------------------------------------------------------------------

class TestDokumentation:
    def test_befehlstext_und_skill_synchron(self):
        heading = "### 1a."
        for where, path in (("command", COMMANDS_DIR / "00-intake.md"),
                            ("skill", SKILLS_DIR / "00-intake" / "SKILL.md")):
            sec = _section(path.read_text(encoding="utf-8"), heading)
            assert sec, (where, "Schritt 1a fehlt")
            for needle in ("--spur <name>", "spur:<name>", "Epic"):
                assert needle in sec, (where, needle)
        res = subprocess.run([sys.executable, str(REPO_ROOT / "scripts" / "sync_skills.py"),
                              "--check"], capture_output=True, text=True,
                             cwd=str(REPO_ROOT), timeout=60)
        assert res.returncode == 0, (res.stdout, res.stderr)

    def test_changelog_nennt_591(self):
        changelog = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        unreleased = changelog.split("## [Unreleased]", 1)[1].split("\n## [", 1)[0]
        added = _section(unreleased, "### Added")
        # Eigener Eintrag (fette Ueberschrift mit #591); der #589-Eintrag erwaehnt
        # #591 schon als Ausblick und zaehlt nicht.
        own = [ln for ln in added.splitlines()
               if re.match(r"^- \*\*[^*]*#591[^*]*\*\*", ln)]
        assert own, "CHANGELOG [Unreleased] -> ### Added hat keinen Eintrag zu #591"
        assert any("Spur" in ln for ln in own), own
        first = re.search(r"^## \[(\d+\.\d+\.\d+)\]", changelog, re.MULTILINE)
        plugin = json.loads((REPO_ROOT / ".claude-plugin" / "plugin.json").read_text())
        assert first and first.group(1) == plugin["version"], \
            "neue Versionsnummer im CHANGELOG ohne Release"


# --- AC-14 --------------------------------------------------------------------------------

class TestRegression:
    def test_ohne_spur_unveraendert(self, tmp_path):
        # queue: bis auf SPUR= exakt die bisherigen Zeilen
        proj = _plain_project(tmp_path / "q")
        res = _cli(proj, "queue", "add", "547", "548", "--autark", "--note", "x")
        assert res.returncode == 0, (res.stdout, res.stderr)
        assert _no_spur(res.stdout.splitlines()) == [
            "QUEUE=547,548", "AUTARK=on", "NEXT=547", "PROMPT=/00-intake #547" + AUTARK_SUFFIX]
        assert _kv(res.stdout, "SPUR") in (None, "none"), res.stdout
        assert _read_auftrag(proj).get("spur", "") == ""
        clr = _cli(proj, "queue", "clear")
        assert _no_spur(clr.stdout.splitlines()) == ["QUEUE=none", "AUTARK=off", "NEXT=none"]
        off = _plain_project(tmp_path / "aus", KILL_CFG)
        assert _cli(off, "queue").stdout.strip() == "QUEUE=disabled"

        # Alte Auftragsdatei ohne Spur: Felder unveraendert
        old = _plain_project(tmp_path / "alt")
        _write_auftrag(old, [(547, "done"), (548, "open")], autark=True, note="n")
        got = _py(old, "import hook_utils as hu\nprint(json.dumps(hu.read_auftrag()))\n")
        assert got.get("spur", "") == "", got
        assert {k: v for k, v in got.items() if k != "spur"} == {
            "issues": [{"n": 547, "status": "done"}, {"n": 548, "status": "open"}],
            "autark": True, "note": "n", "created": "2026-11-09T10:00:00Z",
            "updated": "2026-11-09T10:00:00Z"}, got

        # endstate + Plan: Spur-Labels ohne gesetzte Spur wirken nicht
        for label, auftrag in (("ohne-auftrag", False), ("auftrag-ohne-spur", True)):
            proj, log, env = _spur_case(tmp_path, label)
            if auftrag:
                _write_auftrag(proj, [(DONE, "done")])
            res = _cli(proj, "endstate", env=env)
            assert res.returncode == 0, (label, res.stdout, res.stderr)
            reason = _kv(res.stdout, "SUGGEST_REASON")
            footer = _suggest_line(630, reason)
            assert _no_spur(res.stdout.splitlines()) == [
                "ENDSTATE=done", f"FOOTER={footer}", "SUGGEST_ISSUE=630",
                "SUGGEST_SOURCE=related", f"SUGGEST_REASON={reason}"], (label, res.stdout)
            assert reason.startswith("knüpft an eine Aufgabe an: "), reason
            assert _plan_tail(proj, env) == footer, label

        # Seitenleiste: alte Tokens unveraendert, `spur` (falls da) leer
        data = _data(phase="phase6_implement")
        side = _plain_project(tmp_path / "side")
        _write_auftrag(side, [(548, "open")])
        got = _report(side, data)
        tokens = got["rep"]["tokens"]
        assert set(tokens) - {"spur"} == OLD_TOKENS, tokens
        assert tokens.get("spur", "") == "", tokens
        assert set(got["names"]) - {"spur"} == OLD_TOKENS, got["names"]
        assert tokens["issue"] == "547" and tokens["step"] == "IMPLEMENT", tokens
        assert tokens["next"] == "/50-implement #547", tokens
