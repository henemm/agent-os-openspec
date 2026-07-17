"""TDD RED — Fix #69: validate_dialog_artifact() wertet den LETZTEN Verdict-Block.

Bildet AC-4 der Spec `docs/specs/fix-60-69-gate-parsing.md` ab. Nach einem
Fix-Loop (BROKEN → Fix → neue Runde mit VERIFIED) enthält das Artefakt zwei
`## Verdict`-Blöcke. Der aktuelle `re.search` liest den ERSTEN (veralteten)
Block; korrekt ist der LETZTE.

Direkter Funktionsaufruf mit echter Datei in tmp_path (kein Mocking), Format
nach dem Generator in `adversary_dialog.render_dialog_artifact()`
(`### Runde N`, `- [x]`-Checkliste, `## Verdict`-Block), inkl. MIN_ROUNDS.

RED-Erwartung (gegen den aktuellen Code):
  * test_second_verdict_verified_wins  → FÄLLT (liest erstes BROKEN → (False, ...))
  * test_second_verdict_broken_wins    → FÄLLT (liest erstes VERIFIED → falsch (True, ...))
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
sys.path.insert(0, str(HOOKS_DIR))

from adversary_dialog import validate_dialog_artifact, MIN_ROUNDS


def _artifact(verdicts: list[str]) -> str:
    """Baut ein realistisches Dialog-Artefakt mit >= MIN_ROUNDS Runden und je
    einem `## Verdict`-Block pro Eintrag in `verdicts` (in Dokumentreihenfolge).

    Checkliste vollständig abgehakt, damit die Auswertung bis zum Verdict-Schritt
    durchläuft und wirklich die Verdict-Logik geprüft wird.
    """
    lines = [
        "# Adversary Dialog — fix-60-69-gate-parsing",
        "Spec: docs/specs/fix-60-69-gate-parsing.md",
        "Datum: 2026-07-17 12:00",
        f"Iteration: {len(verdicts)} / 3",
        "",
        "## Checkliste",
        "- [x] Section-gebundener Scan blockt Prosa nicht — Beweis: test_prose",
        "- [x] Repo-Scoping greift außerhalb nicht — Beweis: test_scope",
        "",
        "## Dialog",
    ]
    round_no = 0
    for i, verdict in enumerate(verdicts):
        # Vor jedem Verdict mindestens genug Runden dokumentieren
        rounds_this_block = MIN_ROUNDS if i == 0 else 1
        for _ in range(rounds_this_block):
            round_no += 1
            lines += [
                f"### Runde {round_no}",
                "**Adversary:** Versuch, die Implementierung zu brechen.",
                "**Implementierer:** Antwort mit Beweis.",
                "",
            ]
        lines += [
            "## Verdict",
            f"**{verdict}**",
            "Offene Punkte: 0 / 2",
            "",
        ]
    return "\n".join(lines)


def test_second_verdict_verified_wins(tmp_path):
    """AC-4 (RED): erst BROKEN, dann (Fix-Loop) VERIFIED → Auswertung VERIFIED.

    Heute liest re.search das erste BROKEN → (False, ...). Erwartet: (True, ...)
    mit VERIFIED im Meldungstext.
    """
    art = tmp_path / "adversary_dialog.md"
    art.write_text(_artifact(["BROKEN", "VERIFIED: alle Punkte bewiesen"]))

    valid, message = validate_dialog_artifact(str(art))
    assert valid is True, (
        f"Letzter Verdict ist VERIFIED → muss bestehen, aber valid={valid}, "
        f"message={message!r}"
    )
    assert "VERIFIED" in message


def test_second_verdict_broken_wins(tmp_path):
    """AC-4-Spiegelfall (RED): erst VERIFIED, dann BROKEN → Auswertung BROKEN.

    Stellt sicher, dass wirklich der LETZTE Block zählt (nicht 'irgendein
    VERIFIED'). Heute liest re.search das erste VERIFIED → falsch (True, ...).
    Erwartet: (False, ...) mit BROKEN im Meldungstext.
    """
    art = tmp_path / "adversary_dialog.md"
    art.write_text(_artifact(["VERIFIED: sah zunächst gut aus", "BROKEN"]))

    valid, message = validate_dialog_artifact(str(art))
    assert valid is False, (
        f"Letzter Verdict ist BROKEN → muss durchfallen, aber valid={valid}, "
        f"message={message!r}"
    )
    assert "BROKEN" in message


# --- F001 (CRITICAL): Verdict-Regex darf zitierte Verdicts in Codebloecken nicht werten ---

_HEAD = [
    "# Adversary Dialog — fix-60-69-gate-parsing",
    "Spec: docs/specs/fix-60-69-gate-parsing.md",
    "Datum: 2026-07-17 12:00",
    "Iteration: 1 / 3",
    "",
    "## Checkliste",
    "- [x] Punkt eins bewiesen — Beweis: test_eins",
    "- [x] Punkt zwei bewiesen — Beweis: test_zwei",
    "",
    "## Dialog",
    "### Runde 1",
    "**Adversary:** Versuch eins.",
    "**Implementierer:** Antwort eins.",
    "",
    "### Runde 2",
    "**Adversary:** Versuch zwei.",
    "**Implementierer:** Antwort zwei.",
    "",
]


def test_quoted_verified_in_codeblock_does_not_override_real_broken(tmp_path):
    """F001 (RED): echtes finales BROKEN + spaeter zitiertes VERIFIED im Codeblock -> BROKEN.

    Ein Adversary-Artefakt endet mit echtem '## Verdict' + '**BROKEN**'. Danach folgt
    - z.B. als Formatvorlage/Finding-Illustration - ein in dreifachen Backticks
    zitierter Beispielblock, der wortwoertlich '## Verdict' + '**VERIFIED**'
    enthaelt. Der zitierte Block ist KEINE echte Deklaration und darf nicht zaehlen.

    Heute (globaler re.finditer ohne Fence-Kontext) gewinnt das zitierte VERIFIED
    als 'letzter Block' -> (True, '... VERIFIED'). Erwartet: (False, ...) mit BROKEN.
    """
    art = tmp_path / "adversary_dialog.md"
    art.write_text("\n".join(_HEAD + [
        "## Verdict",
        "**BROKEN**",
        "Finding F001: kritischer Spec-Verstoss.",
        "",
        "## Anhang: Format-Vorlage (zur Orientierung, zitiert)",
        "```",
        "## Verdict",
        "**VERIFIED**",
        "The implementation withstood adversary testing.",
        "```",
        "",
    ]))

    valid, message = validate_dialog_artifact(str(art))
    assert valid is False, (
        f"Echtes finales Verdict ist BROKEN; zitiertes VERIFIED im Codeblock "
        f"darf nicht gewinnen. valid={valid}, message={message!r}"
    )
    assert "BROKEN" in message


def test_quoted_broken_in_codeblock_does_not_override_real_verified(tmp_path):
    """F001-Spiegelfall (RED): echtes finales VERIFIED + zitiertes BROKEN im Codeblock -> VERIFIED.

    Heute gewinnt das zitierte BROKEN als 'letzter Block' -> (False, ...).
    Erwartet: (True, ...) mit VERIFIED - der Codeblock-Inhalt zaehlt nicht.
    """
    art = tmp_path / "adversary_dialog.md"
    art.write_text("\n".join(_HEAD + [
        "## Verdict",
        "**VERIFIED**",
        "Offene Punkte: 0 / 2",
        "",
        "## Anhang: Beispiel eines negativen Laufs (zitiert)",
        "```",
        "## Verdict",
        "**BROKEN**",
        "Finding X: illustratives Gegenbeispiel.",
        "```",
        "",
    ]))

    valid, message = validate_dialog_artifact(str(art))
    assert valid is True, (
        f"Echtes finales Verdict ist VERIFIED; zitiertes BROKEN im Codeblock "
        f"darf nicht gewinnen. valid={valid}, message={message!r}"
    )
    assert "VERIFIED" in message


def test_unbalanced_fence_before_verdict_is_failsafe(tmp_path):
    """F001-Fail-safe (RED): unbalancierte (nie geschlossene) Fence vor dem echten Verdict.

    Design-Wahl: eine offene Fence bis Dateiende blendet allen Text danach aus -
    inkl. eines dort stehenden echten Verdicts. Das ist bewusst fail-safe: lieber
    'kein Verdict gefunden' (blockt, (False, ...)) als ein moeglicherweise in einem
    Codeblock stehendes Verdict faelschlich als echt werten (False-Pass). Ein
    korrekt strukturiertes Artefakt haelt Fences immer geschlossen; ein Verdict
    gehoert nie in einen Codeblock.

    Heute (ohne Fence-Tracking) findet re.finditer das VERIFIED -> (True, ...).
    Erwartet nach Fix: (False, ...) - 'Kein Verdict im Artifact gefunden.'
    """
    art = tmp_path / "adversary_dialog.md"
    art.write_text("\n".join(_HEAD + [
        "## Beispielausgabe (Fence versehentlich nicht geschlossen)",
        "```",
        "irgendein Tool-Output",
        "",
        "## Verdict",
        "**VERIFIED**",
        "",
    ]))

    valid, message = validate_dialog_artifact(str(art))
    assert valid is False, (
        f"Verdict hinter offener Fence darf nicht als echt gewertet werden. "
        f"valid={valid}, message={message!r}"
    )
    assert "Kein Verdict" in message


# --- F003: Tilde-Fences (~~~) gleichwertig zu Backtick-Fences behandeln ---


def test_quoted_verified_in_tilde_fence_does_not_override_real_broken(tmp_path):
    """F003 (RED): echtes finales BROKEN + spaeter zitiertes VERIFIED in ~~~-Fence -> BROKEN.

    GFM kennt Tilde-Fences (~~~) gleichwertig zu Backtick-Fences. Ein in ~~~
    zitierter Beispielblock mit \'## Verdict\'/\'**VERIFIED**\' ist KEINE echte
    Deklaration und darf das echte finale BROKEN nicht ueberschreiben.

    Heute (nur Backtick-Erkennung) rutscht der ~~~-Block durch und das zitierte
    VERIFIED gewinnt als \'letzter Block\' -> (True, ...). Erwartet: (False, ...).
    """
    art = tmp_path / "adversary_dialog.md"
    art.write_text("\n".join(_HEAD + [
        "## Verdict",
        "**BROKEN**",
        "Finding F003: kritischer Spec-Verstoss.",
        "",
        "## Anhang: Format-Vorlage (zur Orientierung, zitiert)",
        "~~~",
        "## Verdict",
        "**VERIFIED**",
        "The implementation withstood adversary testing.",
        "~~~",
        "",
    ]))

    valid, message = validate_dialog_artifact(str(art))
    assert valid is False, (
        f"Echtes finales Verdict ist BROKEN; zitiertes VERIFIED in ~~~-Fence "
        f"darf nicht gewinnen. valid={valid}, message={message!r}"
    )
    assert "BROKEN" in message


def test_quoted_broken_in_tilde_fence_does_not_override_real_verified(tmp_path):
    """F003-Spiegelfall (RED): echtes finales VERIFIED + zitiertes BROKEN in ~~~ -> VERIFIED.

    Heute gewinnt das in ~~~ zitierte BROKEN als \'letzter Block\' -> (False, ...).
    Erwartet: (True, ...) mit VERIFIED - der Fence-Inhalt zaehlt nicht.
    """
    art = tmp_path / "adversary_dialog.md"
    art.write_text("\n".join(_HEAD + [
        "## Verdict",
        "**VERIFIED**",
        "Offene Punkte: 0 / 2",
        "",
        "## Anhang: Beispiel eines negativen Laufs (zitiert)",
        "~~~",
        "## Verdict",
        "**BROKEN**",
        "Finding X: illustratives Gegenbeispiel.",
        "~~~",
        "",
    ]))

    valid, message = validate_dialog_artifact(str(art))
    assert valid is True, (
        f"Echtes finales Verdict ist VERIFIED; zitiertes BROKEN in ~~~-Fence "
        f"darf nicht gewinnen. valid={valid}, message={message!r}"
    )
    assert "VERIFIED" in message


def test_unbalanced_tilde_fence_before_verdict_is_failsafe(tmp_path):
    """F003-Fail-safe (RED): unbalancierte (nie geschlossene) ~~~-Fence vor dem echten Verdict.

    Analog zur Backtick-Fail-safe: eine offene ~~~-Fence bis Dateiende blendet
    allen Text danach aus - inkl. eines dort stehenden echten Verdicts. Lieber
    \'kein Verdict gefunden\' (blockt) als ein moeglicherweise zitiertes Verdict
    faelschlich als echt werten.

    Heute (ohne Tilde-Tracking) findet re.finditer das VERIFIED -> (True, ...).
    Erwartet nach Fix: (False, ...) - \'Kein Verdict im Artifact gefunden.\'
    """
    art = tmp_path / "adversary_dialog.md"
    art.write_text("\n".join(_HEAD + [
        "## Beispielausgabe (Fence versehentlich nicht geschlossen)",
        "~~~",
        "irgendein Tool-Output",
        "",
        "## Verdict",
        "**VERIFIED**",
        "",
    ]))

    valid, message = validate_dialog_artifact(str(art))
    assert valid is False, (
        f"Verdict hinter offener ~~~-Fence darf nicht als echt gewertet werden. "
        f"valid={valid}, message={message!r}"
    )
    assert "Kein Verdict" in message


# --- F004: Fence-Marker-Typ tracken (``` schliesst nur ```, ~~~ nur ~~~) ---


def test_backtick_fence_with_inner_tilde_line_does_not_leak_quoted_verified(tmp_path):
    """F004 (RED): mit ``` geoeffnete Fence enthaelt eine ~~~-Zeile als Inhalt.

    CommonMark/GFM: innerhalb einer mit ``` geoeffneten Fence schliesst NUR eine
    ```-Zeile; eine ~~~-Zeile ist dort gewoehnlicher Inhalt. Der marker-agnostische
    Toggle (bisher) laesst die ~~~-Zeile die Backtick-Fence faelschlich schliessen,
    wodurch das danach ZITIERTE '## Verdict'/'**VERIFIED**' durchrutscht und das
    echte finale BROKEN ueberschreibt.

    Heute (marker-agnostischer Toggle) -> zitiertes VERIFIED gewinnt -> (True, ...).
    Erwartet nach Fix: (False, ...) mit BROKEN.
    """
    art = tmp_path / "adversary_dialog.md"
    art.write_text("\n".join(_HEAD + [
        "## Verdict",
        "**BROKEN**",
        "Finding F004: kritischer Spec-Verstoss.",
        "",
        "## Anhang: Format-Vorlage (zitiert, mit gemischten Fence-Zeichen)",
        "```",
        "~~~",
        "## Verdict",
        "**VERIFIED**",
        "The implementation withstood adversary testing.",
        "```",
        "",
    ]))

    valid, message = validate_dialog_artifact(str(art))
    assert valid is False, (
        f"Echtes finales Verdict ist BROKEN; das in einer ```-Fence zitierte "
        f"VERIFIED (mit ~~~-Zeile im Inneren) darf nicht gewinnen. "
        f"valid={valid}, message={message!r}"
    )
    assert "BROKEN" in message


