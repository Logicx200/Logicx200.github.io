# REACTIONS-SPEC —— 「她会对 agent 做什么反应」完整规格

> 交付：`pet-renderer`（task-6）· 2026-09-30
> 目的：把用户在原项目主页看到的**反应表**补全、逐条落到**真实素材**上，并给出**触发信号 → 反应**的对应关系。
> 上游事实来源（全部逐字核对过，不是猜的）：
> - `Andersen216/dsh-whale-girl-live2d`（<https://github.com/Andersen216/dsh-whale-girl-live2d>）
>   `README.md` §"她跟 agent 的联动"、`skill/SKILL.md`、`docs/作者按键表-对照.md`、`assets/pet.js`、`lib/index.js`
> - `A8Chann/dsh-pet-live2d` `dsh-live2d-pet/README.md` §"会话相位"、`pets/ds-whale-girl/pet.json`
> - 我们自己的 `engine/*.mjs`、`pet/state.mjs`、`pet/STATE-PROTOCOL.md`
> 参考文件已落地到 `pet/model/_ref/`（见 §9）。

---

## 0. 两个硬结论（先看这个）

### 0.1 `FileReferences.Expressions` —— 本地**没有**，A8Chann **有**

| 文件 | `FileReferences.Expressions` |
|---|---|
| 我们本地 `pet/model/c_0120.model3.json`（= Andersen216 的 `assets/model/c_0120.model3.json`） | **不存在**。`FileReferences` 只有 `Moc` / `Textures` / `Physics` / `DisplayInfo` / `Motions` |
| 原始模型包 `A8Chann/.../model-packs/DS鼠控版/c_0120.model3.json` | **不存在**（连 `Motions` 都没有，只有 4 个引用） |
| **`A8Chann/.../pets/ds-whale-girl/c_0120.model3.json`** | **有，44 条**（`Name` 是中文，`File` 是英文名文件） |

所以：Andersen 那份是**手写生成**的（`tools/build-model.mjs`），只补了 `Motions`，漏了 `Expressions`；
A8Chann 那份把 44 个表情的英文副本一并声明了。**这就是运行时 `expressionManager === undefined` 的唯一原因**——
不是 pixi-live2d-display 的问题，是 `model3.json` 里没有声明。

### 0.2 已实测：补上声明后 **44/44 全部生效**

我按用户批准的「只加声明、不动美术」补了一份 `model3.json`，并用真实 WebGL 跑起来验证：

```
expressionManager: DEFINED
definitions: 44   (expected 44)
neutral in-frame fingerprint: 426.531
model.expression(name) accepted: 44/44
in-frame fingerprint changed: 44/44
```

- 复现台：`pet/model/_ref/verify/`（自带 `index.html` + `model3.json` + 一键启动脚本）
- **44 个表情逐个实测有效**，列表见 §3。
- 读参数**必须在帧内**（包 `coreModel.update`）——帧外读拿到的是引擎还原过的基线，
  会得出「44 个都没生效」的错误结论（我第一次探针就是这么错的，见 §10 坑 1）。

> ⚠️ 一个必须说清的小限制：`coreModel.getParameterValueById('ParamCheek16')` 在帧外读回的是 `0`，
> 所以**不要用「按名字读某个参数」来断言表情生效**；用整帧参数指纹（求和）才可靠。

---

## 1. 素材底账（我们真正有的东西）

### 1.1 表情：**44 个**（不是 48）

`pet/model/expressions/*.exp3.json` 实际 **44 个**，与 A8Chann 声明的 44 条一一对应，
`星星眼.exp3.json` / `脸红.exp3.json` 与 A8Chann 的同名英文副本**内容完全一致**（同样的 `ParamCheek16` / `Paramhh2`）。
文件路径与短英文名（**下游代码只引用这个短名，绝不引用中文文件名**）：

| Name | 文件（相对 `pet/model/`） | 中文 | 用途备注 |
|---|---|---|---|
| `starry` | `expressions/星星眼.exp3.json` | 星星眼 | **听主人说 / 凑近看**（`ParamCheek16`） |
| `loveEyes` | `expressions/爱心眼.exp3.json` | 爱心眼 | 情绪 |
| `heartPop` | `expressions/love.exp3.json` | 冒爱心 | 一次性动作 `love` |
| `blush` | `expressions/脸红.exp3.json` | 脸红 | 被摸头/被夸（`Paramhh2`） |
| `excited` | `expressions/开心兴奋.exp3.json` | 开心兴奋 | 交付/庆祝 |
| `sad` | `expressions/悲伤.exp3.json` | 悲伤 | 被中断 |
| `cry` | `expressions/哭.exp3.json` | 大哭 | 失败 |
| `angry` | `expressions/生气.exp3.json` | 生气 | 「才不胖」 |
| `naughty` | `expressions/调皮.exp3.json` | 调皮 | 傲娇/得意 |
| `blank` | `expressions/呆呆眼.exp3.json` | 呆呆眼 | **禁用**（主人点名不要） |
| `drool` | `expressions/闭眼口水.exp3.json` | 闭眼口水 | **睡着** |
| `dizzy` | `expressions/晕晕.exp3.json` | 晕晕 | **禁用** |
| `gloomy` | `expressions/阴暗.exp3.json` | 阴暗 | **工具报错「黑脸」** |
| `tongueOut` | `expressions/吐舌.exp3.json` | 吐舌 | 待机表情池 |
| `soulOut` | `expressions/吐魂.exp3.json` | 吐魂 | 摸尾巴 |
| `sweat` | `expressions/流汗.exp3.json` | 流汗 | 求救/失败 |
| `question` | `expressions/问号.exp3.json` | 问号 | **要你确认 / 问你问题** |
| `exclaim` | `expressions/感叹号.exp3.json` | 感叹号 | 新目标 / 被吓到 |
| `sparkle` | `expressions/情绪花花.exp3.json` | 情绪花花 | 庆祝装饰 |
| `heartbeat` | `expressions/心跳.exp3.json` | 心跳 | 庆祝装饰 / 新目标 |
| `glassesRound` | `expressions/圆眼镜.exp3.json` | 圆眼镜 | **读资料（随机三选一）** |
| `glassesSquare` | `expressions/方眼镜.exp3.json` | 半框方眼镜 | 同上 |
| `glassesOval` | `expressions/椭圆眼镜.exp3.json` | 椭圆眼镜 | 同上 |
| `sunglasses` | `expressions/墨镜.exp3.json` | 墨镜 | 装饰 |
| `stickerCat` | `expressions/猫猫贴纸.exp3.json` | 猫猫贴纸 | **交付/列清单 的奖励装饰** |
| `stickerRabbit` | `expressions/兔兔贴纸.exp3.json` | 兔兔贴纸 | 庆祝装饰 |
| `stickerBow` | `expressions/蝴蝶结贴纸.exp3.json` | 蝴蝶结贴纸 | 装饰 |
| `ponytail` | `expressions/单边马尾.exp3.json` | 单边马尾 | 装饰 |
| `headband` | `expressions/头箍.exp3.json` | 发箍 | 装饰 |
| `whaleHat` | `expressions/鲸鱼.exp3.json` | 头顶鲸 | 装饰 |
| `whaleOnDesk` | `expressions/鲸鱼放桌上.exp3.json` | 鲸鱼放桌上 | 场景 |
| `parfait` | `expressions/巴菲.exp3.json` | 桌面巴菲 | 场景 |
| `claw` | `expressions/魔爪.exp3.json` | 粉魔爪 | 场景 |
| `clawRecolor` | `expressions/魔爪换色.exp3.json` | 白魔爪 | 场景（前置 `claw`） |
| `darkCloth` | `expressions/深色桌布.exp3.json` | 深色桌布 | 场景 |
| `phoneRecolor` | `expressions/手机换色.exp3.json` | 手机换色 | 场景（前置「掏出手机」） |
| `menuPress` | `expressions/点菜按下.exp3.json` | 点菜按下 | **常态道具（板子）** |
| `brush` | `expressions/画笔.exp3.json` | 画笔 | **常态道具（笔）+ 写文件** |
| `eraser` | `expressions/橡皮.exp3.json` | 橡皮擦 | 一次性动作 |
| `undo` | `expressions/撤回.exp3.json` | 撤回 | 一次性动作 |
| `omurice` | `expressions/蛋包饭.exp3.json` | 蛋包饭 | 一次性动作（配 `ketchup`） |
| `squeeze` | `expressions/挤.exp3.json` | MoeMoeQ~ | 一次性动作 |
| `doubleV` | `expressions/双手比耶.exp3.json` | 双手比耶 | 一次性动作 |
| `catPaws` | `expressions/喵喵手~喵~动画.exp3.json` | 喵喵手动画 | 一次性动作 |

