import json
import os
import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner

from miniima.application.conversations import ConversationService
from miniima.application.service import KnowledgeService
from miniima.application.trash import TrashService
from miniima.cli import app
from miniima.errors import MiniimaError, ProviderError
from miniima.storage.repository import Repository


def setup_chat(tmp_path, repository, settings, provider):
    kb = repository.create_kb('网络知识', settings)
    path = tmp_path / '中文 资料.md'
    path.write_text('# TCP\n\nTCP 三次握手确认双方收发能力和初始序列号。', encoding='utf-8')
    knowledge = KnowledgeService(repository, settings, provider)
    knowledge.add(path, kb['id'])
    calls = []
    original = provider.chat

    def chat(messages):
        calls.append(messages)
        payload = json.loads(messages[-1]['content'])
        if 'conversation' in payload:
            return 'TCP 三次握手为什么确认双方收发能力？'
        return original(messages)

    provider.chat = chat
    return kb, ConversationService(knowledge), calls


def test_multi_turn_history_rewrite_and_per_answer_citations(tmp_path, repository, settings, provider):
    kb, chat, calls = setup_chat(tmp_path, repository, settings, provider)
    first = chat.send(kb['id'], 'TCP 为什么需要三次握手？', 'turn-1')
    second = chat.send(kb['id'], '那第三次有什么用？', 'turn-2', first['id'])
    assert first['id'] == second['id'] and len(second['messages']) == 4
    assert [m['role'] for m in second['messages']] == ['user', 'assistant', 'user', 'assistant']
    assert json.loads(calls[1][-1]['content'])['conversation'][0]['content'] == 'TCP 为什么需要三次握手？'
    assert calls[2][1]['role'] == 'user' and calls[2][2]['role'] == 'assistant'
    assert '[1]' not in calls[2][2]['content']
    answers = [m for m in second['messages'] if m['role'] == 'assistant']
    assert all(m['citations'][0]['citation_number'] == 1 for m in answers)
    assert answers[0]['citations'][0]['id'] != answers[1]['citations'][0]['id']
    restarted = Repository(repository.home).get_conversation(first['id'])
    assert restarted['messages'] == second['messages']


def test_failure_retry_dedup_and_late_retry_keep_order(tmp_path, repository, settings, provider):
    kb, chat, calls = setup_chat(tmp_path, repository, settings, provider)
    original = provider.chat
    provider.chat = lambda messages: (_ for _ in ()).throw(ProviderError('模拟 API 超时'))
    failed = chat.send(kb['id'], 'TCP 的作用？', 'failed-1')
    assert failed['messages'][0]['status'] == 'failed'
    assert failed['messages'][0]['content'] == 'TCP 的作用？'
    provider.chat = original
    next_turn = chat.send(kb['id'], 'TCP 握手的过程？', 'turn-2', failed['id'])
    retried = chat.retry('failed-1')
    assert [m['position'] for m in retried['messages']] == [0, 1, 2, 3]
    assert all(m['status'] == 'completed' for m in retried['messages'])
    assert next_turn['id'] == retried['id']
    call_count = len(calls)
    repeated = chat.send(kb['id'], 'TCP 的作用？', 'failed-1')
    assert repeated['messages'] == retried['messages'] and len(calls) == call_count
    with pytest.raises(MiniimaError, match='另一个问题'):
        chat.send(kb['id'], '不同的问题', 'failed-1')


def test_pending_owner_recovery_and_single_flight(repository, settings):
    kb = repository.create_kb('恢复', settings)
    identifier, user, _ = repository.begin_turn(kb['id'], '中断的问题', 'request')
    repository.recover_interrupted()
    assert repository.get_conversation(identifier)['messages'][0]['status'] == 'pending'
    with pytest.raises(MiniimaError, match='正在处理'):
        repository.begin_turn(kb['id'], '第二个问题', 'second', identifier)
    with repository.connection() as connection, connection:
        connection.execute('UPDATE messages SET worker_pid=-1 WHERE id=?', (user['id'],))
    repository.recover_interrupted()
    assert repository.get_conversation(identifier)['messages'][0]['status'] == 'interrupted'


def test_history_context_caps_at_eight_complete_turns():
    messages = []
    for n in range(12):
        messages.extend([{'id': f'u{n}', 'role': 'user', 'content': f'问题{n}', 'position': n * 2, 'status': 'completed'},
                         {'id': f'a{n}', 'role': 'assistant', 'reply_to': f'u{n}', 'content': f'回答{n}', 'citations': []}])
    selected = ConversationService.history({'messages': messages}, 24)
    assert len(selected) == 16 and selected[0]['content'] == '问题4'
    messages[-1]['content'] = '长' * 5000
    assert ConversationService.history({'messages': messages}, 24) == []


