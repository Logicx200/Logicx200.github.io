# -*- coding: utf-8 -*-
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

OUT = Path(r"F:\DeepSeek工作区\软件参数提取")
OUT.mkdir(parents=True, exist_ok=True)

FILES = {
    "DefaultPlanFile": (r"D:\XGGDCOSSim2\Data\SystemBaseFile\DefaultPlanFile.xml", "gb18030"),
    "ModelDatabase": (r"D:\XGGDCOSSim2\Data\SystemBaseFile\ModelDatabase.xml", "utf-16"),
    "DefaultModelDatabase": (r"D:\XGGDCOSSim2\Data\SystemBaseFile\DefaultModelDatabase.xml", "utf-8-sig"),
    "Q2_M": (r"D:\XGGDCOSSim2\Data\AtomData\Q2_M.csv", "gb18030"),
    "Q2_L": (r"D:\XGGDCOSSim2\Data\AtomData\Q2_L.csv", "gb18030"),
}

for name, (path, enc) in FILES.items():
    raw = Path(path).read_bytes()
    text = raw.decode(enc, errors="replace")
    (OUT / f"{name}_decoded.txt").write_text(text, encoding="utf-8")
    print(name, "bytes", len(raw), "chars", len(text), "lines", text.count("\n") + 1)
    if name.startswith("Q2"):
        lines = text.splitlines()
        print("  header/first rows:")
        for ln in lines[:4]:
            print("   ", ln[:500])
        (OUT / f"{name}_head.txt").write_text("\n".join(lines[:40]), encoding="utf-8")

# ---- parse plan xml into a flat tag/value list ----
def flatten(elem, prefix=""):
    rows = []
    tag = elem.tag
    attrs = {k: v for k, v in elem.attrib.items()}
    val = (elem.text or "").strip()
    if val or attrs:
        rows.append({"path": prefix + "/" + tag, "value": val, "attrs": attrs})
    for child in list(elem):
        rows.extend(flatten(child, prefix + "/" + tag))
    return rows


for name in ("DefaultPlanFile", "DefaultModelDatabase"):
    path, enc = FILES[name]
    text = Path(path).read_bytes().decode(enc, errors="replace")
    text = text.replace('encoding="GB2312"', 'encoding="UTF-8"')
    try:
        root = ET.fromstring(text)
    except Exception as e:
        # strip xml declaration
        root = ET.fromstring(text.split("?>", 1)[-1])
    rows = flatten(root)
    (OUT / f"{name}_flat.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print(name, "flattened rows", len(rows))
    # print unique remarks/values summary for plan
    if name == "DefaultPlanFile":
        for r in rows:
            t = r["path"]
            if any(k in t for k in ("ScenarioCode", "ZeroTime", "SpaceParam", "Atmo", "Sensor", "Target", "Background", "Jam")):
                print(t, "=", r["value"][:120], {k: v for k, v in r["attrs"].items() if k in ("remark", "value", "tips")})
