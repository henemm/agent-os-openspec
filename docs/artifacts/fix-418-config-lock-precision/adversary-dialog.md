# Adversary Dialog — fix-418-config-lock-precision
Spec: docs/specs/fix-418-config-lock-precision.md
Datum: 2026-10-10 14:10

## Checkliste
- [x] **Input:** Ein Bash-Befehl durch `bash_gate.py`, mit oder ohne aktiven Workflow.
- [x] **Output:** Befehle, die die wirksame Config beschreiben, ersetzen, entfernen oder verlinken, enden mit Exit 2 und der bestehenden Config-Meldung mit Hinweis auf „override“. Befehle, die sie nur lesen, enden mit Exit 0.
- [x] **Side effects:** Keine neuen Subprozesse, keine neuen Abhängigkeiten, keine geänderten AppStorage-/Config-Keys. Prüfung 3a/3b verhält sich unverändert.
- [x] **AC-1:** Given eine Projektwurzel mit wirksamer Config / When ein lesender Befehl mit Umleitung oder Kopierziel läuft (`git diff openspec.yaml > x.patch`, `grep a openspec.yaml > out.txt`, `cat openspec.yaml > copy`, `cp openspec.yaml backup.yaml`, `cp -t backup/ openspec.yaml`, `cat openspec.yaml | tee copy`) / Then bleibt das Gate bei Exit 0, weil die Config nur Lese-Quelle ist
- [x] **AC-2:** Given eine Projektwurzel mit wirksamer Config / When `sed --in-place`, `sed -ni`, `sed -i ''`, `perl -pi -e` oder `perl -i.bak -pe` die Config trifft / Then blockt das Gate mit Exit 2 und nennt „override“ in der Meldung
- [x] **AC-3:** Given eine Projektwurzel mit wirksamer Config / When `echo x >| cfg`, `echo x &> cfg`, `git checkout -- cfg`, `git restore cfg`, `ln -sf x cfg`, `install x cfg`, `dd if=x of=cfg`, `yq -i .a=1 cfg` oder `cp x -t DIR` (Ziel `DIR/<name>` = Config) läuft / Then blockt das Gate mit Exit 2
- [x] **AC-4:** Given eine Projektwurzel mit wirksamer Config / When `cd docs && sed -i s/a/b/ ../openspec.yaml` oder `cd docs; echo x > ../openspec.yaml` läuft, und in einer Worktree-Sitzung `cd ../../.. && sed -i s/a/b/ openspec.yaml` (Datei im Hauptordner) / Then blockt das Gate mit Exit 2
- [x] **AC-5:** Given eine Projektwurzel mit wirksamer Config / When `cd docs && sed -i s/a/b/ openspec.yaml` läuft (trifft `docs/openspec.yaml`, nicht die wirksame Config) / Then bleibt das Gate bei Exit 0 (Spiegelbild von Teil C)
- [x] **AC-6:** Given eine Projektwurzel mit wirksamer Config / When die Gegenprobe läuft (`echo x > cfg`, `echo x >> cfg`, `sed -i s/a/b/ cfg`, `sed -i.bak s/a/b/ cfg`, `cp x cfg`, `mv x cfg`, `mv cfg old`, `cat x | tee cfg`, `truncate -s0 cfg`, `rm cfg`) / Then blockt das Gate weiterhin jeden dieser Befehle mit Exit 2
- [x] **AC-7:** Given eine Worktree-Sitzung / When `sed -i s/a/b/ openspec.yaml` die Worktree-Kopie trifft (nicht die aufgelöste Datei im Hauptordner) / Then bleibt das Gate bei Exit 0; und Given ein gültiger Override-Token / When ein Schreibbefehl auf die wirksame Config läuft / Then lässt das Gate ihn mit Exit 0 durch
- [x] **AC-8:** Given ein nicht zerlegbarer Befehl (offene Quote) oder ein nicht auflösbares `cd`-Ziel (`cd $X && sed -i s/a/b/ openspec.yaml`) / When das Gate läuft / Then stürzt es nicht ab, die Zielextraktion ist fail-open, und das Ergebnis entspricht dem heutigen Verhalten (kein neuer Block-Grund); die nicht abgedeckten Formen `ex -s cfg`, `patch cfg x.diff`, `git apply x.diff` bleiben Exit 0 (dokumentierte Known Limitation)
- [x] **AC-9:** Given der bestehende Testbestand / When `tests/test_bash_gate_state_integrity_410.py` und das Regressionsnetz `tests/test_bash_gate*` laufen / Then bleiben sie grün (insbesondere `test_wirksame_config_schreiben_blockt`, `test_config_schutz_ohne_aktiven_workflow`, `test_override_gibt_config_frei_aber_nicht_state`, `test_worktree_kopie_lesen_und_app_config_bleiben_frei`)

## Dialog

