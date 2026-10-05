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
