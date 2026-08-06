# Visual Evidence Gateway（视觉证据网关）

Visual Evidence Gateway 是一个本地 MCP 服务器，让 DeepSeek、OpenCode、Pi 等文本代理在需要时读取本地图片，而不必把整个任务切换到多模态代理。

它只暴露一个工具：

```text
vision.inspect(paths, query, mode="auto", rigor="normal")
```

默认后端通过本机 Codex CLI 调用 `gpt-5.6-luna`，并要求使用 ChatGPT 登录。项目不保存账号、Token 或 API Key；如果 Luna 不可用，会直接报错，不会自动切到按量 API 或其他模型。

这是社区项目，不是 OpenAI 官方产品。模型权限取决于账号、地区、工作区和客户端版本。

[English](docs/README.en.md) · [架构](docs/ARCHITECTURE.md) · [安全模型](docs/SECURITY_MODEL.md) · [发布验收](FINAL_RELEASE_DECISION.md)

## 安装

前置条件：已安装 Codex CLI，并使用 ChatGPT 账号登录。

```bash
npm install -g @openai/codex
codex
```

Windows PowerShell：

```powershell
irm https://raw.githubusercontent.com/scy7796/visual-evidence-gateway/main/install.ps1 | iex
```

macOS / Linux：

```bash
curl -fsSL https://raw.githubusercontent.com/scy7796/visual-evidence-gateway/main/install.sh | sh
```

安装器会：

1. 下载与系统和 CPU 匹配的单文件程序；
2. 校验 Release 中的 SHA-256；
3. 使用绝对路径注册 MCP；
4. 检查 ChatGPT 登录并运行一次真实图片探针。

网关本身不需要 Python、pip、venv 或 Node 运行环境。安装器也不会替你安装 Codex 或修改登录方式。

只完成安装和注册、暂不运行 Luna 探针：

```bash
curl -fsSL https://raw.githubusercontent.com/scy7796/visual-evidence-gateway/main/install.sh | sh -s -- --skip-probe
```

Windows：

```powershell
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/scy7796/visual-evidence-gateway/main/install.ps1))) -SkipProbe
```

之后可单独检查：

```bash
visual-evidence-gateway healthcheck --check-connectivity --json
visual-evidence-gateway probe --backend primary --json
codex mcp list
```

安装后需要重启 Codex、IDE 扩展或其他 MCP 宿主，使其重新发现工具。

