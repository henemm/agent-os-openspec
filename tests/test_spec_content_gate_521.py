"""Spec-Inhaltspruefung des CI-Gates lokal bei der Freigabe (Issue #521) — AC-1 bis AC-13.

Spec: docs/specs/fix-521-spec-platzhalter-lokal.md

Befund (#508): Eine Spec, deren AC eine Testzeile mit dem Wort TODO samt
Doppelpunkt zitierte, kam lokal durch die Freigabe (Ampel gruen) und scheiterte
erst in der CI. Kuenftig liegt die Regel einmal in `workflow.py`
(`check_spec_content`, `PLACEHOLDER_MARKERS`); CI-Gate und Freigabe (Listener,
`phase phase4_approved`, `auto-approve`) rufen sie auf.

Testaufbau: echte tmp-Projekte (Spec unter `docs/specs/`, Workflow-State als
JSON, Briefing per `set-briefing` registriert), Aufrufe als Subprozess — kein
Mock der Pruefregel. `_check_spec_content` wird in einem frischen
Python-Subprozess aufgerufen, damit Caches und `sys.modules` je Projekt frisch
sind.

Der Platzhalter-Text wird zur Laufzeit zusammengesetzt (`PH`), damit diese
Datei selbst keinen Platzhalter-Marker im Quelltext traegt.
"""

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
SCRIPTS_DIR = REPO_ROOT / "scripts"
WORKFLOW_PY = HOOKS_DIR / "workflow.py"
LISTENER_PY = HOOKS_DIR / "phase_listener.py"
CI_GATE_PY = SCRIPTS_DIR / "ci_spec_gate.py"
CHANGELOG = REPO_ROOT / "CHANGELOG.md"

WF = "fix-521-demo"
REL_SPEC = "docs/specs/demo.md"
REL_BRIEFING = "docs/briefings/demo.md"
REL_CODE = "src/app.py"

# Platzhalter zur Laufzeit zusammensetzen (siehe Modul-Docstring).
PH = "TO" + "DO:"
MARKER = PH.lower()

AUTO_CONFIG = "autonomy:\n  mode: auto\n"

ADR_FILLED = (
    "## Architektur-Entscheidung (ADR)\n\n"
    "- **ADR-Nr.:** keine\n"
    "- **Rationale:** Reine Ergaenzung ohne Architektur-Relevanz.\n\n"
)
ADR_EMPTY = (
    "## Architektur-Entscheidung (ADR)\n\n"
    "- **ADR-Nr.:** \n"
    "- **Rationale:** Diese Entscheidung betrifft die interne Struktur.\n\n"
)

AC_OK = (
    "- **AC-1:** Given ein angemeldeter Nutzer / When er auf Senden klickt / "
    "Then erscheint eine Bestaetigung.\n"
)
# Zitat einer Testzeile mit Platzhalter — genau der Fall aus #508.
AC_QUOTED_PLACEHOLDER = (
    "- **AC-1:** Given die Testzeile `assert ok  # " + PH + " entfernen` im Test / "
    "When der Nutzer auf Senden klickt / Then erscheint eine Bestaetigung.\n"
)
AC_SHORT = "- **AC-1:** Given x / Then y.\n"

TEST_PLAN = "## Test Plan\n\n- `pytest tests/test_feature.py`\n\n"


def _spec(*, ac: str = AC_OK, test_plan: bool = True, adr: str = ADR_FILLED,
          purpose: str = "Etwas Nuetzliches fuer Nutzer.") -> str:
    return (
        "---\n"
        "entity_id: demo\n"
        "type: feature\n"
        "status: draft\n"
        "---\n\n"
        "# Demo\n\n"
        f"## Purpose\n\n{purpose}\n\n"
        "## Scope\n\n"
        "- **Affected Files:** `src/app.py`\n"
        "- **Estimated Changes:** ~40 LoC\n\n"
        "## Definition of Done\n\n"
        "- [ ] Jede Acceptance Criterion ist durch einen automatischen Test belegt\n"
        "- [ ] Der Nutzer sieht nach dem Klick sein Ergebnis\n\n"
        "## Acceptance Criteria\n\n"
        f"{ac}\n"
        + (TEST_PLAN if test_plan else "")
        + adr
        + "## Changelog\n\n- 2026-11-05: Initial\n"
    )


