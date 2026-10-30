"""Dashboard translations (2.7): i18n.js is loaded and translates UI strings, not content."""
from __future__ import annotations

import json
import shutil
import subprocess
import unittest

from dash_helpers import PACKAGE

ASSETS = PACKAGE / "server" / "assets"

PROBE = r"""
global.window = {};
global.location = { search: '?lang=de', href: 'http://localhost/' };
global.localStorage = { getItem() { return null; } };
global.navigator = { language: 'de-DE' };
const fs = require('fs');
eval(fs.readFileSync(process.argv[1] + '/i18n.js', 'utf8'));
const src = fs.readFileSync(process.argv[1] + '/app.js', 'utf8');
const start = src.indexOf('const LANG_KEY');
const end = src.indexOf('function setLanguage');
eval(src.slice(start, end).replace(/^const /gm, 'var ').replace(/^let /gm, 'var ') + '; global.tr = tr;');
const pack = window.POLIER_I18N.de;
const bad = Object.entries(pack.exact).filter(([key, value]) => typeof value !== 'string' || !value.trim()).map(([key]) => key);
const samples = JSON.parse(process.argv[2]);
console.log(JSON.stringify({
  bad: bad,
  patternsOk: pack.patterns.every(([re, rep]) => re instanceof RegExp && (typeof rep === 'string' || typeof rep === 'function')),
  out: samples.map((sample) => tr(sample))
}));
"""

SAMPLES = {
    "Board": "Board",
    "Your Work": "Meine Arbeit",
    "8 tasks · 4 stages · profile L · base main": "8 Aufgaben · 4 Phasen · Profil L · Basis main",
    "3 tasks done": "3 Aufgaben erledigt",
    "5m ago": "vor 5 Min.",
    "→ Verifying": "→ Prüfung",
    "Toolbar and stage in the UI kit": "Toolbar and stage in the UI kit",
    "The latest estimate": "The latest estimate",
    "python3 tools/gate.py --task ENG-01 --name build": "python3 tools/gate.py --task ENG-01 --name build",
    "transition refused ENG-01: no passing gate record for build, cpp-unit": "transition refused ENG-01: no passing gate record for build, cpp-unit",
    "Step 2 of 6": "Schritt 2 von 6",
    "claude found at /usr/bin/claude": "claude gefunden unter /usr/bin/claude",
    "claude auth login": "claude auth login",
}


class I18nTest(unittest.TestCase):
    def test_index_loads_translations_before_the_app(self) -> None:
        html = (ASSETS / "index.html").read_text(encoding="utf-8")
        self.assertLess(html.index("/assets/i18n.js"), html.index("/assets/app.js"))

    @unittest.skipUnless(shutil.which("node"), "node is needed to evaluate the translations")
    def test_german_translates_ui_and_leaves_content_alone(self) -> None:
        result = subprocess.run(["node", "-e", PROBE, str(ASSETS), json.dumps(list(SAMPLES))],
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        value = json.loads(result.stdout)
        self.assertEqual(value["bad"], [])
        self.assertTrue(value["patternsOk"])
        self.assertEqual(dict(zip(SAMPLES, value["out"])), SAMPLES)


if __name__ == "__main__":
    unittest.main()
