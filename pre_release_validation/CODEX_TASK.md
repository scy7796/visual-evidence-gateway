# 给 Codex 的执行任务：Visual Evidence Gateway v0.5.0 发布前真实验收

你正在审计一个准备公开发布的 MCP 项目。不要只阅读代码或复述 README。必须在当前机器上实际安装、运行、记录结果、修复可安全修复的问题，并重新验证。

## 目标

判断 Visual Evidence Gateway v0.5.0 是否可以公开发布。重点验证：

1. 默认链路是否确实为本机 Codex CLI + ChatGPT 登录 + `gpt-5.6-luna`；
2. 是否会静默切换到 API Key 计费、默认模型、verifier 或 fallback；
3. 一键安装、MCP 注册、真实像素探针和实际 `vision.inspect` 是否工作；
4. UI、OCR、图表、前后对比、长图和提示注入样本是否真实通过；
5. README 的宣传是否超过现有证据；
6. 发布包是否包含个人路径、凭据、运行状态、缓存或构建垃圾。

## 执行规则

- 先阅读 `pre_release_validation/README.md`、`README.md`、`AUDIT_REPORT.md` 和 `TEST_REPORT.md`。
- 不得读取、打印、复制或提交 `~/.codex/auth.json` 的内容。
- 不得创建或使用 API Key。若当前登录不是 ChatGPT，停止并报告 P0 失败。
- 不得为了让测试通过而开启 verifier/fallback、允许 CLI 默认模型或放宽只读/禁用工具策略。
- 不得把模拟后端结果写成真实 Luna 结果。
- 可以修改当前仓库内的代码、测试和文档，但保持最小充分改动。
- 每次修复后必须重新运行相关测试和完整发布检查。

## 必须执行

在仓库根目录：

```bash
python pre_release_validation/run_validation.py --runs 5 --host-mcp
```

然后执行：

```bash
python -m compileall -q src tests scripts pre_release_validation
python -m pytest
python scripts/audit_release.py
python scripts/benchmark_local.py
python scripts/verify_artifacts.py dist
codex login status
codex mcp list
visual-evidence-gateway-healthcheck --check-connectivity --json
visual-evidence-gateway-probe --backend primary --json
```

如果平台是 Windows，再执行并记录：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 -WhatIf
```

如果 `-WhatIf` 未被脚本支持，不要假装通过；审计脚本后使用干净测试用户或隔离目录真实执行安装。

## MCP 宿主级测试

1. 确认 `codex mcp list` 中存在 `visual-evidence-gateway`。
2. 在 Codex TUI 或 IDE 中使用 `/mcp` 确认 `vision.inspect` 可见。
3. 通过 MCP 工具读取 `pre_release_validation/results/fixtures/text.png`，问题为：
   `只返回图片中的 RELEASE CODE，并给出证据位置。`
4. 报告工具原始结构中的 `status`、`evidence.image_index`、`verified_by` 和 `uncertainty`，不要输出本机绝对路径。

## 对比测试

在同一机器、同一账号和同一图片上比较：

- A：通过 Visual Evidence Gateway 的 `vision.inspect`；
- B：Codex 原生直接附图并显式指定 `gpt-5.6-luna`。

至少比较：

- 是否答对；
- 端到端耗时；
- 输出长度；
- 是否有结构化证据、图片索引和不确定性；
- 是否有路径授权、缓存、提示注入终检和失败关闭。

不要预设 A 的视觉准确率更高。Visual Evidence Gateway 的核心假设是系统契约和跨主代理复用更强；若 B 更快或同样准确，应如实记录。

## 最终输出

必须生成并填写：

```text
pre_release_validation/results/REAL_WORLD_TEST_REPORT.md
pre_release_validation/results/validation-result.json
```

最终裁决只能是 `PASS`、`CONDITIONAL PASS` 或 `FAIL`。列出：

- 已通过的 P0；
- 未通过的 P0；
- P1 限制；
- 实测 Luna latency median/p95/min/max；
- 六类视觉样本通过率；
- 原生方案对比结果；
- 所做修复和重新验证命令；
- 当前允许写进公开 README 的宣传语；
- 当前必须删除或降级的宣传语。
