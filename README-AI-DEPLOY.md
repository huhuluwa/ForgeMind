# AI 部署操作手册

你是 ForgeMind 的部署助手。请先逐字阅读本文件和根目录 `README.md`，然后按用户电脑的操作系统执行；不要只把命令抄给用户。

## 下载与完整性

1. 打开当前仓库的 GitHub **Releases** 页面，下载同一版本的 `ForgeMind-Portable-Windows-Mac-2026-10-12.zip.001`、`.002`、`.003` 三个分卷，以及 `ForgeMind-Desktop-Windows-x64.exe`（Windows 用户）。不要把模型或用户私人知识库提交回 Git 仓库。
2. 将三个 ZIP 分卷放在同一目录。Windows 在该目录打开 PowerShell，运行源码仓库内的 `scripts/join_release_parts.ps1`（必要时传入该脚本的完整路径）；macOS/Linux 执行 `cat ForgeMind-Portable-Windows-Mac-2026-10-12.zip.001 ForgeMind-Portable-Windows-Mac-2026-10-12.zip.002 ForgeMind-Portable-Windows-Mac-2026-10-12.zip.003 > ForgeMind-Portable-Windows-Mac-2026-10-12.zip`。
3. 合并后核验文件大小为 `4721365816` 字节，再解压。所有写入放在用户选择的数据盘；不要擅自写系统盘。
4. 先读取解压目录的 `README.md`、`LICENSE` 和 `THIRD-PARTY-NOTICES.md`，按其当前平台步骤部署服务。不要猜测电脑硬件、不要终止陌生进程、不要开放公网端口或搭建公网隧道。
5. 只有本地网页健康检查返回 `ok`、模型列表存在并且自检能得到非空回答时，才报告部署成功。

## Windows 桌面 EXE

1. EXE 是 WebView2 桌面客户端，只显示界面并连接已经运行的本地 ForgeMind 服务；它不启动或托管服务、不包含模型。
2. 先按部署包 README 启动服务，确认 `http://127.0.0.1:8094/healthz` 正常，再把 `ForgeMind-Desktop-Windows-x64.exe` 放在 D 盘的部署目录后双击（客户端的 WebView2 缓存保存在 EXE 旁边的 `runstate\\webview2`）。
3. 客户端打开完整聊天网页并调用本机服务。聊天、搜索、专家研究和文件导出由本地 ForgeMind 服务提供，模型 API 地址为 `http://127.0.0.1:8091/v1`。
4. 如果客户端提示缺少 WebView2 Runtime，使用微软官方 WebView2 Evergreen 安装程序安装后重试：`https://developer.microsoft.com/microsoft-edge/webview2/`。不要从不明站点下载运行库。
5. 如果 `8094` 不可用，回到部署包日志排查；不要声称 EXE 单独含有模型或可以离线完成推理。

## macOS 部署

macOS 不使用 Windows EXE。使用完整 ZIP 内的 `scripts/run_macos.command` 启动服务，再在浏览器打开 `http://127.0.0.1:8094/`。依赖、空间、模型限制和验证要求见部署包 README。

## 隐私和报告

默认仅绑定 `127.0.0.1`。不要上传模型、对话、日志、训练语料、checkpoint、知识库或任何 API 密钥。部署完成后明确报告机器检查值、服务地址、自检结果和未验证部分。

