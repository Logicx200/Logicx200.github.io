#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ETS2 game.sii 重新加密器 — 与 decrypt_sii.py 配对
用同一个 AES-256-CBC 密钥把明文 SII/zlib 数据封回 ScsC 容器。

关键: 头部 [4:36] 的 32 字节字段原样保留(游戏不校验或该字段非 HMAC)。
"""
import sys, struct, zlib
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding

SII_KEY = bytes([
    0x2a,0x5f,0xcb,0x17,0x91,0xd2,0x2f,0xb6,0x02,0x45,0xb3,0xd8,0x36,0x9e,0xd0,0xb2,
    0xc2,0x73,0x71,0x56,0x3f,0xbf,0x1f,0x3c,0x9e,0xdf,0x6b,0x11,0x82,0x5a,0x5d,0x0a,
])
MAGIC = 0x43736353


def encrypt(payload_encrypted_middle, plaintext: bytes) -> bytes:
    """payload_encrypted_middle = 原文件 [4:52] (32字节保留区 + 16字节 IV)"""
    iv = payload_encrypted_middle[32:48]
    body = zlib.compress(plaintext, 9)

    pad = padding.PKCS7(128).padder()
    padded = pad.update(body) + pad.finalize()

    enc = Cipher(algorithms.AES(SII_KEY), modes.CBC(iv)).encryptor()
    ct = enc.update(padded) + enc.finalize()

    out = bytearray()
    out += struct.pack("<I", MAGIC)
    out += payload_encrypted_middle          # 32 字节保留区 + IV 原样
    out += struct.pack("<I", len(body))      # data_size (解压后原始长度)
    out += ct
    return bytes(out)


def main():
    """用法: reencrypt.py <原始game.sii> <新明文> <输出game.sii>"""
    orig_path, plain_path, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
    orig = open(orig_path, "rb").read()
    plain = open(plain_path, "rb").read()

    assert struct.unpack_from("<I", orig, 0)[0] == MAGIC, "原文件不是 ScsC"
    middle = orig[4:52]
    print(f"原始保留区 [4:52]: {middle.hex(' ')}")

    blob = encrypt(middle, plain)
    open(out_path, "wb").write(blob)
    print(f"写出 {len(blob)} bytes -> {out_path}")
    print(f"明文 {len(plain)} bytes, zlib 后 {len(zlib.compress(plain,9))} bytes")


if __name__ == "__main__":
    main()
