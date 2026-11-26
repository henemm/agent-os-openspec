# Reset Workflow

Schließt den aktiven Workflow ab und archiviert ihn.

Hintergrund (Begründungen, Sonderfälle): `docs/befehle/99-reset.md` im Plugin-Ordner — nur bei Bedarf lesen.

## Wiedereinstieg via Issue-Nummer (nach `/clear`)

**Aufruf als `/99-reset #<N>`?** ZUERST Workflow auflösen und aktivieren — steht der falsche aktiv, trifft es fremde Arbeit:

```bash
python3 .claude/hooks/workflow.py find 42   # die übergebene Nummer
python3 .claude/hooks/workflow.py switch <NAME-aus-obigem-Output>
python3 .claude/hooks/workflow.py status
```

**Fasse dem User in 2 Sätzen zusammen, wo der Workflow steht** — vor `phase8_complete` den offenen Pflicht-Schritt nennen und nachfragen, bevor du abschließt. Ohne Argument gilt der aktive Workflow.

## Execute Reset

**Erst prüfen, ob überhaupt gebaut wurde** (`python3 .claude/hooks/workflow.py status`):

- Hat der Workflow das Feld `no_build_reason` (PO-Entscheidung „nichts bauen", per `workflow.py no-build --reason "..."`) **oder** wurde nie eine `spec_file` geschrieben, dann **nicht** `finish`, sondern:

  ```bash
  python3 .claude/hooks/workflow.py abandon --reason "<Begründung>"
  ```

  Begründung für `workflow.py abandon --reason` = Inhalt von `no_build_reason`; fehlt das Feld, den PO nach dem Grund fragen.
- Nur bei geschriebener Spec und abgeschlossener Arbeit:

```bash
python3 .claude/hooks/workflow.py finish
```

Danach neu starten mit `/10-context` bzw. `/20-analyse [feature/bug]`.
