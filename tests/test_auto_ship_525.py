"""Auto-Modus: Claude erstellt PR, wartet auf CI und mergt (Issue #525) — AC-1 bis AC-14.

Spec: docs/specs/feat-525-auto-ship.md

Vertraege, die diese Tests festlegen (zusaetzlich zur Spec):
- CLI `workflow.py auto-ship` laeuft als Subprozess in einem tmp-Projekt mit
  `config.yaml` (Plugin-Block `autonomy`, #372); alle OPENSPEC_*/HERDR_*-Variablen
  werden gestrippt und je Fall gezielt gesetzt; HOME zeigt ins Testverzeichnis.
- Ausgabe: stdout besteht aus genau einer Zeile `AUTO_SHIP=on|off`, Exit 0.
- Command-Text-Tests lesen den Abschnitt ab `### Auto-Modus prüfen` bis
  `## On Failure` aus `core/commands/60-validate.md` UND `skills/60-validate/SKILL.md`
  (generierte Skills schreiben `$WF` statt `python3 .claude/hooks/workflow.py`).

Kein Mock der Entscheidungsregel: jeder CLI-Fall laeuft gegen das echte workflow.py.
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOW_PY = REPO_ROOT / "core" / "hooks" / "workflow.py"
SYNC = REPO_ROOT / "scripts" / "sync_skills.py"
CHANGELOG = REPO_ROOT / "CHANGELOG.md"
COMMAND = REPO_ROOT / "core" / "commands" / "60-validate.md"
SKILL = REPO_ROOT / "skills" / "60-validate" / "SKILL.md"

ON = "AUTO_SHIP=on"
OFF = "AUTO_SHIP=off"
ENV_VAR = "OPENSPEC_AUTONOMY"
NO_SECTION = "project:\n  name: x\n"

SECTION_START = "### Auto-Modus prüfen"
SECTION_END = "## On Failure"


# --- Helpers: CLI ----------------------------------------------------------

def _sandbox(tmp_path: Path, config: "str | None") -> "tuple[Path, Path]":
    proj = tmp_path / "proj"
    (proj / ".git").mkdir(parents=True)
    (proj / ".claude" / "workflows" / "_log").mkdir(parents=True)
    proj = proj.resolve()
    home = (tmp_path / "home").resolve()
    (home / ".claude").mkdir(parents=True)
    if config is not None:
        (proj / "config.yaml").write_text(config)
    return proj, home


def _env(proj: Path, home: Path, switch: "str | None" = None) -> dict:
    env = {k: v for k, v in os.environ.items()
           if k not in {"CLAUDE_TOOL_INPUT", "CLAUDE_PLUGIN_ROOT", "PYTHONPATH"}
           and not k.startswith(("OPENSPEC_", "HERDR_", "GIT_"))}
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["CLAUDE_PROJECT_DIR"] = str(proj)
    env["HOME"] = str(home)
    if switch is not None:
        env[ENV_VAR] = switch
    return env


def _auto_ship(proj: Path, home: Path, switch: "str | None" = None):
    return subprocess.run([sys.executable, str(WORKFLOW_PY), "auto-ship"],
                          capture_output=True, text=True,
                          env=_env(proj, home, switch), cwd=str(proj), timeout=60)


def _check(label: str, res, want: str) -> list:
    lines = res.stdout.splitlines()
    if res.returncode != 0 or lines != [want]:
        return [f"  {label}: rc={res.returncode}, stdout={res.stdout!r} "
                f"(soll genau eine Zeile {want!r}), stderr={res.stderr.strip()[:200]!r}"]
    return []


def _fail(ac: str, wrong: list) -> None:
    assert not wrong, f"{ac}: {len(wrong)} Abweichungen:\n" + "\n".join(wrong)


# --- Helpers: Command-Text --------------------------------------------------

def _section(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    assert SECTION_START in text, f"{path}: Abschnitt {SECTION_START!r} fehlt"
    start = text.index(SECTION_START)
    end = text.index(SECTION_END, start)
    return text[start:end]


def _texts() -> "list[tuple[Path, str]]":
    return [(COMMAND, _section(COMMAND)), (SKILL, _section(SKILL))]


def _flat(text: str) -> str:
    """Zeilenumbrueche und Mehrfach-Leerzeichen zu einem Leerzeichen (Fliesstext-Suche)."""
    return re.sub(r"\s+", " ", text)


def _on_windows(text: str, width: int = 4000) -> "list[str]":
    """Textfenster ab jeder Erwaehnung von `AUTO_SHIP=on` (der `on`-Fall)."""
    flat = _flat(text)
    return [flat[m.start(): m.start() + width] for m in re.finditer(re.escape(ON), flat)]


def _missing(text: str, patterns: dict) -> list:
    flat = _flat(text)
    return [label for label, pat in patterns.items()
            if not re.search(pat, flat, re.IGNORECASE)]


# --- AC-1 bis AC-6: CLI -----------------------------------------------------

class TestAutoShipCli:

    def test_auto_mode_without_ship_key_is_on(self, tmp_path):
        """AC-1: autonomy.mode: auto ohne ship-Schluessel -> genau `AUTO_SHIP=on`, Exit 0."""
        proj, home = _sandbox(tmp_path, "autonomy:\n  mode: auto\n")
        _fail("AC-1", _check("mode auto, kein ship", _auto_ship(proj, home), ON))

    def test_ship_false_is_off(self, tmp_path):
        """AC-2: autonomy.mode: auto + autonomy.ship: false -> `AUTO_SHIP=off`."""
        proj, home = _sandbox(tmp_path, "autonomy:\n  mode: auto\n  ship: false\n")
        wrong = _check("mode auto, ship false", _auto_ship(proj, home), OFF)
        # Auch die Umgebungsvariable schaltet den Projekt-Schalter nicht wieder an.
        wrong += _check("mode auto, ship false, OPENSPEC_AUTONOMY=auto",
                        _auto_ship(proj, home, "auto"), OFF)
        _fail("AC-2", wrong)

    def test_manual_and_missing_config_are_off(self, tmp_path):
        """AC-3: manual bzw. ohne Config-Eintrag (ohne OPENSPEC_AUTONOMY) -> off."""
        wrong = []
        cases = [
            ("mode manual", "autonomy:\n  mode: manual\n"),
            ("mode manual, ship true", "autonomy:\n  mode: manual\n  ship: true\n"),
            ("kein autonomy-Abschnitt", NO_SECTION),
            ("keine Config-Datei", None),
        ]
        for i, (label, config) in enumerate(cases):
            proj, home = _sandbox(tmp_path / f"c{i}", config)
            wrong += _check(label, _auto_ship(proj, home), OFF)
        _fail("AC-3", wrong)

    def test_env_auto_without_project_entry_is_on(self, tmp_path):
        """AC-4: kein autonomy-Eintrag + OPENSPEC_AUTONOMY=auto -> on."""
        proj, home = _sandbox(tmp_path, NO_SECTION)
        wrong = _check("kein Abschnitt, OPENSPEC_AUTONOMY=auto",
                       _auto_ship(proj, home, "auto"), ON)
        # Gegenprobe: ein Projekteintrag manual hat Vorrang vor der Variablen.
        proj2, home2 = _sandbox(tmp_path / "manual", "autonomy:\n  mode: manual\n")
        wrong += _check("mode manual, OPENSPEC_AUTONOMY=auto",
                        _auto_ship(proj2, home2, "auto"), OFF)
        _fail("AC-4", wrong)

    def test_ship_false_only_in_settings_local_does_not_disable(self, tmp_path):
        """AC-5: ship: false nur in settings.local.json schaltet nicht ab."""
        proj, home = _sandbox(tmp_path, "autonomy:\n  mode: auto\n")
        local = json.dumps({"autonomy": {"ship": False}})
        (proj / ".claude" / "settings.local.json").write_text(local)
        (proj / "settings.local.json").write_text(local)
        (home / ".claude" / "settings.local.json").write_text(local)
        _fail("AC-5", _check("ship false nur lokal", _auto_ship(proj, home), ON))

    def test_always_exit_zero_single_line(self, tmp_path):
        """AC-6: beliebige Zustaende -> Exit 0, genau eine Zeile; nur echtes false schaltet ab."""
        wrong = []
        exact = [
            ("ship als String 'false'", "autonomy:\n  mode: auto\n  ship: 'false'\n", ON),
            ("ship als String 'off'", "autonomy:\n  mode: auto\n  ship: 'off'\n", ON),
            ("ship null", "autonomy:\n  mode: auto\n  ship: null\n", ON),
            ("ship 0", "autonomy:\n  mode: auto\n  ship: 0\n", ON),
            ("ship true", "autonomy:\n  mode: auto\n  ship: true\n", ON),
            ("ship false", "autonomy:\n  mode: auto\n  ship: false\n", OFF),
        ]
        for i, (label, config, want) in enumerate(exact):
            proj, home = _sandbox(tmp_path / f"e{i}", config)
            wrong += _check(label, _auto_ship(proj, home), want)

        # Kein Workflow (kein active_workflow, kein State) und keine Config -> off.
        proj, home = _sandbox(tmp_path / "nowf", None)
        wrong += _check("kein Workflow, keine Config", _auto_ship(proj, home), OFF)

        # Kaputte Config: Exit 0 und genau eine gueltige Zeile (fail-closed ueber
        # autonomy_mode ergibt off, die Spec verlangt nur Form + Exit).
        broken = "autonomy: [unclosed\n  mode: : auto\n\t- x"
        proj, home = _sandbox(tmp_path / "broken", broken)
        for switch in (None, "auto"):
            res = _auto_ship(proj, home, switch)
            if res.returncode != 0 or res.stdout.splitlines() not in ([ON], [OFF]):
                wrong.append(f"  kaputte Config ({ENV_VAR}={switch!r}): "
                             f"rc={res.returncode}, stdout={res.stdout!r}, "
                             f"stderr={res.stderr.strip()[:200]!r}")

        # Verwaister Workflow-Zeiger: Auskunft braucht keinen Workflow.
        proj, home = _sandbox(tmp_path / "dangling", "autonomy:\n  mode: auto\n")
        (proj / ".claude" / "active_workflow").write_text("gibt-es-nicht")
        wrong += _check("verwaister active_workflow", _auto_ship(proj, home), ON)
        _fail("AC-6", wrong)


# --- AC-7 bis AC-12: Command-Text --------------------------------------------

class TestCommandText:

    def test_calls_auto_ship_and_documents_switch(self):
        """AC-7: Aufruf `workflow.py auto-ship`, Zeile `AUTO_SHIP=on`, Schalter `autonomy.ship: false`."""
        wrong = []
        for path, text in _texts():
            if not re.search(r"(?:workflow\.py|\$WF) auto-ship\b", text):
                wrong.append(f"  {path.name}: kein Aufruf `workflow.py auto-ship`")
            if ON not in text:
                wrong.append(f"  {path.name}: Zeile {ON!r} fehlt")
            if "autonomy.ship: false" not in text:
                wrong.append(f"  {path.name}: Schalter `autonomy.ship: false` nicht dokumentiert")
            # Nur die ausdruecklich gelesene Zeile schaltet um; alles andere gilt als off.
            if OFF not in text:
                wrong.append(f"  {path.name}: Rueckfall {OFF!r} nicht genannt")
        _fail("AC-7", wrong)

    def test_describes_pr_ci_merge_chain_and_red_ci(self):
        """AC-8: bei AUTO_SHIP=on: PR anlegen -> CI abwarten -> mergen; rote CI beheben oder in Alltagssprache melden."""
        chain = {
            "PR anlegen": r"\bPR\b[^.]{0,80}\b(anlegen|erstellen|legt|anlegt|erstellt)"
                          r"|(anlegen|erstellen|legt|anlegt|erstellt)[^.]{0,80}\bPR\b",
            "CI abwarten": r"\bCI\b[^.]{0,60}(abwarten|abwartet|warten|wartet)"
                           r"|(abwarten|abwartet|warten|wartet)[^.]{0,60}\bCI\b",
            "grüne CI -> mergen": r"grüne[nr]? CI[^.]{0,200}\bmerg",
            "rote CI beheben": r"rote[nr]? CI[^.]{0,200}(beheben|behebt|reparier)",
            "Alltagssprache melden": r"Alltagssprache[^.]{0,40}(melden|meldet|gemeldet)"
                                     r"|(melden|meldet|gemeldet)[^.]{0,80}Alltagssprache",
        }
        wrong = []
        for path, text in _texts():
            windows = _on_windows(text)
            if not windows:
                wrong.append(f"  {path.name}: kein `{ON}`-Fall im Auto-Modus-Abschnitt")
                continue
            joined = " ".join(windows)
            wrong += [f"  {path.name}: im `{ON}`-Fall fehlt: {m}"
                      for m in _missing(joined, chain)]
        _fail("AC-8", wrong)

    def test_protection_rules_no_force_and_no_ci_fallback(self):
        """AC-9: Schutzregeln nie umgehen, nie --force; ohne CI-Checks gilt die lokale Testsuite."""
        rules = {
            "Schutzregeln nie umgehen": r"Schutzregeln[^.]{0,80}nie[^.]{0,40}umg"
                                        r"|nie[^.]{0,40}Schutzregeln[^.]{0,40}umg",
            "nie --force": r"nie[^.]{0,20}`?--force",
            "rote CI nie überbrücken": r"rote[nr]? CI[^.]{0,20}nie[^.]{0,20}überbrück",
            "ohne CI-Checks -> lokale Testsuite":
                r"(keine|ohne)[^.]{0,20}CI-Checks[^.]{0,200}lokale[nr]? Testsuite",
            "Schutzregel verhindert Merge -> Techniker":
                r"wartet auf Prüfung durch einen Techniker",
        }
        wrong = []
        for path, text in _texts():
            windows = _on_windows(text)
            if not windows:
                wrong.append(f"  {path.name}: kein `{ON}`-Fall im Auto-Modus-Abschnitt")
                continue
            joined = " ".join(windows)
            wrong += [f"  {path.name}: im `{ON}`-Fall fehlt: {m}"
                      for m in _missing(joined, rules)]
        _fail("AC-9", wrong)

    def test_du_line_never_names_git_step_when_on(self):
        """AC-10: bei AUTO_SHIP=on nennt die ❗Du-Zeile nie einen Git-Schritt; die alte
        Vorgabe „Merge/PR prüfen“ ist weg, „Offen beim PO: Merge / PR“ gilt nicht für `on`."""
        old_du = "Die ❗Du-Zeile nennt den nächsten PO-Schritt (Merge/PR prüfen)"
        new_rule = r"❗Du-Zeile[^.]{0,60}\bnie\b[^.]{0,40}Git-Schritt"
        wrong = []
        for path in (COMMAND, SKILL):
            full = path.read_text(encoding="utf-8")
            text = _section(path)
            if old_du in _flat(full):
                wrong.append(f"  {path.name}: alte Vorgabe {old_du!r} steht noch im Text")
            windows = _on_windows(text)
            if not windows:
                wrong.append(f"  {path.name}: kein `{ON}`-Fall im Auto-Modus-Abschnitt")
            elif not any(re.search(new_rule, w) for w in windows):
                wrong.append(f"  {path.name}: im `{ON}`-Fall fehlt die Regel "
                             "„❗Du-Zeile nennt nie einen Git-Schritt“")
            # „Offen beim PO: Merge / PR“ darf nur noch ausdruecklich fuer den off-Fall stehen.
            # Bindung: `AUTO_SHIP=off` in derselben Zeile oder bis zu 5 Zeilen davor.
            lines = full.splitlines()
            for i, line in enumerate(lines):
                if not re.search(r"Offen beim PO:?\**:?\s*Merge\s*/\s*PR", line):
                    continue
                if not any(OFF in prev for prev in lines[max(0, i - 5): i + 1]):
                    wrong.append(f"  {path.name}: „Offen beim PO: Merge / PR“ ohne "
                                 f"Bindung an {OFF!r}: {line.strip()[:160]!r}")
            # Abschlussvorlage im on-Fall nennt das Ergebnis (PR-Link, gemergt).
            if windows and not any(re.search(r"PR-Link", w) for w in windows):
                wrong.append(f"  {path.name}: Abschlussvorlage im `{ON}`-Fall nennt keinen PR-Link")
        _fail("AC-10", wrong)

    def test_off_case_keeps_git_policy_text(self):
        """AC-11: für AUTO_SHIP=off bleibt der 4.5.4-Text zur Git-Policy der Projekt-CLAUDE.md."""
        kept = [
            "**Merge und PR — Git-Policy des Projekts sticht:**",
            "Steht in der `CLAUDE.md` des Projekts",
            "„Git entscheidet Claude selbst“",
            "„PO will mit Git nichts zu tun haben“",
            "Ohne solche Policy bleiben Merge und PR beim PO.",
        ]
        wrong = []
        for path, text in _texts():
            flat = _flat(text)
            wrong += [f"  {path.name}: 4.5.4-Text fehlt: {k!r}" for k in kept
                      if _flat(k) not in flat]
            if OFF not in text:
                wrong.append(f"  {path.name}: der Git-Policy-Text ist nicht an {OFF!r} gebunden")
        _fail("AC-11", wrong)

    def test_deploy_stays_separate(self):
        """AC-12: der Auto-Modus deployt nie; deploy.autonomous bleibt eigene, getrennte Entscheidung."""
        rules = {
            "nie Deploy": r"löst nie ein Deploy aus|deployt nie",
            "deploy.autonomous getrennt": r"`deploy\.autonomous`[^.]{0,200}getrennte",
            "kein /70-deploy": r"Kein `/70-deploy` aus dem Auto-Modus",
        }
        wrong = []
        for path, text in _texts():
            wrong += [f"  {path.name}: fehlt: {m}" for m in _missing(text, rules)]
        _fail("AC-12", wrong)


# --- AC-13: Skill-Sync ---------------------------------------------------------

def test_skills_in_sync():
    """AC-13: skills/60-validate/SKILL.md ist aus core/commands/60-validate.md generiert."""
    res = subprocess.run([sys.executable, str(SYNC), "--check"], capture_output=True,
                         text=True, cwd=str(REPO_ROOT), timeout=60)
    assert res.returncode == 0, res.stdout + res.stderr


# --- AC-14: CHANGELOG ----------------------------------------------------------

def test_changelog_mentions_525():
    """AC-14 (release-fest): CHANGELOG.md nennt #525 ab der Zeile `## [Unreleased]`."""
    text = CHANGELOG.read_text(encoding="utf-8")
    start = text.index("## [Unreleased]")
    assert "#525" in text[start:], "Kein #525-Eintrag ab [Unreleased] im CHANGELOG"
