# Mini-ima CLI

本地优先的文档知识库原型，已实现任务书的阶段一和阶段二：TXT/Markdown 导入、结构分块、SQLite 持久化、Embedding API、语义搜索、带来源引用的 RAG 问答，以及默认启用的 C++20 精确检索引擎。

桌面版在独立的 `desktop` 目录，Windows 启动程序为 `desktop/dist/Miniima/Miniima.exe`，使用说明见 [desktop/README.md](desktop/README.md)。桌面版与 CLI 共用数据和配置，原有命令继续可用。

## 在当前 Windows 工作区运行

项目的 `.venv` 已配置 Python 3.12 和依赖，直接在项目目录执行：

```powershell
.\miniima.cmd --help
.\miniima.cmd init
.\miniima.cmd config set --api-key
.\miniima.cmd config test --chat
```

`--api-key` 交互输入默认显示字符，不接受直接跟在命令后的 Key 参数。需要隐藏时加 `--hide-key`。`config test` 会实际调用配置的模型；缺少密钥或调用失败时返回非零退出码。自动化验证使用 Mock，不代表真实 API 连通。

默认 Chat API 为 `https://api.deepseek.com`，模型为 `deepseek-flash`，依据 [DeepSeek 官方快速开始](https://api-docs.deepseek.com/) 的当前模型名称。可按账号实际可用模型更改：

```powershell
.\miniima.cmd config set --base-url "https://api.deepseek.com" --chat-model "deepseek-flash"
.\miniima.cmd config show
```

当前 DeepSeek Flash / V4 模型的问答请求显式关闭 thinking，避免思考过程占满回答预算；参见[官方模式说明](https://api-docs.deepseek.com/guides/thinking_mode/)。其他兼容服务不会收到这个专用参数。

## 配置 Qwen3.7 向量 API

**DeepSeek 负责问答，`qwen3.7-text-embedding` 负责向量。** 一条命令自动设置模型、地址、维度和批次大小，只需输入向量服务的 API Key，并测试连接：

```powershell
.\miniima.cmd config qwen --test
```

Key 输入时默认可见；输入完成后不会再打印完整 Key，`config show` 继续隐藏。需要重新测试时使用：

```powershell
.\miniima.cmd config test --embedding
.\miniima.cmd config test --chat --embedding
```

封装默认使用百炼北京公共兼容地址 `https://dashscope.aliyuncs.com/compatible-mode/v1`，显式请求 1024 维，批次上限 20。模型规格见[官方同步向量接口文档](https://help.aliyun.com/zh/model-studio/text-embedding-synchronous-api)。百炼目前推荐业务空间专属域名，公共域名的迁移说明见[官方兼容接口文档](https://help.aliyun.com/zh/model-studio/embedding-interfaces-compatible-with-openai/)。

如果你的 Key 来自千问 AI 平台，使用该平台[官方提供的地址](https://platform.qianwenai.com/docs/developer-guides/embeddings/embedding)：

```powershell
.\miniima.cmd config qwen --base-url "https://maas.qianwenaiapi.com/compatible-mode/v1" --test
```

其他地域、业务空间专属域名或兼容服务也可通过 `--base-url` 指定。地址必须与 Key 所属服务相匹配，程序不会自动在不同服务之间尝试密钥。

可通过 `--dimension` 指定模型支持的 256、512、768、1024、1536、2048、2560 维之一；更改已有知识库的模型或维度后，应新建知识库重新导入：

```powershell
.\miniima.cmd config qwen --dimension 2560 --test
```

原来的 `config set --embedding-api-key` 命令也可使用：在旧配置尚未填写向量模型时，它会自动补齐 Qwen 默认设置。手工配置其他模型的 `--embedding-base-url`、`--embedding-model`、`--embedding-dimension` 参数仍受支持。Chat 与 Embedding 地址不同时，必须独立输入向量 Key，程序不会自动把 DeepSeek Key 发给其他服务。

## 导入、搜索和问答

```powershell
.\miniima.cmd kb create "计算机网络"
.\miniima.cmd kb list
.\miniima.cmd add .\examples\network.md --kb "计算机网络"
.\miniima.cmd docs --kb "计算机网络"
.\miniima.cmd search "TCP 三次握手" --kb "计算机网络" --top-k 5
.\miniima.cmd ask "TCP 为什么需要三次握手？" --kb "计算机网络"
.\miniima.cmd doctor
```

命令完成后可以关闭终端，再次执行 `search` / `ask`。所有文档、Chunk、float32 向量和问答记录均保存在 SQLite；每次搜索从数据库重建内存索引。来源显示原始文件名、行号、Markdown 标题路径和文档 UUID。文档在同一知识库内按 SHA-256 去重；不同知识库可导入相同文件。

知识库绑定向量服务地址、模型和维度。更改这些配置后，旧知识库会拒绝不兼容的导入和查询；恢复旧配置即可继续使用，或创建新知识库重新导入。修改 Chat 模型不影响已有向量。

删除知识库会要求确认并移入回收站，`--yes` 可跳过交互。原文、向量和对话保留，可恢复：

```powershell
.\miniima.cmd kb delete "计算机网络"
.\miniima.cmd trash list
.\miniima.cmd trash restore kb <知识库UUID>
.\miniima.cmd trash restore conversation <对话UUID>
.\miniima.cmd trash purge kb <知识库UUID>
.\miniima.cmd trash empty
```

## 数据与配置

默认数据目录为用户目录下的 `.miniima`，包含 `config.json`、`miniima.sqlite3` 和 `originals/`。升级到数据库版本 2 前，SQLite 完整备份保存在 `backups/`。可在初始化前设置独立目录：

```powershell
$env:MINIIMA_HOME = "D:\MiniimaData"
.\miniima.cmd init
```

环境变量优先于配置文件，支持任务书中的 `MINIIMA_API_KEY`、`MINIIMA_BASE_URL`、`MINIIMA_CHAT_MODEL`、`MINIIMA_EMBEDDING_MODEL`、`MINIIMA_EMBEDDING_DIMENSION`，以及独立的 `MINIIMA_EMBEDDING_API_KEY`、`MINIIMA_EMBEDDING_BASE_URL`。完整模板见 [.env.example](.env.example)。`.env` 不会自动加载，请通过环境变量或 `config set` 配置。

`config show` 始终隐藏 Key；`config set` 修改本地文件，环境变量仍有更高优先级。通过 CLI 输入的密钥保存在本机 `config.json`，也可仅使用环境变量避免落盘。请勿分享配置目录；Git 忽略规则排除了环境文件、数据库和本地数据目录。

默认分块约 500 个估算 tokens、重叠 80，优先在标题、段落和句子边界拆分。Token 估算采用 CJK 字符及四个 ASCII 字符片段，不是特定模型的精确 tokenizer。可调节：

```powershell
.\miniima.cmd config set --chunk-tokens 500 --chunk-overlap 80 --timeout 30 --max-retries 2
.\miniima.cmd config set --min-score 0.2
```

问答只使用达到 `min-score` 的资料。阈值需要按实际向量模型调节；证据不足时明确提示。参考资料作为不可信 JSON 数据传入，引用编号必须对应本轮真实 Chunk，否则回答不被采用。问答记录保留来源正文快照；这不等同于对模型每项结论进行事实验证。

## 从源码安装

需要 Python 3.12+ 和 C++20 编译器。Windows 推荐安装 Visual Studio 2022 的“使用 C++ 的桌面开发”组件及 Windows SDK。CMake / pybind11 由构建系统提供；不需要 Docker 或常驻服务器。

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
$env:CMAKE_GENERATOR = "Visual Studio 17 2022"
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\miniima.exe --help
```

如使用本项目当前已准备好的虚拟环境，修改 C++ 后可以离线重建：

```powershell
$env:CMAKE_GENERATOR = "Visual Studio 17 2022"
.\.venv\Scripts\python.exe -m pip install --no-build-isolation --no-deps -e .
```

NumPy 基准实现保留用于对照或显式切换：

```powershell
.\miniima.cmd search "TCP" --kb "计算机网络" --engine numpy
.\miniima.cmd config set --engine cpp
```

C++ 扩展缺失时会报错，不会自动更换检索引擎。

## 自动化测试

Python 测试使用 Mock Provider 和 HTTP MockTransport，不需要 API Key，覆盖多进程 CLI 重启、数据库事务、模型绑定、去重、错误恢复、RAG 引用、SDK 请求路由，以及固定随机种子的 C++ / NumPy 对照。临时测试数据放在专用构建目录：

```powershell
New-Item -ItemType Directory -Force .\build | Out-Null
.\.venv\Scripts\python.exe -m pytest -q --basetemp=build/pytest-local
```

CTest 可独立验证 C++ 引擎：

```powershell
.\.venv\Scripts\cmake.exe -S . -B build/cpp-tests -G "Visual Studio 17 2022" -DMINIIMA_BUILD_PYTHON=OFF -DBUILD_TESTING=ON
.\.venv\Scripts\cmake.exe --build build/cpp-tests --config Release
.\.venv\Scripts\ctest.exe --test-dir build/cpp-tests -C Release --output-on-failure
```

当前桌面、多轮对话与回收站验收见 [desktop/VERIFICATION.md](desktop/VERIFICATION.md)；阶段一、二的早期核心验收保留在 [docs/verification.md](docs/verification.md)，实现结构见 [docs/architecture.md](docs/architecture.md)。

## 后续阶段

桌面版已支持持久多轮对话、历史恢复与知识库/对话回收站；CLI `ask` 仍为单次问答，成功记录可在桌面查看。PDF / DOCX / PPTX / XLSX / CSV 解析、单文档删除、统计、流式输出和完整性能 Benchmark 尚未实现。当前仅支持 TXT / MD / Markdown 文本，不支持 OCR、Agent 或云同步。
