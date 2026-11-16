# 实验报告：透明桌宠窗口能不能收到鼠标事件？

> task-11 · `pet-renderer` · 2026-09-30
> 三个实验全部在 `pet\host\experiments\` 下独立进行，**没有改任何生产代码**。
> 每个结论都附实测读数与截图；截图在 `experiments\shots\`。

---

## 0. 结论（一句话）

**能。两个方案实测成立（C 与 A），一个被否决（B）。**
**推荐 C（WPF 层带 alpha=1/255 剪影）** —— 它保住现有架构、零新增运行时；
**A（Electron + symlink 运行时）** 作为备选，代价也比 task-1 判断的小得多：**磁盘只要 0.01 MB**（不是 366 MB）。

| 方案 | 透明是否仍成立 | 窗口能否被命中 | **页面是否真的收到点击** | 结论 |
|---|---|---|---|---|
| **C** WPF alpha=1/255 剪影 | ✅ 截图不可见 | ✅ 人物区返回自己 | ✅ 页面计数 `0 → 2` | **成立，推荐** |
| **B** Win32 色键分层 | ❌ WebView2 区域是**实心品红** | 父窗口 ✅ / **子窗口 ✗** | ❌ 页面计数不动 | **否决** |
| **A** Electron 透明窗口 | ✅ | ✅ 仅 CT-OFF 时 | ✅ 页面计数 `0 → 4` | **成立，备选** |

---

## 1. 根因回顾与实验方法

根因（task-1 实测）：`AllowsTransparency=True` 的 WPF 分层窗口，WPF 自身绘制表面是空的
（内容全在 WebView2 子窗口里），整窗 alpha=0 → Windows 按 alpha 命中 → **整个窗口连同它的子窗口
都被跳过**。`hitmap.ps1` 231 点全 `0/231`。

**实验方法统一为两条互不依赖的证据**：

1. **`WindowFromPoint` + `GetAncestor(GA_ROOT)`**：谁会被投递点击。用返回 HWND 的**类名**区分
   「命中顶层窗口」还是「命中 WebView2 子窗口」——后者才意味着**页面**能收到事件。
2. **页面侧事件计数**：页面把 `mousedown`/`pointerdown` 通过 `postMessage`（WebView2）
   或 `ipcRenderer`（Electron）报回宿主，宿主写进 JSON。这样"点击有没有到页面"是**页面自己说的**，
   不是我们从外面推断的。
3. 真实点击只在 `WindowFromPoint` 明确返回我们窗口时才注入，**绝不误点用户桌面**。

---

## 2. 实验 C：WPF 层带 alpha=1/255 的剪影

### C1 —— 纯 WPF，先证明"1/255 能不能恢复命中"

窗口 420×300 @ (60,60)，四个探针：A 矩形 alpha=1/255、B 矩形 alpha=0、C 矩形不透明、D 窗口空白处。

```
label           route     hit        hitClass
A alpha=1/255   ours(top) 0x30690    HwndWrapper[...]      <- alpha=1 恢复了命中
B alpha=0       OTHERS    0x3072c    Chrome_RenderWidget   <- alpha=0 仍然穿透
C opaque        ours(top) 0x30690    HwndWrapper[...]
D empty area    OTHERS    0x30682    CASCADIA_HOSTING...   <- 窗口空白处穿透
```
**4/4 符合预期。**（读数：`c1-alpha\c1-result.json`，截图 `shots\c1-wpf-alpha.png`）
截图里 **alpha=1 的矩形完全看不见**（桌面文字照旧），只有不透明的绿块可见 ——
也就是说 **alpha=1/255 在视觉上等价于透明，但在命中上前者算"实体"**。这正是需要的那条缝。

### C2 —— WPF + WebView2：左半窗铺 alpha=1 剪影，右半窗不铺

页面在左半窗画一个不透明红圆（代表"她"），其余透明。

```
P1 页面不透明处 + alpha=1 : route=ours(child)  hit=Chrome_RenderWidgetHostHWND (msedgewebview2)
P2 仅 alpha=1（页面透明） : route=ours(child)  hit=Chrome_RenderWidgetHostHWND
P3 什么都没有（右半窗）   : route=OTHERS       hit=CASCADIA_HOSTING...
页面计数：0 -> 2        <- 真实点击注入后，页面自己报的
```
**P1/P2 命中的是 WebView2 子窗口**，所以点击会进入页面；**P3 仍然穿透**。
页面侧事件日志（`c2-wpf-webview2\c2-show.log`）：

```
MSG {"kind":"move","x":120,"y":160,"n":0}
MSG {"kind":"down","x":120,"y":160,"n":1}     <- 页面收到真实 mousedown
MSG {"kind":"down","x":120,"y":160,"n":2}
```
截图 `shots\c2-wpf-webview2.png`：红圆浮在桌面上、绿字 **"page clicks: 2"**、
**桌面文字一直延伸到圆的边缘** —— 透明没有被破坏。

> **为什么 P1 和 P2 都命中子窗口？** 父窗口在该点 alpha≠0 → 命中测试**下探到子窗口** →
> 子窗口（WebView2 内容窗口）成为命中目标。这也解释了 task-1 为什么全穿透：父窗口到处都是
> alpha=0，整棵子树在第一步就被跳过了。

### C 的新缺陷 / 代价

- **没有视觉缺陷**：alpha=1/255 肉眼不可见（C1 截图已证）。
- **粒度**：可点区域 = 你在 WPF 层画出的剪影。若画成整个矩形，则**她周围的空气也会挡住桌面点击**
  （C2 的 P2 就是这个现象）。要做到"只有她身上可点"，需要把轮廓喂给 WPF 层（见 §5 落地清单）。
- **子窗口命中是"整块"的**：只要父窗口在该点可命中，就命中子窗口，页面内部再靠自己
  `hitTest` 细分头/身体。所以 WPF 剪影只需要**粗粒度**，精修交给页面 —— 这让实现难度下降一档。

---

## 3. 实验 B：Win32 色键分层（`LWA_COLORKEY`）

WinForms 顶层窗口 + `WS_EX_LAYERED` + `SetLayeredWindowAttributes(0x00FF00FF, 0, LWA_COLORKEY)`；
窗口自带背景 = 纯品红；**左半窗**挂 WebView2（页面背景也是纯品红 + 一个蓝圆），**右半窗**只有父窗口
自己（品红背景 + 一个父窗口画的绿块）。

API 确实生效了：`SetLayeredWindowAttributes=True  key=0x00ff00ff  flags=1  exStyle=0x90008`。

```
Q1 父窗口品红（右半窗，无子窗口）: OTHERS     <- 父窗口自己的品红被抠掉了 ✅
Q2 父窗口绿块                    : ours(child) <- 父窗口画的东西可见可点 ✅
Q3 子窗口品红（页面背景）        : OTHERS
Q4 子窗口蓝圆（页面不透明内容）  : OTHERS     <- 子窗口完全不可命中 ❌
页面计数：-1 -> -1（没有点击到达页面）
```
截图 `shots\b-colorkey.png` 是决定性的：**左半窗是一整块实心品红**（蓝圆和白底计数条压在上面），
右半窗的品红被正确抠透、桌面可见。

**结论：色键只作用于窗口自己的重定向表面，管不到 WebView2 的 GPU 合成输出。**
于是 B 同时输在两件事上：① WebView2 区域变成一块实心品红（透明不成立）；
② WebView2 子窗口完全不可命中（页面收不到点击）。**B 否决。**

---

## 4. 实验 A：Electron 透明窗口（含代价量化）

### 4.1 关键发现：可以**不复制** 366 MB 运行时

Windows 文件**符号链接在本机不需要管理员权限**（实测 `New-Item -ItemType SymbolicLink` 成功；
目录用 Junction 也行）。于是 `dist\` 里：

- `DeepSeek Harness.exe` 及 14 个运行时文件 → **symlink** 指回 `D:\DeepSeek Harness\`
- `locales\` → **junction**
- `resources\default_app.asar` → symlink（Electron 只有在 `resources\app.asar` **不存在**时
  才会回落到 `default_app.asar` + 命令行给的 app 目录）
- `resources\app\` → **只有我们的 app，真文件**

**并且实测确认：Electron 是"按 symlink 所在目录"找 `resources` 的，不是按目标目录**：

```
execPath      = ...\experiments\a-electron\dist\DeepSeek Harness.exe
resourcesPath = ...\experiments\a-electron\dist\resources
```

（这一点先用 **Node 模式**零风险探明：`ELECTRON_RUN_AS_NODE=1` 跑一个 .cjs 打印 `resourcesPath`，
此时不会加载任何 app.asar，所以不存在"误启动 DSH"的风险。）

### 4.2 磁盘

| | 字节 | MB |
|---|---|---|
| dist 实际占用（真文件） | 5,537 | **0.01** |
| 全量复制等效 | 383,954,613 | 366.17 |
| **省下** | 383,949,076 | **366.16** |

15 个 symlink + 1 个 junction；"Explorer 显示大小"也是 0.01 MB（symlink 的 Length 记 0）。

### 4.3 启动 / 内存

- **启动**：进程内 `t0 → 窗口显示` = **524 / 576 / 624 ms**（三次）≈ **0.6 s**；
  从 `Start-Process` 到窗口显示的墙钟 = **3.1 s**（含 Chromium 冷启动与磁盘缓存）。
- **内存**：整棵进程树 **4 个进程 / 498–499.6 MB working set**。这是 A 方案真正的代价
  （与用户现在的 DSH 主进程同量级）。

### 4.4 命中与点击

```
CT-ON （setIgnoreMouseEvents(true,{forward:true})，生产默认）
  dot(不透明处) -> OTHERS   corner(透明处) -> OTHERS      <- 完全穿透
