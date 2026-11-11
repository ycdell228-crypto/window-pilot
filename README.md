# Window Pilot

让 Codex、DSH 等 MCP 客户端观察和操作指定的 Windows 窗口。

Window Pilot 提供窗口截图、控件与文字读取、后台点击和有限的后台文字输入，也支持独立授权的前台操作。模型通过 MCP 选择目标窗口、读取状态、执行动作，再观察结果，组成可核实的桌面操作流程。

[快速开始](#快速开始) · [Codex 接入](docs/CODEX.md) · [DSH 接入](docs/DSH.md) · [能力范围](docs/BACKGROUND-INPUT-REVIEW.md) · [版本发布](https://github.com/ycdell228-crypto/window-pilot/releases)

## 能做什么

| 能力 | 说明 |
| --- | --- |
| 选择目标窗口 | 枚举窗口、发现关联对话框，按窗口与进程身份精确绑定 |
| 观察窗口状态 | 获取客户区截图、UIA 控件树，以及有长度限制的值、正文和选区信息 |
| 后台鼠标操作 | 向目标窗口发送左键、右键、双击及横向、纵向滚动消息 |
| 标准输入框文字操作 | 对标准 Win32 Edit 替换整值、清空，或在观察到的光标与选区处插入文字 |
| 独立无头浏览器 | 在明确配置的本地 HTTP 站点完成表单操作，不接管用户浏览器 |
| 前台交互 | 独立授权后激活窗口、点击、输入文字、使用快捷键和拖拽 |
| 协调与停止 | 同一执行端内共享窗口操作权，跨连接停止输入，并为未知结果提供恢复流程 |
| 启动程序 | 管理员模式下启动用户指定的本地程序，可配置启动开关与路径白名单 |

截图限定在绑定窗口的客户区。后台输入会拒绝正在前台的目标、同进程窗口及同窗口族。每次输入使用新鲜的单次观察，动作后需要重新读取并确认效果。

## 快速开始

需要 **交互式 Windows 10/11** 和 **Python 3.12+**。

### 1. 获取源码并安装

在 PowerShell 中运行以下命令。

```powershell
git clone https://github.com/ycdell228-crypto/window-pilot.git
cd window-pilot
.\scripts\build-wheel.ps1 -Python python
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --no-index .\dist\window_pilot-0.1.0-py3-none-any.whl
```

pipx 安装、可选依赖和卸载步骤见[安装指南](docs/INSTALL.md)。

### 2. 准备配置

将以下内容保存为自己的配置文件，例如 `C:\path\to\pilot-data\config.json`。此配置使用 PrintWindow 截图，并关闭程序启动。

```json
{
  "window_control": {"capture_backend": "printwindow"},
  "app_launch": {"enabled": false}
}
```

默认 WGC 截图与大图预览需要额外依赖，安装方法见[安装指南](docs/INSTALL.md)。

### 3. 接入 MCP 客户端

由客户端托管以下 stdio 服务命令，使用自己的绝对路径。

```powershell
.\.venv\Scripts\window-pilot.exe serve --config 'C:\path\to\pilot-data\config.json'
```

- Codex 的配置、源码接入和重连步骤见[Codex 接入](docs/CODEX.md)。
- DSH 的原生插件安装和连接方式见[DSH 接入](docs/DSH.md)。
- 需要处理管理员窗口或启动程序时，按[管理员服务指南](docs/ADMIN_SERVICE.md)审阅并安装独立执行端。

## 典型操作流程

常规窗口任务使用 `begin_window_session` → `act_and_observe` → `end_window_session`：选择并观察窗口、执行一次动作并返回新状态、结束会话。底层绑定、租约和观察接口继续保留。详见[窗口流程](docs/WINDOW-WORKFLOW.md)。

浏览器使用 `browser_session` 的 `begin` → `step` → `end`，另有诊断 `observe` 和 `status`。默认关闭，启用条件与本地站点范围见[浏览器接入](docs/BROWSER-MCP.md)。

普通权限模式直接运行 stdio 服务。管理员模式通过普通权限 bridge 连接同用户、同会话的管理员执行端。实际权限与服务状态可通过 `health` 查询。

<details>
<summary>查看 19 项 MCP 工具</summary>

| 工具 | 用途 |
| --- | --- |
| `health` | 查看执行端、权限和服务状态 |
| `list_windows` | 枚举窗口及目标的关联窗口 |
| `bind_window` / `unbind_window` | 绑定或解除一个目标窗口 |
| `get_window_state` | 按需获取截图、控件树、文字和关联窗口信息 |
| `begin_window_session` / `act_and_observe` / `end_window_session` | 常规窗口三步流程 |
| `browser_session` | 独立无头浏览器会话 |
| `observe` / `observe_controls` | 分别读取截图或控件树 |
| `click` | 后台点击、双击与滚动 |
| `control_action` | 控件操作及受支持的整值替换、文字插入 |
| `foreground_action` | 显式前台鼠标与键盘操作 |
| `window_control` | 获取、续期和释放操作权，准备与确认恢复 |
| `input_control` | 停止输入、查询停止状态和明确恢复 |
| `launch_app` | 启动用户指定的本地程序 |
| `launch_test` / `close_test` | 启动或关闭项目自有测试窗口 |

</details>

## 使用范围与权限

- **后台支持取决于应用和控件。** 标准 Win32 Edit 支持整值替换与选区插入。后台按键和拖拽目前拒绝执行，WPF 后台设值也拒绝执行。独立无头浏览器已接入 MCP，仅支持明确允许的本地 HTTP 站点。具体支持项见[后台能力清单](docs/BACKGROUND-INPUT-REVIEW.md)与[浏览器说明](docs/BROWSER-MCP.md)。
- **窗口操作需要验证实际效果。** UIA 提供方可能自行激活窗口，截图与控件读取也分开进行。当前验证覆盖自有测试窗口和有限场景，真实应用的普遍兼容性与连续无干扰仍待验证。结果未知或只执行了一部分时，应停止并检查新证据。本轮支持的无头本地表单任务、生产命名管道验证及测试事故边界见[2026-11-11交付记录](docs/DELIVERY-2026-11-11.md)。
- **管理员模式具有管理员权限。** 执行端信任能够访问管道的同账户、同会话进程。`purpose` 只描述任务；可配置精确应用或站点、期限及撤回策略，默认兼容模式不表示已验证人类授权。见[应用授权](docs/APPLICATION-AUTHORIZATION.md)及[管理员信任与权限边界](docs/ADMIN_SERVICE.md)。
- **截图与审计保存在本地。** 保留数量、容量和期限可配置，详情见[证据保留策略](docs/RETENTION.md)。

## 文档与开发

[安装指南](docs/INSTALL.md) · [窗口绑定](docs/GENERIC_WINDOWS.md) · [UIA 控件操作](docs/UIA_ACTIONS.md) · [鼠标操作](docs/MOUSE_ACTIONS.md) · [前台操作](docs/FOREGROUND.md) · [协调与恢复](docs/COORDINATION.md) · [输入停止](docs/INPUT-STOP.md)

开发约定见 [AGENTS.md](AGENTS.md)，设计演进见[决策记录](docs/decisions-dsh-codex.md)。GitHub Actions 执行普通回归和 wheel 安装验证，原生桌面输入的证据与范围见[验证记录](docs/VALIDATION.md)。

## 许可证

采用 [MIT License](LICENSE)。参考项目与第三方归属见 [NOTICE](NOTICE.md)。