SPEC_COMPLETE = _spec()
SPEC_PLACEHOLDER = _spec(ac=AC_QUOTED_PLACEHOLDER)
SPEC_NO_TEST_PLAN = _spec(test_plan=False)
SPEC_SHORT_AC = _spec(ac=AC_SHORT)
SPEC_ADR_EMPTY = _spec(adr=ADR_EMPTY)
# Mehrere Befunde auf einmal (fuer die Paritaet): fehlender Test Plan,
# zu knappes AC und ein Platzhalter im Fliesstext.
SPEC_MULTI = _spec(ac=AC_SHORT, test_plan=False,
                   purpose="Etwas Nuetzliches. " + PH + " Zielgruppe klaeren.")

BRIEFING = (
    "# PO-Briefing: demo\n\n"
    "- **Spec:** docs/specs/demo.md\n\n"
    "## Was gebaut wird\n\n"
    "Nutzer bekommen nach dem Senden eine sichtbare Bestaetigung.\n\n"
    "## Definition of Done\n\n"
    "Fertig, wenn ein angemeldeter Nutzer nach dem Klick die Bestaetigung sieht.\n\n"
    "## Wie geprueft wird\n\n"
    "Ein automatischer Test klickt stellvertretend und prueft die Bestaetigung.\n\n"
    "## Kritische Anmerkungen\n\n"
    "- Keine offene Entscheidung fuer den PO.\n\n"
    "## Ampel\n\nAmpel: gruen\n"
)

MSG_MISSING_TEST_PLAN = "Pflicht-Sektion '## Test Plan' fehlt."
ADR_MSG_KEY = "ohne ausgefülltes ADR-Feld"


# --- Helpers ---------------------------------------------------------------

def _env(proj: Path) -> dict:
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("HERDR_", "OPENSPEC_"))}
    env["CLAUDE_PROJECT_DIR"] = str(proj)
    env["HOME"] = str(proj / "_home")
    env["OPENSPEC_ACTIVE_WORKFLOW"] = WF
    return env


def _cli(args, proj: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(WORKFLOW_PY), *args],
                          capture_output=True, text=True, env=_env(proj),
                          cwd=str(proj), timeout=60)


def _listener(proj: Path, prompt: str = "approved") -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(LISTENER_PY)],
                          input=json.dumps({"prompt": prompt}),
                          capture_output=True, text=True, env=_env(proj),
                          cwd=str(proj), timeout=60)


def _ci(proj: Path, changed: "list[str] | None" = None) -> subprocess.CompletedProcess:
    changed = changed or [REL_CODE, REL_SPEC, REL_BRIEFING]
    env = {k: v for k, v in os.environ.items() if not k.startswith(("HERDR_", "OPENSPEC_"))}
    return subprocess.run(
        [sys.executable, str(CI_GATE_PY), "--root", str(proj), "--changed-files", *changed],
        capture_output=True, text=True, env=env, timeout=60,
    )


def _wf_path(proj: Path) -> Path:
    return proj / ".claude" / "workflows" / f"{WF}.json"


def _state(proj: Path) -> dict:
    return json.loads(_wf_path(proj).read_text())


def _write_state(proj: Path, **fields) -> None:
    data = _state(proj)
    data.update(fields)
    _wf_path(proj).write_text(json.dumps(data))


def _write(proj: Path, rel: str, content: str) -> Path:
    path = proj / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


