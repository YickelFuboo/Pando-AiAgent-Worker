# 工具输出截断与 tool-output 落盘机制分析

## 一、参考项目 OpenCode 的完整机制

### 1. 不把超长输出直接塞进模型上下文

**核心：** 对超长工具输出统一走 `Truncate.output(...)`，只把「截断后的摘要」作为 `content` 返回给模型，并在结果中加上 `truncated: true` 标记。

#### 实现位置与关键逻辑

| 项目 | 文件 | 函数/位置 | 关键逻辑 |
|------|------|-----------|----------|
| 截断入口常量与类型 | `参考项目/opencode/packages/opencode/src/tool/truncation.ts` | `Truncate` namespace | `MAX_LINES = 2000`、`MAX_BYTES = 50*1024`；`Result` 类型：`{ content, truncated: false }` 或 `{ content, truncated: true, outputPath }` |
| 截断核心实现 | 同上 | `Truncate.output(text, options?, agent?)` | 若 `lines.length <= maxLines && totalBytes <= maxBytes` 直接返回 `{ content: text, truncated: false }`；否则按行/字节截取 `preview`，写完整内容到 `DIR` 下文件，返回 `{ content: message, truncated: true, outputPath: filepath }`，其中 `message` 含预览 + `...N lines/bytes truncated...` + 提示（用 Grep/Read 或 Task 处理完整文件，不要自己读全文件） |
| 工具层统一截断 | `参考项目/opencode/packages/opencode/src/tool/tool.ts` | `Tool.define` 内对 `toolInfo.execute` 的包装 | 执行 `execute(args, ctx)` 得到 `result`；若 `result.metadata.truncated !== undefined` 则跳过截断（工具自管）；否则 `truncated = await Truncate.output(result.output, {}, initCtx?.agent)`，返回 `output: truncated.content`、`metadata: { truncated, outputPath? }` |
| 插件工具截断 | `参考项目/opencode/packages/opencode/src/tool/registry.ts` | `fromPlugin` 内 `execute` | `result = await def.execute(...)`（字符串）；`out = await Truncate.output(result, {}, initCtx?.agent)`；返回 `output: out.truncated ? out.content : result`，`metadata: { truncated, outputPath }` |
| 会话/资源内容截断 | `参考项目/opencode/packages/opencode/src/session/prompt.ts` | 构建 resource 等内容的逻辑（约 897–908 行） | 将多段文本 `textParts.join("\n\n")` 交给 `Truncate.output(..., {}, input.agent)`；返回给模型的 `output` 用 `truncated.content`，`metadata` 带 `truncated` 和 `outputPath` |

**要点：** 模型端看到的工具结果「内容」始终是 `truncated.content`（截断后的摘要 + 提示），不会收到完整原始长文本。

---

### 2. 完整输出落盘到 tool-output 目录

**核心：** 完整内容写入 `Global.Path.data/tool-output/` 下的文件，返回给调用方的结构里带 `outputPath`，模型不会根据该路径自动再读文件。

#### 实现位置与关键逻辑

| 项目 | 文件 | 函数/位置 | 关键逻辑 |
|------|------|-----------|----------|
| 目录与路径定义 | `参考项目/opencode/packages/opencode/src/tool/truncation.ts` | `Truncate.DIR`、`Truncate.GLOB` | `DIR = path.join(Global.Path.data, "tool-output")`；`GLOB = path.join(DIR, "*")` 用于权限/白名单 |
| 数据目录定义 | `参考项目/opencode/packages/opencode/src/global/index.ts` | `Global.Path.data` | `data = path.join(xdgData!, app)`（app 为 `"opencode"`），即 XDG data 目录下的 opencode |
| 落盘写入 | `参考项目/opencode/packages/opencode/src/tool/truncation.ts` | `Truncate.output` 内（约 91–94 行） | 生成 `id = Identifier.ascending("tool")`；`filepath = path.join(DIR, id)`；`await Filesystem.write(filepath, text)` 写入**完整** `text`；返回 `outputPath: filepath` |
| 定时清理 | 同上 | `Truncate.init`、`Truncate.cleanup` | `init` 向 Scheduler 注册每小时执行的 `cleanup`；`cleanup` 扫描 `DIR` 下 `tool_*` 文件，删除早于 `RETENTION_MS`（7 天）的旧文件 |

**要点：** 只有「需要截断」时才会写文件；文件名用升序 ID（如 `tool_xxx`），便于按时间清理；模型侧只消费 `content` 和 metadata 里的 `truncated`/`outputPath`，没有逻辑会去读 `outputPath` 所指文件参与推理。

