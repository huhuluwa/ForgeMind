# Windows 桌面客户端

`ForgeMind-Desktop-Windows-x64.exe` 是 Windows x64 的 WebView2 桌面客户端。它只显示桌面界面，不启动服务器、不自带模型；聊天、搜索、专家研究和导出由已部署的 ForgeMind 服务提供。

- 先启动部署包内的 ForgeMind 服务。
- 客户端连接 `http://127.0.0.1:8094/`，该服务调用 `http://127.0.0.1:8091/v1` 模型 API。
- 需要 Microsoft Edge WebView2 Evergreen Runtime；缺少时从微软官网安装：<https://developer.microsoft.com/microsoft-edge/webview2/>。
- 源码在本目录；官方接入说明见微软 WebView2 WinForms 文档：<https://learn.microsoft.com/en-us/microsoft-edge/webview2/get-started/winforms>。
