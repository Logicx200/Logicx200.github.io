#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ETS2 BSII 解析器 v4 —— 严格逐行移植 DecryptTruck 的 Rust 实现。

关键修正(v3 的错误): 结构块布局是
    u32 block_type(==0) | u8 valid | u32 structure_id | [u32 len][name]
    segments: u32 type | [u32 len][name]
    u32 0 结束
数据块布局是
    u32 block_type | u8 valid | id | 按结构定义顺序的各个值
id: u8 part_count; 0xFF -> 读取 u64; 否则 part_count 次 u64string

本版本会一边解析一边打印「已消费字节区间」，便于和原始字节对照定位。
"""
import struct, sys

CT = '0123456789abcdefghijklmnopqrstuvwxyz_'

SCALAR = {0x01:1, 0x05:4, 0x07:8, 0x09:12, 0x11:12, 0x17:16, 0x19:32,
          0x25:4, 0x27:4, 0x29:2, 0x2B:2, 0x2F:4, 0x31:8, 0x33:8, 0x35:1}
ARRAY  = {0x02:('s',1), 0x04:('u64s',1), 0x06:('f',1), 0x08:('f',2),
          0x0A:('f',3), 0x12:('i',3), 0x18:('f',4), 0x1A:('f',8),
          0x26:('i',1), 0x28:('I',1), 0x2A:('h',1), 0x2C:('H',1),
          0x32:('q',1), 0x34:('Q',1), 0x36:('b',1),
          0x3A:('id',1), 0x3C:('id',1), 0x3E:('id',1), 0x41:('I',2)}
ID_TYPES = (0x39, 0x3B, 0x3D)
ORD = 0x37


class R:
    def __init__(s, b): s.b, s.p = b, 0
    def u32(s):
        v = struct.unpack_from('<I', s.b, s.p)[0]; s.p += 4; return v
    def u64(s):
        v = struct.unpack_from('<Q', s.b, s.p)[0]; s.p += 8; return v
    def u8(s):
        v = s.b[s.p]; s.p += 1; return v
    def st(s):
        n = s.u32(); v = s.b[s.p:s.p+n].decode('utf-8', 'replace'); s.p += n; return v


def rd_id(r):
    pc = r.u8()
    if pc == 0xFF:
        r.u64()
        return 'nameless'
    for _ in range(pc):
        r.u64()
    return 'null' if pc == 0 else f'id{pc}'


def rd_val(r, t, rec=None):
    if t in ARRAY:
        n = r.u32()
        kind, mult = ARRAY[t]
        if kind == 's':
            for _ in range(n): r.st()
        elif kind == 'u64s':
            r.p += 8*n
        elif kind == 'id':
            for _ in range(n): rd_id(r)
        else:
            r.p += n*struct.calcsize('<'+kind)*mult
        return
    if t in ID_TYPES:
        rd_id(r); return
    if t == ORD:
        n = r.u32()
        for _ in range(n):
            r.u32(); r.st()
        return
    if t not in SCALAR:
        raise ValueError(f'type 0x{t:02X} @ {r.p}')
    if rec is not None:
        rec.append((t, r.p, SCALAR[t]))
    r.p += SCALAR[t]


def rd_segments(r):
    segs = []
    while True:
        t = r.u32()
        if t == 0: break
        name = r.st()
        segs.append((t, name))
        if t == ORD:
            n = r.u32()
            for _ in range(n):
                r.u32(); r.st()
    return segs


def main():
    path = sys.argv[1]
    blob = open(path, 'rb').read()
    r = R(blob)
    sig = r.u32(); ver = r.u32()
    print(f"sig=0x{sig:08X} ver={ver} size={len(blob)}")

    structs = {}
    while True:
        save = r.p
        bt = r.u32()
        if bt != 0:
            r.p = save; break
        valid = r.u8()
        if not valid: continue
        sid = r.u32(); name = r.st()
        structs[sid] = (name, rd_segments(r))
    print(f"结构 {len(structs)} 个; 数据区起点={r.p}")
    for sid in (1,2,3,5,11,17,18):
        if sid in structs:
            print(f"  {sid} '{structs[sid][0]}' -> {len(structs[sid][1])} 字段")

    # 数据块
    blk = 0
    while r.p < len(blob) - 4:
        save = r.p
        bt = r.u32()
        if bt not in structs:
            r.p = save; break
        valid = r.u8()
        if not valid: continue
        blk += 1
        name, segs = structs[bt]
        start = r.p
        try:
            rd_id(r)
            for (t, fn) in segs:
                rec = []
                rd_val(r, t, rec)
                if name == 'player':
                    for (tt, off, sz) in rec:
                        print(f"    player.{fn}: type=0x{tt:02X} off={off} size={sz} bytes={blob[off:off+sz].hex(' ')}")
        except Exception as e:
            print(f"!! 失步 块#{blk} 结构{bt}'{name}' @ {r.p}: {e}")
            break
        if blk > 20:
            break
    print(f"\n共解析 {blk} 个数据块")


if __name__ == '__main__':
    main()
