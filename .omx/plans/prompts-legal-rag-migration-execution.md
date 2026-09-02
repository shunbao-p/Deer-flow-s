# Legal RAG 迁入 Deer-flow-s 分阶段执行提示词

方向基线：`/Users/yuh/Desktop/项目/Deer-flow-s/.omx/plans/prd-legal-rag-migration-direction.md`

实施计划：`/Users/yuh/Desktop/项目/Deer-flow-s/.omx/plans/implementation-plan-legal-rag-migration.md`

唯一迁移源仓：`/Users/yuh/Desktop/项目/Legal-consulting-expert`

目标仓库：`/Users/yuh/Desktop/项目/Deer-flow-s`

执行记录：`/Users/yuh/Desktop/项目/Deer-flow-s/.omx/plans/execution-record-legal-rag-migration.md`

总提示词：由生成本文档的会话直接提供，不另建文件。

## 文档权威性与使用方式

本文不是新的需求或架构设计，而是将已批准的方向与实施计划编排为可连续执行、可验证、可中断恢复的工作指令。不要借执行之名重新设计方案，也不要把本文摘要当作替代阅读：执行前须完整读取方向文档、实施计划和本文。

发生冲突时，按以下顺序裁定：

1. 用户在执行会话中的最新明确指令；
2. 方向文档中的目标、边界、非目标和架构停止条件；
3. 实施计划中的文件范围、接口约定、阶段门禁与验收标准；
4. 本分阶段提示词中的执行顺序、记录方法和阶段内指令；
5. 执行记录中已经验证的实施事实与局部裁定；
6. 当前代码和测试所反映的现状。

当前代码是现实依据，但不能静默推翻已批准方向。若只是文件位置、命令入口或局部实现与计划略有出入，应检查代码后采用最小兼容调整，并写入执行记录；若差异会改变产品意图、架构边界或验收标准，则按实质阻塞处理。

稳定阶段 ID 为 `S01` 至 `S08`。每次新会话或上下文恢复后，都以执行记录为进度依据，从首个未完成阶段继续，不得无故重做已完成阶段。若新证据推翻某阶段的完成结论，应记录证据，将该阶段改为需返修，再作最小范围修复。

## 全局执行契约