### 1.2 动作：`Motions` 里 8 组（我们本地已声明）

| 组名（model3 里的 key） | 文件 | Meta | 现在的用法 |
|---|---|---|---|
| `idle` | `motions/idle.motion3.json`（45,228 B） | **`Loop: true`，Duration 4** | ⚠️ **这其实是「猫爪摆手 + 爱心」循环动画，原作者明确停用它**。见 §4 关键决定 |
| `aidale` | `motions/_aidale.motion3.json` | — | ❌ **禁用**（「大锤砸」，且内部驱动 15 个表情参数，一播表情全乱） |
| `selfie` | `motions/自拍.motion3.json` | — | 一次性（前置：掏出手机） |
| `selfieQuick` | `motions/自拍简单.motion3.json` | — | 一次性（前置：掏出手机） |
| `ketchup` | `motions/番茄酱.motion3.json` | — | 一次性（蛋包饭收尾） |
| `openLid` | `motions/开盖.motion3.json` | — | **掏出小设备（手机）**，工作时长按定格 |
| `bubble` | `motions/chuipaopao.motion3.json` | — | ❌ 不上（主人点名不要） |
| `splash` | `motions/喷水.motion3.json` | — | 一次性（戳她时随机） |

**没有对应资产的「动作」**（很重要，别去找不存在的文件）：
- 「奋笔疾书」「挽袖子」在原实现里**只是气泡台词**（`TOOL_LINE.write[1] = '（奋笔疾书）写上了'`、`TOOL_LINE.bash[0] = '（挽袖子）跑个命令试试'`），**没有专属 motion / expression**。
- 「走路般的小幅度摆动」在原实现里也没有资产；逐字输出时只有**口型**（`ParamMouthOpenY`）和气泡，庆祝时有一个纯 CSS 的 `qBounce(1.2)`。

---

## 2. 新状态枚举：从「7 个抽象状态」改成「活动类别」

取代原 `offline | stale | team | busy | working | peak | idle`。
颜色**沿用原冻结色表里还能对上的那 4 个**，其余新增，全部两两不同；`#7EE787` / `#FF7B72` 两个保留色**一律不用**。

| # | `state` | 中文标签 | 字数 | `color` | `pose` | 类别 | 触发（优先级从高到低） |
|---|---|---|---|---|---|---|---|
| 1 | `offline` | 离线 | 2 | `#8B949E` | `offline` | 系统 | DSH 进程不在 / `dshRunning === false` |
| 2 | `stale` | 数据过期 | 4 | `#D2A8FF` | `sleepy` | 系统 | 快照缺失，或 `now - snapshot.at > 45000` |
| 3 | `error` | 出错了 | 3 | `#F85149` | `gloomy` | 一次性 | **工具报错**或**整轮失败**，持续 1.6 s（轮级 3.2 s） |
| 4 | `celebrating` | 收工啦 | 3 | `#E3B341` | `happy` | 一次性 | `turn/end` 且 `reason.kind === 'completed'`，持续 3.0 s |
| 5 | `listening` | 听主人说 | 4 | `#79C0FF` | `starry` | 一次性 | 主人刚发消息，持续 2.6 s |
| 6 | `team` | 团队协作 | 4 | `#56D4DD` | `team` | 持续 | ≥ 2 个 agent `state === 'running'` |
| 7 | `reading` | 查资料 | 3 | `#58A6FF` | `reading` | 持续 | 工具 ∈ **读/搜**（见 §4.2） |
| 8 | `writing` | 写文件 | 3 | `#F0883E` | `scribble` | 持续 | 工具 ∈ **写/改** |
| 9 | `running` | 跑命令 | 3 | `#FFA657` | `sleeves` | 持续 | 工具 ∈ **shell/命令** 或 `jobs[]` 非空 |
| 10 | `thinking` | 想事情 | 3 | `#A5D6FF` | `thinking` | 持续 | 本轮进行中、当前无工具在跑 |
| 11 | `idle` | 空闲 | 2 | `#9DA7B3` | `idle` | 兜底 | DSH 在跑、什么也没发生 |

**相对于旧表的删改（请一并改 `pet/state.mjs` 与测试）**

| 旧 | 新 | 说明 |
|---|---|---|
| `busy` 后台任务 | → `running` 跑命令 | 后台任务本质就是「有工具在跑」，不再单独一档；颜色 `#FFA657` 沿用 |
| `working` 干活中 | → 拆成 `reading` / `writing` / `running` / `thinking` | 这正是用户要的「按活动类型换脸换动作」 |
| `peak` 峰时 | **从桌宠标签里去掉** | 峰谷是**面板**的职责（面板已经常显 峰/谷 + 距切换倒计时），桌宠标签让位给活动类别。若你仍想保留，加第 12 档 `peak` `#E3B341`，优先级放在 `idle` 之上、`thinking` 之下 |

### 2.1 标签显示：**定宽右对齐、不抽动**

用户明确要求。中文标签长度 2–4 个全角字，直接右对齐会让**左边缘**抖动；所以：

```css
#state-label {
  position: fixed;
  right: 8px;                 /* 右边缘锚死：右对齐 + 固定 right，右边缘永不动 */
  top: 8px;
  min-width: 4em;             /* 4 个全角字宽 = 最长标签「数据过期/听主人说」的宽度 */
  text-align: right;
  white-space: nowrap;
  font: 600 14px/1.25 "Microsoft YaHei", system-ui, sans-serif;
  font-variant-numeric: tabular-nums;   /* 数字等宽，detail 行的 token/金额不跳 */
  letter-spacing: 0;                     /* 不要动 letter-spacing */
  transition: color .25s ease, opacity .25s ease;  /* ⚠️ 只允许过渡 color/opacity */
  pointer-events: none;
}
#state-detail {
  position: fixed; right: 8px; top: 30px;
  min-width: 4em; text-align: right; white-space: nowrap;
  font: 11px/1.3 Consolas, monospace;    /* 等宽字体，天然不抽动 */
  font-variant-numeric: tabular-nums;
  color: rgba(220,228,240,.68);
  pointer-events: none;
}
```

**硬性禁止**：`transition: all`、`transition: width`、`transform: scale()` 在标签上、
按标签长度动态改 `right`、给标签加宽度动画。同时**不要**给标签铺底色块——
桌宠是透明分层窗口，任何不透明底都会多出一块方框（见 `renderer/README.md` §2）。

---

## 3. 活动类别 → 表情 / 动作 / 道具（完整对应表）

`pose` 是**语义**，`assets` 是**落地**。下表就是实现清单，`Name` 全部取自 §1.1。

### 3.1 持续态（base 层：一直在，直到被下一档覆盖）

| state | 表情 `expression` | 常态道具 | 额外动作 | 视线 | 说明 |
|---|---|---|---|---|---|
| `thinking` 想事情 | **null（平常脸）** | `menuPress` + `brush` | — | bias 0 | 主人要求「想事就是平常脸」，**不要呆滞眼** |
| `reading` 查资料 | `glassesRound` ⇄ `glassesSquare` ⇄ `glassesOval` ⇄ **null** 随机 | `menuPress` + `brush` + 抽中的眼镜 | 若是**设备类**工具：**收起笔、播 `openLid` 并定格**（掏出小设备） | **bias −0.32（低头看本子）** | 眼镜随机比例 **34 % / 28 % / 10 % / 28 % 不戴** |
| `writing` 写文件 | **null（认真脸）** | `menuPress` + `brush` | — | bias 0 | 「奋笔疾书」只有气泡台词，**没有专属表情** |
| `running` 跑命令 | **null（认真脸）** | `menuPress` + `brush` | — | bias 0 | 「挽袖子」只有气泡台词，**没有专属表情** |
| `listening` 听主人说（2.6 s） | `starry` | `menuPress` + `brush` | — | bias 0 | 气泡里放主人原话，ttl 3500 ms |
| `team` 团队协作 | **null** | `menuPress` + `brush` | — | bias 0 | ≥2 agent；气泡脚注「分身也在干活…」 |
| `idle` 空闲 | **null** | `menuPress` + `brush` | 待机大脑（§3.4） | 漂移 | 兜底复位：每 2 s 检查，base 必须是 neutral |

### 3.2 工具 → 反应（**按工具换脸换动作**的核心）

