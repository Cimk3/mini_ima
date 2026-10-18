import asyncio
import json

import pytest

from miniima.application.conversations import ConversationService
from miniima.application.generation import GenerationRun, GenerationRegistry, generate
from miniima.application.service import KnowledgeService
from miniima.application.exporting import export_conversation
from miniima.errors import MiniimaError, ProviderError
from miniima.storage.repository import Repository


@pytest.fixture
def streaming(tmp_path, repository, settings, provider):
    kb = repository.create_kb('流式资料', settings)
    path = tmp_path / 'TCP.md'
    path.write_text('# TCP\n\nTCP 三次握手同步序列号。', encoding='utf-8')
    knowledge = KnowledgeService(repository, settings, provider)
    knowledge.add(path, kb['id'])
    async def embed(texts):
        return provider.embed(texts)
    async def chat(messages):
        if 'conversation' in json.loads(messages[-1]['content']):
            return 'TCP 的作用？'
        return provider.chat(messages)
    async def stream(messages):
        provider.last_messages = messages
        for delta in ['TCP ', '三次握手。[1]']:
            await asyncio.sleep(0)
            yield delta
    provider.aembed, provider.achat, provider.stream_chat = embed, chat, stream
    return knowledge, kb, provider


def test_text_arrives_before_final_commit_and_repeated_request_is_not_replayed(streaming):
    knowledge, kb, _ = streaming
    events = []
    def event(value):
        events.append(value)
        if value['type'] == 'delta':
            detail = knowledge.repository.get_conversation(value['conversation_id'])
            assert len(detail['messages']) == 1 and detail['messages'][0]['status'] == 'pending'
    run = GenerationRun('first', event)
    result = asyncio.run(generate(knowledge, run, kb['id'], 'TCP 是什么？'))
    assert [item['text'] for item in events if item['type'] == 'delta'] == ['TCP ', '三次握手。[1]']
    assert len(result['messages']) == 2 and result['messages'][1]['citations']
    assert not run.cancel()
    duplicate = asyncio.run(generate(knowledge, GenerationRun('first'), kb['id'], 'TCP 是什么？'))
    assert duplicate['messages'] == result['messages']


@pytest.mark.parametrize('when', ['before', 'searching', 'delta', 'validating'])
def test_cancel_at_each_stage_is_idempotent_and_retains_partial(streaming, when):
    knowledge, kb, _ = streaming
    run = GenerationRun('stop-' + when)
    def event(value):
        if value['type'] == when or value.get('phase') == when:
            assert run.cancel()
            assert run.cancel()
    run.emit = event
    if when == 'before':
        run.cancel()
    result = asyncio.run(generate(knowledge, run, kb['id'], 'TCP 是什么？'))
    assert result['messages'][0]['status'] == 'interrupted'
    assert '已停止' in result['messages'][0]['error']
    if when in ('delta', 'validating'):
        assert result['messages'][1]['content'] and result['messages'][1]['status'] == 'interrupted'
        assert result['messages'][1]['citations'] == []
    else:
        assert len(result['messages']) == 1
    assert not run.cancel()


def test_disconnect_persists_partial_excludes_it_from_context_and_retry_replaces_it(streaming):
    knowledge, kb, provider = streaming
    original = provider.stream_chat
    async def broken(messages):
        yield '未完成内容 [88]'
        raise ProviderError('模拟断线')
    provider.stream_chat = broken
    result = asyncio.run(generate(knowledge, GenerationRun('retry'), kb['id'], 'TCP 是什么？'))
    assert result['messages'][1]['status'] == 'failed'
    assert Repository(knowledge.repository.home).get_conversation(result['id'])['messages'] == result['messages']
    assert ConversationService.history(result, 10) == []
    provider.stream_chat = original
    recovered = asyncio.run(generate(knowledge, GenerationRun('retry'), kb['id'], 'TCP 是什么？', result['id'], retry=True))
    assert len(recovered['messages']) == 2 and all(item['status'] == 'completed' for item in recovered['messages'])
    assert len(recovered['messages'][1]['citations']) == 1
    assert '未完成内容' not in recovered['messages'][1]['content']
    with knowledge.repository.connection() as connection:
        assert connection.execute('PRAGMA user_version').fetchone()[0] == 3
        assert not connection.execute('PRAGMA foreign_key_check').fetchall()


