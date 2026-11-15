"""Plan-Pane 4.13.0: Issue-Kurzfassung im Kopf und Auslieferung als eigener Schritt.

Zwei Befunde aus dem Alltag:
1. Der Plan-Kopf zeigte nur sechs Wörter des Issue-Titels. Jetzt steht dort der
   volle Titel (umbrochen) und darunter „Problem: …“ / „Ziel: …“ aus dem Issue-Text
   (`extract_issue_brief`, Cache `.claude/issue_briefs.json`, CLI `issue-brief`).
2. `phase8_complete` fiel VOR Commit, Push, PR, CI und Merge; der Plan zeigte
   „✔ 8 Fertig / ✅ Erledigt“, während noch ausgeliefert wurde. Jetzt setzt Phase 8
   `ship_status: open`, `ship-status` (auch aus `scripts/ship.py`) führt ihn weiter,
   und erst `done`/`skipped` macht ✅ — Plan, Fußzeile und Seitenleiste gleich.

Stub-`gh` (bash) liegt in <case>/bin: protokolliert jeden Aufruf in GH_LOG, gibt
${GH_TITLE} aus (hier ein JSON-Objekt wie `gh api .../issues/N`) und endet mit
${GH_EXIT:-0}.
"""

import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
SCRIPTS_DIR = REPO_ROOT / "scripts"
WORKFLOW_PY = HOOKS_DIR / "workflow.py"
COMMANDS_DIR = REPO_ROOT / "core" / "commands"

ISSUE = "4130"
WF = f"feat-{ISSUE}-plan"
STEP_MARKS = ("✔", "▶", "○", "✘")
DONE_TAIL = ". Du kannst /clear ausführen und das nächste Issue starten."
WAIT_TAIL = ". Du musst nichts tun, ich melde mich."
KIND_PREFIX = {"done": "✅ Erledigt: ", "waiting": "⏳ Läuft noch: ", "you": "❗ Du: "}

LONG_TITLE = ("Paket F: Profile (Vorlieben je Person, von der KI gepflegt, "
              "bei Buchungen vorgeschlagen)")

BODY_DE = """<!-- Vorlage: bitte ausfuellen -->
## Problem
Heute merkt sich die App **keine** Vorlieben je Person.
Jede Buchung beginnt bei null.

```bash
echo nicht relevant
```

## Ziel
- Je Person ein Profil
- Die KI pflegt es aus Gesprächen
- [ ] Bei Buchungen vorgeschlagen

## Akzeptanzkriterien
- AC-1: irgendwas Messbares
"""

GH_STUB = r"""#!/bin/bash
printf '%s\n' "$*" >> "$GH_LOG"
if [ -n "$GH_TITLE" ]; then printf '%s\n' "$GH_TITLE"; fi
exit "${GH_EXIT:-0}"
"""


# --- Helpers ---------------------------------------------------------------

def _wf():
    sys.path.insert(0, str(HOOKS_DIR))
    import workflow  # noqa: PLC0415
    return workflow


def _bridge():
    sys.path.insert(0, str(HOOKS_DIR))
    import herdr_bridge  # noqa: PLC0415
    return herdr_bridge


def _ship():
    sys.path.insert(0, str(SCRIPTS_DIR))
    import ship  # noqa: PLC0415
    return ship


def _data(name: str = WF, phase: str = "phase8_complete", wtype: str = "feature",
          **fields) -> dict:
    data = {"name": name, "workflow_type": wtype, "current_phase": phase,
            "phase_transitions": [], "phase_log": []}
    data.update(fields)
    return data


def _last(text: str) -> str:
    return text.splitlines()[-1]


def _steps(text: str) -> list:
    return [ln for ln in text.splitlines() if ln[:1] in STEP_MARKS]


def _assert_kind(line: str, kind: str) -> None:
    assert line.startswith(KIND_PREFIX[kind]), (kind, line)
    if kind == "done":
        assert line.endswith(DONE_TAIL), line
    elif kind == "waiting":
        assert line.endswith(WAIT_TAIL), line
    else:
        assert " — " in line, line


