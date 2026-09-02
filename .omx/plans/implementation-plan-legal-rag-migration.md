# Legal RAG 迁入 Deer-flow-s 实施计划

## 文档职责

本文是实施直接依据，基于已确认的方向文档 `.omx/plans/prd-legal-rag-migration-direction.md`，负责回答：改哪些文件、按什么顺序修改、每一步如何验证、何时停止或回退。

本文不重新讨论总体架构选型。若实施中发现必须改变“Deer 为对话主体、Legal 为内部增强服务、单一内建工具接入、Legal 保留数据库与检索链所有权”等已锁定原则，应停止当前步骤并回到方向文档重新评审，而不是在实施中悄然改变架构。

本次迁移唯一源仓（source of truth）固定为 `/Users/yuh/Desktop/项目/Legal-consulting-expert`。机器上的 `/Users/yuh/Desktop/项目/Legal-Expert` 不作为复制、基线或代码对照来源；即便两者当前文件相似，实施中也不得混用。

## 目标结果

完成后，Deer-flow-s 的现有 `lead_agent` 在需要法律依据时调用一个内建 `legal_augmentation` 工具；工具通过内部 HTTP 调用迁入 `services/legal_rag/` 的 Legal RAG 服务。该服务继续使用既有 Neo4j、Milvus、BM25、GraphRAG、rerank、evidence gate 和 claim refine 链，返回结构化证据；Deer 负责结合对话上下文生成最终回复。

非法律任务、Deer 会话状态、前端、Gateway、上传、沙箱、skills、MCP 和普通工具的行为保持不变。

## 已锁定的实施约束

1. 不新增第二个 LangGraph graph、法律 agent 或用户可见聊天系统。
2. 首版接入点是 Deer 内建工具，不使用运行时工具自演化，也不把 MCP 作为并列方案。
3. Legal 依赖单独运行；不把 `langchain-core==0.3.71`、`openai<2`、Neo4j、Milvus、Torch、Sentence Transformers 等依赖合并进 `deerflow-harness`。依赖差异见 `backend/packages/harness/pyproject.toml:5-33` 与 `/Users/yuh/Desktop/项目/Legal-consulting-expert/requirements.txt:3-31`。
4. Deer 不直接执行 Cypher、Milvus search 或法律知识库构建；数据库调用继续由迁入后的 Legal 模块负责。
5. `documents + evidence + refine.claims` 是 Deer 法律生成的权威输入；Legal `answer` 只是已校核草稿。
6. 首版使用现有 agent 工具选择与简洁 prompt 规则触发。只有触发回归测试证明存在系统性漏调用时，才规划轻量 middleware。
7. 不精确比较模型生成文字；迁移等价性比较路由、法规/条文命中、fallback、evidence mode 和 refine verdict 语义。

## 当前代码事实与实施接点

