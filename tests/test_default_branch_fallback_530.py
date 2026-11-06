"""Auto-Modus: Default-Branch ohne origin/HEAD, Namenskonflikt, Punkt-Verweise (Issue #530) — AC-1 bis AC-9.

Spec: docs/specs/fix-530-default-branch-fallback.md

Vertraege, die diese Tests festlegen (zusaetzlich zur Spec):
- Gelesen wird der Abschnitt ab `### Auto-Modus prüfen` bis `## On Failure` aus
  `core/commands/60-validate.md` UND `skills/60-validate/SKILL.md`; Abschnitts- und
  Listenpunkt-Parser stammen aus `tests/test_ship_default_branch_528.py`.
- Der Push-Punkt ist der Listenpunkt mit „pushen“ im fett gesetzten Titel, der
  Commit-Punkt der mit „Committen“.
- Verweise sind `Punkt N` und `Punkt N und M` im Fliesstext (Whitespace normalisiert)
  des ganzen Abschnitts, einschliesslich der Abschlussvorlage.
- Mutationsproben laufen auf Kopien des Textes im Speicher; keine Repo-Datei wird
  veraendert. Kein Mock.
"""

import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_auto_ship_525 import OFF_MARKER  # noqa: E402
from test_ship_default_branch_528 import (  # noqa: E402
    COMMAND,
    ON_SHIP_HEAD,
    SKILL,
    _fail,
    _find,
    _flat,
    _items,
    _section,
    _texts,
    _title,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
SYNC = REPO_ROOT / "scripts" / "sync_skills.py"
CHANGELOG = REPO_ROOT / "CHANGELOG.md"

ON = "AUTO_SHIP=on"
OFF = "AUTO_SHIP=off"
SYMREF = "git symbolic-ref --short refs/remotes/origin/HEAD"
LS_REMOTE = "git ls-remote --symref origin HEAD"
REF_LINE = "ref: refs/heads/"
DEPLOY_SENTENCE = "löst nie ein Deploy aus"

REF_PAT = re.compile(r"\bPunkt (\d+)(?: und (\d+))?\b")

# Festgehaltene Zuordnung Verweis -> Titel-Stichwort(e) des Listenpunkts und Anzahl
# der Stellen im Abschnitt (Spec, Abschnitt „Verweis-Test“).
EXPECTED_REFS = [
    (r"Nach Punkt (\d+) und (\d+)", ("committen", "pushen"), 1),
    (r"Verbot aus Punkt (\d+)", ("pushen",), 1),
    (r"siehe Punkt (\d+)", ("ausliefern",), 2),
    (r"hängt Punkt (\d+) ab", ("committen",), 1),
]


# --- Helpers -------------------------------------------------------------------

def _item_by_title(path: Path, section: str, word: str, wrong: list) -> "str | None":
    items = _items(section)
    hits = _find(items, lambda t: re.search(word, _title(t), re.IGNORECASE))
    if len(hits) != 1:
        wrong.append(f"  {path.name}: genau ein Punkt mit „{word}“ im Titel erwartet, "
                     f"gefunden {len(hits)}")
        return None
    return items[hits[0]][1]


def _titles(section: str) -> "dict[int, str]":
    return {num: _title(text) for num, text in _items(section)}


def _reference_errors(section: str) -> "list[str]":
    """Prueft alle Verweise „Punkt N“ gegen die Listenpunkte; leere Liste = in Ordnung."""
    titles = _titles(section)
    flat = _flat(section)
    errors = []
    for m in REF_PAT.finditer(flat):
        for g in m.groups():
            if g is not None and int(g) not in titles:
                errors.append(f"Verweis {m.group(0)!r} zeigt auf keinen Listenpunkt "
                              f"(vorhanden: {sorted(titles)})")
    for pat, words, count in EXPECTED_REFS:
        hits = list(re.finditer(pat, flat))
        if len(hits) != count:
            errors.append(f"Verweis /{pat}/ {len(hits)}-mal gefunden, erwartet {count}")
        for m in hits:
            for num, word in zip(m.groups(), words):
                title = titles.get(int(num), "")
                if word not in title.lower():
                    errors.append(f"{m.group(0)!r}: Punkt {num} hat den Titel {title!r}, "
                                  f"erwartet ein Titel mit „{word}“")
    return errors


def _segments(text: str, marker: str, other: str, width: int = 400) -> "list[str]":
    """Textstuecke ab jedem `marker` bis zum naechsten `other` (hoechstens `width` Zeichen)."""
    out = []
    for m in re.finditer(re.escape(marker), text):
        end = m.start() + width
        nxt = text.find(other, m.end())
        if nxt != -1:
            end = min(end, nxt)
        out.append(text[m.start():end])
    return out


# --- AC-1 bis AC-3: Fallback `git ls-remote --symref origin HEAD` ---------------

class TestFallback:

    def test_ls_remote_fallback_after_symbolic_ref(self):
        """AC-1: Push-Punkt nennt erst `symbolic-ref`, bei Fehlschlag `ls-remote --symref` mit `ref: refs/heads/`."""
        wrong = []
        for path, section in _texts():
            item = _item_by_title(path, section, r"pushen", wrong)
            if item is None:
                continue
            missing = [s for s in (SYMREF, LS_REMOTE, REF_LINE) if s not in item]
            if missing:
                wrong += [f"  {path.name}: Punkt „pushen“ nennt nicht: `{s}`" for s in missing]
                continue
            sym_at, ls_at = item.index(SYMREF), item.index(LS_REMOTE)
            if not sym_at < ls_at:
                wrong.append(f"  {path.name}: `ls-remote` steht vor `symbolic-ref` "
                             "(soll zweiter Weg sein)")
                continue
            between = item[sym_at + len(SYMREF):ls_at]
            if not re.search(r"fehl|scheiter", between, re.IGNORECASE):
                wrong.append(f"  {path.name}: `ls-remote` ist nicht an das Fehlschlagen von "
                             f"`symbolic-ref` gebunden: {between[:160]!r}")
            if REF_LINE not in item[ls_at:]:
                wrong.append(f"  {path.name}: Zeile `{REF_LINE}` wird nicht als Ergebnis von "
                             "`ls-remote` ausgewertet")
        _fail("AC-1", wrong)

    def test_both_fail_reports_plainly_on_and_as_before_off(self):
        """AC-2: scheitern beide Wege -> on: nicht pushen, Alltagssprache, nie Git-Auftrag an den PO; off: nicht pushen, in der Abschlussmeldung melden."""
        both = re.compile(r"beide[^.]{0,40}(fehl|scheiter)|(fehl|scheiter)[^.]{0,40}beide",
                          re.IGNORECASE)
        no_push = r"nicht (ge)?push"
        on_need = {
            "nicht pushen": no_push,
            "in Alltagssprache melden": r"Alltagssprache",
            "nie ein Git-Auftrag an den PO": r"\bnie\b[^.]{0,40}Git-Auftrag[^.]{0,30}\bPO\b",
        }
        off_need = {
            "nicht pushen": no_push,
            "in der Abschlussmeldung melden": r"Abschlussmeldung[^.]{0,40}meld"
                                              r"|meld[^.]{0,40}Abschlussmeldung",
        }
        wrong = []
        for path, section in _texts():
            item = _item_by_title(path, section, r"pushen", wrong)
            if item is None:
                continue
            m = both.search(item)
            if not m:
                wrong.append(f"  {path.name}: Punkt „pushen“ regelt nicht den Fall, dass "
                             "beide Wege scheitern")
                continue
            tail = item[m.start():]
            for flag, other, need in ((ON, OFF, on_need), (OFF, ON, off_need)):
                segs = _segments(tail, flag, other)
                if not segs:
                    wrong.append(f"  {path.name}: kein `{flag}`-Fall nach „beide scheitern“")
                    continue
                if not any(all(re.search(p, s, re.IGNORECASE) for p in need.values())
                           for s in segs):
                    best = max(segs, key=lambda s: sum(bool(re.search(p, s, re.IGNORECASE))
                                                       for p in need.values()))
                    lacking = [lbl for lbl, p in need.items()
                               if not re.search(p, best, re.IGNORECASE)]
                    wrong.append(f"  {path.name}: `{flag}`-Fall nach „beide scheitern“ "
                                 f"nennt nicht: {lacking}")
        _fail("AC-2", wrong)

    def test_commit_point_refers_to_determination_in_push_point(self):
        """AC-3: Commit-Punkt verweist für den Default-Branch auf den Push-Punkt, ohne `symbolic-ref` zu wiederholen."""
        near = re.compile(r"Default-Branch[^.]{0,160}\bPunkt (\d+)\b"
                          r"|\bPunkt (\d+)\b[^.]{0,160}Default-Branch")
        wrong = []
        for path, section in _texts():
            item = _item_by_title(path, section, r"committen", wrong)
            if item is None:
                continue
            titles = _titles(section)
            if "symbolic-ref" in item:
                wrong.append(f"  {path.name}: Punkt „Committen“ wiederholt den "
                             "`symbolic-ref`-Befehl")
            refs = [int(g) for m in near.finditer(item) for g in m.groups() if g]
            if not any("pushen" in titles.get(n, "").lower() for n in refs):
                wrong.append(f"  {path.name}: Punkt „Committen“ verweist für den "
                             f"Default-Branch nicht auf den Push-Punkt (Verweise: {refs})")
        _fail("AC-3", wrong)


# --- AC-4: Namenskonflikt lokal oder auf dem Remote -----------------------------

class TestNameConflict:

    def test_conflict_local_or_remote_gets_suffix(self):
        """AC-4: „Existiert der Name schon lokal oder auf dem Remote“ -> `-2`, `-3` angehängt."""
        pat = re.compile(r"(existiert|vorhanden|bereits|schon)[^.]{0,60}"
                         r"lokal oder auf dem Remote[^.]{0,80}`-2`[^.]{0,20}`-3`",
                         re.IGNORECASE)
        wrong = []
        for path, section in _texts():
            item = _item_by_title(path, section, r"committen", wrong)
            if item is None:
                continue
            m = pat.search(item)
            if not m:
                wrong.append(f"  {path.name}: Namenskonflikt nennt nicht „lokal oder auf "
                             "dem Remote“ mit Suffix `-2`, `-3`")
                continue
            sentence_end = item.find(".", m.end())
            sentence = item[m.start(): sentence_end if sentence_end != -1 else None]
            if not re.search(r"anhäng|angehängt", sentence, re.IGNORECASE):
                wrong.append(f"  {path.name}: Suffix wird im Konflikt-Satz nicht als "
                             f"angehängt beschrieben: {sentence!r}")
        _fail("AC-4", wrong)


# --- AC-5, AC-6: Verweise „Punkt N“ -------------------------------------------

class TestPointReferences:

    def test_every_reference_matches_item_title(self):
        """AC-5: jeder Verweis zeigt auf einen existierenden Punkt, Zuordnung zum Titel stimmt."""
        wrong = []
        for path, section in _texts():
            wrong += [f"  {path.name}: {e}" for e in _reference_errors(section)]
        _fail("AC-5", wrong)

    def test_wrong_reference_is_detected(self):
        """AC-6: Mutationsprobe — ein verschobener Verweis wird rot gemeldet, das Original nicht."""
        section = _section(COMMAND)
        wrong = []
        if _reference_errors(section):
            wrong.append(f"  Original meldet Fehler: {_reference_errors(section)}")
        titles = _titles(section)
        bad = max(titles) + 3
        mutations = {}
        # Mutiert wird der Rohtext (Listenstruktur bleibt erhalten); Zeilenumbrueche im
        # Verweis sind erlaubt.
        m = re.search(r"Verbot\s+aus\s+Punkt\s+(\d+)", section)
        if m is None:
            wrong.append("  Mutationsbasis fehlt: „Verbot aus Punkt N“ nicht im Text")
        else:
            other = next(n for n in sorted(titles) if "pushen" not in titles[n].lower())
            mutations["Verbot aus Punkt -> falscher Punkt"] = (
                section[:m.start(1)] + str(other) + section[m.end(1):])
            mutations["Verbot aus Punkt -> nicht existierender Punkt"] = (
                section[:m.start(1)] + str(bad) + section[m.end(1):])
        m = re.search(r"Nach\s+Punkt\s+(\d+)\s+und\s+(\d+)", section)
        if m is None:
            wrong.append("  Mutationsbasis fehlt: „Nach Punkt N und M“ nicht im Text")
        else:
            mutations["Nach Punkt N und M -> M vertauscht"] = (
                section[:m.start(2)] + m.group(1) + section[m.end(2):])
        # Umnummerierung der Liste ohne Nachziehen der Verweise: Punkt 2 und 3 tauschen.
        renum = re.sub(r"(?m)^2\. \*\*", "9. **", section)
        renum = re.sub(r"(?m)^3\. \*\*", "2. **", renum)
        renum = re.sub(r"(?m)^9\. \*\*", "3. **", renum)
        mutations["Listenpunkte 2 und 3 umnummeriert"] = renum
        for label, mutated in mutations.items():
            if mutated == section:
                wrong.append(f"  Mutation {label!r} hat den Text nicht verändert")
                continue
            if not _reference_errors(mutated):
                wrong.append(f"  Mutation {label!r} wird nicht erkannt")
        _fail("AC-6", wrong)


# --- AC-7: 4000-Zeichen-Fenster aus #472/#489 ----------------------------------

class TestWindow:

    def test_deploy_sentence_within_4000_chars(self):
        """AC-7: vom ersten `AUTONOMY=auto` bis zum Ende von „löst nie ein Deploy aus“ < 4000 Zeichen; on-/off-Texte vorhanden."""
        wrong = []
        for path in (COMMAND, SKILL):
            text = path.read_text(encoding="utf-8")
            start = text.index("AUTONOMY=auto")
            at = text.find(DEPLOY_SENTENCE, start)
            if at == -1:
                wrong.append(f"  {path.name}: Deploy-Satz fehlt nach `AUTONOMY=auto`")
                continue
            dist = at + len(DEPLOY_SENTENCE) - start
            if dist >= 4000:
                wrong.append(f"  {path.name}: Deploy-Satz endet {dist} Zeichen nach dem ersten "
                             "`AUTONOMY=auto` (soll unter 4000)")
            flat = _flat(_section(path))
            for label, kept in (("on-Text #525", ON_SHIP_HEAD),
                                ("off-Text 4.5.4", OFF_MARKER + " gilt unverändert:")):
                if kept not in flat:
                    wrong.append(f"  {path.name}: {label} fehlt: {kept!r}")
        _fail("AC-7", wrong)


# --- AC-8: Skill-Sync -----------------------------------------------------------

def test_skills_in_sync():
    """AC-8: skills/60-validate/SKILL.md ist aus core/commands/60-validate.md generiert."""
    res = subprocess.run([sys.executable, str(SYNC), "--check"], capture_output=True,
                         text=True, cwd=str(REPO_ROOT), timeout=60)
    assert res.returncode == 0, res.stdout + res.stderr


# --- AC-9: CHANGELOG ------------------------------------------------------------

def test_changelog_mentions_530():
    """AC-9 (release-fest): CHANGELOG.md nennt #530 ab der Zeile `## [Unreleased]`."""
    text = CHANGELOG.read_text(encoding="utf-8")
    start = text.index("## [Unreleased]")
    found = "#530" in text[start:]
    assert found, "Kein #530-Eintrag ab [Unreleased] im CHANGELOG"