def test_tilde_fence_with_inner_backtick_line_does_not_leak_quoted_broken(tmp_path):
    """F004-Spiegelfall (RED): mit ~~~ geoeffnete Fence enthaelt eine ```-Zeile.

    Innerhalb einer mit ~~~ geoeffneten Fence schliesst NUR eine ~~~-Zeile; eine
    ```-Zeile ist dort Inhalt. Der marker-agnostische Toggle laesst die ```-Zeile
    die Tilde-Fence faelschlich schliessen, wodurch das zitierte BROKEN durchrutscht
    und das echte finale VERIFIED ueberschreibt.

    Heute -> zitiertes BROKEN gewinnt -> (False, ...).
    Erwartet nach Fix: (True, ...) mit VERIFIED.
    """
    art = tmp_path / "adversary_dialog.md"
    art.write_text("\n".join(_HEAD + [
        "## Verdict",
        "**VERIFIED**",
        "Offene Punkte: 0 / 2",
        "",
        "## Anhang: Beispiel eines negativen Laufs (zitiert, gemischte Fence-Zeichen)",
        "~~~",
        "```",
        "## Verdict",
        "**BROKEN**",
        "Finding X: illustratives Gegenbeispiel.",
        "~~~",
        "",
    ]))

    valid, message = validate_dialog_artifact(str(art))
    assert valid is True, (
        f"Echtes finales Verdict ist VERIFIED; das in einer ~~~-Fence zitierte "
        f"BROKEN (mit ```-Zeile im Inneren) darf nicht gewinnen. "
        f"valid={valid}, message={message!r}"
    )
    assert "VERIFIED" in message


