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

- `i = arccos(cos φ · sin A)`：由发射场纬度 φ 与射向 A 定**轨道倾角**（注：该公式忽略地球自转；含自转的 3DOF 积分给出 94.65°，与观测射向自洽，见第九节）；
- 若按太阳同步轨道（SSO），用 J2 进动反解对应**高度**；
- 传播方位角不确定度 → 倾角/高度/横向偏差；
- 输出前 1000 km 的地面轨迹采样。

**只能定轨道平面（倾角/射向），不能定 a/e/近地点/速度**——NOTAM 没有速度与各级落区时刻；要完整轨道需 T0（秒级）+ 落区时刻 + 弹道模型，或发射后的 TLE。
---

## 九、按“长征二号丁”参数重算（v2，2026-11-12 修正）

> v1（`trajectory3d.py` + 旧 `make_traj_layer.py`）存在几处硬伤：质量账缺口 5.1 t；二级“推力沿惯性速度”一路硬推，
> 入轨速度 10.1 km/s、e=0.86、近地点在地面以下；地图落点直接写 NOTAM 盒中心、上升段被重投影到大圆上（最大偏 55 km）；
> 经纬度回绕写成 -180（应 -360）；T0 硬编码成 2025 年。v1 文件保留作对照，但结论以下面的 v2 为准。

```bash
python trajectory3d_v2.py     # -> ../trajectory3d.json + ../trajectory3d.png（含 J2，dt=0.1 收敛）
python make_traj_layer.py     # -> ../traj3d.js（读 json；不再重投影、不再写死落点）
```

地图显示：`index.html` 的「🛰 3D 弹道/轨道」图层直接画修正后的弹道（黄色=上升段、青色虚线=滑行段、紫色虚线=入轨后一轨），
落点/入轨点用编号事件标记；旧版「推测弹道轴」默认不勾选（仍可在图层控制里打开）；3D 悬浮窗左上角 🎯 可把地图定位到弹道。
`../map3d.png` 已替换为修正后的地图截图。

**参数（代表性，非官方）**：太原 38.849N 111.608E，射向 **188.2°**（由 A5897/A5898 连线反推）；
两级：m0=**232.0 t** = 一级 175 t 装药 + 10 t 干重 + 二级 40 t 装药 + 4.5 t 干重 + 载荷 1.0 t + 整流罩 1.5 t；
T1=2962 kN/ve1=2650 m/s，T2=742 kN/ve2=2900 m/s；一级按 0.48°/s 俯仰角速率转弯，整流罩 206 s 分离；
二级一次点火进入 550 km 转移轨道，滑行到远地点后二次点火圆化（该推力/装药量下，直接一次点火入轨 550 km 做不到）。

| 事件 | v2 结果（积分） | NOTAM 观测 | 差 |
|---|---|---|---|
| 一级关机/分离 | 156.6 s，61.7 km，2.327 km/s | — | — |
| 一级落点 | **622.9 km**，33.2939N 110.5368E | A5897/26 中心 616.8 km，33.3625N 110.5958E | **9.4 km，落在区内** |
| 整流罩分离 | 206.1 s，103.5 km | — | — |
| 整流罩落点 | **962.2 km**，30.2598N 109.9947E | A5898/26 中心 966.8 km，30.2458N 110.0792E | **8.3 km，落在区内** |
| 二级一次关机 | 311.1 s，152.1 km，7.899 km/s | — | 转移轨道 6408×6921 km |
| 入轨 | **547.1 km**，a=6919.6 km，e=0.0002，i=**94.65°**，95.5 min，v=7.59 km/s | 无约束 | J2 使实际远地点比瞬时目标低 ~3 km |

结论：

1. 一级落区和整流罩落区能被**同一套自洽参数**同时装进 A5897/26 与 A5898/26（分别 9.4 km、8.3 km），落点全部由积分给出，不再依赖“写死盒中心 + 重投影”；
2. 质量账闭合：232.0 = 175 + 10 + 40 + 4.5 + 1.0 + 1.5；二级末端 5.6 t ≥ 干重+载荷 5.5 t（推进剂余量约 0.1 t，即该模型对 550 km 的运载能力约 1 t）；
3. 入轨倾角 **94.65°**，与“标准几何公式” `i=arccos(cosφ·sinA)` 的 96.4° 不同：后者忽略地球自转。含地球自转的 3DOF 积分给出 94.65°，且与观测到的 188.2° 升段地面航迹自洽；
   若任务目标真是 SSO 550 km（需 i≈97.4°、射向≈189.5–190.5°），则与 NOTAM 连线（188.2–188.8°）不一致——这些数据更支持“非 SSO 的 ~94.6° 轨道”，或射向/目标另有调整；
