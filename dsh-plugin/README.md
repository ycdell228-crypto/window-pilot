# Window Pilot 的 DSH 原生插件

这是 DSH 支持的插件包和 bundle，复用 DSH 自带的 `@deepseek-ai/dsh-mcp-client`，在“插件 → 已安装插件”中显示 Window Pilot 名称和中文简介。无需新的浏览器客户端代码，也不增加 MCP 工具。

目前未发布到 npm。取得完整 Window Pilot 源码后，从项目根目录运行 `scripts/install-dsh-plugin.ps1`，先预览，再加 `-Apply` 安装。安装脚本自动使用当前项目路径和指定 Python，写入本机 profile 配置；不要只安装这个子目录而省略服务配置。外部 CLI 安装完成后，保存工作并退出、重开 DSH；本机 0.2.1-rc.3 仅刷新页面未加载新包。完整步骤见 [DSH 接入](../docs/DSH.md)。

bundle 包名为 `window-pilot-dsh`，唯一插件行 ID 为 `window-pilot-mcp`，MCP 命名空间仍为 `window_pilot`。安装会迁移本项目原有的通用 MCP 插入项，避免重复加载。原生卡片开关由 DSH 插件管理器提供：关闭后撤下该连接的工具，开启后建立新连接；旧 token/帧不恢复。

关闭卡片不停止、禁用或删除独立管理员服务，也不提升 DSH。无 HMR 的 profile 中，DSH 会提示需要重启；按其实际提示生效。当前包装没有新增输入策略或游戏流程。
