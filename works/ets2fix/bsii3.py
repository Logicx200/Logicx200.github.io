#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ETS2 BSII 解析器 v3 —— 严格按 DecryptTruck 源码移植。

已验证的布局 (用前 180 字节与官方解码结果对齐):
  header    : u32 'BSII' + u32 version
  结构块    : u32 block_type(==0) + u8 valid + u32 structure_id
              + [u32 len][name] + segments{ u32 type + [u32 len][name] } + u32 0
  数据块    : u32 block_type(!=0) + u8 valid + id + 按结构定义依次取值
  id        : u8 part_count ; 0xFF -> u64 ; 否则 part_count 个 (u64 编码串)
  字符串值  : u32 len + bytes
"""
import struct, sys

CT = '0123456789abcdefghijklmnopqrstuvwxyz_'

SCALAR = {
    0x01: 1, 0x05: 4, 0x07: 8, 0x09: 12, 0x11: 12, 0x17: 16, 0x19: 32,
    0x25: 4, 0x27: 4, 0x29: 2, 0x2B: 2, 0x2F: 4, 0x31: 8, 0x33: 8,
    0x35: 1,
}
ARRAY = {
    0x02: ('s', 1), 0x04: ('u64s', 1), 0x06: ('f', 1), 0x08: ('f', 2),
    0x0A: ('f', 3), 0x12: ('i', 3), 0x18: ('f', 4), 0x1A: ('f', 8),
    0x26: ('i', 1), 0x28: ('I', 1), 0x2A: ('h', 1), 0x2C: ('H', 1),
    0x32: ('q', 1), 0x34: ('Q', 1), 0x36: ('b', 1),
    0x3A: ('id', 1), 0x3C: ('id', 1), 0x3E: ('id', 1), 0x41: ('I', 2),
}
ID_TYPES = (0x39, 0x3B, 0x3D)
ORDINAL = 0x37


class R:
    def __init__(self, b): self.b, self.p = b, 0
    def u32(self):
        v = struct.unpack_from('<I', self.b, self.p)[0]; self.p += 4; return v
    def u64(self):
        v = struct.unpack_from('<Q', self.b, self.p)[0]; self.p += 8; return v
    def u8(self):
        v = self.b[self.p]; self.p += 1; return v
    def s(self):
        n = self.u32(); v = self.b[self.p:self.p+n].decode('utf-8', 'replace'); self.p += n; return v
    def u64str(self):
        raw = self.u64(); v = raw; out = ''
        while v:
            i = (v % 38) - 1; v //= 38
            if 0 <= i < 38: out += CT[i]
        return out, raw


def read_id(r):
    pc = r.u8()
    if pc == 0xFF:
        return ('nameless', r.u64(), r.p - 9)
    parts = []
    start = r.p
    for _ in range(pc):
        parts.append(r.u64str()[0])
    return ('.'.join(parts) if parts else 'null', None, start)


def skip_value(r, t):
    """返回值描述; 标量类型返回 (desc, offset, size) 以便定位"""
    if t in ARRAY:
        n = r.u32()
        kind, mult = ARRAY[t]
        if kind == 's':
            for _ in range(n): r.s()
        elif kind == 'u64s':
            for _ in range(n): r.u64()
        elif kind == 'id':
            for _ in range(n): read_id(r)
        else:
            r.p += n * struct.calcsize('<' + kind) * mult
        return (f'array[{n}]', None, 0)
    if t in ID_TYPES:
        return (read_id(r)[0], None, 0)
    if t == ORDINAL:
        n = r.u32()
        for _ in range(n):
            r.u32(); r.s()
        return (f'ordinal[{n}]', None, 0)
    if t not in SCALAR:
        raise ValueError(f'未知类型 0x{t:02X} @ {r.p}')
    sz = SCALAR[t]
    off = r.p
    raw = r.b[r.p:r.p+sz]; r.p += sz
    return (raw.hex(' '), off, sz)


def read_segments(r):
    segs = []
    while True:
        t = r.u32()
        if t == 0:
            break
        name = r.s()
        segs.append((t, name))
        if t == ORDINAL:
            n = r.u32()
            for _ in range(n):
                r.u32(); r.s()
    return segs


def parse(path, targets):
    blob = open(path, 'rb').read()
    r = R(blob)
    sig = r.u32(); ver = r.u32()
    print(f"BSII signature=0x{sig:08X} version={ver}  size={len(blob)}")

    structs = {}
    while True:
        save = r.p
        bt = r.u32()
        if bt != 0:
            r.p = save; break
        valid = r.u8()
        if not valid:
            continue
        sid = r.u32()
        name = r.s()
        structs[sid] = (name, read_segments(r))
    print(f"结构定义: {len(structs)}\n")
    for sid in sorted(structs):
        print(f"  {sid:4d} '{structs[sid][0]}'  {len(structs[sid][1])} 字段")

    print(f"\n数据块起始偏移 = {r.p}")
    blk = 0
    found = []
    while r.p < len(blob) - 4:
        save = r.p
        bt = r.u32()
        if bt not in structs:
            r.p = save; break
        valid = r.u8()
        if not valid:
            continue
        name, segs = structs[bt]
        blk += 1
        idv = read_id(r)
        for (t, fn) in segs:
            try:
                desc, off, sz = skip_value(r, t)
            except Exception as e:
                print(f"\n!! 失步: 数据块#{blk} 结构{bt}'{name}' 字段'{fn}' type=0x{t:02X}")
                print(f"   偏移 {r.p}: {e}")
                return found, blk
            if (name, fn) in targets:
                found.append((blk, bt, name, fn, t, desc, off, sz))

    print(f"\n解析完成: {blk} 个数据块\n")
    print("=== 命中目标字段 ===")
    for (blk, bt, name, fn, t, desc, off, sz) in found:
        print(f"  块#{blk} 结构{bt} '{name}' . {fn}")
        print(f"     type=0x{t:02X}  值={desc}")
        print(f"     偏移={off}  长度={sz}")
        if off is not None:
            print(f"     上下文={blob[max(0,off-8):off+sz+8].hex(' ')}")
    return found, blk


if __name__ == '__main__':
    targets = set()
    for a in sys.argv[2:]:
        s, f = a.split('.')
        targets.add((s, f))
    if not targets:
        targets = {('player', 'hq_city'), ('player', 'my_truck_placement_valid')}
    parse(sys.argv[1], targets)
