"""Safety and empty-map contract tests for the opt-in GIS preview."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi import HTTPException
from console import map_lab

class FosiMapLabTests(unittest.TestCase):
    def test_status_without_downloaded_data(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)
            (p/"region.json").write_text(json.dumps({"id":"test","bbox_wgs84_lonlat":[1,2,3,4]}),encoding="utf-8")
            with patch.object(map_lab,"DATA_DIR",p):
                result=map_lab.map_lab_status()
                self.assertEqual(result["region"]["id"],"test")
                self.assertFalse(result["simulation_connected"])
                self.assertFalse(any(layer["ready"] for layer in result["layers"].values()))

    def test_no_arbitrary_file_serving(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(map_lab,"DATA_DIR",Path(temp)):
                for name in ("../secret","config","roads/../secret"):
                    with self.assertRaises(HTTPException) as ctx:
                        map_lab.map_lab_layer(name)
                    self.assertEqual(ctx.exception.status_code,404)
                with self.assertRaises(HTTPException):
                    map_lab.map_lab_layer("roads")

    def test_geojson_read_only(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp)/"output"
            folder.mkdir()
            f=folder/"roads.geojson"
            f.write_text('{"type":"FeatureCollection","features":[]}',encoding="utf-8")
            with patch.object(map_lab,"DATA_DIR",Path(temp)):
                response=map_lab.map_lab_layer("roads")
                self.assertEqual(response.path,str(f))
                self.assertEqual(response.media_type,"application/geo+json")

if __name__=="__main__":
    unittest.main()