| 事实 | 代码证据 | 实施含义 |
| --- | --- | --- |
| Deer 只有一个图入口 | `backend/langgraph.json:8-13` | 不改图结构，继续由 `make_lead_agent` 创建主体 |
| Lead agent 的工具统一由 `get_available_tools()` 注入 | `backend/packages/harness/deerflow/agents/lead_agent/agent.py:334-340` | 法律能力从现有工具装配层进入 |
| Built-in tools 在中心列表和条件分支中组装 | `backend/packages/harness/deerflow/tools/tools.py:26-38,46-124` | 新工具通过该函数按 `legal_rag.enabled` 条件暴露 |
| Tool 异常已有统一兜底 | `backend/packages/harness/deerflow/agents/middlewares/tool_error_handling_middleware.py:19-65` | 预期的服务不可用返回结构化失败；未知异常仍交现有 middleware |
| Deer 已依赖 `httpx` | `backend/packages/harness/pyproject.toml:9` | Legal client 不增加 Deer 新依赖 |
| AppConfig 由 Pydantic 统一加载 | `backend/packages/harness/deerflow/config/app_config.py:27-119` | 增加显式 `LegalRAGConfig` 字段，不依赖松散 `model_extra` |
| Legal 已有完整结构化入口 | `/Users/yuh/Desktop/项目/Legal-consulting-expert/main.py:630-847` | `/v1/augment` 直接复用 `ask_question_payload` |
| Legal 服务已有 singleton、health、prewarm | `/Users/yuh/Desktop/项目/Legal-consulting-expert/api/service.py:39-158` | 迁入时保留这些生命周期代码，去掉增强接口对 chat session 的依赖 |
| Legal payload 已含主要契约字段 | `/Users/yuh/Desktop/项目/Legal-consulting-expert/api/schemas.py:57-118` | 新契约以现有 DTO 为基础，仅增加版本和无会话请求模型 |
| Legal 初始化直接构造 Neo4j/Milvus/检索/路由模块 | `/Users/yuh/Desktop/项目/Legal-consulting-expert/main.py:202-270` | 数据库和检索所有权无需重新设计 |
| 现有评测脚本按 documents/evidence/route 解析 | `/Users/yuh/Desktop/项目/Legal-consulting-expert/scripts/eval/run_eval.py:1068-1145` | 只改请求入口，保留指标计算逻辑 |
| Deer harness 禁止反向依赖 `app.*` | `backend/CLAUDE.md:107-130`、`backend/tests/test_harness_boundary.py` | Legal client/contracts 必须完全位于 harness 内且不导入 Gateway |

## 目标文件布局

```text
Deer-flow-s/
├── backend/packages/harness/deerflow/
│   ├── config/
│   │   └── legal_rag_config.py
│   ├── legal/
│   │   ├── __init__.py
│   │   ├── contracts.py
│   │   └── client.py
│   └── tools/builtins/
│       └── legal_augmentation_tool.py
├── backend/tests/
│   ├── test_legal_rag_config.py
│   ├── test_legal_rag_contracts.py
│   ├── test_legal_rag_client.py
│   ├── test_legal_augmentation_tool.py
│   └── test_legal_augmentation_prompt.py
├── services/legal_rag/
│   ├── api/
│   │   ├── __init__.py
│   │   ├── app.py
│   │   ├── schemas.py
│   │   └── service.py
│   ├── rag_modules/
│   ├── scripts/
│   │   ├── eval/
│   │   └── ingest/
│   ├── data/eval/
│   ├── tests/
│   │   ├── test_augmentation_api.py
│   │   └── test_payload_compatibility.py
│   ├── main.py
│   ├── config.py
│   ├── requirements.txt
│   ├── .env.example
│   └── Dockerfile
└── docker/
    ├── docker-compose.yaml
    └── docker-compose-dev.yaml
```

不迁入 `Legal-consulting-expert/frontend/`、`data/session_uploads/`、独立 chat/file API 与演示会话状态。

## `LegalAugmentation v1` 契约

### 服务请求

目标位置：`services/legal_rag/api/schemas.py`

```text
contract_version: "v1"
question: non-empty string
explain_routing: boolean = false
eval_batch_id: optional string      # 仅评测/追踪使用
eval_fast_mode: optional boolean    # 仅评测使用，Deer 正常调用不传
```

不传 `chat_id`、Deer message 对象、LangGraph state、Neo4j/Milvus 参数或用户文件 ID。Deer 负责从对话上下文形成一条自包含法律问题，Legal 不接管 thread。

### 服务成功响应

以现有 `ChatResponse` 字段为主体并增加 `contract_version="v1"`：

- `analysis`: 保留 `strategy/query_complexity/relationship_intensity/confidence/reasoning_required/reasoning`。
- `documents`: 保留法规名、条号、摘要、score、search type、route、rerank 及 fallback 元数据。
- `evidence`: 保留 `mode/reason/top_rerank_score/top_must_hit_count`。
- `refine`: 保留计数和全部 claim verdict；不把 claims 压成普通字符串。
- `answer`: 保留 Legal 已校核草稿，但 Deer 不以它作为唯一事实源。
- `route_fallback/routing_explanation/route_metrics/elapsed_seconds`: 原样保留。

