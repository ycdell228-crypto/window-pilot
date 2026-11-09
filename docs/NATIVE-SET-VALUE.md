# 标准 Edit 原生整值替换

2026-11-09。基于 `b8ca509` 的隔离开发；用户明确“已验收继续”，本小项已接受并授权本地存档，未发布或部署。

## 行为

`control_action action:set_value` 对有新鲜编辑状态的标准 Win32 Edit 改用 `SendMessageTimeoutW(WM_SETTEXT)`，一次替换整个值，可用空字符串清空；不依赖当前选区，不调用 UIA SetValue。`type_text` 仍用 EM_REPLACESEL，仅替换选区或在光标处插入。

先用 `get_window_state include_text:true` 获取 native_edit，再使用其单次观察凭据执行。原生类名、框架、进程、密码/只读样式、全文摘要、选区、控件身份和窗口几何均继续复核；单行控件拒绝换行。派发前重新核对编辑状态和前台边界。消息超时或返回失败标为结果未知，禁止重试或自动改用另一条路线。

没有合格编辑状态的 Win32 控件仍拒绝，WPF 仍拒绝。其他框架不因本项获得后台安全认证。WM_SETTEXT 是提前选择的独立路线，不是在 UIA SetValue 失败后自动兜底。

## 验证与限制

普通检查55通过、0失败、18跳过入口，见 `.local/native-set-value-ordinary.txt`。

共用工作进程回归：文字插入2通过、WPF后台设值拒绝1通过，分别见 `.local/native-set-value-insertion.txt`、`.local/native-set-value-wpf.txt`。

原生专项1通过，见 `.local/native-set-value-final.txt`。独立 WM_GETTEXT 读回证明：仅选中原文的一部分时，整值替换仍得到准确的全部新值；随后空字符串确实清空。只读、缺失编辑状态、单行换行均拒绝；单次观察不能重放；审计不记录输入文字。

所有动作前后采样中目标均非前台。清空动作前后真实鼠标位置有变化，来源未知；本轮不能宣称“全程鼠标未移动”或完整无干扰通过。实现没有移动真实鼠标、全局输入或主动激活调用，但目标应用可能自行处理消息产生副作用，仍标为 unverified。

首次运行在未发送的拒绝步骤因鼠标位置变化而测试失败，见 `.local/native-set-value-tests.txt`。测试原先要求用户鼠标静止，不适合用户继续使用电脑的场景；现改为保留前后快照，不将位置差异直接归因于程序。完整动作回执在 `.local/native-set-value/set-value-effects.json`。旧 UIA SetValue 激活失败的证据仍独立保留，见 BACKGROUND-SET-VALUE.md。

本项只验证自有标准 Edit，不覆盖任意实际编辑器；检查至派发竞态仍存在。后台快捷键和拖拽仍明确不支持，实际应用兼容性和完整无干扰验收尚未完成。不得据此提前发布或升级执行端。
