# 前台动作与真实桌面输入

当前共13项工具，新增 `foreground_action`，须明确绑定 `access="observe_and_foreground"` 及用户任务purpose。此权限与原只读、后台左键/更多鼠标、UIA控件动作分离；其他绑定均不能调用。不会将任何后台失败回退为前台输入。

共享执行端流程：先绑定、`window_control acquire`，再新截图；每个动作消费单次30秒内frame_id并推进同窗口全连接epoch，完成后再截图确认实际效果。激活也属于动作，消耗帧；需要时可显式activate；OS拒绝激活时停止审查结果。明确click可通过真实命中目标窗口的点击自然激活并放置焦点，随后须新观察，再输入。OS拒绝激活直接报告，不使用附加线程输入、模拟Alt键或反复抢前台。

```text
bind_window(hwnd=H, access="observe_and_foreground", purpose="用户本次任务")
window_control(target_id=T, operation="acquire", lease_seconds=60)
observe(target_id=T) → foreground_action(target_id=T, frame_id=F1, action="activate")
observe(target_id=T) → foreground_action(target_id=T, frame_id=F2, action="click", x=120, y=80)
observe(target_id=T) → foreground_action(target_id=T, frame_id=F3, action="keys", keys=["CTRL","A"])
observe(target_id=T) → foreground_action(target_id=T, frame_id=F4, action="text", text="本次任务文字")
observe(target_id=T) → 检查实际效果 → window_control(operation="release", target_id=T)
```

动作参数严格按action区分，不能夹带其他动作字段：

| action | 参数与边界 |
|---|---|
| activate | 无附加字段；SetForegroundWindow一次，随后独立报告OS返回、实际前台匹配与客户区几何，复核身份；激活本身不确认输入焦点，不授予后续输入资格，后续每项输入仍独立核验安全焦点 |
| click | x、y为窗口客户区物理像素；明确真实移动/左键按下/松开，可通过命中目标的正常点击激活窗口并放置焦点；初次点击前检查目标命中和安全控件，点击后才接受新的目标内焦点 |
| keys | keys为1至4项，零至三个CTRL/SHIFT/ALT修饰键在前、一个主键在后；支持A-Z、0-9、F1-F12、ENTER/TAB/ESC/BACKSPACE/DELETE、方向/HOME/END/PAGEUP/PAGEDOWN/SPACE。拒绝Windows键、Alt+Tab/ESC/F4、Ctrl+ESC及Ctrl+Alt组合，不提供任意系统级切换能力 |
| text | 1至512个Unicode码点，SendInput KEYEVENTF_UNICODE/UTF-16输入，含补充平面字符；拒绝NUL、控制字符和孤立代理项。换行/Tab以显式按键操作；无剪贴板API或输入法设置变更 |
| drag | x/y、end_x/end_y均须在同一窗口客户区，steps为2至20；真实左键按下、分段移动、松开，路径各点必须命中精确目标窗口 |

每段检查窗口/进程创建身份、同用户同会话、实际权限、客户区尺寸与屏幕原点、实际前台及原生焦点归属；UIA MTA探针在查询前设置PMv2 DPI，且只返回安全焦点runtime指纹与固定阶段码，不读取名称、Value或Text。焦点元素及其祖先须在精确同进程窗口内且非密码，无法验证则拒绝。点操作先验证命中控件，窗口遮挡或密码字段拒绝；明确点击/拖拽开始造成的目标内合法焦点变化会重新核验，不能迁移到其他窗口或密码对象。

开始前拒绝现有按下的键/鼠标按钮；执行中保留检查，仅排除工具本次持有的精确左右键及其聚合VK，不排除另一侧。CTRL/SHIFT/ALT工具注入采用明确左侧VK，外部事件按scan/extended标志解析精确左右。鼠标动作期间仍检查光标是否被移走。

第三项在一次明确前台动作内建立低级键盘/鼠标钩子与消息泵，动作收尾后撤销；后台、只读及普通模块导入不启动监听。每个本次SendInput带31位随机dwExtraInfo，自身事件须同时匹配该标记和Windows注入标志；非自身事件透传CallNextHookEx并锁存中断，即使短按已松开也不会丢失。回调只暂存本次所需的外部持有集合、光标位置和类别计数，不保存键值、文字或坐标日志。未标记事件不能直接称为真实人类硬件输入，可能来自其他合成来源。

