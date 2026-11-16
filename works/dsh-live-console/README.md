# dsh-live-console

一个 **host 为主的 DSH 插件**：用**一个固定的 HTML 页面**替代桌面小组件，实时显示
每个对话里运行的命令、输出日志、进度条，以及 token 花费 / 缓存命中 / 账户余额。页面由
DSH 自带的 HTTP 服务直接提供，不额外开端口；另带一个很小的 client 半边，只在对话顶栏
加一个“控制台”按钮。

> 旧桌宠/看板（`F:\dsh-usage-widget`）**没有被停用**，等新页面确认后再说（见文末）。

## 当前状态（2026-11-05）

- 已通过 junction 挂进 `profiles/desktop/node_modules`，并加入
  `dsh.profile.bundles`（`package.json.bak-live-console-*` 是安装前备份）。
- 第一版（页面/进度/日志/自动打开）已在运行中的 0.2.1-rc.5 上**热组合**并实测。
- 第二版（**用量/花费/余额** + **顶栏“控制台”按钮**）已写完并通过离线自检，
  但它是 host 源码 + 新增 client half，**需要重启一次 DSH 才会加载**。
- 页面地址写在 `$DSH_HOME\live-console\url.txt`；访问 key 在
  `$DSH_HOME\live-console\key.txt`（已预置为当前 key，重启后 URL 不变）。
- 真机验证（第一版）：页面已自动在浏览器打开（服务端 SSE `clients=1`）；运行中的长任务
  从 `[progress 5/20]` 解析为 25% → 55%，ETA 从 21s 收敛到 6s；事件流里能看到
  `tool/call`、`tool/result`、`step/start` 等。
- 第二版离线验证：用量扫描实测 **2.9 s / 44 个日志 / 61 MB**，得到
  `$25.86`、`9,628` 次调用、缓存命中 `99.6%`；余额接口返回 `￥36.04`；
  页面真机渲染（无头 Edge + demo）确认花费条与按模型明细正常。

如果浏览器把页面关了，重新打开 `url.txt` 里的链接即可；下次某个对话开始跑命令时，
插件发现没有页面连着，也会自动再打开一次。重启之后，DSH 顶栏也会出现“控制台”按钮。

---

## 它做什么

- **一个页面**：`http://127.0.0.1:<GUI端口>/live-console?k=<随机key>`
  （`<GUI端口>` 是 DSH 当前 Web 端口，本机通常是 4620）。
- **自动打开一次**：插件激活后约 2.5 秒打开默认浏览器；之后如果页面被关掉，
  下一次对话开始跑命令时会再打开一次（同一时刻只保留一个页面，不刷屏）。
  页面内自动**跟随最近活跃的对话**，也可以手动点左侧会话固定查看。
- **显示什么**：
  - 顶部花费条：今日花费（$ / ￥）、总计、账户余额、缓存命中率、调用次数、当前峰/谷时；
    “用量详情”展开后是按模型的调用/tokens/花费明细。
  - 左侧：所有对话（标题、目录、运行状态、当前轮/步、运行中任务数），子会话默认隐藏。
  - 中间：命令卡片（命令原文、状态、**进度条**、已运行时间、输出字节/行数、最后一行输出、
    可展开实时日志）。
  - 下方：对话事件流（标题、轮/步、工具调用、工具结果、用户/模型消息摘要）。
- **数据来源**：
  - 任务/日志：`ctx.jobs` 的事件与输出环 + `session/event` 持久事件流 + `api-session/*`。
  - 花费：扫描 `$DSH_HOME\sessions` 里的 v3/v4 会话日志，按每次调用自己的时间戳套
    DeepSeek 峰谷价目表（USD），再按配置汇率折算 CNY；只在激活时和“页面打开期间每 2 分钟”
    扫一次，不跟随每次请求。
  - 余额：`DEEPSEEK_API_KEY`（来自 `$DSH_HOME\.credentials.yaml` 的 `refs:`）请求
    `https://api.deepseek.com/user/balance`，成功缓存 60 秒。
- **DSH 顶栏按钮**：client 半边在对话顶栏注册“控制台”按钮；点击后向 host 的
  `/api/live-console/url`（走 DSH cookie 认证）取带 key 的地址，再 `window.open` 交给
  Electron 用默认浏览器打开。

## 进度条：三级模型（不假装精确）

