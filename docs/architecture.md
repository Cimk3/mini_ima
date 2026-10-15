# 阶段一、二实现结构

## 分层

| 目录 | 职责 |
| --- | --- |
| `src/miniima/cli` | Typer 参数、确认操作、Rich 展示、用户错误 |
| `src/miniima/application` | 文档导入、检索、问答业务，独立于 CLI |
| `src/miniima/documents` | TXT/Markdown 解析、标题及行号元数据、分块 |
| `src/miniima/providers` | OpenAI SDK，独立 Chat / Embedding 地址和密钥 |
| `src/miniima/storage` | 全部 SQL、事务、持久化和迁移 |
| `src/miniima/vector` | C++ 工厂与 NumPy 基准 |
| `src/miniima/rag` | 证据预算、不可信资料 Prompt、引用编号验证 |
| `cpp` | C++20 连续向量存储、余弦 Top-K、小顶堆、pybind11、CTest |

## 数据与迁移

SQLite 是权威数据源，启用 WAL 和外键。七张业务表为 `knowledge_bases`、`documents`、`chunks`、`embeddings`、`conversations`、`messages`、`message_citations`；另有 `schema_migrations` 记录迁移。Chunk 使用 INTEGER 检索 ID 并保留 UUID，其他业务实体使用 UUID。

SQL 迁移位于 `src/miniima/storage/migrations/NNN_description.sql`，随 Python 包分发。桌面启动、`init` 与 CLI 数据访问检查迁移，在 `BEGIN IMMEDIATE` 事务内按顺序应用，记录 `PRAGMA user_version`，拒绝更高版本数据库。版本 2 增加知识库/会话软删除时间、会话标题、消息顺序与请求状态。旧库升级前使用 SQLite backup 接口保存包含 WAL 已提交数据的完整备份，重复初始化保留现有数据。

版本 3 为问题增加 `web_search` 标记，失败重试保留原检索方式。开启联网时，后台通过独立的无凭据 HTTP 请求访问 Bing RSS（备用 DuckDuckGo HTML），只发送当前问题，不传本地资料或历史；网页摘要作为不可信证据参与本轮引用校验。网页引用沿用原有引用快照表，`chunk_id` 为空，链接、检索时间及搜索服务保存在 `source_metadata`，无需关联本地分块。`web.open` IPC 仅允许 HTTP / HTTPS，交由系统默认浏览器打开。

多个对话窗口及各窗口草稿保存在按数据目录隔离的工作区偏好中；SQLite 继续保存对话实体。关闭标签不删除已保存会话。异步发送记录原窗口 key，返回时只更新相应窗口，避免覆盖同知识库下另一个空白对话。

Embedding BLOB 使用小端 float32，保存模型和维度。知识库还绑定服务地址，防止同名模型来自不同服务时被意外混用。所有有效检索行通过当前知识库及 `ready` 文档过滤。

## 导入与恢复

导入先复制文档到临时快照，同时计算 SHA-256，解析与哈希使用相同字节。准备好全部 Chunk 和有效向量后移动原文，最后在一个 SQLite 事务中保存文档、Chunk 和向量。API 或解析失败只记录失败状态，删除临时原文，不损坏已有就绪文档；同内容重试可以继续处理。

原文移动与数据库提交无法跨文件系统做原子事务。进程在移动原文后突然终止，可能留下未被数据库引用的原文；它不会进入检索，重试可重新导入。当前阶段没有清理孤立文件的维护命令。

## ExactIndex 契约

`ExactIndex(dimension)` 提供 `add(ids, vectors)`、`rebuild(ids, vectors)`、`search(query, k)`、`clear()`、`size()`。矩阵形状必须为 `(n, dimension)`，query 必须为一维。输入转换为连续 float32；ID 为正 int64，必须唯一。

输入按 L2 归一化，余弦点积使用 double 累加以减少误差。Top-K 用小顶堆；输出按得分降序、同分 Chunk ID 升序排序。`k=0` 返回空，`k>size` 返回全部，负 k、零向量、NaN/Inf 和维度错误会被拒绝。非法 add/rebuild 保持原索引。Python 绑定保留 GIL，当前不暴露并发修改能力。

## API 与 RAG

OpenAI SDK 提供超时和有限指数退避，`max_retries` 最大为 5。Embedding 分批请求，校验数量、索引、维度、零向量及有限值。服务错误只显示状态和分类，避免错误响应回显密钥或正文。

`config qwen` 预设 `qwen3.7-text-embedding`、百炼北京公共兼容地址、1024 维和最多 20 条的批次，独立保存向量 API Key。可显式覆盖地址和模型支持的维度；SDK 对此模型发送 `dimensions` 参数，并在旧配置批次过大时仍限制为 20。其他模型保留原请求参数。API Key 交互输入默认可见，`--hide-key` 可隐藏，配置展示和服务错误不会输出完整密钥。

本轮资料及来源以 JSON 数据放入 user 消息，system 消息明确它们不可信。问答上下文有估算 token 预算和可调相似度阈值。生成完成后校验引用编号，只保存真实引用的来源正文快照；无效编号或缺失必要引用时拒绝采用回答。CLI `ask` 保持单次行为；桌面通过 `ConversationService` 支持多轮。

## 持久对话与回收站

用户问题先以稳定 `request_id` 和 `pending` 状态提交；SQLite 唯一索引保证请求去重及同会话单次发送。回答完成时在一个事务中保存助手消息、本轮引用快照并更新用户状态；失败保留问题供重试。重试复用原用户消息和预留的回答顺序。进程 PID 随待处理问题保存，重启后只将已退出进程的任务标记为 `interrupted`，避免打断其他仍在运行的桌面后台。

完整历史保存在 SQLite；发送模型的成功问答历史限制为最近 8 轮和 4000 个估算 token，不截断成半轮。追问先结合这段上下文改写为独立检索问题，再检索会话绑定知识库；模型回答只引用本轮证据。旧答案中的引用编号不会作为下轮证据传递。历史引用直接使用 `message_citations.id` 和正文快照，兼容 `chunk_id` 已为空的情况。

知识库和会话正常查询都过滤软删除状态。删除知识库不修改子会话的独立删除时间，因此恢复父库后正常会话出现，单独删除的会话仍在回收站。只有 `TrashService.purge` 永久删除知识库时执行经 UUID、路径和链接检查的原文清理与数据库级联删除；失败保留数据库记录并返回错误。

Rust 白名单开放对话和回收站私有 IPC。Python JSONL 后台将发送任务放入线程池，离线历史与回收站读取可在生成期间响应；Rust 按请求 ID 匹配乱序响应。React 用视图版本和会话 ID 防止迟到结果覆盖其他会话，并按数据目录保存草稿、发件记录及上次打开的会话。运行时仍由 Tauri 和 Windows Job Object 回收后台进程树。
