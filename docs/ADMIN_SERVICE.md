# 管理员常驻执行端：先审查，再由用户安装

```text
普通权限 DSH
  → 普通权限 stdio bridge（现有 @deepseek-ai/dsh-mcp-client）
  → 本机命名管道（Windows ACL + 实际 peer PID/SID/session 检查）
  → 当前用户、交互会话中的管理员 pythonw.exe 执行端
  → 9项接口：原8项窗口/自有测试工具 + launch_app
```

桥接端不执行截图/点击/程序启动，也不代签 UAC。管理员服务实际持有绑定、消费帧、执行 Win32 操作和明确请求的程序启动；health.executor 的 PID、exe、SID、session、integrity_rid 和 is_administrator 来自**执行端**。bridge 进程的权限不能替代验收。任务不是 SYSTEM、不是会话0；服务登录启动本身不启动用户程序或恢复任何日常计划。

## 首次用户操作

以下命令在用户自己的普通 PowerShell 运行，使用同一个当前登录的管理员账户；不要用另一个管理员账号的凭据代替。

```powershell
Set-Location 'C:\path\to\window-pilot'
$pilotPython = 'C:\path\to\python.exe'

# 只生成项目内审查文件，不注册任务、不启动服务、不请求UAC。
.\scripts\admin-service.ps1 -Action Plan -Python $pilotPython

# 只预览将对DSH自己的window-pilot-mcp项做的更改，不写配置。
.\scripts\connect-admin-dsh.ps1 -Mode Bridge -Python $pilotPython
```

先审查 `.local/admin-service/task.plan.xml` 和 `service.plan.json`。任务名固定为 `WindowPilot-WindowService-<用户与项目摘要>`：只在该用户登录后延迟10秒触发、InteractiveToken、HighestAvailable、无限运行时间、不因失败自动重启、不依赖电源/网络、不使用密码或 SYSTEM。Exec 只有同一运行时的 pythonw.exe 与绝对路径 runtime_entry.py，不是 shell。

确认这些文件后，**下面两条是实际修改命令，本轮没有代执行**：

```powershell
# 首次安装：这条会请求一次当前用户的UAC，写本项目服务清单/私有目录ACL，
# 注册并立即启动上述新任务。不会操作任何真实窗口。
.\scripts\admin-service.ps1 -Action Install -Python $pilotPython -Apply

# 只读连接/权限检查；不改任务/DSH配置，不截图或点击。
.\scripts\admin-service.ps1 -Action Status

# 确认实际高权限执行端连通后，才备份并只修改DSH的window-pilot-mcp项。
# 该脚本自己也先检查实际执行端；不通过就保持配置原样。
.\scripts\connect-admin-dsh.ps1 -Mode Bridge -Python $pilotPython -Apply
```

普通旧服务可以暂时与管理员端共存用于切换；新执行端使用独立锁。让 DSH 在空闲时只重连这个插件，确认 tools/list 为9项，然后调用 health。预期 `executor.mode=administrator_service`、`executor.is_administrator=true`、`app_launch.enabled=true`、实际 RID通常12288，`client_integrity_rid` 对普通桥通常8192。数值以实测为准；如果不是这些性质就停止，不能仅凭任务显示 Running 判通过。

## 以后如何启动

首次预授权后，以同一用户登录并进入交互桌面时，Windows 任务自动用最高可用权限启动这个窗口服务，不再每天或每个窗口询问 UAC。DSH 自身启动与否不影响服务；DSH 中只需普通 stdio bridge。服务无自动失败重启；断连、超时或丢失回复都不重发操作。