CT-OFF
  dot -> ours(child)  corner -> ours(child)               <- 整窗可命中
  真实点击注入 -> 页面计数 0 -> 4                          <- 页面收到了
```
截图 `shots\a-electron-ct-off.png`：红圆浮在桌面上、绿字 **"page clicks: 4"**、桌面文字延伸到圆边缘。
另一张 `a-electron-ct-on.png` 是 CT-ON 状态。

**新缺陷**：`setIgnoreMouseEvents` 是**整窗**开关，CT-OFF 时**整个矩形**都会挡住桌面点击
（corner 也变成 ours）。上游的解法是**每 90 ms 轮询页面 `hitTest(鼠标位置)` 再切换开关**
（`desktop/windows/main.js:89-107`，我们 task-1 也抄过），这样就能做到近似逐像素。

### 4.5 实验中踩到的两个坑（都会影响未来实现）

1. **`ELECTRON_RUN_AS_NODE`**：DSH 会给所有子进程注入它，Electron 会退化成 Node 并报
   `bad option: --x=60`。启动前必须清掉。
2. **打包版 `process.argv[1]` 就是第一个开关**：`process.argv.slice(2)` 会**吞掉 `--x=60`**，
   窗口跑到默认位置，导致我一度以为"窗口没显示"。正确写法是
   `process.argv.filter(a => a.startsWith('--'))`。

---

## 5. 推荐与代价表

### 5.1 推荐：**C（WPF alpha=1/255 剪影）**

理由：保住现有 WPF+WebView2 宿主（透明已验证、面板集成已完成、无第二套运行时），
新增的只是一层"命中剪影"和一条页面→宿主的掩码通道。

### 5.2 代价表

| | **C（推荐）** | **A（备选）** | B（否决） |
|---|---|---|---|
| 磁盘 | **+0**（纯代码） | **+0.01 MB**（symlink；全拷贝 366.17 MB） | +0 |
| 内存 | 不变（沿用现有宿主） | **+498 MB / 4 进程** | 不变 |
| 启动 | 不变 | **+0.6 s**（进程内）/ +3.1 s（冷启动墙钟） | 不变 |
| 透明 | 已成立（C1/C2 截图） | 已成立 | **不成立**（实心品红） |
| 页面收点击 | **成立（实测 0→2）** | **成立（实测 0→4）** | 不成立 |
| 逐像素点击穿透 | 需自己维护剪影掩码 | 轮询 `hitTest` + 开关（上游现成做法） | — |
| 复杂度 | 中：宿主画掩码 + 页面报掩码（IPC 已有） | 中：换宿主 + symlink dist | 低，但没用 |
| 风险 | 低（依赖分层窗口按 alpha 命中的既有行为） | 低（但要维护 symlink dist；依赖 Developer Mode/管理员才能建符号链接） | — |

> **如果三个都失败**（本实验未发生）：结论应是"保持只读桌宠"，把 12 项鼠标能力从路线图移除，
> 并且不要留半成品按钮。这里 C 与 A 都成立，所以那条兜底不需要。

### 5.3 最小落地改动清单（**本任务未实施**）

**若选 C**（生产文件分别是 `pet\host\host.ps1`、`pet\renderer\pet-app.js`）：

1. `pet\renderer\pet-app.js`：`PetAPI` 已有 `hitTest(x,y)`；新增
   `PetAPI.mask(cols,rows)` → 返回 `cols×rows` 的 0/1 掩码字符串（复用上游 `buildMask` 的思路：
   读画布 alpha，阈值 ~26/255）。每 ~300 ms 推一次。
2. `pet\host\host.ps1`：在承载 WebView2 的 `Grid` 里，**在 WebView2 下面垫一个 `Canvas`**，
   按掩码画 `cols×rows` 个 `Rectangle`，`Fill = SolidColorBrush(Color.FromArgb(1,0,0,0))`。
   掩码变了就重画（256–1024 个矩形，WPF 扛得住）。
3. `pet\host\host.ps1`：把窗口位置/尺寸随剪影一起更新（剪影按窗口坐标画，天然跟着走）。
4. 点击到达页面后，**页面内部再用自己那份精细 alpha 掩码决定**是摸头、摸身体还是穿透
   （上游 `hitTest` + `POKE_HEAD`/`POKE_BODY` 可直接移植）。
5. 验证：复用 `experiments\lib\win.ps1` 的 `Test-ExpPoint` 做 A/B 探针
   （人物处应 `ours`，空白处应 `OTHERS`），再用页面计数确认点击到达。

**若选 A**：`pet\renderer\host-electron\` 换回 Electron，但 **runtime 改为 symlink dist**（§4.1 的
`make-dist.ps1` 可直接搬），并加上 §4.5 的两个坑的修复 + 上游的 90 ms hitTest 轮询。

---

## 6. 产物与复现

```
pet/host/experiments/
  REPORT.md                     <- 本文
  lib/win.ps1                   <- 共享探针（WindowFromPoint/类名/真实点击/截图/内存）
  lib/webview2/                 <- 复用的 WebView2 SDK dll
  c1-alpha/     c1-show.ps1  c1-run.ps1  c1.json  c1-result.json
  c2-wpf-webview2/ c2-show.ps1 c2-run.ps1 c2.json c2-result.json c2-show.log
  b-colorkey/   b-show.ps1  b-run.ps1  b.json  b-result.json  b-show.log
  a-electron/   make-dist.ps1  a-run.ps1  dist-cost.json  a-result.json
                app/{package.json,main.js,preload.js,page.html}   dist/（symlink，0.01 MB）
  shots/        c1-wpf-alpha.png  c2-wpf-webview2.png  b-colorkey.png
                a-electron-ct-on.png  a-electron-ct-off.png
  probe/        symprobe.cjs  symprobe.txt（resourcesPath 探明）
```

复现（全部纯 ASCII 脚本、无 `.cmd`/`.bat`、无隐藏窗口/提权开关）：

```powershell
$E = "F:\dsh-usage-widget\pet\host\experiments"
& "$E\c1-alpha\c1-run.ps1"          # 实验 C1
& "$E\c2-wpf-webview2\c2-run.ps1"   # 实验 C2
& "$E\b-colorkey\b-run.ps1"         # 实验 B
& "$E\a-electron\make-dist.ps1"     # 实验 A：先建 symlink dist
& "$E\a-electron\a-run.ps1"         # 实验 A
```

跑完已清理：所有实验进程已结束，**用户 DSH（pid 17508）全程存活**，未改
`pet\renderer\**`、`ui\**`、`engine\**`、`verify-project.ps1`。
`dist\` 保留（只有 5.5 KB，且是可复现的产物）。
