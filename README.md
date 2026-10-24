# Window Pilot

通用 Windows 后台窗口控制 MCP。DSH 负责在用户任务范围内观察、决定操作和调度；本插件提供指定程序启动、窗口枚举、精确绑定、定向客户区截图与后台左键点击。

**本机试用版本，采用 [MIT 许可证](LICENSE)。**

## 工具

| 工具 | 用途 |
|---|---|
| health | 后端、绑定范围、故障摘要和自有测试窗口状态 |
| list_windows | 枚举可访问、可见、非最小化/非 cloaked 的应用顶层窗口 |
| bind_window / unbind_window | 绑定精确 HWND/PID/创建时间/路径/线程/窗口类及访问范围，或撤销 token |
| observe | 从绑定窗口自身捕获客户区，保存原图哈希并返回有界图片预览 |
| click | 对明确授权窗口使用30秒内新鲜单次帧，定向投递左键消息 |
| launch_app | 在已授权管理员执行端启动用户点名的本地 .exe，返回启动回执 |
| launch_test / close_test | 仅启动/关闭项目自己的测试窗口 |

共9项工具。旧游戏专用启动、日志监测、完成记录、串行关闭和 WW 专用代理已删除，不再有 click_helper。launch_app 为通用启动接口，没有应用白名单或登记；插件不提供游戏流程或日常调度。

## 管理员常驻模式

支持“普通权限 DSH/stdio 桥 → 同用户同会话命名管道 → 管理员常驻执行端”，保留原8个工具并新增 launch_app。由用户审查文件后单独执行一次安装UAC，通过交互式最高权限登录任务自启；不提升 DSH、不恢复旧日常计划、不在每次点击或启动程序时提权。实际权限以 health.executor 为准。

安装预览、实际修改命令、停止/禁用/卸载与回退见 [ADMIN_SERVICE](docs/ADMIN_SERVICE.md)。本轮仅交付实现和必要检查，没有代安装、修改生产配置或启动高权限服务。

launch_app 接收本地绝对 exe 路径、字符串数组 args、可选 cwd（默认 exe 所在目录）、purpose 和唯一 request_id。普通直连 stdio 模式拒绝启动，不临时请求 UAC。参数通过 shell=False 传递；所选程序及其参数在管理员权限下执行，这不是执行沙箱，也不阻止用户明确要求的解释器程序。应用可能自行激活窗口，PID 或退出码不能证明应用已就绪。完整调用与重连步骤见 [DSH](docs/DSH.md)。

## 最短流程

```text
list_windows()
bind_window(hwnd=H, access="observe_and_click", purpose="用户本次任务", capture_backend="wgc")
observe(target_id=T)
click(target_id=T, frame_id=F, x=X, y=Y)
observe(target_id=T)
unbind_window(target_id=T)
```

绑定默认只读；显式 observe_and_click 和 purpose 授权这一个窗口、这次服务会话，无需终端逐次批准。绑定须使用60秒内列出的身份，新 PID/替换窗口需重新选择，不从窗口内容推断授权。准确参数见 [GENERIC_WINDOWS](docs/GENERIC_WINDOWS.md)。

## 运行与 DSH

需要交互式 Windows 10/11、Python 3.12+。基础 PrintWindow 无第三方依赖；WGC 需要 PyWinRT，较大图像预览需要 Pillow。通用配置只需：

```json
{"window_control":{"capture_backend":"wgc"}}
```

```powershell
if (-not (Test-Path config.local.json)) { Copy-Item config.example.json config.local.json }
python -m pip install --target .local/wgc-deps --upgrade --only-binary :all: -r requirements-wgc.txt
.\scripts\run.ps1 -Python 'C:\path\to\python.exe'
```

run.ps1 是 stdio MCP，应由客户端托管。接入 DSH 0.2.1-rc.2 的方式不变：`scripts/register-dsh.ps1 -Python <路径>`，详见 [DSH](docs/DSH.md)。旧配置中的游戏字段不再读取；本次交付未修改 config.local.json 或历史数据。管理员服务检测到源码变更会自行停止；需启动现有已授权任务，再重连插件加载新版。

## 边界

- 默认 WGC，可通过 window_control、绑定或单帧 observe 显式选择 wgc/printwindow。只从指定 HWND 自身捕获，失败直接报错；没有自动换后端、整屏/区域截图或前台回退。
- 被其他窗口遮挡仍可捕获目标自身内容；锁屏、隐藏/最小化、受保护内容或所有程序兼容性无保证，不自动还原。
- 原始 width/height、sha256 对应原生客户区 PNG。MCP 大图有界预览不超过48 KB；按 image_to_client_scale 换算坐标，不能用模糊文字猜按钮。
- 点击通常向目标的同进程子窗口投递左键消息；仅对严格核验的 Static/WebView2 嵌入链允许跨进程接收，具体边界与审计见 [GENERIC_WINDOWS](docs/GENERIC_WINDOWS.md#嵌入-webview2-窗口)。不移动真实鼠标、不注入键盘、不使用剪贴板/UIA或调用激活。目标已在前台时拒绝后台点击；应用仍可能自行激活，不能替它作绝对保证。
- 高于实际执行端或无法核实权限时不发送点击。管理员模式可处理与执行端同级的管理员窗口，但不会按调用启动 UAC、提升 DSH 或改变消息过滤；普通模式仍保留原权限限制。截图成功不意味着消息可以输入。
- 普通鼠标和非目标前台变化只记诊断；身份、几何、边界、单次帧和部分派发仍严格检查。派发成功不等于效果，须新图确认；错误后停止该 token 输入，不自动重放或重新绑定抹掉错误。

## 状态与交付

本次 launch_app 交付只做语法、导入与9项工具参数声明检查，不实际启动用户程序，不执行模拟大套测试。真实启动及窗口效果由用户验收。历史捕获证据见 [VALIDATION](docs/VALIDATION.md)，不能代表当前所有程序已适配。

私有审计和原图保留在 .local/audit.jsonl、.local/frames/，启动回执保留在 .local/app-launches/，审计与回执不保存启动参数原文。同一 request_id 不重复创建进程，回复丢失或结果未知时禁止自动换新 ID 重试；新的明确启动任务才用新 ID。现有旧业务历史文件原样保留，不再被当前插件读取或恢复。未改原助手、系统设置、旧计划或项目记忆，未覆盖旧 ZIP。

源码、测试、运行/注册/打包脚本保留在对应目录。`scripts/package.ps1` 仅生成本地源码包，排除私有数据，已有 ZIP 会拒绝覆盖；不创建远端、提交或发布 GitHub。参考源码出处见 [NOTICE](NOTICE.md)。
