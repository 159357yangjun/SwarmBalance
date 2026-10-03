# -*- coding: utf-8 -*-
"""从远程 ZIP 用 HTTP Range 只抽取指定成员，不下载整包。

为什么要它：目标数据集 data.zip = 467,774,360 B，而我们只要其中几条 ``.ulg``。
整包拉下来既违反"控制落盘"也浪费时间；服务器实测支持 Range（206 + accept-ranges）。

做法（纯标准库）：
1. Range 读尾部 → 找 EOCD（``PK\\x05\\x06``）→ 得中央目录偏移与大小；
2. Range 读中央目录 → 解析每条 file header → 得到 name / compress_method /
   compressed_size / local_header_offset；
3. Range 读该成员的本地头（30 B + name + extra）→ 得数据起点；
4. Range 读 compressed_size 字节 → method 0 直接落盘，method 8 用 zlib 解 raw deflate。

纪律：只写调用方指定的成员；每个成员单独校验 CRC32，不过就删掉并 bail。
"""
from __future__ import annotations

import binascii
import hashlib
import pathlib
import struct
import urllib.request
import zlib

EOCD_SIG = b"PK\x05\x06"
CD_SIG = b"PK\x01\x02"
LOCAL_SIG = b"PK\x03\x04"


class ZipRangeError(RuntimeError):
    pass


def _fetch(url: str, start: int, end: int, timeout: int = 90) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "range-probe",
                                               "Range": f"bytes={start}-{end}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        if r.status not in (200, 206):
            raise ZipRangeError(f"unexpected status {r.status}")
        return r.read()


def total_size(url: str) -> int:
    """用 1 字节的 range 请求把 Content-Range 里的总长问出来。"""
    req = urllib.request.Request(url, headers={"User-Agent": "range-probe", "Range": "bytes=0-0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        cr = r.headers.get("Content-Range", "")
        body = r.read()
    if "/" not in cr:
        raise ZipRangeError(f"server did not report Content-Range: {cr!r}")
    n = int(cr.rsplit("/", 1)[1])
    if len(body) != 1:
        raise ZipRangeError("range probe returned unexpected body length")
    return n


def read_central_directory(url: str) -> dict:
    """返回 {name: dict(offset, comp_size, uncomp_size, method, crc)}。"""
    size = total_size(url)
    tail = _fetch(url, max(0, size - 68_000), size - 1)
    i = tail.rfind(EOCD_SIG)
    if i < 0:
        raise ZipRangeError("EOCD not found in tail window")
    eocd = tail[i:i + 22]
    cd_size, cd_off = struct.unpack("<II", eocd[12:20])
    if cd_off + cd_size > size:
        raise ZipRangeError("central directory range exceeds file")
    blob = _fetch(url, cd_off, cd_off + cd_size - 1, timeout=180)
    out, p = {}, 0
    while p + 46 <= len(blob) and blob[p:p + 4] == CD_SIG:
        # 中央目录头 PK\x01\x02 占签名(4)+版本(2)+所需版本(2)，故：
        #   8:gp_flags 10:method 12:modtime 14:moddate 16:crc32
        #   20:comp_size 24:uncomp_size 28:name_len 30:extra_len 32:comment_len
        #   34:disk_start 36:internal_attr 38:external_attr 40:local_header_offset
        h = blob[p:]  # 下面的偏移全部相对本条头起点，避免绝对/相对混用
        u16 = lambda o: struct.unpack_from("<H", h, o)[0]
        u32 = lambda o: struct.unpack_from("<I", h, o)[0]
        method = u16(10)
        crc = u32(16)
        csize = u32(20)
        usize = u32(24)
        nlen = u16(28)
        elen = u16(30)
        clen = u16(32)
        ext_off = u32(40)
        name = h[46:46 + nlen].decode("utf-8", "replace")
        out[name] = dict(offset=ext_off, comp_size=csize, uncomp_size=usize,
                         method=method, crc=crc)
        p += 46 + nlen + elen + clen
    if not out:
        raise ZipRangeError("central directory parsed empty")
    return out


def extract_member(url: str, name: str, dest: pathlib.Path, cd: dict | None = None) -> dict:
    cd = cd or read_central_directory(url)
    if name not in cd:
        raise ZipRangeError(f"member not in archive: {name}")
    info = cd[name]
    head = _fetch(url, info["offset"], info["offset"] + 29)
    if head[:4] != LOCAL_SIG:
        raise ZipRangeError("local header signature mismatch")
    ln, le = struct.unpack("<HH", head[26:30])
    base = info["offset"] + 30 + ln + le
    data = _fetch(url, base, base + info["comp_size"] - 1, timeout=300)
    if info["method"] == 0:
        raw = data
    elif info["method"] == 8:
        raw = zlib.decompress(data, -15)
    else:
        raise ZipRangeError(f"unsupported compression method {info['method']}")
    if len(raw) != info["uncomp_size"]:
        raise ZipRangeError(f"size mismatch for {name}: got {len(raw)} want {info['uncomp_size']}")
    got_crc = binascii.crc32(raw) & 0xFFFFFFFF
    if got_crc != info["crc"]:
        raise ZipRangeError(f"CRC mismatch for {name}: {got_crc:08x} != {info['crc']:08x}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(raw)
    return dict(name=name, bytes=len(raw), crc=f"{got_crc:08x}", method=info["method"],
                sha256=hashlib.sha256(raw).hexdigest())


if __name__ == "__main__":
    import sys
    URL = "https://zenodo.org/api/records/19617182/files/data.zip/content"
    members = sys.argv[1:]
    cd = read_central_directory(URL)
    ulgs = sorted(k for k in cd if k.lower().endswith(".ulg"))
    print(f"[CD] entries={len(cd)} ulg={len(ulgs)}")
    if not members:
        for k in ulgs:
            print(f"  {cd[k]['uncomp_size']:>11}  {k}")
        raise SystemExit(0)
    for m in members:
        key = next((k for k in ulgs if k.endswith(m)), None)
        if key is None:
            print(f"[MISS] {m}")
            continue
        dest = pathlib.Path("data/raw/px4_logs/ulg") / pathlib.Path(key).name
        rec = extract_member(URL, key, dest, cd)
        print(f"[OK] {key} -> {dest} bytes={rec['bytes']} crc={rec['crc']} sha256={rec['sha256'][:16]}")
