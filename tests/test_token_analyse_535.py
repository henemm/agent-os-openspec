"""Tests für core/tools/token_analyse.py (#535).

Spec: docs/specs/feat-535-token-analyse.md (AC-1 bis AC-15).
Das Modul wird lazy per importlib geladen, damit eine fehlende Datei in jedem
Test einzeln als Fehlschlag sichtbar wird statt als Collection-Error.
Alle Protokolle sind synthetisch (tmp_path); echte Nutzerprotokolle werden nie
gelesen, CLI-Subprozesse laufen mit HOME auf einem leeren Ordner.
"""
import importlib.util
import json
import os
import pathlib
import re
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
PFAD = ROOT / "core" / "tools" / "token_analyse.py"


def _lade():
    spec = importlib.util.spec_from_file_location("token_analyse_535", PFAD)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


def tool(name, **eingabe):
    return {"type": "tool_use", "name": name, "input": eingabe}


def antwort(mid, bloecke, inp=1, cw=0, cr=1000, out=10, denken=None):
    usage = {"input_tokens": inp, "cache_creation_input_tokens": cw,
             "cache_read_input_tokens": cr, "output_tokens": out}
    if denken is not None:
        usage["output_tokens_details"] = {"thinking_tokens": denken}
    return {"type": "assistant", "message": {"id": mid, "usage": usage, "content": bloecke}}


def schreibe(pfad, eintraege, extra=""):
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_text("".join(json.dumps(e) + "\n" for e in eintraege) + extra, encoding="utf-8")
    return pfad


def je_taetigkeit(b):
    return {z["taetigkeit"]: z for z in b["taetigkeiten"]}


def je_stufe(b):
    return {s["kontext"]: s for s in b["kontext"]}


def cli(*args, tmp_path):
    home = tmp_path.with_name(tmp_path.name + "-home")  # neben, nicht in der Protokollwurzel
    home.mkdir(exist_ok=True)
    env = dict(os.environ, HOME=str(home))
    return subprocess.run([sys.executable, str(PFAD), *args], capture_output=True,
                          text=True, env=env, timeout=60)