4. 仍属“代表性重建”：一子级/整流罩气动系数、上面级可重启、T0（其不确定度不影响地面相对弹道）等为假设；不是官方弹道，不能用于实际航行。

v1 → v2 对照：

| 项 | v1 | v2 |
|---|---|---|
| 质量账 | m0=232 t 但分系统合计 237.1 t；二级末端 2.2 t < 干重+载荷 7.6 t | 自洽，末端 5.6 t |
| 二级 | 推力沿惯性速度，10.1 km/s，e=0.86，近地点地下 | 转移 + 滑行 + 远地点圆化，e=0.0002，547 km |
| 落点 | 事件写死盒中心；上升段重投影大圆（最大偏 55 km） | 积分真实落点，不重投影 |
| 参数 | README 数字依赖隐藏的 `thrust_dir.__defaults__=(88,0.28)`，与默认脚本不一致 | 单一参数，可复现 |
| 经度回绕 | >180° 减 180（应减 360），一轨错 180° | 已修正 |
| T0 | 硬编码 2025-11-18 | 2026-11-18 |
| 步长 | dt=0.5 未收敛（一级落点 633→621 km，二级 a 28835→14190 km） | 上升 dt=0.1、滑行 0.5、圆化 0.01 |

---

## 十、火箭云观测质量场预测（2026-11-12）

```bash
python rocket_cloud.py    # -> ../rocket_cloud_quality.png（连续质量图）
                          #    ../rocketcloud_quality.png（网页用 Mercator 透明热力图）
                          #    ../rocketcloud.js（网页图层数据）
```

几何判据：清晨发射时地面还在晨昏蒙影（太阳高度 < -6°），火箭飞到 50–150 km 的尾迹已被阳光照亮。

- 尾迹被照亮：e_plume > -β(h)，β=acos(R/(R+h)) 为高度 h 处的地平俯角；
- 尾迹在地平线以上：观测点到尾迹星下点的大圆距离 < R·β(h)。

**连续观测质量 Q**（0–1，相对值，最高点归一为 1，不是统计概率）：

```
Q = D × L × V × C     （对尾迹各采样取 max）
D = logistic(天空暗度, 中心 -6°, 宽度 2.2°)       —— 晨昏线附近平滑，线右侧仍 >0
L = logistic(尾迹照亮余量 e_plume+β(h))          —— 贴阴影边界时减半
V = 1 - exp(-尾迹仰角/4°)                        —— 贴地平线→0，20°以上≈1
C = logistic(尾迹方向与太阳方向夹角, 中心 35°)    —— 正对晨光小，背向太阳大
```

结果（T0=2026-11-19 06:44:30 CST）：

- Q 最高点 ≈ 40.3°N, 109.5°E（包头附近，100%）；成都 94%、西安 93%、重庆 92%、呼和浩特 89%、太原 86%、银川 84%；
- 兰州 47%（天很暗但正对晨光）、石家庄 47%、郑州 39%、北京 33%、武汉 17%、上海 1% —— **晨昏线右侧贴近线的地区 Q 不为 0，是平滑衰减**；
- 酒泉 8%（正对晨光且贴地平线）；敦煌、乌鲁木齐 0（尾迹低于地平线或天已大亮）；
- 面积：Q>0.3 约 **294 万 km²**，Q>0.6 约 **164 万 km²**（对照：二值 -6° 几何可见区约 313 万 km²）。

文件与图层：

- `../rocket_cloud_quality.png`：连续质量场静态图（含 35°N 跨晨昏线剖面，展示右侧非零）；
- `../rocketcloud_quality.png`：网页用 Mercator 透明热力图；
- `../rocketcloud.js`：`index.html` 的「🌅 火箭云观测质量」图层（默认勾选）——热力图 + 晨昏线 + 城市 Q 点（点开有 Q、仰角/方位、太阳高度），图例为 Q 渐变色条；
- 截图见 `../rocket_cloud_map.png`。

局限：Q 的 4 个因子与 logistic 参数是**经验性的**，未用任何实际“火箭云”观测标定；没有模拟尾迹亮度、扩散、天气、地形遮挡和月光。Q 只能读作“相对观测条件好坏”，不是“看到概率”。T0 不确定度约 ±分钟级，晨昏线随 T0 平移约 25 km/min。
