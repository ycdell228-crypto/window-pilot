# 安装与最短接入 / Quick start

适用交互式Windows 10/11、Python 3.12+。wheel提供普通权限stdio MCP；管理员服务与DSH原生插件安装仍使用保留的源码目录和对应脚本，分别审查后执行，不能把pipx安装称为管理员服务安装。

## 1. 从本地源码构建wheel

在下载解压或克隆的源码目录运行：

```powershell
.\scripts\build-wheel.ps1 -Python 'C:\path\to\python.exe'
```

得到`dist/window_pilot-0.1.0-py3-none-any.whl`及SHA-256。构建脚本遇到已有wheel会拒绝覆盖，改用新的-Destination目录。版本号沿用当前项目元数据，此开发产物不替换已经发布的v0.1.0标签或其源码包；未经另行发布，不要假定PyPI或GitHub已有这个wheel。

## 2. 隔离安装，二选一

已经安装pipx的用户：

```powershell
pipx install '.\dist\window_pilot-0.1.0-py3-none-any.whl'
window-pilot --help
```

无需pipx的本地虚拟环境方式：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --no-index '.\dist\window_pilot-0.1.0-py3-none-any.whl'
.\.venv\Scripts\window-pilot.exe --help
```

wheel包含UIA/focus/fixture与隔离截图子进程所需的运行文件；普通stdio模式不要求保持源码目录。`-I -S`子进程仍只显式加载自己的安装环境。代码所在目录与数据目录分离；日志、原图与回执写入所选config所在目录的.local，不写入site-packages。

需要可重建的本地源码包时，用`scripts/package.ps1 -Destination <新目录>`生成包含setup.py、MANIFEST.in和运行脚本的源码ZIP；脚本保留已有文件拒绝覆盖的行为。源码ZIP、wheel及测试截图都留在Git忽略目录，发布附件需另行确认。

## 3. 创建自己的配置并由宿主托管

最小无额外依赖配置（显式选择PrintWindow，应用兼容性需自行验证）：

```json
{"window_control":{"capture_backend":"printwindow"},"app_launch":{"enabled":false}}
```

保存为自己的`C:\path\to\pilot-data\config.json`。这是JSON行stdio服务，不是网页或聊天界面；将以下等价命令交给MCP宿主托管，具体注册见[CODEX](CODEX.md)或[DSH](DSH.md)：

```powershell
window-pilot serve --config 'C:\path\to\pilot-data\config.json'
```

使用pipx时通过`Get-Command window-pilot`确定实际exe绝对路径，宿主command使用该路径，args为`["serve","--config","C:\\path\\to\\pilot-data\\config.json"]`；使用venv时command为该venv内Scripts/window-pilot.exe。不要把终端等待JSON请求误判为程序无响应。

默认WGC及大图有界预览所需依赖仍见[requirements-wgc.txt](../requirements-wgc.txt)。pipx环境可用`pipx inject window-pilot -r .\requirements-wgc.txt`；venv用其python执行`-m pip install -r requirements-wgc.txt`。可选依赖安装需要网络和适配当前Python的Windows wheel，不会因截图失败自动切换后端。已有源码安装仍可沿用.local/wgc-deps。

## 验证与卸载

```powershell
python scripts/verify-wheel.py dist/window_pilot-0.1.0-py3-none-any.whl --evidence .local/wheel-smoke
```

该检查在临时venv安装真正wheel、从非源码目录启动console入口，验证13项工具、普通模式拒绝程序启动及隔离子进程导入。另加`--native`会显示并关闭项目自己的测试窗口，验证真实PrintWindow截图和只读UIA；不发键鼠输入、不安装管理员服务、不连接现有执行端。输出wheel-smoke.json；原生模式另有installed-fixture.png。需要交互桌面权限时应在用户已同意的环境执行，不用普通CI绿灯替代。

卸载pipx应用用`pipx uninstall window-pilot`；venv方式在宿主移除该MCP配置并停止进程后可移除自己创建的venv。两者均不卸载另行安装的管理员任务，也不删除config目录中的证据或去重回执，管理员回退见[ADMIN_SERVICE](ADMIN_SERVICE.md)。

## English overview

Build the local wheel with `scripts/build-wheel.ps1`, then install it with pipx or a dedicated Python venv. Configure your MCP host to run `window-pilot serve --config <absolute-config-path>`. Use the explicit PrintWindow config above for the dependency-free starting path; WGC/Pillow are optional dependencies listed in requirements-wgc.txt.

Windows 10/11 and Python 3.12+ are required. Administrator service installation remains a separate, explicitly approved source-based operation. The service trusts accessible same-user, same-session clients; purpose strings do not prove human approval. CI regression checks skip native desktop input. The wheel smoke check verifies installation and protocol behavior; `--native` adds only project-owned screenshot/UIA observation, not keyboard/mouse or privileged end-to-end coverage.
