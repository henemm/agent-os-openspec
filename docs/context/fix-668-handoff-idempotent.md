# Kontext: fix-668-handoff-idempotent (Issue #668, Epic #649)

## Ausgangslage

- `core/hooks/workflow.py::cmd_handoff` (#667) liefert Weg, nächstes Issue und Startauftrag.
- `STARTED=already` existiert nur im `--start`-Zweig (herdr). Nach `handoff --mark cloud`
  meldet ein erneutes `handoff` weiter `HANDOFF=cloud` samt Startauftrag; der Befehlstext
  (`core/commands/60-validate.md` / `70-deploy.md`, Absatz „Kette bei offenem Auftrag")
  ruft dann erneut `create_session` auf → doppelte Sitzung.
- `_handoff_mark` liest nicht neu und schreibt ohne Sperre (Lesen-Ändern-Schreiben über
  den beim Aufruf gelesenen Auftrag) → paralleles `queue`/`complete` kann überschrieben werden.
- Ergänzungskommentar: Wirft `_handoff_mark` nach erfolgreichem `herdr_bridge.start_session`,
  fängt der äußere `except` das und meldet `STARTED=no` → Befehlstext fällt auf inline zurück,
  zweite Sitzung entsteht.

## Betroffene Dateien

- `core/hooks/workflow.py` (`cmd_handoff`, `_handoff_mark`)
- `core/commands/60-validate.md`, `core/commands/70-deploy.md`, `core/commands/80-workflow.md`
- `skills/*` (generiert), `tests/test_handoff_667.py` bzw. neue `tests/test_handoff_668.py`

## Vorbilder

- Sperre: `herdr_bridge._pp_flock(path)` (max ~2 s, fail-open), genutzt in
  `workflow._store_issue_title`.
- Auftragspfad: `hook_utils.auftrag_path(root, auftrag_owner_key())`, Schreiben via
  `hook_utils.write_auftrag`.

## Risiken

- Hook-Code (hohes Risiko laut `adversary_dialog.py risk`), aber eng begrenzt; Bestandstests
  `tests/test_handoff_667.py` sichern das Bestandsverhalten.
