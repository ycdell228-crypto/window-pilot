> 历史记录：旧游戏专用接口、任务监测和管理员代理现已删除。本文保留当时捕获/输入证据，出现的旧接口名称不代表当前可调用；当前仅8项通用/自有测试工具，本轮没有重新实测真实窗口。

# 验证记录

事件日期：2026-10-23（Asia/Shanghai）。下列结果仅代表当时本机验收；版本和进程状态后续须重新核对。

## 结果分层

| 层级 | 结果与证据 |
|---|---|
| 静态设计 | HWND-only PrintWindow 与显式选用的 WGC；没有桌面/显示器捕获、屏幕拷贝、前台输入或键盘接口。默认 daily_authorized=false，助手输入哈希为空。 |
| 首次构建的本地测试 | 当时 15 项全部通过（0 跳过，约 9.65 秒）；点击遇桌面活动仍会锁定的旧策略已由下述局部修复替代，不能用首次测试声称并发点击可用。 |
| DSH 实际 MCP 往返 | DSH 0.2.1-rc.2 看到了被不透明窗口完全遮挡的测试目标，读出红/绿/蓝/黄背景与 clicks=0；依据原帧点击一次 (40,40)，再次看图及窗口标题确认 clicks=1，关闭测试成功。调用返回记录中前台 HWND 和鼠标坐标相同。 |
| ok-ww 只读预览 | DSH 观察到 OK-WW v3.7.6，客户区 1221×800，“截图方式”页面、游戏 Client-Win64-Shipping.exe 已断开；没有点击任何助手按钮。预览进程正常退出。 |
| ok-nte 只读预览 | DSH 观察到 ok-nte v1.4.16，客户区 1200×800，“截图方式”页面、HTGame.exe 已断开；没有点击任何助手按钮。预览进程正常退出。 |
| 原资产核对 | 8 份 `Daily*.json` 及 Basic Options.json 的前后 SHA-256 一致；最后核对无两款助手及配置的两款游戏进程残留。程序自身日志/缓存可能正常更新，不把 GUI 启动称为完全无文件副作用。 |
| 外部配置 | 仅 DSH cordis.patch.yml 新增 window-pilot MCP 插入项，原配置前缀字节保留，备份在本项目 .local/backups；未编辑原助手源码或日常设置。 |

## 已修复的验收问题

1. DSH 新插件需要 `insert`，已有 ID 才可直接覆盖。初次工具不可见后依据安装源码修正本项目新增项，真实调用随后成功。
2. 观察误把并发用户桌面活动当作失败。现改为仅记录前后桌面状态，捕获仍严格检查目标身份、尺寸和图像有效性；故用户浏览网页不影响 HWND 捕获。
3. 关闭消息已生效后，鼠标变化导致错误报告。现以窗口消失及精确进程退出确认关闭，不用鼠标静止作为关闭条件；重复预览收尾可核对“进程已退出”，不把错误解释成未发送消息。

首次实现曾在点击前后桌面状态变化时锁定输入；该做法不能区分用户操作与目标行为，现已撤换。变化只作无归因诊断，真正的目标/帧/投递错误仍失败并锁定，已投递消息不会重放。

## 点击并发活动误锁的局部修复（2026-10-23）

- 删除桌面快照差异触发点击错误的路径，未移除目标 HWND/PID/创建时间/路径/线程/窗口类、同进程子窗口、帧时效/单次使用、尺寸或坐标检查。按下和释放投递前复核身份，派发后继续核对目标及尺寸。
- 返回 `cursor_changed`、`foreground_changed`、`target_became_foreground` 和原因未知的诊断；正常用户活动不触发 `faulted`。目标在调用开始时已经处于前台的既有限制未改。
- 回归测试使用受控桌面快照驱动真实测试窗口点击，分别验证鼠标变化、非目标前台变化、两者同时变化及目标成为前台的诊断。另以受控失败注入验证 UIPI 拒绝、部分派发、屏障失败、目标/子窗口失效、越界及过期帧；这些是故障注入测试，不冒充真实系统权限故障。
- 最终本机回归：32 项全部通过，0 跳过，约 10.55 秒；该次原生点击也实际观测到鼠标坐标变化，未导致锁定。没有通过跳过并发点击用例掩盖错误。
- 用户明确配合的 25 秒真实并发验收：58 次有意安排、各用新帧的测试点击，58 次计数及图像变化均确认；32 次点击期间鼠标变化、2 次前台变化；实际前台进程包含 Chrome、ChatGPT 和 Explorer，目标未成为前台，`faulted=false`、`daily_authorized=false`，自有测试窗口已关闭。该记录使用真实 Win32 消息与桌面读数，没有模拟状态，不是遇错误后的自动重试。
- 独立确认 DSH 已加载修复：先 health 核对旧服务无活动阶段/预览/测试，按 PID、创建时间和完整命令行核对后仅重启本项目 MCP 子进程；未重启 DSH、未改 DSH 配置。DSH 重连后 health 返回新 `input_desktop_policy`，真实看图点击一次并重新观察计数 0→1；点击期间鼠标 [1102,887]→[1095,864]，`cursor_changed=true`、`faulted=false`，测试窗口正常关闭。消息投递与后续图像/标题效果分开确认。
- 本轮未启动助手或游戏、未解锁助手输入、未改助手配置、未恢复计划、未写项目记忆。原 `dist/window-pilot-0.1.0-source.zip` 不在本轮修改范围，未重打，仍是修复前的源代码包；如需交付新包，须另行确认。

