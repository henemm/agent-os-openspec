"""TDD RED — Fix #230: freigegebene Spec darf nach Approval nicht mehr geändert werden.

Bildet AC-1 bis AC-6 der Spec `docs/specs/fix-230-spec-freeze-after-approval.md` ab.

Ausgangslage: `edit_gate.py` erlaubt aktuell JEDE Datei unter `docs/` bzw. mit
`.md`-Endung bedingungslos (ALWAYS_ALLOWED_DIRS / ALWAYS_ALLOWED_PATTERNS,
Schritt 2/2b) — bevor irgendein Phasen- oder Workflow-Check greift. Der
docs-updater-Agent kann deshalb die freigegebene Spec-Datei (`spec_file`)
anfassen, ihren `spec_sha256()` verändern und damit `_check_po_briefing()`
für jede spätere Transition `>= phase4_approved` (inkl. `phase8_complete`)
blockieren lassen ("PO-Briefing ist veraltet").

Subprozess-Muster analog `tests/test_edit_gate_ac_check.py`: hermetisches
Fake-Projekt (`.git` + `.claude/workflows/`), JSON-Payload über stdin,
`OPENSPEC_ACTIVE_WORKFLOW`-Env + `CLAUDE_PROJECT_DIR` + isoliertes `HOME`.
Kein Mocking — echte Dateien in tmp_path.

RED-Erwartung (gegen den aktuellen Code, vor Implementierung von #230):
  * AC-2 (test_edit_at_approval_blocked)     → FÄLLT: returncode 0 statt 2
    (docs/.md-Kurzschluss lässt den Edit unconditional durch)
  * AC-2 (test_edit_after_approval_blocked)  → FÄLLT: returncode 0 statt 2
    (deckt den ursprünglichen #230-Fall bei phase8_complete ab)
  * AC-4 (test_docs_updater_...)             → FÄLLT: neue Freeze-Regel fehlt noch
  * AC-5 (test_validate_command_...)         → FÄLLT: Freeze-Hinweis fehlt noch
  * AC-6 (test_template_placeholder_removed) → FÄLLT: Platzhalter steht noch drin
Regressionsschutz (schon grün, MUSS grün bleiben — Bestandsverhalten):
  * AC-1 (test_edit_before_approval_allowed)
  * AC-3 (test_edit_with_override_allowed)   — heute schon 0, weil ALLES erlaubt ist;
    bleibt nach dem Fix 0, aber dann WEIL der Override-Token greift, nicht mehr
    weil der docs/.md-Kurzschluss alles durchwinkt.
"""

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
EDIT_GATE = HOOKS_DIR / "edit_gate.py"
DOCS_UPDATER_MD = REPO_ROOT / "core" / "agents" / "docs-updater.md"
VALIDATE_MD = REPO_ROOT / "core" / "commands" / "60-validate.md"
TEMPLATE_MD = REPO_ROOT / "docs" / "specs" / "_template.md"


# --- Subprozess-Harness ---

def _run_edit_gate(env: dict, file_path: str, cwd: str) -> subprocess.CompletedProcess:
    payload = json.dumps({"tool_input": {"file_path": file_path}})
    full_env = dict(os.environ)
    full_env.update(env)
    return subprocess.run(
        [sys.executable, str(EDIT_GATE)],
        input=payload, capture_output=True, text=True, env=full_env, cwd=cwd,
    )


def _make_project(tmp_path: Path) -> Path:
    proj = tmp_path / "project"
    (proj / ".git").mkdir(parents=True)
    (proj / ".claude" / "workflows").mkdir(parents=True)
    return proj


def _write_workflow(proj: Path, name: str, phase: str, spec_rel: str) -> None:
    wf = {
        "name": name,
        "current_phase": phase,
        "spec_file": spec_rel,
        "affected_files": [],
        "red_test_done": True,
    }
    (proj / ".claude" / "workflows" / f"{name}.json").write_text(json.dumps(wf))


def _write_token(proj: Path, workflow_name: str) -> None:
    (proj / ".claude" / "user_override_token.json").write_text(json.dumps({
        "version": 2,
        "tokens": {workflow_name: {
            "created": datetime.now().isoformat(),
            "granted_by": "user_prompt",
        }},
    }))


def _env(proj: Path, name: str, home: Path) -> dict:
    return {
        "CLAUDE_PROJECT_DIR": str(proj),
        "OPENSPEC_ACTIVE_WORKFLOW": name,
        "HOME": str(home),
    }


