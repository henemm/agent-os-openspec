"""Tests fuer precondition_origins.py (Issue #285,
docs/specs/feat-285-precondition-origins.md).

Regelweg-Tests gegen mitgelieferte Beispielbaeume (AC-1 bis AC-6, Sprachen
Swift und Python) und gegen den eingefrorenen echten Ausschnitt aus
henemm/loose-ends@c36fec6 (AC-7).

TDD-RED (phase5_tdd_red): `core/hooks/precondition_origins.py` existiert noch
nicht und `config.yaml` traegt den Block `precondition_origins.profiles` noch
nicht (beides Phase 6). Jeder Test importiert das Werkzeug deshalb einzeln
ueber `_import_tool()`, damit das fehlende Modul zu "N failed" fuehrt statt zu
einem Collection-Error, der die ganze Datei blockiert.

Stand nach PO-Entscheidung vom 2026-09-28 (zweite Runde): AC-1 prueft jetzt
zusaetzlich die Filterregel (gelesen werden alle Modellfelder, gelistet nur
die mit Test-Zuweisung -- Feld `notes` als Beleg). AC-7/AC-8 pruefen die
Zugehoerigkeit zu einer "Verdachtsgruppe" (Felder mit hoechstens einer
Produktions-Schreibstelle, Schwelle 12 Zeilen) statt eines Rangplatzes --
"oberste fuenf Zeilen" war am echten Material nachweislich nicht erreichbar
(siehe Spec-Changelog und Purpose-Abschnitt).
"""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures" / "precondition_origins"
SWIFT_ROOT = FIXTURES_DIR / "swift"
PYTHON_ROOT = FIXTURES_DIR / "python"
REFERENCE_ROOT = FIXTURES_DIR / "reference-c36fec6"
AC6_ROOT = FIXTURES_DIR / "ac6_extra_lang"
AC6_CONFIG = FIXTURES_DIR / "ac6_config.yaml"

sys.path.insert(0, str(HOOKS_DIR))


def _import_tool():
    """Importiert precondition_origins bei jedem Testaufruf neu.

    Bewusst kein Modul-Level-Import: Solange core/hooks/precondition_origins.py
    nicht existiert, soll GENAU DIESER Test mit ModuleNotFoundError
    fehlschlagen -- nicht die gesamte Datei beim Einsammeln (Collection Error).
    """
    import precondition_origins  # noqa: F401
    return precondition_origins


def _real_config():
    """Laedt die ECHTE config.yaml dieses Repos ueber config_loader.

    Bewusst NICHT ueber eine eigene Test-Fixture-Config fuer AC-1 bis AC-5 und
    AC-7: Solange `precondition_origins.profiles` dort fehlt (Phase 6 fuegt
    den Block hinzu), schlaegt `load_profile()` fuer diese Tests aus genau
    diesem Grund fehl -- gewollt, siehe Spec-Auftrag.
    """
    from config_loader import load_config
    return load_config()


def _data_rows(table: str) -> list:
    """Markdown-Tabellenzeilen ohne Header/Trennzeile."""
    lines = [line for line in table.splitlines() if line.strip().startswith("|")]
    return [line for line in lines if "---" not in line and "Feld" not in line]


# --- AC-1 ---

def test_ac1_extraction_reads_all_fields_without_naming_them():
    """
    GIVEN einen Beispielbaum mit einer Modelldatei unter dem
    profilkonfigurierten model_globs-Muster (swift:
    Shared/Models/Task.swift mit den VIER Feldern processedAt, energyRaw,
    title, notes; python: models/task.py mit denselben vier Feldern in
    Snake-Case) -- keines davon dem Aufruf als Parameter uebergeben
    WHEN extract_model_fields() die Modelldateien nach dem jeweiligen
    Sprachprofil durchsucht
    THEN liefert es alle vier Feldnamen, ungefragt und vollstaendig -- auch
    notes, das keine Testdatei je zuweist.
    """
    po = _import_tool()
    config = _real_config()

    swift_profile = po.load_profile(config, "swift")
    swift_fields = po.extract_model_fields(SWIFT_ROOT, swift_profile)
    assert set(swift_fields) == {"processedAt", "energyRaw", "title", "notes"}

    python_profile = po.load_profile(config, "python")
    python_fields = po.extract_model_fields(PYTHON_ROOT, python_profile)
    assert set(python_fields) == {"processed_at", "energy_raw", "title", "notes"}