服务端不得为迎合 Deer 重新计算这些字段；只对现有 `ask_question_payload` 结果做 schema 校验和版本包装。

### Deer 工具输出

目标位置：`backend/packages/harness/deerflow/legal/contracts.py` 与 `tools/builtins/legal_augmentation_tool.py`。

- 成功：返回经 Deer 侧 Pydantic 模型验证后的 v1 结构。
- 预期失败：返回小型结构化失败对象，至少区分 `disabled`、`timeout`、`unavailable`、`invalid_response`，且不包含数据库密码、服务响应全文或堆栈。
- 未预期异常：继续由现有 `ToolErrorHandlingMiddleware` 转成 error ToolMessage。

首版不做客户端自动重试。Legal 查询包含 LLM 与重排开销，盲目重试会重复成本；Milvus 运行期重载重试已存在于 `/Users/yuh/Desktop/项目/Legal-consulting-expert/rag_modules/milvus_index_construction.py:532-546`。

## 配置约定

### Deer 侧

新增 `LegalRAGConfig`：

```yaml
legal_rag:
  enabled: false
  base_url: http://127.0.0.1:8003
  timeout_seconds: 120
```

- `enabled=false` 时不向 lead agent 暴露工具，确保现有 Deer 安装不受影响。
- `base_url` 只指向内部服务，不包含数据库地址。`LEGAL_RAG_BASE_URL` 是可选运行时覆盖值，客户端按“环境变量优先、YAML 次之”解析；因此 disabled 或本机开发时不要求必须存在该环境变量。
- 默认总超时采用 120 秒，依据现有 Legal 评测采用的 120 秒请求窗口；实现时 HTTP connect timeout 收紧到 5 秒。
- `config.example.yaml` 新增该段，并新增/恢复 `config_version: 2`；本次无需文本替换 migration，现有 `scripts/config-upgrade.sh` 的递归 merge 负责把缺失的 `legal_rag` 段加入旧配置。同步更新 `test_config_version.py`，避免配置示例缺少版本号时升级脚本提前退出。

### Legal 服务侧

迁入并整理原 `.env.example`，至少保留：

- Neo4j URI/user/password/database。
- Milvus host/port/collection/dimension。
- embedding/reranker 模型与现有检索阈值。
- assist/generation LLM 主备配置。
- LangSmith 可选观测配置。

Legal 使用独立 `services/legal_rag/.env`；不要把数据库凭证作为 Deer tool 参数，也不要为方便而写入 `config.example.yaml`。

## 分阶段实施步骤

### 阶段 0：冻结迁移基线与数据库清单

修改/产物：

- 基线输入固定为 `/Users/yuh/Desktop/项目/Legal-consulting-expert/data/eval/eval_questions_v1_top10.jsonl` 与 `/Users/yuh/Desktop/项目/Legal-consulting-expert/data/eval/eval_questions_v1_full50.jsonl`，不得改从 `Legal-Expert` 或历史 results 目录取样。
- 以当前独立 Legal 服务生成新的 baseline 结果，不直接把历史 `metrics_summary_v1_*.json` 当成当前事实。
- 记录 Neo4j database、labels、relationship types、full-text index；记录 Milvus collection、字段、row count、embedding model 和 dimension。

验证门禁：

- top10 与 full50 请求均能完成，失败项和 route fallback 有记录。
- baseline 至少覆盖 `hybrid_traditional`、`graph_rag` 或 `combined` 中实际可触发的路径；若某一路在现有数据集未触发，补一条专门 fixture，而不是修改路由算法。
- 数据库清单只读生成；不得删除或重建 collection/index。

### 阶段 1：原样迁入 Legal 核心运行时

新增：