| 级别 | 来源 | 页面标签 |
|---|---|---|
| 1. 输出进度 | 程序自己打印的 `42%` / `[progress 3/10]` / `step 3/10`；jobs 注册表自己的 `progress` 行 | 输出进度 / 注册表进度 |
| 1b. 进度文件 | 命令把输出重定向到文件时（`> run.log`、`-o out.txt`、`--output`、`-OutFile`、`| tee`），从文件尾部解析 | 进度文件 |
| 2. 历史估算 | 同一命令此前运行的中位耗时 / 中位输出量；最多估算到 95%，真正的 100% 只由任务结束给出 | 历史耗时估算 / 历史输出量估算 |
| 3. 活动条 | 完全没有数字信号：动画条 + 已运行时间 + 输出字节/行数 + 最后输出时间 | 无进度信号 |

**为什么没有"真进度"**：程序不报告进度时，任何百分比都只能是估算。这里的选择是：
能拿到的真实进度优先；拿不到就用同一个命令的历史估算（会明确标"估算"）；再拿不到
就诚实地显示活动条，而不是编一个数字。

**自动进度约定**：插件通过 `ctx.systemPrompt.section()` 给**所有对话**注入一段系统提示，
要求长时间命令主动打印进度行，并在重定向输出文件时把进度写进文件。这样不需要每个对话
都手动提醒模型——以前"要求当前对话输出进度它就能做到"，现在是默认行为。
已有输出 `x%` / `n/m` 的程序无需任何改动。

## 安装（desktop profile）

包目录：`F:\DeepSeek工作区\dsh-live-console-v15`。

```powershell
# 1) 链接进 desktop profile 的 node_modules
New-Item -ItemType Junction `
  -Path  "$env:USERPROFILE\.dsh\profiles\desktop\node_modules\dsh-live-console" `
  -Target "F:\DeepSeek工作区\dsh-live-console-v15"

# 2) 在 profile 的 dsh.profile.bundles 里加上 "dsh-live-console"
#    $DSH_HOME\profiles\desktop\package.json
```

host 源码改动不会热重载：改了 `src/` 之后需要重启宿主进程（或重启桌面应用）才生效。
新增 bundle 层本身是否热组合取决于版本；已验证 0.2.1-rc.5 下追加条目后会重新组合。

页面地址会写到：

```
$DSH_HOME\live-console\url.txt        # 一行，含随机 k
$DSH_HOME\live-console\history.json   # 每个命令的历史耗时/输出量（用于估算）
```

## 配置（`cordis.patch.yml` 的 loader 行）

| 键 | 默认 | 说明 |
|---|---|---|
| `route` | `/live-console` | 页面与数据路由的基路径 |
| `autoOpen` | `auto` | `auto`＝激活时开一次 + 页面关闭时在下次对话首个命令重开；`once`＝只开一次；`never`＝从不自动开 |
| `openDelayMs` | `2500` | 激活后延迟多久开浏览器 |
| `progressPrompt` | `true` | 是否注入全局进度约定 |
| `keepSettledMs` | `60000` | 已结束任务卡片保留多久 |
| `maxLogBytes` | `262144` | 每个任务保留的输出字节上限（日志查看器） |
| `history` | `true` | 是否持久化命令历史用于估算 |
| `fileProgress` | `true` | 是否 tail 重定向输出文件 |
| `usage` | `true` | 是否统计 token 花费（扫描会话日志） |
| `usageRefreshMs` | `120000` | 页面开着时两次用量扫描的最小间隔 |
| `usdToCny` | `7.1` | 只用于 CNY 展示列的折算汇率 |
| `balance` | `true` | 是否读取 DeepSeek 账户余额 |
| `balanceRefreshMs` | `60000` | 余额刷新间隔（成功结果缓存 60s） |
| `updateMs` | `700` | 服务端刷新/推送周期 |

## 安全

- 路由**只接受本机回环地址**（`allowNonLoopback: false`，默认）；页面与数据接口都要求
  URL 里的随机 `k`（首次生成后持久化在 `key.txt`，重启不变）。这样即使以后开启远程访问，
  链接也不容易被猜。
- 页面带 CSP（`default-src 'none'`，只允许内联样式/脚本与同源连接）、`X-Frame-Options: DENY`。
- 命令输出在页面里全部经 HTML 转义 / `textContent` 渲染，不执行输出内容。
- 注意：控制台页面**不使用 DSH 的 cookie 认证**（那是给 `/api` 与 SPA 的），所以链接本身
  就是凭证；不要把它转发给别人。

## 自检 / 预览

