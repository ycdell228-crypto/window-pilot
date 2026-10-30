# DSH审查改进交付（2026-10-30）

后续确认：用户已明确“上传git吧”并要求一并更新GitHub项目页面。本报告下文保留上传前交验快照；提交/上传授权和边界见WP-NEXT-019，实际远端结果以main历史及页面读回为准。

状态：用户授权的顺序修改已完成本地验证，待交验确认后再提交Git。工作副本window-pilot-opt-text，基线8a3b94d；本次没有部署/重连运行端、更新GitHub或移动已发布v0.1.0标签。

## 按顺序完成

1. README明示管理员管道接受可访问的同SID/同会话进程，客户端不限DSH/Codex；purpose不构成人工批准证明。ADMIN_SERVICE修正当前13项工具和前台/UIA能力，原首轮9项验收单独标注历史。
2. [证据保留](RETENTION.md)：默认截图512张/256 MiB/30天，审计8 MiB、4份归档。并发连接使用共享锁，降低上限时亦处理旧文件；超大单帧不保存并明确报告。启动去重回执不清理。
3. [启动限制](LAUNCH_POLICY.md)：可关闭launch_app或限定规范exe路径，缺省保持兼容；显式空白名单拒绝全部。格式错误不放宽，拒绝在占用request_id和进程创建前发生。路径限制不宣称防御同账户恶意代码，不限制允许程序参数/子进程。
4. CI普通回归输出实际passed、failed/errors及skipped_entries，上传普通结果摘要；新增独立wheel安装冒烟步骤，原生输入仍默认跳过。
5. [安装文档](INSTALL.md)：本地wheel构建、pipx及venv路径、普通stdio与源码管理员安装的区别、英文简版。运行资源随wheel构建，源码脚本仍为唯一编辑来源；源码ZIP补齐setup.py、MANIFEST.in、LICENSE及AGENTS。README加入接入图，实测截图留在被忽略的.local，不为展示改变媒体入库规则。

## 本轮验证

| 验证 | 结果 | 范围 |
|---|---|---|
| `CI=1, WINDOW_PILOT_NATIVE_TESTS=0; scripts/test.ps1` | 38通过、0失败/错误、10个跳过入口 | 27既有普通项、保留6项、启动限制4项、自有fixture清理1项；跳过不算通过 |
| wheel真实安装 | 通过 | 临时venv，从非源码目录运行console入口、13项工具、普通模式拒绝启动、隔离子进程导入 |
| pipx真实安装 | 通过 | pipx工具、home/bin/man全部设在本项目.local内，入口help成功；未修改系统PATH |
| 最终wheel原生只读检查 | 通过 | 自有WPF测试窗口、PrintWindow截图实际保存、UIA读取49节点；无键鼠输入或管理员服务安装 |
| 文本/构建检查 | 通过 | 改动Markdown相对文件链接、PowerShell解析、git diff --check；构建wheel与本地源码ZIP |

unittest显示Ran 40、skipped=10的计数还包含类级跳过入口；本轮test_runner按实际addSuccess单独统计38通过，不按简单相减误报。GitHub CI工作流已修改但尚未推送/远端运行，表内为本地等价验证，不冒称远端绿灯。

最终已验wheel：`.local/validation/dsh-review-20261030/verified-wheel/window_pilot-0.1.0-py3-none-any.whl`，SHA256 `4c6b3b102b1b3d80c6dd348ad401dc5516e7c33b3497ea75384f4895bcedfb56`。

私有证据：`.local/validation/dsh-review-20261030/ordinary-final.log`、`.local/test-results/summary.json`、`verified-installed/wheel-smoke.json`与`verified-installed/installed-fixture.png`（后三个wheel证据位于上述validation目录内，普通摘要另在.local/test-results）。这些文件及测试截图不纳入Git。

## 本轮失败与修正

- 首次在沙箱内安装后调用health，GetCursorPos返回Win32 error 5；转到获准的交互环境后只读验证成功。标准wheel冒烟不调用桌面health，交互检查只在显式--native时执行。
- 中间一次最终构建复验返回TEST_START_TIMEOUT，随后临时目录因自有fixture进程占用清理失败。已重新核对该子进程的精确脚本路径、父PID和创建时间后仅停止此进程；一次清理审批因连接中断未执行，同一操作重新提交后成功，未绕过审批。
- 修复launch_test启动超时及dispose异常时的自有fixture收尾；只结束Service自己创建的子进程，不操作绑定用户程序。新增真实休眠子进程的回归测试证明无窗口时仍能退出。未放宽5秒启动门槛，也未把超时原因归结为用户或单一已证根因。
- 含修复的最终wheel重新构建、安装和原生只读验收通过；失败历史保留，不将它计为通过。

## 保留范围与交验边界

不改管理员管道原有信任模型，不新增带外批准系统；摘要检查承担源码变更停机，未测得性能瓶颈，保留每2秒及请求前的校验。超过1MB请求断连边界保留。四连接症状未纳入本轮修复。

未重跑原生键鼠、人工硬件、完整管理员IPC或真实DSH/Codex端到端输入；WGC可选依赖安装、全平台Python/第三方应用兼容性未全面验证。截图是项目测试窗口读回，不证明任何用户应用适配。

本轮未上传wheel/截图附件，未替换旧发行产物、修改生产或写项目/全局记忆。修改前完整备份及逐项文件检查点在`.local/checkpoints/dsh-review-20261030-140909/`；用户确认后再按项目规则提交，另行明确发布/部署范围。
