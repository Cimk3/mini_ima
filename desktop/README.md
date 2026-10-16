# Mini-ima 桌面版

Windows x64 本地知识库应用。桌面界面使用 Tauri，Python/C++ 与现有 CLI 共用核心、SQLite 和模型配置。

## 使用

取得构建好的应用目录后，打开 `dist/Miniima`，双击 `Miniima.exe`。请保留同目录的 `miniima-backend.exe`，两者需要一起使用。运行时无需安装 Python、Node 或 Rust；需要系统 WebView2 Runtime。Git 仓库不包含打包产物，源码安装从[根目录说明](../README.md#从源码准备环境)开始。

默认打开用户目录下的 `.miniima`，也支持 `MINIIMA_HOME`。在 CLI 导入的文档可直接在桌面版使用，桌面版导入的数据也可通过原 `miniima.cmd` 搜索、问答。终端中临时设置的环境变量只会传给从该终端启动的应用；双击启动时使用系统环境变量。

1. 点击顶部齿轮进入“模型与设置”，填写 DeepSeek 和向量服务的 API Key。
2. 向量模型默认使用 Qwen3.7、百炼北京兼容接口和 1024 维，可修改地址及维度。其他服务的 Key 应填写对应服务地址。
3. 新输入的 Key 默认可见，点击眼睛图标可隐藏。留空保存保留已配置 Key。
4. 点击“保存并测试”验证真实 API 连接。
5. 新建知识库，导入 TXT / Markdown 文档，在“搜索”和“问答”中探索内容。点击文档、命中片段或引用按钮查看来源。

“刷新知识库”会重新读取 CLI 的修改。点击醒目的“新建对话”或顶部加号开始新会话；首次发送才保存，标题取第一个问题前 30 个字符。后续提问追加到同一对话，回答分别保存自己的原文引用。历史按最近更新时间排列，每次加载 50 条，可继续加载。

顶部支持同时打开多个对话窗口，点击标签切换，标签过多时可横向滚动。每个窗口分别保留草稿和联网搜索开关，重启后恢复打开的窗口。关闭标签只关闭视图，已保存的记录仍在左侧历史中；未发送的草稿随关闭标签丢弃。

每个对话绑定一个知识库。选择另一知识库会进入新的空白对话；点击历史时自动恢复相应知识库、完整消息与引用。应用重启恢复上次打开的有效对话，草稿及最近会话按数据目录分别记忆。CLI 单次 `ask` 保持原行为，成功记录也可从桌面历史打开。

桌面浅色外观采用淡紫色三栏工作台，深色外观采用 [GitHub Dark Default / Primer 配色](https://primer.style/product/getting-started/react/theme-reference/)：深灰背景、灰白文字、蓝色选中与聚焦状态。左上按钮可完全隐藏/展开侧栏并记住状态，历史和知识库列表独立滚动，“最近文档”为折叠分区。“笔记”和“标签”入口已移除。右上月亮切换深色，太阳切换浅色；保留文字提示、外观记忆和标题栏窗口操作。

右侧来源栏可从面板右上角收起，通过工作区顶栏的展开按钮恢复，并记住状态。点击引用也会重新打开来源。顶栏设置和主题按钮附近的装饰竖线已移除，“深度思考”入口已移除。

输入区的“联网搜索”为可用开关，默认关闭。开启后使用 Bing 公开 RSS 搜索入口，失败时尝试 [DuckDuckGo HTML 搜索](https://duckduckgo.com/duckduckgo-help-pages/features/non-javascript)，无需额外搜索 API Key；仅向搜索服务发送当前问题（最多前 1000 个字符），不会发送本地文档、历史对话或模型 Key。最多取 5 个网页摘要，优先作为本轮证据，并附带最多 2 个本地片段。它不读取网页全文。网页引用保存链接、摘要和检索时间，可在来源面板点击“打开网页”调用默认浏览器。

联网搜索需要当前网络可访问搜索服务。每个入口最多尝试一次，8 秒网络超时、响应上限 1 MB。公开搜索页面的格式与访问策略可能变化；两个入口均不可用时明确显示失败，问题保留，可稍后重试，不会把未取得的搜索结果伪装成联网回答。重试保留该问题原来的联网选项，历史网页引用无需联网也能查看。DeepSeek / Qwen 的真实 API 连通性仍通过设置页测试。

问答输入区固定在底部，长对话独立滚动。“添加文件”复用原导入流程。右侧可切换来源、详情和预览缩放；旧引用使用本地快照，即使原分块已不在也能查看。Markdown 不执行原始 HTML。多轮模型请求只带最近最多 8 轮、最多 4000 个估算 token 的完整成功问答，追问先改写为独立检索问题；完整历史保留在本地。

0.2 起，历史列表可按标题搜索全部有效记录，不受已加载 50 条的限制；铅笔按钮可重命名，同步到已打开标签并在重启后保留。上翻阅读时保持滚动位置，“回到最新”按钮恢复自动跟随。

发送前先保存问题。失败或上次退出中断的问题显示“重试问题”，重试使用原请求 ID，避免重复保存和调用；同一对话不能同时发送多个问题。切换会话后，迟到结果保存在原会话。窗口关闭时回收后台进程，任务进行中会提示退出确认。

## 版本检测与应用内更新（0.2 起）

设置中的“版本与更新”提供手动检测，启动后也会检查本仓库最新正式版。提示新版本时可以选择稍后；点击“下载并重启更新”并确认后，在应用内下载、显示进度、校验文件，随后退出、替换并自动重启。模型设置有未保存修改时先保存；正在处理任务时不能开始更新。

更新仅替换 `Miniima.exe`、`miniima-backend.exe` 和发布说明，保留数据目录与环境变量。文件替换或新程序启动失败时尝试恢复旧版，保留无法自动恢复的备份。应用目录须可写，网络须能访问 GitHub；检测失败可手动重试。开发预览允许检测，不替换开发环境。0.1 没有此入口，首次升级到 0.2 仍需手动解压新版。

发布者需提供 `Mini-ima-<版本>-windows-x64.zip`，包内恰好包含 `Miniima/` 下的上述三个文件。程序仅接受本仓库的正式版本、固定 GitHub 下载地址及 HTTPS 重定向，核对 GitHub Release Asset 的 SHA-256，并再次校验待替换文件。校验依赖 GitHub 元数据与 HTTPS，并非独立发行签名。检测和下载不使用模型 Key，也不上传文档、对话或 API 配置。

## 回收站与数据库升级

删除知识库或对话需要确认，之后进入“回收站”，可离线恢复。知识库删除时保留原文、向量和对话；恢复知识库会使其正常对话重新可见，此前单独删除的对话仍留在回收站。恢复所属知识库后才能恢复其中单独删除的对话。回收站中的知识库继续占用名称。

“彻底删除”和“清空回收站”有不可恢复的确认提示，程序不自动过期清理。只有彻底删除知识库时才清理对应原文和关联数据；文档暂不提供单独删除。

桌面启动与 CLI 数据命令自动将旧数据库升级到版本 3（新增每条问题的联网选项）；升级前通过 SQLite 备份接口将完整数据库保存到 `MINIIMA_HOME/backups/miniima-v<旧版本>-*.sqlite3`，包含 WAL 中已提交的数据。已有会话分别保留，不合并；恢复范围限于数据库中仍存在的记录。

CLI 示例（项目根目录）：

```powershell
.\miniima.cmd kb delete "知识库名称" --yes
.\miniima.cmd trash list
.\miniima.cmd trash restore kb <知识库UUID>
.\miniima.cmd trash restore conversation <对话UUID>
.\miniima.cmd trash purge conversation <对话UUID>
.\miniima.cmd trash empty
```

`kb delete` 保留原参数与确认方式，改为可恢复删除。`trash purge` / `trash empty` 默认要求确认，可用原有风格的 `--yes` / `-y` 跳过确认。

设置页的结果提示和保存按钮保持可见。弹窗支持 Tab 和 Esc，左侧工作区支持方向键切换。设计说明见 [DESIGN.md](DESIGN.md)，参考图对照见 [design-qa.md](design-qa.md)。

界面同时适配窄屏：手机尺寸下，左上角菜单展开知识库，来源通过独立面板阅读，设置表单采用单列。这里只提供 Windows 应用，响应式布局不等于手机安装包；开发预览使用 Mock 数据。

## 开发环境

需要 Node.js、Rust MSVC 工具链、Visual Studio C++ 编译工具，以及 Python 3.12。桌面 Python 环境独立于原 CLI `.venv`。

先按[根目录说明](../README.md#从源码准备环境)准备 CLI 的 `.venv`，再在项目根目录创建桌面环境并安装构建工具：

```powershell
.\.venv\Scripts\python.exe -m venv --without-pip desktop\.venv
.\.venv\Scripts\python.exe -m pip --python desktop\.venv\Scripts\python.exe install pip pyinstaller pytest scikit-build-core pybind11 cmake ninja
cd desktop
npm.cmd ci
npm.cmd run desktop:dev
```

`desktop:dev` 先构建共享核心 wheel 和后台程序，再打开 Tauri 开发窗口。发布版界面资源包含在应用中，不需要运行开发服务器。

```powershell
npm.cmd run desktop:build
```

完整构建产物位于 `desktop/dist/Miniima`，并生成带版本号的 ZIP。发布目录每次重新组装，仅含两个程序和由 `RELEASE_README.md` 生成的说明；说明链接指向该版本的 GitHub 文档。构建脚本安装匹配当前版本的核心 wheel，以便将 C++ 扩展、迁移 SQL、模型客户端和运行组件完整打包。核心 wheel 的 CMake 中间产物也保存在 `desktop/build/core`，不会重建 CLI 的虚拟环境。

后台注册为 Tauri 的 `externalBin`，由 Rust 管理启动、请求匹配和完整进程树回收。架构参考：[Tauri 官方 sidecar 说明](https://v2.tauri.app/develop/sidecar/)。

## 测试

```powershell
npm.cmd test
cargo test --manifest-path src-tauri/Cargo.toml
.\.venv\Scripts\python.exe -m pytest backend/tests -q --basetemp=build/pytest-desktop
```

Python 与界面自动化测试使用 Mock API，避免依赖真实密钥。开发时的 `http://127.0.0.1:1430/?preview=1` 仅用于界面预览，Mock 数据保存于浏览器本地存储，和正式 SQLite 数据无关；发布版不会启用该模式。

冻结后台与 CLI 的自动互通验收（本地 Mock API）：

```powershell
.\.venv\Scripts\python.exe scripts/smoke.py
```

原生窗口验收可运行 `scripts/smoke.py --gui --reopen --chat-delay 12`。它创建独立的 `build/gui-smoke-*` 数据目录，使用测试 Key 和本地 Mock 服务，关闭第一轮窗口后会自动重新打开以检查持久化，不修改日常知识库。

CLI 仍从项目根目录通过 `miniima.cmd` 使用。完整验证结果见 [验收记录](VERIFICATION.md)。
