"""Issue #294: Framework-eigene Workflow-Dokumente zaehlen nicht als Produktivcode.

Spec (`docs/specs/`), Kontext (`docs/context/`) und PO-Briefing (`docs/briefings/`)
legt das Framework selbst an. Ohne Projekt-Config durften sie bisher das LoC-Gate
ausloesen (Reproduktion: 342/250 bei einem +1/-1-Fix).
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "core" / "hooks"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_gate_coverage import _run_split_loc_check  # noqa: E402

# Reproduktion aus dem Issue: 342 Zeilen Workflow-Dokumente, 1 Zeile Fix.
REPRO_NUMSTAT = (
    "32\t0\tdocs/briefings/fix-280-worktree-config-isolation.md\n"
    "87\t0\tdocs/context/fix-280-worktree-config-isolation.md\n"
    "223\t0\tdocs/specs/infra/fix-280-worktree-config-isolation.md\n"
    "1\t1\tcore/hooks/hook_utils.py\n"
)


def test_large_spec_small_fix_passes_without_project_config(tmp_path, monkeypatch):
    """DoD 1 + 3: ohne jeden scope_guard-Eintrag blockt die grosse Spec nicht."""
    import config_loader
    import edit_gate
    from unittest.mock import MagicMock, patch

    monkeypatch.setattr(config_loader, "load_config", lambda: {})
    orig_root = edit_gate._root
    edit_gate._root = tmp_path
    try:
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=REPRO_NUMSTAT)
            result = edit_gate._check_loc_delta({}, {"name": "wf"})
    finally:
        edit_gate._root = orig_root
    assert result is None, result


def test_project_excludes_do_not_drop_defaults(tmp_path, monkeypatch):
    """Ein eigener loc_exclude_patterns-Eintrag ersetzt die Defaults nicht."""
    cfg = {"max_loc_delta": 250, "loc_exclude_patterns": [r"\.po$"]}
    assert _run_split_loc_check(tmp_path, monkeypatch, REPRO_NUMSTAT, cfg) is None


def test_real_oversized_code_still_blocks(tmp_path, monkeypatch):
    """DoD 2 (Gegenprobe): uebergrosser Produktivcode blockt weiter."""
    cfg = {"max_loc_delta": 250, "loc_exclude_patterns": []}
    numstat = REPRO_NUMSTAT + "300\t0\tcore/hooks/edit_gate.py\n"
    blocked = _run_split_loc_check(tmp_path, monkeypatch, numstat, cfg)
    assert blocked is not None
    assert "Produktiv 301/250" in blocked, blocked


def test_only_top_level_docs_dirs_are_excluded(tmp_path, monkeypatch):
    """Gegenprobe: gleichnamige Ordner tiefer im Baum bleiben Produktivcode."""
    cfg = {"max_loc_delta": 250, "loc_exclude_patterns": []}
    numstat = "300\t0\tsrc/docs/specs/generator.py\n"
    blocked = _run_split_loc_check(tmp_path, monkeypatch, numstat, cfg)
    assert blocked is not None and "Produktiv 300/250" in blocked, blocked


def test_opt_out_counts_docs_again(tmp_path, monkeypatch):
    """scope_guard.exclude_framework_docs: false stellt das alte Verhalten her."""
    cfg = {"max_loc_delta": 250, "loc_exclude_patterns": [],
           "exclude_framework_docs": False}
    blocked = _run_split_loc_check(tmp_path, monkeypatch, REPRO_NUMSTAT, cfg)
    assert blocked is not None and "Produktiv 343/250" in blocked, blocked


def test_finish_measurement_uses_same_defaults(monkeypatch):
    """workflow.py misst loc_delta_final ueber get_scope_loc_config — gleiche Regel."""
    import config_loader
    monkeypatch.setattr(config_loader, "load_config", lambda: {})
    _, excludes = config_loader.get_scope_loc_config()
    import re
    assert any(re.search(p, "docs/specs/x.md") for p in excludes)
    assert not any(re.search(p, "docs/WORKFLOW_GUIDE.md") for p in excludes)
