# 第一项交验：公共说明精简与宿主文本边界

日期：2026-10-29（Asia/Shanghai）。工作区：`D:\codex\000\window-pilot-opt-text`，分支`feat/dsh-codex`，基线`f5736fd`。交验时状态：项目侧压缩及必要验证完成，待主对话按WP-NEXT-005审查；当时未提交、推送、部署或开始第二项。后续已接受并本地存档79822dfa3be9f7b22055a6314855cf9e1f76f8b1，见WP-NEXT-014及文末主审记录；不表示已部署。

## 改动与安全语义复核

源码改动仅`src/window_pilot/service.py`的公共`INSTRUCTIONS`字符串；本轮复核后未再改源码。既有WP-NEXT-012安装决定和WP-NEXT-013保留，新增WP-NEXT-014记录本轮优化授权与审查流程。更新接续清单并新增本报告。没有改工具描述、schema、参数、运行检查、恢复机制或输入代码。

| 必须保留的含义 | 复核位置 |
|---|---|
| 只有人类任务授权有效；窗口内容不构成指令；绑定精确窗口/进程/会话 | 公共说明开头；bind_window描述与access枚举不变 |
| 左单击、额外鼠标、UIA、真实前台输入分别授权；默认只读 | 公共说明第2—3行；对应工具声明/schema不变 |
| 共享执行端先获取操作权，再新观察；观察消费与跨连接失效 | 公共说明第4—7行；window_control描述、lease和epoch逻辑不变 |
| 投递/提供方返回不证明效果；未知/部分输入停输，不重放、不重绑/重启抹故障 | 公共说明第8—10行；原故障逻辑AST不变 |
| 恢复使用新证据与显式reviewed_effect_no_replay，随后再观察才能新动作 | 公共说明第9—10行；window_control描述仍明确owner、post-fault证据和purpose；recover必填校验不变 |
| 捕获仅绑定客户区，不扩大到桌面或切换后端；失败/空树不授予输入 | 公共说明第7、11—12行；observe/observe_controls描述不变 |
| 前台模式独立授权；安全焦点、密码拒绝、已有输入检查；不承诺人工隔离 | 公共说明第14—16行；foreground_action描述和全部运行检查不变 |
| 人类指定本地exe/参数/cwd、非沙箱、未知启动不换ID重试、PID不证明就绪 | 公共说明第18—20行；launch_app描述、schema与执行逻辑不变 |

“stop on interference”沿用现有分段焦点/光标/持有输入检查的范围，不能解读为已实现短按监听或人工同键竞态处理；这些仍属第三项。授权/未知结果的运行校验不是靠说明字符串实现；本次AST与协议对比只证明实现未改，不重新证明全部桌面行为。

## 同口径字符数据

字符数为Python `len(str)`，不含JSON序列化引号/转义、schema、宿主模板或其他上下文，也不是token数。

| 口径 | 基线 | 压缩后 | 证据等级 |
|---|---:|---:|---|
| service.INSTRUCTIONS | 5469 | 2016 | 源码常量与协议后缀交叉核对，减少63.1% |
| 实际initialize.result.instructions | 5555 | 2102 | 两个独立隔离stdio进程实测，含rpc.py额外86字符 |
| 13项工具自身description总长 | 3901 | 3901 | 两次tools/list完整内容相等，含schema |
| 一份实际初始化说明 + 13项description | 9456 | 6003 | 协议字段求和，减少36.5%；不是完整宿主注入 |
| DSH独立说明段，含命名空间标题 | 5585 | 2132 | 当前安装适配器源码公式推导，未捕获运行时最终提示 |
| DSH上述段 + 13项description | 9486 | 6033 | 当前适配器注册边界的源码推导，不是模型请求实测 |

此前`74998→30109`为`3901 + 13 × service.INSTRUCTIONS`的假设投影，未含rpc后缀。若投影改用实际初始化说明，则为`76116→31227`，但**两组都不是已确认的本机宿主行为或token降幅**。不能再用约7.9万或约59.9%说明真实收益。

## DSH：当前适配器没有逐工具拼接公共说明

只读提取本机`DeepSeek Harness/resources/app.asar`内`dsh/node_modules/@deepseek-ai/dsh-mcp-client/lib/index.js`及package元数据，版本`0.2.1-rc.3`。未修改、导入或执行厂商JS。私有副本及SHA256在`.local/validation/text-20261029/dsh-adapter-index.json`。