---

### 3. 给「人/上层 UI」用：truncated + outputPath

**核心：** UI 或客户端看到 `truncated: true` 时，可读 `outputPath` 提供「查看完整输出」；用户也可本地打开 `Global.Path.data/tool-output` 下文件查看。

#### 实现位置与约定

| 项目 | 说明 |
|------|------|
| 数据结构约定 | 工具/插件返回的 `metadata` 含 `truncated: boolean`、可选 `outputPath: string`；发送给模型的内容仍是 `output`（截断后的 `content`） |
| 消息/Part 存储 | 在 OpenCode 的 message-v2 中，tool part 的 `state` 存 `output`、`metadata` 等；UI 从 part 的 metadata 取 `outputPath` 展示「完整输出」入口 |
| 权限与白名单 | `参考项目/opencode/packages/opencode/src/agent/agent.ts` 等处：`Truncate.GLOB` 被加入 external_directory 白名单，允许 explore 等对 `tool-output/*` 的访问（如 Task 工具让 explore 用 Grep/Read 处理该文件），但默认主代理不会自动去读该路径 |

**要点：** 「模型不再自动读 outputPath」是产品/设计约定：提示文案里建议用 Grep/Read(offset,limit) 或 Task 委托处理完整文件，而不是让模型自己读整份文件，避免再次撑爆上下文。

---

## 二、本项目中与「截断 / tool-output」相关的现状

### 1. 已有逻辑（无落盘、无 outputPath）

| 文件 | 逻辑 | 说明 |
|------|------|------|
| `app/agents/tools/local/web.py` | 按 `max_chars` 截断网页正文；在返回的 JSON 里设 `"truncated": true`、`"text": text`（截断后） | 仅内存截断，未写文件，无 `outputPath`；模型收到的是整段 JSON 字符串 |
| `app/agents/tools/local/shell.py` | `result = result[:max_len] + "\n... (truncated, N more chars)"`，`max_len=10000` | 仅内存截断，未写文件，无 `outputPath` |
| `app/infrastructure/llms/utils.py` | `truncate(string, max_len)` | 通用字符串截断，用于 embedding 等，与工具结果无关 |
| `app/infrastructure/llms/chat_models/base/base.py` 等 | `_add_truncate_notify(content)` | 对**模型回复**被截断时追加说明，与**工具输出**截断无关 |

### 2. 工具结果如何进入上下文

| 文件 | 逻辑 | 说明 |
|------|------|------|
| `app/agents/core/react.py` | `tool_result = await self.available_tools.execute(...)`；`return f"{tool_result.result}"` | 工具返回的 `result`（字符串）直接作为该次调用的返回值 |
| `app/agents/core/react.py`（或调用处） | `Message.tool_result_message(result, toolcall.function.name, toolcall.id)` | 该 `result` 字符串成为 `content` 写入一条 role=tool 的消息 |
| `app/agents/sessions/message.py` | `tool_result_message(cls, content, name, tool_call_id)`；`to_context()` 仅带 `role`、`content`、`name`、`tool_call_id` | 发给 LLM 的上下文中，工具结果只有 `content`，**没有单独的 metadata 或 outputPath 字段** |

**结论：** 本项目当前没有「把完整工具输出写入 tool-output 目录 + 返回 outputPath」的机制；截断仅在少数工具内做内存截断，且截断后的内容全部进入模型上下文，没有「截断摘要 + 元数据(outputPath)」的分离设计。

---

## 三、对照小结

| 能力 | OpenCode | 本项目 |
|------|----------|--------|
| 超长工具输出不整段进上下文 | ✅ 通过 `Truncate.output` 统一截断，只把 `content` 摘要给模型 | ⚠️ 仅 web/shell 等个别工具做简单截断，且截断后整段仍进上下文；无统一截断层 |
| 完整输出落盘 | ✅ 写入 `Global.Path.data/tool-output/<id>`，返回 `outputPath` | ❌ 无 |
| UI/人可查完整输出 | ✅ metadata 含 `truncated`、`outputPath`，UI 可读文件 | ❌ 无 outputPath，无统一 metadata 传递 |
| 模型不自动读 outputPath | ✅ 约定 + 提示：用 Grep/Read/Task 处理，不自动读文件 | N/A（无 outputPath） |

若要在本项目中实现与 OpenCode 同类的「工具输出截断 + tool-output 落盘」机制，需要新增：统一截断层（含写 `tool-output`、返回 `outputPath`）、在工具结果消息或上下文中携带 `truncated`/`outputPath` 供 UI 使用，并约定模型不根据 `outputPath` 自动读文件。
