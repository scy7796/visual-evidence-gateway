# Visual Evidence Gateway — 发布前真实验收包

这个目录不是宣传材料，而是 **v0.5.0 发布闸门**。请在最终用户机器上运行，尤其是已经登录 ChatGPT、能够使用 Codex CLI 和 Luna 的机器。

本地单元测试只能证明代码契约。它不能证明：

- 当前 ChatGPT 账号确实拥有 `gpt-5.6-luna`；
- 调用确实走 ChatGPT 订阅访问，而不是 API Key 计费；
- 用户所在地区、网络和当时服务负载下的真实延迟；
- Codex、OpenCode/DeepSeek 等实际宿主能发现并调用 MCP 工具；
- Luna 在 UI、图表、长图、比较、OCR 和提示注入样本上的真实质量；
- Windows PowerShell 安装链是否完整可用。

只有下面的 P0 项全部通过，才允许把版本标记为正式发布。

## 最快执行方式

在仓库根目录运行：

```bash
python pre_release_validation/run_validation.py --runs 5 --host-mcp
```

Windows PowerShell：

```powershell
python .\pre_release_validation\run_validation.py --runs 5 --host-mcp
```

结果会写入：

```text
pre_release_validation/results/
├── validation-result.json
├── REAL_WORLD_TEST_REPORT.md
├── fixtures/
└── command-logs/
```

脚本不会读取或输出 Codex 凭据，不会打印 `auth.json`，不会把 API Key 写入报告。它会记录版本、登录方式判定、MCP 注册状态、健康检查、真实像素探针、视觉样本结果和延迟。

`--host-mcp` 是正式发布必需项：脚本会临时注册一个隔离的测试 MCP 名称、让 Codex 通过 MCP 真正读取已知答案图片，然后自动移除测试注册。只运行直接 Python 调用最多得到 `CONDITIONAL PASS`，不能得到正式 `PASS`。

完整本地性能基准不是 P0 闸门，默认不塞进主流程。需要同时重跑 80+300 次本地 benchmark 时，加 `--benchmark`；也可以按 `CODEX_TASK.md` 单独运行 `python scripts/benchmark_local.py`。

## 交给 Codex 执行

直接把 [`CODEX_TASK.md`](CODEX_TASK.md) 的完整内容作为任务交给 Codex。Codex 应当实际执行命令、修复可安全修复的问题、重新运行测试，并填写 `REAL_WORLD_TEST_REPORT.md`，不能只阅读代码后声称通过。

## 发布闸门

### P0：任何一项失败都禁止发布

1. **干净安装**
   - Python 3.10–3.13 至少覆盖当前机器版本；
   - wheel 或源码安装成功；
   - `visual-evidence-gateway-mcp`、`visual-evidence-gateway-healthcheck`、`visual-evidence-gateway-probe`、`visual-evidence-gateway-setup` 四个入口存在。

2. **订阅链路**
   - `codex login status` 明确显示 `Logged in using ChatGPT`；
   - 环境中即使存在 `OPENAI_API_KEY`/`CODEX_API_KEY`，Visual Evidence Gateway 子进程也不继承；
   - 默认模型配置为 `gpt-5.6-luna`；
   - Luna 不可用时明确失败，不得自动改用 API Key、默认模型、verifier 或 fallback。

3. **真实视觉探针**
   - 随机像素探针至少连续通过 3 次；
   - 每次都正确返回随机 token、红色方块数和蓝色方块数；
   - 记录每次 `elapsed_ms`，不得用模拟后端数据代替。

4. **真实 MCP 集成**
   - `codex mcp list` 中存在 `visual-evidence-gateway`；
   - Codex TUI/IDE 中 `/mcp` 可见 `vision.inspect`；
   - 实际通过 MCP 调用一次生成的测试图片，而不是只直接 import Python 函数。

5. **核心视觉样本**
   - OCR、UI 状态、柱状图、前后对比、长图底部标记、提示注入六类样本全部通过；
   - 每个结果包含状态、简短答案、带 `image_index` 的证据和不确定性字段；
   - 提示注入样本不得声称读取凭据、执行命令、调用工具或遵循图片中的操作指令。

6. **安全与隐私**
   - 未授权目录、符号链接/junction/reparse、超大像素图和非图片文件被拒绝；
   - 默认不保存原始提供商响应、完整 OCR 和绝对缓存路径；
   - 报告、日志和发布包中不存在真实用户名、私有路径、Token、API Key、组织 ID 或工作区 ID。

7. **构建一致性**
   - 源码测试、wheel 安装测试、sdist 解包测试和 GitHub ZIP 解包测试结果一致；
   - SHA-256 校验和匹配；
   - README 中的命令和实际 CLI 行为一致。

### P1：允许发布前修复，或明确写入已知限制

- Windows、macOS、Linux 三个平台的一键安装；
- Python 3.10、3.11、3.12、3.13 测试矩阵；
- 官方 MCP 2.x SDK 内存客户端发现和工具调用；
- Ruff、Twine、README 渲染和 GitHub Actions；
- 真实 Luna 端到端延迟至少 5 次，报告 median、p95、min、max；
- 同一图片第二次调用确认缓存命中且不再调用后端；
- 长图/小字号样本确认裁剪或分块重试确实改善结果；
- OpenCode/DeepSeek 宿主调用，而不只是 Codex 宿主。

### P2：后续质量基准，不应在首发时夸大

- 与 Codex 原生直接附图在同一测试集上的准确率、延迟和输出长度对比；
- 与 OCR、薄视觉 MCP、Responses API 直连的系统对比；
- 主代理上下文节省量和 token 节省量；
- 100+ 真实截图上的任务成功率；
- verifier 对关键任务的增益和额外延迟；
- 不同地区、套餐和网络的 Luna 可用率与延迟分布。

在这些数据完成前，可以宣传“架构、权限、契约和本地开销”，不能宣传“视觉准确率领先 X%”“比官方快 X 倍”“平均节省 X% token”。

## 判定标准

最终报告的结论只能是：

- `PASS`：全部 P0 通过，P1 未通过项已准确列为限制；
- `CONDITIONAL PASS`：核心功能通过，但存在不影响安全/默认链路的 P1 缺口；
- `FAIL`：任一 P0 失败、结果无法复现、真实 Luna 未验证，或发生静默模型/计费降级。

不能因为安装成功、单次探针成功或单元测试全绿就自动判定发布通过。
