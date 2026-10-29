# Codex stdio 接入与配置预览

Window Pilot 的 `serve` 与 `bridge` 都是按行 JSON-RPC 的 stdio MCP，和 DSH 共用13项工具及 text/image 交付。Codex 不需要安装 DSH 原生包。运行环境是同一用户的交互式 Windows 10/11、Python 3.12+；不是 WSL、云端或锁屏桌面。WGC/Pillow 依赖仍按 README 显式准备，PrintWindow 自有窗口验证无需第三方依赖。

配置字段依据 [OpenAI 官方 MCP 文档](https://developers.openai.com/codex/mcp/)（2026-10-28核对）：`mcp_servers`、`command`、`args`、`cwd`、`env`、`enabled` 和超时字段。官方支持用户级 `~/.codex/config.toml` 和项目级 `.codex/config.toml`；实际加载受本机版本、项目信任和管理员策略影响。生成 TOML 和协议通过不等于当前 Codex 已加载或模型已看见图片。

## 先预览，不修改配置

在本开发副本运行以下命令，将 Python 路径替换成当前存在的 `python.exe`：

```powershell
Set-Location D:\codex\000\window-pilot-next
# 只打印 TOML；示例配置默认 WGC，预览本身不启动捕获。
& 'C:\path\to\python.exe' -I -S -B scripts/preview-codex.py --python 'C:\path\to\python.exe' --config config.example.json
# 已自行审阅并准备本机配置时，使用 --config config.local.json。
# 只预览新版自己的管理员 bridge：
& 'C:\path\to\python.exe' -I -S -B scripts/preview-codex.py --python 'C:\path\to\python.exe' --mode bridge
```

脚本只读本项目路径、检查 Python 文件存在并打印配置；不额外启动所选 Python、不读写 Codex/DSH 配置、不连接管道、不安装/启动服务。`--python` 的版本须由操作者核验。默认服务名 `window_pilot_next`，可用 `--server-name` 更改，避免覆盖旧接入。Direct 配置文件必须存在且位于此开发副本内；相对路径也按此目录解析。

输出结构如下，实际路径以脚本输出为准：

```toml
[mcp_servers.window_pilot_next]
command = "C:\\path\\to\\python.exe"
args = ["-I", "-S", "D:\\codex\\000\\window-pilot-next\\scripts\\runtime_entry.py", "serve", "--config", "D:\\codex\\000\\window-pilot-next\\config.example.json"]
cwd = "D:\\codex\\000\\window-pilot-next"
enabled = false
startup_timeout_sec = 20
tool_timeout_sec = 30
[mcp_servers.window_pilot_next.env]
PYTHONUTF8 = "1"
PYTHONUNBUFFERED = "1"
```

入口用绝对路径与 `-I -S` 隔离 Python 用户路径，加载本副本 `src` 和可选 `.local/wgc-deps`；不依赖 PYTHONPATH、全局 pip 安装或调用方当前目录。stdout 只承载 MCP 协议，不应手动在终端交互运行此入口后等待界面出现。

## 模式、接入与回退

| 模式 | 执行位置与条件 | 边界 |
|---|---|---|
| direct（默认） | 普通 Python 直接托管服务；同一配置目录一条连接 | `launch_app` 仍声明但调用拒绝，不自动提权；高完整性目标输入拒绝 |
| bridge | 普通 stdio 转发到本副本 `.local/admin-service/service.json` 对应的已审阅管理员执行端 | 预览不证明清单、管道、权限或服务可用；缺少清单时明确提示尚不可启用；禁止复用原版清单、窗口 token 或帧 |

本轮不部署新版管理员执行端；若以后需要，先审阅 [ADMIN_SERVICE](ADMIN_SERVICE.md) 的具体任务、清单、安装与回退，再由用户决定。不要为验收普通 stdio 安装管理员任务。普通直连支持一个服务所有者；管理员端每条连接持有独立 token/帧，同一执行端共享窗口操作权、观察版本与未知故障门禁。输入前先获取操作权再新观察，流程及独立执行端边界见 [COORDINATION](COORDINATION.md)。

真正接入须另行明确执行：先备份选定配置，再将审阅后的完整服务表与 env 子表合并到选定作用域，确认无同名条目且路径全为新版，明确启用 `enabled = true`，按当前客户端要求重连/重启。只加入禁用表不会出现工具。核验 MCP 状态、13项工具及 `health.executor.mode`；首次只用本项目 fixture，不能用用户应用验证安装。不要直接把预览追加到现有文件末尾造成重复表。

回退：关闭该接入并重连，移除本次新增的服务表和 env 子表；如由备份恢复，先确认备份后没有其他有效修改。接入关闭使该连接 token/帧失效，不能重放动作。移除 bridge 配置不会停止独立管理员服务、删除任务或关闭用户应用；这些需要分别按已审阅服务方案处理。当前预览阶段无宿主配置需要回退。

## 最小验收与图片

正式客户端验收时，只用本项目工具：`launch_test → list_windows`，核对返回 PID 和 `WindowPilotFixture` 类，`bind_window(access="observe_and_click", purpose="用户授权自有窗口验收", capture_backend="printwindow") → observe`。确认实际看见目标及 `clicks=0`，按新帧在客户区 `(40,40)` 点击一次，再 observe 看到 `clicks=1`，最后 unbind/close_test。图片不可见、错误或超时则停止，不能补点或自动重绑。

`observe` 返回先 text 后 image 的标准 MCP 内容；text 含 frame_id、原始客户区尺寸、哈希及缩放，image 含 mimeType 和 base64。48 KB 有界预览继续兼容旧 DSH；原图仍在 `.local/frames`。预览坐标必须乘 `image_to_client_scale` 换算。投递成功仅为 `effect=unverified`，必须新图确认，不因元数据存在就声称模型看见或操作成功。

本地隔离检查（只创建/操作本副本 fixture，需交互式桌面）：

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'src'
& 'C:\path\to\python.exe' -B -m unittest discover -s tests -p test_codex_stdio.py -v
```

该检查解析实际生成的 TOML 并按原样启动 direct 入口，验证初始化、initialized 通知不产生多余响应、工具声明、health、真实窗口图片和一次点击后的新图/计数、清理及纯协议 stdout。另检查 DSH 使用的协议版本仍能协商。它是独立进程 stdio 验证，不是 Codex/DSH 客户端或管理员 bridge 端到端验收；可选 `WINDOW_PILOT_EVIDENCE_DIR` 只能指向此副本 `.local` 内，用于保留前后 PNG。
