"""Schliesst tests/fixtures/ von der pytest-Sammlung aus.

tests/fixtures/precondition_origins/{swift,python}/... enthaelt absichtlich
nachgebauten Beispielcode, der wie eine echte Test-/Produktionsdatei aussieht
(z.B. python/tests/test_task.py) -- das ist Testmaterial FUER
precondition_origins.py, kein Testmodul fuer pytest selbst.

Bewusst HIER (tests/conftest.py), nicht in tests/fixtures/conftest.py: Ein
conftest.py DIREKT in tests/fixtures/ zwingt pytest, dieses Verzeichnis beim
Einlesen der Ignore-Regel selbst auf sys.path zu setzen -- damit waere
`tests/fixtures/precondition_origins/` als bare `import precondition_origins`
erreichbar und koennte das echte Modul aus core/hooks/precondition_origins.py
verdecken (implizites Namespace-Package, PEP 420). tests/ steht ohnehin schon
auf sys.path (alle Testmodule hier werden so importiert); ein zusaetzliches
conftest.py an dieser Stelle aendert daran nichts.
"""

collect_ignore = ["fixtures"]


# --- Herdr-Isolation (Issue #466, AC-15) ------------------------------------
# Laeuft ein Entwickler in einem Herdr-Pane, sind HERDR_* im Environment gesetzt
# und wuerden an jeden Subprozess der Tests vererbt. Die Herdr-Bridge
# (core/hooks/herdr_bridge.py) wuerde dann die echte Sidebar des Entwicklers mit
# Test-Workflows bespielen. Deshalb entfernt diese autouse-Fixture die Variablen
# fuer jeden Test; Tests, die die Bridge pruefen, setzen sie per monkeypatch neu.
import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _strip_herdr_env(monkeypatch):
    for var in ("HERDR_ENV", "HERDR_PANE_ID", "HERDR_BIN_PATH", "HERDR_SOCKET_PATH"):
        monkeypatch.delenv(var, raising=False)
