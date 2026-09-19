# 中国移动意图识别智能体

该模块把用户自然语言转换为可校验的移动业务六元组，同时保留原始输入、字段证据、候选意图、歧义和缺失项。六元组用于程序校验和后续编排，不替代用户原文。

## 处理流程

```text
接收请求 → 规范化 → 检索已审核知识 → 判断知识覆盖
  ├─ 完全命中 → 规则转译 ───────────────────────────────┐
  └─ 部分或未命中 → 准备模型消息 → LLM 决定下一步       │
                            ├─ 产生 tool_calls            │
                            │   ↓                         │
                            │  ToolNode 执行只读工具       │
                            │   └──── 工具结果回到 LLM ────┤
                            └─ 不再调用工具                │
                                ↓                         │
                           结构化编译六元组                 │
                                └──────────────────────────┤
                                                           ↓
                                                     六元组校验
  ├─ 缺失或歧义 → 用户补充 → 重新进入模型消息与工具循环
  ├─ 需要确认   → 用户确认 ─┬─ 确认 → 最终定稿
  │                         └─ 取消 → END
  ├─ 通过       → 最终定稿 → 确认并激活知识 → END
  └─ 无效       → END
```

模型生成或在部分知识基础上补全的结果，在用户确认或校验通过后会直接激活并参与下一次规则匹配，不再经过二次人工审核。ToolNode 只注册查询类工具，不允许在意图转译阶段执行办理、扣费、删除等写操作。手机号码在知识写回时会被掩码，用户和意图任务通过 `user_id + thread_id` 做所有权校验。

## 持久化结构

正式服务默认使用 MongoDB，以下内容不会因为后端重启而丢失：

```text
intent_recognition_db
├── intent_checkpoints          # LangGraph 状态快照
├── intent_checkpoint_writes    # LangGraph 节点写入
├── intent_tasks                # 六元组结果、HITL 状态和用户归属
├── intent_traces               # 本次实际执行节点
└── intent_knowledge            # active/pending/rejected 知识模板
```

原 `knowledge/data/*.json` 只作为初始化迁移来源。服务启动时会幂等迁移已有规则和候选；此后 MongoDB 是事实来源。

Neo4j 是可选的知识关系投影。通用知识模板使用“本人”等脱敏主体；已完成任务会另外保存张三、李四等业务主体实例。每次运行使用独立的 `IntentInstance` 节点，通过 `EXECUTES` 连接动作、通过 `HAS_SUBJECT` 连接业务主体，再由业务主体通过 `INSTANCE_OF` 连接通用主体。不同参数只保存在实例节点的 `instance_data_json` 中，不会在动作和主体之间重复生成运行时直连边。实名实例不会参与通用规则匹配。Neo4j 不可用不会破坏 MongoDB 中的知识，可以在恢复后重新同步。

## 启动

安装该独立模块所需依赖：

```powershell
.\.venv\Scripts\python.exe -m pip install -r .\intent_recognition_agent\requirements.txt
```

后端默认监听 `8096`：

```powershell
.\.venv\Scripts\python.exe .\start_intent_agent.py
```

独立工作台默认监听 `3001`：

```powershell
cd intent_recognition_agent\frontend
npm install
npm run dev
```

MongoDB 必须先监听 `127.0.0.1:27017`。如果暂时只运行单元测试，可以设置：

```powershell
$env:INTENT_PERSISTENCE_BACKEND = "memory"
```

启用 Neo4j 前安装依赖并在 `.env` 设置：

```dotenv
INTENT_NEO4J_ENABLED=true
INTENT_NEO4J_URI=neo4j://127.0.0.1:7687
INTENT_NEO4J_USERNAME=neo4j
INTENT_NEO4J_PASSWORD=你的密码
```

该服务与原项目后端独立运行，不修改或注册到 `src/api_view` 的 FastAPI 应用。

## 主要接口

- `POST /api/intents/recognize`：启动识别。
- `POST /api/intents/{thread_id}/resume`：提交补充信息或确认结果。
- `GET /api/intents/{thread_id}?user_id=...`：读取识别结果。
- `GET /api/intent-graph/definition`：读取静态图定义。
- `GET /api/intent-graph/traces/{thread_id}?user_id=...`：读取用户自己的运行轨迹。
- `GET /api/knowledge/rules`：读取已确认并生效的知识。
- `DELETE /api/knowledge/templates/{id}`：直接删除知识并同步移除 Neo4j 投影。
- `GET /api/knowledge/graph`：获取知识可视化节点和关系。
- `POST /api/knowledge/graph/sync`：将 MongoDB 活动规则重建到 Neo4j。
- `POST /api/knowledge/graph/sync-deletions`：把 Neo4j Browser 中的删除同步回 MongoDB。

在 Neo4j Browser 中查看一次已完成请求的实例详情：

```cypher
MATCH (run:IntentInstance)-[execution:EXECUTES]->(action:KnowledgeEntity)
MATCH (run)-[subject_link:HAS_SUBJECT]->(person:IntentSubject)
RETURN run, execution, action, subject_link, person
```

展开 `IntentInstance` 节点的 `instance_data_json` 属性，可以看到本次请求的主体、动作、业务对象、上下文参数、约束和目标；不要只使用 `MATCH (source:KnowledgeEntity)-[edge]->(target:KnowledgeEntity)`，该写法会排除 `IntentInstance`。

示例：

```json
{
  "text": "给我办理20元10GB流量包，下月生效",
  "user_id": "zhangsan"
}
```

如果用户尚未明确确认，接口返回 `requires_confirmation` 和中断问题。使用返回的 `thread_id` 调用恢复接口并提交 `确认` 后，图才会生成完成状态。

## 配置

- `INTENT_USE_LLM`：是否优先调用模型，默认 `true`。
- `INTENT_MODEL_NAME`：意图模型名称，默认复用 `MAIN_MODEL_NAME`。
- `INTENT_MODEL_BASE_URL`：意图模型的 OpenAI 兼容接口地址；未设置时使用 `DASHSCOPE_BASE_URL`。
- `INTENT_MODEL_API_KEY`：意图模型接口密钥；本地服务可填写任意非空值，例如 `local`。
- `INTENT_MODEL_TIMEOUT`：模型超时秒数，默认 `60`。
- `INTENT_KNOWLEDGE_MODEL_TIMEOUT`：仅用于知识检索未命中后的模型标准化和语义覆盖判断，默认 `15` 秒且不重试，避免“检索知识图谱”长时间阻塞。
- `INTENT_AGENT_HOST` / `INTENT_AGENT_PORT`：独立服务地址，默认 `127.0.0.1:8096`。
- `INTENT_PERSISTENCE_BACKEND`：正式运行使用 `mongodb`，测试可使用 `memory`。
- `INTENT_MONGODB_URI` / `INTENT_MONGODB_DATABASE`：MongoDB 连接和数据库名。
- `INTENT_NEO4J_ENABLED`：是否启用 Neo4j 知识关系投影。

## 知识审核与可视化

工作台下方新增两个区域：

- **已生效知识**：用户确认后的模型识别结果直接进入知识库，可一键删除并同步图谱。
- **移动业务知识图谱**：展示动作、业务对象、参数、约束和目标之间的关系。

批准候选后，状态从 `pending` 更新为 `active`，立即参与下一次规则匹配；启用 Neo4j 时同一次批准还会同步图节点和关系。

模型不可用时，本地规则只处理可以明确匹配的常见请求；无法确定动作时返回可解释错误，不会猜测并执行。