def _project(tmp_path: Path, spec: str = SPEC_COMPLETE, *, name: str = "proj",
             config: str = AUTO_CONFIG) -> Path:
    """tmp-Projekt in phase3_spec: Config, Spec, Briefing (per set-briefing), Code-Datei."""
    proj = tmp_path / name
    (proj / ".git").mkdir(parents=True)
    (proj / ".claude" / "workflows" / "_log").mkdir(parents=True)
    (proj / "_home").mkdir()
    (proj / "openspec.yaml").write_text(config)
    _write(proj, REL_SPEC, spec)
    _write(proj, REL_BRIEFING, BRIEFING)
    _write(proj, REL_CODE, "def f():\n    return 1\n")
    _wf_path(proj).write_text(json.dumps({
        "name": WF, "workflow_type": "feature", "current_phase": "phase3_spec",
        "context_file": "docs/context.md", "spec_file": REL_SPEC,
        "spec_approved": False, "phase_transitions": [], "phase_log": [],
        "approvals": [],
    }))
    (proj / ".claude" / "active_workflow").write_text(WF)
    res = _cli(["set-briefing", REL_BRIEFING], proj)
    assert res.returncode == 0, f"set-briefing: {res.stdout!r} {res.stderr!r}"
    return proj


_PROBE = (
    "import json, sys\n"
    "sys.path.insert(0, sys.argv[1])\n"
    "import workflow\n"
    "data = json.loads(sys.argv[2])\n"
    "print(json.dumps(workflow._check_spec_content(data)))\n"
)


def _local_check(proj: Path, data: "dict | None" = None) -> "str | None":
    """`workflow._check_spec_content(data)` in frischem Subprozess (Projekt = proj)."""
    if data is None:
        data = _state(proj)
    res = subprocess.run(
        [sys.executable, "-c", _PROBE, str(HOOKS_DIR), json.dumps(data)],
        capture_output=True, text=True, env=_env(proj), cwd=str(proj), timeout=60,
    )
    assert res.returncode == 0, (
        f"_check_spec_content nicht aufrufbar: rc={res.returncode} stderr={res.stderr!r}"
    )
    lines = [ln for ln in res.stdout.splitlines() if ln.strip()]
    assert lines, f"keine Ausgabe: stdout={res.stdout!r} stderr={res.stderr!r}"
    return json.loads(lines[-1])


def _auto_approve(proj: Path) -> "tuple[str, str, subprocess.CompletedProcess]":
    res = _cli(["auto-approve"], proj)
    assert res.returncode == 0, f"auto-approve rc={res.returncode} {res.stdout!r} {res.stderr!r}"
    verdict = re.search(r"^AUTO_APPROVE=(\w+)\s*$", res.stdout, re.M)
    reason = re.search(r"^REASON=(.*)$", res.stdout, re.M)
    assert verdict and reason, f"stdout={res.stdout!r} stderr={res.stderr!r}"
    return verdict.group(1), reason.group(1), res


def _ci_spec_findings(res: subprocess.CompletedProcess, rel: str = REL_SPEC) -> "list[str]":
    """CI-Befunde zur Spec-Datei, ohne Pfad-Praefix (Briefing-Befunde gefiltert)."""
    prefix = f"{rel}: "
    out = []
    for line in res.stdout.splitlines():
        m = re.match(r"^  - (.*)$", line)
        if m and m.group(1).startswith(prefix):
            out.append(m.group(1)[len(prefix):].strip())
    return out


def _block_text(res: subprocess.CompletedProcess) -> str:
    return res.stderr + "\n" + res.stdout


# --- AC-1/2/3/5: Freigabe blockiert -----------------------------------------

