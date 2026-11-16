# 桌宠 11 个活动状态 · 实拍索引

> 生成：`pet/showcase/build-docs.mjs`（图片：`pet/showcase/state-<state>.png`，11 张，同一裁剪区域 436×545）
> 采集方式：生产看板照常运行，用页面已有的强制状态通道（`postMessage({type:'pet-force'})`）只替换状态值，
> 桌宠窗口仍是平时那个窗口、平时那个位置；拍完立即解除强制，恢复生产轮询。

| # | `state` | 中文标签 | 颜色 | pose | 触发信号（日志字段） | 她的表情 / 动作 | 图 |
|---|---|---|---|---|---|---|---|
| 1 | `offline` | 离线 | `#8B949E` | `offline` | 心跳文件里 dshRunning === false（DSH 没在跑） | 阴暗 `gloomy`（无道具） | `state-offline.png` |
| 2 | `stale` | 数据过期 | `#D2A8FF` | `sleepy` | snapshot.at 距今 > SNAPSHOT_STALE_MS(45 000 ms)（引擎死了/快照没更新） | 闭眼口水 `drool`（睡着） | `state-stale.png` |
| 3 | `error` | 出错了 | `#F85149` | `gloomy` | tool/result data.error = {name:"FsError", code:"FS_STALE_VERSION"}（或 turn/end reason.kind="error"） | 阴暗 `gloomy`，**1.6 s**，且不叠任何别的东西 | `state-error.png` |
| 4 | `celebrating` | 收工啦 | `#E3B341` | `happy` | turn/end data.reason.kind = "completed"（引擎顺带算出 ms=12300 / tokens=41380） | 开心兴奋 `excited` + 随机一个装饰：猫猫贴纸 / 兔兔贴纸 / 情绪花花 / 心跳 | `state-celebrating.png` |
| 5 | `listening` | 听主人说 | `#79C0FF` | `starry` | user/message data.source.kind = "user"（引擎透传 lastUserAt；TTL 2 600 ms） | 星星眼 `starry` | `state-listening.png` |
| 6 | `team` | 团队协作 | `#56D4DD` | `team` | ≥2 个 agent 的 state = "running"（snapshot.agents） | 平常脸（`null`）+ 板子 + 笔 | `state-team.png` |
| 7 | `reading` | 查资料 | `#58A6FF` | `reading` | tool/call data.name = "web_search"（读类工具；上网类还会掏出小设备） | 三副眼镜随机（圆 34% / 方 28% / 不戴 28% / 椭圆 10%）+ 板子 + 笔；**设备类工具**（`web_search`/`web_fetch`/`browser`/`search_*`）另外**掏出小设备（`openLid` 定格）** | `state-reading.png` |
| 8 | `writing` | 写文件 | `#F0883E` | `scribble` | tool/call data.name = "edit"（写类：write / edit / todo_write） | 认真脸（`null`）+ 板子 + 笔 | `state-writing.png` |
| 9 | `running` | 跑命令 | `#FFA657` | `sleeves` | snapshot.jobs[] 非空（tool/call data.name = "pwsh" 的未配对调用） | 认真脸（`null`）+ 板子 + 笔 | `state-running.png` |
| 10 | `thinking` | 想事情 | `#A5D6FF` | `thinking` | assistant 步骤开着（step/start 未配对 step/end）或 event 距今 ≤ 30 000 ms | 平常脸（`null`）+ 板子 + 笔；主人明确要求「想事就是平常脸」，**不用呆滞眼** | `state-thinking.png` |
| 11 | `idle` | 空闲 | `#9DA7B3` | `idle` | 以上都不成立（DSH 在跑、没工具、没任务、没出词） | 平常脸（`null`）→ 久闲：换表情几秒（吐舌/调皮/问号/脸红/星星眼随机）、换视线、自言自语、喊饿；>99 s 打哈欠、>180 s 睡着（闭眼口水） | `state-idle.png` |

## 每个状态细节

### 离线 · `offline` · `#8B949E`

- 触发信号：心跳文件里 dshRunning === false（DSH 没在跑）
- 引擎给出的 reason：`dshRunning === false`
- detail 行：`DSH 未在运行`
- 表情 / 道具：阴暗 `gloomy`（无道具）
- 动作：不打任何动作；不播音乐、不冒台词
- 台词：—
- 截图：`state-offline.png`

### 数据过期 · `stale` · `#D2A8FF`