class TestZuordnung:
    def test_lesen_und_schreiben_nach_pfad(self):
        """AC-1: Lesen/Schreiben nach Werkzeug und Pfad, je genau eine Tätigkeit."""
        ta = _lade()
        faelle = [
            ([tool("Read", file_path="/r/engine/x.py")], ta.K_LESEN_CODE),
            ([tool("Grep", pattern="foo", path="/r/src")], ta.K_LESEN_CODE),
            ([tool("Read", file_path="/r/docs/specs/a.md")], ta.K_LESEN_DOKU),
            ([tool("Bash", command="sed -n 1,20p docs/adr/0001.md")], ta.K_LESEN_DOKU),
            ([tool("Read", file_path="/r/tests/test_a.py")], ta.K_LESEN_TESTS),
            ([tool("Edit", file_path="/r/engine/x.py")], ta.K_CODE),
            ([tool("Edit", file_path="/r/tests/test_x.py")], ta.K_TESTS_SCHREIBEN),
            ([tool("Write", file_path="/r/docs/specs/neu.md")], ta.K_SPEC),
        ]
        for bloecke, erwartet in faelle:
            assert ta.taetigkeit(bloecke) == erwartet, bloecke
        # Sechs verschiedene Tätigkeiten, keine fällt mit einer anderen zusammen
        kategorien = {ta.K_LESEN_CODE, ta.K_LESEN_DOKU, ta.K_LESEN_TESTS,
                      ta.K_CODE, ta.K_TESTS_SCHREIBEN, ta.K_SPEC}
        assert len(kategorien) == 6

    def test_bash_und_weitere_kategorien(self):
        """AC-2: Bash-Varianten, Teilagenten, Web, MCP, Probieren, Warten, Text, Unbekanntes."""
        ta = _lade()
        faelle = [
            ([tool("Bash", command="python -m pytest -q")], ta.K_TESTEN),
            ([tool("Bash", command="git push origin HEAD")], ta.K_GIT),
            ([tool("Bash", command="gh pr checks 12 --watch")], ta.K_GIT),
            ([tool("Bash", command="python3 .claude/hooks/workflow.py status")], ta.K_STEUERUNG),
            ([tool("Bash", command="python3 server.py --port 8000")], ta.K_BASH),
            ([tool("Agent", prompt="x", subagent_type="Explore")], ta.K_AGENT),
            ([tool("WebSearch", query="x")], ta.K_WEB),
            ([tool("WebFetch", url="https://example.org")], ta.K_WEB),
            ([tool("mcp__github__list_issues", owner="o")], ta.K_KONNEKTOR),
            ([tool("Bash", command="cat > /tmp/claude-1/scratchpad/x.py <<E\nE")], ta.K_PROBIEREN),
            ([tool("Monitor", until="x")], ta.K_WARTEN),
            ([{"type": "text", "text": "Antwort"}], ta.K_OHNE_WERKZEUG),
            ([{"type": "thinking", "thinking": "..."}], ta.K_OHNE_WERKZEUG),
            ([tool("VoelligUnbekanntesWerkzeug", a=1)], ta.K_SONST),
        ]
        for bloecke, erwartet in faelle:
            assert ta.taetigkeit(bloecke) == erwartet, bloecke
        alle = {ta.K_TESTEN, ta.K_GIT, ta.K_STEUERUNG, ta.K_BASH, ta.K_AGENT, ta.K_WEB,
                ta.K_KONNEKTOR, ta.K_PROBIEREN, ta.K_WARTEN, ta.K_OHNE_WERKZEUG, ta.K_SONST}
        assert len(alle) == 11

    def test_openspec_nur_am_wortanfang_ist_doku(self):
        """AC-3: openspec/… ist Doku, agent-os-openspec/… ist Code."""
        ta = _lade()
        assert ta.taetigkeit([tool("Grep", pattern="x", path="/r/openspec/specs")]) == ta.K_LESEN_DOKU
        assert ta.taetigkeit([tool("Read", file_path="openspec/changes/a.yaml")]) == ta.K_LESEN_DOKU
        assert ta.taetigkeit(
            [tool("Read", file_path="/home/x/agent-os-openspec/core/a.py")]) == ta.K_LESEN_CODE
        assert ta.taetigkeit(
            [tool("Grep", pattern="x", path="/home/x/agent-os-openspec/core")]) == ta.K_LESEN_CODE


class TestDeduplizierung:
    def test_streaming_zeilen_maximum_output(self, tmp_path):
        """AC-4: Zeile mit höchstem output_tokens zählt, Blöcke aller Zeilen gesammelt."""
        ta = _lade()
        lesen = [tool("Read", file_path="/r/engine/x.py")]
        text = [{"type": "text", "text": "fertig"}]
        gross = antwort("m1", lesen, inp=5, cw=100, cr=1000, out=50)
        klein = antwort("m1", text, inp=3, cw=0, cr=2000, out=10)
        for name, reihenfolge in (("vor", [gross, klein]), ("nach", [klein, gross])):
            datei = schreibe(tmp_path / name / "-proj" / "a.jsonl", reihenfolge)
            b = ta.bericht([str(datei)])
            assert b["antworten"] == 1, name
            assert b["roh"] == {"inp": 5, "cw": 100, "cr": 1000, "out": 50}, name
            zeilen = je_taetigkeit(b)
            assert set(zeilen) == {ta.K_LESEN_CODE}, name
            assert zeilen[ta.K_LESEN_CODE]["schritte"] == 1, name
            assert zeilen[ta.K_LESEN_CODE]["output"] == 50, name

    def test_dateiuebergreifend_einmal(self, tmp_path):
        """AC-5: dieselbe message.id in zwei Dateien zählt einmal."""
        ta = _lade()
        a = schreibe(tmp_path / "-proj" / "a.jsonl", [antwort("m1", [{"type": "text"}], out=10)])
        b_ = schreibe(tmp_path / "-proj" / "b.jsonl", [
            antwort("m1", [{"type": "text"}], out=10),
            antwort("m2", [{"type": "text"}], out=7),
        ])
        b = ta.bericht([str(a), str(b_)])
        assert b["dateien"] == 2
        assert b["antworten"] == 2
        assert b["roh"]["out"] == 17


