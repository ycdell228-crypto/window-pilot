# 第六项交验：独立无头浏览器适配器与本地表单实跑

2026-11-09。用户指定“浏览器：本地测试页面填写表单”，随后明确“第六项验收通过，存档并继续”。本项随本次提交本地存档，未部署或接入 MCP；第五项已存档为 `7d6451a`。

## 已实现

`scripts/browser-background.mjs` 导出 `BackgroundBrowser`，复用 Playwright 的真实 Chromium 后台接口。固定 `headless:true`，启动独立浏览器和新 context，不使用用户配置、cookies、标签页或现有 CDP 端点。没有 headed、UIA、真实鼠标键盘或前台兜底路线。

- `open({url,purpose})`：只接受显式端口的 `http://127.0.0.1` 站点。purpose 是任务描述，不是授权凭证。HTTP 页面请求仅允许初始 origin；全部 30x 重定向拒绝，WebSocket、service worker、下载和新页面不作为操作路线。该范围控制不是恶意页面或浏览器漏洞的系统安全沙箱，也不声称禁止浏览器自身全部网络活动。
- `observe()`：页面截图、最长8192字符正文、最多128个普通 HTML 表单控件。控件值最多2048字符，密码值不返回。截图与 DOM 分开读取，明确非原子；截图不是隐私打码。返回一次性 observation_id/control_id。
- `act({observation_id,control_id,action,value})`：支持 `set_value` 整值替换和 `click`。使用观察时保存的 ElementHandle；校验当前控件描述、连接状态、页面 origin/导航 epoch、30秒有效期，不用选择器重新寻找替代控件。输入前消费观察，动作后必须重新观察核实结果。
- `set_value` 使用 Playwright ElementHandle.fill，适用于本项支持的普通文本 input/textarea；不冒充 type_text。点击仅支持 button 和有限按钮/勾选 input。密码、只读、禁用、未支持类型拒绝；select、复杂编辑器、iframe/shadow DOM、按键和拖拽不在本项能力内。
- 派发之后出错返回 unknown 并锁定该实例后续输入；不重试、不自动重建浏览器、不重放。派发前拒绝返回 not_sent。只读观察本身不清除故障。
- `stop()` 为幂等、终止式停止，可在操作执行中调用，关闭自有 BrowserServer，超过清理期限才调用其 kill；对象不能恢复或重新打开。已送到网站的请求无法撤销。此接口没有调用共享执行端的 `input_control`。

独立适配器先形成可验收基线，避免在共享协调、资源打包和停止联动未完成时直接公布新 MCP 工具。当前 Python 服务、现有窗口能力和部署均不变。

## 真实流程与验证

运行本机 Chrome `156.0.8078.80`、Node `24.22.1`、Playwright `1.62.1`；未安装依赖。验收入口 `scripts/accept-browser-background.mjs`，复用适配器本身，不用假的浏览器结果。

流程：观察本地 HTTP 表单 → 替换姓名 → 重新观察并检查备注未变 → 替换备注 → 重新观察 → 点击保存 → 从服务器实际收到的 POST 和渲染页面双重核实。

结果：服务器恰好收到一次 `{name: "后台用户", note: "用户可继续使用前台电脑"}`，页面显示同样结果。验收还证明：

- 旧凭据不能再次输入，密码值不读出且密码输入不派发。
- 另一个本地 origin 的直接图片请求及 302 重定向请求均未到达目标服务器。
- 实际导航请求发出但服务器不响应时，动作超时返回 unknown，后续重试被拒绝，服务端请求数仍为1。
- 独立取消案例在请求发出且动作仍执行中调用 stop，结果为 unknown，自有浏览器主进程退出，停止对象不再接受打开/观察/输入。
- Windows 交互桌面只读采样152次：目标浏览器主 PID 成为前台0次、可见顶层窗口0次；光标变化50次。该数字不识别变化来源，不等同用户持续打字的完整证明；采样范围是主 PID，不覆盖所有子进程或采样间隙。适配器的无头执行路线不调用真实桌面输入 API。
- 项目普通回归51通过、0失败、15跳过入口；见 `.local/browser-background-regression.txt`。本项独立端到端验收一套通过，不能与普通单测数量混算。

最终实跑证据：`.local/browser-form/run-1794208924870/` 中的 `before.png`、`after.png`、`results.json`、`desktop.json`；命令回执 `.local/browser-background-desktop-final.txt`。图片已实际查看，显示两字段及保存回执。首次运行因 label 尾部空格使测试无法定位控件，修正为 trim 后重跑；失败输出保留于 `.local/browser-background-first.txt`。

复现（PowerShell，需本机 Node、Playwright、Chromium；路径通过环境变量显式提供）：

```powershell
$env:WINDOW_PILOT_PLAYWRIGHT = '<已安装 playwright 包目录>'
$env:WINDOW_PILOT_BROWSER = '<chrome.exe 或兼容 Chromium 路径>'
$env:WINDOW_PILOT_PYTHON = '<python.exe 路径，启用 Windows 桌面只读采样>'
& '<node.exe 路径>' scripts/accept-browser-background.mjs
```

必须在交互桌面运行采样，沙箱无桌面结果不能当作桌面验收。所有运行证据均写入 `.local/browser-form/`，不入 Git；本项脚本未加入 Python wheel，不要求生产环境安装 Node。

## 下一步与未完成项

这是实际浏览器中的后台表单流程，不是既有前台浏览器窗口的无损接管。无法直接复用用户登录状态；仅本地可信表单和上述动作得到本次验证。尚未接入 MCP、跨连接协调、统一 input_control、可信应用授权生命周期或通用窗口模式，不能宣称 Window Pilot 整体后台目标完成。

原拟本项接受后优先做隔离浏览器模式的服务接入与共享停止联动；用户随后调整顺序，先完成后台输入能力及验证，见决策 WP-NEXT-026。接入前保持实验适配器独立，不把独立 stop 冒称共享停止已覆盖。其他 Windows 应用的 UIA/PostMessage 竞态与兼容性仍待后续处理。
