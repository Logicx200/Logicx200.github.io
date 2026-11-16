# -*- coding: utf-8 -*-
import csv, os

HERE = os.path.dirname(os.path.abspath(__file__))

SCEN = {
    "Dunhuang": ("沙漠背景 / 浮尘", "塔克拉玛干沙漠东缘（敦煌）"),
    "Minqin": ("沙漠背景 / 浮尘", "巴丹吉林—腾格里沙漠边缘（民勤）"),
    "Dalanzadgad": ("沙漠背景 / 浮尘", "蒙古高原戈壁（Dalanzadgad）"),
    "Kashi": ("沙漠沙尘事件", "塔里木盆地西缘（喀什）"),
    "SACOL": ("乡村清洁", "黄土高原半干旱乡村（SACOL）"),
    "XiangHe": ("乡村农业 / 燃烧", "华北平原农业区（香河）"),
    "Taihu": ("乡村 / 城市混合", "长江三角洲（太湖）"),
    "Beijing": ("城市 / 工业", "京津冀城市群（北京）"),
    "SONET_Shanghai": ("城市 / 近岸", "长江三角洲城市与近岸（上海）"),
    "Hong_Kong_PolyU": ("海岛 / 近岸污染", "珠三角城市近岸（香港）"),
    "Dongsha_Island": ("海岛 / 海洋清洁", "南海北部岛屿（东沙岛）"),
    "Lanai": ("海岛 / 海洋清洁", "太平洋远洋岛屿（Lanai）"),
    "Nauru": ("海岛 / 海洋清洁", "热带太平洋（瑙鲁）"),
    "Lhasa": ("高原清洁 / 低水汽", "青藏高原（拉萨）"),
    "Alta_Floresta": ("乡村农业 / 燃烧", "亚马逊农业燃烧（全球对照）"),
    "Solar_Village": ("沙漠沙尘事件", "阿拉伯半岛强沙尘（全球对照）"),
}

rows = []
with open(os.path.join(HERE, "_power_summary.csv"), "r", encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        scen, region = SCEN[r["site"]]
        rows.append({
            "工况类别": scen,
            "站点/区域": region,
            "AERONET站名": r["site"],
            "经度": r["lon"],
            "纬度": r["lat"],
            "PWV中位_cm": r["pw_med"],
            "PWV_p10_cm": r["pw_p10"],
            "PWV_p90_cm": r["pw_p90"],
            "AOD550中位": r["aod_med"],
            "AOD550_p10": r["aod_p10"],
            "AOD550_p90": r["aod_p90"],
            "样本天数": r["n"],
            "数据源": "MERRA-2/CERES (NASA POWER, 2015-2024 逐日)",
            "备注": "",
        })

# 标注同格点问题
for r in rows:
    if r["AERONET站名"] in ("XiangHe", "Beijing"):
        r["备注"] = "MERRA-2 0.5°网格下香河与北京同格点，城乡差异需 AERONET 原始数据"
    if r["AERONET站名"] == "Dongsha_Island":
        r["备注"] = "受亚洲大陆输送影响，清洁日 AOD 约 0.12"
    if r["AERONET站名"] in ("Lanai", "Nauru"):
        r["备注"] = "远洋清洁对照"

out = os.path.join(HERE, "典型观测区_MERRA2气候值.csv")
with open(out, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)
print("saved:", out)
