# Visual Evidence Gateway 中文说明

完整中文说明已经移到仓库根目录的 [`README.md`](../README.md)，其中包括：

- 一键安装与真实像素验收；
- 为什么它比直接贴图、OCR、普通视觉 API 包装器和 Computer Use 更适合文本代理；
- 与 Codex 官方原生看图的正面对比，以及为什么 DeepSeek 主代理 + Luna 视觉专家更合适；
- 本地桥接开销实测和真实 Luna `elapsed_ms` 探针；
- Luna 订阅优先调用契约；
- 最小上下文、裁剪/分块重试、Schema 校验和提示注入防护；
- 安全边界、配置、故障排查、升级与卸载。

## 发布前真实验收

公开发布前运行 `python pre_release_validation/run_validation.py --runs 5 --host-mcp`。本地测试只能证明代码契约，不能证明账号权限、订阅路由、真实 Luna 延迟、宿主级 MCP 调用或跨平台安装。详见 `pre_release_validation/README.md` 与 `claims-matrix.md`。
