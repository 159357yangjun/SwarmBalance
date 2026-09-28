from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from build_conclusion_package import CONFIGS, DOCS, build


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

    def test_package_contains_every_whitelisted_doc_and_config(self):
        """白名单里列出的文件必须真的进包——文档挪进 docs/ 后曾静默漏掉 5 份。"""
        with tempfile.TemporaryDirectory() as td:
            path = build(None, Path(td) / "bundle.zip", allow_missing=True)
            with zipfile.ZipFile(path) as zf:
                packed = {n.split("/", 1)[1] for n in zf.namelist() if "/" in n}
            for rel in DOCS + CONFIGS:
                self.assertIn(rel, packed, "结项证据包缺少白名单文件: %s" % rel)

    def test_missing_whitelisted_file_fails_loudly(self):
        import build_conclusion_package as module

        original = module.DOCS
        module.DOCS = list(original) + ["docs/一份不存在的文档.md"]
        try:
            with tempfile.TemporaryDirectory() as td:
                with self.assertRaises(FileNotFoundError):
                    build(None, Path(td) / "bundle.zip", allow_missing=True)
        finally:
            module.DOCS = original


if __name__ == "__main__":
    unittest.main()
