# pet/renderer —— Live2D 桌宠渲染层（最小可用 + 透明结论）

> 交付人：`pet-renderer`（task-1）· 2026-09-30
> 一句话结论：**逐像素透明成立**，而且有两条路都能跑通；按体积与栈一致原则，推荐 **WPF + WebView2**。

---

## 0. TL;DR

| 问题 | 结论 |
|---|---|
| 能不能做到真正的逐像素透明（模型轮廓外就是桌面）？ | **能**。两条路都实测截图验证过。 |
| 推荐哪条路？ | **WPF + WebView2**（复用系统已装的 WebView2 运行时 `154.0.4258.37`，项目只增加约 0.9 MB）。 |
| Electron 那条路呢？ | 也能，而且唯一能做到「桌宠可以收点击」。但需要复制 **366 MB** 的 Electron 运行时，按 lead 指示已删除，只留 app 代码备注（见 §5）。 |
| 显式 x/y 定位 | **可以**，实测 `1150,320 440x540` 精确生效。 |
| 总在最前（压住 Topmost 的看板） | **可以**，`Topmost=true`，并且宿主每 1.5 s 重提一次以赢得与看板的交错。 |
| 点击穿透 | **可以**：WebView2 方案下窗口天然全程穿透；Electron 方案下 `setIgnoreMouseEvents` 可开可关（关掉时桌宠能收点击）。 |
| 状态标签 | 已接入冻结契约 `pet/STATE-PROTOCOL.md`，读 `renderer/state.json`，不自己判断状态。 |

**验收截图**：`renderer/transparency-proof.png`（WebView2 宿主，真实模型 + 状态标签浮在桌面上，
轮廓外是桌面文字而不是黑/灰底）。

---

## 1. 最终布局

```
pet/
  model/                         ← 素材（68 个文件，5,078,065 字节）
    c_0120.moc3                  2,119,552  sha256 37D62CC7EBE2FE93350C934A2C023AAC44E306833F63D83A130C005E2945CE1C
    c_0120.model3.json           2,526
    c_0120.physics3.json         38,775
    c_0120.cdi3.json             28,364
    c_0120.2048/texture_00.png   1,768,051
    c_0120.2048/texture_01.png   90,177
    motions/*.motion3.json       8 个（idle 45,228 且 Meta.Loop=true → 天然循环）
    expressions/*.exp3.json      48 个
    manifest.json / icon.png
    vendor/pixi.min.js           460,333   (PIXI 6.5.10, MIT)
    vendor/cubism4.min.js        119,922   (pixi-live2d-display 0.4.0, MIT)
    vendor/live2dcubismcore.min.js 207,155 (Live2D Cubism Core 5.1.0, Live2D 专有许可)
    LICENSES/{LICENSE,NOTICE.md,PROVENANCE.md,AUTHORS.md,README.md}
  renderer/
    index.html                   ← 页面：加载三个 vendor、透明画布、状态标签
    pet-app.js                   ← 渲染逻辑 + window.PetAPI
    state.json                   ← 状态契约文件（由 pet/state.mjs 的 computeState 产出）
    webview2-test/               ← ★ 推荐宿主（名字保留实验时的叫法）
      host-webview2.ps1          ← 透明宿主本体
      Microsoft.Web.WebView2.{Core,Wpf,WinForms}.dll + WebView2Loader.dll  (SDK 1.0.3179.45, net462)
      wpf-transparent.ps1/.png   ← 最小透明性实验（纯红圆 + 绿环）
      host-webview2.log / wv2-info.json / wv2-proof.png
    host-electron/app/           ← Electron 方案的历史代码（运行时已删，仅作备注）
    transparency-proof.png                     ★ 主验收截图 = WebView2 宿主
    transparency-proof-electron.png            （Electron 宿主，历史证据）
    transparency-proof-electron-panel-corner.png（Electron 宿主摆在看板替身右下角）
    run-proof.ps1 / shot.ps1 / verify-window.ps1 / hitmap.ps1
    list-windows.ps1 / panel-standin.ps1
```

`model3.json` 引用的 **13 个文件全部存在**（moc3 / 2 贴图 / physics3 / cdi3 / 8 个 motion），
`moc3` 魔数 `MOC3` + 版本 4，两张贴图 PNG 魔数正确。

---

## 2. ★ 配方：WPF + WebView2（推荐）

**技术栈**：Windows PowerShell 5.1（STA）+ WPF + `Microsoft.Web.WebView2.Wpf`（.NET Framework 4.6.2，SDK **1.0.3179.45**，从 `C:\Program Files\SakuraFrpLauncher\` 复制，含原生 `WebView2Loader.dll`）。
SDK 1.0.3179.45 **低于**已装运行时 154.0.4258.37，符合「SDK 不得高于运行时」。

```
窗口   : WindowStyle=None + AllowsTransparency=True + Background=Transparent + Topmost=True
         + ShowInTaskbar=False + ResizeMode=NoResize