def test_nonstream_mode_and_invalid_citations(streaming):
    knowledge, kb, provider = streaming
    events = []
    detail = asyncio.run(generate(knowledge, GenerationRun('normal', events.append), kb['id'], 'TCP 是什么？', stream=False))
    assert detail['messages'][1]['citations'] and not any(item['type'] == 'delta' for item in events)
    async def invalid(messages):
        yield '虚假引用 [99]'
    provider.stream_chat = invalid
    detail = asyncio.run(generate(knowledge, GenerationRun('invalid'), kb['id'], 'TCP 是什么？'))
    assert '无效来源编号' in detail['messages'][1]['content']
    assert detail['messages'][1]['citations'] == []


def test_preparation_io_is_actually_cancelled(streaming):
    knowledge, kb, provider = streaming
    closed = []
    run = GenerationRun('preparation')
    async def embed(texts):
        try:
            run.cancel()
            await asyncio.sleep(30)
        finally:
            closed.append(True)
    provider.aembed = embed
    result = asyncio.run(generate(knowledge, run, kb['id'], 'TCP 是什么？'))
    assert closed and result['messages'][0]['status'] == 'interrupted'


def test_registry_reserves_queued_jobs_before_cancel():
    registry = GenerationRegistry()
    run = registry.reserve('queued')
    assert registry.cancel('queued') and run.cancelled
    with pytest.raises(MiniimaError):
        registry.reserve('queued')
    registry.release(run)
    assert not registry.cancel('queued')


def test_export_uses_snapshots_per_round_and_marks_incomplete(streaming):
    knowledge, kb, provider = streaming
    first = asyncio.run(generate(knowledge, GenerationRun('one'), kb['id'], 'TCP 是什么？'))
    second = asyncio.run(generate(knowledge, GenerationRun('two'), kb['id'], '再介绍 TCP。', first['id']))
    identifier, user, _ = knowledge.repository.begin_turn(kb['id'], '中断的问题', 'three', second['id'])
    detail = knowledge.repository.finish_incomplete(user['id'], '部分回答 [1]', 'interrupted', '已停止生成。')
    # The export remains self-contained after source chunks cease to exist.
    with knowledge.repository.connection() as connection, connection:
        connection.execute('DELETE FROM chunks')
    detail = knowledge.repository.get_conversation(identifier)
    detail['title'] = 'CON:/中文?'
    data = export_conversation(detail)
    assert not any(char in data['filename'] for char in ':?*/\\')
    assert data['markdown'].count('#### [1] TCP.md') == 2
    assert '第 1 轮来源' in data['markdown'] and '第 2 轮来源' in data['markdown']
    assert 'TCP 三次握手同步序列号' in data['markdown']
    assert '部分回答 [1]' in data['markdown'] and '来源尚未校验' in data['markdown']
    assert 'mock-chat-key' not in data['markdown'] and str(knowledge.repository.home) not in data['markdown']


def test_export_web_citation_and_pending_rejection(streaming):
    knowledge, kb, _ = streaming
    identifier, user, _ = knowledge.repository.begin_turn(kb['id'], '网页资料？', 'web')
    with pytest.raises(MiniimaError, match='仍在生成'):
        export_conversation(knowledge.repository.get_conversation(identifier))
    detail = knowledge.repository.complete_turn(user['id'], '网页结论。[1]', [{
        'id': 'web:one', 'chunk_id': None, 'document_id': 'web:one', 'citation_number': 1,
        'filename': '网页标题', 'content': '原文中包含 ``` 围栏',
        'source_metadata': {'kind': 'web', 'url': 'https://example.org/a', 'retrieved_at': '2026-10-18T00:00:00Z'}}])
    data = export_conversation(detail)
    assert 'https://example.org/a' in data['markdown'] and '检索时间' in data['markdown']
    assert '````text' in data['markdown']
