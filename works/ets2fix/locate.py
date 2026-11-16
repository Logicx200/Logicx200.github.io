#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BSII 字段定位器 —— 解码结构定义, 然后定位指定字段的值字节。
格式(经往返验证):
  header   : u32 'BSII' + u32 version
  段头     : u32 type + u32 namelen + name bytes
  字符串值 : u32 len + bytes
  Id       : u8 part_count + (0xFF 时 u64) 或 part_count 个 u64string
"""
import struct, sys

CT = '0123456789abcdefghijklmnopqrstuvwxyz_'

# 标量类型 -> 字节数
SCALAR = {
    0x01: 1,   # UTF8String? 实为 1 字节标志
    0x03: 8,   # EncodedString (城市/公司引用)
    0x05: 4,   # Single
    0x07: 8,   # VectorOf2Single
    0x09: 12,  # VectorOf3Single
    0x11: 12,  # VectorOf3Int32
    0x17: 16,  # VectorOf4Single
    0x19: 32,  # VectorOf8Single
    0x25: 4,   # Int32
    0x27: 4,   # UInt32
    0x29: 2,   # Int16
    0x2B: 2,   # UInt16
    0x2F: 4,   # UInt32Type2
    0x31: 8,   # Int64
    0x33: 8,   # UInt64
    0x35: 1,   # ByteBool
    0x37: None,# OrdinalString (特殊)
    0x39: None,# Id
    0x3B: None,# IdType2
    0x3D: None,# IdType3
}
ARRAY = {
    0x02: ('s',), 0x04: ('u64s',), 0x06: ('f',), 0x08: ('f',2),
    0x0A: ('f',3), 0x12: ('i',3), 0x18: ('f',4), 0x1A: ('f',8),
    0x1F: ('i',),  # 未列出
    0x26: ('i',), 0x28: ('I',), 0x2A: ('h',), 0x2C: ('H',),
    0x32: ('q',), 0x34: ('Q',), 0x36: ('b',),
    0x3A: ('id',), 0x3C: ('id',), 0x3E: ('id',), 0x41: ('I',2),
}


class R:
    def __init__(self, b): self.b, self.p = b, 0
    def u32(self):
        v = struct.unpack_from('<I', self.b, self.p)[0]; self.p += 4; return v
    def u64(self):
        v = struct.unpack_from('<Q', self.b, self.p)[0]; self.p += 8; return v
    def u8(self):
        v = self.b[self.p]; self.p += 1; return v
    def raw(self, n):
        v = self.b[self.p:self.p+n]; self.p += n; return v
    def s(self):
        n = self.u32(); v = self.b[self.p:self.p+n].decode('utf-8','replace'); self.p += n; return v
    def u64str(self):
        raw = self.u64(); v = raw; out = ''
        while v:
            i = (v % 38) - 1; v //= 38
            if 0 <= i < 38: out += CT[i]
        return out, raw


def skip_value(r, t):
    """返回 (值描述, 起始偏移[仅标量], 字节长度)"""
    if t in ARRAY:
        n = r.u32()
        kind = ARRAY[t][0]
        if kind == 's':
            for _ in range(n): r.s()
        elif kind == 'u64s':
            for _ in range(n): r.u64()
        elif kind == 'id':
            for _ in range(n): skip_id(r)
        else:
            fmt, mult = ARRAY[t][0], (ARRAY[t][1] if len(ARRAY[t])>1 else 1)
            r.p += n * struct.calcsize('<'+fmt) * mult
        return f'array[{n}]', None, 0
    if t in (0x39, 0x3B, 0x3D):
        return skip_id(r), None, 0
    if t not in SCALAR:
        raise ValueError(f'未知类型 0x{t:02X} @ {r.p}')
    sz = SCALAR[t]
    if sz is None:
        raise ValueError(f'类型 0x{t:02X} 未定义大小 @ {r.p}')
    off = r.p
    raw = r.raw(sz)
    return raw.hex(' '), off, sz


def skip_id(r):
    pc = r.u8()
    if pc == 0xFF:
        r.u64(); return 'nameless'
    for _ in range(pc):
        r.u64()
    return 'null' if pc == 0 else f'id{pc}'


def read_segments(r):
    segs = []
    while True:
        t = r.u32()
        if t == 0: break
        n = r.u32(); name = r.b[r.p:r.p+n].decode('utf-8','replace'); r.p += n
        segs.append((t, name))
        if t == 0x37:
            m = r.u32()
            for _ in range(m):
                r.u32(); r.s()
    return segs


def main():
    path = sys.argv[1]
    want_struct = sys.argv[2] if len(sys.argv) > 2 else 'player'
    want_field  = sys.argv[3] if len(sys.argv) > 3 else 'my_truck_placement_valid'

    blob = open(path,'rb').read()
    r = R(blob)
    sig = r.u32(); ver = r.u32()
    print(f"BSII version={ver}")

    # 结构块
    structs = {}
    while True:
        save = r.p
        bt = r.u32()
        if bt != 0:
            r.p = save; break
        valid = r.u8()
        if not valid: continue
        sid = r.u32(); name = r.s()
        structs[sid] = (name, read_segments(r))
    print(f"结构 {len(structs)} 个")

    # 数据块
    blk = 0
    while r.p < len(blob) - 4:
        save = r.p
        bt = r.u32()
        if bt not in structs:
            r.p = save; break
        valid = r.u8()
        if not valid: continue
        name, segs = structs[bt]
        blk += 1
        skip_id(r)   # 每个数据块的 id
        for (t, fn) in segs:
            try:
                desc, off, sz = skip_value(r, t)
            except Exception as e:
                print(f"  !! 结构{bt}'{name}' 字段'{fn}' type=0x{t:02X}: {e}")
                return
            if name == want_struct and fn == want_field:
                print(f"\n>>> 命中! 数据块#{blk} 结构{bt} '{name}'")
                print(f"    字段 '{fn}'  type=0x{t:02X}")
                print(f"    值(hex) = {desc}")
                print(f"    字节偏移 = {off}  长度 = {sz}")
                print(f"    上下文 = {blob[max(0,off-12):off+sz+12].hex(' ')}")
    print(f"\n扫描完 {blk} 个数据块")


if __name__ == '__main__':
    main()
