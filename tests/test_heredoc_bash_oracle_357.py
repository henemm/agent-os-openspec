"""#357: strip_heredoc_bodies gegen bash als Orakel (Differenztest).

Jede Zeile traegt eine harmlose Sonde (`: >exec_<n>`); was bash wirklich
ausfuehrt, muss im Ergebnis von strip_heredoc_bodies stehen bleiben. Kleine,
feste Stichprobe fuer CI; breiter: python3 tests/heredoc_bash_oracle.py 1000 <seed>.
"""

import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="bash fehlt")


@pytest.mark.parametrize("seed", [11, 357])
def test_no_executed_line_is_stripped(seed):
    import heredoc_bash_oracle as oracle
    stats, findings = oracle.run(120, seed)
    assert stats["total"] == 120
    assert not findings, findings[:3]


def test_generator_erzeugt_unmaskierte_klammer_quote_zeilen():
    """AC-8 (#365): Body-Zeilen mit `)` vor `"` kommen ohne `#`-Maskierung vor."""
    import random
    import heredoc_bash_oracle as oracle
    hits = []
    for seed in (11, 357):
        rng = random.Random(seed)
        for _ in range(300):
            for text, _p, role in oracle.make_snippet(rng).lines:
                if role != "body" or " #" in text or ")" not in text:
                    continue
                if '"' in text[text.index(")"):]:
                    hits.append(text)
    assert hits, "Generator maskiert alle )-/Quote-Zeilen im Body"


@pytest.mark.parametrize("seed", [11, 357])
def test_feste_stichprobe_findet_keine_ausgefuehrte_folgezeile_im_strip(seed):
    """AC-9, Klasse #365: bash beendet $( ... ) an einer Body-Zeile wie `y)"`.

    Jede Folgezeile, die bash dann ausfuehrt, muss im strip-Ergebnis stehen.
    """
    import heredoc_bash_oracle as oracle
    stats, findings = oracle.run(120, seed)
    assert stats["total"] == 120
    assert not findings, findings[:3]
