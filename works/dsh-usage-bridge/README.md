# dsh-usage-bridge

把 DeepSeek Harness 的**后台任务状态**镜像成一个 JSON 文件，供独立的桌面小组件（widget）读取并显示实时进度。

它只做一件事：**写文件**。

---

## 这是什么

DSH 本身已经维护了一个后台任务注册表（`ctx.jobs`），里面有任务 id、类型、标签、状态、`updateProgress()` 写入的进度行，以及一个**任务运行期间可读**的输出环形缓冲区。

这个插件订阅该注册表的事件，按固定周期用 `readAt()` 读取正在运行任务的输出尾部，从输出里解析出百分比与 ETA，然后把结果**原子地**写入一个 JSON 文件：

```
$DSH_HOME/usage-widget/jobs.json
```

桌面小组件读取这个文件即可，**完全不需要和 DSH 应用通信**——没有 HTTP、没有端口、没有鉴权。

---

## 纯 host 端，没有 client 半边

这一点是刻意设计的，也是它能保证“绝不会影响界面”的原因：

- `package.json` 中**没有** `dsh.client` 字段；
- 不提供任何浏览器端 bundle（没有 `lib/`，没有 `exports["./client"]`）；
- 不注册 Slot、不注册路由（route）、不注册工具（tool）、不注册 Service；
- `cordis.patch.yml` 只插入**一行** loader 记录。

因此浏览器端根本不知道它存在：加载这个插件唯一的可观测效果，就是某个文件里多了几个字节。

---

## 写出的文件

默认路径 `$DSH_HOME/usage-widget/jobs.json`（目录不存在会自动创建）。**加载后的第一个 tick 无条件写一次**，所以即使注册表里一个任务都没有，文件也会在 `intervalMs` 之内出现，内容是一个空信标：

```json
{ "at": 1790695900650, "jobs": [] }
```

这就是“桥接还活着吗”的答案：重启后看到 `{"at":…,"jobs":[]}`，即说明插件已加载并在正常走时钟。实际内容形如：

```json
{
  "at": 1790695900650,
  "jobs": [
    {
      "id": "bash-3",
      "kind": "bash",
      "label": "node sim.mjs",
      "owner": "session-…",
      "status": "running",
      "progress": "step 120/500",
      "detail": null,
      "percent": 24,
      "etaMs": 95000,
      "startedAt": 1790695900650,
      "finishedAt": null,
      "lastLine": "step 120/500"
    }
  ]
}
```

字段含义：

| 字段 | 含义 |
| --- | --- |
| `at` | 本次快照的写入时刻（毫秒时间戳），小组件可据此判断数据是否新鲜 |
| `id` / `kind` / `label` / `owner` | 直接来自注册表的任务身份 |
| `status` | `running` / `stopping` / `completed` / `killed` / `failed` |
| `progress` | 注册表自己的进度行（`JobHandle.updateProgress()` 写入），没有则为 `null` |
| `detail` | 终态说明（例如失败原因），没有则为 `null` |
| `percent` | 推导出的完成百分比，`0`–`100`；推导不出为 `null` |
| `etaMs` | 推导出的剩余毫秒数，已钳制在 **1 秒 ~ 7 天**；推导不出为 `null` |
| `startedAt` / `finishedAt` | 开始 / 结束时刻；未结束为 `null` |
| `lastLine` | 输出尾部的最后一条非空行，去空白、最长 160 字符 |

解析规则：

- `percent` 优先取注册表自己的 `progress` 字符串；没有时才从输出尾部解析。
- 支持的写法：`47.5%`（带百分号），以及 `step 120/500`、`120 | 500`、`120 of 500` 这类比例。
- 会做合理性校验：总数 ≤ 0 或 > 1e12 一律丢弃；百分比不在 `0`–`100` 内一律丢弃。
- `etaMs` 依据**最近两次采样**的速率（百分比/毫秒）推算，因此任务提速时 ETA 会变小，任务卡住时 ETA 会变大——而不是一直沿用历史平均速率。
- 已结束的任务会在文件里**保留约 30 秒**，让小组件能显示一次“完成”，随后自动移除。
- 写入是原子的：先写同目录下的临时文件，再 `rename` 覆盖目标文件，**小组件永远不会读到写了一半的文件**。

---

## 两个配置项

在 `cordis.patch.yml` 的 loader 记录里：

```yaml
- insert:
    - id: usage-bridge
      name: dsh-usage-bridge
      config:
        statePath: ""      # 空字符串 = 使用默认路径 $DSH_HOME/usage-widget/jobs.json
        intervalMs: 1000   # 读取与写盘的周期（毫秒），默认 1000
```

| 配置键 | 默认值 | 说明 |
| --- | --- | --- |
| `statePath` | `""`（空） | 空字符串表示用默认路径；填绝对路径可覆盖 |
| `intervalMs` | `1000` | 每隔多久读一次任务输出、并**最多**写一次文件。事件（注册/结束）会立刻触发一次写入 |

