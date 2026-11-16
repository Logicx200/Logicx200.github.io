# 红外仿真项目 · 实时进度看板

用于展示 **“红外目标探测大气参数化与成像效果评估”从阶段报告升级到正式报告**的全过程进度。页面为纯静态 HTML/CSS/JS，无 CDN、无外部字体、无第三方依赖，可离线使用；数据由同目录的 `progress.json` 驱动，每 **2 秒**自动拉取并在不刷新页面的情况下更新。

适用场景：长时间任务推进时挂在副屏/浏览器标签页上，随时查看总体完成度、各工作流进展、里程碑和实时日志，便于安排时间。

---

## 一、快速启动

### 1. 启动本地静态服务

在“进度看板”目录执行：

```powershell
Set-Location 'F:\DeepSeek工作区\红外目标探测仿真_整合交付_V2.1\06_进度看板'
python -m http.server 8766
```

或使用传统 CMD：

```bat
cd /d F:\DeepSeek工作区\红外目标探测仿真_整合交付_V2.1\06_进度看板
python -m http.server 8766
```

### 2. 打开页面

浏览器访问：

```
http://localhost:8766/
```

> 建议端口固定为 `8766`。若端口被占用，可改用 `8767` 等端口，但启动命令与浏览器地址需保持一致。
> 安全起见可只监听本机：`python -m http.server 8766 --bind 127.0.0.1`。
> 停止服务：在运行窗口按 `Ctrl + C`。

### 3. 实时写入进度

另开一个终端，仍在同一目录下执行（示例）：

```powershell
python update_progress.py --set extract 25 running "字段映射与参数基线表整理中"
python update_progress.py --overall 8 "参数解析推进"
python update_progress.py --log "参数基线表 v0.1 已完成第一轮核对" --level done
```

保存后无需手动刷新或按任何按钮，页面会在 2 秒内自动拉取新数据。顶部右上角会显示“实时同步 / 最后更新 / 上次同步”状态。

---

## 二、⚠️ file:// 打开限制（重要）

直接双击 `index.html` 时，地址栏是 `file:///...`。现代浏览器出于同源安全策略，会阻止页面 `fetch()` 读取同目录的 `progress.json`，因此 **无法实时刷新**。看板会显示友好提示；如果之前通过 HTTP 成功加载过，则可能回显 localStorage 缓存数据并明确标记为缓存。

**正确方式**：始终先用 `python -m http.server 8766` 启动本地服务，再访问 `http://localhost:8766/`。如果只是临时离线提交/归档，也可以将该目录放到任何静态服务器下，只要 `index.html` 与 `progress.json` 同级即可。

---

## 三、页面功能

| 区域 | 内容 |
|---|---|
| 顶部栏 | 项目标题、版本、实时同步状态、最后更新时间、上次同步时间、深浅主题切换按钮 |
| 总体区 | 环形总体进度、当前阶段、总体状态说明、预计完成时间与剩余时间、里程碑完成数、阶段报告 → 正式报告的阶段轨道 |
| 汇总区 | 进行中 / 已完成 / 受阻 / 待启动工作流计数、下一步关键动作、当前焦点 |
| 工作流卡片 | 7 条工作流：进度条、状态徽章、负责人、备注、产物文件；运行中工作流带动态指示 |
| 里程碑 | 垂直时间线，已完成节点、下一步节点、未完成节点；过期未完成节点会提示“待更新” |
| 实时日志 | 最近 30 条，最新在上；INFO / WARN / DONE 分级着色；底部可滚动 |
| 状态与容错 | 每 2 秒拉取一次；文件缺失、JSON 损坏、服务中断时显示中文提示，保留上次成功数据并自动重试 |
| 响应式 | 桌面、平板、手机自适应；支持系统“减少动态效果”设置 |
| 主题 | 深色专业风（默认）/ 浅色主题，选择记录在 localStorage |

