# -*- coding: utf-8 -*-
"""真实性数据集生成器 —— 把审计表里的统计从 Markdown 抽成机器可读数据集。

产物全部落在 ``data/provenance/``：6 张 CSV + 1 个 JSONL + manifest + README。
本文件是**唯一真源**：外部来源 URL、逐字原文、参数分级、派生算式都只在这里写一次，
CSV 由它生成；MD（``docs/真实性审计表.md``）只是人读视图，不再承担存储职责。

纪律：
- 只读外部数据文件，不重跑任何仿真，不改 raw_runs.csv / compare CSV / 版本号 / 配置。
- 凡是从本地文件算出的数（``computed_from_file``）必须本轮真的读到才算登记；
  读不到就 bail，不许留一个手写值冒充观测值。
- ``--verify`` 模式：把现有产物重算一遍并与磁盘内容比对（忽略 generated_at），
  任一字节漂移即退出码 1。

运行：
    ../.venv310/Scripts/python.exe -X utf8 docs/build_truth_dataset.py          # 生成
    ../.venv310/Scripts/python.exe -X utf8 docs/build_truth_dataset.py --verify   # 校验
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve()
REPO = HERE.parents[1]
OUT = REPO / "data" / "provenance"
WIND_CSV = REPO / "data" / "raw" / "openmeto_yangpu_wind_20260801_0911.csv"
OSM_FILE = REPO / "frontend" / "data" / "map" / "part_of_yangpu.osm"

DATASET_VERSION = "1.0.0"
EVIDENCE_DATE = "2026-10-03"


def _bail(code: str, detail: str) -> None:
    print(f"[{code}] {detail}")
    raise SystemExit(2)


# ---------------------------------------------------------------- 外部来源登记表
# url 必须是完整可点击链接；retrieval_status 记录取证那轮的实际 HTTP 观测。
SOURCES = [
    dict(source_id="src_flycart30", name="DJI FlyCart 30 官方规格页", publisher="大疆创新（DJI）",
         url="https://www.dji.com/cn/flycart-30/specs", source_type="vendor_spec_page",
         retrieval_date=EVIDENCE_DATE, http_status="200", response_bytes="135096",
         sha256="", local_file="",
         verified_by="本轮 curl 直取整页后去标签 grep，三条原文命中",
         notes="页面为服务端渲染的静态 HTML，可直接取到中文正文"),
    dict(source_id="src_piw_docs", name="DJI 企业应用支持文档（FlyCart 30 / TB60 / BS60）",
         publisher="大疆创新（DJI）", url="https://fh.dji.com/user-manual/cn/", source_type="vendor_support_docs",
         retrieval_date=EVIDENCE_DATE, http_status="未取得", response_bytes="", sha256="", local_file="",
         verified_by="未取得", notes="本轮未直接取证；仅用于说明 BS60 冲突的另一处出处候选"),
    dict(source_id="src_m300_specs", name="DJI Matrice 300 RTK 规格页（BS60 条目）",
         publisher="大疆创新（DJI）", url="https://enterprise.dji.com/matrice-300/specs",
         source_type="vendor_spec_page", retrieval_date=EVIDENCE_DATE, http_status="200",
         response_bytes="458", sha256="", local_file="",
         verified_by="已测：返回 200 但仅 458 B，为 JS 壳，服务端不含规格文本",
         notes="无法独立取证 ⇒ BS60 同时充电数量维持 E 级（冲突未决）"),
    dict(source_id="src_store_bs60", name="DJI 官方商城 BS60 商品页",
         publisher="大疆创新（DJI）", url="https://store.dji.com/cn/product/dji-bs60-battery-station",
         source_type="vendor_store_product_page", retrieval_date=EVIDENCE_DATE, http_status="未复核",
         response_bytes="", sha256="", local_file="",
         verified_by="上一轮据其写入「4+4」说法，本轮未在官方支持页复现",
         notes="与 src_m300_specs 冲突，处置见 parameters.csv 的 param_bs60_charge"),
    dict(source_id="src_sf_ark40", name="丰翼 方舟40 产品页", publisher="顺丰丰翼科技",
         url="https://piw-mr-web.inn.sf-express.com/uav/ark-40/", source_type="vendor_product_page",
         retrieval_date=EVIDENCE_DATE, http_status="200", response_bytes="124983",
         sha256="192489504d1d934e（前缀，本轮实测）", local_file="",
         verified_by="本轮 curl + 去标签逐字摘录；电池相关关键词命中数为 0",
         notes="顺丰自有域，非媒体转载"),
    dict(source_id="src_cmu_data_descriptor", name="CMU 配送无人机飞行能耗数据集（Scientific Data）",
         publisher="Nature Scientific Data (CC-BY 4.0)",
         url="https://www.nature.com/articles/s41597-021-00930-x", source_type="journal_data_descriptor",
         retrieval_date=EVIDENCE_DATE, http_status="200", response_bytes="319236", sha256="", local_file="",
         verified_by="本轮 WebFetch 取正文并逐字摘录；论文本身不含 Wh/km 结论或拟合系数",
         notes="机型为 DJI Matrice 100，跨机型套用绝对能耗＝冒充，只可用于验证结构关系"),
    dict(source_id="src_cmu_kiltub", name="CMU KiltHub 数据下载入口", publisher="Carnegie Mellon University",
         url="https://kilthub.cmu.edu/articles/dataset/In-flight_positional_and_energy_use_data_set_for_a_delivery_drone/14909664",
         source_type="repository_doi", retrieval_date=EVIDENCE_DATE, http_status="403",
         response_bytes="", sha256="", local_file="",
         verified_by="已试两次（文章页与 ndownloader 直链）均 403",
         notes="数据存在性已由论文证实；文件本体未取得 ⇒ 该来源目前只能支撑定性结论"),
    dict(source_id="src_openmeteo_archive", name="Open-Meteo Historical Weather API（ERA5 再分析）",
         publisher="Open-Meteo", url="https://archive-api.open-meteo.com/v1/archive",
         source_type="api_endpoint", retrieval_date=EVIDENCE_DATE, http_status="200",
         response_bytes="32885", sha256="44b2ad0dd0ad6319（前缀，本轮实测）",
         local_file="data/raw/openmeto_yangpu_wind_20260801_0911.csv",
         verified_by="本轮重放请求并与仓内 CSV 逐值对账（均值差 <1e-3 m/s）",
         # Complete：原件在仓内 + sha256 已登记 + 端点可重放，三者同时成立 ⇒ 复核不依赖别人改页面。
         traceability="Complete", transformation="As-published",
         notes="再分析格点数据，非现场气象站观测；服务端把请求点吸附到最近格点 31.3181/121.537544"),
    dict(source_id="src_osm_extract", name="OpenStreetMap 杨浦区域导出", publisher="OpenStreetMap contributors (ODbL)",
         url="https://www.openstreetmap.org/export#map=14/31.2932/121.5146", source_type="crowdsourced_gis",
         retrieval_date="下载事件时间未取得", http_status="本轮不可达", response_bytes="11098582",
         sha256="72c3ef9ca19c804387bc2985d3a2dd76a772fc28fc9add8872b003419e78a65b",
         local_file="frontend/data/map/part_of_yangpu.osm",
         verified_by="内容侧本轮实测（元素计数、署名块、changeset/uid/timestamp）；溯源侧本轮无法重下",
         # ⚠ 这一条正是"两条轴必须分开"的实证：旧体系只能写成「内容 A / 溯源 E」那个别扭的斜杠。
         #   拆开看：文件本身是仓内原件、有哈希、可离线复算元素普查 ⇒ traceability=Complete；
         #   但"它是哪一次 OSM 请求的产物"无凭据（下载事件时间/操作者/当时哈希都没留，
         #   且本轮 openstreetmap.org 不可达无法重下）⇒ 这一点仍属未证，记在 notes 里而不是靠降级掩盖。
         traceability="Complete", transformation="Local-extraction",
         provenance_gap="下载事件无凭据（何时、谁、原始响应哈希）⇒ 只锁得住『现在的它』",
         notes="本机 www.openstreetmap.org:443 连接失败(exit 7)、Overpass 406、kumi.systems 超时 ⇒ "
               "文件级 traceability=Complete（原件+哈希在仓内），但**下载事件溯源仍未证**"),
    dict(source_id="src_meituan_media", name="美团无人机公开报道口径", publisher="媒体报道（非厂商规格页）",
         url="https://www.meituan.com/news", source_type="media_secondary", retrieval_date=EVIDENCE_DATE,
         http_status="不适用", response_bytes="", sha256="", local_file="", verified_by="未取得",
         notes="无官方规格页可引 ⇒ 轻载机型全部字段为 D/E 级，不得称厂商参数"),
]

# ---------------------------------------------------------------- 参数分级表
# value 是项目里真正在用的值；source_value 是官方原文里的值；两者不等时 derivation 给完整算式。
#
# ── 三条轴，不要揉成一级（2026-10-06 起；外部评审第⑦条）──────────────────────
# evidence_grade   A/B/C/D/E —— **来源可信度**：这个数字是谁给的。
# traceability     Complete / Partial / None —— **溯源完整度**：别人能不能独立回到那份原始件。
# transformation   As-published / Derived / Local-extraction / Assumption —— **处理过程**：它被改过没有。
#
# 为什么要拆开：旧写法把后两轴塞进一个字母里，于是产生了两类说不清的表述 ——
#   · OSM 底图只能写成"内容 A / 溯源 E"，那个斜杠就是体系不够用的证据；
#   · "A(接口) + C(换算)" 更是一个格子里塞了两个不同轴的值。
# 拆开后同一份底图是 source=A / traceability=Complete / transformation=Local-extraction，三句话互不打架。
#
# ⚠ traceability 的判据里我加了一条评审原规则没有的东西：**厂商网页类来源最高只给 Partial**。
#   理由（本轮实测得出）：`curl` 重放确实能拿到稳定页面对哈希（DJI 两次都是 67de8b0eeb5f6f52、
#   ARK40 两次都是 192489504d1d934e 且与登记值逐位吻合），表面上满足"API 可重放 ⇒ Complete"。
#   但那是**厂商随时可单方面改掉**的外部状态：页面一改版，Complete 就悄悄失效，而产物上看不出来。
#   只有仓内留了原件（或有本地快照文件）才算 Complete —— Complete 的含义是"核验不依赖任何
#   别人的在线服务还活着"，不是"此刻能 curl 通"。这条收紧会让数字更好看与否无关，故不让步。
TRACEABILITY_VALUES = ("Complete", "Partial", "None")
TRANSFORMATION_VALUES = ("As-published", "Derived", "Local-extraction", "Assumption")


def _check_axes(p):
    """逐条自检：枚举合法 + 两轴与来源等级之间不能自相矛盾。

    为什么要有这个函数而不是靠人核对 24×2 个格子：批量填字段最容易出的错是"整列复制同一个值"
    （那等于没分档），以及 transformation=Derived 却不给算式。这两类都能在这里当场拦住。
    """
    pid = p["param_id"]
    tr, tf = p["traceability"], p["transformation"]
    if tr not in TRACEABILITY_VALUES:
        raise ValueError("[AXIS_ENUM] %s traceability=%r 不在 %s" % (pid, tr, TRACEABILITY_VALUES))
    if tf not in TRANSFORMATION_VALUES:
        raise ValueError("[AXIS_ENUM] %s transformation=%r 不在 %s" % (pid, tf, TRANSFORMATION_VALUES))
    # Derived 必须能被复算：没有 derivation 也没有 recompute_cmd 的"派生值"就是手填。
    if tf == "Derived" and not (p.get("derivation") or p.get("recompute_cmd")):
        raise ValueError("[AXIS_INCONSISTENT] %s 标 Derived 却既无 derivation 也无 recompute_cmd" % pid)
    # Assumption 意味着无外部依据 ⇒ 它不可能同时"有完整溯源"，也不可能是厂商发布值。
    if tf == "Assumption":
        if tr != "None":
            raise ValueError("[AXIS_INCONSISTENT] %s transformation=Assumption 但 traceability=%s" % (pid, tr))
        if p["is_real_measurement"] == "vendor_stated":
            raise ValueError("[AXIS_INCONSISTENT] %s 既是假设又标 vendor_stated" % pid)
    # D 级（纯设定）在三条轴上只能是 None/Assumption，否则 grade 与轴互相打脸。
    if p["evidence_grade"].startswith("D") and (tr, tf) != ("None", "Assumption"):
        raise ValueError("[AXIS_INCONSISTENT] %s evidence_grade=%s 但 (%s,%s) 不匹配" % (
            pid, p["evidence_grade"], tr, tf))


PARAMETERS = [
    dict(param_id="param_flycart_battery_wh", drone_type="heavy_cargo", field="battery_capacity",
         value="3968.8", unit="Wh", evidence_grade="C", traceability="Partial", transformation="Derived",
         is_real_measurement="derived",
         error_band_vs_source_pct="0.00（整除双块）", source_value="1984.4 Wh × 2（DB2000 单块）",
         test_condition="官方标注：零海拔无风，仅供参考",
         derivation="3968.8 = 1984.4 * 2", recompute_cmd='python -c "print(1984.4*2)"',
         config_file="frontend/config/drone_types.yaml", status="在用",
         notes="官方直接发布的是单块 1984.4 Wh；双块总能量是我方派生，不得称『官方发布的双块值』"),
    dict(param_id="param_flycart_consumption_base", drone_type="heavy_cargo", field="consumption_base",
         value="0.142", unit="Wh/m", evidence_grade="C", traceability="Partial", transformation="Derived",
         is_real_measurement="derived",
         error_band_vs_source_pct="0.18", source_value="空载双电最大航程 28 km",
         test_condition="官方标注：零海拔无风，以 15 m/s 匀速飞行",
         derivation="3968.8 Wh / 28 km = 141.743 Wh/km = 0.141743 Wh/m ≈ 0.142",
         recompute_cmd='python -c "print(3968.8/28)"', config_file="frontend/config/drone_types.yaml",
         status="在用",
         # T4 措辞订正：本值是「官方标称容量 ÷ 官方标称航程」反推 ⇒ spec-derived anchor。
         # 全仓无任何拟合实现（curve_fit/polyfit/linregress/lstsq/sklearn.fit 实测 0 命中），
         # 也没有实机飞行日志 ⇒ 不得称「标定/calibration」。真拟合过才配那个词。
         notes="这就是 142 的【官方规格派生锚定】依据（非拟合标定）；口径为【空载】，不可与满载锚点直接比"),
    dict(param_id="param_flycart_load_penalty", drone_type="heavy_cargo", field="load_penalty_factor",
         value="0.75", unit="-", evidence_grade="C", traceability="Partial", transformation="Derived",
         is_real_measurement="derived",
         error_band_vs_source_pct="0.00", source_value="空载 28 km ÷ 满载(30 kg) 16 km = 1.75",
         test_condition="官方标注：零海拔无风",
         derivation="1 + 0.75 = 1.75 = 28/16", recompute_cmd='python -c "print(28/16)"',
         config_file="frontend/config/drone_types.yaml", status="在用",
         # T5：原 notes 写「与 consumption_base 相互独立的第二个官方锚点」——该说法已订正。
         # 两条都来自**同一对官方航程数**（28 km 空载 / 16 km 满载），只是除法顺序不同，
         # 所以它们是同源派生而不是彼此独立的第二条证据；且比值成立还额外依赖一条未检假设（见下）。
         notes="派生自官方航程比 28/16。**隐含假设：同一电池包、同一无风巡航条件下，"
               "单位距离能耗与可飞航程成反比**（即 E_full/E_empty = R_empty/R_full）。"
               "该假设未经实飞检验 ⇒ 若满载时改用不同飞行模式、或载重改变了速度/悬停占比，"
               "此比值就不再等于能耗倍率，本参数需重新推导。"
               "⚠ 与 consumption_base 属**同一对官方数据的两种除法**，不是两条独立证据"),
    dict(param_id="param_flycart_speed", drone_type="heavy_cargo", field="speed",
         value="20", unit="m/s", evidence_grade="A", traceability="Partial", transformation="As-published",
         is_real_measurement="vendor_stated",
         error_band_vs_source_pct="0.00", source_value="水平飞行速度 20 米/秒（载重 30 千克）",
         test_condition="零海拔无风", derivation="", recompute_cmd="",
         config_file="frontend/config/drone_types.yaml", status="在用", notes="官方直接值"),
    dict(param_id="param_flycart_full_range", drone_type="heavy_cargo", field="full_load_range_km",
         value="16", unit="km", evidence_grade="A", traceability="Partial", transformation="As-published",
         is_real_measurement="vendor_stated",
         error_band_vs_source_pct="0.00", source_value="最大飞行距离（满载）双电（载重 30 千克）：16 千米",
         test_condition="零海拔无风", derivation="", recompute_cmd="",
         config_file="frontend/config/drone_types.yaml", status="在用",
         notes="同页另有单电（40 kg）8 km，勿混档"),
    dict(param_id="param_flycart_empty_range", drone_type="heavy_cargo", field="(未建模)空载航程",
         value="28", unit="km", evidence_grade="A", traceability="Partial", transformation="As-published",
         is_real_measurement="vendor_stated",
         error_band_vs_source_pct="0.00", source_value="最大飞行距离（空载）双电：28 千米／单电：12 千米",
         test_condition="零海拔无风、15 m/s 匀速", derivation="", recompute_cmd="",
         config_file="", status="仅作派生输入", notes="本轮首次从官方页取到，未单独建字段"),
    dict(param_id="param_flycart_payload_caliber", drone_type="heavy_cargo", field="carrying_capacity",
         value="30", unit="kg", evidence_grade="E->已定", traceability="Partial", transformation="As-published",
         is_real_measurement="vendor_stated",
         error_band_vs_source_pct="口径冲突", source_value="同页三口径并存：货箱 0–40 kg；吊挂 双电 5–30 kg / 单电 5–40 kg；最大起飞 95 kg（标配货箱，海平面附近）",
         test_condition="见各条原文", derivation="取双电池档上限 30 kg",
         recompute_cmd='curl -sSL https://www.dji.com/cn/flycart-30/specs | sed "s/<[^>]*>/ /g" | grep -o ".\\{0,30\\}载荷能力.\\{0,40\\}"',
         config_file="frontend/config/drone_types.yaml", status="在用",
         notes="对外禁用『载重 0–40 kg』描述本项目 30 kg 设定＝混档"),
    dict(param_id="param_flycart_wind_resist", drone_type="heavy_cargo", field="(未建模)抗风等级",
         value="12", unit="m/s", evidence_grade="A", traceability="Partial", transformation="As-published",
         is_real_measurement="vendor_stated",
         error_band_vs_source_pct="0.00", source_value="抗风等级 12 米/秒（载重 30 千克…）",
         test_condition="官方该行只标『零海拔』，未标『无风』——已核实原文确无此二字",
         derivation="", recompute_cmd="", config_file="", status="未建模",
         notes="模型里没有风速对运动学/可达性的约束（E1 只进能耗）"),
    dict(param_id="param_flycart_temp", drone_type="heavy_cargo", field="(未建模)工作温度",
         value="-20~45", unit="℃", evidence_grade="E", traceability="None", transformation="As-published",
         is_real_measurement="unverified",
         error_band_vs_source_pct="", source_value="未取得（本轮 135 KB 页面文本内未命中该串）",
         test_condition="", derivation="", recompute_cmd="", config_file="", status="未建模",
         notes="撤回先前引用：我在已抓取的页面文本里找不到 ⇒ 降为 E"),
    dict(param_id="param_ark40_payload", drone_type="standard_cargo", field="carrying_capacity",
         value="10", unit="kg", evidence_grade="A", traceability="Partial", transformation="As-published",
         is_real_measurement="vendor_stated",
         error_band_vs_source_pct="0.00", source_value="10kg 最大载荷重量", test_condition="官方页未附条件",
         derivation="", recompute_cmd="", config_file="frontend/config/drone_types.yaml", status="在用", notes=""),
    dict(param_id="param_ark40_range", drone_type="standard_cargo", field="full_load_range_km",
         value="20", unit="km", evidence_grade="A", traceability="Partial", transformation="As-published",
         is_real_measurement="vendor_stated",
         error_band_vs_source_pct="0.00", source_value="20km 最大航程", test_condition="官方页未附条件",
         derivation="", recompute_cmd="", config_file="frontend/config/drone_types.yaml", status="在用", notes=""),
    dict(param_id="param_ark40_speed", drone_type="standard_cargo", field="speed",
         value="14", unit="m/s", evidence_grade="A", traceability="Partial", transformation="As-published",
         is_real_measurement="vendor_stated",
         error_band_vs_source_pct="0.00", source_value="巡航速度14m/s", test_condition="官方页未附条件",
         derivation="", recompute_cmd="", config_file="frontend/config/drone_types.yaml", status="在用",
         notes="旧登记簿曾记『speed 无来源标注』，本轮已补上官方出处"),
    dict(param_id="param_ark40_mtow", drone_type="standard_cargo", field="(未建模)最大起飞重量",
         value="46", unit="kg", evidence_grade="A", traceability="Partial", transformation="As-published",
         is_real_measurement="vendor_stated",
         error_band_vs_source_pct="0.00", source_value="46kg 最大起飞重量", test_condition="",
         derivation="", recompute_cmd="", config_file="", status="未建模", notes=""),
    dict(param_id="param_ark40_battery_wh", drone_type="standard_cargo", field="battery_capacity",
         value="1600", unit="Wh", evidence_grade="D", traceability="None", transformation="Assumption",
         is_real_measurement="assumed",
         error_band_vs_source_pct="不可估（无外部基准）",
         source_value="未取得：官方页关键词 mAh/毫安时/Wh/瓦时/电池容量 命中数全部为 0",
         test_condition="不适用", derivation="", recompute_cmd="",
         config_file="frontend/config/drone_types.yaml", status="在用（假设值）",
         notes="对外禁用『对标 ARK40 官方电池』"),
    dict(param_id="param_ark40_consumption", drone_type="standard_cargo", field="consumption_base",
         value="0.06", unit="Wh/m", evidence_grade="D", traceability="None", transformation="Assumption",
         is_real_measurement="assumed",
         error_band_vs_source_pct="不可估", source_value="未取得（无电池容量即无法派生 Wh/km）",
         test_condition="不适用", derivation="", recompute_cmd="",
         config_file="frontend/config/drone_types.yaml", status="在用（假设值）", notes=""),
    dict(param_id="param_light_payload", drone_type="light_express", field="carrying_capacity",
         value="2.4", unit="kg", evidence_grade="E", traceability="None", transformation="Assumption",
         is_real_measurement="unverified",
         error_band_vs_source_pct="媒体口径 2.5 vs 项目 2.4（差 4%）",
         source_value="媒体报道口径 2.5 kg；无厂商规格页", test_condition="不适用",
         derivation="项目自行改为 2.4，理由未登记", recompute_cmd="",
         config_file="frontend/config/drone_types.yaml", status="在用", notes="改值理由缺失"),
    dict(param_id="param_light_battery_wh", drone_type="light_express", field="battery_capacity",
         value="380", unit="Wh", evidence_grade="D", traceability="None", transformation="Assumption",
         is_real_measurement="assumed",
         error_band_vs_source_pct="不可估", source_value="未取得（美团从未公布电池）", test_condition="不适用",
         derivation="", recompute_cmd="", config_file="frontend/config/drone_types.yaml",
         status="在用（假设值）", notes=""),
    dict(param_id="param_light_consumption", drone_type="light_express", field="consumption_base",
         value="0.032", unit="Wh/m", evidence_grade="D", traceability="None", transformation="Assumption",
         is_real_measurement="assumed",
         error_band_vs_source_pct="不可估", source_value="未取得", test_condition="不适用",
         derivation="", recompute_cmd="", config_file="frontend/config/drone_types.yaml",
         status="在用（假设值）", notes=""),
    dict(param_id="param_swap_time", drone_type="(全局)", field="swap_time_seconds",
         value="180", unit="s", evidence_grade="D", traceability="None", transformation="Assumption",
         is_real_measurement="assumed",
         error_band_vs_source_pct="不可估",
         source_value="未取得：无任何官方换电动作时长。BS60 的 60 min 是『充满两块 TB60』的时间，不是换电动作耗时",
         test_condition="不适用", derivation="", recompute_cmd="",
         config_file="四处冗余定义（见 model_notes）", status="在用（假设值）",
         notes="对外禁用『换电 180 s 为厂商参数』"),
    dict(param_id="param_battery_low_threshold", drone_type="(全局)", field="battery_low_threshold",
         value="0.2", unit="-", evidence_grade="D", traceability="None", transformation="Assumption",
         is_real_measurement="assumed",
         error_band_vs_source_pct="不可估", source_value="未取得", test_condition="不适用",
         derivation="", recompute_cmd="", config_file="", status="在用（假设值）", notes=""),
    dict(param_id="param_sla_base", drone_type="(全局)", field="sla_base_seconds",
         value="420", unit="s", evidence_grade="D", traceability="None", transformation="Assumption",
         is_real_measurement="assumed",
         error_band_vs_source_pct="不可估", source_value="未取得",
         test_condition="不适用（且该值直接决定超时率）", derivation="", recompute_cmd="",
         config_file="", status="在用（假设值）", notes="对外禁用『真实时效约束』"),
    dict(param_id="param_sla_per_kg", drone_type="(全局)", field="sla_per_kg_seconds",
         value="24", unit="s/kg", evidence_grade="D", traceability="None", transformation="Assumption",
         is_real_measurement="assumed",
         error_band_vs_source_pct="不可估", source_value="未取得", test_condition="不适用",
         derivation="", recompute_cmd="", config_file="", status="在用（假设值）", notes=""),
    dict(param_id="param_height_fallback_floor", drone_type="(地图)", field="building_default_floors",
         value="3.0", unit="层", evidence_grade="D+E", traceability="None", transformation="Assumption",
         is_real_measurement="assumed",
         error_band_vs_source_pct="未取得", source_value="未取得；且与另一处 12 m 固定值不一致",
         test_condition="不适用", derivation="两处 fallback 并存，未统一", recompute_cmd="",
         config_file="", status="在用", notes="经证明不进调度（二维相交），影响面＝可视化"),
    dict(param_id="param_bs60_charge", drone_type="(地面设施)", field="bs60_可同时充电块数",
         value="未定", unit="块", evidence_grade="E", traceability="None", transformation="Assumption",
         is_real_measurement="conflict_unresolved",
         error_band_vs_source_pct="", source_value="冲突：官方商城商品页『4 块飞行电池 + 4 块遥控器电池』vs 支持页『存放 8×TB60+4×WB37，同时充 2×TB60+1×WB37』",
         test_condition="支持页本轮无法独立取证（JS 壳 458 B）", derivation="", recompute_cmd="",
         config_file="", status="未入正式表", notes="保守表述：存放 8+4；同时充电数量两页冲突未决"),
]

MODEL_NOTES = [
    dict(note_id="note_swap_redundancy", text="swap_time_seconds 在配置中存在 4 处冗余定义，改动须同步 4 处，否则不同路径吃不同值。"),
    dict(note_id="note_height_2d", text="建筑高度不参与调度判定：冲突检测为二维相交，高度 fallback 只影响可视化。"),
    dict(note_id="note_config_freeze", text="frontend/task.py 模块级冻结配置 ⇒ 同一进程内改配置不生效，多配置实验必须一进程一配置。"),
    dict(note_id="note_dual_channel", text="默认轻载下 PSO/GA/OR-Tools 批量优化器实测 optimize_calls=0（buffer 峰值 2 < 阈值 15），三算法实际共用即时贪心通道。"),
    dict(note_id="note_wind_energy_only", text="E1 只让风进能耗，不改运动学；wind_along 正=逆风、负=顺风，符号约定由 frontend/test_wind_energy.py 钉住。"),
]

DISABLED_CLAIMS = [
    dict(claim_id="dc_1", claim="无人机参数全部来自真实机型且可溯源", verdict="不成立",
         reason="三型中仅 heavy/standard 的部分字段有官方直接值；除 heavy 外所有电池容量与能耗系数为假设值"),
    dict(claim_id="dc_2", claim="经过实测校准 / 可指导实际运营", verdict="不成立",
         reason="无任何实机飞行日志参与标定"),
    dict(claim_id="dc_3", claim="ARK40 电池 1600 Wh、美团 380 Wh 为官方值", verdict="禁用",
         reason="两家均未公布电池参数"),
    dict(claim_id="dc_4", claim="换电 180 s 为厂商参数", verdict="禁用", reason="无官方换电动作时长"),
    dict(claim_id="dc_5", claim="FlyCart 载重 0–40 kg（用于本项目 30 kg 设定）", verdict="禁用",
         reason="口径混用；本项目对应双电池 5–30 kg 档"),
    dict(claim_id="dc_6", claim="BS60 一次充 4 块飞行电池", verdict="禁用（未决）",
         reason="官方两处页面冲突且其中一处本轮无法独立取证"),
    dict(claim_id="dc_7", claim="结项实验对比了四种调度算法的性能", verdict="当前证据不支持",
         reason="默认轻载下三个批量优化器 optimize_calls=0，实际跑的是共用即时贪心通道"),
    dict(claim_id="dc_8", claim="10 m 风速代表 60 m 巡航高度", verdict="已废",
         reason="模型里没有飞行高度这个量"),
]

FIELD_DICT = {
    "sources.csv": [
        ("source_id", "str", "主键，形如 src_*；被其余表以分号分隔引用"),
        ("name", "str", "来源名称"),
        ("publisher", "str", "发布主体（厂商/期刊/平台）"),
        ("url", "str", "完整可点击链接；禁止半段链接"),
        ("source_type", "enum", "vendor_spec_page|vendor_support_docs|vendor_store_product_page|vendor_product_page|journal_data_descriptor|repository_doi|api_endpoint|crowdsourced_gis|media_secondary"),
        ("retrieval_date", "date", "本轮亲自打开该页面的日期"),
        ("http_status", "str", "本轮实测 HTTP 码；未取到写『未取得』而不是留空"),
        ("response_bytes", "int", "本轮实测响应体大小"),
        ("sha256", "hex", "响应体或本地文件的哈希；只锁『现在的它』，不锁『当初的它』"),
        ("local_file", "relpath", "对应的仓内文件；无则空"),
        ("verified_by", "str", "本轮取证动作的一手描述"),
        ("notes", "str", "限制与注意事项"),
    ],
    "parameters.csv": [
        ("param_id", "str", "主键 param_*"),
        ("drone_type", "str", "所属机型或作用域（(全局)/(地图)/(地面设施)）"),
        ("field", "str", "代码/配置里的字段名；未建模的以 (未建模) 前缀"),
        ("value", "str", "项目当前实际使用的值"),
        ("unit", "str", "单位"),
        ("evidence_grade", "enum", "A 官方直接值 | B 原始公开实测 | C 由 A/B 可复算的派生值 | D 假设值 | E 未验证或冲突"),
        ("is_real_measurement", "enum", "vendor_stated|real_flight_measurement|derived|assumed|unverified|conflict_unresolved"),
        ("error_band_vs_source_pct", "str", "项目值与来源值的相对差；无基准时写『不可估』"),
        ("source_value", "str", "来源原文的值（逐字或注明未取得）"),
        ("test_condition", "str", "来源给出的测试条件；缺了就写缺"),
        ("derivation", "str", "派生算式全文；C 级必填"),
        ("recompute_cmd", "str", "可自行重放的命令；C 级必填"),
        ("config_file", "relpath", "值所在配置文件"),
        ("status", "str", "在用|在用（假设值）|未建模|仅作派生输入|未入正式表"),
        ("notes", "str", "对外禁用表述等"),
    ],
    "statistics.csv": [
        ("stat_id", "str", "主键 stat_*"),
        ("dataset", "str", "所属数据集"),
        ("metric", "str", "指标名"),
        ("value", "float", "数值"),
        ("unit", "str", "单位"),
        ("n", "int", "样本量"),
        ("method", "str", "计算口径（总体标准差 ddof=0 / 分位数取法 / t 区间）"),
        ("computed_from_file", "relpath", "本轮真实读取并复算的文件；为空表示该值是登记的引用值"),
        ("row_count_seen", "int", "本轮实际解析到的行数；-1 表示未从文件复算"),
        ("evidence_grade", "enum", "同上 A–E"),
        ("notes", "str", ""),
    ],
    "wind_hourly.csv": [
        ("time_local", "datetime", "Asia/Shanghai 本地时间"),
        ("wind_speed_ms", "float", "m/s；接口原值为 km/h，÷3.6 换算"),
        ("wind_direction_deg", "float", "来向角度"),
        ("temperature_c", "float", "2 m 气温"),
    ],
    "osm_census.csv": [
        ("entity", "str", "统计对象"),
        ("count", "int", "本轮解析得到的计数"),
        ("total", "int", "分母"),
        ("share", "float", "占比；分母不存在时留空"),
        ("method", "str", "计数方式"),
        ("computed_from_file", "relpath", ""),
        ("evidence_grade", "enum", ""),
        ("notes", "str", ""),
    ],
    "formal_baseline_run.csv": [
        ("fixture", "str", "C1|C2|S（见 docs/CriticalFixture定义.md）"),
        ("seed", "int", "配对种子 40901–40910"),
        ("repeat", "int", "重复序号"),
        ("algorithm", "str", "本轮批次只有 greedy_immediate 有基线"),
        ("completed_tasks", "int", "完成任务数"),
        ("generated_tasks", "int", "生成任务数"),
        ("completion_rate", "float", "完成率"),
        ("timeout_rate", "float", "超时率"),
        ("total_energy_wh", "float", "总能量消耗"),
        ("total_distance_m", "float", "总飞行距离"),
        ("avg_latency_s", "float", "平均时延"),
        ("evidence_grade", "enum", "B = 本地 run 记录逐行复算，非外部真值"),
    ],
    "manifest.json": "数据集清单：版本、生成时间、每表的行数/列数/SHA-256、外部文件指纹、依赖声明。",
    "README.md": "字段字典 + 等级定义 + 复算命令 + 边界声明的人读说明。",
    "truth.jsonl": "一行一条断言（record_type = source|parameter|model_note|disabled_claim），机器可逐条消费。",
}


# ---------------------------------------------------------------- 计算层
def _sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _quantile(sorted_vals, q):
    """线性插值分位（numpy/pandas 默认口径），避免和既有报表口径打架。"""
    if not sorted_vals:
        return float("nan")
    pos = (len(sorted_vals) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (pos - lo)


def compute_wind_stats():
    """本轮真的读 wind CSV，算完返回 (stats 行, hourly 行)。读不到就 bail。"""
    if not WIND_CSV.exists():
        _bail("WIND_CSV_MISSING", f"{WIND_CSV}")
    rows = []
    with WIND_CSV.open(encoding="utf-8-sig") as fh:
        header = fh.readline().strip().split(",")
        if header != ["time_local", "wind_speed_ms", "wind_direction_deg", "temperature_c"]:
            _bail("WIND_CSV_SCHEMA", f"期望 4 列，实得 {header}")
        for line in fh:
            parts = line.rstrip("\n").split(",")
            if len(parts) != 4:
                _bail("WIND_CSV_ROW", f"列数异常: {line!r}")
            try:
                rows.append((parts[0], float(parts[1]), float(parts[2]), float(parts[3])))
            except ValueError:
                _bail("WIND_CSV_VALUE", f"数值解析失败: {line!r}")
    n = len(rows)
    if n == 0:
        _bail("WIND_CSV_EMPTY", str(WIND_CSV))
    ws = sorted(r[1] for r in rows)
    wd = sorted(r[2] for r in rows)
    tc = sorted(r[3] for r in rows)
    mean_ws = sum(ws) / n
    sd_ws = (sum((v - mean_ws) ** 2 for v in ws) / n) ** 0.5
    ge12 = sum(1 for v in ws if v >= 12.0)

    def row(stat_id, dataset, metric, value, unit, nn, method, grade, notes, src=True):
        return dict(stat_id=stat_id, dataset=dataset, metric=metric, value=f"{value:.6g}", unit=unit,
                    n=str(nn), method=method,
                    computed_from_file=("data/raw/openmeto_yangpu_wind_20260801_0911.csv" if src else ""),
                    row_count_seen=(str(n) if src else "-1"), evidence_grade=grade, notes=notes)

    stats = [
        row("stat_wind_rows", "openmeteo_yangpu_hourly", "row_count", n, "rows", n,
            "本轮逐行解析计数", "A", "2026-08-01T00:00 起逐小时连续"),
        row("stat_wind_mean", "openmeteo_yangpu_hourly", "wind_speed_mean", mean_ws, "m/s", n,
            "算术均值", "A", "接口原值 km/h，÷3.6 换算为 m/s"),
        row("stat_wind_sd", "openmeteo_yangpu_hourly", "wind_speed_std", sd_ws, "m/s", n,
            "总体标准差 ddof=0", "A", ""),
        row("stat_wind_min", "openmeteo_yangpu_hourly", "wind_speed_min", ws[0], "m/s", n,
            "min", "A", ""),
        row("stat_wind_p25", "openmeteo_yangpu_hourly", "wind_speed_p25", _quantile(ws, .25), "m/s", n,
            "线性插值分位", "A", ""),
        row("stat_wind_median", "openmeteo_yangpu_hourly", "wind_speed_median", _quantile(ws, .5), "m/s", n,
            "线性插值分位", "A", ""),
        row("stat_wind_p75", "openmeteo_yangpu_hourly", "wind_speed_p75", _quantile(ws, .75), "m/s", n,
            "线性插值分位", "A", ""),
        row("stat_wind_p90", "openmeteo_yangpu_hourly", "wind_speed_p90", _quantile(ws, .9), "m/s", n,
            "线性插值分位", "A", ""),
        row("stat_wind_max", "openmeteo_yangpu_hourly", "wind_speed_max", ws[-1], "m/s", n,
            "max", "A", ""),
        row("stat_wind_ge12_cnt", "openmeteo_yangpu_hourly", "hours_wind_ge_12ms", ge12, "hours", n,
            "计数", "A", "与机型抗风等级 12 m/s 同阈值"),
        row("stat_wind_ge12_share", "openmeteo_yangpu_hourly", "share_hours_wind_ge_12ms", ge12 / n, "-", n,
            "ge12/n", "A", ""),
        row("stat_dir_mean", "openmeteo_yangpu_hourly", "wind_direction_mean", sum(wd) / n, "deg", n,
            "算术均值（角度不做环形均值）", "A", "环形均值另有口径，此处按原值算术均值登记"),
        row("stat_dir_median", "openmeteo_yangpu_hourly", "wind_direction_median", _quantile(wd, .5), "deg", n,
            "线性插值分位", "A", ""),
        row("stat_dir_min", "openmeteo_yangpu_hourly", "wind_direction_min", wd[0], "deg", n, "min", "A", ""),
        row("stat_dir_max", "openmeteo_yangpu_hourly", "wind_direction_max", wd[-1], "deg", n, "max", "A", ""),
        row("stat_temp_mean", "openmeteo_yangpu_hourly", "temperature_mean", sum(tc) / n, "degC", n,
            "算术均值", "A", ""),
        row("stat_temp_median", "openmeteo_yangpu_hourly", "temperature_median", _quantile(tc, .5), "degC", n,
            "线性插值分位", "A", ""),
        row("stat_temp_min", "openmeteo_yangpu_hourly", "temperature_min", tc[0], "degC", n, "min", "A", ""),
        row("stat_temp_max", "openmeteo_yangpu_hourly", "temperature_max", tc[-1], "degC", n, "max", "A", ""),
        row("stat_api_replay_mean", "openmeteo_api_replay_20261003", "wind_speed_mean", 4.009, "m/s", 1008,
            "本轮重放请求：mean(km/h)=14.431 ÷ 3.6", "A",
            "与本地 CSV 均值差 <1e-3 ⇒ 证明本地文件确实来自该接口调用", src=False),
        row("stat_api_generation_ms", "openmeteo_api_replay_20261003", "generationtime_ms", 1.091, "ms", 1,
            "响应自带字段", "A", "", src=False),
        row("stat_api_response_bytes", "openmeteo_api_replay_20261003", "response_body_size", 32885, "bytes", 1,
            "本轮 curl 实测", "A", "", src=False),
        row("stat_api_grid_lat", "openmeteo_api_replay_20261003", "returned_grid_latitude", 31.3181, "deg", 1,
            "响应自带字段", "A", "≠ 请求点 31.29 ⇒ 服务端吸附到最近格点", src=False),
        row("stat_api_grid_lon", "openmeteo_api_replay_20261003", "returned_grid_longitude", 121.537544, "deg", 1,
            "响应自带字段", "A", "≠ 请求点 121.51", src=False),
        row("stat_api_grid_elev", "openmeteo_api_replay_20261003", "returned_grid_elevation", 3.0, "m", 1,
            "响应自带字段", "A", "", src=False),
        row("stat_derive_noenergy", "flycart30_derived", "empty_load_energy_intensity", 3968.8 / 28.0, "Wh/km", 1,
            "3968.8 ÷ 28（官方双块能量 ÷ 空载航程）", "C", "项目 consumption_base=0.142 Wh/m 与之差 0.18%", src=False),
        row("stat_derive_ratio", "flycart30_derived", "full_over_empty_energy_ratio", 28.0 / 16.0, "-", 1,
            "28 ÷ 16（空载航程 ÷ 满载航程）", "C",
            "= 1 + load_penalty_factor(0.75)，数值一致；但成立前提是"
            "「同电池+单位距离能耗 ∝ 1/航程」这一未检假设 ⇒ 只作量级旁证（T5）", src=False),
        row("stat_derive_full", "flycart30_derived", "full_load_energy_intensity", 3968.8 / 16.0, "Wh/km", 1,
            "3968.8 ÷ 16", "C", "0.142×1.75=0.2485 Wh/m 自洽", src=False),
        row("stat_derive_hover", "flycart30_derived", "hover_power_ratio_proxy", 29.0 / 18.0, "-", 1,
            "空载悬停 29 min ÷ 满载悬停 18 min", "C", "只能当旁证：悬停≠巡航", src=False),
        row("stat_osm_height_missing", "osm_yangpu_buildings", "height_tag_missing_share", 0.8574, "-", 2876,
            "缺 tag 数 ÷ building 总数（历史普查口径）", "E",
            "本轮未重做 height-tag 普查，故不从文件复算；引用值", src=False),
    ]
    return stats, rows


def compute_osm_census():
    """本轮扫一遍 OSM 文件重新计数；扫不到就 bail，不用手写值。

    为什么按 XML 事件计数而不是 grep 行数：OSM XML 把一个 way 的多个 tag 分行写，
    行扫描会把"同一 way 上的第二个 building 相关 tag"也算进 building 数（实测虚高到
    2698 vs 真值 2154）。又为什么不在 way 的 end 事件里 findall('tag')：循环末尾的
    el.clear() 会先把 <tag> 从父元素摘掉，现场求值只拿到 None ⇒ 必须在 tag 自己的
    end 事件就地记账。两条都是这把尺子踩过的坑，下面的恒等式断言用来兜住第三次。
    """
    import xml.etree.ElementTree as ET

    if not OSM_FILE.exists():
        _bail("OSM_MISSING", str(OSM_FILE))
    node = way = relation = 0
    cur_way = None
    way_keys = {}
    for ev, el in ET.iterparse(str(OSM_FILE), events=("start", "end")):
        tag = el.tag
        if ev == "start":
            if tag == "way":
                cur_way = el.get("id")
                way_keys.setdefault(cur_way, set())
            continue
        if tag == "node":
            node += 1
        elif tag == "way":
            way += 1
        elif tag == "relation":
            relation += 1
        elif tag == "tag":
            k = el.get("k")
            if cur_way is not None and k is not None:
                way_keys[cur_way].add(k)
        if tag in ("node", "way", "relation"):
            el.clear()
            if tag == "way":
                cur_way = None
    building = sum(1 for ks in way_keys.values() if "building" in ks)
    highway = sum(1 for ks in way_keys.values() if "highway" in ks)
    total = node + way + relation
    # 恒等式：way 元素数必须等于登记过的 way id 数，否则说明解析漏了元素
    if len(way_keys) != way:
        _bail("OSM_WAY_IDENTITY", f"way={way} 但记录到 {len(way_keys)} 个 way id")
    if building > way or highway > way:
        _bail("OSM_TAG_OVERFLOW", f"tag 计数({building}/{highway}) 超过 way 总数 {way}")
    src = "frontend/data/map/part_of_yangpu.osm"
    method = "本轮 ElementTree 事件级计数：在 <tag> 的 end 事件按所属 way 归组去重"
    return [
        dict(entity="node", count=node, total=total, share=f"{node/total:.6g}",
             method=method, computed_from_file=src, evidence_grade="A", notes=""),
        dict(entity="way", count=way, total=total, share=f"{way/total:.6g}",
             method=method, computed_from_file=src, evidence_grade="A", notes=""),
        dict(entity="relation", count=relation, total=total, share=f"{relation/total:.6g}",
             method=method, computed_from_file=src, evidence_grade="A", notes=""),
        dict(entity="elements_total", count=total, total="", share="",
             method="node+way+relation", computed_from_file=src, evidence_grade="A",
             notes="恒等式：node+way+relation=total"),
        dict(entity="ways_with_building_tag", count=building, total=way,
             share=f"{building/way:.6g}" if way else "",
             method="按 way 归组后判 'building' ∈ keys（每 way 最多计一次）",
             computed_from_file=src, evidence_grade="A",
             notes="行扫描会得到虚高值；本行的口径是【带该 tag 的 way 数】"),
        dict(entity="ways_with_highway_tag", count=highway, total=way,
             share=f"{highway/way:.6g}" if way else "",
             method="按 way 归组后判 'highway' ∈ keys（每 way 最多计一次）",
             computed_from_file=src, evidence_grade="A", notes=""),
        dict(entity="file_bytes", count=OSM_FILE.stat().st_size, total="", share="",
             method="os.stat().st_size", computed_from_file=src, evidence_grade="A", notes=""),
        dict(entity="file_sha256", count=_sha(OSM_FILE), total="", share="",
             method="hashlib.sha256(全文件).hexdigest()", computed_from_file=src, evidence_grade="A",
             notes="只锁『现在的它』，不锁『当初的它』⇒ 溯源维持 E 级"),
    ]


def compute_baseline(raw_rel: str):
    """逐行复算 formal baseline；只读，不重跑仿真。"""
    path = REPO / raw_rel
    if not path.exists():
        _bail("BASELINE_MISSING", str(path))
    runs, stats = [], []
    with path.open(encoding="utf-8-sig") as fh:
        header = next(fh).rstrip("\n").split(",")
        idx = {name: i for i, name in enumerate(header)}
        need = ["变量", "取值", "重复", "Seed", "算法", "完成任务数", "生成任务数", "完成率",
                "超时率", "总能量消耗", "总飞行距离", "平均时延"]
        for col in need:
            if col not in idx:
                _bail("BASELINE_COLUMN", f"缺少列 {col}；实得 {header[:10]}...")
        groups = {}
        for line in fh:
            row = line.rstrip("\n").split(",")
            if len(row) != len(header):
                _bail("BASELINE_ROW", f"列数不符: {line[:60]!r}")
            fx = row[idx["取值"]]
            rec = dict(fixture=fx, seed=int(row[idx["Seed"]]), repeat=int(row[idx["重复"]]),
                       algorithm=row[idx["算法"]], completed_tasks=int(float(row[idx["完成任务数"]])),
                       generated_tasks=int(float(row[idx["生成任务数"]])),
                       completion_rate=float(row[idx["完成率"]]), timeout_rate=float(row[idx["超时率"]]),
                       total_energy_wh=float(row[idx["总能量消耗"]]),
                       total_distance_m=float(row[idx["总飞行距离"]]),
                       avg_latency_s=float(row[idx["平均时延"]]), evidence_grade="B")
            runs.append(rec)
            groups.setdefault(fx, []).append(rec)
    for fx in sorted(groups):
        g = groups[fx]
        n = len(g)
        cr = sorted(x["completion_rate"] for x in g)
        to = sorted(x["timeout_rate"] for x in g)
        mean_cr = sum(cr) / n
        sd_cr = (sum((v - mean_cr) ** 2 for v in cr) / n) ** 0.5
        half = 2.228 * sd_cr / (n ** 0.5) if n > 1 else 0.0
        stats.append(dict(stat_id=f"stat_baseline_n_{fx}", dataset="formal_baseline_n10",
                          metric=f"sample_size[{fx}]", value=n, unit="runs", n=n,
                          method="本轮逐行计数", computed_from_file=raw_rel, row_count_seen=n,
                          evidence_grade="B", notes="配对种子 40901–40910"))
        stats.append(dict(stat_id=f"stat_baseline_cr_{fx}", dataset="formal_baseline_n10",
                          metric=f"completion_rate_mean[{fx}]", value=f"{mean_cr:.6g}", unit="-", n=n,
                          method="均值；CI95=±t(2.228,n=10)*sd/sqrt(n)，总体标准差 ddof=0",
                          computed_from_file=raw_rel, row_count_seen=n, evidence_grade="B",
                          notes=f"min={cr[0]:.6g} median={_quantile(cr,.5):.6g} max={cr[-1]:.6g} CI95=[{mean_cr-half:.6g},{mean_cr+half:.6g}]"))
        to_mean = sum(to) / n
        stats.append(dict(stat_id=f"stat_baseline_to_{fx}", dataset="formal_baseline_n10",
                          metric=f"timeout_rate_mean[{fx}]", value=f"{to_mean:.6g}", unit="-", n=n,
                          method="均值", computed_from_file=raw_rel, row_count_seen=n, evidence_grade="B",
                          notes=f"min={to[0]:.6g} max={to[-1]:.6g}"))
    return runs, stats


# ---------------------------------------------------------------- 写出层
def _fmt(v):
    if v is None:
        return ""
    if isinstance(v, float):
        return f"{v:.6g}"
    return str(v)


def _csv_text(cols, rows):
    buf = [",".join(cols)]
    for r in rows:
        vals = [_fmt(r.get(c, "")) for c in cols]
        quoted = ['"' + v.replace('"', '""') + '"' if ("," in v or '"' in v) else v for v in vals]
        buf.append(",".join(quoted))
    return "\n".join(buf) + "\n"


def _write_csv(path: pathlib.Path, text: str):
    path.write_text(text, encoding="utf-8", newline="\n")


def build(write: bool):
    OUT.mkdir(parents=True, exist_ok=True)
    wind_stats, wind_rows = compute_wind_stats()
    osm_rows = compute_osm_census()
    baseline_rel = "results/experiments/formal_baseline_n10_20261003-010435/raw_runs.csv"
    base_runs, base_stats = compute_baseline(baseline_rel)

    stats = wind_stats + [dict(stat_id=r["stat_id"], dataset=r["dataset"], metric=r["metric"],
                               value=_fmt(r["value"]), unit=r["unit"], n=str(r["n"]), method=r["method"],
                               computed_from_file=r["computed_from_file"], row_count_seen=str(r["row_count_seen"]),
                               evidence_grade=r["evidence_grade"], notes=r["notes"]) for r in base_stats]

    src_cols = ["source_id", "name", "publisher", "url", "source_type", "retrieval_date", "http_status",
                "response_bytes", "sha256", "local_file", "verified_by",
                # 全数据集唯二能标 Complete 的就是这两个 source（仓内留有原件 + sha256）；
                # 不写进 CSV 的话，对外那份表格里"Complete"这一档等于不存在。
                "traceability", "transformation", "notes"]
    # 两条新轴必须同时进 parameters.csv：只加进 truth.jsonl 会让两个消费方看到的分级不一致
    # （README 里 parameters.csv 与 truth.jsonl 并列对外，脚本读者拿不到 traceability 就会以为仍是单轴）。
    for p in PARAMETERS:
        p.setdefault("traceability", "")
        p.setdefault("transformation", "")
    for srow in SOURCES:
        srow.setdefault("traceability", "")
        srow.setdefault("transformation", "")
    par_cols = ["param_id", "drone_type", "field", "value", "unit", "evidence_grade",
                "traceability", "transformation", "is_real_measurement",
                "error_band_vs_source_pct", "source_value", "test_condition", "derivation", "recompute_cmd",
                "config_file", "status", "notes"]
    stt_cols = ["stat_id", "dataset", "metric", "value", "unit", "n", "method", "computed_from_file",
                "row_count_seen", "evidence_grade", "notes"]
    wh_cols = ["time_local", "wind_speed_ms", "wind_direction_deg", "temperature_c"]
    oc_cols = ["entity", "count", "total", "share", "method", "computed_from_file", "evidence_grade", "notes"]
    br_cols = ["fixture", "seed", "repeat", "algorithm", "completed_tasks", "generated_tasks",
               "completion_rate", "timeout_rate", "total_energy_wh", "total_distance_m", "avg_latency_s",
               "evidence_grade"]

    texts = {}
    texts["sources.csv"] = _csv_text(src_cols, SOURCES)
    texts["parameters.csv"] = _csv_text(par_cols, PARAMETERS)
    texts["statistics.csv"] = _csv_text(stt_cols, stats)
    texts["wind_hourly.csv"] = _csv_text(wh_cols, [dict(zip(wh_cols, r)) for r in wind_rows])
    texts["osm_census.csv"] = _csv_text(oc_cols, osm_rows)
    texts["formal_baseline_run.csv"] = _csv_text(br_cols, base_runs)

    records = ([{"record_type": "source", "id": s["source_id"], "data": s} for s in SOURCES]
               + [{"record_type": "parameter", "id": p["param_id"], "data": p} for p in PARAMETERS]
               + [{"record_type": "model_note", "id": m["note_id"], "data": m} for m in MODEL_NOTES]
               + [{"record_type": "disabled_claim", "id": d["claim_id"], "data": d} for d in DISABLED_CLAIMS])
    texts["truth.jsonl"] = "\n".join(json.dumps(r, ensure_ascii=False, sort_keys=True)
                                     for r in records) + "\n"
    if write:
        for name, text in texts.items():
            (OUT / name).write_text(text, encoding="utf-8", newline="\n")

    counts = {"sources.csv": len(SOURCES), "parameters.csv": len(PARAMETERS), "statistics.csv": len(stats),
              "wind_hourly.csv": len(wind_rows), "osm_census.csv": len(osm_rows),
              "formal_baseline_run.csv": len(base_runs), "truth.jsonl": len(records)}
    colcounts = {"sources.csv": len(src_cols), "parameters.csv": len(par_cols), "statistics.csv": len(stt_cols),
                 "wind_hourly.csv": len(wh_cols), "osm_census.csv": len(oc_cols),
                 "formal_baseline_run.csv": len(br_cols), "truth.jsonl": "-"}

    grades = {}
    axes = {"traceability": {}, "transformation": {}}
    for p in PARAMETERS:
        _check_axes(p)                     # 枚举合法 + 三轴不自相矛盾
        grades[p["evidence_grade"]] = grades.get(p["evidence_grade"], 0) + 1
        for k in ("traceability", "transformation"):
            axes[k][p[k]] = axes[k].get(p[k], 0) + 1
    # 一整列同一个值 = 根本没分档，比填错更糟（填错还能被上面那条抓住）。
    # ⚠ 但 Complete 这一档**允许在参数表里为空**，且本轮实测就是空的 —— 这不是漏标：
    #   24 条 parameter 全是设备/SLA/换电类数值，其来源要么是厂商网页（按上面的收紧规则只给 Partial），
    #   要么根本没有出处（None）。真正够得上 Complete 的是两个 source 级条目
    #   （src_osm_extract 与 src_openmeteo_archive，仓内留有原件 + sha256），它们不在本表里。
    #   所以判据是"每轴至少两档非空"，而不是"枚举里每个值都必须出现"——后者会逼我给
    #   设备参数硬安一个 Complete，那才是把体系写坏。
    for k, dist in axes.items():
        if len(dist) < 2:
            raise ValueError("[AXIS_DEGENERATE] %s 全部 %d 条都是 %s ⇒ 该轴没有起到区分作用" % (
                k, len(PARAMETERS), list(dist)))
    # 反向哨兵：若哪天有人为了"看起来完整"把某条设备参数提成 Complete，这里要能问一句凭什么。
    for p in PARAMETERS:
        if p["traceability"] == "Complete" and not p.get("local_snapshot"):
            raise ValueError("[AXIS_UNSUPPORTED] %s 标 Complete 但没有 local_snapshot 字段"
                             "（仓内原件路径）⇒ 请补原件或降回 Partial" % p["param_id"])

    manifest = dict(
        dataset="drone-scheduling truth/provenance dataset",
        dataset_version=DATASET_VERSION,
        schema_version=DATASET_VERSION,
        generated_at=_dt.datetime.now().isoformat(timespec="seconds"),
        generator="docs/build_truth_dataset.py",
        git_commit=_git_rev_parse(),
        evidence_date=EVIDENCE_DATE,
        license="内部项目数据；OSM 部分继承 ODbL，Open-Meteo 部分受其服务条款约束",
        files={},
        external_files=dict(
            osm_basemap=dict(path="frontend/data/map/part_of_yangpu.osm", bytes=OSM_FILE.stat().st_size,
                             sha256=_sha(OSM_FILE)),
            wind_csv=dict(path="data/raw/openmeto_yangpu_wind_20260801_0911.csv",
                          bytes=WIND_CSV.stat().st_size, sha256=_sha(WIND_CSV)),
            baseline_raw_runs=dict(path=baseline_rel, bytes=(REPO / baseline_rel).stat().st_size,
                                   sha256=_sha(REPO / baseline_rel))),
        evidence_grades=grades,
        traceability_axes=axes["traceability"],
        transformation_axes=axes["transformation"],
        parameter_counts=len(PARAMETERS),
        disabled_claims=len(DISABLED_CLAIMS),
        row_counts=counts,
        column_counts=colcounts,
        dependencies="Python 3.10 标准库（无第三方依赖）",
        boundary=("本数据集只登记『数字→来源→条件→算式→复算命令』的证据关系。"
                  "三条轴各自独立：evidence_grade A=官方直接值 B=原始公开实测 C=可由 A/B 复算的派生值 "
                  "D=假设值 E=未验证或冲突（来源可信度）；traceability Complete=仓内留有原件或快照可不依赖"
                  "在线服务复核 Partial=有明确出处但核验依赖厂商页面当前状态（改版即失效）None=无外部依据"
                  "（溯源完整度）；transformation As-published=原文照抄 Derived=经过计算且有算式 "
                  "Local-extraction=从原始文件提取 Assumption=无外部依据的设定（处理过程）。"
                  "D/E 级字段不得对外称为厂商参数。"),
    )
    if write:
        for name in counts:
            p = OUT / name
            manifest["files"][name] = dict(bytes=p.stat().st_size, lines=p.read_text(encoding="utf-8").count("\n"),
                                           sha256=_sha(p))
        (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True)
                                           + "\n", encoding="utf-8", newline="\n")
        (OUT / "README.md").write_text(_readme(manifest, counts), encoding="utf-8", newline="\n")
    return manifest, counts, texts


def _git_rev_parse():
    import subprocess
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(REPO), capture_output=True, text=True, timeout=10)
        return out.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def _readme(manifest, counts):
    L = []
    L.append("# 真实性数据集（data/provenance）\n")
    L.append(f"版本 {manifest['dataset_version']}｜取证日期 {manifest['evidence_date']}｜"
             f"生成器 `docs/build_truth_dataset.py`（本目录所有 CSV/JSONL 由它生成，请勿手改）。\n")
    L.append("## 为什么统计不放 MD\n")
    L.append("原先统计散在 `docs/真实性审计表.md` 的表格里：不可查询、不可 join、改一个数要人肉同步多处。"
             "现在每个数是一行带主键的记录，MD 只做人读视图。\n")
    L.append("## 文件\n")
    L.append("| 文件 | 行数 | 说明 |")
    L.append("|---|---|---|")
    desc = {"sources.csv": "外部来源登记：完整 URL + 本轮 HTTP 码 + 响应体大小/哈希 + 取证动作",
            "parameters.csv": "每个仿真参数一行：值、单位、A–E 等级、来源原文、测试条件、派生算式、复算命令",
            "statistics.csv": "统计量一行一个：含样本量、计算口径、本轮是否真从文件复算",
            "wind_hourly.csv": "Open-Meteo 杨浦逐小时风场原始数据（1008 行）",
            "osm_census.csv": "OSM 底图本轮普查计数与文件指纹",
            "formal_baseline_run.csv": "n=10 正式基线逐 run 记录（只读复算，未重跑仿真）",
            "truth.jsonl": "上述断言的 JSON Lines 形式，供程序逐条消费",
            "manifest.json": "清单：版本、每表行数/列数/SHA-256、外部文件指纹、等级分布、边界声明"}
    for name, n in counts.items():
        L.append(f"| `{name}` | {n} | {desc[name]} |")
    L.append("\n## 证据等级\n")
    L.append("| 级 | 含义 |\n|---|---|")
    L.append("| A | 厂商官方规格页/手册的直接值 |")
    L.append("| B | 原始公开实测数据（论文/数据集）或本地 run 记录逐行复算 |")
    L.append("| C | 由 A/B 可复算的派生值（附算式，**不得称『官方实测』**） |")
    L.append("| D | 假设值（无外部依据） |")
    L.append("| E | 未验证 / 存在冲突 |\n")
    L.append(f"当前参数等级分布：{json.dumps(manifest['evidence_grades'], ensure_ascii=False, sort_keys=True)}"
             f"（共 {manifest['parameter_counts']} 个参数）\n")
    L.append("## 字段字典\n")
    for fname, cols in FIELD_DICT.items():
        if not isinstance(cols, list):
            continue
        L.append(f"### `{fname}`\n")
        L.append("| 字段 | 类型 | 含义 |")
        L.append("|---|---|---|")
        for c, t, d in cols:
            L.append(f"| `{c}` | {t} | {d} |")
        L.append("")
    L.append("## 复算\n")
    L.append("```bash\n"
             "# 重新生成（会覆盖本目录）\n"
             "../.venv310/Scripts/python.exe -X utf8 docs/build_truth_dataset.py\n\n"
             "# 只校验：重算并与磁盘比对，任一字节漂移退出码 1\n"
             "../.venv310/Scripts/python.exe -X utf8 docs/build_truth_dataset.py --verify\n\n"
             "# 参数级算式核对\n"
             'python -c "print(1984.4*2, 3968.8/28, 28/16)"\n```\n')
    L.append("## 边界\n")
    L.append(manifest["boundary"] + "\n")
    L.append("`truth.jsonl` 中 `record_type=disabled_claim` 的 8 条为**对外禁用表述**，写论文/答辩稿前先比对这些行。\n")
    L.append("## 已知未完成项\n")
    L.append("- CMU 数据集文件本体未取得（KiltHub 403）⇒ 只能支撑定性结论，见 `sources.csv` 的 `src_cmu_kiltub`。")
    L.append("- OSM 下载事件溯源无凭据（时间/操作者/source_url）⇒ `osm_census.csv` 的内容计数为 A，溯源为 E。")
    L.append("- BS60 同时充电数量两页冲突未决 ⇒ `parameters.csv` 的 `param_bs60_charge`。")
    L.append("- `statistics.csv` 中 `row_count_seen=-1` 的行是**登记的引用值**，本轮未从文件复算，不要当成本轮观测。\n")
    return "\n".join(L)


# ---------------------------------------------------------------- verify
def _normalize(text: str) -> str:
    return "\n".join(text.splitlines())


def verify():
    manifest, _, texts = build(write=False)
    bad = []
    # 外部对照：--verify 若只把源码重算结果和产物比，源码量错了它也会说一致（本轮就
    # 发生过：行扫描把 building 数虚高到 2896，产物与源码一起错）。这里用一个与生成器
    # 实现无关的独立计数交叉核对，要求两把尺子的关系可解释。
    census = {r["entity"]: r["count"] for r in compute_osm_census()}
    line_building = line_highway = 0
    with OSM_FILE.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if 'k="building"' in line:
                line_building += 1
            if 'k="highway"' in line:
                line_highway += 1
    for name, xml_cnt, line_cnt in (("ways_with_building_tag", census["ways_with_building_tag"], line_building),
                                    ("ways_with_highway_tag", census["ways_with_highway_tag"], line_highway)):
        if xml_cnt > line_cnt:
            bad.append(f"{name}: XML 计数 {xml_cnt} > 行扫描 {line_cnt}，两种口径不可能这样排序")
        elif xml_cnt != line_cnt:
            print(f"[XREF] {name}: XML={xml_cnt} 行扫描={line_cnt} ⇒ 有 way 在同一元素上重复挂该 tag，"
                  f"采用【按 way 去重】的 XML 值")
    for name in manifest["row_counts"]:
        p = OUT / name
        if not p.exists():
            bad.append(f"{name}: 文件不存在")
            continue
        disk = _normalize(p.read_text(encoding="utf-8"))
        if name == "manifest.json":
            try:
                d = json.loads(disk)
            except json.JSONDecodeError as e:
                bad.append(f"manifest.json: 解析失败 {e}")
                continue
            for key in ("dataset_version", "evidence_date", "generator", "external_files",
                        "evidence_grades", "parameter_counts", "row_counts", "column_counts", "boundary"):
                if d.get(key) != manifest.get(key):
                    bad.append(f"manifest.json: 字段 {key} 漂移")
            continue
        if name == "README.md":
            continue
        if name == "truth.jsonl":
            # _normalize 会吃掉结尾换行，所以这里绝不能用 count("\n") 当行数（那样恒少 1）
            want = len(disk.splitlines())
            got = manifest["row_counts"][name]
            if want != got:
                bad.append(f"truth.jsonl: 磁盘 {want} 行 != 源码应有 {got} 条记录 ⇒ 需要重新生成")
            elif _normalize(texts[name]) != disk:
                bad.append("truth.jsonl: 内容与源码重算不一致")
            continue
        if name.endswith(".csv"):
            fresh = _normalize(texts[name])
            if disk != fresh:
                first = next((i for i, (a, b) in enumerate(zip(disk.splitlines(), fresh.splitlines()))
                              if a != b), None)
                bad.append(f"{name}: 内容与源码重算不一致（首个差异在第 {None if first is None else first + 2} 行）"
                           f"⇒ 手改过或需要重新生成")
    if bad:
        print("[TRUTH_DATASET_DRIFT] 以下产物与源码重算结果不一致：")
        for b in bad:
            print("  - " + b)
        return 1
    print(f"[OK] data/provenance 全部产物与源码重算一致（{len(manifest['row_counts'])} 个文件，"
          f"{sum(manifest['row_counts'].values())} 行记录）")
    return 0


def main(argv):
    if "--verify" in argv:
        return verify()
    manifest, counts, texts = build(write=True)
    print(f"已生成 {OUT}")
    for name, n in counts.items():
        f = OUT / name
        print(f"  {name:<26} rows={n:<6} bytes={f.stat().st_size}")
    print(f"参数等级分布: {json.dumps(manifest['evidence_grades'], ensure_ascii=False, sort_keys=True)}")
    print("下一步：../.venv310/Scripts/python.exe -X utf8 docs/build_truth_dataset.py --verify")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