class TestKontextstufen:
    def test_stufen_mit_input(self, tmp_path):
        """AC-6: Kontext = input + cache_creation + cache_read."""
        ta = _lade()
        t = [{"type": "text"}]
        eintraege = [
            antwort("u1", t, inp=1, cw=0, cr=99_000),          # 99.001   -> < 100k
            antwort("m1", t, inp=60_000, cw=0, cr=50_000),     # 110.000  -> 100-200k (erst durch input)
            antwort("m2", t, inp=1, cw=30_000, cr=80_000),     # 110.001  -> 100-200k
            antwort("m3", t, inp=1, cw=0, cr=100_500),         # 100.501  -> 100-200k
            antwort("m4", t, inp=1, cw=0, cr=198_000),         # 198.001  -> 100-200k
            antwort("o1", t, inp=3_000, cw=0, cr=199_000),     # 202.000  -> > 200k (erst durch input)
            antwort("o2", t, inp=1, cw=0, cr=250_000),         # 250.001  -> > 200k
        ]
        datei = schreibe(tmp_path / "-proj" / "a.jsonl", eintraege)
        b = ta.bericht([str(datei)])
        stufen = je_stufe(b)
        assert [s["kontext"] for s in b["kontext"]] == ["< 100k", "100-200k", "> 200k"]
        assert stufen["< 100k"]["schritte"] == 1
        assert stufen["100-200k"]["schritte"] == 4
        assert stufen["> 200k"]["schritte"] == 2


class TestBericht:
    def test_gewichtung_anteile_und_rohsummen(self, tmp_path):
        """AC-7: Gewichte 1/2/0,1/5, Anteile und Rohsummen stimmen."""
        ta = _lade()
        assert ta.GEWICHTE == {"inp": 1.0, "cw": 2.0, "cr": 0.1, "out": 5.0}
        eintraege = [
            # Lesen Code: 100*1 + 200*2 + 1000*0,1 + 40*5 = 800
            antwort("m1", [tool("Read", file_path="/r/a.py")], inp=100, cw=200, cr=1000, out=40,
                    denken=10),
            # ohne Werkzeug: 300*1 + 0 + 3000*0,1 + 60*5 = 900
            antwort("m2", [{"type": "text"}], inp=300, cw=0, cr=3000, out=60),
        ]
        datei = schreibe(tmp_path / "-proj" / "a.jsonl", eintraege)
        b = ta.bericht([str(datei)])
        assert b["antworten"] == 2
        assert b["roh"] == {"inp": 400, "cw": 200, "cr": 4000, "out": 100}
        z = je_taetigkeit(b)
        lesen, text = z[ta.K_LESEN_CODE], z[ta.K_OHNE_WERKZEUG]
        assert lesen["kostenanteil_prozent"] == pytest.approx(100 * 800 / 1700, abs=0.1)
        assert text["kostenanteil_prozent"] == pytest.approx(100 * 900 / 1700, abs=0.1)
        assert lesen["outputanteil_prozent"] == pytest.approx(40.0, abs=0.1)
        assert text["outputanteil_prozent"] == pytest.approx(60.0, abs=0.1)
        assert lesen["output"] == 40 and text["output"] == 60
        assert lesen["davon_denken"] == 10 and text["davon_denken"] == 0
        assert lesen["schritte"] == 1 and text["schritte"] == 1

    def test_sortiert_nach_kostenanteil(self, tmp_path, capsys):
        """AC-8: Text- und JSON-Ausgabe nach Kostenanteil absteigend."""
        ta = _lade()
        eintraege = [  # bewusst in aufsteigender Kostenreihenfolge geschrieben
            antwort("m1", [tool("Read", file_path="/r/a.py")], inp=1, cr=0, out=10),
            antwort("m2", [tool("Edit", file_path="/r/a.py")], inp=1, cr=0, out=1_000),
            antwort("m3", [tool("Bash", command="git status")], inp=1, cr=0, out=100_000),
        ]
        schreibe(tmp_path / "-proj" / "s" / "a.jsonl", eintraege)
        erwartet = [ta.K_GIT, ta.K_CODE, ta.K_LESEN_CODE]

        b = ta.bericht([str(tmp_path / "-proj" / "s" / "a.jsonl")])
        assert [z["taetigkeit"] for z in b["taetigkeiten"]] == erwartet
        anteile = [z["kostenanteil_prozent"] for z in b["taetigkeiten"]]
        assert anteile == sorted(anteile, reverse=True)

        assert ta.main(["-proj", "--json", "--verzeichnis", str(tmp_path)]) == 0
        j = json.loads(capsys.readouterr().out)
        assert [z["taetigkeit"] for z in j["taetigkeiten"]] == erwartet

        assert ta.main(["-proj", "--verzeichnis", str(tmp_path)]) == 0
        text = capsys.readouterr().out
        positionen = [text.index(k) for k in erwartet]
        assert positionen == sorted(positionen)