```powershell
# 纯离线单测（进度解析、历史估算、文件重定向提取）
node test/progress-check.mjs

# 用真实 HTTP 服务 + 假 job registry 跑完整插件（页面/JSON/日志/SSE/用量路由）
node test/console-check.mjs

# client 半边：用 module-loader 形式渲染并点击顶栏按钮
node test/client-check.mjs

# 不装进 DSH 也能看页面（模拟 2 个会话、三种进度档位；用量会真实扫描本机会话日志）
node scripts/demo.mjs --port 4622
# 打开 http://127.0.0.1:4622/live-console?k=demo-console-key-123

# 无头 Edge 渲染页面并截图（开发工具；--open-usage 展开用量面板）
node scripts/verify-page.mjs --url "http://127.0.0.1:4622/live-console?k=demo-console-key-123" --out console-preview.png --wait 12000 --open-usage

# 重启 DSH 并验证新版本（会结束当前应用/会话，请在应用外运行；见脚本头注释）
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/restart-and-verify.ps1
```

## 已知限制

- 花费来自会话日志扫描：价格表写死（2026-09-10 生效的 Flash/Pro 峰谷价），
  峰谷按 UTC 周一至周五 01–04、06–10 判定；如果 DeepSeek 之后调价，金额会偏。
- 余额依赖 `DEEPSEEK_API_KEY` 与网络；取不到时显示 `—` 并把原因放在 tooltip。
- 用量扫描在激活时约 2–3 秒 CPU，页面开着时每 2 分钟一次；不需要可在配置里关掉
  `usage` / `balance`。
- 第二版新增了 host 源码与 client 半边：**需要重启一次 DSH 才会加载**；重启后
  顶栏“控制台”按钮和页面花费条才会出现。
- 插件激活前已经在跑的任务不会补登记（激活后的新命令都会出现）。
- 老会话的标题：插件激活时会对当时**还活着**的会话回填标题（从它的 session 事件里找最新的
  `session/title`）；已归档会话不在实时会话表里，不会显示。
- 估算依赖同一命令的完整命令行文本；命令里带随机参数（时间戳、临时文件名）时命中率会下降。
- 旧桌宠的移除方式见 `F:\dsh-usage-widget` 审计结论：先禁 `DshUsageWidgetWatchdog`
  再停 `DshUsageWidget`，`install-startup.ps1 -Uninstall` 有 bug 不会删 watchdog。

## 热替换后的实际布局（2026-11-05）

应用当时没有重启，为了立即生效做了一次“热替换”升级：

- host 代码现在在 `F:\DeepSeek工作区\dsh-live-console-v15`（package name 仍是
  `dsh-live-console`，profile 的 junction 指向这里）。改名是因为 Node 会按解析后的
  绝对 URL 缓存已导入模块；换一个目录才能让 loader 重新 import 最新代码。
- 顶栏“控制台”按钮的 client half 单独放在 `F:\DeepSeek工作区\dsh-live-console-ui`
  （profile bundles 里新增了 `dsh-live-console-ui`）。独立成包是为了让
  `clientModules` 能在热组合时把它收进 boot manifest；host 包的 `dsh.client`
  已移除，避免下次重启出现两个按钮。
- 页面/用量在热替换后立即生效；顶栏按钮需要**刷新一次 DSH 页面**（或下次重启）
  才会出现，因为已经加载的页面不会自动载入新的 client bundle。
- 以后直接修改 `dsh-live-console-v15/src` 仍需重启宿主；修改
  `dsh-live-console-ui/lib/client.js` 也需刷新页面（或重启）。
## 用量卡片（2026-11-05 改版）

原来的顶部细条已移除，改成内容区上方的独立卡片：

- 左侧大号 **账户余额**，右侧依次是今日花费、总计花费、缓存命中、计费状态；
- “用量详情”展开按模型明细（调用 / 命中 / 未命中 / 输出 tokens / 花费）；
- “刷新用量”立即重扫会话日志并刷新余额；
- 卡片只在主机版页面（v3）提供；页面每次请求都重新读取 `src/page.html`，之后改版不需要再热替换 host。
## 布局调整（2026-11-05 第二次）

- 用量卡片移到页面级常驻位置：顶部工具栏下方、<main> 之上，横跨整页；切换/滚动会话都不会挤走。
- 对话标题（会话头）现在位于用量卡片下面，属于内容区。

## 对话事件摘要增强（2026-11-05）

对话事件不再只显示事件类型，而是这一步实际做了什么：

