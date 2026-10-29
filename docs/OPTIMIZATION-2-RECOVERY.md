# 第二项交验：恢复诊断与准备编排

日期：2026-10-29（Asia/Shanghai）。工作区`D:\codex\000\window-pilot-opt-text`，分支`feat/dsh-codex`。首项已按主审授权本地存档为`79822dfa3be9f7b22055a6314855cf9e1f76f8b1`；本项在该检查点之后实施。**以下是当时待主审、未提交或开始第三项的交验快照**；后续主审已接受并本地存档1571dff3aaeb4d89fe36c45af684dcfa74327bcc，见WP-NEXT-015及文末主审记录。第三项已下发，未部署。

## 做了什么

复用13工具中的window_control，新增可选`operation=prepare_recovery`，把获取操作权、证据收集与下一调用参数建议集中起来。原recover入口仍可直接使用，不要求每次先prepare，也不新增强制人工确认。宿主必须按原人类任务评估效果；无法通用自动判断截图所示动作是否正确，本项未声称完成自动效果验证。

| 状态 | 行为 |
|---|---|
| 可靠证明本次未发送 | 拒绝诊断标记attempt_input=not_sent，不再凭前置点击拒绝制造局部输入故障；仍须遵守原观察消费/时效和授权检查 |
| 已发送、尚无新观察 | input_state=sent_unreviewed；prepare取得owner后收集新证据，返回assess_observation，不假称工具已确认实际效果 |
| 部分/未知，或释放/到期/断连后锁存的未审查输入 | 保留共享故障，prepare返回review_required和next_call_after_review，宿主审查后显式提交recover；准备本身不清故障、不补发输入 |
| 失败/空观察 | 无可提交恢复的参数；既有故障保留，不能把空树或截图异常当恢复证据 |
| 无故障、无待观察输入 | prepare返回not_required，不额外截图；该显式调用已取得60秒操作权，后续仍需适时release |

默认只捕获绑定客户区；显式evidence_kind=controls可读原有有界UIA树。传入现有frame_id或observation_id时可复用已经交付的合法证据，避免重复观察。prepare返回的恢复参数包含精确token、证据ID、原绑定purpose和reviewed_effect_no_replay；它们是审查后的调用建议，不是工具自动提交。

典型恢复流程从`acquire → observe → 手工拼recover → observe`变为`prepare_recovery → 审查并提交返回的recover → 执行返回的新observe`。最后一次观察仍然必要，恢复会撤销审查证据；没有以易用性为由复用已撤销图像进行输入。已具备合法证据的旧宿主仍可走原recover流程。

## 修改清单与约束

- `src/window_pilot/service.py`：恢复状态与证据校验、prepare编排；对拒绝追加不含输入原文的结构化诊断；可靠未发送不误封锁。prepare依据取得owner后的最新状态，取得前快照仅作历史说明。主审指出的获取时租约到期边界已修正并验证。
- `src/window_pilot/coordination.py`：只增加输入工作流状态分类，保留共享锁、故障跨连接/交接保存、epoch与在途门禁。观察可用/明确恢复状态不表示应用效果已自动确认。
- `src/window_pilot/rpc.py`：isError的首个text保留原错误，第二个text交付recovery_diagnostic。attempt_input描述本次调用；不能用本次not_sent推翻窗口先前未知故障。
- `tests/test_click_failures.py`：只调整直接相关的前置拒绝/明确not_posted不应要求恢复的断言；原部分/未知封锁断言保留。`tests/test_recovery.py`新增8项行为验收。
- `docs/COORDINATION.md`、接续清单、WP-NEXT-014及本报告记录接口、流程、阶段与限制。

恢复证据必须属于该连接/精确目标、当前epoch、30秒内成功观察及当前owner。截图重核客户区尺寸；UIA要求成功非空树、精确身份与当前屏幕几何。恢复要求原有写绑定，不能从只读绑定清故障或获得新access；前台/后台/UIA授权仍分别检查。unknown/partial、派发后审计异常仍保守封锁。失败读取不会凭空制造输入故障，也不会清除先前故障。

诊断不保存text、keys或UIA value；截图/节点按原证据通道交付，审计不保存图像/树内容。新操作只能准备观察和控制权，不执行输入、任意宏或脚本；不自动rebind、重放、提权、重启执行端或切换捕获后端。