class TestCli:
    def test_liste_fasst_worktrees_zusammen(self, tmp_path):
        """AC-9: --liste zeigt Projekte mit Protokollzahl, Worktrees beim Stamm."""
        t = [antwort("m1", [{"type": "text"}])]
        schreibe(tmp_path / "-proj" / "a.jsonl", t)
        schreibe(tmp_path / "-proj" / "b.jsonl", t)
        schreibe(tmp_path / "-proj--claude-worktrees-x" / "sub" / "c.jsonl", t)
        schreibe(tmp_path / "-proj--claude-worktrees-y" / "d.jsonl", t)
        schreibe(tmp_path / "-andere" / "e.jsonl", t)
        r = cli("--liste", "--verzeichnis", str(tmp_path), tmp_path=tmp_path)
        assert r.returncode == 0, r.stderr
        zeilen = {}
        for zeile in r.stdout.splitlines():
            m = re.match(r"^\s*(\d+)\s+(\S+)\s*$", zeile)
            if m:
                zeilen[m.group(2)] = int(m.group(1))
        assert zeilen == {"-proj": 4, "-andere": 1}
        assert "worktrees" not in r.stdout

    def test_praefix_mit_bindestrich_json_verzeichnis(self, tmp_path):
        """AC-10: Präfix mit '-' als Positionsargument, --json, --verzeichnis."""
        schreibe(tmp_path / "-proj--claude-worktrees-x" / "a.jsonl",
                 [antwort("m1", [tool("Bash", command="git status")])])
        schreibe(tmp_path / "-proj" / "b.jsonl", [antwort("m2", [{"type": "text"}])])
        schreibe(tmp_path / "-fremd" / "c.jsonl", [antwort("m3", [{"type": "text"}])])
        r = cli("-proj", "--json", "--verzeichnis", str(tmp_path), tmp_path=tmp_path)
        assert r.returncode == 0, r.stderr
        b = json.loads(r.stdout)
        assert b["dateien"] == 2
        assert b["antworten"] == 2

    def test_kein_treffer_exit_1_stderr(self, tmp_path):
        """AC-11: Präfix ohne Projekte -> Exit 1, Meldung auf stderr."""
        schreibe(tmp_path / "-proj" / "a.jsonl", [antwort("m1", [{"type": "text"}])])
        r = cli("-gibtesnicht", "--verzeichnis", str(tmp_path), tmp_path=tmp_path)
        assert r.returncode == 1
        assert r.stderr.strip()
        assert r.stdout.strip() == ""

    def test_kaputte_zeilen_und_unlesbare_dateien_werden_uebersprungen(self, tmp_path):
        """AC-12: kaputte Zeilen und unlesbare Dateien übersprungen, Exit 0."""
        ordner = tmp_path / "-proj"
        schreibe(ordner / "gut.jsonl", [
            antwort("m1", [{"type": "text"}], out=10),
            antwort("m2", [tool("Bash", command="git status")], out=20),
        ], extra='kaputt\n{"type": "assistant", "message": {\n\n')
        with open(ordner / "gut.jsonl", "ab") as f:
            f.write(b"\xff\xfe\x00 kein utf8\n")
        (ordner / "x.jsonl").mkdir()  # Verzeichnis mit .jsonl-Namen: nicht lesbar als Datei
        (ordner / "y.jsonl").symlink_to(ordner / "gibt-es-nicht.jsonl")  # kaputter Link
        r = cli("-proj", "--json", "--verzeichnis", str(tmp_path), tmp_path=tmp_path)
        assert r.returncode == 0, r.stderr
        b = json.loads(r.stdout)
        assert b["antworten"] == 2
        assert b["roh"]["out"] == 30

        # F001: Felder mit falschem Typ neben gültigen Antworten (kein Abbruch)
        def roh(mid, usage, bloecke):
            return {"type": "assistant", "message": {"id": mid, "usage": usage, "content": bloecke}}

        def nutz(**kw):
            u = {"input_tokens": 1, "cache_creation_input_tokens": 0,
                 "cache_read_input_tokens": 1000, "output_tokens": 1}
            u.update(kw)
            return u

        text = [{"type": "text"}]
        schreibe(ordner / "typen.jsonl", [
            roh("t1", nutz(input_tokens=None, cache_creation_input_tokens="12",
                           cache_read_input_tokens="x", output_tokens=None), text),
            roh("t1", nutz(output_tokens="99"), text),            # Streaming-Vergleich mit String
            roh(["liste"], nutz(output_tokens=100), text),        # id unhashable -> übersprungen
            roh(42, nutz(output_tokens=100), text),               # id kein str -> übersprungen
            roh("t2", nutz(output_tokens=7, output_tokens_details="viel"), text),
            roh("t3", nutz(output_tokens=3), [{"type": "tool_use", "name": "Bash", "input": "git status"}]),
            roh("t4", nutz(), [{"type": "tool_use", "name": "Edit", "input": {"file_path": None}}]),
            roh("t5", nutz(), [{"type": "tool_use", "name": None, "input": {}}]),
            roh("t6", nutz(), [{"type": "tool_use", "name": ["Bash"], "input": {}}]),
            roh("t7", nutz(), [{"type": "tool_use", "name": "Bash", "input": {"command": ["git", "x"]}}]),
            roh("t8", nutz(), [{"type": "tool_use", "name": "Read", "input": {"file_path": ["a.md"]}}]),
            roh("t9", nutz(output_tokens=True, input_tokens=False), text),  # bool zählt nicht als Zahl
        ])
        r = cli("-proj", "--json", "--verzeichnis", str(tmp_path), tmp_path=tmp_path)
        assert r.returncode == 0, r.stderr
        assert "Traceback" not in r.stderr
        b = json.loads(r.stdout)
        assert b["antworten"] == 2 + 9
        assert b["roh"]["out"] == 30 + 0 + 7 + 3 + 1 + 1 + 1 + 1 + 1 + 0
        assert b["roh"]["inp"] == 2 + 0 + 1 + 1 + 1 + 1 + 1 + 1 + 1 + 0
        assert b["roh"]["cw"] == 0
        assert sum(z["davon_denken"] for z in b["taetigkeiten"]) == 0

        # F002: nicht vorhandener Protokollordner -> Meldung auf stderr, Exit 1
        r = cli("--liste", "--verzeichnis", str(tmp_path / "gibtsnicht"), tmp_path=tmp_path)
        assert r.returncode == 1
        assert r.stderr.strip()
        assert "Traceback" not in r.stderr
        assert r.stdout.strip() == ""


