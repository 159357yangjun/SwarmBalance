from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
for p in (str(ROOT), str(FRONTEND)):
    if p not in sys.path:
        sys.path.insert(0, p)

from console import _preflight

_preflight.require("shapely", gated_in="console/test_portable_runtime.py")

from console.capabilities import runtime_capabilities
from tools.osm import _height_from_tags, _load_map_data_fallback, _utm_epsg


class PortableRuntimeTests(unittest.TestCase):
    def test_utm_zone_for_project_map(self):
        self.assertEqual(_utm_epsg(121.52, 31.28), 32651)

    def test_height_parsing(self):
        self.assertEqual(_height_from_tags({"height": "24 m"}), 24.0)
        self.assertEqual(_height_from_tags({"building:levels": "8"}), 24.0)
        self.assertIsNone(_height_from_tags({"building": "yes"}))

    def test_lightweight_osm_parser(self):
        xml = '''<?xml version="1.0" encoding="UTF-8"?>
<osm version="0.6">
 <bounds minlat="31.28" minlon="121.51" maxlat="31.29" maxlon="121.52"/>
 <node id="1" lat="31.281" lon="121.511"/><node id="2" lat="31.281" lon="121.512"/>
 <node id="3" lat="31.282" lon="121.512"/><node id="4" lat="31.282" lon="121.511"/>
 <way id="10"><nd ref="1"/><nd ref="2"/><nd ref="3"/><nd ref="4"/><nd ref="1"/>
   <tag k="building" v="yes"/><tag k="building:levels" v="10"/><tag k="name" v="Test Tower"/>
 </way>
 <way id="20"><nd ref="1"/><nd ref="2"/><tag k="highway" v="primary"/></way>
</osm>'''
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "tiny.osm"
            path.write_text(xml, encoding="utf-8")
            roads, buildings = _load_map_data_fallback(path)
        self.assertEqual(len(buildings), 1)
        self.assertAlmostEqual(buildings[0]["height"], 30.0)
        self.assertGreater(buildings[0]["geometry"].area, 0)
        self.assertEqual(len(roads["primary"]), 1)

    def test_capability_shape(self):
        caps = runtime_capabilities()
        self.assertIn("greedy", caps["available_algorithms"])
        self.assertIn(caps["map_backend"], {"osmnx", "builtin_xml", "unavailable"})


if __name__ == "__main__":
    unittest.main()
