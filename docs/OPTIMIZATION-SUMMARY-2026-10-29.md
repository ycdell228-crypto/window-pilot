# Window Pilot 三项优化汇总（三项均已逐项接受）

## 当前发布与阅读入口（2026-10-29核对）

- GitHub `ycdell228-crypto/window-pilot` 的 `v0.1.0` 源码基准固定为 [b60cfa55c17fd361330ce1d12df075f4cfcc2720](https://github.com/ycdell228-crypto/window-pilot/commit/b60cfa55c17fd361330ce1d12df075f4cfcc2720)，包含三项优化；[已发布 README](https://github.com/ycdell228-crypto/window-pilot/blob/v0.1.0/README.md)是该版本功能概览。[v0.1.0 预发布](https://github.com/ycdell228-crypto/window-pilot/releases/tag/v0.1.0)及 WP-NEXT-017 保留发布范围。本次文档上传前重新核对 `main` 也为该提交，随后仅向 `main` 追加文档修订；最新文档提交以[main 历史](https://github.com/ycdell228-crypto/window-pilot/commits/main/)核对，不移动版本标签。
- 当前开发规则见 [AGENTS.md](../AGENTS.md)，用户确认的决定沿 [决策记录](decisions-dsh-codex.md)查阅。下面的工作目录、分支、未推送/未发布及待办是当时验收快照，不代表任意检出的当前状态；旧代验收流程不替代本次用户确认，见 WP-NEXT-018。
- 本次编辑开始时，隔离副本为本地 `1ff8604` / `feat/dsh-codex`，`origin` 指向本机开发仓库，并非 GitHub main。此定位只说明本轮起点，不是通用规则；后续本地文档存档用 git log 核对，不同步、切换或修改远端设置。
- 源码发布与本机部署分别核对。本轮未部署、重连或核验运行端；下面的本机安装/连接观察仍是历史事实，不能当作实时状态。接入步骤见 [DSH](DSH.md)、[Codex](CODEX.md)与[管理员服务](ADMIN_SERVICE.md)。

## 三项优化的开发与验收快照

工作区：`D:\codex\000\window-pilot-opt-text`，分支feat/dsh-codex。日期：2026-10-29（Asia/Shanghai）。这是隔离开发结果，未部署到生产，未推送、发布或写项目/全局记忆。

后续发布接续（2026-10-29）：上句及文末“未推送/发布、另行授权”保留为本地验收时快照。用户后续明确授权首个 Release，现已发布 [v0.1.0 预发布](https://github.com/ycdell228-crypto/window-pilot/releases/tag/v0.1.0)，精确远端基准 b60cfa55c17fd361330ce1d12df075f4cfcc2720；详见决策 WP-NEXT-017。本次仅发布既有源码，不部署或重连本机服务，不扩大下列验证范围。

三项均已由主对话逐项审查接受；第三项及本总结随WP-NEXT-016所在提交本地存档。精确提交号用本目录`git log -3 --oneline`及决策文件历史核对，不将本地存档解释为生产已更新。

| 优化 | 当前状态 | 可核对证据 |
|---|---|---|
| 说明压缩与宿主重复核对 | 已接受并存档79822dfa3be9f7b22055a6314855cf9e1f76f8b1 | 公共5469→2016字符；实际初始化5555→2102；13项完整描述/schema当时不变。DSH当前适配器独立注册说明，13倍投影不代表实测；Codex发现失败限制保留 |
| 恢复诊断与准备编排 | 已接受并存档1571dff3aaeb4d89fe36c45af684dcfa74327bcc | prepare_recovery集中获取owner、成功新证据及待审恢复参数；未知不重放、失败/空观察不清故障。恢复8+协调5项通过，旧_call反证能抓原缺陷，普通26通过 |
| 外部输入及时让路 | 已接受，随WP-NEXT-016所在提交本地存档 | 动作级透传钩子+自身标记；20ms检查探针等待；精确左右键释放，已知外部同键持有时延后。新增6项（含6种修饰键子场景）通过；最新清理诊断/已有键/预算/密码焦点4项补验通过，普通27通过（含0接受计数但unknown仍锁存的回归） |

分项报告：[说明](OPTIMIZATION-1-TEXT.md)、[恢复](OPTIMIZATION-2-RECOVERY.md)、[干扰](OPTIMIZATION-3-INTERFERENCE.md)。初版失败与后续修正、用户空闲确认前的失败及方法名loader错误均保留，不算跳过或成功，也不假定根因。

当前工具仍13项，第三项全部输入schema与第二项相同；恢复项扩展了window_control，干扰项更新foreground_action说明与结果诊断。没有任意脚本/宏接口、BlockInput、吞事件、焦点夺回、自动恢复或重放。源码与测试小步保留，各项接受后才存档。

范围限制：受控外部事件是测试SendInput，非真实人类硬件；消息泵心跳不能证明钩子未被系统静默移除，检查到注入/释放与监控失效期间仍有竞态。没有真实管理员IPC或DSH/Codex端到端输入、全部第三方/DPI/IME兼容性或最终模型token收益证明。

额外待办：主对话仅作只读诊断，观察运行端ready、4个桥接进程；源码上限为4连接，新连接断连与该上限吻合，但尚未做因果重现、尚未修复。不能记为已证根因或“主对话已处理”，本副本未修改。

第三项现已接受并获准本地存档，提交后停止并等待，不扩展第四项。部署/重连或GitHub上传另行授权，不能把隔离完成视为生产已更新。
