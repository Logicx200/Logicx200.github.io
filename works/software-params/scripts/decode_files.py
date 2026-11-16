# -*- coding: utf-8 -*-
"""只读解码 D:\XGGDCOSSim2 中的文本/配置/XML 文件为 UTF-8 副本（不修改源目录）。
输出到 F:\DeepSeek工作区\软件参数提取\_decoded\
用法: python scripts\decode_files.py
"""
import os, sys

SRC = r"D:\XGGDCOSSim2"
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_decoded")

FILES = [
    r"Data\config\SystemConfig.ini",
    r"Data\config\SystemConfig.description",
    r"Data\config\logDesc.json",
    r"Data\config\pluginMgr\config.xml",
    r"Data\config\pluginMgr\plugin_prepare_cfg.ini",
    r"Data\config\xgcossim_render\config.xml",
    r"Data\config\xgcossim_schedule\config.xml",
    r"Data\config\xgcossim_schedule\sim_mode_cfg.xml",
    r"Data\SystemBaseFile\DefaultPlanFile.xml",
    r"Data\SystemBaseFile\DefaultModelDatabase.xml",
    r"Data\SystemBaseFile\ModelDatabase.xml",
    r"Data\SystemBaseFile\ModelDatabase.xml.bak",
    r"Data\SystemBaseFile\ScenarioPlan.ini",
    r"Data\ModelData\Background\Config.ini",
    r"Data\ModelData\Background\yngd\Config.ini",
    r"Data\ModelData\Target\Config.ini",
    r"Data\ModelData\Target\F16\Config.ini",
    r"Data\ModelData\Target\f22\Config.ini",
    r"Data\ModelData\Target\nimitz\Config.ini",
    r"Data\ModelData\Target\hm\Config.ini",
    r"Data\ModelData\Target\agzfsc\Config.ini",
    r"Data\ModelData\Target\albk\Config.ini",
    r"Data\ModelData\Jam\干扰名称说明.txt",
    r"Data\ModelData\Jam\baozha\爆炸强光new.txt",
    r"Data\Assets\System\Setting.ini",
    r"bin\xg_config.xml",
    r"bin\Log4Qt.conf",
    r"Data\temp\config.ini",
]

CANDIDATES = ["utf-8-sig", "utf-8", "gb18030", "utf-16-le", "utf-16"]


def sniff_decode(raw: bytes):
    """按 BOM -> 候选编码顺序尝试，返回 (text, encoding, confidence_note)"""
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw.decode("utf-8-sig", errors="replace"), "utf-8-sig", "BOM"
    if raw.startswith(b"\xff\xfe"):
        return raw.decode("utf-16-le", errors="replace"), "utf-16-le", "BOM"
    if raw.startswith(b"\xfe\xff"):
        return raw.decode("utf-16-be", errors="replace"), "utf-16-be", "BOM"
    # 无 BOM: utf-16-le 启发式（大量奇数字节为 0）
    if len(raw) > 8 and raw[1::2].count(0) > len(raw) // 3:
        return raw.decode("utf-16-le", errors="replace"), "utf-16-le", "heuristic-nobom"
    try:
        return raw.decode("utf-8"), "utf-8", "strict"
    except UnicodeDecodeError:
        pass
    try:
        return raw.decode("gb18030"), "gb18030", "fallback"
    except UnicodeDecodeError:
        return raw.decode("gb18030", errors="replace"), "gb18030-replace", "fallback"


def main():
    os.makedirs(OUT, exist_ok=True)
    report = []
    for rel in FILES:
        src = os.path.join(SRC, rel)
        if not os.path.exists(src):
            report.append((rel, "MISSING", "", 0))
            print(f"[MISSING] {rel}")
            continue
        raw = open(src, "rb").read()
        text, enc, note = sniff_decode(raw)
        # 统一换行
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        name = rel.replace("\\", "__")
        dst = os.path.join(OUT, name + ".utf8.txt")
        with open(dst, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        report.append((rel, enc, note, len(text)))
        print(f"[OK] {rel:60s} enc={enc:12s} {note:18s} chars={len(text)}")
    # 编码报告
    with open(os.path.join(OUT, "_encoding_report.csv"), "w", encoding="utf-8-sig", newline="") as f:
        f.write("file,encoding,note,chars\n")
        for rel, enc, note, n in report:
            f.write(f'"{rel}","{enc}","{note}",{n}\n')


if __name__ == "__main__":
    main()
