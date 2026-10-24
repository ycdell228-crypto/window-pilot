# DSH 0.2.1-rc.2 接入

配置格式以本机该版本安装包内 `@deepseek-ai/dsh-mcp-client` 的 README、lib/config schema，以及 `dsh-app-boot` 的补丁语义为依据，未套用其他客户端的 `mcpServers` JSON 格式。

新插件必须用顶层 `insert`；单独 `- id:` 只会覆盖已有 ID，不能插入新项。

```yaml
- insert:
    - id: window-pilot-mcp
      name: '@deepseek-ai/dsh-mcp-client'
      config:
        serverName: window_pilot
        transport: stdio
        command: 'C:\path\to\python.exe'
        args: ['-m', 'window_pilot', 'serve', '--config', 'C:\project\config.local.json']
        cwd: 'C:\project'
        env:
          PYTHONPATH: 'C:\project\src'
          PYTHONUTF8: '1'
          PYTHONUNBUFFERED: '1'
        toolCallTimeoutMs: 30000
        failOnStartupError: false
```

DSH 先进行 stdio 协议探测，再启动真实服务；initialize 返回 instructions 和工具能力，tools/list 当前共9项。支持本机 0.2.1-rc.2 客户端的 2026-07-28 及列明的旧版协议。普通直连服务使用项目锁；管理员执行端的每条连接独立持有 token/帧状态。

普通软件使用：`list_windows → bind_window(hwnd, access="observe_and_click", purpose="用户任务", capture_backend="wgc") → observe → click → observe`。绑定默认只读，明确允许点击后只覆盖该窗口/该服务会话，不需终端逐次确认。实际参数和边界见 [GENERIC_WINDOWS](GENERIC_WINDOWS.md)。DSH/宿主负责决策和调度；需要启动程序时使用通用 launch_app。插件没有游戏流程、日志任务监测或调度能力。管理员常驻模式通过普通stdio桥接入，见 [ADMIN_SERVICE](ADMIN_SERVICE.md)，不是提升整个DSH。

## 启动用户点名的程序

launch_app 只在已授权管理员执行端启用；普通直连模式虽然列出该工具，调用会报 ADMIN_EXECUTOR_REQUIRED，不临时提权或回退。无需应用白名单、登记或逐应用 UAC。以下示例仅说明参数，不会因阅读文档执行：

```json
{
  "exe": "C:\\Program Files\\Wuthering Waves\\launcher.exe",
  "args": [],
  "cwd": "C:\\Program Files\\Wuthering Waves",
  "request_id": "official-launcher-20261024-01",
  "purpose": "用户要求启动官方鸣潮启动器"
}
```

exe 必须是存在的本地绝对 .exe 路径；拒绝 UNC、网络盘、快捷方式和脚本路径。args 为最多128个字符串的数组，默认空数组；cwd 可省略，默认 exe 所在目录。purpose 必填；request_id 为1至64个 ASCII 字母、数字、下划线或连字符，用于一次启动的防重复回执，不是应用登记。shell=False 不解释 shell 命令串，但所选程序可以自行解释参数；在此授权下它以管理员权限执行，并非沙箱。

同一 ID 与相同参数再次调用只返回原回执，不创建新进程；相同 ID 换参数会报错。回复丢失、失败或结果未知时停止，禁止自动换新 ID 重试。一次新的、明确授权的启动才生成新 ID。回执的 PID/初始退出码只说明初始进程，启动器可能转交其他进程；需 list_windows 选择实际窗口、bind_window 后 observe 确认就绪。启动不会自动绑定、点击或关闭程序；程序可能自行激活窗口。

截图与通用授权仍失败即停，不回退、不重放。高于实际执行端的目标仍拒绝。普通模式不能自动提权；管理员模式须用户审查并安装后启用，不能提升DSH或改消息过滤。WGC 能截图不等于消息能输入。大图按 image_to_client_scale 从预览换算到原生客户区；图片不可读或客户端报告 unavailable 时停止，不用元数据冒充看图。

可选自有窗口验收提示词：

> 只用 window_pilot MCP。launch_test 后 list_windows，以返回 PID/类选择自有 fixture。bind_window 指定 access=observe_and_click、purpose=用户授权自有窗口验收、capture_backend=printwindow，然后 observe。只有实际看到图片和目标位置时，使用新帧在客户区 (40,40) click 一次，再 observe 证实计数。close_test 清理。任何错误停止，不补点击，不操作其他软件。

## 更新后重连

管理员执行端检测到源码或服务清单改变会自停，不热更新或自动重启。本次交付未代执行生产重启。已安装并启用管理员任务时，由操作方运行 `scripts/admin-service.ps1 -Action Start -Apply`，再让 DSH 只重连 window-pilot-mcp；无需重新安装任务或修改 DSH 配置。检查 tools/list 为9项，以及 health 的 executor.mode=administrator_service、executor.is_administrator=true、app_launch.enabled=true。普通直连模式则由客户端重启其 stdio 服务，但 launch_app 保持禁用。

更新/重连后旧 token 和帧失效，重新枚举并绑定；不重放旧操作，也不创建或恢复任何旧日常计划。移除接入时，备份后仅删除 window-pilot-mcp 插入项，不改其他插件。

管理员模式的DSH命令为 `python -m window_pilot bridge --service-file <项目>/.local/admin-service/service.json`，transport 仍为 stdio。实际执行端由单独预授权任务启动；不是给stdio命令加RunAs。`connect-admin-dsh.ps1` 默认只预览，显式 -Apply 才先验证真实高权限连接、备份并改本插件项。