class TestApprovalBlocked:

    def test_listener_blocks_placeholder_in_spec(self, tmp_path):
        """AC-1: Zitat mit Platzhalter im AC → 'approved' setzt spec_approved nicht,
        die Block-Meldung nennt den Platzhalter."""
        proj = _project(tmp_path, SPEC_PLACEHOLDER)
        res = _listener(proj)
        data = _state(proj)
        assert data.get("spec_approved") is not True, (
            f"spec_approved trotz Platzhalter gesetzt: stderr={res.stderr!r}"
        )
        assert data.get("current_phase") == "phase3_spec", data.get("current_phase")
        text = _block_text(res)
        assert "Platzhalter" in text and MARKER in text.lower(), text

    def test_auto_approve_returns_human_with_reason(self, tmp_path):
        """AC-2: auto-approve → AUTO_APPROVE=human, REASON beginnt mit 'Spec: '
        und nennt den Platzhalter."""
        proj = _project(tmp_path, SPEC_PLACEHOLDER)
        before = _wf_path(proj).read_bytes()
        verdict, reason, res = _auto_approve(proj)
        assert verdict == "human", res.stdout
        assert reason.startswith("Spec: "), reason
        assert "Platzhalter" in reason and MARKER in reason.lower(), reason
        assert _wf_path(proj).read_bytes() == before, "State darf bei human unveraendert bleiben"

    def test_phase_transition_blocks_placeholder_in_spec(self, tmp_path):
        """AC-3: phase3_spec mit gueltigem Briefing → `phase phase4_approved`
        wird blockiert, die Meldung nennt den Platzhalter."""
        proj = _project(tmp_path, SPEC_PLACEHOLDER)
        # Freigabe-Flag gesetzt, damit nicht schon das Freigabe-Gate blockt.
        _write_state(proj, spec_approved=True)
        res = _cli(["phase", "phase4_approved"], proj)
        assert res.returncode != 0, (
            f"Uebergang trotz Platzhalter erlaubt: stdout={res.stdout!r} stderr={res.stderr!r}"
        )
        assert _state(proj)["current_phase"] == "phase3_spec"
        text = _block_text(res)
        assert "Platzhalter" in text and MARKER in text.lower(), text

    def test_missing_section_and_short_ac_block_locally(self, tmp_path):
        """AC-5: fehlende Pflicht-Sektion Test Plan bzw. AC-N unter 30 Zeichen →
        der Listener blockt mit dem Wortlaut der CI."""
        cases = (
            ("no-tp", SPEC_NO_TEST_PLAN, MSG_MISSING_TEST_PLAN),
            ("short-ac", SPEC_SHORT_AC, None),  # Wortlaut aus der CI-Ausgabe
        )
        for name, spec, expected in cases:
            proj = _project(tmp_path, spec, name=name)
            ci = _ci(proj)
            assert ci.returncode == 1, f"{name}: CI muss ablehnen: {ci.stdout!r}"
            findings = _ci_spec_findings(ci)
            if expected is None:
                findings = [f for f in findings if "zu knapp" in f]
                assert findings, f"{name}: kein AC-Laengen-Befund der CI: {ci.stdout!r}"
                expected = findings[0]
            else:
                assert expected in findings, f"{name}: CI-Wortlaut geaendert: {ci.stdout!r}"
            res = _listener(proj)
            data = _state(proj)
            assert data.get("spec_approved") is not True, (
                f"{name}: spec_approved trotz Befund gesetzt: stderr={res.stderr!r}"
            )
            assert data.get("current_phase") == "phase3_spec"
            assert expected in _block_text(res), (
                f"{name}: CI-Wortlaut {expected!r} fehlt in der Block-Meldung: {res.stderr!r}"
            )


# --- AC-4/12: Paritaet mit dem CI-Gate --------------------------------------