def _make_spec(proj: Path, rel: str = "docs/specs/fix-230-test.md") -> Path:
    spec = proj / rel
    spec.parent.mkdir(parents=True, exist_ok=True)
    spec.write_text("# Test-Spec\n\n## Acceptance Criteria\n\n- **AC-1:** Platzhalter.\n")
    return spec


# --- AC-1: Edit vor Freigabe bleibt erlaubt (Regressionsschutz) ---

def test_edit_before_approval_allowed(tmp_path):
    """AC-1: Workflow in phase3_spec, Edit auf die eigene spec_file → allow() (Exit 0)."""
    proj = _make_project(tmp_path)
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    spec = _make_spec(proj)
    _write_workflow(proj, "draft-wf", "phase3_spec", "docs/specs/fix-230-test.md")

    result = _run_edit_gate(_env(proj, "draft-wf", home), str(spec), cwd=str(proj))

    assert result.returncode == 0, (
        f"Spec vor Freigabe muss weiterhin frei bearbeitbar sein, "
        f"aber returncode={result.returncode}. stderr={result.stderr!r}"
    )


# --- AC-2: Edit ab Freigabe ohne Override wird blockiert (RED heute) ---

def test_edit_at_approval_blocked(tmp_path):
    """AC-2 (RED): current_phase=phase4_approved, kein Override-Token → Exit 2.

    Heute FÄLLT dieser Test: der docs/.md-Kurzschluss in edit_gate.py Schritt 2/2b
    erlaubt die Änderung bedingungslos, bevor irgendein Phasen-Check greift.
    """
    proj = _make_project(tmp_path)
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    spec = _make_spec(proj)
    _write_workflow(proj, "approved-wf", "phase4_approved", "docs/specs/fix-230-test.md")

    result = _run_edit_gate(_env(proj, "approved-wf", home), str(spec), cwd=str(proj))

    assert result.returncode == 2, (
        f"Freigegebene Spec (phase4_approved) muss ohne Override blockiert werden, "
        f"aber returncode={result.returncode}. stderr={result.stderr!r}"
    )
    assert "override" in result.stderr.lower(), (
        f"Blockmeldung muss auf den Override-Weg verweisen. stderr={result.stderr!r}"
    )


def test_edit_after_approval_blocked(tmp_path):
    """AC-2 (RED): current_phase=phase8_complete, kein Override-Token → Exit 2.

    Deckt den ursprünglichen #230-Fall ab: der docs-updater ändert die Spec kurz
    vor `workflow.py phase phase8_complete` — hier bereits IN phase8_complete
    simuliert (spätester Zeitpunkt, an dem der Guard noch greifen muss).
    """
    proj = _make_project(tmp_path)
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    spec = _make_spec(proj)
    _write_workflow(proj, "done-wf", "phase8_complete", "docs/specs/fix-230-test.md")

    result = _run_edit_gate(_env(proj, "done-wf", home), str(spec), cwd=str(proj))

    assert result.returncode == 2, (
        f"Spec darf auch in phase8_complete nicht mehr durch docs-updater "
        f"angefasst werden, aber returncode={result.returncode}. stderr={result.stderr!r}"
    )


# --- AC-3: Override-Token gibt die Änderung trotzdem frei (Regressionsschutz) ---

def test_edit_with_override_allowed(tmp_path):
    """AC-3: Gleicher Zustand wie AC-2 (phase8_complete), aber mit gültigem
    Override-Token für den Workflow → allow() (Exit 0) trotz Freeze."""
    proj = _make_project(tmp_path)
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    spec = _make_spec(proj)
    _write_workflow(proj, "override-wf", "phase8_complete", "docs/specs/fix-230-test.md")
    _write_token(proj, "override-wf")

    result = _run_edit_gate(_env(proj, "override-wf", home), str(spec), cwd=str(proj))

    assert result.returncode == 0, (
        f"Mit gültigem Override-Token muss die Änderung trotz Freeze erlaubt sein, "
        f"aber returncode={result.returncode}. stderr={result.stderr!r}"
    )


# --- Known Limitation der Spec ("archivierte Specs sind kein Freeze-Ziel"):
#     abgeschlossener Workflow + stehengebliebene Env-Var (Finding F001) ---

