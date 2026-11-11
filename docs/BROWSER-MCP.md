# 浏览器 MCP 接入

2026-11-11，隔离副本 browser-integration，基于通信基础 e97b9ce。实现与独立测试已完成，用户随后授权存档并更新既有 GitHub 仓库，见 WP-NEXT-042；安装、部署及验证边界见[交付记录](DELIVERY-2026-11-11.md)。

新增browser_session一个MCP工具（总数19），operation为begin/step/observe/end/status。begin返回session_id及页面状态，step使用返回的control_id执行一个动作再返回新状态；图片提升到MCP顶层，effect_verified始终false。保留既有Windows三步工具及低层接口。

默认禁止启动浏览器；宿主 config.json 需要 browser.enabled:true，node、executable、playwright 三个绝对路径和 allowed_origins 数组，例如 http://127.0.0.1:端口。仅允许指定本地 HTTP 同源，不接管用户浏览器、配置目录或登录状态。purpose 仅任务说明，不作为用户授权证明；期限与撤回见 [应用授权](APPLICATION-AUTHORIZATION.md)。

会话 ID 仅所属 Service 连接可使用；同连接请求串行。共享 Coordinator 追踪浏览器在途调用并排斥前台输入；input_control.stop 通知所有已注册浏览器关闭 stdin，包括空闲会话。resume 等待在途调用结束及专属 Job 进程树清理完成，且不重启旧会话。停止回执的 created_by_this_call 表示是否由本次调用新建停止；重复请求不能据此认领其他调用创建的停止。

step发生通信未知或返回动作unknown时，在共享执行端按精确origin记录故障。重新观察、结束、换连接、恢复停止均不清除此故障，也不可新开同站点会话绕过；本项尚无浏览器故障恢复入口。页面/服务器实际效果必须由人核实，不自动重放或重启。浏览器停止会关闭会话，因此停止后不能继续观察该浏览器页面；Windows低层只读观察规则保持不变。

连接dispose通知所有自有工作进程关闭，然后等待清理；超时仍报告pending_unverified。Windows专属Job在任何浏览器请求前绑定Node，启用kill-on-close；拥有者崩溃会终止该Job后代，Node退出后也清理残留后代，查询active=0才确认cleanup_complete。没有附加到用户浏览器。恶意本地页面安全边界、真实任意网站和生产IPC不能由这些机制自动推断通过。

worker/session/background 三个 mjs 资源加入源码包和 wheel，外部 Node/Playwright/Chrome 仍需宿主提供，不自动下载安装或改配置。独立测试由 GPT-6.1-sol 子智能体完成，证据放 .local/browser-mcp-test/ 与 .local/final-verification/。

## 实现完善与独立证据

按用户“全做完再验收”的新要求，MCP接入与其他阶段统一交验。已解决测试发现的同origin检查竞态及结束8次后容量耗尽：站点故障检查与准入同锁、同站点操作互斥；退出会话移入有界墓碑，保留end幂等，容量只计算活跃会话。

授权期限、撤回和宿主维护grant见APPLICATION-AUTHORIZATION.md。严格模式为enforced，缺省legacy_task_scope保持旧安装兼容，不能称为已验证人类授权。

真实崩溃清理5案通过，证据`.local/browser-crash-test/results.json`：正常EOF、杀Node、杀Job拥有者Python、Chrome出现前EOF、Chrome出现且begin尚未完成时EOF。记录PID创建时间和持有句柄，已观测进程全部退出。此证据不等于操作系统掉电或任意浏览器扩展兼容性认证。

无头完整任务证据`.local/browser-noninterference/results.json`：7.875秒255采样，前台目标命中0、前台激活事件命中0、可见目标窗口0；三次填值、单次提交与server/DOM一致，11个自有进程退出。鼠标坐标变化30次来源未知，没有据此归因。观察不读取用户窗口内容，不发送真实桌面键鼠；仅说明这个支持的本地无头任务，不表示任意Windows应用已满足连续隔离。

生产部署和最终安装验证见[交付记录](DELIVERY-2026-11-11.md)。这些是2026-11-11部署时的证据，当前运行版本仍须以新连接 health 与文件摘要核对。

## 运行独立验收

验收脚本和 `tests/test_browser_mcp.py` 可使用 `WINDOW_PILOT_TEST_NODE`、`WINDOW_PILOT_TEST_PLAYWRIGHT`、`WINDOW_PILOT_TEST_CHROME` 指定绝对路径。未设置时，前两项在当前用户目录的 Codex runtime 缓存查找，Chrome 使用标准 Program Files 路径；脚本不自动安装依赖。这些变量只配置验收进程，不启用生产浏览器或修改宿主配置。普通 runner 默认跳过桌面输入；已安装 wheel 的真实无头验收使用 `python scripts/verify-browser-wheel.py <wheel> --evidence .local/<独立目录>`。
