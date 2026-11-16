#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ETS2 BSII 存档解析器 v2 — 完整解析数据块，定位 hq_city 等字段的字节偏移与取值。
"""
import struct, sys

CT = '0123456789abcdefghijklmnopqrstuvwxyz_'

# 段类型表 (DataTypeIdFormat)
T_BYTEBOOL      = 0x01
T_STR_ARRAY     = 0x02   # array of utf8 string
T_U64STR        = 0x03   # id / 城市引用
T_U64STR_ARRAY  = 0x04
T_ID3           = 0x05
T_ID2           = 0x06
T_ID            = 0x07
T_FLOAT         = 0x08
T_FLOAT_ARRAY   = 0x09
T_INT32         = 0x0A
T_INT32_ARRAY   = 0x0B
T_UINT32        = 0x0C
T_UINT32_ARRAY  = 0x0D
T_INT64         = 0x0E
T_UINT64        = 0x0F
T_BOOL          = 0x10
T_VEC3F         = 0x11
T_VEC3F_ARRAY   = 0x12
T_VEC4F         = 0x13
T_VEC8F         = 0x14
T_UINT16        = 0x15
T_UINT16_ARRAY  = 0x16
T_UINT64_ARRAY  = 0x17
T_ORDINAL       = 0x37   # 55

SIZE = {T_BYTEBOOL:1, T_U64STR:8, T_ID3:8, T_ID2:8, T_ID:8,
        T_FLOAT:4, T_INT32:4, T_UINT32:4, T_INT64:8, T_UINT64:8,
        T_BOOL:1, T_UINT16:2, T_VEC3F:12, T_VEC4F:16, T_VEC8F:32}
ARR_ELEM = {T_FLOAT_ARRAY:('f',4), T_INT32_ARRAY:('i',4), T_UINT32_ARRAY:('I',4),
            T_VEC3F_ARRAY:('f',12), T_STR_ARRAY:None, T_U64STR_ARRAY:None,
            T_UINT16_ARRAY:('H',2), T_UINT64_ARRAY:None, T_BOOL:None}


class R:
    def __init__(self, b): self.b, self.p = b, 0
    def u32(self):
        v = struct.unpack_from('<I', self.b, self.p)[0]; self.p += 4; return v
    def u64(self):
        v = struct.unpack_from('<Q', self.b, self.p)[0]; self.p += 8; return v
    def u16(self):
        v = struct.unpack_from('<H', self.b, self.p)[0]; self.p += 2; return v
    def i32(self):
        v = struct.unpack_from('<i', self.b, self.p)[0]; self.p += 4; return v
    def f32(self):
        v = struct.unpack_from('<f', self.b, self.p)[0]; self.p += 4; return v
    def u8(self):
        v = self.b[self.p]; self.p += 1; return v
    def s(self):
        n = self.u32(); v = self.b[self.p:self.p+n]; self.p += n
        return v.decode('utf-8', 'replace')
    def u64str(self):
        raw = self.u64(); v = raw; out = ''
        while v:
            i = (v % 38) - 1; v //= 38
            if 0 <= i < 38: out += CT[i]
        return out, raw


def skip_or_read(r, t, want=False):
    """按类型读值; want=True 时返回 (value, raw_u64, offset)"""
    if t == 0: return None
    if t == T_BYTEBOOL or t == T_BOOL:
        o = r.p; v = r.u8(); return (v, None, o) if want else v
    if t == T_UINT16:
        o = r.p; v = r.u16(); return (v, None, o) if want else v
    if t == T_U64STR or t == T_ID3 or t == T_ID2 or t == T_ID:
        o = r.p; s, raw = r.u64str(); return (s, raw, o) if want else s
    if t in (T_INT32, T_UINT32):
        o = r.p; v = r.i32(); return (v, None, o) if want else v
    if t in (T_INT64, T_UINT64):
        o = r.p; v = r.u64(); return (v, None, o) if want else v
    if t == T_FLOAT:
        o = r.p; v = r.f32(); return (v, None, o) if want else v
    if t == T_VEC3F:
        o = r.p; v = (r.f32(), r.f32(), r.f32()); return (v, None, o) if want else v
    if t == T_VEC4F:
        o = r.p; v = tuple(r.f32() for _ in range(4)); return (v, None, o) if want else v
    if t == T_VEC8F:
        o = r.p; v = tuple(r.f32() for _ in range(8)); return (v, None, o) if want else v
    if t == T_STR_ARRAY:
        n = r.u32(); return [r.s() for _ in range(n)]
    if t == T_U64STR_ARRAY:
        n = r.u32(); return [r.u64str()[0] for _ in range(n)]
    if t == T_UINT64_ARRAY:
        n = r.u32(); return [r.u64() for _ in range(n)]
    if t in (T_FLOAT_ARRAY, T_INT32_ARRAY, T_UINT32_ARRAY, T_VEC3F_ARRAY, T_UINT16_ARRAY):
        n = r.u32(); fmt, sz = ARR_ELEM[t]
        cnt = n if t != T_VEC3F_ARRAY else n * 3
        return [struct.unpack_from('<' + fmt, r.b, r.p + i * sz)[0] for i in range(cnt)] if False else _read_arr(r, fmt, sz, cnt)
    # 未知类型 —— 保守跳过 0 字节，让调用方报错
    raise ValueError(f"unsupported segment type {t} (0x{t:02X}) at {r.p}")


def _read_arr(r, fmt, sz, cnt):
    out = [struct.unpack_from('<'+fmt, r.b, r.p + i*sz)[0] for i in range(cnt)]
    r.p += cnt*sz
    return out


def read_segments(r):
    segs = []
    while True:
        t = r.u32()
        if t == 0: break
        name = r.s()
        segs.append((t, name))
        if t == T_ORDINAL:
            n = r.u32()
            for _ in range(n):
                r.u32(); r.s()
    return segs


def main():
    path = sys.argv[1]
    blob = open(path, 'rb').read()
    r = R(blob)
    sig = r.u32(); ver = r.u32()
    print(f"signature=0x{sig:08X}('{blob[:4].decode()}') version={ver}")

    # 阶段1: 结构定义
    structures = {}
    while True:
        save = r.p
        bt = r.u32()
        if bt != 0:
            r.p = save; break
        valid = r.u8()
        if not valid: continue
        sid = r.u32(); name = r.s()
        segs = read_segments(r)
        structures[sid] = (name, segs)
    print(f"结构定义: {len(structures)} 个\n")

    # 阶段2: 数据块
    found = []
    total = 0
    while r.p < len(blob) - 8:
        bt = r.u32()
        valid = r.u8()
        if not valid: continue
        if bt not in structures:
            print(f"  !! 未知结构 {bt} @ {r.p}"); break
        name, segs = structures[bt]
        total += 1
        for (t, fn) in segs:
            try:
                res = skip_or_read(r, t, want=True)
            except Exception as e:
                print(f"  !! 解析失败 结构{bt}'{name}' 字段'{fn}' type={t}: {e}")
                return
            if res and fn in ('hq_city', 'last_visited_city', 'current_city'):
                val, raw, off = res
                found.append((bt, name, fn, val, raw, off))
        # 段表以 type==0 结束, 已在 read_segments 消费

    print(f"数据块: {total} 个\n")
    print("=== 城市字段 ===")
    for bt, name, fn, val, raw, off in found:
        print(f"  结构{bt:3d} '{name}' . {fn}")
        print(f"      值 = '{val}'   raw u64 = 0x{raw:016X} ({raw})")
        print(f"      字节偏移 = {off}  (在解密后文件内)")
        print(f"      原始字节 = {blob[off:off+8].hex(' ')}")


if __name__ == '__main__':
    main()
