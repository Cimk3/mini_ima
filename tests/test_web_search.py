import io
import sqlite3
from importlib.resources import files
from urllib.parse import parse_qs, urlsplit

import pytest

from miniima.application.conversations import ConversationService
from miniima.application.service import KnowledgeService
from miniima.errors import MiniimaError, ProviderError
from miniima.providers import web_search
from miniima.storage.repository import Repository


HTML = b'''<div class="result"><a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.org%2Ftcp">TCP <b>reference</b></a>
<a class="result__snippet">Three <b>messages</b> establish a connection.</a></div>
<a class="result__a" href="javascript:alert(1)">Unsafe</a><div class="result__snippet">Ignore</div>
<a class="result__a" href="https://example.org/tcp">Duplicate</a><div class="result__snippet">Same</div>'''
RSS = b'''<rss><channel><item><link>https://example.org/tcp</link><title>TCP reference</title>
<description>Three messages establish a connection.</description></item></channel></rss>'''


def fake_search(monkeypatch, payload=RSS):
    calls = []
    def open_request(request, timeout):
        calls.append((request, timeout))
        return io.BytesIO(payload)
    monkeypatch.setattr(web_search, 'urlopen', open_request)
    return calls


def test_web_search_parses_bounded_snapshots_without_credentials(monkeypatch):
    calls = fake_search(monkeypatch)
    matches = web_search.search_web('TCP 中文问题')
    assert len(matches) == 1
    assert matches[0]['filename'] == 'TCP reference'
    assert matches[0]['content'] == 'Three messages establish a connection.'
    assert matches[0]['chunk_id'] is None
    assert matches[0]['source_metadata']['url'] == 'https://example.org/tcp'
    request, timeout = calls[0]
    assert parse_qs(urlsplit(request.full_url).query) == {'q': ['TCP 中文问题'], 'format': ['rss']}
    assert not any('key' in key.lower() or key.lower() == 'authorization' for key in request.headers)
    assert timeout == 8


def test_html_fallback_unwraps_redirects_and_removes_unsafe_and_duplicate_urls(monkeypatch):
    calls = fake_search(monkeypatch, HTML)
    matches = web_search.search_web('TCP')
    assert len(calls) == 2 and len(matches) == 1
    assert matches[0]['source_metadata']['search_engine'] == 'DuckDuckGo'
    assert matches[0]['source_metadata']['url'] == 'https://example.org/tcp'
    assert matches[0]['filename'] == 'TCP reference'
    assert matches[0]['content'] == 'Three messages establish a connection.'


@pytest.mark.parametrize('payload', [b'<html>captcha</html>', b'x' * 1_000_001], ids=['challenge', 'oversized'])
def test_web_search_reports_unavailable_instead_of_fabricating_results(monkeypatch, payload):
    fake_search(monkeypatch, payload)
    with pytest.raises(ProviderError, match='联网搜索'):
        web_search.search_web('TCP')


def test_web_turn_retry_retains_mode_and_persists_citation_snapshot(repository, settings, provider, monkeypatch):
    calls = fake_search(monkeypatch)
    kb = repository.create_kb('联网测试', settings)
    chat = ConversationService(KnowledgeService(repository, settings, provider))
    original = provider.chat
    provider.chat = lambda messages: (_ for _ in ()).throw(ProviderError('模拟 API 超时'))
    failed = chat.send(kb['id'], 'TCP 当前规范', 'web-request', web_search=True)
    assert failed['messages'][0]['status'] == 'failed'
    assert failed['messages'][0]['web_search'] == 1
    provider.chat = original
    completed = chat.retry('web-request')
    assert len(calls) == 2
    assert len(completed['messages']) == 2
    citation = completed['messages'][1]['citations'][0]
    assert citation['source_metadata']['url'] == 'https://example.org/tcp'
    assert citation['chunk_id'] is None
    assert citation['id'] != 'web-request'
    assert Repository(repository.home).get_conversation(completed['id'])['messages'] == completed['messages']
    with pytest.raises(MiniimaError, match='请求编号'):
        chat.send(kb['id'], 'TCP 当前规范', 'web-request', web_search=False)
    # A normal local question performs no web request.
    chat.send(kb['id'], '本地资料', 'local-request')
    assert len(calls) == 2


def test_v2_upgrade_backs_up_existing_database_and_defaults_web_off(tmp_path):
    home = tmp_path / 'old-home'
    home.mkdir()
    with sqlite3.connect(home / 'miniima.sqlite3') as connection:
        for name in ['001_initial.sql', '002_conversations_and_trash.sql']:
            connection.executescript(files('miniima.storage').joinpath('migrations', name).read_text(encoding='utf-8'))
        connection.execute('PRAGMA user_version=2')
    repository = Repository(home)
    repository.initialize()
    with repository.connection() as connection:
        assert connection.execute('PRAGMA user_version').fetchone()[0] == 3
        assert connection.execute("SELECT dflt_value FROM pragma_table_info('messages') WHERE name='web_search'").fetchone()[0] == '0'
    backups = list((home / 'backups').glob('*.sqlite3'))
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as connection:
        assert connection.execute('PRAGMA user_version').fetchone()[0] == 2


@pytest.mark.parametrize('url', ['file:///local', 'javascript:alert(1)', 'https://user:pass@example.org', 'https://example.org/\ncmd'])
def test_external_url_rejects_non_web_and_embedded_credentials(url):
    assert web_search.public_url(url) is None