刷新逻辑说明：

- 页面请求 `progress.json` 时带时间戳并设置 `no-store`，避免浏览器缓存旧数据；
- 内容未变化时不重绘 DOM；变化时平滑更新进度条并高亮新日志；
- 拉取失败时保留内存中的上次数据，同时写入 `localStorage` 的缓存也用于页面刷新后的回显；
- 顶部连接中断后仍会自动重试；服务恢复后无需刷新页面；
- 最后更新时间为 `progress.json` 内 `meta.updated_at`，上次同步为浏览器最近一次成功拉取时间。

---

## 四、文件说明

```text
进度看板/
├─ index.html          页面结构（内联 SVG 图标，无外部资源）
├─ style.css           深色/浅色主题、布局、响应式与动效
├─ dashboard.js        每 2 秒拉取 progress.json、渲染、缓存与容错
├─ progress.json       看板数据文件（由 update_progress.py 写入）
├─ update_progress.py  命令行更新工具（原子写、字段保留、日志/里程碑/工作流）
└─ README.md           本文件
```

页面不会引用任何外部 URL、CDN 或网络字体。

---

## 五、progress.json 数据结构

下面为结构示例（数值仅用于演示字段类型，当前实际数据见上一节快照）：

```json
{
  "meta": {
    "project": "红外目标探测大气参数化与成像效果评估",
    "version": "0.1.0",
    "updated_at": "2026-11-02 15:39:00",
    "stage": "参数解析与基线准备",
    "eta": "2026-11-06 18:00",
    "summary": "当前总体状态说明（可选扩展）",
    "focus": "当前焦点（可选扩展）",
    "next_action": "下一步关键动作（可选扩展）"
  },
  "overall": {
    "percent": 5,
    "label": "启动基线"
  },
  "workstreams": [
    {
      "id": "extract",
      "name": "软件参数解析",
      "percent": 10,
      "status": "running",
      "owner": "sim-extractor",
      "note": "当前工作流备注",
      "artifacts": [
        "软件参数提取/DefaultPlanFile_flat.json"
      ]
    }
  ],
  "milestones": [
    {
      "time": "2026-11-02 15:32",
      "title": "正式报告升级启动",
      "detail": "里程碑说明",
      "done": true
    }
  ],
  "log": [
    {
      "time": "2026-11-02 15:37:00",
      "level": "info",
      "text": "日志内容"
    }
  ]
}
```

字段约定：

- `meta`：必填对象。`project` / `version` / `updated_at` / `stage` / `eta` 为约定字段；`summary`、`focus`、`next_action` 为看板可选扩展，用于首屏说明与“下一步关键动作”。
- `overall`：必填对象。`percent` 为 0–100 的数字，`label` 为总体状态短标签。
- `workstreams`：必填数组。每条包含 `id`、`name`、`percent`、`status`、`owner`、`note`、`artifacts`。
  - `status` 只使用 `pending` / `running` / `done` / `blocked`，分别显示为待启动 / 进行中 / 已完成 / 受阻。
  - `artifacts` 中的文件路径只作为说明文字展示，不会自动转换成下载链接。
- `milestones`：数组，按时间线顺序排列；`done` 为布尔值。
- `log`：数组，按时间正序追加；页面仅展示最后 30 条并倒序显示（最新在上）。
- 看板与脚本均会保留额外字段，方便后续扩展；但顶层若缺失 `meta`、`overall`、`workstreams`，脚本会拒绝写入以防破坏文件。

当前数据快照（截至 `2026-11-02 15:46`，以 `progress.json` 实际内容为准）：

- 总体 **40%**，阶段“正式报告生成与看板部署”，预计完成 **2026-11-02 20:30**；
- `extract` 软件参数解析 **100% / done**，负责人 `sim-extractor`；
- 其余 6 条工作流均为 **running**：sensor 75%、atmos 65%、scenario 65%、sim 60%、report 55%、pdf 25%；
- 7 个里程碑，已完成 4 个；其中新增了“Q2 正式算例完成”；
- 11 条日志，最新为正式报告 v1.0 主体生成与 PDF 导出准备。

