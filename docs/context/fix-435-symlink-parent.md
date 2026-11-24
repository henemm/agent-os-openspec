# Context: fix-435-symlink-parent

## Request Summary
Issue #435 (Folge aus #417, Adversary F001, Teil von Epic #429): Prüfung 1c in `bash_gate.py`
(Worktree-Sitzung schreibt per Bash in den Haupt-Ordner) löst jedes Schreibziel per `Path.resolve()`
auf. Zielt ein Befehl auf einen Symlink im eigenen Worktree, der in den Haupt-Ordner zeigt
(z. B. `node_modules`), landet das aufgelöste Ziel im Haupt-Ordner → falscher Block. Ausweg heute
nur `override`. Gewünscht: bei Befehlen, die den Link selbst bearbeiten, nur den Elternpfad auflösen.

## Related Files
| File | Relevance |
|------|-----------|
| `core/hooks/bash_gate.py:1266` `_writes_main_repo` | Zu ändern: `(b / t).resolve()` je Ziel |
| `core/hooks/bash_gate.py:592` `_segment_write_targets` | liefert `(bases, targets, seg)` je Schreib-Segment (geteilt mit 1b) |
| `core/hooks/bash_gate.py:552` `_CONFIG_WRITERS` | Ziel-Extraktion je Befehl (cp/install/ln/mv/rm/unlink/tee/truncate/touch/sed/perl/git/dd/yq) + Umleitungen |
| `core/hooks/bash_gate.py:610` `_dir_removal_targets` | Vorbild: Quellen von `rm`/`mv`/`git rm|mv|checkout|restore` (#473 F002) |
| `core/hooks/bash_gate.py:630` `_lexical_path` | Vorbild/Wiederverwendung: nur Elternordner aufgelöst, letzter Bestandteil roh (#473 F002) |
| `core/hooks/bash_gate.py:1900` Abschnitt 1c | Aufrufer, Block-Meldung, Override |
| `tests/test_bash_gate_main_write_417.py` | Bestehende Tests 1c (Subprozess-Gate, `_worktree_sandbox`, `_expect`) |
| `docs/specs/fix-417-bash-main-write.md` | Ursprungs-Spec; Punkt 3 „resolve() damit Symlinks erfasst sind“ |

## Existing Patterns
- #473 F002 hat für 1b dasselbe Problem gelöst: `_lexical_path(base, token)` = normpath/abspath,
  `realpath(dirname)` + `basename` → `rm link` trifft den Link, nicht dessen Ziel.
- Tests laufen das echte Gate als Subprozess in einer Wegwerf-Sandbox (`main` + `.claude/worktrees/<name>`).
- Fail-open bei nicht auflösbaren Zielen (`$`, Backtick, Glob) und Exceptions.

## Befehls-Semantik (entscheidend für die Spec)
Bearbeitet den Link selbst (Elternpfad reicht):
- `rm link`, `unlink link`, `rm -f link` → entfernt nur den Link.
- `mv link x` → Quelle wird als Link umbenannt.
- `git rm|checkout|restore link`, Quellen von `git mv` → Link im Index/Worktree.
- `touch -h`/`--no-dereference link`, `ln -sfn`/`-T` auf bestehenden Link → ersetzt den Link.

Folgt dem Link (Auflösung muss bleiben, sonst Lücke):
- Umleitung `> link`, `cp/install … link`, `tee`, `truncate`, `dd of=`, `sed -i`/`perl -i` (konservativ).
- `touch link` ohne `-h`: ändert Zeitstempel des Ziels bzw. legt bei hängendem Link das Ziel an.
- `ln -sf X link` ohne `-n`/`-T`, wenn `link` auf einen Ordner zeigt: legt in den Ziel-Ordner.
- `mv x link` (Ziel) auf Ordner-Link ohne `-T`: verschiebt in den Ziel-Ordner.
- **Abschließender Schrägstrich:** `rm -r link/` bzw. `link/.` wirkt auf den Inhalt des Ziels;
  `normpath` streicht den Slash → muss gesondert behandelt werden (bleibt aufgelöst).

## Dependencies
- Upstream: `_segment_write_targets`, `_command_args`, `_split_redirects`, `_positional`, `_cd_bases`.
- Downstream: nur Abschnitt 1c (`main_hit`). 1b (`_writes_effective_config`) teilt die Zielerkennung,
  muss unverändert bleiben (eigene Link-Behandlung über `_removes_config_dir`).

## Existing Specs
- `docs/specs/fix-417-bash-main-write.md` — 1c-Grundlage
- #473 (F002) — `_lexical_path` für 1b

## Risks & Considerations
- Lockerung eines Schutzes: jede Befehlsform, die durch den Link schreibt, muss weiter blocken
  (Adversary-Ziel). Im Zweifel aufgelöst lassen.
- Abschließender Slash / `link/.` / `link/sub` (Elternteil ist der Link → durch `realpath(dirname)` korrekt aufgelöst).
- `mv` liefert Quellen und Ziel aus `_CONFIG_WRITERS` gemischt; für 1c braucht es eine Trennung
  Quelle (lexikalisch) vs. Ziel (aufgelöst) — `_dir_removal_targets` liefert die Quellen bereits.
- Risiko-Stufe Adversary: hoch (Gate-Code) → 2 Dialog-Runden.

## Analysis

### Type
Bug (Fehlalarm eines Schutzes). Tiefe nach Intake-Summe 2: Kontext + Analyse in einem Durchgang,
Nachstellung und Semantik-Prüfung direkt im Hauptkontext (keine Teilagenten nötig).

### Reproduktion (2026-11-24, echtes Gate als Subprozess, Sandbox `main/.claude/worktrees/wt`,
`wt/node_modules -> ../../../node_modules`)
Alle elf Befehle `rc=2`: `rm L`, `unlink L`, `mv L nm.bak`, `rm -f L`, `touch -h L`,
`ln -sfn … L`, `git rm L` (Fehlalarm) sowie `rm -r L/`, `echo x > L/a`, `touch L`,
`cp /etc/hosts L` (zu Recht). Ursache: `bash_gate.py:1285` `(b / t).resolve()` folgt dem Link.

### Semantik geprüft (GNU coreutils, Scratch-Verzeichnis)
| Befehl | wirkt auf | Folge für 1c |
|---|---|---|
| `rm [-rf] L`, `unlink L` | Link | lexikalisch |
| `mv L x` (Quelle) | Link | lexikalisch |
| `mv x L` (Ziel, Ordner-Link) | Inhalt des Ziels (`t/f`) | aufgelöst |
| `mv -T x L` | ersetzt Link | lexikalisch |
| `ln -sf x L` ohne `-n` | legt `t/x` an | aufgelöst |
| `ln -sfn x L` / `-T` | ersetzt Link | lexikalisch |
| `touch L` | Ziel (legt bei hängendem Link die Zieldatei an) | aufgelöst |
| `touch -h L` | Link | lexikalisch |
| `rm -r L/` | GNU: verweigert; BSD/macOS: löscht Inhalt des Ziels | aufgelöst |
| `L/.`, `L/..` | Ziel | aufgelöst |
| `git rm/checkout/restore L`, Quellen von `git mv` | Link im Index/Worktree | lexikalisch |

### Affected Files (with changes)
| File | Change Type | Description |
|------|-------------|-------------|
| `core/hooks/bash_gate.py` | MODIFY | `_writes_main_repo`: Link-Rollen je Segment bestimmen, diese per `_lexical_path` prüfen, alles andere wie bisher per `resolve()` |
| `tests/test_bash_gate_symlink_parent_435.py` | CREATE | Subprozess-Tests: Fehlalarm weg, Durchschreib-Fälle blocken weiter |
| `CHANGELOG.md`, `.claude-plugin/plugin.json` (+ Versionsstellen) | MODIFY | Eintrag + Patch-Version |
| `docs/specs/fix-435-symlink-parent.md`, `docs/briefings/fix-435-symlink-parent.md` | CREATE | Spec, PO-Briefing |

### Scope Assessment
- Code-Dateien: 1 (+1 Testdatei)
- Estimated LoC: +40/-3 Code, ~+150 Test
- Risk Level: MEDIUM (Lockerung eines Schutzes; Adversary-Stufe hoch → 2 Runden)

### Technical Approach (Empfehlung)
Neue Hilfsfunktion `_link_acting_targets(seg) -> list` (Tokens, die den Link selbst bearbeiten):
- `rm`, `unlink`: alle Positionsargumente; `mv`/`git rm|mv|checkout|restore`: Quellen über das
  bestehende `_dir_removal_targets`; `mv` Ziel nur mit `-T`/`--no-target-directory`;
- `touch` nur mit `-h`/`--no-dereference` (auch in kombinierten Kurzflags);
- `ln` Ziel nur mit `-n`/`-T`/`--no-dereference`/`--no-target-directory` (auch `-sfn`).
Ein Token wird nur lexikalisch geprüft, wenn (a) es in dieser Link-Liste steht, (b) es im selben
Segment nicht zusätzlich Umleitungsziel oder sonstiges (folgendes) Schreibziel ist und (c) sein letzter
Bestandteil ein normaler Name ist (kein abschließendes `/`, nicht `.`/`..`). Lexikalisch =
`_lexical_path(b, t)` (wie #473 F002); Vergleich gegen `main_dir`/`own` unverändert. Alle übrigen Ziele:
`resolve()` wie bisher. 1b bleibt unverändert.

### Verworfene Alternativen
- **Alles lexikalisch prüfen, Link-Folgen gesondert erkennen:** kehrt die Sicherheitsrichtung um
  (neuer Befehl in `_CONFIG_WRITERS` wäre standardmäßig offen). Verworfen.
- **Jeder Link im eigenen Worktree ist frei:** öffnet `echo > L/a`, `cp x L`, `touch L`. Verworfen.
- **Nur Doku/override belassen:** Issue-Ziel verfehlt.

### Dependencies
`_segment_write_targets`, `_split_redirects`, `_command_args`, `_positional`, `_dir_removal_targets`,
`_lexical_path`. Nur Abschnitt 1c ruft `_writes_main_repo`.

### Open Questions
- keine (technische Designfragen entscheidet der Tech Lead; kein Produktkonflikt)
