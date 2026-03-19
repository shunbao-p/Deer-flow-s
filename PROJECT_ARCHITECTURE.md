# DeerFlow Backend 项目架构图

---

## 一、整体模块结构

```
src/
├── gateway/          # HTTP 入口层（FastAPI）
├── agents/           # Agent 核心层
│   ├── lead_agent/   # 主 Agent
│   ├── middlewares/  # 中间件管道
│   └── memory/       # 记忆系统
├── sandbox/          # 沙盒执行环境
├── tools/            # 工具集
├── subagents/        # 子 Agent
├── mcp/              # MCP 协议支持
├── skills/           # 技能系统
├── models/           # 模型工厂
├── config/           # 配置管理
├── community/        # 第三方集成
└── reflection/       # 反射工具
```

---

## 二、请求完整链路

```
用户发送消息（前端）
        │
        ▼
┌─────────────────────────────────────────┐
│           Gateway 层                     │
│  src/gateway/app.py                     │
│  FastAPI 应用，注册所有路由              │
│                                         │
│  路由分类：                              │
│  ├── LangGraph 路由（主对话）            │
│  │     langgraph.json → make_lead_agent │
│  ├── /api/memory      memory.py         │
│  ├── /api/artifacts   artifacts.py      │
│  ├── /api/uploads     uploads.py        │
│  ├── /api/models      models.py         │
│  ├── /api/skills      skills.py         │
│  └── /api/mcp         mcp.py            │
└─────────────────────────────────────────┘
        │ LangGraph ��由
        ▼
┌─────────────────────────────────────────┐
│           Agent 创建层                   │
│  src/agents/lead_agent/agent.py         │
│  make_lead_agent(config)                │
│                                         │
│  每条消息触发一次，做三件事：            │
│  1. _resolve_model_name()  解析模型名   │
│  2. _build_middlewares()   构建管道链   │
│  3. create_agent()         创建主Agent  │
└─────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────┐
│           Middleware 管道链              │
│  （按顺序执行，固定后不变）              │
│                                         │
│  钩子类型说明：                          │
│  [BA] = before_agent   整轮开始前        │
│  [AA] = after_agent    整轮结束后        │
│  [BM] = before_model   每次LLM调用前    │
│  [AM] = after_model    每次LLM调用后    │
│  [WM] = wrap_model_call 包裹LLM调用     │
│                                         │
│  1.  ThreadDataMiddleware      [BA]     │
│      注入 thread_id 等基础数据           │
│      thread_data_middleware.py          │
│                                         │
│  2.  UploadsMiddleware         [BA]     │
│      扫描上传目录，有新文件则注入消息    │
│      uploads_middleware.py              │
│                                         │
│  3.  SandboxMiddleware         [BA]     │
│      懒初始化沙盒，注入沙盒上下文        │
│      sandbox/middleware.py              │
│                                         │
│  4.  DanglingToolCallMiddleware [WM]    │
│      修复历史中断的工具调用记录          │
│      dangling_tool_call_middleware.py   │
│                                         │
│  5.  SummarizationMiddleware   [BM]     │
│      token超限时压缩历史消息（可选）     │
│      langchain内置                      │
│                                         │
│  6.  TodoListMiddleware        [BM/AM]  │
│      plan mode下提供任务管理工具（可选） │
│      langchain内置                      │
│                                         │
│  7.  TitleMiddleware           [AA]     │
│      首轮对话后自动生成会话标题          │
│      title_middleware.py                │
│                                         │
│  8.  MemoryMiddleware          [AA]     │
│      对话结束后提取信息送入记忆队列      │
│      memory_middleware.py               │
│                                         │
│  9.  ViewImageMiddleware       [BA]     │
│      模型支持视觉时解析图片（可选）      │
│      view_image_middleware.py           │
│                                         │
│  10. SubagentLimitMiddleware   [AM]     │
│      限制并发子Agent数量（可选）         │
│      subagent_limit_middleware.py       │
│                                         │
│  11. ClarificationMiddleware   [AM]     │
│      拦截模型的澄清请求                  │
│      clarification_middleware.py        │
└─────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────┐
│           主 Agent 执行                  │
│  系统提示词构建：                        │
│  src/agents/lead_agent/prompt.py        │
│  apply_prompt_template()                │
│  ├── 注入 memory 上下文                 │
│  ├── 注入 subagent 配置                 │
│  └── 注入 sandbox 路径信息              │
│                                         │
│  工具加载：                              │
│  src/tools/tools.py                     │
│  get_available_tools()                  │
│  ├── 内置工具（clarification/task等）   │
│  ├── sandbox 工具（执行代码/读写文件）  │
│  ├── community 工具（tavily/jina等）    │
│  ├── MCP 工具                           │
│  └── subagent 工具（可选）              │
│                                         │
│  模型调用：                              │
│  src/models/factory.py                  │
│  create_chat_model(name, thinking)      │
└─────────────────────────────────────────┘
        │ 模型调用工具
        ▼
┌─────────────────────────────────────────┐
│           工具执行层                     │
│                                         │
│  Sandbox 工具                           │
│  src/sandbox/tools.py                   │
│  ├── execute_code   执行代码            │
│  ├── read_file      读文件              │
│  ├── write_file     写文件              │
│  └── list_dir       列目录              │
│          │                              │
│          ▼                              │
│  src/sandbox/sandbox.py                 │
│  Sandbox（按 thread 隔离）              │
│  └── 文件路径: ~/.deer-flow/threads/    │
│                {thread_id}/sandbox/     │
│                                         │
│  Subagent 工具（可选）                  │
│  src/subagents/executor.py              │
│  ├── general_purpose  通用子Agent       │
│  └── bash_agent       Bash子Agent      │
│                                         │
│  MCP 工具（可选）                       │
│  src/mcp/tools.py                       │
│  └── 动态加载外部MCP服务的工具          │
│                                         │
│  Community 工具                         │
│  src/community/                         │
│  ├── tavily/    网络搜索                │
│  ├── jina_ai/   网页读取                │
│  ├── firecrawl/ 网页爬取                │
│  └── image_search/ 图片搜索             │
└─────────────────────────────────────────┘
```

