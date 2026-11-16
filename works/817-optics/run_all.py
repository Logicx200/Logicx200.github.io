# -*- coding: utf-8 -*-
"""一键运行全部仿真实验，并把图片输出到 outputs/。

用法：
    python run_all.py              # 运行全部
    python run_all.py d03 d07      # 只运行指定实验
"""
from __future__ import annotations

import os
import runpy
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
DEMOS = os.path.join(HERE, "demos")
sys.path.insert(0, HERE)

ALL = sorted(f[:-3] for f in os.listdir(DEMOS)
             if f.startswith("d") and f.endswith(".py"))


def main(argv):
    if argv:
        targets = []
        for a in argv:
            hit = [n for n in ALL if n.startswith(a)]
            if not hit:
                print(f"[跳过] 没有匹配 '{a}' 的实验")
            targets += hit
    else:
        targets = ALL
    for name in targets:
        path = os.path.join(DEMOS, name + ".py")
        if not os.path.exists(path):
            print(f"[跳过] 找不到 {path}")
            continue
        print("\n" + "=" * 78)
        print(f"运行 {name}")
        print("=" * 78)
        try:
            runpy.run_path(path, run_name="__main__")
        except Exception:
            print(f"!! {name} 运行失败：")
            traceback.print_exc()
            return 1
    print("\n全部实验完成，图片在 outputs/ 目录。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
