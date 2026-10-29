# Window Pilot

面向 DSH、Codex 等宿主的 Windows 窗口自动化 MCP：提供指定程序启动、窗口枚举与精确绑定、窗口客户区截图、UIA 控件读取与操作、定向后台鼠标操作，以及显式授权的前台快捷键、Unicode 文字和拖拽。宿主在用户任务授权内观察、决定操作并确认实际效果。

**本机试用版本，采用 [MIT 许可证](LICENSE)。**

## 三项优化

- **公共说明更精简**：实际 MCP 初始化说明从 5555 减至 2102 字符，保留授权、观察和未知结果边界；这不是 token 计数或真实模型请求的节省比例。DSH 当前适配器把公共说明独立注册，不能按 13 项工具重复相乘。详见[说明精简与宿主边界](docs/OPTIMIZATION-1-TEXT.md)。
- **恢复步骤更集中**：`window_control(operation="prepare_recovery")` 获取操作权并准备新证据和后续调用建议。宿主审查效果后显式恢复，再新观察才能操作；准备不会自动清故障或重放输入。详见[恢复流程](docs/COORDINATION.md)。
- **外部输入时及时让路**：明确前台动作期间监听外部键鼠事件，检测后停止后续输入，并按精确左右键处理工具持有输入的释放与外部同键持有。不会吞事件、阻止人工输入或抢回焦点；同桌面仍有竞态。详见[前台输入与外部干预](docs/FOREGROUND.md)。

三项已逐项验收；验证范围与未覆盖项见[优化汇总](docs/OPTIMIZATION-SUMMARY-2026-10-29.md)。本次源码发布不代表你的本机服务已部署或重连。

## 工具

| 工具 | 用途 |
|---|---|
| health | 后端、绑定范围、故障摘要和自有测试窗口状态 |
| list_windows | 枚举可访问、可见、非最小化/非 cloaked 的应用顶层窗口 |
| bind_window / unbind_window | 绑定精确 HWND/PID/创建时间/路径/线程/窗口类及访问范围，或撤销 token |
| observe | 从绑定窗口自身捕获客户区，保存原图哈希并返回有界图片预览 |
| observe_controls | 只读 UIA 控件树：名称、类型、状态、层级、位置、支持模式及焦点标志；观察级控件 ID |
| window_control | 同一执行端内获取、续期、释放窗口操作权，查询状态；prepare_recovery 准备证据与恢复建议，recover 显式恢复 |
| control_action | 独立授权范围内按观察级 ID 执行一次 Invoke/SetValue/Select/Expand/Collapse/Scroll，随后重新观察 |
| click | 新鲜单次帧定向鼠标消息：默认左键一次；独立observe_and_mouse授权可右键、左键双击、双轴滚轮 |
| foreground_action | 独立前台授权下的真实激活/点击、快捷键、Unicode文字和有界拖拽；外部输入时停止后续输入 |
| launch_app | 在已授权管理员执行端启动用户点名的本地 .exe，返回启动回执 |
| launch_test / close_test | 仅启动/关闭项目自己的测试窗口 |

共13项工具。控件观察见 [UIA](docs/UIA.md)，观察级控件操作和明确的权限/焦点边界见 [UIA_ACTIONS](docs/UIA_ACTIONS.md)。旧游戏专用启动、日志监测、完成记录、串行关闭和 WW 专用代理已删除，不再有 click_helper。launch_app 为通用启动接口，没有应用白名单或登记；插件不提供游戏流程或日常调度。

右键、左键双击和上下左右滚轮的有界参数、子窗口路径、屏幕坐标与部分派发处理见 [MOUSE_ACTIONS](docs/MOUSE_ACTIONS.md)。原左键权限与默认调用保持兼容。

UIA提供方可能自行激活窗口；本机自有fixture已观测到操作期间目标成为前台。工具不调用SetFocus或前台回退，但不能承诺UIA操作全程留在后台，结果会报告桌面采样。

明确前台输入的授权、桌面门禁、焦点/保护检查和释放规则见 [FOREGROUND](docs/FOREGROUND.md)。自有fixture原生8项已通过，主对话已按WP-NEXT-005审查接受，本项与完成报告一并本地存档，提交可由决策记录历史核对。

## 管理员常驻模式

支持“普通权限调用宿主/stdio 桥 → 同用户同会话命名管道 → 管理员常驻执行端”，提供上述13项工具。由用户审查文件后单独执行一次安装UAC，通过交互式最高权限登录任务自启；不提升调用宿主、不恢复旧日常计划、不在每次点击或启动程序时提权。实际权限以 health.executor 为准。

安装预览、实际修改命令、停止/禁用/卸载与回退见 [ADMIN_SERVICE](docs/ADMIN_SERVICE.md)。源码更新不会自动安装、切换或重启本机服务；部署前先预览安装改动并核对自己的接入配置。

launch_app 接收本地绝对 exe 路径、字符串数组 args、可选 cwd（默认 exe 所在目录）、purpose 和唯一 request_id。普通直连 stdio 模式拒绝启动，不临时请求 UAC。参数通过 shell=False 传递；所选程序及其参数在管理员权限下执行，这不是执行沙箱，也不阻止用户明确要求的解释器程序。应用可能自行激活窗口，PID 或退出码不能证明应用已就绪。完整调用与重连步骤见 [DSH](docs/DSH.md)。

## 最短流程