WebView : WebView2.DefaultBackgroundColor = [System.Drawing.Color]::Transparent
页面   : 用 CoreWebView2.SetVirtualHostNameToFolderMapping('pet.local', <pet 目录>, Allow)
         然后 Source = https://pet.local/renderer/index.html
         （这样相对路径 fetch 可用，既不需要本地 HTTP 服务器，也不碰 file:// 的 CORS）
HTML   : html,body{margin:0;background:transparent}  ← 任何不透明底色都会变成一块方框
原生   : WebView2Loader.dll 必须能被找到 —— 脚本用 SetDllDirectory(<脚本目录>) + PATH
事件   : WebView2 的 WPF 控件在 Dispatcher 循环跑起来之前**拒绝** EnsureCoreWebView2Async，
         所以宿主写成 DispatcherTimer 状态机，最后才阻塞在 [Dispatcher]::Run()
```

启动：

```powershell
powershell -NoProfile -File "F:\dsh-usage-widget\pet\renderer\webview2-test\host-webview2.ps1" `
  -X 1150 -Y 320 -W 440 -H 540 -ClickThrough 1 -Topmost 1 -Hold 30
# 结果写到同目录 wv2-info.json / wv2-proof.png
```

实测结果（`wv2-info.json`）：

```json
{ "hwnd":"0x120ac6", "bounds":{"x":1150,"y":320,"width":440,"height":540},
  "topmost":true, "clickThrough":true, "allowsTransparency":true,
  "windowBackground":"#00FFFFFF", "webviewDefaultBackground":"Color [Transparent]",
  "runtime":"154.0.4258.37", "url":"https://pet.local/renderer/index.html" }
```

页面自检（宿主通过 ExecuteScriptAsync 读回）：
`{"ready":true,"alpha":[0,0,0,0],"state":{"state":"busy","label":"后台任务","color":"#FFA657",...}}`
—— 画布四角 alpha 全 0，且状态契约文件真的被读到了。

**截图里看到了什么**（`transparency-proof.png`，600×700，就是宿主窗口 + 四周 80 px）：
鲸鱼娘完整地浮在桌面上，**模型轮廓之外直接就是桌面文字**——
「不需要退化成…」「两张 2048 贴图、8…」「CE.md / PROVENANCE.md」「以 WebView2 为准，把那…」
「摆（它…上本来就装了）。只有当 WebView2 真…」「笔磁盘」等字清清楚楚，一直延伸到她的发丝和
鲸鱼尾巴边缘；右上角是按契约渲染的状态标签「后台任务」（#FFA657）与 detail「pwsh」。
**没有黑框、没有灰底、没有任何窗口矩形边界**。

---

## 3. 交互能力（逐项实测，`verify-window.ps1` / `hitmap.ps1`）

| 能力 | WebView2 宿主 | Electron 宿主（历史） |
|---|---|---|
| 显式 x/y | ✅ 要 `1150,320 440x540` 就是 `1150,320 440x540` | ✅ 同样精确 |
| 总在最前 | ✅ `Topmost=true`；看板也是 Topmost，所以宿主 **每 1.5 s 重提一次** `Topmost`（与看板定时重提同频，赢得交错；SetWindowPos 不抢焦点）。已实测：宠物窗口在一个开着 `-ReassertTopmost` 的 Topmost 替身看板之上，`WindowFromPoint` 在两者重叠处返回的是桌宠 | ✅ `setAlwaysOnTop(true,'screen-saver')`，exStyle `WS_EX_TOPMOST` |
| 点击穿透 | ✅ **天然全程穿透**：231 个探测点全部落到桌面/下层窗口。原因是 WPF `AllowsTransparency` 让窗口成为按 alpha 命中的分层窗口，而 WPF 自身的绘制表面是空的（内容全在 WebView2 子窗口里），于是整窗 alpha=0 → 点击一律穿透 | ✅ 可开可关：`setIgnoreMouseEvents(bool,{forward:true})`。关掉时 exStyle `0x00200008`（无 `WS_EX_LAYERED`/`WS_EX_TRANSPARENT`），`WindowFromPoint` 在宠物中心返回桌宠本身 —— 也就是**唯一能让桌宠真正收到点击的方案** |
| 之后一个像素都点不到 | ⚠️ 是。这个宿主里桌宠**收不到鼠标事件**（想做「戳一下」互动的话要么换 Electron，要么另找非分层窗口的宿主） | 否，可点 |

