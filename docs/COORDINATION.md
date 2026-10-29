# 同一执行端的跨连接窗口协调

本协调项新增 `window_control`；当前加上前台动作草稿共13项工具。协调域是**一个管理员执行端实例**：run创建一个Coordinator，所有连接通过同一生产连接工厂取得独立Service/Dispatcher，并共享该实例。窗口键含HWND、PID、进程创建时间、规范路径、线程ID和窗口类，不按标题或单独PID争用。

Direct stdio仍由项目锁限制一个服务所有者：写绑定在该私有协调域中隐式持有至释放/断连，保留原调用兼容；调用方也可显式使用租期。两个独立Direct进程或不同管理员执行端实例之间**没有共享协调**。本轮没有安装或连接新版管理员服务/管道，也没有切换生产配置。

## 持续操作权

共享执行端必须先绑定所需输入范围，再获取操作权，再取得新观察：

```text
list_windows → bind_window(hwnd=H, access=任务所需写范围, purpose=用户任务)
window_control(target_id=T, operation="acquire", lease_seconds=60)
observe/observe_controls → 判断 → click/control_action → 新观察确认
window_control(target_id=T, operation="renew", lease_seconds=60)  # 必要时
window_control(target_id=T, operation="release")
```

operation为acquire、renew、release、status、prepare_recovery或recover。租期10至120秒，默认60；renew不撤销当前观察。状态返回epoch、owned、owner_is_this_connection、in_flight、剩余租期、faulted和故障码。另返回input_state、recovery_required及适用时的next_call。租期与观察30秒时效各自生效，不替代绑定权限或原生身份/权限检查。

操作权覆盖观察、判断和执行之间的时间；其他连接获取会明确拒绝，不排队抢占。非持有者可只读观察，但在原生输入在途时读操作明确拒绝，避免把中途画面当稳定观察。每窗口的在途标记不持有全局原生动作锁，因此不同窗口可并行；共享审计仅在文件写入时短暂串行。

## 观察失效与在途动作

截图与控件观察保存精确窗口键和epoch。开始窗口输入前推进epoch，即使最终明确拒绝，也要求重新观察；已发送或返回未知当然同样失效。所有连接的旧缓存即使尚保留，也不能通过版本检查；绑定/换连接不能把旧ID变成新观察。释放、过期、断连和新持有者获取也推进版本，新持有者必须新观察。换窗口/进程身份后，旧绑定的原生检查和新键都拒绝旧观察。

输入调用连同结果审计处于该窗口在途上下文中。此时租期到期不会被另一方接管；显式释放也拒绝。断连先标记待释放，动作收尾后才交还，其他窗口不受该动作等待影响。连接退出调用dispose统一释放，不能恢复旧token/帧。

## 不确定结果与显式恢复

未知/部分输入故障保存于共享窗口状态，不随连接、租期或绑定消失。为覆盖响应丢失，已输入但原持有者尚未取得成功新观察就释放/到期/断连，也保守标记为未审查输入故障。成功读到新观察只提供证据，不能自动清除已锁存故障；UIA超时/不可用等失败读取也不能确认先前输入，交还时仍锁存未审查故障。

### 恢复准备与诊断（第二项优化，待主审）

推荐入口：`window_control(target_id=T, operation="prepare_recovery")`。它要求原有写绑定，获取60秒操作权，并以**取得操作权后的最新状态**判断是否需要恢复；取得前状态仅保留为diagnostic_before，不能据此忽略租约到期/交接新产生的故障。

prepare_recovery是可选的便利入口；已有合法证据和参数的宿主仍可直接使用原recover，不强制增加步骤。

- 无故障且无待观察输入：返回`preparation=not_required`，不拍图；不会自动释放刚取得的操作权。
- 已发送但未取得新观察：拍一张绑定客户区图，返回`assess_observation`。宿主须按任务判断实际效果；获得图像不等于工具自动确认效果。
- 已锁存未知/部分或交接后的未审查故障：拍图后仍保留故障，返回`review_required`、证据及`next_call_after_review`。宿主检查证据后，才明确发送该recover调用；不强制弹出新的人工确认。