# --- F005: Fence-Marker-LAENGE tracken (schliessende Fence >= oeffnende Laenge,
#     info-string-Zeile schliesst nicht) — vollstaendige CommonMark-Fence-Regel ---


def test_longer_backtick_open_not_closed_by_shorter_inner_line(tmp_path):
    """F005 (RED): mit 4 Backticks geoeffnete Fence, 3-Backtick-Zeile im Inneren.

    CommonMark/GFM: eine schliessende Fence muss MINDESTENS so lang sein wie die
    oeffnende. Eine mit ```` (4) geoeffnete Fence wird von einer ``` (3) Zeile NICHT
    geschlossen — die 3-Backtick-Zeile ist dort gewoehnlicher Inhalt. Der bisherige
    Tracker prueft nur den Marker-TYP, nicht die LAENGE: die 3-Backtick-Zeile schliesst
    die 4-Backtick-Fence faelschlich, das danach ZITIERTE '## Verdict'/'**VERIFIED**'
    rutscht durch und ueberschreibt das echte finale BROKEN.

    Heute (nur Typ-Tracking) -> zitiertes VERIFIED gewinnt -> (True, ...).
    Erwartet nach Fix: (False, ...) mit BROKEN.
    """
    art = tmp_path / "adversary_dialog.md"
    art.write_text("\n".join(_HEAD + [
        "## Verdict",
        "**BROKEN**",
        "Finding F005: kritischer Spec-Verstoss.",
        "",
        "## Anhang: Format-Vorlage (zitiert, verschachtelte Fence-Laengen)",
        "````",
        "```",
        "## Verdict",
        "**VERIFIED**",
        "The implementation withstood adversary testing.",
        "```",
        "````",
        "",
    ]))

    valid, message = validate_dialog_artifact(str(art))
    assert valid is False, (
        f"Echtes finales Verdict ist BROKEN; das in einer ````-Fence (4) zitierte "
        f"VERIFIED (mit ```-Zeile (3) im Inneren) darf nicht gewinnen. "
        f"valid={valid}, message={message!r}"
    )
    assert "BROKEN" in message


