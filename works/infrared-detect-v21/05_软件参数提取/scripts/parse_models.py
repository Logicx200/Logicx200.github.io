# -*- coding: utf-8 -*-
"""
解析 D:\\XGGDCOSSim2 中的模型库/想定/配置参数 -> models.json（只读源文件）
=====================================================================
输入(均来自 _decoded/ 下的 UTF-8 副本，副本由 scripts\\decode_files.py 生成):
  Data\\SystemBaseFile\\DefaultPlanFile.xml          默认想定(时空/气象/传感器/背景/目标/干扰/导弹)
  Data\\SystemBaseFile\\DefaultModelDatabase.xml     默认模型库(枚举 tips 原文)
  Data\\SystemBaseFile\\ModelDatabase.xml            模型数据库(实际模型清单)
  Data\\ModelData\\Target\\*\\Config.ini             目标模型坐标/波段/温度参数
  Data\\ModelData\\Background\\yngd\\Config.ini      背景模型参数
  Data\\*.osg                                       模型顶点包围盒(近似)
输出:
  F:\\DeepSeek工作区\\软件参数提取\\models.json
  F:\\DeepSeek工作区\\软件参数提取\\_reports\\models_autogen.md
用法: python scripts\\parse_models.py
"""
import os
import re
import json
import xml.etree.ElementTree as ET

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEC = os.path.join(BASE, "_decoded")
REP = os.path.join(BASE, "_reports")
SRC = r"D:\XGGDCOSSim2"
os.makedirs(REP, exist_ok=True)

XML_FILES = {
    "DefaultPlanFile": os.path.join(DEC, "Data__SystemBaseFile__DefaultPlanFile.xml.utf8.txt"),
    "DefaultModelDatabase": os.path.join(DEC, "Data__SystemBaseFile__DefaultModelDatabase.xml.utf8.txt"),
    "ModelDatabase": os.path.join(DEC, "Data__SystemBaseFile__ModelDatabase.xml.utf8.txt"),
}

CONFIG_INI = {
    "target": [
        ("F16", "Data/ModelData/Target/F16/Config.ini"),
        ("f22", "Data/ModelData/Target/f22/Config.ini"),
        ("nimitz", "Data/ModelData/Target/nimitz/Config.ini"),
        ("hm", "Data/ModelData/Target/hm/Config.ini"),
        ("agzfsc", "Data/ModelData/Target/agzfsc/Config.ini"),
        ("albk", "Data/ModelData/Target/albk/Config.ini"),
    ],
    "background": [
        ("yngd", "Data/ModelData/Background/yngd/Config.ini"),
    ],
}

# osc 模型 -> 目录
OSG_MODELS = {
    "F16": "Data/ModelData/Target/F16/f16_vis.osg",
    "f22": "Data/ModelData/Target/f22/f22_vis.osg",
    "nimitz": "Data/ModelData/Target/nimitz/nimitz_vis.osg",
    "hm": "Data/ModelData/Target/hm/hm_vis.osg",
    "agzfsc": "Data/ModelData/Target/agzfsc/agzfsc_vis.osg",
    "albk": "Data/ModelData/Target/albk/albk_vis.osg",
    "yngd": "Data/ModelData/Background/yngd/yonaguni_vis.osg",
}


# ---------------------------------------------------------------- XML 解析
def parse_xml(path):
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    # 去掉 XML 声明以外的注释不影响 ET；直接解析
    return ET.fromstring(text)


def elem_to_dict(el):
    """递归转 dict: 属性 -> @key, 子元素 -> key(单值或 list), 文本 -> #text"""
    d = {}
    for k, v in el.attrib.items():
        d["@" + k] = v
    children = list(el)
    if children:
        for c in children:
            val = elem_to_dict(c)
            if c.tag in d:
                if not isinstance(d[c.tag], list):
                    d[c.tag] = [d[c.tag]]
                d[c.tag].append(val)
            else:
                d[c.tag] = val
    txt = (el.text or "").strip()
    if txt and not children:
        d["#text"] = txt
    # 只有一个子元素 tips 时，把 tips 文本提为 tips 字段
    if children and len(children) == 1 and children[0].tag == "tips":
        d["tips"] = (children[0].text or "").strip()
        del d["tips"]
        d["tips"] = (children[0].text or "").strip()
    return d