---

## 三、Memory 记忆系统链路

```
主Agent完成一轮回答
        │
        ▼
MemoryMiddleware.after_agent()
src/agents/middlewares/memory_middleware.py
  ├── _filter_messages_for_memory()
  │   只保留 human 消息 + 无tool_calls的AI消息
  └── get_memory_queue().add(thread_id, messages)
        │
        ▼
MemoryUpdateQueue.add()
src/agents/memory/queue.py
  ├── 同一thread的旧请求被替换（debounce）
  └── 重置30秒计时器
        │ 30秒后触发
        ▼
MemoryUpdateQueue._process_queue()
  └── MemoryUpdater().update_memory()
        │
        ▼
MemoryUpdater.update_memory()
src/agents/memory/updater.py
  ├── get_memory_data()         读 memory.json（mtime缓存）
  ├── format_conversation_for_update()  格式化对话文本
  ├── MEMORY_UPDATE_PROMPT.format()     构建提示词
  ├── model.invoke()            调用LLM提取信息
  ├── _apply_updates()          应用更新
  │   ├── shouldUpdate=true 的字段才更新
  │   ├── confidence >= 0.7 的fact才存入
  │   └── 超过100条按confidence排序截断
  └── _save_memory_to_file()    原子写入文件
        │                       （先写.tmp再rename）
        ▼
~/.deer-flow/memory.json        全局唯一，所有thread共享

        ┌──────────────────────────────┐
        │  下次对话开始时注入           │
        └──────────────────────────────┘
        │
        ▼
apply_prompt_template()
src/agents/lead_agent/prompt.py
  └── format_memory_for_injection()
      src/agents/memory/prompt.py
      ├── 提取 workContext/personalContext/topOfMind
      ├── 提取 recentMonths/earlierContext
      ├── tiktoken 计算token数，超2000则截断
      └── 返回格式化文本注入系统提示词
```

