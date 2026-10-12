# ForgeMind V4

ForgeMind 是基于 MiniMind 源码构建的本地 AI 项目，包含中文聊天与搜索界面、OpenAI 兼容模型 API、领域专家知识库、文件导出和代码训练/评测源码。AI 部署助手请先阅读 [README-AI-DEPLOY.md](README-AI-DEPLOY.md)。V4 完整训练与部署流程见 [图文 PDF 教程](docs/ForgeMind-V4-全流程训练与部署教程_公开版_20261012.pdf)。

## Release 下载

完整 Windows/macOS 部署包和 Windows 桌面客户端放在 GitHub **Releases**，不是 Git 历史。由于部署 ZIP 有 4.72 GB，分成 `.001`、`.002`、`.003` 三个文件；下载全部分卷后按部署指南合并。每个分卷小于 GitHub Release 单文件 2 GiB 限制。

Windows 桌面 EXE 是 WebView2 客户端。它不启动或托管模型/网页服务，也不包含模型权重；它连接已启动的本地 ForgeMind 服务：界面与搜索/专家接口 `http://127.0.0.1:8094/`，模型 API `http://127.0.0.1:8091/v1`。Windows 电脑如果没有 WebView2 Evergreen Runtime，需要按部署指南从微软官网安装。

## 源码目录

- `minimind/`：MiniMind 基础训练代码，以及 ForgeMind 训练、模型和专家运行时代码。
- `source/`：可部署的 ForgeMind 聊天/API 后端。
- `web/`：聊天界面。
- `scripts/`：服务启动、停止、验证和分卷合并脚本。
- `desktop/`：Windows WebView2 桌面客户端源码。
- `docs/`：V4 图文教程。

本仓库排除了 GGUF/权重、训练数据、checkpoint、运行日志、聊天记录和本机专家知识库。大模型文件在 Release 部署包中，训练数据与私人运行资料留在用户本机。

