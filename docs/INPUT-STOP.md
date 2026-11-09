# 第四项交验：执行端停止与恢复输入

状态：用户于 2026-11-09 明确“第四项验收通过，存档并继续”，本项随本次提交本地存档，未推送或部署。第三项已存档为 `9e2c3c3`。

## 接口与行为

调用 `input_control`：

```json
{"operation":"stop"}
{"operation":"status"}
{"operation":"resume","stop_id":"当前停止回执中的 stop_id","confirmation":"user_requested_resume","purpose":"用户明确要求继续的任务"}
```

- stop 幂等，对同一 Coordinator/执行端全部连接生效；连接退出不会解除停止。返回 stopped、stop_id、in_flight。停止时作废已有观察凭据。
- 停止后拒绝 click、control_action、foreground_action 和新的 launch_app/launch_test；允许只读观察与清理。
- resume 只能在用户新近明确要求继续后调用，要求当前 stop_id；有输入票据在执行时拒绝恢复。恢复再次作废观察，必须重新观察；既有未知输入故障仍须按原恢复流程核实，不自动重放。
- confirmation/purpose 是调用方声明，不是用户授权凭证；该接口不是同账户恶意客户端的安全边界。

## 执行中取消的边界

后台鼠标在每条消息前检查停止。已发下按消息后停止，会中止后续释放消息并保留部分/未知故障；目标应用可能仍保有按下状态，不能自动重试或补发。

UIA 动作工作进程每次等待最多 50ms 后检查停止；停止时终止并回收工作进程。进程创建后取消保守报告 unknown，不能据此证明提供方未执行或撤销已派发效果。50ms 是轮询间隔，不是端到端停止时限。

前台独立模式将停止检查接入已有输入监听检查点；仍允许释放本次自有输入与关闭探针。未新增真实前台输入验收。停止检查和原生派发之间仍存在竞态。

共享服务需另一连接发送停止才能中断当前串行请求；单连接 stdio 只能在请求之间处理停止。in_flight 只计协调器输入票据，不包含启动进程；已经通过入口检查的启动请求不被取消。此项没有物理 Esc、用户停止按钮、跨执行端广播或重启后持久停止。不得通过重启规避停止状态。

## 验证

- `CI=1 WINDOW_PILOT_NATIVE_TESTS=0 python scripts/test_runner.py`：51 通过、0 失败、14 个跳过入口。原始输出 `.local/input-stop-tests-final.txt`。
- `CI=1 WINDOW_PILOT_NATIVE_TESTS=1 python -m unittest discover -s tests -p test_input_stop.py -v`：6 通过，含 5 项普通契约/实际子进程检查与 1 项自有原生窗口检查。输出 `.local/input-stop-native-cancellation.txt`。
- 原生检查覆盖停止时只读、恢复后旧凭据拒绝、重新观察，以及真实 UIA 工作进程创建后、发送 stdin 前取消并回收。没有执行成功设值来证明后台兼容性。
- 普通检查覆盖跨连接停止、幂等、恢复凭据/时效、执行中禁止恢复、未知故障保留、实际工作进程通信/回收，以及鼠标下按后停止不再派发。
- 本项为协议/执行器改动，无新增可截图界面；运行回执在忽略的 `.local/`，不纳入 Git。

## 必须保留的失败与后续问题

早先原生验收尝试恢复后执行 WPF SetValue，失败输出保留于 `.local/input-stop-native.txt`：返回 `unknown / UIA_BACKGROUND_TARGET_IN_USE`，`action_attempted:true`；前后桌面快照显示目标由非前台变为前台，也观察到光标位置变化。快照不能单独确定这些变化由提供方还是外部输入造成，不能把因果归为已证实。

这次运行没有满足严格后台验收。检测到变化并停止不能撤销干扰；该 SetValue 路径尚未证明安全，不再重复该成功输入探测。后续取消测试通过只证明本项取消行为，不覆盖或抹去这次失败。

整体后台目标仍未完成。下一小项应优先处理后台动作的已验证能力范围及默认拒绝策略，再做实际应用完整任务验收；本报告不将建议记为已确认决定。
