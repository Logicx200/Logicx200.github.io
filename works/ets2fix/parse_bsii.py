#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
解析解密后的 BSII 存档，定位字段名及其取值。
BSII 字符串编码: [1字节长度][字符串]，长度 <= 39 直接内联。
"""
import re, sys, struct

def scan_strings(d):
    """返回 [(offset, length, text)]，只认长度前缀正确的 ASCII 串"""
    out = []
    i = 0
    while i < len(d):
        L = d[i]
        if 1 <= L <= 200 and i + 1 + L <= len(d):
            chunk = d[i+1:i+1+L]
            if all(0x20 <= c <= 0x7e for c in chunk):
                out.append((i, L, chunk.decode('ascii')))
                i += 1 + L
                continue
        i += 1
    return out

def main():
    path = sys.argv[1]
    d = open(path, 'rb').read()
    ss = scan_strings(d)
    print(f"文件 {len(d)} 字节, 识别到 {len(ss)} 个字符串\n")

    targets = ['hq_city', 'last_visited_city', 'current_city', 'garages',
               'garage', 'my_truck_placement', 'player', 'economy']
    for t in targets:
        hits = [(o, L, s) for (o, L, s) in ss if s == t]
        print(f"=== {t}  ({len(hits)} 处) ===")
        for (o, L, s) in hits[:4]:
            lo = max(0, o - 16)
            hi = min(len(d), o + 1 + L + 40)
            print(f"  @ {o}")
            print(f"    before : {d[lo:o].hex(' ')}")
            print(f"    field  : {d[o:o+1+L].hex(' ')}   '{s}'")
            print(f"    after  : {d[o+1+L:hi].hex(' ')}")
        print()

if __name__ == '__main__':
    main()
