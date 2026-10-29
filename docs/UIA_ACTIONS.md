# 观察级 UIA 控件操作

`control_action` 对支持标准 UIA pattern 的同进程普通控件执行一次操作。当前13项 MCP 工具。只读 `observe`、原 `observe_and_click` 均不能调用它；必须在用户任务内明确 `bind_window(access="observe_and_control", purpose="本次用户任务")`。此授权只覆盖该精确窗口的 UIA pattern，不包含坐标点击、全局键盘、剪贴板、SetFocus或前台回退。

```text
list_windows → bind_window(hwnd=H, access="observe_and_control", purpose="用户本次任务")
observe_controls(target_id=T) → O=observation_id，C=选定节点的control_id
control_action(target_id=T, observation_id=O, control_id=C, action="invoke")
observe_controls(target_id=T) → 确认真实状态/名称/模式状态变化，必要时另observe截图
```

| action | 对应模式 | 参数与范围 |
|---|---|---|
| invoke | Invoke | 无附加参数，一次Invoke |
| set_value | Value | 必填value，最多2048字符，允许空串；拒绝NUL、只读值和密码控件 |
| select | SelectionItem | 无附加参数，一次Select；不靠名称猜选项 |
| expand / collapse | ExpandCollapse | 无附加参数，一次Expand或Collapse |
| scroll | Scroll | horizontal/vertical各为NoAmount、SmallIncrement/Decrement、LargeIncrement/Decrement；默认NoAmount，至少一个轴有动作，一次Scroll |

模式存在但控件禁用、不可见、屏外、只读值或密码仍会拒绝；普通Pattern不支持时明确返回rejected。没有模拟输入、鼠标/键盘或另一种pattern回退。参数应来自明确用户任务，窗口文字/控件名称不构成授权。

## 标识、检查与单次消费

观察记录保存精确窗口身份、原生几何、有界树、runtime_id、层级、完整名称哈希、控件属性/状态、物理矩形及模式状态。动作按runtime_id重新解析，不用裸编号、名称或AutomationId作为可复用定位。父进程与worker核对窗口PID/创建时间/路径/线程/类、同用户同会话及权限；worker重新读取同样界限的树，任何已观察节点身份/名称/状态/位置/层级变化都拒绝旧观察。发出动作前再次核对根、选定控件runtime_id、启用/密码状态、位置及所属祖先链。

观察有效期30秒；父进程和worker派发前都检查。一次动作消费整次观察，不能拿同一次观察的另一个ID继续执行。截图、UIA重读或本连接内对同窗口的输入会撤销已有观察；UIA/左键输入还会使本连接所有同窗口绑定的旧截图失效。只读拒绝不执行；进入worker后即使已知拒绝也要重新观察。同一执行端现在通过共享操作权与epoch使其他连接旧观察在输入开始时失效，见 [COORDINATION](COORDINATION.md)；人工输入和独立执行端不在此协调域。

根窗口或子树仍可能在最后检查与提供方调用间改变，UIA不能提供原子锁；实际提供方也可能自行激活。返回desktop_observation报告前台与鼠标采样，不从变化推断原因。**本机WPF验收已观测到目标在部分操作期间变成前台，不能承诺UIA操作完全留在后台。** 工具没有调用SetFocus、SendInput或前台回退。

## 结果和未知状态

- provider_returned：提供方调用已返回，effect仍为unverified；必须新观察确认实际效果。
- rejected：执行前明确拒绝，action_attempted=false、effect=not_sent；报告具体错误码。
- unknown：超时、断连、异常或派发后身份无法确认，动作可能已执行；同窗口本连接输入被封住，仍可只读观察。禁止重放、自动换ID或重新绑定清除故障。提供方抛错也不能当作完全没执行。

worker为受源码摘要保护的系统Windows PowerShell/.NET进程，6秒硬截止，不自动重试或提权。SetValue原文仅在stdin负载中传递，不放在进程命令行、不写审计；审计记录value_length、观察/控件ID、动作、结果和桌面诊断。动作错误不返回可能包含输入值的提供方消息。审计写入失败且动作可能执行时同样封住输入。

## 自有fixture验证

`launch_test(kind="uia")` 只启动本项目WPF载体，默认`launch_test()`仍为原生截图/左键fixture；close_test只关闭该子进程的已核验窗口。WPF窗口不主动请求激活，但其UIA提供方执行时可能激活。

`tests/test_uia_actions.py` 的真实正例逐类核对：Invoke计数、SetValue精确界面回显、SelectionItem选中状态、Expand/Collapse状态、Scroll百分比。还检查整次观察单次消费、只读绑定、禁用/密码/不支持对象、受控过期、真实位置变化、同窗口名称变化、审计无输入原文，以及真实worker强制超时后的封锁。截图/左键通过原fixture的真实stdio回归保留。

未覆盖多进程UIA、高权限、真实客户端接入、全部程序提供方、真正卡死或已部分执行的第三方提供方、并发UI竞态；不能从fixture结果推定这些场景已通过。新增定向鼠标动作另见 [MOUSE_ACTIONS](MOUSE_ACTIONS.md)，与UIA授权分开；同一执行端跨连接协调见 [COORDINATION](COORDINATION.md)；独立前台键盘/文字/拖拽见 [FOREGROUND](FOREGROUND.md)，自有fixture原生8项通过、主对话已接受（WP-NEXT-011）。
