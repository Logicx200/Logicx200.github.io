# 重启并验证：用量面板接入**桌面版**

> 这份文档替换了早先面向 `dsh web`（npx 启动、3080 端口、`web` profile）的版本。
> 现在运行的是打包版桌面应用，它启动的是 `$DSH_HOME/profiles/desktop`。

## 现状：已经接进去了

插件已挂到 `profiles/desktop`，并且在**运行中的** GUI 里完成了热组合：

- host 行进入实时组合（`include:usage-dashboard`）
- `/api/usage-dashboard/stats` 返回 200 与真实账目
- 客户端 bundle 被注入，**没有刷新页面**，顶部操作区就出现了 chip

也就是说，"加一个 bundle 层必须重启"这个结论在 0.2.0-rc.2 上**已经不成立**。

## 那为什么还需要重启一次

只剩一个原因：**host 半区的源码改动不会热重载**。

Node 按解析后的 URL 缓存已导入的 ESM 模块，loader 既不重新导入、也不做
cache-busting。实测：改完 `src/session-store.mjs` 后，把 bundle 条目从
`dsh.profile.bundles` 里摘掉（路由变 404）再挂回（路由恢复 200），
`source.artifacts` 仍然停在 10 —— 跑的还是旧代码。

所以这次要重启，是为了让 v4 会话日志的读取修复生效（否则今日花费显示 $0.00）。

## 怎么做

双击 `RESTART.cmd`。它会：结束所有 `DeepSeek Harness.exe` 进程 → 重新拉起应用
→ 等 19387 端口就绪。

窗口会随之关闭，**本对话会中断**，这是预期的：会话记录都在磁盘上，重启后可以继续。

## 然后核对

```powershell
Set-Location 'F:\DeepSeek工作区\dsh-usage-dashboard'
node scripts\verify-live.mjs --url http://127.0.0.1:19387/ --log live-report.txt
```

期望看到：

```
ok    the plugin is composed into the boot manifest  (named in the boot manifest)
ok    the plugin client bundle is served  (… bytes at plugins/??dsh-usage-dashboard/client.js&rev=…)
ok    the stats route answers 200  (HTTP 200)
…
RESULT  all live checks passed
```

另外确认两点：

- `source.artifacts` 应该是 **11**（含今天写出的 `session.v4.jsonl.zstd`）
- 顶部 chip 的「今日」不再是 `$0.00`（当前量级约 `$0.08`）

## 不重启也能看数据

```powershell
node scripts\preview.mjs
```

纯文本报表，直接读会话日志，不依赖 GUI。v4 读取的修复在离线侧已经生效
（11 个会话，今日已计入）。

## 失败排查

| 现象 | 含义 | 处理 |
|---|---|---|
| `/api/...` 返回 401 | 签名 cookie 的有效期到 30 天会被拒 | 改成 29 天（两个 mint 脚本已改） |
| bundle 探针 404 | 探错了 URL：客户端模块不是按包路径单独提供的 | 真实 URL 在根文档的 `__DSH_BOOT__` 里，`verify-live.mjs` 已改为跟随 manifest |
| `duplicate loader entry id: usage-dashboard` | profile 的 `cordis.patch.yml` 又插了一遍该行 | 保持该行只由包自己的 `cordis.patch.yml` 提供 |
| 应用起不来 | — | 从开始菜单手动启动；必要时删掉 desktop profile `package.json` 里的 `"dsh-usage-dashboard"` 条目再启动 |
| `dsh --profile desktop` 报 managed exclusively | 桌面 profile 被 CLI 明确禁止操作 | 这是硬编码限制；要干跑就复制成另一个名字的 profile |
