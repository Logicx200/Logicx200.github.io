# -*- coding: utf-8 -*-
"""下载 O3 / N2O / CO 的 HITRAN2020 线表原始记录（.par 定宽格式）。

背景
----
HITRANonline 的 /lbl/api 接口单请求吞吐量很低（约 8 KB/s），因此把谱线区间切成
50 cm⁻¹ 的小块，多线程并发下载（每个块独立校验波数范围，防止并发请求串数据），
每个块落盘为 07_光谱数据/_hapi_db/raw/<分子>_<起>_<止>.par，可断点续跑。

用法
----
python fetch_hitran_lines.py [--workers 6] [--chunk 50] [--retry 3]
输出：raw/*.par + _hapi_db/raw/_fetch_status.json
"""
import os
import sys
import json
import time
import argparse
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import hapi
import requests

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RAW = os.path.join(BASE, "07_光谱数据", "_hapi_db", "raw")
os.makedirs(RAW, exist_ok=True)
LOG = os.path.join(BASE, "07_光谱数据", "_hapi_db", "fetch_lines.log")
HOST = "https://hitran.org/lbl/api"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) HAPI/1.3.0.0"}

# 各分子要下载的全谱线区间（cm⁻¹）：覆盖 3.7–4.8 μm（2083–2703）与 8–12 μm
# （833–1250）两个业务波段，并前后各留 25 cm⁻¹ 线翼余量；MWIR 截面网格按规范
# 覆盖 2000–4000 cm⁻¹，因此 MWIR 段整段抓取。
MOL_M = {"O3": 3, "N2O": 4, "CO": 5}
RANGES = {
    "O3": [(725.0, 1425.0), (1975.0, 4025.0)],
    "N2O": [(725.0, 1425.0), (1975.0, 4025.0)],
    "CO": [(1975.0, 4025.0)],          # CO 基频 2143 cm⁻¹，LWIR 无谱线
}

_lock = threading.Lock()


