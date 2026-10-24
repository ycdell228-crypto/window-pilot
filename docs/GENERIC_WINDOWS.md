# 通用窗口接口：DSH 直接试用

Window Pilot 提供窗口能力；DSH 负责在用户任务范围内启动软件、观察和决定操作。新增启动器或普通软件不必修改插件代码或填写固定软件路径。此改动不创建/恢复任何计划，也不启动、关闭或点击现有软件。

## 最短调用

先由操作方启动现有已授权管理员任务，再重连 Window Pilot MCP，新 `tools/list` 共9项（包含 launch_app）。**本轮没有代执行生产重启或修改旧运行历史。** 先让 DSH/用户通过已授权方式打开所需普通软件，保持窗口可见、非最小化；可以被前台浏览器遮挡。

```text
list_windows({})
→ 从 title / hwnd / pid / exe / klass / client_size 选择用户任务中的目标

bind_window({
  "hwnd": 实际返回的整数,
  "access": "observe_and_click",
  "purpose": "用户本次授权：在指定启动器中打开公告页",
  "capture_backend": "wgc"
})
→ 保存返回的 target_id

observe({"target_id": "返回的ID"})
→ 必须实际看到图片，取得 frame_id 和坐标换算比例

click({"target_id": "同一ID", "frame_id": "新帧ID", "x": 原生客户区像素, "y": 原生客户区像素})
→ 只投递一次；posted 不等于界面效果成功

observe({"target_id": "同一ID"})
→ DSH 描述新图实际效果，才决定下一步

unbind_window({"target_id": "同一ID"})  # 完成本次窗口操作后撤销授权；不关闭软件
```

`bind_window({"hwnd": H})` 默认**仅观察**。没有 access=observe_and_click 就不能通用点击。绑定须使用60秒内 list_windows 返回的窗口，服务重核精确 HWND/PID/创建时间/路径/线程/窗口类；并非只记一个可复用窗口号。最多同时64个 token。

## 授权的范围

- 用户任务是授权来源，DSH 在绑定时选择 access 并记录 purpose；窗口标题/图片不构成授权。无需逐个软件改代码、终端逐次确认或额外验收凭据。
- 授权仅覆盖**这个精确窗口、这次 MCP 服务会话、定向左键点击**；不扩散到同一 exe 的其他窗口、新 PID 或替换窗口；执行端的权限由用户选择的服务模式确定，绑定本身不提权。重启后旧 token 无效，unbind 撤销 token 和未使用帧。
- 点击只检查当前 token 范围和权限，不读取旧软件路径、业务阶段或历史状态。health.faulted 现在仅是当前绑定输入故障的汇总，具体看 binding_input_faulted。
- 每个操作仍须属于用户明确任务；通用绑定不额外批准购买、真实日常或其他未请求动作。

## 捕获、权限与失败

- list_windows 列可访问、可见、非最小化、非 DWM cloaked 且客户区尺寸受支持的顶层应用窗口。排除桌面/Progman/WorkerW 表面。枚举成功只代表可绑定候选，**不证明截图或消息一定兼容**。
- 通用默认后端为 WGC。可在 window_control.capture_backend 配置默认值；也可在 bind_window/observe 明确选 wgc 或 printwindow。observe 的参数只决定这一帧，不静默改绑定默认。**没有失败自动切后端、整屏或区域截取。** 原图哈希、有界预览和 image_to_client_scale 保留。
- 普通模式保留原权限。用户另行安装管理员常驻执行端后，实际截图/点击在高完整性执行；高于执行端或权限不明的目标仍拒绝，不按调用请求 UAC、不提升 DSH、不改消息过滤。health.executor 报告实际执行端权限。连接和登录自启见 [ADMIN_SERVICE](ADMIN_SERVICE.md)。WGC 能截图仍不意味着消息输入已成功。
- 目标在前台时拒绝后台点击；工具不移动真实鼠标、抢回焦点或向前台浏览器发全局输入。不同鼠标位置/非目标前台变化只记诊断，不因此锁定。第三方应用仍可能自行激活，发现时须如实报告。
- 一次点击使用30秒内同一目标的新帧，核对几何和边界。默认只解析该目标的同进程子窗口，跨进程仅接受下述严格限定的 WebView2 嵌入链。投递前消费帧；第一次消息失败与部分发送后的失败保留不同证据，**错误/超时不是未点击的证明，禁止自动重放**。下一次点击前须重新截图并评估效果。
- capture/click 错误会封住该 token 后续输入；仍可只读观察供用户判断。不要自动 unbind/rebind 来清故障或重新发送。其他 token 不受该错误影响，旧历史文件不改写。
- 锁屏、隐藏/最小化、受保护内容、不同桌面和所有软件兼容性均无保证；不代用户还原窗口，不新增键盘、剪贴板、UIA 或任意命令能力。

