"""Issue #665: veraltete Kommentare in config.yaml (herdr.auto_clear, CONTEXT_CUT).

Pinnt, dass nur Kommentare geaendert wurden (AC-1) und dass die Kommentare
den Stand nach #658/#662/#663 beschreiben (AC-2, AC-3).
"""
import re
import subprocess
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
CONFIG = REPO / "config.yaml"


def _lines():
    return CONFIG.read_text(encoding="utf-8").splitlines()


def _comment_block_before(key):
    """Kommentarzeilen unmittelbar vor dem Top-Level-Schluessel `key:`."""
    lines = _lines()
    idx = next(i for i, l in enumerate(lines) if l.startswith(f"{key}:"))
    block = []
    i = idx - 1
    while i >= 0 and lines[i].startswith("#"):
        block.insert(0, lines[i])
        i -= 1
    assert block, f"kein Kommentarblock vor {key}:"
    return "\n".join(block)


def _section_with_header(key):
    """Kommentarkopf vor `key:` plus alle Zeilen bis zum naechsten Top-Level-Schluessel."""
    lines = _lines()
    idx = next(i for i, l in enumerate(lines) if l.startswith(f"{key}:"))
    end = idx + 1
    top_level = re.compile(r"^[A-Za-z_][\w-]*:")
    while end < len(lines) and not top_level.match(lines[end]):
        end += 1
    return _comment_block_before(key) + "\n" + "\n".join(lines[idx:end])


def test_loaded_config_unchanged():
    """AC-1: yaml.safe_load liefert dieselben Daten wie origin/main."""
    result = subprocess.run(
        ["git", "show", "origin/main:config.yaml"],
        cwd=REPO, capture_output=True, text=True,
    )
    assert result.returncode == 0, f"git show fehlgeschlagen: {result.stderr}"
    before = yaml.safe_load(result.stdout)
    after = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    assert after["context_budget"] == before["context_budget"]
    assert after["herdr"] == before["herdr"]
    assert after == before


def test_context_budget_comment_names_context_stop():
    """AC-2: CONTEXT_STOP=on ist das Haltesignal, Herdr tippt kein /clear."""
    block = _comment_block_before("context_budget")
    flat = " ".join(l.lstrip("# ").strip() for l in block.splitlines())
    assert "CONTEXT_STOP=on" in flat
    assert "(oder Herdr) tippt /clear" not in flat
    assert "oder Herdr" not in flat


def test_herdr_comment_marks_auto_clear_dead():
    """AC-3: auto_clear und OPENSPEC_HERDR_AUTO_CLEAR als wirkungslos (#663) markiert."""
    section = _section_with_header("herdr")
    flat = " ".join(l.strip().lstrip("#").strip() for l in section.splitlines())
    assert "wirkungslos" in flat
    assert "#663" in flat
    assert "OPENSPEC_HERDR_AUTO_CLEAR" in flat
    assert "detachter Runner" not in flat
    assert "Auto-/clear an Phasengrenzen" not in flat
    assert "Wartezeit nach dem Stop vor /clear" not in flat