def test_longer_tilde_open_not_closed_by_shorter_inner_line(tmp_path):
    """F005-Spiegelfall (RED): mit 4 Tilden geoeffnete Fence, 3-Tilden-Zeile im Inneren.

    Analog zur Backtick-Regel: eine mit ~~~~ (4) geoeffnete Fence wird von einer
    ~~~ (3) Zeile NICHT geschlossen. Ohne Laengen-Tracking schliesst die 3-Tilden-Zeile
    die 4-Tilden-Fence faelschlich, das danach ZITIERTE '## Verdict'/'**BROKEN**'
    rutscht durch und ueberschreibt das echte finale VERIFIED.

    Heute -> zitiertes BROKEN gewinnt -> (False, ...).
    Erwartet nach Fix: (True, ...) mit VERIFIED.
    """
    art = tmp_path / "adversary_dialog.md"
    art.write_text("\n".join(_HEAD + [
        "## Verdict",
        "**VERIFIED**",
        "Offene Punkte: 0 / 2",
        "",
        "## Anhang: Beispiel eines negativen Laufs (zitiert, verschachtelte Laengen)",
        "~~~~",
        "~~~",
        "## Verdict",
        "**BROKEN**",
        "Finding X: illustratives Gegenbeispiel.",
        "~~~",
        "~~~~",
        "",
    ]))

    valid, message = validate_dialog_artifact(str(art))
    assert valid is True, (
        f"Echtes finales Verdict ist VERIFIED; das in einer ~~~~-Fence (4) zitierte "
        f"BROKEN (mit ~~~-Zeile (3) im Inneren) darf nicht gewinnen. "
        f"valid={valid}, message={message!r}"
    )
    assert "VERIFIED" in message


