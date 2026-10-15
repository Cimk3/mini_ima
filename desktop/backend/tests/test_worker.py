import io
import json
import os
import queue
import subprocess
import sys
import threading
from dataclasses import replace
from pathlib import Path

import httpx
import pytest
from openai import OpenAI

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from worker import Dispatcher, serve
from miniima.application.service import KnowledgeService
from miniima.config import Settings, load_settings, save_settings
from miniima.providers.openai_compatible import OpenAICompatibleProvider
from miniima.storage.repository import Repository


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch):
    for name in tuple(os.environ):
        if name.startswith("MINIIMA_"):
            monkeypatch.delenv(name)


def handler(request):
    body = json.loads(request.content)
    if request.url.path.endswith("embeddings"):
        return httpx.Response(200, json={"model": "test-embedding", "object": "list", "data": [
            {"object": "embedding", "index": i, "embedding": [1., 0., 0., 0., 0., 0., 0., 0.]}
            for i, _ in enumerate(body["input"])]})
    return httpx.Response(200, json={"id": "test", "object": "chat.completion", "created": 0,
        "model": "test-chat", "choices": [{"index": 0, "finish_reason": "stop",
        "message": {"role": "assistant", "content": "TCP 三次握手用于同步初始序列号。[1]"}}]})


def provider(settings):
    return OpenAICompatibleProvider(settings, client_factory=lambda **kwargs: OpenAI(
        **kwargs, http_client=httpx.Client(transport=httpx.MockTransport(handler))))


@pytest.fixture
def dispatcher(tmp_path):
    root = tmp_path / "数据目录 with spaces"
    dispatcher = Dispatcher(root, provider)
    dispatcher.dispatch("initialize", {})
    save_settings(replace(Settings(), api_key="secret-chat-test", embedding_api_key="secret-embed-test",
                          base_url="https://chat.test/v1", chat_model="test-chat",
                          embedding_base_url="https://embedding.test/v1", embedding_model="test-embedding",
                          embedding_dimension=8), root)
    return dispatcher


def call(dispatcher, method, **params):
    response = dispatcher.handle({"id": "request", "method": method, "params": params})
    assert response["id"] == "request"
    assert "error" not in response, response
    return response["result"]


def test_cli_core_to_desktop_and_desktop_to_cli_persist(dispatcher, tmp_path):
    kb = call(dispatcher, "kb.create", name="网络")
    path = tmp_path / "中文 路径.md"
    path.write_text("# TCP\n\nTCP 三次握手同步序列号。", encoding="utf-8")
    settings = load_settings(dispatcher.home)
    cli_core = KnowledgeService(Repository(dispatcher.home), settings, provider(settings))
    cli_core.add(path, kb["id"])
    assert call(dispatcher, "docs.list", kb=kb["id"])[0]["filename"] == path.name
    answer = call(dispatcher, "ask", kb=kb["id"], question="TCP 如何建立连接？")
    assert answer["citations"][0]["filename"] == path.name
    other = tmp_path / "另一份.txt"
    other.write_text("TCP 第二份笔记", encoding="utf-8")
    assert call(dispatcher, "docs.import", kb=kb["id"], path=str(other))["imported"]
    restarted = KnowledgeService(Repository(dispatcher.home), settings, provider(settings))
    assert len(restarted.search("TCP", kb["id"])) == 2
    assert len(Repository(dispatcher.home).list_documents(kb["id"])) == 2
    assert call(dispatcher, "doctor")["engine"] == "cpp"


def test_dedup_failure_recovery_and_preview_isolation(dispatcher, tmp_path):
    kb = call(dispatcher, "kb.create", name="网络")
    other = call(dispatcher, "kb.create", name="另一个")
    path = tmp_path / "a.md"
    path.write_text("# TCP\n\nTCP 笔记", encoding="utf-8")
    first = call(dispatcher, "docs.import", kb=kb["id"], path=str(path))
    assert not call(dispatcher, "docs.import", kb=kb["id"], path=str(path))["imported"]
    assert call(dispatcher, "docs.preview", kb=kb["id"], document_id=first["document"]["id"])["source_metadata"]["heading_path"] == ["TCP"]
    assert call(dispatcher, "docs.preview", kb=other["id"], document_id=first["document"]["id"]) is None
    invalid = tmp_path / "empty.txt"
    invalid.write_text(" \n ", encoding="utf-8")
    assert "error" in dispatcher.handle({"id": 1, "method": "docs.import", "params": {"kb": kb["id"], "path": str(invalid)}})
    assert call(dispatcher, "search", kb=kb["id"], question="TCP")[0]["filename"] == "a.md"


