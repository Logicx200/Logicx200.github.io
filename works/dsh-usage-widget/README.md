# DSH Usage Widget（旧版桌宠 / 用量挂件）

一个独立桌面小工具（非 DSH 插件）：右下角半透明悬浮窗实时显示 DeepSeek Harness 的 token 用量与花费，并内置一只 Live2D 桌宠（PowerShell/WPF + WebView2 宿主）。

## 怎么跑
- 入口：`powershell -NoProfile -File ui/widget.ps1`（部署路径需纯 ASCII）；
- 安装/卸载启动项：`powershell -NoProfile -File install-startup.ps1`（`-Uninstall` 移除）；
- 自检：`powershell -NoProfile -File verify-project.ps1`；配置见 `config.json`；工程说明见根目录 `README.md`。

## 结构
`engine/` Node 数据引擎（折算花费/余额，NDJSON 输出）；`pet/` 桌宠（Live2D 模型、WebView2 宿主、渲染页）；`ui/widget.ps1` 悬浮窗主程序。

## 说明
- 来源机器路径：`F:\dsh-usage-widget`；已排除 node_modules/dist/Electron 打包产物/WebView2 DLL 与测试截图帧（体积原因）。
- 依赖 Windows PowerShell 5.1、Node.js、WebView2 运行时；模型素材许可见 `pet/model/LICENSES/`。