## 尚未验收，不作已完成声明

- 与真实浏览器窗口逐一遮挡的专项测试：当前完全遮挡测试使用自有不透明窗口；这验证了目标图像不来自覆盖表面，未据此虚构浏览器专项操作记录。
- 两款助手的无害后台点击、与真实游戏连接后的行为。
- 两款游戏的 PrintWindow 同权限兼容性、异环的 WGC、启动器/子进程交接、真实游戏退出；鸣潮当前登录界面的 WGC 已通过下述只读验收。
- DSH 观察助手并开始实际日常、完成判定、真实 ww→nte 全流程。
- 助手内部是否会自关游戏/助手、是否会在运行日常时自行改变前台输入行为：现有配置未修改，须在获准验收前核对并提出冲突。
- 其他 DPI/多屏、UAC 完整性级别、最小化/锁屏/RDP、其他模型或 DSH 版本。

真实运行证据（审计、帧图片和本机配置哈希）只保存在被忽略的 `.local/`，不进入源代码包。无需将原聊天或诊断大文件复制到项目。

## 高完整性真实窗口截图修复（2026-10-23）

证据：MCP PID18832 为 medium（RID8192、未提升、Session1）；实际诊断捕获子进程也是 medium。同一次只读核验中的 ok-ww PID36492、鸣潮 PID37588 均为 high（RID12288、已提升、Session1）。目标身份分别为 HWND330624 / Qt6111QWindowIcon / ok-ww v3.7.9 China，HWND461740 / UnrealWindow / 鸣潮；这些只是当时快照。

调用 PrintWindow 前清零 LastError 后，两目标仍立即返回 0、last_error=5，因此本次拒绝访问并非旧错误残留。此前 v3.7.6 普通 GUI 的成功不能证明已更新且以管理员方式启动的 v3.7.9 可由同一路径捕获；未通过提升 PrintWindow 进程做对照，不能声称已单独证明或排除所有 Qt/GPU 兼容问题。

最小修复：保留 PrintWindow 路径并修正 LastError 采样/措辞；为 ww 显式选择 Windows Graphics Capture。WGC 仅 CreateForWindow(已验证HWND)，以本次会话开始后的帧时间、DWM 与客户区边界、前后身份/几何、黑帧校验把关；失败不自动换后端。依赖仅隔离安装到本项目 .local/wgc-deps，无 UAC、管理员启动、全局 Python 或 DSH 配置变更。本地 config.local.json 仅增加 ww.capture_backend，修改前已备份，所有日常/输入锁不变。

4 项直接相关回归通过：非法后端拒绝、目标图像客户区裁切、短缓冲/越界拒绝、WGC 失败不重试 PrintWindow。自有遮挡测试窗口的 NOACTIVATE 样式不被 WGC 接受；仅对该测试窗口调整捕获资格后验证了目标红色像素，恢复测试样式并关闭测试窗口，未调整真实窗口样式。按用户要求未反复扩大全套测试。

另一个独立阻塞是 DSH 的图片投递：鸣潮原生 PNG 约5.6 MB，已捕获但 DSH 提示 Maximum call stack size exceeded，模型并未看见。现保留原图并发送不超过48 KB的整幅 JPEG 预览、原生/预览尺寸和坐标比例；该修改不是屏幕或截图后端回退。中途助手被最小化时明确拒绝；用户自行还原后才验证，程序没有替用户还原。

最终实际验收由 DSH 通过 MCP 完成，每个窗口各 observe 一次：

| 目标 | 实际图片与尺寸 | 原始帧证据 |
|---|---|---|
| ok-ww v3.7.9 China | 1221×800；有界JPEG同尺寸；DSH读到“关于/应用更新”“已是最新版本”“更新成功 v3.7.6 -> v3.7.9”等文字 | frame cc20b24b7a4c7c88f97ec182；sha256 fd5fe334181451f51c7e890052508ec3cd780cf0839840f62dd5ea159886850c |
| 鸣潮 | 原图2560×1440、预览1280×720、坐标比例2；DSH读到“点击连接”及退出/公告/工具/账号/设置，确认登录界面 | frame 5b26da98c4df44e359da4185；sha256 65177e63ab0e4cdd957a8dcb291c10aded0d6e44883e1f75e624a0fe9c265fa4 |

两者 capture_method 均为 Windows.Graphics.Capture。仅在最新health确认空闲后按PID/创建时间/完整命令行重载项目MCP，DSH重连后实际看图；最终 daily_authorized=false、faulted=false、active/preview/fixture_pid=null。用户两个真实窗口均未被点击、输入、激活、移动、最小化或关闭；未执行日常，未修改助手源码/配置、计划、系统安全设置或项目记忆。

未支持/未验证：最小化、受保护内容、锁屏、HDR色彩精度、游戏内其他场景、任意高权限应用、助手后台输入及真实日常。WGC成功捕获不赋予 PostMessage 跨完整性输入权限；本轮不能据此声称高权限助手可被后台点击。旧源码ZIP未重打，仍不能当作修复后的版本。