def test_settings_preserve_keys_mask_results_and_keep_environment_precedence(dispatcher, monkeypatch):
    result = call(dispatcher, "settings.get")
    assert "secret-chat-test" not in json.dumps(result) and "secret-embed-test" not in json.dumps(result)
    call(dispatcher, "settings.update", values={"api_key": "", "embedding_api_key": "", "timeout": 45})
    settings = load_settings(dispatcher.home)
    assert settings.api_key == "secret-chat-test" and settings.embedding_api_key == "secret-embed-test"
    assert settings.timeout == 45
    monkeypatch.setenv("MINIIMA_CHAT_MODEL", "environment-model")
    snapshot = call(dispatcher, "settings.get")
    assert snapshot["effective"]["chat_model"] == "environment-model"
    assert "chat_model" in snapshot["overrides"]
    call(dispatcher, "settings.update", values={"chat_model": "saved-model"})
    assert load_settings(dispatcher.home).chat_model == "environment-model"


def test_qwen_preset_is_only_a_preview_and_connections_use_mock(dispatcher):
    preset = call(dispatcher, "settings.qwen")
    assert preset["embedding_model"] == "qwen3.7-text-embedding"
    assert load_settings(dispatcher.home).embedding_model == "test-embedding"
    assert call(dispatcher, "connections.test", kind="chat")["connected"]
    assert call(dispatcher, "connections.test", kind="embedding")["dimension"] == 8


def test_model_mismatch_and_provider_errors_are_safe(dispatcher, tmp_path):
    kb = call(dispatcher, "kb.create", name="bound")
    call(dispatcher, "settings.update", values={"embedding_model": "different"})
    response = dispatcher.handle({"id": 1, "method": "search", "params": {"kb": kb["id"], "question": "TCP"}})
    assert "不一致" in response["error"]["message"]
    def broken_provider(settings):
        return OpenAICompatibleProvider(settings, client_factory=lambda **kwargs: OpenAI(**kwargs,
            http_client=httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(
                401, json={"error": {"message": "secret-chat-test raw user document"}})))))
    dispatcher.provider_factory = broken_provider
    response = dispatcher.handle({"id": 2, "method": "connections.test", "params": {"kind": "chat"}})
    assert response["error"]["code"] == "provider"
    assert "401" in response["error"]["message"]
    assert "secret-chat-test" not in json.dumps(response)


def test_shared_trash_retains_originals_until_purged(dispatcher, tmp_path):
    kb = call(dispatcher, "kb.create", name="delete")
    path = tmp_path / "a.txt"
    path.write_text("TCP", encoding="utf-8")
    call(dispatcher, "docs.import", kb=kb["id"], path=str(path))
    directory = dispatcher.home / "originals" / kb["id"]
    assert directory.exists()
    call(dispatcher, "kb.delete", kb=kb["id"])
    assert directory.exists() and not call(dispatcher, 'kb.list')
    call(dispatcher, 'trash.restore', kind='kb', item_id=kb['id'])
    assert call(dispatcher, 'docs.list', kb=kb['id'])
    call(dispatcher, 'kb.delete', kb=kb['id'])
    call(dispatcher, 'trash.purge', kind='kb', item_id=kb['id'])
    assert not directory.exists() and not call(dispatcher, "kb.list")
    assert dispatcher.repository.diagnostics()["foreign_key_errors"] == 0


def test_conversation_ipc_roundtrip_retry_and_trash(dispatcher, tmp_path):
    kb = call(dispatcher, 'kb.create', name='连续对话')
    path = tmp_path / 'TCP.md'
    path.write_text('TCP 三次握手建立可靠连接。', encoding='utf-8')
    call(dispatcher, 'docs.import', kb=kb['id'], path=str(path))
    first = call(dispatcher, 'conversations.send', kb=kb['id'], question='TCP是什么？', request_id='one')
    second = call(dispatcher, 'conversations.send', kb=kb['id'], question='那为什么需要三次？', request_id='two', conversation_id=first['id'])
    assert len(second['messages']) == 4
    assert call(dispatcher, 'conversations.get', request_id='one')['id'] == first['id']
    assert call(dispatcher, 'conversations.list')['items'][0]['title'] == 'TCP是什么？'
    assert isinstance(second['messages'][1]['citations'][0]['id'], str)
    call(dispatcher, 'conversations.delete', conversation_id=first['id'])
    assert call(dispatcher, 'conversations.list')['items'] == []
    assert call(dispatcher, 'trash.list')[0]['kind'] == 'conversation'
    call(dispatcher, 'trash.restore', kind='conversation', item_id=first['id'])
    assert len(call(dispatcher, 'conversations.get', conversation_id=first['id'])['messages']) == 4