1. 始终保持 Deer-flow-s 是唯一对话主体和最终回答界面；Legal RAG 只是按需调用的内部法律增强服务。
2. 首版物理衔接固定为 `Deer built-in tool -> internal Legal service -> ask_question_payload`。不得新增第二 agent、第二 chat/session、第二 LangGraph graph 或 graph node，不得把 MCP、trigger middleware 或运行时工具自演化并列引入首版。
3. 迁移以复用为先。Legal 的 Neo4j、Milvus、BM25、GraphRAG、路由、融合、rerank、evidence gate、claim refine 与 fallback 链仍由 Legal runtime 持有；不得为统一风格而重写、裁剪或重新分层。
4. 唯一复制与 baseline 来源是 `/Users/yuh/Desktop/项目/Legal-consulting-expert`。不得从 `/Users/yuh/Desktop/项目/Legal-Expert`、旧结果目录或其他相似副本取代码或替代基线。
5. Deer 不得直接连接 Neo4j/Milvus，不得获得数据库凭证，不得执行 Cypher、Milvus search 或知识库构建。仅 `services/legal_rag/` 持有数据库与 Legal 重依赖。
6. 复用既有法律数据库、schema、index、collection 与向量。所有清单与兼容性检查均先只读；不得删除、重建、清空、迁移或复制既有数据库数据。model/dimension/schema 不兼容时应令 readiness 失败并记录，不能自动修复数据。
7. `documents + evidence + refine.claims` 是 Deer 生成法律内容的权威输入；Legal `answer` 仅是已校核草稿。supported claim 可据证使用，weak claim 须限定表达，unsupported claim 不得进入最终答案。
8. 若真实对话验收发现 Deer 重新引入 unsupported claim，立即判定单阶段生成方案失败，停止继续粉饰 prompt，保存证据，并依方向文档切换到 `Deer draft -> Legal verify/refine -> Deer final wording` 两阶段方案；此为架构停止/回审点。
9. 首版仅使用现有工具选择与简洁 prompt 规则触发法律增强。只有 `S07` 的固定评测证明存在系统性漏触发，方可基于可复现样本另行提出最小 guard；不得预先加入 middleware。
10. `legal_rag.enabled=false` 必须保持现有 Deer 行为不变。Legal timeout、failed 或 unavailable 不得阻断普通对话，Deer 只能明确说明法律知识库不可用或证据不足，不得伪装为数据库支持的法律结论。
11. Legal 服务可有独立 healthcheck，但 Gateway/LangGraph 不得以其 `service_healthy` 为启动前置。保持降级可用，而非把 Deer 生命周期绑死在 Legal readiness 上。
12. 保持改动小、可审、可回退。优先复用现有函数、配置加载、错误处理中间件和测试模式；不新增无关抽象、通用 SDK、缓存、事件总线、插件框架、前端或基础设施，也不添加计划未要求的依赖。
13. 保护用户已有工作与脏工作树。修改前查看状态与相关 diff；不要覆盖、撤销、格式化或提交无关改动。仅在用户明确要求时创建提交。
14. 不把密钥、密码、令牌、完整用户问题、完整证据文本或服务堆栈写入日志、测试夹具和执行记录。真实凭证只通过既有环境配置使用。
15. 每阶段实行“检查现状 -> 最小实现 -> 自审 diff -> 定向验证 -> 修复 -> 回归验证 -> 更新记录”。验证失败时先在本阶段诊断和修复；不得为了赶进度放宽断言、跳过必要门禁或把失败写成通过。
16. 外部数据库、模型或凭证不可用时，先完成不依赖它们且不会破坏阶段依赖的静态/模拟验证；若本阶段的核心完成条件仍无法证明，记录为 `blocked`，写明已完成部分、缺失条件、复现方法和恢复入口后暂停，不得虚构 live 结果。
17. 阶段通过后自动进入下一阶段，不因普通阶段切换、可恢复测试失败、低风险局部判断或上下文压缩向用户询问是否继续。只在本文列明的架构停止条件、真正无法安全解决的阻塞、必须由用户完成的凭证/登录/外部动作，或全部完成时停止。

## 背景加载与执行前预检

进入任何实施阶段前，依次完成下列动作；预检不是独立阶段，也不是默认停点：

1. 完整读取方向文档、实施计划和本文，不只读取标题、摘要或局部章节。
2. 查看目标仓库的 `AGENTS.md`、相关目录级指令、当前 `git status` 与已有 diff，识别用户既有改动。
3. 检查唯一源仓、两个固定评测集、目标仓相关接点及测试是否仍存在；不得用 `/Users/yuh/Desktop/项目/Legal-Expert` 补缺。
4. 若执行记录已存在，完整读取并核验阶段状态；若不存在，则创建执行记录，至少包含任务元信息、当前总体状态、`S01-S08` 状态表、阶段详情和最终验收区。
5. 执行记录中每个阶段使用 `pending | in_progress | blocked | completed | needs_rework` 之一，并至少维护：`阶段状态`、`执行目标`、`实际完成`、`关键改动与文件`、`验证命令及结果`、`问题、处理与重要决策`、`剩余风险或延期项`、`下一状态`。
6. 将首个非 `completed` 阶段设为当前阶段；若前置阶段为 `blocked` 或 `needs_rework`，先处理前置阶段，不越级宣告下游完成。
7. 对照当前代码检查计划中的路径、接口和命令。安全的局部差异可据实修正并记录；涉及架构边界、数据破坏或能力阉割的差异须停止。
8. 建立或更新基于 `S01-S08` 的任务清单，然后自动开始首个未完成阶段。

