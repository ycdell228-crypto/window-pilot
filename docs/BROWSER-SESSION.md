# 浏览器三步会话封装：已验收

日期：2026-11-10（Asia/Shanghai）。从已发布源码11820ae建立独立副本 browser-integration，分支feat/browser-integration。用户明确“验收通过，继续”，本项获准本地存档；没有改生产源码、配置或执行端。

用户本阶段要求继续浏览器接入、完整无干扰验收、授权流程和后续部署；建议常用调用收敛为观察、操作并观察、结束。本小项落实浏览器适配器层的流程封装，为后续MCP接入做准备，不代表MCP已经接通。

## 调用行为

- `BrowserSession.begin({url,purpose})`：启动专属无头浏览器并返回首次状态；失败时关闭会话。当前仍仅允许指定127.0.0.1端口的HTTP同源页面，不接管用户浏览器或配置目录。
- `step({control_id,action,value})`：内部使用最近观察凭据，执行一次动作，再只读观察。调用方仍必须使用返回状态中的控件ID，不会把旧ID自动映射到新控件。动作结果与观察状态分别返回，`effect_verified:false`，不把新截图当作成功证明。
- `end()`：终止会话、关闭专属浏览器，可重复调用；结束后拒绝观察和输入。`withBrowserSession(options,task)` 用finally保证回调抛错也清理。
- `observe()`：保留只读诊断入口。未知输入或后续观察失败锁定会话输入；重新观察不会解锁，更不会自动重复动作。原始adapter低层接口保持不变。

会话操作串行；结果未知后仍可尝试一次只读观察，若失败保留原动作结果和`state:null`。不自动重启、不改用前台、不恢复用户浏览器。

## 实测

使用本机Chrome和已安装Playwright运行 `node scripts/accept-browser-session.mjs`：真实本地表单填值、单次提交、服务器记录及页面结果一致；effect_verified保持false；真实慢导航触发unknown后禁止第二次输入、服务端仅收到一次；后续观察失败没有丢掉unknown；重复结束和回调异常清理均验证专属进程退出。

证据：`.local/browser-session/run-1794305367721/results.json`、before.png、after.png。已查看after.png，显示输入值background和页面结果saved:background。

原适配器回归 `node scripts/accept-browser-background.mjs` 通过，证据在 `.local/browser-form/run-1794305392688`；覆盖旧凭据、密码拒绝、跨源阻断、未知不重放、执行中取消和进程退出。本轮没有运行桌面采样，不宣称完整无干扰验收通过。截图和本机回执不进入Git。

## 接下来仍需实现

MCP工具与Python/Node通信、共享执行端停止及输入互斥、连接归属、断线/进程崩溃清理、授权生命周期及依赖安装均未由本封装完成。这里的finally只保证调用栈异常清理，不保证宿主崩溃清理；purpose仍非用户授权凭证。

Windows窗口的自动绑定、租约及三步封装也未在此小项实施。上述剩余需求保留，不能用浏览器专属会话替代通用窗口流程或完整验收。