- `services/legal_rag/main.py`
- `services/legal_rag/config.py`
- `services/legal_rag/rag_modules/*`
- `services/legal_rag/requirements.txt`
- 必需的 `scripts/ingest/`、`scripts/eval/` 与 `data/eval/`

实施要求：

- 第一轮以路径修正和打包修正为主，不重命名核心类，不调整检索权重，不替换模型，不整理算法结构。
- 保持 `AdvancedGraphRAGSystem.initialize_system()`、`build_knowledge_base()`、`ask_question_payload()` 和 `_cleanup()` 的行为。
- 独立 Dockerfile 安装 Legal requirements；Deer 的 `backend/uv.lock` 与 harness dependencies 不加入 Legal 重依赖。
- 原独立仓库保持不变，作为阶段 1 至阶段 6 的对照基线。

验证门禁：

- 在 `services/legal_rag/` 环境中直接构造 `AdvancedGraphRAGSystem`，可连接原 Neo4j/Milvus并加载既有 collection。
- top10 的法规/条文命中、route、evidence 与 refine verdict 相对阶段 0 无迁移性变化；允许生成措辞变化。
- 关闭时 Neo4j/Milvus driver 被现有 `_cleanup()` 路径释放。

### 阶段 2：建立无会话的 Legal augmentation API

新增/修改：

- `services/legal_rag/api/schemas.py`
- `services/legal_rag/api/service.py`
- `services/legal_rag/api/app.py`
- `services/legal_rag/tests/test_augmentation_api.py`
- `services/legal_rag/tests/test_payload_compatibility.py`

实施要求：

- 从原 `RAGDemoService` 复用锁、singleton、startup、health、reranker prewarm 和 shutdown。
- 新增 `POST /v1/augment`，无需先调用 `/chats`；内部直接调用 `ask_question_payload(question, explain_routing, eval_fast_mode)`。
- 最终集成服务只需暴露 `/health` 与 `/v1/augment`。原 chat、file upload、session memory 不进入新入口。
- FastAPI startup 初始化失败时进程仍可提供 failed health；augmentation 请求在未 ready 时返回明确的 503。
- `GET /health` 始终返回现有状态结构；仅 `system_ready=true` 时使用 HTTP 200，starting/failed 使用 HTTP 503，使 Docker healthcheck 不必解析自然语言或猜测 readiness。

验证门禁：

- mocked system 下证明请求字段正确传入 `ask_question_payload`，响应字段无丢失。
- 空问题、未知 contract version、未 ready、内部异常分别得到确定的 4xx/503/5xx 行为。
- 用真实 Legal runtime 跑 top10 时，旧 `/chat` baseline 与新 `/v1/augment` 的路由、documents、evidence、refine 语义一致。

### 阶段 3：增加 Deer 侧配置、契约和客户端

新增：

- `backend/packages/harness/deerflow/config/legal_rag_config.py`
- `backend/packages/harness/deerflow/legal/__init__.py`
- `backend/packages/harness/deerflow/legal/contracts.py`
- `backend/packages/harness/deerflow/legal/client.py`
- 对应四类 backend tests。

修改：

- `backend/packages/harness/deerflow/config/app_config.py`
- `backend/packages/harness/deerflow/config/__init__.py`
- `config.example.yaml`
- `.env.example`

实施要求：

- `AppConfig` 显式包含 `legal_rag: LegalRAGConfig`。
- `LegalRAGClient` 使用 `httpx.AsyncClient`，只实现 `augment()` 和必要的 `health()`；不引入通用 service SDK 层。
- 客户端校验 v1 response，拒绝未知版本与缺少权威字段的 200 响应。
- 日志只记录 endpoint、耗时、strategy、evidence mode、document count 和错误类别，不记录完整用户问题、完整证据文本或凭证。

验证门禁：

