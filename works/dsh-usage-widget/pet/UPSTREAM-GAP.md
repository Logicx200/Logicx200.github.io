# UPSTREAM-GAP —— 上游能力完整盘点 & 「缺素材」结论的纠正

> 交付：`pet-renderer`（task-9）· 2026-09-30
> 上游整包（本地已解好，中文名完好）：`F:\whale-chan-research\upstream\extracted\dsh-whale-girl-live2d-main\`
> **139 文件 / 13.89 MB**。核心三个文件：
> `assets/pet.js`（194,372 B / 4,476 行，前端全部行为）、`lib/index.js`（45,547 B，宿主事件→反应）、
> `assets/model/manifest.json`（20,593 B，素材目录）。
> 本文行号均指 `assets/pet.js`，除非写作 `lib/index.js:NNN`。参考副本见 §7。
>
> **重要前提**：本文的「我们的状态」一列是**当前真实代码**，不是 task-1 时的印象。
> 我在写这份盘点前先读了我们自己现在的 `pet/renderer/reactions.js`（564 行）、
> `pet/renderer/pet-app.js`、`pet/renderer/signals.json`、`pet/host/host.ps1`，
> 发现 **task-7 之后反应层已经落地了一大半** —— 这一点如果不查，这份盘点就会反过来又错一次。

---

## 0. 一句话结论

1. **素材一个都不缺**：8 动作 + **44** 表情（不是 48），60 个模型文件，逐文件名 diff：**我们缺失 0**。
2. **「缺素材」这个说法是错的，但错的不是"素材不够"，而是"我们没读代码"**：
   上游有整套由这 44 个表情驱动的**道具 / 眼镜池 / 贴纸 / 装饰 / 场景 / mood / 菜单**系统，
   我们此前只读 `manifest.json` 与 `README`，**从没打开过 `pet.js`**，于是把"没实现"误判成"没素材"。
3. **现在（task-7 之后）我们已经实现了其中最核心的一层**：常态道具（本子+笔）、按工具换脸换道具、
   随机眼镜、掏小设备定格、报错黑脸、收工庆祝+统计、口型、视线、气泡逐字、待机大脑、看门狗。
   **仍然缺的是**：装饰/场景的手动开关、一次性动作 11 个、mood 词表与去重台词、爱心粒子、
   眨眼自控、工作轮播、低性能档、HUD、位置/道具持久化、诊断页 —— 以及**所有要鼠标的能力**（受宿主架构限制）。

---

## 1. 素材盘点：证明「一个都不缺」

| 项 | 上游 | 我们本地 `pet/model/` | 结论 |
|---|---|---|---|
| `assets/model` 全部文件 | **60** | 61（60 + 别的 agent 的 `c_0120.model3.json.bak-task7`） | **缺失 0**（逐文件名 diff） |
| `manifest.json` → `expressions` | **44** 键 | 44 个 `.exp3.json` | 一一对应 |
| `manifest.json` → `motions` | **8** 键 | 8 个 `.motion3.json` | 一一对应 |
| `moc3` / `texture_00` / `texture_01` / `physics3` / `cdi3` | 各 1 | 各 1 | 齐全 |

`manifest.json` 连动作**时长**都给了（上游 `playMotion` 就靠它记账，我们也该用）：

| 组 | duration(s) | 组 | duration(s) |
|---|---|---|---|
| `idle` | **4**（`Loop:true` = 猫爪+爱心循环） | `openLid` | **1**（掏小设备；我们已用） |
| `aidale` | 4.767（禁用） | `bubble` | 5（禁用） |
| `selfie` | 3.3 | `splash` | 0.467 |
| `selfieQuick` | 1.267 | `ketchup` | 5 |

### ⚠️ 口径纠正：是 **44** 个表情，不是 48

| 来源 | 数 |
|---|---|
| 磁盘 `assets/model/expressions/*.exp3.json` | **44** |
| `manifest.json.expressions` 键数 | **44** |
| A8Chann `pets/ds-whale-girl/c_0120.model3.json` 的 `Expressions` | **44** |
| 上游 `README.md` / `SKILL.md` 文案 | 「44 个表情」 |
| task-1 / task-9 简述里的「~48」 | **不成立**，没有第 45–48 个文件或声明 |

我在 task-6 的 `REACTIONS-SPEC.md` 里写的就是 44，这条没错；错的是任务描述里的 48。**以 44 为准。**

---

## 2. 「缺素材」这个结论错在哪 —— 逐条纠正

### 2.1 错法一：把「台词」当成「素材缺失」

| 我们说过的 | 真实出处 | 性质 |
|---|---|---|
| 「奋笔疾书」缺素材 | `pet.js:316` `TOOL_LINE.write = ['好，人家写出来', '（奋笔疾书）写上了', …]` | **台词**。上游写文件的脸就是「认真脸」，没有也不需要"奋笔疾书"表情 |
| 「挽袖子」缺素材 | `pet.js:314` `TOOL_LINE.bash = ['（挽袖子）跑个命令试试', …]` | **台词**。`TOOL_REACT.bash = { mood:'reading', prop:null }`，也不戴道具 |
| 「走路般摆动」缺素材 | `pet.js:2162` `qBounce(power)` —— 给 `ui.stage` 加一个纯 CSS class 的位移，**不碰任何模型参数** | **CSS 动效**，与素材无关 |

模型侧本来就只是「认真脸 + 板子 + 笔」。**真正的缺口是"我们连本子+笔都没实现"，不是"没有专属表情"。**
（附带好消息：`reactions.js:66-79` 现在**已经把 `menuPress`+`brush` 挂上去了**，这条已经补上。）

### 2.2 错法二：真正的错 —— 只读清单不读代码

`pet.js` 里 `mood` 出现 162 次、`prop` 104 次、`手机` 27 次、`眼镜` 22 次、`sticker` 17 次、`glasses` 16 次、`decor` 7 次。
这是一整套**道具 / 贴纸 / 装饰 / 场景 / 心情**系统，**全部由那 44 个表情驱动**（每个 `.exp3.json` 就是「把某参数置 1」的开关）。
我们此前从没打开 `pet.js`，于是：
- 漏掉了「上游用 44 个表情做了 5 页菜单 + 20 多个道具」这件事；
- 反过来把这件事说成「素材不够」。**这是本任务要纠正的核心。**

### 2.3 错法三（我的）：把"当时没实现"当成"永远没有"

写 task-6 时我按 task-1 的认知打了几个 ❌，而 task-7 之后这些已经实现。
**教训：盘点"我们的状态"必须先读自己当前的代码。**

---

## 3. 能力盘点表

状态图例：**✅ 已实现** · **🟡 部分实现** · **❌ 未实现（取舍）** · **🚫 受架构限制（当前宿主）**
「我们」= 当前 `pet/renderer/reactions.js` + `pet-app.js` + `pet/renderer/signals.json` + `pet/host/host.ps1` + `pet/state.mjs`。

### 3.1 渲染与素材

| # | 能力 | 上游实现 | 素材 | 我们的状态 |
|---|---|---|---|---|
| 1 | 透明无边框渲染 | `buildModel 1477`（`backgroundAlpha:0`） | moc3 + 2 贴图 | **✅** WebView2 宿主实测逐像素透明 |
| 2 | 模型加载与取景 | `buildModel 1477`、`measureContent 1717`、`fitFromMeasurement 1694`、`fitModel 1616`（`FIT_FRACTION 57` = full/bust/head） | — | **🟡** 能铺满窗口；没有 bust/head 三档取景 |
| 3 | 表情可用 | `EXPR 742`（上游**自己读 `manifest.json`**，不依赖 `model3.json` 的 Expressions） | 44 个 `exp3.json` | **✅** task-7 已补 `FileReferences.Expressions` + `LipSync=ParamMouthOpenY`，实测 44/44；`reactions.js:129 loadFaceDefs()` 直接读模型自己声明的 `settings.expressions` |
| 4 | 物理摆动 | 框架默认 | `physics3.json` | **✅** |
| 5 | 眨眼 | `blink 1220` / `blinkTick 1222-1282`（CLOSE 60 / HOLD 30 / OPEN 100 ms，间隔 900–3500 ms），**禁用框架 eyeBlink**，并用 `motionActive 1118` 避开动作 | `ParamEyeLOpen/ROpen` | **🟡** 交给框架默认；没有"动作期间不眨眼"的判定 |
| 6 | 说话口型 | `applyRig 1038-1040`：`ParamMouthOpenY = 0.28 + 0.16·sin(phase·11)` | `ParamMouthOpenY` | **✅** `reactions.js:334-342`（streaming 或 listening 时正弦开口；数值与上游不同） |
| 7 | 爱心粒子 | `heartBurst 2057`：`{love:1, heartbeat:1}` 脉冲 2.2 s | `love`、`ParamCheek73`（爱心左 j1–j32 / 右 j33–j57 的循环组） | **❌** |

### 3.2 道具 / 装饰 / 场景

| # | 能力 | 上游实现 | 素材 | 我们的状态 |
|---|---|---|---|---|
| 8 | 常态道具（本子+笔） | `BASE_ITEMS 155`、`IDLE_PROPS 233`、`WORK_PROPS 234` | `menuPress` + `brush` | **✅** `reactions.js:66-80` 每个 ACT 都挂这两个 |
| 9 | 眼镜池（4 副，互斥） | `PROPS 117-120`，组 `glasses`；`setProp 892`；`itemOn 878` | `圆眼镜`/`方眼镜`/`椭圆眼镜`/`墨镜` | **🟡** 只有"读资料时随机戴"，**没有手动开关、没有互斥组管理** |
| 10 | 读资料随机戴眼镜 | `randomGlasses 377`：34 % 圆 / 28 % 半框方 / 10 % 椭圆 / 28 % 不戴 | 同上 | **✅** `reactions.js:66-70` 权重 `[34,28,28,10]` / `[40,30,30]` / `[50,50]` |
| 11 | 贴纸（3 张，互斥） | `PROPS 121-123`，组 `sticker` | `猫猫贴纸`/`兔兔贴纸`/`蝴蝶结贴纸` | **🟡** 只在"收工庆祝"随机戴一张（`reactions.js:461`），**没有手动开关** |
| 12 | 头饰 / 发型 | `PROPS 124-127`，组 `headwear`/`hair` | `情绪花花`/`单边马尾`/`头箍`/`鲸鱼` | **❌**（`sparkle` 只作庆祝装饰出现） |
| 13 | 场景摆设（常驻） | `SCENES 137-145`、`setProp 892`、`clearProps 947` | `深色桌布`/`鲸鱼放桌上`/`巴菲`/`魔爪`/`魔爪换色` | **❌ 完全没有** |
| 14 | 掏出手机（设备模式） | `takeDeviceOut 886`、`putDeviceAway 2231`、`startWork 2214` 播 `openLid` | motion `openLid` | **✅** `reactions.js:213-252`：播 `openLid` 后**自己在帧内采样参数并定格**（框架没有 hold，上游靠 `pet.json` 的 `hold`，我们靠快照） |
| 15 | 手机换色（前置：手机） | `SCENES 144` `needs:'phone'` | `手机换色` | **❌** |
| 16 | 白魔爪（前置：粉魔爪） | `SCENES 142` `needs:'claws'` | `魔爪换色` | **❌** |
| 17 | 互斥组 / 前置自动补齐 | `setProp 892-946`（`group`/`needs`/`clears`） | — | **❌** |
| 18 | 分层状态机 | `rig 768-786`：**三层** `base`/`override`/`user`；`resolveRig 803-818` | — | **🟡** `reactions.js` 有 `base`+`override`（带 TTL），**缺 `user` 持久层**（用户手选的脸/道具赖不住） |
| 19 | 参数独占裁决 | `applyRig 974-1107`（`delta`/`claimed`/`winners`） | — | **🟡** 我们是「后写的赢 + 淡入」（`tickFrame 309-352`），没有冲突检测 |
| 20 | 动作自带表情时不压脸 | `ACTIONS` 的 `mood:null` + `FACE_DRIVING_MOTIONS 1108` | `bubble`/`aidale`/`selfie`/`selfieQuick` | **❌**（我们只有 `openLid` 一个动作） |
| 21 | 道具/位置持久化 | `readLayout 718`/`saveLayout 725`（`localStorage: dsh-live2d-pet:layout`，含 `props`）+ `restoreProps 953` | — | **❌** 位置由宿主给定；道具不持久 |

### 3.3 mood 系统与台词

| # | 能力 | 上游实现 | 我们的状态 |
|---|---|---|---|
| 22 | mood 词表 | `MOOD_FACE 78-104`：neutral/listening/thinking/reading/happy/excited/love/shy/pout/smug/sad/cry/grumpy/dizzy/gloomy/sweat/confused/alert/sleepy/tongue/dead + 旧名兼容 | **🟡** 我们用**活动类别**（11 档）取代 mood 做 base，脸按活动挑；没有 mood 词汇表 |
| 23 | mood/道具名 → 脸（过滤不存在的） | `moodFace 790`、`propExpr 796`、`EXPR 742`、`droppedParams 750` | **✅** `faceDefs` 只装模型真实声明的表情，取不到就静默退回（`mergeParams 149`） |
| 24 | 菜单项台词表 | `FACE_ACT 247-266`（17 项）、`PROP_ACT 269-283`、`SCENE_ACT 284-312` | **❌**（菜单本身受架构限制，见 §4.1） |
| 25 | 人设台词池 | `SAY 440-488`：idle/slack/start/done/fail/head/body/many/ticklish/wake/hungry/fat/tidy/reading/thinking/working… | **🟡** `reactions.js:29-48` 抄了 17 组（reading/grep/glob/web/fetch/writing/edit/running/todo/team/present/done/fail/aborted/idle/hungry/nopang/sleep），**比上游少** |
| 26 | 同池不重复抽取 | `pickFresh 502-521` + `lastPick 495` | **❌** `reactions.js:118 pickLine()` 是纯随机，同一句可能连着出现 |
| 27 | 工具台词全表（34 工具） | `TOOL_LINE 313-342` | **🟡** 按**活动**归一成 16 组（多个工具共用一组），不是每个工具一组 |
| 28 | 工具参数摘要进气泡 | `toolHint 345-364`（键序 command→file_path→path→pattern→query→url→title→description→prompt，兜底 `queries[0]`，>46 字截断） | **✅** `signals.json.tool.summary` 已带摘要，`reactions.js:444` 截 46 字 + 工具名放脚注 |

### 3.4 一次性动作 / 表演调度

| # | 能力 | 上游实现 | 素材 | 我们的状态 |
|---|---|---|---|---|
| 29 | 一次性动作 11 个 | `ACTIONS 176-221`、`playAction 3005`、`playOneShot 1328` | `catPaws`/`doubleV`/`heartPop`/`heartbeat`/`squeeze`/`eraser`/`undo`/`omurice`+`ketchup`/`selfie`/`selfieQuick`/`splash` | **❌ 一个都没做**（只有 `openLid`） |
| 30 | 单次表演调度 | `act 1351-1374`（先 `stopActing()` 归零，再「一个表情 + 至多一个动作 + 至多一个粒子」） | — | **🟡** `reactions.js` 的 override 有 TTL 与回落，但没有"动作+表情+粒子"的合成与归零协议 |
| 31 | 动作播放与时长记账 | `MOTION_PRIORITY 51`、`playMotion 1122-1150`（用 `manifest.motions[g].duration`） | 8 个 motion | **🟡** `pet-app.js` 暴露 `playMotion`/`stopMotions`，`reactions.js` 只用 `openLid`；未按 `duration` 记账 |
| 32 | 停动作 + 清姿势 | `stopActing 1151`、`stopMotion 1317`、`clearMotionPose 1182-1219`（设回 `getParameterDefaultValue` 再 `saveParameters`） | — | **✅** `pet-app.js` 有 `clearMotionPose`（4 处引用）；`reactions.js:245 clearDevice()` 调 `stopMotions()` |
| 33 | 玩偶动作（猫爪摆手） | `ACTIONS.paw` → 播 `idle` 4400 ms | motion `idle` | **❌**；且注意：**上游待机不放动作**，我们目前 `idleMotionGroup` 仍会让它循环——**这条要改**（见 §5.4） |
| 34 | 禁用清单双拦 | `BANNED_MOTIONS 1109` + `renderPane 3592` | `bubble`/`aidale` | **🟡** `PetAPI` 暴露了 `forbiddenMotions`，但没用它做拦截 |

### 3.5 事件驱动（agent 联动）

| # | 能力 | 上游实现 | 我们的状态 |
|---|---|---|---|
| 35 | 事件流订阅 | `connectSSE 3781-3813` ← `lib/index.js:757 /dsh-pet/events`（SSE 实时） | **🟡** 我们轮询 `signals.json`（1.5 s），延迟更大但**不需要注入 DSH 页面** |
| 36 | 用户发话 → 星星眼 + 原话 | `handleEvent 'user' 3827-3835` | **✅** `reactions.js:401-407`（2.6 s `starry` + 原话截 60 字） |
| 37 | 开工 → 工作态 | `'turn-start' 3837-3848`（`startWork()` + `SAY.start`） | **🟡** 由 `state.json` 的 base 覆盖，没有 `SAY.start` |
| 38 | 步骤提示 | `'step-start' 3850-3858`（脚注「正在思考 · 第 N 步」） | **🟡** `state.json.detail` 里有"正在输出"之类，气泡脚注未用 |
| 39 | 逐字输出 → 口型 | `'delta' 3861-3872`（`rig.talking=true` + `stream:true` 气泡） | **✅** `signals.streaming.active` → 口型（`reactions.js:335`）；气泡逐字 16 字/秒（`527-535`） |
| 40 | 定型消息 + token 统计 | `'assistant' 3874-3888` | **🟡** 统计只在 turn-end 显示 |
| 41 | **工具 → 换脸换动作** | `'tool-call' 3890-3926`：`TOOL_REACT 385` 查表 → `setBase(mood, props)`；设备类播 `openLid`；`gaze.biasTarget=-0.32` | **✅** `reactions.js:51-87`（`TOOL_MAP` ~40 个工具名 + `ACT` 表：脸池/权重/道具/`gazeY`/`device`/台词）+ `437-445` |
| 42 | 工具结束（成功/失败分流） | `'tool-result' 3928-3947`：成功→`thinking`+收设备；**失败→`gloomy` 1.6 s、`props:[]`、`exclusive:true`** | **✅** `reactions.js:412-436`（报错 1.6 s 黑脸 + 不叠道具；成功给该活动的脸 2.5 s 再交回 base） |
| 43 | 整轮结束（三种 kind） | `'turn-end' 3961-4019`：completed→`excited`+随机装饰+`qBounce(1.2)`+统计；aborted→`sad` 2.8 s；error→`sweat|sad` 3.2 s；其它→`pout` 2.6 s | **✅/🟡** `reactions.js:448-470` 四种分支 + 装饰 + 统计行都在；**缺 `qBounce` 蹦一下** |
| 44 | 一轮结束强制复位 + 看门狗 | `setBase('neutral')` + `startLoops 4185-4190`（每 2 s） | **✅** `tickWatchdog`（`reactions.js:355`，每 2 s 回落 + 气泡到期） |
| 45 | 子代理提示 | `'subagent' 4021-4023` | **🟡** `signals.agents` 有数字，`ACT.team` 有脸，无脚注提示 |
| 46 | 审批 | `'approval' 4025-4031`（`question` 8 s） | **🟡** `TOOL_MAP.ask_user_question='asking'` → `question`；无审批事件源 |
| 47 | 工作轮播（9–14 s 慢切） | `WORK_CYCLE 2206`、`workTick 2238-2256`（`9000+rand*5000`） | **❌** |
| 48 | 外部控制入口 | `handleControl 4049-4069` ← `POST /dsh-pet/control` | **🟡** `PetReactions.say()` / `setForced()` 是等价物，但没有 HTTP 入口 |

### 3.6 待机行为

| # | 能力 | 上游实现 | 我们的状态 |
|---|---|---|---|
| 49 | 待机大脑（权重表） | `IDLE_TABLE 4096-4102`：glance 46 / express 28 / mutter 22 / hungry 4 / nopang 2；周期 3.5–7.5 s | **🟡** `reactions.js:368-387` 用 `roll` 阈值近似（换脸 30 % / 自言自语 30 % / 喊饿 15 %），**没有 glance 与 nopang** |
| 50 | 待机换表情（不改变眼型） | `idleExpress 4123-4136`：池 `shy/confused/excited/alert/tongue/sweat/love`，2.2–4.8 s | **🟡** 池是 `tongueOut/naughty/question/blush/starry`（其中 `starry` 会变眼型，与上游"不变眼型"的约束不符） |
| 51 | 自言自语 / 喊饿 / 强调不胖 | `runIdleBehavior 4158-4169` | **🟡** 有 mutter/hungry，**无 nopang** |
| 52 | 打哈欠 → 睡着 → 唤醒 | `4205-4217`（哈欠 `sleepAfterMs*0.55`≈99 s、`rand<0.4`；睡着 180 s；`wakeUp 4107` 鼠标一动就醒） | **🟡** 有 99 s 哈欠 / 180 s 睡着（`reactions.js:371-375`）；**没有唤醒**（没有鼠标，见 §4.1） |
| 53 | 视线跟随光标 | `gazeTick 2067-2161`、`gazeCfg 2027`（radius 0 整屏 / gain 0.78 / rate 1.6）、`gazeDetach 2063` | **🚫** 需要鼠标；我们只有 `idleMs>20 s` 的自动漂移（`reactions.js:344-347`） |
| 54 | 低头看本子（视线偏置） | `gaze.biasTarget = -0.32`（`3896`） | **✅** `ACT.*.gazeY`（reading −0.32 / glob −0.18 / web −0.2 / writing −0.1） |
| 55 | 位置存档 / 贴边吸附 / 拖动惯性 | `applyPosition 1825`、`snapOnRelease 1783`、`glideTo 1756`、`dragInertia 2179` | **🚫** 需要鼠标 |
| 56 | 低性能档 | `PERF 1449`、`applyPerf 1451-1467`（20 fps、分辨率 1×、关自言自语与自主动作）、`setLowPower 1470` | **❌ 成本极低、收益明确，建议做** |

### 3.7 UI / 面板 / HUD

| # | 能力 | 上游实现 | 我们的状态 |
|---|---|---|---|
| 57 | 气泡（名字/正文/脚注/ttl/stream） | `makeBubble 2369-2415` | **🟡** `reactions.js:254-306` 有气泡 + 脚注 + 逐字；**没有名字行**（上游气泡带"DS 鲸鱼娘"） |
| 58 | 工具栏 4 键 | `buildUI 2262-2368`、`bindMenu 3468-3485` | **🚫** |
| 59 | 五页菜单（表情/装饰/场景/动作/设置） | `bindMenu 3447`、`TABS 3448`、`renderPane 3488-3763` | **🚫** |
| 60 | 表情页（按表情去重 + 平常脸 + 悬停提示） | `renderPane 3493-3544` | **🚫** |
| 61 | 装饰/场景页 + 全部摘掉 | `renderPane 3546-3586` | **🚫**（但"自动戴"不依赖鼠标，见 §5.3） |
| 62 | 动作页 | `renderPane 3588-3606` | **🚫** |
| 63 | 设置页（大小/视线三参/口型开关/一键重置/回到角落/隐藏/退出） | `renderPane 3608-3762` | **🚫**（大小与位置可由宿主参数替代） |
| 64 | 一键重置所有状态 | `resetEverything 3312` | **❌** 逻辑可做，入口受限 |
| 65 | 输入框（说话/打断） | `bindComposer 3372`、`doSend 3397`、`lib/index.js:873 /say`、`:936 /cancel` | **🚫** |
| 66 | 钱包 HUD | `hudRender 3081-3126`、`hudFetch 3134-3190`、`openHud 3210`、`hudPopTurnEnd 3246` | **🚫** 右键入口；**数据我们本来就有**，可做常驻小字（§5.3） |
| 67 | 命中掩码（点空气穿透） | `mask 1855`、`buildMask 1906-1969`、`hitTest 1972-1983`、`bandWindow 1864`、`computeBands 1893`、`overDock 1989` | **🚫** 算法可移植，但我们的窗口**天生全程穿透**，掩码没有意义 |
| 68 | 鼠标交互（悬停/拖/戳/右键/双击） | `wireInteractions 2419-2606` | **🚫** 见 §4.1（`reactions.js:18-19` 也已注明不做） |
| 69 | 戳她（分区 + 连击分档） | `poke 2861-2934`、`POKE_TIER 2629-2642`（2.6 s 窗口；>2.4 次/秒=痒；>3.8 次/秒且≥7 下=炸毛，6 s 冷静）、`POKE_BUSY 2708`、`POKE_HEAD 2722`、`POKE_BODY 2786` | **🚫** |
| 70 | 贴边小球（收起态） | 桌面壳 `desktop/windows/main.js` / `macos/ball.swift` | **🚫** 需要壳 |
| 71 | 音效 | `DEFAULT_CONFIG.sound`（`lib/index.js:80`，上游也**只预留未实现**） | — |
| 72 | 诊断页 | `lib/index.js:1015 /dsh-pet/diag`、`:815 /dsh-pet/state` | **🟡** `PetAPI.selfTestResult/startSelfTest/modelMetrics` + `PetReactions.trace()/snapshot()` 是等价物，但没有页面 |

### 3.8 宿主侧（`lib/index.js`）

| # | 能力 | 位置 | 我们的状态 |
|---|---|---|---|
| 73 | 注入 DSH Web 页面 | `lib/index.js:1081-1085` | **✅ 不同做法**：独立透明窗口，不注入（这正是用户要的形态） |
| 74 | 配置 | `DEFAULT_CONFIG 57-85`（height/corner/lookAtCursor/talkMouth/sleepAfterMs/bubbleTtlMs/showComposer/showReasoning/sound） | **🟡** 我们的可调项散在宿主参数与 `ACT` 表里，没有统一配置 |
| 75 | 本机通行证 | `lib/index.js:350-360` | **✅ 不需要**：`pet://` 自定义协议，无端口暴露 |
| 76 | 静态资源路由 | `/dsh-pet/vendor :476`、`/dsh-pet/model :487`（中文名 `decodeURIComponent`） | **✅** `SetVirtualHostNameToFolderMapping` |
| 77 | 记账（余额/峰谷/本轮 tokens） | `lib/index.js:213-310`、`:796 /hud` | **🟡** `engine` 有同样数据，`state.json` 已通；没做成 HUD |

### 3.9 ✅ 我们已经完成、上游没有（或比上游更贴需求）的部分

| 能力 | 说明 |
|---|---|
| 独立透明窗口 + 逐像素 alpha | 上游是注入 DSH 页面的挂件（`lib/index.js:1081`）；我们挂在看板外，**这是用户要的形态** |
| `signals.json` 反应信号桥 | `reactions.js` 的两个输入之一，携带 `tool{name,phase,ok,error,summary}` / `lastError` / `turn{phase,reason,ms,tokens}` / `streaming.active` / `lastUserAt/Text` / `idleMs` / `agents` / `jobs` —— **这正是 task-6 里判定"引擎缺的透传"，task-7 已经把它补出来了** |
| 11 档活动状态 + 定宽标签 | 比上游的 mood 更贴「agent 在干什么」 |
| 表情声明补丁 | 上游自己读 `manifest.json` 所以不会踩；我们踩了并已修（task-7，44/44 实测） |
| 展示用 forced 模式 | `setForced()` + `force-state.json`，可离线拍 11 个状态的图（`pet/showcase/`） |

---

## 4. 三类必须分开的「没做」

### 4.1 🚫 受架构限制（**当前宿主**下做不到）

**清单**：#53 视线跟随光标、#55 拖动/贴边吸附、#58 工具栏、#59–63 五页菜单、#64 一键重置入口、#65 输入框、#66 右键 HUD、#67 命中掩码、#68 鼠标交互、#69 戳她/摸头/连点炸毛、#70 贴边小球。另 #52 的「鼠标一动就醒」也在此列。

**原因（task-1 实测，非推测）**：宿主是 WPF + WebView2，窗口开了 `AllowsTransparency=True`。
`pet-app.js` 的 `alphaProbe` 读到画布四角 `[0,0,0,0]`，而 WPF 自身绘制表面是空的（内容全在 WebView2 子窗口里），
于是整个分层窗口 alpha=0 → **Windows 按 alpha 命中，全程穿透**。
`hitmap.ps1` 在 231 个探测点得到 `0/231`（开/关穿透都一样），`WindowFromPoint` 永远返回下层窗口。
**页面收不到 `pointermove`/`pointerdown`/`contextmenu`。**（`reactions.js:18-19` 已据此写明不做。）

**这不是"永远不可能"，而是"必须先动宿主"**。三条候选，**均未做实验**：

| 路径 | 做法 | 代价 | 风险 |
|---|---|---|---|
| A 换 Electron 宿主 | `transparent:true` + `setIgnoreMouseEvents(bool,{forward:true})`；task-1 已实测关穿透时 `WindowFromPoint` 命中桌宠 | 需要 366 MB 运行时（已删除） | 体积 |
| B Win32 分层 + 色键 | `WS_EX_LAYERED` + `LWA_COLORKEY`（品红底） | 中等 | **WebView2 走 DirectComposition，色键是否作用于其输出未知**；且与逐像素透明冲突 |
| C 让 WPF 层带极低 alpha 剪影 | 把命中轮廓画进 WPF 图层（alpha=1/255），视觉不可见、命中恢复 | 需要在宿主里离屏渲染取轮廓 | **完全未验证**：还需 WebView2 子窗口在那些像素上"让点击落回父窗口"，否则点击打到子窗口、页面仍收不到 |

**建议**：把「桌宠可点击」单独立项做一次**宿主实验**（先 C，最小，不行再评估 A）。
在那之前，§4.1 的能力一律不做，也不要在 UI 上留半成品。

### 4.2 ❌ 仅为取舍未做（**能做，只是没排上**）

按性价比排序（**这是接下来的实施清单**）：

| 优先级 | 能力 | 为什么 |
|---|---|---|
| **P0** | 一次性动作 11 个 + `act()` 合成（#29/#30/#31） | 上游「装饰/场景/动作」三页的内容主体；`openLid` 已经证明 `playMotion`+定格链路通，加动作只是查表 |
| **P0** | 场景 7 项 + 装饰手动开关（#9 补全/#11 补全/#12/#13/#17） | 全靠 44 个表情驱动，**零新素材**；没有鼠标，所以先做「事件驱动的自动佩戴 + 宿主参数开关」 |
| **P0** | `qBounce` 收工蹦一下（#43 缺件） | 纯 CSS 一行，补上"伸懒腰比耶"的观感 |
| **P1** | 爱心粒子（#7） | 摸头/爱心的观感来源；`love`+`heartbeat` 直接可用 |
| **P1** | 工作轮播 9–14 s（#47） | 用户要的「干活时不是钉在一张脸上」 |
| **P1** | 低性能档（#56） | `applyPerf` 二十行，直接解决"又热又卡" |
| **P1** | 用户持久层 `userProps`（#18 补全）+ 互斥组（#17） | 装饰/场景要"戴上就留着"必须靠它 |
| **P1** | `pickFresh` 去重台词（#26）+ 补全台词池（#25/#27） | 连着两次同一句很出戏 |
| **P2** | 眨眼自控（#5） | 让"动作期间不眨眼"成立 |
| **P2** | 爱心粒子之外的粒子/脉冲 |  |
| **P2** | HUD 常驻小字（#66 降级） | 数据现成，只画不点 |
| **P2** | 命名行气泡（#57 补全）、诊断页（#72 升级） | 打磨 |
| **P3** | 音效（#71，上游也只预留）、配置统一（#74） |  |

### 4.3 ✅ 已经做完的

见 §3.9。**特别提示：task-6 里我判定"引擎缺透传、报错黑脸/收工统计做不了"的那个结论，
已经被 task-7 的 `signals.json` 解决了** —— 这三项现在都是 ✅。这条必须写进结论，否则又是一次过期判断。

---

## 5. 实现指南（针对 §4.2 的清单）

### 5.1 素材来源一律照抄上游，不要自创

| 要加的东西 | 上游位置 | 素材（短英文名见 `REACTIONS-SPEC.md` §1.1） |
|---|---|---|
| 11 个一次性动作的素材/时长/台词 | `ACTIONS 176-221` | `catPaws`/`doubleV`/`heartPop`/`heartbeat`/`squeeze`/`eraser`/`undo`/`omurice`+motion`ketchup`/motion`selfie`/motion`selfieQuick`/motion`splash` |
| 场景 7 项 | `SCENES 137-145` | `darkCloth`/`whaleOnDesk`/`parfait`/`claw`/`clawRecolor`/`phone`(openLid 定格)/`phoneRecolor` |
| 装饰 11 项 | `PROPS 116-128` | 4 眼镜 / 3 贴纸 / `sparkle` / `ponytail` / `headband` / `whaleHat` |
| 互斥组与前置 | `setProp 892-946` | `glasses`(4 互斥) / `sticker`(3 互斥) / `headwear`(`sparkle`+`headband`) / `hair` / `cloth` / `claw`+`clawColor` / `device`；**前置**：`clawRecolor→claw`、`phoneRecolor/selfie/selfieQuick→phone` |

### 5.2 与现有 11 档状态的关系（**不要另起一套**）

- **11 档状态 = base 的"活动类别"**（`state.json`）→ 决定**标签**与"该活动的默认脸/道具"（现在 `reactions.js:65-87 ACT` 已经在做）。
- **一次性动作 / 粒子 / 蹦跳 = override 层**，TTL 到期回落 base（现在已有）。
- **装饰 / 场景 = 未来的 `userProps` 持久层**：优先级最高、不限期、由用户或事件开关；`override` 期间是否让位照上游 `resolveRig 812-816`（`exclusive` 时连常态道具都放下）。
- **工具事件**只改 base（`reactions.js:441`）或给短 TTL（`432`），**不写 userProps**——否则会出现上游反复修的"道具赖着不走"。

### 5.3 没有鼠标怎么触发装饰/场景（务实做法）

既然点不到菜单，就用**事件驱动 + 宿主参数**先跑起来，等 §4.1 有结论再补手动入口：

| 场景 | 触发（现成信号） |
|---|---|
| 读资料自动戴眼镜 | **已有**（`ACT.reading/grep` 的 faces 权重） |
| 交付自动戴 `stickerCat` | **已有**（`ACT.todo/present`） |
| 收工随机装饰 | **已有**（`reactions.js:461`） |
| 新目标戴 `heartbeat` | `signals.tool.name === 'create_goal'` → `ACT.goal` 加 props |
| 上网掏手机 | **已有**（`ACT.web/fetch` 的 `device:true`） |
| 深色桌布 / 巴菲 / 魔爪 / 鲸鱼放桌上 | 加一个**宿主参数**（如 `host.ps1 -Props darkCloth,parfait`）或复用 `signals`，先让它们能被触发与验证 |
| 手机换色 | 在 `phone` 已开时由宿主参数打开（并实现前置自动补） |

### 5.4 两个必须在实现时一起修的既有问题

1. **待机不应放动作**：上游明确 `idle` 那支是「猫爪 + 爱心」循环、**已停用**（`SKILL.md`「待机不放动作」）。
   我们现在仍用 `idleMotionGroup` 让它循环 —— 应当**停掉常驻动作**，把 `idle` 只当 `ACTIONS.paw` 的一次性 4400 ms 素材。
2. **`exclusive` 语义**：上游报错时是 `props:[]` **+ `exclusive:true`**（连本子笔都放下，"砸的时候就只砸一下"）。
   我们 `reactions.js:200` 只是"override 时不挂 props"，**常态道具是否要在此刻摘下没有显式表达**，建议补 `exclusive` 字段。

### 5.5 工作量与风险

| 项 | 工作量 | 风险 |
|---|---|---|
| 11 个一次性动作 + `act()` | 2 天 | 低（链路已通：`playMotion`/定格/`clearMotionPose` 都在） |
| 场景 + 装饰 + 互斥/前置 + `userProps` | 2–3 天 | 低（纯查表与集合运算）；**风险在"没有入口"**，先走 §5.3 |
| `qBounce` / 爱心粒子 / 工作轮播 / 低性能档 | 1 天 | 低 |
| `pickFresh` + 台词池补全 | 0.5 天 | 低 |
| 眨眼自控 | 0.5 天 | 中（要避开动作，参考上游 `motionActive`） |
| 宿主实验（可点击） | 1–2 天 | **高**（三条路径都未验证，可能全部失败；失败则接受"只读桌宠"） |

---

## 6. 一句话给决策者

- **素材：够。** 44 表情 + 8 动作，一个不缺；task-7 已把声明补齐，44/44 生效。
- **「缺素材」是误判**：错在只读清单不读代码。上游有整套道具/装饰/场景系统，全靠这 44 个表情，**零新增素材**。
- **而且我们已经补了一大半**：常态道具、按工具换脸换道具、随机眼镜、掏小设备定格、报错黑脸、
  收工庆祝+统计、口型、视线、气泡逐字、待机大脑、看门狗 —— 都在 `reactions.js` 里跑起来了
  （task-6 里"引擎缺透传"的判断也已被 task-7 的 `signals.json` 解决）。
- **还剩两块**：① 一次性动作 / 场景 / 装饰 / 持久层 / 轮播 / 低性能档（**能做，1–3 天**）；
  ② 所有要鼠标的能力（**宿主架构问题**，需一次实验，失败就接受"只读桌宠"）。

---

## 7. 交付物与参考文件

```
pet/UPSTREAM-GAP.md                     ← 本文
pet/model/_ref/upstream2/
  assets/pet.js                         194,372 B  前端全部行为（4,476 行）
  assets/manifest.json                   20,593 B  44 表情 + 8 动作（含 duration）
  lib/index.js                           45,547 B  宿主：事件→SSE、路由、HUD、配置
  docs/作者按键表-对照.md                  6,440 B  52 条热键逐条对照
  docs/index.html                        12,753 B  项目主页
  skill/SKILL.md                         12,689 B  驱动指南（自动反应表 + 时长）
```

配套（均在项目内）：
- `pet/REACTIONS-SPEC.md` —— 44 表情短英文名、11 档状态枚举、TOOL_LINE 全表、优先级/打断规则、日志字段映射、`model3.json` 补丁片段
- `pet/renderer/reactions.js` —— **我们的策略层现状**（564 行；本文 §3 的「我们」一列即以此为准）
- `pet/renderer/signals.json` / `state.json` —— 反应层的两个输入
- `pet/showcase/` + `pet/host/react*/` —— 11 个状态的实拍图（可用于对照上游观感）
