# NOTAM 数据源：实测记录与工具

> 测试时间：2026-11-12（北京时间）｜测试网络：中国大陆家宽｜方法：PowerShell / Edge headless
> 结论先说：**中国官方有一个免费、无需登录的 NOTAM 数据出口——民航局空管局情报中心 eAIP China 的月度 NOTAM Summary（含面状危险区坐标）**。本目录里的 `notams.json / notams.js` 就是用它生成的。

---

## 一、可用：CAAC AIS · eAIP China 月度 NOTAM Summary（当前采用）

| 项 | 值 |
|---|---|
| 列表接口 | `POST https://www.eaipchina.cn/eaip/homeFile/listPublish`，body `{"pageNum":1,"pageSize":100}` |
| 下载地址 | `GET https://www.eaipchina.cn/eaip/homeFile/{filePath}`（`filePath` 里的 `\` 换成 `/`，空格 URL 编码） |
| 最新文件 | `NOTAM Summary In Nov.2026` → `homeFile/NOTAM_SUMMARY/NOTAM Summary In Nov.2026/2026-11.zip`（约 1.4 MB） |
| 压缩包内容 | `A.pdf E.pdf F.pdf G.pdf L.pdf M.pdf U.pdf W.pdf Y.pdf`（按 NOTAM 系列分册） |
| 内容说明 | “The following NOTAM were **still in force on 2026-11-02** …”，即当月 2 日的有效快照，含 `TEMPORARY DANGER AREA ESTABLISHED BOUNDED BY: NddmmssEdddmmss-…` 全部坐标 |
| 更新频率 | 每月初（当前最新 2026-11 期，2026-11-04 发布） |
| 费用 | 免费，无需登录 |
| 局限 | 快照时点是每月 1–2 日；**当月 3 日以后新发的 NOTAM 不在里面**（要实时得登录 eAIP） |

已解析出的面状 NOTAM（见 `../notams.json`）：

- `A 4484/26` **ZB(SR)801 北京特别限制区**：`A CIRCLE WITH A RADIUS OF 300KM CENTERED AT N395410E1162327`，SFC–UNL，H24，PERM（这条是现行有效的）
- `A 3167/26 / A 5562/26 / A 5624/26 / A 5672/26 / A 5673/26`：11/3–11/6 的临时危险区（已结束，可用于和海事局航警对照）

## 二、可用但需账号：eAIP 在线 NOTAM 查询

- 入口 `https://www.eaipchina.cn/`（页面上有 NOTAM Summary 下载区 + eAIP 登录）
- 接口 `POST https://www.eaipchina.cn/eaip/notamSummary`：未登录返回 `{"retCode":0,"retMsg":"login has expired"}`，需 token
- 航空公司 / 通航运行人可向情报中心申请账号，可查实时 NOTAM

## 三、存在但本网络抓不到

