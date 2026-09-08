"""no_fly_zone 最小单测集：验证禁飞区判定与绕飞不穿区。

运行方式：
    python -m unittest tests.test_no_fly -v
    python tests/test_no_fly.py
"""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "frontend"))

from no_fly_zone import NoFlyZone, NoFlyZoneSet  # noqa: E402
from shapely.geometry import Point, Polygon  # noqa: E402


class TestNoFlyZone(unittest.TestCase):
    def test_circle_contains(self):
        z = NoFlyZone("c", Point(0, 0).buffer(100), margin=0, raw=None)
        self.assertTrue(z.contains(0, 0))
        self.assertTrue(z.contains(50, 0))
        self.assertFalse(z.contains(150, 0))

    def test_margin_expands(self):
        z = NoFlyZone("c", Point(0, 0).buffer(100), margin=20, raw=None)
        self.assertTrue(z.contains(110, 0))   # 100+20 半径内
        self.assertFalse(z.contains(130, 0))

    def test_line_intersection(self):
        z = NoFlyZone("c", Point(0, 0).buffer(100), margin=0, raw=None)
        self.assertTrue(z.intersects_line((-200, 0), (200, 0)))
        self.assertFalse(z.intersects_line((-200, 200), (200, 200)))


class TestNoFlyZoneSet(unittest.TestCase):
    def test_path_blocked(self):
        zone = NoFlyZone("c", Point(0, 0).buffer(100), margin=0, raw=None)
        s = NoFlyZoneSet([zone], enabled=True)
        self.assertTrue(s.path_blocked((-200, 0), (200, 0)))
        self.assertFalse(s.path_blocked((-200, 200), (200, 200)))

    def test_disabled(self):
        zone = NoFlyZone("c", Point(0, 0).buffer(100), margin=0, raw=None)
        s = NoFlyZoneSet([zone], enabled=False)
        self.assertFalse(s.path_blocked((-200, 0), (200, 0)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
