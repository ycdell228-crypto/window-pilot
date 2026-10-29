# 定向右键、双击与双向滚轮

扩展现有 `click`，当前工具总数为13（含后续新增的window_control，见 [COORDINATION](COORDINATION.md)）。省略 action 时仍为原来的左键一次；原 `observe_and_click` 授权仍只允许该行为。新动作须明确 `bind_window(access="observe_and_mouse", purpose="用户本次任务")`，不授予UIA动作、全局键盘、真实鼠标、剪贴板或前台操作。

每次先从绑定窗口自身 observe 得到新鲜单次帧，输入 x/y 都是原生客户区物理像素。成功投递后仍须再次截图确认；有界组内的双击按一次动作消费帧，不能用旧帧补发消息。

| action | 参数 | 派发 |
|---|---|---|
| left_click（默认） | x/y、target_id、frame_id | 原WM_LBUTTONDOWN/UP |
| right_click | 同上 | WM_RBUTTONDOWN/UP |
| left_double_click | 同上 | DOWN、UP、WM_LBUTTONDBLCLK、UP |
| scroll | 同上，必填steps，axis默认vertical | 一条WM_MOUSEWHEEL或WM_MOUSEHWHEEL |

scroll 的steps必须是非零整数，范围 -10至10，每步120单位；vertical正数向上、负数向下，horizontal正数向右、负数向左。非scroll动作拒绝axis/steps，不静默忽略额外参数。

```json
{"target_id":"T","frame_id":"新帧F","x":300,"y":100,"action":"right_click"}
{"target_id":"T","frame_id":"再取得的新帧F2","x":300,"y":100,"action":"left_double_click"}
{"target_id":"T","frame_id":"再取得的新帧F3","x":300,"y":100,"action":"scroll","axis":"horizontal","steps":-2}
```

## 接收路径、坐标与双击语义

沿用精确窗口身份、逐层ChildWindowFromPointEx核验、同进程子窗口或严格Static/WebView2嵌入链。每条消息前与派发后重核接收链、父子关系、PID/创建时间/路径/线程/类、权限、几何、样式和点位；不进行全局hit-test或读取焦点窗口。滚轮只投递到该点命中的已核验子窗口，不因无效果改投父窗口/前台或重发。

按钮消息lParam为接收窗口客户区坐标。滚轮lParam为根窗口客户区点换算的**屏幕物理坐标**，按有符号16位分量编码，支持负坐标；超出[-32768,32767]明确拒绝。wParam高字为带符号增量，低字不带全局键盘/按钮修饰状态。应用可自行向内部父控件传播消息，工具本身只发送一次，不承诺所有控件都消费滚轮或弹出菜单。

双击要求最终接收窗口类设置CS_DBLCLKS；不支持时在派发前拒绝，不回退成两个单击。第二次按下使用WM_LBUTTONDBLCLK，固定同一点，按本机GetDoubleClickTime的查询值限制投递间隔，并复核类样式。时间窗超出时可能第一组单击已经发送，须报告部分组并停止；不能补发第二次普通单击。工具不修改系统双击或滚轮设置。

## 证据、失败与效果

审计的click_dispatch_prepared在第一条消息前保存接收链、完整计划、实际坐标语义及增量；完成或出错保留逐条messages状态：posted、not_posted、attempted（返回未知）。down_posted/up_posted是按钮组状态，up_posted指最终要求的释放；双击第一条UP是否发送以逐条列表为准。滚轮没有按钮按下/释放，不能由两个布尔值都false推断没有输入。

未投递的明确失败报告input_sent=false；已有成功投递则true；仅有不明尝试则unknown。部分发送、消息屏障超时/失败或后续核验失败都会封住该绑定输入，帧不会恢复。禁止自动重放、补释放、重绑绕过或切换其他输入；仍可只读截图供操作方检查。成功返回也只是effect=unverified，图片实际变化才是后续证据。

输入开始时使同一执行端所有连接的同窗口旧控件观察/帧失效；持续操作权及未知故障门禁见 [COORDINATION](COORDINATION.md)。独立执行端和人工输入不在协调域。桌面变化只作无归因采样，不把用户同时移动鼠标/切换窗口视为工具输入的证明。工具不调用SetForegroundWindow、SendInput、SetFocus或移动真实鼠标。

## 本机验收范围

`tests/test_mouse_actions.py` 只打开/截图/操作/关闭新版原生fixture，使用自有子窗口记录独立右键状态、单击/双击区别、双轴增量与实际接收屏幕点；viewport标记真实移动，由截图像素核对四向内容移动。另验证负屏幕坐标、无CS_DBLCLKS拒绝、旧左键权限不扩展、双击时间窗超出、双击末次释放失败和滚轮屏障失败。时间与失败注入明确标识，不冒充真实系统故障。

原有左键/过期帧/身份变化/部分发送回归保留，并增加未知投递分类。具体命令与证据见 [VALIDATION](VALIDATION.md)。真实WebView2的新鼠标动作、其他软件菜单/滚动处理、多屏DPI全组合、高权限与实际客户端加载均未由fixture推定通过。
