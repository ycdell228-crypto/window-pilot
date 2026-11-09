# 后台按键请求：明确能力边界

2026-11-09。交验后用户回复“继续”，按逐项确认流程本项随本次提交本地存档，未推送或部署。已接受的文字插入为 `6fd64c6`。

## 本项实现及没有实现的能力

`control_action` 新增独立请求 `action: press_key`，参数为 `keys`，与 set_value/type_text 的 value 不混用。例如：

```json
{"target_id":"窗口绑定","observation_id":"本次观察","control_id":"控件身份","action":"press_key","keys":["CTRL","A"]}
```

当前没有通过后台安全验收的 Windows 按键后端，因此所有合法 press_key 请求均明确返回：

```json
{"status":"rejected","effect":"not_sent","action_attempted":false,"error":"BACKGROUND_KEY_BACKEND_UNAVAILABLE","execution_method":null,"foreground_fallback":false}
```

**这是能力声明和拒绝契约，不是可用的后台快捷键实现，也不是证明所有应用都不可能后台按键。** 普通 Windows 键盘处理可能依赖焦点、线程键盘状态或全局状态；目前没有把任何 PostMessage 键序列认证为通用后台键盘。本项不会发送键盘消息、调用 SendInput、SetValue、EM_REPLACESEL，也不自动调用 foreground_action。

后台观察的每个控件新增 `background_actions.press_key`，明确 `status:refused`、`supported_keys:[]`、相同原因和无前台兜底。语法接受1至4个最长32字符的大写键名，语法合法不代表该键受支持。文字和按键参数混用、空序列、超长序列拒绝。

## 与已有保护的关系

公共调用仍需精确窗口绑定、observe_and_control、有效控件身份、新鲜单次观察及共享协调许可。明确拒绝会消费本次观察，但不建立未知输入故障；旧故障不会因尝试此请求而清除。执行端停止后仍拒绝请求。

拒绝发生在 Python 层输入后端之前，不启动动作 worker。`desktop_observation.sampled:false` 表示没有为这次未派发请求采样桌面，不伪造前后相同的诊断。审计只记录 key_count，不记录按键内容；派发准备记录亦不含键序列。返回 rejected 不等于动作成功。

明确前台键盘能力原样保留，必须由用户独立选择，不能作为后台失败兜底。浏览器实验适配器未增加按键，也未提前接入 MCP。

## 验证

- 普通回归 `CI=1 WINDOW_PILOT_NATIVE_TESTS=0 python scripts/test_runner.py`：54通过、0失败、17跳过入口；`.local/background-key-tests.txt`。
- 专项 `CI=1 WINDOW_PILOT_NATIVE_TESTS=1 python -m unittest discover -s tests -p test_background_keys.py -v`：3通过（2普通边界检查、1真实窗口集成检查）；`.local/background-key-native.txt`。
- 边界检查将输入工作进程、SendInput、PostMessage、SendMessageTimeout 和前台动作入口设为一旦调用即失败，验证 ENTER、CTRL+A、ALT+F4、LEFT、BACKSPACE 均不会触发这些路线。此为禁止副作用检查，不冒充真实按键效果测试。
- 原生检查读取自有标准 Edit，调用拒绝后重新观察，正文和选区不变；旧观察不可复用、没有未知故障，另一连接停止后请求被拒绝，审计没有 CTRL 键内容。没有对用户应用发送按键。
- 没有新增产品界面或截图需求；结果以协议回执、实际控件读回和副作用边界检查验证。

## 第2项仍未整体完成

可用的后台文字插入已单独验收；本项仅明确 Windows 按键暂不支持。后续仍需核对整值替换、点击、滚动的实际应用证据及后台拖拽支持/拒绝范围。整体验收不能把本项“拒绝测试通过”解释为“后台按键可用”；若用户需要某应用的具体快捷键，应单独验证应用专用后端，而不是悄悄转真实键盘。
