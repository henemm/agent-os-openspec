"""Auto-Modus: Ausliefer-Pfad bei Checkout auf dem Default-Branch (Issue #528) — AC-1 bis AC-10.

Spec: docs/specs/fix-528-ship-default-branch.md

Vertraege, die diese Tests festlegen (zusaetzlich zur Spec):
- Gelesen wird der Abschnitt ab `### Auto-Modus prüfen` bis `## On Failure` aus
  `core/commands/60-validate.md` UND `skills/60-validate/SKILL.md` (generierte Skills
  schreiben `$WF` statt `python3 .claude/hooks/workflow.py`).
- Die Auto-Modus-Liste beginnt nach der Zeile `Bei `AUTONOMY=auto``; ein Listenpunkt
  ist eine Zeile `<n>. ` am Zeilenanfang samt aller eingerueckten Folgezeilen. Er endet
  am naechsten Listenpunkt oder an der ersten nicht eingerueckten Textzeile.
- Ein Listenpunkt wird ueber seinen fett gesetzten Titel (`**...**` am Anfang) erkannt:
  „Committen“, „pushen“, „Deploy bleibt beim PO“; der Ausliefer-Punkt ueber den
  on-Text `**Bei `AUTO_SHIP=on` liefert Claude selbst aus:**`.
- Gesucht wird im Fliesstext (Whitespace normalisiert). Kein Mock.
"""

import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_auto_ship_525 import OFF_MARKER, _on_windows  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
SYNC = REPO_ROOT / "scripts" / "sync_skills.py"
CHANGELOG = REPO_ROOT / "CHANGELOG.md"
COMMAND = REPO_ROOT / "core" / "commands" / "60-validate.md"
SKILL = REPO_ROOT / "skills" / "60-validate" / "SKILL.md"

ON = "AUTO_SHIP=on"
OFF = "AUTO_SHIP=off"
SECTION_START = "### Auto-Modus prüfen"
SECTION_END = "## On Failure"
LIST_START = "Bei `AUTONOMY=auto`"

AUTO_SHIP_CALL = r"(?:workflow\.py|\$WF) auto-ship\b"
ON_SHIP_HEAD = "**Bei `AUTO_SHIP=on` liefert Claude selbst aus:**"


# --- Helpers -------------------------------------------------------------------