## 新开发副本：双宿主 stdio 接入首项（2026-10-28）

范围为 `window-pilot-next` 的 `feat/dsh-codex`，从 `fde29e9` 继续；本节不重新验收原版运行状态。核心继续共用 Dispatcher，只有宿主提示文本和过时工具数说明调整；DSH 原生包未修改。新增 `scripts/preview-codex.py` 与 [Codex接入说明](CODEX.md)，只打印默认禁用的 direct/bridge TOML，不修改宿主配置。

- 环境：本机 Python 3.12.14；未安装新依赖。配置预览可被标准库 tomllib 解析，命令/cwd 均指向此副本，外部 direct 配置被拒绝；bridge 清单不存在时明确提示尚不可启用，不连接原版服务。
- 必要检查：`scripts/test.ps1 -Python <本机Python>` 退出0，报告 `Ran 25 tests`、`OK (skipped=2)`：24项通过，新的真实桌面用例跳过，另有旧 NativeTests 类在初始化时整体跳过。原因是普通沙箱 `GetForegroundWindow` 为空；不把跳过算作原生通过。通过项包含17项点击故障回归、4项后端回归、原协议检查及2项新配置/协议检查。
- 单独在可见交互桌面执行 `python -B -m unittest discover -s tests -p test_codex_stdio.py -k test_generated_direct_entry -v`，1/1通过。原样使用生成 TOML 的 command/args/cwd/env 启动新版普通 stdio；验证 2025-06-18 初始化、通知无多余响应、9项工具、标准文本/PNG内容、图片尺寸/哈希、fixture精确绑定、一次点击和后续新图/标题 `clicks=0 → clicks=1`。预设动作不重试，最后 unbind/close_test，health 确认 fixture_pid=null、faulted=false，stdio 子进程退出0。
- 另通过真实 stdio 初始化核对 DSH 使用的 2026-07-28 协议协商，原协议用例覆盖2025-03-26。保留的 `PROTOCOLS` 集合未扩展。它们是协议进程测试，不是 DSH 客户端新接入实测。
- 私有证据位于 `.local/validation/codex-stdio-20261028-214511/`：`stdio-before.png`、`stdio-after.png`，人工打开核对计数0→1；另保存 direct/bridge 禁用预览。媒体与本机路径配置均被 Git 忽略，`git diff --check` 通过。

尚未覆盖：Codex/DSH 客户端加载新版及模型实际图片交付、新版管理员 bridge/高完整性服务、WGC大图、旧 NativeTests 类、跨客户端流程互斥或帧失效协调。本轮不修改原版、全局宿主配置、服务、任务或记忆，不提交、不推送、不发布。首项待用户确认；后续UIA/更多输入未开始。

## 新开发副本：只读 UIA 控件观察（2026-10-28）

前项状态已推进：用户明确“首项已完成，继续做剩下的吧”，准备文件及双宿主首项已本地存档为 `abf56ba099c90cc46bcc663d03bd5b7204443fb2`，记录于 WP-NEXT-004；原“待确认/UIA未开始”属于上节交付时的历史状态。本项在该干净基线上实施，尚待用户验收，未再提交。

- 新增第10项工具 `observe_controls`。已绑定精确窗口的同进程 Control View 子树，返回名称、类型、状态、层级、屏幕/客户区物理矩形、支持模式和节点焦点标志，配合独立截图；只读绑定可用。控件ID绑定观察/窗口/连接；读取不执行控件动作，不查询全局焦点或桌面根，不读取 Value/Text 正文。
- 无新安装依赖。使用 Windows 自带的 .NET UIA 和 Windows PowerShell 独立 worker，默认64节点/深度5，上限128/8，6秒硬超时；身份/几何前后重核，异常丢弃部分树，跨进程子树明确跳过。新增worker纳入管理员源码摘要保护，修改worker能改变摘要的本地文件回归通过；未因此安装/运行管理员服务。
- 本机首次真实读取曾把原生 Button 报为 Pane；随后直接注册内置代理又出现空引用。现按“先取得精确根元素、再注册内置代理”的顺序修复。原生断言未放宽，最终读取的 Button/Edit 类型、Invoke声明、禁用状态、层级、客户区 x=16 位置均核对正确。
- 真实桌面 `python -B -m unittest discover -s tests -p test_uia.py -v` 的原生3项通过：只读树及fixture标题/焦点诊断、节点/深度截断与观察ID替换/非法限制拒绝、旧创建时间身份拒绝和真实独立worker强制超时。超时用1毫秒截止强制触发，证明父进程终止/返回路径，不等于实测失控UIA提供方。
- 真实 stdio 的 `test_codex_stdio.py -k test_generated_direct_entry` 1/1通过：10项工具、截图与控件树通过frame_id配对、fixture按钮存在，原有一次后台点击后新图/标题0→1，最后关闭fixture及stdio进程。UIA读取本身没有点击；PNG已打开核对新增原生控件与计数。截图与树仍非原子快照。
- 项目 `scripts/test.ps1 -Python <本机Python>` 最终退出0，报告 `Ran 26 tests, OK (skipped=3)`：25项通过；新stdio原生用例及UIA/旧NativeTests两个类在沙箱中因无交互桌面跳过。新UIA类及新stdio用例已按上文另行真实通过，旧NativeTests类仍未重跑，不宣称全部原生套件通过。
- 本地证据：`.local/validation/uia-20261028/uia-tree.json`（真实10节点树及桌面前后读数，fixture标题未变；该次前台与鼠标读数也未变）、`stdio-before.png`、`stdio-after.png`。证据已确认被Git忽略，不入源码或记忆索引；`git diff --check` 通过。

