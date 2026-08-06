# Visual Evidence Gateway（视觉证据网关）

Visual Evidence Gateway 是一个本地 MCP 服务器。DeepSeek、OpenCode、Pi 等文本代理可以在需要时调用它读取本地图片，主任务仍留在原来的代理中。

服务器只暴露一个工具：

```text
vision.inspect(paths, query, mode="auto", rigor="normal")
```

默认后端通过本机 Codex CLI 调用 `gpt-5.6-luna`，并要求 Codex 使用 ChatGPT 登录。项目不保存账号、Token 或 API Key。Luna 不可用时，请求会失败，不会自动改用按量 API 或其他模型。

这是社区项目，不是 OpenAI 官方产品。Luna 是否可用取决于账号、地区、工作区和客户端版本。

[English](docs/README.en.md) · [架构](docs/ARCHITECTURE.md) · [安全模型](docs/SECURITY_MODEL.md) · [发布验收](FINAL_RELEASE_DECISION.md)

## 安装

先安装 Codex CLI，并使用 ChatGPT 账号登录：

```bash
npm install -g @openai/codex
codex
```

Windows PowerShell：

```powershell
irm https://raw.githubusercontent.com/scy7796/visual-evidence-gateway/main/install.ps1 | iex
```

macOS 或 Linux：

```bash
curl -fsSL https://raw.githubusercontent.com/scy7796/visual-evidence-gateway/main/install.sh | sh
```

安装器会下载对应平台的单文件程序，核对 Release 中的 SHA-256，使用绝对路径注册 MCP，然后检查 ChatGPT 登录并运行一次真实图片探针。网关本身不需要 Python、pip、venv 或 Node 运行环境。安装器也不会替你安装 Codex 或修改登录方式。

只安装和注册，暂不运行 Luna 探针：

```bash
curl -fsSL https://raw.githubusercontent.com/scy7796/visual-evidence-gateway/main/install.sh | sh -s -- --skip-probe
```

Windows：

```powershell
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/scy7796/visual-evidence-gateway/main/install.ps1))) -SkipProbe
```

安装后可以单独检查：

```bash
visual-evidence-gateway healthcheck --check-connectivity --json
visual-evidence-gateway probe --backend primary --json
codex mcp list
```

重启 Codex、IDE 扩展或其他 MCP 宿主后，工具才会重新被发现。