def find(node, path):
    return node.find(path)


def collect_tips_enums(root):
    """收集所有带枚举说明的参数：
    - 子元素 <tips>文本</tips>（DefaultPlanFile 风格）
    - 属性 tips="..."（模型库 XML 风格）
    含 remark 原文 / tips 原文 / value / 风格(style)
    """
    out = []
    for el in root.iter():
        tips_el = el.find("tips")
        tips_attr = el.attrib.get("tips")
        if tips_el is not None:
            out.append({
                "tag": el.tag,
                "remark": el.attrib.get("remark", ""),
                "value": el.attrib.get("value", ""),
                "tips": (tips_el.text or "").strip(),
                "style": "child-element",
            })
        elif tips_attr:
            out.append({
                "tag": el.tag,
                "remark": el.attrib.get("remark", ""),
                "value": el.attrib.get("value", ""),
                "tips": tips_attr.strip(),
                "style": "attribute",
            })
    # 记录父路径，便于去重/定位
    parent = {c: p for p in root.iter() for c in p}
    els = [e for e in root.iter()
           if e.find("tips") is not None or e.attrib.get("tips")]
    for rec, el in zip(out, els):
        chain = []
        cur = el
        while cur in parent:
            cur = parent[cur]
            chain.append(cur.tag)
        rec["path"] = "/" + "/".join(reversed(chain)) + "/" + el.tag
    return out


def dedup_enums(items):
    """同 tag+tips 合并，保留出现位置"""
    merged = {}
    for it in items:
        key = (it["tag"], it["tips"])
        if key not in merged:
            merged[key] = dict(it)
            merged[key]["paths"] = [it["path"]]
            merged[key]["values_seen"] = [it["value"]]
        else:
            merged[key]["paths"].append(it["path"])
            if it["value"] not in merged[key]["values_seen"]:
                merged[key]["values_seen"].append(it["value"])
    return list(merged.values())


def tips_to_map(tips):
    """'1:沙漠 2:戈壁 ...' -> {'1':'沙漠', ...}"""
    m = {}
    for part in re.split(r"[；;]\s*", tips):
        for seg in re.findall(r"(\d+)\s*[:：]\s*([^0-9:：]+)", part):
            m[seg[0]] = seg[1].strip()
    return m


# ---------------------------------------------------------------- INI 解析
def parse_ini_with_comments(path):
    sections = {}
    cur = None
    pending_comment = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            s = line.rstrip("\n")
            st = s.strip()
            if not st:
                pending_comment = []
                continue
            if st.startswith("#") or st.startswith(";"):
                pending_comment.append(st.lstrip("#;").strip())
                continue
            if st.startswith("[") and st.endswith("]"):
                cur = st[1:-1]
                sections[cur] = {}
                pending_comment = []
                continue
            if "=" in st and cur is not None:
                k, v = st.split("=", 1)
                sections[cur][k.strip()] = {
                    "value": v.strip(),
                    "comment": " ".join(pending_comment),
                }
                pending_comment = []
    return sections