未覆盖：空树/不支持提供方的真实样本、UIA读取中途的实际进程替换、多屏DPI、受保护/高完整性窗口、多进程嵌入控件、新版管理员bridge、实际Codex/DSH加载。返回模式声明不是可执行或成功证明；没有按控件操作、前台键盘/文字/拖拽或跨连接流程互斥。本项到此交验，用户确认后才存档和继续。

## 观察级 UIA 控件操作（2026-10-28）

前项状态已推进：用户授权主对话逐项审查/验收与下发后续项（WP-NEXT-005）；主对话已接受只读UIA，该项与局部流程记录已存档为 `e2e86fa`。本节控件操作在该干净基线上实施，尚未提交，停在主对话审查点。

- 新增第11项工具 `control_action`，独立的 `observe_and_control` + purpose 授权。原只读与 `observe_and_click` 不授予UIA动作或全局键盘。支持 Invoke、SetValue、SelectionItem.Select、Expand/Collapse、Scroll，均为一次标准pattern调用，无前台/其他输入回退。
- 父进程及worker限制30秒观察和单次消费；保存原始有界树及runtime_id/名称哈希/层级/状态/几何，执行前重读比对并复核选定控件/祖先与根窗口精确身份、同用户同会话和权限。动作使同连接所有同窗口绑定的旧控件观察/截图失效。它不解决跨连接流程互斥；UIA最后检查与提供方调用之间仍存在竞态。
- 输入原文只经stdin，不进入命令行或审计。审计留value_length、动作与结果；错误码使用固定允许列表，不回传可能包含输入的提供方消息。未知结果封锁同窗口本连接输入，保留只读观察，不重放/自动重绑。6秒worker截止，提供方返回仍标记effect=unverified。
- 新建纯本地系统WPF fixture（`launch_test(kind="uia")`），原生fixture仍为默认。未安装依赖、运行用户程序或新管理员服务。新增worker/fixture脚本均纳入源码摘要保护。
- `python -B -m unittest discover -s tests -p test_uia_actions.py -v` 在交互桌面最终 **5/5通过，0失败**。真实正例分别确认按钮 `Invoked: 0→1`、SetValue精确界面回显、Option B选中且A取消、Expanded/Collapsed状态、纵向滚动 `0→30.434782608695652%`。每次都新观察确认，不把pattern声明或provider返回当效果。
- 同组拒绝检查覆盖旧ID及同观察其他ID、只读授权、禁用/密码/不支持对象、受控31秒龄期、实际窗口移动和同窗口原生按钮名称改变后的旧树。前台和鼠标状态采样只作诊断；正例实际观测过target_became_foreground=true，不能归因或承诺完整后台。
- 两项未知结果检查分别为真实worker在1毫秒截止被终止，以及真实Invoke已返回后受控注入一次桌面诊断失败；后者新观察仍见 `Invoked: 1`，两者均标记unknown并封锁输入。诊断失败和龄期为明确注入，非真实桌面故障/时间等待；没有测试失控第三方提供方的实际部分执行。
- 直接相关真实回归：`test_uia.py` **4/4通过**（其中3项原生，1项源码摘要文件回归），`test_codex_stdio.py -k test_generated_direct_entry` **1/1通过**，验证11项声明、截图/只读树、一次原生左键与新图0→1、关闭fixture及stdio进程。最终动作异常收尾改动由上述5项动作测试重跑确认；截图/左键代码未再变。
- `scripts/test.ps1 -Python <本机Python>` 最终退出0，`Ran 27 tests, OK (skipped=5)`：25项通过；新stdio/同窗口变更两用例及UIA/动作/旧NativeTests三个类因沙箱无交互桌面跳过。新原生部分已按上文另跑；旧NativeTests类仍未重跑。`git diff --check`通过。
- 私有证据 `.local/validation/uia-actions-20261028/uia-action-effects.json` 保存真实动作状态/桌面采样、拒绝码和未知结果检查；同目录的原生stdio前后PNG与UIA树保留，均Git忽略。测试合成输入的审计无原文由实际私有审计文件断言核对，临时审计随测试目录清理。

未验证：实际Codex/DSH接入、新版管理员bridge/高权限、多进程/游戏控件、全部UIA提供方兼容性、真实第三方挂死/部分执行、跨连接竞争。没有实施右键/双击/滚轮、前台键盘/文字/拖拽或操作权协调；这些仍逐项安排。原版与生产配置/服务/任务未动，本项未提交/推送/发布，项目记忆未写。

## 定向右键、左键双击与双轴滚轮（2026-10-28）