def test_ac1_untested_field_extracted_but_not_listed(monkeypatch, tmp_path):
    """
    GIVEN denselben Beispielbaum -- notes wird von KEINER Testdatei
    zugewiesen, processedAt/energyRaw/title je von mindestens einer
    WHEN das Werkzeug per CLI (main(), --lang swift bzw. --lang python,
    --root auf den Beispielbaum, --out auf eine Datei) laeuft
    THEN enthaelt die Ausgabetabelle nur processedAt, energyRaw und title --
    notes fehlt, obwohl extract_model_fields() es gelesen hat (siehe
    vorheriger Test). Gelesen werden alle Felder, gelistet nur die mit
    Test-Zuweisung.
    """
    po = _import_tool()

    swift_out = tmp_path / "swift_table.md"
    monkeypatch.setattr(sys, "argv", [
        "precondition_origins.py", "--lang", "swift",
        "--root", str(SWIFT_ROOT), "--out", str(swift_out),
    ])
    po.main()
    swift_table = swift_out.read_text()
    assert "processedAt" in swift_table
    assert "energyRaw" in swift_table
    assert "title" in swift_table
    assert "notes" not in swift_table

    python_out = tmp_path / "python_table.md"
    monkeypatch.setattr(sys, "argv", [
        "precondition_origins.py", "--lang", "python",
        "--root", str(PYTHON_ROOT), "--out", str(python_out),
    ])
    po.main()
    python_table = python_out.read_text()
    assert "processed_at" in python_table
    assert "energy_raw" in python_table
    assert "title" in python_table
    assert "notes" not in python_table


# --- AC-2 ---

def test_ac2_local_variables_and_comparisons_produce_no_hit():
    """
    GIVEN Testdateien mit (a) fuenf echten Feld-Zuweisungen
    (task.processedAt = Date(...) / task.processed_at = datetime.now()),
    (b) einer lokalen Variablen gleichen Namens ohne Objektbezug
    (let processedAt = Date() / processed_at = datetime.now()) und (c) einem
    Vergleich (task.processedAt == nil / task.processed_at == None)
    WHEN find_assignments() gegen die Test-Globs fuer processedAt laeuft
    THEN zaehlt es genau die fuenf echten Zuweisungen -- (b) und (c) erzeugen
    keinen Treffer.
    """
    po = _import_tool()
    config = _real_config()

    swift_profile = po.load_profile(config, "swift")
    swift_hits = po.find_assignments(
        SWIFT_ROOT, swift_profile["test_globs"], [],
        ["processedAt"], swift_profile["assignment_pattern"],
    )
    assert len(swift_hits.get("processedAt", [])) == 5
    # Zeile 44 = lokale Variable (Rauschen), Zeile 52 = Vergleich (Rauschen)
    assert not any(h.endswith(":44") for h in swift_hits.get("processedAt", []))
    assert not any(h.endswith(":52") for h in swift_hits.get("processedAt", []))

    python_profile = po.load_profile(config, "python")
    python_hits = po.find_assignments(
        PYTHON_ROOT, python_profile["test_globs"], [],
        ["processed_at"], python_profile["assignment_pattern"],
    )
    assert len(python_hits.get("processed_at", [])) == 5
    # Zeile 46 = lokale Variable (Rauschen), Zeile 54 = Vergleich (Rauschen)
    assert not any(h.endswith(":46") for h in python_hits.get("processed_at", []))
    assert not any(h.endswith(":54") for h in python_hits.get("processed_at", []))