```text
list_windows()
bind_window(hwnd=H, access="observe_and_click", purpose="用户本次任务", capture_backend="wgc")
window_control(target_id=T, operation="acquire", lease_seconds=60)
observe(target_id=T)
click(target_id=T, frame_id=F, x=X, y=Y)
observe(target_id=T)
window_control(target_id=T, operation="release")
unbind_window(target_id=T)
```

绑定默认只读；显式 observe_and_click 和 purpose 授权这一个窗口、这次服务会话，无需终端逐次批准。绑定须使用60秒内列出的身份，新 PID/替换窗口需重新选择，不从窗口内容推断授权。准确参数见 [GENERIC_WINDOWS](docs/GENERIC_WINDOWS.md)。

## 运行与宿主接入

需要交互式 Windows 10/11、Python 3.12+。基础 PrintWindow 无第三方依赖；WGC 需要 PyWinRT，较大图像预览需要 Pillow。通用配置只需：

```json
{"window_control":{"capture_backend":"wgc"}}
```

```powershell
if (-not (Test-Path config.local.json)) { Copy-Item config.example.json config.local.json }
python -m pip install --target .local/wgc-deps --upgrade --only-binary :all: -r requirements-wgc.txt
.\scripts\run.ps1 -Python 'C:\path\to\python.exe'
```

run.ps1 是 stdio MCP，应由客户端托管。Codex 的禁用状态配置预览、普通/bridge 模式、接入与回退见 [CODEX](docs/CODEX.md)；预览脚本不修改宿主配置或启动服务。

DSH 推荐使用原生插件包，让“已安装插件”显示 **Window Pilot** 名称、中文简介和启用/禁用入口：先运行 `scripts/install-dsh-plugin.ps1 -Python <路径>` 预览，再显式加 `-Apply` 安装；完整说明及普通/管理员模式见 [DSH](docs/DSH.md)。旧 register-dsh.ps1 只提供通用 MCP 接入，没有独立卡片；不要与原生包重复插入。旧配置中的游戏字段不再读取。管理员服务检测到 Python 源码或服务清单变更会自行停止；需要时启动现有已授权任务，再重连插件加载新版。

两种宿主复用相同的13项工具、初始化说明和标准 MCP text/image 内容，不需要 DSH 专属图片格式。普通直连同一配置目录只允许一个服务；管理员模式每条连接各有 token/帧，同一执行端共享持续窗口操作权、观察版本和未知故障门禁，调用方须先获取操作权再新观察；不同窗口可并行。独立执行端之间及人工输入不在此协调域，详见 [COORDINATION](docs/COORDINATION.md)。48 KB 预览上限继续保留。

## 边界

- 默认 WGC，可通过配置的 window_control 字段、绑定或单帧 observe 显式选择 wgc/printwindow。只从指定 HWND 自身捕获，失败直接报错；没有自动换后端、整屏/区域截图或前台回退。
- 被其他窗口遮挡仍可捕获目标自身内容；锁屏、隐藏/最小化、受保护内容或所有程序兼容性无保证，不自动还原。
- 原始 width/height、sha256 对应原生客户区 PNG。MCP 大图有界预览不超过48 KB；按 image_to_client_scale 换算坐标，不能用模糊文字猜按钮。
- 鼠标动作按授权向目标的同进程子窗口投递按钮/滚轮消息；仅对严格核验的 Static/WebView2 嵌入链允许跨进程接收，具体边界与审计见 [GENERIC_WINDOWS](docs/GENERIC_WINDOWS.md#嵌入-webview2-窗口)。已授权目标恰好在前台时仍使用同样的局部 PostMessage，后台click不主动切换前台、不移动真实鼠标、不注入键盘或调用激活；前台输入须另行显式授权。应用仍可能自行激活，不能替它作绝对保证。
- 高于实际执行端或无法核实权限时不发送点击。管理员模式可处理与执行端同级的管理员窗口，但不会按调用启动 UAC、提升 DSH 或改变消息过滤；普通模式仍保留原权限限制。截图成功不意味着消息可以输入。
- 普通鼠标和非目标前台变化只记诊断；身份、几何、边界、单次帧和部分派发仍严格检查。派发成功不等于效果，须新图确认；错误后停止该 token 输入，不自动重放或重新绑定抹掉错误。

## 状态与交付

当前仍为13项工具。三项优化的最终普通检查为27项通过、0失败，10个原生入口跳过，跳过不计为通过。恢复和外部干预的分项原生验证、历史失败及限制见[优化汇总](docs/OPTIMIZATION-SUMMARY-2026-10-29.md)与 [VALIDATION](docs/VALIDATION.md)。外部事件测试使用受控 SendInput，不代表真实人类硬件验收；真实宿主端到端输入、全部第三方/DPI/输入法兼容性及最终 token 收益仍未验证。

私有审计和原图保留在 .local/audit.jsonl、.local/frames/，启动回执保留在 .local/app-launches/，审计与回执不保存启动参数原文。同一 request_id 不重复创建进程，回复丢失或结果未知时禁止自动换新 ID 重试；新的明确启动任务才用新 ID。现有旧业务历史文件原样保留，不再被当前插件读取或恢复。未改原助手、系统设置、旧计划或项目记忆，未覆盖旧 ZIP。

源码、测试、运行/注册/打包脚本保留在对应目录。`scripts/package.ps1` 仅生成本地源码包，排除私有数据，已有 ZIP 会拒绝覆盖；不创建远端、提交或发布 GitHub。参考源码出处见 [NOTICE](NOTICE.md)。