| 工具 `name` | `state` | 表情 | 顺手道具 | 气泡台词（原文照抄，`pickFresh` 轮换） | 摘要来源 `args` |
|---|---|---|---|---|---|
| `read` `pdf_read` `docx_read` `xlsx_read` `pptx_read` `skill` `auto_cite` | `reading` | 眼镜随机 | 眼镜 + 板子 + 笔 | `（凑近看）先读一下这份` / `人家看看里面写了啥` / `翻开看看…` / `（认真脸）读一下` | `file_path` |
| `grep` | `reading` | 眼镜随机 | 同上 | `（眯着眼）搜一下关键词` / `人家查查哪里用到了` / `（翻）搜搜看` | `pattern` |
| `glob` | `thinking` | null | 同上 | `（翻箱倒柜）找找在哪儿` / `人家找找这个文件` / `翻一下目录` | `pattern` |
| `web_search` | `reading` | 眼镜随机 | **掏出小设备 `openLid`（定格）** | `（掏手机）上网查一下` / `人家搜搜看` / `（划手机）查查这个` / `网上应该有答案` | `queries[0]` 或 `query` |
| `web_fetch` `browser` `fetch` | `reading` | 眼镜随机 | 小设备 | `（点开链接）读读这页` / `人家看看这个网页` / `（凑近屏幕）` | `url` |
| `search_papers` `search_arxiv` `pubmed_*` | `reading` | 眼镜随机 | 小设备 | `（翻文献）查查有没有人写过` / `人家去翻翻论文` / `（戴眼镜）查文献去` | `query` |
| `kb_search` `kb_rag` | `reading` | 眼镜随机 | 小设备 | `（查资料库）人家找找` / `翻翻知识库` / `（翻）这儿应该有` | `query` |
| `kb_ingest` | `reading` | `excited` | 小设备 | `（搬书）人家收进库里` / `把这份收好` | `path` |
| `write` `edit` | `writing` | null | 板子 + 笔 | `好，人家写出来` / `（奋笔疾书）写上了` / `这就给你落成文件` / `写成文件啦`；`edit` 用 `（改改改）这里调一下` … | `file_path` |
| `bash` | `running` | null | 板子 + 笔 | `（挽袖子）跑个命令试试` / `让人家敲两行命令` / `命令行交给人家` / `（噼里啪啦）跑起来了` | `command` |
| `todo_write` | `writing` → `excited` | `stickerCat` | 板子 + 笔 | `（列清单）先排个计划` / `人家记一下要做啥` / `（在本子上划拉）` | `description` |
| `subagent` `subagent_fork` `task` `workflow` `ralph` | `team` | null | 板子 + 笔 | `（招手）叫个分身来帮忙` / `人家派个分身去办` / `（分工）这就安排`；`workflow` 用 `（排兵布阵）同时开几路` | `description` |
| `present` `pdf_create` `docx_create` `pptx_create` `xlsx_write` | `celebrating` | `excited`（一次性 3 s） | `stickerCat` | `（举起来）喏，给你` / `人家交付啦` / `（递过去）弄好了` | `title` |
| `sci_draw` | `celebrating` | `excited` + `sparkle` | `sparkle` | `（画画）人家画一个` / `（拿笔）给你画出来` | `prompt` |
| `ask_user_question` | **`error`** 档同级的「等你」 | `question` | 板子 + 笔 | `（歪头）这个得问问主人` / `人家不确定，问一下` | `question` |
| `create_goal` | — | `exclaim` + `heartbeat` | — | `（立个目标）人家记下了` / `这个人家盯着办` | `objective` |
| `update_goal` `get_goal` | `thinking` | `exclaim` / null | — | `（看一眼任务）` / `人家看看进度` | — |
| **未匹配的其它工具** | `reading` | **`glassesRound`（兜底）** | 板子 + 笔 | 通用「认真看资料」台词 | 按 `command/file_path/path/pattern/query/url/title/description/prompt` 顺序取第一个非空值，截断 46 字 + `…` |

**`args` 摘要规则**（照抄 `toolHint()`）：键顺序
`command → file_path → path → pattern → query → url → title → description → prompt`，
再兜底 `queries[0]`；去换行、压空白、>46 字截断加 `…`。摘要放在**气泡第二行**，
脚注放工具中文名——这样面板那边在跑什么，桌宠能同步看出来。

**设备类工具集合**（会「掏出手机」的）：
`web_search` `web_fetch` `search_papers` `kb_search` `kb_rag` `search_semantic`
`search_google_scholar` `pubmed_search_papers` `search_arxiv` `browser` `fetch`。

### 3.3 结束态（一次性，override 层，带 TTL）

| 触发 | `state` | 表情 | 装饰 | 台词 / 附加 | 时长 |
|---|---|---|---|---|---|
| `turn/end` · `kind === 'completed'` | `celebrating` | `excited` | **随机一个**：`stickerCat` / `stickerRabbit` / `sparkle` / `heartbeat` | `SAY.done`（4 句轮换）+ **统计行**「12.3s · 41,380 tokens」+ `qBounce(1.2)`（纯 CSS 蹦一下，不碰模型参数） | **3000 ms**；统计行在 2800 ms 后接到气泡里，ttl 4200 ms |
| `turn/end` · `kind === 'aborted'` | — | `sad` | — | `诶…人家还没做完呢` / `被打断了…` | **2800 ms** |
| `turn/end` · `kind === 'error'` | `error` | `sweat` ⇄ `sad` 随机 | — | `SAY.fail` 3 句之一 + **错误摘要**（≤160 字） | **3200 ms** |
| `turn/end` · 其它 kind | — | `naughty`（傲娇） | — | — | **2600 ms** |
| `tool/result` · **有 `error`** | `error` | **`gloomy`（黑一下脸）** | **无**（`props: []`，`exclusive: true`） | `（脸黑了）这个工具报错了：<name\|code>` | **1600 ms** |
| `tool/result` · 无 `error` | `thinking` | null | 板子 + 笔 | 清掉工具道具、收起小设备 | 持续到下一个事件 |

> 「黑一下脸」**必须很短**（1.6 s）且**不叠任何别的东西**——用户原话是「不砸东西」，
> 而 `aidale`（大锤砸）已被永久禁用。`tool/result` 成功时**不是**庆祝，只回到 `thinking`。

### 3.4 待机大脑（只在她空闲时跑）

轮询 1200 ms，命中后 `nextAt = now + 3500 + rand*4000`（**3.5–7.5 s** 挑一件事）。
权重表（**这就是性格**，权重=频率）：

| 行为 | 权重 | 做什么 | 时长 |
|---|---|---|---|
| `glance` 看别处 | 46 | 立刻换一个视线落点（`gaze.nextDrift = 0`） | — |
| `express` 换个表情 | 28 | 池：`blush` `question` `excited` `exclaim` `tongueOut` `sweat` `loveEyes`（**必须不改变眼型的**） | **2200 + rand×2600 ms（2.2–4.8 s）** |
| `mutter` 自言自语 | 22 | `SAY.idle` 6 句轮换 | **4200 ms** |
| `hungry` 喊饿 | 4 | `naughty` + `SAY.hungry` | **4600 ms** |
| `nopang` 强调不胖 | 2 | `angry` + `SAY.fat` | **4200 ms** |

**渐进式困倦**（每 15 s 检查一次，`sleepAfterMs = 180000`）：

| 条件 | 反应 | 时长 |
|---|---|---|
| `quiet > 180000 × 0.55`（≈ 99 s）且 `rand < 0.4` | `sleepy`（`drool`）+ 气泡「（打了个哈欠）」 | **2600 ms** |
| `quiet > 180000`（**3 分钟**） | base 切 `sleepy`，气泡 `Zzz…` / `（打瞌睡）` / `（趴桌上睡着了）` | ttl 9000 ms |
| 睡着时鼠标动 | `alert`（`exclaim`）+ `SAY.wake` | **1800 ms** |

**工作轮播**（这是 `thinking` 态内部的慢切换，别再切太快）：

| 项 | 值 |
|---|---|
| 周期 | `now + 9000 + rand*5000` → **9–14 s** |
| 循环 | `reading`（看资料）⇄ `thinking`（思考）两档交替 |
| 触发条件 | `state !== 'idle'` 且不在一次性表演中 |
| 附带 | 只在气泡已可见且不在逐字输出时，更新气泡正文 + 脚注「看资料」/「思考中」 |

### 3.5 逐字输出（streaming）

| 信号 | 反应 | 备注 |
|---|---|---|
| 第一个 `delta` / `text-delta` | `state = listening`→`thinking`，**开头型气泡**（`stream: true`，不自动收），`rig.talking = true` | 气泡名「DS 鲸鱼娘」 |
| 每个 chunk | 气泡**逐字追加**；口型：`ParamMouthOpenY = 0.28 + 0.16 × sin(phase × 11)` | ⚠️ 这条要求 `model3.json` 的 `Groups.LipSync.Ids` 含 `ParamMouthOpenY`（见 §6） |
| `assistant/message` 收尾 | `rig.talking = false`，气泡定格成完整文本（sticky），脚注加「本轮 N tokens」 | |
| 被中断 | `m.interrupted` 为真时**不动**（保留上一句） | |

