"""Private UTF-8 JSON-lines transport. No HTTP server or CLI parsing."""
from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, fields, replace
from pathlib import Path
from typing import TextIO

from miniima.application.service import KnowledgeService
from miniima.application.conversations import ConversationService
from miniima.application.trash import TrashService
from miniima.application.generation import GenerationRegistry, generate
from miniima.application.exporting import export_conversation
from miniima.config import Settings, data_home, load_settings, qwen_settings, save_settings
from miniima.errors import ConfigurationError, MiniimaError, ProviderError
from miniima.providers.openai_compatible import OpenAICompatibleProvider
from miniima.storage.repository import Repository
from miniima.vector import create_index
from updates import UpdateService


class RequestError(MiniimaError):
    pass


def public_settings(settings: Settings) -> dict:
    values = asdict(settings)
    values.pop("api_key")
    values.pop("embedding_api_key")
    return {**values, "api_key_configured": bool(settings.api_key),
            "embedding_api_key_configured": bool(settings.embedding_model and settings.embedding_dimension > 0
                                                  and settings.embedding_key),
            "embedding_ready": bool(settings.embedding_model and settings.embedding_dimension > 0
                                    and settings.embedding_key)}


class Dispatcher:
    def __init__(self, home: Path | None = None, provider_factory=OpenAICompatibleProvider):
        self.home = home or data_home()
        self.repository = Repository(self.home)
        self.provider_factory = provider_factory
        self.initialized = False
        self.updates = UpdateService()
        self.generations = GenerationRegistry()

    def settings_snapshot(self) -> dict:
        saved = load_settings(self.home, use_env=False)
        effective = load_settings(self.home)
        overrides = [field.name for field in fields(Settings)
                     if f"MINIIMA_{field.name.upper()}" in os.environ]
        return {"saved": public_settings(saved), "effective": public_settings(effective),
                "overrides": overrides, "home": str(self.home)}

    def service(self) -> KnowledgeService:
        settings = load_settings(self.home)
        return KnowledgeService(self.repository, settings, self.provider_factory(settings))

    @staticmethod
    def text(params: dict, name: str) -> str:
        value = params.get(name)
        if not isinstance(value, str) or not value.strip():
            raise RequestError("请求缺少必要的文本参数。")
        return value

    def dispatch(self, method: str, params: dict):
        if method == 'conversations.cancel':
            return {'accepted': self.generations.cancel(self.text(params, 'request_id'))}
        if method == 'conversations.export':
            return export_conversation(self.repository.get_conversation(self.text(params, 'conversation_id')))
        if method == 'web.open':
            import webbrowser
            from miniima.providers.web_search import public_url
            url = public_url(self.text(params, 'url'))
            if not url:
                raise RequestError('只支持有效的 HTTP / HTTPS 网页链接。')
            if not webbrowser.open(url):
                raise RequestError('无法打开默认浏览器，请复制网页链接后手动打开。')
            return {'opened': True}
        if method == "initialize":
            self.repository.initialize()
            if not self.initialized:
                self.repository.recover_interrupted()
                self.initialized = True
            return {"knowledge_bases": self.repository.list_kbs(), "settings": self.settings_snapshot()}
        if method == 'conversations.list':
            return self.repository.list_conversations(params.get('offset', 0), params.get('limit', 50), params.get('query', ''))
        if method == 'conversations.rename':
            return self.repository.rename_conversation(self.text(params, 'conversation_id'), self.text(params, 'title'))
        if method == 'updates.check':
            return self.updates.check(self.text(params, 'current_version'))
        if method == 'updates.prepare':
            return self.updates.prepare(self.text(params, 'current_version'), Path(self.text(params, 'app_dir')),
                                        self.text(params, 'expected_version'))
        if method == 'updates.status':
            return self.updates.status()
        if method == 'conversations.get':
            if 'request_id' in params:
                conversation, _ = self.repository.retry_details(self.text(params, 'request_id'))
                return self.repository.get_conversation(conversation['id'])
            return self.repository.get_conversation(self.text(params, 'conversation_id'))
        if method == 'conversations.send':
            if not isinstance(params.get('web_search', False), bool):
                raise RequestError('联网搜索选项无效。')
            conversation_id = params.get('conversation_id')
            if conversation_id is not None and (not isinstance(conversation_id, str) or not conversation_id.strip()):
                raise RequestError('对话编号无效。')
            return ConversationService(self.service()).send(self.text(params, 'kb'), self.text(params, 'question'),
                self.text(params, 'request_id'), conversation_id, web_search=params.get('web_search', False))
        if method == 'conversations.retry':
            return ConversationService(self.service()).retry(self.text(params, 'request_id'))
        if method == 'conversations.delete':
            self.repository.delete_conversation(self.text(params, 'conversation_id'))
            return {'deleted': True}
        if method == 'trash.list':
            return self.repository.list_trash()
        if method in ('trash.restore', 'trash.purge'):
            kind, identifier = self.text(params, 'kind'), self.text(params, 'item_id')
            if method == 'trash.restore':
                self.repository.restore(kind, identifier)
            else:
                TrashService(self.repository).purge(kind, identifier)
            return {'done': True}
        if method == 'trash.empty':
            TrashService(self.repository).empty()
            return {'done': True}
        if method == "kb.list":
            return self.repository.list_kbs()
        if method == "kb.create":
            return self.repository.create_kb(self.text(params, "name"), load_settings(self.home))
        if method == "kb.delete":
            return self.service().delete_kb(self.text(params, "kb"))
        if method == "docs.list":
            return self.repository.list_documents(self.text(params, "kb"))
        if method == "docs.preview":
            return self.repository.document_excerpt(self.text(params, "kb"), self.text(params, "document_id"))
        if method == "docs.import":
            document, imported = self.service().add(Path(self.text(params, "path")), self.text(params, "kb"))
            return {"document": document, "imported": imported}
        if method in ("search", "ask"):
            query, kb = self.text(params, "question"), self.text(params, "kb")
            top_k = params.get("top_k", 5)
            if type(top_k) is not int or not 1 <= top_k <= 100:
                raise RequestError("检索数量应为 1–100。")
            service = self.service()
            if method == "search":
                return service.search(query, kb, top_k)
            return asdict(service.ask(query, kb, top_k))
        if method == "settings.get":
            return self.settings_snapshot()
        if method == "settings.update":
            defaults = asdict(Settings())
            updates = params.get("values")
            if not isinstance(updates, dict) or set(updates) - defaults.keys():
                raise RequestError("配置请求包含未知字段。")
            updates = dict(updates)
            for name, value in tuple(updates.items()):
                expected = type(defaults[name])
                if expected is float:
                    valid = type(value) in (int, float)
                else:
                    valid = type(value) is expected
                if not valid:
                    raise RequestError("配置项的类型不正确。")
                if name.endswith("api_key"):
                    if not value.strip():
                        updates.pop(name)  # Empty entry preserves an already configured key.
                    else:
                        updates[name] = value.strip()
            settings = replace(load_settings(self.home, use_env=False), **updates)
            settings.validate()
            save_settings(settings, self.home)
            return self.settings_snapshot()
        if method == "settings.qwen":
            settings = qwen_settings(load_settings(self.home, use_env=False))
            return public_settings(settings)  # Preview a preset; save is an explicit action.
        if method == "connections.test":
            kind = params.get("kind")
            provider = self.provider_factory(load_settings(self.home))
            if kind == "chat":
                provider.test_chat()
                return {"kind": kind, "connected": True}
            if kind == "embedding":
                dimension = int(provider.test_embedding())
                return {"kind": kind, "connected": True, "dimension": dimension}
            raise RequestError("请选择问答或向量连接测试。")
        if method == "doctor":
            diagnostics = self.repository.diagnostics()
            settings = load_settings(self.home)
            create_index(max(1, settings.embedding_dimension), settings.retrieval_engine)
            return {**diagnostics, "engine": settings.retrieval_engine, "home": str(self.home)}
        if method == "shutdown":
            return {"shutdown": True}
        raise RequestError("不支持的桌面请求。")

    def reserve_generation(self, request, emit):
        if (isinstance(request, dict) and request.get('progress') is True
                and request.get('method') in ('conversations.send', 'conversations.retry')):
            params = request.get('params', {})
            if not isinstance(params, dict):
                raise RequestError('请求格式无效。')
            identifier = self.text(params, 'request_id')
            return self.generations.reserve(identifier,
                lambda event: emit({'id': request.get('id'), 'event': event}))
        return None

    def handle(self, request, *, run=None) -> dict:
        identifier = request.get("id") if isinstance(request, dict) else None
        try:
            if not isinstance(request, dict) or not isinstance(identifier, (str, int)):
                raise RequestError("请求格式无效。")
            method, params = request.get("method"), request.get("params", {})
            if not isinstance(method, str) or not isinstance(params, dict):
                raise RequestError("请求格式无效。")
            if run is None:
                run = self.reserve_generation(request, lambda event: None)
            if run:
                if not isinstance(params.get('stream', True), bool) or not isinstance(params.get('web_search', False), bool):
                    raise RequestError('生成选项无效。')
                if method == 'conversations.retry':
                    conversation, user = self.repository.retry_details(run.request_id)
                    kb, question, conversation_id = conversation['knowledge_base_id'], user['content'], conversation['id']
                    web_search = bool(user['web_search'])
                else:
                    kb, question = self.text(params, 'kb'), self.text(params, 'question')
                    conversation_id = params.get('conversation_id')
                    if conversation_id is not None and (not isinstance(conversation_id, str) or not conversation_id.strip()):
                        raise RequestError('对话编号无效。')
                    web_search = params.get('web_search', False)
                result = asyncio.run(generate(self.service(), run, kb, question, conversation_id,
                    retry=method == 'conversations.retry', web_search=web_search, stream=params.get('stream', True)))
                return {'id': identifier, 'result': result}
            return {"id": identifier, "result": self.dispatch(method, params)}
        except MiniimaError as exc:
            code = "configuration" if isinstance(exc, ConfigurationError) else (
                "provider" if isinstance(exc, ProviderError) else "request")
            return {"id": identifier, "error": {"code": code, "message": str(exc)}}
        except (OSError, sqlite3.Error, ValueError, TypeError):
            return {"id": identifier, "error": {"code": "operation", "message": "操作失败，请检查文件、设置及数据完整性。"}}
        except Exception:
            # Neither an exception repr nor request params are written to a log.
            return {"id": identifier, "error": {"code": "internal", "message": "本地处理出现异常，请重试或重新启动应用。"}}
        finally:
            if run:
                self.generations.release(run)