def test_ac2_only_dot_assignments_counted():
    """
    GIVEN eine Testdatei, die das Feld title zweimal echt zuweist
    (task.title = "Renamed" / "Renamed Again") und zusaetzlich einmal nur
    vergleicht (task.title == "Fixed")
    WHEN find_assignments() gegen die Test-Globs fuer title laeuft
    THEN zaehlt es genau die zwei echten Zuweisungen -- der Vergleich zaehlt
    nicht mit, weil nur eine Punkt-Zuweisung (`.title =`), keine
    Punkt-Vergleich (`.title ==`) zaehlt.
    """
    po = _import_tool()
    config = _real_config()

    swift_profile = po.load_profile(config, "swift")
    swift_hits = po.find_assignments(
        SWIFT_ROOT, swift_profile["test_globs"], [],
        ["title"], swift_profile["assignment_pattern"],
    )
    assert len(swift_hits.get("title", [])) == 2
    assert not any(h.endswith(":75") for h in swift_hits.get("title", []))

    python_profile = po.load_profile(config, "python")
    python_hits = po.find_assignments(
        PYTHON_ROOT, python_profile["test_globs"], [],
        ["title"], python_profile["assignment_pattern"],
    )
    assert len(python_hits.get("title", [])) == 2
    assert not any(h.endswith(":77") for h in python_hits.get("title", []))


# --- AC-3 ---

def test_ac3_production_write_sites_counted_and_located():
    """
    GIVEN eine Produktionsdatei mit bekannter Schreibstellen-Zahl je Feld
    (1x processedAt, 0x energyRaw, 3x title; analog processed_at/energy_raw/
    title in python)
    WHEN find_assignments() gegen die Produktions-Globs (minus Excludes)
    laeuft
    THEN zeigt jedes Feld die korrekte Anzahl UND die korrekten
    Datei:Zeile-Fundstellen, in der Reihenfolge, in der sie im Quelltext
    stehen.
    """
    po = _import_tool()
    config = _real_config()

    swift_profile = po.load_profile(config, "swift")
    swift_hits = po.find_assignments(
        SWIFT_ROOT, swift_profile["production_globs"],
        swift_profile["production_exclude_globs"],
        ["processedAt", "energyRaw", "title"], swift_profile["assignment_pattern"],
    )
    assert len(swift_hits.get("processedAt", [])) == 1
    assert swift_hits["processedAt"][0].endswith("EnrichmentWriter.swift:8")
    assert swift_hits.get("energyRaw", []) == []
    assert len(swift_hits.get("title", [])) == 3
    assert [h.split(":")[-1] for h in swift_hits["title"]] == ["13", "18", "23"]

    python_profile = po.load_profile(config, "python")
    python_hits = po.find_assignments(
        PYTHON_ROOT, python_profile["production_globs"],
        python_profile["production_exclude_globs"],
        ["processed_at", "energy_raw", "title"], python_profile["assignment_pattern"],
    )
    assert len(python_hits.get("processed_at", [])) == 1
    assert python_hits["processed_at"][0].endswith("writer.py:12")
    assert python_hits.get("energy_raw", []) == []
    assert len(python_hits.get("title", [])) == 3
    assert [h.split(":")[-1] for h in python_hits["title"]] == ["16", "21", "25"]


# --- AC-4 ---

def test_ac4_table_sorted_ascending_by_production_writes():
    """
    GIVEN die drei Felder aus dem Fixture mit unterschiedlicher
    Schreibstellen-Zahl (energyRaw: 0, processedAt: 1, title: 3), alle mit
    mindestens einer Test-Zuweisung
    WHEN render_table() die Tabelle rendert
    THEN stehen die Zeilen aufsteigend nach Produktions-Schreibstellen
    sortiert: energyRaw vor processedAt vor title.
    """
    po = _import_tool()
    fields = ["processedAt", "energyRaw", "title"]
    test_hits = {
        "processedAt": ["Tests/TaskTests.swift:15"],
        "energyRaw": ["Tests/TaskTests.swift:57"],
        "title": ["Tests/TaskTests.swift:63", "Tests/TaskTests.swift:69"],
    }
    prod_hits = {
        "processedAt": ["Sources/EnrichmentWriter.swift:8"],
        "energyRaw": [],
        "title": [
            "Sources/EnrichmentWriter.swift:13",
            "Sources/EnrichmentWriter.swift:18",
            "Sources/EnrichmentWriter.swift:23",
        ],
    }
    table = po.render_table(fields, test_hits, prod_hits)

    idx_energy = table.index("energyRaw")
    idx_processed = table.index("processedAt")
    idx_title = table.index("title")
    assert idx_energy < idx_processed < idx_title