- 工具调用：运行命令 · python sim.py、读取文件 · docs/a.md、搜索 · TODO、搜索网页 · … 等；
- 工具结果：工具名 + 成功/失败 + 结果摘要 + 耗时（如 pwsh 完成 · … · 622ms）；
- 命令任务：启动命令 · … / 命令结束 · completed · exit code: 0；
- 助手步骤：模型回复 · 346 tokens：这一步的文字摘要；
- 轮/步：第 8 轮 · 第 13 步开始 / 结束、第 8 轮结束（completed）。

## 对话内容面板（2026-11-05）

- 会话标题下方新增一个固定高度（约 132px、可滚动）的小面板：显示该会话最近 6 条「你 / 模型」消息，超出裁到 700 字；
- 激活时会从当前存活会话的 session 事件回填最近对话，之后随 SSE 实时更新；
- 只占内容区一小条，不挤占任务/日志/事件的主要版面。

## 对话输入框（2026-11-05）

- 对话面板加高到约 238px，并在底部加入输入框：Enter 发送、Shift+Enter 换行；
- 发送走 POST /live-console/send（页面 key + 本机回环校验），host 端调用 live Agent 的 ollowup()，等同于在 DSH 里给当前对话发消息；
- 只允许发送到当前有 live agent 的会话；空消息 400、未知会话 404。

## 2026-11-05 启动故障与处置

- 根因：dsh-live-console-ui/lib/client.js 一次 PowerShell UTF-8 往返后变成乱码，DSH 启动时 client bundle 抛 SyntaxError: Invalid or unexpected token，web boot 报 “1 entry did not activate”，应用无法正常进入。
- 已用干净源码重写该 client bundle，ode --check 与客户端行为测试 7 项全过。
- 但本次恢复 profile 时**暂不加载** dsh-live-console-ui（避免再次 boot 风险）；页面/用量/对话/输入框全部由 host 插件 dsh-live-console 提供。
- 当前 profile bundles：base、web-app、experimental-agent-team-profile、experimental-auto-review、dsh-usage-bridge、dsh-live-console。
- 顶栏“控制台”按钮因此暂时没有；需要时建议改成 host 侧注入的链接（不引入 client bundle），或验证后再单独启用 UI 包。

## 顶栏入口的安全替代（2026-11-05）

- 不再启用 client bundle dsh-live-console-ui，改为 host 侧通过 webServer.tapIndex 往应用首页注入一个右下角浮动“控制台”按钮；
- 按钮点击时向已认证的 /api/live-console/url 取带 key 的页面地址，再 window.open 交给 Electron 打开默认浏览器；
- 首页改动只需刷新一次应用页面（或下次启动）即可出现，不参与启动时的 client 模块扫描，因此不会重现 boot 失败。

## 浮动“控制台”按钮（2026-11-05 修正）

- webServer.tapIndex 只作用于 HTTP 首页；桌面应用窗口的 index 由 Electron 本地提供，注入行来自 host 启动时通过 IPC 发送的 collectIndexInjections()。
- 因此改为订阅 webserver/index-inject 并推入 { kind: script, placement: head, text: ... }，这才是桌面窗口消费的通道。
- 该注入在应用启动时读取一次，所以按钮需要**重启一次 DSH** 才会出现在窗口右下角；页面本身无需重启。

## 重启后标题/对话为空修复（2026-11-05）

- 原因：恢复的会话在插件激活之后才发布，原来只回填一次，因此标题为空、最近对话为空（只剩启动后的新消息）。
- 修复：每 2 秒轻量扫一次 ctx.sessions.list()，对尚未回填的 session 各扫描一次自己的事件日志，恢复标题和最近 6 条对话；已扫描的会话直接跳过。
- 该修复热加载后立即生效，无需重启。

## 对话图谱页面（2026-11-05）

- 入口：控制台顶栏“图谱”按钮，或直接访问 /live-console/graph?k=<key>；
- 每个持久化用户对话 = 一个节点，节点保存标题、目录、时间、消息数、关键词和最多 8000 字内容摘要；
- 两个对话共享至少一个关键词就连线，边携带共享关键词列表，线宽随共享关键词数量增加；
- 关键词提取：清洗掉 harness 注入的运行时上下文伪用户消息后，用 CJK bigram/trigram + 英文词的 TF-IDF 排名，每个节点取前 10 个，并去掉“传感/感器”这类被更长词包含的重复项；
- 内部 subagent/teammate 会话不进入图谱（它们不是用户对话）；
- 数据由扫描 $DSH_HOME/sessions/**/session.v*.jsonl.zstd 生成，单飞 + 60 秒缓存；“刷新数据”强制重扫；
- 页面支持搜索、关键词高亮、点击节点查看内容、拖拽/缩放/重新布局。

