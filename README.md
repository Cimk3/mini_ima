# Mini-ima

Mini-ima 是一个本地优先的个人知识管理工具：把 TXT 和 Markdown 文档整理成知识库，通过语义搜索找到资料，再围绕资料进行带来源引用的问答。

项目同时提供 **Windows 桌面应用**和 **CLI 命令行**，两者共用 Python/C++ 核心、SQLite 数据和模型配置。桌面端使用 Tauri 2、React、TypeScript 和 Vite，默认检索引擎为 C++20 精确向量检索。

## 功能

| 功能 | 说明 |
| --- | --- |
| 知识库管理 | 创建多个知识库，导入 TXT、MD、Markdown 文件，同一知识库内自动跳过重复文件。 |
| 语义搜索 | 按文档含义检索，展示匹配片段、文件名、标题路径和行号。 |
| 带引用问答 | 从知识库检索证据，校验本轮引用，保存回答及引用片段快照。 |
| 持久多轮对话 | 新建对话、连续追问、查看历史、失败重试，重启后恢复已保存消息。 |
| 多对话窗口 | 顶部标签切换不同对话，各自保留草稿和联网搜索开关，恢复上次打开的窗口。 |
| 联网搜索 | 可选的网页摘要检索，无需额外搜索 Key，回答中保留网页链接和摘要。 |
| 回收站 | 知识库和对话可恢复删除，支持恢复、彻底删除和清空，与 CLI 互通。 |
| 桌面工作区 | 左右侧栏可收起，支持窄窗口布局、浅色主题和 GitHub 深色配色。 |
| 模型设置 | 问答和向量服务分别设置地址、模型及 API Key，并分别测试连接。 |

桌面端支持多轮对话；CLI 的 `ask` 保持单次问答，其成功记录也能在桌面历史中查看。每个对话绑定一个知识库，切换知识库会进入新的空白对话。

## 获取与运行

本仓库提供源码，**不包含虚拟环境、依赖、打包程序或个人数据**。首次克隆后，需要按下方步骤安装和构建；`desktop/dist/Miniima/` 是本地构建后的产物目录。

如果已有构建好的应用目录，保留以下两个程序在同一目录，双击 `Miniima.exe` 即可运行：

```text
Miniima/
├── Miniima.exe
├── miniima-backend.exe
└── README.md
```

打包版面向 Windows x64，运行时需要系统安装 WebView2 Runtime，无需另装 Python、Node.js 或 Rust。首次启动会引导填写模型配置；连接测试会发起真实 API 请求。

### 从源码准备环境

Windows 开发环境需要：

- Git、Python 3.12。
- Visual Studio 2022 的“使用 C++ 的桌面开发”组件及 Windows SDK，用于编译 C++ 扩展。
- 开发桌面版还需要 Node.js 20.19+、npm、Rust 的 MSVC 工具链和 WebView2 Runtime。

以下命令均在 PowerShell 中执行：

```powershell
git clone https://github.com/Cimk3/mini_ima.git
cd mini_ima

py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
$env:CMAKE_GENERATOR = "Visual Studio 17 2022"
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"

.\miniima.cmd --help
.\miniima.cmd init
```

`init` 可以在尚未填写 Key 时完成初始化。`miniima.cmd` 使用项目根目录的 `.venv`，因此无需手动激活虚拟环境；也可使用 `.\.venv\Scripts\miniima.exe`。

### 启动桌面开发版

完成上面的环境准备后，在项目根目录创建独立的桌面 Python 环境：

```powershell
.\.venv\Scripts\python.exe -m venv --without-pip desktop\.venv
.\.venv\Scripts\python.exe -m pip --python desktop\.venv\Scripts\python.exe install pip pyinstaller pytest scikit-build-core pybind11 cmake ninja

cd desktop
npm.cmd ci
npm.cmd run desktop:dev
```

`desktop:dev` 会构建共享核心和后台程序，再启动真正的 Tauri 桌面窗口。首次运行需要下载依赖并编译；桌面构建不会修改 CLI 的虚拟环境。

在 `desktop` 目录执行完整打包：

```powershell
npm.cmd run desktop:build
```

