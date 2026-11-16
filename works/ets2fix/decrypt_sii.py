#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ETS2/ATS game.sii 解密器 (ScsC 二进制格式)
移植自 CoffeSiberian/DecryptTruck (src/utils/aes.rs)

格式:
  [0:4]    signature  (u32 LE)  期望 0x43736353 = "ScsC"
  [4:36]   hmac       (32 bytes, 不参与解密)
  [36:52]  iv         (16 bytes)  AES-CBC 初始向量
  [52:56]  data_size  (u32 LE)
  [56:]    AES-256-CBC 密文, PKCS7 填充, 解出后为 zlib 压缩的 SII 文本
"""
import sys, struct, zlib
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding

SII_KEY = bytes([
    0x2a,0x5f,0xcb,0x17,0x91,0xd2,0x2f,0xb6,0x02,0x45,0xb3,0xd8,0x36,0x9e,0xd0,0xb2,
    0xc2,0x73,0x71,0x56,0x3f,0xbf,0x1f,0x3c,0x9e,0xdf,0x6b,0x11,0x82,0x5a,0x5d,0x0a,
])
MAGIC = 0x43736353  # 'ScsC' little-endian


def decrypt(blob: bytes) -> bytes:
    if len(blob) < 56:
        raise ValueError("file too small")
    sig, = struct.unpack_from("<I", blob, 0)
    if sig != MAGIC:
        raise ValueError(f"unexpected signature 0x{sig:08X} (want 0x{MAGIC:08X} 'ScsC')")
    iv = blob[36:52]
    data_size, = struct.unpack_from("<I", blob, 52)
    ct = blob[56:]

    dec = Cipher(algorithms.AES(SII_KEY), modes.CBC(iv)).decryptor()
    padded = dec.update(ct) + dec.finalize()
    unp = padding.PKCS7(128).unpadder()
    raw = unp.update(padded) + unp.finalize()

    # 尝试 zlib 解压
    try:
        out = zlib.decompress(raw)
    except zlib.error:
        try:
            out = zlib.decompressobj().decompress(raw)
        except zlib.error:
            out = raw  # 未压缩
    return out, data_size


def main():
    if len(sys.argv) < 2:
        print("用法: python decrypt_sii.py <game.sii> [输出文件]")
        return 2
    src = sys.argv[1]
    blob = open(src, "rb").read()
    text, dsize = decrypt(blob)
    dst = sys.argv[2] if len(sys.argv) > 2 else src + ".decrypted.txt"
    open(dst, "wb").write(text)
    print(f"OK  输入 {len(blob)} bytes  声明 data_size={dsize}")
    print(f"    解出 {len(text)} bytes -> {dst}")
    print(f"    开头: {text[:120]!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