---

## 四、Middleware 管道判断逻辑

```
_build_middlewares(config, model_name)
src/agents/lead_agent/agent.py

判断依据来源：
┌─────────────────────────────────────────────┐
│  config.yaml 静态配置                        │
│  ├── summarization.enabled                  │
│  │   → 决定 SummarizationMiddleware 是否加入 │
│  └── model.supports_vision                  │
│      → 决定 ViewImageMiddleware 是否加入     │
├─────────────────────────────────────────────┤
│  前端运行时参数 config.configurable          │
│  ├── is_plan_mode                           │
│  │   → 决定 TodoListMiddleware 是否加入      │
│  └── subagent_enabled                       │
│      → 决定 SubagentLimitMiddleware 是否加入 │
└─────────────────────────────────────────────┘

无条件加入（每次都有）：
  ThreadDataMiddleware
  UploadsMiddleware
  SandboxMiddleware
  DanglingToolCallMiddleware
  TitleMiddleware
  MemoryMiddleware
  ClarificationMiddleware
```

---

## 五、Sandbox 沙盒系统链路

```
SandboxMiddleware.before_agent()
src/sandbox/middleware.py
  └── 懒初始化：第一次调用时创建沙盒
        │
        ▼
Sandbox（按 thread_id 隔离）
src/sandbox/sandbox.py
  └── 文件目录结构：
      ~/.deer-flow/threads/{thread_id}/
      ├── sandbox/          ← 代码执行工作目录
      └── uploads/          ← 用户上传文件目录

工具调用时：
  execute_code → LocalSandbox.run_code()
  read_file    → 读 sandbox/ 目录下的文件
  write_file   → 写 sandbox/ 目录下的文件
  list_dir     → 列 sandbox/ 目录
```

---

## 六、配置文件与模块对应关系

```
config.yaml
  ├── models[]              → src/config/model_config.py
  │   ├── name              → create_chat_model() 模型选择
  │   ├── supports_vision   → ViewImageMiddleware 是否启用
  │   └── supports_thinking → thinking_enabled 是否生效
  ├── summarization         → src/config/summarization_config.py
  │   └── enabled           → SummarizationMiddleware 是否启用
  ├── memory                → src/config/memory_config.py
  │   ├── enabled           → MemoryMiddleware 是否工���
  │   ├── debounce_seconds  → 队列等待时间（默认30s）
  │   ├── max_facts         → facts最大条数（默认100）
  │   └── fact_confidence_threshold → fact最低置信度（默认0.7）
  ├── sandbox               → src/config/sandbox_config.py
  ├── skills                → src/config/skills_config.py
  └── subagents             → src/config/subagents_config.py
```

---

## 七、关键文件速查

| 功能 | 文件路径 |
|------|---------|
| 主Agent创建入口 | `src/agents/lead_agent/agent.py` |
| 系统提示词构建 | `src/agents/lead_agent/prompt.py` |
| 会话状态定义 | `src/agents/thread_state.py` |
| 工具加载总入口 | `src/tools/tools.py` |
| 模型工厂 | `src/models/factory.py` |
| 沙盒核心 | `src/sandbox/sandbox.py` |
| 沙盒中间件 | `src/sandbox/middleware.py` |
| 记忆队列 | `src/agents/memory/queue.py` |
| 记忆更新引擎 | `src/agents/memory/updater.py` |
| 记忆提示词模板 | `src/agents/memory/prompt.py` |
| Gateway入口 | `src/gateway/app.py` |
| MCP工具加载 | `src/mcp/tools.py` |
| 子Agent执行器 | `src/subagents/executor.py` |
| 配置总入口 | `src/config/app_config.py` |