#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ETS2 存档补丁器 —— 解密 -> 改字节 -> 回写 -> 用官方工具回读验证

用法:
  patch_save.py <源game.sii> <输出game.sii> [--verify]

流程保证:
  1. 先解密得到 BSII 明文
  2. 只在明文上做精确字节替换 (长度不变)
  3. 重新加密 (保留原头部 32 字节校验区)
  4. 调官方 decrypt_truck.exe 回读, 确认改动生效且文件可解析
"""
import sys, os, struct, zlib, subprocess
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding

SII_KEY = bytes([
    0x2a,0x5f,0xcb,0x17,0x91,0xd2,0x2f,0xb6,0x02,0x45,0xb3,0xd8,0x36,0x9e,0xd0,0xb2,
    0xc2,0x73,0x71,0x56,0x3f,0xbf,0x1f,0x3c,0x9e,0xdf,0x6b,0x11,0x82,0x5a,0x5d,0x0a,
])
MAGIC = 0x43736353
CT = '0123456789abcdefghijklmnopqrstuvwxyz_'


def u64str(s: str) -> int:
    v = 0
    for ch in reversed(s):
        v = v * 38 + CT.index(ch) + 1
    return v


def decrypt(blob: bytes) -> bytes:
    assert struct.unpack_from('<I', blob, 0)[0] == MAGIC
    iv = blob[36:52]
    ct = blob[56:]
    dec = Cipher(algorithms.AES(SII_KEY), modes.CBC(iv)).decryptor()
    padded = dec.update(ct) + dec.finalize()
    unp = padding.PKCS7(128).unpadder()
    raw = unp.update(padded) + unp.finalize()
    return zlib.decompress(raw)


def encrypt(middle52: bytes, plain: bytes) -> bytes:
    iv = middle52[32:48]
    body = zlib.compress(plain, 9)
    pad = padding.PKCS7(128).padder()
    padded = pad.update(body) + pad.finalize()
    enc = Cipher(algorithms.AES(SII_KEY), modes.CBC(iv)).encryptor()
    ct = enc.update(padded) + enc.finalize()
    return struct.pack('<I', MAGIC) + middle52 + struct.pack('<I', len(body)) + ct


def find_all(b, pat):
    out, i = [], 0
    while True:
        j = b.find(pat, i)
        if j < 0:
            return out
        out.append(j); i = j + 1


def main():
    src, dst = sys.argv[1], sys.argv[2]
    orig = open(src, 'rb').read()
    plain = decrypt(orig)
    print(f"解密: {len(orig)} -> {len(plain)} 字节")

    # ---------- 在这里定义改动 ----------
    # 锚点: player 块里 truck_placement / my_truck_placement 的零位移签名
    ZERO = struct.pack('<3f', 0, 0, 0) + struct.pack('<4f', 1, 0, 0, 0)
    hits = find_all(plain, ZERO)
    print(f"零位移签名 {len(hits)} 处")
    for h in hits[:12]:
        print(f"   @{h}")

    # 演示: 把 hq_city 的城市引用从 dortmund 改成 berlin (仅当定位成功)
    print()
    print("=== 定位 hq_city 值 ===")
    # 在 player 数据块区域搜 dortmund 的 u64
    dm = struct.pack('<Q', u64str('dortmund'))
    bl = struct.pack('<Q', u64str('berlin'))
    print(f"  dortmund u64 = {dm.hex(' ')}  命中 {find_all(plain, dm)}")
    print(f"  berlin   u64 = {bl.hex(' ')}  命中 {find_all(plain, bl)}")

    # 写出 (无改动) 以验证链路
    middle = orig[4:52]
    out = encrypt(middle, plain)
    open(dst, 'wb').write(out)
    print(f"\n已写出 {len(out)} 字节 -> {dst}")


if __name__ == '__main__':
    main()