### Runde 1
**Adversary:** Nachprüfung der Lauf-1-Befunde per Differenzlauf (neues Gate gegen Gate von HEAD, Temp-Projekt mit openspec.yaml und docs/).
- F001 (git rm/mv): `git rm openspec.yaml`, `git rm -f openspec.yaml`, `git rm -- openspec.yaml`, `git mv openspec.yaml x`, `git mv x openspec.yaml`, `git mv -f openspec.yaml y`: alle Exit 2 (war in Lauf 1 Exit 0). BEHOBEN.
- F002 (popd): `cd docs && popd && sed -i s/a/b/ openspec.yaml` Exit 2, `cd docs && popd && sed -i s/a/b/ ../openspec.yaml` Exit 2 (HEAD: 0). BEHOBEN.
- Neue Fehlalarme geprüft, alle Exit 0: `git rm --cached build/x`, `git mv a b`, `git mv --force a b`, `git rm -r docs/old`, `git rm -r --cached .`, `git rm --cached -r docs`, `git mv docs/a docs/b`, `git status`, `popd` allein, `cd docs && popd && cat openspec.yaml`.
- Lese-Befehle (AC-1) Exit 0: `git diff openspec.yaml > x.patch`, `grep a openspec.yaml > out.txt`, `cat openspec.yaml > copy`, `cp openspec.yaml backup.yaml`, `cp -t backup/ openspec.yaml`, `cat openspec.yaml | tee copy`, `sed -n 1p openspec.yaml`, `cp openspec.yaml x 2>/dev/null`.
- Schreib-Befehle (AC-2/3) Exit 2: `sed --in-place`, `sed -ni`, `sed -i ''`, `perl -pi -e`, `perl -i.bak -pe`, `>|`, `&>`, `git checkout -- cfg`, `git restore cfg`, `ln -sf x cfg`, `install x cfg`, `dd of=cfg`, `yq -i`. `cp x -t .` Exit 0, weil das Ziel `./x` ist, nicht die Config.
- Gegenprobe (AC-6): alle 10 Formen Exit 2 (gleich HEAD).
- cd-Kontext (AC-4/5): `cd docs && sed -i s/a/b/ ../openspec.yaml` Exit 2, `cd docs; echo x > ../openspec.yaml` Exit 2, `cd docs && sed -i s/a/b/ openspec.yaml` Exit 0, `cd docs && cd .. && sed -i … openspec.yaml` Exit 2, `pushd docs && sed -i … openspec.yaml` Exit 0.
- AC-8: `cd $X && sed -i … openspec.yaml` Exit 2 (wie HEAD, kein neuer Block-Grund). Offene Quote `echo "unterminated > openspec.yaml` Exit 0, kein Absturz. `ex -s`, `patch cfg x.diff`, `git apply x.diff` Exit 0 (Known Limitation).
- Beobachtung (kein Finding): `git -C docs rm openspec.yaml` Exit 2, wie HEAD. Es löst gegen cwd statt gegen -C auf. Das ist fail-closed und keine Regression.
**Implementierer:** n/a (gezielter Fix aus Lauf 1 liegt vor, in Runde 1 nachgeprüft).

### Runde 2
**Adversary:** Testsuiten und Randfälle erneut.
- `tests/test_bash_gate_config_lock_418.py`, `tests/test_bash_gate_state_integrity_410.py`, `tests/test_bash_gate_ln_state_407.py`: 30 passed, 0 failed.
- `pytest tests/ -k bash_gate`: 172 passed, 0 failed, 0 übersprungen (2282 deselected).
- Fail-open: `_writes_effective_config` fängt jede Exception und gibt False zurück (Z. 552 ff.). `popd` und nicht auflösbare Ziele (`$ \` * ? [`) behalten alte Basis und cwd, damit kein neuer Block-Grund entsteht.
- Side effects: Es gibt keine neuen Subprozesse oder Importe außer dem bestehenden `config_loader`. Die Prüfung ist eine reine Token-Analyse. 3a/3b sind unverändert (Regressionsnetz grün).
- AC-7: Der Override-Token-Zweig in Prüfung 1b (`and not _any_override_token()`, Z. 1150) bleibt erhalten; `test_override_gibt_config_frei_aber_nicht_state` ist grün. Die Worktree-Kopie löst auf eine andere Datei auf und bleibt frei.
**Implementierer:** n/a

Confirmation:
  AC: Input
  Code reference: core/hooks/bash_gate.py:1150
  Evidence: Prüfung 1b läuft unabhängig vom Workflow (vor allen Schnellwegen) auf den zerlegten Befehl.
  Status: CONFIRMED

Confirmation:
  AC: Output
  Code reference: core/hooks/bash_gate.py:552
  Evidence: `_writes_effective_config` gibt True nur bei echtem Schreibziel zurück; Block-Meldung mit „override“ bei Z. 1150 ff. Lesende Befehle Exit 0, schreibende Exit 2 (Differenzlauf).
  Status: CONFIRMED

