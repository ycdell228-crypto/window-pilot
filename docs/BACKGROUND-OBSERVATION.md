# 后台统一观察：首项交验

2026-11-08。实现仅在隔离副本 `background-observation`；用户随后已验收，首项存档为 `0198c27`，继承基线另存为 `d25e896`。未部署或推送。下文各阶段“未提交/待验收”保留为当时状态，生产目录及其既有未提交内容保留。

## 功能对应核对

官方参考为本机 computer-use 插件 `26.1103.32239/docs/api.md` 的 Windows API；本轮核对接口文档，不声称检查或复制官方二进制原生核心。

| 官方设计 | 原工作区现状 | 本项/后续边界 |
|---|---|---|
| get_window_state | observe 截图、observe_controls 树两个入口 | 新增统一入口；可按需读取，明确非原子 |
| 值、正文、文字选区 | 不读值/正文；有焦点标志及 SelectionItem 状态 | 本项增加有界字段；Win32 Edit 选区有限支持，WPF 等明确不支持 |
| focused_element、selected_elements | 树内焦点、选择状态 | 返回 focused_control_ids、selected_control_ids；仅代表已返回树，不跨窗口找焦点 |
| set_value、type_text、press_key | UIA set_value；文字/按键在明确前台接口 | 后台插入文字、快捷键未实现，本项不变更动作 |
| 元素/坐标点击 | UIA invoke 和 PostMessage 坐标接口分开 | 已有有限支持；不统一为自动重试路线 |
| 应用/窗口发现 | list_windows、精确 bind、可选 launch_app | 缺少 list_apps、应用归属及弹窗衔接 |
| 关联临时界面截图 | 只截绑定窗口客户区 | 多窗口联合观察未实现 |
| 停止与清理 | 有连接清理、前台动作干扰检测 | 缺统一后台停止入口、回合停止锁存 |
| 授权生命周期 | 独立范围/用途字符串、解绑 | 用途不是可信用户授权凭证 |
| 统一错误恢复 | 已有未知故障、epoch、prepare_recovery/recover | 保留；新观察不自动清故障或重放 |
| 隐藏通信细节 | 显式窗口租约 | 自动管理租约留待后续 |

核对来源：`src/window_pilot/service.py` 工具声明/dispatch、`uia.py`、`scripts/uia-observe.ps1`、`win32.py`、`coordination.py`。旧生产 health 实测为共享管理员执行端，不代表新实现部署。

## 调用契约

先 `list_windows`、`bind_window` 得到 `target_id`，再调用：

```json
{"target_id":"<binding>","include_screenshot":true,"include_accessibility":true,"include_text":true,"max_text_length":512,"max_total_text_length":8192}
```

三个 include 默认 true。至少请求截图或 accessibility；截图单独请求时无需启动 UIA。旧 observe/observe_controls 接口保留，旧 observe_controls 默认不读文字。官方 include_text 表示 accessibility，而此接口另用 include_accessibility 控制树、include_text 控制值/正文读取；不是逐参数兼容替代。

- 返回 `identity`、总体起止时间、`read_only:true`、`atomic_snapshot:false`、`screenshot` 和 `accessibility`。未请求的部分为 null。图片沿 MCP 原生 image 内容交付；截图坐标/缩放、frame_id 都在 screenshot 内。
- accessibility 包含树、observation_id、frame_id、焦点及已选控件 ID。每个节点的 `text.value`、`text.document_text`、`text.selected_text` 各自给出状态和可用文本；不擅自选一个节点当全应用正文。
- 每字段上限 1..2048 UTF-16 单元，默认512；全树新增文字总额 1..32768，默认8192；最多16个选区。保留 UTF-16 代理对，限制只针对新增文字字段，原树名称另有既有上限。
- 状态：`ok`、`empty`、`unsupported`、`unavailable`、`truncated`、`password_filtered`。unsupported/unavailable/filter 不返回 text，不等于空文本。正文只在完整同进程树内读取；树截断或跳过外进程子树时返回 `incomplete_privacy_scope`。
- 根据提供方 IsPassword 过滤密码控件、已知密码祖先/后代的新增文字，不回显提供方异常正文。此过滤不是截图打码，也不是对错误标注密码属性的恶意提供方的保证。
- ValuePattern.Value 原生 API 本身不支持限长，worker 获取后才截断；TextPattern.GetText 按所需长度读取。保留6秒 worker 超时及262144字节整体输出上限，失败不改用全桌面或前台。
- 文字选区目前只启用已实测的 Win32 `Edit` 提供方直接读取。WPF TextBox 的非焦点选区读取曾超时；返回 `unsupported/background_selection_provider_not_validated`，不通过聚焦、移动范围或更换输入路线修补。
- `status:partial` 表示 UIA 失败但截图成功；各文字字段仍单独检查状态。截图失败整体报错，不再调用备用后端。身份/epoch/时效失效整体拒绝，丢弃本次缓存凭据。
- 观察关联不会清除未知故障；故障窗口仍可读取。新鲜 frame/observation 可用于原接口，但输入仍要单独授权、获取操作权，保留单次消费和30秒期限；不新增前台兜底。