def _kv(stdout: str, key: str) -> "str | None":
    for line in stdout.splitlines():
        if line.startswith(key + "="):
            return line[len(key) + 1:]
    return None


def _project(root: Path) -> Path:
    proj = root / "proj"
    (proj / ".git").mkdir(parents=True)
    (proj / ".claude" / "workflows" / "_log").mkdir(parents=True)
    (proj / ".claude" / "workflows" / "_archive").mkdir(parents=True)
    (proj / "_home").mkdir()
    return proj


def _case(tmp_path: Path, label: str, *, gh: bool = True, **extra):
    root = tmp_path / label
    root.mkdir()
    proj = _project(root)
    log = root / "gh.log"
    bindir = root / "bin"
    bindir.mkdir()
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("HERDR_", "OPENSPEC_", "GH_"))}
    env["CLAUDE_PROJECT_DIR"] = str(proj)
    env["HOME"] = str(proj / "_home")
    env["GH_LOG"] = str(log)
    if gh:
        stub = bindir / "gh"
        stub.write_text(GH_STUB)
        stub.chmod(stub.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        env["PATH"] = f"{bindir}{os.pathsep}{os.environ.get('PATH', '')}"
    else:
        (bindir / "python3").symlink_to(sys.executable)
        env["PATH"] = str(bindir)
    env.update(extra)
    return proj, log, env


def _write_active(proj: Path, data: dict) -> None:
    (proj / ".claude" / "workflows" / f"{data['name']}.json").write_text(json.dumps(data))
    (proj / ".claude" / "active_workflow").write_text(data["name"])


def _write_archived(proj: Path, data: dict) -> Path:
    path = proj / ".claude" / "workflows" / "_archive" / f"{data['name']}.json"
    path.write_text(json.dumps(data))
    return path


def _workflow(args, env, cwd, timeout: float = 30):
    return subprocess.run([sys.executable, str(WORKFLOW_PY), *args], capture_output=True,
                          text=True, env=env, cwd=str(cwd), timeout=timeout)


def _gh_calls(log: Path) -> list:
    return [ln for ln in log.read_text().splitlines() if ln] if log.exists() else []


# =============================================================================
# Teil 1: Issue-Kurzfassung im Plan-Kopf
# =============================================================================

def test_extract_brief_german_sections():
    wf = _wf()
    brief = wf.extract_issue_brief(LONG_TITLE, BODY_DE)
    assert brief["title"] == LONG_TITLE
    assert brief["problem"] == ("Heute merkt sich die App keine Vorlieben je Person. "
                                "Jede Buchung beginnt bei null.")
    assert brief["goal"] == ("Je Person ein Profil; Die KI pflegt es aus Gesprächen; "
                             "Bei Buchungen vorgeschlagen")
    for text in brief.values():
        assert "nicht relevant" not in text  # Code-Block entfernt
        assert "Vorlage" not in text          # HTML-Kommentar entfernt
        assert "**" not in text and "[ ]" not in text


def test_extract_brief_english_and_inline_bold():
    wf = _wf()
    en = wf.extract_issue_brief("T", "### Motivation\nUsers lose context.\n\n"
                                      "### Expected behavior\nProfiles persist.\n")
    assert en["problem"] == "Users lose context."
    assert en["goal"] == "Profiles persist."

    inline = wf.extract_issue_brief("T", "**Problem:** Der Export bricht ab.\n"
                                         "**Ziel:** Export läuft durch.\n")
    assert inline["problem"] == "Der Export bricht ab."
    assert inline["goal"] == "Export läuft durch."


def test_extract_brief_without_headings_and_empty():
    wf = _wf()
    plain = wf.extract_issue_brief("T", "Erster Absatz mit [Link](http://x) und `code`.\n\n"
                                        "Zweiter Absatz.\n")
    assert plain["problem"] == "Erster Absatz mit Link und code. Zweiter Absatz."
    assert plain["goal"] == ""

    # Einstieg vor der ersten Ueberschrift zaehlt als Problem, wenn keine passt
    pre = wf.extract_issue_brief("T", "Kurzer Einstieg.\n\n## Ziel\nX soll Y.\n")
    assert pre["problem"] == "Kurzer Einstieg."
    assert pre["goal"] == "X soll Y."

    for body in ("", None, "```\nnur code\n```", "<!-- nur kommentar -->"):
        brief = wf.extract_issue_brief("T", body)
        assert brief == {"title": "T", "problem": "", "goal": ""}, (body, brief)


def test_extract_brief_clamps_length():
    wf = _wf()
    brief = wf.extract_issue_brief("T", "## Problem\n" + "wort " * 200 + "\n## Ziel\nkurz\n")
    assert len(brief["problem"]) <= wf.BRIEF_MAX_CHARS
    assert brief["problem"].endswith("…")
    assert brief["goal"] == "kurz"


def test_render_plan_head_with_brief_and_wrapping():
    wf = _wf()
    base = _data(phase="phase5_tdd_red", issue_title="Kurzer Titel")
    plain = wf.render_plan(dict(base))
    with_brief = wf.render_plan(dict(base, issue_brief={"problem": "P-Text", "goal": "Z-Text"}))
    lines = with_brief.splitlines()
    assert lines[:7] == [f"Workflow #{ISSUE}", WF, "Kurzer Titel", "",
                         "Problem: P-Text", "Ziel: Z-Text", ""], lines
    # Ohne Kurzfassung (oder leer) exakt wie bisher
    assert plain.splitlines()[:4] == [f"Workflow #{ISSUE}", WF, "Kurzer Titel", ""]
    assert wf.render_plan(dict(base, issue_brief={})) == plain
    assert wf.render_plan(dict(base, issue_brief={"problem": "", "goal": " "})) == plain
    assert wf.render_plan(dict(base, issue_brief="kein dict")) == plain
    # Nur Ziel -> nur eine Zeile
    only_goal = wf.render_plan(dict(base, issue_brief={"goal": "Z"})).splitlines()
    assert only_goal[4:6] == ["Ziel: Z", ""], only_goal

    # Breite: Titel und Absaetze werden umbrochen statt gekappt, Absatz hoechstens
    # PLAN_BRIEF_MAX_LINES Zeilen (letzte endet mit „…“)
    width = 24
    long_data = dict(base, issue_title=LONG_TITLE,
                     issue_brief={"problem": "Problemwort " * 40, "goal": "Zielwort " * 3})
    out = wf.render_plan(long_data, width=width)
    wrapped = out.splitlines()
    assert all(len(ln) <= width for ln in wrapped), wrapped
    title_block = wrapped[2:wrapped.index("")]
    assert 2 <= len(title_block) <= wf.PLAN_TITLE_MAX_LINES, title_block
    assert "".join(title_block).startswith("Paket F:")
    rest = wrapped[len(title_block) + 3:]
    brief_block = rest[:rest.index("")]
    goal_at = next(i for i, ln in enumerate(brief_block) if ln.startswith("Ziel: "))
    problem_lines = brief_block[:goal_at]
    assert problem_lines[0].startswith("Problem:")
    assert len(problem_lines) == wf.PLAN_BRIEF_MAX_LINES, problem_lines
    assert problem_lines[-1].endswith("…")
    goal_lines = brief_block[goal_at:]
    assert 1 <= len(goal_lines) <= wf.PLAN_BRIEF_MAX_LINES, goal_lines
    assert " ".join(goal_lines) == "Ziel: Zielwort Zielwort Zielwort", goal_lines
    assert rest[rest.index("") + 1].startswith(("✔", "▶", "○")), rest  # danach die Schritte


def test_issue_brief_cli_fetches_caches_and_plan_shows_it(tmp_path):
    payload = json.dumps({"title": LONG_TITLE, "body": BODY_DE})
    proj, log, env = _case(tmp_path, "ok", GH_TITLE=payload)
    _write_active(proj, _data(phase="phase5_tdd_red"))

    res = _workflow(["issue-brief", ISSUE], env, proj)
    assert res.returncode == 0, res.stderr
    assert _kv(res.stdout, "TITLE") == LONG_TITLE
    assert _kv(res.stdout, "PROBLEM").startswith("Heute merkt sich die App keine Vorlieben")
    assert _kv(res.stdout, "ZIEL").startswith("Je Person ein Profil;")
    assert _kv(res.stdout, "SOURCE") == "issue"
    calls = _gh_calls(log)
    assert len(calls) == 1 and calls[0].startswith(f"api repos/{{owner}}/{{repo}}/issues/{ISSUE}"), calls

    # Beide Caches: voller Titel (nicht mehr 6 Woerter) und Kurzfassung
    titles = json.loads((proj / ".claude" / "issue_titles.json").read_text())
    assert titles[ISSUE] == LONG_TITLE
    briefs = json.loads((proj / ".claude" / "issue_briefs.json").read_text())
    assert briefs[ISSUE]["problem"].startswith("Heute merkt sich")
    assert briefs[ISSUE]["source"] == "issue"

    # Plan zeigt Titel + Problem/Ziel aus dem Cache, ohne weiteren gh-Aufruf
    plan = _workflow(["plan"], env, proj)
    assert plan.returncode == 0, plan.stderr
    lines = plan.stdout.splitlines()
    assert lines[:3] == [f"Workflow #{ISSUE}", WF, LONG_TITLE], lines
    assert lines[4].startswith("Problem: Heute merkt sich"), lines
    assert lines[5].startswith("Ziel: Je Person ein Profil;"), lines
    assert len(_gh_calls(log)) == 1

    # Zweiter Aufruf: aus dem Cache, kein gh
    again = _workflow(["issue-brief", ISSUE], env, proj)
    assert again.returncode == 0 and _kv(again.stdout, "SOURCE") == "issue"
    assert len(_gh_calls(log)) == 1

    # `issue-title` liefert jetzt den vollen Titel
    title = _workflow(["issue-title", ISSUE], env, proj)
    assert title.stdout.strip() == LONG_TITLE


def test_issue_brief_manual_override_and_reset(tmp_path):
    payload = json.dumps({"title": LONG_TITLE, "body": BODY_DE})
    proj, log, env = _case(tmp_path, "manual", GH_TITLE=payload)
    _write_active(proj, _data(phase="phase5_tdd_red"))

    res = _workflow(["issue-brief", ISSUE, "--problem", "Von Hand: Problem.",
                     "--ziel", "Von Hand: Ziel."], env, proj)
    assert res.returncode == 0, res.stderr
    assert _kv(res.stdout, "PROBLEM") == "Von Hand: Problem."
    assert _kv(res.stdout, "ZIEL") == "Von Hand: Ziel."
    assert _kv(res.stdout, "SOURCE") == "manual"
    assert _kv(res.stdout, "TITLE") == LONG_TITLE  # Titel kommt weiterhin vom Issue

    # Ein erneutes Holen aus dem Issue ueberschreibt die manuelle Fassung nicht
    assert _workflow(["issue-title", ISSUE], env, proj).returncode == 0
    briefs = json.loads((proj / ".claude" / "issue_briefs.json").read_text())
    assert briefs[ISSUE]["problem"] == "Von Hand: Problem."
    plan = _workflow(["plan"], env, proj).stdout.splitlines()
    assert plan[4] == "Problem: Von Hand: Problem." and plan[5] == "Ziel: Von Hand: Ziel.", plan

    # --auto verwirft die manuelle Fassung und liest wieder aus dem Issue
    auto = _workflow(["issue-brief", ISSUE, "--auto"], env, proj)
    assert auto.returncode == 0, auto.stderr
    assert _kv(auto.stdout, "SOURCE") == "issue"
    assert _kv(auto.stdout, "PROBLEM").startswith("Heute merkt sich")


def test_issue_brief_fail_open(tmp_path):
    # gh Exit 1: leere Felder, SOURCE=none, Exit 0, kein Cache
    proj, log, env = _case(tmp_path, "fail", GH_TITLE="egal", GH_EXIT="1")
    _write_active(proj, _data(phase="phase5_tdd_red"))
    res = _workflow(["issue-brief", ISSUE], env, proj)
    assert res.returncode == 0, res.stderr
    assert _kv(res.stdout, "SOURCE") == "none"
    assert _kv(res.stdout, "PROBLEM") == ""
    assert not (proj / ".claude" / "issue_briefs.json").exists()
    assert _workflow(["plan"], env, proj).returncode == 0

    # gh liefert nur Text (kein JSON): zaehlt als Titel, Kurzfassung leer
    proj2, log2, env2 = _case(tmp_path, "text", GH_TITLE="Nur ein Titel")
    _write_active(proj2, _data(phase="phase5_tdd_red"))
    res2 = _workflow(["issue-brief", ISSUE], env2, proj2)
    assert res2.returncode == 0, res2.stderr
    assert _kv(res2.stdout, "TITLE") == "Nur ein Titel"
    assert _kv(res2.stdout, "PROBLEM") == ""

    # kaputter Cache: plan laeuft, kein Kopfblock
    (proj2 / ".claude" / "issue_briefs.json").write_text("{kaputt")
    plan = _workflow(["plan"], env2, proj2)
    assert plan.returncode == 0 and "Problem:" not in plan.stdout


def test_watch_fetches_brief_once_and_start_spawns(tmp_path):
    payload = json.dumps({"title": "Kurzer Titel", "body": "## Problem\nP.\n## Ziel\nZ.\n"})
    proj, log, env = _case(tmp_path, "watch", GH_TITLE=payload,
                           OPENSPEC_PLAN_WATCH_ROUNDS="3", OPENSPEC_PLAN_WATCH_INTERVAL="0",
                           PYTHONUNBUFFERED="1")
    _write_active(proj, _data(phase="phase5_tdd_red"))
    # Alter Titel-Cache ohne Kurzfassung: der Watcher holt trotzdem genau einmal nach
    (proj / ".claude" / "issue_titles.json").write_text(json.dumps({ISSUE: "Alt…"}))
    res = _workflow(["plan", "--watch"], env, proj)
    assert res.returncode == 0, res.stderr
    frames = [f for f in res.stdout.split("\x1b[H\x1b[2J") if f.strip()]
    assert any("Problem: P." in f and "Ziel: Z." in f and "Kurzer Titel" in f
               for f in frames[1:]), frames
    assert len(_gh_calls(log)) == 1, _gh_calls(log)


# =============================================================================
# Teil 2: Auslieferung als eigener Schritt
# =============================================================================

def test_plan_shows_ship_step_before_phase8():
    wf = _wf()
    for phase in ("phase1_context", "phase5_tdd_red", "phase7_validate"):
        out = wf.render_plan(_data(phase=phase))
        steps = _steps(out)
        assert "○ Ausliefern" in steps, out
        assert steps.index("○ Ausliefern") == len(steps) - 1, steps
        assert "○ 8 Code fertig" in steps, steps
        assert not any("8 Fertig" in s for s in steps), steps
    # Fast Track ebenso
    out = wf.render_plan(_data(phase="phase6_implement", wtype="feature-fast"))
    assert "○ Ausliefern" in _steps(out)
    # Mit Deploy: Ausliefern VOR Deploy
    out = wf.render_plan(_data(phase="phase7_validate"), deploy="configured")
    steps = _steps(out)
    assert steps[-2:] == ["○ Ausliefern", "○ Deploy"], steps


def test_phase8_ship_states_plan_and_endstate():
    wf = _wf()
    cases = [
        # (ship_status, note, auto_mode, Plan-Zeile, Art)
        ("open", None, False, "▶ Ausliefern  (offen)", "you"),
        ("open", None, True, "▶ Ausliefern  (offen)", "waiting"),
        ("running", "PR 5: CI läuft", False, "▶ Ausliefern  (läuft)", "waiting"),
        ("failed", "CI rot (tests)", False, "✘ Ausliefern  (fehlgeschlagen)", "you"),
        ("failed", "CI rot (tests)", True, "✘ Ausliefern  (fehlgeschlagen)", "you"),
        ("done", "PR 5 gemergt", False, "✔ Ausliefern", "done"),
        ("skipped", "kein Remote", False, "○ Ausliefern  (entfällt)", "done"),
    ]
    for archived in (False, True):
        for status, note, auto, line, kind in cases:
            fields = {"ship_status": status}
            if note:
                fields["ship_note"] = note
            data = _data(**fields)
            ctx = (archived, status, auto)
            queue = {"auto_mode": auto}
            out = wf.render_plan(data, archived=archived, queue=queue)
            steps = _steps(out)
            assert steps[-1] == line, (ctx, steps)
            assert "✔ 8 Code fertig" in steps, (ctx, steps)
            tail = _last(out)
            _assert_kind(tail, kind)
            es = wf.end_state(data, archived=archived, auto_mode=auto)
            assert es["kind"] == kind and es["line"] == tail, (ctx, es, tail)
            if status in ("open", "running"):
                assert "Auslieferung" in tail, (ctx, tail)
                assert "✅" not in tail
            if status == "running":
                assert "(PR 5: CI läuft)" in tail, tail
            if status == "failed":
                assert tail.startswith(f"❗ Du: /60-validate #{ISSUE} — Auslieferung fehlgeschlagen (CI rot (tests))"), tail
                assert es["cmd"] == f"/60-validate #{ISSUE}"
            if status == "open" and not auto:
                assert tail.startswith("❗ Du: Sichern freigeben — "), tail
                assert "git" not in tail.lower(), tail
            if status == "done":
                assert tail == f"✅ Erledigt: #{ISSUE} ist fertig und ausgeliefert{DONE_TAIL}", tail
            if status == "skipped":
                assert tail == f"✅ Erledigt: #{ISSUE} ist fertig{DONE_TAIL}", tail


def test_legacy_without_marker_unchanged():
    wf = _wf()
    for archived in (False, True):
        out = wf.render_plan(_data(), archived=archived)
        steps = _steps(out)
        assert not any("Ausliefern" in s for s in steps), steps
        assert "✔ 8 Fertig" in steps, steps
        assert _last(out) == f"✅ Erledigt: #{ISSUE} ist fertig{DONE_TAIL}"
    # abgebrochen / ohne Build: nie ein Schritt Ausliefern
    for fields in ({"status": "abandoned"}, {"no_build_reason": "doppelt"}):
        out = wf.render_plan(_data(phase="phase3_spec", **fields))
        assert not any("Ausliefern" in s for s in _steps(out)), out
        out = wf.render_plan(_data(ship_status="open", **fields), archived=True)
        assert not any("Ausliefern" in s for s in _steps(out)), out
        _assert_kind(_last(out), "done")


def test_ship_before_deploy():
    wf = _wf()
    # Auslieferung offen: Deploy bleibt ○, Endzustand spricht von der Auslieferung
    out = wf.render_plan(_data(ship_status="running", ship_note="CI"), deploy="configured",
                         autonomous=True)
    steps = _steps(out)
    assert steps[-2:] == ["▶ Ausliefern  (läuft)", "○ Deploy"], steps
    assert "Auslieferung" in _last(out) and "Deploy" not in _last(out), _last(out)
    # Ausgeliefert: Deploy-Logik wie bisher (#510/#550)
    out = wf.render_plan(_data(ship_status="done"), deploy="configured")
    assert _steps(out)[-2:] == ["✔ Ausliefern", "▶ Deploy  (offen)"], _steps(out)
    assert _last(out).startswith(f"❗ Du: /70-deploy #{ISSUE} — ")
    out = wf.render_plan(_data(ship_status="done", deploy_status="done"), deploy="configured")
    assert _steps(out)[-2:] == ["✔ Ausliefern", "✔ Deploy"], _steps(out)
    assert _last(out) == f"✅ Erledigt: #{ISSUE} ist fertig und deployt{DONE_TAIL}"
    # Ausliefern entfaellt: Deploy wie bisher
    out = wf.render_plan(_data(ship_status="skipped"), deploy="configured", autonomous=True)
    assert _steps(out)[-1] == "▶ Deploy  (offen)"
    _assert_kind(_last(out), "waiting")


def test_waiting_on_and_queue_interplay():
    wf = _wf()
    # waiting_on gewinnt gegen offen/laufend, nicht gegen fehlgeschlagen
    es = wf.end_state(_data(ship_status="open", waiting_on="CI"))
    assert es["kind"] == "waiting" and es["line"] == f"⏳ Läuft noch: CI{WAIT_TAIL}"
    es = wf.end_state(_data(ship_status="failed", waiting_on="CI"))
    assert es["kind"] == "you" and "Auslieferung fehlgeschlagen" in es["line"]
    # Naechstes Issue aus dem Auftrag erst nach der Auslieferung
    es = wf.end_state(_data(ship_status="running"), queue_next=77, autark=True)
    assert es["kind"] == "waiting" and "Auslieferung" in es["line"], es
    es = wf.end_state(_data(ship_status="done"), queue_next=77, autark=True)
    assert "#77" in es["line"], es
    # queue_end_args liefert auto_mode (Default False)
    args = wf.queue_end_args(_data())
    assert args.get("auto_mode") is False, args


def test_mark_ship_open_and_backstep_reset():
    wf = _wf()
    data = _data(phase="phase7_validate")
    wf._mark_ship_open(data)
    assert data["ship_status"] == "open"
    data["ship_status"] = "done"
    wf._mark_ship_open(data)
    assert data["ship_status"] == "done"  # schon gesetzt bleibt
    for fields in ({"no_build_reason": "x"}, {"status": "abandoned"}):
        d = _data(**fields)
        wf._mark_ship_open(d)
        assert "ship_status" not in d, d
    # Ruecksprung vor Phase 8 verwirft die Marker (wie deploy_*)
    d = _data(ship_status="failed", ship_at="t", ship_note="n")
    wf._reset_approvals_on_backstep(d, "phase8_complete", "phase6_implement")
    assert not any(k in d for k in ("ship_status", "ship_at", "ship_note")), d


def test_ship_status_cli_active_archived_and_fallback(tmp_path):
    proj, log, env = _case(tmp_path, "cli", gh=False)
    # a) aktiver Workflow in Phase 8
    _write_active(proj, _data(ship_status="open"))
    res = _workflow(["ship-status", "running", "--note", "PR 5: CI läuft"], env, proj)
    assert res.returncode == 0, res.stderr
    assert res.stdout.strip() == f"SHIP_STATUS=running ({WF})"
    state = json.loads((proj / ".claude" / "workflows" / f"{WF}.json").read_text())
    assert state["ship_status"] == "running" and state["ship_note"] == "PR 5: CI läuft"
    assert state["ship_at"]
    es = _workflow(["endstate"], env, proj)
    assert _kv(es.stdout, "ENDSTATE") == "waiting"
    assert "(PR 5: CI läuft)" in _kv(es.stdout, "FOOTER")
    assert _kv(es.stdout, "SHIP_STATUS") == "running"
    plan = _workflow(["plan"], env, proj).stdout
    assert "▶ Ausliefern  (läuft)" in plan and _last(plan) == _kv(es.stdout, "FOOTER")

    # b) ohne aktiven Workflow: juengster archivierter mit offener Auslieferung
    (proj / ".claude" / "workflows" / f"{WF}.json").unlink()
    (proj / ".claude" / "active_workflow").unlink()
    old = _write_archived(proj, _data(name="feat-1-alt", ship_status="done"))
    cur = _write_archived(proj, _data(ship_status="running"))
    os.utime(old, (1, 1))
    res = _workflow(["ship-status", "done", "--note", "PR 5 gemergt"], env, proj)
    assert res.returncode == 0, res.stderr
    assert res.stdout.strip() == f"SHIP_STATUS=done ({WF})"
    assert json.loads(cur.read_text())["ship_status"] == "done"
    assert json.loads(old.read_text()) == _data(name="feat-1-alt", ship_status="done")  # unberuehrt
    es = _workflow(["endstate", ISSUE], env, proj)
    assert _kv(es.stdout, "ENDSTATE") == "done"
    assert _kv(es.stdout, "FOOTER") == f"✅ Erledigt: #{ISSUE} ist fertig und ausgeliefert{DONE_TAIL}"
    assert _kv(es.stdout, "SHIP_STATUS") == "done"

    # c) explizite Nummer, Note entfaellt ohne --note; failed -> ❗ /60-validate
    res = _workflow(["ship-status", "failed", ISSUE, "--note", "CI rot"], env, proj)
    assert res.returncode == 0, res.stderr
    es = _workflow(["endstate", ISSUE], env, proj)
    assert _kv(es.stdout, "ENDSTATE") == "you"
    assert _kv(es.stdout, "FOOTER").startswith(f"❗ Du: /60-validate #{ISSUE} — Auslieferung fehlgeschlagen (CI rot)")
    # c2) Adversary F001: nach `failed` findet ein erneuter Lauf ohne Nummer den Workflow
    res = _workflow(["ship-status", "running", "--note", "zweiter Versuch"], env, proj)
    assert res.returncode == 0 and res.stdout.strip() == f"SHIP_STATUS=running ({WF})", res.stderr
    assert json.loads(cur.read_text())["ship_note"] == "zweiter Versuch"
    res = _workflow(["ship-status", "skipped", ISSUE], env, proj)
    assert "ship_note" not in json.loads(cur.read_text())

    # d) nichts offen und kein aktiver Workflow: Exit 1 mit Hinweis
    res = _workflow(["ship-status", "done"], env, proj)
    assert res.returncode == 1 and "Issue-Nummer" in res.stderr
    # e) falscher Wert: Usage, Exit 1
    res = _workflow(["ship-status", "green"], env, proj)
    assert res.returncode == 1 and "Usage" in res.stderr


def test_ship_py_reports_status(tmp_path, monkeypatch):
    ship = _ship()
    assert ship._workflow_py() == str(WORKFLOW_PY)
    proj, log, env = _case(tmp_path, "shippy", gh=False)
    cur = _write_archived(proj, _data(ship_status="open"))
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(proj))
    monkeypatch.chdir(proj)
    ship.ship_status("running", "PR 9: CI läuft")
    assert json.loads(cur.read_text())["ship_status"] == "running"
    assert json.loads(cur.read_text())["ship_note"] == "PR 9: CI läuft"
    ship.ship_status("done", "PR 9 gemergt")
    assert json.loads(cur.read_text())["ship_status"] == "done"
    # Quelltext: jeder Ausgang von main() meldet einen Stand
    src = (SCRIPTS_DIR / "ship.py").read_text(encoding="utf-8")
    for needle in ('ship_status("running"', 'ship_status("failed"', 'ship_status("done"'):
        assert needle in src, needle