> 判断依据是 `WindowFromPoint()` + `GetAncestor(GA_ROOT)`：它返回的就是 Windows 真正会投递点击的窗口。
> 工具本身在两个方向都被验证过（在替身看板不透明处正确返回看板；在 Electron 关闭穿透时正确返回桌宠）。

---

## 4. 试过但没走的路 / 踩过的坑

1. **`raw.githubusercontent.com` 超时** —— 没用它。`api.github.com` 能用但 **60 次/小时限流**，
   把 `assets/model/**` 下到一半就 429 了。最后用 `codeload.github.com` 拉整包 tar.gz（一次请求）。
   `cdn.jsdelivr.net` 也可用，可作备用。**tar.exe 会把中文文件名解成乱码**（`开盖` → `寮€鐩?`），
   改用 Python `tarfile` 解包，157 个成员 0 缺失。
2. **Windows PowerShell 5.1 把无 BOM 的 UTF-8 `.ps1` 按 GBK 读** —— 中文注释里的多字节字符
   会**吞掉下一行**，把紧跟其后的 `if (Test-Path Env:\ELECTRON_RUN_AS_NODE) { Remove-Item ... }`
   整行并进注释。症状是 Electron exe 退化成纯 Node 解释器并报
   `Cannot find module 'electron'`。**结论：本项目的 `.ps1` 一律写纯 ASCII**（或写 BOM）。
3. **DSH 给所有子进程注入 `ELECTRON_RUN_AS_NODE=1`** —— 直接跑 `DeepSeek Harness.exe` 会变成
   Node。必须先 `Remove-Item Env:\ELECTRON_RUN_AS_NODE`。（Electron 方案才有这个问题。）
4. **反过来的坑**：`$Info` 和 `$info` 在 PowerShell 里是同一个变量（大小写不敏感）。
   我把参数 `$Info`（输出路径）和局部 hashtable `$info`（要写的内容）写成同名，
   于是 `Set-Content -Path $Info` 拿到一个 hashtable，**信息文件永远写不出来、还不报错**。
5. **`Select-Object -First N` 会掐断上游管道**，把正在跑的 GUI 子进程连带杀掉，
   并让它在 `uncaughtException → 写日志 → 断管 EPIPE → 又 uncaughtException` 里无限自旋。
   排查时务必用 `*> 文件` 而不是 `| Select-Object -First`。
6. **Electron 运行时要独占 userData**：直接跑会去碰 `%APPDATA%` 里真实 DSH 的 profile，
   必须传 `--user-data-dir=<自己的目录>`。
7. **WPF + WebView2 一开始起不来**：先报
   `EnsureCoreWebView2Async cannot be used before the application's event loop has started running`，
   改成「先跑 Dispatcher 循环、在 timer 里调 Ensure」才成功（见 §2 的配方）。
8. **没有真去看板的窗口**：跑 `list-windows.ps1` 时桌面上没有 `DSH usage` 窗口
   （用户的看板当时不在前台/未运行），所以「桌宠压在看板右下角」这张图用的是
   `panel-standin.ps1` 造的**替身**（同色 `#1B1F27`、同样 Topmost），见
   `transparency-proof-electron-panel-corner.png`。真机整合时把 `-X/-Y` 换成看板实际矩形即可。

---

## 5. Electron 方案（已删运行时，仅留代码备注）

`host-electron/app/main.js` + `preload.js` + `package.json` 保留，`run-pet.ps1` 保留作为复现脚本。
**`host-electron/runtime/`（366 MB，75 个文件，其中 `DeepSeek Harness.exe` 233 MB）已按 lead 指示删除**，
项目因此从 373 MB 回到 **8.4 MB**。

当时之所以要复制：`DeepSeek Harness.exe` 所在目录里存在 `resources/app.asar`，
Electron 会优先加载它而不是命令行给的 app 目录，所以**不能直接让 `D:\DeepSeek Harness\DeepSeek Harness.exe`
加载我们的 app**；要让 Electron 回落到 `resources/default_app.asar` + argv[1]，
就必须有一份**没有 `resources/app.asar` 的运行时副本**。
最小副本 = 顶层 dll/pak/dat/bin + `locales\` + `resources\default_app.asar`，共 366 MB；
跨盘（D: → F:）无法用硬链接，所以只能实拷。
如果哪天又需要这条路，把上面那些文件从 `D:\DeepSeek Harness\` 复制到
`host-electron\runtime\`，然后 `run-pet.ps1 -X 1150 -Y 320` 即可（脚本已处理 ENV 与 userData）。

Electron 实测配方（当时可用）：

```js
new BrowserWindow({ frame:false, transparent:true, backgroundColor:'#00000000',
                    hasShadow:false, skipTaskbar:true, resizable:false, show:false,
                    webPreferences:{ contextIsolation:true, backgroundThrottling:false } })
