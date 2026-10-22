"""Map-first shell contract: no permanently occupied nav/drawers; legacy APIs intact.

These are DOM markup contracts, not visual/browser G3 acceptance.
"""
import unittest
from html.parser import HTMLParser
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from console.map_lab import router

ROOT = Path(__file__).resolve().parents[2]
PAGE = ROOT / "console" / "static" / "map_lab.html"
SCRIPT = ROOT / "console" / "static" / "map_lab.js"


class Ids(HTMLParser):
    def __init__(self):
        super().__init__()
        self.by_id = {}
    def handle_starttag(self, tag, attrs):
        data = dict(attrs)
        if "id" in data:
            if data["id"] in self.by_id:
                raise AssertionError("Duplicate HTML ID: " + data["id"])
            self.by_id[data["id"]] = (tag, data)


class MapFirstShellTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = PAGE.read_text(encoding="utf-8")
        cls.js = SCRIPT.read_text(encoding="utf-8")
        cls.doc = Ids()
        cls.doc.feed(cls.html)

    def test_default_state_is_single_map_with_collapsed_tools(self):
        for id_ in ("workspace-drawer", "inspector", "activity-panel", "app-dropdown"):
            self.assertIn("hidden", self.doc.by_id[id_][1])
        self.assertIn("map", self.doc.by_id)
        self.assertIn("workspace", self.html)
        self.assertNotIn('class="sidebar"', self.html)
        self.assertNotIn('data-page="projects"', self.html)
        self.assertNotIn('data-page="run"', self.html)

    def test_only_real_functions_have_prominent_controls(self):
        for id_ in ("resources-trigger", "region-trigger", "activity-trigger", "app-menu",
                    "draw", "viewport", "back", "prepare", "cancel", "header-prepare",
                    "close-inspector", "close-activity", "close-drawer", "open-region"):
            self.assertEqual(self.doc.by_id[id_][0], "button")
            self.assertIn('"' + id_ + '"', self.js)
        for field in ("west","south","east","north","progress","progressbar",
                      "progress-text","quality","selection","state","center",
                      "messages","map-error"):
            self.assertIn(field, self.doc.by_id)
        for name in ("buildings","roads","water","landuse","railways"):
            self.assertIn('data-layer="' + name + '"', self.html)
            self.assertIn("c-" + name, self.doc.by_id)

    def test_security_and_limitations_are_explicit(self):
        self.assertIn("仅供 GIS 预览",self.html)
        self.assertIn("未绑定仿真项目",self.html)
        self.assertIn("仿真",self.html)
        self.assertIn("非正式计算地图",self.html)
        self.assertIn("30 km²",self.html)

    def test_region_mismatch_prevents_wrong_package_preview(self):
        self.assertIn('job.bbox', self.js)
        self.assertIn('manifest.bbox_wgs84_lonlat', self.js)
        self.assertIn('swarmbalance_preview_package', self.js)
        self.assertIn('queryRenderedFeatures', self.js)
        self.assertIn('function hideDrawer()', self.js)

    def test_http_still_uses_original_gis_service_and_serves_shell(self):
        app = FastAPI()
        app.include_router(router)
        with TestClient(app) as client:
            resp = client.get("/map-lab")
            self.assertEqual(resp.status_code, 200)
            self.assertIn('id="workspace-drawer"', resp.text)
            self.assertIn('id="map"', resp.text)
            script = client.get("/map-lab/assets/map_lab.js")
            self.assertEqual(script.status_code, 200)
            self.assertIn("function setupShell()", script.text)
            self.assertFalse(client.get("/api/map-lab/status").json()["simulation_connected"])

if __name__ == "__main__":
    unittest.main()