前项已由主对话按 WP-NEXT-005 审查接受，控件动作及 WP-NEXT-006 已本地存档为 `8a61360`；以上“未实施右键/双击/滚轮”是前项交付时的历史范围。本项在干净基线上开发，未提交，停在主对话审查点。

- 扩展现有click，工具总数仍11。默认action=left_click，原observe_and_click只允许左键一次；右键/左双击/双向滚轮要求显式observe_and_mouse与purpose。无全局鼠标、SendInput、SetFocus或SetForegroundWindow；原WebView2子窗口/进程链核验不变。
- 每组消费同窗口30秒内单次帧；逐条消息前与派发后重核身份、路由、权限和几何。滚轮是一条消息，steps非零整数[-10,10]、每步120；正向分别为上/右。lParam按根客户点转换为有符号屏幕坐标，非接收子窗口客户点。双击要求接收类CS_DBLCLKS，发送DOWN/UP/DBLCLK/UP并限制投递时间窗，不退成两个单击。
- 派发前审计保存完整计划及接收/坐标证据；逐条记录posted/not_posted/attempted（未知）。部分派发、屏障或后核验失败保留证据、封锁绑定输入，不补消息/重发/自动重绑。提供方效果仍unverified，须新图确认。
- 在交互桌面运行 `python -B -m unittest discover -s tests -p test_mouse_actions.py -v`，最终 **6/6通过**。自有WindowPilotMouseSurface子窗口独立记录右键计数与context=OPEN、single-down=2/double=1/releases=3（先单击再双击）、上下累计240→-120、左右累计120→-120。四向滚动均由真实新截图中的洋红viewport标记位移再次核对，不只读派发表或计数。
- 实际滚轮接收屏幕点样本为(409,238)，与子窗口客户点(40,40)不同；另移动自有fixture到负坐标，接收点(-391,238)与独立ClientToScreen结果一致，横向-120且新图变化。坐标/PID只是该轮自有fixture证据，不可当后续目标。
- 原生检查另涵盖无CS_DBLCLKS拒绝且不发消息、旧左键权限拒绝右键；受控将查询时间窗缩至1ms并延迟首次释放后，只收到第一单击、不发DBLCLK/回退；受控双击第四条释放失败时保留前三条posted、最后not_posted，实际releases=1/double=1；受控滚轮屏障失败时仍确认已收到120增量，绑定停输。均为显式注入，不冒充真实系统UIPI或挂死。
- 原有左键/过期帧/越界/身份/部分发送等17项故障回归继续通过，新增未知API返回注入1项，合计 **18/18通过**；未知尝试记录为attempted、input_sent=unknown且不重放。真实stdio `test_codex_stdio.py -k test_generated_direct_entry` **1/1通过**，原省略action的左键、图片及只读UIA配对、计数0→1和fixture/进程清理保持。
- 项目脚本 `scripts/test.ps1 -Python <本机Python>` 退出0，`Ran 28 tests, OK (skipped=6)`：26项通过；stdio/旧树变更两用例和鼠标/UIA/控件动作/旧NativeTests四类在沙箱无交互桌面而跳过。鼠标与stdio按上文另行真实通过，本轮没有重跑全部UIA动作/旧NativeTests原生套件，不声称全原生套件覆盖。
- 私有证据 `.local/validation/mouse-20261028/mouse-effects.json`、00-before/01至07-after PNG、负坐标与失败后的PNG等；已实际打开右键/双击截图核对独立状态。媒体与回执确认Git忽略，`git diff --check`通过。

未验证：真实WebView2的新鼠标动作、其他软件右键菜单/滚轮消费、高权限、真实Codex/DSH加载、所有多屏DPI布局/边界、真实生产断连或系统级部分发送。单个fixture不代表所有程序兼容；不自动切前台、改接收窗口或重试。本项未提交/推送/发布，不改原版、生产配置/服务/任务或项目记忆；前台键盘/文字/拖拽、跨连接协调仍未实施。


## 同一执行端跨连接窗口协调（2026-10-29）

暂停/恢复文档已由主对话接受，并本地存档为 `5c95357`（WP-NEXT-009）；鼠标项已存档为 `3b0ed5f`。以下协调实现仍未提交，交主对话审查；前台键盘、Unicode文字与拖拽尚未开始。