> 说明：初始化时曾写入一份总体 **5%** 的启动基线（`extract` 10% running、其余 pending），用于页面与自动刷新验收。随后执行端通过 `update_progress.py` 写入了真实推进数据，本看板当前保留并按 40% 的实时状态展示，不覆盖该更新。

---

## 六、update_progress.py 用法

先进入看板目录：

```powershell
Set-Location 'F:\DeepSeek工作区\红外目标探测仿真_整合交付_V2.1\06_进度看板'
```

### 1. 查看 / 帮助

```powershell
python update_progress.py --show
python update_progress.py --help
```

### 2. 更新工作流

```powershell
# 语法：--set ID PERCENT STATUS [NOTE]
python update_progress.py --set extract 35 running "正在核对字段映射表"
python update_progress.py --set extract 100 done "参数映射表 v1.0 已交付"
python update_progress.py --set sensor 5 blocked "等待探测器参数确认"
```

- `STATUS` 必须是 `pending` / `running` / `done` / `blocked`。
- `NOTE` 可省略；省略时保留原备注。
- 只修改指定字段，`owner`、`artifacts` 和未知扩展字段不变。
- 可一次更新多条（重复 `--set`）：

```powershell
python update_progress.py --set extract 100 done --set sensor 20 running "开始搭建像元与 MTF 模型"
```

### 3. 更新总体进度

```powershell
python update_progress.py --overall 8
python update_progress.py --overall 8 "参数解析推进"
```

省略 `LABEL` 时保留原标签。总体百分比由人工控制，不会根据工作流百分比自动加权计算。

### 4. 追加日志

```powershell
python update_progress.py --log "参数映射表 v0.1 已完成" --level info
python update_progress.py --log "传感器参数缺少文档，需要确认" --level warn
python update_progress.py --log "软件参数解析完成" --level done
```

- `--level`：`info` / `warn` / `done`，默认 `info`。
- 可一次追加多条（重复 `--log`）；同一批次共用同一个级别。

### 5. 新增 / 更新里程碑

```powershell
# 计划中的里程碑（done: false）
python update_progress.py --milestone "2026-11-06 18:00" "PDF 终稿交付" "完成 PDF 导出与校对"

# 标记该标题的里程碑为已完成（同标题会更新，不会重复新增）
python update_progress.py --milestone "2026-11-06 18:00" "PDF 终稿交付" --milestone-done
```

时间与标题也可以不加引号分开传：

```powershell
python update_progress.py --milestone 2026-11-06 18:00 "PDF 终稿交付" "完成校对" --milestone-done
```

脚本按 **标题** 做 upsert：相同标题更新时间和详情；未加 `--milestone-done` 时保留已有完成状态，新增项默认为未完成。

### 6. 更新 meta 字段

```powershell
python update_progress.py --meta stage "模型接入与工况扩充"
python update_progress.py --meta eta "2026-11-06 18:00" --meta version "0.2.0"
python update_progress.py --meta next_action "完成参数基线后启动传感器建模"
python update_progress.py --meta focus "参数映射表 v0.1"
```

`meta.updated_at` 会由脚本自动设置为执行时刻，无需手动维护。

### 7. 组合更新 + 预览 + 指定文件

```powershell
# 常见更新组合
python update_progress.py `
  --set extract 60 running "正在生成映射草案" `
  --overall 12 "参数解析阶段" `
  --log "参数解析推进到 60%" --level info

# 只预览，不写文件
python update_progress.py --set extract 70 running "预览一下" --dry-run

# 指定其他数据文件
python update_progress.py --file .\progress.backup.json --show
```

PowerShell 中如需换行，使用反引号 `` ` `` 续行；也可以写成单行。

