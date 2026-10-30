# 可选程序启动限制

在config文件顶层配置app_launch；缺省为`{"enabled": true}`，兼容此前管理员服务允许启动任意有效本地exe的行为。普通直连stdio仍始终拒绝launch_app，不因配置开启获得管理员能力。

关闭程序启动接口：

```json
{"app_launch": {"enabled": false}}
```

只允许选定exe（示例路径需替换为自己机器上实际存在的文件）：

```json
{
  "app_launch": {
    "enabled": true,
    "allowlist": ["C:\\Program Files\\Example\\Example.exe"]
  }
}
```

allowlist省略表示不限制exe，显式空数组表示一个exe也不允许。路径必须是已存在的绝对本地exe，按解析后的规范路径比较，不支持目录前缀/通配符。格式错误或不存在的白名单路径拒绝加载，不退回无限制。策略在服务创建时加载；修改后需空闲停止/启动服务并重连，旧输入不重放。health.app_launch报告enabled、allowlist_configured及allowed_executable_count。

拒绝发生在创建进程或持久化占用request_id之前；已有启动去重记录仍保留，且不得借重复request_id绕过新限制。关闭接口不关闭已启动程序，也不撤销其他窗口输入工具。

这只是操作方限制误用范围的配置，不是人工批准系统或防御同账户恶意代码的安全边界。它不约束允许程序的args/cwd、子进程、插件或DLL；允许解释器/可执行命令的程序可能继续执行其他代码，可写路径中的exe也可能被替换。同账户代码修改配置/源码及管理员窗口输入的既有信任范围仍存在。需要真正对抗这些威胁时，需要独立设计受保护的策略、程序身份/参数约束与可信批准链，不能把路径白名单称为完整隔离。