- 触发信号：snapshot.at 距今 > SNAPSHOT_STALE_MS(45 000 ms)（引擎死了/快照没更新）
- 引擎给出的 reason：`snapshot age 600000ms > SNAPSHOT_STALE_MS`
- detail 行：`快照 600s 无更新`
- 表情 / 道具：闭眼口水 `drool`（睡着）
- 动作：安静待机；不打动作
- 台词：—
- 截图：`state-stale.png`

### 出错了 · `error` · `#F85149`

- 触发信号：tool/result data.error = {name:"FsError", code:"FS_STALE_VERSION"}（或 turn/end reason.kind="error"）
- 引擎给出的 reason：`tool edit failed 400ms ago`
- detail 行：`报错 · edit · FsError/FS_STALE_VERSION`
- 表情 / 道具：阴暗 `gloomy`，**1.6 s**，且不叠任何别的东西
- 动作：不播动作（大锤 `aidale` 永久禁用）
- 台词：「（脸黑了）这个工具报错了：<工具名> · <错误码>」
- 截图：`state-error.png`

### 收工啦 · `celebrating` · `#E3B341`

- 触发信号：turn/end data.reason.kind = "completed"（引擎顺带算出 ms=12300 / tokens=41380）
- 引擎给出的 reason：`turn completed 600ms ago`
- detail 行：`12.3s · 41380 tokens`
- 表情 / 道具：开心兴奋 `excited` + 随机一个装饰：猫猫贴纸 / 兔兔贴纸 / 情绪花花 / 心跳
- 动作：纯 CSS 蹦一下（`qBounce`，不碰模型参数）
- 台词：「都弄好了…」等 3 句轮换 + 统计行「12.3s · 41380 tokens」
- 截图：`state-celebrating.png`

### 听主人说 · `listening` · `#79C0FF`

- 触发信号：user/message data.source.kind = "user"（引擎透传 lastUserAt；TTL 2 600 ms）
- 引擎给出的 reason：`user message 500ms ago <= LISTEN_TTL_MS`
- detail 行：（空）
- 表情 / 道具：星星眼 `starry`
- 动作：不打动作
- 台词：气泡里放主人原话（截 60 字）
- 截图：`state-listening.png`

### 团队协作 · `team` · `#56D4DD`

- 触发信号：≥2 个 agent 的 state = "running"（snapshot.agents）
- 引擎给出的 reason：`2 agents running`
- detail 行：`运行 2 个智能体 · Whale Girl showcase`
- 表情 / 道具：平常脸（`null`）+ 板子 + 笔
- 动作：不打动作
- 台词：「（招手）叫个分身来帮忙」等 3 句轮换
- 截图：`state-team.png`

### 查资料 · `reading` · `#58A6FF`

- 触发信号：tool/call data.name = "web_search"（读类工具；上网类还会掏出小设备）
- 引擎给出的 reason：`tool web_search in flight (reading)`
- detail 行：`web_search · live2d expression`
- 表情 / 道具：三副眼镜随机（圆 34% / 方 28% / 不戴 28% / 椭圆 10%）+ 板子 + 笔；**设备类工具**（`web_search`/`web_fetch`/`browser`/`search_*`）另外**掏出小设备（`openLid` 定格）**
- 动作：设备类播 `openLid`，播完把参数抽成定格层保持住（框架没有 `hold`）
- 台词：「（凑近看）先读一下这份」「（掏手机）上网查一下」等，脚注为参数摘要
- 截图：`state-reading.png`

### 写文件 · `writing` · `#F0883E`

- 触发信号：tool/call data.name = "edit"（写类：write / edit / todo_write）
- 引擎给出的 reason：`tool edit in flight (writing)`
- detail 行：`edit · pet/renderer/reactions.js`
- 表情 / 道具：认真脸（`null`）+ 板子 + 笔
- 动作：不打动作（「奋笔疾书」**没有专属素材**，见缺口 2）
- 台词：「好，人家写出来」「（奋笔疾书）写上了」等
- 截图：`state-writing.png`

### 跑命令 · `running` · `#FFA657`

- 触发信号：snapshot.jobs[] 非空（tool/call data.name = "pwsh" 的未配对调用）
- 引擎给出的 reason：`1 job(s) present`
- detail 行：`pwsh · 45.2% 剩余 00:37`
- 表情 / 道具：认真脸（`null`）+ 板子 + 笔
- 动作：不打动作（「挽袖子」**没有专属素材**，见缺口 2）
- 台词：「（挽袖子）跑个命令试试」等
- 截图：`state-running.png`