| 源 | 状态 | 说明 |
|---|---|---|
| [FAA NOTAM Search](https://notams.aim.faa.gov/notamSearch/) | **403（Akamai 拦截）** | 覆盖中国 FIR（ZBPE/ZGZU/ZSSS…）的实时 NOTAM，**能访问的话是最好的免费实时源**；GitHub 项目 [mikezang/NotamForChina](https://github.com/mikezang/NotamForChina) 正是用它解析中国发射 NOTAM |
| `www.notams.faa.gov`（DINS） | DNS 不存在 | 已退役，旧脚本里的地址失效 |
| [Notamify](https://api.notamify.com/api/v2) | 401 / Cloudflare | 有中国数据、有公开文档；`Authorization: Bearer <key>`，按页计费（1 credit/页）；网页端有 Cloudflare 质询 |
| [PilotEFB](https://pilotefb.com/notams/zsha/) | 页面可看、API 401 | 覆盖中国 9 个 FIR + 213 个机场；`/api/notams?icao=` 要 `x-turnstile-token`（Cloudflare Turnstile），人工浏览器能过，脚本过不去 |
| OpenAIP / SkyDrop 空域包 | 无中国数据 | 国家包列表里没有 `cn`，中国空域（P/D/R 区）在 OpenAIP 无覆盖 |
| 商业 API（Aviation Edge 等） | 付费 | 未测 |

## 四、工具链

```bash
# 1. 下载最新一期 NOTAM Summary（zip 解压后得到 9 个 PDF）
python fetch_notam_summary.py ./notam_data

# 2. PDF → 文本（需要 poppler 的 pdftotext；TeX Live 自带）
pdftotext -enc UTF-8 A.pdf A.txt   # 对 9 个 PDF 各做一次

# 3. 解析：临时危险区 / 限制区 → notams.json + notams.js
python parse_notam_summary.py ./notam_data/txt ..

# 4. 打开 ../index.html，点「📡 NOTAM」标签页
```

脚本规则：

- 只保留 **11 月仍有效或 PERM** 的面状区域
- 几何两种：`E)` 里出现 `RADIUS OF xxx KM/NM CENTERED AT NddmmssEdddmmss` → 圆；出现 ≥3 个 `NddmmssEdddmmss` → 多边形
- 状态按 B)/C) 与当前时间比较：`active / ended / upcoming`

## 五、如果以后要做“实时”

1. 拿一台能访问 `notams.aim.faa.gov` 的机器（或 VPN），按 FIR 搜 `ZBPE / ZGZU / ZSSS / ZSHA / ZJSA / ZYSH / ZLHW / ZPKM / ZWUQ / ZHWH`，导出 Raw 文本 → 直接喂给 `parse_notam_summary.py`（同一套正则）。
2. 或者买 Notamify API key，把 `GET /api/v2/notams?location=ZSSS` 的结果映射成同样的 `notams.json` 结构（字段：`id / fir / kind / begin_utc / end_utc / geom / e`）。
3. `index.html` 只依赖 `notams.js`，换数据源不用改前端。

---

## 附：2026-11-12 日本代理复测（用户提供代理后）

代理生效确认：出口 IP `94.177.131.182`（Tokyo / AS199524 G-Core Labs），系统代理 `127.0.0.1:7890`。
结论：**换日本代理只解决了一半问题**——Cloudflare 类站点能过，Akamai 类站点仍按 IP 拦。

| 目标 | 复测结果 | 原因 |
|---|---|---|
| `notams.aim.faa.gov/notamSearch/nsapp.html` | **403 Access Denied**（PowerShell / Edge headless / Edge 真实窗口 全部一样） | Akamai 按 IP 段拦截：该出口是数据中心 IP，不是住宅/美国线路 |
| FAA（经 Jina Reader / allorigins / codetabs / corsproxy / cors.eu.org 等中转） | 522 / 401 / 429 / 403 | 中转出口同样被 Akamai 拒；公共 CORS 代理限流 |
| `notamify.com` | **Cloudflare 通过**（真实 Edge + 代理可正常出页面） | 但内容在付费墙后：`Current NOTAMs for ZSHA — Unlock Notamify Pro`，$24.9/月（7 天试用）；API 仍需 Bearer key |
| `pilotefb.com/notams/zsha/` | 页面能开，但 **Turnstile 过不去**（“verification could not run / A quick bot check”） | 数据中心 IP 被 Turnstile 判为高风险；Jina Reader 抓同样卡在验证页 |
| `r.jina.ai` 中转 | **可达**（此前大陆网络不可达） | 可用于抓普通页面；对 FAA/Notamify 无效 |
| eAIP China 月度汇总 | 仍可用 | 与代理无关 |

### 结论

1. **要拿实时中国 NOTAM，实际只有两条路**：
   - 美国住宅 IP / 合规 VPN 访问 FAA NOTAM Search（覆盖 ZBPE/ZGZU/ZSSS 等中国 FIR，免费）；
   - 民航局 eAIP 账号（航司/通航可申请），走 `https://www.eaipchina.cn/eaip/notamSummary`。
2. 付费方案：Notamify API key（`api.notamify.com/api/v2`，Bearer + credits），代理已能过它的 Cloudflare。
3. 数据中心代理对 Cloudflare 站点有效，对 Akamai（FAA）无效；换住宅代理（最好美国）再试 FAA 才有意义。

### FAA 请求模板（在可达网络下直接跑）

```bash
# 1) 取会话与 cookie
curl -c ck.txt -A "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/131" \
     https://notams.aim.faa.gov/notamSearch/nsapp.html -o /dev/null

# 2) 按 FIR 查询（POST）
curl -b ck.txt -A "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/131" \
  -H "Content-Type: application/x-www-form-urlencoded; charset=UTF-8" \
  -H "X-Requested-With: XMLHttpRequest" \
  -H "Referer: https://notams.aim.faa.gov/notamSearch/nsapp.html" \
  --data "searchType=0&designatorsForLocation=ZBPE&notamsOnly=false&radius=10&radiusSearchOnDesignator=false&radiusSearchUnit=NM&noFlightPathSearch=true&noRadiusSearch=true&pageSize=50&pageNum=0&format=json" \
  https://notams.aim.faa.gov/notamSearch/search
```

返回 JSON 的 `notamList[].icaoMessage` 就是原始 NOTAM 文本，字段与我们 `notams.json` 的 `e / begin_utc / end_utc / fir` 一一对应，解析正则可直接复用。
中国 FIR 代码：`ZBPE ZGZU ZHWH ZJSA ZLHW ZPKM ZSHA ZYSH ZWUQ`。
---

## 六、手工补录单条 NOTAM（manual_notams.json）

月报快照之后新发的 NOTAM 抓不到时，可以直接把原文贴进 `tools/manual_notams.json`，然后重跑解析：

```json
[{
  "id": "A 5898/26", "fir": "ZHWH", "kind": "临时危险区",
  "begin_utc": "2026-11-18T22:44:00+00:00", "end_utc": "2026-11-18T23:10:00+00:00",
  "geom": {"kind": "polygon", "coords": [[30.583333,109.95],[30.55,110.316667],[29.9,110.216667],[29.95,109.833333]]},
  "qline": "ZHWH/QRDCA/IV/BO/W/000/999/3015N11004E022",
  "e": "A TEMPORARY DANGER AREA ESTABLISHED BOUNDED BY: ...",
  "source": "用户提供的原始 NOTAM 文本（CREATED: 11 NOV 2026 03:08 / SOURCE: ZBBBYNYX）"
}]
```

- 状态自动按 B)/C) 与当前时间算：`active / upcoming / ended`
- 地图上 `active` 琥珀色、`upcoming` 黄色虚线、`ended` 灰色虚线
- 已补录样例：`A 5898/26`（ZHWH，2026-11-18 22:44–23:10 UTC，湖北西部临时危险区）<br>- 只给 E) 段、没有编号/时间也能画：`status` 填 `unknown`，图上显示为橙色虚线、"时间未提供"（样例：陕西东南临时危险区）
---

