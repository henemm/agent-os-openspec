---
description: Kurz-Alias für /agent-os-openspec:50-implement
allowed-tools: Bash(python3 -c *)
---
<!-- openspec-alias: do-not-treat-as-legacy-duplicate -->

/agent-os-openspec:50-implement $ARGUMENTS

Ist das Plugin agent-os-openspec geladen, gilt die Weiterleitung oben und der Block unten gibt nichts aus. Steht unten der Befehlstext, arbeite danach. Steht unten BEFEHLSTEXT FEHLT, beginne die Phase nicht und informiere den PO. Erscheint der Codeblock unten wörtlich statt seiner Ausgabe, führe ihn per Bash aus.

```!
python3 -c 'exec("import json, os, sys\nn = sys.argv[1]\ntry:\n    d = json.load(open(os.path.expanduser(\"~/.claude/plugins/installed_plugins.json\")))\n    ok = any(str(k).startswith(\"agent-os-openspec@\") for k in (d.get(\"plugins\") or {}))\nexcept Exception:\n    ok = False\nc = [os.environ.get(\"CLAUDE_PROJECT_DIR\") or \"\", os.getcwd()]\nc += [a for a in sys.argv[2:] if a and not a.startswith(\"${\")]\ns = lambda x: os.path.join(x, \"skills\", n, \"SKILL.md\")\nr = next((x for x in c if x and os.path.isfile(s(x))), None)\nif ok:\n    pass\nelif r:\n    print(\"Plugin agent-os-openspec ist in dieser Sitzung nicht geladen — der folgende Befehlstext gilt.\")\n    if os.path.isdir(os.path.join(r, \"core\", \"hooks\")):\n        print(\"export CLAUDE_PLUGIN_ROOT=\" + r)\n    for line in open(s(r), encoding=\"utf-8\").read().splitlines():\n        v = line.startswith(\"\\u2699 \")\n        print((\"Versionsmarker (als letzte Zeile ausgeben): \" + line) if v else line)\nelse:\n    print(\"BEFEHLSTEXT FEHLT: Plugin agent-os-openspec ist nicht geladen und unter \" + s(c[0] or c[1]) + \" liegt keine Kopie. Beginne die Phase NICHT und rate nicht — informiere den PO, dass der Befehlstext in dieser Sitzung fehlt.\")")' 50-implement "${CLAUDE_PROJECT_DIR}"
```
