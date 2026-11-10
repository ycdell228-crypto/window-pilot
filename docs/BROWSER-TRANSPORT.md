# 浏览器执行端通信基础（已验收）

2026-11-10，基于已验收存档d1bbb26，在隔离副本browser-integration实施；测试交验后用户回复“继续”，接受此小项并授权本地存档。尚未部署或新增公开MCP工具；下文未验收状态保留为交验时快照。

Python BrowserTransport用宿主配置的绝对路径启动Node browser-worker，Node复用已验收BrowserSession。请求按行JSON传递，含独立id；仅允许begin/step/observe/end/status，不接受页面提供的命令或可执行路径，不经shell。请求64KiB、响应8MiB上限。输入正文不写日志，工作进程错误仅返回固定代码。

每连接仅一个在途请求，结果id匹配后才返回；已开始发送后的通信失败、超时或取消均返回BROWSER_COMMUNICATION_UNKNOWN并关闭输入，不重发、不重启。check_running回调供后续共享停止接入使用，此处尚未接入Coordinator。

close关闭stdin，工作进程收到EOF后停止会话并等待在途任务清理，覆盖打开期间的EOF竞态。Python最多等待15秒，未退出则返回pending_unverified，不强杀或声称清理完成。worker_exited仅表示Node退出，不单独证明Chrome退出。尚待独立实测进程树、连接关闭和异常路径。

本小项仅建立通信基础，尚未做MCP注册、连接归属、共享停止、Windows窗口三步流程、安装依赖或wheel资源打包。宿主强制崩溃及完整桌面无干扰亦不宣称通过。测试委托GPT-6.1-sol子智能体，证据放.local/browser-transport-test/；通过后交用户验收，不先提交。

## 独立测试结果与当前状态

GPT-6.1-sol子智能体已完成`scripts/accept-browser-transport.py`及会话回归，run.log与session-regression.log均报告passed。主智能体核对脚本、原始结果及表单截图：实际仅提交transport-once一次，effect_verified为false；未知结果后拒绝重放；在途取消与并发拒绝；超时后终止会话；超大请求/响应、非法协议和依赖失败不回显正文；正常及取消用例的已追踪专属进程树全部退出，HTTP线程结束。

故意不退出的测试worker在15秒截止后明确返回pending_unverified，由测试脚本只终止该自有测试进程；此证据证明诚实报告未完成清理，不证明实现具备强制清理能力。真实浏览器和受控假worker测试分别承担效果与通信异常验证，不混淆两者。证据位于`.local/browser-transport-test/results.json`等原始文件。

因用户调整优先级，期间先完成并验收Windows三步流程；现该源码edc3609已快进合入本副本，取代上文“Windows窗口三步流程尚未实施”的当前状态。浏览器通信文件未因合入改变，仍未验收、未提交，MCP注册和共享生命周期仍是下一实施项；生产源码未修改。
