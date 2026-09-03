# Legal RAG 内部增强服务

这是迁入 Deer-flow-s 的 Legal RAG **内部服务**，不是第二套对话系统，也不是第二 agent。

Deer 仍是唯一对话主体和最终回答界面。本服务只提供无会话的法律增强：

```text
Deer lead_agent
  → built-in tool `legal_augmentation`
  → LegalRAGClient
  → POST /v1/augment
  → AdvancedGraphRAGSystem.ask_question_payload()
```

权威依据是 `documents + evidence + refine.claims`。Legal `answer` 只是已校核草稿。`unsupported` claim 不得进入 Deer 终答。

验收后，本目录是 Legal runtime 的维护源。`/Users/yuh/Desktop/项目/Legal-consulting-expert` 只保留历史 baseline，不要双边改算法。

## 对外接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/health` | `system_ready=true` 时 HTTP 200，否则 503 |
| `POST` | `/v1/augment` | 无 `chat_id`，直接问一句自包含法律问题 |

默认端口：`8003`。不经 Nginx 对用户暴露。

请求字段：`contract_version=v1`、`question`、可选 `explain_routing` / `eval_batch_id` / `eval_fast_mode`。

## 启用方式（Deer 侧）

1. 复制 `config.example.yaml` 为 `config.yaml`（或 `make config`）。
2. 打开法律工具：

```yaml
legal_rag:
  enabled: true
  base_url: http://127.0.0.1:8003
  timeout_seconds: 120
```

3. 可选覆盖：环境变量 `LEGAL_RAG_BASE_URL` 优先于 YAML。
4. `enabled=false`（默认）时，工具和 `<legal_augmentation>` prompt 都不会进入 lead agent。

Deer 不持有 Neo4j/Milvus 凭证，也不执行 Cypher 或向量检索。

## 数据库复用

本服务连接**已有**法律库，不在 Deer compose 里新建或复制 Neo4j/Milvus。

默认标识（以实际运行实例为准）：

- Neo4j database：`neo4j`
- fulltext：`legal_fulltext_idx`
- labels：`LawDocument` / `Article` / `LegalDomain` / `RiskScenario` / `ComplianceStep`
- Milvus collection：`legal_knowledge`
- embedding：`BAAI/bge-small-zh-v1.5`，dimension `512`

本机进程与 Compose 都只读 `services/legal_rag/.env`。不要把 Neo4j/Milvus 写进根 `.env`、`config.yaml`、Gateway、LangGraph 或 compose `environment`。本机可用 `localhost`；容器内必须改成容器可达地址，例如 `bolt://host.docker.internal:7687`、`MILVUS_HOST=host.docker.internal`，或已有库的局域网地址。

如果 collection 不存在、加载失败，或 model / dimension / schema 不兼容，health 应失败。迁入服务启动时调用 `build_knowledge_base(allow_rebuild=False)`，不会自动重建 collection 或图。

## 本地运行

```bash
cp services/legal_rag/.env.example services/legal_rag/.env
# 填入已有库地址和模型密钥，不要指向空库

# 确认已有 Neo4j :7687、Milvus :19530 可连且含法律数据
uvicorn api.app:app --host 0.0.0.0 --port 8003
```

在 `services/legal_rag/` 下启动时，确保 `PYTHONPATH` 包含该目录。

## Compose

`docker/docker-compose.yaml` 与 `docker/docker-compose-dev.yaml` 都有内部服务 `legal-rag`。

- LangGraph 使用 `LEGAL_RAG_BASE_URL=http://legal-rag:8003`
- `depends_on: legal-rag` 只表示启动顺序，**没有** `service_healthy`
- Legal 不可用时，Deer 普通对话继续；工具返回 `timeout` / `unavailable`

开发映射：`8003:8003`。生产 compose 不经 Nginx 暴露。

只启动内部服务、复用已有库（不要 `up` 空的 Neo4j/Milvus）：

```bash
# 先把已有库地址写进 services/legal_rag/.env，不要在这条命令前再 export Neo4j/Milvus
docker compose -f docker/docker-compose-dev.yaml up -d --build legal-rag
```

Compose 不会再用 `environment` 覆盖该文件里的 `NEO4J_*` / `MILVUS_*`。文件缺失或地址错误时，只有 `legal-rag` health 失败；Gateway / LangGraph 不以 `service_healthy` 为启动前置。

启动时会按条文从已有 Neo4j 构图（跨机约 15 分钟），healthcheck `start_period` 为 1800s，避免构图未完成就被重启。`GET /health` 在 `system_ready=true` 之前是 503。ready 后只读库存应与启动前一致：不得出现第二份 collection，也不得改变 `legal_knowledge` 行数。

## 评测

默认走无会话 `/v1/augment`：

```bash
python services/legal_rag/scripts/eval/run_eval.py \
  --base-url http://127.0.0.1:8003 \
  --api-mode augment \
  --dataset services/legal_rag/data/eval/eval_questions_v1_top10.jsonl \
  --output-dir .omx/plans/artifacts/s07 \
  --eval-batch-id s07-top10 \
  --warmup-mode light \
  --skip-db-validate
```

对照独立源仓旧入口（仅 S01 / 新旧入口对比）：

```bash
python services/legal_rag/scripts/eval/run_eval.py \
  --base-url http://127.0.0.1:8000 \
  --api-mode chat \
  --dataset /Users/yuh/Desktop/项目/Legal-consulting-expert/data/eval/eval_questions_v1_top10.jsonl \
  --output-dir .omx/plans/artifacts/s01 \
  --eval-batch-id s01-top10 \
  --warmup-mode light \
  --skip-db-validate
```

逐题语义对比（不打印完整问题）：

```bash
python services/legal_rag/scripts/eval/compare_eval_runs.py \
  --baseline .omx/plans/artifacts/s01/eval_details.csv \
  --current .omx/plans/artifacts/s07/eval_details.csv \
  --output .omx/plans/artifacts/s07/compare.json
```

真实文件名以 `run_eval.py` 写出的 versioned path 为准。

## 受控降级

| 情况 | Deer 行为 |
| --- | --- |
| `legal_rag.enabled=false` | 不暴露工具，现有对话不变 |
| 服务 timeout / 不可达 / 非 2xx | 工具返回结构化失败，不伪装成库支持结论 |
| `evidence.mode=insufficient` | 明确说证据不足 |
| claim `verdict=unsupported` | 不得写入最终回答 |

## 测试

```bash
cd backend
PYTHONPATH=../services/legal_rag uv run pytest ../services/legal_rag/tests
uv run pytest tests/test_legal_rag_config.py tests/test_legal_rag_contracts.py \
  tests/test_legal_rag_client.py tests/test_legal_augmentation_tool.py \
  tests/test_legal_augmentation_prompt.py tests/test_legal_augmentation_scenarios.py
```

对真实服务的集成测试默认跳过：

```bash
LEGAL_RAG_LIVE=1 uv run pytest tests/integration/test_legal_augmentation_flow.py
```
