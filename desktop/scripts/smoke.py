"""Packaged-program acceptance using an isolated home and a local Mock API."""
from __future__ import annotations

import argparse
import json
import os
import queue
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from miniima.config import Settings, save_settings
from miniima.storage.repository import Repository

DESKTOP = Path(__file__).resolve().parents[1]
ROOT = DESKTOP.parent


class MockAPI(BaseHTTPRequestHandler):
    calls = 0
    chat_delay = 0.
    fail_chat_once = False
    history_lengths = []

    def log_message(self, format, *args):
        pass

    def do_POST(self):
        MockAPI.calls += 1
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
        if self.path.endswith("embeddings"):
            vectors = []
            for i, text in enumerate(body["input"]):
                vector = [0.] * 8
                vector[0 if "TCP" in text or "握手" in text else 1 if "以太网" in text else 2] = 1.
                vectors.append({"object": "embedding", "index": i, "embedding": vector})
            result = {"object": "list", "model": "mock-embedding", "data": vectors,
                      "usage": {"prompt_tokens": 1, "total_tokens": 1}}
        else:
            messages = body['messages']
            rewriting = '独立的知识库检索问题' in messages[0]['content']
            if MockAPI.fail_chat_once and not rewriting:
                MockAPI.fail_chat_once = False
                self.send_response(401)
                self.send_header('Content-Length', '0')
                self.end_headers()
                return
            if not rewriting:
                MockAPI.history_lengths.append(len(messages) - 2)
                time.sleep(MockAPI.chat_delay)
            content = 'TCP 三次握手中第三次确认的作用是什么？' if rewriting else 'TCP 三次握手让双方确认连接可用，并同步初始序列号。[1]\n\n这是本地 Mock 接口的验收回答。'
            result = {"id": "mock", "object": "chat.completion", "created": 0, "model": "mock-chat",
                      "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant",
                          "content": content}}]}
        encoded = json.dumps(result, ensure_ascii=False).encode()
        try:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass  # Expected when the busy-close check interrupts a local request.