def test_conversation_errors_keep_question_and_do_not_repeat_request(dispatcher, tmp_path):
    kb = call(dispatcher, 'kb.create', name='失败恢复')
    path = tmp_path / 'TCP.txt'
    path.write_text('TCP 使用握手。', encoding='utf-8')
    call(dispatcher, 'docs.import', kb=kb['id'], path=str(path))
    original = dispatcher.provider_factory
    class Broken:
        def embed(self, texts):
            from miniima.errors import ProviderError
            raise ProviderError('模拟 API 超时')
    dispatcher.provider_factory = lambda settings: Broken()
    failed = call(dispatcher, 'conversations.send', kb=kb['id'], question='TCP', request_id='stable')
    assert failed['messages'][0]['status'] == 'failed'
    dispatcher.provider_factory = original
    retried = call(dispatcher, 'conversations.retry', request_id='stable')
    assert len(retried['messages']) == 2
    assert len(call(dispatcher, 'conversations.send', kb=kb['id'], question='TCP', request_id='stable')['messages']) == 2


@pytest.mark.parametrize("payload", [None, [], {"id": "1", "method": "shell.exec"},
    {"id": "1", "method": "settings.update", "params": {"values": {"unknown": "secret-value"}}},
    {"id": "1", "method": "settings.update", "params": {"values": {"embedding_dimension": "secret-value"}}}])
def test_invalid_requests_do_not_leak_values(dispatcher, payload):
    response = dispatcher.handle(payload)
    assert "error" in response and "secret-value" not in json.dumps(response)


def test_json_lines_malformed_input_and_shutdown(dispatcher):
    lines = 'bad json\n' + json.dumps({"id": "ok", "method": "kb.list"}) + '\n' + json.dumps({"id": "end", "method": "shutdown"}) + '\n' + json.dumps({"id": "never", "method": "kb.list"})
    output = io.StringIO()
    serve(dispatcher, io.StringIO(lines), output)
    responses = [json.loads(line) for line in output.getvalue().splitlines()]
    assert len(responses) == 3 and responses[0]["id"] is None
    assert responses[-1] == {"id": "end", "result": {"shutdown": True}}


def test_history_stays_responsive_while_a_turn_is_pending(dispatcher, tmp_path):
    kb = call(dispatcher, 'kb.create', name='异步读取')
    path = tmp_path / 'TCP.txt'
    path.write_text('TCP 三次握手。', encoding='utf-8')
    call(dispatcher, 'docs.import', kb=kb['id'], path=str(path))
    entered, release = threading.Event(), threading.Event()
    original_factory = dispatcher.provider_factory
    chats = []

    class Delayed:
        def __init__(self, settings):
            self.provider = original_factory(settings)
        def embed(self, texts):
            return self.provider.embed(texts)
        def chat(self, messages):
            chats.append(messages)
            entered.set()
            assert release.wait(10)
            return self.provider.chat(messages)

    dispatcher.provider_factory = Delayed
    inputs, outputs = queue.Queue(), queue.Queue()

    class Output:
        def write(self, line):
            outputs.put(json.loads(line))
        def flush(self):
            pass

    def submit(identifier, method, **params):
        inputs.put(json.dumps({'id': identifier, 'method': method, 'params': params}) + '\n')

    worker = threading.Thread(target=serve, args=(dispatcher, iter(inputs.get, None), Output()), daemon=True)
    worker.start()
    try:
        submit('turn', 'conversations.send', kb=kb['id'], question='TCP', request_id='stable')
        assert entered.wait(5)
        submit('history', 'conversations.list')
        history = outputs.get(timeout=5)
        assert history['id'] == 'history' and history['result']['total'] == 1
        submit('duplicate', 'conversations.send', kb=kb['id'], question='TCP', request_id='stable')
        duplicate = outputs.get(timeout=5)
        assert duplicate['id'] == 'duplicate' and '仍在处理中' in duplicate['error']['message']
        release.set()
        completed = outputs.get(timeout=5)
        assert completed['id'] == 'turn' and len(completed['result']['messages']) == 2
        assert len(chats) == 1
    finally:
        release.set()
        inputs.put(None)
        worker.join(10)
    assert not worker.is_alive()


def test_worker_subprocess_exits_on_eof_without_a_server(tmp_path):
    worker = Path(__file__).resolve().parents[1] / "worker.py"
    env = {**os.environ, "MINIIMA_HOME": str(tmp_path / "subprocess-home"), "PYTHONIOENCODING": "utf-8"}
    commands = '\n'.join(json.dumps({"id": str(i), "method": method}) for i, method in enumerate(("initialize", "doctor"))) + '\n'
    result = subprocess.run([sys.executable, str(worker)], input=commands, capture_output=True,
                            text=True, encoding="utf-8", env=env, timeout=30)
    assert result.returncode == 0, result.stderr
    responses = [json.loads(line) for line in result.stdout.splitlines()]
    assert len(responses) == 2 and responses[1]["result"]["engine"] == "cpp"
