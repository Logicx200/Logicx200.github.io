#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用真实 Edge(非 headless) + CDP 打开页面并抓正文，适合有 Cloudflare/Turnstile 的站点。

用法：先启动 Edge：
    msedge.exe --remote-debugging-port=9222 --user-data-dir=<temp> --no-first-run about:blank
再运行：
    python cdp_dump.py 9222 https://pilotefb.com/notams/zsha/ 45 out.html
"""
import asyncio, json, sys, time, urllib.parse, urllib.request
import websockets


def http_json(url, method='GET'):
    req = urllib.request.Request(url, method=method)
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read().decode('utf-8'))


def open_tab(port, url):
    """优先复用已存在的同 URL 标签页，否则新建"""
    for _ in range(40):
        try:
            tabs = http_json(f'http://127.0.0.1:{port}/json/list')
            for t in tabs:
                if t.get('type') == 'page' and t.get('webSocketDebuggerUrl'):
                    if url.split('//')[1].split('/')[0] in (t.get('url') or ''):
                        return t
        except Exception:
            pass
        time.sleep(0.5)
    return http_json(f'http://127.0.0.1:{port}/json/new?' + urllib.parse.quote(url, safe=''), method='PUT')


async def main(port, url, wait_s, out):
    tab = open_tab(port, url)
    print('target:', tab.get('url'))
    async with websockets.connect(tab['webSocketDebuggerUrl'], max_size=64 * 1024 * 1024) as ws:
        mid = [0]

        async def call(method, params=None):
            mid[0] += 1
            await ws.send(json.dumps({'id': mid[0], 'method': method, 'params': params or {}}))
            while True:
                msg = json.loads(await ws.recv())
                if msg.get('id') == mid[0]:
                    return msg

        await call('Page.enable')
        await call('Runtime.enable')
        deadline = time.time() + wait_s
        text = ''
        while time.time() < deadline:
            r = await call('Runtime.evaluate', {
                'expression': 'document.body ? document.body.innerText : ""',
                'returnByValue': True})
            text = (r.get('result', {}).get('result', {}).get('value') or '')
            bad = ('Just a moment' in text) or ('verification could not run' in text) or ('正在进行安全验证' in text)
            if len(text) > 800 and not bad and ('NOTAM' in text or 'Q)' in text):
                await asyncio.sleep(2)
                r = await call('Runtime.evaluate', {
                    'expression': 'document.body ? document.body.innerText : ""', 'returnByValue': True})
                text = (r.get('result', {}).get('result', {}).get('value') or '')
                break
            await asyncio.sleep(2)
        r = await call('Runtime.evaluate', {'expression': 'document.documentElement.outerHTML', 'returnByValue': True})
        html = r.get('result', {}).get('result', {}).get('value') or ''
        with open(out, 'w', encoding='utf-8') as f:
            f.write(html)
        with open(out + '.txt', 'w', encoding='utf-8') as f:
            f.write(text)
        print('saved', out, len(html), 'chars | text', len(text))
        print('--- head ---')
        print(text[:500])


if __name__ == '__main__':
    asyncio.run(main(sys.argv[1], sys.argv[2], float(sys.argv[3]), sys.argv[4]))
