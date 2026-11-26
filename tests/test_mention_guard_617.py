"""Erwähnungs-Sperre: PreToolUse-Bash-Hook gegen nackte `@name` in gh-Texten (#617).

Der Hook läuft wie in Claude Code als eigener Prozess mit der PreToolUse-Payload
auf stdin. Blockade = Exit 2 mit Begründung auf stderr; jeder andere Fall Exit 0.

Die Testdaten setzen jede Erwähnung erst zur Laufzeit aus `AT` zusammen, damit
diese Datei selbst auf GitHub niemanden erwähnt.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOK = REPO_ROOT / "core" / "hooks" / "mention_guard.py"
HOOKS_JSON = REPO_ROOT / "hooks" / "hooks.json"
AT = "@"  # Namen werden zusammengesetzt, damit diese Datei selbst niemanden erwähnt


def _env(tmp_path: Path, extra=None) -> dict:
    env = {k: v for k, v in os.environ.items()
           if k not in ("OPENSPEC_MENTION_GUARD", "CLAUDE_TOOL_NAME", "CLAUDE_TOOL_INPUT")}
    # Projekt-Config aus dem tmp-Ordner (config_loader nimmt CLAUDE_PROJECT_DIR zuerst)
    env["CLAUDE_PROJECT_DIR"] = str(tmp_path)
    env.update(extra or {})
    return env


def _run(tmp_path: Path, payload, env_extra=None) -> subprocess.CompletedProcess:
    data = payload if isinstance(payload, str) else json.dumps(payload)
    return subprocess.run([sys.executable, str(HOOK)], input=data, capture_output=True,
                          text=True, cwd=str(tmp_path), env=_env(tmp_path, env_extra),
                          timeout=20)


def _bash(tmp_path: Path, command: str, env_extra=None) -> subprocess.CompletedProcess:
    payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash",
               "tool_input": {"command": command}, "cwd": str(tmp_path)}
    return _run(tmp_path, payload, env_extra)


def _blocked(r: subprocess.CompletedProcess, *names: str) -> None:
    assert r.returncode == 2, f"erwartet Exit 2, bekam {r.returncode}: {r.stderr}"
    for n in names:
        assert AT + n in r.stderr, r.stderr
    assert "Backtick" in r.stderr, r.stderr
    assert "allowed_users" in r.stderr, r.stderr


def _free(r: subprocess.CompletedProcess) -> None:
    assert r.returncode == 0, f"erwartet Exit 0, bekam {r.returncode}: {r.stderr}"


# --- AC-1: nackte Erwähnung blockt -------------------------------------------

def test_ac1_issue_comment_mit_nackter_erwaehnung(tmp_path):
    r = _bash(tmp_path, f'gh issue comment 5 --body "verbunden · {AT}henning"')
    _blocked(r, "henning")
    assert "benachrichtig" in r.stderr


def test_ac1_positionen_und_schreibweisen(tmp_path):
    for text in (f"{AT}henning ist da",            # Zeilenanfang
                 f"Zeile eins\n{AT}henning",         # Anfang einer Folgezeile
                 f"(siehe {AT}henning)",             # nach Klammer
                 f"Konto:{AT}henning",               # nach Doppelpunkt
                 f"verbunden ·{AT}henning",          # nach „·“
                 f"Gruß an {AT}henning.",            # Satzende
                 f"Gruß an {AT}Henning"):            # Großschreibung
        r = _bash(tmp_path, f"gh issue comment 5 --body '{text}'")
        assert r.returncode == 2, f"{text!r}: {r.stderr}"
    r = _bash(tmp_path, f"gh issue comment 5 --body 'Hallo {AT}Henning'")
    _blocked(r, "Henning")


def test_ac1_alle_schreibenden_befehle(tmp_path):
    body = f"--body 'x {AT}henning'"
    for cmd in (f"gh issue create --title t {body}",
                f"gh issue edit 5 {body}",
                f"gh issue close 5 --comment 'x {AT}henning'",
                f"gh issue reopen 5 --comment 'x {AT}henning'",
                f"gh pr create --title t {body}",
                f"gh pr comment 7 {body}",
                f"gh pr review 7 --approve {body}",
                f"gh pr merge 7 --merge {body}",
                f"gh pr edit 7 {body}",
                f"gh release create v1 --notes 'x {AT}henning'",
                f"gh release edit v1 --notes 'x {AT}henning'",
                f"gh api repos/o/r/issues/5/comments -f body='x {AT}henning'",
                f"gh api -X POST repos/o/r/issues/5/comments -f body='x {AT}henning'"):
        r = _bash(tmp_path, cmd)
        assert r.returncode == 2, f"{cmd}: {r.stderr}"


def test_ac1_gh_hinter_zuweisung_pfad_und_globalem_flag(tmp_path):
    body = f"--body 'x {AT}henning'"
    for cmd in (f"GH_TOKEN=abc /usr/bin/gh issue comment 5 {body}",
                f"gh -R owner/repo issue comment 5 {body}",
                f"gh --repo owner/repo issue comment 5 {body}",
                f"gh issue -R owner/repo comment 5 {body}",
                f"gh issue comment 5 --repo owner/repo {body}",
                f"cd /tmp && gh issue comment 5 {body}",
                f"echo los; gh pr comment 7 {body} | cat",
                f'gh issue comment 5 --body "$(printf \'x {AT}henning\')"'):
        r = _bash(tmp_path, cmd)
        assert r.returncode == 2, f"{cmd}: {r.stderr}"


def test_ac1_mehrere_namen_werden_genannt(tmp_path):
    r = _bash(tmp_path, f"gh issue comment 5 --body 'an {AT}anna und {AT}bert-2'")
    _blocked(r, "anna", "bert-2")


# --- AC-2: keine Erwähnung ---------------------------------------------------

def test_ac2_backticks_codeblock_mail_paket(tmp_path):
    for text in (f"verbunden · `{AT}henning`",
                 f"Oberfläche:\n```\nverbunden · {AT}henning\n```\nEnde",
                 "Mail an henning" + AT + "henemm.com",
                 f"Paket {AT}scope/paket installieren",
                 "kein At-Zeichen hier"):
        r = _bash(tmp_path, f"gh issue comment 5 --body-file - <<'EOF'\n{text}\nEOF")
        assert r.returncode == 0, f"{text!r}: {r.stderr}"


def test_ac2_shellformen_im_schreibenden_befehl(tmp_path):
    for cmd in ('f() { gh issue comment "$@"; }',
                'gh issue comment 5 --body "${teile[@]}"',
                'gh issue comment "${args[@]}"'):
        _free(_bash(tmp_path, cmd))


def test_ac2_feld_mit_dateiverweis_selbst_ist_keine_erwaehnung(tmp_path):
    (tmp_path / "datei.json").write_text('{"body": "sauber"}')
    _free(_bash(tmp_path, "gh api repos/o/r/issues/5/comments -F body=@datei.json"))
    _free(_bash(tmp_path, "gh api repos/o/r/issues/5/comments --field body=@datei.json"))


# --- AC-3: Body-Dateien und Heredocs -----------------------------------------

def test_ac3_body_file_mit_erwaehnung(tmp_path):
    (tmp_path / "body.md").write_text(f"Text\nverbunden · {AT}henning\n")
    _blocked(_bash(tmp_path, "gh issue comment 5 --body-file body.md"), "henning")
    _blocked(_bash(tmp_path, "gh issue comment 5 --body-file=body.md"), "henning")
    _blocked(_bash(tmp_path, "gh pr create --title t -F body.md"), "henning")
    _blocked(_bash(tmp_path, f"gh issue comment 5 --body-file {tmp_path / 'body.md'}"),
             "henning")


def test_ac3_body_file_sauber(tmp_path):
    (tmp_path / "body.md").write_text("Text\nverbunden · `" + AT + "henning`\n")
    _free(_bash(tmp_path, "gh issue comment 5 --body-file body.md"))
    _free(_bash(tmp_path, "gh issue comment 5 --body-file fehlt.md"))


def test_ac3_heredoc_schreibt_body_file_im_selben_befehl(tmp_path):
    cmd = (f"cat > {tmp_path}/neu.md <<'EOF'\nGruß an {AT}henning\nEOF\n"
           f"gh pr create --title t --body-file {tmp_path}/neu.md")
    assert not (tmp_path / "neu.md").exists()
    _blocked(_bash(tmp_path, cmd), "henning")


def test_ac3_api_feld_und_input_datei(tmp_path):
    (tmp_path / "datei.md").write_text(f"x {AT}henning")
    _blocked(_bash(tmp_path, "gh api repos/o/r/issues/5/comments -F body=@datei.md"),
             "henning")
    _blocked(_bash(tmp_path, "gh api repos/o/r/issues/5/comments --field body=@datei.md"),
             "henning")
    (tmp_path / "in.json").write_text(json.dumps({"body": f"x {AT}henning"}))
    _blocked(_bash(tmp_path, "gh api repos/o/r/issues/5/comments --input in.json"),
             "henning")


def test_ac3_relativer_pfad_gegen_payload_cwd(tmp_path):
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "b.md").write_text(f"{AT}henning")
    payload = {"tool_name": "Bash", "cwd": str(sub),
               "tool_input": {"command": "gh issue comment 5 --body-file b.md"}}
    r = _run(tmp_path, payload)  # Prozess-cwd ist tmp_path, payload-cwd ist sub
    _blocked(r, "henning")


# --- AC-4: lesende Befehle und Befehle ohne gh -------------------------------

def test_ac4_lesende_befehle_frei(tmp_path):
    for cmd in ("gh issue view 5",
                f"gh issue list --search '{AT}henning'",
                f'gh search issues "{AT}henning"',
                f"gh api -X GET search/issues -f q='{AT}henning'",
                f"gh api --method GET search/issues -f q='{AT}henning'",
                f"gh api -XGET search/issues -f q='{AT}henning'",
                f"gh api --method=GET search/issues -f q='{AT}henning'",
                f"gh pr view 7 --comments | grep '{AT}henning'",
                f"echo 'Gruß an {AT}henning'",
                f"git commit -m 'Gruß an {AT}henning'",
                f"cat > notiz.md <<'EOF'\n{AT}henning\nEOF"):
        r = _bash(tmp_path, cmd)
        assert r.returncode == 0, f"{cmd}: {r.stderr}"


# --- AC-5: Freigabeliste und Abschalten --------------------------------------

def test_ac5_freigabeliste_aus_openspec_yaml(tmp_path):
    (tmp_path / "openspec.yaml").write_text(
        "mention_guard:\n  allowed_users: [Henning]\n", encoding="utf-8")
    _free(_bash(tmp_path, f"gh issue comment 5 --body 'Hallo {AT}henning'"))
    # andere Namen blocken weiter, der freigegebene wird nicht genannt
    r = _bash(tmp_path, f"gh issue comment 5 --body 'Hallo {AT}henning und {AT}anna'")
    _blocked(r, "anna")
    assert AT + "henning" not in r.stderr


def test_ac5_abschalten_per_config(tmp_path):
    (tmp_path / "openspec.yaml").write_text(
        "mention_guard:\n  enabled: false\n", encoding="utf-8")
    _free(_bash(tmp_path, f"gh issue comment 5 --body 'Hallo {AT}henning'"))


def test_ac5_abschalten_per_umgebung(tmp_path):
    cmd = f"gh issue comment 5 --body 'Hallo {AT}henning'"
    for wert in ("0", "off", "false", "no", "disabled", "OFF"):
        _free(_bash(tmp_path, cmd, {"OPENSPEC_MENTION_GUARD": wert}))
    assert _bash(tmp_path, cmd, {"OPENSPEC_MENTION_GUARD": "1"}).returncode == 2


# --- AC-6: fail-open ---------------------------------------------------------

def test_ac6_kaputte_oder_fremde_payload(tmp_path):
    for payload in ("", "{kaputt", "[]", "null",
                    json.dumps({"tool_name": "Read",
                                "tool_input": {"file_path": f"{AT}henning"}}),
                    json.dumps({"tool_name": "Write", "tool_input": {
                        "content": f"gh issue comment 5 --body '{AT}henning'"}}),
                    json.dumps({"tool_name": "Bash"}),
                    json.dumps({"tool_name": "Bash", "tool_input": {}}),
                    json.dumps({"tool_name": "Bash", "tool_input": {"command": 5}}),
                    json.dumps({"tool_name": "Bash", "tool_input": "gh issue comment"})):
        r = _run(tmp_path, payload)
        assert r.returncode == 0, f"{payload!r}: {r.stderr}"


def test_ac6_kaputte_config_und_unlesbare_datei(tmp_path):
    (tmp_path / "openspec.yaml").write_text("mention_guard: [kaputt\n", encoding="utf-8")
    r = _bash(tmp_path, "gh issue comment 5 --body-file /dev/null")
    assert r.returncode == 0, r.stderr
    (tmp_path / "openspec.yaml").write_text("mention_guard: 5\n", encoding="utf-8")
    r = _bash(tmp_path, "gh issue comment 5 --body-file ordner")
    assert r.returncode == 0, r.stderr


# --- Registrierung -----------------------------------------------------------

def test_registriert_unter_pretooluse_bash():
    data = json.loads(HOOKS_JSON.read_text())
    befehle = [h["command"] for g in data["hooks"]["PreToolUse"]
               if g.get("matcher") == "Bash" for h in g["hooks"]]
    assert "${CLAUDE_PLUGIN_ROOT}/core/hooks/mention_guard.py" in befehle
    assert os.access(HOOK, os.X_OK)


def test_default_block_in_config_yaml():
    import yaml
    cfg = yaml.safe_load((REPO_ROOT / "config.yaml").read_text())
    assert cfg["mention_guard"] == {"enabled": True, "allowed_users": []}


# --- Fix-Runde: F001 gh api nur schreibend, wenn es schreibt; jq-Ausdrücke ---

def test_f001_api_ohne_felder_mit_jq_ist_lesend(tmp_path):
    for cmd in ("gh api repos/x/y/issues/1/comments --jq '.[] | " + AT + "tsv'",
                "gh api repos/x/y/issues --jq='.[] | " + AT + "csv'",
                "gh api repos/x/y/issues -q '.[] | " + AT + "tsv'",
                "gh api repos/x/y/issues --template '{{" + AT + "foo}}'",
                "gh api repos/x/y/issues -X get -f q='" + AT + "henning'",
                "gh api repos/x/y/issues --method=get -f q='" + AT + "henning'"):
        r = _bash(tmp_path, cmd)
        assert r.returncode == 0, f"{cmd}: {r.stderr}"


def test_f001_api_schreibt_bei_methode_oder_feldern(tmp_path):
    for cmd in (f"gh api -XPOST repos/o/r/issues 'x {AT}henning'",
                f"gh api --method=post repos/o/r/issues 'x {AT}henning'",
                f"gh api -X delete repos/o/r/x 'x {AT}henning'",
                f"gh api -X PATCH repos/o/r/x 'x {AT}henning'",
                f"gh api repos/o/r/issues -fbody='x {AT}henning'",
                f"gh api repos/o/r/issues --raw-field body='x {AT}henning'",
                f"gh api repos/o/r/issues --raw-field='body=x {AT}henning'",
                f"gh api repos/o/r/issues -F 'body=x {AT}henning'"):
        r = _bash(tmp_path, cmd)
        assert r.returncode == 2, f"{cmd}: {r.stderr}"


def test_f001_jq_ausdruck_in_schreibendem_befehl_zaehlt_nicht(tmp_path):
    _free(_bash(tmp_path, "gh api -X POST repos/o/r/issues -f body=ok --jq '.user | "
                + AT + "tsv'"))
    _free(_bash(tmp_path, "gh api repos/o/r/issues -f body=ok -t '{{" + AT + "x}}'"))
    _blocked(_bash(tmp_path, f"gh api repos/o/r/issues -f body='{AT}henning' --jq .id"),
             "henning")


# --- F002: Text aus Dateien per Shell -----------------------------------------

def test_f002_text_aus_datei_per_shell(tmp_path):
    (tmp_path / "datei").write_text(f"x {AT}henning")
    for cmd in ('gh issue comment 1 -b "$(cat datei)"',
                'gh issue comment 1 --body "$(cat datei)"',
                'gh issue comment 1 --body "$(cat -- datei)"',
                'gh api repos/o/r/issues/1/comments -f body="$(cat datei)"',
                'B=$(cat datei); gh issue comment 1 --body "$B"',
                'gh issue comment 1 --body "`cat datei`"',
                'gh issue comment 1 --body "$(< datei)"',
                'gh issue comment 1 --body-file - < datei',
                'gh issue comment 1 --body-file -<datei'):
        r = _bash(tmp_path, cmd)
        assert r.returncode == 2, f"{cmd}: {r.stderr}"
        assert AT + "henning" in r.stderr


def test_f002_saubere_datei_und_lesender_befehl(tmp_path):
    (tmp_path / "sauber").write_text("nichts")
    (tmp_path / "datei").write_text(f"x {AT}henning")
    _free(_bash(tmp_path, 'gh issue comment 1 --body "$(cat sauber)"'))
    _free(_bash(tmp_path, 'gh issue view 1 < datei'))
    _free(_bash(tmp_path, 'B=$(cat datei); echo "$B"'))


# --- Zusatz / AC-7: Präfixe und Shell-Aufrufe ---------------------------------

def test_ac7_gh_hinter_shell_und_praefixen(tmp_path):
    (tmp_path / "b.md").write_text(f"{AT}henning")
    body = f"--body 'x {AT}henning'"
    for cmd in (f"bash -c \"gh issue comment 1 {body}\"",
                "sh -c 'gh issue comment 1 --body-file b.md'",
                f"bash -lc \"cd . && gh pr comment 1 {body}\"",
                f"timeout 30 gh issue comment 1 {body}",
                f"timeout -s KILL 30 gh issue comment 1 {body}",
                f"nice -n 5 gh issue comment 1 {body}",
                f"sudo -u hem gh issue comment 1 {body}",
                f"env -u X GH_TOKEN=1 gh issue comment 1 {body}",
                "timeout 30 gh issue comment 1 --body-file b.md",
                f"echo 5 | xargs -I{{}} gh issue comment {{}} {body}"):
        r = _bash(tmp_path, cmd)
        assert r.returncode == 2, f"{cmd}: {r.stderr}"


def test_ac7_lesend_hinter_shell_bleibt_frei(tmp_path):
    for cmd in (f"bash -c \"gh issue list --search '{AT}henning'\"",
                f"timeout 30 gh issue view 1 | grep '{AT}henning'"):
        _free(_bash(tmp_path, cmd))


# --- Laufzeitgrenze ------------------------------------------------------------

def test_laufzeit_150kb_unter_2s_und_ueber_200kb_frei(tmp_path):
    import time
    fueller = "wort " * (150 * 1024 // 5)
    cmd = f"gh issue comment 1 --body '{fueller} {AT}henning'"
    # #671: Grundaufwand (Prozessstart, Import) im selben Lauf am selben Hook
    # messen und abziehen; nur der Mehraufwand fuer 150 KB zaehlt gegen 2,0 s.
    grund = float("inf")
    for _ in range(2):
        t0 = time.monotonic()
        rk = _bash(tmp_path, f"gh issue comment 1 --body 'kurz {AT}henning'")
        grund = min(grund, time.monotonic() - t0)
        assert rk.returncode == 2, rk.stderr
    t0 = time.monotonic()
    r = _bash(tmp_path, cmd)
    dauer = time.monotonic() - t0
    assert r.returncode == 2, r.stderr
    assert dauer - grund < 2.0, (dauer, grund)
    gross = f"gh issue comment 1 --body '{'wort ' * (250 * 1024 // 5)} {AT}henning'"
    _free(_bash(tmp_path, gross))


# --- F003: Grenzfälle, die Mutationen fangen ----------------------------------

def test_grob_fallback_bei_offenem_anfuehrungszeichen(tmp_path):
    _blocked(_bash(tmp_path, f"gh issue comment 5 --body 'x {AT}henning"), "henning")
    _blocked(_bash(tmp_path, f"gh api repos/o/r -f body='x {AT}henning"), "henning")
    _free(_bash(tmp_path, f"gh api -X GET search -f q='{AT}henning"))
    _free(_bash(tmp_path, f"gh issue view 5 --comments 'x {AT}henning"))


def test_inline_code_mit_text_davor(tmp_path):
    _free(_bash(tmp_path, f"gh issue comment 5 --body 'cc `fix {AT}henning` x'"))


def test_namensgrenzen(tmp_path):
    def run(text):
        return _bash(tmp_path, f"gh issue comment 5 --body '{text}'")
    _free(run(f"x {AT}foo-"))                       # Name endet nie auf -
    _free(run(f"x {AT}foo- y"))
    _free(run(f"x {AT}org/team"))                   # Team-Erwähnung bleibt frei (Spec)
    _blocked(run(f"x {AT}foo-bar y"), "foo-bar")
    _blocked(run(f"x {AT}{'a' * 39} y"), "a" * 39)
    _free(run(f"x {AT}{'a' * 40} y"))               # länger als ein Nutzername


def test_dedup_name_einmal_in_meldung(tmp_path):
    r = _bash(tmp_path, f"gh issue comment 5 --body '{AT}anna, {AT}Anna und {AT}anna'")
    assert r.returncode == 2, r.stderr
    assert r.stderr.lower().count(AT + "anna") == 1, r.stderr


def test_eine_mb_grenze_je_datei(tmp_path):
    (tmp_path / "hinten.md").write_bytes(b"x" * (1024 * 1024) + f" {AT}henning".encode())
    _free(_bash(tmp_path, "gh issue comment 5 --body-file hinten.md"))
    (tmp_path / "vorn.md").write_bytes(f"{AT}henning ".encode() + b"x" * (1024 * 1024))
    _blocked(_bash(tmp_path, "gh issue comment 5 --body-file vorn.md"), "henning")


def test_feld_formen_mit_dateiverweis(tmp_path):
    (tmp_path / "datei.md").write_text(f"x {AT}henning")
    for cmd in ("gh api repos/o/r/issues/5/comments --field=body=@datei.md",
                "gh api repos/o/r/issues/5/comments -Fbody=@datei.md"):
        _blocked(_bash(tmp_path, cmd), "henning")


def test_heredoc_mit_apostroph_vor_body_file(tmp_path):
    # Ohne Heredoc-Strip scheitert die Zerlegung am Apostroph, und die
    # existierende Body-Datei würde nicht mehr gelesen.
    (tmp_path / "vorhanden.md").write_text(f"{AT}henning")
    cmd = ("cat > notiz.md <<'EOF'\nit's done\nEOF\n"
           "gh issue comment 1 --body-file vorhanden.md")
    _blocked(_bash(tmp_path, cmd), "henning")


def test_verzeichnis_als_body_file(tmp_path):
    (tmp_path / "ordner").mkdir()
    _free(_bash(tmp_path, "gh issue comment 5 --body-file ordner"))
    r = _bash(tmp_path, f"gh issue comment 5 --body-file ordner --title '{AT}henning'")
    _blocked(r, "henning")


def test_stdin_aus_cat_in_derselben_pipe(tmp_path):
    (tmp_path / "datei").write_text(f"x {AT}henning")
    (tmp_path / "sauber").write_text("nichts")
    for cmd in ("cat datei | gh issue comment 1 --body-file -",
                "cat datei | gh pr create -t t -F -",
                "cat datei | gh issue comment 1 --body-file=-",
                "cat -- datei | gh api repos/o/r/issues/1/comments --input -"):
        r = _bash(tmp_path, cmd)
        assert r.returncode == 2, f"{cmd}: {r.stderr}"
    _free(_bash(tmp_path, "cat sauber | gh issue comment 1 --body-file -"))
    _free(_bash(tmp_path, "cat datei; gh issue comment 1 --body-file -"))  # keine Pipe
    _free(_bash(tmp_path, "cat datei | gh issue view 1"))


def test_jq_ausdruecke_in_schreibendem_api_befehl(tmp_path):
    for cmd in ("gh api -X POST repos/o/r/issues -f body=ok -q '.[] | " + AT + "tsv'",
                "gh api -X POST repos/o/r/issues -f body=ok --jq='.[] | " + AT + "csv'",
                "gh api -X POST repos/o/r/issues -f body=ok --template '{{" + AT + "x}}'"):
        _free(_bash(tmp_path, cmd))


def test_body_aus_umleitung_in_substitution(tmp_path):
    (tmp_path / "datei").write_text(f"x {AT}henning")
    _blocked(_bash(tmp_path, 'gh issue comment 1 -b "$(< datei)"'), "henning")


def test_verschachteltes_bash_c(tmp_path):
    (tmp_path / "b.md").write_text(f"{AT}henning")
    for cmd in ("bash -c \"sh -c 'gh issue comment 1 --body-file b.md'\"",
                "bash -c \"sh -c \\\"bash -c 'gh issue comment 1 --body-file b.md'\\\"\""):
        _blocked(_bash(tmp_path, cmd), "henning")


def test_grob_fallback_in_bash_c_und_methoden(tmp_path):
    _blocked(_bash(tmp_path, f"bash -c \"gh issue comment 1 --body 'x {AT}henning\""),
             "henning")
    _free(_bash(tmp_path, f'gh api -X GET search -f q="offen {AT}henning'))
    _blocked(_bash(tmp_path, f'gh api -X POST repos/o/r -f body="offen {AT}henning'),
             "henning")


def test_200kb_grenze_genau(tmp_path):
    kopf = "gh issue comment 1 --body '"
    fuss = f" {AT}henning'"

    def cmd(laenge):
        return kopf + "x" * (laenge - len(kopf) - len(fuss)) + fuss
    _blocked(_bash(tmp_path, cmd(200 * 1024)), "henning")
    _free(_bash(tmp_path, cmd(200 * 1024 + 1)))


def test_kaputte_config_schuetzt_weiter_ohne_absturz(tmp_path):
    cmd = f"gh issue comment 5 --body 'x {AT}henning'"
    for inhalt in ("mention_guard: [kaputt\n", "mention_guard: 5\n",
                   "mention_guard:\n  allowed_users: 5\n",
                   "mention_guard:\n  allowed_users: [[x], {a: 1}]\n"):
        (tmp_path / "openspec.yaml").write_text(inhalt, encoding="utf-8")
        r = _bash(tmp_path, cmd)
        assert r.returncode == 2, f"{inhalt!r}: {r.stderr}"
        assert "Traceback" not in r.stderr