# --- AC-5 ---

def test_ac5_zero_write_field_on_top_and_marked():
    """
    GIVEN energyRaw mit 0 Produktions-Schreibstellen neben Feldern mit >= 1,
    alle mit mindestens einer Test-Zuweisung
    WHEN render_table() die Tabelle rendert
    THEN steht energyRaw in der obersten Datenzeile, und die Zelle
    "Produktions-Schreibstellen" dieser Zeile enthaelt sichtbar den Text
    "keine Schreibstelle im Produktivcode".
    """
    po = _import_tool()
    fields = ["processedAt", "energyRaw", "title"]
    test_hits = {
        "processedAt": ["Tests/TaskTests.swift:15"],
        "energyRaw": ["Tests/TaskTests.swift:57"],
        "title": ["Tests/TaskTests.swift:63", "Tests/TaskTests.swift:69"],
    }
    prod_hits = {
        "processedAt": ["Sources/EnrichmentWriter.swift:8"],
        "energyRaw": [],
        "title": [
            "Sources/EnrichmentWriter.swift:13",
            "Sources/EnrichmentWriter.swift:18",
            "Sources/EnrichmentWriter.swift:23",
        ],
    }
    table = po.render_table(fields, test_hits, prod_hits)

    rows = _data_rows(table)
    assert rows, "Tabelle enthaelt keine Datenzeilen"
    first_row = rows[0]
    assert "energyRaw" in first_row
    assert "keine Schreibstelle im Produktivcode" in first_row


# --- AC-6 ---

def test_ac6_third_profile_addable_without_code_change():
    """
    GIVEN ein drittes, frei in einer Test-Fixture-Config ergaenztes Profil
    ("kotlin", NICHT die echte config.yaml, kein Codeeingriff in
    precondition_origins.py) mit eigenem model_globs/field_pattern/
    assignment_pattern gegen einen passenden Beispielbaum
    WHEN das Werkzeug mit --lang kotlin laeuft
    THEN liefert es dieselbe Art Tabelle wie fuer swift/python -- und der
    Profilname "kotlin" kommt im Quelltext von precondition_origins.py nicht
    vor (Beleg: kein Code wurde fuer dieses Profil geschrieben).
    """
    po = _import_tool()
    import yaml
    fixture_config = yaml.safe_load(AC6_CONFIG.read_text())

    source = (HOOKS_DIR / "precondition_origins.py").read_text()
    assert "kotlin" not in source, (
        "precondition_origins.py darf keinen Profil-spezifischen Code fuer "
        "'kotlin' enthalten -- AC-6 verlangt Erweiterbarkeit per Config allein"
    )

    profile = po.load_profile(fixture_config, "kotlin")
    fields = po.extract_model_fields(AC6_ROOT, profile)
    assert fields == ["count"]

    test_hits = po.find_assignments(
        AC6_ROOT, profile["test_globs"], [], fields, profile["assignment_pattern"],
    )
    prod_hits = po.find_assignments(
        AC6_ROOT, profile["production_globs"], profile["production_exclude_globs"],
        fields, profile["assignment_pattern"],
    )
    assert len(test_hits.get("count", [])) == 3
    assert len(prod_hits.get("count", [])) == 2

    table = po.render_table(fields, test_hits, prod_hits)
    assert "count" in table
    assert "|" in table


# --- AC-7 ---

