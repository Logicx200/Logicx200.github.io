#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从民航局空管局情报中心 eAIP China 下载最新一期《NOTAM Summary》（免费、无需登录）。

用法:
    python fetch_notam_summary.py <输出目录>
    # 之后可用 pdftotext 转文本，再跑 parse_notam_summary.py

依赖: 仅标准库 (urllib)。
"""
import sys, os, json, ssl, zipfile, urllib.request, urllib.parse

BASE = 'https://www.eaipchina.cn'
LIST_API = BASE + '/eaip/homeFile/listPublish'
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36'

# eAIP 的 TLS 指纹对默认客户端不友好：显式限定 TLS1.2 + SECLEVEL=1
CTX = ssl.create_default_context()
CTX.minimum_version = ssl.TLSVersion.TLSv1_2
try:
    CTX.set_ciphers('DEFAULT@SECLEVEL=1')
except ssl.SSLError:
    pass


def post_json(url, payload):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(), method='POST',
        headers={'User-Agent': UA, 'Content-Type': 'application/json',
                 'Accept': 'application/json', 'Referer': BASE + '/'})
    with urllib.request.urlopen(req, timeout=60, context=CTX) as r:
        return json.loads(r.read().decode('utf-8'))


def main(out_dir):
    os.makedirs(out_dir, exist_ok=True)
    data = post_json(LIST_API, {'pageNum': 1, 'pageSize': 100})['data']
    summaries = [d for d in data if d.get('dataType') == 'NOTAM_SUMMARY']
    if not summaries:
        print('没有找到 NOTAM_SUMMARY'); return
    latest = summaries[0]                      # 接口按发布时间倒序
    path = latest['filePath'].replace('\\', '/')
    url = BASE + '/eaip/' + urllib.parse.quote(path, safe='')
    print('最新一期:', latest['dataVersion'], latest['createTime'])
    print('下载:', url)
    zip_path = os.path.join(out_dir, latest['fileName'])
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Referer': BASE + '/'})
    with urllib.request.urlopen(req, timeout=180, context=CTX) as r, open(zip_path, 'wb') as f:
        f.write(r.read())
    print('已保存', zip_path, os.path.getsize(zip_path), 'bytes')
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(os.path.join(out_dir, 'extract'))
    print('解压到', os.path.join(out_dir, 'extract'))
    print('下一步: pdftotext -enc UTF-8 <x>.pdf <x>.txt ;; python parse_notam_summary.py <txt目录> ..')


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'notam_data')