- config 默认 disabled，合法配置可加载，无效 URL/非正 timeout 被拒绝。
- client 的成功、timeout、连接失败、非 2xx、非法 JSON、版本不匹配和字段缺失都有独立测试。
- `backend/tests/test_harness_boundary.py` 继续通过。

### 阶段 4：接入一个 Deer 内建工具与触发规则

新增：

- `backend/packages/harness/deerflow/tools/builtins/legal_augmentation_tool.py`
- `backend/tests/test_legal_augmentation_tool.py`
- `backend/tests/test_legal_augmentation_prompt.py`

修改：

- `backend/packages/harness/deerflow/tools/builtins/__init__.py`
- `backend/packages/harness/deerflow/tools/tools.py`
- `backend/packages/harness/deerflow/agents/lead_agent/prompt.py`

实施要求：

- `get_available_tools()` 仅在 `config.legal_rag.enabled` 时加入 `legal_augmentation`；disabled 时工具 schema 不进入模型上下文。
- 工具参数只保留自包含 `question` 和可选 `explain_routing`，不让模型选择 Milvus/Neo4j/GraphRAG 策略。
- 工具说明写清“法律结论、法条、责任、权利义务等需要数据库依据时使用；普通事实、写作、代码等非法律任务不使用”。
- prompt 增加单一 `<legal_augmentation>` 段：外层只判断是否需要法律增强；最终回答遵守 supported/weak/unsupported 和 evidence mode。
- 不新增 trigger middleware，不修改 `ThreadState`，不新增 graph node。

验证门禁：

- disabled/enabled 时工具集合分别不存在/存在法律工具。
- 工具成功返回完整权威结构；已知服务失败返回受控失败对象；未知错误被现有 ToolErrorHandlingMiddleware 捕获。
- prompt 测试证明 enabled 时包含触发和证据规则，disabled 时不注入。
- 构造含 unsupported claim 的固定工具响应，阶段 4 只静态验证 tool 返回仍保留 verdict，且 prompt 明确禁止使用该 claim；不虚构额外“消费层”。是否真的未回流到最终答案，仅由阶段 6 的对话级 live/integration gate 判定。

### 阶段 5：部署与现有法律数据库连通

新增/修改：

- `services/legal_rag/Dockerfile`
- `services/legal_rag/.env.example`
- `docker/docker-compose.yaml`
- `docker/docker-compose-dev.yaml`

实施要求：

- 增加内部 `legal-rag` 服务，建议端口 8003；不经 Nginx 暴露为用户 API。
- LangGraph 容器内以环境变量覆盖 `LEGAL_RAG_BASE_URL=http://legal-rag:8003`；本机开发使用 YAML 默认的 `http://127.0.0.1:8003`。
- Legal 服务使用独立 env 文件接收 Neo4j/Milvus/模型配置。
- 容器内 Neo4j/Milvus 地址必须使用可达的 service name、`host.docker.internal` 或真实外部地址，不得沿用指向容器自身的 `localhost`；Linux compose 保留与现有 Deer 一致的 `host-gateway` 映射。
- 首版连接现有 Neo4j/Milvus，不在 Deer compose 中创建第二套数据库或复制 collection。
- 只有 `legal-rag` 获得数据库凭证；Gateway 和 LangGraph 不需要 Neo4j/Milvus 环境变量。
- `legal-rag` 自身配置 healthcheck，但 Gateway/LangGraph 不以 `service_healthy` 作为启动前置。若 compose 使用 `depends_on`，只表达启动顺序，不把 Deer 的可启动性绑定到 Legal ready；运行期由 Legal client 的 unavailable/timeout 结果完成降级。

验证门禁：

- `docker compose config` 成功。
- Legal health 能反映 ready/failed；数据库地址错误不会导致 Deer frontend/Gateway/LangGraph 整体退出。
- 集成环境的 Legal 查询确实命中原 `legal_knowledge` collection 和原 Neo4j database，row count/graph data 未被复制或重建。

### 阶段 6：评测脚本迁移与端到端验收

修改：

