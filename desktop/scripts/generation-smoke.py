"""Frozen-backend acceptance against a local, credential-free OpenAI fixture.

All files and optional UI processes live under a new desktop/build directory.
--ui keeps the local fixture alive for native window verification until stdin closes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import queue
import shutil
import sqlite3
import subprocess
import threading
import time
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

DESKTOP = Path(__file__).resolve().parents[1]


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, *args):
        pass

    def respond(self, data):
        payload = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self):
        try:
            assert self.headers.get('Authorization') == 'Bearer miniima-test-only'
            data = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            if self.path.endswith('/embeddings'):
                if any('慢检索' in item for item in data['input']):
                    time.sleep(2)
                self.respond({'object': 'list', 'model': 'fixture-embedding', 'data': [
                    {'object': 'embedding', 'index': index, 'embedding': [1., 0., 0., 0., 0., 0., 0., 0.]}
                    for index, _ in enumerate(data['input'])], 'usage': {'prompt_tokens': 1, 'total_tokens': 1}})
                return
            assert self.path.endswith('/chat/completions')
            payload = json.loads(data['messages'][-1]['content'])
            question = payload.get('question', 'TCP')
            text = 'TCP 三次握手用于同步序列号，并确认双方通信能力。[1]'
            if 'conversation' in payload:
                text = question
            if '[无效引用]' in question:
                text = '这段回答包含无效来源。[99]'
            if not data.get('stream'):
                self.respond({'id': 'fixture', 'object': 'chat.completion', 'created': 1, 'model': 'fixture-chat',
                    'choices': [{'index': 0, 'finish_reason': 'stop', 'message': {'role': 'assistant', 'content': text}}]})
                return
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.send_header('Connection', 'close')
            self.end_headers()
            self.close_connection = True
            if '[长回答]' in question:
                text = ('TCP 通过握手建立可靠连接。' * 100) + '[1]'
            for offset in range(0, len(text), 5):
                chunk = {'id': 'fixture', 'object': 'chat.completion.chunk', 'created': 1, 'model': 'fixture-chat',
                    'choices': [{'index': 0, 'delta': {'content': text[offset:offset + 5]}, 'finish_reason': None}]}
                self.wfile.write(('data: ' + json.dumps(chunk, ensure_ascii=False) + '\n\n').encode())
                self.wfile.flush()
                if '[断线]' in question:
                    return
                time.sleep(.25 if '[长回答]' in question else .10)
            chunk['choices'] = [{'index': 0, 'delta': {}, 'finish_reason': 'stop'}]
            self.wfile.write(('data: ' + json.dumps(chunk) + '\n\ndata: [DONE]\n\n').encode())
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass


class Backend:
    def __init__(self, executable: Path, home: Path):
        env = {name: value for name, value in os.environ.items() if not name.startswith('MINIIMA_')}
        env.update(MINIIMA_HOME=str(home), PYTHONIOENCODING='utf-8', PYTHONUTF8='1')
        self.env = env
        self.process = subprocess.Popen([str(executable)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, encoding='utf-8', env=env, creationflags=subprocess.CREATE_NO_WINDOW)
        self.output = queue.Queue()
        self.saved = {}
        self.sequence = 0
        def read():
            for line in self.process.stdout:
                self.output.put(json.loads(line))
        threading.Thread(target=read, daemon=True).start()

    def send(self, method, params=None, *, progress=False):
        self.sequence += 1
        identifier = str(self.sequence)
        self.process.stdin.write(json.dumps({'id': identifier, 'method': method, 'params': params or {}, 'progress': progress}) + '\n')
        self.process.stdin.flush()
        return identifier

    def receive(self, identifier, on_event=lambda event: None):
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            item = self.saved.pop(identifier, None)
            if item is None:
                item = self.output.get(timeout=max(.1, deadline - time.monotonic()))
            if item['id'] != identifier:
                self.saved[item['id']] = item
                continue
            if 'event' in item:
                on_event(item['event'])
                continue
            assert 'error' not in item, item.get('error', {}).get('message')
            return item['result']
        raise TimeoutError('Frozen backend did not finish its request')

    def call(self, method, params=None, **kwargs):
        return self.receive(self.send(method, params, **kwargs))

    def close(self):
        try:
            self.call('shutdown')
            self.process.wait(timeout=10)
            assert self.process.returncode == 0
        finally:
            if self.process.poll() is None:
                self.process.kill()
                self.process.wait(timeout=10)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--old-package', type=Path)
    parser.add_argument('--ui', action='store_true')
    args = parser.parse_args()
    root = DESKTOP / 'build' / f'generation-smoke-{time.time_ns()}'
    install, home = root / 'install', root / 'home'
    install.mkdir(parents=True)
    for name in ('Miniima.exe', 'miniima-backend.exe', 'README.md'):
        shutil.copy2(DESKTOP / 'dist' / 'Miniima' / name, install / name)
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    seed_executable = install / 'miniima-backend.exe'
    if args.old_package:
        old = root / 'old-install'
        old.mkdir()
        with zipfile.ZipFile(args.old_package) as package:
            for name in ('Miniima.exe', 'miniima-backend.exe', 'README.md'):
                (old / name).write_bytes(package.read('Miniima/' + name))
        seed_executable = old / 'miniima-backend.exe'
    seed = Backend(seed_executable, home)
    try:
        seed.call('initialize')
        address = f'http://127.0.0.1:{server.server_port}/v1'
        seed.call('settings.update', {'values': {'api_key': 'miniima-test-only', 'base_url': address,
            'chat_model': 'fixture-chat', 'embedding_api_key': 'miniima-test-only', 'embedding_base_url': address,
            'embedding_model': 'fixture-embedding', 'embedding_dimension': 8, 'retrieval_engine': 'cpp'}})
        kb = seed.call('kb.create', {'name': '0.3.0 验收资料'})
        source = root / '中文测试资料.md'
        source.write_text('# TCP\n\nTCP 三次握手用于同步序列号，并确认双方通信能力。', encoding='utf-8')
        seed.call('docs.import', {'kb': kb['id'], 'path': str(source)})
        legacy = seed.call('conversations.send', {'kb': kb['id'], 'question': '升级前的 TCP 问题', 'request_id': 'legacy'})
    finally:
        seed.close()
    configuration = hashlib.sha256((home / 'config.json').read_bytes()).hexdigest()
    backend = Backend(install / 'miniima-backend.exe', home)
    results = []
    try:
        backend.call('initialize')
        assert backend.call('conversations.get', {'conversation_id': legacy['id']})['messages'] == legacy['messages']
        results.append('0.2.2 conversation/configuration/schema compatibility')
        common = {'kb': kb['id'], 'conversation_id': legacy['id']}
        first_delta = []
        identifier = backend.send('conversations.send', {**common, 'question': '流式解释 TCP', 'request_id': 'stream'}, progress=True)
        detail = backend.receive(identifier, lambda event: first_delta.append(time.monotonic()) if event['type'] == 'delta' else None)
        assert first_delta and time.monotonic() - first_delta[0] > .2 and detail['messages'][-1]['citations']
        results.append('real SDK SSE text arrives before completion; C++ retrieval and citation snapshots')
        cancel_ids = []
        def stop(event):
            if event['type'] == 'delta' and not cancel_ids:
                cancel_ids.append(backend.send('conversations.cancel', {'request_id': 'stop'}))
        identifier = backend.send('conversations.send', {**common, 'question': '停止 TCP 回答', 'request_id': 'stop'}, progress=True)
        partial = backend.receive(identifier, stop)
        assert backend.receive(cancel_ids[0])['accepted']
        assert partial['messages'][-1]['status'] == 'interrupted' and partial['messages'][-1]['content']
        assert not partial['messages'][-1]['citations']
        retried = backend.call('conversations.retry', {'request_id': 'stop'}, progress=True)
        assert len(retried['messages']) == len(partial['messages']) and retried['messages'][-1]['citations']
        results.append('stop closes stream, preserves partial answer; retry replaces in place')
        failed = backend.call('conversations.send', {**common, 'question': 'TCP [断线]', 'request_id': 'broken'}, progress=True)
        assert failed['messages'][-1]['status'] == 'failed' and failed['messages'][-1]['content']
        invalid = backend.call('conversations.send', {**common, 'question': 'TCP [无效引用]', 'request_id': 'invalid'}, progress=True)
        assert '无效来源编号' in invalid['messages'][-1]['content'] and not invalid['messages'][-1]['citations']
        normal = backend.call('conversations.send', {**common, 'question': '非流式 TCP', 'request_id': 'plain', 'stream': False}, progress=True)
        assert normal['messages'][-1]['citations']
        results.append('disconnect, invalid citations and non-streaming compatibility')
        cancelled = []
        def stop_preparation(event):
            if event.get('phase') == 'searching' and not cancelled:
                cancelled.append(backend.send('conversations.cancel', {'request_id': 'prepare-stop'}))
        identifier = backend.send('conversations.send', {**common, 'question': 'TCP 慢检索', 'request_id': 'prepare-stop'}, progress=True)
        stopped = backend.receive(identifier, stop_preparation)
        assert stopped['messages'][-1]['role'] == 'user' and stopped['messages'][-1]['status'] == 'interrupted'
        results.append('cancel during preparation without duplicate or empty assistant messages')
        # No server is required for exports and history recovery.
        if not args.ui:
            server.shutdown()
        exported = backend.call('conversations.export', {'conversation_id': legacy['id']})
        assert '第 1 轮来源' in exported['markdown'] and '第 2 轮来源' in exported['markdown']
        assert '未完成' in exported['markdown'] and '来源尚未校验' in exported['markdown']
        assert 'miniima-test-only' not in exported['markdown']
        (root / exported['filename']).write_text(exported['markdown'], encoding='utf-8')
        assert backend.call('doctor')['integrity'] == 'ok'
        results.append('offline full transcript with per-round sources and incomplete states')
    finally:
        backend.close()
    restarted = Backend(install / 'miniima-backend.exe', home)
    try:
        restarted.call('initialize')
        restored = restarted.call('conversations.get', {'conversation_id': legacy['id']})
        assert any(item['status'] == 'failed' and item['role'] == 'assistant' for item in restored['messages'])
        assert hashlib.sha256((home / 'config.json').read_bytes()).hexdigest() == configuration
        with sqlite3.connect(home / 'miniima.sqlite3') as connection:
            assert connection.execute('PRAGMA user_version').fetchone()[0] == 3
            assert connection.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        results.append('restart restores incomplete text without changing configuration or Schema 3')
    finally:
        restarted.close()
    report = {'root': str(root), 'checks': results}
    (root / 'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False), flush=True)
    if args.ui:
        child = subprocess.Popen([str(install / 'Miniima.exe')], env=restarted.env, cwd=install)
        print(json.dumps({'ui_pid': child.pid, 'install': str(install), 'home': str(home)}, ensure_ascii=False), flush=True)
        try:
            input('Press Enter after native UI verification.\n')
        finally:
            if child.poll() is None:
                child.terminate()
                child.wait(timeout=10)
            server.shutdown()
    server.server_close()


if __name__ == '__main__':
    main()