def test_shorter_open_closed_by_longer_line_real_verdict_after_counts(tmp_path):
    """F005-Regelbestaetigung: 3-Backtick-Fence, geschlossen von 4-Backtick-Zeile.

    Eine schliessende Fence DARF laenger sein als die oeffnende (Regel: >= Oeffnungs-
    laenge). Eine mit ``` (3) geoeffnete Fence wird also von ```` (4) korrekt
    geschlossen; das danach folgende ECHTE Verdict zaehlt. Das in der Fence zitierte
    BROKEN ist Inhalt und wird verworfen.

    Erwartet: (True, ...) mit VERIFIED — sowohl vor als auch nach dem Fix (bereits gruen).
    """
    art = tmp_path / "adversary_dialog.md"
    art.write_text("\n".join(_HEAD + [
        "## Anhang: Format-Vorlage (zitiert)",
        "```",
        "## Verdict",
        "**BROKEN**",
        "Finding Y: illustratives Gegenbeispiel.",
        "````",
        "",
        "## Verdict",
        "**VERIFIED**",
        "Offene Punkte: 0 / 2",
        "",
    ]))

    valid, message = validate_dialog_artifact(str(art))
    assert valid is True, (
        f"Die ```-Fence (3) wird von ```` (4) korrekt geschlossen; das echte "
        f"nachfolgende VERIFIED zaehlt. valid={valid}, message={message!r}"
    )
    assert "VERIFIED" in message


def test_info_string_line_does_not_close_open_fence(tmp_path):
    """F005 (RED): eine 'Schliesszeile' mit Info-String (```python) schliesst NICHT.

    CommonMark: eine schliessende Fence darf NACH dem Marker-Lauf hoechstens
    Whitespace enthalten. Eine Zeile wie ```python ist daher KEINE schliessende
    Fence, sondern gewoehnlicher Inhalt der offenen Fence. Der bisherige Tracker
    prueft nur den Praefix und laesst ```python die ```-Fence faelschlich schliessen;
    das danach ZITIERTE '## Verdict'/'**VERIFIED**' rutscht durch und ueberschreibt
    das echte finale BROKEN.

    Heute (nur Praefix-Pruefung) -> zitiertes VERIFIED gewinnt -> (True, ...).
    Erwartet nach Fix: (False, ...) mit BROKEN.
    """
    art = tmp_path / "adversary_dialog.md"
    art.write_text("\n".join(_HEAD + [
        "## Verdict",
        "**BROKEN**",
        "Finding F005b: kritischer Spec-Verstoss.",
        "",
        "## Anhang: Format-Vorlage (zitiert, mit Info-String)",
        "```",
        "```python",
        "## Verdict",
        "**VERIFIED**",
        "print('withstood adversary testing')",
        "```",
        "",
    ]))

    valid, message = validate_dialog_artifact(str(art))
    assert valid is False, (
        f"Echtes finales Verdict ist BROKEN; die '```python'-Zeile (Info-String) "
        f"schliesst die Fence nicht, das zitierte VERIFIED darf nicht gewinnen. "
        f"valid={valid}, message={message!r}"
    )
    assert "BROKEN" in message