## 七、从 NOTAM 推算发射窗口（launch_window.py）

```bash
python launch_window.py ../notams.json ../
# 输出 trajectory.js：地图上出现「🛰 推测弹道轴」图层
```

算法：

1. 取同一时段内的面状危险区，算几何中心；
2. 相邻中心连线方位角（共线偏差 < 5° 才继续）；
3. 与已知发射场（太原/酒泉/西昌/文昌/海阳）做“连线延长线”匹配，取方位偏差最小者；
4. T0 硬边界 = 各窗口交集 `[max(B), min(C)]`；若各窗口起点相差 ≤2 min，T0 ≈ 最早起点 + 1.5 min；
5. 输出射向、各落区距发射场距离、T0 估算与范围。

**精度与边界**：目前只能给到 ±2–3 min 的“窗口”，不能给秒级点火时刻；要精确 T0 需要发射场 NOTAM + 弹道时间表/历史样本，且 NOTAM 时间本身可能临时调整。属推断，不可用于实际航行。
---

## 八、从方位角估算轨道平面（orbit_estimate.py）

```bash
python orbit_estimate.py ../trajectory.js
```

- `i = arccos(cos φ · sin A)`：由发射场纬度 φ 与射向 A 定**轨道倾角**；
- 若按太阳同步轨道（SSO），用 J2 进动反解对应**高度**；
- 传播方位角不确定度 → 倾角/高度/横向偏差；
- 输出前 1000 km 的地面轨迹采样。

**只能定轨道平面（倾角/射向），不能定 a/e/近地点/速度**——NOTAM 没有速度与各级落区时刻；要完整轨道需 T0（秒级）+ 落区时刻 + 弹道模型，或发射后的 TLE。
---

## 九、按“长征二号丁”参数拟合（2026-11-12）

公开参数近似：起飞 232 t；一级 4×YF-20B 海平面 2962 kN、Isp≈2650 m/s；二级 YF-22E 真空 742 kN、Isp≈2900 m/s；
一级装药 175 t、二级装药 38 t、整流罩 1.5 t、载荷 3.1 t。3DOF 积分（`trajectory3d.py`，射向 188.2°）：

| 事件 | 模型 | NOTAM 观测 | 差 |
|---|---|---|---|
| 一级关机/分离 | 157 s，84.5 km，2.20 km/s | — | — |
| 一级落点 | **633 km**，33.25N 110.39E | A5897/26 **617 km**，33.36N 110.60E | +16 km，位置 ~20 km |
| 整流罩落点（分离 200 s） | 1156 km，28.67N 110.23E | A5898/26 **967 km**，30.25N 110.08E | +189 km，偏南 |
| 整流罩落点（分离 **185 s**） | **961 km，30.4N 110.2E** | A5898/26 **967 km**，30.25N 110.08E | **-6 km，位置差约 15 km** |
| 二级入轨 | 306 s，483 km，10.1 km/s（未闭环制导） | 未知 | 能量偏高，需真实制导 |

结论：
1. 一级落区与 CZ-2D 参数**吻合得相当好**（633 vs 617 km，位置差 ~20 km），支持“太原 + CZ-2D”的猜测；
2. 第二块 967 km 落区：把整流罩分离放到 **185 s**（131 km 高）后，模型落点 961 km / 30.4N 110.2E，与 A5898/26 几乎重合（-6 km）——CZ-2D 整流罩分离本来就在 180–200 s，说明这块就是**整流罩**，不是二级残骸；两块落区 = 一级 + 整流罩，均在内陆；
3. 入轨段需要真实的闭环制导与二级装药量，当前开环模型只能给量级，不能给轨道根数；倾角结论以几何模型（96.4–97.2°）为准。