`$DSH_HOME` 的解析方式：环境变量 `DSH_HOME`；未设置时回退到 `~/.dsh`。这与其他 host 端插件在本机使用的约定保持一致。

---

## 卸载

1. 从 profile 的 `dsh.profile.bundles` 里删掉本 bundle 的记录；
2. 删除指向本目录的 junction / 链接（若当初是通过链接安装的）；
3. 可选：删除 `$DSH_HOME/usage-widget/jobs.json`（以及空的 `usage-widget` 目录）。

因为没有任何 client 半边，卸载后**不需要清理浏览器端资源**，刷新页面即可。

---

## `read` 为什么故意不调用

注册表提供两个读接口：

- `readAt(id, from)` —— 按**绝对字节偏移**读取，**不移动任何游标**；
- `read(id)` —— 从**模型自己的游标**消费，并把游标推进到当前末尾。

本插件**只使用 `readAt`，整个包里没有任何一处调用 `read`**。

原因是 `read` 会推进模型自己的读取游标——如果桥接插件调用了它，模型就会**失去对自己启动的任务输出的可见性**（输出被插件“偷走”了）。`readAt` 与模型游标互不干扰，两者读的是同一份字节。

这一点由离线检查强制保证：stub 里的 `read()` 被实现为**直接抛异常**，只要插件调用一次，检查就会失败。

环形缓冲是有界且可丢失的：如果注册表报告某次读取是 `lossy`（保留窗口已经从游标下方滑走），插件**不会**尝试补全缺口，而是直接把游标重新对齐到注册表返回的 `next`，然后继续读新输出。

---

## 离线自检

不需要启动 DSH，也不接触真实应用：

```powershell
& "C:\Users\x1503\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\node\bin\node.exe" test/bridge-check.mjs
```

`test/bridge-check.mjs` 用一个 **stub Cordis context** 驱动插件：伪造的 `ctx.jobs`（事件总线 + 输出环）、effect 注册器、被接管的进程级 `setInterval`/`clearInterval`、被捕获的 `console.error`，以及一个临时 `$DSH_HOME`。stub 的 context 是一个 **Proxy**，复刻 Cordis 自己的语义：除 `jobs` 和 `effect` 之外的任何属性读取都**直接抛异常**。它覆盖：

1. 注册的 running 任务出现在 `jobs.json`，且 `label` / `status` / `startedAt` 正确；
2. 环里喂 `step 120/500` 得到 `percent: 24`，喂 `47.5%` 得到 `percent: 47.5`；
3. 两个采样产生被钳制的 `etaMs`，且速率变化时 ETA 朝正确方向移动；
4. 已结束任务短暂保留后消失；
5. 读取抛异常时插件不死、且文件仍是合法 JSON（含 lossy 重同步）；
6. `read()` 从未被调用（stub 让它抛异常，检查依然通过）；
7. `$DSH_HOME` 解析正确，显式 `statePath` 覆盖默认路径；
8. 注册表不存在时 `apply()` 彻底惰性；
9. 注册表什么都没报告时，**第一个 tick 仍写出 `{"at":…,"jobs":[]}` 空信标**；
10. 插件从未读过 `jobs` / `effect` 之外的任何 ctx 属性。

---

## 设计取舍与已知风险

- **只声明它真正需要的东西**：`export const inject = ['jobs']`，然后直接读 `ctx.jobs`。Cordis 的 ctx 是一个 **proxy：读取任何既不是核心方法、又没在 `inject` 里声明的属性，GET 本身就会抛异常**（`?.` 也救不了，因为抛的是取属性这一步）。所以插件读取的 ctx 属性被压缩到恰好两个：`ctx.jobs`（服务）与 `ctx.effect`（核心方法）。注册表不存在时 Cordis 根本不会调用 `apply`，插件处于 pending 而不是 failed 状态。定时器用进程级 `setInterval`/`clearInterval`（`timer` 服务暴露的是 `ctx.interval`，不是 `ctx.setInterval`），并在同一个 `ctx.effect` 的 teardown 里清掉。日志走 `console.error`，从不碰 `ctx.logger`。
- **绝不向宿主抛异常**：订阅回调、定时器 tick、环读取、文件写入全部包在 try/catch 里；同类失败只记一条日志（防刷屏），插件继续运行。
- **文件写入是“发出即忘”的**：宿主事件永远不会等待磁盘。写入通过内部的 promise 队列**串行化**，避免两次并发 `rename` 以相反顺序落盘、导致旧状态覆盖新状态。
- **风险**：即使写入被串行化，磁盘上仍可能短暂看到“上一周期”的内容——这是有意的（widget 读的是快照，`at` 字段可用于判断新鲜度）。另外 `percent`/`etaMs` 是从**文本**里猜出来的：如果某个脚本输出了看起来像百分比、实际不是的数字，推导值就会失真。注册表自己的 `progress` 行始终优先，建议生产方用 `updateProgress()` 提供权威进度。