- 新增第12项工具 `window_control`，支持持续操作权获取/续期/释放/状态及凭新观察明确恢复。实际管理员连接工厂为每连接创建独立Service/Dispatcher，共享同一Coordinator；每窗口精确身份键、租期、epoch、在途标记和未知故障由执行端统一管理，不再用全局原生操作锁串行所有窗口。Direct私有域保留写绑定隐式持有的兼容路径。详细契约见 [COORDINATION](COORDINATION.md)。
- `python -B -m unittest discover -s tests -p test_coordination.py -v` 在交互桌面最终 **5/5通过，0失败**（12.419秒）。测试经生产连接工厂、独立连接上下文和真实自有原生fixture运行；未使用实际命名管道、管理员进程或真实宿主客户端，不称作IPC端到端测试。
- 争用/转交测试实际点击计数增加，所有连接旧截图及实际Button控件ID拒绝；特别在A仍持有操作权、尚未release时，B以旧frame_id调用observe_controls，已得到 `WINDOW_OBSERVATION_INVALIDATED`，证明输入本身使跨连接观察失效，而非仅转交造成失效。断连释放后同时获取只有一个胜者，胜者真实点击计数为1。
- 续期与在途测试中受控推进租期时钟/暂停原生动作：过期和disconnect均不能让另一连接接管在途窗口；另一真实窗口同时完成点击，证明窗口间不被全局动作锁阻塞。测试明确区分受控时间/暂停与实际窗口效果。
- 未知/部分输入通过受控注入触发，并以真实窗口效果及拒绝码核对；故障跨过期、重绑、断连和新连接保留。恢复须新持有者读取当前epoch证据并确认 `reviewed_effect_no_replay`，恢复后再新观察才能输入。未补发/重放旧动作；成功输入后尚未新观察即交还也保守锁存未审查故障。
- UIA同序列早先在默认和浅树均出现6秒超时，不能只归因深度。现观察/动作worker显式 `-MTA`，修正无窗口UIA线程依赖PowerShell默认STA的风险，符合微软UIA线程建议；WPF fixture仍STA。保留6秒界限、不加重试或前台回退。原worker增加固定阶段/apartment毫秒诊断，只有固定字段，不记录控件内容；超时结果也可保留最后阶段。
- 最终协调测试恢复原默认深度5/64节点及双截图后读取UIA的序列。最新私有证据阶段分别为script_start 7ms、assemblies_loaded 447ms、interop_compiled 764ms、root_resolved 1084ms、proxies_registered 1102ms、tree_read 1420ms，全为MTA，完整进程耗时2748ms。早期失败无阶段采样，故不能绝对证明每次超时的根因，也不声称所有负载/提供方稳定性已覆盖。
- 收尾审查修正失败UIA读取被错误当作输入后确认的边界：仅status=ok调用observe_end，失败仍检查epoch但不确认效果。新增真实worker受控1ms超时回归，实际先点击一次，再超时读取、释放/转交，确认未审查故障仍封锁输入；临时恢复旧缺陷时该断言明确失败，finally恢复修复源码。修复版本完整5项通过，普通项目命令也重新通过。
- MTA修正后、固定阶段诊断添加前，定向鼠标原生回归 **6/6**、UIA动作原生 **5/5**、真实stdio截图/UIA/默认左键回归 **1/1** 均通过。最终5项协调测试另覆盖了阶段诊断版本；以上不冒称同一时刻的一次全套运行。
- 项目命令 `scripts/test.ps1 -Python <本机Python>` 最终退出0，`Ran 28 tests, OK (skipped=7)`：26普通项通过、2个单项原生跳过，另5个类因沙箱无交互桌面在初始化跳过。相关原生项按上述单独运行，旧NativeTests仍未重跑。未为文档整理重复扩大测试。
- 私有证据 `.local/validation/coordination-20261029/coordination-effects.json` 保存五项效果、拒绝、注入边界及阶段数据，Git排除；超时调查副本/日志在 `.local/validation/coordination-uia-trace.*`，不入库。所有测试fixture已按执行记录关闭；`git diff --check`通过。

范围仅单个执行端的内存协调，容量有界，不跨独立执行端或重启持久化；不得以重启替代未知效果审查或恢复旧观察。人工输入不受该锁控制。未覆盖实际IPC/新版管理员部署/高权限、真实Codex或DSH客户端、多进程及第三方提供方兼容性；原版、生产配置/服务/任务保持隔离，未推送/发布、未写项目记忆。本项停在主对话审查点。


## 前台输入开发中，尚未验收（2026-10-29）

协调项已由主对话接受并本地存档为 `732ac3a`（WP-NEXT-010）。本节为后续前台项的**进行中记录**，不是功能通过或交验结论；当前改动未提交。

- 已接入第13项工具foreground_action、独立observe_and_foreground授权、现有共享窗口epoch/未知故障，以及前台独占桌面输入门禁。新增MTA安全焦点worker和WPF自有fixture，均受源码摘要保护。当前只完成代码/语法层检查，实际行为仍待验证。
- 本轮普通项目命令曾因协议用例工具集合仍为12而失败；更新为实际13项后，`scripts/test.ps1 -Python <本机Python>` 报 `Ran 28 tests, OK (skipped=8)`：26普通项通过、2单项及6个类的原生初始化跳过。该次记录早于后续前台输入修订，不作为最新全部原生或前台行为通过证明。
- 首次前台2项测试因fixture标题识别仍限定UIA名称，在launch_test阶段超时；随后修正按kind核对标题，并补setUp失败清理。另一次确曾读到foreground为空、GetCursorPos拒绝访问，测试类按桌面条件跳过；这仅是当时观察，不能解释后续所有失败。
- 后来沙箱外只读确认foreground_available=true、cursor_available=true，桌面恢复。随后的6项测试全部在setUp的activate失败，**是6项失败而非跳过**；单项进一步返回FOREGROUND_TARGET_OR_GEOMETRY_CHANGED。尚不能仅凭该合并错误断定SetForegroundWindow被OS拒绝或布局变化，因此新增独立激活诊断：SetForegroundWindow返回值、实际前台是否目标及客户区尺寸是否匹配；该诊断版本尚未实跑。
- 已改为支持明确的真实click通过命中窗口自然激活并放置焦点，不做后台回退。单项继续验证时，click前的安全探针得到FOREGROUND_PROTECTED_OR_UNVERIFIED_FOCUS，快捷键/Unicode正例尚未到达。随后将worker响应改为直接Console.WriteLine，避免循环管道输出缓冲的可能性；这是待验证修订，未确认其为上述失败根因。
- 用户随后选择“稍后再测”，本开发对话停止真实桌面输入验收；未反复尝试激活或向无关前台注入快捷键。当前仍待：中文/补充平面Unicode精确回显、Ctrl+A/Backspace实际效果、Thumb真实拖拽位移、密码/旧授权/失焦/物理已有输入拒绝、共享桌面争用、部分输入释放和总预算等关键路径。已编写相关原生用例，不把未通过或未执行当作覆盖。
- 代码总工作预算18秒，探针单次最多6秒并受剩余预算约束，另预留释放/关闭worker；Ctrl左右键别名与合法点操作焦点迁移已按静态风险修订。需后续实际验证释放与时限，不能仅据源码承诺25秒桥接范围已端到端证明。

