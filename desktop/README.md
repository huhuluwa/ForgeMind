# Windows 桌面启动器

`ForgeMind-Desktop-Windows-x64.exe` 会先检查本地服务；若未运行，它会自动定位 ForgeMind 部署包并执行 `scripts/run_windows.ps1`，等待网页健康检查通过后在桌面窗口打开聊天界面。

- 默认查找 `D:\simon\ForgeMind-Work\project\output\ForgeMind-Portable-2026-10-12`，也支持 `FORGEMIND_DEPLOYMENT_DIR` 环境变量；未找到时可在文件夹选择框中选择部署包根目录。
- 启动模型 API `http://127.0.0.1:8091/v1` 与网页服务 `http://127.0.0.1:8094/`。模型权重仍由部署包提供，EXE 不包含权重。
- 首次启动会按部署脚本创建 Python 环境并安装网页依赖，可能需要几分钟和网络。
- 需要 Microsoft Edge WebView2 Evergreen Runtime；缺少时从微软官网安装：<https://developer.microsoft.com/microsoft-edge/webview2/>。
- 源码在本目录；官方接入说明见微软 WebView2 WinForms 文档：<https://learn.microsoft.com/en-us/microsoft-edge/webview2/get-started/winforms>。
