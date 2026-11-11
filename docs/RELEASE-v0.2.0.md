Window Pilot v0.2.0 为 Codex、DSH 等 MCP 客户端提供 **19 项工具**，用于指定 Windows 窗口和独立无头浏览器的观察与操作。本版本为预发布，支持范围以已验证的应用与场景为准。

## 相对 v0.1.0 的完整变化

本次以旧标签 `b60cfa55c17fd361330ce1d12df075f4cfcc2720` 为基准对比源码，包含从 v0.1.0 发布后累积的改进。

| 方面 | v0.1.0 | v0.2.0 |
| --- | --- | --- |
| MCP 接口 | 13 项工具 | 19 项；新增 `get_window_state`、`input_control`、窗口三步工具和 `browser_session`，共6项 |
| 窗口观察 | 截图与控件树分别调用 | 统一读取入口，可选截图/控件/文字，增加有界值、正文、选区及焦点/选择信息；组合读取仍非原子快照 |
| 关联窗口 | 基础枚举及精确绑定 | 按 owner 链发现关联窗口、报告可能阻塞状态；不自动继承绑定或权限 |
| 后台文字输入 | 既有 UIA set_value 路线 | 标准 Win32 Edit 原生整值替换/清空，以及光标或选区处插入；整值与插入语义分开 |
| 后台输入保护 | 身份、几何、单次观察、租约及未知故障保护 | 加入前台目标/同进程/窗口族拒绝、派发时复核和逐动作能力提示；WPF 后台设值拒绝 |
| 输入停止 | 操作权协调与未知故障恢复 | 新增执行端共享 stop/status/resume、在途取消、停止回执归属保护，覆盖空闲浏览器及进程树清理 |
| 浏览器 | 无浏览器会话接口 | 独立无头 Chrome、本地 HTTP 精确 origin、表单设值/点击、连接归属、未知结果锁定及专属 Job 清理 |
| 应用/站点访问 | purpose 任务描述与操作范围 | 服务端 grant 可限定应用/站点、期限和撤回；默认兼容模式，purpose 仍不是授权凭证 |
| 程序启动 | 已有管理员 launch_app | 新增操作人可配置的启动开关和规范路径白名单 |
| 本地证据 | 已有截图与审计 | 新增截图数量/容量/期限与审计轮转，保留启动去重回执 |
| 安装与构建 | 主要按源码接入 | wheel 完整运行资源、pipx/venv 安装路径、源码包完善、CI 普通结果摘要及隔离安装验证 |
| 验证记录 | 发布时普通27通过、10个原生跳过入口 | 本次普通62通过、21个跳过入口，另有19工具安装验证与11项真实无头浏览器验证；原生与真实应用范围分别说明 |

DSH/Codex 双宿主、独立授权的前台键盘与拖拽、跨连接窗口操作权、恢复证据准备、前台操作期间外部输入让路，均已在 v0.1.0 提供。v0.2.0 保留并衔接这些能力，不把它们重复计作新增。

部分变化是兼容性收紧：过去可尝试的 WPF/UIA 后台设值路径现拒绝，标准 Edit 使用已限定的原生路线。后台按键和后台拖拽仍没有可用后端；新增请求与拒绝契约不表示动作已经可用。

## 重点更新

- **Windows 三步流程**：`begin_window_session` → `act_and_observe` → `end_window_session`。选择并观察窗口，执行一次动作并返回新状态，最后结束会话；低层绑定、观察和操作接口继续保留。
- **浏览器 MCP 会话**：`browser_session` 提供 begin / step / observe / end / status。使用独立无头 Chrome，在明确允许的 `http://127.0.0.1:端口` 站点设值或点击，不接管用户浏览器、登录状态或配置目录。
- **共享停止与进程清理**：会话仅所属连接可用，执行端共享停止；断连或停止关闭自有浏览器进程，专属 Windows Job 清理进程树。未知输入按精确 origin 锁定，不自动重放或换连接绕过。
- **应用访问策略**：可配置应用路径或站点、授权期限及撤回。purpose 仅为任务说明；默认 `legacy_task_scope` 保持兼容，严格 `enforced` 模式需要操作人配置 grant。
- **安装与版本一致性**：Python 包、MCP 版本和 DSH 插件标识统一为 0.2.0，wheel 包含三个浏览器 mjs 运行资源；普通测试默认跳过桌面输入。