def test_ac7_real_frozen_excerpt_field_in_suspect_group():
    """
    GIVEN den eingefrorenen echten Ausschnitt
    tests/fixtures/precondition_origins/reference-c36fec6/ -- UNVERAENDERTE
    Originaldateien aus henemm/loose-ends@c36fec6 (Shared/Models/TaskItem.swift,
    Shared/Enrichment/EnrichmentWriter.swift,
    Shared/Enrichment/EnrichmentCoordinator.swift,
    LooseEndsTests/EnrichmentTests.swift), NICHT gegen nachgebaute Beispiele
    WHEN das Werkzeug mit --lang swift gegen diesen Ausschnitt laeuft (Felder
    extrahieren, Test- und Produktions-Zuweisungen suchen, filtern auf Felder
    mit mindestens einer Test-Zuweisung, Tabelle rendern)
    THEN erscheint processedAt in der Verdachtsgruppe -- den gefilterten
    Zeilen mit hoechstens einer Produktions-Schreibstelle --, diese Gruppe
    umfasst hoechstens 12 Zeilen, und processedAt weist genau eine
    Produktions-Schreibstelle aus: Shared/Enrichment/EnrichmentWriter.swift:94.
    """
    po = _import_tool()
    config = _real_config()
    profile = po.load_profile(config, "swift")

    all_fields = po.extract_model_fields(REFERENCE_ROOT, profile)
    assert "processedAt" in all_fields

    test_hits = po.find_assignments(
        REFERENCE_ROOT, profile["test_globs"], [],
        all_fields, profile["assignment_pattern"],
    )
    prod_hits = po.find_assignments(
        REFERENCE_ROOT, profile["production_globs"],
        profile["production_exclude_globs"],
        all_fields, profile["assignment_pattern"],
    )

    # Genau eine Produktions-Schreibstelle, an der belegten Zeile.
    assert len(prod_hits.get("processedAt", [])) == 1
    assert prod_hits["processedAt"][0].endswith("EnrichmentWriter.swift:94")
    assert len(test_hits.get("processedAt", [])) >= 1

    # Filterregel (Implementation Details, Schritt 5): nur Felder mit
    # mindestens einer Test-Zuweisung zaehlen fuer die Tabelle/Verdachtsgruppe.
    filtered = [f for f in all_fields if test_hits.get(f)]
    assert "processedAt" in filtered

    # Verdachtsgruppe: gefilterte Felder mit hoechstens einer
    # Produktions-Schreibstelle. Schwelle laut AC-7 bewusst 12, nicht der
    # gemessene Wert (10) -- Spielraum fuer zulaessige Profil-Verfeinerungen.
    suspect_group = [f for f in filtered if len(prod_hits.get(f, [])) <= 1]
    assert len(suspect_group) <= 12, (
        f"Verdachtsgruppe umfasst {len(suspect_group)} Zeilen, erlaubt sind "
        f"hoechstens 12: {sorted(suspect_group)}"
    )
    assert "processedAt" in suspect_group

    # Tabellen-Ebene: processedAt und seine Fundstelle erscheinen im
    # gerenderten Ergebnis; ein Feld OHNE Test-Zuweisung (per Konstruktion
    # nicht in `filtered`) darf nicht auftauchen (Filterregel, siehe AC-1).
    excluded_field = next(f for f in all_fields if f not in filtered)
    table = po.render_table(all_fields, test_hits, prod_hits)
    assert "processedAt" in table
    assert "EnrichmentWriter.swift:94" in table
    assert excluded_field not in table


def test_ac7_fixture_missing_fails_not_skips(monkeypatch, capsys):
    """
    GIVEN einen nicht existierenden Pfad anstelle des eingefrorenen
    Ausschnitts
    WHEN das Werkzeug (main()) mit --root auf diesen fehlenden Pfad zeigt
    THEN bricht der Aufruf mit Exit-Code 1 ab und nennt den geprueften Pfad in
    der Meldung (Spec "## Error Handling": "--root existiert nicht oder ist
    keine Verzeichnis -> Exit 1 mit dem geprueften Pfad in der Meldung") --
    er wird NICHT uebersprungen (kein pytest.skip, kein leeres Ergebnis, kein
    stiller Erfolg).
    """
    po = _import_tool()
    missing_root = FIXTURES_DIR / "reference-c36fec6-DOES-NOT-EXIST"
    assert not missing_root.exists()

    monkeypatch.setattr(
        sys, "argv",
        ["precondition_origins.py", "--lang", "swift", "--root", str(missing_root)],
    )
    with pytest.raises(SystemExit) as exc_info:
        po.main()
    assert exc_info.value.code == 1

    captured = capsys.readouterr()
    assert str(missing_root) in (captured.err + captured.out)
