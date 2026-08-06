# 发布帖草稿

建议先完成一次 Codex Desktop 重启后的真实 `vision.inspect` 调用，再发布下面这段。把最后一行的宿主版本和截图补上即可。

---

我把一个给文本模型补视觉的工具开源了：Visual Evidence Gateway。

它不是把整张图直接塞进主对话，而是给 DeepSeek、OpenCode、Pi 这类文本代理提供一个只读 MCP 工具：

```text
vision.inspect(paths, query)
```

主代理继续负责规划和代码；只有答案确实依赖图片时，才让 Luna 读取指定图片。返回的是简短答案、定位证据和不确定性，不是完整 OCR 或一大段视觉描述。

默认链路复用本机 Codex 的 ChatGPT 登录，并显式指定 `gpt-5.6-luna`。项目不保存 API Key；Luna 不可用时直接失败，不会静默切到按量 API 或其他模型。

我主要补了几个普通视觉包装器容易忽略的地方：

- 只允许读取授权目录中的图片；
- 拒绝 symlink、junction 和常见凭据目录；
- 图片经过限额、稳定读取和私有暂存；
- 证据不足时可裁剪或分块重试；
- 后端结果必须通过 Schema、图片索引和模型身份检查；
- 图片里的命令式文字不会直接变成本机操作；
- 缓存命中时仍重新检查文件，但不会再次调用后端。

安装只需要已有 Codex CLI 和 ChatGPT 登录。

Windows：

```powershell
irm https://raw.githubusercontent.com/scy7796/visual-evidence-gateway/main/install.ps1 | iex
```

macOS / Linux：

```bash
curl -fsSL https://raw.githubusercontent.com/scy7796/visual-evidence-gateway/main/install.sh | sh
```

同机六类合成图片测试里，Codex 原生附图和网关都完成了 6/6 个任务。网关的关键字段完整命中是 6/6，原生附图是 4/6；但网关中位耗时更慢，20.2 秒对 16.6 秒。它的主要优势不是更快，而是输出更短、权限更窄、调用链更容易审计。

项目地址：

https://github.com/scy7796/visual-evidence-gateway

当前已知限制：Windows ARM64 暂无预构建；二进制未签名；Luna 权限取决于账号；Codex Desktop 宿主需要在重启后单独确认工具调用。

验证环境：`<填写 Codex Desktop/CLI 版本>`  
宿主调用截图：`<填写图片链接>`

---

## 更短版本

开源了一个给 DeepSeek/OpenCode 接视觉的只读 MCP：Visual Evidence Gateway。

它通过本机 Codex 登录调用 Luna，但只把任务相关的简短证据返回主代理；中间加了路径授权、模型固定、裁剪重试、Schema 校验、图片提示注入检查和失败关闭。

一条命令安装，不需要 Python 环境：

https://github.com/scy7796/visual-evidence-gateway

适合“文本模型长期主控，偶尔需要看本地截图”的工作流。不是官方项目，也不宣称比原生视觉普遍更快或更准。
