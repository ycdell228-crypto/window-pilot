# DSH 原生插件与 MCP 接入

DSH 原生插件继续使用本目录的共用 MCP 核心；Codex 直接使用标准 stdio，见 [CODEX](CODEX.md)。新版隔离开发期间不要运行本页的 `-Apply` 命令迁移原版生产插件，也不要把新版接到原版管理员服务。核心的文本/图片和调用规则适用于所有调用宿主。

## 推荐：安装原生 Window Pilot 卡片

项目提供 `dsh-plugin/` 原生包，包名 `window-pilot-dsh`，插件行 ID 仍为 `window-pilot-mcp`，MCP 命名空间仍为 `window_pilot`。在 DSH 的“插件 → 已安装插件”中，包通过 DSH 真实的 manifest/bundle 和导出 locale 元数据展示 **Window Pilot** 与中文简介，使用标准启用/禁用入口；不是给通用 MCP 改名，也没有单独重写 MCP 客户端。

需要完整项目、可用 Python 与 DSH。包声明 DSH >=0.2.1-rc.2；本次本机实际版本为 **0.2.1-rc.3**，其他版本需自行核验。当前包未发布到 npm，采用当前源码子目录的本地链接。安装不依赖作者的用户名、盘符或固定 Python 路径：

```powershell
Set-Location C:\your-project\window-pilot
# 默认只预览；Bridge 模式先要求已审查安装的管理员服务可连接。
.\scripts\install-dsh-plugin.ps1 -Python 'C:\your-python\python.exe'
# 实际安装：先校验服务和备份，再只迁移本插件并调用官方 DSH CLI 安装本地包。
.\scripts\install-dsh-plugin.ps1 -Python 'C:\your-python\python.exe' -Apply
```

管理员服务首次配置见 [ADMIN_SERVICE](ADMIN_SERVICE.md)。暂时只使用普通窗口时，可以显式加 `-Mode Direct`（先准备 config.local.json），此时 launch_app 仍被拒绝，不自动申请 UAC。可以用 `-Dsh` 指定 DSH CLI 路径，`-Profile` 指定已有 `DSH_HOME/profiles/<name>`；默认采用当前用户 desktop profile。脚本只为该子进程设置对应 DSH_HOME。

安装脚本备份 profile 的 package.json、cordis.patch.yml、现有锁文件和 workspace 设置到项目 `.local/backups/native-plugin-*/`，随后把本项目旧的独立 `insert` 迁成覆盖项，由原生 bundle 唯一提供插入行。调用官方 `dsh plugin --profile <name> add --save-prod --ignore-scripts --prefer-offline link:<当前项目>/dsh-plugin`，由 DSH 记录依赖并选中 bundle；优先缓存，既有依赖缺少解析元数据时允许包管理器获取元数据。已有其他依赖声明及已安装直接依赖版本在安装后重核；其他插件、模型及登录项不迁移。遇到复杂或重复的 Window Pilot 配置会停止，不猜测重写。CLI安装失败时，只在本插件 patch 未被并发修改的情况下恢复这次 patch 写入，并保留备份；不自动重复安装或覆盖其他配置，需要检查实际残留状态再处理。

脚本通过外部 CLI 安装后，先保存工作并退出、重新打开 DSH，再到“插件”页核验。本机 0.2.1-rc.3 实测仅重新进入页面或点击刷新没有加载新包，重开 DSH 后卡片及接入才出现。卡片来源为本地源码链接；名字来自 `locale/en.json`、`locale/zh.json` 的 meta.title，简介来自 meta.description。以后在原生管理器内操作开关时，按其实际应用或需要重启的提示处理。写入 package.json 不等同于运行时加载成功，须检查实际插件状态、13项工具及 health。

卡片关闭会撤销此 MCP 接入的工具并断开对应连接，开启会建立新连接；旧 token/帧不恢复，也不重放未完成操作。关闭卡片不会停止/禁用/删除独立管理员服务或其任务，不关闭已启动的用户程序，不提升整个 DSH。服务生命周期仍由 [管理员服务脚本](ADMIN_SERVICE.md#停止禁用卸载和恢复) 的明确操作控制。

插件包只复用 DSH 自带 `@deepseek-ai/dsh-mcp-client` 的 Config/inject/apply；没有新增工具、输入模式、前台操作或游戏业务。先确认只有一个 `window_pilot` 命名空间，再调用 health：管理员模式应报告实际 `executor.mode=administrator_service`、`is_administrator=true`。不要通过启动游戏来验收插件安装。

## 原通用 MCP 配置（不提供独立原生卡片）

配置格式以本机该版本安装包内 `@deepseek-ai/dsh-mcp-client` 的 README、lib/config schema，以及 `dsh-app-boot` 的补丁语义为依据，未套用其他客户端的 `mcpServers` JSON 格式。

以下是旧独立 MCP 接入方式。原生包已经负责 `insert`，安装原生包后不要再添加这份独立插入项。单独 `- id:` 只覆盖 bundle 已有 ID，因此原生卡片关闭时不会被 profile 覆盖项重新插入。

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

DSH 先进行 stdio 协议探测，再启动真实服务；initialize 返回 instructions 和工具能力，tools/list 当前共13项。支持本机 0.2.1-rc.2 客户端的 2026-07-28 及列明的旧版协议。普通直连服务使用项目锁；管理员执行端的每条连接独立持有 token/帧状态。

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

管理员执行端检测到源码或服务清单改变会自停，不热更新或自动重启。本次交付未代执行生产重启。已安装并启用管理员任务时，由操作方运行 `scripts/admin-service.ps1 -Action Start -Apply`，再让 DSH 只重连 window-pilot-mcp；无需重新安装任务或修改 DSH 配置。检查 tools/list 为13项，以及 health 的 executor.mode=administrator_service、executor.is_administrator=true、app_launch.enabled=true。普通直连模式则由客户端重启其 stdio 服务，但 launch_app 保持禁用。

更新/重连后旧 token 和帧失效，重新枚举并绑定；不重放旧操作，也不创建或恢复任何旧日常计划。移除接入时，备份后仅删除 window-pilot-mcp 插入项，不改其他插件。

管理员模式的DSH命令为 `python -m window_pilot bridge --service-file <项目>/.local/admin-service/service.json`，transport 仍为 stdio。实际执行端由单独预授权任务启动；不是给stdio命令加RunAs。`connect-admin-dsh.ps1` 默认只预览，显式 -Apply 才先验证真实高权限连接、备份并改本插件项。