def test_archived_workflow_with_stale_env_var_allows_edit(tmp_path):
    """Archivierter Workflow + stale OPENSPEC_ACTIVE_WORKFLOW → Exit 0.

    Nach `workflow.py finish` wandert die Workflow-JSON nach `_archive/`, die
    `active_workflow`-Datei und der settings.local.json-Eintrag verschwinden —
    aber die Env-Var der aufrufenden Shell bleibt stehen (ein Kindprozess kann
    sie nicht löschen), und `resolve_active_workflow()` prüft diese dritte
    Quelle nicht auf Existenz. Griff der Freeze-Check über
    `_read_active_workflow()` (mit dessen `_archive/`-Fallback), wäre die Spec
    eines längst abgeschlossenen Workflows dauerhaft eingefroren.

    Die Spec garantiert das Gegenteil (Implementation Details: "Archivierte
    Workflows (`_archive/`) werden ausgeschlossen — eine archivierte Spec ist
    kein Freeze-Ziel mehr").
    """
    proj = _make_project(tmp_path)
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    spec = _make_spec(proj)

    # Workflow NUR im Archiv — keine Live-Datei unter .claude/workflows/
    archive = proj / ".claude" / "workflows" / "_archive"
    archive.mkdir(parents=True)
    (archive / "archived-wf.json").write_text(json.dumps({
        "name": "archived-wf",
        "current_phase": "phase8_complete",
        "spec_file": "docs/specs/fix-230-test.md",
        "affected_files": [],
        "red_test_done": True,
    }))

    # Stale Env-Var zeigt weiter auf den archivierten Namen
    result = _run_edit_gate(_env(proj, "archived-wf", home), str(spec), cwd=str(proj))

    assert result.returncode == 0, (
        f"Die Spec eines archivierten Workflows darf nicht eingefroren bleiben, "
        f"auch wenn OPENSPEC_ACTIVE_WORKFLOW noch auf ihn zeigt, "
        f"aber returncode={result.returncode}. stderr={result.stderr!r}"
    )


# --- AC-4: docs-updater.md verbietet das Anfassen freigegebener Specs (RED heute) ---

def test_docs_updater_no_longer_promises_unconditional_spec_edit():
    """AC-4 (RED): docs-updater.md enthält noch keine explizite Freeze-Regel."""
    content = DOCS_UPDATER_MD.read_text()
    lowered = content.lower()

    has_freeze_rule = (
        "freigegeben" in lowered
        and ("nicht mehr bearbeit" in lowered or "schreibgeschützt" in lowered)
    )
    assert has_freeze_rule, (
        "core/agents/docs-updater.md muss nach dem Fix eine explizite Regel "
        "enthalten, dass eine bereits freigegebene Entity-Spec (Phase >= "
        "approved) nicht mehr bearbeitet werden darf (#230)."
    )


# --- AC-5: 60-validate.md nennt die Spec nicht mehr als Bearbeitungsziel (RED heute) ---

def test_validate_command_spec_file_not_edit_target():
    """AC-5 (RED): Step-3-Prompt-Text im 60-validate.md enthält noch keinen
    Freeze-Hinweis für den docs-updater-Dispatch."""
    content = VALIDATE_MD.read_text()
    lowered = content.lower()

    assert "eingefroren" in lowered or "nicht mehr bearbeiten" in lowered or "nicht bearbeiten" in lowered, (
        "core/commands/60-validate.md Step 3 muss ausdrücklich darauf "
        "hinweisen, dass die Spec-Datei nach Freigabe eingefroren ist und "
        "nicht mehr als Bearbeitungsziel für den docs-updater gilt (#230)."
    )


# --- AC-6: Template-Platzhalter verspricht keine nachträgliche Spec-Änderung mehr (RED heute) ---

def test_template_placeholder_removed():
    """AC-6 (RED): _template.md enthält noch den Platzhalter, der eine
    nachträgliche Bearbeitung der freigegebenen Spec verspricht."""
    content = TEMPLATE_MD.read_text()

    assert "wird nach der TDD-RED-Phase eingetragen" not in content, (
        "docs/specs/_template.md darf den Platzhalter 'wird nach der "
        "TDD-RED-Phase eingetragen' nicht mehr enthalten — er verspricht eine "
        "nachträgliche Änderung an der freigegebenen Spec, die der neue "
        "Spec-Freeze-Guard (#230) verhindert."
    )