- `services/legal_rag/scripts/eval/run_eval.py`
- 必要时新增 `backend/tests/integration/test_legal_augmentation_flow.py`，默认跳过真实外部服务，显式环境开关后运行。

实施要求：

- 将评测请求从“先 `/chats`、再 `/chat`”改为直接 `/v1/augment`；命中、route、evidence、graph fallback、latency 计算尽量不动。
- 对比阶段 0 baseline 与迁移后服务，不用历史 summary 替代本轮结果。
- Deer 侧至少覆盖：非法律不调用、简单法律调用、关系型法律调用、Legal timeout/failed、insufficient evidence、unsupported claim 六类场景。
- 若普通 tool selection 出现系统性漏触发，先记录可复现样本，再另行增加最小 guard；不得在没有证据时预先加入 middleware。

验证门禁：

- `hybrid_traditional`、`graph_rag`、`combined` 中阶段 0 可触发的策略迁移后仍可判读；rerank fallback、evidence mode 和 refine verdict 字段语义保留。
- 新服务无新增 request failure；法规/条文命中不得因接口迁移而下降。若模型波动导致差异，需按单题 documents 与 route 复核，不能只看总分。
- Deer 最终回答不包含 Legal 标为 unsupported 的 claim；一旦出现，停止单阶段实现并切换方向文档规定的两阶段核验方案。
- Legal 不可用时，Deer 返回明确“法律知识库当前不可用/证据不足”的限制说明，不伪装成数据库支持结论。

### 阶段 7：文档同步与收口

修改：

- `README.md`、`README_zh.md`
- `PROJECT_ARCHITECTURE.md`
- `backend/CLAUDE.md`
- Legal 服务运行说明（放在 `services/legal_rag/README.md`）

实施要求：

- 记录启用方式、服务地址、数据库复用方式、健康检查、非法律降级和评测命令。
- 更新 Deer 架构图，但不把 Legal 描述为第二 agent 或第二 chat backend。
- 标明原 Legal 独立仓库在迁移验收后只作历史基线，避免双边修改。

验证门禁：

- 文档命令可在当前仓库路径执行。
- 项目结构、端口和配置名与代码一致。

## 修改清单总览

### Deer 新增文件

- `backend/packages/harness/deerflow/config/legal_rag_config.py`
- `backend/packages/harness/deerflow/legal/__init__.py`
- `backend/packages/harness/deerflow/legal/contracts.py`
- `backend/packages/harness/deerflow/legal/client.py`
- `backend/packages/harness/deerflow/tools/builtins/legal_augmentation_tool.py`
- 对应 backend 单元/集成测试。

### Deer 修改文件

- `backend/packages/harness/deerflow/config/app_config.py`
- `backend/packages/harness/deerflow/config/__init__.py`
- `backend/packages/harness/deerflow/tools/builtins/__init__.py`
- `backend/packages/harness/deerflow/tools/tools.py`
- `backend/packages/harness/deerflow/agents/lead_agent/prompt.py`
- `config.example.yaml`
- `.env.example`
- `docker/docker-compose.yaml`
- `docker/docker-compose-dev.yaml`
- 项目文档。

### 从 Legal 迁入并少量适配

- `main.py`、`config.py`、`rag_modules/*`。
- `api` 中 startup/health/prewarm 核心，新增 stateless augmentation endpoint。
- `requirements.txt`、`.env.example`、必要的 ingest/eval scripts 和 eval datasets。

### 明确不修改

- Deer frontend。
- Gateway API 路由与 Nginx 外部路由。
- Deer `ThreadState`、checkpointer、memory、uploads、sandbox、skills、MCP、自演化机制。
- Legal 检索权重、路由算法、graph grounding、rerank、evidence gate、refine 规则，除非迁移验证证明原代码本身无法运行；此类问题须单独记录，不与接口迁移混改。

## 验证命令顺序

实施时按从小到大运行，前一层未通过不进入后一层：