## 图谱页面视觉重做（2026-11-05）

- 深色极光背景 + 玻璃拟态顶栏/侧栏，节点为渐变发光球，连线弯曲并带流动光点；
- 入场按节点错峰缩放淡入，镜头/缩放平滑缓动；悬停节点放大并显示浮动提示，点击节点镜头聚焦、右侧玻璃面板滑入；
- 选中节点外圈脉冲，邻居与关联边高亮，其余淡出；关键词/搜索高亮同一组对话；
- 顶栏统计、关键词胶囊条、缩放/布局工具条、拖拽画布、滚轮缩放、Esc 取消选择；
- 图谱页路径 /live-console/graph?k=<key>，控制台顶栏“图谱”入口。

## 无损上下文归档（2026-11-05）

- 控制台/图谱页“归档”按钮，或访问 /live-console/context-archive?k=<key>，下载 dsh-context-archive-*.tar.gz；
- 归档内容：manifest.json（每会话 SHA-256、大小、header）+ README.txt + 原始 sessions/<workspace>/<session>/session.vN.jsonl.zstd；
- 原文件按字节复制，不解码、不截断、不重排；DSH 日志本身是 zstd 无损压缩，外层 gzip 只做打包；
- 当前规模：45 个会话，约 63 MB（原始压缩日志已占 60 MB，主要是容器开销）；
- 这是存储/传输出口；无损压缩不会减少模型上下文的 token，模型输入仍需解压后的文本。

## 图谱关键词/节点样式（2026-11-05）

- 关键词数量无上限：当前 22 个对话约 1.2 万个关键词（平均 772/对话），节点详情全量保留；页面详情渲染前 240 个避免卡顿；
- 连线只使用每个节点相关度最高的 24 个关键词，否则公共 bigram 会把图连成一团；节点仍保留全部关键词；
- 节点改为统一蓝色扁平圆点，去掉渐变、光晕和阴影；选中为白描边，悬停提亮。

## 图谱交互与视觉重做（2026-11-05 第二轮）

- 去掉极光/玻璃/发光/粒子/常驻 rAF；页面只在数据变化、交互、相机过渡时重绘；
- 节点统一为扁平蓝色圆点，选中白描边，悬停提亮；文字标签改为 DOM 渲染，缩放时保持清晰；
- 滚轮缩放改为**即时、以鼠标位置为锚点**，不再边缩放边漂移；
- 支持拖拽节点、拖拽画布、单击选中（右侧详情滑入）、双击画布适应、F 适应、Esc 取消；
- 详情面板包含关键词（前 160 个 + 总数）、完整对话内容、关联对话（可点击跳转）；
- 点击测试验证：详情打开、关键词 160 个、关联 6 个。

## 节点外发光与放大（2026-11-05）

- 悬停：节点放大约 1.22 倍并出现柔和蓝色外发光；
- 选中：放大约 1.4 倍、更强外发光 + 一圈细描边；
- 放大用短缓动过渡（约 200ms），不是瞬间跳变；发光只画在节点外侧，节点本体保持纯色扁平，不做 3D 球面明暗；
- 命中检测和标签位置都使用放大后的实际半径。

## 文件节点、类型颜色、自发光与动效（2026-11-05）

- 新增文件/交付物节点：从 read/write/edit/read_image 的工具参数提取绝对路径，只保留被 ≥2 个对话引用且磁盘仍存在的文件，节点与对话之间是“引用文件”边（虚线）；当前 22 对话 / 36 文件 / 127 关系；
- 类型用颜色区分：对话=蓝色，文件=琥珀色；顶部图例可对照；
- 所有节点常态自发光，悬停/选中时发光增强并放大（悬停 1.18x，选中 1.36x）；
- 节点原始半径从 5.5–14.5px 缩小到约 2.8–8px；
- 动画改为时间型缓动：修复 rAF 时间戳早于 performance.now 导致 dt 为负、scale 爆掉的问题；滚轮缩放 110ms 平滑过渡且每帧锚定鼠标位置；选中聚焦 260ms 缓动；
- 节点缩放用指数缓动，不再瞬间跳变。