### 想事情 · `thinking` · `#A5D6FF`

- 触发信号：assistant 步骤开着（step/start 未配对 step/end）或 event 距今 ≤ 30 000 ms
- 引擎给出的 reason：`assistant step open`
- detail 行：`正在输出`
- 表情 / 道具：平常脸（`null`）+ 板子 + 笔；主人明确要求「想事就是平常脸」，**不用呆滞眼**
- 动作：不打动作；逐字输出时口型 `ParamMouthOpenY` 按正弦开合
- 台词：—
- 截图：`state-thinking.png`

### 空闲 · `idle` · `#9DA7B3`

- 触发信号：以上都不成立（DSH 在跑、没工具、没任务、没出词）
- 引擎给出的 reason：`nothing happening, DSH up`
- detail 行：（空）
- 表情 / 道具：平常脸（`null`）→ 久闲：换表情几秒（吐舌/调皮/问号/脸红/星星眼随机）、换视线、自言自语、喊饿；>99 s 打哈欠、>180 s 睡着（闭眼口水）
- 动作：不打动作（**`idle.motion3.json` 已停用**：它是猫爪摆手+爱心循环，见缺口 4）
- 台词：「（发呆）…」「人家在呢」「…要不要喝点水？」「（肚子叫）有点饿了…」
- 截图：`state-idle.png`

## 已知缺口（如实标注，没有美化）

1. **桌宠全程穿透**：这是既定偏好（宿主设 `WS_EX_TRANSPARENT`；实测窗口内 11 个探测点全部落到下层窗口，读数见 `pet/host/task13-passthrough.txt`）。她的动作与表情只由**事件与参数通道**驱动，没有任何指针入口。
2. **`奋笔疾书` / `挽袖子` / `走路般摆动` 没有素材**：不伪造。写文件用认真脸 + 板子/笔 + 台词「（奋笔疾书）写上了」；跑命令同理用「（挽袖子）跑个命令试试」；`走路般摆动` 完全不实现。
3. **没有 token 级流式信号**：DSH 会话日志里没有任何 `agent/assistant-stream` 记录（25 个 artifact 实测 0 条），所以引擎只发「一个 assistant 步骤开着」的紧凑信号，**逐字冒字由页面按时间自己做**（60 ms 一个字 ≈ 16 字/秒）。
4. **黑脸 1.6 s，但状态窗口取 3.2 s**：引擎按 2 s 折叠会话日志，1.6 s 的窗口可能整段落在两次轮询之间 → 标签永远不显示「出错了」。所以**脸仍然只黑 1.6 s**（`REACTIONS-SPEC` §3.3 的原值），状态窗口放宽到 3.2 s 保证可见。
5. **`ask_user_question` 归到「想事情」**：11 个活动类别里没有「问你」这一档，所以状态取 `thinking`，表情仍用具象的 `question`（问号）+ 台词「（歪头）这个得问问主人」。
6. **`peak` 峰时不再是状态**：峰谷是看板页脚的职责，已从标签轮转删除（spec 里保留为可选第 12 档，不实现）。
7. **快工具的脸延后 2.5 s**：引擎 2 s 折叠，`read`/`edit` 这类工具被看到时往往已经是 `result`；若只在 `call` 阶段挂脸，眼镜/笔/手机几乎永远不出现，所以成功结果也挂 2.5 s 该活动的脸，然后回落到 state.json 的 base。
8. **`idle.motion3.json` 不播**：它其实是「猫爪摆手 + 爱心」循环（`Meta.Loop=true`），原作者已停用；页面不再传 `idleMotionGroup`（框架默认组名 `Idle` 在模型里不存在 → 永不自动播）。`aidale`（大锤砸）与 `bubble`（吹泡泡糖）双拦。

## 授权（派生作品）

模型素材 **CC BY-NC-SA 4.0**（署名—非商业性使用—相同方式共享），版权归 **上善无形 / ZipZipPipe / 氵六青**。
本次补 `FileReferences.Expressions`（44 条）与 `Groups[LipSync].Ids = ["ParamMouthOpenY"]` 属于**对模型的改编**，
因此 `pet/model/c_0120.model3.json` 是**派生作品**：个人 / 给朋友的小范围自用可以；
一旦对外分发**必须** ① 保留三位署名、② **不得商用**、③ 以相同协议（CC BY-NC-SA 4.0）发布、④ 注明修改内容。
**不能只挂仓库的 MIT。** 详见 `pet/model/LICENSES/DERIVATIVE-model3-json.md`。