launch_app 使用现有管理员执行端，支持用户明确点名的任意本地 .exe；本次授权不设应用白名单或登记，不逐应用请求 UAC。参数为 exe、args 字符串数组、可选 cwd、purpose、唯一 request_id，示例见 [DSH](DSH.md#启动用户点名的程序)。进程通过 shell=False 创建，但所选程序及其参数有管理员执行能力，不能把它当作命令沙箱；DSH 仍须限定在用户任务内。普通直连 stdio 模式拒绝该工具。

启动前在 `.local/app-launches/` 持久化占用 request_id，同一 ID 不再创建第二个进程，跨连接及服务重启仍保留。回执与审计不保存参数原文；结果未知时不得自动换新 ID 重试。启动回执不保证应用就绪，可能出现初始进程退出或转交；DSH 需重新选择实际窗口并观察。该工具不自动绑定、点击或关闭应用，应用自身可能激活窗口。

源码或服务清单变化时，现有摘要检查会让服务自停。代码交付完成后，操作方启动已授权任务（`-Action Start -Apply`），再重连 DSH 插件并检查上述9项声明和实际权限；不需要重装任务或更改生产配置。旧 token/帧失效，不恢复未完成操作。

多用户/多RDP会话、锁屏、隐藏/最小化和受保护内容不保证可用；SID/session 不一致会拒绝连接，不能用会话0或其他桌面冒充当前桌面。任务在登录之后运行，不是未登录时的开机控制服务。这个登录自启与任何日常调度无关。

## 停止、禁用、卸载和恢复

```powershell
# 只读：查询这个任务以及真正执行端的health。
.\scripts\admin-service.ps1 -Action Status

# 停止本次服务（本机管道控制，无UAC）；不关闭绑定的用户软件。
# 下一次登录仍会启动；停止时在途操作可能结果未知，禁止重放。
.\scripts\admin-service.ps1 -Action Stop -Apply

# 手动重新启动已预授权且已启用的这个任务；不重发旧操作。
.\scripts\admin-service.ps1 -Action Start -Apply

# 禁用以阻止以后登录自启，并停止该服务；会请求管理这个任务的UAC。
.\scripts\admin-service.ps1 -Action Disable -Apply

# 重新启用以后登录自启；要当前启动，再执行上面的Start。
.\scripts\admin-service.ps1 -Action Enable -Apply

# 回退到普通权限旧stdio模式，只改本插件项并先备份；然后空闲时重连插件。
.\scripts\connect-admin-dsh.ps1 -Mode Direct -Python $pilotPython -Apply

# 卸载：禁用/停止/备份XML并注销本次任务；会请求UAC。
# 不删除审计、帧、原配置或本项目文件。
.\scripts\admin-service.ps1 -Action Uninstall -Apply
```

若 Windows 拒绝普通账户手动 Start，可由用户在同一账户的管理员 PowerShell 执行相同命令；登录自动启动不依赖该手动调用。Disable/Uninstall 的管道停止失败时，仅停止这个任务的进程，不按名称杀其他进程。安装升级会备份已有本项目任务/清单，拒绝覆盖同名的其他任务。恢复旧XML或迁移路径须先人工核对当前路径与账户，不自动导入旧计划。

DSH 配置备份位于 `.local/backups/cordis.patch.before-*.yml`；回退脚本只改此插件字段，比覆盖整份旧备份更适合保留其他插件的新变化。服务移动目录/Python更新前先卸载或重新审查安装，固定路径不会自行跟随。

## 保留的控制边界

- 管道只用 `\\.\pipe\WindowPilot.*`，拒绝远程客户端，显式ACL授予当前SID读写但不授予创建其他管道实例；管理员可创建服务实例。服务端再检查真实连接进程的SID/session，客户端检查真正服务PID、Python路径及高完整性。
- 普通桥只转发 initialize/ping/tools/list/tools/call；服务分发9项工具，新增通用 launch_app，仍无键盘、剪贴板或 UIA 输入接口。独立 CLI 的 stop 控制仅结束此服务。
- launch_app 明确接收用户点名的可执行路径、参数和工作目录，不接收执行端服务路径或修改服务配置。每条连接有独立临时token/帧/故障范围，实际操作串行；更新/重启/断连不恢复旧 token、未完成点击或测试会话。客户端不自动重连重发，也无低权限/截图后端回退。
- 精确身份、显式绑定授权、30秒新帧、单次消费、几何/坐标检查、点击后新图确认与部分派发证据都保留。默认使用同进程接收窗口；只对 [严格核验的 Static/WebView2 嵌入链](GENERIC_WINDOWS.md#嵌入-webview2-窗口) 允许同用户同会话、可证实进程亲缘的 WebView2 子进程。最终接收窗口与按下/松开状态写入审计；高于执行端或受保护的窗口仍可能拒绝。
- 源码、Python运行时和安装路径是用户信任的管理员程序；对它们的修改会影响之后的管理员执行。这是限定IPC接口，不是防御同一账户恶意改源码的安全沙箱。仅对本项目服务私有目录设置ACL，不改变UAC、消息过滤或系统全局策略。

## 本轮证据等级

本次 launch_app 交付只做语法、导入与9项工具参数声明检查；不实际启动用户程序，不执行模拟大套测试。没有代执行 UAC、任务注册、管理员服务重启、生产 DSH 配置修改或真实窗口操作。部署后的实际启动与权限由操作方验收，源码检查不能代替运行中执行端验证。

实现依据：[命名管道权限](https://learn.microsoft.com/en-us/windows/win32/ipc/named-pipe-security-and-access-rights)、[Task Scheduler schema](https://learn.microsoft.com/en-us/windows/win32/taskschd/task-scheduler-schema)、[无限执行时间PT0S](https://learn.microsoft.com/en-us/windows/win32/taskschd/taskschedulerschema-executiontimelimit-settingstype-element)。