检测异常后停止后续按下/移动。清理只释放工具记录的精确键/按钮；已观察到外部同键仍按住时延后释放，返回release_deferred_count，不声称该状态已释放。外部按右侧而工具持有左侧时仍释放工具左侧。监听失效本身不等于人正在持有所有键：没有已知外部同键持有时尽力释放工具输入，并报告input_monitor_failed；监听失效后新发生的同键竞争仍可能不可见，无法消除该竞态。不会释放其他原本按下的键、恢复光标、BlockInput、吞事件或抢回焦点。

owned_input_release_failed只表示按键/按钮释放注入失败；input_cleanup_failed另报worker/钩子/消息泵清理故障，不把历史监听失败误称为按键释放失败。external_input_detected依据实际外部类别计数，不把内部监听异常设置的中断信号当外部事件。原生焦点变化诊断只报告实际前台/客户区尺寸是否匹配，不读取无关窗口内容。

动作总工作预算18秒，每次探针等待上限6秒且受剩余总预算约束；释放和关闭worker另预留清理时间，主动总预算低于bridge的25秒响应界限。超时/失焦/部分注入/不确定返回或释放失败均报告unknown，由现有共享故障门禁阻止换连接重放。没有自动重试按下；异常收尾只尝试释放本次工具持有的输入。用户须新观察核对实际效果，并按 [COORDINATION](COORDINATION.md) 明确恢复，之后再新观察发起新的动作。

探针响应等待每20ms检查中断和剩余预算，外部干预不必等满6秒；这不证明所有OS API、进程清理或调度都有同样响应上限。尚未调用原生输入的中断为not_sent，不制造共享输入故障；开始原生调用但无法确认的结果保守unknown，不以布尔false冒充未发送。

input_sent保留布尔类型；input_attempted表示原生调用已尝试，delivery另区分not_sent、sent_effect_unverified、attempted_outcome_unknown。接受计数为0但已尝试且结果未知时，input_sent可以为false，status仍unknown并锁存共享故障；不能仅凭该布尔值认定未发送或允许重放。

100ms定时消息与last_ack只证明消息泵仍响应，无法证明Windows没有因LowLevelHooksTimeout静默移除钩子。低级钩子、OS输入状态、提供方等待和最后检查到注入/释放之间仍有窗口，且标记不是安全隔离边界。本方案不承诺同桌面完全隔离人工输入，也不自动重放、恢复或重新获取焦点。

前台输入独占同一执行端的桌面输入门禁；其他连接的前台、UIA动作或后台鼠标在此期间拒绝，不排队注入。任一后台动作在途时也拒绝开始前台动作。没有前台动作时，不同窗口的后台操作仍可并行。独立执行端/Direct进程及人工输入不在同一个门禁域，不能同时拿它们控制桌面。

审计仅存动作、计数、长度、坐标/结果和固定错误码，不保存文字或按键序列原文，不回传第三方提供方异常原文。截图本身可能含任务输入，应继续保留在Git排除的本地证据中。SendInput返回只证明注入计数，不代表应用效果，必须新观察确认。

测试只操作 `launch_test(kind="foreground")` 自有WPF载体；真实效果、故障注入和未覆盖范围在 [VALIDATION](VALIDATION.md) 分别记录。未实际部署管理员服务/命名管道或在Codex/DSH宿主中加载新版；第三方游戏/自绘、多进程、受保护/高权限窗口以及所有DPI/输入法兼容性不由fixture通过推定。

当前验收状态：用户已明确恢复桌面测试；自有fixture最终8项真实效果/安全边界测试通过，主对话已按WP-NEXT-005审查接受（WP-NEXT-011）；本项与完成报告一并本地存档，提交可由决策记录历史核对。早期失败和离桌面检查在VALIDATION保留。

前台专用fixture明确设置Topmost保持可见，仍不自行激活；真实点击/拖拽效果验收依赖目标无遮挡。仅此自有fixture采用该测试设置，生产窗口与遮挡拒绝检查不变。真实失焦验收通过fixture在DragStarted时把焦点移到本窗空PasswordBox，核对实际UIA焦点、停输及释放，不按内部调用次数造错。已有按键验收使用测试先注入的Ctrl模拟已有OS按下状态，证明动作拒绝且不误释放；测试finally自行释放。预算验收把生产18秒参数受控缩至5秒并真实等待到期，证明剩余预算及释放路径，不能当作真实bridge端到端25秒保证。
