# 第三项：前台输入遇外部干预及时让路

日期：2026-10-29（Asia/Shanghai）。工作区`D:\codex\000\window-pilot-opt-text`，分支feat/dsh-codex，基线为第二项已接受提交`1571dff3aaeb4d89fe36c45af684dcfa74327bcc`。以下保留当时未提交、待审的交验快照；后续主审已接受，第三项随WP-NEXT-016所在提交本地存档，精确提交号用git log核对。未部署。

交验时状态：实现及必要验证完成，**当时待主审，未提交或部署**。中途原生运行遇外部事件/前台变化而停输，曾按主对话要求暂停桌面输入；用户明确“可以，接下来几分钟不用键鼠”后，仅补验未完成及最新修订4项，4/4通过、66.456秒。空闲后通过不反推先前失败一定由用户输入造成；历史失败保留，不算跳过或通过。

## 实现

- `input_monitor.py`仅在明确前台动作中建立WH_KEYBOARD_LL/WH_MOUSE_LL、独立消息泵和定时消息；正常/异常收尾都撤销。不在模块导入、只读或后台操作安装长期监听，回调始终CallNextHookEx，不拦截或吞事件。
- SendInput使用本次随机31位dwExtraInfo；自身事件必须同时匹配标记及注入标志。全宽随机标记在本机短探针中未匹配，改为31位后，一次真实标记鼠标移动记为own_mouse=1、external=0。这个对照不证明所有Windows输入路径的位宽行为，标记也不是隔离/防伪边界。
- 外部事件锁存中断；短按松开后中断仍保留。只暂存本次所需外部按住集合、当前位置与类别计数，不存按键/文字/位置历史。统计区分外部注入标志、未注入事件及无位置变化通知；未标记不等于真实硬件。无位置变化通知目前同样停输，没有据此放松检查。
- 探针响应等待每20ms检查中断/预算，不必等满6秒。此处只中断可控的响应等待，不保证所有Win32调用/进程终止/调度都有同一截止。
- 现有CTRL/SHIFT/ALT名称改用精确左侧VK；外部回调按VK/scan/extended解析左右。持有检查只排除工具自己的精确侧及聚合VK，另一侧仍检查。清理时已知外部同键仍按住则延后释放并报告数量；另一侧外部按住不能导致工具侧遗留。
- 监听失效时仍尽力释放无已知外部同键持有的工具输入，不能把监听坏了等同于所有键都归外部持有。该失效期间新外部同键输入仍可能不可见，竞态无法消除。
- 按键释放失败、worker/监控清理失败、监控内部故障分为owned_input_release_failed、input_cleanup_failed、input_monitor_failed；外部输入诊断依据实际类别计数，不依据内部错误也会置位的interrupted信号。
- 未调用原生输入的中断为not_sent，不制造共享输入故障；已开始/部分/不确定输入仍保守unknown，沿用跨连接fault与显式恢复，不重放。原始焦点/几何/epoch/共享输入门禁不放宽。原生焦点错误只增加两个匹配布尔诊断，不读取无关窗口内容。
- 主审要求保留input_sent布尔契约，未引入bool|string联合类型；input_attempted与独立delivery表达尝试/不确定派发。0接受计数+input_sent=false不能清掉status=unknown及共享故障。该输出整理不改原生发送/释放路径，按要求不再开桌面测试。

接口仍13工具，无新增输入参数；仅更新foreground_action描述与其结果/拒绝诊断，window_control恢复契约沿用第二项。前台契约详见FOREGROUND.md。没有改IPC容量、部署配置、服务、任务、厂商包或运行副本。

## 已有验证

原始证据均在Git忽略的`.local/validation/interference-20261029/`，Python使用既定运行时与-B，不安装依赖。