不想直接执行远程脚本时，可以从 [Releases](https://github.com/scy7796/visual-evidence-gateway/releases) 下载对应平台的二进制和校验和，再运行：

```bash
./visual-evidence-gateway setup
```

## 什么时候有用

这个项目适合图片只占少数步骤的长任务。例如，主代理负责规划和代码，遇到终端截图、UI、图表、流程图或前后对比图时，再调用 `vision.inspect`。主代理收到的是与问题相关的短答案、定位证据和不确定性，不是完整 OCR 或一段很长的视觉描述。

以下情况通常直接用现有工具更合适：

- Codex 本身就是主代理，只需人工查看一两张图片；
- 源码、日志、CSV 或 DOM 已经可以直接读取；
- 任务需要鼠标、键盘、浏览器操作或实时屏幕理解；
- 任务要求完全离线；
- 医学影像、工业检测或精密测量等专业场景。

## 和直接附图的区别

Codex 原生附图的路径最短，适合一次性的人工看图。Visual Evidence Gateway 适合由文本代理长期负责主任务，并通过固定工具获取视觉证据的工作流。

| 方案 | 适合的任务 | 主要差异 |
|---|---|---|
| Codex 原生附图 | Codex 是主代理，人工查看单张图 | 使用简单，视觉结果留在当前 Codex 会话中 |
| OCR | 清晰文本，速度优先 | 不理解布局、颜色、图形和 UI 状态 |
| 通用视觉 API 或 MCP | 快速接入任意视觉模型 | 路径限制、模型绑定和输出校验取决于实现 |
| Visual Evidence Gateway | 文本代理长期主控，偶尔需要看图 | 有路径授权、模型固定、裁剪重试、结构化证据和失败关闭 |

2026-08-06 的同机测试使用了六类合成图片：

| 指标 | Codex 原生附图 | 本网关 |
|---|---:|---:|
| 完成任务 | 6/6 | 6/6 |
| 预设字段完整命中 | 4/6 | 6/6 |
| 中位端到端时间 | 16.6 秒 | 20.2 秒 |
| 中位返回长度 | 602 字符 | 62 字符 |

本网关在这次测试中更慢，返回内容更短。六类合成图片不能代表所有真实任务，也不能证明本网关普遍更准。完整记录在 [`pre_release_validation/results/comparison/`](pre_release_validation/results/comparison/) 中。

## 请求如何处理

```text
文本主代理
    │ vision.inspect
    ▼
路径授权与文件稳定性检查
    ▼
图片限额、规范化和私有暂存
    ▼
Codex CLI + gpt-5.6-luna
    ▼
Schema、模型身份和语义检查
    ▼
必要时裁剪或分块重试
    ▼
短答案、定位证据和不确定性
```

主代理提交一到四个已授权图片路径和一个具体问题。默认返回内容包括短答案、带图片索引的证据、与问题直接相关的文字、不确定性，以及必要的后端和验证元数据。

完整 OCR、原始后端响应和本机缓存绝对路径默认不会进入主对话，也不会默认落盘。

## 文件、模型和数据边界

默认配置只允许读取 MCP 进程的当前工作目录。它拒绝凭据目录、配置目录、缓存目录、符号链接、junction、reparse point、UNC 或 verbatim path，以及 NTFS alternate data stream。文件大小、图片尺寸、像素数和解码过程都有上限。通过检查的图片会被复制到本次请求的私有临时目录。

Codex 子进程使用只读沙箱，并关闭 Shell、子代理、hooks、远程插件、自动依赖安装和网页搜索。网关还会检查后端返回的 JSON Schema、图片索引、状态和模型身份。ChatGPT 模式下，子进程不会继承 API Key、Base URL、组织或项目计费变量。verifier 和 fallback 默认关闭。

这些限制可以缩短图片文字到本机动作的攻击链，也能减少任意文件读取和视觉数据留存。它们不能代替完整隔离。处理高度敏感图片时，仍应使用独立系统用户、容器或虚拟机，并只授权必要目录。详细说明见 [`docs/SECURITY_MODEL.md`](docs/SECURITY_MODEL.md)。

## 图片中的指令

截图、海报和文档可能包含“忽略规则”“执行命令”或“读取密钥”等文字。网关把这些内容当作图片数据，在提示词和返回结果两端检查高风险语义。视觉后端没有 Shell、浏览器、插件或写权限。

这不能证明视觉模型永远不会受诱导。它能限制模型受诱导后可以做什么，并在结果进入主代理前再检查一次。

## 缓存和延迟

默认配置不保存原始后端响应、完整 OCR 或本机缓存路径：

```yaml
cache:
  store_raw: false
  store_full_text: false
  expose_local_refs: false
```

缓存键基于暂存后的图片字节、问题和相关配置，并使用 HMAC 签名。命中缓存时，网关仍会重新授权路径并检查文件是否被替换。这样做会保留几十毫秒的本地开销，但不会再次调用远程模型。

发布验收机上的本地流水线数据不包含网络和 Luna 推理：

| 路径 | 次数 | 中位数 | P95 | 后端调用 |
|---|---:|---:|---:|---:|
| 未命中缓存 | 80 | 92.4 ms | 146.6 ms | 1 次模拟后端 |
| 缓存命中 | 300 | 67.2 ms | 82.8 ms | 0 |

本次验收的 10 次真实探针耗时为 18.1 到 31.9 秒，中位约 21 到 25 秒。这个数字受账号、地区、网络和服务负载影响。安装后的 `probe` 会返回当前机器的 `elapsed_ms`。

## 工具参数

```text
vision.inspect(
  paths: list[str],
  query: str,
  mode: "auto" | "ui" | "text" | "chart" | "diagram" | "compare" | "general",
  rigor: "normal" | "critical" | "cheap"
)
```

`paths` 接受一到四个绝对图片路径，且路径必须位于 `allowed_roots` 内。`query` 应只描述需要从图片确认的问题。`mode` 指定任务类型，`auto` 会根据图片数量和问题选择。

`normal` 使用主后端，并在证据不足时裁剪或分块。`critical` 可以启用独立 verifier，冲突时返回部分结论。`cheap` 优先使用主后端，只在配置允许时进入备用路径。

## 默认配置

```yaml
backends:
  primary:
    enabled: true
    via: codex_cli
    command: codex
    model: "gpt-5.6-luna"
    auth_mode: chatgpt
    min_cli_version: "0.146.0"
    reasoning_effort: medium
    extra_args: [--ephemeral, --ignore-user-config]
    allow_cli_default_model: false
  verifier:
    enabled: false
  fallback:
    enabled: false

allowed_roots:
  - "{cwd}"

cache:
  store_raw: false
  store_full_text: false
  expose_local_refs: false
```

完整示例见 [`examples/config.yaml`](examples/config.yaml)。远程端点、API Key 和额外模型只能由操作者显式配置。

## 命令

```text
visual-evidence-gateway setup
visual-evidence-gateway serve
visual-evidence-gateway healthcheck
visual-evidence-gateway probe
```

手动注册：

```bash
codex mcp add visual-evidence-gateway -- visual-evidence-gateway serve
```

使用指定配置文件：

```bash
codex mcp add visual-evidence-gateway \
  --env VISUAL_EVIDENCE_GATEWAY_CONFIG=/absolute/path/to/config.yaml \
  -- visual-evidence-gateway serve
```

## v0.5.0 的验证范围

已经验证的部分包括 ChatGPT 登录、显式 `gpt-5.6-luna` 调用、10 次真实像素探针、六类图片、路径安全负例、缓存、严格 JSON Schema、官方 MCP SDK 的 stdio 协议调用、Windows 安装器，以及多平台 CI 构建。

Codex Desktop 作为 MCP 宿主的人工调用还没有完成。验证机上的 npm Codex CLI 0.146.1 无法完成 stdio MCP 工具调用，所以协议测试使用了官方 MCP SDK 客户端。这证明服务器可以完成 MCP 协议交互，不能证明 Codex Desktop 已经实测。完整裁决见 [`FINAL_RELEASE_DECISION.md`](FINAL_RELEASE_DECISION.md)。

当前还有几项限制：

- Windows ARM64 没有预构建二进制；
- 发布二进制尚未代码签名，安装器依赖 HTTPS 和 SHA-256 清单；
- macOS 和 Linux 安装器由 CI 与 POSIX 集成测试覆盖，真实账号验收机器是 Windows；
- Luna 权限和延迟由上游账号与服务状态决定；
- 默认后端需要网络。

## 故障排查

找不到 Codex：

```bash
codex --version
```

确认 npm 全局安装目录已经进入 `PATH`。

未确认 ChatGPT 登录：

```bash
codex logout
codex login
codex login status
```

默认订阅链路不接受 API Key 登录。

Luna 不可用或探针失败时，当前账号、工作区、地区、客户端版本或服务端权限可能没有开放该模型。项目不会自动切到按量 API。可以等待权限开放，或在私有配置中选择其他支持图片输入的后端。

MCP 已注册但工具不可见：

```bash
codex mcp list
```

确认存在 `visual-evidence-gateway`，然后完全重启宿主。

图片被拒绝时，将图片复制到当前项目目录。不要把整个用户主目录加入 `allowed_roots`。

## 升级和卸载

升级时重新运行对应平台的安装脚本。

卸载 MCP 注册：

```bash
codex mcp remove visual-evidence-gateway
```

随后删除安装和配置目录：

- Windows：`%LOCALAPPDATA%\VisualEvidenceGateway\bin`、`%APPDATA%\visual-evidence-gateway`；
- macOS：`~/Library/Application Support/visual-evidence-gateway`；
- Linux：`~/.local/share/visual-evidence-gateway`、`~/.config/visual-evidence-gateway`。

## 从源码开发

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install -e ".[dev]"
ruff check .
pytest
python -m compileall -q src tests scripts
python scripts/audit_release.py
```

发布前真实验收：

```bash
python pre_release_validation/run_validation.py --runs 5 --host-mcp
```

## 名称迁移

项目在 0.5.0 从 `vision-bridge-mcp` 更名为 `visual-evidence-gateway`，因为原名称已被同类项目占用。旧安装目录和 MCP 注册不会自动删除。确认不再使用后，可以执行：

```bash
codex mcp remove vision-bridge
```

旧环境变量 `VISION_BRIDGE_*` 不再生效，新前缀是 `VISUAL_EVIDENCE_GATEWAY_*`。

## 项目信息

- 当前版本：0.5.0
- 许可证：MIT
- 默认传输：本地 stdio MCP
- 默认后端：Codex CLI、`gpt-5.6-luna`、ChatGPT 登录
- 项目性质：社区项目

用过之后觉得它确实解决了问题，可以点一下 Star。这样其他需要给文本代理接视觉的人更容易找到它。