## 需求覆盖与阶段总览

| ID | 阶段 | 主要交付物 | 核心验证证据 | 下一状态 |
| --- | --- | --- | --- | --- |
| S01 | 冻结 Legal baseline 与数据库清单 | 本轮 top10/full50 基线、路由覆盖、Neo4j/Milvus 只读清单 | 请求结果、失败/fallback 记录、schema/collection/model/dimension 清单 | S02 |
| S02 | 迁入 Legal 核心 runtime | `services/legal_rag/` 核心、独立依赖、必要 ingest/eval/data | 既有库连通、top10 语义对等、cleanup 释放 | S03 |
| S03 | 建立无会话 `/v1/augment` | v1 schema、service/app、health/readiness、API 测试 | mocked contract 行为与真实 top10 新旧入口语义一致 | S04 |
| S04 | 增加 Deer 配置、契约与客户端 | `LegalRAGConfig`、v1 contracts、薄 HTTP client、配置示例 | 配置/客户端异常矩阵、boundary 测试 | S05 |
| S05 | 接入内建工具与 prompt 触发 | 唯一 `legal_augmentation` 工具、条件注册、证据消费规则 | enabled/disabled、受控失败、verdict 保留、prompt 测试 | S06 |
| S06 | 部署及既有 Neo4j/Milvus 连通 | Legal image/env/compose/healthcheck 与内部 URL | compose config、独立降级、原库命中且未复制重建 | S07 |
| S07 | 迁移评测并端到端验收 | `/v1/augment` 评测入口、六类 Deer 场景、baseline 对比 | 路由/命中/evidence/refine 对等及 unsupported stop gate | S08 或架构回审 |
| S08 | 文档同步与最终收口 | 项目与 Legal 服务文档、最终全量验证、执行记录结论 | 文档命令一致、完整测试/已说明的 live 缺口、验收清单 | complete |

## S01：冻结 Legal baseline 与数据库清单

### 目标与非目标

目标是以当前独立 Legal 服务生成可复核的迁移前事实，并只读记录既有法律数据库兼容信息。不要复制代码、改路由算法、调整评测问题、重建数据库或把历史 summary 当作本轮结果。

依赖：背景预检完成，唯一源仓及固定评测输入存在；运行 live baseline 所需服务与凭证可用。

入口条件：`S01` 为首个未完成阶段。

### 开始前读取

- 实施计划“阶段 0”“验证命令顺序”“风险、处理与回退点”。
- 源仓评测脚本、配置、数据库初始化代码及运行说明。
- 固定输入：
  - `/Users/yuh/Desktop/项目/Legal-consulting-expert/data/eval/eval_questions_v1_top10.jsonl`
  - `/Users/yuh/Desktop/项目/Legal-consulting-expert/data/eval/eval_questions_v1_full50.jsonl`

### 实施要求

1. 先从源仓现有文档和脚本发现正确的启动、评测与结果保存方式，不臆造命令。
2. 以当前独立服务重新运行 top10 和 full50，保存本轮原始结果、环境事实、失败项和 route fallback；旧 `metrics_summary_v1_*.json` 只能作参考。
3. 比较语义字段而非生成文字，至少记录 strategy/route、法规或条文命中、documents、rerank/fallback、evidence mode 与 refine verdict。
4. 确认现有数据集可触发的 `hybrid_traditional`、`graph_rag`、`combined` 路径。缺失路径只补专门 fixture，不修改路由算法，不污染固定输入。
5. 只读记录 Neo4j database、labels、relationship types、full-text index，以及 Milvus collection、字段、row count、embedding model、dimension。明确记录现有默认/实际 collection 与 index 名是否一致。

### 验证与验收