1. Legal 纯单元测试与 API contract 测试。
2. `cd backend && uv run pytest tests/test_legal_rag_config.py tests/test_legal_rag_contracts.py tests/test_legal_rag_client.py tests/test_legal_augmentation_tool.py tests/test_legal_augmentation_prompt.py`
3. `cd backend && uv run pytest tests/test_harness_boundary.py tests/test_lead_agent_prompt_skills.py tests/test_config_version.py`
4. `cd backend && uv run ruff check packages/harness/deerflow tests`
5. `docker compose -f docker/docker-compose-dev.yaml config` 与 production compose config。
6. 对真实 Neo4j/Milvus 运行 Legal top10，再运行 full50。
7. Deer 对话级六类场景验收。
8. 最后运行完整 backend test suite；若环境不具备真实数据库/模型密钥，清楚区分已通过的纯本地测试与未执行的 live tests。

## 可验收标准

1. `legal_rag.enabled=false` 时，Deer 工具集合与 prompt 不含 Legal 能力，现有测试无回归。
2. `enabled=true` 且服务 ready 时，法律问题可通过唯一内建工具获得 v1 结构结果。
3. 新 `/v1/augment` 不需要创建 Legal chat session，并完整保留现有 payload 语义。
4. 迁入服务使用原 Neo4j/Milvus 数据、schema、collection 与索引，不产生第二份法律数据库。
5. Deer 环境不安装 Legal 重依赖，不获得数据库凭证，不包含直接数据库查询代码。
6. Legal 原有路由、召回、rerank fallback、evidence 与 refine 能力在迁移后仍可触发和观测。
7. 非法律请求不调用 Legal；Legal 不可用不阻断 Deer 普通对话。
8. Deer 不重新引入 unsupported claim；否则单阶段方案判定失败。
9. 无新增前端、第二会话系统、graph node、middleware、MCP server 或不必要基础设施。
10. 代码、测试、compose 与文档共同通过对应门禁后，方可移除对原 Legal 仓库的运行依赖。

## 风险、处理与回退点

| 风险 | 预防/处理 | 回退点 |
| --- | --- | --- |
| 依赖冲突 | 独立 service image 与 requirements | 不合并 Deer lockfile，关闭服务即可回退 |
| 现有 Milvus 向量不兼容 | 启动前核对 model/dimension/schema | readiness failed；不自动重建 |
| Neo4j schema/index 不一致 | 阶段 0 只读清单和 smoke query | 保留原配置，不运行迁移写操作 |
| Tool 漏触发 | 固定 trigger 样本，先调 prompt/description | 仅有证据后再设计最小 guard |
| Deer 二次生成破坏 refine | 固定 unsupported 样本和最终回答检查 | 切换两阶段 verify/refine 流 |
| Legal 服务延迟或不可用 | 120 秒上限、health、结构化失败、无盲重试 | `enabled=false` 隐藏工具，Deer 主体继续运行 |
| 两份 Legal 代码长期分叉 | 迁移期以原仓为 baseline，验收后 Deer 内 service 成为唯一维护源 | 未验收前不删除原仓 |

## 实施停止条件

出现以下任一情况时停止当前实施阶段，不用临时补丁绕过：

- 必须修改 Deer 主 graph 或引入第二 agent 才能继续。
- 必须让 Deer 直接连接 Neo4j/Milvus 才能完成接口。
- 迁移后需要删除或重建现有法律数据库才能运行。
- Legal 核心路由、GraphRAG、rerank、evidence 或 refine 被迫移除。
- Deer 最终回答重新包含 unsupported claim。
- 实施需要新增方向文档未授权的外部基础设施或依赖。

此时应保存已完成的验证证据，回到方向文档重新评审，不把范围扩张混入当前迁移。

## 当前状态

计划已形成，尚未开始业务代码修改。执行应从阶段 0 开始，按门禁顺序推进，不并行改写两端核心链路。
