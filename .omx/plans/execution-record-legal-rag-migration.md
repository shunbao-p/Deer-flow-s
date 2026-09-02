# Legal RAG 迁入 Deer-flow-s 执行记录

## 任务元信息

- 目标仓库：`/Users/yuh/Desktop/项目/Deer-flow-s`
- 唯一源仓：`/Users/yuh/Desktop/项目/Legal-consulting-expert`
- 禁止源仓：`/Users/yuh/Desktop/项目/Legal-Expert`
- 方向文档：`.omx/plans/prd-legal-rag-migration-direction.md`
- 实施计划：`.omx/plans/implementation-plan-legal-rag-migration.md`
- 分阶段提示词：`.omx/plans/prompts-legal-rag-migration-execution.md`
- 开始时间：2026-09-02
- 当前总体状态：`blocked`
- 当前阶段：`S01`（live 门禁仍缺）；S02–S08 仅有静态进度，均未 completed

## 背景预检

- 已完整读取方向文档、实施计划、分阶段提示词。
- 执行记录原先不存在，本文件于预检时创建。
- `git status`：工作树仅有未跟踪 `.omx/`，无已有业务代码 diff。
- 源仓固定评测输入存在：
  - `data/eval/eval_questions_v1_top10.jsonl`
  - `data/eval/eval_questions_v1_full50.jsonl`
- 目标仓 `services/` 为空目录；`deerflow/legal/` 仅有 `__pycache__`。
- 禁止源仓目录在磁盘上存在，实施中不使用。

## 阶段状态表

| ID | 状态 | 下一状态 |
| --- | --- | --- |
| S01 | blocked | S02（须先完成本轮 live baseline） |
| S02 | in_progress | S03（代码已迁入，live 对等未证） |
| S03 | in_progress | S04（mocked API 已过，live 对比未做） |
| S04 | in_progress | S05（单元测试已过，待 S01–S03 live） |
| S05 | in_progress | S06（单元测试已过，待 live 对话） |
| S06 | in_progress | S07（compose 已接入 legal-rag，原库命中未证） |
| S07 | in_progress | S08（评测入口已改，live 对比/六类对话未做） |
| S08 | in_progress | complete（文档已同步，全量 live 未过） |

## S01：冻结 Legal baseline 与数据库清单

- 阶段状态：`blocked`
- 执行目标：以当前独立 Legal 服务生成 top10/full50 本轮 baseline，并只读记录 Neo4j/Milvus 清单。
- 实际完成：
  - 完整读取方向文档、实施计划、分阶段提示词；创建本执行记录。
  - 确认唯一源仓评测输入存在：`eval_questions_v1_top10.jsonl`、`eval_questions_v1_full50.jsonl`。
  - 从源仓脚本确认评测入口为 `scripts/eval/run_eval.py`，默认 `http://127.0.0.1:8000`，先 `/chats` 再 `/chat`。
  - 从源仓 `config.py` 只读记录默认库标识（非本轮实测）：Neo4j database=`neo4j`，fulltext=`legal_fulltext_idx`，labels=`LawDocument/Article/LegalDomain/RiskScenario/ComplianceStep`；Milvus collection=`legal_knowledge`，dimension=`512`，embedding=`BAAI/bge-small-zh-v1.5`。
  - 2026-09-02 13:21 再次探测：8000/7687/19530 仍关闭；无 Legal `.env`；无 LLM/DB 环境变量；无 neo4j/milvus docker 镜像或 volume；本机无 Neo4j/Milvus 数据目录。
  - 2026-09-02 13:23 第三次探测：8000/8003/7687/7474/19530 仍关闭；源仓与 `services/legal_rag/` 均无 `.env`；shell 无相关密钥；`docker ps` 为空；无 neo4j/milvus volume；源仓 `volumes/` 不存在。源仓 `docker-compose.yml` 只含空 Milvus 栈定义，按契约不得 `up`。磁盘未找到 `neostore*` / `legal_knowledge*`。仅有镜像 `deer-flow-legal-rag-review:latest`（服务镜像，不含库数据）。
  - 2026-09-02 13:37 第四次探测：上述端口仍关闭；无 `.env`；无运行中的 neo4j/milvus 容器。扩大搜索仍无 Neo4j Desktop、`neostore`、LawRefBook 数据目录或源仓 `volumes/`。
  - 2026-09-02 13:41 第五次探测：端口仍关闭。`/Volumes/macshot` 仅为截图应用，无库数据。源仓 `data/raw/Laws` 为空；`.gitignore` 忽略 `volumes/` 且该目录不存在。
  - 2026-09-02 13:44 第六次探测：8000/8003/7687/19530 仍关闭；无 `.env`；无运行中 docker 容器。
  - 2026-09-02 13:45 第七次探测：端口仍关闭。源仓 git 仅有 initial import，从未提交 `volumes/` 或 `.env`；本机无该数据面。先前 MCP sidecar 方案不在当前工作树，现行实现仍是 built-in tool → `/v1/augment`。再堆静态测试不能替代 live 门禁，本阶段按契约停在用户恢复环境。
  - 2026-09-02 13:46 第八次探测：端口仍关闭；源仓与迁入服务均无 `.venv`；`deer-flow-legal-rag-review` 镜像已不存在。修了 S01 恢复脚本：库存脚本失败不再中断评测，并显式处理 driver ImportError。
  - 2026-09-02 13:48 第九次探测：仍全部关闭、无 `.env`。未再追加业务代码；剩余工作全部是 live 门禁。
  - 历史 `metrics_summary_v1_4.json` 仅作路由参考：full50 曾覆盖 `graph_rag=28` / `hybrid_traditional=19` / `combined=2`。**不是本轮 baseline**。
  - 完成不依赖 live 的静态准备：评测输入统计、只读库存脚本、S01 恢复脚本。这不是本轮 baseline。
