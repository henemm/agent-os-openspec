"""Erkennung der git-Aufrufform statt naiver Teilstring-Pruefung (Issue #1431).

Bis hierher entschied jedes Commit-Gate ueber `"git commit" in command`. Das
war in BEIDE Richtungen falsch:

* **Unterblockieren** — jede Form mit etwas zwischen `git` und dem Unterbefehl
  (`git -C /pfad commit`, `git -c k=v commit`, `git --no-pager commit`) umging
  das Gate still. Beim Bash-Gate beendete zusaetzlich ein Fast Path den Hook
  VOR Secrets-Guard, Credential-Pruefung und allen Commit-Gates.
* **Ueberblockieren** — die blosse Erwaehnung (`grep -rn "git commit"`,
  `gh issue create --body "... git commit ..."`) loeste die Gates aus.

Getestet wird die Erkennung (hook_utils) UND ihre Wirkung im echten Bash-Gate
(Subprozess gegen eine isolierte Sandbox, kein Mock).

**Entscheidungsregel seit Runde 3 (PO-Richtungswechsel).** Zwei Nachbesserungs-
runden haben gezeigt, dass "erkenne ich einen Commit? nein -> durchlassen" die
falsche Grundhaltung ist: eine Kommandozeile ist beliebig verschachtelbar
(Backticks, `$( … )`, Schleifen-Schluesselwoerter, `eval`, Heredocs), und alles
Unverstandene rutschte durch. Gilt jetzt:

  1. Zerlegung findet den Aufruf                      -> pruefen
  2. Zerlegung findet nichts, Kommando sauber zerlegbar -> durchlassen
  3. Zerlegung findet nichts, Kommando NICHT sicher
     zerlegbar, Zeichenfolge kommt vor               -> im Zweifel pruefen

Die alte Teilstring-Pruefung ist damit die **Untergrenze**: was sie gefangen
haette, wird weiterhin geprueft — ausser das Kommando ist sauber zerlegbar und
enthaelt nachweislich nur eine Erwaehnung. Der Test
`test_echter_commit_aufruf_wird_immer_erkannt` haelt das ueber eine breite
Fallsammlung strukturell fest, statt Einzelfaelle abzuhaken.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
sys.path.insert(0, str(HOOKS_DIR))

import bash_gate  # noqa: E402
import hook_utils  # noqa: E402


# --------------------------------------------------------------------- #
# 1. Aufrufformen werden erkannt
# --------------------------------------------------------------------- #

AUFRUFFORMEN = [
    'git commit -m "x"',
    'git -c commit.gpgsign=false commit -m "x"',
    'git -C /home/hem/repo commit -m "x"',
    'git --no-pager commit -m "x"',
    'git --git-dir=/a/.git --work-tree=/a commit -m "x"',
    'git --git-dir /a/.git commit -m "x"',
    'cd /repo && git commit -m "x"',
    'git add -A && git -C /repo commit -m "x"',
    '/usr/bin/git commit -m "x"',
    'bash -c "git -C /repo commit -m x"',
    # Adversary F002: Trenner OHNE umgebende Leerzeichen. Die alte Teilstring-
    # Pruefung fing das (`git commit` steht woertlich drin) — eine reine
    # shlex.split-Zerlegung nicht mehr, sie verklebt `/tmp&&git` zu EINEM Token.
    "cd /tmp&&git commit -m x",
    "cd /tmp&&git -C /repo commit -m x",
    "git add -A;git commit -m x",
    "git fetch||git commit -m x",
    # Adversary F001: Zeilenumbruch als Kommando-Trenner (shlex verschluckt ihn
    # als gewoehnlichen Whitespace).
    "cd /repo\ngit commit -m x",
    "git status\ngit commit -m x",
    # Adversary F004: mehrgliedrige Wrapper-Kette vor `git` (Mutation
    # while -> if in der Vor-Wrapper-Behandlung fiel bisher keinem Test auf).
    "sudo env git commit -m x",
    "FOO=1 BAR=2 git commit -m x",
    "sudo env FOO=1 git -C /repo commit -m x",
]


@pytest.mark.parametrize("command", AUFRUFFORMEN)
def test_aufrufform_wird_als_commit_erkannt(command):
    assert hook_utils.is_git_subcommand(command, "commit") is True, command


ERWAEHNUNGEN = [
    'grep -rn "git commit" .claude/hooks/',
    'echo "vor dem git commit noch pruefen"',
    'gh issue create --title "Gate" --body "... git commit ... umgeht"',
    'git log --grep="commit" --oneline',
    'git log --oneline | grep -c " commit "',
    'git status',
    'rg "git commit" -l',
    # Quoting darf durch die schaerfere Trenner-Erkennung nicht kaputtgehen:
    # Trenner- und Klammer-Zeichen INNERHALB von Anfuehrungszeichen sind Text.
    'gh issue create --body "erst git status, dann && git commit -m x"',
    'echo "cd /tmp&&git commit -m x"',
    'grep -rn "git commit" src/ | wc -l',
]


def test_mehrzeilige_commit_message_bleibt_ein_token():
    """Zeilenumbruch INNERHALB von Anfuehrungszeichen ist kein Kommando-Trenner."""
    command = 'git commit -m "Betreff\n\nRumpfzeile"'
    assert hook_utils.git_subcommands(command) == ["commit"]
    assert hook_utils.is_pure_git_command(command) is True


@pytest.mark.parametrize("command", ERWAEHNUNGEN)
def test_blosse_erwaehnung_wird_nicht_als_commit_erkannt(command):
    assert hook_utils.is_git_subcommand(command, "commit") is False, command


def test_andere_unterbefehle_werden_unterschieden():
    assert hook_utils.is_git_subcommand("git -C /r add -A", "add") is True
    assert hook_utils.is_git_subcommand("git -C /r add -A", "commit") is False
    assert hook_utils.git_subcommands("git add -A && git commit -m x") == ["add", "commit"]


# --------------------------------------------------------------------- #
# 1b. Breite Fallsammlung — strukturelle Nichtregression
# --------------------------------------------------------------------- #
#
# Jeder Eintrag: (Kommando, ruft_wirklich_git_commit_auf).
# Die Sammlung deckt alle Verschachtelungs-Familien ab, die in drei
# Adversary-Runden aufgetaucht sind, plus eigene Ergaenzungen. Sie ist die
# Grundlage der beiden Struktur-Tests darunter.

AUFRUFE = [
    # --- direkte Formen und git-Vor-Optionen
    'git commit -m "x"',
    "git -c commit.gpgsign=false commit -m x",
    "git -C /home/hem/repo commit -m x",
    "git --no-pager commit -m x",
    "git --git-dir=/a/.git --work-tree=/a commit -m x",
    "git --git-dir /a/.git commit -m x",
    "/usr/bin/git commit -m x",
    "git commit --amend --no-edit",
    # --- Verkettung, mit und ohne Leerzeichen, mit Zeilenumbruch
    "cd /repo && git commit -m x",
    "git add -A && git -C /repo commit -m x",
    "cd /tmp&&git commit -m x",
    "git add -A;git commit -m x",
    "git fetch||git commit -m x",
    "cd /repo\ngit commit -m x",
    "git status\ngit -C /r commit -m x",
    # --- Wrapper vor git
    "sudo env git commit -m x",
    "FOO=1 BAR=2 git commit -m x",
    "sudo env FOO=1 git -C /repo commit -m x",
    "xargs -I{} git commit -m x",
    "nohup git commit -m x",
    # --- Kommandosubstitution (F005)
    "`git commit -m x`",
    "`git -C /repo commit -m x`",
    "git status `git commit -m x`",
    "echo $(git commit -m x)",
    "echo $(git -C /r commit -m x)",
    # --- Kontrollstrukturen (F006)
    "for f in a b; do git commit -m $f; done",
    "for f in a b; do git -C /r commit -m $f; done",
    "if git diff --quiet; then git commit -m x; fi",
    "while true; do git commit -m x; done",
    "case x in a) git commit -m x;; esac",
    "test -f a && { git commit -m x; }",
    # --- verschachtelte Shells / eval
    'bash -c "git -C /repo commit -m x"',
    'bash -c "cd /r && git commit -m x"',
    'eval "git commit -m x"',
    'sh -c "xargs git commit"',
    # --- Kommentarzeichen (F007)
    "git commit -m x # notiz",
    "git -C /r commit -m x # notiz",
    # --- Heredoc / Prozess-Substitution / Zeilenfortsetzung
    "git commit -F - <<EOF\nBetreff\nEOF",
    "cat <(git commit -m x)",
    "git \\\n commit -m x",
    "git -C /r \\\n commit -m x",
    # F009: Zeilenfortsetzung MITTEN IM WORT. Die Shell entfernt sie ersatzlos,
    # `gi\<umbruch>t` ist fuer sie schlicht `git`. Wird sie durch ein Leerzeichen
    # ersetzt, zerfaellt das Wort und es bleibt gar kein git-Token uebrig.
    "gi\\\nt commit -m x",
    "gi\\\nt -C /r commit -m x",
    # …dieselben Formen mit CRLF (Windows-Zeilenende)
    "gi\\\r\nt commit -m x",
    "git \\\r\n commit -m x",
    "git -C /r \\\r\n commit -m x",
    # --- kaputte Quotes (Lexer scheitert)
    'git commit -m "unbalancierte quote',
]

# Erwaehnungen, die SAUBER zerlegbar sind — hier muss die neue Entscheidung
# "durchlassen" lauten, obwohl die alte Teilstring-Pruefung angeschlagen haette.
# Das ist die einzige erlaubte Abschwaechung gegenueber der alten Pruefung.
ERWAEHNUNGEN_SAUBER = [
    'grep -rn "git commit" .claude/hooks/',
    'echo "vor dem git commit noch pruefen"',
    'gh issue create --title "Gate" --body "... git commit ... umgeht"',
    'rg "git commit" -l',
    'echo "cd /tmp&&git commit -m x"',
    'gh pr create --body "erst git status, dann && git commit -m x"',
    "git log --grep=commit --oneline",
    'git log --oneline | grep -c " commit "',
    "git status",
]


@pytest.mark.parametrize("command", AUFRUFE)
def test_echter_commit_aufruf_wird_immer_erkannt(command):
    """Kein Kommando, das wirklich committet, darf ungeprueft durchlaufen.

    Strukturelle Nichtregression: die Sammlung deckt alle bekannten
    Verschachtelungs-Familien ab. Ein neuer Trick muss hier eingetragen werden
    und faellt dann sofort auf, statt still durchzurutschen.
    """
    assert hook_utils.is_git_subcommand(command, "commit") is True, command


# Erwaehnungen INNERHALB einer Konstruktion, die wir nicht zuverlaessig
# auswerten koennen. Hier ist "im Zweifel pruefen" die gewollte Antwort — die
# Zeichenfolge steht UNGEQUOTET im Token-Strom, und ob sie ausgefuehrt wird,
# entscheidet erst die verschachtelte Shell. Der Preis ist ein zusaetzlicher
# Gate-Lauf, nicht ein Block: das Gate prueft dann seine echte Bedingung.
ERWAEHNUNGEN_IM_ZWEIFEL = [
    'bash -c "echo git commit"',
    "echo the git commit is broken",
]


@pytest.mark.parametrize("command", ERWAEHNUNGEN_SAUBER)
def test_saubere_erwaehnung_wird_durchgelassen(command):
    assert hook_utils.is_git_subcommand(command, "commit") is False, command


@pytest.mark.parametrize("command", ERWAEHNUNGEN_IM_ZWEIFEL)
def test_ungequotete_erwaehnung_wird_im_zweifel_geprueft(command):
    """Bewusste Ueber-Erkennung — dokumentiert, nicht uebersehen.

    Eine UNGEQUOTETE Erwaehnung ist von einem Aufruf durch einen unbekannten
    Wrapper (`xargs -I{} git commit`) nicht unterscheidbar. Die neue
    Grundhaltung entscheidet solche Faelle zugunsten des Pruefens.
    """
    assert hook_utils.is_git_subcommand(command, "commit") is True, command


def test_fallsammlung_deckt_beide_richtungen_ab():
    """Wachhund gegen eine Sammlung, die die Aussage nicht mehr traegt.

    Ohne diese Pruefung koennte die Sammlung stillschweigend auf lauter Faelle
    zusammenschrumpfen, die schon die alte Teilstring-Pruefung fing — der
    Struktur-Test waere dann wertlos.
    """
    alt_faengt = [c for c in AUFRUFE if "git commit" in c]
    alt_verfehlt = [c for c in AUFRUFE if "git commit" not in c]
    assert len(alt_faengt) >= 20, "zu wenige Faelle, die die alte Pruefung fing"
    assert len(alt_verfehlt) >= 12, "zu wenige Faelle, die die alte Pruefung verfehlte"
    assert len(ERWAEHNUNGEN_SAUBER) >= 8


# --------------------------------------------------------------------- #
# 2. Unzerlegbares Kommando: kein Absturz, im Zweifel pruefen
# --------------------------------------------------------------------- #

def test_unzerlegbares_kommando_stuerzt_nicht_ab():
    """Kaputte Quotes duerfen weder werfen noch eine Aussage vortaeuschen."""
    command = "echo 'offen && git status"
    assert hook_utils.is_git_subcommand(command, "commit") is False
    assert hook_utils.git_subcommands(command) == []
    assert hook_utils.is_pure_git_command(command) is False


def test_unzerlegbares_kommando_mit_commit_wird_im_zweifel_geprueft():
    """Richtungswechsel Runde 3: unzerlegbar + Zeichenfolge -> pruefen.

    Vorher lieferte dieser Fall False ("fail-open") — damit war das Gate ueber
    absichtlich kaputte Quotes umgehbar.
    """
    command = 'git commit -m "unbalancierte quote'
    assert hook_utils.is_git_subcommand(command, "commit") is True
    assert hook_utils.is_pure_git_command(command) is False


def test_zeilenfortsetzung_wird_ersatzlos_entfernt_und_nichts_sonst():
    """F009 samt Abgrenzung: nur `\\`+Umbruch verschwindet, sonst kein Backslash.

    Die Shell entfernt eine Zeilenfortsetzung ERSATZLOS — sie ist kein
    Trennzeichen. Ein Leerzeichen als Ersatz zerreisst `gi\\<umbruch>t` in zwei
    Woerter, und damit verschwindet das einzige git-Token.
    """
    # ersatzlos: die Wortteile kleben wieder zusammen
    assert hook_utils.git_subcommands("gi\\\nt commit -m x") == ["commit"]
    assert hook_utils.git_subcommands("gi\\\r\nt commit -m x") == ["commit"]
    assert hook_utils.is_pure_git_command("gi\\\nt status") is True

    # ein maskiertes LEERZEICHEN ist etwas ganz anderes und bleibt unberuehrt
    assert hook_utils._git_lex("git add mein\\ datei.txt") == [
        "git", "add", "mein datei.txt"
    ]

    # Backslash in Anfuehrungszeichen: Struktur bleibt heil, Inhalt folgt der
    # Shell (in doppelten Quotes ist `\\`+Umbruch ebenfalls Fortsetzung)
    quoted = 'git commit -m "Pfad C:\\\ntemp"'
    assert hook_utils.git_subcommands(quoted) == ["commit"]
    assert hook_utils._git_lex(quoted)[-1] == "Pfad C:temp"

    # doppelter Backslash (Windows-Pfad) wird nicht angefasst
    assert hook_utils._git_lex('git add "C:\\\\temp\\\\x.txt"') == [
        "git", "add", "C:\\temp\\x.txt"
    ]


def test_wrapper_kette_bleibt_ein_reiner_git_aufruf():
    """F004: mehrgliedrige Wrapper vor `git` duerfen die Ausnahme nicht kippen.

    `is_pure_git_command` traegt die Ausnahme von der Freigabe-Marker-Sperre.
    Ohne vollstaendiges Ueberspringen der Wrapper-Kette (`sudo env git …`)
    verloere ein legitimer git-Aufruf sie — und mit einem angehaengten
    Nicht-git-Kommando muss sie in jedem Fall entfallen.
    """
    assert hook_utils.is_pure_git_command("sudo env git status") is True
    assert hook_utils.is_pure_git_command("FOO=1 BAR=2 git status") is True
    assert hook_utils.is_pure_git_command("sudo env FOO=1 git -C /r status") is True
    assert hook_utils.is_pure_git_command("sudo env git status && touch /tmp/x") is False


def test_kommentarzeichen_verdeckt_kein_angehaengtes_kommando():
    """F007: `#` muss Text bleiben (`commenters=""`), sonst verschwindet der Rest."""
    command = "git status # notiz\ntouch /tmp/marker"
    assert hook_utils.is_pure_git_command(command) is False
    assert hook_utils.git_subcommands("git commit -m x # notiz") == ["commit"]


# --------------------------------------------------------------------- #
# 3. Whitelist: Aufruf statt Erwaehnung
# --------------------------------------------------------------------- #

def test_whitelist_trifft_alternative_git_aufrufform():
    assert bash_gate._is_whitelisted('git -C /repo add .claude/workflows/x.json') is True


def test_whitelist_trifft_nicht_bei_blosser_erwaehnung():
    cmd = 'python3 -c "open(\'.claude/workflows/x.json\',\'w\')"  # git commit'
    assert bash_gate._is_whitelisted(cmd) is False


def test_whitelist_erkennt_skript_eintraege_ueber_pfad():
    assert bash_gate._is_whitelisted(
        'python3 /plugin/core/hooks/workflow.py phase phase6_implement'
    ) is True
    assert bash_gate._is_whitelisted('echo "siehe workflow.py"') is False


# --------------------------------------------------------------------- #
# 4. Wirkungstest — echtes Bash-Gate als Subprozess gegen eine Sandbox
# --------------------------------------------------------------------- #

def _sandbox(tmp_path: Path) -> Path:
    """Projekt-Sandbox mit aktivem Workflow in phase6_implement ohne Verdict."""
    claude = tmp_path / ".claude"
    (claude / "workflows").mkdir(parents=True)
    (tmp_path / ".git").mkdir()  # kein Worktree -> Haupt-Repo-Aufloesung
    (claude / "active_workflow").write_text("sandboxwf\n")
    (claude / "workflows" / "sandboxwf.json").write_text(json.dumps({
        "name": "sandboxwf",
        "current_phase": "phase6_implement",
        "workflow_type": "feature",
    }))
    return tmp_path


def _run_bash_gate(command: str, project_dir: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["CLAUDE_PROJECT_DIR"] = str(project_dir)
    env["CLAUDE_TOOL_INPUT"] = json.dumps({"command": command})
    env.pop("OPENSPEC_ACTIVE_WORKFLOW", None)
    return subprocess.run(
        [sys.executable, str(HOOKS_DIR / "bash_gate.py")],
        cwd=str(project_dir), env=env, capture_output=True, text=True, timeout=60,
    )


def test_wirkung_alternative_aufrufform_wird_vom_gate_geprueft(tmp_path):
    """`git -C /pfad commit` muss am fehlenden Adversary-Verdict blocken.

    Vor dem Fix beendete der Fast Path (`startswith("git ")` +
    `"git commit" not in command`) den Hook mit ALLOW — Secrets-Guard,
    Credential-Pruefung und alle Commit-Gates liefen nie.
    """
    sandbox = _sandbox(tmp_path)
    proc = _run_bash_gate(f'git -C {sandbox} commit -m "x"', sandbox)
    assert proc.returncode == 2, (
        "Alternative Aufrufform umgeht das Gate weiterhin: "
        f"rc={proc.returncode} out={proc.stdout!r} err={proc.stderr!r}"
    )
    assert "Adversary verdict" in proc.stderr


def test_wirkung_kanonische_aufrufform_blockt_weiterhin(tmp_path):
    sandbox = _sandbox(tmp_path)
    proc = _run_bash_gate('git commit -m "x"', sandbox)
    assert proc.returncode == 2, proc.stderr


def test_wirkung_erwaehnung_wird_nicht_mehr_blockiert(tmp_path):
    """`grep -rn "git commit"` ist ein Lesebefehl — das Gate darf nicht anspringen."""
    sandbox = _sandbox(tmp_path)
    proc = _run_bash_gate('grep -rn "git commit" .claude/hooks/', sandbox)
    assert proc.returncode == 0, (
        "Blosse Erwaehnung loest die Commit-Gates weiterhin aus: "
        f"rc={proc.returncode} err={proc.stderr!r}"
    )


def _sandbox_ohne_workflow(tmp_path: Path) -> Path:
    """Sandbox OHNE aktiven Workflow.

    F008: Die frueher hier behauptete Begruendung ("mit Workflow waere der Test
    gruen, ohne die Marker-Sperre je zu pruefen") ist empirisch falsch — der
    Adversary konnte sie nicht reproduzieren. Richtig ist: Fast Path (Abschnitt
    2) und Marker-Sperre (Abschnitt 3a) arbeiten workflow-UNABHAENGIG, beide
    Sandbox-Varianten liefern dasselbe Ergebnis. Die workflow-freie Variante
    wird trotzdem genutzt, weil sie die Ursache eines Blocks eindeutig macht:
    hier kann NUR die Marker-Sperre Exit 2 erzeugen, nicht zusaetzlich das
    Adversary-Verdict-Gate aus Abschnitt 5.
    """
    (tmp_path / ".claude").mkdir(parents=True)
    (tmp_path / ".git").mkdir()
    return tmp_path


MARKER_ANHAENGSEL = [
    # mit Leerzeichen um den Trenner (Ausgangsbefund)
    "git status && touch .claude/user_approved_validation_wf",
    # Adversary F001: Zeilenumbruch statt '&&'
    "git status\ntouch .claude/user_approved_validation_wf",
    "git commit -m x\ntouch .claude/user_approved_validation_wf",
    # Adversary F002: Trenner ohne Leerzeichen
    "git status&&touch .claude/user_approved_validation_wf",
    "git status;touch .claude/user_approved_validation_wf",
    # Adversary F005: Kommandosubstitution mit Backticks
    "git status `touch .claude/user_approved_validation_wf`",
    "`touch .claude/user_approved_validation_wf`",
    # Adversary F006: Kontrollstruktur-Schluesselwoerter
    "for f in a; do touch .claude/user_approved_validation_wf; done",
    "if git diff --quiet; then touch .claude/user_approved_validation_wf; fi",
    # Adversary F007: Kommentarzeichen verdeckt das angehaengte Kommando
    "git status # notiz\ntouch .claude/user_approved_validation_wf",
]


@pytest.mark.parametrize("command", MARKER_ANHAENGSEL)
def test_wirkung_marker_ausnahme_gilt_nicht_fuer_angehaengtes_kommando(tmp_path, command):
    """Ein angehaengtes `touch <freigabe-marker>` darf die Marker-Sperre nie umgehen.

    Die Ausnahme in Abschnitt 3a gilt nur fuer reine git-Ketten. Sobald ein
    Nicht-git-Segment dranhaengt — egal ob per `&&`, `;` oder Zeilenumbruch,
    mit oder ohne Leerzeichen — muss die Sperre greifen.
    """
    sandbox = _sandbox_ohne_workflow(tmp_path)
    proc = _run_bash_gate(command, sandbox)
    assert proc.returncode == 2, (
        "Freigabe-Marker per Bash erzeugbar — Kommando-Trenner nicht erkannt: "
        f"rc={proc.returncode} cmd={command!r} err={proc.stderr!r}"
    )


def test_wirkung_trenner_ohne_leerzeichen_wird_vom_gate_geprueft(tmp_path):
    """Adversary F002: `cd /tmp&&git commit` muss die Commit-Gates erreichen.

    Regression gegenueber dem ALTEN Teilstring-Code, der diesen Fall fing.
    """
    sandbox = _sandbox(tmp_path)
    proc = _run_bash_gate("cd /tmp&&git commit -m x", sandbox)
    assert proc.returncode == 2, (
        "Trenner ohne Leerzeichen umgeht das Adversary-Verdict-Gate: "
        f"rc={proc.returncode} err={proc.stderr!r}"
    )
    assert "Adversary verdict" in proc.stderr


def test_wirkung_zeilenumbruch_vor_commit_wird_vom_gate_geprueft(tmp_path):
    """Adversary F001: Zeilenumbruch als Trenner vor dem Commit."""
    sandbox = _sandbox(tmp_path)
    proc = _run_bash_gate("cd /tmp\ngit -C /repo commit -m x", sandbox)
    assert proc.returncode == 2, (
        f"Zeilenumbruch-Trenner umgeht das Gate: rc={proc.returncode} err={proc.stderr!r}"
    )


def test_wirkung_commit_message_darf_marker_erwaehnen(tmp_path):
    """Gegenprobe: eine reine git-Kette bleibt von der Marker-Sperre ausgenommen."""
    sandbox = _sandbox(tmp_path)
    proc = _run_bash_gate('git log --grep="user_approved_validation"', sandbox)
    assert proc.returncode == 0, proc.stderr
