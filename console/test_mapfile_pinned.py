# -*- coding: utf-8 -*-
"""输入地图的内容哈希必须被钉住，而且钉的那份要跟盘上对得上。

为什么值得一条测试：`provenance_baseline.json` 早就钉住了加载器在这张图上跑出来的
观测值（2889 栋 / 2864 个 NaN / 18 个碰撞体），登记簿里那一整片"实测"数字的来源
也都是它 —— 但**没有任何地方钉住被读的那个 .osm 本身**。
只钉结论不钉输入，"可复现"就只在没人换过文件之前成立：拷一份同名不同内容的地图进来，
加载观测会红，可没人能一眼说出原因是输入变了；而"这张图是不是答辩用的那张"
这个问题本身仍然无法回答。

判据是代码现算 sha256 去比基线里的手抄值，所以这里必须演示"钉错了会红"，
否则一条永远为真的断言等于没钉。
"""
from __future__ import annotations

import io
import json
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import verify_data_provenance as VP  # noqa: E402

BASELINE = ROOT / "provenance_baseline.json"


def _baseline():
    return json.loads(BASELINE.read_text(encoding="utf-8"))


def _run(doc):
    rep = []
    rc = VP.check_mapfile(rep, baseline=doc)
    return rc, rep


class MapfilePinTests(unittest.TestCase):

    def test_baseline_pins_the_map_and_it_matches_disk(self):
        doc = _baseline()
        self.assertIn("map_file", doc, "基线没写 map_file 路径")
        self.assertIn("map_file_sha256", doc, "基线没钉 map_file_sha256 —— 输入未被固定")
        self.assertEqual(len(doc["map_file_sha256"]), 64,
                         "钉的不是 sha256 十六进制（长度 %d）" % len(doc["map_file_sha256"]))
        rc, rep = _run(doc)
        self.assertEqual(rc, 0, "地图哈希与基线不一致：%s" % rep)
        self.assertTrue([r for r in rep if r[0] == "OK" and r[1] == "MAPFILE"], rep)
        # 字节数也要自洽：哈希对得上而大小对不上不可能同时成立
        size = os.stat(ROOT / doc["map_file"]).st_size
        self.assertEqual(doc.get("map_file_bytes"), size,
                         "基线记的字节数与盘上不符")

    def test_wrong_pin_goes_red_and_prints_measured_hash(self):
        """钉错必须红，而且拒绝原文要给实测值 —— 否则人还得自己去算。"""
        doc = _baseline()
        real = doc["map_file_sha256"]
        bogus = ("0" if real[0] != "0" else "1") + real[1:]
        self.assertNotEqual(bogus, real, "扰动没改变任何字符，判据会空转")
        doc["map_file_sha256"] = bogus
        rc, rep = _run(doc)
        self.assertEqual(rc, 1, "哈希被改错了却判过：%s" % rep)
        text = " ".join(x[2] for x in rep)
        self.assertIn(real, text, "报警里要给实测哈希，不能只说不一致")
        self.assertIn("需重跑", text, "报警要说清后果：地图类结论全部作废")

    def test_missing_pin_is_red_and_names_the_command(self):
        doc = _baseline()
        doc.pop("map_file_sha256", None)
        rc, rep = _run(doc)
        self.assertEqual(rc, 1, "没钉输入地图却判过")
        self.assertIn("--write-mapfile-baseline", rep[0][2],
                      "报警要直接给出采集命令，不能只说缺字段")

    def test_map_declared_in_baseline_actually_exists(self):
        doc = _baseline()
        p = ROOT / doc["map_file"]
        self.assertTrue(p.is_file(), "基线指向的地图文件不在盘上：%s" % doc["map_file"])
        rc, rep = _run(dict(doc, map_file="frontend/data/map/no_such_map_probe.osm"))
        self.assertEqual(rc, 1, "文件不存在却判过 —— 这条门是空的")

    def test_digest_is_streamed_not_whole_file_in_memory(self):
        """实测哈希必须来自分块读的文件本身。

        判别式：把同一份地图的**前半截**当成被核对的对象（造一个临时文件并指过去），
        哈希必然不同 -> 判红。若 check_mapfile 其实只是把基线值抄回来，这里就会绿。
        """
        doc = _baseline()
        rel = doc["map_file"]
        src = ROOT / rel
        half = src.stat().st_size // 2
        probe_rel = "results/adhoc/_mapfile_pin_probe.osm"
        probe = ROOT / probe_rel
        probe.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(src, "rb") as f_in, open(probe, "wb") as f_out:
                f_out.write(f_in.read(half))
            rc, rep = _run(dict(doc, map_file=probe_rel,
                                map_file_bytes=os.stat(probe).st_size))
            self.assertEqual(rc, 1, "半份地图被判成与基线一致 —— 哈希根本没在算")
            self.assertIn("sha256=", rep[0][2])
            self.assertEqual(VP.mapfile_digest(probe_rel)[1], half,
                             "分块统计的字节数与实际不符")
        finally:
            try:
                probe.unlink()
            except FileNotFoundError:
                pass


if __name__ == "__main__":
    unittest.main()