完成后打开 `desktop/dist/Miniima/Miniima.exe`。发布版界面资源随应用打包，无需启动网页服务器。更多开发、打包和验收说明见 [桌面版说明](desktop/README.md)。

## 桌面版使用

1. 打开“模型与设置”，分别填写问答服务和向量服务的 Key，核对服务地址、模型和维度，保存并测试。
2. 新建知识库，使用原生文件选择框导入 TXT 或 Markdown，等待处理完成；批量导入会显示进度、重复跳过和失败原因。
3. 在“全局搜索”中检索资料，或点击“新建对话”围绕当前知识库提问。
4. 点击回答的来源引用，在右侧查看原文片段和位置；网页来源可以在默认浏览器中打开。
5. 从左侧历史恢复对话，使用顶部加号打开另一个对话窗口。关闭标签只关闭视图，已保存的对话仍保留在历史中。
6. 需要网页资料时开启输入区的“联网搜索”；不用时保持关闭。通过刷新入口读取 CLI 刚导入的数据。

新输入的 API Key 默认可见，可通过眼睛按钮隐藏；已有 Key 只显示配置状态，留空保存会保留原值。删除知识库或对话会移入回收站，彻底删除和清空会再次要求确认。

## 模型与 API 配置

项目提供以下预设，实际可用模型与地址以你的服务账号为准：

| 用途 | 项目预设 |
| --- | --- |
| 问答 | DeepSeek，地址 `https://api.deepseek.com`，模型 `deepseek-flash`。 |
| 向量 | `qwen3.7-text-embedding`，地址 `https://dashscope.aliyuncs.com/compatible-mode/v1`，1024 维，批次上限 20。 |

问答和向量通常使用不同的 Key。项目支持 OpenAI 兼容接口，可以在桌面设置或 CLI 中修改地址、模型和向量维度。地址必须与 Key 所属服务匹配。

在项目根目录通过 CLI 交互输入并测试：

```powershell
# 输入问答 Key，然后测试问答接口
.\miniima.cmd config set --api-key
.\miniima.cmd config test --chat

# 应用 Qwen 向量预设，输入独立的向量 Key，然后测试
.\miniima.cmd config qwen --test

# 查看配置（Key 会被隐藏），或重新测试两个接口
.\miniima.cmd config show
.\miniima.cmd config test --chat --embedding
```

`--api-key` 用于交互输入，不要把 Key 直接写在命令后面。输入默认可见，需要隐藏时使用 `config set --api-key --hide-key` 或 `config qwen --hide-key --test`。测试失败会显示原因并返回非零退出码。

修改问答模型示例：

```powershell
.\miniima.cmd config set --base-url "https://api.deepseek.com" --chat-model "deepseek-flash"
.\miniima.cmd config set --help
.\miniima.cmd config qwen --help
```

知识库会绑定向量服务地址、模型和维度；改变这些配置后，旧知识库会拒绝不兼容的导入和查询。可以恢复原配置，或创建新知识库重新导入。修改问答模型不影响已有向量。

## CLI 使用

以下示例使用仓库自带的 [网络知识示例文档](examples/network.md)，运行前需完成向量和问答配置：

```powershell
.\miniima.cmd kb create "计算机网络"
.\miniima.cmd kb list
.\miniima.cmd add .\examples\network.md --kb "计算机网络"
.\miniima.cmd docs --kb "计算机网络"
.\miniima.cmd search "TCP 三次握手" --kb "计算机网络" --top-k 5
.\miniima.cmd ask "TCP 为什么需要三次握手？" --kb "计算机网络"
.\miniima.cmd doctor
```

`doctor` 检查本地数据库、检索引擎和配置完整性，不会测试真实 API 连通性。Key 未配置时会提示缺失，使用 `config test` 才会调用模型。

知识库与回收站操作：

```powershell
.\miniima.cmd kb delete "计算机网络"
.\miniima.cmd trash list
```

从回收站列表取得对应 UUID，再恢复或彻底删除。下方变量请替换为实际 ID；`kind` 支持 `kb` 和 `conversation`：

