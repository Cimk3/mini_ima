import io
import json
import sys
from pathlib import Path

from miniima.application.generation import GenerationRun

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'desktop' / 'backend'))
from worker import Dispatcher, serve

from test_generation import streaming


def test_reserved_generation_can_be_cancelled_while_queued_and_exported(streaming):
    knowledge, kb, _ = streaming
    dispatcher = Dispatcher(knowledge.repository.home)
    dispatcher.service = lambda: knowledge
    requests = [
        {'id': 'generate', 'method': 'conversations.send', 'progress': True,
         'params': {'kb': kb['id'], 'question': 'TCP 是什么？', 'request_id': 'ipc-stop', 'stream': True}},
        {'id': 'cancel', 'method': 'conversations.cancel', 'params': {'request_id': 'ipc-stop'}},
        {'id': 'list', 'method': 'conversations.list', 'params': {}},
    ]
    output = io.StringIO()
    serve(dispatcher, io.StringIO(''.join(json.dumps(item) + '\n' for item in requests)), output)
    responses = [json.loads(line) for line in output.getvalue().splitlines()]
    final = [item for item in responses if item['id'] == 'generate' and 'result' in item]
    assert len(final) == 1 and final[0]['result']['messages'][0]['status'] == 'interrupted'
    assert next(item for item in responses if item['id'] == 'cancel')['result']['accepted']
    assert any(item.get('event', {}).get('type') == 'started' for item in responses)
    detail = final[0]['result']
    exported = dispatcher.handle({'id': 'export', 'method': 'conversations.export', 'params': {'conversation_id': detail['id']}})
    assert '已停止生成' in exported['result']['markdown']
    assert not dispatcher.generations.runs
