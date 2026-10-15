from __future__ import annotations

import functools
import sqlite3
from dataclasses import asdict, replace
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table
from rich.text import Text

from miniima import __version__
from miniima.config import (QWEN_EMBEDDING_BASE_URL, QWEN_EMBEDDING_DIMENSION,
                           data_home, load_settings, qwen_settings, save_settings)
from miniima.errors import ConfigurationError, MiniimaError
from miniima.storage.repository import Repository

app = typer.Typer(help="Mini-ima 本地知识库 · 阶段一、二 CLI", no_args_is_help=True, add_completion=False,
                  pretty_exceptions_enable=False)
kb_app = typer.Typer(help="管理知识库", no_args_is_help=True)
config_app = typer.Typer(help="配置 API 并测试连接", no_args_is_help=True)
trash_app = typer.Typer(help='恢复或彻底删除知识库和对话', no_args_is_help=True)
app.add_typer(kb_app, name="kb")
app.add_typer(config_app, name="config")
app.add_typer(trash_app, name='trash')
console = Console()


def handled(function):
    @functools.wraps(function)
    def wrapped(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except MiniimaError as exc:
            console.print(Text(f"错误：{exc}", style="red"))
            raise typer.Exit(1) from None
        except (OSError, sqlite3.Error, ValueError) as exc:
            # Exception bodies from the network, filesystem, or documents may contain secrets.
            console.print(Text(f"操作失败（{type(exc).__name__}），请检查文件权限、配置及数据完整性。", style="red"))
            raise typer.Exit(1) from None
    return wrapped


def service():
    from miniima.application.service import KnowledgeService
    return KnowledgeService(Repository(data_home()), load_settings())


def prompt_api_key(label: str, *, hide_key: bool = False) -> str:
    key = typer.prompt(label, hide_input=hide_key).strip()
    if not key:
        raise ConfigurationError("API Key 不能为空。")
    return key


def source_location(item: dict) -> str:
    metadata = item["source_metadata"]
    location = f"行 {metadata['line_start']}–{metadata['line_end']}"
    headings = metadata.get("heading_path", [])
    return location + (" · " + " / ".join(headings) if headings else "")


@app.callback()
def callback(version: Annotated[bool, typer.Option("--version", help="显示版本", is_eager=True)] = False):
    if version:
        console.print(__version__)
        raise typer.Exit()


@app.command()
@handled
def init():
    """初始化数据目录、配置模板和 SQLite，可重复执行。"""
    repository = Repository(data_home())
    repository.initialize()
    console.print(Text(f"初始化完成：{repository.home}"))


@config_app.command("show")
@handled
def config_show():
    """显示当前有效配置，密钥只显示是否已配置。"""
    settings = load_settings()
    table = Table("配置项", "当前值")
    for name, value in asdict(settings).items():
        if name.endswith("api_key"):
            value = "已配置（隐藏）" if value else "未配置"
        table.add_row(name, Text(str(value)))
    console.print(Text(f"数据目录：{data_home()}（环境变量优先于 config.json）"))
    console.print(table)


@config_app.command("set")
@handled
def config_set(
    api_key: Annotated[bool, typer.Option("--api-key", help="输入 DeepSeek API Key，默认可见")] = False,
    base_url: Annotated[str | None, typer.Option(help="Chat API 地址")] = None,
    chat_model: Annotated[str | None, typer.Option(help="DeepSeek 模型名")] = None,
    embedding_api_key: Annotated[bool, typer.Option("--embedding-api-key", help="输入向量服务 API Key，默认可见")] = False,
    embedding_base_url: Annotated[str | None, typer.Option(help="独立 Embedding API 地址")] = None,
    embedding_model: Annotated[str | None, typer.Option(help="Embedding 模型名")] = None,
    embedding_dimension: Annotated[int | None, typer.Option(min=1, help="模型输出的向量维度")] = None,
    engine: Annotated[str | None, typer.Option(help="cpp 或 numpy")] = None,
    chunk_tokens: Annotated[int | None, typer.Option(min=16)] = None,
    chunk_overlap: Annotated[int | None, typer.Option(min=0)] = None,
    timeout: Annotated[float | None, typer.Option(min=0.1)] = None,
    max_retries: Annotated[int | None, typer.Option(min=0, max=5)] = None,
    min_score: Annotated[float | None, typer.Option(min=-1, max=1)] = None,
    hide_key: Annotated[bool, typer.Option("--hide-key", help="本次隐藏输入 API Key")] = False,
):
    """保存配置，API Key 在交互输入时默认可见。"""
    settings = load_settings(use_env=False)
    changes = {name: value for name, value in {
        "base_url": base_url, "chat_model": chat_model, "embedding_base_url": embedding_base_url,
        "embedding_model": embedding_model, "embedding_dimension": embedding_dimension,
        "retrieval_engine": engine, "chunk_tokens": chunk_tokens, "chunk_overlap": chunk_overlap,
        "timeout": timeout, "max_retries": max_retries, "min_score": min_score,
    }.items() if value is not None}
    if embedding_api_key:
        candidate = replace(settings, **changes)
        if not candidate.embedding_model:
            candidate = qwen_settings(candidate,
                                      base_url=candidate.embedding_base_url or QWEN_EMBEDDING_BASE_URL,
                                      dimension=candidate.embedding_dimension or QWEN_EMBEDDING_DIMENSION)
            changes.update({name: getattr(candidate, name) for name in (
                "embedding_base_url", "embedding_model", "embedding_dimension", "embedding_batch_size")})
    if api_key:
        changes["api_key"] = prompt_api_key("DeepSeek API Key", hide_key=hide_key)
    if embedding_api_key:
        changes["embedding_api_key"] = prompt_api_key("Embedding API Key", hide_key=hide_key)
    if not changes:
        console.print("没有需要保存的配置，使用 miniima config set --help 查看参数。")
        return
    save_settings(replace(settings, **changes))
    console.print("配置已保存；config show 中的 API Key 仍会隐藏。")


@config_app.command("qwen")
@handled
def config_qwen(
    base_url: Annotated[str, typer.Option(help="Embedding 地址，默认百炼北京公共接口")] = QWEN_EMBEDDING_BASE_URL,
    dimension: Annotated[int, typer.Option(min=1, help="输出维度，默认 1024")] = QWEN_EMBEDDING_DIMENSION,
    hide_key: Annotated[bool, typer.Option("--hide-key", help="本次隐藏输入 API Key")] = False,
    test: Annotated[bool, typer.Option("--test", help="保存后实际测试 Embedding 连接")] = False,
):
    """自动配置 qwen3.7-text-embedding，只需输入 API Key，输入默认可见。"""
    settings = qwen_settings(load_settings(use_env=False), base_url=base_url, dimension=dimension)
    console.print(Text(f"Embedding：{settings.embedding_model} · {settings.embedding_dimension} 维"))
    console.print(Text(f"服务地址：{settings.embedding_url}"))
    key = prompt_api_key("Qwen Embedding API Key", hide_key=hide_key)
    save_settings(replace(settings, embedding_api_key=key))
    console.print("Qwen 配置已保存。")
    if test:
        effective = load_settings()
        if (effective.embedding_model, effective.embedding_url, effective.embedding_dimension) != (
                settings.embedding_model, settings.embedding_url, settings.embedding_dimension):
            raise ConfigurationError("环境变量覆盖了刚保存的 Qwen 配置，请检查 MINIIMA_EMBEDDING_* 后再测试。")
        from miniima.providers.openai_compatible import OpenAICompatibleProvider
        dimension = OpenAICompatibleProvider(effective).test_embedding()
        console.print(f"Embedding 连接成功，向量维度：{dimension}。")


@config_app.command("test")
@handled
def config_test(
    chat: Annotated[bool, typer.Option("--chat", help="实际调用 Chat API")] = False,
    embedding: Annotated[bool, typer.Option("--embedding", help="实际生成一个向量并校验维度")] = False,
):
    """实际测试 API，可能产生少量服务费用。默认仅测试 DeepSeek 问答。"""
    from miniima.providers.openai_compatible import OpenAICompatibleProvider
    provider = OpenAICompatibleProvider(load_settings())
    if not chat and not embedding:
        chat = True
    failures = 0
    for kind, enabled in (("Chat", chat), ("Embedding", embedding)):
        if not enabled:
            continue
        try:
            if kind == "Chat":
                provider.test_chat()
                console.print("Chat 连接成功，模型返回了有效文本。")
            else:
                dimension = provider.test_embedding()
                console.print(f"Embedding 连接成功，向量维度：{dimension}。")
        except MiniimaError as exc:
            console.print(Text(f"{kind} 测试失败：{exc}", style="red"))
            failures += 1
    if failures:
        raise typer.Exit(1)


@kb_app.command("create")
@handled
def kb_create(name: str):
    """创建知识库，绑定当前向量模型、维度和服务地址。"""
    kb = Repository(data_home()).create_kb(name, load_settings())
    console.print(Text(f"知识库已创建：{kb['name']} · {kb['id']}"))


@kb_app.command("list")
@handled
def kb_list():
    table = Table("名称", "UUID", "Embedding 模型", "维度")
    for kb in Repository(data_home()).list_kbs():
        table.add_row(Text(kb["name"]), kb["id"], Text(kb["embedding_model"]), str(kb["embedding_dimension"]))
    console.print(table)


@kb_app.command("delete")
@handled
def kb_delete(name: str, yes: Annotated[bool, typer.Option("--yes", "-y")] = False):
    """将知识库移入回收站，保留文档、向量及问答记录。"""
    repository = Repository(data_home())
    kb = repository.get_kb(name)
    if not yes and not typer.confirm(f"确认将知识库「{kb['name']}」移入回收站？之后可以恢复。"):
        console.print("已取消。")
        return
    service().delete_kb(kb["id"])
    console.print("知识库已移入回收站。")


@trash_app.command('list')
@handled
def trash_list():
    table = Table('类型', 'UUID', '名称', '所属知识库', '删除时间')
    table.columns[1].min_width = 36
    table.columns[1].no_wrap = True
    for item in Repository(data_home()).list_trash():
        table.add_row(item['kind'], item['id'], Text(item['title']), Text(item['knowledge_base_name']), item['deleted_at'])
    console.print(table)


@trash_app.command('restore')
@handled
def trash_restore(kind: str, identifier: str):
    Repository(data_home()).restore(kind, identifier)
    console.print('项目已恢复。')


@trash_app.command('purge')
@handled
def trash_purge(kind: str, identifier: str, yes: Annotated[bool, typer.Option('--yes', '-y')] = False):
    from miniima.application.trash import TrashService
    if not yes and not typer.confirm('确认彻底删除此项目？此操作无法恢复。'):
        console.print('已取消。')
        return
    TrashService(Repository(data_home())).purge(kind, identifier)
    console.print('项目已彻底删除。')


@trash_app.command('empty')
@handled
def trash_empty(yes: Annotated[bool, typer.Option('--yes', '-y')] = False):
    from miniima.application.trash import TrashService
    if not yes and not typer.confirm('确认清空回收站？其中的项目将无法恢复。'):
        console.print('已取消。')
        return
    TrashService(Repository(data_home())).empty()
    console.print('回收站已清空。')


@app.command()
@handled
def add(path: Path, kb: Annotated[str, typer.Option("--kb", help="知识库名称或 UUID")]):
    """导入 TXT/Markdown；同一知识库内按 SHA-256 去重。"""
    document, imported = service().add(path, kb)
    console.print(Text(f"{'导入完成' if imported else '内容相同，已跳过'}：{document['filename']} · {document['id']}"))


@app.command()
@handled
def docs(kb: Annotated[str, typer.Option("--kb")]):
    """查看文档状态和 Chunk 数量。"""
    table = Table("UUID", "文件名", "状态", "Chunks", "错误")
    for document in Repository(data_home()).list_documents(kb):
        table.add_row(document["id"], Text(document["filename"]), document["status"],
                      str(document["chunk_count"]), Text(document["error"] or ""))
    console.print(table)


@app.command()
@handled
def search(question: str, kb: Annotated[str, typer.Option("--kb")],
           top_k: Annotated[int, typer.Option(min=1, max=100)] = 5,
           engine: Annotated[str | None, typer.Option(help="本次使用 cpp 或 numpy")] = None):
    """语义搜索并展示文件、行号、标题和摘要。"""
    matches = service().search(question, kb, top_k, engine=engine)
    if not matches:
        console.print("知识库中没有可检索的有效文档，请先导入。")
    for number, match in enumerate(matches, 1):
        console.print(Text(f"[{number}] 相似度 {match['score']:.4f} · {match['filename']} · {source_location(match)}"))
        console.print(Text(match["content"][:400]))


@app.command()
@handled
def ask(question: str, kb: Annotated[str, typer.Option("--kb")],
        top_k: Annotated[int, typer.Option(min=1, max=100)] = 5,
        engine: Annotated[str | None, typer.Option(help="本次使用 cpp 或 numpy")] = None):
    """根据知识库回答，校验引用并保存问答记录。"""
    answer = service().ask(question, kb, top_k, engine=engine)
    console.print(Text(answer.text))
    if answer.citations:
        console.print("\n来源：")
        for item in answer.citations:
            console.print(Text(f"[{item['citation_number']}] {item['filename']} · {source_location(item)} · {item['document_id']}"))
    console.print(Text(f"\n会话已保存：{answer.conversation_id}"))


@app.command()
@handled
def doctor():
    """离线检查数据库、默认引擎和配置；连接测试请用 config test。"""
    settings = load_settings()
    repository = Repository(data_home())
    diagnostics = repository.diagnostics()
    console.print(Text(str(diagnostics)))
    from miniima.vector import create_index
    create_index(max(settings.embedding_dimension, 1), settings.retrieval_engine)
    console.print(f"检索引擎可用：{settings.retrieval_engine}")
    settings.require_chat()
    settings.require_embedding()
    if diagnostics["integrity"] != "ok" or diagnostics["foreign_key_errors"]:
        raise MiniimaError("数据库完整性检查未通过。")
    console.print("本地检查通过；使用 miniima config test --chat --embedding 测试真实 API。")


def main():
    app()
