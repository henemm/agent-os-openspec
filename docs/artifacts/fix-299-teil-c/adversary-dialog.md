# Adversary-Dialog fix-299-teil-c (Nachpruefung)

Code reference: core/hooks/bash_gate.py:260
Code reference: core/hooks/bash_gate.py:272
Code reference: core/hooks/bash_gate.py:294
Code reference: core/hooks/bash_gate.py:312
Code reference: core/hooks/hook_utils.py:317

### Runde 1

Methode: Subprozess-Aufrufe des echten Gates (Sandbox mit .git, active_workflow, Workflow phase6_implement) mit ca. 110 Befehlen, dazu die Suites Teil C + false_positives + freetext_64_75 + erkennung_299 + teil_b: 94 passed, 0 failed.

AC-1 (cd/pushd in den Workflow-Ordner + Schreib-Indikator auf bloßen Namen mit Endung json blockt): cd mit ./ Praefix, cd -- .claude mit Schreibzugriff auf workflows/<name>, cd workflows/sub, pushd, cd mit absolutem Pfad, dazu tee/cp/mv/rm/sed -i/truncate/Umleitung mit > und >> liefern alle Exit 2 (_cd_into_claude, bash_gate.py:294).
Status: CONFIRMED

AC-2 (Umleitung hinter erlaubtem Befehl auf State/Marker blockt): git status mit >, >>, >|, &>, &>>, 2>, 2>>, 1>, ohne Leerzeichen (status>state), mit ;>, ;;>, &&>, ;(>, |>, ;&>, hinter Zeilenfortsetzung und hinter Kommentarzeile liefern Exit 2; auch echo x &>state (_redirects_to_protected, _strip_leading_separators, bash_gate.py:260/272).
Status: CONFIRMED

AC-3 (Kommentar mit Apostroph am Ende von git status && sed -i auf State blockt): Exit 2, identisch mit der Variante ohne Apostroph (hook_utils.py:317).
Status: CONFIRMED

AC-4 (harmlose Befehle bleiben erlaubt): cd in den Workflow-Ordner allein, mit ls, mit cat auf den Namen, git log nach out.txt, git status 2>&1, git status | tee out.txt, Umleitung nach dev-null (auch &>, 1>&2), git status;>out.txt alle Exit 0. Fehlalarm-Gegenproben: cd in .claude/worktrees/x mit cat package.json, mit Schreiben nach out.json bzw. package.json, cd .claude/hooks mit Schreiben nach a.json, cd .claude/worktrees/x/.claude/hooks, pushd im Worktree, gh pr create --body mit # und State-Pfad im Text: alle Exit 0.
Status: CONFIRMED

AC-5 (kein Kommentar bleibt unveraendert): git log --grep=#1431, echo $# ${#x}, Commit-Message mit #123 (blockt als Commit), fix#123, echo "it's" nach out.txt, git status # don't panic verhalten sich wie vorher.
Status: CONFIRMED

AC-6 (unbalancierte Quotes fail-open): Commit mit offenem Quote und # blockt weiterhin als Commit (Befehl unveraendert zurueck, hook_utils.py:317, Rueckgabe command bei offenem quote).
Status: CONFIRMED

Vier Erstbefunde: F001 (cd in Worktree-Ordner mit package.json) behoben, Exit 0. F002 (status;>state) behoben, Exit 2. F003 (Kommentar endet auf Backslash): Kommentarzeile mit Backslash gefolgt von git commit blockt als Commit, korrekt (Kommentar endet am Zeilenende). F004 (# hinter Klammer zu) behoben.
Status: CONFIRMED

### Runde 2

Nachbohren an den staerksten Verdachtsstellen (Fixes selbst).

Commit-Erkennung bleibt (Gegenprobe d): git commit -m x, mit Kommentar dahinter, hinter Kommentarzeile, mit Zeilenfortsetzung zwischen git und commit, hinter echo a;# c, hinter Kommentar mit Fortsetzung, commit -F - mit Heredoc und # im Text, cd .claude/worktrees/x && commit: alle Exit 2 (Adversary verdict). git commit-tree bleibt Exit 0.
Status: CONFIRMED

Trenner-Praefixe: &&>, &>, &>>, >|, 2>, ;>, ;;>, ;(>, |> sowie echte Ziele dev-null, &1, 1>&2 sind korrekt getrennt (blocken bzw. erlaubt).
Status: CONFIRMED

Zeilenfortsetzung: status mit Backslash-Newline vor > out.txt Exit 0, vor > state Exit 2, Kommentar mit Backslash gefolgt von >out.txt Exit 0, Kombination mit Kommentar und ;> auf state Exit 2.
Status: CONFIRMED

Restluecken (alle LOW, ungewoehnlich, ausserhalb des Alltags):

F001: severity LOW, category edge_case. description: Direkt angehaengte Umleitung nach cd in den Workflow-Ordner (echo x>w.json ohne Leerzeichen) liefert Exit 0, weil der Name im Token x>w.json haengt und das Datei-Token-Muster nicht greift. evidence: core/hooks/bash_gate.py:312 (_cd_context_protected nutzt _matches_file_token auf Segmenten). Repro: cd .claude/workflows && echo x>w.json in der Sandbox. remediation: Token an > aufspalten bevor gematcht wird.

F002: severity LOW, category edge_case. description: cd .claude/workflows;>w.json und cd .claude/workflows&&>w.json (nackte Umleitung ohne Befehl, ohne Leerzeichen) Exit 0. evidence: core/hooks/bash_gate.py:312. remediation: _strip_leading_separators auch in _cd_context_protected anwenden.

F003: severity LOW, category edge_case. description: Pfadnormalisierung fehlt in _cd_into_claude: cd .claude/./workflows, .claude/hooks/../workflows, .claude/worktrees/../workflows werden nicht erkannt (Exit 0). evidence: core/hooks/bash_gate.py:294 (nur Split an Schraegstrich). remediation: posixpath.normpath vor dem Split. Vorsaetzliche Verschleierung, Known Limitation.

Alltagsnaehe: Keine der Restluecken tritt beim versehentlichen Arbeiten auf; die haeufigen Formen sind abgedeckt. Hinweis: Ein Heredoc-Body, der einen State-Pfad nennt, blockt weiter; das ist Bestandsverhalten ohne Bezug zum Diff.

Gesamt: 7/7 ACs belegt (AC-7: 94 passed, 0 failed in den fuenf genannten Suites).
Status: CONFIRMED

VERDICT: VERIFIED

## Geprüfte Dateien

- sha256:a29c3b940bf27f085fe7959b8be79437e320968daa000d5ab615d93b1b83b527  core/hooks/bash_gate.py
- sha256:1738a25c4df0d9e7c6c5036adbd7b2b7e7e59b9b8b250efce21934b1db836794  core/hooks/hook_utils.py
