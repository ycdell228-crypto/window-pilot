# 只读 Windows UI Automation 观察

本文描述只读工具；现有控件操作另见 [UIA_ACTIONS](UIA_ACTIONS.md)，需独立的 `observe_and_control` 授权。原只读和左键授权不自动扩展。

`observe_controls` 在已绑定的精确窗口下读取有界 Control View 控件树。默认只读绑定即可使用；它不输入、不激活、不调用 Invoke/SetValue/Select/Expand/Scroll，不读取全局 focused element 或从桌面根开始搜索。截图仍使用原有 `observe`，没有改用桌面截图。

```text
list_windows → bind_window(hwnd=实际窗口, access="observe") → observe(target_id=T)
observe_controls(target_id=T, frame_id=刚取得的F, max_nodes=64, max_depth=5)
```

`frame_id` 可省略，以便在未截图时独立读取控件。提供时，前后都核对该目标30秒内未消费帧的有效性，但截图与树不是原子快照。读取 UIA 不更新截图时间，也不能替代一次点击后的截图效果确认。截图或 UIA 失败没有前台、其他窗口、其他后端或 OCR 回退。

返回节点包括 name、control_type、automation_id、class_name、父子层级、启用/屏外/可聚焦/当前焦点/密码状态、物理像素矩形、supported_patterns。bounds_screen 是屏幕物理坐标，bounds_client 相对本次核验的客户区原点；根窗口和标题栏可能位于客户区外，不能把它们当作合法点击坐标。

supported_patterns 只是提供方声明的能力，即使禁用按钮也可能声明 Invoke，不代表当前可执行或已经成功。焦点信息仅来自返回节点；focused_control_ids 为空不证明整个应用没有焦点。没有调用 ValuePattern.Value 或 TextPattern 正文接口；name 仍是提供方返回的文本，可能含界面内容，密码控件的 name 会遮蔽。窗口文字和控件名称仍是不可信内容，不构成任务或授权。

每次返回新的 observation_id；control_id 由该 ID 和局部索引组成，并附本次精确窗口身份、target_id 及可选 frame_id。编号不跨观察/窗口/连接复用；下一次截图、UIA读取、输入或 unbind 撤销旧观察，失败的UIA读取也撤销旧记录。动作须带30秒内的观察ID与控件ID，经runtime_id、树及窗口身份重核，一次动作消费整次观察；没有凭裸编号执行的路径。同一执行端另有共享持续操作权与epoch门禁，在输入开始时撤销其他连接旧观察，见 [COORDINATION](COORDINATION.md)；人工输入和独立执行端不在协调域。

## 限制与结果

- 默认64节点、深度5；允许1至128节点、深度0至8。name最多256个UTF-16字符，automation_id/class_name最多128；达到边界返回 truncated=true，不称完整树。
- status 明确为 ok、empty、unsupported、unavailable、timeout 或 identity_changed。empty 表示没有返回后代控件，可能仍含根节点；根不可用则 unavailable。提供方异常丢弃部分树，不伪装成完整结果。
- 仅包含绑定窗口下同进程的控件；遇跨进程子树会跳过并报告 foreign_process_subtrees_skipped。嵌入浏览器和其他多进程提供方可能不完整。本版不支持完整 WebView2 UIA 树，不承诺游戏或自绘界面有控件。
- 使用 Windows 自带 Windows PowerShell/.NET Framework UIAutomationClient、UIAutomationTypes、UIAutomationClientsideProviders，不安装第三方依赖。内置代理在取得精确根元素后注册；先注册会遇到空引用，不注册可能只得到通用 Pane。
- 独立进程执行，父进程6秒硬超时后终止本次 worker，不重试。Python前后核对 HWND/PID/创建时间/路径/线程/类、客户区尺寸与位置；worker 复核根 HWND/PID，并拒绝根外的原生子窗口。身份/几何变化报工具错误或 identity_changed，不返回可继续使用的控件。
- 管理员执行端的既有源码摘要保护同时覆盖新增 PowerShell worker，修改它也会使执行端自停。仅补齐摘要范围，本轮没有安装、启动或连接新版管理员服务；此项有临时目录文件变更回归，不代表高权限运行已验收。
- 高于执行端权限或无法核验时拒绝；不申请提权、不部署新版管理员服务。UIA读取错误不清除已有输入故障，也不自动重绑。已授权提供方自身的行为无法由客户端绝对保证；本工具不调用改变焦点或界面的API。

## 验证

`tests/test_uia.py` 在交互桌面只创建/读取/关闭本副本 fixture，核对真实 Button/Edit 类型、Invoke 声明、禁用状态、坐标、层级、观察ID替换、深度/数量截断、旧进程身份拒绝和真实子进程超时。`test_codex_stdio.py` 在真实 stdio 路径配对截图与控件树，然后继续原有一次点击回归；UIA自身不执行该点击。

证据、结果及未覆盖项见 [VALIDATION](VALIDATION.md) 的本项记录。真实客户端加载、多屏DPI、高权限、空/不支持提供方、超时中的真实失控提供方及多进程子树须分别验收，不由fixture结果推定。