class TestCiParity:

    def test_local_message_contains_every_ci_finding(self, tmp_path):
        """AC-4: Jeder CI-Befund zur Spec (ohne Pfad-Praefix) steckt in der lokalen
        Meldung (`_check_spec_content` und Listener-Block)."""
        for name, spec in (("placeholder", SPEC_PLACEHOLDER), ("multi", SPEC_MULTI)):
            proj = _project(tmp_path, spec, name=name)
            ci = _ci(proj)
            assert ci.returncode == 1, f"{name}: CI muss ablehnen: {ci.stdout!r}"
            findings = _ci_spec_findings(ci)
            assert findings, f"{name}: keine Spec-Befunde in der CI-Ausgabe: {ci.stdout!r}"
            if name == "placeholder":
                assert any("Platzhalter" in f for f in findings), ci.stdout

            local = _local_check(proj)
            assert local, f"{name}: lokale Pruefung meldet nichts, CI aber {findings!r}"
            res = _listener(proj)
            block = _block_text(res)
            for finding in findings:
                assert finding in local, (
                    f"{name}: CI-Befund {finding!r} fehlt in _check_spec_content: {local!r}"
                )
                assert finding in block, (
                    f"{name}: CI-Befund {finding!r} fehlt in der Listener-Meldung: {res.stderr!r}"
                )

    def test_old_workflow_copy_fails_closed_with_update_hint(self, tmp_path):
        """AC-12: Projekt-Kopie von workflow.py ohne `check_spec_content` → CI meldet
        einen Befund mit Hinweis `setup.py --update` und endet mit Exit 1."""
        proj = tmp_path / "old"
        hooks = proj / "core" / "hooks"
        hooks.mkdir(parents=True)
        # Veraltete Projekt-Kopie: kennt die Briefing-/ADR-Funktionen, die das
        # CI-Gate heute aufruft, aber kein check_spec_content.
        (hooks / "workflow.py").write_text(
            '"""Veraltete workflow.py-Kopie ohne check_spec_content (Test #521)."""\n\n'
            "def check_adr_content(content):\n"
            "    return None\n\n\n"
            "def check_briefing_content(content, max_words=None):\n"
            "    return None\n\n\n"
            "def parse_briefing_frontmatter(content):\n"
            "    lines = content.splitlines()\n"
            "    if not lines or lines[0].strip() != '---':\n"
            "        return {}\n"
            "    out = {}\n"
            "    for line in lines[1:]:\n"
            "        if line.strip() == '---':\n"
            "            break\n"
            "        key, _, value = line.partition(':')\n"
            "        out[key.strip()] = value.strip()\n"
            "    return out\n"
        )
        _write(proj, REL_SPEC, SPEC_COMPLETE)
        _write(proj, REL_CODE, "def f():\n    return 1\n")
        sha = hashlib.sha256((proj / REL_SPEC).read_bytes()).hexdigest()
        _write(proj, REL_BRIEFING,
               f"---\nspec_file: {REL_SPEC}\nspec_sha256: {sha}\n---\n\n" + BRIEFING)
        res = _ci(proj)
        assert res.returncode == 1, (
            f"Veraltete workflow.py-Kopie muss fail-closed sein: rc={res.returncode} "
            f"stdout={res.stdout!r} stderr={res.stderr!r}"
        )
        assert "setup.py --update" in res.stdout, res.stdout


# --- AC-6: vollstaendige Spec ------------------------------------------------

class TestApprovalPasses:

    def test_complete_spec_passes_all_three_paths(self, tmp_path):
        """AC-6: vollstaendige Spec ohne Platzhalter → Listener, `phase
        phase4_approved` und `auto-approve` geben frei."""
        # Vorbedingung: die Fixture ist CI-vollstaendig.
        ci_proj = _project(tmp_path, SPEC_COMPLETE, name="ci")
        ci = _ci(ci_proj)
        assert ci.returncode == 0, f"Fixture nicht CI-vollstaendig: {ci.stdout!r}"

        # 1. Listener
        proj = _project(tmp_path, SPEC_COMPLETE, name="listener")
        res = _listener(proj)
        data = _state(proj)
        assert data.get("spec_approved") is True, f"stderr={res.stderr!r} stdout={res.stdout!r}"
        assert data.get("current_phase") == "phase4_approved", data.get("current_phase")

        # 2. workflow.py phase phase4_approved
        proj = _project(tmp_path, SPEC_COMPLETE, name="phase")
        _write_state(proj, spec_approved=True)
        res = _cli(["phase", "phase4_approved"], proj)
        assert res.returncode == 0, f"stdout={res.stdout!r} stderr={res.stderr!r}"
        assert _state(proj)["current_phase"] == "phase4_approved"

        # 3. auto-approve
        proj = _project(tmp_path, SPEC_COMPLETE, name="auto")
        verdict, reason, res = _auto_approve(proj)
        assert verdict == "done", f"REASON={reason!r} stdout={res.stdout!r}"
        assert _state(proj).get("spec_approved") is True


