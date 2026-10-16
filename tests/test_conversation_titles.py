import pytest

from miniima.errors import MiniimaError
from miniima.storage.repository import Repository


def test_titles_search_all_history_and_rename_survives_restart(repository, settings):
    kb = repository.create_kb('历史标题', settings)
    first = repository.save_answer(kb['id'], '早期的 TCP 问题', '保留回答', [])
    for number in range(54):
        repository.save_answer(kb['id'], f'其他问题 {number}', '回答', [])
    assert first not in [row['id'] for row in repository.list_conversations()['items']]
    assert repository.list_conversations(query='tcp')['items'][0]['id'] == first
    before = repository.get_conversation(first)['messages']
    repository.rename_conversation(first, '  网络复习 100%_  ')
    restarted = Repository(repository.home)
    assert restarted.get_conversation(first)['title'] == '网络复习 100%_'
    assert restarted.get_conversation(first)['messages'] == before
    assert restarted.list_conversations(query='%_')['total'] == 1
    with pytest.raises(MiniimaError, match='标题'):
        repository.rename_conversation(first, '   ')
    repository.delete_conversation(first)
    assert restarted.list_conversations(query='网络复习')['total'] == 0
    with pytest.raises(MiniimaError, match='回收站'):
        repository.rename_conversation(first, '不应修改')
