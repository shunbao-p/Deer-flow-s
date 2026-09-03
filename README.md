# DeerFlow 自演化改造版

[![Python](https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white)](./backend/pyproject.toml)
[![Node.js](https://img.shields.io/badge/Node.js-22%2B-339933?logo=node.js&logoColor=white)](./Makefile)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)

> 一个围绕 Agent 受控自演化深度改造的 DeerFlow fork，重点覆盖运行时 `skill` 创建、基于 MCP 的运行时 `tool` 接入、生命周期治理与行为级验证。

## 项目概览

这个仓库**不是原版 DeerFlow 的介绍页**。  
它是在字节跳动开源 DeerFlow 基础上做的**深度改造 fork**，核心想解决一个问题：

> 原版 DeerFlow 很擅长编排已有能力，但当 Agent 遇到真实能力缺口时，新的 `skill` 或 `tool` 仍然需要人工补充。

这个 fork 的目标，是让 Agent 逐步具备下面这些能力：

- 判断当前缺的是 `skill gap` 还是 `tool gap`
- 在权限边界内于运行时沉淀新能力
- 通过受控安装 / 注册流程把新能力正式接入系统
- 在后续消息中复用新能力
- 对 custom skill 做生命周期治理，避免能力空间失控膨胀

一句话概括，就是把 DeerFlow 从一个主要**消费既有能力**的系统，升级成一个可以**受控沉淀、接入并治理新能力**的系统。

## 为什么做这个 Fork

这次改造主要围绕两个现实问题展开：

1. **能力缺口仍然需要人工介入**
   当现有 `skill` 或 `tool` 无法完成任务时，系统仍然依赖人工补能力。

2. **运行时新增能力缺少治理**
   即使可以引入新能力，如果没有复用检查、生命周期控制和硬边界约束，custom 能力空间会迅速变得混乱且难以维护。

## 这次改造增加了什么

这个 fork 在 DeerFlow 原有能力基础上，主要补了 4 条核心能力线：

### 1. 运行时 Skill 自演化

Agent 可以判断一个任务是否值得沉淀成可复用 `skill`，然后通过受控路径完成创建、安装和复用，而不是依赖人工手动接入。

核心结果：

- 受控的运行时 `skill` 创建
- 统一的 `.skill` 安装链路
- 安装后可在后续消息中复用

### 2. 运行时 Tool 自演化

Agent 可以区分“缺少流程知识”还是“缺少执行能力”。  
当缺口是真实 `tool gap` 时，系统会走 MCP 正式接入路径，而不是停留在一次性脚本层面。

核心结果：

- `skill gap` 与 `tool gap` 的路由分流
- 运行时 MCP tool 接入
- 正式注册，而不是一次性脚本替代

### 3. Custom Skill 生命周期治理

这次改造并不只停留在“能创建新 skill”，还补上了 custom skill 的治理逻辑，使能力库长期可维护。

核心结果：

- 创建前做重复 / 相似 skill 检查
- 优先复用或原地更新已有 custom skill
- 支持启用 / 停用控制
- 对 disabled custom skill 做文件级访问拦截

### 4. 基于 LangSmith 的行为级验证

这次改造还补了行为级评估和回归流程，用来验证 Agent 的路由、创建、接入和复用逻辑，而不只是停留在单元测试层面。

核心结果：

- LangSmith 回归测试流程
- 场景化测试归档
- 覆盖创建、复用、接入和后续消息使用链路

## 核心能力链路

### Skill 自演化链路

`发现缺口 -> 生命周期检查 -> 创建策略判定 -> 在工作区生成 skill -> 通过受控 bridge 安装 -> 在后续消息中复用`

### Tool 自演化链路

`发现缺口 -> 判断 skill gap / tool gap -> 在工作区生成 MCP tool 项目 -> 通过受控 bridge 安装/注册 -> 验证 -> 在后续消息中复用`

## 关键工程判断

下面这些判断，才是这次 fork 真正的工程核心：

### 1. 必须区分 Skill Gap 和 Tool Gap

并不是每次任务做不出来，都应该创建一个新 `tool`。

- `skill` 解决的是可复用流程知识
- `tool` 解决的是可复用执行能力

如果没有这条边界，Agent 很容易要么滥建工具，要么把临时脚本误当成正式能力。

### 2. 临时脚本不等于正式 Tool

一次性的 bash/python 脚本也许能解决当前轮问题，但这**不等于**系统已经拥有一个可复用正式工具能力。

因此，这个 fork 里的运行时 tool 自演化，走的是正式 MCP 接入路径，而不是“Agent 临时写过一次脚本就算完成”。

### 3. 新能力必须通过受控 Bridge 接入

Agent 不能直接写入全局能力目录。

运行时生成的产物会先落在当前线程工作区，再通过后端受控逻辑完成安装或注册。这样既保留了权限边界，也让整条链路具备可审计、可测试性。

### 4. 治理必须有硬边界，不能只靠 Prompt 约束

停用一个 skill，不能只停留在 Prompt 层面的软提醒。

这个 fork 增加了 disabled custom skill 的文件级访问拦截，避免 Agent 继续把它们当成可用 skill 去读取和执行。

## 改造验证

这次改造不只是代码层面完成实现，也做了行为层面的验证。

验证重点包括：

- 基于 LangSmith 的场景测试与回归流程
- 覆盖 `skill/tool` 创建判定的案例归档
- 已有能力复用验证
- 安装 / 注册链路验证
- 后续消息复用行为验证

当前本地已经沉淀了 `40+` 个归档场景，重点验证的是 Agent 行为，而不只是孤立单元逻辑。

## 技术与方法

- `Python`
- `LangGraph`
- `LangChain`
- `MCP`
- `LangSmith`
- `Agent Middleware`
- `Skill/Tool Gap Routing`

## 重点查看目录

如果你想先看这次改造真正落地的核心位置，建议从下面这些目录开始：

- Runtime skill builder：
  [`skills/public/runtime-skill-builder/SKILL.md`](./skills/public/runtime-skill-builder/SKILL.md)
- Runtime tool builder：
  [`skills/public/runtime-tool-builder/SKILL.md`](./skills/public/runtime-tool-builder/SKILL.md)
- 示例 custom MCP tool：
  [`custom-mcp-servers/network-diagnostics/README.md`](./custom-mcp-servers/network-diagnostics/README.md)
- Skill 安装与治理：
  [`backend/packages/harness/deerflow/skills/`](./backend/packages/harness/deerflow/skills/)
- MCP 接入链路：
  [`backend/packages/harness/deerflow/mcp/`](./backend/packages/harness/deerflow/mcp/)
- 自演化相关 built-in tools：
  [`backend/packages/harness/deerflow/tools/builtins/`](./backend/packages/harness/deerflow/tools/builtins/)

## Quick Start

This fork keeps DeerFlow's basic startup approach. A minimal local flow is:

1. Generate local config:

   ```bash
   make config
   ```

2. Install dependencies:

   ```bash
   make install
   ```

3. Start the project:

   ```bash
   make dev
   ```

4. Open:

   ```text
   http://localhost:2026
   ```

If you prefer Docker:

```bash
make docker-init
make docker-start
```

For detailed runtime configuration, refer to:

- [`backend/docs/CONFIGURATION.md`](./backend/docs/CONFIGURATION.md)
- [`backend/docs/MCP_SERVER.md`](./backend/docs/MCP_SERVER.md)
- [`backend/docs/ARCHITECTURE.md`](./backend/docs/ARCHITECTURE.md)

## Legal RAG 内部增强

本仓库可以把既有法律 RAG 接成 **Deer 的一个内建工具**，不是第二 agent，也不是第二套聊天后端。

```text
用户 ↔ Deer lead_agent ↔ legal_augmentation 工具 ↔ 内部服务 :8003 /v1/augment
```

- 默认关闭：`config.yaml` 里 `legal_rag.enabled: false`
- 打开后，法律问题才允许调用唯一工具 `legal_augmentation`
- 权威字段是 `documents + evidence + refine.claims`；Legal `answer` 只是草稿
- `unsupported` claim 不得进入最终回答
- Neo4j / Milvus 仍由 `services/legal_rag/` 连接**已有库**，Deer 不直连、不复制、不重建
- 服务不可用时，普通对话继续，只说明法律库不可用或证据不足

启用与评测见 [`services/legal_rag/README.md`](./services/legal_rag/README.md)。

## 如何体验这个 Fork 独有的能力

把项目跑起来只是第一步。这个 fork 真正的差异化价值，在于运行时 `skill` 和运行时 `tool` 的受控自演化链路。

### 开始前先确认

请先确认下面这些条件成立：

- [`config.example.yaml`](./config.example.yaml) 或你本地 `config.yaml` 中的 `skills.auto_create_enabled: true`
- 公共 builder skill 仍然可用：
  - [`skills/public/runtime-skill-builder/SKILL.md`](./skills/public/runtime-skill-builder/SKILL.md)
  - [`skills/public/runtime-tool-builder/SKILL.md`](./skills/public/runtime-tool-builder/SKILL.md)
- 当前模型配置可以支撑多步 Agent 执行
- 如果你想看行为链路，先配置好 LangSmith tracing

### 体验运行时 Skill 自演化

你需要给 Agent 一个明确要求“沉淀成可复用能力”的任务，而不是只要求它完成当前轮回答。

示例 prompt：

```text
我后续还会重复使用这套流程。
请不要只回答一次，而是创建并安装一个可复用 skill，
把原始产品需求文本整理成结构化评审卡片，包含固定栏目、检查项和总结。
让它在这个线程后续消息里也可以继续复用。
```

你应该预期看到：

1. Agent 先判断这是不是一个适合沉淀成 `skill` 的任务。
2. 如果允许创建，它会在当前线程工作区生成草稿。
3. 它会通过受控 bridge 打包并安装 `.skill`。
4. 新能力应当在同线程的后续消息中可用。

你可以从这些位置验证：

- 安装后的 custom skills：[`skills/custom/`](./skills/custom/)
- 相关策略与中间件：[`backend/packages/harness/deerflow/skills/`](./backend/packages/harness/deerflow/skills/) 与 [`backend/packages/harness/deerflow/agents/middlewares/`](./backend/packages/harness/deerflow/agents/middlewares/)

### 体验运行时 Tool 自演化

你需要给 Agent 一个明确要求“形成正式可复用执行能力”的任务，而不是让它临时写个一次性脚本。

示例 prompt：

```text
我需要一个后续消息里也能反复调用的正式工具，而不是一次性脚本。
请创建并注册一个 tool，用来检查主机名并返回结构化的基础网络诊断结果。
如果这属于真实 tool gap，请通过 MCP 路径接入。
```

你应该预期看到：

1. Agent 先区分这是 `tool gap` 还是 `skill gap`。
2. 如果是真实 `tool gap`，它会在工作区生成最小 Python `stdio` MCP server 项目。
3. 它会通过受控 MCP bridge 完成安装和注册。
4. 这个能力应当在同线程后续消息中可用。

你可以从这些位置验证：

- 安装后的 MCP 项目：[`custom-mcp-servers/`](./custom-mcp-servers/)
- MCP 注册结果：[`extensions_config.json`](./extensions_config.json)
- MCP 接入逻辑：[`backend/packages/harness/deerflow/mcp/`](./backend/packages/harness/deerflow/mcp/)

### 一个重要验证说明

这个 fork **不会**把运行时接入能力设计成“当前轮热插拔立即可用”。

正确的语义应该是：

- 当前轮：判断、生成、安装 / 注册
- 同线程后续消息：复用新能力

如果你第一次验证这个 fork，请至少在同一个线程里用两条消息来确认效果。

## 当前范围与边界

这个 fork 是一套有明确收敛边界的实现，并不是“任意动态生成任意能力”。

当前比较重要的边界包括：

- 运行时 `tool` 自演化当前主要收敛在最小 Python `stdio` MCP server 路线
- 运行时 `tool` 接入面向的是正式可复用执行能力，不是替代所有临时脚本
- 生命周期治理当前主要聚焦 `custom` skills，而不是整个 public skill 空间
- disabled custom skill 会被文件级拦截，但这不代表模型在完全不读取该 skill 时一定不能产出相似结果
- 新安装的 skill 和新注册的 MCP tool，通常在后续消息中生效，而不是当前响应自动热更新
- 最终路由仍然受当前启用能力、配置状态和模型行为影响

## 行为级验证

这次 fork 的验证不只停留在单元逻辑层面。除了代码级测试，还配套了面向 LangSmith 的场景化评估，用来检查 Agent 是否真的做出了正确的路由和接入决策。

验证重点包括：

- 一个任务是否应该停留在普通工具路径
- 一个任务是否应该沉淀成 `skill` 还是 `tool`
- 运行时安装 / 注册是否沿受控路径成功完成
- 新能力是否能在后续消息中被正确复用

当前本地已经沉淀了 `40+` 个归档场景，重点用于行为级验证。

## 与上游的关系

这个项目基于字节跳动开源 DeerFlow：

- Upstream: <https://github.com/bytedance/deer-flow>

这个仓库是一个**深度改造 fork**，不是官方 upstream 仓库。
这里的重点，是在 DeerFlow 原始 agent harness 之上增加的“自演化 + 治理”能力层。

## License

This repository follows the same license terms as the upstream DeerFlow project unless explicitly stated otherwise.