class TestDatenschutz:
    def test_ausgabe_ohne_protokollinhalte(self, tmp_path, capsys):
        """AC-13: weder Text- noch JSON-Ausgabe enthält Protokollinhalte."""
        ta = _lade()
        marker = ["GEHEIMPROMPT7x", "GEHEIMTEXT4k", "GEHEIMDENKEN2m", "GEHEIMBEFEHL3q",
                  "GEHEIMPFAD9z", "GEHEIMEDIT5w", "GEHEIMERGEBNIS8p"]
        eintraege = [
            {"type": "user", "message": {"role": "user", "content": "Bitte GEHEIMPROMPT7x pruefen"}},
            antwort("m1", [{"type": "thinking", "thinking": "GEHEIMDENKEN2m"},
                           {"type": "text", "text": "Ich sage GEHEIMTEXT4k"}]),
            antwort("m2", [tool("Bash", command="echo GEHEIMBEFEHL3q && git log")]),
            antwort("m3", [tool("Read", file_path="/home/u/GEHEIMPFAD9z/a.py")]),
            antwort("m4", [tool("Edit", file_path="/home/u/GEHEIMEDIT5w/b.py",
                                old_string="a", new_string="b")]),
            {"type": "user", "message": {"role": "user", "content": [
                {"type": "tool_result", "content": "GEHEIMERGEBNIS8p"}]}},
        ]
        schreibe(tmp_path / "-proj" / "s" / "a.jsonl", eintraege)

        assert ta.main(["-proj", "--verzeichnis", str(tmp_path)]) == 0
        text = capsys.readouterr()
        assert ta.main(["-proj", "--json", "--verzeichnis", str(tmp_path)]) == 0
        js = capsys.readouterr()
        assert json.loads(js.out)["antworten"] == 4
        for ausgabe in (text.out, text.err, js.out, js.err):
            for m in marker:
                assert m not in ausgabe, m


