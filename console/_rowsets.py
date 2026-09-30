# -*- coding: utf-8 -*-
"""核心 4 算法 / 已撤除 6 算法 —— 这个行集合的唯一定义处。

为什么要有这个文件：`CORE`/`WITHDRAWN` 原先只写在 `console/test_plots_archive_void.py` 里，
而现在有三个人要用它：作废判据、行集合差异的生成器、引用门禁（声明了"仅核心 4"就必须
跟表里的实际算法列对得上）。各抄一份的话，"作废"和"门禁"会各说各话 —— 同一族里
最阴的一种：两套实现都对，但判的是不同的集合。
"""
from __future__ import annotations

CORE = {"greedy", "pso", "ga", "ortools"}
WITHDRAWN = {"iql", "iql_u", "vdn", "vdn_u", "qmix", "qmix_u"}   # 6b8c4c8 撤除的六个
ALL_NAMED = CORE | WITHDRAWN

#: 引用作废产物时允许的两种行集合声明（写进引用标注，门禁按表实际内容核对）
ROW_SETS = {
    "core4": CORE,
    "all10": ALL_NAMED,
}
ROW_SET_LABEL = {"core4": "仅核心 4 算法", "all10": "含 6 个已撤除算法（共 10 行）"}


def split(rows, key="Algorithm"):
    """按算法名把行分成 (core, withdrawn, other)。`other` 必须为空，非空说明表变了。"""
    core, wd, other = [], [], []
    for r in rows:
        name = (r.get(key) or r.get(list(r)[0]) or "").strip()
        if name in CORE:
            core.append(r)
        elif name in WITHDRAWN:
            wd.append(r)
        else:
            other.append(r)
    return core, wd, other


def declared_set(token):
    return ROW_SETS.get(token)