# ---------------------------------------------------------------- OSG 包围盒
def osg_bbox(path, max_bytes=None):
    """流式解析 OSG ascii 中所有 Vec3Array 顶点，返回局部包围盒与统计"""
    if not os.path.exists(path):
        return {"status": "missing"}
    size = os.path.getsize(path)
    mn = [float("inf")] * 3
    mx = [float("-inf")] * 3
    n_vert = 0
    n_array = 0
    prim = []
    big = max_bytes is not None and size > max_bytes
    buf = []
    with open(path, "r", encoding="latin-1", errors="replace") as f:
        pending = 0
        for line in f:
            if pending > 0:
                parts = line.split()
                if len(parts) >= 3:
                    try:
                        x, y, z = float(parts[0]), float(parts[1]), float(parts[2])
                    except ValueError:
                        pending = 0
                        continue
                    n_vert += 1
                    if x < mn[0]: mn[0] = x
                    if y < mn[1]: mn[1] = y
                    if z < mn[2]: mn[2] = z
                    if x > mx[0]: mx[0] = x
                    if y > mx[1]: mx[1] = y
                    if z > mx[2]: mx[2] = z
                pending -= 1
                continue
            m = re.search(r"VertexArray\s+Vec3Array\s+(\d+)", line)
            if m:
                n_array += 1
                pending = int(m.group(1))
                continue
            m = re.search(r"DrawArrays\s+(\w+)\s+(\d+)\s+(\d+)", line)
            if m and len(prim) < 40:
                prim.append(f"{m.group(1)}:{m.group(3)}")
            elif re.search(r"DrawElements\s+(\w+)\s+(\d+)", line) and len(prim) < 40:
                mm = re.search(r"DrawElements\s+(\w+)\s+(\d+)", line)
                prim.append(f"{mm.group(1)}(idx):{mm.group(2)}")
    res = {
        "status": "ok",
        "file": os.path.relpath(path, SRC).replace("\\", "/"),
        "bytes": size,
        "n_vec3_arrays": n_array,
        "n_vertices": n_vert,
        "primitive_samples": prim,
    }
    if n_vert:
        res["bbox_local"] = {
            "min": [round(v, 4) for v in mn],
            "max": [round(v, 4) for v in mx],
            "size": [round(mx[i] - mn[i], 4) for i in range(3)],
            "center": [round((mx[i] + mn[i]) / 2, 4) for i in range(3)],
            "unit_assumption": "OSG 局部坐标，未做变换(文件中无 MatrixTransform)；通常 1 单位=1 m，但需外部标定",
        }
    else:
        res["bbox_local"] = None
    return res