### 安全写入机制

- 读取完整 JSON → 在内存中修改指定字段 → 写同目录临时文件 → `fsync` → `os.replace` 原子替换；
- 写入期间使用同目录 `progress.json.lock` 串行化并发更新（避免读-改-写丢更新）；异常退出留下的锁超过 45 秒会视为过期；
- JSON 非法、顶层结构缺失、工作流 ID 不存在、百分比越界、状态值非法时 **拒绝写入**，不会破坏现有文件；
- 未识别的字段全部保留，方便后续给 `meta` / 工作流扩展内容；
- 写入失败时会清理临时文件；页面因原子替换不会读到半截 JSON。

---

## 七、推荐工作流

1. 每次推进前先更新工作流和总体进度；
2. 用 `--log` 记录关键节点、风险和完成事件；
3. 里程碑完成时同步标记 `--milestone-done`；
4. 任务结束或需要交接时，更新 `meta.stage` / `meta.next_action` / `meta.eta`。

一条较完整的阶段更新示例：

```powershell
python update_progress.py `
  --set extract 100 done "参数基线表与字段清单已交付" `
  --set sensor 15 running "开始接入 NETD 与 MTF 参数" `
  --overall 20 "基线完成，进入模型接入" `
  --log "软件参数解析完成，正式报告进入模型接入阶段" --level done `
  --milestone "2026-11-03 18:00" "软件参数解析完成" --milestone-done `
  --meta stage "传感器与大气模型接入" `
  --meta next_action "完成传感器等效建模并启动大气数据接入"
```

---

## 八、注意事项 / 已知限制

- **必须通过 HTTP 打开**才能读取 `progress.json`；直接双击打开会受浏览器限制（见第二节）。
- 数据刷新是 2 秒轮询，不是 WebSocket 推送；对本地几百 KB 的 JSON 足够，但没有“即时推送”语义。浏览器后台标签页可能被节流，切回前台会立即补拉一次。
- 当本地服务停止或文件异常时，页面保留最后一次成功数据并显示错误提示；如果强制刷新页面，则依赖 localStorage 缓存回显，缓存时间可能早于最新文件。
- 页面与 `progress.json` 必须放在同一目录，且通过同一个 HTTP 服务访问；跨目录/跨端口读取会受同源策略限制。
- 工作流 owner 名称只是展示文本，不会自动创建子代理或分派任务。
- 更新工具不负责启动 HTTP 服务；需要先运行 `python -m http.server 8766`。
- 不支持通过脚本直接删除日志/里程碑；如需删除请手动编辑 `progress.json`，修改前建议保留一份副本。
- 页面使用现代 CSS（`color-mix`、CSS 变量、Grid）和原生 `fetch`；建议使用近期版本的 Edge / Chrome / Firefox。
- `python -m http.server` 默认监听所有网卡。若机器处于不可信网络，建议加 `--bind 127.0.0.1` 只允许本机访问。
- 端口/服务生命周期由使用者控制；若其他程序占用 8766，换端口并同步修改访问地址即可。

---

## 九、本地验证建议

```powershell
Set-Location 'F:\DeepSeek工作区\红外目标探测仿真_整合交付_V2.1\06_进度看板'

# 1) 校验数据与 CLI
python update_progress.py --show
node --check dashboard.js          # 已安装 Node.js 时可选
python -m py_compile update_progress.py

# 2) 启动服务
python -m http.server 8766 --bind 127.0.0.1

# 3) 另开终端检查 JSON 可访问并返回 200
Invoke-WebRequest http://127.0.0.1:8766/progress.json -UseBasicParsing |
  Select-Object StatusCode, Content
```

浏览器打开 `http://127.0.0.1:8766/` 后，可另开终端执行：

```powershell
python update_progress.py --log "页面自动刷新验证" --level info
```

观察页面是否在约 2 秒内更新日志与顶部“上次同步”。