**「走路般的小幅度摆动」没有资产**。可选替代（都不碰模型参数）：
① 什么都不加，只有口型 + 逐字气泡（最保守）；
② 在容器上做 ±2 px 的竖向正弦位移（CSS，`prefers-reduced-motion` 时关闭）。
**不要**为了这个去播 `idle` 动作——那是猫爪+爱心循环动画。

---

## 4. 优先级与打断规则（实现必须照这个来）

### 4.1 分层

| 层 | 谁在里面 | 生命周期 |
|---|---|---|
| `userProps` | 用户手动戴的装饰/场景（眼镜、贴纸、桌布、手机…） | **常驻**，直到用户再点一下 |
| `base` | 活动类别决定的常态（表情 + 常态道具） | **持续**，被更高优先级的 base 覆盖 |
| `override` | 一次性表演（报错黑脸、庆祝、交付、听主人说、待机小动作） | **TTL 自动过期**，绝不写进 `userProps` |
| `talking` | 逐字口型 | 随流式输出开关 |

### 4.2 一次性的优先级（数字越大越强）

| 优先级 | 事件 | 时长 |
|---|---|---|
| 5 | **整轮结束**（completed / aborted / error） | 2.6–3.2 s |
| 4 | **工具报错黑脸** | 1.6 s |
| 3 | 交付类（`present` / `*_create` / `sci_draw`） | 3.0 s |
| 2 | `listening` 听主人说、要你确认的 `question` | 2.6 s（确认档 8.0 s） |
| 1 | 待机小动作（express / mutter / hungry / nopang） | 2.2–4.6 s |
| 0 | base | 持续 |

**规则**
1. **先归零再开始**：任何新的一次性表演前先 `stopActing()`，保证「一个表情 + 至多一个动作 + 至多一个装饰」。
2. **同级后到者顶掉先到者**；高优先级可打断低优先级；低优先级**不能**打断高优先级。
3. **同一参数只有一个写入者**：表情优先于道具；冲突记进 `state.exclusive.skipped` 便于排查。
4. **动作自带表情时不压脸**：`mood: null` 的动作（`selfie` / `selfieQuick` / `ketchup` / `splash` / 猫爪）把脸交还给动画。
5. **工作事件优先于点击互动**：干活时点她**不打断**（最多弹一下表示「知道了」）。
6. **`turn/end` 强制复位**：清 override（**连同装饰开关**）、清工具道具、收起小设备、base 回 `neutral`、`rig.talking = false`。这是**硬要求**，必须配**兜底看门狗**（每 2000 ms：`idle` 且无 override 时 base 必须 `neutral`、`gaze.biasTarget` 必须 0）。
7. **待机大脑不插队**：`override` 非空时 `runIdleBehavior()` 直接 return。
8. **切模式前先收动作**：`tool-call` 到达时 `stopActing()`；停动作必须同时 `clearMotionPose()`
   （把动作写过的参数设回 `getParameterDefaultValue()` 再 `saveParameters()` 一次），
   否则快照会把动作最后一帧一直装回来——症状是「手机收不回、表情回不去、一键重置也没用」。

### 4.3 回落规则（谁结束了回到哪）

| 结束事件 | 回落到 |
|---|---|
| 一次性 TTL 到 | 回到当前 `base` |
| `tool/result` 成功 | `base = thinking`（清工具道具、收小设备） |
| `turn/end` | `base = neutral` + 待机大脑重新开始计时 |
| `user/message` | `base = listening`（2.6 s）→ 之后由 `turn/start` 接管成 `thinking` |
| 用户手动清空 / 归位 | `neutral` + 摘掉全部道具 + 停轮播（否则几秒后又被推回工作脸，看起来像「重置没生效」） |

---

## 5. 触发信号：DSH 日志字段 → 反应

### 5.1 DSH 会话日志的原始事件（真源头）

位置：`$DSH_HOME/sessions/<workspace-dir>/<session-id>/session.v<N>.jsonl.zstd`
（`zstd` 是**多帧拼接**容器；我们引擎已有 `engine/zstd.mjs` + `engine/session-store.mjs` 能读）

| 日志记录 | 关键字段 | 我们的反应 |
|---|---|---|
| `session` | `id` `cwd` `origin` `delegationDepth` | 判定主会话 vs 子代理（`delegationDepth > 0` = 子代理） |
| `user/message` | `data.source.kind === 'user'`、`data.content[]` 里的 `text` | **`listening`**：`starry` + 气泡放主人原话（截 300 字）2.6 s |
| `turn/start` | `data.turn` | base → `thinking`，清零本轮 token 计数，`startWork()`（收起一次性表演、播/定格 `openLid`） |
| `step/start` | `data.turn` `data.step` | 气泡脚注「正在思考 · 第 N 步」 |
| `assistant/message` | `data.content[]`（`text` / `reasoning` / `image` / `tool-call`）、`data.usage.{input,cache,output}` | 定型气泡 + 累加本轮 tokens |
| `agent/assistant-stream` → `chunk` | `c.type`：`text-delta` / `reasoning-delta` / `tool-call-delta`（字段 `c.text` / `c.name`） | **逐字气泡 + 口型**；`tool-call-delta` = 工具即将调用（可提前探头） |
| `tool/call` | `data.callId`、`data.name`、**`data.arguments`（JSON 字符串）** | **§3.2 整张表**：`state` + 表情 + 道具 + 气泡台词 + args 摘要 |
| `tool/result` | `data.message.content[0].toolCallId`、**`data.error.{name,code}`** | 有 `error` → **`error` 档黑脸 1.6 s**；无 → `thinking` |
| `turn/end` | `data.turn`、**`data.reason.kind`**（`completed` / `error` / `aborted`）、`ms`、`tokens` | **§3.3 整张表**：庆祝 / 中断 / 失败 + 统计行 |
| `approval/request` | 等你批准 | `question` + 「需要你点一下确认」8.0 s |
| `user-questions/request` | 它问了你一个问题 | `question` + 举手 |
| `subagent/descriptor` `subagent/start|end` | 子代理起止 | `team` 档 + 气泡脚注「分身也在干活…」 |
| `agent/error` | 出错 | `error` 档 |

`error` 的两种粒度：**`tool/result` 的 `error`** = 单个工具挂了（1.6 s 黑脸）；
**`turn/end` 的 `reason.kind === 'error'`** = 整轮失败（3.2 s + 错误摘要）。**两件事，别混。**

### 5.2 我们引擎现有的 NDJSON（**缺口清单，必须知道**）

`node engine/cli.mjs` 现在只吐四类行：

```
{"type":"ready",   at, pollMs, usdToCny}
{"type":"snapshot",at, peakNow, rate, today{…}, total{…}, balance{…}, agents[…], jobs[…], jobsSource}
{"type":"event",   at, session, turn, step, model, hit, miss, out, costUsd, costCny}
{"type":"error",   at, message}
```

| 能直接拿到 | 字段 |
|---|---|
| agent 列表 | `agents[]`：`{id,label,state:'running'|'idle',model,turn,startedAt,elapsedMs,sinceLastWriteMs}` |
| 正在跑的工具 | `jobs[]`：`{id,session,program,command,startedAt,elapsedMs,progress,progressNote}` |
| 峰谷 | `snapshot.peakNow` |
| 每次 assistant 记账 | `event`：`hit/miss/out`、`costUsd/costCny`、`turn`、`step` |

| **拿不到**（→ 这些反应做不了） | 缺什么 |
|---|---|
| ❌ **工具报错黑脸** | `jobs[]` 行**没有 `error` 字段**；`tool/result` 只被用来**移除**未配对的 call（`results.add(id)`），成败信息被丢掉了 |
| ❌ **按工具名分类** | `jobs[].program` 是 `programOf(parseArguments(raw), call.name)`：`bash` 的参数里带 `command` 时返回的是**内层程序名**（`pwsh` / `node` / `python`），**不是** `bash`。只有参数里没有程序名时才回落到工具名 |
| ❌ **收工庆祝 + 用时/花费** | snapshot 里**没有** `turn/end` 的 `reason.kind` / `ms` / `tokens`；`agents[].state` 由 `running` 变 `idle` 只能推断「刚结束」，分不出 completed/aborted/error |
| ❌ **逐字气泡 + 口型** | `event` 是按 **assistant/message** 聚合的，不是 token 级 delta |
| ❌ **等你确认 / 问你问题** | 无 `approval` / `user-questions` 信号 |

**结论（实现必须选一条路）**

- **推荐 A：反应层直接复读 DSH 会话日志**（复用 `engine/zstd.mjs` + `engine/session-store.mjs` 的解析），
  这样 §5.1 的**全部**信号都拿得到，也不用改引擎。
