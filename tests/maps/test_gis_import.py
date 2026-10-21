"""Offline, deterministic coverage for region-select/import/cache GIS preview."""
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from console import gis_import as gis
from console import map_lab


class GISImportTests(unittest.TestCase):
    BBOX = [121.44, 41.93, 121.45, 41.94]

    @staticmethod
    def fake_data(tile):
        return {
            "osm3s": {"timestamp_osm_base": "2026-10-01T00:00:00Z"},
            "elements": [
                {"type": "way", "id": 13, "tags": {"building": "yes"},
                 "geometry": [{"lon": 121.443, "lat": 41.933},
                              {"lon": 121.445, "lat": 41.933},
                              {"lon": 121.445, "lat": 41.935},
                              {"lon": 121.443, "lat": 41.935},
                              {"lon": 121.443, "lat": 41.933}]},
                {"type": "way", "id": 14, "tags": {"highway": "residential"},
                 "geometry": [{"lon": 121.439, "lat": 41.932},
                              {"lon": 121.448, "lat": 41.939}]},
                {"type": "way", "id": 15, "tags": {"natural": "water"},
                 "geometry": [{"lon": 121.44, "lat": 41.936},
                              {"lon": 121.447, "lat": 41.936},
                              {"lon": 121.447, "lat": 41.94},
                              {"lon": 121.44, "lat": 41.936}]},
                {"type": "relation", "id": 400, "tags": {"type": "multipolygon"}}
            ]
        }

    def test_bbox_validation_and_explicit_area_limit(self):
        self.assertEqual(gis.validate_bbox(self.BBOX), self.BBOX)
        for bad in ([0, 0, 20, 20], [121.5, 42, 121.4, 43],
                    [float("nan"), 41, 122, 42], [True, 41, 122, 42],
                    [0, 90, 2, 91], [121, 41, 121, 42]):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                gis.validate_bbox(bad)

    def test_fosi_starting_bounds_are_accepted(self):
        default = [121.41216481,41.91485205,121.47245519,41.95986786]
        self.assertLessEqual(gis.bbox_area(default)[2], gis.MAX_AREA_KM2)
        self.assertLessEqual(len(gis.tile_bboxes(default)), gis.MAX_TILES)

    def test_safe_query_coordinates_and_small_tiles(self):
        query = gis.query_for(self.BBOX)
        self.assertIn("way[\"building\"](41.93,121.44,41.94,121.45)", query)
        self.assertIn("out body geom", query)
        tiles = gis.tile_bboxes(self.BBOX)
        self.assertTrue(tiles)
        self.assertTrue(all(gis.bbox_area(t)[2] <= gis.MAX_AREA_KM2 for t in tiles))

    def test_building_and_road_clip_without_inventing_height(self):
        groups, q = gis.convert_elements(self.fake_data(self.BBOX)["elements"], self.BBOX)
        self.assertEqual(len(groups["buildings"]), 1)
        self.assertEqual(len(groups["roads"]), 1)
        self.assertEqual(len(groups["water"]), 1)
        self.assertEqual(q["unknown_building_heights"], 1)
        self.assertFalse(q["relations_assembled"])
        self.assertFalse(q["simulation_safe"])
        road_pts = groups["roads"][0]["geometry"]["coordinates"]
        self.assertTrue(all(self.BBOX[0] <= x <= self.BBOX[2] for x, y in road_pts))

    def test_cached_tiles_frozen_package_and_repeat(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            calls, events = [], []
            def fake(tile):
                calls.append(tile)
                return self.fake_data(tile)
            progress = lambda *args: events.append(args)
            package, hits, total = gis.run_import(
                self.BBOX, progress, threading.Event(),
                root=root, fetcher=fake, pause=lambda _: None)
            self.assertEqual(hits, 0)
            self.assertEqual(len(calls), total)
            manifest = gis.manifest_for(package, root)
            self.assertEqual(manifest["feature_counts"]["buildings"], 1)
            self.assertFalse(manifest["quality"]["simulation_safe"])
            self.assertTrue((root / "packages" / package / "roads.geojson").exists())
            package2, hits2, total2 = gis.run_import(
                self.BBOX, progress, threading.Event(), root=root,
                fetcher=lambda _: self.fail("cached tile should be reused"),
                pause=lambda _: None)
            self.assertEqual(package, package2)
            self.assertEqual(hits2, total2)

    def test_cancel_before_network_request(self):
        with tempfile.TemporaryDirectory() as d:
            stop = threading.Event()
            stop.set()
            with self.assertRaises(gis.ImportCancelled):
                gis.run_import(self.BBOX, lambda *args: None, stop, root=d,
                               fetcher=lambda _: self.fail("cancel should avoid network"))

    def test_partial_bad_response_never_publish_package(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(gis.ImportFailure):
                gis.run_import(self.BBOX, lambda *args: None, threading.Event(),
                               root=d, fetcher=lambda _: {"elements": "wrong"})
            self.assertFalse((Path(d) / "packages").exists())

    def test_interrupted_job_record_after_restart(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            ident = "f" * 32
            gis.write_json(gis.job_path(ident, root),
                           {"id": ident, "status": "downloading", "message": "old"})
            res = gis.read_job(ident, root)
            self.assertEqual(res["status"], "interrupted")
            with self.assertRaises(ValueError):
                gis.job_path("../arbitrary", root)


class GISRouteTests(unittest.TestCase):
    def setUp(self):
        app=FastAPI()
        app.include_router(map_lab.router)
        self.client=TestClient(app)

    def test_static_page_js_and_invalid_import_bounds(self):
        self.assertEqual(self.client.get("/map-lab").status_code, 200)
        self.assertEqual(self.client.get("/map-lab/assets/map_lab.js").status_code, 200)
        result=self.client.post("/api/gis/import-jobs",json={"bbox":[0,0,25,25]})
        self.assertEqual(result.status_code, 422)
        self.assertEqual(self.client.get("/api/gis/packages/nonexistent").status_code, 404)
        self.assertEqual(self.client.get("/api/gis/import-jobs/nope").status_code, 404)

    def test_job_api_contract_without_network(self):
        pretend = {"id": "a" * 32, "bbox": GISImportTests.BBOX, "status": "queued",
                   "completed_tiles":0,"total_tiles":1}
        with patch.object(gis, "start_job", return_value=pretend) as start:
            result=self.client.post("/api/gis/import-jobs",json={"bbox":GISImportTests.BBOX})
            self.assertEqual(result.status_code, 202)
            self.assertEqual(result.json()["id"], pretend["id"])
            start.assert_called_once()

if __name__=="__main__":
    unittest.main()
