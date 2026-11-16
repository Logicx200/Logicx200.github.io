# -*- coding: utf-8 -*-
import os
from pathlib import Path

files = [
    r"D:\XGGDCOSSim2\Data\SystemBaseFile\DefaultPlanFile.xml",
    r"D:\XGGDCOSSim2\Data\SystemBaseFile\ModelDatabase.xml",
    r"D:\XGGDCOSSim2\Data\AtomData\Q2_M.csv",
    r"D:\XGGDCOSSim2\Data\AtomData\Q2_L.csv",
    r"D:\XGGDCOSSim2\Data\config\pluginMgr\config.xml",
    r"D:\XGGDCOSSim2\Data\config\xgcossim_render\config.xml",
]
out = Path(r"F:\DeepSeek工作区\软件参数提取")
out.mkdir(parents=True, exist_ok=True)

for f in files:
    p = Path(f)
    raw = p.read_bytes()[:8000]
    enc = None
    for e in ("utf-8-sig", "utf-8", "gb18030", "gbk", "gb2312", "big5", "utf-16"):
        try:
            text = raw.decode(e)
            if "\ufffd" not in text:
                enc = e
                break
        except Exception:
            continue
    print("=" * 30, p.name, "size", p.stat().st_size, "encoding", enc)
    txt = raw.decode(enc or "gb18030", errors="replace")
    print(txt[:2500].replace("\r\n", "\n"))
    (out / (p.stem + "_head.txt")).write_text(
        f"FILE: {p}\nENCODING: {enc}\nSIZE: {p.stat().st_size}\n\n" + txt,
        encoding="utf-8",
    )
