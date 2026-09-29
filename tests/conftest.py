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