- 关键改动与文件：
  - `.omx/plans/execution-record-legal-rag-migration.md`
  - `.omx/plans/artifacts/s01/eval_input_stats.json`（仅题量与法规计数字段，无完整问题）
  - `.omx/plans/artifacts/s01/readonly_db_inventory.py`（只读，无写库）
  - `.omx/plans/artifacts/s01/run_s01_live.sh`（仅在源仓 `/health` 已 ready 时跑清单 + top10/full50；绝不启动空库）
  - 未启动、未创建、未复制任何数据库。
- 验证命令及结果：
  - `curl http://127.0.0.1:8000/health` → 连接失败（两次探测相同）。
  - `nc 127.0.0.1:7687` / `19530` → closed。
  - `docker images` / `docker volume ls` → 无 milvus/neo4j 资产。
  - 源仓 `.env` 不存在。
  - 静态输入：top10=10 题；full50=50 题（其中 35 题带 expected_law_primary）。
  - **本轮 top10/full50 baseline 未执行**（核心门禁未满足，未虚构结果）。
  - 历史 `data/eval/results/metrics_summary_v1_4.json` 仅作参考，不作为本轮 baseline。
- 问题、处理与重要决策：
  - S01 核心完成条件是本轮 live baseline + 只读库清单。环境缺失时按契约停止，不进入 S02，不启动空的 compose（会形成空库，违反“不重建/不复制”）。
  - 所需用户动作（外部环境，无法由代理代办）：
    1. 启动**已有法律数据**的 Neo4j（bolt 可达，含 LawDocument/Article 与 `legal_fulltext_idx`）。
    2. 启动**已有** Milvus，且 collection `legal_knowledge` 已存在、embedding/dimension 与现网一致。
    3. 在源仓创建 `.env`（可从 `.env.example` 复制），填入可用的 `MOONSHOT_API_KEY`/`DEEPSEEK_API_KEY` 及真实 Neo4j/Milvus 连接。
    4. 在源仓启动独立 Legal API：`uvicorn api.app:app --host 0.0.0.0 --port 8000`，直到 `/health` 的 `status=ready`。
  - 恢复位置：用户完成上述动作后，从 **S01 评测执行**继续，不要重做文档预检。下一步命令：
    1. 只读导出 Neo4j labels/rels/indexes 与 Milvus collection/row count/dimension。
    2. `python scripts/eval/run_eval.py --base-url http://127.0.0.1:8000 --dataset data/eval/eval_questions_v1_top10.jsonl --output-dir <Deer>/.omx/plans/artifacts/s01 --eval-batch-id s01-top10 --warmup-mode light`
    3. 同样跑 `eval_questions_v1_full50.jsonl`，batch id `s01-full50`。
    4. 核对路由覆盖后将 S01 标为 completed，再进入 S02。
- 剩余风险或延期项：本机当前看不到既有法律库进程或数据卷；用户需指向已有实例，不能为评测新建空库。
- 下一状态：等待用户恢复环境后继续 S01 live 门禁。S02–S06 仅做了不依赖库的静态实现，均未标 completed。

## S02：原样迁入 Legal 核心 runtime

