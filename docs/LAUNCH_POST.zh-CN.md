# 发布帖草稿

先重启 Codex Desktop，确认它能实际调用一次 `vision.inspect`。把成功截图和宿主版本补到文末后再发。

## 完整版

我平时会让 DeepSeek 或 OpenCode 负责规划和代码，但它们碰到截图就停住了。直接换成多模态主模型可以解决，不过整个任务也跟着换了模型。我更想保留原来的主代理，只在确实需要看图时，单独叫一个视觉模型来读。

所以我做了 Visual Evidence Gateway。它是一个本地 MCP 服务器，只提供一个工具：

```text
vision.inspect(paths, query)
```

主代理把图片路径和具体问题交给网关。网关检查路径、限制图片大小、把图片复制到本次请求的私有目录，然后通过本机 Codex CLI 调用 `gpt-5.6-luna`。返回内容只有短答案、定位证据和不确定性，不包含完整 OCR 或整段视觉分析。

默认链路使用 Codex 的 ChatGPT 登录。项目不保存 API Key，也不会在 Luna 不可用时自动切到按量 API 或其他模型。

我花得最多的时间不在“把图片发给模型”，而是在调用前后加限制：

- 图片只能来自授权目录；
- symlink、junction 和常见凭据目录会被拒绝；
- 后端没有 Shell、浏览器、插件或写权限；
- 结果必须通过 JSON Schema、图片索引和模型身份检查；
- 证据不足时可以裁剪或分块重试；
- 缓存命中仍会检查文件，但不会再次调用后端。

安装需要已有 Codex CLI 和 ChatGPT 登录。网关本身不需要 Python 环境。

Windows：

```powershell
irm https://raw.githubusercontent.com/scy7796/visual-evidence-gateway/main/install.ps1 | iex
```

macOS 或 Linux：

```bash
curl -fsSL https://raw.githubusercontent.com/scy7796/visual-evidence-gateway/main/install.sh | sh
```

我用六类合成图片做了同机测试。Codex 原生附图和网关都完成了 6/6 个任务。预设字段完整命中是 4/6 对 6/6，原生附图更快，中位 16.6 秒，网关是 20.2 秒。网关返回的内容短很多，中位 62 字符，原生附图是 602 字符。

这组测试很小，不能说明网关在所有图片上更准。它目前更明确的价值是：主代理不用换，图片权限更窄，返回格式固定，调用路径也容易检查。

项目地址：

https://github.com/scy7796/visual-evidence-gateway

当前限制也写在仓库里。Windows ARM64 暂无预构建，二进制没有代码签名，Luna 权限取决于账号。Codex Desktop 作为 MCP 宿主还需要在重启后完成一次人工调用验证。

宿主版本：`<填写>`

调用截图：`<填写>`

用过之后觉得有用，可以点个 Star。它能让有相同需求的人更容易搜到这个项目。

## 短版

我开源了一个给 DeepSeek、OpenCode 和 Pi 接视觉的本地 MCP：Visual Evidence Gateway。

主代理继续负责规划和代码，只有问题依赖图片时才调用 Luna。网关限制可读路径，固定 ChatGPT 登录和 `gpt-5.6-luna`，并把结果压成短答案、定位证据和不确定性。Luna 不可用时会直接失败，不会自动切到按量 API。

一条命令安装，网关本身不需要 Python：

https://github.com/scy7796/visual-evidence-gateway

它适合“文本代理长期主控，偶尔需要看本地截图”的工作流。原生附图更快也更简单，网关的取舍是更窄的权限和更固定的结果契约。
