"""Project-to-GIS preview bindings are real, isolated and simulation-safe."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from console import map_lab, studio_project_preview as preview


A = "a" * 32
B = "b" * 32
PKG = "c" * 24


def project(pid):
    if pid not in (A, B):
        raise FileNotFoundError(pid)
    return {"project_id": pid, "name": "项目" + pid[:1]}


def manifest(pid):
    if pid != PKG:
        raise FileNotFoundError(pid)
    return {"package_id": PKG, "bbox_wgs84_lonlat": [121.44, 41.93, 121.45, 41.94],
            "quality": {"simulation_safe": False}, "feature_counts": {"buildings": 1}}


class ProjectPreviewRegistryTests(unittest.TestCase):
    def test_attach_persists_and_separates_projects(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertIsNone(preview.get_preview(A, project, root=folder)["map_preview"])
            result = preview.attach_preview(A, PKG, project, root=folder, manifest_loader=manifest)
            self.assertFalse(result["simulation_connected"])
            self.assertEqual(result["map_preview"]["package_id"], PKG)
            reopened = preview.get_preview(A, project, root=folder, manifest_loader=manifest)
            self.assertEqual(reopened["map_preview"]["package_id"], PKG)
            self.assertIsNone(preview.get_preview(B, project, root=folder)["map_preview"])
            self.assertEqual(sorted(p.name for p in Path(folder).glob("*.json")), [A + ".json"])

    def test_invalid_id_missing_project_or_package_cannot_persist(self):
        with tempfile.TemporaryDirectory() as folder:
            for pid in ("../x", "", "A" * 32, "a" * 33):
                with self.subTest(pid=pid), self.assertRaises(ValueError):
                    preview.attach_preview(pid, PKG, project, root=folder, manifest_loader=manifest)
            with self.assertRaises(FileNotFoundError):
                preview.attach_preview("d" * 32, PKG, project, root=folder, manifest_loader=manifest)
            with self.assertRaises(FileNotFoundError):
                preview.attach_preview(A, "d" * 24, project, root=folder, manifest_loader=manifest)
            self.assertFalse(list(Path(folder).glob("*.json")))

    def test_no_simulation_safe_package_can_be_mislabeled_as_preview(self):
        with tempfile.TemporaryDirectory() as folder:
            bad = lambda pid: {"package_id": pid, "bbox_wgs84_lonlat": [1,2,3,4],
                               "quality": {"simulation_safe": True}}
            with self.assertRaises(ValueError):
                preview.attach_preview(A, PKG, project, root=folder, manifest_loader=bad)
            self.assertFalse(list(Path(folder).glob("*.json")))

    def test_error_on_corrupted_mapping(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / (A+".json")
            path.write_text("{}", encoding="utf-8")
            with self.assertRaises(ValueError):
                preview.get_preview(A, project, root=folder, manifest_loader=manifest)


class ProjectPreviewAPITests(unittest.TestCase):
    def test_routes_with_fake_existing_projects_and_packages(self):
        with tempfile.TemporaryDirectory() as folder:
            app = FastAPI()
            app.include_router(map_lab.router)
            with patch.object(preview, "BASE", Path(folder)), \
                 patch.object(map_lab, "_get_mvp_project", side_effect=project), \
                 patch.object(map_lab.gis, "manifest_for", side_effect=manifest), \
                 TestClient(app) as client:
                route = "/api/gis/project-previews/"
                self.assertEqual(client.get(route+A).status_code, 200)
                self.assertIsNone(client.get(route+A).json()["map_preview"])
                self.assertEqual(client.put(route+A,json={"package_id":PKG}).status_code,200)
                self.assertEqual(client.get(route+A).json()["map_preview"]["package_id"], PKG)
                self.assertIsNone(client.get(route+B).json()["map_preview"])
                self.assertEqual(client.get(route+"../hack").status_code,404)
                self.assertEqual(client.put(route+A,json={"package_id":"x"}).status_code,422)
                self.assertEqual(client.put(route+A,json={"package_id":"d"*24}).status_code,404)
                self.assertEqual(client.get(route+"d"*32).status_code,404)
                self.assertFalse(client.get(route+A).json()["simulation_connected"])


if __name__ == "__main__":
    unittest.main()
