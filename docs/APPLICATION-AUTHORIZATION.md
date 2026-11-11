# 应用访问范围与授权生命周期

授权来自宿主维护的配置，不来自模型填写的purpose、窗口文本或网页内容。本实现是同用户执行端的访问策略，不是防御同账户恶意程序篡改配置的安全边界。

`config.local.json`可设置`authorization.mode`：

- `legacy_task_scope`（未配置时默认）：兼容现有安装，由宿主/用户任务限定访问；返回的策略含human_authorization_verified:false，不能声称用途字符串已经通过授权验证。
- `enforced`：只有匹配且未过期、未撤回的服务端grant才允许绑定/读取/输入。没有grant即拒绝，配置损坏也拒绝，不降级。

```json
{
  "authorization": {
    "mode": "enforced",
    "grants": [{
      "id": "operator-local-form-task",
      "expires_at": "2026-11-11T23:00:00+08:00",
      "access": ["browser"],
      "origins": ["http://127.0.0.1:8123"],
      "executables": [],
      "revoked": false
    }]
  }
}
```

示例时间仅演示格式，实际由操作人按任务设置。浏览器还需browser.enabled、node/executable/playwright绝对路径和allowed_origins。origin精确匹配协议/主机/端口，不允许通配符或使用purpose代替grant。

Windows应用grant使用executables绝对路径及access：observe、observe_and_click、observe_and_mouse、observe_and_control或observe_and_foreground；对应写权限包含只读observe，不互相扩大到其他写模式。精确窗口身份、控件、观察时效等原保护继续适用；grant不授权任意命令或管理员提权。

新建：操作人在任务外维护配置，模型没有创建grant的MCP接口。到期：expires_at必须有时区，过期拒绝。撤回：移除grant或设revoked:true。下一调用及在途检查重新读取文件，不复用启动时授权快照；在途效果可能已发生，返回unknown并停输，不撤销或重复输入。清理/end/解绑不因撤回被阻塞。前置检查明确未派发时报告not_sent。

改变浏览器可执行文件等宿主启动配置需重建连接；授权grant本身按调用/在途轮询重读。跨调用不是原子授权事务，文件写入间隙会拒绝；操作人宜采用临时文件加原子替换更新配置。

这一步提供范围、期限和撤回，不宣称具备签名用户审批界面、操作系统身份隔离或任意程序安全认证。严格模式需操作人明确配置；兼容模式不得在对外说明中伪装成严格授权已启用。
