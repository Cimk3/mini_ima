# 验证记录

日期：2026-10-12。验证环境：Windows x64、Python 3.12.14。

## 阶段一

命令：`.venv\Scripts\python.exe -m pytest -q --tb=short --basetemp=build/pytest-phase1`

结果：**33 passed**，14.64 秒。

覆盖 TXT/Markdown、编码和空文档、分块大小与重叠、SQLite WAL 与外键、重复初始化、事务回滚、去重、知识库隔离、模型绑定、失败重试、RAG 来源及问答保存、密钥隐藏、SDK 路由与有限重试、NumPy 边界。

导入与重启验收使用五个独立 CLI 进程依次执行 init、kb create、add、search、ask，并使用 Mock Provider；重启后成功从数据库重建检索资料并展示来源。

## 阶段二

使用 scikit-build-core / CMake / pybind11 成功构建并安装 Windows x64 Python 3.12 扩展。编译器：Visual Studio 2022、MSVC 19.44.35209.0；构建工具：CMake 4.4.4。

命令：`.venv\Scripts\python.exe -m pytest -q --tb=short --basetemp=build/pytest-phase2`

结果：**56 passed**，22.24 秒。C++ 与 NumPy 使用固定种子，在 2 / 8 / 32 / 768 维数据上核对 Top-K ID 和相似度；包含空索引、同分截断、非连续 NumPy 输入、零向量、NaN/Inf、维度错误、非法 ID、负 K 和失败重建的原子性。独立进程 CLI 持久化验收分别在两种引擎上通过。

CTest：`cmake -S . -B build/cpp-tests -G "Visual Studio 17 2022" -DMINIIMA_BUILD_PYTHON=OFF -DBUILD_TESTING=ON`，随后执行 Release 构建和 `ctest --test-dir build/cpp-tests -C Release --output-on-failure`。

结果：**1/1 passed**，覆盖核心 C++ 边界和大数值向量。

收尾测试：`.venv\Scripts\python.exe -m pytest -q --tb=short --basetemp=build/pytest-final`。

结果：**59 passed**，23.90 秒。新增校验覆盖 DeepSeek 非 thinking 请求参数、其他服务不接收专用参数，以及拒绝空回答和被截断的回答。

普通 wheel 构建：`python -m pip wheel --no-build-isolation --no-deps . --wheel-dir dist`。产物为 `dist/miniima-0.1.0-cp312-cp312-win_amd64.whl`，包含 `.pyd` 扩展及 `001_initial.sql`，不包含配置密钥或用户数据。

wheel 单独安装至 `build/wheel-install` 后，使用 `python -S` 避开 editable 安装的路径注入，确认导入来自安装包，成功执行 CLI init、SQLite 完整性检查以及 C++ 同分 Top-K 检索。结果：**PASS**。

## Qwen3.7 接口与可见输入更新

按用户要求新增 `config qwen --test`：预设模型、百炼北京公共兼容地址、1024 维和最多 20 条批次，只需交互输入向量 API Key。Key 输入默认可见，`--hide-key` 可隐藏，`config show` 仍遮蔽完整密钥。原先未填写向量模型的配置也可通过 `config set --embedding-api-key` 自动补齐预设。

相关测试：`python -m pytest -q tests/test_qwen.py tests/test_cli_config.py tests/test_provider.py --tb=short --basetemp=build/pytest-qwen`，结果 **29 passed**，24.23 秒。

完整回归：`python -m pytest -q --tb=short --basetemp=build/pytest-qwen-full`，结果 **74 passed**，26.53 秒。覆盖可见及隐藏输入、保存与展示、Chat 配置保留、旧配置补全、连接测试入口、环境变量覆盖、空 Key、SDK 路由、显式维度、批次限制与不支持维度的拒绝。

Windows wheel 已重新构建，并检查包含 Qwen 预设、可见输入和 `dimensions` 请求逻辑。真实 Qwen API Key 尚未输入，Qwen 请求和连接测试入口均通过 Mock 验证，未调用实际向量服务。

## API 验证范围

未提供真实 API Key，未声称真实 DeepSeek 或向量服务连接成功。SDK 通过 `httpx.MockTransport` 验证请求路径、独立密钥、批次顺序、错误分类、向量校验和重试次数。用户可通过 `miniima config test --chat --embedding` 自行进行真实服务测试。