```powershell
$kbId = "替换为知识库UUID"
$conversationId = "替换为对话UUID"
.\miniima.cmd trash restore kb $kbId
.\miniima.cmd trash restore conversation $conversationId
.\miniima.cmd trash purge conversation $conversationId
.\miniima.cmd trash empty
```

彻底删除和清空默认要求确认，`--yes` / `-y` 可跳过确认。删除知识库会保留原文、向量和对话；所属知识库已删除时，先恢复知识库。回收站中的知识库仍占用原名称。

默认使用 C++ 检索，也可以显式选择 NumPy 对照实现：

```powershell
.\miniima.cmd search "TCP" --kb "计算机网络" --engine numpy
```

C++ 扩展缺失时会报错，不会静默切换引擎。

## 数据与隐私

桌面版和 CLI 默认共用用户目录下的 `.miniima`，其中包含：

- `config.json`：模型配置和本地保存的 API Key。
- `miniima.sqlite3`：知识库、文档分块、向量、消息和引用快照。
- `originals/`：导入文档的原始副本。
- `backups/`：数据库迁移前通过 SQLite 备份接口生成的完整备份。

也可以在启动前设置独立目录；桌面与 CLI 使用相同的 `MINIIMA_HOME` 才会看到同一份数据：

```powershell
$env:MINIIMA_HOME = Join-Path $env:LOCALAPPDATA "MiniimaData"
.\miniima.cmd init
```

在终端临时设置的变量只传给从该终端启动的应用；双击启动使用系统环境变量。环境变量优先于配置文件，支持的变量见 [.env.example](.env.example)。项目不会自动加载 `.env`。

数据保存在本机，但模型调用需要联网：导入和语义检索会向配置的向量服务发送文本，问答会向配置的问答服务发送问题、检索片段和有限的对话上下文。启用联网搜索时，当前问题的前 1000 个字符会发送给 Bing 或备用 DuckDuckGo 搜索入口；不会向搜索服务发送本地文档、历史对话或模型 Key。该功能使用网页摘要，不读取网页全文；搜索失败时会明确提示。

通过界面或 CLI 保存的 Key 以明文保存在本机 `config.json`，请勿分享数据目录；也可以只通过环境变量提供 Key。仓库忽略了 API 配置、环境文件、个人数据库、原文、备份和构建产物，`.env.example` 中的 Key 留空。备份数据时需要同时保护配置和文档内容。

## 开发与测试

Python 与前端自动化测试使用 Mock API，不需要真实 Key，不代表 DeepSeek 或 Qwen 的真实连接已经通过。真实连接请使用设置页测试按钮或 `config test` 验证。

在项目根目录运行核心测试：

```powershell
.\.venv\Scripts\python.exe -m pytest -q --basetemp=build/pytest-local
```

在 `desktop` 目录运行桌面测试：

```powershell
npm.cmd test
cargo test --manifest-path src-tauri/Cargo.toml
.\.venv\Scripts\python.exe -m pytest backend/tests -q --basetemp=build/pytest-desktop
```

代码与文档入口：

| 路径 | 内容 |
| --- | --- |
| `src/miniima/` | Python 业务核心、CLI、模型适配、SQLite 存储与增量迁移。 |
| `cpp/` | C++20 精确检索引擎、Python 绑定与 C++ 测试。 |
| `desktop/` | React 界面、Tauri 宿主、Python IPC 后台和打包脚本。 |
| [桌面版说明](desktop/README.md) | 交互说明、开发和打包流程。 |
| [桌面验收记录](desktop/VERIFICATION.md) | 功能验证及真实调用与 Mock 的边界。 |
| [核心架构](docs/architecture.md) | 核心模块和数据结构说明。 |
| [早期核心验收](docs/verification.md) | CLI 与检索引擎的阶段验收。 |

## 当前范围

当前支持 TXT / MD / Markdown。PDF、Office 文档、CSV、OCR、单文档删除、流式回答、云同步及完整性能 Benchmark 尚未实现。窄屏适配用于窗口布局，当前交付平台仍为 Windows x64，未提供手机安装包。

引用校验用于确保来源对应本轮资料，不等同于对模型每项结论进行事实验证；资料不足时仍需结合原文判断。
