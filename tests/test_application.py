from dataclasses import replace

import numpy as np
import pytest

from miniima.application.service import KnowledgeService
from miniima.documents.chunking import make_chunks
from miniima.documents.parsers import parse
from miniima.errors import MiniimaError, ProviderError
from miniima.rag.answering import validate_citations
from miniima.storage.repository import Repository


def test_persistence_search_rag_and_citation_snapshots(tmp_path, repository, settings, provider):
    kb = repository.create_kb("网络", settings)
    path = tmp_path / "notes.md"
    path.write_text("# TCP\n\nTCP 使用三次握手建立连接。", encoding="utf-8")
    service = KnowledgeService(repository, settings, provider)
    document, imported = service.add(path, kb["name"])
    assert imported
    # Reconstruct the repository and service: no in-memory state is required.
    restarted = KnowledgeService(Repository(repository.home), settings, provider)
    matches = restarted.search("TCP 握手", kb["id"])
    assert matches[0]["document_id"] == document["id"]
    assert matches[0]["source_metadata"]["heading_path"] == ["TCP"]
    result = restarted.ask("TCP 如何建立连接？", kb["name"])
    assert "[1]" in result.text and len(result.citations) == 1
    assert "不可信数据" in provider.last_messages[0]["content"]
    with repository.connection() as connection:
        assert connection.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 2
        citation = connection.execute("SELECT * FROM message_citations").fetchone()
        assert citation["filename"] == "notes.md"
        assert "三次握手" in citation["content"]
        vector = connection.execute("SELECT vector FROM embeddings").fetchone()[0]
        assert len(vector) == 8 * 4
    assert repository.diagnostics() == {"integrity": "ok", "foreign_key_errors": 0,
                                        "schema_version": 3, "journal_mode": "wal"}


def test_dedup_and_knowledge_base_isolation(tmp_path, repository, settings, provider):
    one = repository.create_kb("一", settings)
    two = repository.create_kb("二", settings)
    path = tmp_path / "a.txt"
    path.write_text("TCP 三次握手", encoding="utf-8")
    service = KnowledgeService(repository, settings, provider)
    doc_one, _ = service.add(path, one["id"])
    calls = provider.embedding_calls
    assert service.add(path, one["id"])[1] is False
    assert provider.embedding_calls == calls
    doc_two, _ = service.add(path, two["id"])
    assert doc_two["id"] != doc_one["id"]
    assert all(match["document_id"] == doc_two["id"] for match in service.search("TCP", two["id"]))


def test_failed_embedding_is_retriable_and_preserves_existing_data(tmp_path, repository, settings, provider):
    kb = repository.create_kb("网络", settings)
    service = KnowledgeService(repository, settings, provider)
    path = tmp_path / "good.txt"
    path.write_text("TCP 已有内容", encoding="utf-8")
    original, _ = service.add(path, kb["id"])
    other = tmp_path / "other.txt"
    other.write_text("以太网 新内容", encoding="utf-8")
    provider.fail = True
    with pytest.raises(ProviderError):
        service.add(other, kb["id"])
    failed = next(doc for doc in repository.list_documents(kb["id"]) if doc["status"] == "failed")
    assert failed["chunk_count"] == 0
    assert len(list((repository.home / "originals" / kb["id"]).iterdir())) == 1
    provider.fail = False
    assert service.search("TCP", kb["id"])[0]["document_id"] == original["id"]
    retried, imported = service.add(other, kb["id"])
    assert imported and retried["id"] == failed["id"] and retried["status"] == "ready"


def test_sql_failure_rolls_back_entire_import(tmp_path, repository, settings):
    kb = repository.create_kb("rollback", settings)
    path = tmp_path / "a.txt"
    path.write_text("TCP 网络", encoding="utf-8")
    chunks = make_chunks(parse(path), "doc", "txt")
    document = {"id": "doc", "knowledge_base_id": kb["id"], "filename": "a.txt", "sha256": "a" * 64,
                "source_type": "txt", "original_path": "mock.txt"}
    with pytest.raises(ValueError):
        repository.store_document(document, chunks, np.empty((0, 8)), kb)
    assert repository.list_documents(kb["id"]) == []
    assert repository.index_data(kb)[0] == []


@pytest.mark.parametrize("field,value", [("embedding_model", "other"), ("embedding_dimension", 9),
                                         ("embedding_base_url", "https://different.test")])
def test_incompatible_configuration_rejected(repository, settings, provider, field, value):
    kb = repository.create_kb("bound", settings)
    service = KnowledgeService(repository, replace(settings, **{field: value}), provider)
    with pytest.raises(MiniimaError, match="不一致"):
        service.search("TCP", kb["id"])


def test_insufficient_evidence_skips_chat(repository, settings, provider):
    kb = repository.create_kb("empty", settings)
    service = KnowledgeService(repository, settings, provider)
    result = service.ask("TCP", kb["id"])
    assert "证据不足" in result.text
    assert provider.embedding_calls == provider.chat_calls == 0


def test_invalid_citations_fail_closed():
    assert "无效来源" in validate_citations("虚构 [99]", [{"citation_number": 1}])[0]
    assert validate_citations("没引用", [{"citation_number": 1}])[1] == []


def test_repeat_init_unique_names_and_cascade(repository, settings):
    kb = repository.create_kb("keep", settings)
    repository.initialize()
    assert repository.get_kb(kb["id"])["name"] == "keep"
    with pytest.raises(MiniimaError, match="同名"):
        repository.create_kb("keep", settings)
    conversation = repository.save_answer(kb["id"], "question", "answer", [])
    repository.delete_kb(kb["id"])
    assert not repository.list_kbs()
    repository.purge('kb', kb['id'])
    with repository.connection() as connection:
        assert connection.execute("SELECT COUNT(*) FROM messages WHERE conversation_id=?", (conversation,)).fetchone()[0] == 0


def test_api_failure_does_not_save_partial_conversation(tmp_path, repository, settings, provider):
    kb = repository.create_kb("errors", settings)
    path = tmp_path / "a.txt"
    path.write_text("TCP 内容", encoding="utf-8")
    service = KnowledgeService(repository, settings, provider)
    service.add(path, kb["id"])
    def broken_chat(messages):
        raise ProviderError("模拟 Chat 错误")
    provider.chat = broken_chat
    with pytest.raises(ProviderError):
        service.ask("TCP", kb["id"])
    with repository.connection() as connection:
        assert connection.execute("SELECT COUNT(*) FROM conversations").fetchone()[0] == 0