## 验证与反证

Python均为`C:\Users\33482\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe`，使用-B；未安装全局依赖。

1. 最终原生命令：设置`CI=1; WINDOW_PILOT_NATIVE_TESTS=1; PYTHONPATH=<本副本src>;<本副本tests>`后运行`python -B -m unittest test_recovery test_coordination -v`，**13/13通过，0失败、0跳过，13.115秒**。包括新增恢复8项、既有协调5项。生产create_connection_service生成独立Service/Dispatcher，共用真实Coordinator，实际创建/读取/后台点击自有fixture；不等于真实IPC、管理员部署或DSH/Codex端到端。
2. 原生直接效果：受控丢失释放消息后，窗口clicks仍0；prepare和recover均不增加计数，明确新观察后的新点击才变1。真实已发送clicks=1后交接会保留未审查故障；审查恢复后仍1。真实非空UIA树可准备恢复；实际移动自有fixture 2像素后，旧UIA几何证据拒绝，重新准备后恢复及新点击通过。
3. 证据反例：另一连接的ID拒绝；拥有自己当前证据但不是owner的连接拒绝；受控31秒过期证据拒绝；release推进epoch后的证据拒绝；只读绑定prepare/recover拒绝。没有通过这些路径扩大输入授权。
4. 受控故障清楚标记：丢失释放是对实际PostMessage发送链的故障注入；截图不可用与空提供方回复是受控失败；UIA超时用真实worker的1ms截止；证据过期和租约边界用受控时间，不冒称真实OS随机故障。获取操作权前推进11秒，由真实Coordinator执行租约到期/交接，验证新故障必须返回review_required和合法恢复计划。
5. 隐私：经实际Dispatcher拒绝含测试text/keys/UIA value的无权限动作，验证审计不含原文/相应参数；诊断不取这些参数。没有向用户应用或桌面注入这些输入。
6. 修复反证：`.local/recovery-counterexample.py`仅在测试进程内装回首项存档的旧_call，运行同一个“未发送无需恢复”行为测试，得到**1个预期失败、0错误**：recovery_required错误为true。反证脚本确认缺陷被抓住后退出0，源码未被改回。当前修复版本对应测试通过；反证的失败不计为正常测试通过。
7. 普通命令：`CI=1; WINDOW_PILOT_NATIVE_TESTS=0; PYTHONDONTWRITEBYTECODE=1; scripts/test.ps1 -Python <上述Python>`，退出0，`Ran 28 tests in 0.510s, OK (skipped=9)`，**26普通项通过、0失败**。2个单项及7个原生类入口跳过（新增恢复类也跳过），不算原生通过。
8. 实际Dispatcher initialize/tools/list核对：仍13工具，仅window_control的描述/schema有预期变化；其余12项完整描述/schema相等，公共初始化说明与首项已接受版本相同。`git diff --check`通过，暂存区为空。

最终原生回执、分项JSON、两张PNG及工具契约检查在`.local/validation/recovery-20261029/final/`，普通输出在上一层ordinary-output.txt，反证输出在上一层counterexample-output.txt，均Git忽略。图像已打开核对：partial-prepared-before.png显示clicks=0、single-down=1；partial-after-new-action.png显示clicks=1、single-down=2。截图来自自有fixture，不含用户桌面/应用内容。

## 未验证与停止边界

没有连接已安装执行端或运行真实DSH/Codex输入任务，没有验证实际管理员IPC/高权限/第三方控件完整工作流；实际效果证据限本项目fixture，真实硬件人工输入监听与同键竞态属于第三项，未修改foreground.py或实现第三项。未重跑无关前台/鼠标全套旧原生测试。

主对话另行只读排查的生产连接容量/握手问题不在本项修复范围，未修改admin_service.py或生产配置/服务/任务、重试传输或重启执行端。只读源码比对确认运行副本service.py仍为f5736fd基线；这不是实时服务health证明。没有推送、发布、部署或写_memory/全局记忆。

本项达到交验范围后停止，等待主审；尚未获得第二项接受/存档或第三项实施授权。

主审后续：主对话已核对本报告证据、源码、两张效果截图和旧_call反证，明确接受第二项，授权本地存档并下发第三项；见WP-NEXT-015。本段推进上述待审快照，历史范围保留。文档后续未重跑已通过原生，本项随本段所在提交存档，未部署。
