# 生产工具集与指南状态

v0.2.2新增生产工具集配置及指南可读状态。本项基于v0.2.1，在隔离副本tool-surface实施，用户已明确接受并要求发布成0.2.2，见WP-NEXT-049。本文交验结果保留发布前的版本与证据快照；既有v0.2.1标签的19项工具保持冻结，源码发布不表示本机已部署。

## 配置

未配置时等同于：

```json
{"tools": {"profile": "compact", "self_test": false}}
```

| profile | self_test | 公开工具数 | 额外入口 |
|---|---|---:|---|
| compact | false | 15 | 默认生产集 |
| legacy | false | 17 | 增加observe和observe_controls |
| compact | true | 17 | 增加launch_test和close_test |
| legacy | true | 19 | 旧观察入口和开发自测入口全部启用 |

profile仅接受compact／legacy，self_test必须为JSON布尔值；非法类型、未知配置键会拒绝启动，不自动猜测或扩大工具集。配置在连接建立时读取，变更后应重连；不支持调用方在工具参数中自行打开开关。

关闭自测时，tools/list不列出两个入口，tools/call及Service.call也拒绝调用，包括close_test；后台仍可通过连接清理处置自身已创建的fixture。自测只服务于显式开发配置，普通生产配置不会启动测试窗口。

## 观察接口与兼容

compact通过get_window_state提供截图、控件或组合读取，保留原参数、返回结构和全部证据边界：

- 只截图：include_accessibility=false。frame_id位于screenshot.frame_id。
- 只读控件：include_screenshot=false；不需要文字时加include_text=false。observation_id和nodes位于accessibility。
- 组合读取：保持默认。截图和控件仍非原子快照，失败与部分状态不得当作输入许可。

不再公开两个重复观察工具；直接调用会返回LEGACY_OBSERVER_DISABLED。需要旧返回结构、已有帧关联等旧语义的客户端，可由操作方显式设置legacy。内部observe／observe_controls实现继续供组合观察、窗口流程和恢复准备使用。恢复成功后的next_call按所选工具集返回可调用的观察入口；复核证据仍会失效，必须重新观察，不能重放输入。

保留工具的字段、类型、枚举、长度和数值边界均未删除；只省去语义冗余的空required数组，服务端仍拒绝未知参数。没有通过宽泛object或取消校验压缩schema。

## 指南可读状态

health.guides_available表示服务端当时能以UTF-8读取全部四份非空指南；缺失、空文件、解码或文件访问错误都返回false，修复后下一次检查即可恢复。resources/list仍是目录声明，不能用它替代实际可读检查。

该状态不表示客户端缓存已刷新或模型已经阅读指南，不作为输入授权／调用门。指南不可读时health和其他已有入口仍可工作；原指南中遇到恢复／浏览器说明不可用时停止对应操作的提示保留。

## 交验

普通测试、真实自有窗口、安装包和声明体积的最终结果在本文交验结果补记中列出。原生验收只操作本副本创建的fixture，未连接或修改生产服务；旧native验收配置显式打开自测与兼容观察，普通runner继续默认跳过原生桌面测试。

### 交验结果 · 2026-11-12

基线为v0.2.1提交50f19d782b2551a3a8577086080a9332123a9e62。原运行副本仍在该提交，本轮未改其源码、服务、宿主配置或原有未提交的WP-NEXT-047部署记录。隔离副本继承该部署记录，再补用户本轮已确认范围WP-NEXT-048；暂存区为空，未提交／推送／部署。包版本仍是开发基线0.2.1，不把本地候选wheel冒称已发布包。

| 声明文本（紧凑JSON字符数） | v0.2.1完整19项 | 默认compact 15项 | 减少 |
|---|---:|---:|---:|
| inputSchema合计 | 5,720 | 5,041 | 11.9% |
| 单项描述合计 | 4,662 | 4,101 | 12.0% |
| 完整工具定义合计 | 11,442 | 9,986 | 12.7% |

统计不含宿主附加公共说明、技能目录和按需读取正文；未测计费token、缓存或模型成功率。逐个工具的schema与基线比较，仅省略空required数组，补回其默认空值后全部相等，字段、类型、枚举、长度／数值和未知字段约束未删。原始比较在`.local/schema-comparison.json`。

验证结果：

- `python -B scripts/test_runner.py`：普通69通过、0失败、0错误，22个原生／浏览器跳过入口。真实stdio覆盖四种配置的15／17／17／19项工具集、隐藏入口拒绝、旧入口兼容和错误后连接可用；配置非法时服务资源尚未创建即拒绝。回执`.local/final-regression.log`、`.local/test-results/summary.json`。
- 文件可读性测试用真实临时文件验证全部四份指南分别缺失、恢复、空白、无效UTF-8和目录冒充文件的情况；只替换资源根目录，不替换文件读取或可用性计算。
- `python -B -m unittest test_tool_surface.ToolSurfaceNativeTests -v`（显式WINDOW_PILOT_NATIVE_TESTS=1，仅此类）：1/1通过，3.865秒。实际自有窗口截图／控件／组合读取、一次后台点击后计数1、释放操作权形成待审故障、准备与恢复、返回的compact新观察调用可用，最终计数仍1。health实际报告指南true／缺失false，缺失时状态查询仍可用；未设置读过指南的代码门。资源根目录在缺失用例中受控指向不存在路径，其余原生读取／消息／状态为真实操作。回执`.local/tool-surface-native-final.log`、`.local/tool-surface-native/result.json`，截图`.local/tool-surface-native/after.png`已查看；只含自有fixture客户区。
- wheel构建通过。`python scripts/verify-wheel.py .local/wheel/window_pilot-0.2.1-py3-none-any.whl --evidence .local/wheel-check`在干净venv验证默认15工具、4指南读取、普通模式管理员启动拒绝及隔离worker入口通过。相同wheel显式`--native`验收通过：开发开关下17工具、health字段、实际自有WPF窗口截图及49个UIA节点；未发送输入。回执`.local/wheel-check/wheel-smoke.json`和`.local/wheel-native-check/wheel-smoke.json`。
- 语法、文档本地链接及`git diff --check`通过。生产HEAD和工作区状态与本项开始时一致。必要改动之外没有扩大键鼠／浏览器／管理员IPC验收，也没有实际宿主缓存刷新或任意应用兼容性验证。

达到本项范围后停止，交用户验收；实际版本编号、发布与部署另按后续明确授权执行。

后续确认（2026-11-12）：用户明确“改完了发布成0.2.2吧”，接受本项并授权存档、更新既有GitHub仓库及v0.2.2正式发布，替代上述待验收／未授权发布状态。发布前0.2.2普通测试及干净wheel安装另行复核；不重复扩大已通过的原生验收。本轮不部署本机或写入项目／全局记忆，实际提交、Release和CI以发布回执核对。

0.2.2发布前复核：普通69通过、0失败、22跳过入口；新构建的0.2.2 wheel在干净venv安装，默认15工具、4指南读取及普通模式管理员启动拒绝通过。回执`.local/release-022-tests.log`及`.local/wheel-022-check/wheel-smoke.json`。原生执行逻辑未变，沿用上述已通过专项范围，不将本轮普通／wheel复核写成重新完成所有原生验收。