- top10 与 full50 均完成；任何失败及 fallback 均有逐项记录。
- 对实际可触发的路由、evidence 与 refine 语义形成后续可比较基线。
- 数据库清单完整，且有证据表明未执行删除、重建或写入式迁移。
- 若凭证或外部服务缺失导致无法形成真实 baseline，不得进入 S02；按全局契约记录真实 blocker。

### 执行记录更新

记录结果文件位置、运行方式、运行环境、数据集摘要、路由覆盖、失败/fallback、数据库清单、敏感信息脱敏说明与 S02 readiness。不得把凭证写入记录。

### 完成条件与下一状态

只有本轮 baseline 和数据库清单均可复核时标记 `S01 completed`，随后自动进入 `S02`。

## S02：原样迁入 Legal 核心 runtime

### 目标与非目标

目标是把 Legal 核心以最小路径/打包适配迁入 `services/legal_rag/`，并证明其仍连接原 Neo4j/Milvus、保持基线语义。不要重命名核心类、整理算法、改变权重/模型，也不要迁入 frontend、session upload、独立 chat/file API 或演示会话状态。

依赖：`S01 completed`。

入口条件：baseline 与数据库清单可用于对照。

### 开始前读取

- 实施计划“目标文件布局”“阶段 1”“明确不修改”。
- 源仓 `main.py`、`config.py`、`rag_modules/`、`requirements.txt`、必要的 `scripts/ingest/`、`scripts/eval/` 与 `data/eval/`。
- 目标仓 `services/` 的现状、忽略规则和容器构建约定。

### 实施要求

1. 从唯一源仓迁入计划明确列出的核心文件，第一轮只做目标仓运行所需的 import、路径、打包与资源定位修正。
2. 保持 `AdvancedGraphRAGSystem.initialize_system()`、`build_knowledge_base()`、`ask_question_payload()` 与 `_cleanup()` 行为。
3. 保持 Legal 的独立 requirements/runtime；不得把 Legal 重依赖加入 Deer harness、`backend/uv.lock` 或 harness dependency set。
4. 保留必要 ingestion 和 evaluation 工具，但不把用户对话变成 ingestion 路径。
5. 源仓在迁移验收前只作只读 baseline，不进行双边同步修改。

### 验证与验收

- 在迁入 runtime 的独立环境中直接构造系统，可连接既有 Neo4j/Milvus 并加载既有 collection/index。
- 对 top10 比较 route、法规/条文命中、evidence 与 refine verdict，相对 S01 不得出现迁移性变化；生成措辞可波动。
- 验证 `_cleanup()` 释放 Neo4j/Milvus driver。
- 自审依赖边界，确认 Deer harness 未引入 Legal 重依赖。

### 执行记录更新

记录实际迁入/排除的文件、为运行所作的最小适配、依赖边界、baseline 对比及 cleanup 证据。任何原代码自身问题须单独标明，不能与接口迁移混改。

### 完成条件与下一状态

迁入 runtime 可独立运行且语义对等时标记 `S02 completed`，随后自动进入 `S03`。

## S03：建立无会话 Legal augmentation API

### 目标与非目标

目标是复用既有 lifecycle，新增版本化、无会话的 `/v1/augment` 边界。不要把 Legal chat/session/frontend 带入 Deer，也不要在 adapter 内重新实现检索、rerank、evidence 或 refine。

依赖：`S02 completed`。

入口条件：迁入 runtime 已通过基线对比。

### 开始前读取

- 实施计划“LegalAugmentation v1 契约”“阶段 2”。
- 迁入前后的 `api/service.py`、`api/schemas.py` 与 `ask_question_payload` 实际返回结构。

### 实施要求