不希望直接执行远程脚本时，可以从 [Releases](https://github.com/scy7796/visual-evidence-gateway/releases) 下载对应平台的二进制和校验和，然后运行：

```bash
./visual-evidence-gateway setup
```

## 适用场景

这个项目适合以下工作流：

- 主代理是 DeepSeek、OpenCode、Pi 或其他文本模型；
- 图片只占任务中的少数步骤；
- 需要读取终端截图、UI、图表、流程图或前后对比图；
- 希望主代理只收到问题相关的证据，而不是完整 OCR 和长篇视觉描述；
- 希望限制图片读取范围，并明确知道实际调用了哪个视觉模型。

以下场景通常不需要它：

- Codex 本身就是主代理，只需人工查看一两张图片；
- 源码、日志、CSV 或 DOM 已经可以直接读取；
- 任务需要鼠标、键盘、浏览器操作或实时屏幕理解；
- 任务要求完全离线；
- 医学影像、工业检测或精密测量等专业场景。

## 它和直接附图有什么区别

Codex 原生附图更适合一次性的人工看图。Visual Evidence Gateway 解决的是跨代理调用和结果约束：文本主代理通过固定的 MCP 工具请求视觉证据，Luna 只负责读取图片。

| 方案 | 更适合 | 主要差异 |
|---|---|---|
| Codex 原生附图 | Codex 是主代理、人工查看单张图 | 路径最短，使用最简单 |
| OCR | 清晰文本、速度优先 | 不理解布局、颜色、图形和 UI 状态 |
| 通用视觉 API/MCP | 快速接入任意视觉模型 | 是否有路径限制、模型绑定和输出校验取决于具体实现 |
| Visual Evidence Gateway | 文本代理长期主控，偶尔需要可靠看图 | 只读路径、模型固定、裁剪重试、结构化证据、最小返回和失败关闭 |

在 2026-08-06 的同机六类合成样本中：

- Codex 原生附图和本网关都完成了 6/6 个任务；
- 预设关键字段完整命中：原生附图 4/6，本网关 6/6；
- 中位端到端时间：原生附图 16.6 秒，本网关 20.2 秒；
- 中位返回长度：原生附图 602 字符，本网关 62 字符。

这组测试只说明当前样本和机器上的结果。它不能证明本网关在所有图片上更准确或更快。完整记录见 [`pre_release_validation/results/comparison/`](pre_release_validation/results/comparison/)。

## 工作方式

```text
文本主代理
    │ vision.inspect
    ▼
路径授权与稳定读取
    ▼
图片限额、规范化和私有暂存
    ▼
Codex CLI + gpt-5.6-luna
    ▼
Schema、模型身份和语义检查
    ▼
必要时裁剪或分块重试
    ▼
简短答案、定位证据和不确定性
```

主代理提交一到四个已授权图片路径和一个具体问题。网关默认只返回：

- 简短答案；
- 带图片索引的证据；
- 与问题直接相关的少量文字；
- 不确定性；
- 必要的后端和验证元数据。

完整 OCR、原始后端响应和本机缓存绝对路径默认不会进入主对话，也不会默认落盘。

## 默认安全边界

默认配置采取以下限制：

- 只允许读取 MCP 进程当前工作目录；
- 拒绝凭据目录、配置目录和缓存目录；
- 拒绝符号链接、junction、reparse point、UNC/verbatim path 和 NTFS alternate data stream；
- 对文件大小、图片尺寸、像素数和解码过程设限；
- 授权后将图片复制到每次请求的私有临时目录；
- Codex 子进程使用只读沙箱；
- 关闭 Shell、子代理、hooks、远程插件、自动依赖安装和网页搜索；
- 强制检查后端返回的 JSON Schema、图片索引、状态和模型身份；
- 从 ChatGPT 模式的子进程环境中移除 API Key、Base URL、组织和项目计费变量；
- verifier 和 fallback 默认关闭。

这些措施减少了任意文件读取、提示注入转化为本机动作、模型静默替换和视觉数据长期留存的风险，但它不是完整隔离容器。处理高度敏感图片时，仍应使用独立系统用户、容器或虚拟机，并只授权最小目录。

详细说明见 [`docs/SECURITY_MODEL.md`](docs/SECURITY_MODEL.md)。

## 图片提示注入

图片中的文字可能包含“忽略规则”“执行命令”“读取密钥”等内容。网关把图片文字视为待观察数据，并在返回前检查执行声明和高风险语义。

它不能保证视觉模型永远不会受诱导。它的作用是让视觉后端没有 Shell、浏览器、插件和写权限，并在结果进入主代理前增加一道检查。

## 缓存

默认配置：

```yaml
cache:
  store_raw: false
  store_full_text: false
  expose_local_refs: false
```

缓存键基于实际暂存的图片字节、问题和相关配置，并使用 HMAC 签名。缓存命中时仍会重新进行路径授权和文件稳定性检查，因此本地耗时不会降到零；主要收益是避免重复调用远程模型。

发布验收机上的本地流水线数据（不包含网络和 Luna 推理）：

| 路径 | 次数 | 中位数 | P95 | 后端调用 |
|---|---:|---:|---:|---:|
| 未命中缓存 | 80 | 92.4 ms | 146.6 ms | 1 次模拟后端 |
| 缓存命中 | 300 | 67.2 ms | 82.8 ms | 0 |

真实 Luna 延迟取决于账号、地区、网络和服务负载。安装后的 `probe` 会返回当前机器的 `elapsed_ms`。本次验收的 10 次真实探针范围为 18.1–31.9 秒，中位约 21–25 秒；这不是固定性能承诺。

## MCP 工具

```text
vision.inspect(
  paths: list[str],
  query: str,
  mode: "auto" | "ui" | "text" | "chart" | "diagram" | "compare" | "general",
  rigor: "normal" | "critical" | "cheap"
)
```

- `paths`：一到四个绝对图片路径，必须位于 `allowed_roots` 内；
- `query`：只写需要从图片确认的问题；
- `mode`：任务类型，`auto` 会根据图片数量和问题选择；
- `normal`：主后端，证据不足时允许裁剪或分块；
- `critical`：可启用独立 verifier，冲突时返回部分结论；
- `cheap`：优先主后端，只在配置允许时进入备用路径。

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

## 验证状态

v0.5.0 已验证：

- ChatGPT 登录和显式 `gpt-5.6-luna` 调用；
- 10 次真实随机像素探针；
- OCR、UI、图表、前后对比、长图和图片提示注入样本；
- 未授权路径、非图片、symlink/junction 等负例；
- 缓存命中不重复调用后端；
- 后端载荷的严格 JSON Schema；
- 官方 MCP SDK 客户端通过 stdio 完成协议级调用；
- Windows 安装器模拟、真实单文件程序探针和多平台 CI 构建。

需要明确区分：**Codex Desktop 作为宿主的重启后人工调用尚未完成验证。** 当前 Windows 上的 npm Codex CLI 0.146.1 无法完成 stdio MCP 工具调用；协议级验收使用官方 MCP SDK 客户端。该限制不会影响服务器协议测试，但不能等同于 Codex Desktop 已经实测。

完整裁决见 [`FINAL_RELEASE_DECISION.md`](FINAL_RELEASE_DECISION.md)。

## 已知限制

- Codex Desktop 宿主级调用仍需人工验证；
- Windows ARM64 暂无预构建二进制；
- 发布二进制尚未代码签名，安装器依赖 HTTPS 和 SHA-256 清单；
- macOS/Linux 安装器已由 CI 和 POSIX 集成测试覆盖，但本次真实账号验收机器是 Windows；
- Luna 权限和延迟由上游账号与服务状态决定；
- 默认后端需要网络。

## 故障排查

### 找不到 Codex

```bash
codex --version
```

确认 npm 全局安装目录已经进入 `PATH`。

### 未确认 ChatGPT 登录

```bash
codex logout
codex login
codex login status
```

默认订阅链路不接受 API Key 登录。

### Luna 不可用或探针失败

这通常表示当前账号、工作区、地区、客户端版本或服务端权限没有暴露该模型。项目不会自动切到按量 API。可以等待权限开放，或在私有配置中显式选择其他支持图片输入的后端。

### MCP 已注册但工具不可见

```bash
codex mcp list
```

确认存在 `visual-evidence-gateway`，然后完全重启宿主。

### 图片被拒绝

将图片复制到当前项目目录。不要为了省事把整个用户主目录加入 `allowed_roots`。

## 升级与卸载

升级：重新运行对应平台的安装脚本。

卸载 MCP 注册：

```bash
codex mcp remove visual-evidence-gateway
```

删除安装和配置目录：

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

项目在 0.5.0 从 `vision-bridge-mcp` 更名为 `visual-evidence-gateway`，原因是原名称已被同类项目占用。

旧安装目录和 MCP 注册不会自动删除。确认不再使用后，可手工执行：

```bash
codex mcp remove vision-bridge
```

旧环境变量 `VISION_BRIDGE_*` 不再生效；新前缀为 `VISUAL_EVIDENCE_GATEWAY_*`。

## 项目状态

- 当前版本：0.5.0
- 许可证：MIT
- 默认传输：本地 stdio MCP
- 默认后端：Codex CLI + `gpt-5.6-luna` + ChatGPT 登录
- 项目性质：社区项目，非 OpenAI 官方产品