# ---------------------------------------------------------------- 主流程
def main():
    out = {
        "generated_by": "scripts/parse_models.py",
        "source_root": SRC,
        "note": "只读解析 D:\\XGGDCOSSim2，未修改源文件；枚举/参数均为软件原始定义",
        "sources": {},
        "enums": {},
        "default_plan": {},
        "model_database": {},
        "models": [],
        "bounding_boxes": {},
    }

    roots = {}
    for name, p in XML_FILES.items():
        if os.path.exists(p):
            roots[name] = parse_xml(p)
            out["sources"][name] = {
                "decoded_copy": os.path.relpath(p, BASE),
                "orig": os.path.join(SRC, "Data", "SystemBaseFile", name + ".xml"),
                "encoding": {"DefaultPlanFile": "GB2312/GB18030",
                             "DefaultModelDatabase": "GB2312 声明, 实际 UTF-8 兼容",
                             "ModelDatabase": "UTF-8"}[name],
            }
        else:
            out["sources"][name] = {"error": "decoded copy missing"}

    # ---- 1. 全部枚举 (tips 原文) ----
    all_enums = []
    for name, r in roots.items():
        for it in collect_tips_enums(r):
            it["source"] = name
            all_enums.append(it)
    ded = dedup_enums(all_enums)
    for it in ded:
        it["enum_map"] = tips_to_map(it["tips"])
    out["all_tips_enums"] = ded

    key_enum_map = {
        "bg_type": ("Type", "1:沙漠"),
        "bg_class": ("Class", "1:地面背景"),
        "target_type": ("TargetType", "1:地面静止目标"),
        "entity_class": ("EntityClass", "1:目标"),
        "jam_type": ("JamType", "1:直射阳光"),
        "jam_class": ("JamClass", "1：阳光干扰"),
        "jam_impl_type": ("ImplType", "1:贴图"),
        "sensor_type": ("SensorType", "4:可见光"),
        "sensor_class": ("SensorClass", "1：中波红外"),
        "bg_class_plan": ("BgClass", "1：地面背景"),
        "bg_type_plan": ("BgType", "1：沙漠"),
        "weather_type": ("WeatherType", "0：晴天"),
        "aerosol": ("AtmAerosol", "0：干净大陆"),
        "atm_mode": ("AtmMode", "0：美国标准大气"),
        "imaga_band1": ("ImagBand1Class", "0：无"),
        "laser_band": ("LaserBandClass", "0：无"),
        "bit_width": ("BitWidth", "1：8位"),
        "colourful": ("Colourful", "1:彩色"),
        "img_out_injection": ("ImgOutModeInjection", "1：显卡"),
        "cloud_class": ("CloudClass", "0：无云"),
        "guid_mod1_class": ("GuidMod1Class", "0：无"),
        "guid_band": ("GuidMod1Band", "1：可见光"),
        "missile_class": ("MissileClass", "1：弹道导弹"),
        "miss_plat_class": ("MissPlatClass", "1：陆基"),
        "las_waveband": ("LasWavebandType", "1：紫外"),
    }
    for out_key, (tag, hint) in key_enum_map.items():
        cands = [e for e in ded if e["tag"] == tag and hint in e["tips"]]
        if not cands:
            cands = [e for e in ded if e["tag"] == tag]
        if cands:
            out["enums"][out_key] = {
                "tag": tag,
                "remark": cands[0]["remark"],
                "tips": cands[0]["tips"],
                "enum_map": cands[0]["enum_map"],
                "sources": sorted(set(c["source"] for c in cands)),
                "paths": cands[0]["paths"][:6],
            }
            if out_key == "jam_type":
                # 干扰类型有两套：模型库(1~13) / 想定(1~18)，全部保留
                out["enums"]["jam_type_all_variants"] = [
                    {"tips": e["tips"], "enum_map": e["enum_map"],
                     "sources": sorted(set(c["source"] for c in ded if c["tag"] == tag and c["tips"] == e["tips"]))}
                    for e in ded if e["tag"] == tag
                ]

    # 按 tag 汇总所有枚举变体（便于另一个模型查全）
    by_tag = {}
    for e in ded:
        by_tag.setdefault(e["tag"], []).append({
            "remark": e["remark"],
            "tips": e["tips"],
            "enum_map": e["enum_map"],
            "style": e["style"],
            "sources": sorted(set(c["source"] for c in ded if c["tag"] == e["tag"] and c["tips"] == e["tips"])),
            "paths": e["paths"][:6],
        })
    out["enums_by_tag"] = by_tag

    # ---- 2. 默认想定关键参数 ----
    dp = roots.get("DefaultPlanFile")
    if dp is not None:
        def txt(path, default=None):
            e = dp.find(path)
            if e is None:
                return default
            v = e.attrib.get("value")
            if v is None:
                v = (e.text or "").strip()
            return v

        def section(path):
            e = dp.find(path)
            return elem_to_dict(e) if e is not None else {}

        out["default_plan"] = {
            "SpaceParam": section("SpaceParam"),
            "WeatherParam": section("WeatherParam"),
            "SensorParam": section("SensorParam"),
            "BGParam": section("BGParam"),
            "TargetJamPlatParam": section("TargetJamPlatParam"),
            "JamParam.CommonParam": section("JamParam/JamID/CommonParam"),
            "MissileWeapon.PlatformInfo": section("MissileWeapon/MissPlatID/MissilePlatformInfo"),
            "MissileWeapon.Missiles": section("MissileWeapon/MissPlatID/Missiles"),
            "MissileWeapon.DYTParam": section("MissileWeapon/MissPlatID/Missiles/DYTParam"),
            "scenario_code": txt("SpaceParam/ScenarioCode"),
        }

    # ---- 3. 模型数据库 ----
    mdb = roots.get("ModelDatabase")
    dmd = roots.get("DefaultModelDatabase")
    for name, r in (("ModelDatabase", mdb), ("DefaultModelDatabase", dmd)):
        if r is None:
            continue
        md = {}
        for grp, tags in [
            ("background", ["BGModel/SubBGInfo"]),
            ("jam", ["JamModel/SubJamInfo"]),
            ("target", ["TargetModel/SubTargetInfo"]),
            ("sensor", ["SensorModel/SubSensorInfo"]),
            ("missile_launch_platform", ["MissileLaunchPlatformModel/SubMissileLaunchPlatInfo"]),
            ("missile", ["MissileModel/SubMissileInfo"]),
        ]:
            items = []
            for path in tags:
                for el in r.findall(path):
                    items.append(elem_to_dict(el))
            if items:
                md[grp] = items
        out["model_database"][name] = md

    # ---- 4. 模型 Config.ini + 包围盒 ----
    for kind, lst in CONFIG_INI.items():
        for tag, rel in lst:
            p = os.path.join(SRC, rel.replace("/", "\\"))
            if not os.path.exists(p):
                out["models"].append({"tag": tag, "kind": kind, "status": "missing", "path": rel})
                continue
            # 直接用 decode 后的副本（若存在）
            dec_name = rel.replace("/", "__") + ".utf8.txt"
            dec = os.path.join(DEC, dec_name)
            src = dec if os.path.exists(dec) else p
            secs = parse_ini_with_comments(src)
            cfg = {k: v["value"] for k, v in secs.get("Config", {}).items()}
            param = {k: v["value"] for k, v in secs.get("Parameter", {}).items()}
            param_comments = {k: v["comment"] for k, v in secs.get("Parameter", {}).items()}
            model = {
                "tag": tag, "kind": kind,
                "source_dir": os.path.dirname(rel).replace("/", "\\"),
                "status": "ok",
                "ModelName": cfg.get("ModelName"),
                "ModelCategory": cfg.get("ModelCategory"),
                "Longitude": cfg.get("Longitude"),
                "Latitude": cfg.get("Latitude"),
                "Elevation": cfg.get("Elevation"),
                "BigModelFile": cfg.get("BigModelFile"),
                "SmallModelFile": cfg.get("SmallModelFile"),
                "VisTexture": cfg.get("VisTexture", ""),
                "InfraredRatio": cfg.get("InfraredRatio"),
                "VisibleRatio": cfg.get("VisibleRatio"),
                "band_params": {},
            }
            for band, pref, label in [
                ("visible_color", "Crgb", "可见光彩色"),
                ("visible_gray", "Krgb", "可见光灰度"),
                ("mwir", "Mrgb", "中波"),
                ("lwir", "Lrgb", "长波"),
            ]:
                keys = [k for k in param if k.startswith(pref)]
                if keys:
                    d = {}
                    for k in keys:
                        suffix = k[len(pref):]
                        d[suffix] = param[k]
                        if param_comments.get(k):
                            d[suffix + "_label"] = param_comments[k]
                    model["band_params"][band] = d
            out["models"].append(model)

    for tag, rel in OSG_MODELS.items():
        p = os.path.join(SRC, rel.replace("/", "\\"))
        bb = osg_bbox(p, max_bytes=40 * 1024 * 1024)
        out["bounding_boxes"][tag] = bb

    # ---- 5. 汇总表格 markdown ----
    lines = []
    lines.append("# 自动提取：模型库 / 枚举 / 包围盒（由 parse_models.py 生成）\n")
    lines.append("## 1. 默认模型库模型清单（ModelDatabase.xml）\n")
    md = out["model_database"].get("ModelDatabase", {})
    if md.get("target"):
        lines.append("| Id | 型号名称 | 显示名称 | TargetType | 模型路径 | 类别 |")
        lines.append("|---|---|---|---|---|---|")
        for it in md["target"]:
            lines.append("| {} | {} | {} | {} | {} | {} |".format(
                it.get("@Id", ""), it.get("ProductName", {}).get("@value", ""),
                it.get("DisplaytName", {}).get("@value", ""),
                it.get("TargetType", {}).get("@value", ""),
                it.get("TargetPath", {}).get("@value", ""),
                it.get("ModelDescribe", {}).get("@value", "")))
    if md.get("jam"):
        lines.append("\n### 干扰模型清单\n")
        lines.append("| Id | 干扰类型 | 型号名称 | 实现方式 | 模型路径 |")
        lines.append("|---|---|---|---|---|")
        for it in md["jam"]:
            lines.append("| {} | {} | {} | {} | {} |".format(
                it.get("@Id", ""), it.get("JamType", {}).get("@value", ""),
                it.get("ProductName", {}).get("@value", ""),
                it.get("ImplType", {}).get("@value", ""),
                it.get("JamPath", {}).get("@value", "")))
    if md.get("background"):
        lines.append("\n### 背景模型清单\n")
        lines.append("| Id | 背景名称 | 背景类型 | 类别 | 经纬高 | 模型路径 |")
        lines.append("|---|---|---|---|---|---|")
        for it in md["background"]:
            lines.append("| {} | {} | {} | {} | {} | {} |".format(
                it.get("@Id", ""),
                it.get("BackgroundName", {}).get("@value", ""),
                it.get("Type", {}).get("@value", ""),
                it.get("Class", {}).get("@value", ""),
                "%s, %s, %s" % (it.get("KeyAreaLon", {}).get("@value", ""),
                                it.get("KeyAreaLat", {}).get("@value", ""),
                                it.get("KeyAreaHig", {}).get("@value", "")),
                it.get("ModelPath", {}).get("@value", "")))

    lines.append("\n## 2. 目标 / 背景模型 Config.ini 参数\n")
    lines.append("| tag | 模型名称 | 类别 | 经度 | 纬度 | 高程(m) | 模型文件 | 中波(μm) | 长波(μm) | 环境温度 | 温度范围 | 中波辐亮度范围 | 长波辐亮度范围 |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for m in out["models"]:
        if m.get("status") != "ok":
            continue
        bp = m["band_params"]
        mw = bp.get("mwir", {})
        lw = bp.get("lwir", {})
        lines.append("| {} | {} | {} | {} | {} | {} | {} | {}-{} | {}-{} | {} | {}-{} | {}-{} | {}-{} |".format(
            m["tag"], m.get("ModelName"), m.get("ModelCategory"),
            m.get("Longitude"), m.get("Latitude"), m.get("Elevation"),
            m.get("BigModelFile"),
            mw.get("MinWave", ""), mw.get("MaxWave", ""),
            lw.get("MinWave", ""), lw.get("MaxWave", ""),
            mw.get("AmbientTemp", ""),
            mw.get("MinTemp", ""), mw.get("MaxTemp", ""),
            mw.get("MinRadiant", ""), mw.get("MaxRadiant", ""),
            lw.get("MinRadiant", ""), lw.get("MaxRadiant", "")))

    lines.append("\n## 3. 模型包围盒（OSG 顶点，局部坐标）\n")
    lines.append("| tag | 顶点数 | bbox min | bbox max | 尺寸 (x,y,z) | 文件 |")
    lines.append("|---|---|---|---|---|---|")
    for tag, bb in out["bounding_boxes"].items():
        if bb.get("status") != "ok" or not bb.get("bbox_local"):
            lines.append("| {} | - | - | - | - | {} |".format(tag, bb.get("file", "?")))
            continue
        b = bb["bbox_local"]
        lines.append("| {} | {} | {} | {} | {} | {} |".format(
            tag, bb["n_vertices"], b["min"], b["max"], b["size"], bb["file"]))

    lines.append("\n## 4. 枚举（tips 原文，节选关键项）\n")
    for k, v in out["enums"].items():
        if not isinstance(v, dict):
            continue
        lines.append("### {}（{}）\n".format(k, v.get("remark", "")))
        lines.append("- tips 原文：`{}`".format(v.get("tips", "")))
        lines.append("- 解析：{}".format(json.dumps(v.get("enum_map", {}), ensure_ascii=False)))
        lines.append("")
    if "jam_type_all_variants" in out["enums"]:
        lines.append("### jam_type 全部变体（模型库 1~13 与想定 1~18）\n")
        for va in out["enums"]["jam_type_all_variants"]:
            lines.append("- `{}` 来源: {}".format(va["tips"], ",".join(va["sources"])))
        lines.append("")

    with open(os.path.join(REP, "models_autogen.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    with open(os.path.join(BASE, "models.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print("models.json ->", os.path.join(BASE, "models.json"))
    print("markdown   ->", os.path.join(REP, "models_autogen.md"))
    print("enums:", len(out["enums"]), "all_tips_enums:", len(out["all_tips_enums"]),
          "models:", len(out["models"]), "bbox:", len(out["bounding_boxes"]))
    for tag, bb in out["bounding_boxes"].items():
        if bb.get("bbox_local"):
            print("  bbox", tag, bb["bbox_local"]["size"], "verts", bb["n_vertices"])


if __name__ == "__main__":
    main()
