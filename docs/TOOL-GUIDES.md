# 工具描述精简交验

2026-11-12（Asia/Shanghai）。隔离副本 `tool-guidance`，分支 `feat/tool-guidance`，基线 `7367be49c1aa45ddbed53f95c23248f7a923d67a`。本项待用户验收，未提交、推送或部署；没有修改项目或全局记忆。

后续确认：用户随后明确“既然改完了就把GitHub上的更新一下吧，更新成0.2.1”，接受本项并授权存档、更新既有GitHub仓库和发布v0.2.1正式版，见WP-NEXT-046。上文待验收／未授权上传状态保留为交验时快照；本次没有部署本机执行端或写入记忆。发布提交与CI以Git历史、Release页面及工作流结果为准。

发布前复核：0.2.1普通测试仍为63通过、0失败、21跳过；重新构建的0.2.1 wheel在干净venv中安装，19工具与4份指南读取通过，回执`.local/release-021-tests.log`和`.local/wheel-021-check/wheel-smoke.json`。下文0.2.0 wheel为首次交验快照，保留原证据，不作为当前0.2.1包名。

## 改动

- 19项工具的名称和输入 schema 不变；公共说明和单项描述保留授权、精确目标、新观察、未知停输、禁止重放/前台兜底等约束。
- `dsh-plugin/skills/window-pilot/SKILL.md` 是指南入口；Windows低层细节、恢复、浏览器流程分为三个按需引用。指南与执行逻辑分离，未改 `Service` 的输入实现。
- DSH 原生插件在宿主提供 skills 服务时注册一个 `window-pilot` 技能；停用所属插件会撤销注册。旧宿主缺少服务时保持 MCP 接入，指南仍可经只读资源读取。
- MCP 增加静态 `resources/list`、`resources/read` 和空的模板列表，不增加输入工具。资源 URI 固定为 `window-pilot://guides/SKILL.md` 及 `window-pilot://guides/references/{windows,recovery,browser}.md`；不接受任意文件路径。
- 同一份 Markdown 同时随 DSH 包、源码包及 wheel 提供，不维护两套流程。恢复和浏览器指南无法读取时，提示停止对应操作。

## 描述体积

按基线与当前源码提取文本比较，计 Unicode 字符，不含工具 schema、宿主封装、skill 目录简介、资源目录和按需加载正文：

| 内容 | 原字符数 | 新字符数 |
|---|---:|---:|
| 公共说明，不含旧 RPC 附加句 | 2,124 | 800 |
| 19项单独描述合计 | 7,804 | 4,662 |
| DSH 公共说明一次＋单独描述 | 10,014 | 5,462 |
| 当前 Codex 投影：19项分别附公共说明，另计 initialize | 52,004 | 20,662 |

上述两个投影的描述文本分别减少45.5%和60.3%。DSH按本机0.2.2-rc.1客户端的独立 server-instructions 注入机制计算；Codex按本聊天实际展示的重复附加方式计算，不推广到其他宿主版本。19份 schema 本身没有缩减。技能目录和资源发现仍有少量固定成本；首次加载指南及后续引用会增加当时的上下文，直到压缩前仍会保留。没有测量真实 DeepSeek/Codex 计费 token、缓存命中、模型注意力或任务成功率，不能将字符降幅当作这些指标的实测改善。

## 验证

1. `python -B scripts/test_runner.py`：普通63通过、0失败、0错误，21个原生/浏览器入口跳过；原始输出 `.local/ordinary-tests.log`，摘要 `.local/test-results/summary.json`。新增一项真实stdio测试验证4份指南列出/读取、任意路径拒绝及错误后连接仍可用。
2. 基线 AST 对比：19项名称/schema完全相同；`service.py` 从 `validate_arguments` 起的实现AST完全相同。文本统计 `.local/description-comparison.json`。
3. 从本机 DSH 安装包只读复制七个必要依赖到本项 `.local`，使用真实 Cordis/SkillRegistry 在隔离Node进程注册、列出、加载正文和三个引用；注销后目录为空。没有连接生产MCP。命令 `node .local/validate-dsh.cjs`，回执 `.local/dsh-registry.log`。
4. `quick_validate.py dsh-plugin/skills/window-pilot`通过；两个JS入口 `node --check`通过。校验依赖PyYAML仅安装在本项 `.local/validation-deps`。
5. `pip wheel --no-deps --no-build-isolation --wheel-dir .local/wheel .`构建通过；`python scripts/verify-wheel.py .local/wheel/window_pilot-0.2.0-py3-none-any.whl --evidence .local/wheel-check`在干净venv安装通过。19工具、4份指南经真实stdio读取、管理员启动拒绝与隔离worker入口通过。回执 `.local/wheel-check/wheel-smoke.json`。
6. `git diff --check`通过；原运行副本仍为上述HEAD且工作区干净，源码、服务、任务、宿主接入均未切换。

首轮新测试额外调用health时，沙箱拒绝GetCursorPos；改为ping验证错误后的协议连接，未改health实现或放宽权限。早期隔离DSH校验脚本漏等Cordis插件就绪、使用了不存在的根dispose方法，现按真实API等待并销毁fiber后通过；不作为产品缺陷。没有重跑键鼠/浏览器任务、管理员IPC或真实DSH卡片加载；也未验证模型会否在真实会话中正确选择指南。验收后存档与本机部署分别执行，不以源码修改冒称当前服务已经生效。
