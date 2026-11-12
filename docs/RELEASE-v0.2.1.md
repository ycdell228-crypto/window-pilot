Window Pilot v0.2.1 精简工具描述，将 Windows 低层操作、恢复协议与浏览器流程改为按需读取。此版本为正式发布，保留 v0.2.0 的 **19 项 MCP 工具及参数**。

## 本次更新

- 工具描述与公共说明保留硬约束；精确目标、独立授权、新鲜单次证据、未知停输、禁止重放及前台兜底等规则继续适用。输入执行逻辑未改。
- DSH 原生插件在宿主提供 skills 服务时注册 `window-pilot` 技能，目录只展示短简介；正文与恢复／浏览器引用按需加载，停用插件撤销注册。
- Codex 等 MCP 客户端可读取 `window-pilot://guides/SKILL.md`，再按任务读取 `references/windows.md`、`references/recovery.md` 或 `references/browser.md`。资源只交付指南，不执行输入或扩大权限。恢复／浏览器指南无法读取时停止对应操作。
- 源码包、DSH 插件及 Python wheel 包含同一份指南；安装示例、CI 与版本元数据统一为 0.2.1。

## 描述体积比较

与 v0.2.0 后续 main 基线 `7367be49c1aa45ddbed53f95c23248f7a923d67a` 比较，按本机 DSH 公共说明单次注入方式，工具描述＋公共说明由10,014字符减至5,462字符（减少45.5%）；按当前 Codex 每项工具重复附加公共说明并另计初始化说明的方式，由52,004字符减至20,662字符（减少60.3%）。

这是说明文本字符量比较，不是实际计费 token、缓存命中或任务成功率测试。未计不变的工具 schema、技能目录和资源发现成本；按需读取正文仍会占用后续上下文。宿主版本与工具暴露方式会影响实际收益。

## 验证与范围

- 普通回归 **63通过、0失败**，21个原生／浏览器入口跳过。
- 真实 stdio 验证4份指南列出与读取、任意文件路径拒绝、错误后协议连接可用。
- 本机 DSH 0.2.2-rc.1 的真实 Cordis／SkillRegistry 在隔离进程中验证技能注册、发现、正文和引用读取、注销。
- 0.2.1 wheel 在干净 venv 中安装，19工具、4指南读取、隔离worker入口与普通模式管理员启动拒绝通过。

没有重跑键鼠／浏览器原生任务、管理员IPC或真实DSH卡片加载；没有验证模型在真实会话中的指南选择效果。本版本不扩大原有后台应用兼容性或无干扰结论。v0.2.0 的功能与原生验证范围见[上一版本说明](https://github.com/ycdell228-crypto/window-pilot/blob/v0.2.0/docs/RELEASE-v0.2.0.md)，本项细节见[交验说明](https://github.com/ycdell228-crypto/window-pilot/blob/v0.2.1/docs/TOOL-GUIDES.md)。

## 获取与升级

本页 Source code (zip / tar.gz) 对应冻结的 `v0.2.1` 标签；不提供额外二进制附件，也未发布到 PyPI／npm。需要交互式 Windows 10/11 与 Python 3.12+，下载源码后运行：

```powershell
.\scripts\build-wheel.ps1 -Python python
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --no-index .\dist\window_pilot-0.2.1-py3-none-any.whl
```

已有执行端需按安装文档备份、部署、重启并建立新连接后才能使用精简描述；发布源码不会自动升级本机或当前会话。旧token、帧和状态ID不得复用。

[安装说明](https://github.com/ycdell228-crypto/window-pilot/blob/v0.2.1/docs/INSTALL.md) · [Codex接入](https://github.com/ycdell228-crypto/window-pilot/blob/v0.2.1/docs/CODEX.md) · [DSH接入](https://github.com/ycdell228-crypto/window-pilot/blob/v0.2.1/docs/DSH.md)
