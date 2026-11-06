"""Tests für core/tools/token_analyse.py (#535): Zuordnung, Doppelzählung, Aufruf."""
import importlib.util
import json
import pathlib

PFAD = pathlib.Path(__file__).resolve().parent.parent / "core" / "tools" / "token_analyse.py"
spec = importlib.util.spec_from_file_location("token_analyse", PFAD)
ta = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ta)


def tool(name, **eingabe):
    return {"type": "tool_use", "name": name, "input": eingabe}


def test_zuordnung():
    assert ta.taetigkeit([{"type": "text"}]) == ta.K_OHNE_WERKZEUG
    assert ta.taetigkeit([tool("Read", file_path="/a")]) == ta.K_RECHERCHE
    assert ta.taetigkeit([tool("Edit", file_path="/r/engine/x.py")]) == ta.K_CODE
    assert ta.taetigkeit([tool("Edit", file_path="/r/tests/test_x.py")]) == ta.K_TESTS_SCHREIBEN
    assert ta.taetigkeit([tool("Write", file_path="/r/docs/spec.md")]) == ta.K_SPEC
    assert ta.taetigkeit([tool("Bash", command="python -m pytest -q")]) == ta.K_TESTEN
    assert ta.taetigkeit([tool("Bash", command="git push origin HEAD")]) == ta.K_GIT
    assert ta.taetigkeit([tool("Bash", command="grep -n foo a.py | head")]) == ta.K_RECHERCHE
    assert ta.taetigkeit([tool("Bash", command="cat > /tmp/claude-1/scratchpad/x.py <<E\nE")]) == ta.K_PROBIEREN
    assert ta.taetigkeit([tool("Bash", command="python3 workflow.py status")]) == ta.K_STEUERUNG
    assert ta.taetigkeit([tool("Agent", prompt="x")]) == ta.K_AGENT


def antwort(mid, bloecke, cr=1000, out=10):
    usage = {"input_tokens": 1, "cache_creation_input_tokens": 0,
             "cache_read_input_tokens": cr, "output_tokens": out}
    return {"type": "assistant", "message": {"id": mid, "usage": usage, "content": bloecke}}


def test_antwort_wird_nur_einmal_gezaehlt_und_bloecke_gesammelt(tmp_path):
    ordner = tmp_path / "-proj" / "s"
    ordner.mkdir(parents=True)
    zeilen = [
        antwort("m1", [{"type": "thinking"}]),
        antwort("m1", [tool("Read", file_path="/a")]),
        antwort("m2", [{"type": "text"}], cr=250_000),
    ]
    (ordner / "a.jsonl").write_text("\n".join(json.dumps(z) for z in zeilen) + "\nkaputt\n")
    b = ta.bericht(list((tmp_path / "-proj").glob("**/*.jsonl")))
    assert b["antworten"] == 2
    namen = {z["taetigkeit"]: z for z in b["taetigkeiten"]}
    assert namen[ta.K_RECHERCHE]["schritte"] == 1
    assert namen[ta.K_OHNE_WERKZEUG]["schritte"] == 1
    stufen = {s["kontext"]: s for s in b["kontext"]}
    assert stufen["> 200k"]["schritte"] == 1


def test_aufruf_liste_und_auswertung(tmp_path, capsys):
    (tmp_path / "-proj--claude-worktrees-x").mkdir()
    (tmp_path / "-proj--claude-worktrees-x" / "a.jsonl").write_text(
        json.dumps(antwort("m1", [tool("Bash", command="git status")])) + "\n")
    assert ta.main(["--liste", "--verzeichnis", str(tmp_path)]) == 0
    assert "-proj" in capsys.readouterr().out
    assert ta.main(["-proj", "--json", "--verzeichnis", str(tmp_path)]) == 0
    assert json.loads(capsys.readouterr().out)["antworten"] == 1
    assert ta.main(["-gibtesnicht", "--verzeichnis", str(tmp_path)]) == 1
