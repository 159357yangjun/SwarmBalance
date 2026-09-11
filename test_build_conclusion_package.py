from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from build_conclusion_package import build


class ConclusionPackageTests(unittest.TestCase):
    def test_can_build_structure_only_package(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "bundle.zip"
            path = build(None, out, allow_missing=True)
            self.assertTrue(path.exists())
            with zipfile.ZipFile(path) as zf:
                names = zf.namelist()
            self.assertTrue(any(n.endswith("结项交付说明.md") for n in names))
            self.assertTrue(any(n.endswith("CHECKSUMS.sha256") for n in names))
            self.assertTrue(any(n.endswith("VERSION") for n in names))


if __name__ == "__main__":
    unittest.main()