def log(msg):
    with _lock:
        print(msg, flush=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(msg + "\n")


def iso_ids(mol):
    """返回该分子全部同位素的 HITRAN 全局 iso id 列表。"""
    M = MOL_M[mol]
    key = hapi.ISO_INDEX["id"]
    return [hapi.ISO[(M, i)][key] for i in sorted(k[1] for k in hapi.ISO if k[0] == M)]


def chunk_name(mol, a, b):
    return os.path.join(RAW, "%s_%05d_%05d.par" % (mol, round(a), round(b)))


def parse_records(txt):
    """解析 HITRAN 定宽 .par 记录，返回 (molec_id, iso_id, nu) 列表。"""
    rows = []
    for line in txt.splitlines():
        if len(line) < 67:
            continue
        try:
            rows.append((int(line[0:2]), int(line[2:3]), float(line[3:15])))
        except ValueError:
            continue
    return rows


def fetch_chunk(mol, a, b, iso_str):
    """下载并校验一个谱线块；返回 (ok, msg, nbytes, nlines, seconds)。"""
    fn = chunk_name(mol, a, b)
    if os.path.exists(fn) and os.path.getsize(fn) >= 0:
        meta_path = fn + ".meta"
        if os.path.exists(meta_path):
            try:
                m = json.load(open(meta_path, encoding="utf-8"))
                if m.get("ok"):
                    return True, "cached", m.get("bytes", 0), m.get("nlines", 0), 0.0
            except Exception:
                pass
    url = "%s?iso_ids_list=%s&numin=%g&numax=%g" % (HOST, iso_str, a, b)
    last = "no attempt"
    for attempt in range(1, 4):
        t0 = time.time()
        try:
            r = requests.get(url, headers=UA, timeout=1200)
            if r.status_code != 200:
                last = "HTTP %d" % r.status_code
            else:
                txt = r.text
                rows = parse_records(txt)
                bad_mol = [x for x in rows if x[0] != MOL_M[mol]]
                if bad_mol:
                    last = "molecule mismatch (%d rows)" % len(bad_mol)
                elif rows:
                    nus = [x[2] for x in rows]
                    if min(nus) < a - 0.02 or max(nus) > b + 0.02:
                        last = "range violation [%.2f,%.2f]" % (min(nus), max(nus))
                    elif any(nus[i] > nus[i + 1] + 1e-6 for i in range(len(nus) - 1)):
                        last = "not sorted"
                    else:
                        tmp = fn + ".tmp"
                        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
                            f.write(txt)
                        os.replace(tmp, fn)
                        nb = os.path.getsize(fn)
                        with open(fn + ".meta", "w", encoding="utf-8") as f:
                            json.dump(dict(ok=True, mol=mol, numin=a, numax=b,
                                           nlines=len(rows), bytes=nb,
                                           fetched_at=time.strftime("%Y-%m-%dT%H:%M:%S")),
                                      f, ensure_ascii=False)
                        return True, "n=%d" % len(rows), nb, len(rows), time.time() - t0
                else:
                    # 空区间：HITRAN 该区间无谱线，写空文件即视为完成
                    with open(fn, "w", encoding="utf-8", newline="\n") as f:
                        f.write("")
                    with open(fn + ".meta", "w", encoding="utf-8") as f:
                        json.dump(dict(ok=True, mol=mol, numin=a, numax=b, nlines=0,
                                       bytes=0, fetched_at=time.strftime("%Y-%m-%dT%H:%M:%S")),
                                  f, ensure_ascii=False)
                    return True, "empty", 0, 0, time.time() - t0
        except Exception as e:  # noqa: BLE001
            last = "%s: %s" % (type(e).__name__, str(e)[:80])
        time.sleep(1.5 * attempt)
    return False, "FAILED " + last, 0, 0, 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--chunk", type=float, default=50.0)
    ap.add_argument("--species", default="O3,N2O,CO")
    ap.add_argument("--serial", action="store_true", help="只用 1 个线程（排查并发串数据）")
    args = ap.parse_args()
    species = [s.strip() for s in args.species.split(",") if s.strip()]
    if args.serial:
        args.workers = 1

    log("=" * 70)
    log("[start] %s  分子=%s  chunk=%.0f cm-1  workers=%d"
        % (time.strftime("%Y-%m-%d %H:%M:%S"), species, args.chunk, args.workers))
    iso = {m: ",".join(str(v) for v in iso_ids(m)) for m in species}
    for m in species:
        log("  iso_ids %s = %s" % (m, iso[m]))

    jobs = []
    for mol in species:
        for (lo, hi) in RANGES[mol]:
            a = lo
            while a < hi - 1e-9:
                b = min(a + args.chunk, hi)
                jobs.append((mol, a, b))
                a = b
    log("[plan] 共 %d 个谱线块" % len(jobs))

    t0 = time.time()
    done = 0
    total_bytes = 0
    failed = []
    lock2 = threading.Lock()

    # 心跳：每 30 s 打印一次已落盘原始线表字节数，便于观察下载是否卡死
    stop_beat = threading.Event()

    def heartbeat():
        while not stop_beat.wait(30.0):
            try:
                nb = sum(os.path.getsize(os.path.join(RAW, f))
                         for f in os.listdir(RAW) if f.endswith(".par"))
            except OSError:
                nb = 0
            log("[heartbeat] 已落盘 %d MB, 进行中 %d/%d 个块, 已用 %.0fs"
                % (nb / 1e6, done, len(jobs), time.time() - t0))

    threading.Thread(target=heartbeat, daemon=True).start()

    def one(job):
        mol, a, b = job
        ok, msg, nb, nl, sec = fetch_chunk(mol, a, b, iso[mol])
        return job, ok, msg, nb, nl, sec

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(one, j) for j in jobs]
        for fut in as_completed(futs):
            job, ok, msg, nb, nl, sec = fut.result()
            with lock2:
                done += 1
                total_bytes += nb
                if not ok:
                    failed.append(job)
                rate = total_bytes / max(time.time() - t0, 1e-6) / 1024.0
                log("[progress %d/%d] %s %g-%g: %s  %.2f MB total  %.1f KB/s  %.1fs"
                    % (done, len(jobs), job[0], job[1], job[2], msg,
                       total_bytes / 1e6, rate, sec))

    stop_beat.set()

    # 失败块串行重试一遍
    if failed:
        log("[retry] %d 个块串行重试" % len(failed))
        still = []
        for job in failed:
            mol, a, b = job
            ok, msg, nb, nl, sec = fetch_chunk(mol, a, b, iso[mol])
            log("  retry %s %g-%g: %s" % (mol, a, b, msg))
            if not ok:
                still.append(job)
        failed = still

    status = dict(time=time.strftime("%Y-%m-%dT%H:%M:%S"),
                  n_jobs=len(jobs), n_failed=len(failed),
                  failed=[list(j) for j in failed],
                  total_bytes=total_bytes,
                  elapsed_s=round(time.time() - t0, 1))
    with open(os.path.join(RAW, "_fetch_status.json"), "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False, indent=2)
    log("[done] 用时 %.0fs  下载 %.2f MB  失败 %d" %
        (time.time() - t0, total_bytes / 1e6, len(failed)))
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