1. 复用原 `RAGDemoService` 的锁、singleton、startup、health、reranker prewarm 与 shutdown。
2. 实现 `POST /v1/augment`，请求仅含 v1 约定字段，不依赖 `/chats`、`chat_id` 或 Deer thread/state。
3. 直接委托 `ask_question_payload(question, explain_routing, eval_fast_mode)`，仅做 schema 校验与版本包装，不重新计算结果字段。
4. 成功响应完整保留 `analysis`、`documents`、`evidence`、`refine`、`answer`、route/fallback/metrics/timing 等计划约定语义。
5. `/health` 在 ready 时返回 200，在 starting/failed 时返回 503；初始化失败后进程仍能提供 failed health，未 ready 的 augmentation 返回明确 503。
6. 最终集成服务只需公开内部 `/health` 与 `/v1/augment`。

### 验证与验收

- mocked system 验证字段传递与响应无丢失。
- 覆盖空问题、未知 contract version、未 ready、内部异常的确定性 4xx/503/5xx 行为。
- 真实 top10 下，新 `/v1/augment` 与旧 `/chat` baseline 的 route、documents、evidence、refine 语义一致。
- 运行 Legal 纯单元测试与 API contract 测试；从现有项目配置发现准确命令并记录。

### 执行记录更新

记录 v1 实际 schema、状态码矩阵、lifecycle 复用点、测试命令/结果、真实入口对比与已知兼容限制。

### 完成条件与下一状态

无会话 API 契约及生命周期均通过模拟与真实语义验证时标记 `S03 completed`，随后自动进入 `S04`。

## S04：增加 Deer 侧配置、契约与薄客户端

### 目标与非目标

目标是在 Deer harness 内建立最薄的 v1 transport boundary。不要创建通用 service SDK、数据库 adapter 或重试框架，不要让 Gateway/app 反向渗入 harness。

依赖：`S03 completed`。

入口条件：服务端 v1 schema 已冻结且可测试。

### 开始前读取

- 实施计划“Deer 工具输出”“配置约定”“阶段 3”。
- 当前 `AppConfig`、配置导出、harness boundary、HTTP client/error handling 与相关测试模式。

### 实施要求

1. 新增明确的 `LegalRAGConfig`，使 `AppConfig` 显式持有 `legal_rag`；默认 disabled，base URL 与 timeout 遵守计划约定。
2. 支持 `LEGAL_RAG_BASE_URL` 环境变量优先、YAML 次之；disabled/本机开发不强制存在该变量。
3. 在 `deerflow/legal/` 实现 v1 request/result models 和仅含必要 `augment()`/`health()` 的 `httpx.AsyncClient` 客户端。总 timeout 默认 120 秒，connect timeout 5 秒；首版不做自动重试。
4. 验证成功响应的 contract version 和权威字段；将 timeout、unavailable、invalid response 等预期失败映射为后续工具可消费的受控类别。
5. 日志只保留 endpoint、耗时、strategy、evidence mode、document count 与错误类别，不记录完整问题、证据、凭证或响应全文。
6. 更新 `config.example.yaml`、`.env.example`、`config_version: 2` 及对应版本测试；沿用现有递归 merge，不另造文本迁移器。

### 验证与验收

依实施计划执行并记录：

```bash
cd backend && uv run pytest tests/test_legal_rag_config.py tests/test_legal_rag_contracts.py tests/test_legal_rag_client.py
cd backend && uv run pytest tests/test_harness_boundary.py tests/test_config_version.py
```

测试须覆盖默认 disabled、合法配置、无效 URL/timeout、成功、timeout、连接失败、非 2xx、非法 JSON、版本不匹配和权威字段缺失。若实际测试文件命名在实施中按计划形成，使用真实文件名并在记录中说明，不得虚构通过。

### 执行记录更新

记录配置优先级、contract 冻结事实、错误分类、日志脱敏检查、文件 diff 与测试结果。

### 完成条件与下一状态

服务端 v1 可被 Deer models/client 严格消费且 harness boundary 无回归时标记 `S04 completed`，随后自动进入 `S05`。

## S05：接入唯一 Deer 内建工具与触发规则

### 目标与非目标

