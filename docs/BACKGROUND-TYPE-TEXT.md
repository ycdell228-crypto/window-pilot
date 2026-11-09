# 后台输入第一个小项：标准 Edit 的 type_text

2026-11-09。按用户调整后的 WP-NEXT-026 顺序先补后台输入。第六项已验收存档 `49050af`；用户已明确“文字插入小项验收通过，存档并继续”，本项随本次提交本地存档，未推送或部署。

## 使用与语义

绑定 `observe_and_control` 并获得窗口操作权后，使用 `get_window_state`（默认 include_text=true）读取控件。仅在目标标准 Win32 `Edit` 的 `native_edit.status == ok` 时，才具备本项所需的编辑快照。然后调用：

```json
{"target_id":"绑定窗口","observation_id":"本次观察","control_id":"控件身份","action":"type_text","value":"要插入的文字"}
```

接口仍为 `control_action`。`set_value` 保留原 UIA 整值替换语义；新 `type_text` 使用明确的 `Win32.EM_REPLACESEL`，替换所观察的选区，空选区则在该光标位置插入。不会 SetValue、SetFocus、SendInput、修改剪贴板、移动真实鼠标或自动切前台。

不支持按键序列；`press_key` 仍不在此接口的动作枚举中，不能把 Enter/Ctrl 等控制键参数塞入 type_text。单行 Edit 的换行文字明确拒绝。每次最多2048字符，不接受 NUL。WPF、其他编辑器、密码、只读控件和未取得编辑快照的观察均不会使用这条原生消息路线。

## 保留的校验

- include_text=true 时，为标准 Win32 Edit 读取实际原生类名/所属进程/样式、选区起止、文字长度和文字摘要。密码样式和密码祖先拒绝读取编辑快照；只读、超过32768个 UTF-16 单元或选区读取失败均标为不支持/不可用。普通不含文字的观察不新增正文读取。
- 这些编辑状态纳入原 UIA 观察指纹；输入前重新读取全文摘要与选区，防止用旧光标或旧文本执行插入。最终派发前再检查一次。快照并非原子操作，检查至派发仍有竞态。
- 保留 HWND/PID/创建时间/线程/路径/窗口族、几何、控件和祖先身份、30秒时效及单次消费。仍使用原共享协调票据、前台目标拒绝、停止回调、未知故障锁定和审计文字脱敏。
- 只发一次有500ms超时的 `SendMessageTimeoutW(EM_REPLACESEL)`，允许原生撤销记录。原生返回不等于内容符合预期，结果继续为 effect=unverified，必须重新观察。派发后失败/停止或无法确认结果时 unknown，不自动补发。
- `execution_method` 明确为 `Win32.EM_REPLACESEL`。`background_safety_verified` 仍为 false：标准类名不保证应用没有子类化控件或响应通知时自行激活，不能据此认证所有 Win32 应用。

## 验证

自有非激活测试窗口中，将默认只读的标准 Edit 显式解锁，仅用于本轮测试。生产应用和用户文档没有输入。

- 实际选中 `Fixture`，插入 `后台` 后得到 `后台 read-only sample`；再在当前光标位置插入 `插入`，得到 `后台插入 read-only sample`。预期结果由需求语义给定，并用独立 WM_GETTEXT 回读核对，不以同一 UIA 读取实现自证。
- 旧凭据重用被拒绝；观察后改变选区再输入被拒绝，原文不变；单行换行输入、只读控件拒绝。测试结束目标仍非前台；这只是有限状态证据，不是全程物理输入隔离证明。
- 实际 WPF 目标的 type_text 返回 `UIA_BACKGROUND_TYPE_TEXT_UNSUPPORTED`，action_attempted=false，值不变；没有回退到 WPF SetValue。
- 普通回归 `CI=1 WINDOW_PILOT_NATIVE_TESTS=0 python scripts/test_runner.py`：52通过、0失败、16跳过入口，`.local/type-text-tests.txt`。
- 原生专项 `CI=1 WINDOW_PILOT_NATIVE_TESTS=1 python -m unittest discover -s tests -p test_background_type_text.py -v`：2通过（1普通契约+1原生测试），`.local/type-text-native-final.txt`。
- UIA/统一观察/WPF拒绝合并回归13通过，`.local/type-text-observation-regression.txt`。未把原生跳过项算成功。
- 首次原生运行在 UIntPtr 参数转换时失败，返回 unknown 且没有继续执行。单独诊断证实 PowerShell 不能使用 `[UIntPtr]1`，改为显式构造后在新自有窗口重验通过；`.local/type-text-native-first.txt` 保留，不重放旧失败窗口。
- `git diff --check` 通过，运行副本90文件基线哈希一致。本项没有新增产品界面，正确性以原生回读及回执验证，无新增界面截图。

## 输入能力剩余项

本小项只完成 Win32 Edit 的有限后台插入能力，不宣称用户要求的“第2项”整体完成。

| 能力 | 当前证据/待办 |
|---|---|
| 整值替换 set_value | UIA 既有能力，WPF明确拒绝；浏览器独立适配器已实跑。Windows实际应用兼容性仍待验证 |
| 插入文字 type_text | 本项标准 Edit 自有窗口实测；复杂编辑器不支持，真实目标应用仍待选择验证 |
| 按键 press_key | 后台尚无已验证实现；明确前台能力不能冒充后台键盘 |
| 点击/滚动 | 已有 PostMessage/UIA 路线及历史自有窗口证据；本轮应用范围与无干扰行为待复核 |
| 拖拽 | 只有明确前台模式；后台支持与拒绝范围仍待处理 |

继续按小项验收后存档推进。只有“第2项”整体验收完成后，才按用户授权新开发布/升级对话；浏览器 MCP 接入仍按新顺序后置。