- **推荐 B（更省事）：给引擎加一类透传行**，例如
  `{"type":"tool","phase":"call"|"result","name":…,"args":…,"ok":bool,"error":{name,code}}`
  与 `{"type":"turn","phase":"start"|"end","reason":{kind},"ms":…,"tokens":…}`，
  再把 `tool/call.data.name` **原样**放进 `jobs[].name`。
  ⚠️ 但 `engine/**` **不在本任务写范围内**，这条要**另开任务**由引擎 owner 做。

在只吃现有 NDJSON 的降级模式下，能做到的是：`listening`（靠 `agents[].sinceLastWriteMs` 骤降近似）、
`thinking` / `reading` / `writing` / `running` **只按 `jobs[].program` 粗分**、
`idle`、`offline`、`stale`、`team`、`peak`；**报错黑脸、收工统计、逐字口型做不了**。

---

## 6. 最小元数据改法（可直接照抄）

### 6.1 改什么

在 `pet/model/c_0120.model3.json` 的 `FileReferences` 里**新增 `Expressions`**（放在 `Motions` 之后），
并把 **`Groups[LipSync].Ids` 从 `[]` 改成 `["ParamMouthOpenY"]`**（否则逐字口型永远是闭嘴）。
**不动任何 `.moc3` / 贴图 / `.exp3.json` / `.motion3.json`。**

`ParamMouthOpenY` 已确认存在于 `c_0120.cdi3.json`（同族的 `ParamMouthForm` 也在），所以这条是纯声明。

### 6.2 片段（44 条，**完整可直接粘贴**）

完整可用文件已生成：**`pet/model/_ref/c_0120.model3.patched.json`**（直接替换原文件即可）。
`Expressions` 数组单独一份在 `pet/model/_ref/expressions-names.json`，TSV 对照表在 `expressions-names.tsv`。

开头与结尾长这样（中间按 §1.1 表格顺序全列）：

```json
"Expressions": [
    { "Name": "heartPop",     "File": "expressions/love.exp3.json" },
    { "Name": "loveEyes",     "File": "expressions/爱心眼.exp3.json" },
    { "Name": "parfait",      "File": "expressions/巴菲.exp3.json" },
    { "Name": "sad",          "File": "expressions/悲伤.exp3.json" },
    { "Name": "drool",        "File": "expressions/闭眼口水.exp3.json" },
    { "Name": "undo",         "File": "expressions/撤回.exp3.json" },
    { "Name": "blank",        "File": "expressions/呆呆眼.exp3.json" },
    { "Name": "ponytail",     "File": "expressions/单边马尾.exp3.json" },
    { "Name": "omurice",      "File": "expressions/蛋包饭.exp3.json" },
    { "Name": "menuPress",    "File": "expressions/点菜按下.exp3.json" },
    { "Name": "naughty",      "File": "expressions/调皮.exp3.json" },
    { "Name": "glassesSquare","File": "expressions/方眼镜.exp3.json" },
    { "Name": "exclaim",      "File": "expressions/感叹号.exp3.json" },
    { "Name": "stickerBow",   "File": "expressions/蝴蝶结贴纸.exp3.json" },
    { "Name": "brush",        "File": "expressions/画笔.exp3.json" },
    { "Name": "squeeze",      "File": "expressions/挤.exp3.json" },
    { "Name": "whaleHat",     "File": "expressions/鲸鱼.exp3.json" },
    { "Name": "whaleOnDesk",  "File": "expressions/鲸鱼放桌上.exp3.json" },
    { "Name": "excited",      "File": "expressions/开心兴奋.exp3.json" },
    { "Name": "cry",          "File": "expressions/哭.exp3.json" },
    { "Name": "blush",        "File": "expressions/脸红.exp3.json" },
    { "Name": "sweat",        "File": "expressions/流汗.exp3.json" },
    { "Name": "stickerCat",   "File": "expressions/猫猫贴纸.exp3.json" },
    { "Name": "catPaws",      "File": "expressions/喵喵手~喵~动画.exp3.json" },
    { "Name": "claw",         "File": "expressions/魔爪.exp3.json" },
    { "Name": "clawRecolor",  "File": "expressions/魔爪换色.exp3.json" },
    { "Name": "sunglasses",   "File": "expressions/墨镜.exp3.json" },
    { "Name": "sparkle",      "File": "expressions/情绪花花.exp3.json" },
    { "Name": "darkCloth",    "File": "expressions/深色桌布.exp3.json" },
    { "Name": "angry",        "File": "expressions/生气.exp3.json" },
    { "Name": "phoneRecolor", "File": "expressions/手机换色.exp3.json" },
    { "Name": "doubleV",      "File": "expressions/双手比耶.exp3.json" },
    { "Name": "headband",     "File": "expressions/头箍.exp3.json" },
    { "Name": "soulOut",      "File": "expressions/吐魂.exp3.json" },
    { "Name": "tongueOut",    "File": "expressions/吐舌.exp3.json" },
    { "Name": "stickerRabbit","File": "expressions/兔兔贴纸.exp3.json" },
    { "Name": "glassesOval",  "File": "expressions/椭圆眼镜.exp3.json" },
    { "Name": "question",     "File": "expressions/问号.exp3.json" },
    { "Name": "eraser",       "File": "expressions/橡皮.exp3.json" },
    { "Name": "heartbeat",    "File": "expressions/心跳.exp3.json" },
    { "Name": "starry",       "File": "expressions/星星眼.exp3.json" },
    { "Name": "gloomy",       "File": "expressions/阴暗.exp3.json" },
    { "Name": "glassesRound", "File": "expressions/圆眼镜.exp3.json" },
    { "Name": "dizzy",        "File": "expressions/晕晕.exp3.json" }
]
```

```json
{ "Target": "Parameter", "Name": "LipSync", "Ids": ["ParamMouthOpenY"] }
```

### 6.3 授权影响（用户已批准，但这句必须留档）

模型素材是 **CC BY-NC-SA 4.0**（署名 — **非商业性使用** — 相同方式共享），
版权归 **上善无形 / ZipZipPipe / 氵六青** 三位。

**补 `Expressions` 声明 + 改 `LipSync` 是对模型的改编，因此这份 `model3.json` 属于「派生作品」。**
- **个人 / 给朋友的小范围自用：可以**（用户已明确批准，正是这个范围）。
- 一旦对外分发这份 `model3.json`，**必须**：① 保留三位的署名；② **不得商用**；
  ③ 以 **相同协议（CC BY-NC-SA 4.0）** 发布；④ 注明修改内容（「补了表情声明与口型参数」）。
- 模型作者的无偿分享与转载授权**不解除**角色形象本身的 NC / SA 条件（`PROVENANCE.md` 原文）。
- 所以：**这份派生 `model3.json` 也要按 BY-NC-SA 4.0 走，不能只挂仓库的 MIT。**
  实施时请在 `pet/model/LICENSES/` 里追加一句派生说明（谁改的、改了什么、日期）。

---

## 7. 作者按键表里「已经定义、但我们还没实现」的反应

来源：`docs/作者按键表-对照.md`（**52 条热键逐条对照**）。我们目前只做了「7 个抽象状态 + 动作」，
下面这些**原作者定义了、A8Chann 实现了、我们还没做**：

### 7.1 一次性动作（11 个，`ACTIONS`）

| key | 名字 | 素材 | 时长 | 前置 |
|---|---|---|---|---|
| `paw` | 猫爪摆手 | motion `idle`（就是那个 Loop 动画） | **4400 ms** | — |
| `catPaw` | 喵喵手 | `catPaws` | 3000 ms | — |
| `doubleV` | 双手比耶 | `doubleV` | 2800 ms | — |
| `love` | 冒爱心 | `heartPop` | 3200 ms | — |
| `heartbeat` | 心跳 | `heartbeat` | 3200 ms | — |
| `squeeze` | MoeMoeQ~ | `squeeze` | 2600 ms | — |
| `eraser` | 橡皮擦 | `eraser` | 2600 ms | — |
| `undo` | 撤回 | `undo` | 2600 ms | — |
| `omurice` | 蛋包饭 | `omurice` + motion `ketchup` | **6200 ms** | — （挤完酱就消失） |
| `selfie` | 自拍 | motion `selfie` | 3600 ms | **掏出手机** |
| `selfieQuick` | 快速自拍 | motion `selfieQuick` | 2000 ms | **掏出手机** |
| `splash` | 鲸鱼喷水 | motion `splash` | 2200 ms | 左键点她时**随机** |

**永久不上**：`bubble` 吹泡泡糖（`chuipaopao`）、`aidale` 大锤砸。代码里要**双拦**（清单 + 播放入口）。

### 7.2 装饰（常驻，同类互斥）