# --- F006 (CRITICAL): Einrueckungsgrenze der Fence (CommonMark: max. 3 Spaces) ---


def test_indented_4space_pseudo_close_does_not_close_fence(tmp_path):
    """F006 (RED): eine mit 4 Spaces eingerueckte 'Schliesszeile' schliesst NICHT.

    CommonMark: eine schliessende Fence darf hoechstens 3 Spaces eingerueckt sein.
    Eine mit >= 4 Spaces eingerueckte Marker-Zeile ist gewoehnlicher Inhalt der
    offenen Fence, KEIN gueltiger Abschluss. Der bisherige Tracker wendet lstrip()
    an und entfernt beliebige Einrueckung -> die 4-Space-Zeile schliesst die Fence
    faelschlich frueh, das danach ZITIERTE '## Verdict'/'**VERIFIED**' rutscht durch
    und ueberschreibt das echte finale BROKEN (False-Pass).

    Heute (lstrip entfernt alles) -> zitiertes VERIFIED gewinnt -> (True, ...).
    Erwartet nach Fix: (False, ...) mit BROKEN.
    """
    art = tmp_path / "adversary_dialog.md"
    art.write_text("\n".join(_HEAD + [
        "## Verdict",
        "**BROKEN**",
        "Finding F006: kritischer Spec-Verstoss.",
        "",
        "## Anhang: Format-Vorlage (zitiert, 4-Space-Pseudo-Schliesser)",
        "```",
        "    ```",
        "## Verdict",
        "**VERIFIED**",
        "The implementation withstood adversary testing.",
        "```",
        "",
    ]))

    valid, message = validate_dialog_artifact(str(art))
    assert valid is False, (
        f"Echtes finales Verdict ist BROKEN; die um 4 Spaces eingerueckte "
        f"Pseudo-Schliesszeile schliesst die Fence nach CommonMark NICHT, das "
        f"zitierte VERIFIED darf nicht gewinnen. valid={valid}, message={message!r}"
    )
    assert "BROKEN" in message


def test_tab_indented_pseudo_close_does_not_close_fence(tmp_path):
    """F006-Spiegelfall (RED): eine mit Tab eingerueckte 'Schliesszeile' schliesst NICHT.

    CommonMark zaehlt einen Tab als >= 4 Spaces; eine Tab-eingerueckte Marker-Zeile
    ist daher Inhalt, kein gueltiger Fence-Abschluss. Der bisherige lstrip()-Tracker
    schliesst faelschlich -> das ZITIERTE '## Verdict'/'**BROKEN**' rutscht durch und
    ueberschreibt das echte finale VERIFIED.

    Heute -> zitiertes BROKEN gewinnt -> (False, ...).
    Erwartet nach Fix: (True, ...) mit VERIFIED.
    """
    art = tmp_path / "adversary_dialog.md"
    art.write_text("\n".join(_HEAD + [
        "## Verdict",
        "**VERIFIED**",
        "Offene Punkte: 0 / 2",
        "",
        "## Anhang: Beispiel eines negativen Laufs (zitiert, Tab-Pseudo-Schliesser)",
        "```",
        "\t```",
        "## Verdict",
        "**BROKEN**",
        "Finding X: illustratives Gegenbeispiel.",
        "```",
        "",
    ]))

    valid, message = validate_dialog_artifact(str(art))
    assert valid is True, (
        f"Echtes finales Verdict ist VERIFIED; die per Tab eingerueckte "
        f"Pseudo-Schliesszeile schliesst die Fence nach CommonMark NICHT, das "
        f"zitierte BROKEN darf nicht gewinnen. valid={valid}, message={message!r}"
    )
    assert "VERIFIED" in message