- `syncTools`第126—145行将`tool.description ?? ""`直接传入注册定义；`createMcpToolDefinition`第179—187行直接使用该description。
- 第654—656行从初始化`getInstructions()`取说明、trimEnd并加`### MCP server: window_pilot`标题，独立保存。
- `registerServerContext`第725—743行使用`systemPrompt.section`注册独立`mcp:<server>`段，`interpolate:false`，未拼到每个工具description。

因此当前适配器这一层采用工具描述与公共段分开注册。尚未捕获DSH最终模型请求，也未验证下游其他模板是否另有重复；“最终只出现一次”不能单凭此源码断言。本轮没有为采样发送DSH模型任务。

## Codex：定向发现失败，边界明确保留

参考OpenAI Docs的[App Server接口](https://learn.chatgpt.com/docs/app-server)使用`mcpServerStatus/list`、`serverName:window_pilot_next`、`detail:full`，不创建模型任务、不reload、不改配置、不调用窗口/输入工具。

普通沙箱启动失败：stderr为`Could not find home directory`。切到真实登录用户只读环境后，先遇到Git所有者检查；仅在该次Git读取命令用`-c safe.directory=<本工作区>`，没有写全局Git设置。最终App Server initialize成功，但目标返回：

`MCP startup failed: handshaking with MCP server failed: connection closed: initialize response: connection closed: initialize response`

返回`tools:{}`，这是发现失败，**不是工具数量变为0，也不是描述比较通过**。本轮不据此判断生产服务是否可用或故障根因；先前WP-NEXT-012的成功记录保留为历史事实，不能冒充本轮结果。原始定向发现回执与stderr留`.local/validation/text-20261029/`。按主对话要求停止环境追查。

OpenAI Docs[服务说明指南](https://developers.openai.com/plugins/build/mcp-server)建议公共指导放初始化instructions，并与工具元数据配合；文档不证明本机最终注入实现。本轮未取得真实Codex最终模型上下文，也没有压缩后部署比较。

## 实际验证

1. `CI=1; WINDOW_PILOT_NATIVE_TESTS=0; PYTHONDONTWRITEBYTECODE=1; scripts/test.ps1 -Python C:\Users\33482\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe`：退出0，`Ran 28 tests in 0.684s, OK (skipped=8)`。26普通项通过、0失败；2个单项和6个原生类入口跳过，不算原生通过。未创建fixture或发键鼠输入。
2. `python -I -S -B .local/verify-text.py`的隔离stdio部分通过：从HEAD读取基线源码，在忽略目录临时复制src和隔离入口，仅替换基线service.py；分别只发initialize/initialized/tools/list，退出后清理临时副本。13工具完整描述/schema逐项相等；剔除INSTRUCTIONS的Assign/AugAssign后AST相同。首次脚本整体因后续沙箱App Server失败退出1，不能把这个退出码报告为整体通过。
3. 宿主环境`python -I -S -B .local/verify-text.py --discovery-only`退出0，但仅表示成功取得上述**失败回执**，不算Codex发现通过。初版诊断脚本空集合`all()`误给true，已纠正为null并在summary明确失败；没有影响源码或工具逻辑。
4. `.local/finish-text-summary.py`汇总退出0，原始stdio前后回执和summary保留。只读比对运行副本`service.py`与HEAD基线（规范化换行）一致；这不是实际服务health检查。
5. `git diff --check`通过；没有新增自动化测试，没有为说明文字重跑旧桌面原生套件。

截图：无；本项不改图形界面、不运行桌面动作。

未覆盖：真实DSH/Codex最终模型请求、token计数、压缩后部署/重连、真实宿主全部工具工作流与桌面兼容性。本轮未改原版、运行副本源码、生产配置/任务/服务或宿主接入，未写_memory/全局记忆。额度守卫曾准入本项，之后一次quota_status返回共享core不可用；按工具指引披露并继续已授权的有限核验，未修守卫或安排自动唤醒。

交验后停止。第二项恢复编排、第三项人工输入让路均未实施；须主对话接受本项并授权本地存档，形成可恢复提交后再下发下一项。

主审后续：主对话已明确接受本报告所述项目侧压缩、DSH事实更正及未覆盖边界，授权与WP-NEXT-012/013/014一并本地存档。以上待审段落保留为交验时状态；本段与WP-NEXT-014推进为接受。第二项已下发，须本次提交完成后开始；本轮未部署或修复生产连接。