四副眼镜 `glassesRound|glassesSquare|glassesOval|sunglasses`（组 `glasses`，只戴一副）·
三张贴纸 `stickerCat|stickerRabbit|stickerBow`（组 `sticker`，只贴一张）·
`sparkle` 情绪花花 · `ponytail` 单边马尾 · `headband` 发箍 · `whaleHat` 头顶鲸。
`sparkle` 与 `headband` 同属 `headwear`（头部），**互斥**。

### 7.3 场景（常驻）

`darkCloth` 深色桌布 · `whaleOnDesk` 鲸鱼放桌上 · `parfait` 桌面巴菲 ·
`claw` 粉魔爪 · `clawRecolor` 白魔爪（**前置 `claw`**）· 「掏出手机」（设备，无表情）·
`phoneRecolor` 手机换色（**前置 掏出手机**）。

### 7.4 表情菜单

原作者给了 **24 个表情热键**；A8Chann 按表情去重成 **16 个按钮**。
点一下演 **3~4 s** 然后自己让位，平常永远是平常脸。
**不上**：`blank` 呆呆眼、`dizzy` 晕晕（主人点名不要）。`drool` 闭眼口水**要保留**。

### 7.5 交互（我们完全没做）

| 交互 | 触发 | 默认反应 | 台词池 |
|---|---|---|---|
| 摸头 | 点在**头部**（含头发/耳朵） | `blush` / `question` / `starry` 随机（**不脸红**？原文：摸头=脸红系） | `SAY.head` 4 句 |
| 摸身体 | 点其它部位 | 气泡 | `SAY.body` 3 句 |
| 连点炸毛 | 快连点 | 递进：`ticklish`（痒）→ `SAY.many`（真生气） | 两档阈值，见 `pokeTier()` |

### 7.6 其它已定义未实现

`mood` 19 种（`neutral listening thinking happy excited love shy sad cry angry playful dizzy gloomy sweat confused alert sleepy tongue dead`）·
说话口型开关 · 视线跟随灵敏度 · 低性能档（`PERF.low`：不自言自语、不自己找戏、不打哈欠）·
右键钱包 HUD（余额 / 本轮消耗 / 峰谷 / 距切换）· 一键归位（含「停掉干活轮播」）。

---

## 8. 参考实现对照：两家怎么做的

| 问题 | Andersen216（我们的素材来源） | A8Chann |
|---|---|---|
| 反应由什么驱动 | **真实事件流**（`ctx.on('session/event')` + `agent/assistant-stream`），**不是轮播** | 同样订阅真实事件：`agent/status`、`tools/pre-execute|post-execute`、`approval/request`、`user-questions/request`、`subagent/start|end`、`agent/inbox/inserted`、`agent/turn-stopping`、`agent/error` |
| 抽象层 | 无相位，直接 `case 'tool-call'` 分支 | **8 个相位**：`thinking` `tool` `waiting` `asking` `helper` `queued` `done` `failed` |
| 反应配置 | `assets/pet.js` 顶部「性格表」硬编码（`MOOD_FACE` / `TOOL_REACT` / `TOOL_LINE`） | `pet.json` 数据驱动：20 个互斥槽位 + 每槽位带权重的条目表 |
| 「多久算久闲」 | 待机大脑 **3.5–7.5 s** 一次；哈欠 ≈ **99 s**；睡着 **180 s** | 摸鱼 = 静置一会儿后**每槽位各掷一次骰子**（权重即频率），阈值可配 |
| 占位/冲突 | 三层 `base`/`override`/`userProps` + 参数独占裁决 | **相位接管**：相位点名的槽位用它抽到的，没点名的一律让位；**装扮槽永远归用户** |
| 动作定格 | `openLid` + `hold` | `motionOptions.OpenCase.hold = true`、`Selfie.holdParams.phone5 = 10` |

**结论：两家的「反应」都是事件驱动的，没有任何一家用「定时随机」当主逻辑**（随机只在待机小动作里）。
所以我们的实现也必须以事件驱动为主，待机大脑只在 `idle` 时跑。

---

## 9. 交付物与参考文件

```
pet/REACTIONS-SPEC.md                      ← 本文
pet/model/_ref/
  c_0120.model3.patched.json               ← 可直接替换的补好表情声明的 model3.json
  expressions-names.json                   ← 只有 Expressions 数组
  expressions-names.tsv                    ← Name / File / 备注 / 原文件名
  verify/index.html                        ← 复现台：加载 patched 模型，逐个应用 44 个表情并读帧内参数
  verify/model3.json                       ← 复现台用的副本（路径加了 ../../ 前缀）
  verify/names.json
  verify/host/{run-bench.ps1, 4 个 WebView2 dll, wv2-proof.png, wv2-info.json}
```

复现台怎么跑（**纯 ASCII 脚本、不写 `renderer/`**）：

```powershell
powershell -NoProfile -File "F:\dsh-usage-widget\pet\model\_ref\verify\host\run-bench.ps1" `
  -X 80 -Y 60 -W 720 -H 640 -ClickThrough 1 -Hold 26 -Page model/_ref/verify/index.html