# --- AC-7/8/10: Geltungsbereich ---------------------------------------------

class TestScopeOfCheck:

    def test_fast_track_and_foreign_paths_not_checked(self, tmp_path):
        """AC-7: Platzhalter-Spec unter docs/specs/fast/ bzw. ausserhalb von
        docs/specs/ → `_check_spec_content` liefert None."""
        proj = _project(tmp_path, SPEC_PLACEHOLDER)
        base = _state(proj)
        # Gegenprobe: dieselbe Spec unter docs/specs/ wird geprueft.
        assert _local_check(proj, dict(base, spec_file=REL_SPEC)), (
            "Gegenprobe: Platzhalter-Spec unter docs/specs/ muss einen Befund liefern"
        )
        for rel in ("docs/specs/fast/demo.md", "specs/demo.md", "docs/other/demo.md"):
            _write(proj, rel, SPEC_PLACEHOLDER)
            result = _local_check(proj, dict(base, spec_file=rel))
            assert result is None, f"{rel}: nicht von der CI geprueft, lokal aber: {result!r}"

    def test_kill_switch_disables_local_check(self, tmp_path):
        """AC-8: `ci_spec_gate.enabled: false` → die Platzhalter-Spec wird lokal
        nicht geprueft (Listener und auto-approve geben frei)."""
        config = AUTO_CONFIG + "ci_spec_gate:\n  enabled: false\n"
        proj = _project(tmp_path, SPEC_PLACEHOLDER, name="listener", config=config)
        assert _local_check(proj) is None
        res = _listener(proj)
        data = _state(proj)
        assert data.get("spec_approved") is True, f"stderr={res.stderr!r}"
        assert data.get("current_phase") == "phase4_approved"

        proj = _project(tmp_path, SPEC_PLACEHOLDER, name="auto", config=config)
        verdict, reason, res = _auto_approve(proj)
        assert verdict == "done", f"REASON={reason!r} stdout={res.stdout!r}"

    def test_later_phase_transition_not_blocked(self, tmp_path):
        """AC-10: Workflow in phase6_implement mit Platzhalter in der Spec →
        ein spaeterer Phasenwechsel wird von der Spec-Pruefung nicht blockiert.

        Ziel ist `phase6b_adversary` statt `phase7_validate`: seit
        fix-schritte-ueberspringen verlangt Phase 7 den Adversary-Nachweis, der
        hier nichts zur Sache tut. Die Spec-Pruefung (ab phase4) liegt auf beiden
        Wegen gleich."""
        proj = _project(tmp_path, SPEC_PLACEHOLDER)
        _write_state(proj, current_phase="phase6_implement", spec_approved=True,
                     red_test_done=True)
        res = _cli(["phase", "phase6b_adversary"], proj)
        assert res.returncode == 0, f"stdout={res.stdout!r} stderr={res.stderr!r}"
        assert _state(proj)["current_phase"] == "phase6b_adversary"


# --- AC-9: ADR-Befund nicht doppelt -----------------------------------------