目标是让现有 lead agent 通过既有工具装配点获得一个法律增强能力。不要改 `ThreadState`、主 graph、agent 数量或工具自演化机制，不要增加 middleware，也不要让模型选择 Legal 内部检索策略。

依赖：`S04 completed`。

入口条件：客户端契约及错误分类已经验证。

### 开始前读取

- 实施计划“阶段 4”与当前 `tools.py`、builtins export、lead-agent prompt、`ToolErrorHandlingMiddleware` 及相应测试。

### 实施要求

1. 新增唯一 `legal_augmentation` built-in tool，参数仅为自包含 `question` 和可选 `explain_routing`。
2. 仅在 `config.legal_rag.enabled` 时通过现有 `get_available_tools()` 装配；disabled 时工具 schema 与法律 prompt 均不得进入模型上下文。
3. 工具说明与单一 `<legal_augmentation>` prompt 段只负责外层“是否需要法律依据”判断，并明确非法律任务不调用。
4. 保留并传递 documents/evidence/refine.claim verdict；prompt 明确规定 supported/weak/unsupported 与 evidence mode 的消费规则。
5. 预期失败返回小型结构化对象，至少区分 `disabled`、`timeout`、`unavailable`、`invalid_response`，且不泄露内部响应和堆栈；未知异常继续交既有 middleware。
6. 不添加额外“消费层”。阶段内只证明结构和规则存在；最终答案是否遵守 verdict 由 S07 live/integration gate 裁定。

### 验证与验收

依实施计划执行并记录：

```bash
cd backend && uv run pytest tests/test_legal_augmentation_tool.py tests/test_legal_augmentation_prompt.py
cd backend && uv run pytest tests/test_harness_boundary.py tests/test_lead_agent_prompt_skills.py tests/test_config_version.py
cd backend && uv run ruff check packages/harness/deerflow tests
```

须证明 enabled/disabled 工具集合差异、成功结构完整、预期失败受控、未知异常沿用 middleware、prompt 条件注入，以及固定 unsupported claim 仍保留 verdict 且被规则禁止使用。

### 执行记录更新

记录工具注册接点、prompt 边界、失败对象、未引入 graph/middleware 的确认、测试与 lint 结果。

### 完成条件与下一状态

唯一工具在 enabled 条件下可用、disabled 无侵入且证据语义未被压扁时标记 `S05 completed`，随后自动进入 `S06`。

## S06：部署并连通既有 Neo4j/Milvus

### 目标与非目标

目标是把 Legal runtime 作为 Deer compose 内部服务运行并复用原法律数据库。不要经 Nginx 暴露用户 API，不要创建第二套数据库，不要把 Legal readiness 变成 Deer 启动前置。

依赖：`S05 completed`。

入口条件：tool-to-service 契约已经由本地测试验证。

### 开始前读取

- 实施计划“Legal 服务侧配置”“阶段 5”。
- 当前 Deer compose/dev compose、host-gateway 约定、源仓 compose 与 `.env.example`。

### 实施要求

1. 为 `services/legal_rag/` 提供独立 Dockerfile、requirements 与 `.env.example`，保留 Neo4j、Milvus、embedding/reranker、LLM、retrieval 及可选 LangSmith 配置。
2. 在 production/dev compose 中增加内部 `legal-rag`（计划建议端口 8003），LangGraph 容器使用 `LEGAL_RAG_BASE_URL=http://legal-rag:8003`，本机默认仍为 `http://127.0.0.1:8003`。
3. 容器数据库地址使用可达 service name、`host.docker.internal` 或真实外部地址；不得使用指向容器自身的 localhost。Linux 保留现有 host-gateway 模式。
4. 仅 legal-rag 获得数据库凭证。Gateway/LangGraph 不得获得 Neo4j/Milvus 环境变量。
5. legal-rag 自有 healthcheck；Gateway/LangGraph 不使用 `service_healthy` 依赖它。错误数据库地址时，Deer 其他组件仍应启动并通过客户端受控降级。
6. 加载原 collection/index/schema；不得复制、重建或静默修复不兼容数据。

