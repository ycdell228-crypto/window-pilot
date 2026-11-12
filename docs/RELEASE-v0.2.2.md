Window Pilot v0.2.2 精简生产工具集，并增加指南可读状态。此版本为正式发布，默认提供 **15项生产 MCP 工具**，保留显式兼容与开发自测配置。

## 主要变化

- `health.guides_available`检查服务端全部四份指南是否实际可读、UTF-8有效且非空；缺失或读取失败报告false。它不表示模型已经读过指南，不增加“必须读过才能调用”的代码门。
- `launch_test`／`close_test`默认不再列出且拒绝调用。仅操作方显式配置`tools.self_test=true`时启用；关闭状态下直接Service调用也拒绝，连接清理仍能处置自身已创建的fixture。
- 默认从`get_window_state`选择截图、控件或组合读取，不再公开重复的`observe`／`observe_controls`。内部实现保留，恢复成功回执按所选工具集返回可调用的新观察入口；仍要求新鲜单次证据，禁止重放输入。
- 默认schema文本从5,720减至5,041字符（约11.9%），完整工具定义从11,442减至9,986字符（约12.7%）。保留工具的参数、枚举、长度和数值边界未删除，仅省略语义冗余的空required数组。字符数按紧凑JSON计算，不是计费token、缓存或模型成功率实测。
- Python包、MCP报告版本、DSH插件元数据、安装示例和CI wheel路径统一为0.2.2。

## 升级兼容配置

**已有客户端直接调用旧观察工具时，升级前请设置`tools.profile="legacy"`，并在部署后重连。** 未配置tools字段的旧安装升级后会采用新的15项默认生产集。

默认配置：

```json
{"tools": {"profile": "compact", "self_test": false}}
```

兼容旧观察接口的生产配置：

```json
{"tools": {"profile": "legacy", "self_test": false}}
```

| 配置 | 工具数 |
|---|---:|
| compact，自测关闭（默认） | 15 |
| legacy，自测关闭 | 17 |
| compact，自测开启 | 17 |
| legacy，自测开启 | 19 |

旧观察入口在compact下会明确拒绝；工具调用不能自行更改服务端开关。profile及self_test配置在连接建立时读取，非法值拒绝启动。常规用户使用`get_window_state(include_accessibility=false)`只截图，或`include_screenshot=false`只读控件；证据ID分别位于screenshot和accessibility中。

## 验证与边界

- 普通回归 **69通过、0失败**，22个原生／浏览器跳过入口；真实stdio验证四种工具配置和隐藏入口拒绝。
- 真实文件验证四份指南分别缺失、恢复、空白、无效UTF-8及目录冒充文件的状态。
- 自有Windows窗口专项1/1通过：截图／控件／组合读取、一次后台点击、恢复不重放、返回的新观察调用可用；计数保持1。指南不可用时health和状态查询仍可用。
- wheel干净安装验证默认15工具、4指南读取、普通模式管理员启动拒绝及隔离worker入口。开发配置下的已安装wheel验证17工具、health状态、真实自有窗口截图及49个UIA节点；未发送输入。

本次没有扩大管理员IPC、真实宿主缓存刷新、浏览器任务或任意第三方应用兼容性验证。后台按键、拖拽及WPF后台设值等既有限制保留。完整证据范围见[交验与配置说明](https://github.com/ycdell228-crypto/window-pilot/blob/v0.2.2/docs/TOOL-SURFACE.md)。

## 获取与安装

本页 Source code (zip / tar.gz) 对应冻结的`v0.2.2`标签；无额外二进制或媒体附件，未发布到PyPI／npm。需要交互式Windows 10/11与Python 3.12+：

```powershell
.\scripts\build-wheel.ps1 -Python python
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --no-index .\dist\window_pilot-0.2.2-py3-none-any.whl
```

源码发布不会自动升级本机。已有执行端需备份、部署并重连后才使用新工具集，不复用旧token、帧或状态ID。v0.2.1及更早标签和下载包保持不变。

[安装说明](https://github.com/ycdell228-crypto/window-pilot/blob/v0.2.2/docs/INSTALL.md) · [Codex接入](https://github.com/ycdell228-crypto/window-pilot/blob/v0.2.2/docs/CODEX.md) · [DSH接入](https://github.com/ycdell228-crypto/window-pilot/blob/v0.2.2/docs/DSH.md)