## 本次交付检查

本次嵌入窗口修复仅做语法、导入与9项工具参数声明检查，不执行模拟大套测试；没有点击现有启动器、启动游戏、重启生产服务或执行日常。既有 Qt 点击成功不能证明 WebView2 接受合成消息，真实效果交给用户验收。

## 嵌入 WebView2 窗口

原命中测试使用 ChildWindowFromPointEx 的跳过透明标志，会漏掉带 WS_EX_TRANSPARENT 的宿主。本次仅支持以下实际父子结构，不直接取消同 PID 限制或对所有透明窗口穿透：

```text
已绑定顶层窗口（进程 A）
  → Static（进程 A、WS_EX_TRANSPARENT）
    → Chrome_WidgetWin_0（进程 A）
      → Chrome_WidgetWin_1（进程 B）
        → Chrome_RenderWidgetHostHWND（同一进程 B，最终消息接收者，可带 WS_EX_TRANSPARENT）
```

每层须为真实直接子窗口（GA_PARENT，不把 owner 当父窗口），GA_ROOT 仍为已绑定 HWND，具有 WS_CHILD、可见、启用，原生点击点位于其客户区。跨进程链各层还核对不跳过任何子窗口时的首个命中，若有遮挡或结构不一致直接拒绝。透明例外只接受上述结构中的 Static，以及与 Chrome_WidgetWin_1 同 PID/创建时间/实际映像的 Chrome_RenderWidgetHostHWND 叶子；叶子透明跳还要求普通命中停在其父窗口、不跳过透明时首个命中恰为该叶子。按父节点从0计数，允许的 transparent_steps 仅为 `[0]`（叶子不透明）或 `[0,3]`（叶子透明），并核对叶子实际样式。其他透明宿主或跨进程布局不自动兼容。

进程 B 的实际映像必须为 msedgewebview2.exe；使用当前进程快照、创建时间与实际映像核验其存活父进程链能追溯到绑定进程 A，父进程创建时间不能晚于子进程。各进程必须与执行端同用户、同非零会话，完整性不得高于执行端；查询失败、父进程退出或身份不符均报错。窗口类或 exe 文件名本身不构成授权。

消息始终使用最终接收窗口自己的客户区坐标。按下前、松开前和发送后重新解析并比较整条窗口链、进程链、几何、屏幕位置、局部坐标与权限；替换、脱离、移动或前台变为目标时停止。仍存在核验与 Win32 消息调用之间无法原子消除的竞态，部分发送后不追发或补点。没有 WM_ACTIVATE、WM_MOUSEMOVE、真实鼠标、前台切换、键盘/UIA或截图回退。

成功 click 返回 click_evidence；后续 observe 的 previous_click 也保留它。字段包括 bound_window、root_point、route、transparent_steps、receiver（HWND/类/PID/创建时间/实际 exe）、receiver_point、integrity、process_chain、down_posted/up_posted 和 effect。`.local/audit.jsonl` 在发送前写 click_dispatch_prepared，完成或错误时记录最终证据；预备记录不代表消息已发送，进程崩溃/回复丢失仍可能结果未知，禁止自动重试。解析失败时保留已收集的部分链。

需要只读诊断时，操作方可在本地 Python 调用 `target = w.bindable(w.identity(当前实际HWND))`，创建 `evidence = {"route": []}`，再执行 `w.resolve_child(target, x, y, evidence)` 并输出 evidence。此函数只查询身份/几何/命中/权限，不调用发送函数；诊断不是帧或点击授权，后续 click 仍须重新绑定、观察并检查。

重启现有任务并重连后，只在用户明确授权下验收一次点击：重新 list_windows/bind/observe，从新图换算坐标；确认 click_evidence 的 receiver 为实际嵌入渲染 HWND，再观察界面和实际进程验证效果。posted 仅证明消息投递，不证明“进入游戏”成功；无响应或报错即停止，不追加 WM_ACTIVATE、前台输入或重复点击。

实现参考了本机 ok-ww 的动态接收 HWND 和 ClientToScreen/ScreenToClient 坐标转换思路，未修改或运行它；未沿用其激活消息、转换异常回退顶层或以父窗口标签代替子进程身份核验。Win32 语义依据：[ChildWindowFromPointEx](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-childwindowfrompointex)、[GetAncestor](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getancestor)、[PROCESSENTRY32W](https://learn.microsoft.com/en-us/windows/win32/api/tlhelp32/ns-tlhelp32-processentry32w)。