既有窗口截图、UIA 控件和有界文字读取、标准 Win32 Edit 整值替换与选区插入、后台点击与滚动，以及独立授权的前台交互继续保留。

## 获取与安装

本页 Assets 的 **Source code (zip / tar.gz)** 对应冻结的 `v0.2.0` 标签。需要交互式 Windows 10/11 和 Python 3.12+，下载源码后在 PowerShell 中运行：

```powershell
.\scripts\build-wheel.ps1 -Python python
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --no-index .\dist\window_pilot-0.2.0-py3-none-any.whl
```

本次不提供 PyPI/npm 包或预构建安装附件。浏览器默认关闭；启用需自行准备 Node、Playwright、Chrome，配置绝对路径及精确允许的本地 HTTP origin。

[版本 README](https://github.com/ycdell228-crypto/window-pilot/blob/v0.2.0/README.md) · [安装指南](https://github.com/ycdell228-crypto/window-pilot/blob/v0.2.0/docs/INSTALL.md) · [Codex](https://github.com/ycdell228-crypto/window-pilot/blob/v0.2.0/docs/CODEX.md) · [DSH](https://github.com/ycdell228-crypto/window-pilot/blob/v0.2.0/docs/DSH.md) · [浏览器接入](https://github.com/ycdell228-crypto/window-pilot/blob/v0.2.0/docs/BROWSER-MCP.md) · [应用授权](https://github.com/ycdell228-crypto/window-pilot/blob/v0.2.0/docs/APPLICATION-AUTHORIZATION.md)

## 验证与使用范围

- 发布前普通回归：62 通过、0 失败、21 个跳过入口；跳过不算通过。
- 全新安装 wheel：19 工具契约、隔离 worker 导入、普通模式拒绝程序启动通过；已安装 wheel 的真实无头浏览器测试 11 项通过。
- 本轮功能交付已有 5 案崩溃清理、真实管理员命名管道与独立本地表单任务证据；这些不是本次版本号调整后重新跑过的整套原生桌面测试。
- 独立本地表单任务为 7.875 秒、255 次采样，目标前台/可见窗口命中为 0；鼠标坐标变化 30 次来源未知。结论限该场景，不能泛化任意应用或整个测试期间。
- 先前曾误启动包含前台输入的原生测试，实际桌面影响未完整记录；事故记录保留，后续独立测试不抵消这次事故。

后台按键、后台拖拽及 WPF 后台设值仍拒绝执行。浏览器未知 origin 故障目前没有自动恢复入口，必须检查实际效果，不得用重启或新会话绕过。管理员执行端信任能够访问管道的同账户、同会话进程，访问策略不是同账户恶意程序隔离层。

源码发布不代表已有安装自动升级。更新前核对自己的源码、配置和执行端；安装后以 `health.version`、源码摘要及 19 工具声明确认实际版本。

[交付与验证边界](https://github.com/ycdell228-crypto/window-pilot/blob/v0.2.0/docs/DELIVERY-2026-11-11.md) · [后台能力](https://github.com/ycdell228-crypto/window-pilot/blob/v0.2.0/docs/BACKGROUND-INPUT-REVIEW.md) · [版本 CI](https://github.com/ycdell228-crypto/window-pilot/actions)

v0.1.0 标签和历史源码包保留不变，仍对应其 13 项工具。项目采用 [MIT License](https://github.com/ycdell228-crypto/window-pilot/blob/v0.2.0/LICENSE)。