### 验证与验收

依实施计划执行并记录实际 compose 文件：

```bash
docker compose -f docker/docker-compose-dev.yaml config
docker compose -f docker/docker-compose.yaml config
```

另外验证 health 的 ready/failed、错误数据库地址下 Deer 主体独立可用、真实查询命中原 `legal_knowledge` collection 与原 Neo4j database，以及 row count/graph data 未复制或重建。

### 执行记录更新

记录 compose 解析、实际内部地址、凭证隔离检查、health/degradation 结果、原库标识与只读一致性证据。敏感值必须脱敏。

### 完成条件与下一状态

集成部署可解析、Legal 可独立 ready/failed、Deer 可降级且原数据库未复制重建时标记 `S06 completed`，随后自动进入 `S07`。

## S07：迁移评测并完成端到端验收

### 目标与非目标

目标是证明迁移后的 Legal 链与 Deer 对话衔接均满足计划，而非只证明接口返回 200。不要用历史 summary 代替本轮结果，不要精确比较生成措辞，不要在没有系统性漏触发证据时添加 guard。

依赖：`S06 completed`。

入口条件：集成环境可连接既有法律数据库，S01 baseline 可供对比。

### 开始前读取

- 实施计划“阶段 6”“验证命令顺序”“可验收标准”“实施停止条件”。
- S01 baseline、S03/S05/S06 的真实契约和执行记录。
- 迁入的 `scripts/eval/run_eval.py` 及当前 Deer 对话/集成测试入口。

### 实施要求

1. 将评测请求从“创建 `/chats` 后调用 `/chat`”改为直接调用 `/v1/augment`；尽量不动命中、route、evidence、graph fallback 与 latency 计算。
2. 重新运行 top10，再运行 full50，与 S01 的本轮 baseline 比较。逐题审查差异，不能只看总分。
3. Deer 至少覆盖六类对话：非法律不调用、简单法律调用、关系型法律调用、Legal timeout/failed、insufficient evidence、unsupported claim。
4. 集成测试若依赖真实外部服务，应默认跳过并以明确环境开关启用；本轮 live 验收仍须实际运行并记录，除非真实 blocker 被如实声明。
5. 若固定 trigger suite 证明普通 tool selection 存在系统性漏触发，先保存复现样本和统计证据，再依方向文档提出/实现最小 guard；不得把偶发模型波动直接上升为 middleware 需求。
6. 检查最终回答是否重新引入 unsupported claim。若出现，立即执行全局契约第 8 条，不得继续以微调措辞掩盖。

### 验证与验收

- S01 可触发的 `hybrid_traditional`、`graph_rag`、`combined` 路径迁移后仍可判读；rerank fallback、evidence mode、refine verdict 语义保留。
- 新服务无接口迁移导致的新增 request failure，法规/条文命中不因迁移下降；模型波动按单题 documents/route 复核。
- 六类 Deer 场景均有证据；Legal 不可用时有明确限制说明且普通对话不被阻断。
- Deer 最终答案不包含 unsupported claim。此项为硬门禁。
- 从实施计划“验证命令顺序”第 1 至第 7 项按依赖执行所有适用验证，并记录完整命令、结果与环境限制。

### 执行记录更新

记录新评测结果路径、与 S01 的逐项差异、六类场景证据、trigger 统计、unsupported hard gate 结论、任何 guard 决策及进入 S08 的 readiness。

### 完成条件与下一状态

所有 parity 与对话级硬门禁通过时标记 `S07 completed`，随后自动进入 `S08`。若 unsupported claim 回流或需越过其他架构停止条件，则将 S07 标为 `blocked`，保存证据并回到方向评审。

## S08：文档同步、全量验证与最终收口

### 目标与非目标

目标是让代码、配置、部署、测试、运行说明与执行记录一致，并形成可审计的最终结论。不要借收尾扩展功能或美化性重构。