class Worker:
    def __init__(self, executable, env):
        self.process = subprocess.Popen([str(executable)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE, text=True, encoding='utf-8', env=env)
        self.responses, self.sequence = queue.Queue(), 0
        def read():
            for line in self.process.stdout:
                self.responses.put(json.loads(line))
            self.responses.put(None)
        threading.Thread(target=read, daemon=True).start()

    def call(self, method, *, expected_error=False, **params):
        self.sequence += 1
        identifier = str(self.sequence)
        self.process.stdin.write(json.dumps({'id': identifier, 'method': method, 'params': params}, ensure_ascii=False) + '\n')
        self.process.stdin.flush()
        response = self.responses.get(timeout=90)
        assert response and response['id'] == identifier, response
        assert ('error' in response) == expected_error, response
        return response['error'] if expected_error else response['result']

    def close(self):
        try:
            if self.process.poll() is None:
                self.call('shutdown')
                self.process.stdin.close()
                # The one-file bootloader can spend time cleaning extracted DLLs on Windows.
                assert self.process.wait(timeout=45) == 0
        finally:
            if self.process.poll() is None:
                self.process.kill()
                self.process.wait(timeout=10)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--gui", action="store_true")
    parser.add_argument("--reopen", action="store_true", help="Restart the GUI once with the same home and Mock API")
    parser.add_argument("--chat-delay", type=float, default=0., help="Delay Mock chat responses to check the busy-close dialog")
    options = parser.parse_args()
    MockAPI.chat_delay = max(0., options.chat_delay)
    server = ThreadingHTTPServer(("127.0.0.1", 0), MockAPI)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_port}/v1"
    prefix = "gui-smoke" if options.gui else "frozen-smoke"
    home = DESKTOP / "build" / f"{prefix}-{uuid.uuid4().hex[:8]}"
    repository = Repository(home)
    repository.initialize()
    settings = replace(Settings(), api_key="mock-only", base_url=url, chat_model="mock-chat",
                       embedding_api_key="mock-only", embedding_base_url=url, embedding_model="mock-embedding",
                       embedding_dimension=8, max_retries=0)
    save_settings(settings, home)
    env = {name: value for name, value in os.environ.items() if not name.startswith("MINIIMA_")}
    env.update(MINIIMA_HOME=str(home), PYTHONIOENCODING="utf-8", PYTHONUTF8="1", NO_PROXY="127.0.0.1,localhost",
               HTTP_PROXY="", HTTPS_PROXY="", ALL_PROXY="", TEMP=str(DESKTOP / "build" / "temp"), TMP=str(DESKTOP / "build" / "temp"))
    name = "桌面验收（Mock）"
    if not repository.list_kbs():
        result = subprocess.run([str(ROOT / ".venv" / "Scripts" / "python.exe"), "-m", "miniima", "kb", "create", name],
                                env=env, capture_output=True, text=True, encoding="utf-8", timeout=30)
        assert result.returncode == 0, result.stderr + result.stdout
    kb = repository.get_kb(name)
    files = DESKTOP / "build" / "验收文件 with spaces"
    files.mkdir(exist_ok=True)
    original = files / "CLI 导入样例.md"
    original.write_text("# 计算机网络\n\n## TCP 三次握手\n\nTCP 用三次握手建立连接，同步初始序列号。", encoding="utf-8")
    new_file = files / "桌面导入样例.txt"
    new_file.write_text("以太网笔记\n\n以太网共享介质使用 CSMA/CD 检测冲突。", encoding="utf-8")
    result = subprocess.run([str(ROOT / ".venv" / "Scripts" / "python.exe"), "-m", "miniima", "add", str(original), "--kb", kb["id"]],
                            env=env, capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stderr + result.stdout
    if options.gui:
        # A successful CLI ask must appear in the desktop history as its own conversation.
        MockAPI.chat_delay = 0
        result = subprocess.run([str(ROOT / '.venv' / 'Scripts' / 'python.exe'), '-m', 'miniima', 'ask', 'CLI 历史：TCP是什么？', '--kb', kb['id']],
                                env=env, capture_output=True, text=True, encoding='utf-8', timeout=30)
        assert result.returncode == 0, result.stderr + result.stdout
        MockAPI.chat_delay = max(0., options.chat_delay)
        executable = DESKTOP / "dist" / "Miniima" / "Miniima.exe"
        print(f"MOCK_HOME={home}", flush=True)
        print(f"IMPORT_FILE={new_file}", flush=True)
        for run in range(2 if options.reopen else 1):
            application = subprocess.Popen([str(executable)], env=env)
            print(f"GUI_RUN={run + 1}; GUI_PID={application.pid}", flush=True)
            returncode = application.wait()
            assert returncode == 0, f"GUI exited with {returncode}"
            print(f"GUI_CLOSED={run + 1}", flush=True)
        assert repository.diagnostics()["integrity"] == "ok"
        server.shutdown()
        print(f"GUI_EXIT={returncode}; LOCAL_MOCK_REQUESTS={MockAPI.calls}", flush=True)
        return
    worker_path = DESKTOP / 'dist' / 'Miniima' / 'miniima-backend.exe'
    worker = Worker(worker_path, env)
    def cli(*arguments):
        result = subprocess.run([str(ROOT / '.venv' / 'Scripts' / 'python.exe'), '-m', 'miniima', *arguments],
                                env=env, capture_output=True, text=True, encoding='utf-8', timeout=30)
        assert result.returncode == 0, result.stderr + result.stdout
        return result.stdout
    try:
        worker.call('initialize')
        assert worker.call('doctor')['engine'] == 'cpp'
        assert worker.call('doctor')['schema_version'] == 2
        assert worker.call('search', kb=kb['id'], question='TCP 三次握手')[0]['filename'] == original.name
        assert worker.call('ask', kb=kb['id'], question='为什么需要TCP三次握手？')['citations'][0]['filename'] == original.name
        assert worker.call('docs.import', kb=kb['id'], path=str(new_file))['imported']
        assert not worker.call('docs.import', kb=kb['id'], path=str(new_file))['imported']
        assert worker.call('connections.test', kind='embedding')['dimension'] == 8
        first = worker.call('conversations.send', kb=kb['id'], question='TCP为什么需要三次握手？', request_id='first')
        second = worker.call('conversations.send', kb=kb['id'], conversation_id=first['id'], question='那第三次呢？', request_id='second')
        assert len(second['messages']) == 4 and MockAPI.history_lengths[-1] == 2
        assert second['messages'][1]['citations'][0]['id'] != second['messages'][3]['citations'][0]['id']
        assert worker.call('conversations.get', request_id='second')['id'] == first['id']
        count = MockAPI.calls
        assert len(worker.call('conversations.send', kb=kb['id'], conversation_id=first['id'], question='那第三次呢？', request_id='second')['messages']) == 4
        assert MockAPI.calls == count
        MockAPI.fail_chat_once = True
        failed = worker.call('conversations.send', kb=kb['id'], conversation_id=first['id'], question='TCP 的作用？', request_id='retry')
        assert failed['messages'][-1]['status'] == 'failed'
        retried = worker.call('conversations.retry', request_id='retry')
        assert len(retried['messages']) == 6 and retried['messages'][-2]['status'] == 'completed'
        worker.call('conversations.delete', conversation_id=first['id'])
        assert worker.call('conversations.list')['total'] == 1  # The independent CLI-style ask remains.
        cli('trash', 'restore', 'conversation', first['id'])
        assert len(worker.call('conversations.get', conversation_id=first['id'])['messages']) == 6
        cli('kb', 'delete', kb['id'], '--yes')
        assert worker.call('kb.list') == []
        assert '不存在' in worker.call('conversations.get', conversation_id=first['id'], expected_error=True)['message']
        worker.call('trash.restore', kind='kb', item_id=kb['id'])
        assert new_file.name in cli('search', '以太网', '--kb', kb['id'])
        removable = worker.call('conversations.send', kb=kb['id'], question='TCP临时回收记录', request_id='removable')
        worker.call('conversations.delete', conversation_id=removable['id'])
        worker.call('trash.purge', kind='conversation', item_id=removable['id'])
        empty_base = worker.call('kb.create', name='清空回收测试')
        worker.call('kb.delete', kb=empty_base['id'])
        worker.call('trash.empty')
        assert worker.call('trash.list') == []
    finally:
        worker.close()
    reopened = Worker(worker_path, env)
    try:
        reopened.call('initialize')
        assert reopened.call('conversations.get', conversation_id=first['id'])['messages'] == retried['messages']
    finally:
        reopened.close()
    result = subprocess.run([str(ROOT / ".venv" / "Scripts" / "python.exe"), "-m", "miniima", "search", "以太网", "--kb", kb["id"]],
                            env=env, capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0 and new_file.name in result.stdout
    assert repository.diagnostics()["integrity"] == "ok"
    server.shutdown()
    print(f'MOCK_HOME={home}')
    print('PASS: packaged Python/C++ + multi-turn/history/citations + failure/retry/dedup + CLI/trash interoperability + restart/shutdown')


if __name__ == "__main__":
    main()
