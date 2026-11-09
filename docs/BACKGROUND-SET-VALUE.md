# Win32 整值替换后台验收失败与拒绝修复

后续独立路线交验见 [标准 Edit 原生整值替换](NATIVE-SET-VALUE.md)。下文是 UIA.ValuePattern 路线失败与拒绝的历史记录；不表示 WM_SETTEXT 路线也已失败。

2026-11-09。基于鼠标小项存档 `a1e0564` 的隔离开发；交验后用户回复“继续”，接受本修复并授权本地存档，未发布或部署。

## 发现与修复

自有标准 Win32 Edit 的 UIA.ValuePattern.SetValue 确实将整个值改为指定文字，但动作前目标非前台、动作后目标成为前台；真实光标位置未变。执行端返回 `unknown / UIA_BACKGROUND_TARGET_IN_USE`，未重复发送。快照不证明焦点变化的因果，但该路线没有满足后台验收要求。

现在观察能力提示与动作工作进程均拒绝 Win32 框架的 `set_value`，返回 `UIA_BACKGROUND_WIN32_SET_VALUE_REFUSED`、`action_attempted:false`、`effect:not_sent`。只读、密码等原有优先拒绝保留；现有 WPF 拒绝不变。不自动改用 EM_REPLACESEL、鼠标、键盘或前台输入。文字插入的独立 EM_REPLACESEL 路线不变。

此为有意收紧：拒绝覆盖 Win32 框架，不仅单个测试 Edit；其他提供方仍未得到后台安全认证。当前没有通过验收的通用 Windows 整值替换路线，浏览器独立无头适配器的 fill 是另一条尚未接入 MCP 的能力。

## 验证

- 普通测试：55通过、0失败、18个跳过入口，`.local/background-set-value-tests.txt`。
- 修复后原生专项：1通过。独立 WM_GETTEXT 验证原值不变；非空/清空请求均拒绝，能力缓存被清空也不能绕过工作进程检查；旧观察不可复用，未形成未知故障，审计不含输入正文。见 `.local/background-set-value-refusal-final.txt` 和 `.local/background-set-value/set-value-effects.json`。
- 文字插入回归：2通过，含实际插入、选区替换和光标变化拒绝；见 `.local/background-set-value-insertion-regression.txt`。
- 首次实际派发失败保留于 `.local/background-set-value-native-desktop.txt` 和 `.local/background-set-value/failed-provider-effects.json`。中间拒绝错误码被脱敏为通用错误的失败保留于 `.local/background-set-value-refusal.txt`，已将明确拒绝码加入允许列表后复验通过。
- 沙箱没有交互桌面的首次运行只跳过，不算原生通过。证据均不进入 Git；本项无新界面，使用独立文本读取作为效果证据。

## 后续

本小项修复已暴露的后台边界，不代表整值替换能力完成。按键、拖拽仍拒绝；Windows 输入的实际应用兼容性与无干扰整体目标仍未完成。须先验收本小项，再按小项推进；不提前触发发布和插件升级对话。