- 新增6项：`python -B -m unittest test_input_interference.InterferenceNativeTests -v`，6/6通过、0失败、0跳过，50.398秒（new-tests/output.txt）。含CTRL/SHIFT/ALT同侧及异侧6个子场景。实际低级钩子与自有前台WPF fixture，经生产Service和共享Coordinator；外部事件为受控SendInput，不是人工硬件。
- 短按/鼠标干预：仅暂停本测试拥有的focus worker，使真实响应等待保持未返回，再在自有fixture发外部F9短按或鼠标移动；动作实际中断至返回172—218ms，各精确修饰键释放/保留由GetAsyncKeyState核验，worker由生产close终止。不是模拟时间或伪造UIA成功。短按后F9和工具Ctrl均up，echo保持initial；跨连接仍拒绝重放。
- 构造期间外部短按触发初始化失败后真实钩子线程退出；鼠标钩子安装受控失败时，先前实际装好的键盘钩子也清理。非注入事件即使extra匹配，也仍视为外部的回调策略单独模拟验证，不冒称硬件测试。
- 同侧外部hold保留，工具不发送该侧up；异侧外部hold保留且工具侧up。测试finally只清理测试自身合成输入；不把用户实际持有键释放。监控失败后Ctrl真实up的路径在初版6项中通过，主审要求拆分清理诊断后，最新单项在quiet-final批次通过，断言真实Ctrl已up、external_input_detected=false、owned_input_release_failed=false、input_monitor_failed=true且input_cleanup_failed=false。
- 修正标记后的原有Unicode/快捷键单项1/1通过，17.233秒（own-input-fixed/output.txt），真实echo和Ctrl+A/Backspace清空、审计脱敏保持；正常拖拽在后续focused批次通过。没有为文档重复整个旧前台套件。
- 最终普通命令显式`CI=1; WINDOW_PILOT_NATIVE_TESTS=0; PYTHONDONTWRITEBYTECODE=1`执行scripts/test.ps1：**27普通项通过、0失败**，10个跳过入口（8个类+2个单项），Ran 29 in 0.551s（ordinary-final-output.txt）；跳过不算原生通过。新增一项直接风险回归：在受控原生结果边界返回unknown/布尔false/0接受计数，经真实Service、Dispatcher、InputTicket及shared Coordinator，确认共享故障锁存并拒绝后续输入。该项不声称原生桌面验证。此前26普通项的历史输出不作为最终计数。此后仅文档整理，不重跑原生。
- 实际Dispatcher tools/list仍13项，全部inputSchema与第二项相等，只有foreground_action描述更新；未实例化Service或InputMonitor完成该只读契约检查（contract-check.json）。运行副本service.py只读比对仍为f5736fd基线，不等于实时health。git diff --check通过。

## 保留的失败与待验

- own-input最初全宽标记单项失败：移动后报外部干预，停止后续点击；随后诊断单项在初始化遇外部事件。短探针对照后修正31位标记，成功记录不覆盖原失败。
- final-focused批次5个入口：监控失效与正常拖拽通过；已有键与预算用例在setUp遇外部事件未进入场景；另一个入口方法名写错造成loader错误。正确方法是test_drag_focus_loss_releases_button_and_stops，调用名已在后续脚本修正，无需改生产逻辑；loader错误不是产品失败，也不算通过/跳过。
- final-boundaries批次3项：已有键和密码迁移setUp出现未标记鼠标移动；预算setUp点击后报FOREGROUND_TARGET_OR_GEOMETRY_CHANGED。未读其他窗口内容，不能确定原因。cleanup-diagnostic后续单项也在setUp报相同前台/几何错误，未执行新的清理字段断言。所有原始输出保留。
- 用户明确空闲后：`python -I -S -B .local/foreground-focused-check.py`实际运行监控故障清理字段、已有键、预算与真实密码焦点迁移4项，**4/4通过、0失败/跳过，66.456秒**（quiet-final/output.txt）。已有键仍down且未被动作误释放；预算用例真实Ctrl按下后等到5秒截止并释放；fixture实际将焦点移到密码框后停输并释放鼠标。之前的6项成功按其版本/范围保留，未无依据重跑全套。新fixture是独立测试，不重放前一个未知动作。
- quiet-final批次先运行新类监控故障单项，再运行旧类3项；两类原先共用foreground-effects.json，后类JSON覆盖了该批次前一类摘要，但原始4项测试输出未覆盖，最新字段由通过的断言验证。现已为新类改用interference-effects.json，防止以后混跑覆盖；没有为文件命名再跑桌面。旧new-tests/foreground-effects.json的6项记录保留原名与内容。

截图：new-tests/drag-interrupted.png为自有fixture中断图；final-focused/drag-after.png为正常拖拽图；own-input-fixed/unicode-after.png为文字/快捷键正例。均不入Git，已打开核对。真实人工硬件事件没有验收，受控注入与回调策略模拟均如上标明。

## 限制

定时消息/last_ack只证明消息泵响应，不能证明Windows没有因LowLevelHooksTimeout静默移除钩子。回调到检查、检查到注入/释放，以及监听失效后新发生同键输入仍有竞态；不承诺同桌面完全隔离。没有真实人工硬件验证、实际管理员IPC或真实DSH/Codex端到端输入验收，不推定第三方/高权限/DPI/IME全部兼容。监控不BlockInput、不夺回焦点、不自动恢复/重放。

本轮仅隔离开发与验证；原版、生产window-pilot-next源码/配置/服务/任务和_memory/全局记忆未改。达到约定验收后停止，仍需主对话审查，本项不自行提交。

主审后续：第三项已明确接受，三项均已逐项接受。主审核对本报告原始输出、最终代码、布尔契约及x48中断图，授权一次本地存档并要求提交后等待；见WP-NEXT-016。本段推进上述待审快照，不抹历史失败或未覆盖范围。停止实现和桌面测试，仅补文档与本地存档，不部署/重连、push或Release，不扩展第四项。