def test_v1_migration_backs_up_wal_and_preserves_old_order(tmp_path):
    home = tmp_path / '旧数据库'
    home.mkdir()
    sql = Path(__file__).parents[1] / 'src/miniima/storage/migrations/001_initial.sql'
    connection = sqlite3.connect(home / 'miniima.sqlite3')
    connection.execute('PRAGMA journal_mode=WAL')
    connection.executescript(sql.read_text(encoding='utf-8'))
    connection.execute("INSERT INTO knowledge_bases VALUES ('kb','旧知识库','model',8,'https://test','time','time')")
    connection.execute("INSERT INTO conversations VALUES ('old','kb','time','time')")
    connection.execute("INSERT INTO messages VALUES ('z-user','old','user','原来的问题','time','time')")
    connection.execute("INSERT INTO messages VALUES ('a-answer','old','assistant','原来的回答 [1]','time','time')")
    connection.execute("INSERT INTO conversations VALUES ('separate','kb','time','time')")
    connection.execute("INSERT INTO messages VALUES ('second-user','separate','user','另一条独立问答','time','time')")
    connection.execute("INSERT INTO messages VALUES ('second-answer','separate','assistant','另一条回答','time','time')")
    connection.execute("INSERT INTO message_citations VALUES ('cite','a-answer',NULL,1,'doc','旧文档.md','原文快照','{}','time')")
    connection.execute('PRAGMA user_version=1')
    connection.commit()
    repository = Repository(home)
    assert repository.list_kbs()[0]['id'] == 'kb'  # Data commands upgrade without a separate init.
    connection.close()
    detail = repository.get_conversation('old')
    assert detail['title'] == '原来的问题'
    assert [m['role'] for m in detail['messages']] == ['user', 'assistant']
    assert detail['messages'][1]['reply_to'] == 'z-user'
    assert detail['messages'][1]['citations'][0]['chunk_id'] is None
    assert repository.get_conversation('separate')['title'] == '另一条独立问答'
    assert repository.list_conversations()['total'] == 2
    backups = list((home / 'backups').glob('*.sqlite3'))
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as backup:
        assert backup.execute('PRAGMA user_version').fetchone()[0] == 1
        assert backup.execute('SELECT COUNT(*) FROM messages').fetchone()[0] == 4
    repository.initialize()
    assert len(list((home / 'backups').glob('*.sqlite3'))) == 1


def test_trash_parent_restore_preserves_independent_child_state(tmp_path, repository, settings, provider):
    kb, chat, _ = setup_chat(tmp_path, repository, settings, provider)
    first = chat.send(kb['id'], 'TCP 1', 'one')
    second = chat.send(kb['id'], 'TCP 2', 'two')
    repository.delete_conversation(second['id'])
    originals = repository.home / 'originals' / kb['id']
    KnowledgeService(repository, settings).delete_kb(kb['id'])
    assert originals.exists() and repository.list_kbs() == [] and repository.list_conversations()['items'] == []
    with pytest.raises(MiniimaError, match='回收站'):
        repository.create_kb(kb['name'], settings)
    with pytest.raises(MiniimaError, match='先恢复'):
        repository.restore('conversation', second['id'])
    repository.restore('kb', kb['id'])
    assert repository.list_conversations()['items'][0]['id'] == first['id']
    repository.restore('conversation', second['id'])
    assert repository.list_conversations()['total'] == 2
    repository.delete_conversation(first['id'])
    TrashService(repository).purge('conversation', first['id'])
    assert originals.exists() and repository.list_documents(kb['id'])
    repository.delete_conversation(second['id'])
    repository.delete_kb(kb['id'])
    TrashService(repository).empty()
    assert not originals.exists() and repository.list_trash() == []
    assert repository.diagnostics()['foreign_key_errors'] == 0


def test_missing_chunk_snapshot_still_readable(tmp_path, repository, settings, provider):
    kb, chat, _ = setup_chat(tmp_path, repository, settings, provider)
    detail = chat.send(kb['id'], 'TCP', 'request')
    with repository.connection() as connection, connection:
        connection.execute('DELETE FROM chunks')
    citation = repository.get_conversation(detail['id'])['messages'][1]['citations'][0]
    assert citation['chunk_id'] is None and 'TCP' in citation['content']


def test_pagination_and_binding(repository, settings):
    first = repository.create_kb('一', settings)
    second = repository.create_kb('二', settings)
    for n in range(53):
        repository.save_answer(first['id'], f'问题{n}', '回答', [])
    page = repository.list_conversations()
    assert len(page['items']) == 50 and page['total'] == 53 and page['has_more']
    assert len(repository.list_conversations(50)['items']) == 3
    with pytest.raises(MiniimaError, match='另一个知识库'):
        repository.begin_turn(second['id'], '跨知识库', 'other', page['items'][0]['id'])


def test_cli_delete_restore_purge_confirmation(repository, settings, monkeypatch):
    monkeypatch.setenv('MINIIMA_HOME', str(repository.home))
    kb = repository.create_kb('命令行回收', settings)
    runner = CliRunner()
    assert runner.invoke(app, ['kb', 'delete', kb['name'], '--yes']).exit_code == 0
    assert kb['id'] in runner.invoke(app, ['trash', 'list']).output
    assert runner.invoke(app, ['trash', 'restore', 'kb', kb['id']]).exit_code == 0
    assert repository.get_kb(kb['id'])
    runner.invoke(app, ['kb', 'delete', kb['name'], '--yes'])
    assert runner.invoke(app, ['trash', 'purge', 'kb', kb['id']], input='n\n').exit_code == 0
    assert repository.list_trash()
    assert runner.invoke(app, ['trash', 'purge', 'kb', kb['id'], '--yes']).exit_code == 0
    assert repository.list_trash() == []


def test_cleanup_failure_keeps_the_knowledge_base_in_trash(tmp_path, repository, settings, provider, monkeypatch):
    kb, _, _ = setup_chat(tmp_path, repository, settings, provider)
    repository.delete_kb(kb['id'])
    def denied(path):
        raise PermissionError('simulated locked original')
    monkeypatch.setattr('miniima.application.trash.shutil.rmtree', denied)
    with pytest.raises(PermissionError):
        TrashService(repository).purge('kb', kb['id'])
    assert repository.list_trash()[0]['id'] == kb['id']
    repository.restore('kb', kb['id'])
    assert repository.list_documents(kb['id'])
