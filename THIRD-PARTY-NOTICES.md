# 第三方组件与模型说明

- 模型权重：Qwen2.5-Coder-7B-Instruct 的 Q4_K_M GGUF 量化文件，模型许可为 Apache License 2.0。上游模型卡与许可见 https://huggingface.co/Qwen/Qwen2.5-Coder-7B-Instruct-GGUF 和 https://huggingface.co/Qwen/Qwen2.5-Coder-7B-Instruct/blob/main/LICENSE。
- 推理运行时：随包携带的 Windows llama.cpp 二进制文件；上游项目采用 MIT License，见 https://github.com/ggml-org/llama.cpp/blob/master/LICENSE。OpenMP 许可文本随 Windows 运行时附带。
- 拼音组件：pypinyin 0.55.0，MIT License；许可文本位于 licenses/pypinyin-MIT.txt。
- ForgeMind / MiniMind 项目源码许可文本随包根目录 LICENSE 提供。对各第三方组件仍应分别遵守其上游许可。
- 量价专家知识库保存搜索来源摘要与原创整理内容；原网页版权归各来源所有，引用链接随资料保存。