def test_close_line_indented_3spaces_still_closes(tmp_path):
    """F006-Regelbestaetigung: eine mit 1-3 Spaces eingerueckte Schliesszeile schliesst.

    CommonMark: bis zu 3 Spaces Einrueckung sind bei OEFFNEN und SCHLIESSEN erlaubt.
    Eine mit 3 Spaces eingerueckte ```-Zeile schliesst also eine offene Fence korrekt;
    das danach folgende ECHTE Verdict zaehlt, der zitierte Fence-Inhalt wird verworfen.

    Erwartet: (True, ...) mit VERIFIED — sowohl vor als auch nach dem Fix (Kontrolle,
    dass die Einrueckungs-Verschaerfung standardkonforme Schliesser NICHT bricht).
    """
    art = tmp_path / "adversary_dialog.md"
    art.write_text("\n".join(_HEAD + [
        "## Anhang: Format-Vorlage (zitiert, 3-Space-Schliesser ist gueltig)",
        "```",
        "## Verdict",
        "**BROKEN**",
        "Finding Y: illustratives Gegenbeispiel.",
        "   ```",
        "",
        "## Verdict",
        "**VERIFIED**",
        "Offene Punkte: 0 / 2",
        "",
    ]))

    valid, message = validate_dialog_artifact(str(art))
    assert valid is True, (
        f"Eine um 3 Spaces eingerueckte ```-Zeile schliesst die Fence korrekt "
        f"(CommonMark erlaubt <= 3 Spaces); das echte nachfolgende VERIFIED zaehlt. "
        f"valid={valid}, message={message!r}"
    )
    assert "VERIFIED" in message


def test_midline_verdict_not_anchored_does_not_override_real_broken(tmp_path):
    """Anker (RED): ein '## Verdict' MITTEN in einer Fliesstextzeile zaehlt nicht.

    Die Struktur-Regexe (Verdict, Runden) sind nicht am Zeilenanfang verankert:
    re.finditer(r'## Verdict\\s*\\n\\*\\*...') matcht auch '...siehe ## Verdict'
    mitten in einer Prosa-Zeile (kein Codeblock, wird also nicht von
    _strip_fenced_code_blocks entfernt). So kann ein in Prosa erwaehntes,
    NICHT zeilenanfangs stehendes '## Verdict' + '**VERIFIED**' das echte finale
    BROKEN ueberschreiben.

    Heute (unverankert) -> das mid-line zitierte VERIFIED gewinnt -> (True, ...).
    Erwartet nach Fix ((?m)^-Anker): (False, ...) mit BROKEN.
    """
    art = tmp_path / "adversary_dialog.md"
    art.write_text("\n".join(_HEAD + [
        "## Verdict",
        "**BROKEN**",
        "Finding Z: kritischer Spec-Verstoss.",
        "",
        "Zur Illustration sei hier der Zielzustand siehe ## Verdict",
        "**VERIFIED** waere das gewuenschte Ergebnis gewesen.",
        "",
    ]))

    valid, message = validate_dialog_artifact(str(art))
    assert valid is False, (
        f"Echtes finales Verdict ist BROKEN; ein '## Verdict' MITTEN in einer "
        f"Prosa-Zeile ist keine Markdown-Ueberschrift und darf nicht als Verdict "
        f"zaehlen. valid={valid}, message={message!r}"
    )
    assert "BROKEN" in message


# --- F007 (CRITICAL): Backtick-Oeffner mit Backtick im Info-String ist KEIN Oeffner ---
# CommonMark: der Info-String eines Backtick-Fence-Oeffners darf KEINEN Backtick
# enthalten -> eine solche Zeile ist gewoehnlicher Absatz, kein Fence-Oeffner. Bisher
# oeffnete die Implementierung faelschlich; die unmittelbar folgende ECHTE bare
# ```-Zeile wurde dann als SCHLIESSER der (faelschlich) offenen Fence gewertet, sodass
# der Parser vorzeitig in den "ausserhalb"-Zustand zurueckfiel und den real
# versteckten Inhalt (inkl. zitiertem Verdict) als echte Struktur freigab (False-Pass).


