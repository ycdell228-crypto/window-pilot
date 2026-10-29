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

operation为acquire、renew、release、status或recover。租期10至120秒，默认60；renew不撤销当前观察。状态返回epoch、owned、owner_is_this_connection、in_flight、剩余租期、faulted和故障码。租期与观察30秒时效各自生效，不替代绑定权限或原生身份/权限检查。

操作权覆盖观察、判断和执行之间的时间；其他连接获取会明确拒绝，不排队抢占。非持有者可只读观察，但在原生输入在途时读操作明确拒绝，避免把中途画面当稳定观察。每窗口的在途标记不持有全局原生动作锁，因此不同窗口可并行；共享审计仅在文件写入时短暂串行。

## 观察失效与在途动作

截图与控件观察保存精确窗口键和epoch。开始窗口输入前推进epoch，即使最终明确拒绝，也要求重新观察；已发送或返回未知当然同样失效。所有连接的旧缓存即使尚保留，也不能通过版本检查；绑定/换连接不能把旧ID变成新观察。释放、过期、断连和新持有者获取也推进版本，新持有者必须新观察。换窗口/进程身份后，旧绑定的原生检查和新键都拒绝旧观察。

输入调用连同结果审计处于该窗口在途上下文中。此时租期到期不会被另一方接管；显式释放也拒绝。断连先标记待释放，动作收尾后才交还，其他窗口不受该动作等待影响。连接退出调用dispose统一释放，不能恢复旧token/帧。

## 不确定结果与显式恢复

未知/部分输入故障保存于共享窗口状态，不随连接、租期或绑定消失。为覆盖响应丢失，已输入但原持有者尚未取得成功新观察就释放/到期/断连，也保守标记为未审查输入故障。成功读到新观察只提供证据，不能自动清除已锁存故障；UIA超时/不可用等失败读取也不能确认先前输入，交还时仍锁存未审查故障。

恢复者先获得操作权（故障状态不阻止获取，但阻止输入），再读取故障后的新截图或有效控件观察，检查实际效果。明确恢复示例：

```text
window_control(target_id=T, operation="recover", frame_id=新帧F,
               purpose="本次用户任务中已检查未知输入后的实际效果",
               confirmation="reviewed_effect_no_replay")
```

可用observation_id替代frame_id，二选一；证据须属于同一目标、当前epoch且30秒内。恢复要求当前持有者、无在途动作，清除共享故障并再次推进epoch、撤销证据；仍须新观察后才能发起新的明确动作。不会补发、重放或自动重新绑定。其他连接旧的局部故障标志不自动清除，可在共享故障已明确恢复后重新选择绑定/按同规则处理。

状态仅在本执行端内存中保存，容量有界；本项不做持久化历史恢复。停止/重启执行端结束该协调域，但不得用重启代替未知结果审查、恢复旧观察或重放旧动作。

## 验证层级与UIA线程修正

验收使用两个及多个独立Service/Dispatcher，经**实际管理员连接工厂**共享真实Coordinator，操控自有原生fixture；覆盖争用、并发唯一持有者、输入发生即跨连接失效、转交/断连、续期/在途过期、不同窗口隔离、未知故障保留与明确恢复。不是两个裸状态机调用，也不是实际IPC/高权限/宿主客户端端到端验收。

同序列曾在深/浅UIA读取均出现6秒超时。无窗口UIA worker现显式用MTA，遵循[微软线程模型建议](https://learn.microsoft.com/en-us/windows/win32/winauto/uiauto-threading)，不再依赖PowerShell默认STA；WPF fixture仍用STA。保持6秒截止，原脚本报告固定阶段毫秒与实际apartment，不记录控件内容。超时返回最后阶段并停止worker，无自动重试或前台回退。修正后恢复原默认深度5/64节点与双截图序列通过；这不承诺所有提供方或所有负载下不会超时，旧失败具体阻塞阶段未被采样，不能绝对归因。

结果、注入边界及未覆盖项见 [VALIDATION](VALIDATION.md)。前台键盘、Unicode文字与拖拽的独立实现见 [FOREGROUND](FOREGROUND.md)，自有fixture原生8项通过、主对话已接受（WP-NEXT-011）；本协调项历史验收不包含它。