默认证据为frame；需要控件证据时显式传`evidence_kind="controls"`，只读取原有有界同进程UIA树。也可提供已有的frame_id或observation_id（只能一个），通过当前owner、目标、epoch、30秒和几何校验后复用，避免重复观察；此时返回`reused:true`，不会重发旧图/树。获取操作权造成的epoch变化不能把旧证据变成新证据。

准备成功返回的recover参数带精确target、证据ID、原绑定purpose与`reviewed_effect_no_replay`；参数是待审建议，准备工具本身不会提交恢复、点击或重放。证据失败/空树返回`evidence_unavailable`且不提供recover参数；截图抛错仍为isError。它们都不清除既有故障。成功recover仍撤销审查证据，并返回一个明确的`next_call`新观察；宿主判断新观察后才能发起新的动作。截图与UIA不会自动互相降级。

`input_state`区分`no_input_recorded`、`not_sent`、`sent_unreviewed`、`partial_or_unknown`、`observation_available`与`reviewed_no_replay`。后两者描述工作流/证据状态，不宣称应用效果正确。已知前置拒绝、接收链拒绝或有直接not_posted证据且无任何posted/attempted消息的失败，不再制造输入故障；失败观察也不凭空制造输入故障，但不会清除先前故障。未知派发、部分派发及已发送后审计失败仍保守封锁。

工具拒绝的首个text仍保留原错误字符串；具备目标上下文时，追加第二个text JSON `recovery_diagnostic`。`attempt_input=not_sent`只表示**本次调用**没有发送，不能推翻同一窗口先前的`input_state=partial_or_unknown`或`recovery_required=true`。协调器拒绝/尚未开始的调用和可靠派发证据用于分类，不把布尔false或IPC断连直接解释为无输入。未进入Service的传输失败不由本诊断覆盖，结果未知时不重试。

诊断只含状态、目标token和下一调用所需字段，不包含文字、键序列或UIA value原文；证据按原截图/控件通道交付，审计不记录图像/树内容。准备不是任意工作流或脚本接口，恢复不改变绑定的access，不增加前台/管理员授权。

恢复者先获得操作权（故障状态不阻止获取，但阻止输入），再读取故障后的新截图或有效控件观察，检查实际效果。明确恢复示例：

```text
window_control(target_id=T, operation="recover", frame_id=新帧F,
               purpose="本次用户任务中已检查未知输入后的实际效果",
               confirmation="reviewed_effect_no_replay")
```

可用observation_id替代frame_id，二选一；证据须属于同一目标、当前epoch且30秒内。恢复要求写绑定、当前持有者、无在途动作及成功非空观察（UIA还重核当前屏幕几何），清除共享故障并再次推进epoch、撤销证据；仍须新观察后才能发起新的明确动作。不会补发、重放或自动重新绑定。其他连接旧的局部故障标志不自动清除，可在共享故障已明确恢复后重新选择绑定/按同规则处理。

状态仅在本执行端内存中保存，容量有界；本项不做持久化历史恢复。停止/重启执行端结束该协调域，但不得用重启代替未知结果审查、恢复旧观察或重放旧动作。

## 验证层级与UIA线程修正

验收使用两个及多个独立Service/Dispatcher，经**实际管理员连接工厂**共享真实Coordinator，操控自有原生fixture；覆盖争用、并发唯一持有者、输入发生即跨连接失效、转交/断连、续期/在途过期、不同窗口隔离、未知故障保留与明确恢复。不是两个裸状态机调用，也不是实际IPC/高权限/宿主客户端端到端验收。

同序列曾在深/浅UIA读取均出现6秒超时。无窗口UIA worker现显式用MTA，遵循[微软线程模型建议](https://learn.microsoft.com/en-us/windows/win32/winauto/uiauto-threading)，不再依赖PowerShell默认STA；WPF fixture仍用STA。保持6秒截止，原脚本报告固定阶段毫秒与实际apartment，不记录控件内容。超时返回最后阶段并停止worker，无自动重试或前台回退。修正后恢复原默认深度5/64节点与双截图序列通过；这不承诺所有提供方或所有负载下不会超时，旧失败具体阻塞阶段未被采样，不能绝对归因。

结果、注入边界及未覆盖项见 [VALIDATION](VALIDATION.md)。前台键盘、Unicode文字与拖拽的独立实现见 [FOREGROUND](FOREGROUND.md)，自有fixture原生8项通过、主对话已接受（WP-NEXT-011）；本协调项历史验收不包含它。