当前源码及契约见 [FOREGROUND](FOREGROUND.md)；私有运行证据位于 `.local/validation/foreground-20261029/`，目前不是成功验收证据。原版、生产配置/服务、宿主接入及项目记忆未改；不推送发布，不提交本项，不安排自动唤醒。


### 前台探针的离桌面审查补充（2026-10-29，原生验收仍暂停）

- 确认新worker原来没有PMv2 DPI设置，而Python传入物理屏幕点；已在任何UIA查询之前设置SetProcessDpiAwarenessContext(-4)，失败即停止。该坐标一致性缺陷由源码对照确认，尚未证明是先前失败根因，也未实际验证缩放屏幕命中。
- 原父进程把请求写入、等待、EOF、JSON错误和worker拒绝合并为同一码，历史记录无法定位准确UIA阶段。现仅保留固定transport阶段及worker阶段/apartment，不返回提供方原文；root PID/HWND在读取point/focus前重核，提供方注册改为每个worker首次初始化一次，祖先链仍须到达精确root且全程同进程、非密码。
- 无桌面查询的管道检查：把诊断副本中FromHandle所在行替换为主动throw，确保在调用任何窗口/point/focus/祖先API之前退出。实际Windows PowerShell MTA、真实Popen管道、保持stdin不关闭，连续两次JSON往返均被父进程精确识别为worker_rejected/root_resolve；首项3375ms、后项0ms。PMv2初始化阶段通过；这只证明启动/编译/协议/固定阶段传递，不证明UIA目标读取可用。
- 对照把相同诊断副本的WriteLine恢复为原管道ConvertTo-Json，同样在stdin保持打开时得到两次响应，3094ms/0ms。因此没有证据把原生失败归因于管道输出缓冲，保留为未证假设；不把Console.WriteLine改动称为已修复原生根因。
- PowerShell脚本语法解析通过，git diff --check通过。尚未运行带新阶段码的真实fixture探针；先前失败的准确root/point/focus/ancestor阶段仍未知，待用户授权恢复桌面验收后采样。
- activate文档已与代码对齐：它只复核激活返回/实际前台/几何/身份，不证明安全输入焦点；后续点击或键盘/文字/拖拽各自重新检查，不因激活成功继承输入资格。


### 等待桌面恢复前的最终非交互检查（2026-10-29）

明确设置 `$env:CI='1'; $env:WINDOW_PILOT_NATIVE_TESTS='0'` 后执行 `scripts/test.ps1 -Python C:\Users\33482\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe`，退出0，`Ran 28 tests in 1.330s, OK (skipped=8)`：26普通项通过、2个单项与6个类原生初始化跳过，0失败。前台新测试已遵守与既有原生测试相同的CI门禁，本次没有创建测试窗口或注入输入，不把跳过算作前台通过。固定阶段码离桌面检查范围仅到主动停止的root_resolve，point/focus/祖先链和真实效果仍未验收。PowerShell语法解析及git diff --check通过；当前仍停在等待用户恢复真实桌面验收的位置。


## 前台输入恢复后的最终原生验收（2026-10-29）

用户在主对话明确选择“现在可以，继续测试”，替代此前“稍后再测”。以下结果推进上述进行中状态，保留原失败记录；本项仍未提交，待主对话审查。