class TestVerteilung:
    def test_datei_in_core_tools_und_setup_spiegelt_tools(self):
        """AC-14: Datei in core/tools, setup.py spiegelt core/tools/*.py ohne Sonderfall."""
        assert PFAD.is_file()
        setup = (ROOT / "setup.py").read_text(encoding="utf-8")
        assert re.search(r'CORE_DIR\s*/\s*"tools"\s*,\s*"\*\.py"', setup), \
            "setup.py spiegelt core/tools/*.py nicht mehr"
        assert "token_analyse" not in setup


def test_changelog_mentions_535():
    """AC-15: CHANGELOG [Unreleased] -> ### Added nennt #535."""
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    # [Unreleased] plus juengster Versionsabschnitt: nach einem Release steht der
    # Eintrag dort.
    m = re.search(r"^## \[Unreleased\][^\n]*\n(.*?)(?=^## \[\d)", text, re.S | re.M)
    assert m, "kein [Unreleased]-Abschnitt"
    rest = text[m.end():]
    neu = re.search(r"^## \[\d[^\n]*\n(.*?)(?=^## \[|\Z)", rest, re.S | re.M)
    abschnitt = m.group(1) + (neu.group(1) if neu else "")
    added = re.search(r"^### Added[^\n]*\n(.*?)(?=^### |\Z)", abschnitt, re.S | re.M)
    assert added, "kein ### Added unter [Unreleased] oder im neuesten Release"
    assert "#535" in added.group(1)
