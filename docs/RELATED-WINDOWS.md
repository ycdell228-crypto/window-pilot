# 第三项：关联窗口发现与显式绑定

2026-11-08。第二项已验收并本地存档 `d9ddb30`。用户随后明确“第三项验收通过，存档并继续”，本项随本次提交本地存档；未部署或推送。

## 接口

- 旧 `list_windows({})` 保持枚举行为；`list_windows({"target_id":"<已绑定窗口>"})` 只返回 Win32 owner 链关联的可访问顶层窗口。
- `get_window_state` 默认增加 `related_windows`，可用 `include_related_windows:false` 关闭。该字段只包含窗口元数据，不额外截图、读弹窗正文或输入。
- `relationship` 区分 `owned_descendant`（目标拥有的窗口/后代）、`owner`（目标的拥有者）与 `shared_owner`（共享拥有者）。同进程本身不算关联。
- `target_enabled` 和候选窗口 `enabled` 来自窗口状态；目标禁用且拥有的关联窗口可用时，`may_block_target:true` 只是可能阻塞的提示，不断言模态。
- 返回原有完整窗口身份及 `owner_chain`。owner链最多16层，拒绝环；发现过程中身份/owner发生变化的候选跳过，计入 `skipped_unstable`。目标身份、owner链或 enabled 变化则整体拒绝。
- 选择关联 HWND 后必须显式 `bind_window`；默认仍只读，原 target_id 不切换、权限不继承。窗口关闭后再次枚举会移除它，不能使用旧列表自动恢复。

## 验证与边界

普通回归45通过、0失败、13跳过入口。新增两项测试：受控owner环拒绝；真实自有NOACTIVATE主窗口、拥有窗口、嵌套窗口、同进程无关窗口，核对筛选、禁用主窗提示、显式只读绑定、原绑定不变、已关闭窗口失效。两项通过（0.209秒）；没有发送真实键鼠或激活窗口。

证据在 `.local/related-windows/native.json` 与 `ordinary.txt`；统一观察原生回归8通过、0失败（33.001秒），见 `observation-regression.txt`。`git diff --check` 通过，生产90个基线文件哈希未变。媒体/本机证据不入Git。

尚未实现多窗口联合截图、应用级 list_apps、无owner的自定义弹层或跨进程嵌入控件发现。这些元数据来自分次读取，仍非原子快照；只能发现当前可访问、可见且可绑定的窗口。不能据此宣称真实应用完整后台任务已验收。本项不更改前台模式或自动切前台兜底。