class TestAdrNotDuplicated:

    def test_single_adr_message_in_listener_block(self, tmp_path):
        """AC-9: leeres ADR-Feld bei aktivem ADR-Gate → genau eine ADR-Meldung im
        Listener-Block; bei abgeschaltetem ADR-Gate meldet der Spec-Wrapper sie."""
        # a) ADR-Gate aktiv: _check_adr meldet, der Spec-Wrapper nicht.
        proj = _project(tmp_path, SPEC_ADR_EMPTY, name="adr-on")
        res = _listener(proj)
        assert _state(proj).get("spec_approved") is not True, res.stderr
        assert res.stderr.count(ADR_MSG_KEY) == 1, (
            f"ADR-Meldung nicht genau einmal: {res.stderr!r}"
        )
        local = _local_check(proj)
        assert not (local and ADR_MSG_KEY in local), (
            f"Spec-Wrapper meldet ADR trotz aktivem ADR-Gate: {local!r}"
        )

        # b) ADR-Gate aus: der Spec-Wrapper meldet den ADR-Befund wie die CI.
        config = AUTO_CONFIG + "adr_gate:\n  enabled: false\n"
        proj = _project(tmp_path, SPEC_ADR_EMPTY, name="adr-off", config=config)
        local = _local_check(proj)
        assert local and ADR_MSG_KEY in local, (
            f"Spec-Wrapper muss bei abgeschaltetem ADR-Gate den ADR-Befund melden: {local!r}"
        )
        res = _listener(proj)
        assert _state(proj).get("spec_approved") is not True, (
            f"Freigabe trotz leerem ADR-Feld (ADR-Gate aus, CI-Gate an): {res.stderr!r}"
        )
        assert res.stderr.count(ADR_MSG_KEY) == 1, (
            f"ADR-Meldung nicht genau einmal: {res.stderr!r}"
        )


# --- AC-11: eine Platzhalter-Liste ------------------------------------------

class TestSingleList:

    def test_only_one_placeholder_list(self):
        """AC-11: genau eine Definition `PLACEHOLDER_MARKERS` (in workflow.py), kein
        `SPEC_PLACEHOLDERS` in ci_spec_gate, kein `_PO_BRIEFING_PLACEHOLDERS` in
        workflow; ein Briefing mit spitzer Klammer + 'platzhalter' bleibt abgelehnt."""
        sources = sorted(HOOKS_DIR.glob("*.py")) + sorted(SCRIPTS_DIR.glob("*.py"))
        definition = re.compile(r"^[ \t]*PLACEHOLDER_MARKERS\b[^=\n]*=(?!=)", re.M)
        hits = [(p.relative_to(REPO_ROOT).as_posix(), len(definition.findall(p.read_text())))
                for p in sources]
        hits = [(rel, n) for rel, n in hits if n]
        assert hits == [("core/hooks/workflow.py", 1)], (
            f"Erwartet genau eine Definition PLACEHOLDER_MARKERS in workflow.py: {hits!r}"
        )
        assert "SPEC_PLACEHOLDERS" not in (SCRIPTS_DIR / "ci_spec_gate.py").read_text()
        assert "_PO_BRIEFING_PLACEHOLDERS" not in WORKFLOW_PY.read_text()

        if str(HOOKS_DIR) not in sys.path:
            sys.path.insert(0, str(HOOKS_DIR))
        import workflow  # noqa: PLC0415

        expected = {"[" + "todo", "[" + "tbd", "to" + "do:", "fix" + "me:", "xx" + "x:", "<platzhalter"}
        assert set(workflow.PLACEHOLDER_MARKERS) == expected, workflow.PLACEHOLDER_MARKERS

        complete = BRIEFING
        assert workflow.check_briefing_content(complete) is None, (
            "Vorbedingung: das Briefing ohne Marker ist vollstaendig"
        )
        marked = complete.replace(
            "- Keine offene Entscheidung fuer den PO.",
            "- <Platzhalter: offene Entscheidung fuer den PO eintragen>",
        )
        err = workflow.check_briefing_content(marked)
        assert err and "Platzhalter" in err, err


# --- AC-13: CHANGELOG --------------------------------------------------------

def test_changelog_mentions_521():
    """AC-13 (release-fest): CHANGELOG.md nennt #521 ab der Zeile `## [Unreleased]`,
    also unter [Unreleased] oder in irgendeinem Versionsabschnitt danach."""
    text = CHANGELOG.read_text()
    start = text.index("## [Unreleased]")
    assert "#521" in text[start:], "Kein #521-Eintrag ab [Unreleased] im CHANGELOG"