Confirmation:
  AC: Side effects
  Code reference: core/hooks/bash_gate.py:525
  Evidence: Reine Token-Analyse ohne Subprozess; Regressionsnetz zu 3a/3b grün (172 passed).
  Status: CONFIRMED

Confirmation:
  AC: AC-1
  Code reference: core/hooks/bash_gate.py:437
  Evidence: `_copy_targets` liefert nur Ziel (letztes Argument bzw. `-t DIR/<name>`), `_split_redirects` (Z. 378) nimmt nur Umleitungsziele; die Quelle zählt nie. Alle 6 Formen Exit 0.
  Status: CONFIRMED

Confirmation:
  AC: AC-2
  Code reference: core/hooks/bash_gate.py:451
  Evidence: `_sed_targets` erkennt `--in-place`, `-ni`, `-i ''` (leere Tokens in Z. 525 ff. gefiltert), `_perl_targets` (Z. 485) erkennt `-pi`/`-i.bak`. Alle Exit 2.
  Status: CONFIRMED

Confirmation:
  AC: AC-3
  Code reference: core/hooks/bash_gate.py:513
  Evidence: `_CONFIG_WRITERS` deckt cp/install/ln/dd/yq/git ab; `_split_redirects` (Z. 378) deckt `>|` und `&>`; `_git_write_targets` (Z. 505) deckt checkout/restore. Alle Exit 2.
  Status: CONFIRMED

Confirmation:
  AC: AC-4
  Code reference: core/hooks/bash_gate.py:539
  Evidence: `_cd_bases` führt die Basis über cd/pushd nach; popd behält alte Basis und cwd. `cd docs && sed -i … ../openspec.yaml` und `cd docs; echo x > ../openspec.yaml` Exit 2, ebenso `cd docs && popd && sed -i … openspec.yaml` (F002 behoben).
  Status: CONFIRMED

Confirmation:
  AC: AC-5
  Code reference: core/hooks/bash_gate.py:552
  Evidence: Auflösung gegen die nachgeführte Basis: `cd docs && sed -i s/a/b/ openspec.yaml` trifft docs/openspec.yaml, Exit 0.
  Status: CONFIRMED

Confirmation:
  AC: AC-6
  Code reference: core/hooks/bash_gate.py:513
  Evidence: `_CONFIG_WRITERS` für mv/rm/tee/truncate und Umleitungen; alle 10 Gegenproben Exit 2. Zusätzlich `git rm`/`git mv` (Z. 505, F001 behoben) Exit 2.
  Status: CONFIRMED

Confirmation:
  AC: AC-7
  Code reference: core/hooks/bash_gate.py:1150
  Evidence: Block nur `and not _any_override_token()`; die Worktree-Kopie löst auf eine andere Datei auf als `find_config_file(find_project_root())` (Z. 552 ff.).
  Status: CONFIRMED

Confirmation:
  AC: AC-8
  Code reference: core/hooks/bash_gate.py:378
  Evidence: Offene Quote führt zu Exit 0 ohne Absturz; `cd $X` erhält alte Basis und cwd (Z. 539), Ergebnis wie HEAD. Alle Extraktionen laufen unter try/except fail-open (Z. 552 ff.). `ex -s`, `patch`, `git apply` Exit 0 (Known Limitation).
  Status: CONFIRMED

Confirmation:
  AC: AC-9
  Code reference: core/hooks/bash_gate.py:1150
  Evidence: 30 passed (418/410/407) und 172 passed (`-k bash_gate`), 0 failed, 0 übersprungen.
  Status: CONFIRMED

Nachprüfung Lauf-1-Befunde:
- F001 (MEDIUM, Regression, `git rm`/`git mv` openspec.yaml): BEHOBEN. Code reference: core/hooks/bash_gate.py:505. Alle Formen Exit 2, keine Fehlalarme bei `--cached build/x`, `git mv a b`, `-r docs/old`.
- F002 (LOW, `popd`): BEHOBEN. Code reference: core/hooks/bash_gate.py:539.

Offene Findings: keine.

## Herkunft der Vorbedingungen
kein Sprachprofil konfiguriert (`precondition_origins.default_lang`)

## Verdict
Tests: 30 passed + 172 passed, 0 failed, 0 übersprungen. Edge cases geprüft, keine gebrochen. Regressionen: keine. Checkliste: 12/12 bewiesen.

VERDICT: VERIFIED

## Geprüfte Dateien

- sha256:c3acf9ece3f48e9063056672c860e4642a5bc17fa70562ee09bb537b93115e20  core/hooks/bash_gate.py

## Prüfbasis

- base: 65a953df1450294a0047cfb3c7eda81946dcf619
- blob:4efbb3a429572aaa52f6ff807295ccb5f3e0411d  core/hooks/bash_gate.py