def test_backtick_infostring_opener_does_not_swallow_real_opener_false_pass(tmp_path):
    """F007 (RED): ```foo`bar (Backtick im Info-String) darf KEINEN Fence oeffnen.

    Payload nach echtem finalen '## Verdict'/'**BROKEN**':
      (1) eine Zeile '```foo`bar' — Backtick im Info-String -> nach CommonMark KEIN
          gueltiger Backtick-Fence-Oeffner, sondern gewoehnlicher Absatz.
      (2) direkt danach eine bare '```'-Zeile — DAS ist der echte, gueltige Oeffner.
      (3) versteckter Fence-Inhalt inkl. zitiertem '## Verdict'/'**VERIFIED**'.
      (4) eine echte bare '```'-Schliesszeile.

    Heute (C4 als bewusste Abweichung): Zeile (1) OEFFNET faelschlich; Zeile (2)
    schliesst diese Pseudo-Fence -> ab (3) gilt der Parser als 'ausserhalb' und das
    zitierte VERIFIED gewinnt als 'letzter Block' -> (True, ...). FALSE-PASS.
    Erwartet nach Fix: (False, ...) mit BROKEN — der Inhalt ab (2) bleibt versteckt.
    """
    art = tmp_path / "adversary_dialog.md"
    art.write_text("\n".join(_HEAD + [
        "## Verdict",
        "**BROKEN**",
        "Finding F007: kritischer Spec-Verstoss.",
        "",
        "## Anhang: Format-Vorlage (zitiert, Backtick im Info-String)",
        "```foo`bar",
        "```",
        "## Verdict",
        "**VERIFIED**",
        "The implementation withstood adversary testing.",
        "```",
        "",
    ]))

    valid, message = validate_dialog_artifact(str(art))
    assert valid is False, (
        f"Echtes finales Verdict ist BROKEN; eine '```foo`bar'-Zeile (Backtick im "
        f"Info-String) ist nach CommonMark KEIN Fence-Oeffner, darf also die echte "
        f"nachfolgende ```-Fence nicht 'vorwegnehmen'. Das zitierte VERIFIED darf "
        f"nicht gewinnen. valid={valid}, message={message!r}"
    )
    assert "BROKEN" in message


def test_backtick_infostring_opener_mirror_real_verified_wins(tmp_path):
    """F007-Spiegelfall (RED): zitiertes BROKEN in der real offenen Fence -> VERIFIED.

    Echtes finales '## Verdict'/'**VERIFIED**', danach ein Anhang mit (1) einer
    '```foo`bar'-Zeile (kein Oeffner), (2) echter bare '```'-Oeffner, (3) verstecktem
    zitierten '## Verdict'/'**BROKEN**', (4) echter '```'-Schliesser.

    Heute -> das zitierte BROKEN leakt und gewinnt -> (False, ...).
    Erwartet nach Fix: (True, ...) mit VERIFIED.
    """
    art = tmp_path / "adversary_dialog.md"
    art.write_text("\n".join(_HEAD + [
        "## Verdict",
        "**VERIFIED**",
        "Offene Punkte: 0 / 2",
        "",
        "## Anhang: Beispiel eines negativen Laufs (zitiert, Backtick im Info-String)",
        "```foo`bar",
        "```",
        "## Verdict",
        "**BROKEN**",
        "Finding X: illustratives Gegenbeispiel.",
        "```",
        "",
    ]))

    valid, message = validate_dialog_artifact(str(art))
    assert valid is True, (
        f"Echtes finales Verdict ist VERIFIED; das in der echten ```-Fence zitierte "
        f"BROKEN darf nicht gewinnen (die vorangehende '```foo`bar'-Zeile ist kein "
        f"Oeffner). valid={valid}, message={message!r}"
    )
    assert "VERIFIED" in message


def test_tilde_infostring_opener_still_opens_no_overregulation(tmp_path):
    """F007-Gegenprobe: ~~~foo`bar (Backtick im Info-String) OEFFNET WEITERHIN.

    CommonMark erlaubt Backticks (und Tilden) im Info-String eines TILDE-Fence-
    Oeffners — die Backtick-Restriktion gilt NUR fuer Backtick-Fences. Der C4-Fix
    darf Tilde-Fences also NICHT einschraenken (sonst entsteht die naechste
    Divergenz). '~~~foo`bar' muss eine Fence OEFFNEN; der Inhalt danach — inkl.
    zitiertem '## Verdict'/'**VERIFIED**' — bleibt verborgen bis zur '~~~'-Schliesszeile.

    Erwartet: (False, ...) mit BROKEN — sowohl vor als auch nach dem Fix (bereits
    gruen; haelt die Nicht-Ueberregulierung des Tilde-Pfads fest).
    """
    art = tmp_path / "adversary_dialog.md"
    art.write_text("\n".join(_HEAD + [
        "## Verdict",
        "**BROKEN**",
        "Finding F007g: kritischer Spec-Verstoss.",
        "",
        "## Anhang: Format-Vorlage (zitiert, Tilde-Oeffner mit Backtick im Info-String)",
        "~~~foo`bar",
        "## Verdict",
        "**VERIFIED**",
        "The implementation withstood adversary testing.",
        "~~~",
        "",
    ]))

    valid, message = validate_dialog_artifact(str(art))
    assert valid is False, (
        f"Echtes finales Verdict ist BROKEN; '~~~foo`bar' OEFFNET eine gueltige "
        f"Tilde-Fence (CommonMark erlaubt Backticks im Tilde-Info-String), das "
        f"zitierte VERIFIED bleibt verborgen. valid={valid}, message={message!r}"
    )
    assert "BROKEN" in message