def serve(dispatcher: Dispatcher, input_stream: TextIO, output_stream: TextIO) -> None:
    output_lock = threading.Lock()

    def write(response):
        with output_lock:
            output_stream.write(json.dumps(response, ensure_ascii=False, allow_nan=False) + "\n")
            output_stream.flush()

    def process(request, run=None):
        write(dispatcher.handle(request, run=run))

    # Keep offline history/trash reads responsive while a model request is running.
    with ThreadPoolExecutor(max_workers=2, thread_name_prefix='miniima-turn') as executor:
        for line in input_stream:
            try:
                request = json.loads(line)
            except (ValueError, TypeError):
                write({"id": None, "error": {"code": "request", "message": "请求不是有效的 JSON。"}})
                continue
            if isinstance(request, dict) and request.get('method') in ('conversations.send', 'conversations.retry', 'updates.check', 'updates.prepare'):
                try:
                    run = dispatcher.reserve_generation(request, write)
                except MiniimaError as error:
                    write({'id': request.get('id'), 'error': {'code': 'request', 'message': str(error)}})
                    continue
                executor.submit(process, request, run)
                continue
            response = dispatcher.handle(request)
            write(response)
            if isinstance(request, dict) and request.get("method") == "shutdown" and "result" in response:
                break


def main() -> None:
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="strict")
    serve(Dispatcher(), sys.stdin, sys.stdout)


if __name__ == "__main__":
    main()
