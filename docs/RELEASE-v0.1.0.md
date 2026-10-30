Window Pilot 首个 GitHub 预发布，供 DSH 与 Codex 用户试用。版本 `v0.1.0`，源码提交固定为 [`b60cfa55c17fd361330ce1d12df075f4cfcc2720`](https://github.com/ycdell228-crypto/window-pilot/commit/b60cfa55c17fd361330ce1d12df075f4cfcc2720)。本版仍需按具体应用验证兼容性。

### 最新开发文档

main后续开发已增加证据保留策略、可选程序启动限制及wheel/pipx安装路径，见[10月30日改进](https://github.com/ycdell228-crypto/window-pilot/blob/main/docs/REVIEW-FIXES-2026-10-30.md)和[最新安装说明](https://github.com/ycdell228-crypto/window-pilot/blob/main/docs/INSTALL.md)。这些后续改动不在本页v0.1.0标签及自动源码包中；本页下列版本能力与27项普通检查仍仅对应冻结版本，不能用main的38项检查替代。

本标签及自动源码包保留发布时快照；后续文档整理不移动标签，也不代表功能或本机部署升级。接手开发请先读 main 分支的[当前开发规则](https://github.com/ycdell228-crypto/window-pilot/blob/main/AGENTS.md)与[发布和历史文档入口](https://github.com/ycdell228-crypto/window-pilot/blob/main/docs/OPTIMIZATION-SUMMARY-2026-10-29.md)，不要把历史隔离目录、待审/未发布措辞或旧代验收流程当成当前任务授权。下列版本功能、验证及安装链接仍对应 v0.1.0。

### 可用能力

- DSH 原生插件与 Codex 标准 stdio/bridge 接入，共享 13 项 MCP 工具及标准 text/image 内容。
- 精确窗口绑定、窗口截图、UIA 控件观察及 Invoke/SetValue/Select/Expand/Collapse/Scroll 操作；动作绑定新鲜观察，操作后重新确认效果。
- 定向后台左键、右键、双击与双轴滚轮；独立明确授权后的前台激活/点击、快捷键、Unicode 文字和有界拖拽。
- 同一执行端内跨连接的窗口操作权、观察版本与未知结果恢复门禁。独立执行端与人工输入不属于该协调域。

### 本轮三项优化

1. MCP 初始化公共说明由 **5555 减至 2102 字符**，保留授权、观察和未知结果边界。这是字符测量，不代表真实宿主或模型 token 节省，不能按 13 项工具重复相乘。
2. `window_control(operation="prepare_recovery")` 集中获取操作权、准备新证据和后续恢复调用建议；宿主审查后显式恢复，未知输入不自动重放，准备或观察不会自动清除故障。
3. 明确前台动作期间监听外部键鼠，检测后停止后续输入，并按所有权与精确左右键清理本次持有输入。不会吞事件、阻止人工输入或抢回焦点，同桌面仍有竞态。

### 验证范围

- 发布基准的普通检查：**27 项通过、0 失败，另 10 个原生跳过入口**；跳过不算通过。[GitHub Actions：Windows tests](https://github.com/ycdell228-crypto/window-pilot/actions/runs/40883741937) 已完成且结果为 success。
- 沿用已审查记录：恢复 8 项与协调 5 项、受控外部干扰 6 项及后续 4 项针对性补验。具体版本、历史失败与限制见[优化汇总](https://github.com/ycdell228-crypto/window-pilot/blob/v0.1.0/docs/OPTIMIZATION-SUMMARY-2026-10-29.md)及[验证记录](https://github.com/ycdell228-crypto/window-pilot/blob/v0.1.0/docs/VALIDATION.md)。本次发布没有重跑桌面输入测试；这些不同轮次不合并冒称完整原生覆盖。
- 外部事件使用受控 `SendInput`，不是人类硬件验收。真实宿主端到端输入、完整管理员 IPC 输入流程及广泛第三方兼容性未获全面验证。

### 安装与升级

需要交互式 **Windows 10/11、Python 3.12+**（`pyproject.toml` 要求 `>=3.12`）。从本页 Assets 下载 GitHub 自动生成的 **Source code (zip)** 或 **Source code (tar.gz)**；本次仅提供源码，没有额外安装包或 exe。

- [README：运行与依赖准备](https://github.com/ycdell228-crypto/window-pilot/blob/v0.1.0/README.md)
- [DSH：插件安装、接入与回退](https://github.com/ycdell228-crypto/window-pilot/blob/v0.1.0/docs/DSH.md)
- [Codex：配置预览与接入](https://github.com/ycdell228-crypto/window-pilot/blob/v0.1.0/docs/CODEX.md)
- [管理员服务：安装预览、停止与回退](https://github.com/ycdell228-crypto/window-pilot/blob/v0.1.0/docs/ADMIN_SERVICE.md)

文档中的作者本机路径须替换成自己的路径；历史“待审/未发布”字样是当时验收快照，三项优化的最终接受记录见决策 WP-NEXT-016。下载或更新源码不会自动升级、重启服务或重连本机 DSH/Codex；部署前先审阅接入与回退说明，避免直接覆盖正在运行的源码。

### 已知限制

同桌面输入仍存在检查到注入/释放之间的竞态，不能保证完全隔离。UIA 提供方可能自行激活窗口；第三方控件、DPI、输入法及具体应用都需另行验证。截图成功或消息投递成功不等于实际效果；未知结果必须先检查证据，不自动重试。跨连接协调限于同一执行端，现有验证范围不代表所有应用或所有宿主流程均已通过。
