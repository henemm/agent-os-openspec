# Adversary Dialog — fix-410-state-integrity-gaps
Spec: docs/specs/fix-410-state-integrity-gaps.md
Datum: 2026-10-09 12:05

## Checkliste
- [x] **Input:** Ein Bash-Befehl durch `bash_gate.py`.
- [x] **Output:** Die unten genannten Schreibweisen enden mit Exit 2 und der bestehenden 3b-Meldung „Direct state file manipulation“ (Config: eigene Meldung mit Hinweis auf „override“). Lesende und unbeteiligte Befehle laufen mit Exit 0.
- [x] **Side effects:** Keine neuen Subprozesse, keine neuen Abhängigkeiten. State-Befehle ohne aktiven Workflow bleiben unverändert; nur die Config-Sperre gilt auch ohne Workflow.
- [x] **AC-1:** Given ein aktiver Workflow / When `cp .claude/workflows/fix* docs/x/`, `ln .claude/workflows/fix* docs/x/` oder `mv .claude/workflows/fix* docs/x/` läuft / Then blockt das Gate mit Exit 2
- [x] **AC-2:** Given ein aktiver Workflow / When `ls .claude/workflows/fix*` oder `cat .claude/workflows/x.json` läuft / Then bleibt Exit 0; zugleich blockt `cp docs/a.json .claude/workflows/b.json` weiter mit Exit 2 (Sanity)
- [x] **AC-3:** Given ein aktiver Workflow / When `cat .claude/workflows/fix* > docs/x` läuft / Then blockt das Gate mit Exit 2 (hinnehmbarer, dokumentierter Fehlalarm; Ausweg `workflow.py status`)
- [x] **AC-4:** Given eine Projektwurzel mit wirksamer Config (aufgelöst über `find_config_file(find_project_root())`) / When `echo x > <wirksame config>`, `sed -i s/a/b/ <wirksame config>` (auch `openspec.yaml`, relativer Pfad `../../config.yaml`, absoluter Pfad) läuft / Then blockt das Gate mit Exit 2 und nennt „override“ in der Meldung
- [x] **AC-5:** Given kein aktiver Workflow / When derselbe Schreibbefehl auf die wirksame Config läuft / Then blockt das Gate mit Exit 2 (Config-Schutz ist workflow-unabhängig)
- [x] **AC-6:** Given ein gültiger Override-Token / When ein Schreibbefehl auf die wirksame Config läuft / Then lässt das Gate ihn mit Exit 0 durch; ein Schreibbefehl auf Workflow-State bleibt trotz Token bei Exit 2
- [x] **AC-7:** Given eine Worktree-Sitzung / When `sed -i s/a/b/ config.yaml` die Worktree-Kopie trifft (nicht die aufgelöste Datei im Hauptordner), oder `cat config.yaml` und `grep enabled <main>/config.yaml` lesen, oder eine App-`config.yaml` im Root ohne Plugin-Block geschrieben wird / Then bleibt Exit 0
- [x] **AC-8:** Given ein aktiver Workflow / When `cp -r docs/w/. .claude/workflows/.`, `rsync -a docs/w/ .claude/workflows/.` oder ein Ordner-Token mit `/..` läuft / Then blockt das Gate mit Exit 2 (F001)
- [x] **AC-9:** Given ein aktiver Workflow / When `ln -s .claude//workflows d` läuft / Then blockt das Gate mit Exit 2 (F002)
- [x] **AC-10:** Given ein aktiver Workflow / When `cd .claude && ln -s workflows ../w` oder `pushd .claude; ln -s workflows ../w` läuft / Then blockt das Gate mit Exit 2 (F003)
- [x] **AC-11:** Given ein aktiver Workflow / When `cd .claude && ls workflows`, `cd .claude/worktrees/x && cp a b`, `ls .claude && rm docs/x` oder ein `workflow.py`-Aufruf läuft / Then bleibt Exit 0
- [x] **AC-12:** Given ein aktiver Workflow / When Freitext in `-m`/`--body` die Zeichenfolge „cp .claude/workflows/fix*“ enthält / Then bleibt Exit 0 (Freitext-Ausnahme)
- [x] **AC-13:** Given kein aktiver Workflow / When die State-Befehle aus AC-1, AC-8, AC-9 und AC-10 laufen / Then bleibt Exit 0 (State-Schutz weiter nur im Workflow, #407 AC-9)
- [x] **AC-14:** Given der bestehende Testbestand / When die Regressionstests laufen / Then bleiben sie grün

## Dialog

### Runde 1
**Adversary:** Suite aus dem Auftrag vollständig gelaufen: 134 passed, 0 failed, 0 skipped (Output: docs/artifacts/fix-410-state-integrity-gaps/adversary-test-output.txt). `git diff core/hooks/bash_gate.py` und Spec gelesen, dann das echte Gate als Subprozess gegen Wegwerf-Sandboxes (Workflow aktiv, ohne Workflow, ohne Config, `framework: enabled: false`) mit rund 50 State-Befehlen geprobt.

Exit 2 (Workflow aktiv): `cp|ln|mv|rm .claude/workflows/fix*`, `fi?`, `[a-z]*.json`, `*`, `cp -r .claude/workflows/ docs/`, in Anführungszeichen, mit `./`- und absolutem Präfix; `ln -s .claude/workflows/. d`, `ln -s .claude/workflows/.. d`, `ln -s .claude/ d`, `ln -s .claude/. d`, `ln -s .claude/../.claude/workflows d`; `cp -r docs/w/. .claude/workflows/.`, `rsync -a docs/w/ .claude/workflows/.`; cd-Kontext `cd .claude && ln -s workflows ../w`, `cd .claude/workflows && ln -s . ../w`, `cd .claude; cp -r workflows ../w`, `mv`, `rsync`, `sed -i x.json`, `cd .claude && cd workflows && rm x.json`; `cat .claude/workflows/fix* > docs/x` (dokumentierter Fehlalarm, AC-3).

Exit 0: `ls .claude/workflows/fix*`, `cat .claude/workflows/x.json`, `grep a .claude/workflows/fi*`, `cd .claude && ls workflows`, `cd .claude && cat workflows/x.json`, `cd .claude/worktrees/x && cp a b`, `cd .claude && ls workflows | wc -l`, `cd .claude && git status`, `ls -ln`, `echo .claude/workflows/fix* > /dev/null`; Freitext in `git commit -m "cp …fix*"` löst 3b nicht aus (es blockt nur das Adversary-Gate). Ohne Workflow bleiben alle vier State-Befehle bei Exit 0 (AC-13).

Umgehungen Teil 1 (Exit 0): `.claude//workflows/fix*`, `.claude/./workflows/fix*`, `.claude/workflows/../workflows/fix*`, `cd .claude && ln -s ./workflows ../w`, `tee .claude/workflows/x.txt` — Randfälle, siehe F004.
**Implementierer:** (nicht anwesend)

### Runde 2
**Adversary:** Gezielt an der Config-Sperre nachgebohrt.

Exit 2 mit „override“-Hinweis: `echo x >`, `>>`, `1>`, `echo x>openspec.yaml`, Heredoc mit `>`; `sed -i`, `sed -i ''`, `sed -i.bak`; `cp x openspec.yaml`, `mv`, `rm`, `truncate`, `tee`; `git show HEAD:openspec.yaml > openspec.yaml`; Pfadformen `./openspec.yaml`, `docs/../openspec.yaml`, absolut, über Symlink (`docs/lnk.yaml`, `docs/rootlnk/openspec.yaml`), im Worktree `../../../openspec.yaml`. Ohne Workflow und bei `framework: enabled: false` ebenfalls Exit 2.

Exit 0: `cat`, `grep`; `sed -i config.yaml` bei Worktree-Kopie und App-Config; Worktree `sed -i openspec.yaml` auf die Kopie; ohne jede Config; mit gültigem Override-Token `sed -i` auf die Config, während `cp docs/a.json .claude/workflows/b.json` weiter Exit 2 liefert (AC-6).

Fehlalarme (F001): `git diff openspec.yaml > x.patch`, `grep a ../../../openspec.yaml > out.txt`, `cat ../../../openspec.yaml > /tmp/…`, `cp openspec.yaml backup.yaml`. Durchrutscher (F002/F003): `sed --in-place`, `sed -ni`, `perl -pi -e`, `ex -s`, `dd of=`, `install x`, `patch`, `yq -i`, `git apply`, `>|`, `git checkout -- openspec.yaml`, `git restore openspec.yaml`, `ln -sf x <config>`; `cd docs && sed -i … ../openspec.yaml`; Variablen/Globs; `bash -c "sed -i … config.yaml"` (#416).

Gemeldete Punkte: (a) eigene Liste `PROTECTED_GLOB_PATTERNS` korrekt, wirkt nur mit `dirs=wf_active` und erfüllt AC-13; (b) Fehlalarm real, Klasse F001, Ausweg override; (c) bestätigt, vorsätzliche Umgehung, #416.
**Implementierer:** (nicht anwesend)

Confirmation:
  AC: Input
  Code reference: core/hooks/bash_gate.py:946
  Evidence: main() liest den Befehl aus CLAUDE_TOOL_INPUT bzw. stdin; alle Proben als echter Subprozess mit CLAUDE_PROJECT_DIR und cwd in Wegwerf-Sandboxes.
  Status: CONFIRMED

Confirmation:
  AC: Output
  Code reference: core/hooks/bash_gate.py:976
  Evidence: Geprüfte Schreibweisen enden mit Exit 2 und "Direct state file manipulation"; Config-Sperre mit eigener Meldung samt "override" (Z. 976-982); lesende Befehle Exit 0.
  Status: CONFIRMED

Confirmation:
  AC: Side effects
  Code reference: core/hooks/bash_gate.py:378
  Evidence: _writes_effective_config löst die Config lazy erst bei Schreib-Indikator auf, nur Path.resolve() und Token-Vergleich, kein Subprozess, keine neue Abhängigkeit; State-Prüfung ohne Workflow unverändert.
  Status: CONFIRMED

Confirmation:
  AC: AC-1
  Code reference: core/hooks/bash_gate.py:75
  Evidence: PROTECTED_GLOB_PATTERNS greift über _protected_outside_whitelist (Z. 271-272); cp, ln, mv, rm auf .claude/workflows/fix* Exit 2.
  Status: CONFIRMED

Confirmation:
  AC: AC-2
  Code reference: core/hooks/bash_gate.py:75
  Evidence: ls .claude/workflows/fix*, cat .claude/workflows/x.json, grep a …/fi* Exit 0; cp docs/a.json .claude/workflows/b.json Exit 2.
  Status: CONFIRMED

Confirmation:
  AC: AC-3
  Code reference: core/hooks/bash_gate.py:272
  Evidence: cat .claude/workflows/fix* > docs/x Exit 2 (dokumentierter Fehlalarm).
  Status: CONFIRMED

Confirmation:
  AC: AC-4
  Code reference: core/hooks/bash_gate.py:378
  Evidence: echo x >, sed -i, cp auf openspec.yaml und config.yaml Exit 2 mit "override"; relativ, absolut, ../, Symlink, aus Worktree auf Hauptordner (../../../openspec.yaml); test_wirksame_config_schreiben_blockt grün.
  Status: CONFIRMED

Confirmation:
  AC: AC-5
  Code reference: core/hooks/bash_gate.py:976
  Evidence: Block steht vor der Workflow-Prüfung; ohne aktiven Workflow sed -i und echo > auf die Config Exit 2.
  Status: CONFIRMED

Confirmation:
  AC: AC-6
  Code reference: core/hooks/bash_gate.py:977
  Evidence: Mit gültigem Override-Token sed -i auf die Config Exit 0; cp docs/a.json .claude/workflows/b.json bleibt Exit 2.
  Status: CONFIRMED

Confirmation:
  AC: AC-7
  Code reference: core/hooks/bash_gate.py:378
  Evidence: Echter Worktree: sed -i auf Worktree-Kopie Exit 0; cat/grep auf wirksame Datei Exit 0; App-config.yaml ohne Plugin-Block Exit 0.
  Status: CONFIRMED

Confirmation:
  AC: AC-8
  Code reference: core/hooks/bash_gate.py:70
  Evidence: cp -r docs/w/. .claude/workflows/., rsync -a docs/w/ .claude/workflows/., ln -s … .claude/workflows/.. Exit 2.
  Status: CONFIRMED

Confirmation:
  AC: AC-9
  Code reference: core/hooks/bash_gate.py:70
  Evidence: ln -s .claude//workflows d Exit 2 (Muster /+); ohne Workflow Exit 0.
  Status: CONFIRMED

Confirmation:
  AC: AC-10
  Code reference: core/hooks/bash_gate.py:362
  Evidence: cd .claude && ln -s workflows ../w, cd .claude/workflows && ln -s . ../w, cd .claude; cp -r workflows ../w Exit 2; Aufruf in Z. 1053; pushd im Testmodul.
  Status: CONFIRMED

Confirmation:
  AC: AC-11
  Code reference: core/hooks/bash_gate.py:362
  Evidence: cd .claude && ls workflows, cd .claude/worktrees/x && cp a b, cd .claude && git status, cd .claude && ls workflows | wc -l Exit 0; ls .claude && rm docs/x und workflow.py im grünen Test.
  Status: CONFIRMED

Confirmation:
  AC: AC-12
  Code reference: core/hooks/bash_gate.py:272
  Evidence: git commit -m "cp .claude/workflows/fix* x" löst 3b nicht aus; Freitext-Test grün.
  Status: CONFIRMED

Confirmation:
  AC: AC-13
  Code reference: core/hooks/bash_gate.py:1053
  Evidence: Ohne Workflow cp …fix*, rsync …/., ln -s .claude//workflows d, cd .claude && ln -s workflows ../w jeweils Exit 0; Glob-Muster und cd-Zweig nur unter wf_active.
  Status: CONFIRMED

Confirmation:
  AC: AC-14
  Code reference: core/hooks/bash_gate.py:272
  Evidence: Acht Regressionsdateien plus neue Datei: 134 passed, 0 failed (adversary-test-output.txt).
  Status: CONFIRMED

Finding:
  ID: F001
  Severity: MEDIUM
  Category: edge_case
  Code reference: core/hooks/bash_gate.py:378
  Description: _writes_effective_config blockt, sobald ein Segment irgendeinen Schreib-Indikator hat (auch Umleitung auf fremde Datei) und irgendein Argument auf die Config zeigt: git diff openspec.yaml > x.patch, grep a <config> > out.txt, cat <config> > copy, cp openspec.yaml backup.yaml blocken (Exit 2).
  Spec requirement: Implementation Details Punkt 4 — "Lesen (cat, grep) bleibt frei"
  Conflict: Lesen der Config mit Umleitung auf andere Datei blockt; nicht in Known Limitations. Ausweg override.
  Remediation: Nur Umleitungsziele bzw. letztes Argument bei cp/mv mit der Config vergleichen, oder als Known Limitation benennen.

Finding:
  ID: F002
  Severity: MEDIUM
  Category: edge_case
  Code reference: core/hooks/bash_gate.py:496
  Description: Schreib-Indikatoren erfassen sed --in-place, sed -ni, perl -pi -e, ex -s, dd of=, install, patch, yq -i, git apply, git checkout -- <config>, git restore <config>, >| und ln -sf x <config> nicht (Exit 0).
  Spec requirement: AC-4 — sed -i/echo > auf die wirksame Config blocken; Known Limitations — nur versehentlich auslösbare Schreibweisen
  Conflict: sed --in-place ist die GNU-Langform von sed -i und eher versehentlich auslösbar.
  Remediation: --in-place, -ni, perl -pi, >| in die Indikatoren aufnehmen, sonst Known Limitation.

Finding:
  ID: F003
  Severity: LOW
  Category: edge_case
  Code reference: core/hooks/bash_gate.py:976
  Description: Config-Sperre wertet Path.cwd() aus und ignoriert cd im selben Befehl: cd docs && sed -i … ../openspec.yaml und im Worktree cd ../../.. && sed -i … openspec.yaml Exit 0.
  Spec requirement: AC-4 — relative und absolute Pfadform
  Conflict: Relative Pfadform nach cd im Befehl wird nicht erkannt.
  Remediation: Einfache cd-Segmente nachführen oder Known Limitation (#416).

Finding:
  ID: F004
  Severity: LOW
  Category: edge_case
  Code reference: core/hooks/bash_gate.py:75
  Description: Glob-Muster und _dir_token_in_cd_context kennen // und /./ in Kombination mit Glob nicht: cp .claude//workflows/fix* docs/, cp .claude/./workflows/fix* docs/, cp .claude/workflows/../workflows/fix* docs/, cd .claude && ln -s ./workflows ../w Exit 0.
  Spec requirement: AC-9 verlangt nur ln -s .claude//workflows d; Known Limitations Textumgehung
  Conflict: Nicht ausdrücklich verlangt; gleiche Klasse wie F002 aus #407.
  Remediation: Known Limitation oder os.path.normpath vor dem Musterabgleich.

## Herkunft der Vorbedingungen

kein Sprachprofil konfiguriert (`precondition_origins.default_lang`)

## Verdict

VERDICT: VERIFIED
Alle 17 Punkte sind belegt: 134 Tests grün (0 failed, 0 skipped), die Spec-Zielbefehle liefen am echten Gate wie vorgesehen (AC-1 bis AC-13 per Subprozess-Probe, Input, Output und Side effects per Codepfad). Die Findings sind Fehlalarme oder Umgehungen außerhalb der Spec-Befehlsliste; kein Finding verletzt ein Akzeptanzkriterium. F001 und F002 (MEDIUM) gehen als Folgearbeit in ein eigenes Ticket, F003/F004 zur Prüfung an der Quelle (#416).

## Geprüfte Dateien

- sha256:aa4d9744eb2aff0fd6483dd265324630faacfb25c8f0b82a9ed73580370f4b05  core/hooks/bash_gate.py

## Prüfbasis

- base: 3dbf84e85b60c1f36a47c0e89a1f9661757b6fe1
- blob:dc133680ea12c5d5728dc821f00af2cbbaf9dc08  core/hooks/bash_gate.py