# 结果看同目录 wv2-proof.png
```

复现台读到的结果（本次实测）：`expressionManager: DEFINED` · `definitions: 44` ·
`accepted: 44/44` · `in-frame fingerprint changed: 44/44`。

上游参考（本次调研用的原文）在仓库外的 `F:\whale-chan-research\model\x\`（两家仓库的完整解包），
关键几份：`.../docs/作者按键表-对照.md`、`.../skill/SKILL.md`、`.../assets/pet.js`、
`.../lib/index.js`、`.../pets/ds-whale-girl/{pet.json,README.md}`。

---

## 10. 留给实现者的坑（都是我这次踩过的）

1. **读参数必须在帧内**。帧外读 `coreModel._model.parameters.values` 拿到的是引擎还原过的基线，
   会得出「44 个表情一个都没生效」的结论。要包 `coreModel.update`，在它**之后**取样。
   我第一次探针就是这么错的（`changed: 0/44`），改对之后才是 `44/44`。
2. **表情是淡入的**，`internalModel.update(dt, now)` 的第二个参数是**单调递增的毫秒**。
   用 `update(0, true)` 一次量到的是 t=0，什么都不会变。要连续推进 ~1.6 s。
3. **不要按名字读单个参数下断言**：`getParameterValueById('ParamCheek16')` 帧外读回 `0`。
   用整帧参数指纹（求和）才可靠。
4. **`idle.motion3.json` 不是待机动作**，它是「猫爪摆手 + 爱心」循环（`Meta.Loop = true`）。
   原作者把它停用了；我们的渲染器现在还在 `idle` 循环播，**整合时要停掉**，否则常驻卖萌。
5. **`aidale`（大锤砸）不能播**：它内部驱动 15 个表情参数（呆呆眼/哭/开心/晕晕/感叹号），
   一播就同时点亮好几个表情，看起来像「表情全乱了」。庆祝要用 `qBounce`（纯 CSS）而不是它。
6. **停动作必须 `stopMotion()` + `clearMotionPose()`**：框架每帧 `saveParameters → update → loadParameters`，
   快照是在动作写入之后存的；只 `stopMotion()` 不清姿势，动作最后一帧会被一直装回来
   （症状：手机收不回、蛋包饭永远挂桌上、一键重置也没用）。
7. **`jobs[].program` 不是工具名**：`bash` 的参数里有 `command` 时它返回内层程序名（`pwsh`/`node`）。
   要按工具分类，必须拿到 `tool/call.data.name`（见 §5.2 的建议 B）。
8. **`tool/result` 的成败信息在现有引擎里被丢掉了**（只用来移除未配对的 call）。
   「报错黑脸」这条反应**现在做不了**，必须先按 §5.2 选 A 或 B。
9. **PowerShell 5.1 读无 BOM 的 UTF-8 `.ps1` 会按 GBK 解**，中文注释会吞掉下一行；
   变量名大小写不敏感（`$Info` 和 `$info` 是同一个）。本目录 `.ps1` 一律**纯 ASCII**。
10. **含中文的 JSON 用 PS 5.1 读要显式 `-Encoding UTF8`**，否则 `ConvertFrom-Json` 会失败。

---

## 11. 与旧契约的差异（要同步改的文件）

| 文件 | 要改什么 |
|---|---|
| `pet/state.mjs` | 状态枚举换成 §2 的 11 个；`computeState()` 增加活动类别判定所需的输入（工具名、tool 成败、turn 结束原因） |
| `pet/STATE-PROTOCOL.md` | 状态表、色表、`pose` 表按 §2 / §3 更新；写明标签「定宽右对齐不抽动」 |
| `pet/state-cli.mjs` | 折叠逻辑要能把 `tool/call.data.name` 与 `tool/result.data.error` 带出来 |
| `pet/test/state.test.mjs` | 11 个状态的用例 + 优先级/回落用例 |
| `pet/renderer/state.json` | 形状不变（`state/label/color/detail/pose/reason/source`），值域换成新枚举 |
| `pet/model/c_0120.model3.json` | 按 §6.2 补 `Expressions` + 改 `LipSync` |
| `pet/model/LICENSES/` | 追加一句派生说明（改了 `model3.json`，BY-NC-SA 4.0，日期与人） |

`pose` 值域（供动作映射用，先只记录）：`offline` `sleepy` `team` `starry` `thinking`
`reading` `scribble` `sleeves` `happy` `gloomy` `idle`。

---

## 12. 实现记要（task-7 落地后回填，**含所有如实标注的缺口**）

> 实现者：`pet-integrate`（task-7）· 2026-09-30
> 这一节只记录**实际做成了什么、用什么替换了什么、哪一条没做**，不重复 §3/§4 的规格。

### 12.1 信号来源：走 §5.2 的「B：引擎透传」（lead 决策）

| 落地物 | 位置 | 说明 |
|---|---|---|
| `{"type":"tool",at,session,name,tool,phase:"call"\|"result",ok,error}` | `engine/activity.mjs` 折叠 + `engine/cli.mjs` 发出 | **纯追加**，每个新事件只发一次（`state.reported` 去重） |
| `{"type":"turn",at,session,phase:"start"\|"end",reason,ms,tokens}` | 同上 | 同上 |
| `jobs[].name` / `jobs[].tool` = **原样工具名** | `engine/activity.mjs` `buildJobs()` | `program` 仍是内层程序名（`pwsh`/`node`），分类用 `name`（§10 坑 7） |
| `pet/renderer/signals.json` | `engine/pet-state.mjs` `writeSignals()`（原子写） | 反应层的紧凑输入：`tool{name,phase,ok,error,summary,state}`、`turn{reason,ms,tokens}`、`streaming{active}`、`lastUserAt/lastUserText`、`idleMs`、`agents`、`jobs` |

实测（真实会话日志，25 个 artifact）：`tool/call` 1 192 条、`tool/result` 1 200 条（其中 **109 条带 `data.error`**）、`turn/end` 44 条、`user/message` 119 条。
面板对未知 `type` 的行为已实测：看板的 JSON 泵 `switch` 的 `default` 分支只在载荷**看着像快照**（含 `todayCny`/`totalCny`/… 之一）时才刷新页脚，`tool`/`turn` 两个字段集都不匹配 → **静默忽略，不弹消息条、不报错、不崩**。

### 12.2 与规格不同、或规格没写清的地方（逐条如实标注）

| # | 规格/上游说法 | 实现里的事实 | 处理 |
|---|---|---|---|
| 1 | `turn/end` 带 `ms`/`tokens` | 真实日志里 `turn/end.data` **只有 `{turn, reason:{kind}}`** | 引擎自己算：`ms` = 该回合 `turn/start`→`turn/end`；`tokens` = 该回合内 `assistant/message.data.usage.totalTokens` 求和 |
| 2 | `agent/assistant-stream` 逐 token delta | **日志里根本没有这类记录**（25 个 artifact 里 0 条） | 引擎只发「一个 assistant 步骤开着」（`step/start` 未配对 `step/end`）这个紧凑信号；**逐字冒字由页面自己按时间做**（lead 决策，成本≈0） |
| 3 | 「`掏出手机` + hold 定格」 | pixi-live2d-display 0.4.0 **没有 `hold`** | `reactions.js` 播 `openLid`，1.0 s 后在帧内抽样**全部参数**作为定格层，逐帧重写，直到换工具/超时（`clearDevice`） |
| 4 | 「眼镜 + 板子 + 笔」同时在场 | 框架的 `expressionManager` 一次**只能有一个表情** | 走 `beforeModelUpdate` 帧内钩子自己合成：把若干 `.exp3.json` 的参数集合并后写参（淡入自己插值）。这是唯一能同时戴眼镜+拿板子+拿笔的时机（§10 坑 1 的同一机制） |
| 5 | `奋笔疾书`（写文件） | **没有专属表情/动作**（§3.1 已注明） | 认真脸（`null`）+ 板子/笔道具 + 气泡台词「（奋笔疾书）写上了」等，**不伪造素材** |
| 6 | `挽袖子`（跑命令） | **没有专属表情/动作** | 同上：认真脸 + 道具 + 台词「（挽袖子）跑个命令试试」 |
| 7 | `走路般摆动`（作者按键表） | 素材里**没有对应动作** | **不实现**，不伪造 |
| 8 | 逐字口型 | `Groups[LipSync].Ids` 原来是 `[]` | 已补 `["ParamMouthOpenY"]`（§6），同时 `reactions.js` 自己也按 `sin` 写这个参数——两条路都通 |
| 9 | 摸头 / 摸身体 / 连点炸毛（**用户明确不要交互，故不做**） | 桌宠窗口按架构**天生鼠标穿透**（WebView2 `WS_EX_TRANSPARENT`），收不到点击 | **不做**，就是这一节 §7.5 的结论；不假装能做 |
| 10 | `peak` 峰时是一档状态 | lead 决策：峰谷是面板页脚的职责 | **从标签轮转里删掉**（§2 保留为可选第 12 档，不实现）；`snapshot.peakNow` 仍在，测试里显式断言它落到 `idle` |
| 11 | `ask_user_question` 是「error 档同级的等你」 | 11 个活动类别里**没有**「问你」这一档 | 归到 `thinking`（标签「想事情」），表情仍用 `question` + 台词「（歪头）这个得问问主人」 |
| 12 | `idle.motion3.json` 是待机循环 | 它其实是**猫爪摆手+爱心**（`Meta.Loop=true`），原作者已停用（§10 坑 4） | 页面**不再传 `idleMotionGroup`**（框架默认组名是 `Idle`，模型里没有 → 永不自动播），也不手动播 `idle` |
| 13 | `aidale` 大锤砸禁用 | — | **双拦**：`FORBIDDEN_MOTIONS = ['aidale','bubble']` 清单 + `PetAPI.playMotion()` 入口再拦一次；`verify-project.ps1` 断言 `reactions.js` 里不出现 `aidale` |
| 14 | `expressionManager` 拿不到表情 | `definitions` 其实是**数组**（下标 0..43），名字在每项的 `.Name` | 页面用 `definitions.map(d => d.Name)` 取名；用 `getExpressionIndex(name) > -1` 判存在（第一次探针用 `Object.keys()` 拿到 `"0".."43"`，是个坑） |

### 12.3 四个「反直觉事实」的落实证据

1. **`aidale` 永久禁用**：清单 + 播放入口双拦（`verify-project.ps1` 有硬检查）。
2. **`idle` 循环停用**：`pet-app.js` 不再传 `idleMotionGroup`；宿主探针里 `motionGroups` 仍列 8 组，但页面从不播 `idle`。
3. **`掏出手机` = `openLid` 定格**：`reactions.js` 的 `startDevice()/tickHeld()`（抽样→定格层→`clearDevice()` 释放）。
4. **无对应资产的三条**（奋笔疾书/挽袖子/走路般摆动）：见 §12.2 的 5-7，全部如实标注、不伪造。

### 12.4 元数据补丁与实测（§6 的执行结果）

`pet/model/c_0120.model3.json` 已替换为 `_ref/c_0120.model3.patched.json` 的内容（字节一致），
`FileReferences.Expressions` = **44** 条、每个文件都存在、`Motions` 仍是 8 组、`Groups[LipSync].Ids = ["ParamMouthOpenY"]`。
原文件备份为 `pet/model/c_0120.model3.json.bak-task7`。

**生产页面 + 生产模型**上的逐个实测（`?selftest=1`，走真实 ticker，帧内 `beforeModelUpdate` 取样，每个表情连续推进 1.6 s）：

```
expressionManager        DEFINED
definitions              44
model.expression(name)   accepted 44/44
in-frame fingerprint     changed 44/44   (delta -166.7 .. +413.0)
```

原始报告：`pet/host/task7-expression-selftest.json`（另有第一次用粗阈值 `>1` 的
`task7-expression-selftest-run1.json`：43/44 —— 唯一"没变化"的 `whaleOnDesk`
实际是 **+0.21**：它给 `fangzhuoshang` 加 1，而该参数已经接近上限被夹住，
所以阈值从 1 降到 0.05 后 44/44 全过。这个坑记在这里，免得下次又误判成"没生效"）。

### 12.5 授权（必须留档）

模型素材 **CC BY-NC-SA 4.0**（署名—非商业性使用—相同方式共享），版权归 **上善无形 / ZipZipPipe / 氵六青**。
本次补 `Expressions` 声明 + 改 `LipSync` 属于**对模型的改编**，因此 `pet/model/c_0120.model3.json`
是**派生作品**：个人 / 给朋友的小范围自用可以（用户已明确批准）；一旦对外分发**必须**
① 保留三位署名、② **不得商用**、③ 以相同协议（CC BY-NC-SA 4.0）发布、④ 注明修改内容。
**不能只挂仓库的 MIT。** 派生说明已追加到 `pet/model/LICENSES/`。

---

## 13. 上游能力补齐记要（task-10 回填）

> 实现者：`pet-integrate`（task-10）· 2026-09-30
> 依据：`pet/UPSTREAM-GAP.md` §4.2 的 P0 清单 + §5 的实现指南。**全程零新增素材**：
> 11 个一次性动作 / 7 个场景 / 11 个装饰全部由已声明的 44 个表情与 8 个动作驱动。

### 13.1 补了什么（位置：`pet/renderer/reactions.js`）

| 能力 | 实现 | 素材（短英文名） | 时长 | 与 11 档的关系 |
|---|---|---|---|---|
| 装饰 11 项 | `DECOR` 表：11 项各占一个 `slot`，**同 slot 自动互斥**；`userProps` 常驻层（最高优先级、不吃 TTL、`localStorage` 持久） | 4 眼镜 / 3 贴纸 / `sparkle`+`headband` / `ponytail`+`whaleHat` | 常驻 | **不改 11 档**：只叠在 base 之上；`exclusive` 时整体让位 |
| 场景 7 项 | `SCENES` 表 + `needs` 前置自动补齐 + 关前置时依赖项一起关（上游 `setProp 892` 的 group/needs/clears 语义） | `darkCloth`/`whaleOnDesk`/`parfait`/`claw`/`clawRecolor`(`needs:claw`)/`phone`(`openLid` 定格)/`phoneRecolor`(`needs:phone`) | 常驻 | 同上 |
| 一次性动作 11(+1) | `ACTIONS` 表 + `act()` 合成（先 `stopActing()` 归零 → 一个动作 + 一个表情 + 粒子脉冲），按上游时长记账，看门狗到点 `act-end` | `catPaws`/`doubleV`/`heartPop`/`heartbeat`/`squeeze`/`eraser`/`undo`/`omurice`+motion`ketchup`/motion`selfie`/motion`selfieQuick`/motion`splash`（另 `paw` 用的就是 `idle` 那一支，**只播一次 4 400 ms**） | 2 000–6 200 ms | override 层：脸按动作走，TTL 到期回落 base；`selfie*` 自动先掏手机 |
| `qBounce` | `qBounce()` + `index.html` 的 `@keyframes qbounce`（**只动画 canvas**，往下弹 5 px，不碰模型参数） | — | 500 ms | 只在 `celebrating` 触发（上游 `'turn-end'` 的 `qBounce(1.2)`） |
| P1 爱心脉冲 | `love`/`heartbeat` 的 `pulse`：480 ms 一次连上三次脸 | `heartPop`/`heartbeat` | 3 200 ms | 同 override 层 |
| P1 工作轮播 | 干活态（reading/writing/running/thinking/team）每 **9 000 + rand×5 000 ms** 重掷一次脸 | — | 9–14 s | 只重掷 base，不动 userProps |
| P1 低性能档 | `setLowPower(true)` → `ticker.maxFPS = 20` + 关待机大脑与工作轮播 | — | — | 与 11 档无关 |
| P1 `pickFresh` | 同一池子不连着抽同一句（上游 `pickFresh 502`） | — | — | 台词层 |
| P1 `userProps` 持久层 | `localStorage['dsh-live2d-pet:props']`（只存道具，位置仍由宿主给） | — | — | 优先级最高的常驻层 |

**入口**：没有鼠标（§4.1），所以用「事件驱动 + 参数通道」：`PetReactions.act(name)` /
`setProp(key,on)` / `setProps([...])` / `setLowPower(bool)` / `qBounce()`，
以及宿主侧的 `pet\host\force-state.json`（payload 支持 `act` / `props` / `lowPower`）。
`pet\host\gap-check.ps1` 会把 10 项能力逐个跑一遍并写
`pet\showcase\task10-gap-check.txt`（含帧内参数读数与层级快照）。

### 13.2 「待机到底还在不在播 `idle`？」——**实测结论：没有在播**

task-6 的盘点是针对 **task-7 之前**的代码（那时确实传了 `idleMotionGroup: 'idle'`）。
task-7 已经去掉那一行，本轮用**帧内参数取样**复核（`pet-watch` 通道，8 s，41 个样本）：

```
motionManager.groups.idle      = "Idle"        <- 框架 Cubism4MotionManager 的默认组名（大写 I）
model3.json 里的组             = "idle"        <- 大小写不同 -> 组不存在 -> 永不自动播
motionGroups 已加载的动作      = (空)          <- 没有任何动作被加载
playing / 队列长度             = false / 0
ParamArmLA / ParamArmRA 跨度   = 0 / 0          <- 「猫爪摆手」会动的两条手臂纹丝不动
ParamAngleX/Y/Z 跨度           = 15.0 / 8.0 / 10.0   <- 这些是框架内置的自然摆动 + 呼吸
ParamEyeLOpen/ROpen 跨度       = 1 / 1          <- 眨眼
```

结论：**待机没有循环动作**，可见的小幅摆动来自框架的 `updateNaturalMovements` 与视线
控制器，不是「猫爪+爱心」。所以**代码不需要改**，只把它变成硬检查：
`verify-project.ps1` 断言页面里不出现 `idleMotionGroup:`，并断言 gap 报告里
`playing=False` / `idleGroup=Idle`（§13.1 的 `paw` 是唯一的例外，且**只播一次**）。

### 13.3 `exclusive` 语义（第二个既有缺陷）

上游报错是 `props: []` **+ `exclusive: true`**（连本子笔都放下）。我们原来只是
「override 期间不挂它自己的 props」，**用户层的装饰/场景与定格的小设备仍会留着**。
现在 `exclusive: true` 的 override 会：① 不挂任何常态道具；② 不挂 `userProps`；
③ 把定格的小设备收起来（`clearDevice('exclusive')`）。
实测证据：`E1 tool error -> props:[] + exclusive` →
`override=[error(exclusive)] applied.props=[-] exclusive=[True]`（`userProps` 仍记着，事后自动恢复）。

### 13.4 踩坑：WebView2 会缓存 `pet.local` 的脚本

改完 `pet-app.js` / `reactions.js` 后重新拉起宿主，页面**仍然跑旧脚本**（新增的诊断字段
一直不出现），因为虚拟主机映射没有 `Cache-Control`。现在 `index.html` 的两个 `<script>`
都带缓存戳（`?v=12`）——**以后每次改这两个 JS 都要把数字 +1**，`verify-project.ps1`
也断言缓存戳存在。

### 13.5 仍然没做

- **P2/P3**：眨眼自控（动作期间不眨眼）、HUD 常驻小字、命名行气泡、诊断页升级、音效、配置统一 —— 均未做。
- **受架构限制的 12 项**（菜单 / HUD / 拖拽 / 戳她 / 视线跟随 / 贴边小球…）**一律不做**，
  也不留半成品按钮或死代码，等 §4.1 的宿主动作实验结论。
- `phone`/`claw` 这类"场景"目前只能由参数通道开关（没有鼠标入口），这是 §5.3 的务实取舍。

---

## 14. 交互层：**已按用户决定整体移除**（task-13）

用户明确表示**不要鼠标交互模组**，只要**动作与表情**。因此 task-11 的宿主实验与 task-12 的
十二项鼠标能力**全部删除**（宿主命中剪影与 1/255 网格、`PetAPI.mask/alphaAt`、右键菜单、
一键重置菜单项、贴边小球、滚轮缩放、戳她/分区命中/连击炸毛、拖拽+贴边+`pet-offset.json`、
视线跟随的 `GetCursorPos` 轮询、鼠标一动就醒），`verify-project.ps1` 里对应的检查也一并换成
**「整窗穿透」硬检查**。

理由：桌宠窗口本来**天生全程穿透、不挡用户点桌面**（`WS_EX_TRANSPARENT`），命中剪影那套
为了让鼠标点得到，把这条既定偏好破坏了 —— 得不偿失。现在 `-ClickThrough` 默认回到 1，
实测 11 个探测点（人物头/身、窗口中心、四角、四边中点）**全部落到下层窗口**，读数见
`pet/host/task13-passthrough.txt`。

保留并加固的是**动作与表情**那一层：§12/§13 的全部反应、装饰 11 / 场景 7 / 一次性动作 12 ——
它们继续**只由事件或参数通道驱动**，不提供任何鼠标入口。