依赖：`S07 completed`。

入口条件：核心迁移与端到端硬门禁均已通过。

### 开始前读取

- 实施计划“阶段 7”“修改清单总览”“验证命令顺序”“可验收标准”。
- 当前 README、架构文档、`backend/CLAUDE.md`、实际配置/compose/命令与全部执行记录。

### 实施要求

1. 同步 `README.md`、`README_zh.md`、`PROJECT_ARCHITECTURE.md`、`backend/CLAUDE.md` 与 `services/legal_rag/README.md`。
2. 说明启用方式、服务地址、数据库复用、health/readiness、受控降级、评测命令与凭证边界；架构图不得把 Legal 描述为第二 agent/chat backend。
3. 标明验收后 `services/legal_rag/` 是维护源，原 Legal 独立仓只保留历史 baseline 角色；不删除原仓。
4. 校验文档中的路径、端口、配置名和命令均与实际代码一致。
5. 运行实施计划要求的完整 backend test suite，并重跑受本阶段文档/配置改动影响的 lint、compose config 和关键 smoke checks。
6. 对照实施计划 10 条可验收标准及方向文档非目标逐条收口，检查无第二会话、graph node、middleware、MCP、前端、直接 DB client 或不必要基础设施。

### 验证与验收

- 文档命令可在当前仓库路径执行，代码/端口/配置一致。
- 所有定向测试、boundary、prompt、config、ruff、compose config 与完整 backend suite 有新鲜结果。
- live top10/full50 与六类对话结果已在 S07 留证；若某项因外部环境未执行，不能宣告总体完整完成，应在执行记录明确标为剩余阻塞或条件性就绪。
- 审阅最终 diff，确认无无关修改、敏感信息、调试残留或计划外依赖。

### 执行记录更新

将 S08 与总体状态更新为 `completed` 或如实保持 `blocked`。汇总实际改动文件、验证证据、架构边界检查、关键决策、未解决风险、live 验证状态及是否达到可验收标准。

### 完成条件与下一状态

只有计划要求的代码、测试、compose、live 验收和文档均通过，且不存在未说明的硬门禁缺口时，方可标记总体 `complete`。随后停止执行并提交证据化最终报告；不得自动删除源仓、数据库或 baseline 产物。

## 人工门

本任务不预设人工门，`S01-S08` 应连续自动执行。阶段边界、测试失败、lint 错误、低风险实现判断和普通外部服务重启均不是人工门。

只有以下情形确需暂停：

- 缺少必须由用户提供或完成的凭证、登录、MFA、设备批准或外部环境动作，且它阻断当前阶段核心门禁；
- 需要破坏性数据库动作、不可逆操作、生产发布或方向文档之外的重大范围变更；
- 命中方向/实施计划的架构停止条件，且无法在既有边界内安全修复。

暂停前必须更新执行记录：标记受阻阶段、列出已完成工作与已通过验证、精确描述所需用户动作或决策、给出脱敏复现证据，并写明恢复后应从哪个阶段哪一步继续。用户完成动作后，执行会话须先验证条件已满足，再从记录指定位置续跑。

## 最终验收与收尾

全部阶段结束时，执行会话必须：

1. 重读方向文档的非目标/停止条件、实施计划的修改清单/可验收标准，以及完整执行记录。
2. 对照 `S01-S08` 确认无遗漏、无无故跳过、无已完成阶段被后续改动破坏。
3. 确认最终执行记录是事实状态，而非计划复述；每个完成阶段都有改动与验证证据。
4. 给出一次最终报告，至少包括：总体结论、实际改动范围、关键文件、验证命令及结果、baseline/端到端证据、重要实施决策、剩余风险或未执行项、执行记录状态。
5. 若尚有硬门禁或 live 验证缺失，应明确写为未完成/阻塞，不得用“代码已写完”替代总体完成。

