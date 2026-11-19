# Fast Track: Erwähnungs-Sperre für Texte, die per gh veröffentlicht werden (#617)

## Problem

Claude-Sitzungen haben in Issue-Kommentaren Oberflächentexte aus Mockups zitiert, die ein nacktes
`@name` enthielten („verbunden · `@henning`“). GitHub wertet jedes nackte `@name` als Erwähnung
und benachrichtigt den gleichnamigen Nutzer, hier eine fremde Person. Vier Fälle vom 24.10. bis
19.11.2026 (henemm/gregor_zwanzig#2795 zweimal, #3151, henemm/frieda-reisen#25), der Betroffene
hat sich beschwert. Eine Gedächtnisregel hat nicht gereicht; die Sperre muss mechanisch sein und
in allen Projekten greifen, deshalb liefert das Plugin sie aus.

## Scope

- `core/hooks/mention_guard.py`: neuer PreToolUse-Hook (Bash) nach dem Muster der übrigen Guards
  (hook_utils, fail-open, Blockade per `block()` mit Exit 2).
- Geprüft werden nur Befehle, die Text auf GitHub veröffentlichen: `gh issue|pr` mit
  `create|comment|edit|close|reopen|review|merge`, `gh release create|edit`, `gh api` nur wenn es
  tatsächlich schreibt (Methode POST/PATCH/PUT/DELETE oder Felder `-f/-F/--field/--raw-field/--input`
  ohne `-X GET`, wie gh selbst entscheidet). Lesende Befehle (`view`, `list`, `search`, `gh api`
  ohne Felder, `gh api -X GET …`) bleiben frei; Ausdrücke hinter `--jq/-q/--template/-t` zählen
  nie als Text. `gh` hinter `bash -c`/`sh -c`, `timeout`, `nice`, `xargs` wird erkannt; Text aus
  `$(cat <datei>)` und `< <datei>` wird mitgelesen. Befehle über 200 KB werden nicht geprüft
  (fail-open, Laufzeitgrenze).
- Geprüfter Text: der gesamte Befehl (inklusive Heredoc-Inhalten, weil `--body-file` oft auf eine
  Datei zeigt, die derselbe Befehl erst schreibt) und der Inhalt existierender Dateien aus
  `--body-file`/`-F <datei>`/`--input <datei>`/`-F feld=@datei` (höchstens 1 MB je Datei).
- Erwähnung wie bei GitHub: `@` am Anfang oder nach einem Zeichen, das kein Wortzeichen, kein
  Backtick und keins von `/ . @ -` ist, gefolgt von einem Nutzernamen (`[A-Za-z0-9]`, dann bis 38
  Zeichen aus `[A-Za-z0-9-]`), dahinter kein Wortzeichen, kein `-` und kein `/`. Text in Backticks
  und Codeblöcken zählt nicht. E-Mail-Adressen (`name@domain`), Pakete (`@scope/paket`) und
  Shell-Formen (`"$@"`, `${a[@]}`) sind dadurch keine Treffer.
- Freigabeliste `mention_guard.allowed_users` (Groß-/Kleinschreibung egal), Abschalten per
  `mention_guard.enabled: false` oder Umgebungsvariable `OPENSPEC_MENTION_GUARD=0`.
- Registrierung in `hooks/hooks.json` unter PreToolUse/Bash, Cloud-Block `.claude/settings.json`
  per `scripts/sync_cloud_hooks.py` nachgezogen, Standardwerte in `config.yaml`.
- Nicht enthalten: Texte, die nicht über `gh` laufen (Commit-Nachrichten lösen bei GitHub keine
  Benachrichtigung aus), MCP-Werkzeuge für GitHub.

## Definition of Done

Alle ACs sind durch Tests belegt; die volle Suite bleibt grün; `sync_cloud_hooks.py --check`
meldet keine Drift.

## Acceptance Criteria

- **AC-1:** Given ein `gh issue comment`-Befehl, dessen Text ein nacktes `@henning` enthält, When der Hook läuft, Then endet er mit Exit 2 und nennt den Namen und den Weg, ihn in Backticks zu setzen.
- **AC-2:** Given derselbe Text mit `@henning` in Backticks oder in einem Codeblock, als E-Mail-Adresse oder als Paketname `@scope/paket`, When der Hook läuft, Then Exit 0.
- **AC-3:** Given ein `--body-file`, dessen Datei ein nacktes `@name` enthält, oder ein Heredoc im selben Befehl, der die Datei erst schreibt, When der Hook läuft, Then Exit 2.
- **AC-4:** Given ein lesender Befehl (`gh issue view`, `gh search issues "@henning"`, `gh api -X GET …`, `gh api <pfad> --jq '.[] | @tsv'` ohne Felder) oder ein Befehl ohne `gh`, When der Hook läuft, Then Exit 0.
- **AC-7:** Given ein schreibender gh-Befehl, dessen Text per `$(cat <datei>)` aus einer Datei mit nacktem `@name` kommt, oder der hinter `bash -c`/`timeout` steht, When der Hook läuft, Then Exit 2.
- **AC-5:** Given der Name steht in `mention_guard.allowed_users`, oder `OPENSPEC_MENTION_GUARD=0`, oder `mention_guard.enabled: false`, When der Hook läuft, Then Exit 0.
- **AC-6:** Given eine kaputte oder fremde Payload (kein JSON, anderes Werkzeug, kein Befehl), When der Hook läuft, Then Exit 0.

## Test Plan

- `tests/test_mention_guard_617.py` (AC-1 bis AC-7, Registrierung in `hooks/hooks.json`), volle Suite.