- 恢复后单项先得到FOREGROUND_POINT_OCCLUDED，确认那次失败发生于真实点命中被遮挡，输入被拒绝。仅为前台专用自有fixture增加Topmost可见性，仍ShowActivated=false；没有修改任何用户窗口或放宽生产遮挡检查。随后Unicode单项1/1通过（18.983秒）。早先无阶段记录的PROTECTED_OR_UNVERIFIED失败仍不可绝对归因；DPI、固定阶段诊断和初始化修正后不再复现，不能把某一修正独称已证根因。
- 完整原生前台测试最初6/6通过（68.198秒）。主审指出原失焦注入按内部次数耦合后，已替换为真正fixture焦点迁移，并增加已有键状态与剩余预算检查。最终命令 `python -B -m unittest discover -s tests -p test_foreground.py -v` 在真实桌面 **8/8通过、0失败、0跳过**（98.235秒）。经实际生产连接工厂、独立Service和共享Coordinator运行，不是实际IPC/管理员服务/真实宿主端到端。
- Ctrl+A后KEYEVENTF_UNICODE精确回显“中文验收 Ω 😀”，含中文和补充平面字符；再次Ctrl+A与Backspace实际清空。私有审计断言确认文字和按键序列原文不在日志。拖拽使真实WPF Thumb从Canvas x40移动到x160，独立UIA状态为Drag x:160，并核对实际控件矩形位移120像素及按钮释放；不是仅SendInput返回成功。
- 真实失焦：明确点击fixture的arm按钮，再拖拽；fixture在真实DragStarted时将焦点移到本窗空PasswordBox。工具实际UIA安全检查拒绝并停输，测试确认PasswordBox的has_keyboard_focus=true、前台仍为精确fixture、鼠标左键已释放。取代原按第12次native_focus抛错的测试；早期模拟记录不冒充当前真实迁移。
- 已有按键：测试先实际注入Ctrl按下形成已有OS状态，输入调用明确拒绝且Ctrl仍保持按下、编辑回显不变；测试finally再释放。该状态为受控合成，不冒称人工键盘硬件事件。预算：生产默认18秒，受控改为5秒，并在实际Ctrl按下后真实等待至剩余预算耗尽；5313ms内返回unknown，Ctrl释放、编辑回显未变。没有模拟monotonic，不宣称实际25秒bridge端到端或所有OS调用硬截止已证明。
- 其他直接检查：4种旧授权拒绝前台动作、旧帧拒绝、密码点/密码焦点文字拒绝、另一窗口后台输入在前台门禁中拒绝及释放后实际clicks=1、后台在途时前台拒绝、受控第二次SendInput失败后释放Ctrl且共享故障跨断连保留。部分注入失败为明确注入，非真实系统随机故障；无重放。
- 完整8项证据 `.local/validation/foreground-20261029/foreground-effects.json`，单独截图正例保存在screenshots子目录，不覆盖完整8项回执。图像是自有fixture，继续Git排除。当前没有为文档更新重复所有旧原生套件。

仍未覆盖：真实Codex/DSH加载、实际命名管道/管理员部署/高权限、第三方/游戏/自绘/跨进程控件、所有缩放/多屏布局与输入法、失控第三方UIA提供方、人工与注入同键重合的全部竞态。真实桌面资源跨独立执行端没有共享锁；最后检查与OS注入之间仍有竞态。原版、生产配置/服务/宿主接入、项目记忆未改，不推送发布。


### 最终交主审前回归与截图

- 仅为保留实际效果图，运行 `python -B -m unittest discover -s tests -p test_foreground.py -k unicode -k drag_changes -v`，2/2通过（28.617秒）；未重跑全部8项。截图直接复制对应observe的原生PNG，分别为 `.local/validation/foreground-20261029/screenshots/unicode-after.png` 与 `drag-after.png`，已打开核对中文/Ω/emoji及Echo相同、Thumb移动及Drag x:160。该两项回执在screenshots子目录，完整8项JSON不被覆盖。
- 共享gate直接相关协调回归命令 `python -B -m unittest discover -s tests -p test_coordination.py -v`，5/5通过（7.131秒）。证据独立保存在 `.local/validation/foreground-20261029/coordination-regression/`，未覆盖先前协调验收回执。
- 最新普通检查明确禁用原生：`$env:CI='1'; $env:WINDOW_PILOT_NATIVE_TESTS='0'; scripts/test.ps1 -Python <本机Python>`，`Ran 28 tests in 0.543s, OK (skipped=8)`，26普通项通过、2个原生单项及6个类初始化跳过、0失败。此后仅health说明文字与本验证文档补齐，原生动作逻辑未再改变；不为文档整理重复旧原生套件。
- git diff --check通过。PNG、JSON回执确认Git排除，暂存区为空；未新增Git提交，HEAD仍732ac3a。当前功能交主对话审查，尚未将该项写入验收决定或存档。


### 主对话最终接受（2026-10-29）

主对话按WP-NEXT-005核对最终8项原生、5项协调、普通26项通过/8个跳过入口及两张实际截图与当前源码，明确接受前台项。WP-NEXT-011记录用户恢复桌面授权、接受结论、存档范围及限制。本条推进以上“待主审”历史快照，不改写失败或暂缓事实。当前达到约定标准，停止扩展；等待主对话完成报告落盘后一次本地存档，不因验收文档重跑原生，不推送/发布/部署/切换生产接入，不写_memory。


### 最终存档授权与范围（2026-10-29）

主对话已写入COMPLETION-2026-10-29.md，并明确授权为已接受前台功能及最终文档/决策/报告一次本地存档。本节、WP-NEXT-011、完成报告与实现随所在提交存档，旧失败与阶段等待记录保留为历史。无新实现或原生重测；提交前检查diff及显式暂存文件仅源码、测试和文档，不纳入媒体、JSON回执或本机数据。无推送/发布/部署/生产切换或_memory写入。