def test_herdr_sidebar_shows_pending_ship():
    hb = _bridge()
    wf = _wf()
    # Phase 8 ohne Marker leert die Leiste weiterhin (#466/#550)
    assert hb.build_report(_data()) is None
    for status, state in (("open", "du"), ("running", "läuft"), ("failed", "du")):
        rep = hb.build_report(_data(ship_status=status))
        assert rep is not None, status
        assert rep["tokens"]["step"] == "SHIP", rep
        assert rep["tokens"]["state"] == state, (status, rep)
        assert rep["tokens"]["state"] == {"done": "erledigt", "waiting": "läuft", "you": "du"}[
            wf.end_state(_data(ship_status=status), **wf.queue_end_args(_data()))["kind"]]
    assert hb.build_report(_data(ship_status="done")) is None


def test_commands_describe_ship_status():
    validate = (COMMANDS_DIR / "60-validate.md").read_text(encoding="utf-8")
    assert "ship-status" in validate
    assert "ship-status skipped" in validate or "ship-status skipped" in validate.replace("`", "")
    # Step 4 erklaert, dass Phase 8 nur „Code fertig“ heisst
    assert re.search(r"Code fertig", validate)
    intake = (COMMANDS_DIR / "00-intake.md").read_text(encoding="utf-8")
    assert "issue-brief" in intake
    # Skills sind nachgezogen
    skill = (REPO_ROOT / "skills" / "60-validate" / "SKILL.md").read_text(encoding="utf-8")
    assert "ship-status" in skill