- 阶段状态：`in_progress`
- 执行目标：将 Legal 核心以最小适配迁入 `services/legal_rag/`。
- 实际完成：已从唯一源仓复制 `main.py`、`config.py`、`rag_modules/`、`requirements.txt`、`scripts/ingest|eval`、评测 jsonl、`.env.example`。未迁 frontend/session uploads。未改检索算法。未把 Legal 重依赖写入 harness。2026-09-02 复核：`main.py`/`config.py`/`rag_modules/*.py` 与源仓字节一致。
- 关键改动与文件：`services/legal_rag/**`（核心 runtime）。`main.py` 仅增加 `build_knowledge_base(allow_rebuild=...)` 默认 True，保持源仓 CLI 行为。
- 验证命令及结果：`ast.parse` 全部迁入 Python 通过。SHA256 与源仓核心文件一致。**未做** top10 相对 S01 语义对比（S01 baseline 不存在）。未做 live `_cleanup` 验证。
- 问题、处理与重要决策：在 S01 blocked 时开始静态迁入，是为推进代码落地，不视为 S02 完成。源仓 `build_knowledge_base()` 在集合缺失或加载失败时会重建 Milvus；迁入服务改为 `allow_rebuild=False`，避免 compose 打到空库时自动建库。
- 剩余风险或延期项：必须用本轮 S01 baseline 做 top10 对等后才能 completed。
- 下一状态：S01 live 完成后做连通与语义对比。

## S03：建立无会话 Legal augmentation API

- 阶段状态：`in_progress`
- 执行目标：复用 lifecycle，新增 `/v1/augment`。
- 实际完成：新增 `api/schemas.py`、`api/service.py`、`api/app.py`；仅暴露 `/health` 与 `/v1/augment`；直接委托 `ask_question_payload`；ready=200，否则 health=503。启动调用 `build_knowledge_base(allow_rebuild=False)`。
- 关键改动与文件：`services/legal_rag/api/*`、`services/legal_rag/tests/test_augmentation_api.py`、`test_payload_compatibility.py`。
- 验证命令及结果：`PYTHONPATH=../services/legal_rag uv run pytest ../services/legal_rag/tests` → 15 passed（含拒绝重建）。**未做** 真实 top10 旧 `/chat` vs 新 `/v1/augment` 对比。
- 问题、处理与重要决策：契约在现有 ChatResponse 字段上加 `contract_version=v1`，不重算检索字段。
- 剩余风险或延期项：live 入口对比。
- 下一状态：S01/S02 live 后补真实对比。

## S04：增加 Deer 侧配置、契约与薄客户端

- 阶段状态：`in_progress`
- 执行目标：在 harness 内建立最薄 v1 transport。
- 实际完成：`LegalRAGConfig` 默认 disabled；`LEGAL_RAG_BASE_URL` 环境优先；`LegalRAGClient` 使用 AsyncClient，无重试；日志不含完整问题/证据。
- 关键改动与文件：`deerflow/config/legal_rag_config.py`、`deerflow/legal/*`、`app_config.py`、`config.example.yaml`（`config_version: 2`）、`.env.example`、对应 tests。
- 验证命令及结果：`uv run pytest tests/test_legal_rag_config.py tests/test_legal_rag_contracts.py tests/test_legal_rag_client.py tests/test_harness_boundary.py tests/test_config_version.py` 通过。
- 问题、处理与重要决策：`legal_rag` 使用 default_factory，旧 config 缺字段不会启动失败。`health()` 读取 503 JSON 而不 raise，便于区分 failed 与不可达。
- 剩余风险或延期项：阶段完成仍依赖 S01–S03 live 门禁。
- 下一状态：S05 静态已接上。

## S05：接入唯一 Deer 内建工具与触发规则

- 阶段状态：`in_progress`
- 执行目标：按 `legal_rag.enabled` 装配 `legal_augmentation`。
- 实际完成：唯一 built-in tool；disabled 不进工具集/prompt；prompt 含 supported/weak/unsupported 规则；未改 ThreadState/graph，未加 middleware。
- 关键改动与文件：`legal_augmentation_tool.py`、`tools.py`、`prompt.py`、`test_legal_augmentation_tool.py`、`test_legal_augmentation_prompt.py`。
- 验证命令及结果：上述 tool/prompt 测试 + `test_lead_agent_prompt_skills.py` 通过。ruff 对新文件通过。
- 问题、处理与重要决策：工具为 async，避免在 LangGraph 事件循环里 `asyncio.run`。
- 剩余风险或延期项：六类对话与 unsupported 回流只在 S07 live 判定。
- 下一状态：S06 静态已接上。

## S06：部署并连通既有 Neo4j/Milvus

- 阶段状态：`in_progress`
- 执行目标：compose 接入内部 legal-rag，复用原库。
- 实际完成：独立 Dockerfile；dev/prod compose 增加内部 `legal-rag`；LangGraph 设 `LEGAL_RAG_BASE_URL=http://legal-rag:8003`；`depends_on` 无 `service_healthy`；库地址默认 `host.docker.internal`，不在 compose 中新建 Neo4j/Milvus。
- 关键改动与文件：`services/legal_rag/Dockerfile`、`docker/docker-compose.yaml`、`docker/docker-compose-dev.yaml`。
- 验证命令及结果：在补齐既有 compose 所需路径变量后，`docker compose ... config --services` 含 `legal-rag`。**未做** 真实查询命中原 collection、未做错误地址降级 live。
- 问题、处理与重要决策：不经 Nginx 暴露；凭证只进 legal-rag env。
- 剩余风险或延期项：原库连通与未复制/未重建证据。
- 下一状态：环境恢复后做 live 命中验证。