## 验证及限制

必要普通回归与新增原生观察用例见 `tests/test_window_state.py`，原生仅自有测试窗口。Win32 测试只给自有子控件初始化选区，不发送真实键鼠；WPF 测试检查值、正文、密码过滤和选择控件ID。测试回执与截图在 `.local/validation/window-state/`，不入Git。

最终验证（2026-11-08）：`CI=1 WINDOW_PILOT_NATIVE_TESTS=0 python scripts/test_runner.py` 普通39通过、0失败、12个跳过入口；`CI=1 WINDOW_PILOT_NATIVE_TESTS=1 python -m unittest discover -s tests -p test_window_state.py -v` 7通过、0失败、18.279秒，其中1项无桌面契约检查、6项自有窗口用例。实际使用 bundled Python，PYTHONPATH 指向本副本 src。最后保存的 WPF 截图/树读取前后前台 HWND 与鼠标位置相同，UIA 诊断 changed=false；这仅是阶段采样。`git diff --check` 通过，生产90个基线文件哈希复核一致。

历史失败保留：初版工具名单未包含新接口；选区 GetText 在 WPF 提供方超时；尝试克隆/移动范围后提供方报 ElementNotAvailable，且原生 Edit 首次观察阶段曾两次出现目标成为前台。该范围移动方案已移除，改为直接有界读取并限制提供方；这些观察不足以确定前台变化因果。最终结果在交验回复和该目录日志中列明。

前台/鼠标只做阶段采样，不能证明采样间绝无变化；不宣称全程后台验收通过。未验证真实用户应用的完整读写任务、多进程嵌入编辑器、实际宿主重新发现工具、管理员 IPC 新接口及所有提供方。第一项只读接口完成不等于整个“后台版 computer use”目标完成。

## 现有改动保护

### 2026-11-08 恢复后的首项复核

发现并复现：截图完成后、自有窗口尺寸改变、再读取控件树时，统一接口此前仍返回成功，组合结果包含不同尺寸的截图与树。新增原生回归在修复前因“未抛出错误”失败；这不是此前7项通过所覆盖的情况。

已在首项内补充统一读取前后客户区位置/尺寸校验，同时对照截图尺寸与 UIA geometry。不一致返回 `WINDOW_STATE_GEOMETRY_CHANGED`，移除本次 frame 和 control observation 凭据；仍不声称非原子的读取变成原子快照，也不能检测采样之间改变又恢复的情况。

修复后同一回归通过（6.657秒），完整本项8项通过/0失败（26.932秒）；普通39通过/0失败、12跳过入口。回执为 `.local/validation/window-state/geometry-fix.txt`、`native-geometry-fix.txt`、`ordinary-geometry-fix.txt`，最新截图/状态在其 `geometry-fixed/` 子目录。测试只以 NOACTIVATE 调整自有窗口；没有用户窗口输入。`git diff --check` 通过，生产90个基线文件哈希仍一致。首项仍待用户验收，未提交、部署或保存项目记忆。

### 基线

隔离副本以生产 HEAD `f5736fdba989e68ac18aad2beb4947955eef735c` 独立克隆，不共享 Git 硬链接，再复制当前90个已跟踪/未忽略文件，逐项 SHA256 一致。基线文件及 manifest 在 `.local/baseline/`；Git diff 含历史未提交改动，不能把全部差异当成本项。提交前应只审本项相对该基线的差异，并另行确认继承改动如何归档。
