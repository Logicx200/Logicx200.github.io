#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
在 BSII 数据区里定位「城市引用」字节模式。

已验证事实:
  - 编码串 = u64 (base38, 字符表 0-9a-z_), 小端
  - 单词 "dortmund" 的编码值
  - 城市字段的 3 段结构 = [u8 03][u64][u64][u64], 段间以值 0x...ff 收尾

策略: 直接在文件里搜 8 字节小端 u64 的精确字节序列, 因为编码值是双射的。
"""
import struct, sys

CT = '0123456789abcdefghijklmnopqrstuvwxyz_'


def encode_u64str(s: str) -> int:
    """字符串 -> u64 (decode_u64_string 的逆)"""
    v = 0
    # decode 时: while value: idx = value%38 -1; value//=38; push CT[idx]
    # 即低位先出字符。逆运算: 从最后一个字符开始
    for ch in reversed(s):
        idx = CT.index(ch) + 1
        v = v * 38 + idx
    return v


def decode_u64str(v: int) -> str:
    out = ''
    while v:
        i = (v % 38) - 1; v //= 38
        if 0 <= i < 38:
            out += CT[i]
    return out


def find_pattern(blob, target_u64):
    """在文件里搜 8 字节小端 u64"""
    pat = struct.pack('<Q', target_u64)
    hits = []
    start = 0
    while True:
        i = blob.find(pat, start)
        if i < 0:
            break
        hits.append(i)
        start = i + 1
    return hits


def main():
    path = sys.argv[1]
    words = sys.argv[2:] or ['dortmund', 'travemunde']
    blob = open(path, 'rb').read()
    print(f"文件 {len(blob)} 字节\n")

    for w in words:
        v = encode_u64str(w)
        back = decode_u64str(v)
        print(f"'{w}': u64=0x{v:016X}  验证回解='{back}'  {'OK' if back==w else '!! 不匹配'}")
        hits = find_pattern(blob, v)
        print(f"   字节模式 {struct.pack('<Q', v).hex(' ')}")
        print(f"   命中 {len(hits)} 处: {hits[:12]}")
        for h in hits[:6]:
            lo = max(0, h - 20); hi = min(len(blob), h + 8 + 20)
            print(f"      @{h}: {blob[lo:h].hex(' ')} | {blob[h:h+8].hex(' ')} | {blob[h+8:hi].hex(' ')}")
        print()


if __name__ == '__main__':
    main()