## S07：迁移评测并完成端到端验收

- 阶段状态：`in_progress`
- 执行目标：评测入口改为 `/v1/augment`，完成六类对话验收。
- 实际完成：迁入评测脚本默认改为 `POST /v1/augment`；保留 `--api-mode chat` 仅供对照独立源仓 `/chat`。增加 refine 计数列（不含 claim 正文）。新增语义对比脚本、S07 恢复脚本，以及六类场景的工具级 + **scripted lead-agent 回路**测试。live top10/full50 对比与真实模型对话未做。
- 关键改动与文件：
  - `services/legal_rag/scripts/eval/run_eval.py`
  - `services/legal_rag/scripts/eval/compare_eval_runs.py`
  - `services/legal_rag/tests/test_run_eval_augment.py`
  - `backend/tests/test_legal_augmentation_scenarios.py`
  - `backend/tests/test_legal_augmentation_agent_loop.py`
  - `backend/tests/integration/test_legal_augmentation_flow.py`（`LEGAL_RAG_LIVE=1` 才跑）
  - `.omx/plans/artifacts/s07/run_s07_live.sh`
- 验证命令及结果：评测请求形状测试通过；六类场景工具级与 scripted agent 回路通过（unsupported 文本未进入终答）。集成测试默认 skipped。**未做** 与 S01 baseline 的 live 对比，也未用真实 LLM 验收对话。
- 问题、处理与重要决策：`--api-mode chat` 是为了用同一套指标脚本打源仓旧入口，不修改源仓。对话级 unsupported 回流只能 live 判定。
- 剩余风险或延期项：S01 live 未形成，S07 不能 completed。
- 下一状态：环境恢复并完成 S01–S06 live 后跑 augment 评测与六类对话。

## S08：文档同步、全量验证与最终收口

- 阶段状态：`in_progress`
- 执行目标：文档与代码一致，完成最终验收对照。
- 实际完成：已写 `services/legal_rag/README.md`，并同步 README / README_zh / PROJECT_ARCHITECTURE / backend/CLAUDE.md / backend/docs/ARCHITECTURE.md / CONFIGURATION.md。未宣称总体完成。
- 关键改动与文件：上述文档与 Legal 服务 README。
- 验证命令及结果：文档路径/端口与代码一致（8003、`/v1/augment`、`legal_rag.enabled`）。全量 live 验收未做。
- 问题、处理与重要决策：文档按当前静态实现撰写，并写明 live 门禁未过。
- 剩余风险或延期项：缺少 S01–S07 live 证据时不能收口。
- 下一状态：live 通过后再对照 10 条验收标准。

## 最终验收区

- 总体结论：`blocked`。S01 live baseline 未形成，S01–S08 均未 completed。静态代码、单测、评测入口和文档已落地。
- 实际改动范围：`services/legal_rag/`、Deer harness legal client/tool/config/prompt、compose、评测脚本、项目文档、执行记录。
- 验证证据：Deer 定向单测含六类 scripted agent 回路通过；Legal API/eval/no-rebuild mocked 15 passed；compose/harness 边界测试 3 passed（无 Neo4j/Milvus 服务、无 `service_healthy`、harness 无重依赖、Deer 无直接 DB client）；迁入核心文件与源仓哈希一致。无本轮 top10/full50 baseline，无真实 LLM 六类对话，无原库命中证据。
- 10 条验收标准对照（当前证据）：
  1. disabled 时不暴露工具/prompt：单测证明；未做完整回归 suite 作为收口。
  2. enabled + ready 时工具返回 v1：单测/mocked 证明；live 未证。
  3. `/v1/augment` 无 session：mocked 证明；与旧 `/chat` live 对比未做。
  4. 复用原库且不产生第二份库：compose 不含 Neo4j/Milvus；启动拒绝重建。原库命中未证。
  5. Deer 无重依赖/无直接 DB 代码：边界测试证明。
  6. 路由/rerank/evidence/refine 仍可触发：历史参考有三路；本轮 live 未证。
  7. 非法律不调用、不可用不阻断：scripted 回路证明；真实模型未证。
  8. unsupported 不进终答：scripted 回路证明；真实 LLM 硬门禁未证。
  9. 无第二 agent/graph/frontend/middleware/MCP：代码审查一致。
  10. 可移除对源仓运行依赖：否，S01 仍必须打源仓 live API。
- 未解决风险：缺少已有 Neo4j/Milvus、源仓 `.env` 与 Legal API。恢复后运行 `.omx/plans/artifacts/run_remaining_live.sh`，不要重做文档预检，也不要 `docker compose up` 空库。