def _section(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    assert SECTION_START in text, f"{path}: Abschnitt {SECTION_START!r} fehlt"
    start = text.index(SECTION_START)
    end = text.index(SECTION_END, start)
    return text[start:end]


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _items(section: str) -> "list[tuple[int, str]]":
    """Nummerierte Punkte der Auto-Modus-Liste als (Nummer, Fliesstext)."""
    assert LIST_START in section, f"Listeneinleitung {LIST_START!r} fehlt"
    lines = section[section.index(LIST_START):].splitlines()[1:]
    items, current = [], None
    for line in lines:
        head = re.match(r"^(\d+)\.\s", line)
        if head:
            if current:
                items.append(current)
            current = [int(head.group(1)), [line]]
        elif current is not None:
            if line.strip() and not line.startswith((" ", "\t")):
                break
            current[1].append(line)
    if current:
        items.append(current)
    return [(num, _flat("\n".join(body)).strip()) for num, body in items]


def _title(item: str) -> str:
    m = re.match(r"^\d+\.\s+\*\*(.+?)\*\*", item)
    return m.group(1) if m else ""


def _find(items, pred) -> "list[int]":
    """Positionen (0-basiert) aller Punkte, auf die `pred` zutrifft."""
    return [i for i, (_, text) in enumerate(items) if pred(text)]


def _texts() -> "list[tuple[Path, str]]":
    return [(COMMAND, _section(COMMAND)), (SKILL, _section(SKILL))]


def _fail(ac: str, wrong: list) -> None:
    assert not wrong, f"{ac}: {len(wrong)} Abweichungen:\n" + "\n".join(wrong)


def _commit_item(path: Path, section: str, wrong: list) -> "str | None":
    items = _items(section)
    hits = _find(items, lambda t: re.search(r"committen", _title(t), re.IGNORECASE))
    if len(hits) != 1:
        wrong.append(f"  {path.name}: genau ein Punkt „Committen“ erwartet, "
                     f"gefunden {len(hits)}")
        return None
    return items[hits[0]][1]


# --- AC-1, AC-6, AC-7: Reihenfolge und Zuschnitt der Liste ---------------------

class TestOrder:

    def test_auto_ship_check_precedes_commit_point(self):
        """AC-1: `workflow.py auto-ship` steht als eigener Punkt vor „Committen“."""
        wrong = []
        for path, section in _texts():
            items = _items(section)
            nums = [n for n, _ in items]
            if nums != list(range(1, len(nums) + 1)):
                wrong.append(f"  {path.name}: Punkte nicht fortlaufend nummeriert: {nums}")
            ship = _find(items, lambda t: re.search(AUTO_SHIP_CALL, t))
            commit = _find(items, lambda t: re.search(r"committen", _title(t), re.IGNORECASE))
            if len(ship) != 1:
                wrong.append(f"  {path.name}: Aufruf `auto-ship` in {len(ship)} Punkten "
                             "(soll genau einer)")
                continue
            if len(commit) != 1:
                wrong.append(f"  {path.name}: Punkt „Committen“ {len(commit)}-mal (soll einmal)")
                continue
            s, c = ship[0], commit[0]
            if s >= c:
                wrong.append(f"  {path.name}: `auto-ship`-Prüfung ist Punkt {items[s][0]}, "
                             f"„Committen“ Punkt {items[c][0]} — Prüfung muss davor stehen")
            title = _title(items[s][1])
            if "auto-ship" not in title:
                wrong.append(f"  {path.name}: der `auto-ship`-Punkt hat keinen eigenen Titel "
                             f"zur Prüfung (Titel: {title!r})")
            if re.search(r"Deploy bleibt beim PO", items[s][1]):
                wrong.append(f"  {path.name}: `auto-ship`-Prüfung steckt im Deploy-Punkt")
        _fail("AC-1", wrong)

    def test_deploy_point_has_no_ship_text(self):
        """AC-6: Deploy-Punkt ohne `auto-ship` und Ausliefer-Text; on-Text in eigenem Punkt."""
        wrong = []
        for path, section in _texts():
            items = _items(section)
            deploy = _find(items, lambda t: "Deploy bleibt beim PO" in _title(t))
            ship = _find(items, lambda t: ON_SHIP_HEAD in t)
            push = _find(items, lambda t: re.search(r"pushen", _title(t), re.IGNORECASE))
            if len(deploy) != 1 or len(ship) != 1:
                wrong.append(f"  {path.name}: Deploy-Punkt {len(deploy)}-mal, "
                             f"Ausliefer-Punkt {len(ship)}-mal (je einmal erwartet)")
                continue
            d_text = items[deploy[0]][1]
            for label, pat in {
                "`auto-ship`": r"auto-ship",
                "`AUTO_SHIP`": r"AUTO_SHIP",
                "PR anlegen": r"\bPR\b",
                "mergen": r"\bmerg",
                "Git-Policy": r"Git-Policy",
            }.items():
                if re.search(pat, d_text):
                    wrong.append(f"  {path.name}: Deploy-Punkt enthält noch {label}")
            if not re.search(r"löst nie ein Deploy aus", d_text):
                wrong.append(f"  {path.name}: Deploy-Satz fehlt im Deploy-Punkt")
            if ship[0] == deploy[0]:
                wrong.append(f"  {path.name}: on-Text steht im Deploy-Punkt")
            s_text = items[ship[0]][1]
            for label, pat in {"PR": r"\bPR\b", "CI": r"\bCI\b", "Merge": r"\bmerg"}.items():
                if not re.search(pat, s_text):
                    wrong.append(f"  {path.name}: Ausliefer-Punkt nennt {label} nicht")
            # Ausgeliefert wird erst nach dem Push (der on-Text setzt Commit und Push voraus).
            if len(push) != 1:
                wrong.append(f"  {path.name}: Punkt „pushen“ {len(push)}-mal (soll einmal)")
            elif not push[0] < ship[0]:
                wrong.append(f"  {path.name}: Ausliefer-Punkt steht nicht nach dem Push-Punkt "
                             f"(Positionen {push[0]}, {ship[0]})")
        _fail("AC-6", wrong)

    def test_on_and_off_text_kept_verbatim(self):
        """AC-7: on-Text (#525) und off-Text (4.5.4) bleiben im Wortlaut; on vor off."""
        on_kept = [
            ON_SHIP_HEAD,
            "den PR vom Feature-Branch auf den Default-Branch anlegen (PR-Vorlage des Repos "
            "beachten), die CI abwarten (PR-Aktivität abonnieren statt Polling, wo verfügbar) "
            "und bei grüner CI und konfliktfreiem PR mergen, mit der im Repo üblichen Methode "
            "(an der Historie des Default-Branchs ablesbar, im Zweifel Squash); danach den "
            "Feature-Branch auf den neuen Stand bringen.",
            "Merge-Konflikt: Default-Branch in den Feature-Branch mergen, Konflikt lösen, "
            "Tests erneut laufen lassen, wieder warten.",
            "Bei roter CI die Ursache suchen und beheben (ein Code-Fix zählt wie BROKEN: "
            "zurück zu `phase6_implement`) oder, wenn nicht aus diesem Änderungssatz behebbar, "
            "das Problem in Alltagssprache melden.",
            "Hat das Repo keine CI-Checks, wird auf Basis der grünen lokalen Testsuite aus "
            "Phase 7 gemergt.",
            "Schutzregeln (Pflicht-Reviews, Branch-Protection) werden nie umgangen, nie "
            "`--force`, rote CI nie überbrücken; verhindert eine Schutzregel den Merge, lautet "
            "die Meldung „wartet auf Prüfung durch einen Techniker“.",
            "Auch ohne Zugang zu Remote oder GitHub: in Alltagssprache melden, nie ein "
            "Git-Auftrag an den PO.",
        ]
        off_kept = [
            OFF_MARKER + " gilt unverändert:",
            "**Merge und PR — Git-Policy des Projekts sticht:** Steht in der `CLAUDE.md` des "
            "Projekts (oder in der Memory), dass Claude Git und Auslieferung selbst erledigt "
            "(Formulierungen wie „Git entscheidet Claude selbst“, „bis `main` ausliefern“, "
            "„PO will mit Git nichts zu tun haben“), dann ist das bindend: Du legst den PR an, "
            "wartest die CI ab und lieferst nach den dort beschriebenen Regeln (z. B. "
            "Vorspulen) selbst auf den Default-Branch aus, im selben Turn, und meldest nur das "
            "Ergebnis.",
            "(nie `main` pushen) gilt dann nur so weit, wie die Projektregel den Weg nicht "
            "ausdrücklich vorgibt; nie `--force`, nie Schutzregeln umgehen, rote CI nie "
            "überbrücken. Ohne solche Policy bleiben Merge und PR beim PO.",
        ]
        wrong = []
        for path, section in _texts():
            flat = _flat(section)
            for label, kept in (("on-Text #525", on_kept), ("off-Text 4.5.4", off_kept)):
                wrong += [f"  {path.name}: {label} nicht im Wortlaut: {k[:70]!r}…"
                          for k in kept if _flat(k) not in flat]
            if ON_SHIP_HEAD in flat and OFF_MARKER in flat \
                    and flat.index(ON_SHIP_HEAD) > flat.index(OFF_MARKER):
                wrong.append(f"  {path.name}: off-Fall steht vor dem on-Fall")
        _fail("AC-7", wrong)


# --- AC-2 bis AC-5: Default-Branch-Pfad bei AUTO_SHIP=on -------------------------

class TestDefaultBranchPath:

    def test_switch_branch_before_commit_with_workflow_name(self):
        """AC-2: bei on + main/master/Default-Branch/detached HEAD vor dem Commit `git switch -c <workflow>`."""
        need = {
            "`AUTO_SHIP=on`": re.escape(ON),
            "`main`": r"`main`",
            "`master`": r"`master`",
            "Default-Branch des Remotes": r"Default-Branch des Remotes",
            "detached `HEAD`": r"detached `?HEAD",
            "VOR dem Commit": r"\bvor dem Commit\b",
            "`git switch -c` mit Workflow-Namen":
                r"git switch -c\s+<?[\w-]*workflow[\w-]*>?",
            "Branch mit dem Workflow-Namen": r"Workflow-Namen",
        }
        wrong = []
        for path, section in _texts():
            item = _commit_item(path, section, wrong)
            if item is None:
                continue
            wrong += [f"  {path.name}: Punkt „Committen“ nennt nicht: {label}"
                      for label, pat in need.items()
                      if not re.search(pat, item, re.IGNORECASE)]
            # Die Branch-Anlage muss vor der Commit-Anweisung beschrieben sein,
            # nicht erst als Nachgang („danach“/„nach dem Commit“).
            if re.search(r"nach dem Commit[^.]{0,80}git switch -c", item, re.IGNORECASE):
                wrong.append(f"  {path.name}: `git switch -c` erst nach dem Commit")
        _fail("AC-2", wrong)

    def test_name_conflict_gets_suffix(self):
        """AC-3: vorhandener Branch-Name -> Suffix `-2`, `-3` anhängen."""
        pat = (r"(existiert|vorhanden|bereits|schon)[^.]{0,120}`-2`[^.]{0,20}`-3`"
               r"|`-2`[^.]{0,20}`-3`[^.]{0,120}(existiert|vorhanden|bereits|schon)")
        wrong = []
        for path, section in _texts():
            item = _commit_item(path, section, wrong)
            if item is None:
                continue
            if not re.search(pat, item, re.IGNORECASE):
                wrong.append(f"  {path.name}: Punkt „Committen“ regelt den vorhandenen "
                             "Branch-Namen nicht über `-2`, `-3`")
            if not re.search(r"anhäng|angehängt", item, re.IGNORECASE):
                wrong.append(f"  {path.name}: Suffix wird nicht als angehängt beschrieben")
        _fail("AC-3", wrong)

    def test_no_reset_and_no_force(self):
        """AC-4: lokaler Default-Branch wird nie zurückgesetzt (kein `reset`), nie `--force`."""
        need = {
            "lokaler Default-Branch nie zurückgesetzt":
                r"lokale[nr]? Default-Branch[^.]{0,60}\bnie\b[^.]{0,30}zurückgesetzt",
            "kein `reset`": r"\bkein(en)?\b[^.]{0,10}`(git )?reset`",
            "kein `--force`": r"\b(kein|nie)\b[^.]{0,10}`--force`",
        }
        wrong = []
        for path, section in _texts():
            item = _commit_item(path, section, wrong)
            if item is None:
                continue
            wrong += [f"  {path.name}: Punkt „Committen“ nennt nicht: {label}"
                      for label, pat in need.items() if not re.search(pat, item)]
        _fail("AC-4", wrong)

    def test_no_git_task_for_po_and_hint_only_for_off(self):
        """AC-5: on-Abschlussmeldung ohne Git-Schritt (auch nicht für den neuen Branch);
        „nur committet und der PO … darauf hingewiesen“ gilt ausdrücklich nur für off."""
        hint = r"nur committet[^.]{0,80}darauf hingewiesen"
        no_git = (r"Abschlussmeldung[^.]{0,120}\b(keinen|kein|nie)\b[^.]{0,30}Git-Schritt"
                  r"[^.]{0,120}(angelegte[nr]?|neue[nr]?) (Feature-)?Branch")
        wrong = []
        for path, section in _texts():
            flat = _flat(section)
            hits = list(re.finditer(hint, flat))
            if not hits:
                wrong.append(f"  {path.name}: Satz „nur committet … darauf hingewiesen“ fehlt")
            for m in hits:
                before = flat[max(0, m.start() - 250): m.start()]
                off_at, on_at = before.rfind(OFF), before.rfind(ON)
                if off_at == -1 or on_at > off_at:
                    wrong.append(f"  {path.name}: „nur committet … darauf hingewiesen“ ist "
                                 f"nicht ausdrücklich an {OFF!r} gebunden: "
                                 f"{flat[max(0, m.start() - 120): m.end()]!r}")
            listed = " ".join(text for _, text in _items(section))
            if not re.search(no_git, listed, re.IGNORECASE):
                wrong.append(f"  {path.name}: keine Regel „Abschlussmeldung bei `{ON}` nennt "
                             "keinen Git-Schritt, auch nicht für den angelegten Branch“")
        _fail("AC-5", wrong)


# --- AC-8: Mutationstest zur Fenster-Verengung (F002) -----------------------------

RULES_525 = {
    "Schutzregeln nie umgehen": r"Schutzregeln[^.]{0,80}nie[^.]{0,40}umg"
                                r"|nie[^.]{0,40}Schutzregeln[^.]{0,40}umg",
    "nie --force": r"nie[^.]{0,20}`?--force",
    "❗Du-Zeile nie Git-Schritt": r"❗Du-Zeile[^.]{0,60}\bnie\b[^.]{0,40}Git-Schritt",
}

RULES_TEXT = ("Schutzregeln (Pflicht-Reviews, Branch-Protection) werden nie umgangen, "
              "nie `--force`, rote CI nie überbrücken. "
              "Die ❗Du-Zeile nennt nie einen Git-Schritt (PR, Merge, Push).")


def _found(windows: "list[str]") -> "list[str]":
    joined = " ".join(windows)
    return [label for label, pat in RULES_525.items()
            if re.search(pat, joined, re.IGNORECASE)]


class TestWindowNarrowing:

    def test_rules_only_in_off_paragraph_not_found(self):
        """AC-8: Regeln nur im off-Absatz -> kein Fenster findet sie; im on-Absatz -> gefunden."""
        off_only = (f"**Bei `{ON}` liefert Claude selbst aus:** PR anlegen, CI abwarten, mergen.\n"
                    f"{OFF_MARKER} gilt unverändert:\n{RULES_TEXT}\n")
        on_has = (f"**Bei `{ON}` liefert Claude selbst aus:** PR anlegen, CI abwarten, mergen. "
                  f"{RULES_TEXT}\n{OFF_MARKER} gilt unverändert: Git-Policy des Projekts.\n")
        wrong = []
        # Gegenprobe: das alte, breite Fenster (4000 Zeichen ohne Marker-Ende) haette
        # die Regeln im off-Absatz gefunden — sonst belegt der Mutationstest nichts.
        flat = _flat(off_only)
        wide = [flat[m.start(): m.start() + 4000] for m in re.finditer(re.escape(ON), flat)]
        if _found(wide) != list(RULES_525):
            wrong.append(f"  Gegenprobe kaputt: breites Fenster findet nur {_found(wide)}")
        windows = _on_windows(off_only)
        if not windows:
            wrong.append("  off-only-Text: kein Fenster ab `AUTO_SHIP=on`")
        leaked = _found(windows)
        if leaked:
            wrong.append(f"  Regeln nur im off-Absatz, trotzdem im on-Fenster gefunden: {leaked}")
        if any(OFF_MARKER in w for w in windows):
            wrong.append("  on-Fenster reicht über den off-Marker hinaus")
        kept = _found(_on_windows(on_has))
        if kept != list(RULES_525):
            missing = [r for r in RULES_525 if r not in kept]
            wrong.append(f"  Regeln im on-Absatz nicht mehr gefunden: {missing}")
        # Ohne off-Marker gilt weiter die Breite.
        no_marker = f"Bei `{ON}`: " + "x " * 10 + RULES_TEXT
        if _found(_on_windows(no_marker)) != list(RULES_525):
            wrong.append("  ohne off-Marker greift die bisherige Fensterbreite nicht mehr")
        _fail("AC-8", wrong)


# --- AC-9: Skill-Sync -------------------------------------------------------------

def test_skills_in_sync():
    """AC-9: skills/60-validate/SKILL.md ist aus core/commands/60-validate.md generiert."""
    res = subprocess.run([sys.executable, str(SYNC), "--check"], capture_output=True,
                         text=True, cwd=str(REPO_ROOT), timeout=60)
    assert res.returncode == 0, res.stdout + res.stderr


# --- AC-10: CHANGELOG -------------------------------------------------------------

def test_changelog_mentions_528():
    """AC-10 (release-fest): CHANGELOG.md nennt #528 ab der Zeile `## [Unreleased]`."""
    text = CHANGELOG.read_text(encoding="utf-8")
    start = text.index("## [Unreleased]")
    assert "#528" in text[start:], "Kein #528-Eintrag ab [Unreleased] im CHANGELOG"