win.setAlwaysOnTop(true, 'screen-saver')
win.setIgnoreMouseEvents(on, { forward: true })     // on/off 都验证过
// 页面背景必须真透明；exStyle 实测 0x00280028 = NOREDIRECTIONBITMAP|LAYERED|TRANSPARENT|TOPMOST
```

---

## 6. 状态契约接法（已实现，不需要改页面）

页面**不判断状态**，只读 `pet/renderer/state.json`（每 1.5 s 轮询一次，带 `?t=` 防缓存）。
文件内容就是 `pet/state.mjs` 里 `computeState()` 的返回值原样：

```json
{ "state":"busy", "label":"后台任务", "color":"#FFA657",
  "detail":"pwsh", "pose":"busy", "reason":"1 job(s) present", "source":"snapshot" }
```

生产方法（整合阶段一行搞定）：

```powershell
node pet\state-cli.mjs --json   # 取 .result，原样写进 pet\renderer\state.json
```

其他注入方式也都实现好了：
- `index.html?state=working` 强制一个状态（调试用）；
- `window.postMessage({type:'pet-state', payload:{...}})` 由宿主直接推。

标签画在桌宠区域右上角（`#state-label`），字体色 = `color`，detail 在其下一行；
底色不打块，避免在透明窗口里多出一块不透明矩形。七色与中文标签按冻结表原样使用，
`pose → 动作/表情` 的映射在 `pet-app.js` 里是 `POSE_ASSETS = {}`，**目前只记录不执行**，
等整合阶段把 `pose`（`offline|sleepy|team|busy|happy|idle`）对到真实动作/表情名后再填。
`pose` 也已暴露在 `PetAPI.getState().pose`。

---

## 7. 授权（照抄 `model/LICENSES/PROVENANCE.md` 与 `NOTICE.md`）

- **代码**：MIT，Copyright © 2026 **Andersen216**。
- **模型素材**（`assets/model/**`：moc3 / 贴图 / 表情 / 动作 / 物理 / cdi3）：
  **不适用 MIT**，**CC BY-NC-SA 4.0（署名 — 非商业性使用 — 相同方式共享）**，
  版权归 **上善无形 / ZipZipPipe / 氵六青** 三位。
  形象链：上善无形「溟月」→ ZipZipPipe 女仆鲸鱼娘 → 氵六青 Live2D 化。
- **模型作者使用须知原文照录**：

  ```
  商用直播√
  自印物料√

  禁止任何形式的盗用以及出售，此模型为无偿分享

  模型制作：B站@氵六青（11272072）
  使用问题和定制桌宠请加QQ交流群：645169617
  ```

  补充（PROVENANCE 原话）：氵六青同意转载/开源，但**不解除**角色形象本身的许可条件，
  所以 **非商业（NC）与相同方式共享（SA）依然有效**。
- **第三方运行时**：`live2dcubismcore.min.js` = Live2D Inc. 专有许可（Cubism SDK Redistributable Code）；
  `pixi.min.js` = MIT（PIXI.js 6.5.10）；`cubism4.min.js` = MIT（pixi-live2d-display 0.4.0）。
- 本机为个人自用；**若要公开发布/商用必须先按 NC 条件处理**。

---

## 8. 几条留给整合阶段的提醒

1. `webview2-test/` 里那 4 个 DLL（约 0.9 MB）是宿主的一部分，**不要删**；换机器时从
   `C:\Program Files\SakuraFrpLauncher\` 或 NuGet `Microsoft.Web.WebView2`（选 net462、版本 ≤ 运行时）
   重新取。
2. 看板矩形到手后，`-X/-Y` 直接传：想「约 1/4 落在看板里」，用
   `X = 看板right - 桌宠W/2`、`Y = 看板bottom - 桌宠H/2`（包围盒左上象限落在看板右下角）。
   注意看板本身贴在工作区右下角，桌宠会有一部分落在屏幕外，**看板需要按约定上移**。
3. 桌宠窗口是 Topmost 且天然穿透，**不会挡看板的点击**；但它也收不到点击。
4. 所有 `.ps1` 保持纯 ASCII（见 §4.2）。
5. 不要用 `sandbox_permissions`；不要造 `.cmd/.bat`；不要 `-WindowStyle Hidden` /
   `-ExecutionPolicy Bypass` / `-EncodedCommand`。本任务全程没碰这些，也没碰
   `ui\widget.ps1`、`engine\**`、`config.json`、`install-startup.ps1`、`verify-project.ps1`。
