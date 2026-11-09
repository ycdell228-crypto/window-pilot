# 第五项交验：UIA 动作能力提示与 WPF 设值拒绝

2026-11-09。用户明确“第五项验收通过，存档并继续”，本项随本次提交在隔离副本本地存档，未推送或部署。第四项已验收并存档为 `e9849e7`。

## 行为

UIA 观察中的每个节点新增 `framework_id` 和 `background_actions`，后者按 invoke、set_value、select、expand、collapse、scroll 分别返回：

- `status: refused`：当前不可派发，`reason` 给出密码、禁用、不可见、Pattern 不支持、只读或 WPF 后台设值拒绝原因。
- `status: unverified`：当前静态规则未拒绝，但没有后台安全认证；不能据此承诺不会激活、移动光标或与用户切窗竞争。动态身份、前台、租约和观察时效校验仍然适用。
- `execution_method`：对应 `UIA.ValuePattern` 等机制；表示拟用路线，拒绝结果不代表执行过该机制。
- `background_safety_verified: false`：本项没有把任何 UIA 提供方宣布为后台安全。

观察和派发前共用同一规则函数。动作 worker 重新读取控件并判断，不信任旧缓存中的能力提示；framework 纳入观察指纹，并在实际调用前复核。已有权限、单次消费、未知停输及停止回调保留。

WPF 提供方的后台 set_value 现在明确返回 `rejected / UIA_BACKGROUND_WPF_SET_VALUE_REFUSED`、`action_attempted:false`、`effect:not_sent`。不调用 SetValue、不改用鼠标或前台，不自动寻找另一输入路线。拒绝仍消费本次观察，但不建立未知输入故障。已知密码、禁用等原因优先返回。

这是一项有意的兼容性收紧：过去可尝试 WPF SetValue，现在拒绝。理由是第四项探测未满足后台无干扰底线，尚无足够证据把它作为后台能力开放。该规则不推断其他框架安全，也不把此前窗口/光标变化的因果归为已证实。

## 验证与证据

- 普通回归：`CI=1 WINDOW_PILOT_NATIVE_TESTS=0 python scripts/test_runner.py`，51 通过、0 失败、15 个跳过入口，见 `.local/background-capabilities-tests.txt`。
- 专项：`CI=1 WINDOW_PILOT_NATIVE_TESTS=1 python -m unittest discover -s tests -p test_background_capabilities.py -v`，自有 WPF 窗口 1 通过。真实工作进程重新判断、缓存提示被清空仍拒绝、控件值不变、无未知故障、观察被消费、输入文字未进入审计均得到验证。见 `.local/background-capabilities-native-final.txt`。
- 共享观察回归：unittest 合并 `test_uia.py` 和 `test_window_state.py`，12 通过、0 失败（含普通检查与原生只读检查），见 `.local/background-capabilities-observation.txt`。未重复旧的多 Pattern 实际输入测试；旧 WPF 设值成功断言已改为拒绝/值不变，超时探测适配停止回调参数。
- 专项以约 10ms 周期采样前台 HWND，没有采到目标窗口成为前台；这不是连续隔离证明，不能排除采样间隙变化。允许用户在其他窗口间正常切换，不操纵用户键鼠。
- 首次沙箱运行没有交互桌面，跳过1项；首次交互桌面运行的规则/值检查通过，但“前后前台 HWND 相同”断言失败。该断言不适用于用户可正常切窗的场景，改为目标前台采样检查；失败记录 `.local/background-capabilities-native-desktop.txt` 保留，未将变化原因归为用户或提供方。
- `git diff --check` 通过；运行副本基线90文件哈希一致。所有回执均在忽略的 `.local/`，无新增可截图界面。

## 后续仍待完成

本项收紧已知问题路径并澄清能力信息，没有实现通用后台写入，也没有通过实际应用完整任务验收。其他 UIA 动作及 PostMessage 路线的应用兼容性、同桌面竞态仍需处理；严格后台整体目标未完成。后续应选择具体应用和动作建立实际无干扰证据，必要时使用应用专用后台接口或独立桌面方案，不能用单次绿色测试作为普遍认证。
